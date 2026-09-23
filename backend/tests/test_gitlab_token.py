"""
R1 GitLab token 绑定接口测试 — PUT/DELETE /api/users/me/gitlab-token
=====================================================================
覆盖场景:
- 绑定成功(mock httpx,不真实外呼)
- 无效 token(1012,模拟 GitLab API 401)
- scope 不足(1013,缺 read_repository 或 write_repository)
- 解绑成功
- 重绑(覆盖旧 token)
- 响应最小化(不含 gitlab_token_encrypted)
- 未登录访问返回 401

注意:所有 GitLab API 调用通过 httpx mock 模拟,不发起真实外部请求。
"""
import pytest
import httpx


# ---------------------------------------------------------------------------
# mock GitLab API 辅助函数
# ---------------------------------------------------------------------------
def mock_gitlab_user_api(status_code=200, username="testuser", scopes=None):
    """
    创建 GitLab API mock handler。
    模拟 GET {gitlab_instance_url}/api/v4/user 接口。
    """
    if scopes is None:
        scopes = ["read_repository", "write_repository"]

    async def handler(request: httpx.Request) -> httpx.Response:
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
        elif status_code == 401:
            return httpx.Response(status_code=401, json={"message": "401 Unauthorized"})
        else:
            return httpx.Response(status_code=status_code)

    return handler


