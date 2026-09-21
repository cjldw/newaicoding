"""
R9 Runner 侧 pty 管理测试(fake docker api,socketpair 真实 I/O)
==========================
- test_exec_create_pty:exec_create(tty=True)+ 输出批量回调
- test_pty_session_reuse:同 session 二次创建 → attach(False),不新建
- test_write_input_resize_kill
"""
import socket as py_socket
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
