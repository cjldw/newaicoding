"""
R6 交付提醒(每日巡检)— TDD Red 测试
====================================================
覆盖(DEVPLAN/R6.md「完成判据」全部 6 条 + 行为规格固化项):

判据1 delivery_date=明天 → 「临近」通知 + last_run_date=今天 + 同日不重发
  → test_sweep_tomorrow_notifies_related_users(通知内容/收件人/链接/返回条数)
  → test_sweep_persists_last_run_date(last_run_date 落 platform_settings)
  → test_sweep_same_day_rerun_no_resend(同日连跑两次,第二次 0 发送)
  → test_sweep_restart_same_day_idempotent(重启同日:预置 last_run_date → 0 发送)
判据2 delivery_date=昨天 → 「已逾期」
  → test_sweep_yesterday_overdue_title
判据3 终态命中日期 → 不发(异常)
  → test_sweep_skips_terminal_status(done/archived 各一)
判据4 空名单 → 不发不报错(异常)
  → test_sweep_empty_list_noop([] 与存量 NULL 两形态)
判据5 mock platform_settings 异常 → 巡检跳过不崩(异常)
  → test_sweep_settings_error_skips_round
判据6 通知 type=req_delivery_reminder 落库(ENUM 改表生效)
  → test_sweep_notification_type_persisted_enum(真实 send_notification 落库验证)

行为规格固化(非判据但 R6.md 明确):
  → test_sweep_survives_removed_member(关联用户过滤仍为项目成员)
  → test_sweep_window_excludes_backfilled_date(补录=昨天且次日巡检 → 逾期第2天
    不属两时点 → 不发,存量补录边界固化用例)

约定契约(实现按此实现,测试按此断言):
- 新模块 app/services/delivery_reminder_service.py:
  run_delivery_reminder_sweep(db) -> int(返回发送条数);
  gmt8_today() 返回 UTC naive +8h 的 date,是巡检「今天」唯一来源
- 巡检窗口:delivery_date IN (today-1, today+1) AND status NOT IN (done, archived)
- 通知:send_notification(type="req_delivery_reminder", level="normal",
  标题含「交付临近(明天)」/「已逾期」,link=/requirements/{req_id});
  收件人=关联用户过滤仍为项目成员;单条失败 try/except 继续
- last_run_date:platform_settings key=req_delivery_reminder_last_date;
  防重入读写独立成函数(实现方最终命名 maybe_run_daily_sweep,直调口径同契约:
  读 last_run_date != 今天 → 跑 run_delivery_reminder_sweep 并写回;= 今天 → 跳过)

mock 口径(先例 test_requirement_review_notify.py:patch 定义模块属性;requirement_service
以 `from app.services import notification_service` 模块属性调用,同惯例假定新服务以
`platform_settings_service.get_setting(...)` 方式读写,patch 定义模块即可拦截):
- 日期:patch("app.services.delivery_reminder_service.gmt8_today", return_value=固定日)
- 发送:patch("app.services.notification_service.send_notification", new_callable=AsyncMock)
- settings 读:patch("app.services.platform_settings_service.get_setting")(仅异常用例)
- settings 写:不 mock,以 PlatformSetting 表行断言(对 update_settings/直 ORM 实现
  细节不敏感);同日防重入用例针对 maybe_run_daily_sweep 的 last_run_date 读写闭环

注意(Red 设计):若 delivery_reminder_service 模块不存在,经 delivery_svc fixture
惰性导入,每个用例独立报「未实现」失败(11 用例 = 11 红,不做整体 collection error)。
实际时间线:实现由 rd-dev 于本测试 Red 编写期间并行落盘(见
docs/20260926_需求关联用户通知/.scratch/R6/qa-red-tests.md 运行记录)。
"""
import uuid
from datetime import date, timedelta
from unittest.mock import AsyncMock, patch

import pytest
import sqlalchemy

from app.models.notification import Notification
from app.models.project import PlatformSetting
from tests.test_requirement_related_users import (
    _add_member,
    _create_requirement,
    _mk_user,
)
from tests.test_requirements_api import _setup_project

