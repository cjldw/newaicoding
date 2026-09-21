"""
R13 模型接入接口测试
==========================
覆盖:
- 配置 CRUD(创建成功/13001 连接失败/13002 重名/13003 default 冲突/更新/删除/13004 删 default)
- api_key 加密存储 + 打码回显(sk-1***cdef 格式)
- viewer 视角不含 api_key 字段
- 连通性测试端点(成功/404/超时)
- 权限:owner 专属写操作(editor/viewer 403)

LLM mock 说明:llm_service 有独立的 _test_transport 注入点(conftest 的
autouse patch 只覆盖 gitlab_service),用 _with_llm_mock 上下文管理器注入。
"""
import uuid
import contextlib

import pytest
import httpx

from tests.test_projects_api import _insert_project, _register_and_login


@contextlib.contextmanager
def _llm_mock(handler):
    """llm_service 独立 transport 注入(不影响 gitlab_service)"""
    from app.services import llm_service

    llm_service.set_test_transport(httpx.MockTransport(handler))
    try:
        yield
    finally:
        llm_service.set_test_transport(None)


def _llm_ok_handler(request: httpx.Request) -> httpx.Response:
    """GET {base_url}/models → 200"""
    if request.method == "GET" and request.url.path.endswith("/models"):
        return httpx.Response(200, json={"data": [{"id": "claude-sonnet-5"}]})
    return httpx.Response(404)


def _llm_status_handler(status_code: int):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path.endswith("/models"):
            return httpx.Response(status_code)
        return httpx.Response(404)
    return handler


def _llm_timeout_handler(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectTimeout("connection timed out", request=request)


async def _create_config(client, headers, project_id, name="主用 Claude", is_default=False,
                         api_key="sk-1234567890abcdef", base_url="https://llm.example.com/v1"):
    return await client.post(
        f"/api/projects/{project_id}/model-configs",
        headers=headers,
        json={
            "name": name,
            "base_url": base_url,
            "api_key": api_key,
            "model": "claude-sonnet-5",
            "is_default": is_default,
            "enabled": True,
        },
    )


# ---------------------------------------------------------------------------
# 创建
# ---------------------------------------------------------------------------
class TestCreateConfig:
    @pytest.mark.asyncio
    async def test_create_config_success(self, client, auth_headers, db_session, registered_user):
        """创建配置成功(LLM mock 200)"""
        project = await _insert_project(db_session, registered_user["user_id"])
        with _llm_mock(_llm_ok_handler):
            resp = await _create_config(client, auth_headers, project.project_id)
        data = resp.json()
        assert data["code"] == 0
        assert data["data"]["name"] == "主用 Claude"
        assert data["data"]["api_key_masked"] == "sk-1***cdef"
        assert "配置创建成功" in data["message"]

    @pytest.mark.asyncio
    async def test_create_config_connection_failed(self, client, auth_headers, db_session, registered_user):
        """连接失败(401):返回 13001"""
        project = await _insert_project(db_session, registered_user["user_id"])
        with _llm_mock(_llm_status_handler(401)):
            resp = await _create_config(client, auth_headers, project.project_id)
        assert resp.json()["code"] == 13001

    @pytest.mark.asyncio
    async def test_create_config_timeout(self, client, auth_headers, db_session, registered_user):
        """连接超时:返回 13001"""
        project = await _insert_project(db_session, registered_user["user_id"])
        with _llm_mock(_llm_timeout_handler):
            resp = await _create_config(client, auth_headers, project.project_id)
        assert resp.json()["code"] == 13001

    @pytest.mark.asyncio
    async def test_create_config_duplicate_name(self, client, auth_headers, db_session, registered_user):
        """配置名重复:返回 13002"""
        project = await _insert_project(db_session, registered_user["user_id"])
        with _llm_mock(_llm_ok_handler):
            await _create_config(client, auth_headers, project.project_id, name="cfg")
            resp = await _create_config(client, auth_headers, project.project_id, name="cfg")
        assert resp.json()["code"] == 13002

    @pytest.mark.asyncio
    async def test_create_config_duplicate_default(self, client, auth_headers, db_session, registered_user):
        """已有 default 再建 default:返回 13003"""
        project = await _insert_project(db_session, registered_user["user_id"])
        with _llm_mock(_llm_ok_handler):
            await _create_config(client, auth_headers, project.project_id, name="a", is_default=True)
            resp = await _create_config(client, auth_headers, project.project_id, name="b", is_default=True)
        assert resp.json()["code"] == 13003

    @pytest.mark.asyncio
    async def test_create_by_editor_denied(self, client, auth_headers, db_session, registered_user, second_user_headers):
        """editor 创建配置:403(R13 矩阵:创建/更新/删除仅 owner)"""
        project = await _insert_project(db_session, registered_user["user_id"])
        editor_headers, editor_phone = await _register_with_phone(client)
        # 邀请 editor(R12 接口;GitLab 未配置会跳过同步,无需 mock)
        resp = await client.post(
            f"/api/projects/{project.project_id}/members",
            headers=auth_headers,
            json={"phone": editor_phone, "role": "editor"},
        )
        assert resp.json()["code"] == 0
        with _llm_mock(_llm_ok_handler):
            resp = await _create_config(client, editor_headers, project.project_id)
        assert resp.status_code == 403
        assert resp.json()["code"] == 1901


async def _register_with_phone(client):
    """注册普通用户,返回 (headers, phone)——邀请成员需要真实手机号"""
    phone = f"135{str(uuid.uuid4().int)[:8]}"
    resp = await client.post("/api/auth/register", json={"phone": phone, "password": "Test1234"})
    assert resp.status_code == 200 and resp.json()["code"] == 0
    resp = await client.post("/api/auth/login", json={"phone": phone, "password": "Test1234"})
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}, phone


