"""
R2 项目管理接口测试(Green 阶段修正版)
==========================================
覆盖场景:
- 创建项目 (auto/manual 模式)
- 错误码 2001 (bot token 未配置) / 2002 (repo URL 格式无效,R27 语义收窄) /
  2011 (仓库不存在 404) / 2003 (项目数超限 >50)
- 项目列表/详情/更新/删除/归档
- 追加绑定仓库 (成功 + 错误码 2004/2005)
- 解绑仓库 (成功 + 错误码 2006)
- slug 唯一性
- 权限矩阵 (owner vs non-owner)
- 空态场景

Red→Green 修正说明:原 Red 版对"不存在的 project_id"断言成功,违背 arrange-act-assert;
Green 版统一改为先直插 DB 造数据(不经 GitLab),再走接口断言。用例名与断言意图保持不变。

注意: 所有 GitLab API 调用通过 httpx mock 模拟,不发起真实外部请求。
"""
import uuid

import pytest
import httpx


# ---------------------------------------------------------------------------
# 测试辅助:直插 DB 造数据(绕过 GitLab)
# ---------------------------------------------------------------------------
async def _insert_project(db_session, owner_id, slug=None, status="active", visibility="private"):
    """直插一条项目记录,返回 Project ORM 对象"""
    from app.models.project import Project

    slug = slug or f"proj-{uuid.uuid4().hex[:8]}"
    p = Project(
        name=f"项目 {slug}",
        slug=slug,
        owner_id=owner_id,
        status=status,
        visibility=visibility,
    )
    db_session.add(p)
    await db_session.flush()
    return p


async def _insert_repo(db_session, project_id, created_by, role="test", gitlab_repo_id=None):
    """直插一条项目仓库关联"""
    from app.models.project import ProjectRepo

    r = ProjectRepo(
        project_id=project_id,
        role=role,
        gitlab_repo_url=f"https://gitlab.example.com/test-group/repo-{uuid.uuid4().hex[:6]}.git",
        gitlab_repo_id=gitlab_repo_id or uuid.uuid4().int % 100000,
        gitlab_bind_type="manual",
        created_by=created_by,
    )
    db_session.add(r)
    await db_session.flush()
    return r


async def _seed_gitlab_settings(db_session):
    """
    直插平台 GitLab 配置(gitlab_url / bot token(加密) / bot group_id)。
    需要走 GitLab mock 的用例必须先调用,否则服务层 2001 拦截。
    """
    from app.core.encryption import encrypt_token
    from app.models.project import PlatformSetting

    db_session.add(PlatformSetting(key="gitlab_url", value="https://gitlab.example.com", updated_by="test"))
    db_session.add(PlatformSetting(
        key="gitlab_bot_token",
        value={"__encrypted": encrypt_token("glpat-test-token")},
        updated_by="test",
    ))
    db_session.add(PlatformSetting(key="gitlab_bot_group_id", value=1, updated_by="test"))
    await db_session.flush()


async def _register_and_login(client):
    """注册+登录第二个用户,返回 (headers, user_id)(首个注册用户是 superadmin,此函数返回的是普通用户)"""
    phone = f"137{str(uuid.uuid4().int)[:8]}"
    resp = await client.post("/api/auth/register", json={"phone": phone, "password": "Test1234"})
    assert resp.status_code == 200
    assert resp.json()["code"] == 0
    user_id = resp.json()["data"]["user_id"]
    resp = await client.post("/api/auth/login", json={"phone": phone, "password": "Test1234"})
    assert resp.status_code == 200
    access_token = resp.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {access_token}"}, user_id


# ---------------------------------------------------------------------------
# mock GitLab API 辅助函数 (R2 扩展)
# ---------------------------------------------------------------------------
def mock_gitlab_create_project(status_code=200, project_id=123, slug="test-project"):
    """模拟 POST /api/v4/projects (创建仓库)"""
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and "/api/v4/projects" in str(request.url):
            if status_code == 200:
                return httpx.Response(
                    status_code=201,
                    json={
                        "id": project_id,
                        "name": slug,
                        "path": slug,
                        "path_with_namespace": f"test-group/{slug}",
                        "http_url_to_repo": f"https://gitlab.example.com/test-group/{slug}.git",
                        "default_branch": "master",
                    },
                )
            return httpx.Response(status_code=status_code, json={"message": "error"})
        return httpx.Response(status_code=404)
    return handler


