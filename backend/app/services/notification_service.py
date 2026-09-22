"""通知服务 - R18(发送/钉钉/WebSocket 推送)"""

import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification, UserNotificationSettings
from app.models.project import Project

logger = logging.getLogger(__name__)

DINGTALK_FAIL_LIMIT = 3  # 连续失败 ≥3 次标记 webhook 失效


# ---------------------------------------------------------------------------
# 发送通知(业务事件入口)
# ---------------------------------------------------------------------------
async def send_notification(
    db: AsyncSession,
    *,
    recipient_id: str,
    type: str,
    level: str,
    title: str,
    content: str,
    link: Optional[str] = None,
    project_id: Optional[str] = None,
    task_id: Optional[str] = None,
) -> Notification:
    """
    创建站内通知(critical 再触发钉钉;toast 走 WS 频道由 WS 层广播)。
    级别 × 通道矩阵:
    - critical:站内信 + 钉钉(个人,若启用)+ 钉钉(项目,若启用)
    - normal/info:仅站内信(toast 由前端 WS 收到后按开关渲染)
    """
    notification = Notification(
        recipient_id=recipient_id,
        type=type,
        level=level,
        title=title,
        content=content,
        link=link,
        project_id=project_id,
        task_id=task_id,
    )
    db.add(notification)
    await db.flush()

    if level == "critical":
        await _send_dingtalk_personal(db, recipient_id, notification)
        if project_id:
            await _send_dingtalk_project(db, project_id, notification)

    logger.info("通知发送 recipient=%s type=%s level=%s", recipient_id, type, level)
    return notification


async def _send_dingtalk_personal(db: AsyncSession, recipient_id: str, notification: Notification) -> None:
    """个人钉钉:启用且 webhook 存在才发送;连续失败 ≥3 次自动停用并回写"""
    settings = (await db.execute(
        select(UserNotificationSettings).where(UserNotificationSettings.user_id == recipient_id)
    )).scalars().first()
    if settings is None or not settings.dingtalk_enabled or not settings.dingtalk_webhook:
        return

    ok = await _post_dingtalk(settings.dingtalk_webhook, notification)
    if ok:
        settings.dingtalk_fail_count = 0
    else:
        settings.dingtalk_fail_count = (settings.dingtalk_fail_count or 0) + 1
        if settings.dingtalk_fail_count >= 3:
            settings.dingtalk_enabled = False
            # 通知用户重新配置(站内信,info 级)
            db.add(Notification(
                recipient_id=recipient_id,
                type="runner_offline",  # 复用枚举内最接近类型;R19 可扩展专用类型
                level="info",
                title="钉钉通知已停用",
                content="钉钉 webhook 连续失败 3 次,已自动停用。请到个人设置重新配置。",
                link="/settings/notifications",
            ))
    await db.flush()


async def _send_dingtalk_project(db: AsyncSession, project_id: str, notification: Notification) -> None:
    """项目钉钉群:owner 配置的项目 webhook"""
    project = (await db.execute(
        select(Project).where(Project.project_id == project_id)
    )).scalars().first()
    if project is None or not project.dingtalk_enabled or not project.dingtalk_webhook:
        return
    await _post_dingtalk(project.dingtalk_webhook, notification)


async def _post_dingtalk(webhook: str, notification: Notification) -> bool:
    """调钉钉 webhook(markdown);4xx/网络错误返回 False(不抛异常,不影响站内信)"""
    import httpx

    payload = {
        "msgtype": "markdown",
        "markdown": {
            "title": notification.title,
            "text": f"### {notification.title}\n\n{notification.content}"
                    + (f"\n\n[查看详情]({notification.link})" if notification.link else ""),
        },
    }
    try:
        import httpx as _httpx

        async with _httpx.AsyncClient(timeout=10.0, verify=False) as client:
            resp = await client.post(webhook, json=payload)
        if resp.status_code >= 400:
            logger.warning("钉钉 webhook 返回 %s", resp.status_code)
            return False
        return True
    except Exception as e:
        logger.warning("钉钉 webhook 调用异常: %s", e)
        return False


async def test_dingtalk_webhook(webhook: str) -> tuple[bool, str]:
    """测试钉钉 webhook:发送测试 markdown;返回 (ok, message)"""
    import httpx as _httpx

    payload = {
        "msgtype": "markdown",
        "markdown": {"title": "旗程测试消息", "text": "### 旗程测试消息\n\n钉钉通知配置成功"},
    }
    try:
        async with _httpx.AsyncClient(timeout=10.0, verify=False) as client:
            resp = await client.post(webhook, json=payload)
        if resp.status_code >= 400:
            return False, "钉钉 Webhook 无效,请检查后重试"
        return True, "测试消息已发送,请检查钉钉群"
    except Exception:
        return False, "钉钉 Webhook 无效,请检查后重试"
