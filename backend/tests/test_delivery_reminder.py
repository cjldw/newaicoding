"""
R6 交付提醒(每日巡检)— 契约定稿测试(today 直调口径,9 用例)
================================================================
重建背景:本文件曾由 QA 以 TDD Red 产出(Green 9/9),后被外部删除
(DEVPLAN.md 决策留痕:以 11 用例文件 test_r6_delivery_reminder.py 去重);
R6 审计 P1 判定删除不当——本文件契约会今口径差异在「today 直调」可测性
(不 patch 时钟),按 .scratch/R6/qa-red-tests.md 定稿契约重建,两文件并存。

定稿契约(见 .scratch/R6/qa-red-tests.md):
- run_delivery_reminder_sweep(db, today=None) -> int:巡检主体;today=GMT+8 date
  直调入参(None 时内部 gmt8_today());窗口 delivery_date IN (today-1, today+1)
  且 status NOT IN (done, archived);收件人=关联用户去重 ∩ 仍为项目成员;
  单条失败 try/except 继续;返回成功发送数;不读写 platform_settings
- maybe_run_daily_sweep(db=None, today=None):防重入包装;
  get_setting(db, "req_delivery_reminder_last_date") == today → 跳过;
  否则跑巡检并 update_settings 写回 today;settings 读失败 → 跳过本轮不崩

覆盖映射(qa-red-tests.md 9 点 → 用例):
  1 test_tomorrow_two_related_users_get_upcoming_notifs   明天两关联用户收「临近」
  2 test_yesterday_gets_overdue_notif                     昨天收「已逾期」
  3 test_terminal_status_no_notify                        终态豁免(done/archived)
  4 test_empty_or_nonmember_list_no_notify_no_error       空名单/非成员过滤
  5 test_one_user_send_failure_others_still_notified      单发失败继续
 6a test_last_run_today_skips_sweep                       last_run_date 同日幂等
 6b test_last_run_yesterday_runs_and_updates_to_today     次日跑并写回 today
  7 test_settings_read_failure_skips_round_no_crash       settings 读失败跳过不崩
  8 test_day_before_yesterday_out_of_window_no_notify     前天窗口外不发

mock 口径(先例 test_requirement_review_notify.py;与 11 用例文件的差异:
日期不 patch gmt8_today,一律 today=FIXED_TODAY 直调入参):
- 发送:patch("app.services.notification_service.send_notification", new_callable=AsyncMock)
- settings 读:patch("app.services.platform_settings_service.get_setting", new_callable=AsyncMock)
- settings 写:patch("app.services.platform_settings_service.update_settings", new_callable=AsyncMock)
"""
from datetime import date, timedelta
from unittest.mock import AsyncMock, patch

import pytest
import sqlalchemy

from app.models.project import PlatformSetting
from app.models.project_member import ProjectMember
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
DAY_BEFORE = FIXED_TODAY - timedelta(days=2)
LAST_RUN_KEY = "req_delivery_reminder_last_date"


# ---------------------------------------------------------------------------
# 环境噪声处置(qa-red-tests.md 留痕:共享远程测试库存在历史崩溃会话遗留行)
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
async def _clean_stale_platform_settings(db_session):
    """测试前清 gitlab_* 遗留行(_seed_gitlab_settings 盲插,遗留行必炸;
    conftest 只保证测试后清理)。"""
    await db_session.execute(
        sqlalchemy.delete(PlatformSetting).where(PlatformSetting.key.like("gitlab_%"))
    )
    await db_session.flush()


# ---------------------------------------------------------------------------
# 辅助(口径照抄 test_requirement_review_notify.py / test_r6_delivery_reminder.py)
# ---------------------------------------------------------------------------
async def _get_req_orm(db_session, req_id: str):
    from app.models.requirement import Requirement

    return (await db_session.execute(
        sqlalchemy.select(Requirement).where(Requirement.req_id == req_id)
    )).scalars().first()


async def _add_member_once(db_session, project_id: str, user_id: str, role: str = "editor") -> None:
    """幂等补成员行(查重后 add;同事务重复补行必 Duplicate entry)。"""
    existing = (await db_session.execute(
        sqlalchemy.select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user_id,
        )
    )).scalars().first()
    if existing is None:
        _add_member(db_session, project_id, user_id, role=role)


