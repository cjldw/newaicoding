"""归档服务 - R14(需求 done 后自动归档:时间线 + 归档总结 + 知识提取钩子)

V1 决策(留痕见 DEVPLAN/R14):
- AI 生成总结/提取知识走 R4 任务对话通道(CLI 兜底);本服务提供:
  1. archive_data(req):时间线(tasks/routes/requirement 数据合成)+ 归档路径
  2. archive_requirement(req):确定性模板生成 summary(不调 AI),置 archived,
     并提取最小知识条目(doc,draft)
- 后续由 R4 会话能力升级为真 AI 生成(钩子点已隔离)
"""

import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.container import Container
from app.models.project import Project
from app.models.requirement import Requirement
from app.models.route import Route
from app.models.task import Task
from app.services import knowledge_service

logger = logging.getLogger(__name__)


def _archive_dir(title: str, date: Optional[datetime] = None) -> str:
    """Q26:docs/{YYYYMMDD}_{descSlug}_archive(无任务短 id,系统生成)"""
    import re

    slug = re.sub(r"[^\w一-鿿-]+", "-", title.strip(), flags=re.UNICODE)
    slug = re.sub(r"-{2,}", "-", slug).strip("-")[:32] or "需求"
    date = date or datetime.now()
    return f"docs/{date.strftime('%Y%m%d')}_{slug}_archive"


def summary_path(title: str, date: Optional[datetime] = None) -> str:
    return f"{_archive_dir(title, date)}/summary.md"


def _summary_markdown(req: Requirement, project: Project) -> str:
    """确定性模板总结(V1;AI 生成走 R4 会话通道升级)"""
    lines = [
        f"# 归档总结:{req.title}",
        "",
        f"- 项目:{project.name}",
        f"- 需求分支:{req.req_branch}",
        "- 状态:全部发布任务已完成",
        "",
        "## 过程回顾",
        "",
        "1. 需求创建并完成 AI 打磨,PRD 评审通过",
        "2. 开发任务完成编码并推送至需求分支",
        "3. 测试任务执行,结果归档",
        "4. 发布任务合并至 master 并完成部署",
        "",
        "## 后续",
        "",
        "- 如需修改,请新建需求并关联本归档",
    ]
    return "\n".join(lines)


async def build_timeline(db: AsyncSession, req: Requirement) -> list[dict]:
    """时间线:需求创建 → 任务创建/完成 → 部署(数据来自本地台账;commit 明细经 GitLab 归 R4 联调)"""
    timeline: list[dict] = []

    timeline.append({
        "type": "requirement_created",
        "timestamp": req.created_at,
        "actor": {"user_id": req.created_by},
        "description": "需求创建",
    })

    tasks = (await db.execute(
        select(Task).where(Task.req_id == req.req_id).order_by(Task.created_at.asc())
    )).scalars().all()
    for t in tasks:
        timeline.append({
            "type": "task_created",
            "timestamp": t.created_at,
            "task_id": t.task_id,
            "task_type": t.type,
            "description": {"requirement": "创建打磨任务", "dev": "创建开发任务",
                            "test": "创建测试任务", "release": "创建发布任务"}.get(t.type, "创建任务"),
        })
        if t.started_at:
            timeline.append({
                "type": "task_started",
                "timestamp": t.started_at,
                "task_id": t.task_id,
                "task_type": t.type,
                "description": "任务开始执行",
            })
        if t.finished_at:
            timeline.append({
                "type": "task_finished",
                "timestamp": t.finished_at,
                "task_id": t.task_id,
                "task_type": t.type,
                "description": "任务完成",
            })
        # R7:发布任务 deployed 节点(deploy_phase 驱动,路由未注册也可回放)
        if t.type == "release" and (t.extended_attributes or {}).get("deploy_phase") == "deployed":
            timeline.append({
                "type": "deployed",
                "timestamp": t.finished_at or t.updated_at,
                "task_id": t.task_id,
                "task_type": t.type,
                "description": "部署成功",
            })

    routes = (await db.execute(
        select(Route).where(Route.task_id.in_(
            select(Task.task_id).where(Task.req_id == req.req_id)
        ), Route.type == "deploy")
    )).scalars().all()
    for r in routes:
        timeline.append({
            "type": "deployed",
            "timestamp": r.created_at,
            "deploy_url": f"http://{r.host}",
            "description": "部署成功",
        })

    timeline.sort(key=lambda item: item.get("timestamp") or datetime.min)
    return timeline


async def get_archive_data(db: AsyncSession, req: Requirement) -> dict:
    """归档页数据:需求信息 + 时间线 + 归档总结路径 + 关联知识条目"""
    from app.models.knowledge_entry import KnowledgeEntry
    from app.services.requirement_service import _creator_brief

    entries = (await db.execute(
        select(KnowledgeEntry).where(KnowledgeEntry.req_id == req.req_id)
        .order_by(KnowledgeEntry.created_at.asc())
    )).scalars().all()

    return {
        "req_id": req.req_id,
        "title": req.title,
        "status": req.status,
        "summary_file_path": summary_path(req.title),
        "timeline": await build_timeline(db, req),
        "knowledge": [
            {
                "entry_id": e.entry_id,
                "type": e.type,
                "title": e.title,
                "tags": e.tags or [],
                "status": e.status,
                "created_by": e.created_by,
                "created_at": e.created_at,
                # R4 联调对齐:前端据 project_id 决定详情路由(项目级/平台级)
                "project_id": e.project_id,
            }
            for e in entries
        ],
        "created_by": await _creator_brief(db, req.created_by),
        "created_at": req.created_at,
    }


async def archive_requirement(db: AsyncSession, req: Requirement, project: Project) -> None:
    """
    自动归档(done → archived):
    - 生成归档总结(确定性模板;summary.md 的容器内 commit 由 R4 发布通道补——
      此时需求分支已 merge,平台以 bot token 经 GitLab API 提交,V1 留待联调钩子)
    - 提取最小知识条目(doc,draft):归档记录本身
    """
    if req.status != "done":
        return

    summary_md = _summary_markdown(req, project)
    dir_path = _archive_dir(req.title)
    logger.info("归档总结生成(待经 GitLab API commit 到 master)%s/summary.md", dir_path)

    await knowledge_service.create_entry(
        db, project.project_id, None,
        type="doc",
        title=f"归档:{req.title}",
        content=summary_md,
        tags=["归档"],
        source_links=[{"type": "requirement", "url": f"/requirements/{req.req_id}"}],
        status="draft",
        created_by_kind="ai",
        req_id=req.req_id,
    )
    # 传 None operator 的兼容:created_by_kind=ai 时不校验角色
    req.status = "archived"
    await db.flush()
    logger.info("需求已归档 req=%s", req.req_id)
