"""
R1 手动添加双类型(代码引用 / 直接创建)后端面 — Red 阶段失败测试
====================================================================
覆盖 DEVPLAN/R1.md「接口契约」「字段定义」「权限矩阵」「测试验证逻辑」:

1. A 型创建:POST /api/projects/{pid}/knowledge 携带
   source_links=[{type:"code", repo_id, branch, paths[]}] → 200,落库含 code 对象,
   状态 published(A 型 content 可选=说明文字)
2. 服务端校验(400 + 错误码;20010=路径数超限,20011=仓库不属于本项目):
   - paths 11 个 → 400 + 20010
   - repo_id 属于其他项目 → 400 + 20011
   - type=code 缺 branch / 缺 paths → 400(业务错误码)
   - paths 空数组 → 400;单路径 >500 字符 → 400
   - B 型(无 source_links)创建成功(存量行为回归,预期基线 Green)
3. 新增 GET /api/projects/{pid}/repos/{repo_id}/branches:
   - 成员 200 → [{name, default}](default 标注)
   - 非成员 403 / repo 不属于本项目 → 404(GitLab 调用 mock)

GitLab 外部调用 mock:沿用 conftest 方案 —— `with httpx.MockTransport(handler):`
进入上下文时由 autouse fixture 注入 gitlab_service._test_transport(conftest.py:395),
不自建注入机制;首注册用户恒为 superadmin,平台/项目角色用例用后续注册用户。
"""
import uuid

import httpx
import pytest
from sqlalchemy import select

from app.models.knowledge_entry import KnowledgeEntry

KB_PATHS_OVER_LIMIT = 20010   # R1 契约:paths 数量超限(1-10 之外)
KB_REPO_NOT_IN_PROJECT = 20011  # R1 契约:仓库不属于本项目


# ---------------------------------------------------------------------------
# 测试辅助:用户 / 项目 / repo / 成员 / 平台 GitLab 配置(沿用 test_knowledge_entry_detail 写法)
# ---------------------------------------------------------------------------
async def _mk_user(client):
    """注册并登录一个新用户,返回 {headers, user_id}"""
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
        name=f"R1 双类型项目 {uuid.uuid4().hex[:6]}",
        slug=f"r1c-{uuid.uuid4().hex[:8]}",
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


async def _seed_gitlab_settings(db_session):
    """直插平台 GitLab 配置(branches 接口读 bot token/gitlab_url 用;R27/R2 同款)"""
    from app.core.encryption import encrypt_token
    from app.models.project import PlatformSetting

    db_session.add(PlatformSetting(key="gitlab_url", value="https://gitlab.example.com",
                                   updated_by="test"))
    db_session.add(PlatformSetting(
        key="gitlab_bot_token",
        value={"__encrypted": encrypt_token("glpat-r1-test-token")},
        updated_by="test",
    ))
    db_session.add(PlatformSetting(key="gitlab_bot_group_id", value=1, updated_by="test"))
    await db_session.flush()


def _code_link(repo_id, branch="main", paths=None):
    """R1 字段定义:A 型 source_links 含且仅含一个 code 对象"""
    return [{"type": "code", "repo_id": repo_id, "branch": branch,
             "paths": paths or []}]


async def _create_entry(client, headers, project_id, **overrides) -> "httpx.Response":
    """POST /api/projects/{pid}/knowledge;缺省 B 型四字段,body 可覆盖"""
    payload = {
        "type": "code_snippet",
        "title": f"R1 条目 {uuid.uuid4().hex[:6]}",
        "content": "重试装饰器用法说明",
        "tags": ["python"],
    }
    payload.update(overrides)
    return await client.post(f"/api/projects/{project_id}/knowledge",
                             json=payload, headers=headers)


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


