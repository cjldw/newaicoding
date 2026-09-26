"""
BUG-038 修复验证测试 — 平台设置单键解密失败打挂整页(逐键容错)
=====================================================
根因:.env PLATFORM_SECRET_KEY 轮换后,存量密文(旧密钥加密)解密抛
cryptography.exceptions.InvalidTag,_decode_stored 未捕获 → GET
/api/admin/platform-settings 500,设置页整体不可用。

覆盖场景(先红后绿):
1. 非当前密钥加密的密文插入 platform_settings → GET 断言 200(修复前必 500)
2. 失效键在响应中呈「未配置形态」(缺席),其余正常键不受影响
3. get_setting 对失效密文返回 None + warning 日志(不含明文/密文)
4. 解密失败消费方路径:test-connection → 2001(非 500)
5. resolve_config 平台回退 → 13005(非 500)
6. 失效键经 PUT 重录 → GET 打码回显(自愈闭环)
"""
import base64
import os

import pytest

from tests.test_projects_api import _insert_project


# ---------------------------------------------------------------------------
# 辅助:用「非当前密钥」插入加密平台设置行
# ---------------------------------------------------------------------------
async def _insert_stale_encrypted_setting(db_session, key: str, plaintext: str = "glpat-stale-old-token"):
    """
    用独立随机 AESGCM key 加密后直插 platform_settings(模拟密钥轮换后
    存量密文:格式合法但当前密钥必 InvalidTag)。返回密文 b64(供断言日志不泄露)。
    """
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    from app.models.project import PlatformSetting

    stale_key = AESGCM(os.urandom(32))
    nonce = os.urandom(12)
    encrypted = base64.b64encode(nonce + stale_key.encrypt(nonce, plaintext.encode("utf-8"), None)).decode("ascii")
    db_session.add(PlatformSetting(
        key=key,
        value={"__encrypted": encrypted},
        updated_by="test",
    ))
    await db_session.flush()
    return encrypted


