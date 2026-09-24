"""
R9 Runner 侧 pty 管理测试(fake docker api,socketpair 真实 I/O)
==========================
- test_exec_create_pty:exec_create(tty=True)+ 输出批量回调
- test_pty_session_reuse:同 session 二次创建 → attach(False),不新建
- test_write_input_resize_kill
- R31.F1:test_host_shell_*:宿主 shell 会话(subprocess 真进程,Windows/Linux 皆可跑)
"""
import socket as py_socket
import subprocess
import sys
import threading
import time

import pytest

from terminal_manager import TerminalManager


class FakeDockerAPI:
    def __init__(self):
        self.exec_create_kwargs = None
        self.exec_ids: list[str] = []
        self.resizes: list[tuple] = []
        self._pair = py_socket.socketpair()
        self.sock_counter = 0

    def exec_create(self, container_id, cmd, tty=False, stdin=False, workdir=None):
        self.exec_create_kwargs = {
            "container_id": container_id, "cmd": cmd,
            "tty": tty, "stdin": stdin, "workdir": workdir,
        }
        exec_id = f"exec-{self.sock_counter}"
        self.exec_ids.append(exec_id)
        self.sock_counter += 1
        return exec_id

    def exec_start(self, exec_id, tty=True, socket=True, demux=False):
        # 每次新建一对:返回 master 端(docker 语义),测试端写 slave 模拟容器输出
        a, b = py_socket.socketpair()
        self._pair = (a, b)
        return FakeSocketIO(a)

    def exec_resize(self, exec_id, height=None, width=None):
        self.resizes.append((exec_id, height, width))


class FakeSocketIO:
    """docker-py SocketIO 替身:raw socket 语义(recv/sendall via _sock)"""

    def __init__(self, sock: py_socket.socket):
        self._sock = sock

    def recv(self, n: int) -> bytes:
        return self._sock.recv(n)

    def write(self, data: bytes):
        self._sock.sendall(data)

    def flush(self):
        pass

    def close(self):
        try:
            self._sock.close()
        except OSError:
            pass


@pytest.fixture
def api():
    return FakeDockerAPI()


def drain_and_collect(mgr: TerminalManager, session_id: str, out: list, stop: threading.Event):
    """从回调收集输出(测试线程)"""
    while not stop.is_set():
        if out:
            return


class TestExecPty:
    def test_exec_create_pty(self, api):
        """创建 pty:exec_create tty=True;输出经批量缓冲回调"""
        mgr = TerminalManager(docker_api_factory=lambda: api, flush_interval=0.01, flush_threshold=4)
        collected: list[str] = []

        def on_output(session_id: str, data: str):
            collected.append(data)

        created = mgr.create_pty(
            container_id="docker-x", cmd=["/bin/bash"], session_id="s-1",
            on_output=on_output, cwd="/workspace/main",
        )
        assert created is True
        assert api.exec_create_kwargs["tty"] is True
        assert api.exec_create_kwargs["stdin"] is True
        assert api.exec_create_kwargs["workdir"] == "/workspace/main"

        # 模拟容器输出:master 端可读到 b 端写入的数据
        b_end = api._pair[1]
        b_end.sendall(b"hello terminal\n")

        deadline = time.time() + 2
        while time.time() < deadline and not collected:
            time.sleep(0.01)
        assert any("hello terminal" in c for c in collected)

        mgr.kill("s-1")
        b_end.close()

    def test_pty_session_reuse(self, api):
        """同 session 二次创建 → attach(False),不新建 exec"""
        mgr = TerminalManager(docker_api_factory=lambda: api, flush_interval=0.01)
        first = mgr.create_pty("docker-x", ["/bin/bash"], "s-1", on_output=lambda s, d: None)
        second = mgr.create_pty("docker-x", ["/bin/bash"], "s-1", on_output=lambda s, d: None)
        assert first is True
        assert second is False  # 复用 attach
        assert len(api.exec_ids) == 1
        mgr.kill("s-1")

    def test_write_input_and_resize_and_kill(self, api):
        """stdin 写入 / resize / kill"""
        mgr = TerminalManager(docker_api_factory=lambda: api, flush_interval=0.01)
        mgr.create_pty("docker-x", ["/bin/bash"], "s-2", on_output=lambda s, d: None)

        b_end = api._pair[1]
        assert mgr.write_input("s-2", "echo hi\n") is True
        b_end.settimeout(1)
        received = b_end.recv(1024)
        assert received == b"echo hi\n"

        mgr.resize("s-2", 120, 40)
        assert api.resizes[-1] == ("exec-0", 40, 120)

        assert mgr.kill("s-2") is True
        assert mgr.kill("s-2") is False  # 已关闭
        b_end.close()