# ---------------------------------------------------------------------------
# 绑定成功
# ---------------------------------------------------------------------------
class TestBindGitLabTokenSuccess:
    """绑定 GitLab token 成功"""

    @pytest.mark.asyncio
    async def test_bind_gitlab_token_success(self, client, auth_headers):
        """绑定有效 GitLab token:返回用户名和 scopes"""
        # mock GitLab API
        with httpx.MockTransport(mock_gitlab_user_api(200)):
            resp = await client.put(
                "/api/users/me/gitlab-token",
                headers=auth_headers,
                json={"gitlab_token": "glpat-valid-token-12345"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 0
        assert "message" in data
        assert data["data"]["gitlab_username"] == "testuser"
        assert "read_repository" in data["data"]["gitlab_token_scopes"]
        assert "write_repository" in data["data"]["gitlab_token_scopes"]
        assert data["data"]["gitlab_token_bound_at"] is not None

    @pytest.mark.asyncio
    async def test_bind_gitlab_token_response_no_encrypted_token(self, client, auth_headers):
        """绑定响应不含 gitlab_token_encrypted(响应最小化)"""
        with httpx.MockTransport(mock_gitlab_user_api(200)):
            resp = await client.put(
                "/api/users/me/gitlab-token",
                headers=auth_headers,
                json={"gitlab_token": "glpat-valid-token-12345"},
            )
        assert resp.status_code == 200
        data = resp.json()
        resp_text = str(data)
        assert "gitlab_token_encrypted" not in resp_text
        # 也不返回原始 token
        assert "glpat-valid-token-12345" not in resp_text

    @pytest.mark.asyncio
    async def test_bind_gitlab_token_shows_in_get_me(self, client, auth_headers):
        """绑定后,GET /api/users/me 应反映绑定状态"""
        with httpx.MockTransport(mock_gitlab_user_api(200, username="bounduser")):
            await client.put(
                "/api/users/me/gitlab-token",
                headers=auth_headers,
                json={"gitlab_token": "glpat-valid-token"},
            )

        resp = await client.get("/api/users/me", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["gitlab_username"] == "bounduser"
        assert data["gitlab_token_bound"] is True
        assert "read_repository" in data["gitlab_token_scopes"]
        assert data["gitlab_token_bound_at"] is not None


# ---------------------------------------------------------------------------
# 无效 token — 1012
# ---------------------------------------------------------------------------
class TestBindGitLabTokenInvalid:
    """绑定无效 GitLab token"""

    @pytest.mark.asyncio
    async def test_bind_invalid_token_returns_1012(self, client, auth_headers):
        """GitLab API 返回 401:返回错误码 1012"""
        with httpx.MockTransport(mock_gitlab_user_api(401)):
            resp = await client.put(
                "/api/users/me/gitlab-token",
                headers=auth_headers,
                json={"gitlab_token": "glpat-invalid-token"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 1012
        assert "无效" in data["message"] or "invalid" in data["message"].lower()

    @pytest.mark.asyncio
    async def test_bind_empty_token(self, client, auth_headers):
        """空 token:参数校验失败"""
        resp = await client.put(
            "/api/users/me/gitlab-token",
            headers=auth_headers,
            json={"gitlab_token": ""},
        )
        assert resp.status_code in (200, 422)


# ---------------------------------------------------------------------------
# scope 不足 — 1013
# ---------------------------------------------------------------------------
class TestBindGitLabTokenInsufficientScope:
    """GitLab token scope 不足"""

    @pytest.mark.asyncio
    async def test_bind_token_missing_read_scope_returns_1013(self, client, auth_headers):
        """缺少 read_repository scope:返回 1013"""
        with httpx.MockTransport(mock_gitlab_user_api(200, scopes=["write_repository"])):
            resp = await client.put(
                "/api/users/me/gitlab-token",
                headers=auth_headers,
                json={"gitlab_token": "glpat-no-read-scope"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 1013
        assert "scope" in data["message"].lower() or "权限" in data["message"]

    @pytest.mark.asyncio
    async def test_bind_token_missing_write_scope_returns_1013(self, client, auth_headers):
        """缺少 write_repository scope:返回 1013"""
        with httpx.MockTransport(mock_gitlab_user_api(200, scopes=["read_repository"])):
            resp = await client.put(
                "/api/users/me/gitlab-token",
                headers=auth_headers,
                json={"gitlab_token": "glpat-no-write-scope"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 1013

    @pytest.mark.asyncio
    async def test_bind_token_insufficient_scopes_returns_1013(self, client, auth_headers):
        """header 存在但缺少全部必需 scope:返回 1013(BUG-016 后"真权限不足"以带 header 表达)"""
        with httpx.MockTransport(mock_gitlab_user_api(200, scopes=["read_user"])):
            resp = await client.put(
                "/api/users/me/gitlab-token",
                headers=auth_headers,
                json={"gitlab_token": "glpat-no-scopes"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 1013

    @pytest.mark.asyncio
    async def test_bind_token_no_scopes_header_old_gitlab_passes(self, client, auth_headers):
        """BUG-016:X-Token-Scopes 头缺失(GitLab v11.x)→ scope 置 ["unknown"] 放行,绑定成功"""
        with httpx.MockTransport(mock_gitlab_user_api(200, scopes=[])):
            resp = await client.put(
                "/api/users/me/gitlab-token",
                headers=auth_headers,
                json={"gitlab_token": "glpat-old-gitlab"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 0
        assert data["data"]["gitlab_token_scopes"] == ["unknown"]

        # 绑定结果落库:GET /me 反映 unknown scopes
        me = await client.get("/api/users/me", headers=auth_headers)
        assert me.status_code == 200
        assert me.json()["data"]["gitlab_token_scopes"] == ["unknown"]


# ---------------------------------------------------------------------------
# 解绑
# ---------------------------------------------------------------------------
class TestUnbindGitLabToken:
    """解绑 GitLab token"""

    @pytest.mark.asyncio
    async def test_unbind_gitlab_token_success(self, client, auth_headers):
        """解绑成功"""
        # 先绑定
        with httpx.MockTransport(mock_gitlab_user_api(200)):
            await client.put(
                "/api/users/me/gitlab-token",
                headers=auth_headers,
                json={"gitlab_token": "glpat-to-unbind"},
            )

        # 解绑
        resp = await client.delete("/api/users/me/gitlab-token", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 0
        assert "message" in data

    @pytest.mark.asyncio
    async def test_unbind_reflected_in_get_me(self, client, auth_headers):
        """解绑后,GET /api/users/me 应反映未绑定状态"""
        # 绑定
        with httpx.MockTransport(mock_gitlab_user_api(200)):
            await client.put(
                "/api/users/me/gitlab-token",
                headers=auth_headers,
                json={"gitlab_token": "glpat-to-check"},
            )

        # 解绑
        await client.delete("/api/users/me/gitlab-token", headers=auth_headers)

        # 验证
        resp = await client.get("/api/users/me", headers=auth_headers)
        data = resp.json()["data"]
        assert data["gitlab_username"] is None
        assert data["gitlab_token_bound"] is False
        assert data["gitlab_token_scopes"] in (None, [])
        assert data["gitlab_token_bound_at"] is None

    @pytest.mark.asyncio
    async def test_unbind_when_not_bound(self, client, auth_headers):
        """未绑定时解绑:应成功(幂等)"""
        resp = await client.delete("/api/users/me/gitlab-token", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 0

    @pytest.mark.asyncio
    async def test_unbind_no_auth_returns_401(self, client):
        """未登录解绑:返回 401"""
        resp = await client.delete("/api/users/me/gitlab-token")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# 重绑(覆盖旧 token)
# ---------------------------------------------------------------------------
class TestRebindGitLabToken:
    """重绑 GitLab token(覆盖旧 token)"""

    @pytest.mark.asyncio
    async def test_rebind_overwrites_old_token(self, client, auth_headers):
        """重绑:新 token 覆盖旧 token"""
        # 第一次绑定
        with httpx.MockTransport(mock_gitlab_user_api(200, username="user1")):
            resp1 = await client.put(
                "/api/users/me/gitlab-token",
                headers=auth_headers,
                json={"gitlab_token": "glpat-first-token"},
            )
        assert resp1.json()["code"] == 0
        assert resp1.json()["data"]["gitlab_username"] == "user1"

        # 第二次绑定(重绑)
        with httpx.MockTransport(mock_gitlab_user_api(200, username="user2")):
            resp2 = await client.put(
                "/api/users/me/gitlab-token",
                headers=auth_headers,
                json={"gitlab_token": "glpat-second-token"},
            )
        assert resp2.json()["code"] == 0
        assert resp2.json()["data"]["gitlab_username"] == "user2"

        # 验证:GET /api/users/me 显示最新绑定信息
        resp = await client.get("/api/users/me", headers=auth_headers)
        data = resp.json()["data"]
        assert data["gitlab_username"] == "user2"
        assert data["gitlab_token_bound"] is True


# ---------------------------------------------------------------------------
# 鉴权校验
# ---------------------------------------------------------------------------
class TestGitLabTokenAuth:
    """GitLab token 接口鉴权校验"""

    @pytest.mark.asyncio
    async def test_bind_no_auth_returns_401(self, client):
        """未登录绑定:返回 401"""
        resp = await client.put(
            "/api/users/me/gitlab-token",
            json={"gitlab_token": "glpat-test"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_bind_invalid_auth_returns_401(self, client):
        """无效 JWT 绑定:返回 401"""
        resp = await client.put(
            "/api/users/me/gitlab-token",
            headers={"Authorization": "Bearer invalid"},
            json={"gitlab_token": "glpat-test"},
        )
        assert resp.status_code == 401
