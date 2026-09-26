"""系统级 Claude 资产采集服务 - R5(probe_claude 链路平台侧)

链路(R5.md 接口契约):
    超管 POST /api/admin/system-assets/collect
      → 本服务 collect:asyncio.Lock 防并发(并发第二次等待后直接返回首次结果)
      → pick runner(DB 调度优先,内存注册表兜底;无 → 502 无可用 Runner)
      → request_runner 下发 {"type":"probe_claude","image":...} 等待回报(超时 120s)
      → 覆盖入库 claude_system_assets(先清后插,同事务;失败异常上抛旧数据保留)
      → 响应 {skills:n, mcps:n, collected_at, image_tag};空结果附「镜像未内置」警告

一致性域(R5.md 服务端行为规格 + 收口审查裁决):
- 探测失败/超时 → 502 可重试,不做任何写库(旧采集数据保留)
- 超时 → 记失败冷却标记(窗口=COLLECT_TIMEOUT):窗口内重试立即 502
  「上次采集仍在进行」,不再堆叠临时容器(Runner 侧 probe 线程不可强杀)
- 单侧探测命令失败(Runner 回报 failed_sides)→ 部分结果语义(PRD R1):
  失败侧不清该侧旧库,成功侧正常覆盖,响应 data.warning 带警告
- 采集成功但结果为空 → 仍属成功采集:清空旧表 + 警告日志「镜像未内置」
"""

import asyncio
import logging
import time
from datetime import datetime

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.response import BizError, ErrCode
from app.models.system_asset import ClaudeSystemAsset
from app.services import runner_service

logger = logging.getLogger(__name__)

COLLECT_TIMEOUT = 120.0                      # probe 回报超时(秒;R5.md 契约)
DEFAULT_PROBE_IMAGE = "platform/devbox:v1"   # 与 Runner start_container 默认镜像一致

# 进程级互斥:同一时刻只允许一次探测(临时容器起→探→毁不并发)
_COLLECT_LOCK = asyncio.Lock()
# 并发域状态(形态便于测试间清零,.scratch/R5/qa-red-tests.md fixture 契约):
# - 成功:{"result": 响应, "done_at": monotonic}——done_at = 完成时刻,
#   arrival <= done_at 即「等待期间已有采集完成」→ 复用,不重复起容器。
# - 失败冷却:{"failed_at": monotonic}——超时后 Runner 侧 probe 可能仍在跑
#   (线程不可强杀,临时容器未毁),冷却窗口(= COLLECT_TIMEOUT,与 Runner 侧
#   wait_for 上限对齐)内重试立即 502「上次采集仍在进行」,不再堆叠容器。
_last_result: dict = {}


async def _pick_probe_runner(db: AsyncSession):
    """选探测 Runner(对齐 container_service 调度先例):pick_runner_db(worker,
    最少负载)→ 内存注册表 get → 无连接即 502;不回落任意在线连接
    (防 probe 落到 deploy 机:其无 devbox 镜像/容器权限语义不同)"""
    runner = await runner_service.pick_runner_db(db, "worker")
    conn = runner_service.runner_registry.get(runner.runner_id) if runner is not None else None
    if conn is None:
        # DB 无在线(或连接刚断):按无可用处理,不回落
        logger.warning("系统资产采集中止:无可用 worker Runner(DB 调度与内存注册表均无)")
        raise BizError(
            ErrCode.NO_RUNNER_AVAILABLE,
            "无可用 Runner 在线,无法采集(请先启动 Runner)",
            status_code=502,
        )
    return conn


