"""Runner 主进程 - R8/R16(WebSocket 客户端,连接平台)

启动:
    PLATFORM_URL=wss://platform.example.com/ws/runner \
    RUNNER_TOKEN=plt-runner-xxx \
    RUNNER_ID=runner-01 \
    RUNNER_ROLE=worker \
    RUNNER_HOST=1.2.3.4 \
    python3 main.py

协议(R16):
- register:{type, token, machine_info, host} → register_success(runner_id)
- heartbeat:{type, timestamp}(30s;平台 >5min 漂移拒绝、60s 无心跳判 offline)
- sync:连接后上报本地容器列表,平台对账(状态以 Runner 为准)
- start_container / stop_container 指令处理;Docker events 回报
- 断线自动重连(指数退避)
"""

import asyncio
import logging
import os
import platform as py_platform
import queue
import threading
import time
from typing import Any

import websockets

from container_manager import ContainerManager
from file_watcher import FileWatcher
from terminal_manager import TerminalManager

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("runner")

PLATFORM_URL = os.environ.get("PLATFORM_URL", "ws://localhost:8000/ws/runner")
RUNNER_TOKEN = os.environ.get("RUNNER_TOKEN", "")
RUNNER_ID = os.environ.get("RUNNER_ID", "runner-local")       # 仅日志标识;身份由 token 决定
RUNNER_ROLE = os.environ.get("RUNNER_ROLE", "worker")
RUNNER_HOST = os.environ.get("RUNNER_HOST", "")
HEARTBEAT_INTERVAL = 30  # 秒(D13:30s 心跳;平台 60s 未收到判 offline)

manager = ContainerManager()
terminals = TerminalManager()
watchers = FileWatcher()

# 运行中的 repo 清单(停止容器时强制 push 需要;容器 id → repos)
running_repos: dict[str, list[dict]] = {}


def _pty_output_callback(ws: Any):
    """pty 输出回调(读线程上下文)→ 线程安全投递主事件循环 → 转发平台"""

    async def _send(session_id: str, data: str):
        await send(ws, {"type": "terminal_output", "session_id": session_id, "data": data})

    def callback(session_id: str, data: str):
        if _MAIN_LOOP is not None:
            asyncio.run_coroutine_threadsafe(_send(session_id, data), _MAIN_LOOP)

    return callback


_MAIN_LOOP: Any = None  # main() 里赋值(主事件循环,供 pty 线程投递)


def collect_machine_info() -> dict:
    """机器信息(注册上报;docker 版本取不到时留空)"""
    docker_version = ""
    try:
        import docker

        docker_version = docker.from_env().version()["Version"]
    except Exception:
        pass
    try:
        mem_gb = round(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 1024**3, 1)
    except (AttributeError, ValueError, OSError):
        mem_gb = 0
    return {
        "os": py_platform.system().lower(),
        "arch": py_platform.machine(),
        "cpu_count": os.cpu_count() or 0,
        "mem_total_gb": mem_gb,
        "docker_version": docker_version,
    }


def local_container_states() -> list[dict]:
    """本地实际运行的容器列表(恢复对账用)"""
    try:
        containers = manager.client.containers.list(filters={"label": "qicheng.managed=true"})
        return [
            {"container_id": c.short_id, "status": "running" if c.status == "running" else "stopped"}
            for c in containers
        ]
    except Exception:
        logger.exception("读取本地容器列表失败(对账跳过)")
        return []


async def send(ws: Any, payload: dict) -> None:
    import json

    await ws.send(json.dumps(payload, ensure_ascii=False))


async def send_result(ws: Any, req_id: str, ok: bool, data=None, error: str = "") -> None:
    """请求-响应结算(R11 文件操作)"""
    await send(ws, {"type": "result", "req_id": req_id, "ok": ok, "data": data, "error": error})


def _watcher_event_callback(ws: Any):
    """watcher 事件 → 转发平台(R11)"""

    def callback(task_id: str, kind: str, path: str):
        if _MAIN_LOOP is not None:
            asyncio.run_coroutine_threadsafe(
                send(ws, {"type": kind, "task_id": task_id, "path": path}), _MAIN_LOOP
            )

    return callback