async def _mk_project_with_member(client, db_session, auth_headers, registered_user,
                                  related) -> dict:
    """一测一项目(gitlab settings 每事务只能 seed 一次)+ 名单成员行。

    related:关联用户凭据列表(R1 名单按项目成员过滤,先补成员再建需求);
    传 [] → 空名单;传 None → 不传 related_user_ids 字段。
    """
    project = await _setup_project(db_session, registered_user)
    await _add_member_once(db_session, project.project_id, registered_user["user_id"])
    for u in related or []:
        if u["user_id"] != registered_user["user_id"]:
            await _add_member_once(db_session, project.project_id, u["user_id"])
    await db_session.flush()

    payload = {"title": "交付提醒需求", "description": "d"}
    if related is not None:
        payload["related_user_ids"] = [u["user_id"] for u in related]
    body = await _create_requirement(client, auth_headers, project, payload)
    assert body["code"] == 0, body
    req = await _get_req_orm(db_session, body["data"]["req_id"])
    assert req is not None, body
    return {"project": project, "req": req}


async def _mk_due_requirement(client, db_session, auth_headers, registered_user,
                              related, delivery_date, status="approved", project=None) -> dict:
    """建需求(带名单)+ ORM 置 delivery_date/status;project 传 None 新建。"""
    if project is None:
        env = await _mk_project_with_member(
            client, db_session, auth_headers, registered_user, related)
        project = env["project"]
    else:
        for u in related or []:
            if u["user_id"] != registered_user["user_id"]:
                await _add_member_once(db_session, project.project_id, u["user_id"])
        await db_session.flush()
        payload = {"title": "交付提醒需求", "description": "d"}
        if related is not None:
            payload["related_user_ids"] = [u["user_id"] for u in related]
        body = await _create_requirement(client, auth_headers, project, payload)
        assert body["code"] == 0, body
        req = await _get_req_orm(db_session, body["data"]["req_id"])
        assert req is not None, body
        env = {"project": project, "req": req}

    env["req"].delivery_date = delivery_date
    env["req"].status = status
    await db_session.flush()
    return env


def _payload_of(mock_update) -> dict:
    """update_settings 第三参兼容取法(qa-red-tests.md:args[-1] / kwargs['payload'] 均可)。"""
    assert mock_update.await_count >= 1, "update_settings 未被调用"
    kw_payload = mock_update.await_args.kwargs.get("payload")
    return kw_payload if kw_payload is not None else mock_update.await_args.args[-1]


# ---------------------------------------------------------------------------
# 1 delivery_date=明天 → 两关联用户各收「交付临近(明天)」
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_tomorrow_two_related_users_get_upcoming_notifs(
    client, db_session, auth_headers, registered_user,
):
    from app.services import delivery_reminder_service as delivery_svc

    u1 = await _mk_user(client)
    u2 = await _mk_user(client)
    env = await _mk_due_requirement(
        client, db_session, auth_headers, registered_user, [u1, u2], TOMORROW,
    )
    req = env["req"]

    with patch("app.services.notification_service.send_notification",
               new_callable=AsyncMock) as mock_send:
        sent = await delivery_svc.run_delivery_reminder_sweep(db_session, FIXED_TODAY)

    assert sent == 2, f"应返回发送条数 2,实际 {sent!r}"
    assert mock_send.await_count == 2, f"期望 2 次通知,实际 {mock_send.await_count}"
    recipients = set()
    for c in mock_send.await_args_list:
        kw = c.kwargs
        recipients.add(kw["recipient_id"])
        assert kw["type"] == "req_delivery_reminder", kw
        assert kw["level"] == "normal", kw
        assert req.title in kw["title"], kw
        assert "临近" in kw["title"], kw
        assert kw["link"] == f"/requirements/{req.req_id}", kw
        assert isinstance(kw["content"], str) and kw["content"], kw
    assert recipients == {u1["user_id"], u2["user_id"]}, recipients


