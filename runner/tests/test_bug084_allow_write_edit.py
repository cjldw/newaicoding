"""
BUG-084(R8.F8)Red 测试:headless 对话 --allowedTools 必须放开 Write/Edit
====================================================================
根因:allowedTools 仅白名单 MCP 工具,Write/Edit/Bash 走 headless 默认静默
拒绝(R5.F3 摘除 permgate 后无审批通道)→ rd-prd 把 PRD.md 写到配置路径全凭
AI 恰好选用 filesystem MCP(10-08 偶然成功一次;10-09 两次 finish 容器内均无
文件,prd_content 回填落空)。

修复契约:流式命令的 --allowedTools 含 Write 与 Edit(Bash 不放开——终端交互
链路本就是人工审批面)。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from container_manager import ContainerManager
from test_prompt_transport import FakeClient


class TestAllowWriteEdit:
    def test_stream_allowed_tools_contains_write_edit(self):
        """流式命令 --allowedTools 应含 Write 与 Edit"""
        fake = FakeClient()
        mgr = ContainerManager(client_factory=lambda: fake)

        captured = {}

        class FakeAPI:
            def exec_create(self, cid, cmd, tty=False, stdin=False):
                captured["cmd"] = cmd
                return "exec-1"

            def exec_start(self, exec_id, tty=False, socket=True, demux=False):
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

        fake.api = FakeAPI()

        try:
            mgr.claude_prompt_stream(
                container_id="abc123def456",
                prompt="普通消息",
                workdir="/workspace/main",
            )
        except Exception:
            pass  # 空响应解析报错不影响 cmd 断言

        cmd_str = " ".join(captured["cmd"]) if isinstance(captured["cmd"], list) else captured["cmd"]
        assert "--allowedTools" in cmd_str, "流式命令应保留 --allowedTools 旗标"
        allowed_section = cmd_str.split("--allowedTools", 1)[1]
        assert " Write" in allowed_section, (
            "BUG-084:allowedTools 缺 Write——headless 下写文件被静默拒绝,"
            "rd-prd 无法落盘 PRD.md"
        )
        assert " Edit" in allowed_section, "BUG-084:allowedTools 缺 Edit"
        assert " Bash" not in allowed_section, (
            "BUG-084:Bash 不放开——终端交互链路保持人工审批面"
        )
