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
import shutil
import socket
import sys
import threading
import time
import uuid
from typing import Any

import websockets

from container_manager import ContainerManager
from file_watcher import FileWatcher
from terminal_manager import TerminalManager

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("runner")

# R31:平台指令式停止标志(runner_shutdown 置位 → main 循环不再重连,退出进程)
_SHUTDOWN_REQUESTED = False

PLATFORM_URL = os.environ.get("PLATFORM_URL", "ws://localhost:8000/ws/runner")
RUNNER_TOKEN = os.environ.get("RUNNER_TOKEN", "")
RUNNER_ID = os.environ.get("RUNNER_ID", "runner-local")       # 仅日志标识;身份由 token 决定
RUNNER_ROLE = os.environ.get("RUNNER_ROLE", "worker")
RUNNER_HOST = os.environ.get("RUNNER_HOST", "")
HEARTBEAT_INTERVAL = 30  # 秒(D13:30s 心跳;平台 60s 未收到判 offline)
PROBE_CLAUDE_TIMEOUT = 120.0  # R5 probe_claude 整体 wait_for 上限(与平台侧 COLLECT_TIMEOUT 对齐)
# BUG-079:120 → 540 —— rd-prd 等技能用 Agent 工具启动**异步后台探索子代理**,
# 主回合 end_turn 后 CLI 等待 task-notification 期间 stream-json 零输出,
# 120s 看门狗误杀(实测探索 ~2min,Very-thorough 更长)→ 对话死循环。
# 取值:≥300s 盖过分钟级探索;<600s(平台 request_runner_stream 守卫)让
# runner 侧先 pkill 收口(error=stream_timeout),真挂死仍在 10min 内被杀
STREAM_TIMEOUT = 540.0  # R8.F6:claude_prompt_stream 单次执行上限;超时 → cancel + stream_timeout 回报
                         # 触发场景:--session-id 被容器内交互 claude 占用 + --permission-prompt-tool
                         # 下 bridge.py 阻塞 stdin → sock.recv 无限挂死(详见 hang-analysis.md)

manager = ContainerManager()
terminals = TerminalManager()
watchers = FileWatcher()

# 运行中的 repo 清单(停止容器时强制 push 需要;容器 id → repos)
running_repos: dict[str, list[dict]] = {}

# R34.F1:对话真取消 —— 执行中 exec_tool 登记(req_id → container_id,供
# exec_tool_cancel 定位容器)与已取消标记(终态回报按 error="cancelled" 结算);
# 仅登记长耗时 AI 执行工具(claude_prompt / claude_prompt_stream)
_active_execs: dict[str, str] = {}
_cancelled_execs: set[str] = set()

# R34.F3:AI 权限确认 —— 挂起确认表(confirm_id → 容器/seq/input,应答下行
# exec_tool_confirm 据此写桥接应答文件)与流式执行的确认轮询任务登记
_pending_confirms: dict[str, dict] = {}
_stream_pollers: dict[str, tuple[Any, str]] = {}  # req_id → (poller task, container_id)


