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
    session_id: str | None = None,
    resume: bool = False,
) -> dict:
    """
    发送一轮 AI 请求(当前 CLI 兜底实现):
    经 Runner exec 在容器内执行 claude CLI,返回 {"result", "tokens_in", "tokens_out"}。

    R9.F1 会话参数:
    - session_id: 任务级 claude CLI 会话 ID(可选,不传时维持原行为)
    - resume: True=续接已有会话(--resume),False=首次建会话(--session-id)
    """
    from app.services import runner_service

    req_id = uuid.uuid4().hex
    args = {"prompt": prompt, "workdir": workdir}
    # R9.F1:会话参数透传(不传时维持原样,兼容旧行为)
    if session_id is not None:
        args["session_id"] = session_id
        if resume:
            args["resume"] = True

    message = {
        "type": "exec_tool",
        "container_id": container_id,
        "tool": "claude_prompt",
        "args": args,
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


async def run_prompt_stream(
    runner_conn,
    container_id: str,
    prompt: str,
    task_id: str,
    workdir: str = "/workspace/main",
    session_id: str | None = None,
    resume: bool = False,
):
    """
    R32.F3:流式发送一轮 AI 请求(exec_tool=claude_prompt_stream)。
    返回 (stream_iter, finalize):
    - stream_iter:async generator,逐条产出 Runner 上泵的 stream-json 行(dict 事件)
    - finalize():等待终态,返回 {"result", "tokens_in", "tokens_out"}(失败抛 RuntimeError)
    调用方(task_service)边迭代边广播,结束后 await finalize() 落库。
    """
    import json as _json

    from app.services import runner_service

    req_id, queue = await runner_service.request_runner_stream(
        runner_conn,
        {
            "type": "exec_tool",
            "container_id": container_id,
            "task_id": task_id,
            "tool": "claude_prompt_stream",
            "args": {
                "prompt": prompt,
                "workdir": workdir,
                **({"session_id": session_id} if session_id is not None else {}),
                **({"resume": True} if (session_id is not None and resume) else {}),
            },
        },
    )

    final: dict = {}

    async def stream_iter():
        while True:
            evt = await queue.get()
            if evt["type"] == "done":
                final.update(evt)
                return
            try:
                yield _json.loads(evt["line"])
            except (ValueError, TypeError):
                yield {"type": "raw", "text": evt["line"]}

    async def finalize() -> dict:
        # 调用方若提前中断迭代,这里排空队列直到 done
        while "type" not in final:
            evt = await queue.get()
            if evt["type"] == "done":
                final.update(evt)
        if not final.get("ok"):
            raise RuntimeError(final.get("error") or "AI 执行失败")
        data = final.get("data") or {}
        return {
            "result": data.get("result", ""),
            "tokens_in": int(data.get("tokens_in", 0) or 0),
            "tokens_out": int(data.get("tokens_out", 0) or 0),
        }

    return stream_iter(), finalize


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
