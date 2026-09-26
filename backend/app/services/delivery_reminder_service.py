"""交付提醒每日巡检 - R6(PRD-B R3;GMT+8 每日一次)

口径(PRD-B R3 已确认):
- 每日巡检(GMT+8)查 delivery_date IN (今天-1, 今天+1) 且需求未终态(done/archived):
  - delivery_date=明天 →「需求《X》交付时间临近(明天)」
  - delivery_date=昨天 →「需求《X》已逾期」
- 收件人=需求关联用户(related_user_ids 去重保序)过滤仍为项目成员者;空名单跳过
- 防重入:last_run_date 存 platform_settings(req_delivery_reminder_last_date),
  maybe_run_daily_sweep 包装层同日判重(读写闭环),同一 GMT+8 日只发一轮
  (重启同日不重发);两时点各一日的窗口 + 每日一轮 ⇒ 每需求每阶段天然至多一条
- 存量补录边界:补录=昨天且当天巡检已跑 → 次日已是逾期第 2 天,不在两时点窗口 → 不发(PRD 接受)
- settings 读/写失败:记日志跳过本轮,不崩(写失败回滚本轮通知,防「已发未记」重发)

契约(Green 定稿,见 .scratch/R6/qa-red-tests.md):
- run_delivery_reminder_sweep(db, today=None):巡检主体,today 直调入参
  (None 时内部 gmt8_today),不读写 platform_settings(防重入是包装层职责)
- maybe_run_daily_sweep(db=None, today=None):防重入包装 + session/commit 生命周期
"""

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project_member import ProjectMember
from app.models.requirement import Requirement
from app.services import notification_service, platform_settings_service

logger = logging.getLogger(__name__)

# 通知类型(models/notification.py ENUM 已新增,改表 SQL 见 .scratch/R6/deploy-sql.md)
NOTIFICATION_TYPE = "req_delivery_reminder"
# last_run_date 的 platform_settings key(白名单已加,见 platform_settings_service.SETTING_KEYS)
LAST_RUN_KEY = "req_delivery_reminder_last_date"
# 系统占位操作人(与 runner_service.offline 审计同一口径)
SYSTEM_USER_ID = "00000000-0000-0000-0000-000000000000"
# 终态(命中巡检日期也不发)
TERMINAL_STATUSES = ("done", "archived")


# ---------------------------------------------------------------------------
# 时区口径:「今天」= GMT+8
# ---------------------------------------------------------------------------
def gmt8_today() -> date:
    """平台时区约定的「今天」:UTC naive + 8h 取 date(与 R5 逾期标记同口径)"""
    utc_naive = datetime.now(timezone.utc).replace(tzinfo=None)
    return (utc_naive + timedelta(hours=8)).date()


# ---------------------------------------------------------------------------
# 每日巡检主体(today 直调,不读写 platform_settings;防重入见 maybe_run_daily_sweep)
# ---------------------------------------------------------------------------
async def run_delivery_reminder_sweep(db: AsyncSession, today: Optional[date] = None) -> int:
    """
    跑一轮交付提醒巡检(巡检主体,直调/包装两用):
    1. 查 delivery_date IN (today-1, today+1) 且未终态的需求,按需求向关联用户
       (过滤仍为项目成员)发站内提醒;单条失败记日志继续
    2. 返回成功发送条数(commit 归调用方;本函数不读写 platform_settings,
       防重入 last_run_date 判定是 maybe_run_daily_sweep 包装层职责)

    today 直调传入可测(不依赖真实时钟);缺省取 gmt8_today()(lifespan 口径)。
    """
    today = today or gmt8_today()
    return await _notify_due_requirements(db, today)


async def _notify_due_requirements(db: AsyncSession, today: date) -> int:
    """巡检窗口内的需求逐个发提醒;返回成功发送条数"""
    window = [today - timedelta(days=1), today + timedelta(days=1)]
    result = await db.execute(
        select(Requirement).where(
            Requirement.delivery_date.in_(window),
            Requirement.status.notin_(TERMINAL_STATUSES),
        )
    )
    reqs = list(result.scalars().all())

    sent = 0
    for req in reqs:
        sent += await _notify_requirement(db, req, today)
    logger.info("交付提醒巡检窗口命中 today=%s window=%s 需求=%d 发送=%d",
                today, [d.isoformat() for d in window], len(reqs), sent)
    return sent


