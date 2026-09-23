"""
R8 Runner 侧测试(fake docker client,不依赖真实 Docker)
==========================
- test_start_container_success:拉起容器(clone/checkout 执行;端口映射 20000-29999)
- test_stop_container_force_push:销毁前强制 push;push 失败保留容器
- test_container_event_restart:die 自动重启 ≤3 次,超过 restart_failed
- allocate_ports:范围与冲突重试
"""
import random

import pytest

from container_manager import ContainerManager, allocate_ports


class FakeExecResult:
    def __init__(self, code=0):
        self.exit_code = code
        self.output = b""

    def __iter__(self):
        # 兼容 docker SDK 的 namedtuple 用法:exit_code, output = exec_run(...)
        return iter((self.exit_code, self.output))


class FakeContainer:
    def __init__(self, short_id="abc123def456"):
        self.short_id = short_id
        self.exec_calls: list[str] = []
        self.stopped = False
        self.removed = False
        self.push_fail = False

    def exec_run(self, cmd):
        self.exec_calls.append(cmd)
        if "git push" in cmd and self.push_fail:
            return FakeExecResult(1)
        return FakeExecResult(0)

    def stop(self, timeout=10):
        self.stopped = True

    def remove(self, force=False):
        self.removed = True

    def start(self):
        self.stopped = False


class FakeContainersAPI:
    def __init__(self):
        self.run_kwargs = None
        self.container = FakeContainer()
        self._get_targets = {}

    def run(self, **kwargs):
        self.run_kwargs = kwargs
        return self.container

    def get(self, container_id):
        return self._get_targets.get(container_id, self.container)


class FakeClient:
    def __init__(self):
        self.containers = FakeContainersAPI()


# ---------------------------------------------------------------------------
# 端口分配
# ---------------------------------------------------------------------------
class TestAllocatePorts:
    def test_range_and_uniqueness(self):
        mapping = allocate_ports([5173, 8000], rng=random.Random(42))
        assert set(mapping.keys()) == {5173, 8000}
        for host_port in mapping.values():
            assert 20000 <= host_port <= 29999
        assert len(set(mapping.values())) == 2

    def test_conflict_retry(self):
        taken = set(range(20000, 20100))
        before = set(taken)
        mapping = allocate_ports([5173], rng=random.Random(1), taken=taken)
        host_port = mapping[5173]
        assert host_port not in before
        assert 20000 <= host_port <= 29999


# ---------------------------------------------------------------------------
# 启动容器
# ---------------------------------------------------------------------------
class TestStartContainer:
    def test_start_container_success(self):
        fake = FakeClient()
        mgr = ContainerManager(client_factory=lambda: fake)
        result = mgr.start_container(
            task_id="task-1",
            image="platform/devbox:v1",
            env={"GITLAB_TOKEN": "tok", "LLM_API_KEY": "sk-x"},
            ports=[5173, 8000],
            repos=[{"url": "https://gitlab.example.com/g/r.git", "path": "/workspace/r", "branch": "req-9"}],
        )
        # docker run 参数:detach/env/资源限制/labels
        kw = fake.containers.run_kwargs
        assert kw["image"] == "platform/devbox:v1"
        assert kw["detach"] is True
        assert kw["environment"]["GITLAB_TOKEN"] == "tok"
        assert kw["labels"]["qicheng.task_id"] == "task-1"
        assert set(kw["ports"].keys()) == {"5173/tcp", "8000/tcp"}
        for host_port in kw["ports"].values():
            assert 20000 <= host_port <= 29999

        # git clone + checkout(分支存在则直接 checkout)
        clone_cmds = [c for c in fake.containers.container.exec_calls if "git clone" in c]
        assert len(clone_cmds) == 1
        assert any("git checkout req-9" in c for c in fake.containers.container.exec_calls)

        # 回报结构
        assert result["container_id"] == fake.containers.container.short_id
        assert set(result["ports"].keys()) == {"5173", "8000"}

    def test_start_container_creates_branch_when_missing(self):
        """分支不存在(checkout 失败)→ 自动建新分支 git checkout -b"""

        class FailCheckoutContainer(FakeContainer):
            def exec_run(self, cmd):
                self.exec_calls.append(cmd)
                if "git checkout req-9" in cmd and "-b" not in cmd:
                    return FakeExecResult(1)  # 模拟远端分支不存在
                return FakeExecResult(0)

        fake = FakeClient()
        fake.containers.container = FailCheckoutContainer()
        mgr = ContainerManager(client_factory=lambda: fake)
        mgr.start_container(
            task_id="task-2",
            image="platform/devbox:v1",
            env={},
            ports=[5173],
            repos=[{"url": "https://gitlab.example.com/g/r.git", "path": "/workspace/r", "branch": "req-9"}],
        )
        assert any("git checkout req-9" in c for c in fake.containers.container.exec_calls)
        assert any("git checkout -b req-9" in c for c in fake.containers.container.exec_calls)


