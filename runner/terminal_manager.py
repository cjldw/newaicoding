"""Runner pty 管理 - R9(docker exec tty;docker 低层 API 可注入便于测试)

- create_pty(container_id, cmd, session_id):exec_create(tty=True, stdin=True)
  + exec_start(socket=True) → 后台线程批量读输出(50ms 或 8KB)→ 回调
- write_input(session_id, data):写 pty stdin
- resize(session_id, cols, rows):exec_resize
- kill(session_id):关 socket
- attach 复用:同 session_id 已有 pty 直接返回(断线重连不丢 shell 状态)
"""

import logging
import socket as py_socket
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

# 输出批量缓冲:每 50ms 或每 8KB 推一次(R9 分片)
FLUSH_INTERVAL_SECONDS = 0.05
FLUSH_THRESHOLD_BYTES = 8 * 1024


@dataclass
class PtySession:
    session_id: str
    container_id: str
    exec_id: str
    sock: Any                       # docker-py SocketIO(exec_start socket=True)
    thread: Optional[threading.Thread] = None
    closed: bool = False
    buffer: bytearray = field(default_factory=bytearray)
    buffer_lock: threading.Lock = field(default_factory=threading.Lock)


class TerminalManager:
    """pty 会话管理(docker_api 可注入;测试传 fake)"""

    def __init__(
        self,
        docker_api_factory: Optional[Callable[[], Any]] = None,
        flush_interval: float = FLUSH_INTERVAL_SECONDS,
        flush_threshold: int = FLUSH_THRESHOLD_BYTES,
    ) -> None:
        self._docker_api_factory = docker_api_factory or self._default_api_factory
        self.flush_interval = flush_interval
        self.flush_threshold = flush_threshold
        self.sessions: dict[str, PtySession] = {}

    @staticmethod
    def _default_api_factory() -> Any:
        import docker

        return docker.from_env().api

    @property
    def api(self) -> Any:
        if not hasattr(self, "_api"):
            self._api = self._docker_api_factory()
        return self._api

    # -----------------------------------------------------------------
    def create_pty(
        self,
        container_id: str,
        cmd: list[str],
        session_id: str,
        on_output: Callable[[str, str], None],
        cwd: str = "/workspace/main",
    ) -> bool:
        """
        创建 pty;session 已存在则 attach 复用(返回 False 表示复用而非新建)。
        on_output(session_id, data):输出回调(已批量缓冲,Runner 主进程转发平台)。
        """
        existing = self.sessions.get(session_id)
        if existing is not None and not existing.closed:
            # pty 会话复用:attach 而非新建(shell 历史不丢)
            logger.info("pty 会话复用 attach session=%s", session_id)
            return False

        exec_id = self.api.exec_create(
            container_id, cmd, tty=True, stdin=True, workdir=cwd or None,
        )
        sock = self.api.exec_start(exec_id, tty=True, socket=True, demux=False)

        session = PtySession(session_id=session_id, container_id=container_id,
                             exec_id=exec_id, sock=sock)
        self.sessions[session_id] = session

        thread = threading.Thread(
            target=self._read_loop, args=(session, on_output), daemon=True,
        )
        session.thread = thread
        thread.start()
        logger.info("pty 已创建 session=%s container=%s", session_id, container_id)
        return True

    def _read_loop(self, session: PtySession, on_output: Callable[[str, str], None]) -> None:
        """读 pty 输出 → 批量缓冲(50ms / 8KB)→ 回调"""
        last_flush = time.monotonic()

        def flush(force: bool = False) -> None:
            with session.buffer_lock:
                if not session.buffer:
                    return
                elapsed = time.monotonic() - last_flush
                if not force and len(session.buffer) < self.flush_threshold and elapsed < self.flush_interval:
                    return
                data = bytes(session.buffer)
                session.buffer.clear()
            last_flush_marker = time.monotonic()
            try:
                on_output(session.session_id, data.decode("utf-8", errors="replace"))
            except Exception:
                logger.exception("pty 输出回调异常 session=%s", session.session_id)
            _ = last_flush_marker  # noqa: B018 — 保持可读性

        while not session.closed:
            try:
                chunk = session.sock.recv(4096)
            except (OSError, ValueError):
                break
            if not chunk:
                break
            with session.buffer_lock:
                session.buffer.extend(chunk)
            flush()
            # 间隔控制:缓冲未满时短暂 sleep 等待聚合
            time.sleep(self.flush_interval / 4)

        flush(force=True)
        session.closed = True
        self.sessions.pop(session.session_id, None)
        logger.info("pty 读取结束 session=%s", session.session_id)

    # -----------------------------------------------------------------
    def write_input(self, session_id: str, data: str) -> bool:
        """写 pty stdin"""
        session = self.sessions.get(session_id)
        if session is None or session.closed:
            return False
        try:
            sock = session.sock
            raw = getattr(sock, "_sock", sock)
            # 写路径探测:Windows docker 返回 NpipeSocket —— 它不是 socket.socket
            # 子类(hasattr sendall=True / write=False),用 isinstance(socket.socket)
            # 判断会落到 write+flush 分支并抛 AttributeError,导致终端键盘输入
            # 全部丢失(输出 recv 不受影响,故表现为"看得见回显打不了字")。
            # 统一改为:有 sendall 就用 sendall(NpipeSocket 与 raw socket 皆支持),
            # 仅无 sendall 的类文件对象(SocketIO 场景)才回退 write+flush。
            sendall = getattr(raw, "sendall", None)
            if sendall is not None:
                sendall(data.encode("utf-8"))
                return True
            # 类文件对象回退路径
            sock.write(data.encode("utf-8"))
            sock.flush()
            return True
        except Exception:
            # 带 traceback 记录(原 warning 吞栈,同类问题无从排查)
            logger.exception("pty 写入失败 session=%s", session_id)
            return False

    def resize(self, session_id: str, cols: int, rows: int) -> None:
        session = self.sessions.get(session_id)
        if session is None:
            return
        try:
            self.api.exec_resize(session.exec_id, height=rows, width=cols)
        except Exception:
            logger.warning("pty resize 失败 session=%s", session_id)

    def kill(self, session_id: str) -> bool:
        """关闭 pty(关闭 Tab / 会话关闭)"""
        session = self.sessions.get(session_id)
        if session is None:
            return False
        session.closed = True
        try:
            # 与 write_input 同理:NpipeSocket 有 shutdown 但不是 socket.socket 子类,
            # isinstance 判断会跳过 shutdown;改为探测式调用(close 兜底)
            sock = getattr(session.sock, "_sock", session.sock)
            shutdown = getattr(sock, "shutdown", None)
            if shutdown is not None:
                shutdown(py_socket.SHUT_RDWR)
            sock.close()
        except Exception:
            pass
        self.sessions.pop(session_id, None)
        logger.info("pty 已关闭 session=%s", session_id)
        return True
