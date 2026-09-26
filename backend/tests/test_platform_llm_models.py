"""
R1 平台级模型多配置(llm_models / llm_default_model)— Red phase(失败测试)
=============================================================================
覆盖 DEVPLAN/R1.md 完成判据 1-4(后端部分)+ 服务端行为规格:

① SETTING_KEYS 新键校验:llm_models(strlist:去重→13009、>10 项→13008、
   每项 1-64 字符)、llm_default_model(必须 ∈ llm_models → 2007)
② PUT 四键齐备口径:缺任一键 → 2007;四键合法 → updated 含四键
③ 保存仅对 llm_default_model 做连通测试(mock llm_service.test_connectivity):
   失败 → 2008 且整批不落库;成功 → 只测 default 一次
④ GET 兼容映射:库中仅旧 llm_model 值 → 响应含 llm_models=[旧值](旧键保留)
⑤ _resolve_platform_config 兼容读:
   - 仅旧键 → model=旧值(存量行为不变)
   - 新键齐全 → model=llm_default_model
   - llm_models=[] 且无旧键 → 13005

标注【守卫】的用例锁定既有兼容行为,Red 阶段即通过,实现时不得回退;
其余用例预期失败(新键/新校验未实现:当前 PUT 走三键齐备口径,
llm_models/llm_default_model 不在白名单 → 2007「非法配置键」)。
"""
import pytest
from sqlalchemy import select

from app.core.response import BizError, ErrCode
from app.models.project import PlatformSetting
from app.services import llm_service

BASE_URL = "https://llm.example.com/v1"
API_KEY = "sk-test-key-1234567890"


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------
def _llm4_payload(models=None, default=None, **override):
    """四键 PUT payload(llm_models/llm_default_model 为 R1 新键)"""
    if models is None:
        models = ["gpt-4o", "claude-sonnet-5"]
    payload = {
        "llm_base_url": BASE_URL,
        "llm_api_key": API_KEY,
        "llm_models": models,
        "llm_default_model": default if default is not None else models[0],
    }
    payload.update(override)
    return payload


class _ConnectivitySpy:
    """llm_service.test_connectivity 替身:记录调用参数,可注入失败"""

    def __init__(self, exc=None):
        self.calls = []
        self._exc = exc

    async def __call__(self, base_url, api_key, model):
        self.calls.append({"base_url": base_url, "api_key": api_key, "model": model})
        if self._exc is not None:
            raise self._exc
        return {"success": True, "latency_ms": 12}


@pytest.fixture
def conn_spy(monkeypatch):
    """安装 test_connectivity 替身(mock,不发真实网络请求),返回 spy"""

    def _install(exc=None):
        spy = _ConnectivitySpy(exc)
        monkeypatch.setattr(llm_service, "test_connectivity", spy)
        return spy

    return _install


async def _insert_setting(db_session, key: str, value):
    """直插平台设置行(绕过 API;模拟存量/手工数据)"""
    from app.services.platform_settings_service import _encode_stored

    db_session.add(PlatformSetting(key=key, value=_encode_stored(key, value), updated_by="test"))
    await db_session.flush()


async def _get_setting_row(db_session, key: str):
    result = await db_session.execute(select(PlatformSetting).where(PlatformSetting.key == key))
    return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# ① SETTING_KEYS 新键 llm_models(strlist)/ llm_default_model 校验
