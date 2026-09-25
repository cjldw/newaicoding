"""
R2 条目详情页(后端面)— Red 阶段失败测试
============================================
覆盖 DEVPLAN/R2.md「接口契约」「权限矩阵」「测试验证逻辑」:

1. GET /api/knowledge/{entry_id} 权限收紧:
   - 项目级条目:成员(viewer+)200 / 非成员 403
   - 平台级条目(project_id=null):任意登录用户 200
2. 新增 GET /api/knowledge/{entry_id}/code?path={path}:
   - 文件:全量返回不截断(base64→utf-8)
   - 目录:递归树(children 嵌套;二进制文件只列节点不拉内容)
   - path 404 → code 20012「代码来源不可达」;repo 已解绑 → 同 20012
   - 非成员 403(鉴权同 detail)
   - 服务端缓存:同参数二次请求不触发 GitLab 调用;refresh=1 穿透
   - 目录 >200 文件:截断到 200 + partial:true
3. detail 响应含 permissions:{can_edit, can_delete, editable_fields}
   (R3 预埋;viewer/editor/owner 三态按权限矩阵断言)

GitLab 外部调用 mock:沿用 conftest 现有方案 —— `with httpx.MockTransport(handler):`
进入上下文时由 autouse fixture 注入 gitlab_service._test_transport(conftest.py:395),
不自建注入机制;计数器直接挂在 handler 上(缓存命中断言用)。
"""
import base64
import uuid
from urllib.parse import unquote

import httpx
import pytest

CODE_UNREACHABLE = 20012          # R2 契约:「代码来源不可达」(path 404 / repo 已解绑同码)
MAX_DIR_FILES = 200               # R2 契约:目录递归总文件数上限


# ---------------------------------------------------------------------------
# 测试辅助:用户 / 项目 / repo / 条目 / 平台 GitLab 配置(沿用既有测试写法)
# ---------------------------------------------------------------------------
async def _mk_user(client):
    """注册并登录一个新用户,返回 {headers, user_id}(test_project_members_api 同款)"""
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
        name=f"R2 详情项目 {uuid.uuid4().hex[:6]}",
        slug=f"r2d-{uuid.uuid4().hex[:8]}",
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
        gitlab_repo_id=gitlab_repo_id or uuid.uuid4().int % 100000,
        gitlab_bind_type="auto",
        created_by=str(uuid.uuid4()),   # project_repos.created_by NOT NULL(其余测试同款必填)
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


async def _mk_entry(db_session, project_id, source_links=None, created_by="human",
                    status="published", title=None):
    from app.models.knowledge_entry import KnowledgeEntry

    e = KnowledgeEntry(
        project_id=project_id,
        req_id="manual",
        type="code_snippet",
        title=title or f"R2 条目 {uuid.uuid4().hex[:6]}",
        content="重试装饰器用法说明",
        tags=["python"],
        source_links=source_links,
        created_by=created_by,
        status=status,
    )
    db_session.add(e)
    await db_session.flush()
    return e


async def _seed_gitlab_settings(db_session):
    """直插平台 GitLab 配置(code 接口读 bot token/gitlab_url 用;R27 同款)"""
    from app.core.encryption import encrypt_token
    from app.models.project import PlatformSetting

    db_session.add(PlatformSetting(key="gitlab_url", value="https://gitlab.example.com",
                                   updated_by="test"))
    db_session.add(PlatformSetting(
        key="gitlab_bot_token",
        value={"__encrypted": encrypt_token("glpat-r2-test-token")},
        updated_by="test",
    ))
    db_session.add(PlatformSetting(key="gitlab_bot_group_id", value=1, updated_by="test"))
    await db_session.flush()


def _code_link(repo_id, branch="main", paths=None):
    """R1 定稿的 source_links code 对象(A 型;R2 详情页消费它拉代码)"""
    return [{"type": "code", "repo_id": repo_id, "branch": branch,
             "paths": paths or []}]


