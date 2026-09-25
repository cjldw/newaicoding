"""
R3.F2 知识条目超管全权限开放 — Red 阶段失败测试
================================================
覆盖 DEVPLAN/R3.F2.md「接口契约变更」「permissions 结构扩展」「测试验证逻辑」,
全部用「超管且非该项目成员」场景(项目 owner 为普通用户,超管不在成员表):

1. GET 项目级条目 200 / GET code 200 / GET branches 200(超管直通)
2. POST /projects/{pid}/knowledge 创建 200(超管非成员)
3. PATCH 人工条目 200 全字段 / DELETE 200 / publish 200 / promote 200
4. detail permissions:超管 can_edit/can_delete/can_publish/can_promote 全 true
   (Red 主战场:entry_permissions 现只回 3 键,can_publish/can_promote 缺失)
5. AI 条目:超管 PATCH content → 400+20013(白名单不受超管影响);PATCH tags → 200
6. 普通非成员用户行为零回归(403/1901 基线)

脚手架照抄 test_knowledge_entry_edit_delete.py / test_knowledge_entry_detail.py:
首注册用户恒 superadmin(registered_user/auth_headers 即超管身份,本项目外=非成员),
普通用户(owner)一律用 _mk_user 后续注册;GitLab 外呼用 httpx.MockTransport +
conftest autouse patch 注入。每测试必带 registered_user 占首注册引导位。
"""
import base64
import uuid
from urllib.parse import unquote

import httpx
import pytest
from sqlalchemy import select

KB_AI_ONLY_TAGS = 20013   # R3 契约:AI 条目仅支持编辑标签(超管亦不豁免)
NO_PROJECT_PERMISSION = 1901

HUMAN_EDITABLE_FIELDS = {"title", "content", "tags", "type", "source_links"}


# ---------------------------------------------------------------------------
# 测试辅助:用户 / 项目 / repo / 成员 / 条目(沿用既有 R1/R2/R3 测试写法)
# ---------------------------------------------------------------------------
async def _mk_user(client):
    """注册并登录一个新用户,返回 {headers, user_id}(首注册用户恒 superadmin,这里是后续普通用户)"""
    phone = f"135{str(uuid.uuid4().int)[:8]}"
    resp = await client.post("/api/auth/register", json={"phone": phone, "password": "Test1234"})
    assert resp.status_code == 200 and resp.json()["code"] == 0
    user_id = resp.json()["data"]["user_id"]
    resp = await client.post("/api/auth/login", json={"phone": phone, "password": "Test1234"})
    assert resp.status_code == 200
    headers = {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}
    return {"headers": headers, "user_id": user_id}


async def _mk_project(db_session, owner_id):
    from app.models.project import Project

    p = Project(
        name=f"R3F2 超管项目 {uuid.uuid4().hex[:6]}",
        slug=f"r3f2-{uuid.uuid4().hex[:8]}",
        owner_id=owner_id,
        status="active",
        visibility="private",
    )
    db_session.add(p)
    await db_session.flush()
    return p


async def _mk_repo(db_session, project_id, gitlab_repo_id=None):
    from app.models.project import ProjectRepo

    repo = ProjectRepo(
        project_id=project_id,
        role="main",
        gitlab_repo_url=f"https://gitlab.example.com/grp/repo-{uuid.uuid4().hex[:6]}.git",
        gitlab_repo_id=gitlab_repo_id or (uuid.uuid4().int % 100000),
        gitlab_bind_type="auto",
        created_by=str(uuid.uuid4()),   # project_repos.created_by NOT NULL(既有测试同款必填)
    )
    db_session.add(repo)
    await db_session.flush()
    return repo


async def _mk_member(db_session, project_id, user_id, role="viewer"):
    from app.models.project_member import ProjectMember

    m = ProjectMember(project_id=project_id, user_id=user_id, role=role,
                      invited_by=user_id)
    db_session.add(m)
    await db_session.flush()
    return m


async def _mk_entry(db_session, project_id, created_by="human", status="published",
                    title=None, type="code_snippet", source_links=None):
    """直插条目(不带 created_by_user_id = 他人/历史行,归属判定不依赖创建者)"""
    from app.models.knowledge_entry import KnowledgeEntry

    e = KnowledgeEntry(
        project_id=project_id,
        req_id="manual",
        type=type,
        title=title or f"R3F2 条目 {uuid.uuid4().hex[:6]}",
        content="重试装饰器用法说明",
        tags=["python"],
        source_links=source_links or [],
        created_by=created_by,
        status=status,
    )
    db_session.add(e)
    await db_session.flush()
    return e