def mock_gitlab_search_project(status_code=200, project_id=456, found=True):
    """模拟 GET /api/v4/projects?search={url} (搜索仓库)"""
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and "/api/v4/projects" in str(request.url):
            if status_code == 200 and found:
                return httpx.Response(
                    status_code=200,
                    json=[{
                        "id": project_id,
                        "name": "existing-repo",
                        "http_url_to_repo": "https://gitlab.example.com/test-group/existing-repo.git",
                    }],
                )
            return httpx.Response(status_code=200, json=[])
        return httpx.Response(status_code=404)
    return handler


def mock_gitlab_get_project(status_code=200, project_id=789, has_permission=True):
    """模拟 GET /api/v4/projects/{id} (获取仓库详情)"""
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and "/api/v4/projects/" in str(request.url):
            if status_code == 200:
                return httpx.Response(
                    status_code=200,
                    json={
                        "id": project_id,
                        "name": "test-repo",
                        "http_url_to_repo": "https://gitlab.example.com/test-group/test-repo.git",
                        "permissions": {
                            "project_access": {"access_level": 40} if has_permission else None,
                        },
                    },
                )
            return httpx.Response(status_code=status_code, json={"message": "error"})
        return httpx.Response(status_code=404)
    return handler


def mock_gitlab_add_member(status_code=200, user_id=1, access_level=40):
    """模拟 POST /api/v4/projects/{id}/members (添加成员)"""
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and "/members" in str(request.url):
            if status_code == 200:
                return httpx.Response(
                    status_code=201,
                    json={
                        "id": 1,
                        "username": "testuser",
                        "access_level": access_level,
                    },
                )
            return httpx.Response(status_code=status_code, json={"message": "error"})
        return httpx.Response(status_code=404)
    return handler


def mock_gitlab_check_member(status_code=200, is_member=True, access_level=40):
    """模拟 GET /api/v4/projects/{id}/members/{user_id} (检查成员)"""
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and "/members/" in str(request.url):
            if status_code == 200 and is_member:
                return httpx.Response(
                    status_code=200,
                    json={
                        "id": 1,
                        "username": "testuser",
                        "access_level": access_level,
                    },
                )
            return httpx.Response(status_code=404, json={"message": "not found"})
        return httpx.Response(status_code=404)
    return handler


def mock_gitlab_user_api(status_code=200, username="testuser", scopes=None):
    """模拟 GET /api/v4/user (获取当前用户信息)"""
    if scopes is None:
        scopes = ["read_repository", "write_repository"]

    async def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and "/api/v4/user" in str(request.url):
            if status_code == 200:
                return httpx.Response(
                    status_code=200,
                    json={
                        "id": 1,
                        "username": username,
                        "name": "Test User",
                        "state": "active",
                    },
                    headers={
                        "X-Token-Name": "test-token",
                        "X-Token-Scopes": " ".join(scopes),
                    },
                )
            return httpx.Response(status_code=status_code, json={"message": "error"})
        return httpx.Response(status_code=404)
    return handler