async def handle_message(ws: Any, msg: dict) -> None:
    """处理平台指令"""
    mtype = msg.get("type")

    if mtype == "start_container":
        task_id = msg.get("task_id", "")
        try:
            result = manager.start_container(
                task_id=task_id,
                image=msg.get("image", "platform/devbox:v1"),
                env=msg.get("env") or {},
                ports=msg.get("ports") or [5173, 8000],
                repos=msg.get("repos") or [],
                cpu_limit=msg.get("cpu_limit", "2c"),
                mem_limit=msg.get("mem_limit", "4g"),
                disk_limit=msg.get("disk_limit", "10g"),
            )
            running_repos[result["container_id"]] = msg.get("repos") or []
            register_probe(result["container_id"], result["ports"])
            # R11:启动文件 watcher(AI/人修改 → 平台 → 编辑器实时刷新)
            watchers.start(result["container_id"], task_id, manager, _watcher_event_callback(ws))
            await send(ws, {
                "type": "container_started",
                "task_id": task_id,
                "container_id": result["container_id"],
                "ports": result["ports"],
            })
        except Exception as e:
            logger.exception("start_container 失败 task=%s", task_id)
            await send(ws, {"type": "container_event", "event": "start_failed", "task_id": task_id, "error": str(e)})

    elif mtype == "stop_container":
        container_id = msg.get("container_id", "")
        repos = running_repos.pop(container_id, [])
        unregister_probe(container_id)
        watchers.stop(container_id)
        push_ok = manager.stop_container(container_id, force_push=True, repos=repos)
        if push_ok:
            await send(ws, {"type": "container_stopped", "container_id": container_id})
        else:
            # push 失败:容器保留 30 分钟,平台重试(分片异常场景)
            await send(ws, {"type": "container_event", "event": "push_failed_keepalive", "container_id": container_id})

    elif mtype == "exec":
        # R9 终端:docker exec 新 pty(session 复用 = attach)
        session_id = msg.get("session_id", "")
        created = terminals.create_pty(
            container_id=msg.get("container_id", ""),
            cmd=msg.get("cmd") or ["/bin/bash"],
            session_id=session_id,
            on_output=_pty_output_callback(ws),
        )
        await send(ws, {"type": "exec_started", "session_id": session_id, "created": created})

    elif mtype == "terminal_input":
        terminals.write_input(msg.get("session_id", ""), msg.get("data", ""))

    elif mtype == "terminal_resize":
        terminals.resize(msg.get("session_id", ""), int(msg.get("cols", 80)), int(msg.get("rows", 24)))

    elif mtype == "terminal_close":
        session_id = msg.get("session_id", "")
        terminals.kill(session_id)
        await send(ws, {"type": "exec_closed", "session_id": session_id})

    elif mtype in ("file_list", "read_file", "write_file", "file_op", "git_diff", "git_changes"):
        # R11 容器文件操作(带 req_id 的请求-响应)
        req_id = msg.get("req_id", "")
        container_id = msg.get("container_id", "")
        try:
            if mtype == "file_list":
                data = {"items": manager.list_dir(container_id, msg.get("path", "/workspace/main"))}
            elif mtype == "read_file":
                data = {"content": manager.read_file(container_id, msg.get("path", ""))}
            elif mtype == "write_file":
                manager.write_file(container_id, msg.get("path", ""), msg.get("content", ""))
                data = {}
            elif mtype == "file_op":
                manager.file_op(
                    container_id, msg.get("operation", ""),
                    msg.get("path", ""), msg.get("new_path"),
                    base_branch=msg.get("base_branch", "master"),
                )
                data = {}
            elif mtype == "git_diff":
                data = {"files": manager.git_diff(
                    container_id, msg.get("repo_path", "/workspace/main"),
                    msg.get("base_branch", ""))}
            else:  # git_changes
                data = {"files": manager.git_changes(
                    container_id, msg.get("repo_path", "/workspace/main"),
                    msg.get("base_branch", "master"))}
            await send_result(ws, req_id, True, data)
        except Exception as e:
            await send_result(ws, req_id, False, error=str(e))

    elif mtype in ("git_merge", "deploy_run"):
        # R7 发布执行(merge / 部署脚本+健康检查)
        req_id = msg.get("req_id", "")
        try:
            if mtype == "git_merge":
                manager.merge_branch(
                    msg.get("container_id", ""), msg.get("repo_path", "/workspace/main"),
                    msg.get("source_branch", ""), msg.get("target_branch", "master"),
                )
                await send_result(ws, req_id, True, {})
            else:
                data = manager.run_deploy(
                    msg.get("container_id", ""), msg.get("script", ""),
                    int(msg.get("health_port", 0)), msg.get("health_path", "/"),
                )
                await send_result(ws, req_id, True, data)
        except Exception as e:
            await send_result(ws, req_id, False, error=str(e))

    elif mtype == "git_commit":
        # R3 评审通过:PRD commit + push(评审人个人 token)
        try:
            manager.commit_push(
                msg.get("container_id", ""), msg.get("repo_path", "/workspace/main"),
                msg.get("add_path", ""), msg.get("message", ""),
                msg.get("branch", ""), msg.get("token", ""),
            )
        except Exception as e:
            logger.warning("PRD commit/push 失败: %s", e)

    elif mtype == "exec_tool":
        # R4 AI 执行(CLI 兜底):claude -p <prompt>
        req_id = msg.get("req_id", "")
        tool = msg.get("tool", "")
        args = msg.get("args") or {}
        try:
            if tool == "claude_prompt":
                data = manager.claude_prompt(
                    msg.get("container_id", ""), args.get("prompt", ""),
                    workdir=args.get("workdir", "/workspace/main"),
                )
                await send_result(ws, req_id, True, data)
            else:
                await send_result(ws, req_id, False, error=f"未知工具: {tool}")
        except Exception as e:
            await send_result(ws, req_id, False, error=str(e))

    elif mtype == "write_file_b64":
        # R4 附件写入(base64 字节流)
        req_id = msg.get("req_id", "")
        try:
            import base64

            manager.write_file(
                msg.get("container_id", ""), msg.get("path", ""),
                base64.b64decode(msg.get("content_b64", "")).decode("utf-8", errors="replace"),
            )
            await send_result(ws, req_id, True, {})
        except Exception as e:
            await send_result(ws, req_id, False, error=str(e))

    elif mtype == "read_file_b64":
        # R4 附件下载(base64 字节流)
        req_id = msg.get("req_id", "")
        try:
            import base64

            raw = manager.read_file_bytes(msg.get("container_id", ""), msg.get("path", ""))
            await send_result(ws, req_id, True, {"content_b64": base64.b64encode(raw).decode("ascii")})
        except Exception as e:
            await send_result(ws, req_id, False, error=str(e))

    else:
        logger.warning("未知指令 type=%s", mtype)


