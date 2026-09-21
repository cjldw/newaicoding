"""Claude 服务 - R4(AI 执行适配层,按 D3)

- 主路径(SDK):claude-agent-sdk(ClaudeSDKClient)——本机未安装该包(pip 网络
  受限,需 Node sidecar),保留 adapter 接口,装包后无侵入切换
- 兜底路径(CLI,当前实现):经 Runner 在容器内执行 `claude -p <prompt>` 非交互
  模式(镜像已预装 @anthropic-ai/claude-code,env 注入 ANTHROPIC_* 配置,R8/R3)
- 输出:CLI JSON 输出解析 {result, tokens};工具调用事件以容器内产物为准
  (文件 watcher + git diff,工作台活动流展示)
"""

import logging
import shlex
import uuid
from typing import Any, Optional

logger = logging.getLogger(__name__)


async def run_prompt(
    runner_conn,
    container_id: str,
    prompt: str,
    workdir: str = "/workspace/main",
    timeout: float = 600.0,
) -> dict:
    """
    发送一轮 AI 请求(当前 CLI 兜底实现):
    经 Runner exec 在容器内执行 claude CLI,返回 {"result", "tokens_in", "tokens_out"}。
    """
    from app.services import runner_service

    req_id = uuid.uuid4().hex
    message = {
        "type": "exec_tool",
        "container_id": container_id,
        "tool": "claude_prompt",
        "args": {"prompt": prompt, "workdir": workdir},
        "req_id": req_id,
    }
    try:
        result = await runner_service.request_runner(runner_conn, message, timeout=timeout)
    except TimeoutError:
        raise RuntimeError("AI 执行超时")
    if not result.get("ok"):
        raise RuntimeError(result.get("error") or "AI 执行失败")

    data = result.get("data") or {}
    return {
        "result": data.get("result", ""),
        "tokens_in": int(data.get("tokens_in", 0) or 0),
        "tokens_out": int(data.get("tokens_out", 0) or 0),
    }


def build_claude_exec(prompt: str, workdir: str = "/workspace/main") -> tuple[str, str]:
    """构造容器内 claude CLI 命令(Runner exec_tool=claude_prompt 调用)"""
    quoted = shlex.quote(prompt)
    cmd = (
        f"cd {workdir} 2>/dev/null; "
        f"claude -p {quoted} --output-format json 2>/dev/null"
    )
    return cmd, workdir


# ---------------------------------------------------------------------------
# SDK 主路径 adapter(claude-agent-sdk 可用后的无侵入切换点;当前不可用)
# ---------------------------------------------------------------------------
class SdkNotAvailable(RuntimeError):
    pass


class ClaudeSdkAdapter:
    """SDK 模式占位:接口与 CLI 对齐,运行时抛 SdkNotAvailable 走 CLI 兜底"""

    def __init__(self, base_url: str, api_key: str, model: str) -> None:
        self.base_url = base_url
        self.api_key = api_key
        self.model = model

    async def create_conversation(self) -> str:
        raise SdkNotAvailable("claude-agent-sdk 未安装,使用 CLI 兜底路径")

    async def send_message(self, conversation_id: str, prompt: str) -> dict:  # noqa: ARG002
        raise SdkNotAvailable("claude-agent-sdk 未安装,使用 CLI 兜底路径")