# ---------------------------------------------------------------------------
# 创建项目 — auto 模式
# ---------------------------------------------------------------------------
class TestCreateProjectAuto:
    """auto 模式创建项目"""

    @pytest.mark.asyncio
    async def test_create_project_auto_success(self, client, auth_headers, db_session):
        """auto 模式创建项目成功"""
        await _seed_gitlab_settings(db_session)
        # mock GitLab API: 创建仓库 + 添加成员
        with httpx.MockTransport(mock_gitlab_create_project(200, project_id=123, slug="test-project")):
            resp = await client.post(
                "/api/projects",
                headers=auth_headers,
                json={
                    "name": "Test Project",
                    "description": "Test description",
                    "visibility": "private",
                    "default_branch": "master",
                    "main_repo": {
                        "bind_type": "auto",
                    },
                },
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 0
        assert "project_id" in data["data"]
        assert data["data"]["slug"] == "test-project"
        assert data["data"]["main_repo"]["gitlab_repo_id"] == 123

    @pytest.mark.asyncio
    async def test_create_project_auto_bot_token_not_configured(self, client, auth_headers):
        """bot token 未配置:返回 2001"""
        # 不 mock GitLab API,模拟 bot token 未配置场景
        resp = await client.post(
            "/api/projects",
            headers=auth_headers,
            json={
                "name": "Test Project",
                "visibility": "private",
                "main_repo": {"bind_type": "auto"},
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 2001
        assert "未配置" in data["message"] or "bot" in data["message"].lower()

    @pytest.mark.asyncio
    async def test_create_project_limit_exceeded(self, client, auth_headers, db_session, registered_user):
        """项目数超限 (>50):返回 2003"""
        await _seed_gitlab_settings(db_session)
        # 直插 50 个项目占满配额
        for _ in range(50):
            await _insert_project(db_session, registered_user["user_id"])
        with httpx.MockTransport(mock_gitlab_create_project(200)):
            resp = await client.post(
                "/api/projects",
                headers=auth_headers,
                json={
                    "name": "Project 51",
                    "visibility": "private",
                    "main_repo": {"bind_type": "auto"},
                },
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 2003
        assert "超限" in data["message"] or "limit" in data["message"].lower()


# ---------------------------------------------------------------------------
# 创建项目 — manual 模式
# ---------------------------------------------------------------------------
class TestCreateProjectManual:
    """manual 模式创建项目"""

    @pytest.mark.asyncio
    async def test_create_project_manual_success(self, client, auth_headers, db_session):
        """manual 模式创建项目成功"""
        await _seed_gitlab_settings(db_session)
        # mock GitLab API: 查仓库 + 校验权限
        with httpx.MockTransport(mock_gitlab_get_project(200, project_id=456, has_permission=True)):
            resp = await client.post(
                "/api/projects",
                headers=auth_headers,
                json={
                    "name": "Manual Project",
                    "description": "Manual binding",
                    "visibility": "private",
                    "main_repo": {
                        "bind_type": "manual",
                        "gitlab_repo_url": "https://gitlab.example.com/test-group/existing-repo.git",
                    },
                },
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 0
        assert "project_id" in data["data"]
        assert data["data"]["main_repo"]["gitlab_repo_id"] == 456

    @pytest.mark.asyncio
    async def test_create_project_invalid_repo_url(self, client, auth_headers, db_session):
        """GitLab 查仓库 404(仓库不存在):返回 2011(R27 细分,原折叠为 2002)"""
        await _seed_gitlab_settings(db_session)
        with httpx.MockTransport(mock_gitlab_get_project(404, has_permission=False)):
            resp = await client.post(
                "/api/projects",
                headers=auth_headers,
                json={
                    "name": "Invalid Project",
                    "visibility": "private",
                    "main_repo": {
                        "bind_type": "manual",
                        "gitlab_repo_url": "https://gitlab.example.com/nonexistent/repo.git",
                    },
                },
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 2011
        # R27 新文案:含平台 GitLab 地址指引(逐字前缀断言,gitlab_url 按平台配置插值)
        assert data["message"] == (
            "仓库不存在,请检查 group/repo 名称是否正确(仅支持平台 GitLab:https://gitlab.example.com)"
        )


# ---------------------------------------------------------------------------
# 项目列表
# ---------------------------------------------------------------------------
class TestProjectList:
    """项目列表"""

    @pytest.mark.asyncio
    async def test_project_list_empty(self, client, auth_headers):
        """空态:无项目时返回空列表"""
        resp = await client.get("/api/projects", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 0
        assert data["data"]["items"] == []
        assert data["data"]["total"] == 0

    @pytest.mark.asyncio
    async def test_project_list_with_projects(self, client, auth_headers, db_session, registered_user):
        """有项目时返回列表"""
        await _insert_project(db_session, registered_user["user_id"])
        resp = await client.get("/api/projects", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 0
        assert "items" in data["data"]
        assert "total" in data["data"]
        assert data["data"]["total"] >= 1

    @pytest.mark.asyncio
    async def test_project_list_pagination(self, client, auth_headers):
        """分页参数"""
        resp = await client.get(
            "/api/projects?page=1&page_size=10",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 0
        assert data["data"]["page"] == 1
        assert data["data"]["page_size"] == 10


# ---------------------------------------------------------------------------
# 项目详情
# ---------------------------------------------------------------------------
class TestProjectDetail:
    """项目详情"""

    @pytest.mark.asyncio
    async def test_project_detail_success(self, client, auth_headers, db_session, registered_user):
        """获取项目详情成功"""
        project = await _insert_project(db_session, registered_user["user_id"])
        resp = await client.get(f"/api/projects/{project.project_id}", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 0
        assert data["data"]["project_id"] == project.project_id
        assert "repos" in data["data"]

    @pytest.mark.asyncio
    async def test_project_detail_not_found(self, client, auth_headers):
        """项目不存在:返回 404"""
        fake_project_id = "00000000-0000-0000-0000-999999999999"
        resp = await client.get(f"/api/projects/{fake_project_id}", headers=auth_headers)
        assert resp.status_code in (200, 404)
        data = resp.json()
        # 预期返回业务错误码或 404
        assert data["code"] != 0 or resp.status_code == 404


# ---------------------------------------------------------------------------
# 更新项目
# ---------------------------------------------------------------------------
class TestProjectUpdate:
    """更新项目"""

    @pytest.mark.asyncio
    async def test_project_update_success(self, client, auth_headers, db_session, registered_user):
        """更新项目成功 (owner)"""
        project = await _insert_project(db_session, registered_user["user_id"])
        resp = await client.patch(
            f"/api/projects/{project.project_id}",
            headers=auth_headers,
            json={
                "name": "Updated Project Name",
                "description": "Updated description",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 0
        assert data["data"]["name"] == "Updated Project Name"

    @pytest.mark.asyncio
    async def test_project_update_non_owner(self, client, auth_headers, db_session, registered_user):
        """非 owner 更新项目:返回 403"""
        project = await _insert_project(db_session, registered_user["user_id"])
        other_headers, _uid = await _register_and_login(client)
        resp = await client.patch(
            f"/api/projects/{project.project_id}",
            headers=other_headers,
            json={"name": "Updated Name"},
        )
        assert resp.status_code in (200, 403)
        data = resp.json()
        # 预期返回权限错误
        assert data["code"] != 0 or resp.status_code == 403


# ---------------------------------------------------------------------------
# 删除项目
# ---------------------------------------------------------------------------
class TestProjectDelete:
    """删除项目"""

    @pytest.mark.asyncio
    async def test_project_delete_success(self, client, auth_headers, db_session, registered_user):
        """删除项目成功 (软删)"""
        project = await _insert_project(db_session, registered_user["user_id"])
        resp = await client.delete(f"/api/projects/{project.project_id}", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 0
        assert "删除" in data["message"] or "delete" in data["message"].lower()


# ---------------------------------------------------------------------------
# 归档项目
# ---------------------------------------------------------------------------
class TestProjectArchive:
    """归档项目"""

    @pytest.mark.asyncio
    async def test_project_archive_success(self, client, auth_headers, db_session, registered_user):
        """归档项目成功"""
        project = await _insert_project(db_session, registered_user["user_id"])
        resp = await client.post(
            f"/api/projects/{project.project_id}/archive",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 0
        assert "归档" in data["message"] or "archive" in data["message"].lower()


# ---------------------------------------------------------------------------
# 追加绑定仓库
# ---------------------------------------------------------------------------
class TestAddRepo:
    """追加绑定仓库"""

    @pytest.mark.asyncio
    async def test_add_repo_success(self, client, auth_headers, db_session, registered_user):
        """追加绑定仓库成功 (test/docs/other)"""
        await _seed_gitlab_settings(db_session)
        project = await _insert_project(db_session, registered_user["user_id"])
        with httpx.MockTransport(mock_gitlab_get_project(200, project_id=789)):
            resp = await client.post(
                f"/api/projects/{project.project_id}/repos",
                headers=auth_headers,
                json={
                    "role": "test",
                    "gitlab_repo_url": "https://gitlab.example.com/test-group/test-repo.git",
                },
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 0
        assert data["data"]["role"] == "test"
        assert data["data"]["gitlab_repo_id"] == 789

    @pytest.mark.asyncio
    async def test_add_repo_duplicate(self, client, auth_headers, db_session, registered_user):
        """同一 repo 重复绑定:返回 2004"""
        await _seed_gitlab_settings(db_session)
        project = await _insert_project(db_session, registered_user["user_id"])
        # 已绑定 gitlab_repo_id=789
        await _insert_repo(db_session, project.project_id, registered_user["user_id"],
                           role="test", gitlab_repo_id=789)
        with httpx.MockTransport(mock_gitlab_get_project(200, project_id=789)):
            resp = await client.post(
                f"/api/projects/{project.project_id}/repos",
                headers=auth_headers,
                json={
                    "role": "docs",
                    "gitlab_repo_url": "https://gitlab.example.com/test-group/duplicate-repo.git",
                },
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 2004
        assert "已绑定" in data["message"] or "duplicate" in data["message"].lower()

    @pytest.mark.asyncio
    async def test_add_repo_limit_exceeded(self, client, auth_headers, db_session, registered_user):
        """绑定数超限 (>10):返回 2005"""
        await _seed_gitlab_settings(db_session)
        project = await _insert_project(db_session, registered_user["user_id"])
        # 直插 10 条绑定占满配额
        for i in range(10):
            await _insert_repo(db_session, project.project_id, registered_user["user_id"],
                               role="other", gitlab_repo_id=1000 + i)
        with httpx.MockTransport(mock_gitlab_get_project(200, project_id=789)):
            resp = await client.post(
                f"/api/projects/{project.project_id}/repos",
                headers=auth_headers,
                json={
                    "role": "test",
                    "gitlab_repo_url": "https://gitlab.example.com/test-group/repo-11.git",
                },
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 2005
        assert "超限" in data["message"] or "limit" in data["message"].lower()


# ---------------------------------------------------------------------------
# 解绑仓库
# ---------------------------------------------------------------------------
class TestUnbindRepo:
    """解绑仓库"""

    @pytest.mark.asyncio
    async def test_unbind_repo_success(self, client, auth_headers, db_session, registered_user):
        """解绑仓库成功 (非 main)"""
        project = await _insert_project(db_session, registered_user["user_id"])
        repo = await _insert_repo(db_session, project.project_id, registered_user["user_id"], role="test")
        resp = await client.delete(
            f"/api/projects/{project.project_id}/repos/{repo.repo_id}",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 0
        assert "解绑" in data["message"] or "unbind" in data["message"].lower()

    @pytest.mark.asyncio
    async def test_unbind_main_repo(self, client, auth_headers, db_session, registered_user):
        """解绑 main repo:返回 2006"""
        project = await _insert_project(db_session, registered_user["user_id"])
        main_repo = await _insert_repo(db_session, project.project_id, registered_user["user_id"], role="main")
        resp = await client.delete(
            f"/api/projects/{project.project_id}/repos/{main_repo.repo_id}",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 2006
        assert "主仓库" in data["message"] or "main" in data["message"].lower()


# ---------------------------------------------------------------------------
# slug 唯一性
# ---------------------------------------------------------------------------
class TestSlugUniqueness:
    """slug 唯一性"""

    @pytest.mark.asyncio
    async def test_slug_unique_auto_suffix(self, client, auth_headers, db_session):
        """slug 冲突自动加后缀"""
        await _seed_gitlab_settings(db_session)
        # 先创建一个项目 slug="test-project"
        # 再创建同名项目,预期 slug="test-project-xxxx"
        with httpx.MockTransport(mock_gitlab_create_project(200, slug="test-project")):
            resp1 = await client.post(
                "/api/projects",
                headers=auth_headers,
                json={
                    "name": "Test Project",
                    "visibility": "private",
                    "main_repo": {"bind_type": "auto"},
                },
            )
        assert resp1.status_code == 200

        # 第二次创建同名项目
        with httpx.MockTransport(mock_gitlab_create_project(200, slug="test-project-abc123")):
            resp2 = await client.post(
                "/api/projects",
                headers=auth_headers,
                json={
                    "name": "Test Project",
                    "visibility": "private",
                    "main_repo": {"bind_type": "auto"},
                },
            )
        assert resp2.status_code == 200
        data = resp2.json()
        assert data["code"] == 0
        # slug 应该自动加后缀
        assert data["data"]["slug"].startswith("test-project-")


# ---------------------------------------------------------------------------
# 权限矩阵
# ---------------------------------------------------------------------------
class TestPermissionMatrix:
    """权限矩阵"""

    @pytest.mark.asyncio
    async def test_non_owner_cannot_delete(self, client, auth_headers, db_session, registered_user):
        """非 owner 不能删除项目"""
        project = await _insert_project(db_session, registered_user["user_id"])
        other_headers, _uid = await _register_and_login(client)
        resp = await client.delete(f"/api/projects/{project.project_id}", headers=other_headers)
        assert resp.status_code in (200, 403)
        data = resp.json()
        assert data["code"] != 0 or resp.status_code == 403

    @pytest.mark.asyncio
    async def test_non_owner_cannot_archive(self, client, auth_headers, db_session, registered_user):
        """非 owner 不能归档项目"""
        project = await _insert_project(db_session, registered_user["user_id"])
        other_headers, _uid = await _register_and_login(client)
        resp = await client.post(
            f"/api/projects/{project.project_id}/archive",
            headers=other_headers,
        )
        assert resp.status_code in (200, 403)
        data = resp.json()
        assert data["code"] != 0 or resp.status_code == 403


# ---------------------------------------------------------------------------
# 鉴权校验
# ---------------------------------------------------------------------------
class TestProjectAuth:
    """项目接口鉴权校验"""

    @pytest.mark.asyncio
    async def test_create_project_no_auth_returns_401(self, client):
        """未登录创建项目:返回 401"""
        resp = await client.post(
            "/api/projects",
            json={
                "name": "Test Project",
                "visibility": "private",
                "main_repo": {"bind_type": "auto"},
            },
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_list_projects_no_auth_returns_401(self, client):
        """未登录查看项目列表:返回 401"""
        resp = await client.get("/api/projects")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_get_project_detail_no_auth_returns_401(self, client):
        """未登录查看项目详情:返回 401"""
        fake_project_id = "00000000-0000-0000-0000-000000000001"
        resp = await client.get(f"/api/projects/{fake_project_id}")
        assert resp.status_code == 401