# ---------------------------------------------------------------------------
# GitLab mock:files 字典 → /repository/tree + /repository/files 两个端点
# calls 计数器供缓存命中断言;mock 刻意宽容:tree 不带 page 参数时返回全量列表
# (真实 GitLab 单页 ≤100;此处若实现分页则按 page/per_page 切片,两种实现都可 Green)
# ---------------------------------------------------------------------------
class FakeGitLab:
    def __init__(self, files, branch="main"):
        self.files = files            # {path: str | bytes}
        self.branch = branch
        self.calls = {"tree": 0, "file": 0, "total": 0}

    def _tree_entries(self, base, recursive):
        out, seen = [], set()

        def add(node_path, kind, size=None):
            if node_path in seen:
                return
            seen.add(node_path)
            entry = {"id": f"gid-{len(seen)}", "name": node_path.rsplit("/", 1)[-1],
                     "path": node_path, "type": kind}
            if kind == "blob":
                entry["size"] = size
            out.append(entry)

        for p in sorted(self.files):
            if base and not p.startswith(base + "/"):
                continue
            rel = p[len(base) + 1:] if base else p
            raw = self.files[p]
            size = len(raw) if isinstance(raw, (bytes, bytearray)) else len(raw.encode("utf-8"))
            parts = rel.split("/")
            if len(parts) == 1:
                add(p, "blob", size)
            else:
                if recursive:
                    for i in range(1, len(parts)):
                        add((base + "/" if base else "") + "/".join(parts[:i]), "tree")
                else:
                    add((base + "/" if base else "") + parts[0], "tree")
                add(p, "blob", size)
        return out

    async def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls["total"] += 1
        if request.url.path.endswith("/repository/tree"):
            self.calls["tree"] += 1
            base = (request.url.params.get("path") or "").strip("/")
            recursive = request.url.params.get("recursive") in ("true", "1")
            entries = self._tree_entries(base, recursive)
            page = request.url.params.get("page")
            if page is not None:
                per_page = int(request.url.params.get("per_page") or "100")
                start = (int(page) - 1) * per_page
                entries = entries[start:start + per_page]
            return httpx.Response(200, json=entries)
        if "/repository/files/" in request.url.path:
            self.calls["file"] += 1
            p = unquote(request.url.path.split("/repository/files/", 1)[1])
            if p not in self.files or request.url.params.get("ref") != self.branch:
                return httpx.Response(404, json={"message": "404 File Not Found"})
            raw = self.files[p]
            blob = raw if isinstance(raw, (bytes, bytearray)) else str(raw).encode("utf-8")
            return httpx.Response(200, json={
                "file_name": p.rsplit("/", 1)[-1],
                "path": p,
                "size": len(blob),
                "encoding": "base64",
                "content": base64.b64encode(blob).decode("ascii"),
            })
        return httpx.Response(404, json={"message": "not found"})


PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00\x01\x02" * 8   # 非 utf-8 可解码 → 二进制

# 标准目录样本:文本 / 嵌套子目录 / 二进制各一
SAMPLE_DIR_FILES = {
    "src/main.py": "print('main')\n",
    "src/utils/helpers.py": "def help_me():\n    pass\n",
    "src/assets/logo.png": PNG_BYTES,
}


# ---------------------------------------------------------------------------
# 1. detail 权限收紧(GET /api/knowledge/{entry_id})
# ---------------------------------------------------------------------------
class TestDetailAccessTightening:
    @pytest.mark.asyncio
    async def test_project_entry_member_viewer_200(self, client, auth_headers,
                                                   db_session, registered_user):
        """项目级条目:项目 viewer 成员访问 → 200(权限矩阵:viewer+ ✅)"""
        project = await _mk_project(db_session, registered_user["user_id"])
        entry = await _mk_entry(db_session, project.project_id)
        viewer = await _mk_user(client)
        await _mk_member(db_session, project.project_id, viewer["user_id"], role="viewer")

        resp = await client.get(f"/api/knowledge/{entry.entry_id}", headers=viewer["headers"])
        assert resp.status_code == 200, f"viewer 成员应 200,实际 {resp.status_code}"
        data = resp.json()
        assert data["code"] == 0, f"viewer 成员应放行,实际 code={data.get('code')}"
        assert data["data"]["entry_id"] == entry.entry_id
        assert data["data"]["content"] == entry.content

    @pytest.mark.asyncio
    async def test_project_entry_non_member_403(self, client, auth_headers,
                                                db_session, registered_user):
        """项目级条目:非成员访问 → 403(现实现仅登录即可,Red:实际 200)"""
        project = await _mk_project(db_session, registered_user["user_id"])
        entry = await _mk_entry(db_session, project.project_id)
        outsider = await _mk_user(client)

        resp = await client.get(f"/api/knowledge/{entry.entry_id}", headers=outsider["headers"])
        assert resp.status_code == 403, (
            f"非成员访问项目级条目应 403,实际 {resp.status_code}(权限收紧未实现)"
        )
        assert resp.json()["code"] == 1901

    @pytest.mark.asyncio
    async def test_platform_entry_any_logged_in_200(self, client, auth_headers,
                                                    db_session, registered_user):
        """平台级条目(project_id=null):任意登录用户 → 200(全员可见口径)"""
        entry = await _mk_entry(db_session, None, title="平台级通用模式")
        any_user = await _mk_user(client)

        resp = await client.get(f"/api/knowledge/{entry.entry_id}", headers=any_user["headers"])
        assert resp.status_code == 200, f"平台级条目登录用户应 200,实际 {resp.status_code}"
        data = resp.json()
        assert data["code"] == 0
        assert data["data"]["project_id"] is None


