"""Runner pty 管理 - R9(docker exec tty;docker 低层 API 可注入便于测试)

- create_pty(container_id, cmd, session_id):exec_create(tty=True, stdin=True)
  + exec_start(socket=True) → 后台线程批量读输出(50ms 或 8KB)→ 回调
- write_input(session_id, data):写 pty stdin
- resize(session_id, cols, rows):exec_resize
- kill(session_id):关 socket
- attach 复用:同 session_id 已有 pty 直接返回(断线重连不丢 shell 状态)
- R31.F1:create_host_shell —— 非容器 runner(R31 本机裸跑)的宿主 shell 会话
  (subprocess 管道模式;Windows=cmd.exe / Linux=bash;无 pty,resize no-op)
"""

import logging
import socket as py_socket
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

# 输出批量缓冲:每 50ms 或每 8KB 推一次(R9 分片)
FLUSH_INTERVAL_SECONDS = 0.05
FLUSH_THRESHOLD_BYTES = 8 * 1024

# R31.F1:平台→runner 的宿主 shell 哨兵 container_id( runners.py 空串分支使用)
HOST_CONTAINER_SENTINEL = "__host__"


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


@dataclass
class HostSession:
    """宿主 shell 会话(R31.F1):subprocess 管道模式,无 pty"""
    session_id: str
    proc: subprocess.Popen
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
        self.host_sessions: dict[str, HostSession] = {}  # R31.F1

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
                # BUG-050:docker exec_start(socket=True) 在标准 Linux/Docker Desktop 返回
                # SocketIO(file-like,只有 .read()),Windows 原生 NpipeSocket 才有 .recv()——
                # 探测式选择读法(与 write_input 的 sendall 探测同思路,BUG-031 先例);
                # 此前硬编码 .recv() 导致容器形态 runner 的终端读循环秒崩(AttributeError)
                if hasattr(session.sock, "recv"):
                    chunk = session.sock.recv(4096)
                else:
                    chunk = session.sock.read(4096)
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
    # R31.F1:宿主 shell 会话(非容器 runner 的降级终端通道)
    # -----------------------------------------------------------------
    @staticmethod
    def _default_host_shell_cmd() -> list[str]:
        # Windows 无 pty,管道模式 cmd.exe;Linux/macOS 用 bash
        # BUG-048(rd-fix 第 25 轮):裸 `cmd.exe` 检测到 stdin=管道时进入非交互模式,
        # 执行完缓冲命令即退出 → 读循环秒 EOF(「宿主 shell 读取结束」)→ 终端零输出;
        # `/K` 强制保持交互(执行初始命令后不退出),管道下常驻等输入
        return ["cmd.exe", "/K"] if sys.platform.startswith("win") else ["bash"]

    def create_host_shell(
        self,
        session_id: str,
        on_output: Callable[[str, str], None],
        shell_cmd: Optional[list[str]] = None,
    ) -> bool:
        """
        创建宿主 shell 会话(subprocess 管道模式;shell_cmd 可注入便于测试)。
        session 已存在则 attach 复用(返回 False,与 create_pty 同语义)。
        已知降级:无 pty → resize 无效/交互式程序体验打折(排障够用)。
        """
        existing = self.host_sessions.get(session_id)
        if existing is not None and not existing.closed:
            logger.info("宿主 shell 会话复用 attach session=%s", session_id)
            return False

        cmd = shell_cmd or self._default_host_shell_cmd()
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        session = HostSession(session_id=session_id, proc=proc)
        self.host_sessions[session_id] = session

        thread = threading.Thread(
            target=self._host_read_loop, args=(session, on_output), daemon=True,
        )
        session.thread = thread
        thread.start()
        logger.info("宿主 shell 已创建 session=%s cmd=%s", session_id, cmd)
        return True

    def _host_read_loop(self, session: HostSession, on_output: Callable[[str, str], None]) -> None:
        """读宿主进程 stdout → 批量缓冲(与 pty 同款 50ms/8KB)→ 回调"""
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
            try:
                on_output(session.session_id, data.decode("utf-8", errors="replace"))
            except Exception:
                logger.exception("宿主 shell 输出回调异常 session=%s", session.session_id)

        while not session.closed:
            try:
                # read1 而非 read:read(size) 会阻塞凑满 size 或 EOF,终端输出
                # 会被憋住(短输出场景 5s 内读不到);read1 单缓冲即返
                chunk = session.proc.stdout.read1(4096)
            except (OSError, ValueError):
                break
            if not chunk:
                break  # 进程退出/管道关闭
            with session.buffer_lock:
                session.buffer.extend(chunk)
            flush()

        flush(force=True)
        session.closed = True
        self.host_sessions.pop(session.session_id, None)
        logger.info("宿主 shell 读取结束 session=%s", session.session_id)

    # -----------------------------------------------------------------
    def write_input(self, session_id: str, data: str) -> bool:
        """写 pty stdin(宿主会话分流:写进程 stdin)"""
        # R31.F1:宿主会话优先分流(docker pty 与宿主 shell 两张表)
        host = self.host_sessions.get(session_id)
        if host is not None and not host.closed:
            try:
                # BUG-048:管道模式无 pty,行尾仿真需自行完成——xterm Enter 发裸 \r,
                # 而 cmd.exe 管道下只认 \r\n(裸 \r 滞留不执行,表现为"敲了没反应");
                # 归一化(\r\n→\n→\r→\n→\r\n)幂等,不重复扩行尾
                normalized = (
                    data.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\r\n")
                )
                host.proc.stdin.write(normalized.encode("utf-8"))
                host.proc.stdin.flush()
                return True
            except Exception:
                logger.exception("宿主 shell 写入失败 session=%s", session_id)
                return False
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
        """关闭 pty(关闭 Tab / 会话关闭);宿主会话分流为杀进程"""
        # R31.F1:宿主会话分流
        host = self.host_sessions.pop(session_id, None)
        if host is not None and not host.closed:
            host.closed = True
            try:
                host.proc.kill()
            except Exception:
                pass
            logger.info("宿主 shell 已关闭 session=%s", session_id)
            return True
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
