"""
R8.F4(BUG-036)— 平台自定义变量 + LLM_URL 别名 — 单测
=====================================================
判据覆盖:
1. custom_env_vars 保存/回显(GET 原样,不打码)
2. envmap 校验:非法键名 2007 / 系统保留名 2007 / 值超长 2007 / 非字符串值 2007 / 空 dict 合法
3. 容器 env 注入:custom_env_vars 全量透传 + LLM_URL 别名 = LLM_BASE_URL + 系统键不被自定义覆盖
"""
import pytest
from unittest.mock import AsyncMock, patch

from app.services.platform_settings_service import (
    SETTING_KEYS,
    RESERVED_ENV_KEYS,
    validate_setting_value,
)
from app.core.response import BizError, ErrCode


# ---------------------------------------------------------------------------
# 判据 1/2:校验与保存
# ---------------------------------------------------------------------------
class TestCustomEnvValidation:
    """validate_setting_value('custom_env_vars', ...) 单元口径"""

    def test_key_registered(self):
        assert "custom_env_vars" in SETTING_KEYS
        assert SETTING_KEYS["custom_env_vars"][0] == "envmap"

    def test_valid_dict_passes(self):
        v = validate_setting_value("custom_env_vars", {"HTTP_PROXY": "http://1.2.3.4:8080", "MY_FLAG": "1"})
        assert v == {"HTTP_PROXY": "http://1.2.3.4:8080", "MY_FLAG": "1"}

    def test_empty_dict_allowed(self):
        assert validate_setting_value("custom_env_vars", {}) == {}

    def test_non_dict_rejected(self):
        with pytest.raises(BizError) as e:
            validate_setting_value("custom_env_vars", ["a"])
        assert e.value.code == ErrCode.PLATFORM_SETTING_INVALID

    def test_bad_key_name_rejected(self):
        for bad in ["1ABC", "HAS-DASH", "中文KEY", "A B"]:
            with pytest.raises(BizError) as e:
                validate_setting_value("custom_env_vars", {bad: "v"})
            assert e.value.code == ErrCode.PLATFORM_SETTING_INVALID
            # 文案含违规键名、不含值
            assert bad in e.value.message

    def test_reserved_key_rejected(self):
        assert "LLM_MODEL" in RESERVED_ENV_KEYS
        assert "LLM_URL" in RESERVED_ENV_KEYS
        with pytest.raises(BizError) as e:
            validate_setting_value("custom_env_vars", {"LLM_MODEL": "hack"})
        assert "系统保留" in e.value.message

    def test_non_string_value_rejected(self):
        with pytest.raises(BizError) as e:
            validate_setting_value("custom_env_vars", {"N": 123})
        assert e.value.code == ErrCode.PLATFORM_SETTING_INVALID

    def test_long_value_rejected(self):
        with pytest.raises(BizError) as e:
            validate_setting_value("custom_env_vars", {"BIG": "x" * 2049})
        assert "超长" in e.value.message

    def test_too_many_keys_rejected(self):
        big = {f"K{i}": "v" for i in range(51)}
        with pytest.raises(BizError) as e:
            validate_setting_value("custom_env_vars", big)
        assert "超限" in e.value.message