# ---------------------------------------------------------------------------
# 3. detail 响应 permissions(R3 预埋,后端算好;按权限矩阵三态)
# ---------------------------------------------------------------------------
class TestDetailPermissionsBlock:
    async def _project_with_roles(self, client, db_session, registered_user):
        """owner=registered_user + editor/viewer 各一;返回 (project, owner, editor, viewer)"""
        project = await _mk_project(db_session, registered_user["user_id"])
        editor = await _mk_user(client)
        viewer = await _mk_user(client)
        await _mk_member(db_session, project.project_id, editor["user_id"], role="editor")
        await _mk_member(db_session, project.project_id, viewer["user_id"], role="viewer")
        return project, registered_user, editor, viewer

    async def _permissions_of(self, client, entry_id, headers) -> dict:
        resp = await client.get(f"/api/knowledge/{entry_id}", headers=headers)
        assert resp.status_code == 200, f"detail 应 200,实际 {resp.status_code}"
        data = resp.json()
        assert data["code"] == 0
        perms = data["data"].get("permissions")
        assert perms is not None, (
            f"detail 响应缺 permissions 块(R2 预埋 R3):keys={sorted(data['data'].keys())}"
        )
        return perms

    @pytest.mark.asyncio
    async def test_viewer_cannot_edit_delete(self, client, auth_headers, db_session,
                                             registered_user):
        """viewer:can_edit=false / can_delete=false / editable_fields=[]"""
        project, _o, _e, viewer = await self._project_with_roles(client, db_session, registered_user)
        entry = await _mk_entry(db_session, project.project_id, created_by="human")

        perms = await self._permissions_of(client, entry.entry_id, viewer["headers"])
        assert perms.get("can_edit") is False, f"viewer can_edit 应 False,实际 {perms}"
        assert perms.get("can_delete") is False, f"viewer can_delete 应 False,实际 {perms}"
        assert perms.get("editable_fields") == [], (
            f"viewer editable_fields 应为空,实际 {perms.get('editable_fields')}"
        )

    @pytest.mark.asyncio
    async def test_editor_can_edit_and_delete(self, client, auth_headers,
                                              db_session, registered_user):
        """editor(非创建者):人工条目可全字段编辑(can_edit=true),亦可删(can_delete=true;
        R3 口径「项目 owner/editor 可删」,B1 收口)"""
        project, _o, editor, _v = await self._project_with_roles(client, db_session, registered_user)
        entry = await _mk_entry(db_session, project.project_id, created_by="human")

        perms = await self._permissions_of(client, entry.entry_id, editor["headers"])
        assert perms.get("can_edit") is True, f"editor can_edit 应 True,实际 {perms}"
        assert perms.get("can_delete") is True, f"editor can_delete 应 True,实际 {perms}"
        fields = set(perms.get("editable_fields") or [])
        assert {"title", "content", "tags"} <= fields, (
            f"editor editable_fields 应含 title/content/tags,实际 {sorted(fields)}"
        )

    @pytest.mark.asyncio
    async def test_owner_can_edit_and_delete(self, client, auth_headers, db_session,
                                             registered_user):
        """owner:can_edit=true / can_delete=true(权限矩阵:owner 发布/提升皆 ✅)"""
        project, owner, _e, _v = await self._project_with_roles(client, db_session, registered_user)
        entry = await _mk_entry(db_session, project.project_id, created_by="human")

        perms = await self._permissions_of(client, entry.entry_id, auth_headers)
        assert perms.get("can_edit") is True, f"owner can_edit 应 True,实际 {perms}"
        assert perms.get("can_delete") is True, f"owner can_delete 应 True,实际 {perms}"

    @pytest.mark.asyncio
    async def test_ai_entry_only_tags_editable(self, client, auth_headers, db_session,
                                               registered_user):
        """AI 条目:仅标签可编辑(R3 已确认口径)→ editable_fields==['tags']"""
        project, owner, _e, _v = await self._project_with_roles(client, db_session, registered_user)
        entry = await _mk_entry(db_session, project.project_id, created_by="ai")

        perms = await self._permissions_of(client, entry.entry_id, auth_headers)
        assert perms.get("editable_fields") == ["tags"], (
            f"AI 条目 editable_fields 应仅 ['tags'],实际 {perms.get('editable_fields')}"
        )

    @pytest.mark.asyncio
    async def test_platform_entry_delete_superadmin_only(self, client, auth_headers,
                                                         superadmin_headers, db_session,
                                                         registered_user):
        """平台级条目:普通登录用户 can_edit/can_delete 均 false;超管均 true(R3 矩阵:仅超管)"""
        entry = await _mk_entry(db_session, None, created_by="human", title="平台级条目")

        # 仓库约定(test_platform_settings_api 同款):auth_headers 是首个注册用户=superadmin,
        # 「普通用户」必须用第二个注册用户,故这里 _mk_user 现注册一个 role=user 的用户
        normal = await _mk_user(client)

        perms = await self._permissions_of(client, entry.entry_id, normal["headers"])
        assert perms.get("can_edit") is False, f"平台级普通用户 can_edit 应 False,实际 {perms}"
        assert perms.get("can_delete") is False, f"平台级普通用户 can_delete 应 False,实际 {perms}"

        perms_admin = await self._permissions_of(client, entry.entry_id, superadmin_headers)
        assert perms_admin.get("can_edit") is True, f"平台级超管 can_edit 应 True,实际 {perms_admin}"
        assert perms_admin.get("can_delete") is True, f"平台级超管 can_delete 应 True,实际 {perms_admin}"


