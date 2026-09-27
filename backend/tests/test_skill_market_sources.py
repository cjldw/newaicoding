"""
R1(skills 市场安装)— 市场源配置 — QA TDD Red phase
====================================================
依据 docs/20260926_skills市场安装/DEVPLAN/R1.md(接口契约 + 权限矩阵)。

覆盖:
1. 未配置时 GET /api/skills/market/sources 返回默认两源种子
   (ModelScope / skills.sh,name/type/base 齐全)
2. 超管 PUT /api/admin/platform-settings 写 skill_market_sources 合法 JSON 数组
   → 保存成功;再读 sources 返回新值
3. 非法(base 非 https / 缺 type / type 非法值 / 缺 base / 非数组)→ 400 校验拒绝
4. 普通登录用户 GET sources 200;PUT /api/admin/platform-settings → 403(19002)

服务层契约(同文件 DEVPLAN/R1.md):
- SETTING_KEYS 注册 skill_market_sources:("json", None)
- validate_setting_value 加 json 数组分支(逐项 name/type/base,base 必须 https 开头)
- get_setting 首次读取为空 → 返回默认两源种子
  (ModelScope base=https://modelscope.cn;skills.sh base=https://skills.sh)
"""
import pytest
import pytest_asyncio
from sqlalchemy import delete

from app.models.project import PlatformSetting
from app.services.platform_settings_service import (
    SETTING_KEYS,
    get_setting,
    validate_setting_value,
)
from app.core.response import ErrCode

SOURCES_URL = "/api/skills/market/sources"
SETTINGS_URL = "/api/admin/platform-settings"

# PRD 定义的合法 type 枚举:modelscope | skillssh
DEFAULT_SEED = [
    {"name": "ModelScope", "type": "modelscope", "base": "https://modelscope.cn"},
    {"name": "skills.sh", "type": "skillssh", "base": "https://skills.sh"},
]

VALID_CUSTOM = [
    {"name": "ModelScope镜像", "type": "modelscope", "base": "https://mirror.example.com"},
    {"name": "skills.sh", "type": "skillssh", "base": "https://skills.sh"},
]


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture
async def clean_platform_settings(db_session):
    """确保「未配置」前提:清空 platform_settings(隔离其他用例/历史残留写入)"""
    await db_session.execute(delete(PlatformSetting))
    await db_session.commit()
    yield db_session


def _get_sources(body) -> list:
    """读取 sources 端点的 data(契约:源数组)"""
    return body["data"]


