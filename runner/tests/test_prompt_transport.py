"""
R5.F5(BUG-076) Red 测试:prompt 不应以 CLI 参数传递(超 ARG_MAX 失败)
====================================================================
根因:runner/container_manager.py 的 claude_prompt / claude_prompt_stream
把 prompt 经 shlex.quote 拼进 bash -lc 命令行,Linux ARG_MAX 单参数 ~128KB,
超长消息(用户文本 + @附件注入)直接 exec 失败。

修复方向:prompt 改走 stdin / 临时文件传递,argv 不含完整 prompt 文本。

本测试:构造 >128KB 中文 prompt,断言生成的 cmd 不包含完整 prompt 文本
(即必须走 stdin/文件)。当前实现拼 shlex.quote(prompt) → 断言失败(Red)。
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from container_manager import ContainerManager


# ---------------------------------------------------------------------------
# Fake docker client(沿用 runner/tests 既有风格)
# ---------------------------------------------------------------------------
class FakeExecResult:
    def __init__(self, code=0, output=b""):
        self.exit_code = code
        self.output = output

    def __iter__(self):
        return iter((self.exit_code, self.output))


class FakeContainer:
    def __init__(self, short_id="abc123def456"):
        self.short_id = short_id
        self.exec_calls: list[str] = []
        self.last_cmd = None

    def exec_run(self, cmd):
        # cmd 可能是 list(如 ["bash","-lc", shell_cmd])或 str
        if isinstance(cmd, list):
            self.last_cmd = " ".join(cmd)
        else:
            self.last_cmd = cmd
        self.exec_calls.append(self.last_cmd)
        # 返回空 JSON 让 claude_prompt 能解析(避免 JSONDecodeError 干扰断言)
        return FakeExecResult(0, b'{"result":"ok","total_tokens_in":1,"total_tokens_out":1}')


class FakeContainersAPI:
    def __init__(self):
        self.container = FakeContainer()

    def get(self, container_id):
        return self.container


class FakeClient:
    def __init__(self):
        self.containers = FakeContainersAPI()


# ---------------------------------------------------------------------------
# 核心 Red:prompt >128KB 不应出现在 argv / shell cmd 中
# ---------------------------------------------------------------------------
class TestPromptTransport:
    def test_long_prompt_not_in_argv_claude_prompt(self):
        """claude_prompt: >128KB 中文 prompt 不应拼进命令行(当前会拼 → Red)"""
        # 构造 >128KB 中文 prompt(每中文字符 3 字节 UTF-8;50000 字 ≈ 150KB)
        long_prompt = "测试长消息" * 50000  # 300KB 文本
        assert len(long_prompt.encode("utf-8")) > 128 * 1024

        fake = FakeClient()
        mgr = ContainerManager(client_factory=lambda: fake)

        # 调用 claude_prompt(同步方法)
        mgr.claude_prompt(
            container_id="abc123def456",
            prompt=long_prompt,
            workdir="/workspace/main",
        )

        # 断言:exec 的 shell cmd 不包含完整 prompt 文本
        # (修复后应走 stdin/文件,cmd 中只有占位符或文件路径)
        executed_cmd = fake.containers.container.last_cmd
        assert executed_cmd is not None, "应当触发了一次 exec"
        # Red 断言:完整 prompt 不应出现在命令行
        assert long_prompt not in executed_cmd, (
            "BUG-076:prompt 不应以 CLI 参数传递(超 ARG_MAX);应改走 stdin/临时文件"
        )

    def test_long_prompt_not_in_argv_claude_prompt_stream(self):
        """claude_prompt_stream: >128KB 中文 prompt 不应拼进命令行(当前会拼 → Red)"""
        long_prompt = "流式长消息验证" * 50000  # ~300KB
        assert len(long_prompt.encode("utf-8")) > 128 * 1024

        fake = FakeClient()
        mgr = ContainerManager(client_factory=lambda: fake)

        # claude_prompt_stream 需要 docker low-level API;此处只测 cmd 构造
        # 用 monkey-patch 避开真实 socket,只捕获 exec_create 的 cmd 参数
        captured_cmd = {}

        class FakeAPI:
            def exec_create(self, cid, cmd, tty=False, stdin=False):
                captured_cmd["cmd"] = cmd
                return "exec-1"

            def exec_start(self, exec_id, tty=False, socket=True, demux=False):
                # 返回立即 EOF 的假 socket,让 stream 循环结束
                class FakeSock:
                    def recv(self, n):
                        return b""
                    def read(self, n=-1):
                        return b""
                    def close(self):
                        pass
                    def makefile(self, *a, **kw):
                        import io
                        return io.BytesIO(b"")
                return FakeSock()

        # R5.F5:docker.DockerClient.api 是 low-level APIClient;直接挂到 fake.api
        fake.api = FakeAPI()

        try:
            mgr.claude_prompt_stream(
                container_id="abc123def456",
                prompt=long_prompt,
                workdir="/workspace/main",
            )
        except Exception:
            # stream 解析可能因空响应抛错,不影响 cmd 断言
            pass

        cmd = captured_cmd.get("cmd")
        assert cmd is not None, "exec_create 应被调用"
        # cmd 是 list(如 ["bash","-lc", shell_cmd]),拼成字符串检查
        cmd_str = " ".join(cmd) if isinstance(cmd, list) else cmd
        assert long_prompt not in cmd_str, (
            "BUG-076:stream 路径同样不应把 prompt 拼进命令行"
        )
