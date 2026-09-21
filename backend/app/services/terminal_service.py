"""终端服务 - R9(会话注册表 + 输入输出转发 + 限流 + 破坏性命令审计)

架构:前端 WS(/ws/terminal/{session_id}) ↔ 平台(本模块,路由) ↔ Runner WS(exec pty)。

- 会话注册表(内存):session_id → 前端 WebSocket 连接
- 转发:input 前端→Runner;output Runner→前端;ai_output(R4/R5 SDK 事件)→前端
- 限流:单会话输出 > 1000 块/秒丢弃中间块(插入限流提示一次)
- 审计:破坏性命令(rm -rf / git reset --hard 等)写结构化告警日志(R19 audit_logs 接入后入库)
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from fastapi import WebSocket

logger = logging.getLogger(__name__)

# 高频输出限流:每秒最多转发的输出块数(超出丢弃中间,保留最新)
MAX_OUTPUT_CHUNKS_PER_SECOND = 1000
# 破坏性命令关键词(不拦截,仅审计;R19 接入 audit_logs 后入库)
DESTRUCTIVE_PATTERNS = ("rm -rf", "git reset --hard", "mkfs", "dd if=", "> /dev/sda", "git push --force")


@dataclass
class TerminalConnection:
    """一条前端终端 WS 连接"""
    session_id: str
    task_id: str
    runner_id: str
    user_id: str
    websocket: WebSocket
    # 限流状态(滑动 1s 窗口)
    chunk_timestamps: list[float] = field(default_factory=list)
    drop_hint_sent: bool = False
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class TerminalRegistry:
    """session_id → 前端连接(内存态;pty 断线重连时复用)"""

    def __init__(self) -> None:
        self._sessions: dict[str, TerminalConnection] = {}

    def put(self, conn: TerminalConnection) -> None:
        self._sessions[conn.session_id] = conn

    def pop(self, session_id: str) -> Optional[TerminalConnection]:
        return self._sessions.pop(session_id, None)

    def get(self, session_id: str) -> Optional[TerminalConnection]:
        return self._sessions.get(session_id)


terminal_registry = TerminalRegistry()


# ---------------------------------------------------------------------------
# 限流
# ---------------------------------------------------------------------------
def check_rate_limit(conn: TerminalConnection) -> bool:
    """
    输出限流:>1000 块/秒丢弃中间块。
    返回 True=允许转发;False=本块丢弃(每秒首次丢弃时给一次提示标记)。
    """
    now = time.monotonic()
    window = [t for t in conn.chunk_timestamps if now - t < 1.0]
    if len(window) >= MAX_OUTPUT_CHUNKS_PER_SECOND:
        conn.chunk_timestamps = window
        if not conn.drop_hint_sent:
            conn.drop_hint_sent = True
            logger.info("终端输出限流触发 session=%s", conn.session_id)
        return False
    window.append(now)
    conn.chunk_timestamps = window
    if len(window) < MAX_OUTPUT_CHUNKS_PER_SECOND // 2:
        conn.drop_hint_sent = False  # 降回阈值以下后重置提示
    return True


# ---------------------------------------------------------------------------
# 转发(WS 端点与 Runner 消息处理调用)
# ---------------------------------------------------------------------------
async def forward_output_to_frontend(session_id: str, data: str, kind: str = "output") -> bool:
    """
    Runner → 前端输出转发(kind: output / ai_output)。
    会话不在线返回 False(Runner 侧缓冲丢弃)。
    """
    conn = terminal_registry.get(session_id)
    if conn is None or conn.websocket is None:
        return False
    if kind == "output" and not check_rate_limit(conn):
        return False
    try:
        async with conn.lock:
            await conn.websocket.send_json({"type": kind, "data": data})
        return True
    except Exception:
        logger.warning("终端输出转发失败 session=%s", session_id)
        return False


async def forward_input_to_runner(session_id: str, data: str) -> bool:
    """前端 → Runner 输入转发(先审计破坏性命令);Runner 离线返回 False"""
    audit_destructive_input(session_id, data)

    from app.services.runner_service import runner_registry as runner_conn_registry

    conn = terminal_registry.get(session_id)
    if conn is None:
        return False
    runner_conn = runner_conn_registry.get(conn.runner_id)
    if runner_conn is None or runner_conn.websocket is None:
        return False
    await runner_service_safe_send(runner_conn, {
        "type": "terminal_input",
        "session_id": session_id,
        "data": data,
    })
    return True


async def forward_resize_to_runner(session_id: str, cols: int, rows: int) -> None:
    from app.services.runner_service import runner_registry as runner_conn_registry

    conn = terminal_registry.get(session_id)
    if conn is None:
        return
    runner_conn = runner_conn_registry.get(conn.runner_id)
    if runner_conn is None or runner_conn.websocket is None:
        return
    await runner_service_safe_send(runner_conn, {
        "type": "terminal_resize",
        "session_id": session_id,
        "cols": cols,
        "rows": rows,
    })


async def runner_service_safe_send(runner_conn, message: dict) -> None:
    """下发给 Runner(异常吞掉记日志,终端场景不抛)"""
    try:
        from app.services.runner_service import send_to_runner
        await send_to_runner(runner_conn, message)
    except Exception as e:
        logger.warning("终端指令下发失败: %s", e)


# ---------------------------------------------------------------------------
# 审计
# ---------------------------------------------------------------------------
def audit_destructive_input(session_id: str, data: str) -> None:
    """
    破坏性命令审计(不拦截):rm -rf / git reset --hard / mkfs / dd 等。
    R19 audit_logs 落库;当前结构化日志(含会话,不含完整内容避免日志膨胀)。
    """
    lowered = data.lower()
    for pattern in DESTRUCTIVE_PATTERNS:
        if pattern in lowered:
            # TODO(R19): 写 audit_logs(terminal.destructive_command)
            logger.warning(
                "审计:终端破坏性命令 session=%s pattern=%s", session_id, pattern
            )
            break


# ---------------------------------------------------------------------------
# AI 输出通道(R4/R5 SDK 事件消费)
# ---------------------------------------------------------------------------
async def push_ai_output(task_id: str, line: str) -> None:
    """
    SDK 工具事件 → 终端回显(只读,[ai] 前缀高亮)。
    广播给该任务的所有在线终端会话。
    """
    for conn in list(terminal_registry._sessions.values()):  # noqa: SLF001 — 同模块注册表
        if conn.task_id == task_id:
            await forward_output_to_frontend(conn.session_id, f"[ai] {line}\n", kind="ai_output")