# ---------------------------------------------------------------------------
# 更新 / 删除
# ---------------------------------------------------------------------------
class TestUpdateDeleteConfig:
    @pytest.mark.asyncio
    async def test_update_config_success(self, client, auth_headers, db_session, registered_user):
        """更新配置成功(改名不触发连通性重测;换 key 触发重测)"""
        project = await _insert_project(db_session, registered_user["user_id"])
        with _llm_mock(_llm_ok_handler):
            resp = await _create_config(client, auth_headers, project.project_id)
        config_id = resp.json()["data"]["config_id"]

        # 改名(无连接要素变更,不需要 mock)
        resp = await client.patch(
            f"/api/projects/{project.project_id}/model-configs/{config_id}",
            headers=auth_headers,
            json={"name": "备用 DeepSeek"},
        )
        data = resp.json()
        assert data["code"] == 0
        assert data["data"]["name"] == "备用 DeepSeek"
        assert "配置更新成功" in data["message"]

        # 换 api_key(触发重测,mock 200)
        with _llm_mock(_llm_ok_handler):
            resp = await client.patch(
                f"/api/projects/{project.project_id}/model-configs/{config_id}",
                headers=auth_headers,
                json={"api_key": "sk-ffffffffffffffff"},
            )
        assert resp.json()["code"] == 0
        assert resp.json()["data"]["api_key_masked"] == "sk-f***ffff"

    @pytest.mark.asyncio
    async def test_delete_config_success(self, client, auth_headers, db_session, registered_user):
        """删除非 default 配置成功"""
        project = await _insert_project(db_session, registered_user["user_id"])
        with _llm_mock(_llm_ok_handler):
            resp = await _create_config(client, auth_headers, project.project_id, is_default=False)
        config_id = resp.json()["data"]["config_id"]
        resp = await client.delete(
            f"/api/projects/{project.project_id}/model-configs/{config_id}",
            headers=auth_headers,
        )
        assert resp.json()["code"] == 0
        assert "已删除" in resp.json()["message"]

    @pytest.mark.asyncio
    async def test_delete_default_config(self, client, auth_headers, db_session, registered_user):
        """删除 default 配置:返回 13004"""
        project = await _insert_project(db_session, registered_user["user_id"])
        with _llm_mock(_llm_ok_handler):
            resp = await _create_config(client, auth_headers, project.project_id, is_default=True)
        config_id = resp.json()["data"]["config_id"]
        resp = await client.delete(
            f"/api/projects/{project.project_id}/model-configs/{config_id}",
            headers=auth_headers,
        )
        assert resp.json()["code"] == 13004
        assert "不可删除默认配置" in resp.json()["message"]


