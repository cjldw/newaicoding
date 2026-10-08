"""
BUG-079 Red 测试:后台探索 Agent 与 120s 流式看门狗互杀
====================================================
现场(2026-10-08,任务 228e6d07「后台登录图验证码」打磨):
  rd-prd 技能用 Agent 工具启动**异步后台探索子代理**,主回合 end_turn 后
  CLI 等待 task-notification 期间 stream-json **零输出**;runner R8.F6 看门狗
  120s 到点 pkill → 用户消息标「发送失败」、已流出回复被清空;重发再启一个
  Agent 再被杀 → 对话死循环,用户全程输入被锁(POST pending),无法回答访谈。

修复(双管):
  1. STREAM_TIMEOUT 120 → 540:给后台探索(实测 ~2min,Very-thorough 更长)
     留足空间,同时 < 平台侧 request_runner_stream 600s 守卫(runner 先收口,
     仍能 pkill 真挂死);
  2. 流式命令追加 --forward-subagent-text(仅 --print + stream-json 生效,
     正是本链路):子代理文本/思考转发为主流事件,探索期不再全静默。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main as runner_main

from container_manager import ContainerManager
from test_prompt_transport import FakeClient


class TestBug079BackgroundAgentSurvival:
    def test_stream_timeout_covers_background_exploration(self):
        """看门狗必须 ≥ 5min(后台探索实测分钟级),且 < 平台 600s 守卫"""
        assert runner_main.STREAM_TIMEOUT >= 300, (
            "BUG-079:120s 看门狗杀掉 rd-prd 后台探索子代理的静默等待期,"
            "对话死循环;须 ≥ 300s"
        )
        assert runner_main.STREAM_TIMEOUT < 600, (
            "BUG-079:须 < 平台 request_runner_stream 600s 守卫,"
            "让 runner 侧先 pkill 收口(error=stream_timeout)"
        )

    def test_stream_cmd_forwards_subagent_text(self):
        """流式命令应携带 --forward-subagent-text(探索期进度可见,静默期缩短)"""
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
        assert "--forward-subagent-text" in cmd_str, (
            "BUG-079:流式命令缺少 --forward-subagent-text,"
            "子代理探索期主流零事件(用户只见静默,看门狗易误杀)"
        )