async def heartbeat(ws: Any) -> None:
    while True:
        await asyncio.sleep(HEARTBEAT_INTERVAL)
        try:
            await send(ws, {"type": "heartbeat", "timestamp": time.time()})
        except Exception:
            return


async def port_prober(ws: Any) -> None:
    """
    R10 端口探测:每 3s 对运行中容器的映射端口做 TCP 连接探测,
    监听 → port_listening;关闭 → port_closed(平台注册/摘除预览路由)。
    """
    probe_state: dict[tuple[str, int], bool] = {}  # (container_id, 容器端口) → 上次是否监听

    while True:
        await asyncio.sleep(3)
        for container_id, info in list(running_probes.items()):
            for container_port, host_port in info["ports"].items():
                listening = _probe_port(host_port)
                key = (container_id, container_port)
                last = probe_state.get(key)
                if listening and last is not True:
                    await send(ws, {"type": "port_listening", "container_id": container_id, "port": container_port})
                elif not listening and last is True:
                    await send(ws, {"type": "port_closed", "container_id": container_id, "port": container_port})
                probe_state[key] = listening


def _probe_port(host_port: int, timeout: float = 0.5) -> bool:
    """TCP 探测宿主机端口是否有监听"""
    import socket

    if not host_port:
        return False
    try:
        with socket.create_connection(("127.0.0.1", host_port), timeout=timeout):
            return True
    except OSError:
        return False