# 固定「今天」(避开当前真实日期,防与库内存量数据巧合)
FIXED_TODAY = date(2030, 6, 15)
TOMORROW = FIXED_TODAY + timedelta(days=1)
YESTERDAY = FIXED_TODAY - timedelta(days=1)
LAST_RUN_KEY = "req_delivery_reminder_last_date"

# ---------------------------------------------------------------------------
# 被测模块惰性导入(Red:模块未实现 → 每用例经 fixture 独立红)
# ---------------------------------------------------------------------------
try:
    from app.services import delivery_reminder_service as _delivery_svc
except ImportError as _e:  # pragma: no cover - Red 阶段必经
    _delivery_svc = None
    _SVC_IMPORT_ERROR = _e
else:
    _SVC_IMPORT_ERROR = None


@pytest.fixture
def delivery_svc():
    if _delivery_svc is None:
        pytest.fail(
            f"app/services/delivery_reminder_service.py 未实现(Red 预期): {_SVC_IMPORT_ERROR}"
        )
    return _delivery_svc


# ---------------------------------------------------------------------------
# 辅助(口径照抄 test_requirement_review_notify.py)
# ---------------------------------------------------------------------------
async def _get_req_orm(db_session, req_id: str):
    from app.models.requirement import Requirement

    return (await db_session.execute(
        sqlalchemy.select(Requirement).where(Requirement.req_id == req_id)
    )).scalars().first()


async def _mk_due_requirement(client, db_session, auth_headers, registered_user,
                              related, delivery_date, status="approved", project=None) -> dict:
    """建需求(带名单)+ ORM 置 delivery_date/status。

    related:关联用户凭据列表(成员行在此统一 _add_member 后再建需求——R1 名单
    存储按项目成员过滤;owner 补成员行,操作人跳重)。related 传 [] → 空名单;
    传 None → 不传字段(配合用例 7 ORM 置 NULL)。
    project 传 None → 新建项目(含 gitlab settings 种子,首次调用);一测多需求时
    复用同一项目传入,避免 _seed_gitlab_settings 二次直插撞 platform_settings 主键。
    """
    if project is None:
        project = await _setup_project(db_session, registered_user)
        _add_member(db_session, project.project_id, registered_user["user_id"], role="editor")
    for u in related or []:
        if u["user_id"] != registered_user["user_id"]:
            _add_member(db_session, project.project_id, u["user_id"], role="editor")
    await db_session.flush()

    payload = {"title": "交付提醒需求", "description": "d"}
    if related is not None:
        payload["related_user_ids"] = [u["user_id"] for u in related]
    body = await _create_requirement(client, auth_headers, project, payload)
    assert body["code"] == 0, body
    req = await _get_req_orm(db_session, body["data"]["req_id"])
    assert req is not None, body

    req.delivery_date = delivery_date
    req.status = status
    await db_session.flush()
    return {"project": project, "req": req}


async def _get_last_run_row(db_session):
    return (await db_session.execute(
        sqlalchemy.select(PlatformSetting).where(PlatformSetting.key == LAST_RUN_KEY)
    )).scalars().first()


def _kw(call) -> dict:
    return call.kwargs


# ---------------------------------------------------------------------------
# 判据1a delivery_date=明天 → 关联用户各收「交付临近(明天)」;返回发送条数
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_sweep_tomorrow_notifies_related_users(
    client, db_session, auth_headers, registered_user, delivery_svc,
):
    u1 = await _mk_user(client)
    u2 = await _mk_user(client)
    env = await _mk_due_requirement(
        client, db_session, auth_headers, registered_user, [u1, u2], TOMORROW,
    )
    req = env["req"]

    with patch("app.services.delivery_reminder_service.gmt8_today", return_value=FIXED_TODAY), \
         patch("app.services.notification_service.send_notification", new_callable=AsyncMock) as mock_send:
        sent = await delivery_svc.run_delivery_reminder_sweep(db_session)

    assert sent == 2, f"应返回发送条数 2,实际 {sent!r}"
    assert mock_send.await_count == 2, f"期望 2 次通知,实际 {mock_send.await_count}"
    recipients = set()
    for call in mock_send.await_args_list:
        kw = _kw(call)
        recipients.add(kw["recipient_id"])
        assert kw["type"] == "req_delivery_reminder", kw
        assert kw["level"] == "normal", kw
        assert "交付临近" in kw["title"], kw
        assert "明天" in kw["title"], kw
        assert kw["link"] == f"/requirements/{req.req_id}", kw
        assert isinstance(kw["content"], str) and kw["content"], kw
    assert recipients == {u1["user_id"], u2["user_id"]}, recipients