async def _confirm_poller(ws: Any, req_id: str, task_id: str, container_id: str) -> None:
    """
    R34.F3:轮询容器内桥接请求日志(req.log)→ 上行 claude_confirm_request 给平台。
    通道语义:容器内桥接与 Runner 无直连,经 docker exec cat 中转(0.5s 轮询;
    实证:CLI 等待期间 stdout 静默,确认请求的唯一上行信号源就是桥接侧)。
    持续读失败(容器已销毁等)自动退出,清理由 exec_tool finally 兜底。
    """
    cursor = 0
    seen: set[int] = set()
    failures = 0
    while True:
        await asyncio.sleep(0.5)
        try:
            cursor, requests = await asyncio.to_thread(
                manager.read_new_confirm_requests, container_id, cursor)
            failures = 0
        except Exception:
            failures += 1
            if failures >= 4:
                logger.warning("确认请求轮询持续失败,退出 req_id=%s container=%s", req_id, container_id)
                return
            continue
        for req in requests:
            seq = req.get("n")
            if seq is None or seq in seen:
                continue  # 幂等护栏:cursor 推进与桥接追加竞态下不重复上行
            seen.add(seq)
            confirm_id = uuid.uuid4().hex
            _pending_confirms[confirm_id] = {
                "req_id": req_id,
                "container_id": container_id,
                "seq": seq,
                "input": req.get("input") or {},
            }
            logger.info("权限确认请求上行 req_id=%s confirm=%s tool=%s",
                        req_id, confirm_id, req.get("tool_name", ""))
            await send(ws, {
                "type": "claude_confirm_request",
                "req_id": req_id,
                "task_id": task_id,
                "confirm_id": confirm_id,
                "tool_name": req.get("tool_name", ""),
                "input": req.get("input") or {},
            })


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
    """机器信息(注册上报)。

    R16.F4(BUG-045):内存采集原用 os.sysconf(SC_PAGE_SIZE/SC_PHYS_PAGES),
    仅 Unix 存在——Windows 必 AttributeError 被吞 → mem_total_gb 恒 0;Windows
    改走 ctypes GlobalMemoryStatusEx。并按用户指令扩充 os_version/hostname/ip/
    disk/cpu_model 字段(纯标准库,双平台兼容)。
    容错约定:逐字段独立 try/except,失败字段整键不出现(绝不上报 None 值,
    也不阻塞注册);docker 版本取不到时留空串(既有行为)。
    """
    info: dict = {
        "os": py_platform.system().lower(),
        "arch": py_platform.machine(),
        "cpu_count": os.cpu_count() or 0,
    }

    # docker 版本(懒 import,与既有行为一致)
    docker_version = ""
    try:
        import docker

        docker_version = docker.from_env().version()["Version"]
    except Exception:
        pass
    info["docker_version"] = docker_version

    # R26:自报自身容器 id(容器内 HOSTNAME=短 id;docker exec_create 接受短 id)。
    # 裸跑进程(非容器)时 HOSTNAME 是主机名 → 平台侧 exec 探活失败按 6003 口径兜底。
    info["self_container_id"] = os.getenv("HOSTNAME", "")

    # 内存总量:Windows 走 GlobalMemoryStatusEx(sysconf 的 SC_* 参数仅 Unix 存在)
    try:
        if sys.platform == "win32":
            import ctypes

            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
                info["mem_total_gb"] = round(stat.ullTotalPhys / 1024**3, 1)
        else:
            info["mem_total_gb"] = round(
                os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 1024**3, 1
            )
    except Exception:
        pass

    # OS 版本(如 "Windows-11-10.0.22621-SP0";截断防超长)
    try:
        os_version = py_platform.platform()
        if os_version:
            info["os_version"] = os_version[:100]
    except Exception:
        pass

    # 主机名
    try:
        hostname = socket.gethostname()
        if hostname:
            info["hostname"] = hostname
    except Exception:
        pass

    # 本机出口 IP:UDP connect 不实际发包,仅让协议栈选路由;多网卡取默认路由出口
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            if ip:
                info["ip"] = ip
        finally:
            s.close()
    except Exception:
        pass

    # 磁盘(runner 进程工作目录所在盘:任务容器/镜像通常同盘)
    try:
        usage = shutil.disk_usage(os.getcwd())
        info["disk_total_gb"] = round(usage.total / 1024**3, 1)
        info["disk_free_gb"] = round(usage.free / 1024**3, 1)
    except Exception:
        pass

    # CPU 型号(Windows 返回族号串;为空/超长截断,取不到则不上报)
    try:
        cpu_model = (py_platform.processor() or "").strip()
        if cpu_model:
            info["cpu_model"] = cpu_model[:80]
    except Exception:
        pass

    return info


def local_container_states() -> list[dict]:
    """本地实际运行的容器列表(恢复对账用)"""
    try:
        containers = manager.client.containers.list(filters={"label": "qicheng.managed=true"})
        return [
            {
                "container_id": c.short_id,
                "status": "running" if c.status == "running" else "stopped",
                # R8.F5(BUG-055):带 task 标签,平台对账可按 task_id 收养
                # 「started 回报丢失」的容器,而非误判为未知/孤儿
                "task_id": (c.labels or {}).get("qicheng.task_id", ""),
            }
            for c in containers
        ]
    except Exception:
        logger.exception("读取本地容器列表失败(对账跳过)")
        return []


# 全部 ws 下发收敛到这一把锁:heartbeat / event_listener / port_prober /
# receive_loop 回包与两条 run_coroutine_threadsafe 线程泵(pty 输出/watcher 事件)
# 并发 send 会让 websockets 帧交错 → 服务端 RST 掉线
# (rd-fix 第 14 轮 BUG-032 根因②,13:12/13:40/13:55 三次掉线实证)
_SEND_LOCK = asyncio.Lock()