# ---------------------------------------------------------------------------
# 停止(强制 push)
# ---------------------------------------------------------------------------
class TestStopContainer:
    def test_stop_container_force_push(self):
        fake = FakeClient()
        mgr = ContainerManager(client_factory=lambda: fake)
        repos = [{"url": "https://g/r.git", "path": "/workspace/r", "branch": "req-9"}]

        ok = mgr.stop_container("abc123def456", force_push=True, repos=repos)
        assert ok is True
        assert any("git push --all origin" in c for c in fake.containers.container.exec_calls)
        assert fake.containers.container.stopped is True
        assert fake.containers.container.removed is True

    def test_stop_container_push_failure_keeps_container(self):
        """push 失败:保留容器(不 stop/rm),返回 False(平台 30 分钟后重试)"""
        fake = FakeClient()
        fake.containers.container.push_fail = True
        mgr = ContainerManager(client_factory=lambda: fake)
        repos = [{"url": "https://g/r.git", "path": "/workspace/r"}]

        ok = mgr.stop_container("abc123def456", force_push=True, repos=repos)
        assert ok is False
        assert fake.containers.container.stopped is False
        assert fake.containers.container.removed is False

    def test_stop_without_push_destroys_directly(self):
        fake = FakeClient()
        mgr = ContainerManager(client_factory=lambda: fake)
        ok = mgr.stop_container("abc123def456", force_push=False)
        assert ok is True
        assert fake.containers.container.removed is True
        assert not any("git push" in c for c in fake.containers.container.exec_calls)


# ---------------------------------------------------------------------------
# 事件监听与崩溃重启
# ---------------------------------------------------------------------------
class TestContainerEvents:
    def test_die_auto_restart_up_to_three(self):
        fake = FakeClient()
        mgr = ContainerManager(client_factory=lambda: fake)

        # 前 3 次 die → 自动重启
        for i in range(3):
            assert mgr.handle_event("die", "abc123") == "restarted"
        # 第 4 次 → restart_failed(平台标 failed)
        assert mgr.handle_event("die", "abc123") == "restart_failed"

    def test_oom_marks_failed(self):
        mgr = ContainerManager(client_factory=lambda: FakeClient())
        assert mgr.handle_event("oom", "abc123") == "restart_failed"

    def test_iter_events_filters(self):
        """iter_events 只产出容器 start/die/oom 事件"""
        fake = FakeClient()

        class FakeEvents:
            def events(self, decode=True):
                yield {"Type": "container", "Action": "die", "id": "1"}
                yield {"Type": "image", "Action": "pull", "id": "2"}  # 应被过滤
                yield {"Type": "container", "Action": "oom", "id": "3"}

        fake.events = FakeEvents().events

        mgr = ContainerManager(client_factory=lambda: fake)
        actions = [e["Action"] for e in mgr.iter_events()]
        assert actions == ["die", "oom"]