# ---------------------------------------------------------------------------
# 2 delivery_date=昨天 → 「已逾期」
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_yesterday_gets_overdue_notif(
    client, db_session, auth_headers, registered_user,
):
    from app.services import delivery_reminder_service as delivery_svc

    u1 = await _mk_user(client)
    env = await _mk_due_requirement(
        client, db_session, auth_headers, registered_user, [u1], YESTERDAY,
    )
    req = env["req"]

    with patch("app.services.notification_service.send_notification",
               new_callable=AsyncMock) as mock_send:
        sent = await delivery_svc.run_delivery_reminder_sweep(db_session, FIXED_TODAY)

    assert sent == 1, f"应返回发送条数 1,实际 {sent!r}"
    assert mock_send.await_count == 1, f"期望 1 次通知,实际 {mock_send.await_count}"
    kw = mock_send.await_args.kwargs
    assert kw["recipient_id"] == u1["user_id"], kw
    assert kw["type"] == "req_delivery_reminder", kw
    assert kw["level"] == "normal", kw
    assert "已逾期" in kw["title"], kw
    assert kw["link"] == f"/requirements/{req.req_id}", kw


# ---------------------------------------------------------------------------
# 3 终态(done/archived)命中日期 → 零发送零调用
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_terminal_status_no_notify(
    client, db_session, auth_headers, registered_user,
):
    from app.services import delivery_reminder_service as delivery_svc

    u1 = await _mk_user(client)
    u2 = await _mk_user(client)
    env1 = await _mk_due_requirement(
        client, db_session, auth_headers, registered_user, [u1], TOMORROW, status="done",
    )
    await _mk_due_requirement(
        client, db_session, auth_headers, registered_user, [u2], YESTERDAY,
        status="archived", project=env1["project"],
    )

    with patch("app.services.notification_service.send_notification",
               new_callable=AsyncMock) as mock_send:
        sent = await delivery_svc.run_delivery_reminder_sweep(db_session, FIXED_TODAY)

    assert sent == 0, f"终态命中日期应全跳过返回 0,实际 {sent!r}"
    assert mock_send.await_count == 0, f"终态需求不得发通知,实际 {mock_send.await_count}"


# ---------------------------------------------------------------------------
# 4 空名单 + 成员全移除两形态 → 零发送不报错
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_empty_or_nonmember_list_no_notify_no_error(
    client, db_session, auth_headers, registered_user,
):
    from app.services import delivery_reminder_service as delivery_svc

    u1 = await _mk_user(client)
    # 形态一:显式空名单
    env1 = await _mk_due_requirement(
        client, db_session, auth_headers, registered_user, [], TOMORROW,
    )
    # 形态二:关联用户已全部移出项目(ORM 置 NULL 同义形态并入:存量 NULL 也跳过)
    env = await _mk_due_requirement(
        client, db_session, auth_headers, registered_user, [u1], YESTERDAY,
        project=env1["project"],
    )
    env["req"].related_user_ids = None
    member_row = (await db_session.execute(
        sqlalchemy.select(ProjectMember).where(
            ProjectMember.project_id == env["project"].project_id,
            ProjectMember.user_id == u1["user_id"],
        )
    )).scalars().first()
    if member_row is not None:
        await db_session.delete(member_row)
    await db_session.flush()

    with patch("app.services.notification_service.send_notification",
               new_callable=AsyncMock) as mock_send:
        sent = await delivery_svc.run_delivery_reminder_sweep(db_session, FIXED_TODAY)

    assert sent == 0, f"空名单/非成员应零发送返回 0,实际 {sent!r}"
    assert mock_send.await_count == 0, f"空名单/非成员应零调用,实际 {mock_send.await_count}"


# ---------------------------------------------------------------------------
# 5 首个收件人单发失败 → 被吞,次条照发,函数不抛,返回 1
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_one_user_send_failure_others_still_notified(
    client, db_session, auth_headers, registered_user,
):
    from app.services import delivery_reminder_service as delivery_svc

    u1 = await _mk_user(client)
    u2 = await _mk_user(client)
    await _mk_due_requirement(
        client, db_session, auth_headers, registered_user, [u1, u2], TOMORROW,
    )

    with patch("app.services.notification_service.send_notification",
               new_callable=AsyncMock) as mock_send:
        mock_send.side_effect = [RuntimeError("send boom"), None]
        sent = await delivery_svc.run_delivery_reminder_sweep(db_session, FIXED_TODAY)

    assert sent == 1, f"首条失败被吞、次条成功,应返回 1,实际 {sent!r}"
    assert mock_send.await_count == 2, f"失败不得中断其余收件人,期望 2 次调用,实际 {mock_send.await_count}"