# ---------------------------------------------------------------------------
# 服务层契约:SETTING_KEYS / validate_setting_value / get_setting 默认种子
# ---------------------------------------------------------------------------
class TestServiceContract:
    """platform_settings_service 对 R1 的服务层契约"""

    def test_setting_key_registered_as_json(self):
        """SETTING_KEYS 注册 skill_market_sources,类型 json"""
        assert "skill_market_sources" in SETTING_KEYS
        assert SETTING_KEYS["skill_market_sources"][0] == "json"

    def test_validate_accepts_valid_array(self):
        """合法 JSON 数组(逐项 name/type/base)通过校验"""
        out = validate_setting_value("skill_market_sources", VALID_CUSTOM)
        assert out == VALID_CUSTOM

    def test_validate_rejects_base_not_https(self):
        """base 非 https(http://)→ 2007,文案指明 base"""
        bad = [{"name": "X", "type": "skillssh", "base": "http://evil.com"}]
        with pytest.raises(Exception) as e:
            validate_setting_value("skill_market_sources", bad)
        assert getattr(e.value, "code", None) == ErrCode.PLATFORM_SETTING_INVALID
        assert "base" in e.value.message

    def test_validate_rejects_missing_type(self):
        """缺 type → 2007,文案指明 type"""
        bad = [{"name": "X", "base": "https://ok.example.com"}]
        with pytest.raises(Exception) as e:
            validate_setting_value("skill_market_sources", bad)
        assert getattr(e.value, "code", None) == ErrCode.PLATFORM_SETTING_INVALID
        assert "type" in e.value.message

    def test_validate_rejects_illegal_type(self):
        """type 非法值(枚举外)→ 2007,文案指明 type"""
        bad = [{"name": "X", "type": "github", "base": "https://ok.example.com"}]
        with pytest.raises(Exception) as e:
            validate_setting_value("skill_market_sources", bad)
        assert getattr(e.value, "code", None) == ErrCode.PLATFORM_SETTING_INVALID
        assert "type" in e.value.message

    def test_validate_rejects_duplicate_type(self):
        """同批两条 type=modelscope → 2007 拒重(同 strlist 口径,不静默合并;
        search 按 type 取源,重复即无提示死配置)"""
        bad = [
            {"name": "A", "type": "modelscope", "base": "https://a.example.com"},
            {"name": "B", "type": "modelscope", "base": "https://b.example.com"},
        ]
        with pytest.raises(Exception) as e:
            validate_setting_value("skill_market_sources", bad)
        assert getattr(e.value, "code", None) == ErrCode.PLATFORM_SETTING_INVALID
        assert "type" in e.value.message
        assert "重复" in e.value.message

    def test_validate_rejects_missing_name(self):
        """缺 name → 2007,文案指明 name"""
        bad = [{"type": "skillssh", "base": "https://ok.example.com"}]
        with pytest.raises(Exception) as e:
            validate_setting_value("skill_market_sources", bad)
        assert getattr(e.value, "code", None) == ErrCode.PLATFORM_SETTING_INVALID
        assert "name" in e.value.message

    def test_validate_rejects_missing_base(self):
        """缺 base → 2007,文案指明 base"""
        bad = [{"name": "X", "type": "skillssh"}]
        with pytest.raises(Exception) as e:
            validate_setting_value("skill_market_sources", bad)
        assert getattr(e.value, "code", None) == ErrCode.PLATFORM_SETTING_INVALID
        assert "base" in e.value.message

    def test_validate_rejects_non_array(self):
        """非数组(dict/字符串)→ 2007"""
        for bad in ({"name": "X"}, "https://x", [{"name": 1, "type": "skillssh", "base": "https://a.b"}]):
            with pytest.raises(Exception) as e:
                validate_setting_value("skill_market_sources", bad)
            assert getattr(e.value, "code", None) == ErrCode.PLATFORM_SETTING_INVALID

    @pytest.mark.asyncio
    async def test_get_setting_returns_default_seed_when_unset(self, clean_platform_settings):
        """首次读取为空 → 返回默认两源种子(ModelScope/skills.sh)"""
        seed = await get_setting(clean_platform_settings, "skill_market_sources")
        assert isinstance(seed, list) and len(seed) == 2
        names = {s["name"] for s in seed}
        assert names == {"ModelScope", "skills.sh"}
        assert {s["base"] for s in seed} == {"https://modelscope.cn", "https://skills.sh"}
        for s in seed:
            assert {"name", "type", "base"} <= set(s.keys())
        type_by_name = {s["name"]: s["type"] for s in seed}
        assert type_by_name["ModelScope"] == "modelscope"
        assert type_by_name["skills.sh"] == "skillssh"