# ---------------------------------------------------------------------------
class TestLlmModelsValidation:
    """PUT /api/admin/platform-settings — llm_models strlist 校验(完成判据 1)"""

    @pytest.mark.asyncio
    async def test_put_duplicate_models_rejected_13009(self, client, superadmin_headers, conn_spy):
        """模型名重复 → 13009(服务端去重校验兜底;前端「该模型已存在」)"""
        conn_spy()
        resp = await client.put(
            "/api/admin/platform-settings",
            headers=superadmin_headers,
            json=_llm4_payload(models=["gpt-4o", "gpt-4o"], default="gpt-4o"),
        )
        data = resp.json()
        assert data["code"] == 13009, data

    @pytest.mark.asyncio
    async def test_put_models_over_limit_rejected_13008(self, client, superadmin_headers, conn_spy):
        """llm_models 第 11 项 → 13008(上限 10)"""
        conn_spy()
        models = [f"model-{i:02d}" for i in range(11)]
        resp = await client.put(
            "/api/admin/platform-settings",
            headers=superadmin_headers,
            json=_llm4_payload(models=models, default="model-00"),
        )
        data = resp.json()
        assert data["code"] == 13008, data

    @pytest.mark.asyncio
    async def test_put_model_name_64_chars_accepted(self, client, superadmin_headers, conn_spy):
        """模型名 64 字符边界合法(每项 1-64 字符)→ 保存成功"""
        conn_spy()
        name_64 = "a" * 64
        resp = await client.put(
            "/api/admin/platform-settings",
            headers=superadmin_headers,
            json=_llm4_payload(models=[name_64], default=name_64),
        )
        data = resp.json()
        assert data["code"] == 0, data
        assert "llm_models" in data["data"]["updated"]

    @pytest.mark.asyncio
    async def test_put_model_name_over_64_chars_rejected(self, client, superadmin_headers,
                                                         db_session, conn_spy):
        """【守卫语义】模型名 65 字符 → 校验拒绝(2007),且不落库"""
        conn_spy()
        resp = await client.put(
            "/api/admin/platform-settings",
            headers=superadmin_headers,
            json=_llm4_payload(models=["a" * 65], default="a" * 65),
        )
        data = resp.json()
        assert data["code"] == 2007, data
        assert await _get_setting_row(db_session, "llm_models") is None

    @pytest.mark.asyncio
    async def test_put_model_name_empty_rejected(self, client, superadmin_headers, conn_spy):
        """【守卫语义】模型名空串 → 拒绝(每项非空)"""
        conn_spy()
        resp = await client.put(
            "/api/admin/platform-settings",
            headers=superadmin_headers,
            json=_llm4_payload(models=[""], default=""),
        )
        assert resp.json()["code"] == 2007

    @pytest.mark.asyncio
    async def test_put_default_not_in_models_rejected(self, client, superadmin_headers, conn_spy):
        """【守卫语义】llm_default_model 不在 llm_models 内 → 拒绝(2007)"""
        conn_spy()
        resp = await client.put(
            "/api/admin/platform-settings",
            headers=superadmin_headers,
            json=_llm4_payload(models=["gpt-4o"], default="claude-sonnet-5"),
        )
        assert resp.json()["code"] == 2007


# ---------------------------------------------------------------------------
# ② PUT 四键齐备口径(替换 R23 三键齐备)
# ---------------------------------------------------------------------------
class TestPutFourKeysCompleteness:
    """payload 含任一 llm 键 → 四键必须齐备,缺一整批拒(完成判据 2 前半)"""

    @pytest.mark.asyncio
    async def test_put_missing_any_key_rejected_2007(self, client, superadmin_headers):
        """缺任一键(base_url/api_key/models/default_model)→ 2007"""
        four = ["llm_base_url", "llm_api_key", "llm_models", "llm_default_model"]
        for missing in four:
            payload = {k: v for k, v in _llm4_payload().items() if k != missing}
            resp = await client.put(
                "/api/admin/platform-settings",
                headers=superadmin_headers,
                json=payload,
            )
            data = resp.json()
            assert data["code"] == 2007, f"缺 {missing} 应 2007,实际 {data}"

    @pytest.mark.asyncio
    async def test_put_all_four_keys_success(self, client, superadmin_headers, conn_spy):
        """四键合法 → 200,updated 含四键(完成判据 2 后半)"""
        conn_spy()
        resp = await client.put(
            "/api/admin/platform-settings",
            headers=superadmin_headers,
            json=_llm4_payload(),
        )
        data = resp.json()
        assert data["code"] == 0, data
        updated = set(data["data"]["updated"])
        assert {"llm_base_url", "llm_api_key", "llm_models", "llm_default_model"} <= updated