# ---------------------------------------------------------------------------
# 6a last_run_date=今天 → 同日幂等:零发送、不写 settings
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_last_run_today_skips_sweep(
    client, db_session, auth_headers, registered_user,
):
    from app.services import delivery_reminder_service as delivery_svc

    u1 = await _mk_user(client)
    await _mk_due_requirement(
        client, db_session, auth_headers, registered_user, [u1], TOMORROW,
    )

    with patch("app.services.notification_service.send_notification",
               new_callable=AsyncMock) as mock_send, \
         patch("app.services.platform_settings_service.get_setting",
               new_callable=AsyncMock) as mock_get, \
         patch("app.services.platform_settings_service.update_settings",
               new_callable=AsyncMock) as mock_update:
        mock_get.return_value = FIXED_TODAY.isoformat()
        sent = await delivery_svc.maybe_run_daily_sweep(db_session, today=FIXED_TODAY)

    assert not sent, f"last_run_date=今天应防重入跳过(0/None),实际 {sent!r}"
    assert mock_send.await_count == 0, f"同日不得重发,实际 {mock_send.await_count}"
    assert mock_update.await_count == 0, "同日跳过不得写 settings"


# ---------------------------------------------------------------------------
# 6b last_run_date=昨天(非今天)→ 跑巡检发 1 条 + update_settings 写回 today
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_last_run_yesterday_runs_and_updates_to_today(
    client, db_session, auth_headers, registered_user,
):
    from app.services import delivery_reminder_service as delivery_svc

    u1 = await _mk_user(client)
    await _mk_due_requirement(
        client, db_session, auth_headers, registered_user, [u1], TOMORROW,
    )

    with patch("app.services.notification_service.send_notification",
               new_callable=AsyncMock) as mock_send, \
         patch("app.services.platform_settings_service.get_setting",
               new_callable=AsyncMock) as mock_get, \
         patch("app.services.platform_settings_service.update_settings",
               new_callable=AsyncMock) as mock_update:
        mock_get.return_value = YESTERDAY.isoformat()
        sent = await delivery_svc.maybe_run_daily_sweep(db_session, today=FIXED_TODAY)

    assert sent == 1, f"last_run_date≠今天应触发巡检发送 1 条,实际 {sent!r}"
    assert mock_send.await_count == 1, f"期望 1 次通知,实际 {mock_send.await_count}"
    assert _payload_of(mock_update) == {LAST_RUN_KEY: FIXED_TODAY.isoformat()}, \
        f"应把 last_run_date 写回今天,实际 {_payload_of(mock_update)!r}"


# ---------------------------------------------------------------------------
# 7 settings 读失败 → 不崩、零发送、不写 settings(跳过本轮)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_settings_read_failure_skips_round_no_crash(
    client, db_session, auth_headers, registered_user,
):
    from app.services import delivery_reminder_service as delivery_svc

    u1 = await _mk_user(client)
    await _mk_due_requirement(
        client, db_session, auth_headers, registered_user, [u1], TOMORROW,
    )

    with patch("app.services.notification_service.send_notification",
               new_callable=AsyncMock) as mock_send, \
         patch("app.services.platform_settings_service.get_setting",
               new_callable=AsyncMock) as mock_get, \
         patch("app.services.platform_settings_service.update_settings",
               new_callable=AsyncMock) as mock_update:
        mock_get.side_effect = RuntimeError("settings boom")
        sent = await delivery_svc.maybe_run_daily_sweep(db_session, today=FIXED_TODAY)

    assert not sent, f"settings 读失败应跳过本轮(0/None),实际 {sent!r}"
    assert mock_send.await_count == 0, f"settings 读失败应零发送,实际 {mock_send.await_count}"
    assert mock_update.await_count == 0, "settings 读失败不得写回"


# ---------------------------------------------------------------------------
# 8 delivery_date=前天(窗口外)→ 零发送
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_day_before_yesterday_out_of_window_no_notify(
    client, db_session, auth_headers, registered_user,
):
    from app.services import delivery_reminder_service as delivery_svc

    u1 = await _mk_user(client)
    await _mk_due_requirement(
        client, db_session, auth_headers, registered_user, [u1], DAY_BEFORE,
    )

    with patch("app.services.notification_service.send_notification",
               new_callable=AsyncMock) as mock_send:
        sent = await delivery_svc.run_delivery_reminder_sweep(db_session, FIXED_TODAY)

    assert sent == 0, f"前天出两时点窗口应不发,实际 {sent!r}"
    assert mock_send.await_count == 0, f"窗口外日期不得发通知,实际 {mock_send.await_count}"