# ---------------------------------------------------------------------------
# 2. code 接口(GET /api/knowledge/{entry_id}/code?path=)
# ---------------------------------------------------------------------------
class TestCodeEndpoint:
    async def _entry_with_repo(self, db_session, registered_user, files=None, branch="main"):
        """项目 + main repo + A 型条目(source_links 指向该 repo);返回 (entry, repo, project)"""
        project = await _mk_project(db_session, registered_user["user_id"])
        repo = await _mk_repo(db_session, project.project_id)
        paths = list((files or SAMPLE_DIR_FILES).keys())
        entry = await _mk_entry(db_session, project.project_id,
                                source_links=_code_link(repo.repo_id, branch=branch, paths=paths))
        await _seed_gitlab_settings(db_session)
        return entry, repo, project

    @pytest.mark.asyncio
    async def test_code_file_full_content_no_truncation(self, client, auth_headers, db_session,
                                                        registered_user):
        """文件路径:base64→utf-8 全量返回(10 万字符级不截断),size 为字节数"""
        big_text = "x = %d  # %s\n" % (0, "a" * 100_000)
        entry, repo, _p = await self._entry_with_repo(
            db_session, registered_user, files={"app/services/retry.py": big_text})

        with httpx.MockTransport(FakeGitLab({"app/services/retry.py": big_text}).handler):
            resp = await client.get(f"/api/knowledge/{entry.entry_id}/code",
                                    headers=auth_headers, params={"path": "app/services/retry.py"})
        assert resp.status_code == 200, f"code 接口应存在且 200,实际 {resp.status_code}"
        data = resp.json()
        assert data.get("code") == 0, f"code={data.get('code')} message={data.get('message')}"
        body = data.get("data") or {}
        assert body.get("kind") == "file", f"kind 应为 file,实际 {body.get('kind')}"
        assert body.get("path") == "app/services/retry.py"
        assert body.get("content") == big_text, (
            f"文件应全量返回不截断:期望 {len(big_text)} 字符,实际 "
            f"{len(body.get('content') or '')}"
        )
        assert body.get("size") == len(big_text.encode("utf-8")), (
            f"size 应为字节数 {len(big_text.encode())},实际 {body.get('size')}"
        )

    @pytest.mark.asyncio
    async def test_code_dir_recursive_tree_with_binary_node(self, client, auth_headers,
                                                            db_session, registered_user):
        """目录路径:递归树(children 嵌套、文本节点带 content);二进制文件只列节点不拉内容"""
        entry, repo, _p = await self._entry_with_repo(db_session, registered_user,
                                                      files=SAMPLE_DIR_FILES)

        with httpx.MockTransport(FakeGitLab(SAMPLE_DIR_FILES).handler):
            resp = await client.get(f"/api/knowledge/{entry.entry_id}/code",
                                    headers=auth_headers, params={"path": "src"})
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("code") == 0, f"code={data.get('code')} message={data.get('message')}"
        body = data.get("data") or {}
        assert body.get("kind") == "dir", f"目录路径 kind 应为 dir,实际 {body.get('kind')}"

        tree = body.get("tree")
        assert isinstance(tree, list) and tree, f"tree 应为非空数组,实际 {tree!r}"

        def find(nodes, name):
            for n in nodes:
                if n.get("path", "").rsplit("/", 1)[-1] == name:
                    return n
            return None

        main = find(tree, "main.py")
        assert main is not None, f"树中应有 main.py,实际 paths={[n.get('path') for n in tree]}"
        assert main.get("kind") == "file"
        assert main.get("content") == "print('main')\n", f"文本节点应带 content,实际 {main}"

        utils = find(tree, "utils")
        assert utils is not None, "树中应有 utils 目录节点"
        assert utils.get("kind") == "dir"
        children = utils.get("children")
        assert isinstance(children, list) and children, f"目录节点应含 children,实际 {utils}"
        helper = find(children, "helpers.py")
        assert helper is not None, f"children 应递归含 helpers.py,实际 {children}"
        assert helper.get("content") == "def help_me():\n    pass\n"

        assets = find(tree, "assets")
        assert assets is not None and assets.get("kind") == "dir", "树中应有 assets 目录节点"
        logo = find(assets.get("children") or [], "logo.png")
        assert logo is not None, "二进制文件应列节点(不缺失)"
        assert not logo.get("content"), (
            f"二进制文件只列节点不拉 content,实际 content={str(logo.get('content'))[:40]!r}"
        )
        assert logo.get("size", 0) == len(PNG_BYTES), f"二进制节点应带 size,实际 {logo}"

    @pytest.mark.asyncio
    async def test_code_path_404_returns_20012(self, client, auth_headers, db_session,
                                               registered_user):
        """path 不存在(GitLab 404)→ code 20012「代码来源不可达」(逐块失败互不影响口径)"""
        entry, repo, _p = await self._entry_with_repo(
            db_session, registered_user, files={"src/exists.py": "ok = True\n"})

        with httpx.MockTransport(FakeGitLab({"src/exists.py": "ok = True\n"}).handler):
            resp = await client.get(f"/api/knowledge/{entry.entry_id}/code",
                                    headers=auth_headers, params={"path": "src/ghost.py"})
        data = resp.json()
        assert data.get("code") == CODE_UNREACHABLE, (
            f"path 404 应返回 20012,实际 code={data.get('code')} message={data.get('message')}"
        )
        assert "代码来源不可达" in (data.get("message") or ""), (
            f"message 应含「代码来源不可达」,实际 {data.get('message')!r}"
        )

    @pytest.mark.asyncio
    async def test_code_repo_unbound_returns_20012(self, client, auth_headers, db_session,
                                                   registered_user):
        """source_links 指向的 ProjectRepo 已不存在(解绑)→ 同码 20012"""
        project = await _mk_project(db_session, registered_user["user_id"])
        ghost_repo_id = str(uuid.uuid4())   # 不落 ProjectRepo 行 = 已解绑
        entry = await _mk_entry(db_session, project.project_id,
                                source_links=_code_link(ghost_repo_id, paths=["a.py"]))
        await _seed_gitlab_settings(db_session)

        with httpx.MockTransport(FakeGitLab({"a.py": "a = 1\n"}).handler):
            resp = await client.get(f"/api/knowledge/{entry.entry_id}/code",
                                    headers=auth_headers, params={"path": "a.py"})
        data = resp.json()
        assert data.get("code") == CODE_UNREACHABLE, (
            f"repo 已解绑应返回 20012 同码,实际 code={data.get('code')} message={data.get('message')}"
        )

    @pytest.mark.asyncio
    async def test_code_non_member_403(self, client, auth_headers, db_session, registered_user):
        """非成员访问项目级条目 code 接口 → 403(鉴权同 detail)"""
        entry, repo, _p = await self._entry_with_repo(
            db_session, registered_user, files={"a.py": "a = 1\n"})
        outsider = await _mk_user(client)

        with httpx.MockTransport(FakeGitLab({"a.py": "a = 1\n"}).handler):
            resp = await client.get(f"/api/knowledge/{entry.entry_id}/code",
                                    headers=outsider["headers"], params={"path": "a.py"})
        assert resp.status_code == 403, (
            f"非成员调 code 接口应 403,实际 {resp.status_code}(接口未实现时为 404 路由未命中)"
        )

    @pytest.mark.asyncio
    async def test_code_cache_hit_and_refresh_bypass(self, client, auth_headers, db_session,
                                                     registered_user):
        """缓存:同参数二次请求不触发 GitLab 调用(mock 计数不变);refresh=1 穿透取新"""
        entry, repo, _p = await self._entry_with_repo(
            db_session, registered_user, files={"cached.py": "cached = True\n"})
        gl = FakeGitLab({"cached.py": "cached = True\n"})

        async def get_code(**params):
            return await client.get(f"/api/knowledge/{entry.entry_id}/code",
                                    headers=auth_headers, params={"path": "cached.py", **params})

        with httpx.MockTransport(gl.handler):
            r1 = await get_code()
            assert r1.json().get("code") == 0, (
                f"首次请求应成功(接口未实现时此处 Red):{r1.status_code} {r1.text[:120]}"
            )
            n1 = gl.calls["total"]
            assert n1 > 0, "首次请求应触发 GitLab 调用"

            r2 = await get_code()
            assert r2.json().get("code") == 0
            assert gl.calls["total"] == n1, (
                f"同参数二次请求应命中服务端缓存(GitLab 调用数应保持 {n1}),"
                f"实际 {gl.calls['total']}"
            )

            r3 = await get_code(refresh="1")
            assert r3.json().get("code") == 0
            assert gl.calls["total"] > n1, (
                f"refresh=1 应穿透缓存重新拉取(调用数应 > {n1}),实际 {gl.calls['total']}"
            )

    @pytest.mark.asyncio
    async def test_code_dir_over_200_files_truncated_partial(self, client, auth_headers,
                                                             db_session, registered_user):
        """目录 205 个文件 → 截断为 200 且 partial:true(提示「仅加载前 200 个文件」口径)"""
        files = {f"big/f{i:03d}.py": f"v{i} = {i}\n" for i in range(205)}
        entry, repo, _p = await self._entry_with_repo(db_session, registered_user, files=files)

        with httpx.MockTransport(FakeGitLab(files).handler):
            resp = await client.get(f"/api/knowledge/{entry.entry_id}/code",
                                    headers=auth_headers, params={"path": "big"})
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("code") == 0, f"code={data.get('code')} message={data.get('message')}"
        body = data.get("data") or {}
        assert body.get("partial") is True, (
            f"目录超 200 文件应返回 partial:true,实际 partial={body.get('partial')}"
        )
        file_nodes = [n for n in (body.get("tree") or []) if n.get("kind") == "file"]
        assert len(file_nodes) == MAX_DIR_FILES, (
            f"文件节点应截断为 {MAX_DIR_FILES},实际 {len(file_nodes)}"
        )