# ---------------------------------------------------------------------------
# 判据2 delivery_date=昨天 → 「已逾期」
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_sweep_yesterday_overdue_title(
    client, db_session, auth_headers, registered_user, delivery_svc,
):
    u1 = await _mk_user(client)
    env = await _mk_due_requirement(
        client, db_session, auth_headers, registered_user, [u1], YESTERDAY,
    )
    req = env["req"]

    with patch("app.services.delivery_reminder_service.gmt8_today", return_value=FIXED_TODAY), \
         patch("app.services.notification_service.send_notification", new_callable=AsyncMock) as mock_send:
        sent = await delivery_svc.run_delivery_reminder_sweep(db_session)

    assert sent == 1, f"应返回发送条数 1,实际 {sent!r}"
    assert mock_send.await_count == 1, f"期望 1 次通知,实际 {mock_send.await_count}"
    kw = _kw(mock_send.await_args_list[0])
    assert kw["recipient_id"] == u1["user_id"], kw
    assert kw["type"] == "req_delivery_reminder", kw
    assert kw["level"] == "normal", kw
    assert "已逾期" in kw["title"], kw
    assert kw["link"] == f"/requirements/{req.req_id}", kw


# ---------------------------------------------------------------------------
# 判据1b 巡检后 last_run_date=今天 落 platform_settings(防重入入口 maybe_run_daily_sweep)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_sweep_persists_last_run_date(
    client, db_session, auth_headers, registered_user, delivery_svc,
):
    u1 = await _mk_user(client)
    await _mk_due_requirement(client, db_session, auth_headers, registered_user, [u1], TOMORROW)

    with patch("app.services.delivery_reminder_service.gmt8_today", return_value=FIXED_TODAY), \
         patch("app.services.notification_service.send_notification", new_callable=AsyncMock):
        sent = await delivery_svc.maybe_run_daily_sweep(db_session)

    assert sent == 1, f"首轮应触发巡检发送 1 条,实际 {sent!r}"
    row = await _get_last_run_row(db_session)
    assert row is not None, f"platform_settings 应落 key={LAST_RUN_KEY}"
    assert FIXED_TODAY.isoformat() in str(row.value), \
        f"last_run_date 应为 {FIXED_TODAY.isoformat()},实际 {row.value!r}"


# ---------------------------------------------------------------------------
# 判据1c 同日再触发不重发(连跑两次:第二次读到首轮写的 last_run_date → 跳过)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_sweep_same_day_rerun_no_resend(
    client, db_session, auth_headers, registered_user, delivery_svc,
):
    u1 = await _mk_user(client)
    await _mk_due_requirement(client, db_session, auth_headers, registered_user, [u1], TOMORROW)

    with patch("app.services.delivery_reminder_service.gmt8_today", return_value=FIXED_TODAY), \
         patch("app.services.notification_service.send_notification", new_callable=AsyncMock) as mock_send:
        first = await delivery_svc.maybe_run_daily_sweep(db_session)
        second = await delivery_svc.maybe_run_daily_sweep(db_session)

    assert first == 1, f"首轮应发送 1 条,实际 {first!r}"
    assert not second, f"同日第二轮应防重入跳过(0/None),实际 {second!r}"
    assert mock_send.await_count == 1, \
        f"同日第二轮不得重发,期望累计 1 次调用,实际 {mock_send.await_count}"