# 运行中容器的探测信息(容器 id → {容器端口: 宿主机端口});start 成功时登记
running_probes: dict[str, dict[str, dict[int, int]]] = {}


def register_probe(container_id: str, ports: dict[str, int]) -> None:
    """start_container 成功后登记探测端口(容器端口 → 宿主机端口)"""
    running_probes[container_id] = {"ports": {int(k): v for k, v in ports.items()}}


def unregister_probe(container_id: str) -> None:
    running_probes.pop(container_id, None)


async def event_listener(ws: Any) -> None:
    """Docker events → 回报平台(die 时 manager 内先自动重启 ≤3 次)

    BUG-027:
    - 同步 events 流改在独立线程泵送(原在协程内阻塞迭代,饿死事件循环 → 心跳停摆被平台判 offline)
    - 只处理平台容器(label qicheng.managed=true);宿主机上无关容器不接管不回报
    """
    events_q: queue.Queue = queue.Queue()

    def _pump() -> None:
        try:
            for ev in manager.iter_events():
                events_q.put(ev)
        except Exception:
            # Docker daemon 挂了:上报平台,平台标记 offline 不再调度(R16)
            logger.exception("Docker events 监听异常")

    threading.Thread(target=_pump, daemon=True, name="docker-events").start()

    while True:
        while events_q.empty():
            await asyncio.sleep(0.2)
        event = events_q.get_nowait()
        action = event.get("Action")
        attrs = (event.get("Actor") or {}).get("Attributes") or {}
        if attrs.get("qicheng.managed") != "true":
            continue
        container_id = (attrs.get("name") or event.get("id") or "")[:12]
        exit_code = attrs.get("exitCode")
        if action == "die":
            outcome = manager.handle_event("die", event.get("id", ""), exit_code)
            if outcome == "restarted":
                await send(ws, {"type": "container_event", "event": "restarted", "container_id": container_id})
                continue
            await send(ws, {
                "type": "container_event",
                "event": "die",
                "container_id": container_id,
                "exit_code": exit_code,
            })
        else:
            await send(ws, {"type": "container_event", "event": action, "container_id": container_id})


async def _receive_loop(ws: Any) -> None:
    async for raw in ws:
        import json

        try:
            await handle_message(ws, json.loads(raw))
        except Exception:
            logger.exception("处理消息失败: %s", raw[:200])


async def session() -> None:
    """单次连接会话:register(token+machine_info) → sync 对账 → 并发(收消息/心跳/事件)"""
    url = f"{PLATFORM_URL}"
    async with websockets.connect(url) as ws:
        await send(ws, {
            "type": "register",
            "token": RUNNER_TOKEN,
            "machine_info": collect_machine_info(),
            "host": RUNNER_HOST,
        })
        import json

        ack = json.loads(await ws.recv())
        if ack.get("type") != "register_success":
            raise RuntimeError(f"注册被拒绝: {ack}")
        logger.info("注册成功 runner_id=%s", ack.get("runner_id"))

        # 恢复对账:上报本地实际容器(R16)
        states = local_container_states()
        if states:
            await send(ws, {"type": "sync", "containers": states})

        receive_task = asyncio.create_task(_receive_loop(ws))
        beat_task = asyncio.create_task(heartbeat(ws))
        event_task = asyncio.create_task(event_listener(ws))
        probe_task = asyncio.create_task(port_prober(ws))
        done, pending = await asyncio.wait(
            {receive_task, beat_task, event_task, probe_task}, return_when=asyncio.FIRST_COMPLETED
        )
        for task in pending:
            task.cancel()


async def main() -> None:
    global _MAIN_LOOP
    _MAIN_LOOP = asyncio.get_running_loop()
    backoff = 1
    while True:
        try:
            logger.info("连接平台 %s", PLATFORM_URL)
            await session()
            backoff = 1
        except Exception as e:
            logger.warning("连接断开: %s(%ds 后重连)", e, backoff)
        await asyncio.sleep(backoff)
        backoff = min(backoff * 2, 60)


if __name__ == "__main__":
    asyncio.run(main())