# ---------------------------------------------------------------------------
# R9.F1:claude_prompt 会话参数(cmd 拼接三分支)
# ---------------------------------------------------------------------------
class TestClaudePromptSession:
    """claude_prompt cmd 拼接:无参/session_id/resume 三分支"""

    def test_claude_prompt_no_session(self):
        """无 session 参数 → 原 cmd(兼容旧行为)"""
        fake = FakeClient()
        mgr = ContainerManager(client_factory=lambda: fake)
        # lambda 必须同时记录 cmd 到 exec_calls(原 FakeContainer.exec_run 自带记录,
        # 但覆盖后需要手动追加)
        container = fake.containers.container
        container.exec_run = lambda cmd: (
            container.exec_calls.append(cmd),
            (0, b'{"result":"ok","total_tokens_in":1,"total_tokens_out":2}'),
        )[1]

        result = mgr.claude_prompt("abc123def456", "hello world")

        # 验证 cmd 不含 --session-id 或 --resume
        exec_cmds = fake.containers.container.exec_calls
        # exec_capture 内部用 bash -lc 包装,实际 exec_run 的参数是 list
        # 找到包含 claude 的命令
        claude_cmd = None
        for cmd in exec_cmds:
            if isinstance(cmd, list):
                # bash -lc "..." 形式
                if len(cmd) >= 3 and "claude" in cmd[2]:
                    claude_cmd = cmd[2]
                    break
            elif isinstance(cmd, str) and "claude" in cmd:
                claude_cmd = cmd
                break
        assert claude_cmd is not None
        assert "--session-id" not in claude_cmd
        assert "--resume" not in claude_cmd
        assert "claude -p" in claude_cmd
        assert "--output-format json" in claude_cmd

    def test_claude_prompt_with_session_id(self):
        """session_id + resume=False → cmd 含 --session-id <sid>"""
        import uuid
        fake = FakeClient()
        mgr = ContainerManager(client_factory=lambda: fake)
        # lambda 必须同时记录 cmd 到 exec_calls
        container = fake.containers.container
        container.exec_run = lambda cmd: (
            container.exec_calls.append(cmd),
            (0, b'{"result":"ok","total_tokens_in":1,"total_tokens_out":2}'),
        )[1]

        test_sid = str(uuid.uuid4())
        result = mgr.claude_prompt("abc123def456", "hello", session_id=test_sid, resume=False)

        # 找到 claude 命令
        claude_cmd = None
        for cmd in fake.containers.container.exec_calls:
            if isinstance(cmd, list) and len(cmd) >= 3 and "claude" in cmd[2]:
                claude_cmd = cmd[2]
                break
        assert claude_cmd is not None
        assert f"--session-id {test_sid}" in claude_cmd
        assert "--resume" not in claude_cmd

    def test_claude_prompt_with_resume(self):
        """resume=True → cmd 含 --resume <sid>"""
        import uuid
        fake = FakeClient()
        mgr = ContainerManager(client_factory=lambda: fake)
        # lambda 必须同时记录 cmd 到 exec_calls
        container = fake.containers.container
        container.exec_run = lambda cmd: (
            container.exec_calls.append(cmd),
            (0, b'{"result":"ok","total_tokens_in":1,"total_tokens_out":2}'),
        )[1]

        test_sid = str(uuid.uuid4())
        result = mgr.claude_prompt("abc123def456", "hello", session_id=test_sid, resume=True)

        # 找到 claude 命令
        claude_cmd = None
        for cmd in fake.containers.container.exec_calls:
            if isinstance(cmd, list) and len(cmd) >= 3 and "claude" in cmd[2]:
                claude_cmd = cmd[2]
                break
        assert claude_cmd is not None
        assert f"--resume {test_sid}" in claude_cmd
        # resume 模式下不应有 --session-id
        assert "--session-id" not in claude_cmd