# ---------------------------------------------------------------------------
# GitLab mock:/repository/branches 分支列表(branches 接口用)
# mock 刻意宽容:不带 page 参数返回全量;实现分页则按 page/per_page 切片,两种实现都可 Green
# ---------------------------------------------------------------------------
class FakeGitLabBranches:
    def __init__(self, branches):
        self.branches = branches   # GitLab 原始形态:[{name, default, ...}]
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
# 1. A 型创建成功(source_links code 对象落库)
# ---------------------------------------------------------------------------
class TestCreateTypeACodeLink:
    @pytest.mark.asyncio
    async def test_type_a_create_persists_code_link(self, client, auth_headers, db_session,
                                                    registered_user):
        """A 型:仓库+分支+2 路径提交成功,DB source_links 含 code 对象,状态 published
        (完成判据:选仓库+分支+2 个路径提交成功)"""
        project = await _mk_project(db_session, registered_user["user_id"])
        repo = await _mk_repo(db_session, project.project_id)
        paths = ["backend/app/services/", "backend/app/api/knowledge.py"]

        resp = await _create_entry(
            client, auth_headers, project.project_id,
            type="code_snippet",
            content="为什么这段代码值得沉淀的说明",
            source_links=_code_link(repo.repo_id, branch="main", paths=paths),
        )
        assert resp.status_code == 200, f"A 型创建应 200,实际 {resp.status_code} {resp.text[:160]}"
        data = resp.json()
        assert data["code"] == 0, f"code={data.get('code')} message={data.get('message')}"
        body = data["data"]
        assert body["entry_id"], "响应应含 entry_id"
        assert body["status"] == "published", (
            f"人工创建直接 published,实际 {body.get('status')}"
        )

        # 落库核对:source_links 原样承载 code 对象(无表结构变更,JSON 承载)
        row = (await db_session.execute(
            select(KnowledgeEntry).where(KnowledgeEntry.entry_id == body["entry_id"])
        )).scalars().one()
        assert row.status == "published"
        assert row.source_links == [{"type": "code", "repo_id": repo.repo_id,
                                     "branch": "main", "paths": paths}], (
            f"DB source_links 应含 code 对象,实际 {row.source_links!r}"
        )
        assert row.created_by == "human"

    @pytest.mark.asyncio
    async def test_type_a_content_optional(self, client, auth_headers, db_session,
                                           registered_user):
        """字段定义:A 型 content 可选(说明文字)——缺省/空串均可创建"""
        project = await _mk_project(db_session, registered_user["user_id"])
        repo = await _mk_repo(db_session, project.project_id)

        resp = await _create_entry(
            client, auth_headers, project.project_id,
            content="",
            source_links=_code_link(repo.repo_id, branch="main", paths=["src/"]),
        )
        assert resp.status_code == 200, (
            f"A 型 content 可选,空说明应可创建,实际 {resp.status_code}(现 schema min_length=1 → 422)"
        )
        assert resp.json()["code"] == 0