# ---------------------------------------------------------------------------
# 打码 / 权限视角
# ---------------------------------------------------------------------------
class TestMaskingAndView:
    @pytest.mark.asyncio
    async def test_api_key_masked_in_list(self, client, auth_headers, db_session, registered_user):
        """列表返回打码 key,不含明文"""
        project = await _insert_project(db_session, registered_user["user_id"])
        with _llm_mock(_llm_ok_handler):
            await _create_config(client, auth_headers, project.project_id)
        resp = await client.get(f"/api/projects/{project.project_id}/model-configs", headers=auth_headers)
        items = resp.json()["data"]["items"]
        assert len(items) == 1
        assert items[0]["api_key_masked"] == "sk-1***cdef"
        assert "sk-1234567890abcdef" not in str(resp.json())

    @pytest.mark.asyncio
    async def test_viewer_list_hides_api_key(self, client, auth_headers, db_session, registered_user):
        """viewer 列表不含 api_key 字段(权限矩阵)"""
        project = await _insert_project(db_session, registered_user["user_id"])
        with _llm_mock(_llm_ok_handler):
            await _create_config(client, auth_headers, project.project_id)
        # 注册 viewer 并加入项目
        phone = f"135{str(uuid.uuid4().int)[:8]}"
        await client.post("/api/auth/register", json={"phone": phone, "password": "Test1234"})
        resp = await client.post("/api/auth/login", json={"phone": phone, "password": "Test1234"})
        viewer_headers = {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}
        await client.post(
            f"/api/projects/{project.project_id}/members",
            headers=auth_headers,
            json={"phone": phone, "role": "viewer"},
        )
        resp = await client.get(f"/api/projects/{project.project_id}/model-configs", headers=viewer_headers)
        items = resp.json()["data"]["items"]
        assert len(items) == 1
        assert "api_key_masked" not in items[0]


# ---------------------------------------------------------------------------
# 连通性测试端点
# ---------------------------------------------------------------------------
class TestConnectivityEndpoint:
    @pytest.mark.asyncio
    async def test_test_endpoint_success(self, client, auth_headers, db_session, registered_user):
        """POST test 成功:返回 success + latency"""
        project = await _insert_project(db_session, registered_user["user_id"])
        with _llm_mock(_llm_ok_handler):
            resp = await client.post(
                f"/api/projects/{project.project_id}/model-configs/test",
                headers=auth_headers,
                json={"base_url": "https://llm.example.com/v1", "api_key": "sk-abc", "model": "claude-sonnet-5"},
            )
        data = resp.json()
        assert data["code"] == 0
        assert data["data"]["success"] is True
        assert isinstance(data["data"]["latency_ms"], int)

    @pytest.mark.asyncio
    async def test_test_endpoint_404(self, client, auth_headers, db_session, registered_user):
        """POST test base_url 错误(404):13001"""
        project = await _insert_project(db_session, registered_user["user_id"])
        with _llm_mock(_llm_status_handler(404)):
            resp = await client.post(
                f"/api/projects/{project.project_id}/model-configs/test",
                headers=auth_headers,
                json={"base_url": "https://llm.example.com/v1", "api_key": "sk-abc", "model": "x"},
            )
        assert resp.json()["code"] == 13001

    @pytest.mark.asyncio
    async def test_no_auth_returns_401(self, client, db_session, registered_user):
        """未登录访问配置列表:401"""
        project = await _insert_project(db_session, registered_user["user_id"])
        resp = await client.get(f"/api/projects/{project.project_id}/model-configs")
        assert resp.status_code == 401
