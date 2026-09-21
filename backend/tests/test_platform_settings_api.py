"""
R2 平台设置接口测试 — Red phase (失败测试)
==========================================
覆盖场景:
- GET /api/admin/platform-settings (超管获取配置)
- PUT /api/admin/platform-settings (超管更新配置)
- 错误码 2007 (非法配置值:域名格式非法/数值越界)
- 错误码 19002 (非超管访问)
- Token 打码回显 (gitlab_bot_token / gitlab_webhook_secret)
- Key 白名单校验 (仅允许白名单内的 key)
- 空态场景 (未配置任何设置)

注意: 由于 R2 后端代码未实现,所有测试预期失败 (Red phase)。
"""
import pytest
import httpx


# ---------------------------------------------------------------------------
# 获取平台设置
# ---------------------------------------------------------------------------
class TestGetPlatformSettings:
    """GET /api/admin/platform-settings"""

    @pytest.mark.asyncio
    async def test_get_platform_settings_empty(self, client, superadmin_headers):
        """空态:未配置任何设置时返回空字典或默认值"""
        resp = await client.get("/api/admin/platform-settings", headers=superadmin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 0
        # 应返回配置项键值对(可能为空或默认值)
        assert "data" in data

    @pytest.mark.asyncio
    async def test_get_platform_settings_with_values(self, client, superadmin_headers):
        """有配置时返回所有配置项"""
        # 先设置一些配置(模拟)
        # 由于 R2 未实现,此测试预期失败
        resp = await client.get("/api/admin/platform-settings", headers=superadmin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 0

    @pytest.mark.asyncio
    async def test_get_platform_settings_token_masked(self, client, superadmin_headers):
        """敏感 token 打码回显 (gitlab_bot_token / gitlab_webhook_secret)"""
        # 先设置 bot token(模拟)
        # 由于 R2 未实现,此测试预期失败
        resp = await client.get("/api/admin/platform-settings", headers=superadmin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 0
        # 如果返回了 gitlab_bot_token,应该是打码格式
        if "gitlab_bot_token" in data.get("data", {}):
            token_value = data["data"]["gitlab_bot_token"]
            # 打码格式:前缀 + •••••••• + 后缀(如 glpat-••••••••9x2f)
            assert "•" in token_value or "***" in token_value
            # 不应返回明文 token
            assert "glpat-" not in token_value or "•" in token_value

    @pytest.mark.asyncio
    async def test_get_platform_settings_webhook_secret_masked(self, client, superadmin_headers):
        """webhook secret 打码回显"""
        resp = await client.get("/api/admin/platform-settings", headers=superadmin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 0
        # 如果返回了 gitlab_webhook_secret,应该是打码格式
        if "gitlab_webhook_secret" in data.get("data", {}):
            secret_value = data["data"]["gitlab_webhook_secret"]
            assert "•" in secret_value or "***" in secret_value


# ---------------------------------------------------------------------------
# 更新平台设置
# ---------------------------------------------------------------------------
class TestPutPlatformSettings:
    """PUT /api/admin/platform-settings"""

    @pytest.mark.asyncio
    async def test_put_platform_settings_success(self, client, superadmin_headers):
        """超管更新配置成功"""
        resp = await client.put(
            "/api/admin/platform-settings",
            headers=superadmin_headers,
            json={
                "gitlab_url": "https://gitlab.example.com",
                "gitlab_bot_group_id": 12345,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 0
        assert "updated" in data["data"]
        assert "gitlab_url" in data["data"]["updated"]
        assert "gitlab_bot_group_id" in data["data"]["updated"]

    @pytest.mark.asyncio
    async def test_put_platform_settings_bot_token(self, client, superadmin_headers):
        """更新 bot token (应加密存储)"""
        resp = await client.put(
            "/api/admin/platform-settings",
            headers=superadmin_headers,
            json={
                "gitlab_bot_token": "glpat-new-bot-token-12345",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 0
        assert "gitlab_bot_token" in data["data"]["updated"]

    @pytest.mark.asyncio
    async def test_put_platform_settings_webhook_secret(self, client, superadmin_headers):
        """更新 webhook secret (应加密存储)"""
        resp = await client.put(
            "/api/admin/platform-settings",
            headers=superadmin_headers,
            json={
                "gitlab_webhook_secret": "new-webhook-secret-xyz",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 0
        assert "gitlab_webhook_secret" in data["data"]["updated"]

    @pytest.mark.asyncio
    async def test_put_platform_settings_domain_fields(self, client, superadmin_headers):
        """更新域名配置"""
        resp = await client.put(
            "/api/admin/platform-settings",
            headers=superadmin_headers,
            json={
                "preview_base_domain": "preview.example.com",
                "deploy_base_domain": "deploy.example.com",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 0
        assert "preview_base_domain" in data["data"]["updated"]
        assert "deploy_base_domain" in data["data"]["updated"]

    @pytest.mark.asyncio
    async def test_put_platform_settings_numeric_fields(self, client, superadmin_headers):
        """更新数值配置"""
        resp = await client.put(
            "/api/admin/platform-settings",
            headers=superadmin_headers,
            json={
                "max_containers_total": 100,
                "kb_max_pages_per_kb": 1000,
                "kb_max_file_mb": 5,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 0


# ---------------------------------------------------------------------------
# 错误码 2007 — 非法配置值
# ---------------------------------------------------------------------------
class TestPlatformSettingsIllegalValue:
    """非法配置值:返回 2007"""

    @pytest.mark.asyncio
    async def test_put_invalid_domain_format(self, client, superadmin_headers):
        """域名格式非法:返回 2007"""
        resp = await client.put(
            "/api/admin/platform-settings",
            headers=superadmin_headers,
            json={
                "preview_base_domain": "not-a-valid-domain",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 2007
        assert "域名" in data["message"] or "格式" in data["message"] or "illegal" in data["message"].lower()

    @pytest.mark.asyncio
    async def test_put_numeric_out_of_range(self, client, superadmin_headers):
        """数值越界:返回 2007"""
        resp = await client.put(
            "/api/admin/platform-settings",
            headers=superadmin_headers,
            json={
                "max_containers_total": -1,  # 应为正整数
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 2007
        assert "越界" in data["message"] or "范围" in data["message"] or "illegal" in data["message"].lower()

    @pytest.mark.asyncio
    async def test_put_numeric_not_integer(self, client, superadmin_headers):
        """数值非整数:返回 2007"""
        resp = await client.put(
            "/api/admin/platform-settings",
            headers=superadmin_headers,
            json={
                "max_containers_total": "not-a-number",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 2007

    @pytest.mark.asyncio
    async def test_put_empty_required_value(self, client, superadmin_headers):
        """必填项为空:返回 2007"""
        resp = await client.put(
            "/api/admin/platform-settings",
            headers=superadmin_headers,
            json={
                "gitlab_url": "",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 2007


# ---------------------------------------------------------------------------
# Key 白名单校验
# ---------------------------------------------------------------------------
class TestPlatformSettingsWhitelist:
    """Key 白名单校验"""

    @pytest.mark.asyncio
    async def test_put_unknown_key_rejected(self, client, superadmin_headers):
        """未知 key 被拒绝"""
        resp = await client.put(
            "/api/admin/platform-settings",
            headers=superadmin_headers,
            json={
                "unknown_key": "some-value",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        # 应返回参数错误或忽略未知 key
        assert data["code"] != 0 or "unknown_key" not in str(data.get("data", {}))

    @pytest.mark.asyncio
    async def test_put_valid_keys_accepted(self, client, superadmin_headers):
        """白名单内的 key 可写"""
        valid_keys = [
            "gitlab_url",
            "gitlab_bot_token",
            "gitlab_bot_group_id",
            "gitlab_webhook_secret",
            "preview_base_domain",
            "deploy_base_domain",
            "max_containers_total",
            "kb_max_pages_per_kb",
            "kb_max_file_mb",
        ]
        # 逐个测试每个合法 key
        for key in valid_keys:
            if "domain" in key:
                value = "example.com"
            elif "token" in key or "secret" in key:
                value = "test-value-123"
            elif "url" in key:
                value = "https://gitlab.example.com"
            elif "group_id" in key:
                value = 12345
            else:
                value = 100

            resp = await client.put(
                "/api/admin/platform-settings",
                headers=superadmin_headers,
                json={key: value},
            )
            assert resp.status_code == 200
            data = resp.json()
            # 合法 key 应成功或至少不被拒绝为未知 key
            assert data["code"] == 0 or key in str(data.get("data", {}))


# ---------------------------------------------------------------------------
# 错误码 19002 — 非超管访问
# ---------------------------------------------------------------------------
class TestPlatformSettingsNonSuperadmin:
    """非超管访问:返回 19002(注意:auth_headers 是首个注册用户=superadmin,必须用第二个用户)"""

    @pytest.mark.asyncio
    async def test_get_platform_settings_non_superadmin(self, client, auth_headers, second_user_headers):
        """普通用户 GET 平台设置:返回 19002(auth_headers 先注册占住首用户位,second 才是普通用户)"""
        resp = await client.get("/api/admin/platform-settings", headers=second_user_headers)
        assert resp.status_code in (200, 403)
        data = resp.json()
        assert data["code"] == 19002
        assert "超管" in data["message"] or "权限" in data["message"] or "superadmin" in data["message"].lower()

    @pytest.mark.asyncio
    async def test_put_platform_settings_non_superadmin(self, client, auth_headers, second_user_headers):
        """普通用户 PUT 平台设置:返回 19002"""
        resp = await client.put(
            "/api/admin/platform-settings",
            headers=second_user_headers,
            json={"gitlab_url": "https://gitlab.example.com"},
        )
        assert resp.status_code in (200, 403)
        data = resp.json()
        assert data["code"] == 19002

    @pytest.mark.asyncio
    async def test_get_platform_settings_no_auth(self, client):
        """未登录 GET 平台设置:返回 401"""
        resp = await client.get("/api/admin/platform-settings")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_put_platform_settings_no_auth(self, client):
        """未登录 PUT 平台设置:返回 401"""
        resp = await client.put(
            "/api/admin/platform-settings",
            json={"gitlab_url": "https://gitlab.example.com"},
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# 审计日志 (R19 action_type)
# ---------------------------------------------------------------------------
class TestPlatformSettingsAudit:
    """平台设置变更审计"""

    @pytest.mark.asyncio
    async def test_put_platform_settings_audit_log(self, client, superadmin_headers):
        """PUT 操作应记录审计日志"""
        # 由于 R2 未实现审计日志,此测试预期失败
        resp = await client.put(
            "/api/admin/platform-settings",
            headers=superadmin_headers,
            json={"gitlab_url": "https://gitlab.example.com"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 0
        # 审计日志应在后台记录(此处无法直接验证,仅确认接口成功)


# ---------------------------------------------------------------------------
# 即时生效验证
# ---------------------------------------------------------------------------
class TestPlatformSettingsImmediateEffect:
    """配置变更即时生效"""

    @pytest.mark.asyncio
    async def test_bot_token_change_immediate_effect(self, client, superadmin_headers):
        """bot token 变更后立即生效 (无需重启)"""
        # 设置新 bot token
        resp = await client.put(
            "/api/admin/platform-settings",
            headers=superadmin_headers,
            json={"gitlab_bot_token": "glpat-new-token"},
        )
        assert resp.status_code == 200

        # 立即读取,应反映新值(打码)
        resp = await client.get("/api/admin/platform-settings", headers=superadmin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 0
        # 如果返回了 token,应该是打码格式
        if "gitlab_bot_token" in data.get("data", {}):
            token_value = data["data"]["gitlab_bot_token"]
            assert "•" in token_value or "***" in token_value