class TestHostShell:
    """R31.F1:宿主 shell 会话(非容器 runner 降级通道)"""

    def _shell_cmd(self) -> list:
        # 轻量真进程:打印标记后阻塞在 input(),保持 stdin 可写、进程存活
        return [sys.executable, "-c", "print('host-shell-ok', flush=True); input()"]

    def test_create_output_write_kill(self):
        mgr = TerminalManager(docker_api_factory=lambda: None, flush_interval=0.01, flush_threshold=4)
        collected: list[str] = []
        created = mgr.create_host_shell("h-1", on_output=lambda s, d: collected.append(d), shell_cmd=self._shell_cmd())
        assert created is True

        deadline = time.time() + 5
        while time.time() < deadline and not collected:
            time.sleep(0.01)
        assert any("host-shell-ok" in c for c in collected)

        # stdin 写入(不炸即通;进程阻塞在 input 消费它)
        assert mgr.write_input("h-1", "x\n") is True
        # 未知会话写入 → False
        assert mgr.write_input("h-none", "x\n") is False
        # resize 对宿主会话 no-op(无 pty,不应抛异常)
        mgr.resize("h-1", 100, 30)

        assert mgr.kill("h-1") is True
        assert mgr.kill("h-1") is False  # 已关闭
        # 进程确被终止
        time.sleep(0.2)
        assert mgr.host_sessions.get("h-1") is None

    def test_host_shell_reuse(self):
        mgr = TerminalManager(docker_api_factory=lambda: None, flush_interval=0.01)
        first = mgr.create_host_shell("h-2", on_output=lambda s, d: None, shell_cmd=self._shell_cmd())
        second = mgr.create_host_shell("h-2", on_output=lambda s, d: None, shell_cmd=self._shell_cmd())
        assert first is True
        assert second is False  # 复用 attach,不新建进程
        assert len(mgr.host_sessions) == 1
        mgr.kill("h-2")

    def test_default_shell_cmd_by_platform(self):
        # Windows=cmd.exe /K(BUG-048:无 /K 时管道 stdin 下 cmd 非交互即退),其他=bash
        cmd = TerminalManager._default_host_shell_cmd()
        if sys.platform.startswith("win"):
            assert cmd == ["cmd.exe", "/K"]
        else:
            assert cmd == ["bash"]

    def test_read_loop_supports_socketio(self):
        """BUG-050:docker SDK SocketIO(只有 .read() 无 .recv())读循环不崩且能产出输出"""
        import threading

        from terminal_manager import PtySession

        class FakeSocketIO:
            """模拟 docker-py SocketIO:file-like,只有 read()"""

            def __init__(self):
                self._sent = False

            def read(self, n):
                if self._sent:
                    return b""  # EOF → 读循环正常收尾
                self._sent = True
                return b"hello BUG050"

        mgr = TerminalManager()
        session = PtySession(
            session_id="s-bug050", container_id="c-bug050", exec_id="e-bug050",
            sock=FakeSocketIO(),
        )
        got: list[str] = []
        t = threading.Thread(
            target=mgr._read_loop, args=(session, lambda s, d: got.append(d)), daemon=True,
        )
        t.start()
        t.join(timeout=3)
        assert not t.is_alive(), "读循环卡死(未走 .read 分支)"
        assert any("hello BUG050" in d for d in got), f"输出未送达: {got}"

    def test_host_shell_alive_after_spawn(self):
        """BUG-048 回归:管道模式下默认 shell spawn 后应保持存活(不秒退 EOF)"""
        if not sys.platform.startswith("win"):
            self.skipTest("Windows 专属回归")
        mgr = TerminalManager()
        got: list[tuple[str, str]] = []
        sid = "h-alive"
        created = mgr.create_host_shell(sid, on_output=lambda s, d: got.append((s, d)))
        assert created is True
        try:
            import time as _time
            _time.sleep(2.0)  # 稍等读循环;若 cmd 秒退会触发「读取结束」+ closed
            session = mgr.host_sessions.get(sid)
            assert session is not None, "会话被读循环移除(cmd 提前退出)"
            assert session.proc.poll() is None, "cmd.exe 进程提前退出(缺 /K 回归)"
        finally:
            mgr.kill(sid)