# ---------------------------------------------------------------------------
# 场景 1/2:GET 平台设置(掩码回显)不再被单键失效打挂
# ---------------------------------------------------------------------------
class TestGetPlatformSettingsInvalidSecret:
    """GET /api/admin/platform-settings 对失效密文逐键容错(BUG-038)"""

    @pytest.mark.asyncio
    async def test_get_with_stale_secrets_returns_200(self, client, superadmin_headers, db_session):
        """三个敏感键全部失效 → GET 200(修复前:500 InvalidTag)"""
        await _insert_stale_encrypted_setting(db_session, "gitlab_bot_token")
        await _insert_stale_encrypted_setting(db_session, "gitlab_webhook_secret", "whsec-stale")
        await _insert_stale_encrypted_setting(db_session, "llm_api_key", "sk-stale")

        resp = await client.get("/api/admin/platform-settings", headers=superadmin_headers)
        assert resp.status_code == 200
        assert resp.json()["code"] == 0

    @pytest.mark.asyncio
    async def test_stale_key_absent_and_healthy_keys_normal(self, client, superadmin_headers, db_session):
        """失效键呈未配置形态(缺席);同时写入的正常键不受影响"""
        await _insert_stale_encrypted_setting(db_session, "gitlab_bot_token")
        # 正常键(当前密钥经 API 写入)
        resp = await client.put(
            "/api/admin/platform-settings",
            headers=superadmin_headers,
            json={"gitlab_url": "https://gitlab.example.com", "gitlab_bot_group_id": 1},
        )
        assert resp.json()["code"] == 0

        resp = await client.get("/api/admin/platform-settings", headers=superadmin_headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        # 失效键缺席(与"从未配置"同构)
        assert "gitlab_bot_token" not in data
        # 正常键不受影响
        assert data["gitlab_url"] == "https://gitlab.example.com"
        assert data["gitlab_bot_group_id"] == 1


# ---------------------------------------------------------------------------
# 场景 3:get_setting service 层折叠为 None + warning 日志
# ---------------------------------------------------------------------------
class TestGetSettingInvalidSecret:
    """get_setting 对失效密文返回 None(既有未配置语义)"""

    @pytest.mark.asyncio
    async def test_get_setting_stale_secret_returns_none(self, db_session):
        """service 层单测:失效密文 → None(修复前:抛 InvalidTag)"""
        from app.services.platform_settings_service import get_setting

        await _insert_stale_encrypted_setting(db_session, "gitlab_bot_token")
        assert await get_setting(db_session, "gitlab_bot_token") is None

    @pytest.mark.asyncio
    async def test_get_setting_corrupt_ciphertext_returns_none(self, db_session):
        """密文损坏(非法 base64)同样折叠为 None,不抛异常"""
        from app.models.project import PlatformSetting
        from app.services.platform_settings_service import get_setting

        db_session.add(PlatformSetting(
            key="gitlab_webhook_secret",
            value={"__encrypted": "!!not-valid-base64!!"},
            updated_by="test",
        ))
        await db_session.flush()
        assert await get_setting(db_session, "gitlab_webhook_secret") is None

    @pytest.mark.asyncio
    async def test_get_setting_stale_secret_warns_without_leaking(self, db_session, caplog):
        """warning 日志含键名与「密文失效需重置」,不落明文/密文"""
        import logging

        from app.services.platform_settings_service import get_setting

        plaintext = "glpat-super-secret-plaintext"
        encrypted_b64 = await _insert_stale_encrypted_setting(
            db_session, "gitlab_bot_token", plaintext=plaintext
        )

        with caplog.at_level(logging.WARNING):
            assert await get_setting(db_session, "gitlab_bot_token") is None

        # 只考察本服务的日志(SQLAlchemy echo 的 SQL 绑定参数与本修复无关)
        svc_records = [
            r for r in caplog.records
            if r.name == "app.services.platform_settings_service"
        ]
        assert any("gitlab_bot_token" in r.getMessage() for r in svc_records)
        assert any("失效" in r.getMessage() or "重置" in r.getMessage() for r in svc_records)
        # 明文/密文均不得落本服务日志
        assert all(plaintext not in r.getMessage() for r in svc_records)
        assert all(encrypted_b64 not in r.getMessage() for r in svc_records)


# ---------------------------------------------------------------------------
# 场景 4/5:解密失败消费方走既有「未配置」业务码,不 500
# ---------------------------------------------------------------------------
class TestConsumersCleanBizCode:
    """失效密文的消费方路径干净降级(2001 / 13005)"""

    @pytest.mark.asyncio
    async def test_connection_stale_token_returns_2001(self, client, superadmin_headers, db_session):
        """gitlab_url 正常 + bot token 失效 → test-connection 2001(修复前:500)"""
        from app.models.project import PlatformSetting

        await _insert_stale_encrypted_setting(db_session, "gitlab_bot_token")
        db_session.add(PlatformSetting(key="gitlab_url", value="https://gitlab.example.com", updated_by="test"))
        await db_session.flush()

        resp = await client.post(
            "/api/admin/platform-settings/test-connection", headers=superadmin_headers
        )
        assert resp.status_code == 200
        assert resp.json()["code"] == 2001

    @pytest.mark.asyncio
    async def test_resolve_config_stale_llm_key_returns_13005(self, db_session, registered_user):
        """llm_base_url/llm_models/llm_default_model 正常 + llm_api_key 失效 → 13005(修复前:InvalidTag)"""
        from app.core.response import BizError
        from app.services import llm_service

        from tests.test_r23_platform_llm_config import _insert_platform_setting

        project = await _insert_project(db_session, registered_user["user_id"])
        await _insert_platform_setting(db_session, "llm_base_url", "https://platform-llm.example.com/v1")
        await _insert_stale_encrypted_setting(db_session, "llm_api_key", "sk-stale")
        await _insert_platform_setting(db_session, "llm_models", ["platform-model"])
        await _insert_platform_setting(db_session, "llm_default_model", "platform-model")

        with pytest.raises(BizError) as exc_info:
            await llm_service.resolve_config(db_session, project.project_id)
        assert exc_info.value.code == 13005

    @pytest.mark.asyncio
    async def test_stale_llm_key_resolvable_endpoint_none_state(self, client, auth_headers, db_session, registered_user):
        """resolvable 端点:llm_api_key 失效 → effective_source=none(非 500)"""
        from tests.test_r23_platform_llm_config import _insert_platform_setting

        project = await _insert_project(db_session, registered_user["user_id"])
        await _insert_platform_setting(db_session, "llm_base_url", "https://platform-llm.example.com/v1")
        await _insert_stale_encrypted_setting(db_session, "llm_api_key", "sk-stale")
        await _insert_platform_setting(db_session, "llm_models", ["platform-model"])
        await _insert_platform_setting(db_session, "llm_default_model", "platform-model")

        resp = await client.get(
            f"/api/projects/{project.project_id}/model-configs/resolvable",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["effective_source"] == "none"


# ---------------------------------------------------------------------------
# 场景 6:失效键经 PUT 重录即自愈
# ---------------------------------------------------------------------------
class TestStaleKeySelfHeal:
    """失效键重录(当前密钥重新加密)→ GET 恢复打码回显"""

    @pytest.mark.asyncio
    async def test_stale_key_re_record_via_put_self_heals(self, client, superadmin_headers, db_session):
        await _insert_stale_encrypted_setting(db_session, "gitlab_bot_token")

        # 重录前:GET 无该键(未配置形态)
        resp = await client.get("/api/admin/platform-settings", headers=superadmin_headers)
        assert resp.status_code == 200
        assert "gitlab_bot_token" not in resp.json()["data"]

        # PUT 重录(当前密钥加密落盘)
        resp = await client.put(
            "/api/admin/platform-settings",
            headers=superadmin_headers,
            json={"gitlab_bot_token": "glpat-new-recorded-token"},
        )
        assert resp.status_code == 200
        assert resp.json()["code"] == 0

        # GET 恢复打码回显,不回明文
        resp = await client.get("/api/admin/platform-settings", headers=superadmin_headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "gitlab_bot_token" in data
        assert "•" in data["gitlab_bot_token"] or "***" in data["gitlab_bot_token"]
        assert "glpat-new-recorded-token" not in data["gitlab_bot_token"]


# ---------------------------------------------------------------------------
# 防误伤:普通(非加密)行与库内其余行不受容错改动影响
# ---------------------------------------------------------------------------
class TestDecodeStoredUntouchedPaths:
    """_decode_stored 非 sensitive 路径行为不变"""

    @pytest.mark.asyncio
    async def test_normal_rows_unaffected(self, client, superadmin_headers, db_session):
        """普通键原样回读;未配置键缺席(既有语义)"""
        from app.services.platform_settings_service import get_setting

        from tests.test_r23_platform_llm_config import _insert_platform_setting

        await _insert_platform_setting(db_session, "gitlab_url", "https://gitlab.example.com")
        assert await get_setting(db_session, "gitlab_url") == "https://gitlab.example.com"
        assert await get_setting(db_session, "deploy_base_domain") is None

    @pytest.mark.asyncio
    async def test_healthy_secret_still_masked(self, client, superadmin_headers):
        """健康密钥加密的敏感键仍正常打码(容错不改变正常路径)"""
        resp = await client.put(
            "/api/admin/platform-settings",
            headers=superadmin_headers,
            json={"gitlab_webhook_secret": "whsec-healthy-value"},
        )
        assert resp.json()["code"] == 0

        resp = await client.get("/api/admin/platform-settings", headers=superadmin_headers)
        data = resp.json()["data"]
        assert "gitlab_webhook_secret" in data
        assert "•" in data["gitlab_webhook_secret"]
