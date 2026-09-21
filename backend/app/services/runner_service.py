"""Runner 通信服务 - R8(Runner 注册表 + WebSocket 消息下发)

协议(D13/R8 分片):JSON 消息,type ∈
  register / heartbeat / start_container / stop_container            (平台 → Runner)
  container_started / container_stopped / container_event            (Runner → 平台)

R8 最小版:Runner 注册表为内存态(连接 ↔ runner_id/role/负载);
R16 落 runners 表后升级为 DB 注册 + 心跳判定 offline。
"""

import asyncio
import logging
import random
from dataclasses import dataclass, field
from typing import Optional

from fastapi import WebSocket

logger = logging.getLogger(__name__)


@dataclass
class RunnerConnection:
    """一条已连接的 Runner"""
    runner_id: str
    role: str = "general"          # general / deploy(R16 正式化)
    websocket: Optional[WebSocket] = None
    host: str = ""                 # Runner 宿主机地址(网关直连用,D20)
    load: int = 0                  # 运行中容器数(平台侧口径)
    last_heartbeat_ts: float = 0.0
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


class RunnerRegistry:
    """Runner 连接注册表(单实例内存态;R16 升级 DB)"""

    def __init__(self) -> None:
        self._runners: dict[str, RunnerConnection] = {}

    # ---- 注册 / 注销 ----
    def register(self, runner_id: str, role: str, websocket: WebSocket, host: str) -> RunnerConnection:
        conn = RunnerConnection(runner_id=runner_id, role=role, websocket=websocket, host=host)
        self._runners[runner_id] = conn
        logger.info("Runner 注册 runner=%s role=%s host=%s", runner_id, role, host)
        return conn

    def unregister(self, runner_id: str) -> None:
        if runner_id in self._runners:
            logger.info("Runner 断开 runner=%s", runner_id)
            del self._runners[runner_id]

    def get(self, runner_id: str) -> Optional[RunnerConnection]:
        return self._runners.get(runner_id)

    def list_online(self) -> list[RunnerConnection]:
        return list(self._runners.values())

    # ---- 调度 ----
    def pick_runner(self, required_role: str = "general") -> Optional[RunnerConnection]:
        """
        调度器:最少负载 + role 匹配;负载相同随机选(分片异常场景)。
        required_role="deploy" 时只选 role=deploy 的 Runner;
        required_role="general" 时可选 general(部署 Runner 不承接普通任务)。
        """
        if required_role == "deploy":
            candidates = [r for r in self._runners.values() if r.role == "deploy"]
        else:
            candidates = [r for r in self._runners.values() if r.role != "deploy"]
        if not candidates:
            return None
        min_load = min(r.load for r in candidates)
        least = [r for r in candidates if r.load == min_load]
        return random.choice(least)


# 全局单例(进程内共享;WebSocket 端点与容器服务共用)
runner_registry = RunnerRegistry()


async def send_to_runner(conn: RunnerConnection, message: dict) -> None:
    """平台 → Runner 下发 JSON 消息(并发安全)"""
    if conn.websocket is None:
        raise RuntimeError(f"Runner {conn.runner_id} websocket 未连接")
    async with conn.lock:
        await conn.websocket.send_json(message)


def build_start_container_message(
    task_id: str,
    image: str,
    env: dict,
    ports: list[int],
    repos: list[dict],
    cpu_limit: str = "2c",
    mem_limit: str = "4g",
    disk_limit: str = "10g",
) -> dict:
    """构造 start_container 指令(结构按 R8 分片契约)"""
    return {
        "type": "start_container",
        "task_id": task_id,
        "image": image,
        "env": env,
        "ports": ports,
        "cpu_limit": cpu_limit,
        "mem_limit": mem_limit,
        "disk_limit": disk_limit,
        "repos": repos,
    }


def build_stop_container_message(container_id: str) -> dict:
    return {"type": "stop_container", "container_id": container_id}