# ---------------------------------------------------------------------------
# 判据1c(强化)重启同日不重跑:预置 last_run_date=今天 → 直接跳过零发送
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_sweep_restart_same_day_idempotent(
    client, db_session, auth_headers, registered_user, delivery_svc,
):
    u1 = await _mk_user(client)
    await _mk_due_requirement(client, db_session, auth_headers, registered_user, [u1], TOMORROW)
    db_session.add(PlatformSetting(
        key=LAST_RUN_KEY, value=FIXED_TODAY.isoformat(), updated_by="system",
    ))
    await db_session.flush()

    with patch("app.services.delivery_reminder_service.gmt8_today", return_value=FIXED_TODAY), \
         patch("app.services.notification_service.send_notification", new_callable=AsyncMock) as mock_send:
        sent = await delivery_svc.maybe_run_daily_sweep(db_session)

    assert not sent, f"last_run_date=今天 应直接跳过(0/None),实际 {sent!r}"
    assert mock_send.await_count == 0, f"重启同日不得重发,实际 {mock_send.await_count}"


# ---------------------------------------------------------------------------
# 判据3 终态(done/archived)命中日期 → 不发
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_sweep_skips_terminal_status(
    client, db_session, auth_headers, registered_user, delivery_svc,
):
    u1 = await _mk_user(client)
    u2 = await _mk_user(client)
    env1 = await _mk_due_requirement(
        client, db_session, auth_headers, registered_user, [u1], TOMORROW, status="done",
    )
    await _mk_due_requirement(
        client, db_session, auth_headers, registered_user, [u2], YESTERDAY,
        status="archived", project=env1["project"],
    )

    with patch("app.services.delivery_reminder_service.gmt8_today", return_value=FIXED_TODAY), \
         patch("app.services.notification_service.send_notification", new_callable=AsyncMock) as mock_send:
        sent = await delivery_svc.run_delivery_reminder_sweep(db_session)

    assert sent == 0, f"终态命中日期应全跳过返回 0,实际 {sent!r}"
    assert mock_send.await_count == 0, f"终态需求不得发通知,实际 {mock_send.await_count}"


# ---------------------------------------------------------------------------
# 判据4 空名单 → 不发不报错([] 与存量 NULL 两形态)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_sweep_empty_list_noop(
    client, db_session, auth_headers, registered_user, delivery_svc,
):
    # 形态一:显式空名单
    env1 = await _mk_due_requirement(
        client, db_session, auth_headers, registered_user, [], TOMORROW,
    )
    # 形态二:存量 NULL(ORM 置 NULL 模拟)
    env = await _mk_due_requirement(
        client, db_session, auth_headers, registered_user, None, YESTERDAY,
        project=env1["project"],
    )
    env["req"].related_user_ids = None
    await db_session.flush()

    with patch("app.services.delivery_reminder_service.gmt8_today", return_value=FIXED_TODAY), \
         patch("app.services.notification_service.send_notification", new_callable=AsyncMock) as mock_send:
        sent = await delivery_svc.run_delivery_reminder_sweep(db_session)

    assert sent == 0, f"空名单应零发送返回 0,实际 {sent!r}"
    assert mock_send.await_count == 0, f"空名单应零调用,实际 {mock_send.await_count}"


# ---------------------------------------------------------------------------
# 行为规格 关联用户过滤仍为项目成员(已移出 → 跳过,其余正常)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_sweep_survives_removed_member(
    client, db_session, auth_headers, registered_user, delivery_svc,
):
    from app.models.project_member import ProjectMember

    u1 = await _mk_user(client)
    u2 = await _mk_user(client)
    env = await _mk_due_requirement(
        client, db_session, auth_headers, registered_user, [u1, u2], TOMORROW,
    )
    project = env["project"]

    u2_member = (await db_session.execute(
        sqlalchemy.select(ProjectMember).where(
            ProjectMember.project_id == project.project_id,
            ProjectMember.user_id == u2["user_id"],
        )
    )).scalars().first()
    assert u2_member is not None
    await db_session.delete(u2_member)
    await db_session.flush()

    with patch("app.services.delivery_reminder_service.gmt8_today", return_value=FIXED_TODAY), \
         patch("app.services.notification_service.send_notification", new_callable=AsyncMock) as mock_send:
        sent = await delivery_svc.run_delivery_reminder_sweep(db_session)

    assert sent == 1, f"已移出成员应被过滤,期望 1 条,实际 {sent!r}"
    assert mock_send.await_count == 1, f"期望 1 次通知,实际 {mock_send.await_count}"
    kw = _kw(mock_send.await_args_list[0])
    assert kw["recipient_id"] == u1["user_id"], kw
    assert kw["recipient_id"] != u2["user_id"], kw