async def send(ws: Any, payload: dict) -> None:
    import json

    data = json.dumps(payload, ensure_ascii=False)
    async with _SEND_LOCK:
        await ws.send(data)


async def send_result(ws: Any, req_id: str, ok: bool, data=None, error: str = "") -> None:
    """请求-响应结算(R11 文件操作)"""
    await send(ws, {"type": "result", "req_id": req_id, "ok": ok, "data": data, "error": error})


async def safe_send_result(ws: Any, req_id: str, ok: bool, data=None, error: str = "") -> None:
    """结果回报(防炸版):连接已死时仅记日志 —— receive_loop 因回报失败而死亡会
    中断所有消息处理,连接由重连循环重建即可,不应连带炸循环(BUG-032)"""
    try:
        await send_result(ws, req_id, ok, data, error)
    except Exception:
        logger.warning("send_result 失败(连接不可用) req_id=%s", req_id)


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
                image=msg.get("image", "platform/devbox:v2"),
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
        # R31.F1:container_id="__host__" 哨兵 → 宿主 shell 会话(非容器 runner 降级通道)
        session_id = msg.get("session_id", "")
        container_id = msg.get("container_id", "")
        if container_id == "__host__":
            created = terminals.create_host_shell(
                session_id=session_id,
                on_output=_pty_output_callback(ws),
            )
        else:
            created = terminals.create_pty(
                container_id=container_id,
                cmd=msg.get("cmd") or ["/bin/bash"],
                session_id=session_id,
                on_output=_pty_output_callback(ws),
                # BUG-049/R31.F3:cwd 可由消息携带(R26 Runner 容器 shell 传 "/app",
                # 其镜像 WORKDIR);不携带时维持任务容器 /workspace/main 语义(R9)
                cwd=msg.get("cwd") or "/workspace/main",
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
        # R39:新格式(message_b64 + author_name_b64/author_email_b64)走 git_commit 方法;
        # 身份两字段同样走 base64 通道(防引号/分号命令注入,与 message 同口径);
        # 旧格式(add_path + message + branch + token)保留 R3 commit_push 兼容
        req_id = msg.get("req_id", "")
        if msg.get("message_b64") is not None:
            # R39 新通道:base64 message + base64 身份 + 空检
            try:
                data = manager.git_commit(
                    msg.get("container_id", ""),
                    msg.get("repo_path", "/workspace/main"),
                    msg.get("message_b64", ""),
                    msg.get("author_name_b64", ""),
                    msg.get("author_email_b64", ""),
                )
                await send_result(ws, req_id, True, data)
            except Exception as e:
                await send_result(ws, req_id, False, error=str(e))
        else:
            # R3 旧通道:commit + push 焊死(保留兼容)
            try:
                manager.commit_push(
                    msg.get("container_id", ""), msg.get("repo_path", "/workspace/main"),
                    msg.get("add_path", ""), msg.get("message", ""),
                    msg.get("branch", ""), msg.get("token", ""),
                )
            except Exception as e:
                logger.warning("PRD commit/push 失败: %s", e)

    elif mtype == "git_push":
        # R39:独立 push(临时注入 oauth2 remote → push → 恢复原 remote)
        req_id = msg.get("req_id", "")
        try:
            data = manager.git_push(
                msg.get("container_id", ""),
                msg.get("repo_path", "/workspace/main"),
                msg.get("branch", ""),
                msg.get("token", ""),
            )
            await send_result(ws, req_id, True, data)
        except Exception as e:
            await send_result(ws, req_id, False, error=str(e))

    elif mtype == "exec_tool":
        # R4 AI 执行(CLI 兜底):claude -p <prompt>;R32.F1:claude_inject 资产注入;R32.F3:claude_prompt_stream 流式
        req_id = msg.get("req_id", "")
        tool = msg.get("tool", "")
        args = msg.get("args") or {}
        container_id = msg.get("container_id", "")
        # R34.F1:长耗时 AI 执行登记在途(供 exec_tool_cancel 按 req_id 定位容器;
        # claude_inject 秒级完成,不登记不可取消)
        cancellable = tool in ("claude_prompt", "claude_prompt_stream")
        if cancellable:
            _active_execs[req_id] = container_id
            _cancelled_execs.discard(req_id)
            logger.info("exec_tool 在途登记 req_id=%s tool=%s container=%s", req_id, tool, container_id)
        try:
            if tool == "claude_prompt":
                # 同步 docker exec 会 minute 级堵死事件循环 → websockets ping/pong
                # 饿死(服务端杀连接)+ heartbeat 饿死(sweep_offline 注销活连接)
                # → 掉线根因①(BUG-032);移入线程池保持循环畅通
                # R9.F1:透传 session_id/resume 参数(任务级 claude 会话共用)
                data = await asyncio.to_thread(
                    manager.claude_prompt,
                    container_id, args.get("prompt", ""),
                    workdir=args.get("workdir", "/workspace/main"),
                    session_id=args.get("session_id"),
                    resume=args.get("resume", False),
                    model=args.get("model"),
                )
                # R34.F1:已取消 → 终态按 error="cancelled" 回报(平台广播 chat_done ok:false)
                if req_id in _cancelled_execs:
                    logger.info("exec_tool 已取消,按 cancelled 结算 req_id=%s", req_id)
                    await safe_send_result(ws, req_id, False, error="cancelled")
                else:
                    await safe_send_result(ws, req_id, True, data)
            elif tool == "claude_inject":
                # R32.F1:Skills/MCP 注入(同路线程池,防堵事件循环)
                data = await asyncio.to_thread(
                    manager.claude_inject,
                    msg.get("container_id", ""),
                    skills=args.get("skills") or [],
                    mcp_config=args.get("mcp_config") or {},
                )
                await safe_send_result(ws, req_id, True, data)
            elif tool == "claude_prompt_stream":
                # R32.F3:流式对话 —— 容器内 stream-json 逐行泵出,行事件直推平台
                # (claude_stream 消息,不走 result;终态仍走 result 结算 req_id)。
                # 投递复用 _MAIN_LOOP(与 pty/watcher 线程泵同路,受 _SEND_LOCK 保护)
                async def _on_line(line: str) -> None:
                    await send(ws, {
                        "type": "claude_stream",
                        "req_id": req_id,
                        "task_id": msg.get("task_id", ""),
                        "line": line,
                    })

                def _on_line_threadsafe(line: str) -> None:
                    if _MAIN_LOOP is not None:
                        fut = asyncio.run_coroutine_threadsafe(_on_line(line), _MAIN_LOOP)
                        try:
                            fut.result(timeout=10)
                        except Exception:
                            pass  # 推送失败不阻断执行(终态 result 仍兜底)

                # R34.F3:权限确认桥接注入 + 请求轮询 —— R5.F3 二修(BUG-072 第 41 轮):
                # CLI 2.1.280 下 permgate 桥机制实测失效(container_manager.perm_flag 已
                # 恒空),注入只剩副作用(permgate 白占 mcpServers、每次 headless 白拉一个
                # python3 进程),不再注入、不再起轮询;需审批工具(Bash/Edit/Write)维持
                # 静默拒绝,桥接恢复归 CLI 升级/换实现(BUG-072/R34.F3 留档)
                stream_container = msg.get("container_id", "")
                perm_ok = False

                # R8.F6:超时守卫 —— --session-id 被容器内交互 claude 占用时,
                # --permission-prompt-tool 下 bridge.py 阻塞 stdin,sock.recv 无限挂死
                # (详见 hang-analysis.md)。wait_for 兜底:超时 → pkill 容器内 claude
                # 进程树 → 按 error="stream_timeout" 回报,平台侧收到终态而非永久挂起
                data = None
                stream_timed_out = False
                try:
                    data = await asyncio.wait_for(
                        asyncio.to_thread(
                            manager.claude_prompt_stream,
                            msg.get("container_id", ""), args.get("prompt", ""),
                            workdir=args.get("workdir", "/workspace/main"),
                            session_id=args.get("session_id"),
                            resume=args.get("resume", False),
                            model=args.get("model"),
                            permission_bridge=perm_ok,
                            on_line=_on_line_threadsafe,
                        ),
                        timeout=STREAM_TIMEOUT,
                    )
                except asyncio.TimeoutError:
                    stream_timed_out = True
                    logger.warning(
                        "claude_prompt_stream 超时(%ss),杀容器内 claude req_id=%s container=%s",
                        STREAM_TIMEOUT, req_id, msg.get("container_id", ""),
                    )
                    try:
                        await asyncio.to_thread(
                            manager.cancel_claude, msg.get("container_id", ""))
                    except Exception:
                        logger.warning("超时后 cancel_claude 失败 container=%s", msg.get("container_id", ""))

                # BUG-060(R32.F8):--resume 的会话在新容器/被清理后不存在 → CLI 报错
                # 走 stderr(被 2>/dev/null 吞),stdout 零行 → 空 result。识别「带会话
                # 且零行」自动降级为无会话重跑(新会话);首趟零行,二次上泵无重复。
                # R34.F1:已取消(零行来自 pkill)不得重跑,直接按 cancelled 结算
                # R8.F6:超时路径跳过降级(已 pkill,重跑无意义)
                # R5.F3 三修(BUG-072):CLI 2.1.280 对 resume 不存在会话输出单行
                # error-result(is_error=true,非零行)——原零行判定漏掉该形态
                # (BUG-067②),resume_error=True 时同样降级,免毒化会话死循环
                if (not stream_timed_out and data is not None
                        and args.get("session_id")
                        and (data.get("lines") == 0 or data.get("resume_error"))
                        and req_id not in _cancelled_execs):
                    logger.warning(
                        "claude resume 无会话返回空,降级新会话重跑 container=%s session=%s",
                        msg.get("container_id", ""), args.get("session_id"),
                    )
                    try:
                        data = await asyncio.wait_for(
                            asyncio.to_thread(
                                manager.claude_prompt_stream,
                                msg.get("container_id", ""), args.get("prompt", ""),
                                workdir=args.get("workdir", "/workspace/main"),
                                session_id=None,
                                resume=False,
                                model=args.get("model"),
                                permission_bridge=perm_ok,
                                on_line=_on_line_threadsafe,
                            ),
                            timeout=STREAM_TIMEOUT,
                        )
                    except asyncio.TimeoutError:
                        stream_timed_out = True
                        logger.warning(
                            "claude_prompt_stream 降级重跑也超时(%ss) req_id=%s container=%s",
                            STREAM_TIMEOUT, req_id, msg.get("container_id", ""),
                        )
                        try:
                            await asyncio.to_thread(
                                manager.cancel_claude, msg.get("container_id", ""))
                        except Exception:
                            logger.warning("降级超时后 cancel_claude 失败 container=%s", msg.get("container_id", ""))

                # R8.F6:超时 → error="stream_timeout" 回报(优先级:cancelled > stream_timeout)
                if stream_timed_out and req_id not in _cancelled_execs:
                    await safe_send_result(ws, req_id, False, error="stream_timeout")
                # R34.F1:已取消 → 终态按 error="cancelled" 回报(部分行结果丢弃)
                elif req_id in _cancelled_execs:
                    logger.info("claude_prompt_stream 已取消,按 cancelled 结算 req_id=%s lines=%s",
                                req_id, (data or {}).get("lines"))
                    await safe_send_result(ws, req_id, False, error="cancelled")
                elif not stream_timed_out and data is not None:
                    await safe_send_result(ws, req_id, True, data)
            else:
                await safe_send_result(ws, req_id, False, error=f"未知工具: {tool}")
        except Exception as e:
            # R34.F1:取消路径(pkill 连带 exec 会话退出抛错)统一按 cancelled 回报
            error = "cancelled" if req_id in _cancelled_execs else str(e)
            if req_id in _cancelled_execs:
                logger.info("exec_tool 取消路径异常退出 req_id=%s: %s", req_id, e)
            await safe_send_result(ws, req_id, False, error=error)
        finally:
            if cancellable:
                _active_execs.pop(req_id, None)
                _cancelled_execs.discard(req_id)
            # R34.F3:停止确认轮询 + 清理桥接残留(仅流式路径登记;未应答挂起一并注销,
            # 平台侧由其自身超时/停止收口兜底)
            poller_entry = _stream_pollers.pop(req_id, None)
            if poller_entry is not None:
                poller_entry[0].cancel()
                for cid in [c for c, v in _pending_confirms.items() if v.get("req_id") == req_id]:
                    _pending_confirms.pop(cid, None)
                try:
                    await asyncio.to_thread(manager.cleanup_permission_bridge, poller_entry[1])
                except Exception:
                    logger.warning("权限桥接清理失败 container=%s", poller_entry[1])

    elif mtype == "probe_claude":
        # R5 系统级采集:临时容器起→探→毁单次调用内完成(同路线程池,防堵事件循环);
        # 整体 wait_for 上限 120s(与平台 COLLECT_TIMEOUT 对齐):卡死的探测及时回
        # ok=False,不让平台等满双倍窗口;线程不可强杀,probe 内部 finally 仍会销毁容器
        req_id = msg.get("req_id", "")
        try:
            data = await asyncio.wait_for(
                asyncio.to_thread(
                    manager.probe_claude,
                    image=msg.get("image", "platform/devbox:v2"),
                ),
                timeout=PROBE_CLAUDE_TIMEOUT,
            )
            await safe_send_result(ws, req_id, True, data)
        except Exception as e:
            logger.exception("probe_claude 失败(容器启动/exec 异常/超时)")
            await safe_send_result(ws, req_id, False, error=str(e))

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

    elif mtype == "runner_shutdown":
        # R31 平台指令式停止:回 result 后请求优雅退出(容器不动,由平台删除代停流程处理);
        # 置标志 → _receive_loop 返回 → session 结束 → main 循环检测到标志即退出进程(不重连)
        req_id = msg.get("req_id", "")
        global _SHUTDOWN_REQUESTED
        _SHUTDOWN_REQUESTED = True
        await safe_send_result(ws, req_id, True, {})
        logger.info("收到 runner_shutdown,回报后退出进程")

    elif mtype == "exec_tool_cancel":
        # R34.F1:对话真取消 —— 按 req_id 定位执行中容器,docker exec pkill 容器内
        # claude → 执行线程随 exec socket EOF 退出 → exec_tool 终态按
        # ok=False(error="cancelled")回报,平台据此广播 chat_done ok:false。
        # 本指令火后不理(不回 result):终态经原 req_id 的 result 结算,若在此
        # 抢先回包会与原请求终态撞 req_id,提前结算流式等待队列。
        # pkill 走线程池(同步 docker exec,防堵事件循环,同 BUG-032 口径)
        target = msg.get("req_id", "")
        target_container = _active_execs.get(target)
        logger.info("收到 exec_tool_cancel req_id=%s container=%s", target, target_container or "无在途执行")
        if target_container is not None:
            _cancelled_execs.add(target)
            try:
                await asyncio.to_thread(manager.cancel_claude, target_container)
            except Exception:
                # 容器已销毁等场景:pkill 失败仅记日志;执行线程仍由平台超时兜底收敛
                logger.exception("exec_tool_cancel 执行失败 req_id=%s container=%s", target, target_container)

    elif mtype == "exec_tool_confirm":
        # R34.F3:平台确认应答下行(用户允许/拒绝)→ 写桥接应答文件 ans-{seq}.json,
        # 桥接轮询读到后回 MCP 应答放行/拒绝,容器内 claude 继续执行。
        # 未知 confirm_id(桥接已超时自拒/Runner 重启丢表)仅告警,不回包。
        confirm_id = msg.get("confirm_id", "")
        choice = msg.get("choice", "deny")
        info = _pending_confirms.pop(confirm_id, None)
        logger.info("收到确认应答 confirm=%s choice=%s 命中挂起=%s", confirm_id, choice, info is not None)
        if info is not None:
            if choice == "allow":
                # allow 必须回传 updatedInput(实证:CLI 用它实际执行),原样回传请求 input
                decision = {"behavior": "allow", "updatedInput": info.get("input") or {}}
            else:
                decision = {"behavior": "deny", "message": "用户拒绝了本次工具调用", "interrupt": False}
            try:
                await asyncio.to_thread(
                    manager.write_confirm_answer,
                    info.get("container_id", ""), info.get("seq"), decision)
            except Exception:
                logger.exception("确认应答写入失败 confirm=%s container=%s",
                                 confirm_id, info.get("container_id"))

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
        if _SHUTDOWN_REQUESTED:
            # R31:处理完 runner_shutdown(已回 result)→ 返回结束 receive 任务
            # → session 的 asyncio.wait 完成 → main 检测标志退出进程
            return


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
        if _SHUTDOWN_REQUESTED:
            # R31:平台指令停止 → 不再重连,退出进程
            logger.info("检测到 runner_shutdown,退出进程")
            break
        try:
            logger.info("连接平台 %s", PLATFORM_URL)
            await session()
            backoff = 1
        except Exception as e:
            logger.warning("连接断开: %s(%ds 后重连)", e, backoff)
        if _SHUTDOWN_REQUESTED:
            logger.info("检测到 runner_shutdown,退出进程")
            break
        await asyncio.sleep(backoff)
        backoff = min(backoff * 2, 60)


if __name__ == "__main__":
    asyncio.run(main())