async def _notify_requirement(db: AsyncSession, req: Requirement, today: date) -> int:
    """向单个需求的关联用户发提醒;返回成功发送条数(空名单/全非成员 → 0)"""
    ids = [uid for uid in dict.fromkeys(req.related_user_ids or [])]  # 去重保序
    if not ids:
        logger.info("交付提醒跳过空名单 req=%s delivery_date=%s", req.req_id, req.delivery_date)
        return 0

    # 过滤仍为该项目成员(巡检时点可能已被移出)
    result = await db.execute(
        select(ProjectMember.user_id).where(
            ProjectMember.project_id == req.project_id,
            ProjectMember.user_id.in_(ids),
        )
    )
    member_ids = set(result.scalars().all())
    recipients = [uid for uid in ids if uid in member_ids]
    if len(recipients) < len(ids):
        logger.info(
            "交付提醒跳过非项目成员 req=%s project=%s skip=%s",
            req.req_id, req.project_id, [uid for uid in ids if uid not in member_ids],
        )
    if not recipients:
        return 0

    overdue = req.delivery_date == today - timedelta(days=1)
    date_str = req.delivery_date.isoformat() if req.delivery_date else ""
    if overdue:
        title = f"需求《{req.title}》已逾期"
        content = f"需求交付时间为 {date_str},已逾期 1 天,请尽快跟进。"
    else:
        title = f"需求《{req.title}》交付临近(明天)"
        content = f"需求交付时间为明天({date_str}),请关注进度、按期交付。"

    sent = 0
    for uid in recipients:
        try:
            await notification_service.send_notification(
                db,
                recipient_id=uid,
                type=NOTIFICATION_TYPE,
                level="normal",
                title=title,
                content=content,
                link=f"/requirements/{req.req_id}",
                project_id=req.project_id,
            )
            sent += 1
        except Exception as e:
            logger.warning("交付提醒单发失败(跳过继续) req=%s recipient=%s: %s", req.req_id, uid, e)
    return sent


# ---------------------------------------------------------------------------
# lifespan 防重入包装(60s 循环调用:读 last_run_date 判重 → 巡检 → 写回,
# 自持 session/commit,异常兜底不崩)
# ---------------------------------------------------------------------------
async def maybe_run_daily_sweep(
    db: Optional[AsyncSession] = None, today: Optional[date] = None
) -> Optional[int]:
    """
    每日巡检调度包装(防重入判定在此层,last_run_date 读写闭环):
    1. 读 platform_settings 的 req_delivery_reminder_last_date,= 今天(GMT+8)
       → 防重入跳过(返回 0);读失败 → 本轮跳过(宁缺勿重,不崩)
    2. 跑 run_delivery_reminder_sweep(db, today) 并把 last_run_date 写回今天;
       写失败 → 回滚本轮已 flush 的通知(同事务),防「已发未记」次日重发
    (任何异常记日志返回 None,不崩,下一轮 60s 循环继续。)

    db 传 None 时自建 session 并自行 commit(lifespan 用法);
    传入 db 时复用调用方事务,commit 归调用方(测试用法)。
    返回本轮发送条数;防重入/读写失败跳过时为 0(同 falsy),兜底异常为 None。
    """
    today = today or gmt8_today()
    own_session = db is None
    if own_session:
        from app.database import async_session_factory

        db = async_session_factory()

    try:
        # 1) 防重入:读 last_run_date(失败 → 本轮跳过,宁缺勿重)
        try:
            last = await platform_settings_service.get_setting(db, LAST_RUN_KEY)
        except Exception as e:
            logger.warning("交付提醒巡检:读取 %s 失败,本轮跳过: %s", LAST_RUN_KEY, e)
            return 0
        if last == today.isoformat():
            logger.info("交付提醒巡检:今日已跑(last_run_date=%s),防重入跳过", last)
            return 0

        logger.info("交付提醒巡检开始 today=%s(last_run_date=%s)", today, last)
        sent = await run_delivery_reminder_sweep(db, today)

        # 2) 写回 last_run_date:失败 → 回滚本轮通知(同事务),防次日重发
        try:
            await platform_settings_service.update_settings(
                db, SYSTEM_USER_ID, {LAST_RUN_KEY: today.isoformat()}
            )
        except Exception as e:
            await db.rollback()
            logger.warning("交付提醒巡检:写回 %s 失败,本轮已回滚(0 发送): %s", LAST_RUN_KEY, e)
            return 0

        if own_session:
            await db.commit()
        logger.info("交付提醒巡检完成 today=%s sent=%d", today, sent)
        return sent
    except Exception as e:
        logger.warning("交付提醒每日巡检异常,本轮跳过(下一轮继续): %s", e)
        return None
    finally:
        if own_session:
            await db.close()