async def collect(db: AsyncSession, operator_user_id: str, image: str = DEFAULT_PROBE_IMAGE) -> dict:
    """
    采集镜像内置 skills/MCP 并覆盖入库。返回响应契约:
    {skills: n, mcps: n, collected_at: str, image_tag: str[, warning: str]}
    探测失败/超时 → BizError 502(不写库,旧数据保留)。
    """
    arrival = time.monotonic()
    async with _COLLECT_LOCK:
        cached = _last_result.get("result")
        if cached is not None and arrival <= _last_result.get("done_at", 0.0):
            # 并发第二次:等待期间首次已完成 → 直接返回首次结果(不重复起容器)
            logger.info(
                "系统资产采集并发去重:复用首次结果 user=%s collected_at=%s",
                operator_user_id, cached.get("collected_at"),
            )
            return cached

        # 失败冷却:上次超时后 Runner 侧 probe 可能仍在进行(容器未毁),
        # 窗口内重试立即 502,不再堆叠临时容器(窗口 = COLLECT_TIMEOUT:
        # Runner 侧 wait_for 上限同长,窗口结束必然已回报/自毁)
        failed_at = _last_result.get("failed_at")
        if failed_at is not None and time.monotonic() - failed_at < COLLECT_TIMEOUT:
            logger.warning(
                "系统资产采集冷却中:上次探测超时(%.0fs 前),拒绝重试 user=%s",
                time.monotonic() - failed_at, operator_user_id,
            )
            raise BizError(
                ErrCode.SYSTEM_ASSET_PROBE_FAILED,
                "上次采集仍在进行,请稍后再试(冷却窗口内不重复起容器)",
                status_code=502,
            )

        t0 = time.monotonic()
        conn = await _pick_probe_runner(db)
        # pick 只做 SELECT:提交结束当前事务,不把 DB 连接钉在最长 120s 的探测上;
        # 探测后的覆盖入库在下方新事务承接
        await db.commit()
        logger.info(
            "系统资产采集开始 user=%s runner=%s image=%s timeout=%.0fs",
            operator_user_id, conn.runner_id, image, COLLECT_TIMEOUT,
        )

        message = {"type": "probe_claude", "image": image}
        try:
            result = await runner_service.request_runner(conn, message, timeout=COLLECT_TIMEOUT)
        except TimeoutError as e:
            # 死链/超时(request_runner 已归一化 TimeoutError)→ 502 可重试,旧数据保留;
            # 同时记失败冷却标记(窗口内重试直接 502,防堆叠容器)
            _last_result.clear()
            _last_result["failed_at"] = time.monotonic()
            logger.warning(
                "系统资产采集失败:Runner 探测超时或连接不可用 runner=%s 耗时=%.1fs: %s",
                conn.runner_id, time.monotonic() - t0, e,
            )
            raise BizError(
                ErrCode.SYSTEM_ASSET_PROBE_FAILED,
                "Runner 探测超时或连接不可用,可稍后重试(原有数据未受影响)",
                status_code=502,
            ) from e
        if not result.get("ok"):
            # Runner 回报 ok=False(容器启动/exec 失败)→ 502 可重试,旧数据保留。
            # Runner 已给出终态(容器已毁、无残留执行),无堆叠风险 → 不设冷却
            error = str(result.get("error") or "探测失败")
            logger.warning(
                "系统资产采集失败:Runner 回报失败 runner=%s 耗时=%.1fs: %s",
                conn.runner_id, time.monotonic() - t0, error,
            )
            raise BizError(
                ErrCode.SYSTEM_ASSET_PROBE_FAILED,
                f"镜像探测失败: {error}(可重试,原有数据未受影响)",
                status_code=502,
            )

        probe = result.get("data") or {}
        # 部分结果语义(PRD R1):单侧探测命令失败 → 失败侧按空且不清该侧旧库,响应带警告
        failed_sides = {s for s in (probe.get("failed_sides") or []) if s in ("skills", "mcps")}
        side_warnings = [str(w) for w in (probe.get("warnings") or []) if str(w)]
        skills = [str(s).strip() for s in (probe.get("skills") or []) if str(s).strip()]
        # mcp name 非 str(int 等)→ str() coerce 走 502 之外的正常路径,不 500
        mcps = [
            m for m in (probe.get("mcps") or [])
            if isinstance(m, dict) and str(m.get("name") or "").strip()
        ]
        if "skills" in failed_sides:
            skills = []
        if "mcps" in failed_sides:
            mcps = []
        image_tag = str(probe.get("image_tag") or image or DEFAULT_PROBE_IMAGE)
        collected_at = datetime.now()

        # 覆盖入库(探测后新事务承接):成功侧先清后插;失败侧不清该侧旧库(部分结果)。
        # 插失败整体回滚 → 旧数据保留
        rows: list[ClaudeSystemAsset] = []
        if "skills" not in failed_sides:
            await db.execute(delete(ClaudeSystemAsset).where(ClaudeSystemAsset.kind == "skill"))
            skill_rows = [
                ClaudeSystemAsset(
                    name=name, kind="skill",
                    detail={"name": name},
                    collected_at=collected_at, image_tag=image_tag,
                )
                for name in skills
            ]
            rows += skill_rows
            db.add_all(skill_rows)
        if "mcps" not in failed_sides:
            await db.execute(delete(ClaudeSystemAsset).where(ClaudeSystemAsset.kind == "mcp"))
            mcp_rows = [
                ClaudeSystemAsset(
                    name=str(m["name"]).strip(), kind="mcp",
                    detail=m,  # 探测原文(传输类型/命令等)
                    collected_at=collected_at, image_tag=image_tag,
                )
                for m in mcps
            ]
            rows += mcp_rows
            db.add_all(mcp_rows)
        await db.flush()

        out = {
            "skills": len(skills),
            "mcps": len(mcps),
            "collected_at": collected_at.isoformat(sep=" ", timespec="seconds"),
            "image_tag": image_tag,
        }
        warnings = list(side_warnings)
        if not rows and not failed_sides:
            # 状态域:空结果仍是成功采集(清空旧表),但要警告「镜像未内置」
            warnings.append("镜像未内置任何 skills/MCP,请检查镜像构建(已清空原有列表)")
        if warnings:
            logger.warning("系统资产采集警告(image=%s): %s", image_tag, "; ".join(warnings))
            out["warning"] = "; ".join(warnings)
        _last_result.clear()
        _last_result["result"] = out
        _last_result["done_at"] = time.monotonic()
        logger.info(
            "系统资产采集完成 skills=%d mcps=%d failed_sides=%s image=%s 耗时=%.1fs",
            len(skills), len(mcps), sorted(failed_sides) or "无", image_tag, time.monotonic() - t0,
        )
        return out