# ---------------------------------------------------------------------------
# ③ 保存仅对 llm_default_model 做连通测试;失败整批拒绝
# ---------------------------------------------------------------------------
class TestConnectivityOnSave:
    """PUT llm 分支连通测试(mock llm_service.test_connectivity;完成判据 2)"""

    @pytest.mark.asyncio
    async def test_put_connectivity_failed_rejects_batch(self, client, superadmin_headers,
                                                         db_session, conn_spy):
        """default 连不通 → 2008,且四键整批不落库"""
        conn_spy(exc=BizError(ErrCode.LLM_CONNECT_FAILED, "连接失败,请检查 Base URL 和 API Key"))
        resp = await client.put(
            "/api/admin/platform-settings",
            headers=superadmin_headers,
            json=_llm4_payload(),
        )
        data = resp.json()
        assert data["code"] == 2008, data

        # 整批拒绝:四键任何一行都不落库
        for key in ("llm_base_url", "llm_api_key", "llm_models", "llm_default_model"):
            assert await _get_setting_row(db_session, key) is None, key

    @pytest.mark.asyncio
    async def test_connectivity_tested_only_for_default_model(self, client, superadmin_headers,
                                                              conn_spy):
        """仅对 llm_default_model 测一次;测试对象取 payload 的 default"""
        spy = conn_spy()
        resp = await client.put(
            "/api/admin/platform-settings",
            headers=superadmin_headers,
            json=_llm4_payload(models=["gpt-4o", "claude-sonnet-5"], default="claude-sonnet-5"),
        )
        data = resp.json()
        assert data["code"] == 0, data
        assert len(spy.calls) == 1, f"应仅测 default 一次,实际 {spy.calls}"
        assert spy.calls[0]["base_url"] == BASE_URL
        assert spy.calls[0]["api_key"] == API_KEY
        assert spy.calls[0]["model"] == "claude-sonnet-5"


# ---------------------------------------------------------------------------
# ④ GET 兼容映射(存量单值 → llm_models)
# ---------------------------------------------------------------------------
class TestGetCompatMapping:
    """GET /api/admin/platform-settings — llm_model 旧值映射(完成判据 3)"""

    @pytest.mark.asyncio
    async def test_get_maps_legacy_llm_model_to_models(self, client, superadmin_headers, db_session):
        """库中仅旧 llm_model 值 → GET 返回 llm_models=[旧值],旧键原样保留"""
        await _insert_setting(db_session, "llm_model", "legacy-model")

        resp = await client.get("/api/admin/platform-settings", headers=superadmin_headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["llm_models"] == ["legacy-model"], data
        # 原 llm_model 键原样保留
        assert data["llm_model"] == "legacy-model"


# ---------------------------------------------------------------------------
# ⑤ _resolve_platform_config 兼容读
# ---------------------------------------------------------------------------
class TestResolvePlatformConfigCompat:
    """llm_service._resolve_platform_config 新旧键兼容(完成判据 4)"""

    @pytest.mark.asyncio
    async def test_resolve_legacy_only_keys_model_fallback(self, db_session):
        """【守卫】仅旧键(llm_model)→ model=旧值,存量行为不变"""
        await _insert_setting(db_session, "llm_base_url", BASE_URL)
        await _insert_setting(db_session, "llm_api_key", API_KEY)
        await _insert_setting(db_session, "llm_model", "legacy-model")

        result = await llm_service._resolve_platform_config(db_session)
        assert result["source"] == "platform"
        assert result["model"] == "legacy-model"

    @pytest.mark.asyncio
    async def test_resolve_new_keys_use_default_model(self, db_session):
        """新键齐全 → model=llm_default_model"""
        await _insert_setting(db_session, "llm_base_url", BASE_URL)
        await _insert_setting(db_session, "llm_api_key", API_KEY)
        await _insert_setting(db_session, "llm_models", ["gpt-4o", "claude-sonnet-5"])
        await _insert_setting(db_session, "llm_default_model", "claude-sonnet-5")

        result = await llm_service._resolve_platform_config(db_session)
        assert result["source"] == "platform"
        assert result["model"] == "claude-sonnet-5"

    @pytest.mark.asyncio
    async def test_resolve_empty_models_no_legacy_13005(self, db_session):
        """【守卫】llm_models=[] 且无旧键 → 按未配置 13005"""
        await _insert_setting(db_session, "llm_base_url", BASE_URL)
        await _insert_setting(db_session, "llm_api_key", API_KEY)
        await _insert_setting(db_session, "llm_models", [])

        from app.core.response import BizError

        with pytest.raises(BizError) as exc_info:
            await llm_service._resolve_platform_config(db_session)
        assert exc_info.value.code == 13005