# ---------------------------------------------------------------------------
# 1. 未配置时 GET sources → 默认两源种子(JWT 登录即可)
# ---------------------------------------------------------------------------
class TestDefaultSeedApi:
    @pytest.mark.asyncio
    async def test_unset_returns_two_default_sources(self, client, clean_platform_settings, auth_headers):
        """未配置时普通登录用户 GET sources 返回默认两源种子"""
        resp = await client.get(SOURCES_URL, headers=auth_headers)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["code"] == 0
        sources = _get_sources(body)
        assert isinstance(sources, list) and len(sources) == 2
        names = {s["name"] for s in sources}
        assert names == {"ModelScope", "skills.sh"}
        assert {s["base"] for s in sources} == {"https://modelscope.cn", "https://skills.sh"}
        for s in sources:
            assert {"name", "type", "base"} <= set(s.keys())
        type_by_name = {s["name"]: s["type"] for s in sources}
        assert type_by_name["ModelScope"] == "modelscope"
        assert type_by_name["skills.sh"] == "skillssh"

    @pytest.mark.asyncio
    async def test_sources_require_login(self, client, clean_platform_settings):
        """未登录(无 JWT)GET sources → 401"""
        resp = await client.get(SOURCES_URL)
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# 2. 超管 PUT 写合法 JSON 数组 → 保存成功;再读 sources 返回新值
# ---------------------------------------------------------------------------
class TestSuperadminWriteRoundTrip:
    @pytest.mark.asyncio
    async def test_put_valid_sources_then_read_back(self, client, clean_platform_settings, superadmin_headers):
        """超管保存合法数组 → code 0;GET sources 返回新值(替换种子)"""
        resp = await client.put(
            SETTINGS_URL, headers=superadmin_headers, json={"skill_market_sources": VALID_CUSTOM}
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["code"] == 0, body
        assert "skill_market_sources" in body["data"]["updated"]

        # sources 读接口回读新值
        got = await client.get(SOURCES_URL, headers=superadmin_headers)
        assert got.status_code == 200
        assert _get_sources(got.json()) == VALID_CUSTOM

        # admin 设置页 GET 也回显该键
        got_admin = await client.get(SETTINGS_URL, headers=superadmin_headers)
        assert got_admin.status_code == 200
        assert got_admin.json()["data"]["skill_market_sources"] == VALID_CUSTOM

    @pytest.mark.asyncio
    async def test_update_settings_roundtrip(self, db_session, clean_platform_settings):
        """服务层 update_settings → get_setting 全链路(归一化后原样回读)"""
        from app.services.platform_settings_service import update_settings

        updated = await update_settings(db_session, "u-qa", {"skill_market_sources": VALID_CUSTOM})
        assert "skill_market_sources" in updated
        await db_session.commit()
        assert await get_setting(db_session, "skill_market_sources") == VALID_CUSTOM


# ---------------------------------------------------------------------------
# 3. 非法输入 → 400 校验拒绝(整批拒绝,不部分写入)
# ---------------------------------------------------------------------------
class TestInvalidSourcesRejected:
    def _cases(self):
        return {
            "base_not_https": [{"name": "X", "type": "skillssh", "base": "http://evil.com"}],
            "base_not_url": [{"name": "X", "type": "skillssh", "base": "not-a-url"}],
            "missing_type": [{"name": "X", "base": "https://ok.example.com"}],
            "illegal_type": [{"name": "X", "type": "github", "base": "https://ok.example.com"}],
            "duplicate_type": [
                {"name": "A", "type": "modelscope", "base": "https://a.example.com"},
                {"name": "B", "type": "modelscope", "base": "https://b.example.com"},
            ],
            "missing_base": [{"name": "X", "type": "skillssh"}],
            "missing_name": [{"type": "skillssh", "base": "https://ok.example.com"}],
            "non_array": {"name": "X", "type": "skillssh", "base": "https://ok.example.com"},
        }

    @pytest.mark.asyncio
    async def test_invalid_values_rejected_400(self, client, clean_platform_settings, superadmin_headers):
        """每类非法输入 → HTTP 400 + code 2007"""
        for label, bad in self._cases().items():
            resp = await client.put(
                SETTINGS_URL, headers=superadmin_headers, json={"skill_market_sources": bad}
            )
            assert resp.status_code == 400, f"[{label}] {resp.status_code} {resp.text}"
            body = resp.json()
            assert body["code"] == ErrCode.PLATFORM_SETTING_INVALID, f"[{label}] {body}"

    @pytest.mark.asyncio
    async def test_rejected_write_does_not_persist(self, client, clean_platform_settings, superadmin_headers):
        """非法 base 整批拒绝后不落库:GET sources 仍为默认种子"""
        bad = [
            {"name": "好源", "type": "modelscope", "base": "https://good.example.com"},
            {"name": "坏源", "type": "skillssh", "base": "http://evil.com"},
        ]
        resp = await client.put(SETTINGS_URL, headers=superadmin_headers, json={"skill_market_sources": bad})
        assert resp.status_code == 400
        got = await client.get(SOURCES_URL, headers=superadmin_headers)
        sources = _get_sources(got.json())
        assert {s["base"] for s in sources} == {"https://modelscope.cn", "https://skills.sh"}


# ---------------------------------------------------------------------------
# 4. 权限矩阵:登录用户可读不可改;超管可读可改
# ---------------------------------------------------------------------------
class TestPermissionMatrix:
    @pytest.mark.asyncio
    async def test_normal_user_get_sources_ok(self, client, clean_platform_settings, auth_headers, second_user_headers):
        """普通登录用户 GET sources → 200 code 0(auth_headers 先注册占住首用户=超管位)"""
        resp = await client.get(SOURCES_URL, headers=second_user_headers)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["code"] == 0
        assert isinstance(_get_sources(body), list)

    @pytest.mark.asyncio
    async def test_normal_user_put_forbidden(self, client, clean_platform_settings, auth_headers, second_user_headers):
        """普通用户 PUT /api/admin/platform-settings → 403 code 19002"""
        resp = await client.put(
            SETTINGS_URL,
            headers=second_user_headers,
            json={"skill_market_sources": VALID_CUSTOM},
        )
        assert resp.status_code == 403, resp.text
        body = resp.json()
        assert body["code"] == ErrCode.NOT_SUPERADMIN

    @pytest.mark.asyncio
    async def test_normal_user_put_does_not_change_sources(
        self, client, clean_platform_settings, auth_headers, second_user_headers
    ):
        """普通用户写被拒后 sources 不变(仍默认种子)"""
        resp = await client.put(
            SETTINGS_URL,
            headers=second_user_headers,
            json={"skill_market_sources": VALID_CUSTOM},
        )
        assert resp.status_code == 403
        got = await client.get(SOURCES_URL, headers=auth_headers)
        sources = _get_sources(got.json())
        assert {s["base"] for s in sources} == {"https://modelscope.cn", "https://skills.sh"}