# ---------------------------------------------------------------------------
# 判据5 mock platform_settings 异常 → 巡检跳过本轮不崩(异常;防重入入口直调)
# 契约允许「抛异常(调度层捕获)」或「吞掉返回」两种口径,断言共同不变量:
# 本轮零发送、不产生通知;若选择返回口径则不得抛且返回 0/None。
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_sweep_settings_error_skips_round(
    client, db_session, auth_headers, registered_user, delivery_svc,
):
    u1 = await _mk_user(client)
    await _mk_due_requirement(client, db_session, auth_headers, registered_user, [u1], TOMORROW)

    with patch("app.services.delivery_reminder_service.gmt8_today", return_value=FIXED_TODAY), \
         patch("app.services.notification_service.send_notification", new_callable=AsyncMock) as mock_send, \
         patch("app.services.platform_settings_service.get_setting", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = RuntimeError("settings boom")
        raised = None
        try:
            sent = await delivery_svc.maybe_run_daily_sweep(db_session)
        except Exception as e:  # 抛异常口径:调度层捕获,巡检不崩进程
            raised = e

    if raised is None:
        assert not sent, f"跳过口径应返回 0/None,实际 {sent!r}"
    assert mock_send.await_count == 0, f"settings 异常本轮应零发送,实际 {mock_send.await_count}"
    rows = (await db_session.execute(sqlalchemy.select(Notification))).scalars().all()
    assert rows == [], f"settings 异常不得落任何通知,实际 {len(rows)} 条"


# ---------------------------------------------------------------------------
# 行为规格 存量补录边界固化:补录=昨天(D-1),次日(D+1)巡检窗口={D, D+2}
# → 逾期第2天不属两时点 → 不发
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_sweep_window_excludes_backfilled_date(
    client, db_session, auth_headers, registered_user, delivery_svc,
):
    u1 = await _mk_user(client)
    await _mk_due_requirement(
        client, db_session, auth_headers, registered_user, [u1], YESTERDAY,
    )

    day_after = FIXED_TODAY + timedelta(days=1)  # 次日巡检
    with patch("app.services.delivery_reminder_service.gmt8_today", return_value=day_after), \
         patch("app.services.notification_service.send_notification", new_callable=AsyncMock) as mock_send:
        sent = await delivery_svc.run_delivery_reminder_sweep(db_session)

    assert sent == 0, f"补录日期出两时点窗口应不发,实际 {sent!r}"
    assert mock_send.await_count == 0, f"窗口外日期不得发通知,实际 {mock_send.await_count}"


# ---------------------------------------------------------------------------
# 判据6 通知 type=req_delivery_reminder 真实落库(ENUM 改表生效;
# 不 mock send_notification,仅 mock 日期)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_sweep_notification_type_persisted_enum(
    client, db_session, auth_headers, registered_user, delivery_svc,
):
    u1 = await _mk_user(client)
    env = await _mk_due_requirement(
        client, db_session, auth_headers, registered_user, [u1], TOMORROW,
    )
    req = env["req"]

    with patch("app.services.delivery_reminder_service.gmt8_today", return_value=FIXED_TODAY):
        sent = await delivery_svc.run_delivery_reminder_sweep(db_session)

    assert sent == 1, f"应真实落库 1 条,实际 {sent!r}"
    rows = (await db_session.execute(
        sqlalchemy.select(Notification).where(Notification.type == "req_delivery_reminder")
    )).scalars().all()
    assert len(rows) == 1, f"notifications 应有 1 条 type=req_delivery_reminder,实际 {len(rows)}(ENUM 改表生效?)"
    assert rows[0].recipient_id == u1["user_id"]
    assert rows[0].level == "normal"
    assert "交付临近" in rows[0].title
    assert rows[0].link == f"/requirements/{req.req_id}"