class TestCustomEnvApiRoundTrip:
    """PUT/GET 全链路:保存 → 回显原样(非敏感不打码)"""

    @pytest.mark.asyncio
    async def test_put_then_get_plain_value(self, client, superadmin_headers):
        resp = await client.put(
            "/api/admin/platform-settings",
            headers=superadmin_headers,
            json={"custom_env_vars": {"MY_TEST_VAR": "hello-123"}},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 0
        # updated 键列表(R23 决策①)
        assert "custom_env_vars" in (body["data"]["updated"] if isinstance(body["data"], dict) else body["data"])

        got = await client.get("/api/admin/platform-settings", headers=superadmin_headers)
        data = got.json()["data"]
        assert data["custom_env_vars"] == {"MY_TEST_VAR": "hello-123"}

    @pytest.mark.asyncio
    async def test_put_reserved_rejected_via_api(self, client, superadmin_headers):
        resp = await client.put(
            "/api/admin/platform-settings",
            headers=superadmin_headers,
            json={"custom_env_vars": {"TASK_ID": "x"}},
        )
        assert resp.json()["code"] == ErrCode.PLATFORM_SETTING_INVALID


# ---------------------------------------------------------------------------
# 判据 3:容器 env 注入(打磨任务 + start_task 两条链)
# ---------------------------------------------------------------------------
class _AnyUser:
    """task_service 两条链的 operator 仅做参数占位(实际不落用户字段)"""
    user_id = "u-test"
    role = "user"
    gitlab_username = "tester"
    nickname = "测试"


@pytest.mark.asyncio
async def test_polish_env_contains_llm_url_and_custom_vars(db_session):
    """create_polish_task 的 env:LLM_URL=LLM_BASE_URL 同值;自定义变量透传;系统键仍由系统产出"""
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, patch

    from tests.test_projects_api import _insert_project
    from app.services import task_service, llm_service
    from app.services.platform_settings_service import update_settings, get_setting

    project = await _insert_project(db_session, owner_id=_AnyUser.user_id)
    await update_settings(db_session, _AnyUser.user_id, {
        "custom_env_vars": {"MY_VAR": "my-value", "HTTP_PROXY": "http://p:3128"},
    })
    assert await get_setting(db_session, "custom_env_vars") == {"MY_VAR": "my-value", "HTTP_PROXY": "http://p:3128"}

    fake_req = SimpleNamespace(
        req_id="req-r8f4", req_branch="req-r8f4", title="t", description="d",
        created_by=_AnyUser.user_id, priority="medium", status="draft",
    )
    captured = {}

    async def fake_schedule(db, **kwargs):
        captured.update(kwargs)

    with patch("app.services.container_service.schedule_and_start", side_effect=fake_schedule), \
         patch.object(llm_service, "resolve_config", AsyncMock(return_value={
             "base_url": "http://llm.example.com/v1", "api_key": "sk-test-key-1234567890", "model": "m1",
         })), \
         patch("app.services.llm_service.container_base_url", side_effect=lambda u: u.replace("http://llm.example.com", "http://host.docker.internal")):
        await task_service.create_polish_task(db_session, project, fake_req, _AnyUser())

    env = captured["env"]
    assert env["LLM_URL"] == env["LLM_BASE_URL"]
    assert env["MY_VAR"] == "my-value"
    assert env["HTTP_PROXY"] == "http://p:3128"
    # 系统键仍由系统产出(铺底不反客为主)
    assert env["LLM_MODEL"] == "m1"
    assert env["REQ_ID"] == "req-r8f4"


@pytest.mark.asyncio
async def test_start_task_env_includes_custom_vars(db_session):
    """start_task 链同样注入自定义变量与 LLM_URL"""
    from unittest.mock import AsyncMock, patch

    from tests.test_projects_api import _insert_project
    from app.models.requirement import Requirement
    from app.models.task import Task
    from app.services import task_service, llm_service
    from app.services.platform_settings_service import update_settings

    project = await _insert_project(db_session, owner_id=_AnyUser.user_id)
    await update_settings(db_session, _AnyUser.user_id, {
        "custom_env_vars": {"START_VAR": "yes"},
    })

    requirement = Requirement(
        project_id=project.project_id, title="r", description="d",
        req_branch="req-x", status="approved", created_by=_AnyUser.user_id,
        priority="medium",
    )
    db_session.add(requirement)
    await db_session.flush()  # req_id 默认值在 flush 时生成,Task 需引用真实 req_id
    task = Task(
        project_id=project.project_id, req_id=requirement.req_id, type="dev",
        title="t", description="d", base_branch="main", work_branch="req-x", status="pending",
        created_by=_AnyUser.user_id,
    )
    db_session.add(task)
    await db_session.flush()

    captured = {}

    async def fake_schedule(db, **kwargs):
        captured.update(kwargs)

    with patch("app.services.container_service.schedule_and_start", side_effect=fake_schedule), \
         patch.object(llm_service, "resolve_config", AsyncMock(return_value={
             "base_url": "http://llm.example.com/v1", "api_key": "sk-test-key-1234567890", "model": "m1",
         })), \
         patch("app.services.llm_service.container_base_url", side_effect=lambda u: u):
        await task_service.start_task(db_session, task, project, requirement)

    env = captured["env"]
    assert env["START_VAR"] == "yes"
    assert env["LLM_URL"] == env["LLM_BASE_URL"]