# ---------------------------------------------------------------------------
# 2. A 型服务端校验(400 + 错误码)
# ---------------------------------------------------------------------------
class TestCreateTypeAValidation:
    async def _project_with_repo(self, db_session, registered_user):
        project = await _mk_project(db_session, registered_user["user_id"])
        repo = await _mk_repo(db_session, project.project_id)
        return project, repo

    @pytest.mark.asyncio
    async def test_paths_11_returns_400_20010(self, client, auth_headers, db_session,
                                              registered_user):
        """paths 11 个 → 400 + 20010(路径数超限;前端拦截 + 服务端兜底)"""
        project, repo = await self._project_with_repo(db_session, registered_user)

        resp = await _create_entry(
            client, auth_headers, project.project_id,
            source_links=_code_link(repo.repo_id, branch="main",
                                    paths=[f"src/m{i}.py" for i in range(11)]),
        )
        _assert_biz_400(resp, KB_PATHS_OVER_LIMIT)

    @pytest.mark.asyncio
    async def test_repo_id_of_other_project_returns_400_20011(self, client, auth_headers,
                                                              db_session, registered_user):
        """repo_id 绑定在其他项目 → 400 + 20011(仓库不属于本项目)"""
        project, _repo = await self._project_with_repo(db_session, registered_user)
        other_project = await _mk_project(db_session, registered_user["user_id"])
        other_repo = await _mk_repo(db_session, other_project.project_id)

        resp = await _create_entry(
            client, auth_headers, project.project_id,
            source_links=_code_link(other_repo.repo_id, branch="main", paths=["src/"]),
        )
        _assert_biz_400(resp, KB_REPO_NOT_IN_PROJECT)

    @pytest.mark.asyncio
    async def test_type_code_missing_branch_returns_400(self, client, auth_headers,
                                                        db_session, registered_user):
        """type=code 缺 branch → 400(type=code 时必填 repo_id/branch/paths)"""
        project, repo = await self._project_with_repo(db_session, registered_user)

        resp = await _create_entry(
            client, auth_headers, project.project_id,
            source_links=[{"type": "code", "repo_id": repo.repo_id, "paths": ["src/"]}],
        )
        _assert_biz_400(resp)

    @pytest.mark.asyncio
    async def test_type_code_missing_paths_returns_400(self, client, auth_headers,
                                                       db_session, registered_user):
        """type=code 缺 paths → 400"""
        project, repo = await self._project_with_repo(db_session, registered_user)

        resp = await _create_entry(
            client, auth_headers, project.project_id,
            source_links=[{"type": "code", "repo_id": repo.repo_id, "branch": "main"}],
        )
        _assert_biz_400(resp)

    @pytest.mark.asyncio
    async def test_paths_empty_array_returns_400(self, client, auth_headers, db_session,
                                                 registered_user):
        """paths=[] → 400(paths 长度 1-10,空数组不满足下界)"""
        project, repo = await self._project_with_repo(db_session, registered_user)

        resp = await _create_entry(
            client, auth_headers, project.project_id,
            source_links=_code_link(repo.repo_id, branch="main", paths=[]),
        )
        _assert_biz_400(resp)

    @pytest.mark.asyncio
    async def test_single_path_over_500_chars_returns_400(self, client, auth_headers,
                                                          db_session, registered_user):
        """单路径 >500 字符 → 400(契约:每个 ≤500 字符)"""
        project, repo = await self._project_with_repo(db_session, registered_user)

        resp = await _create_entry(
            client, auth_headers, project.project_id,
            source_links=_code_link(repo.repo_id, branch="main",
                                    paths=["a" * 501 + ".py"]),
        )
        _assert_biz_400(resp)


# ---------------------------------------------------------------------------
# 2b. B 型创建(存量行为回归,预期基线 Green)+ 权限矩阵非成员 403(存量)
# ---------------------------------------------------------------------------
class TestCreateTypeBRegression:
    @pytest.mark.asyncio
    async def test_type_b_create_without_source_links_success(self, client, auth_headers,
                                                              db_session, registered_user):
        """B 型:四字段提交(无 source_links)→ 200,落库 source_links=[],published"""
        project = await _mk_project(db_session, registered_user["user_id"])

        resp = await _create_entry(
            client, auth_headers, project.project_id,
            type="pattern",
            content="# 直接创建\n\nMarkdown 正文",
            tags=["architecture"],
        )
        assert resp.status_code == 200, f"B 型存量创建应 200,实际 {resp.status_code}"
        data = resp.json()
        assert data["code"] == 0, f"code={data.get('code')} message={data.get('message')}"
        assert data["data"]["status"] == "published"

        row = (await db_session.execute(
            select(KnowledgeEntry).where(KnowledgeEntry.entry_id == data["data"]["entry_id"])
        )).scalars().one()
        assert row.source_links == []
        assert row.type == "pattern"

    @pytest.mark.asyncio
    async def test_create_non_member_403(self, client, auth_headers, db_session,
                                         registered_user):
        """权限矩阵:非成员创建 → 403 code=1901(存量 Guard 回归)"""
        project = await _mk_project(db_session, registered_user["user_id"])
        outsider = await _mk_user(client)

        resp = await _create_entry(client, outsider["headers"], project.project_id)
        assert resp.status_code == 403, f"非成员创建应 403,实际 {resp.status_code}"
        assert resp.json()["code"] == 1901