def _code_link(repo_id, branch="main", paths=None):
    """R1 定稿的 source_links code 对象(A 型)"""
    return [{"type": "code", "repo_id": repo_id, "branch": branch,
             "paths": paths or []}]


async def _create_entry_api(client, headers, project_id, **overrides):
    """POST /api/projects/{pid}/knowledge(人工创建,直接 published;R1 存量接口)"""
    payload = {
        "type": "code_snippet",
        "title": f"R3F2 创建条目 {uuid.uuid4().hex[:6]}",
        "content": "重试装饰器用法说明",
        "tags": ["python"],
    }
    payload.update(overrides)
    resp = await client.post(f"/api/projects/{project_id}/knowledge",
                             json=payload, headers=headers)
    assert resp.status_code == 200, (
        f"超管(非项目成员)创建应 200,实际 {resp.status_code} {resp.text[:160]}"
    )
    assert resp.json()["code"] == 0, f"code={resp.json().get('code')}"
    return resp.json()["data"]["entry_id"]


def _assert_biz_400(resp, code=None):
    """服务端校验失败契约:HTTP 400 + 统一响应体非零业务错误码(非 422/非 500)"""
    assert resp.status_code == 400, (
        f"应 400,实际 {resp.status_code}(校验未实现时通常 200;pydantic 拦截则 422)"
        f" body={resp.text[:160]}"
    )
    body = resp.json()
    assert body.get("code") not in (None, 0, 422, 500), (
        f"应返回业务错误码,实际 body={body}"
    )
    if code is not None:
        assert body["code"] == code, f"错误码应 {code},实际 {body.get('code')}"
    return body


async def _get_row(db_session, entry_id):
    from app.models.knowledge_entry import KnowledgeEntry

    return (await db_session.execute(
        select(KnowledgeEntry).where(KnowledgeEntry.entry_id == entry_id)
    )).scalars().one()


async def _seed_gitlab_settings(db_session):
    """直插平台 GitLab 配置(branches/code 接口读 bot token/gitlab_url 用;R27/R2 同款)"""
    from app.core.encryption import encrypt_token
    from app.models.project import PlatformSetting

    db_session.add(PlatformSetting(key="gitlab_url", value="https://gitlab.example.com",
                                   updated_by="test"))
    db_session.add(PlatformSetting(
        key="gitlab_bot_token",
        value={"__encrypted": encrypt_token("glpat-r3f2-test-token")},
        updated_by="test",
    ))
    db_session.add(PlatformSetting(key="gitlab_bot_group_id", value=1, updated_by="test"))
    await db_session.flush()


# ---------------------------------------------------------------------------
# GitLab mock:/repository/branches(branches 接口用;宽容分页,同 R1 测试)
# ---------------------------------------------------------------------------
class FakeGitLabBranches:
    def __init__(self, branches):
        self.branches = branches
        self.calls = 0

    async def handler(self, request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/repository/branches"):
            self.calls += 1
            items = self.branches
            page = request.url.params.get("page")
            if page is not None:
                per_page = int(request.url.params.get("per_page") or "100")
                start = (int(page) - 1) * per_page
                items = items[start:start + per_page]
            return httpx.Response(200, json=items)
        return httpx.Response(404, json={"message": "not found"})


GITLAB_BRANCHES = [
    {"name": "main", "default": True, "commit": {"id": "a1"}},
    {"name": "feat/retry", "default": False, "commit": {"id": "b2"}},
]


# ---------------------------------------------------------------------------
# GitLab mock:/repository/tree + /repository/files(code 接口用;同 R2 详情测试)
# ---------------------------------------------------------------------------
class FakeGitLab:
    def __init__(self, files, branch="main"):
        self.files = files            # {path: str | bytes}
        self.branch = branch
        self.calls = {"tree": 0, "file": 0, "total": 0}

    async def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls["total"] += 1
        if request.url.path.endswith("/repository/tree"):
            self.calls["tree"] += 1
            base = (request.url.params.get("path") or "").strip("/")
            entries = [
                {"id": f"gid-{i}", "name": p.rsplit("/", 1)[-1], "path": p, "type": "blob",
                 "size": len(str(v).encode("utf-8"))}
                for i, (p, v) in enumerate(sorted(self.files.items()))
                if not base or p.startswith(base + "/")
            ]
            return httpx.Response(200, json=entries)
        if "/repository/files/" in request.url.path:
            self.calls["file"] += 1
            p = unquote(request.url.path.split("/repository/files/", 1)[1])
            if p not in self.files or request.url.params.get("ref") != self.branch:
                return httpx.Response(404, json={"message": "404 File Not Found"})
            blob = str(self.files[p]).encode("utf-8")
            return httpx.Response(200, json={
                "file_name": p.rsplit("/", 1)[-1],
                "path": p,
                "size": len(blob),
                "encoding": "base64",
                "content": base64.b64encode(blob).decode("ascii"),
            })
        return httpx.Response(404, json={"message": "not found"})


# ---------------------------------------------------------------------------
# 1. 读链路:项目级条目 detail / code / branches(超管非成员)
# ---------------------------------------------------------------------------
class TestSuperadminReadProjectEntry:
    @pytest.mark.asyncio
    async def test_detail_200(self, client, auth_headers, db_session, registered_user):
        """超管非成员 GET /knowledge/{id}(项目级)→ 200(R3.F2:_ensure_entry_readable 直通;
        registered_user 即首注册超管,owner 为普通用户且超管不在成员表)"""
        owner = await _mk_user(client)
        project = await _mk_project(db_session, owner["user_id"])
        entry = await _mk_entry(db_session, project.project_id)

        resp = await client.get(f"/api/knowledge/{entry.entry_id}", headers=auth_headers)
        assert resp.status_code == 200, (
            f"超管非成员读项目级条目应 200,实际 {resp.status_code}{resp.text[:160]}"
        )
        assert resp.json()["data"]["title"] == entry.title

    @pytest.mark.asyncio
    async def test_code_200(self, client, auth_headers, db_session, registered_user):
        """超管非成员 GET /knowledge/{id}/code → 200 拉到文件内容(R3.F2:关联代码 Tab 依赖)"""
        owner = await _mk_user(client)
        project = await _mk_project(db_session, owner["user_id"])
        repo = await _mk_repo(db_session, project.project_id)
        entry = await _mk_entry(db_session, project.project_id,
                                source_links=_code_link(repo.repo_id, "main",
                                                        ["app/services/retry.py"]))
        await _seed_gitlab_settings(db_session)

        with httpx.MockTransport(FakeGitLab({"app/services/retry.py": "def retry(): ...\n"}).handler):
            resp = await client.get(
                f"/api/knowledge/{entry.entry_id}/code",
                params={"path": "app/services/retry.py"},
                headers=auth_headers,
            )
        assert resp.status_code == 200, (
            f"超管非成员拉取条目代码应 200,实际 {resp.status_code}{resp.text[:160]}"
        )
        data = resp.json()["data"]
        assert data.get("content") == "def retry(): ...\n", f"代码内容不符,实际 {data!r}"

    @pytest.mark.asyncio
    async def test_branches_200(self, client, auth_headers, db_session, registered_user):
        """超管非成员 GET /projects/{pid}/repos/{repo_id}/branches → 200(R3.F2 直通)"""
        owner = await _mk_user(client)
        project = await _mk_project(db_session, owner["user_id"])
        repo = await _mk_repo(db_session, project.project_id)
        await _seed_gitlab_settings(db_session)
        gl = FakeGitLabBranches(GITLAB_BRANCHES)

        with httpx.MockTransport(gl.handler):
            resp = await client.get(
                f"/api/projects/{project.project_id}/repos/{repo.repo_id}/branches",
                headers=auth_headers,
            )
        assert resp.status_code == 200, (
            f"超管非成员取分支列表应 200,实际 {resp.status_code}{resp.text[:160]}"
        )
        branches = resp.json()["data"]
        assert isinstance(branches, list) and len(branches) == 2, f"应 2 个分支,实际 {branches!r}"
        assert gl.calls >= 1, "应实际调用 GitLab /repository/branches(mock 计数)"


# ---------------------------------------------------------------------------
# 2. 创建:POST /projects/{pid}/knowledge(超管非成员)
# ---------------------------------------------------------------------------
class TestSuperadminCreateEntry:
    @pytest.mark.asyncio
    async def test_create_200_by_non_member_superadmin(self, client, auth_headers,
                                                       db_session, registered_user):
        """超管非成员在任意项目创建知识条目 → 200(R3.F2:创建不限项目成员身份);
        落库 created_by_user_id=超管 user_id、created_by=human、status=published"""
        owner = await _mk_user(client)
        project = await _mk_project(db_session, owner["user_id"])

        entry_id = await _create_entry_api(
            client, auth_headers, project.project_id,
            title="超管跨项目新建条目", tags=["ops"],
        )
        row = await _get_row(db_session, entry_id)
        assert row.project_id == project.project_id
        assert row.created_by == "human" and row.status == "published"
        assert row.created_by_user_id == registered_user["user_id"], (
            f"created_by_user_id 应落超管 {registered_user['user_id']},"
            f"实际 {getattr(row, 'created_by_user_id', None)!r}"
        )


# ---------------------------------------------------------------------------
# 3. 写链路:PATCH 全字段 / DELETE / publish / promote(超管非成员)
# ---------------------------------------------------------------------------
class TestSuperadminWriteEntry:
    @pytest.mark.asyncio
    async def test_patch_all_fields_200(self, client, auth_headers, db_session,
                                        registered_user):
        """超管非成员 PATCH 他人人工条目全字段 → 200 且逐字段落库(R3.F2:超管全字段)"""
        owner = await _mk_user(client)
        project = await _mk_project(db_session, owner["user_id"])
        repo = await _mk_repo(db_session, project.project_id)
        entry = await _mk_entry(db_session, project.project_id)

        new_paths = ["backend/app/services/retry.py"]
        resp = await client.patch(
            f"/api/knowledge/{entry.entry_id}",
            json={
                "title": "超管改的新标题",
                "type": "pattern",
                "tags": ["architecture", "retry"],
                "content": "# 超管改的正文\n\nMarkdown",
                "source_links": [{"type": "code", "repo_id": repo.repo_id,
                                  "branch": "main", "paths": new_paths}],
            },
            headers=auth_headers,
        )
        assert resp.status_code == 200, (
            f"超管非成员编辑人工条目应 200,实际 {resp.status_code}{resp.text[:160]}"
        )
        row = await _get_row(db_session, entry.entry_id)
        assert row.title == "超管改的新标题", f"title 实际 {row.title}"
        assert row.type == "pattern", f"type 实际 {row.type}"
        assert row.tags == ["architecture", "retry"], f"tags 实际 {row.tags}"
        assert row.content == "# 超管改的正文\n\nMarkdown", f"content 实际 {row.content!r}"
        assert row.source_links == [{"type": "code", "repo_id": repo.repo_id,
                                     "branch": "main", "paths": new_paths}], (
            f"source_links 实际 {row.source_links!r}"
        )

    @pytest.mark.asyncio
    async def test_delete_200(self, client, auth_headers, db_session, registered_user):
        """超管非成员 DELETE 他人条目 → 200,删除后 detail 404(R3.F2:超管可删)"""
        owner = await _mk_user(client)
        project = await _mk_project(db_session, owner["user_id"])
        entry = await _mk_entry(db_session, project.project_id)

        resp = await client.delete(f"/api/knowledge/{entry.entry_id}", headers=auth_headers)
        assert resp.status_code == 200, (
            f"超管非成员删除条目应 200,实际 {resp.status_code}{resp.text[:160]}"
        )
        detail = await client.get(f"/api/knowledge/{entry.entry_id}", headers=auth_headers)
        assert detail.status_code == 404, f"删除后详情应 404,实际 {detail.status_code}"

    @pytest.mark.asyncio
    async def test_publish_draft_200(self, client, auth_headers, db_session,
                                     registered_user):
        """超管非成员 publish draft 条目 → 200 且落库 published(R3.F2:发布直通)"""
        owner = await _mk_user(client)
        project = await _mk_project(db_session, owner["user_id"])
        entry = await _mk_entry(db_session, project.project_id, status="draft")

        resp = await client.post(f"/api/knowledge/{entry.entry_id}/publish",
                                 headers=auth_headers)
        assert resp.status_code == 200, (
            f"超管非成员发布 draft 应 200,实际 {resp.status_code}{resp.text[:160]}"
        )
        row = await _get_row(db_session, entry.entry_id)
        assert row.status == "published", f"发布后 status 应 published,实际 {row.status}"

    @pytest.mark.asyncio
    async def test_promote_200(self, client, auth_headers, db_session, registered_user):
        """超管非成员 promote 项目级条目 → 200 且 project_id 置空(R3.F2:提升直通;
        R2 审计缺口收口确认)"""
        owner = await _mk_user(client)
        project = await _mk_project(db_session, owner["user_id"])
        entry = await _mk_entry(db_session, project.project_id)

        resp = await client.post(f"/api/knowledge/{entry.entry_id}/promote",
                                 headers=auth_headers)
        assert resp.status_code == 200, (
            f"超管非成员提升条目应 200,实际 {resp.status_code}{resp.text[:160]}"
        )
        row = await _get_row(db_session, entry.entry_id)
        assert row.project_id is None, f"提升后应为平台级(project_id NULL),实际 {row.project_id!r}"


# ---------------------------------------------------------------------------
# 4. detail permissions:超管四权全 true(Red 主战场:can_publish/can_promote 缺失)
# ---------------------------------------------------------------------------
class TestSuperadminPermissions:
    @pytest.mark.asyncio
    async def test_project_entry_all_true(self, client, auth_headers, db_session,
                                          registered_user):
        """超管非成员对项目级人工条目:can_edit/can_delete/can_publish/can_promote 全 true,
        editable_fields=人工全字段(R3.F2 permissions 扩展:后端计算四键)"""
        owner = await _mk_user(client)
        project = await _mk_project(db_session, owner["user_id"])
        entry = await _mk_entry(db_session, project.project_id)

        detail = await client.get(f"/api/knowledge/{entry.entry_id}", headers=auth_headers)
        assert detail.status_code == 200, f"详情应 200,实际 {detail.status_code}"
        perms = detail.json()["data"].get("permissions")
        assert perms is not None, "detail 响应缺 permissions 块"
        assert perms.get("can_edit") is True, f"超管 can_edit 应 True,实际 {perms}"
        assert perms.get("can_delete") is True, f"超管 can_delete 应 True,实际 {perms}"
        assert perms.get("can_publish") is True, (
            f"超管 can_publish 应 True(后端计算字段,缺失=前端按钮无法显隐),实际 {perms}"
        )
        assert perms.get("can_promote") is True, (
            f"超管 can_promote 应 True(后端计算字段,R2 审计缺口),实际 {perms}"
        )
        assert set(perms.get("editable_fields") or []) == HUMAN_EDITABLE_FIELDS, (
            f"人工条目 editable_fields 应全字段,实际 {perms.get('editable_fields')}"
        )

    @pytest.mark.asyncio
    async def test_platform_entry_all_true(self, client, auth_headers, db_session,
                                           registered_user):
        """超管对平台级条目:四权全 true(平台级本就超管专属,permissions 口径需一致)"""
        entry = await _mk_entry(db_session, None, title="平台级权限条目")

        detail = await client.get(f"/api/knowledge/{entry.entry_id}", headers=auth_headers)
        assert detail.status_code == 200, f"详情应 200,实际 {detail.status_code}"
        perms = detail.json()["data"].get("permissions")
        assert perms is not None, "detail 响应缺 permissions 块"
        assert perms.get("can_edit") is True and perms.get("can_delete") is True, (
            f"平台级超管 can_edit/can_delete 应 True,实际 {perms}"
        )
        assert perms.get("can_publish") is True and perms.get("can_promote") is True, (
            f"平台级超管 can_publish/can_promote 应 True,实际 {perms}"
        )


# ---------------------------------------------------------------------------
# 5. AI 条目白名单不受超管影响
# ---------------------------------------------------------------------------
class TestSuperadminAiWhitelist:
    @pytest.mark.asyncio
    async def test_ai_entry_patch_content_400_20013(self, client, auth_headers,
                                                    db_session, registered_user):
        """AI 条目超管 PATCH content → 400+20013(白名单是内容治理规则,超管不豁免)"""
        owner = await _mk_user(client)
        project = await _mk_project(db_session, owner["user_id"])
        entry = await _mk_entry(db_session, project.project_id, created_by="ai",
                                title="AI 归档条目")

        resp = await client.patch(
            f"/api/knowledge/{entry.entry_id}",
            json={"content": "超管试图篡改 AI 归档正文"},
            headers=auth_headers,
        )
        body = _assert_biz_400(resp, KB_AI_ONLY_TAGS)
        assert "仅" in (body.get("message") or ""), (
            f"message 应提示仅支持编辑标签,实际 {body.get('message')!r}"
        )
        row = await _get_row(db_session, entry.entry_id)
        assert row.content == entry.content, "400 后 AI 条目正文不应被改动"

    @pytest.mark.asyncio
    async def test_ai_entry_patch_tags_200(self, client, auth_headers, db_session,
                                           registered_user):
        """AI 条目超管 PATCH tags → 200(白名单内字段放行),正文不变"""
        owner = await _mk_user(client)
        project = await _mk_project(db_session, owner["user_id"])
        entry = await _mk_entry(db_session, project.project_id, created_by="ai")

        resp = await client.patch(
            f"/api/knowledge/{entry.entry_id}",
            json={"tags": ["ai", "超管改"]},
            headers=auth_headers,
        )
        assert resp.status_code == 200, (
            f"AI 条目超管 PATCH tags 应 200,实际 {resp.status_code}{resp.text[:160]}"
        )
        row = await _get_row(db_session, entry.entry_id)
        assert row.tags == ["ai", "超管改"], f"tags 实际 {row.tags}"
        assert row.content == entry.content, "正文不应被连带改动"


# ---------------------------------------------------------------------------
# 6. 普通非成员用户行为零回归(403/1901 基线)
# ---------------------------------------------------------------------------
class TestNonMemberBaselineRegression:
    @pytest.mark.asyncio
    async def test_non_member_read_403(self, client, db_session, registered_user):
        """普通非成员(无成员行):detail/code/branches/list 全 403+1901(回归基线)"""
        owner = await _mk_user(client)
        project = await _mk_project(db_session, owner["user_id"])
        repo = await _mk_repo(db_session, project.project_id)
        entry = await _mk_entry(db_session, project.project_id,
                                source_links=_code_link(repo.repo_id, "main", ["a.py"]))
        stranger = await _mk_user(client)

        resp = await client.get(f"/api/knowledge/{entry.entry_id}", headers=stranger["headers"])
        assert resp.status_code == 403 and resp.json()["code"] == NO_PROJECT_PERMISSION, (
            f"非成员 detail 应 403/1901,实际 {resp.status_code} {resp.json().get('code')}"
        )

        resp = await client.get(
            f"/api/knowledge/{entry.entry_id}/code",
            params={"path": "a.py"}, headers=stranger["headers"])
        assert resp.status_code == 403, f"非成员 code 应 403,实际 {resp.status_code}"

        resp = await client.get(
            f"/api/projects/{project.project_id}/repos/{repo.repo_id}/branches",
            headers=stranger["headers"])
        assert resp.status_code == 403, f"非成员 branches 应 403,实际 {resp.status_code}"

        resp = await client.get(
            f"/api/projects/{project.project_id}/knowledge", headers=stranger["headers"])
        assert resp.status_code == 403, f"非成员 list 应 403,实际 {resp.status_code}"

    @pytest.mark.asyncio
    async def test_non_member_create_403(self, client, db_session, registered_user):
        """普通非成员 POST /projects/{pid}/knowledge → 403(回归基线,不随超管放行扩大)"""
        owner = await _mk_user(client)
        project = await _mk_project(db_session, owner["user_id"])
        stranger = await _mk_user(client)

        resp = await client.post(
            f"/api/projects/{project.project_id}/knowledge",
            json={"type": "code_snippet", "title": "非成员想建条目", "content": "x"},
            headers=stranger["headers"],
        )
        assert resp.status_code == 403, (
            f"非成员创建应 403,实际 {resp.status_code}{resp.text[:160]}"
        )

    @pytest.mark.asyncio
    async def test_non_member_write_403(self, client, db_session, registered_user):
        """普通非成员 PATCH/DELETE/publish/promote → 403+1901,条目不被改动(回归基线)"""
        owner = await _mk_user(client)
        project = await _mk_project(db_session, owner["user_id"])
        entry = await _mk_entry(db_session, project.project_id, status="draft")
        stranger = await _mk_user(client)

        resp = await client.patch(
            f"/api/knowledge/{entry.entry_id}", json={"title": "非成员改"},
            headers=stranger["headers"])
        assert resp.status_code == 403 and resp.json()["code"] == NO_PROJECT_PERMISSION, (
            f"非成员 PATCH 应 403/1901,实际 {resp.status_code} {resp.json().get('code')}"
        )

        resp = await client.delete(f"/api/knowledge/{entry.entry_id}",
                                   headers=stranger["headers"])
        assert resp.status_code == 403, f"非成员 DELETE 应 403,实际 {resp.status_code}"

        resp = await client.post(f"/api/knowledge/{entry.entry_id}/publish",
                                 headers=stranger["headers"])
        assert resp.status_code == 403, f"非成员 publish 应 403,实际 {resp.status_code}"

        resp = await client.post(f"/api/knowledge/{entry.entry_id}/promote",
                                 headers=stranger["headers"])
        assert resp.status_code == 403, f"非成员 promote 应 403,实际 {resp.status_code}"

        row = await _get_row(db_session, entry.entry_id)
        assert row.title == entry.title and row.status == "draft", (
            "403 后条目标题/状态不应被改动"
        )