# ---------------------------------------------------------------------------
# 3. 分支列表接口(GET /api/projects/{pid}/repos/{repo_id}/branches)
# ---------------------------------------------------------------------------
class TestRepoBranchesEndpoint:
    @pytest.mark.asyncio
    async def test_member_lists_branches_with_default_flag(self, client, auth_headers,
                                                           db_session, registered_user):
        """成员(owner≥viewer)→ 200 [{name, default}];default 分支标注;走 GitLab mock"""
        from app.models.project import ProjectRepo

        project = await _mk_project(db_session, registered_user["user_id"])
        repo = await _mk_repo(db_session, project.project_id, gitlab_repo_id=42001)
        await _seed_gitlab_settings(db_session)
        gl = FakeGitLabBranches(GITLAB_BRANCHES)

        with httpx.MockTransport(gl.handler):
            resp = await client.get(
                f"/api/projects/{project.project_id}/repos/{repo.repo_id}/branches",
                headers=auth_headers,
            )
        assert resp.status_code == 200, (
            f"分支接口应存在且 200,实际 {resp.status_code}(未实现时 404 路由未命中)"
        )
        data = resp.json()
        assert data["code"] == 0, f"code={data.get('code')} message={data.get('message')}"
        branches = data["data"]
        assert isinstance(branches, list) and len(branches) == 2, (
            f"应返回 2 个分支,实际 {branches!r}"
        )
        by_name = {b.get("name"): b for b in branches}
        assert "main" in by_name and "feat/retry" in by_name, (
            f"响应应以 name 标注分支,实际 {branches!r}"
        )
        assert by_name["main"].get("default") is True, (
            f"default 分支应标注 default:true,实际 {by_name.get('main')}"
        )
        assert by_name["feat/retry"].get("default") is False, (
            f"非 default 分支应标注 default:false,实际 {by_name.get('feat/retry')}"
        )
        assert gl.calls >= 1, "应实际调用 GitLab /repository/branches(mock 计数)"

        # 直连 ProjectRepo.gitlab_repo_id(而非 url 解析):mock 收到的 project id 应为 42001
        row = (await db_session.execute(
            select(ProjectRepo).where(ProjectRepo.repo_id == repo.repo_id)
        )).scalars().one()
        assert row.gitlab_repo_id == 42001

    @pytest.mark.asyncio
    async def test_branches_non_member_403(self, client, db_session, registered_user):
        """非成员 → 403(鉴权:项目 viewer)"""
        project = await _mk_project(db_session, registered_user["user_id"])
        repo = await _mk_repo(db_session, project.project_id)
        await _seed_gitlab_settings(db_session)
        outsider = await _mk_user(client)

        with httpx.MockTransport(FakeGitLabBranches(GITLAB_BRANCHES).handler):
            resp = await client.get(
                f"/api/projects/{project.project_id}/repos/{repo.repo_id}/branches",
                headers=outsider["headers"],
            )
        assert resp.status_code == 403, (
            f"非成员调分支接口应 403,实际 {resp.status_code}(接口未实现时为 404 路由未命中)"
        )
        assert resp.json()["code"] == 1901

    @pytest.mark.asyncio
    async def test_branches_repo_of_other_project_404(self, client, auth_headers,
                                                      db_session, registered_user):
        """repo 不属于本项目(绑在另一项目)→ 404(统一响应体,非路由缺省 404)"""
        project = await _mk_project(db_session, registered_user["user_id"])
        other_project = await _mk_project(db_session, registered_user["user_id"])
        other_repo = await _mk_repo(db_session, other_project.project_id)
        await _seed_gitlab_settings(db_session)

        with httpx.MockTransport(FakeGitLabBranches(GITLAB_BRANCHES).handler):
            resp = await client.get(
                f"/api/projects/{project.project_id}/repos/{other_repo.repo_id}/branches",
                headers=auth_headers,
            )
        assert resp.status_code == 404, (
            f"repo 不属于本项目应 404,实际 {resp.status_code}"
        )
        assert "code" in resp.json(), (
            f"应返回统一响应体(含 code),实际 {resp.text[:120]}"
            "(路由未实现时 FastAPI 缺省体 {'detail': 'Not Found'} 无 code)"
        )
