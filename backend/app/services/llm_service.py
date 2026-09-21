"""LLM 调用服务 - R13(SDK 模式主路径的配置解析;连通性测试)

- 连通性测试:GET {base_url}/models(OpenAI 兼容),Bearer api_key,超时 10s
- SDK 模式:resolve_config() 给任务执行方(R4/R5)提供解密后的配置
- CLI 模式:LLM_ENV_KEYS 定义注入容器的环境变量契约(R8 容器创建时消费);
  key 仅容器内存,不落镜像/日志
"""

import logging
import time
from typing import Optional

import httpx

from app.core.encryption import decrypt_token
from app.core.response import BizError, ErrCode
from app.models.model_config import ModelConfig

logger = logging.getLogger(__name__)

# 连通性测试超时(秒)
LLM_TEST_TIMEOUT = 10.0

# CLI 模式容器 env 注入契约(分片:通用变量 + Claude CLI 兼容变量;R8 消费)
LLM_ENV_KEYS = {
    "LLM_BASE_URL": "base_url",
    "LLM_API_KEY": "api_key",
    "LLM_MODEL": "model",
    "ANTHROPIC_BASE_URL": "base_url",
    "ANTHROPIC_API_KEY": "api_key",
}

# ---------------------------------------------------------------------------
# 测试用 mock client 注入点(与 gitlab_service._test_transport 同机制;
# conftest 的 autouse patch 只覆盖 gitlab,LLM 的 mock 由测试直接调
# set_test_transport 设置)
# ---------------------------------------------------------------------------
_test_transport: Optional[httpx.MockTransport] = None


def set_test_transport(transport: Optional[httpx.MockTransport]) -> None:
    """供测试注入/清除 mock transport"""
    global _test_transport
    _test_transport = transport


def _get_client() -> httpx.AsyncClient:
    if _test_transport is not None:
        return httpx.AsyncClient(transport=_test_transport, timeout=LLM_TEST_TIMEOUT)
    return httpx.AsyncClient(timeout=LLM_TEST_TIMEOUT, verify=False)


async def test_connectivity(base_url: str, api_key: str, model: str) -> dict:
    """
    连通性测试:GET {base_url}/models,Authorization: Bearer {api_key}
    200 → {"success": True, "latency_ms": N}
    401/404/超时/网络错误 → BizError(13001)
    (model 参数保留在契约中:OpenAI 兼容 /models 不需要 model,留作部分
     兼容网关校验用,不参与本请求)
    """
    url = f"{base_url.rstrip('/')}/models"
    client = _get_client()
    start = time.perf_counter()
    try:
        resp = await client.get(url, headers={"Authorization": f"Bearer {api_key}"})
    except httpx.HTTPError as e:
        logger.warning("LLM 连通性测试失败 %s: %s", url, e)
        raise BizError(ErrCode.LLM_CONNECT_FAILED, "连接失败,请检查 Base URL 和 API Key")
    finally:
        await client.aclose()

    latency_ms = int((time.perf_counter() - start) * 1000)

    if resp.status_code == 200:
        return {"success": True, "latency_ms": latency_ms}
    if resp.status_code == 401:
        logger.info("LLM 连通性 401(api_key 无效) %s", url)
    elif resp.status_code == 404:
        logger.info("LLM 连通性 404(base_url 错误) %s", url)
    else:
        logger.info("LLM 连通性 %s %s", resp.status_code, url)
    raise BizError(ErrCode.LLM_CONNECT_FAILED, "连接失败,请检查 Base URL 和 API Key")


def decrypt_config(config: ModelConfig) -> dict:
    """解密一条配置 → {base_url, api_key, model}(SDK/CLI 消费用,禁止入日志)"""
    return {
        "base_url": config.base_url,
        "api_key": decrypt_token(config.api_key_encrypted),
        "model": config.model,
    }


async def resolve_config(db, project_id: str, config_id: Optional[str] = None) -> dict:
    """
    任务执行时解析配置:优先指定 config_id(会话级切换),否则取项目 default。
    无可用配置 → BizError(13005 语义:未配置,任务入口禁用并引导;
    复用 13001 不合适,独立码 13005)。
    """
    from sqlalchemy import select

    if config_id is not None:
        result = await db.execute(
            select(ModelConfig).where(ModelConfig.config_id == config_id)
        )
    else:
        result = await db.execute(
            select(ModelConfig).where(
                ModelConfig.project_id == project_id,
                ModelConfig.is_default.is_(True),
                ModelConfig.enabled.is_(True),
            )
        )
    config = result.scalar_one_or_none()
    if config is None:
        raise BizError(13005, "项目未配置可用模型,请先在项目设置中添加模型配置")
    return decrypt_config(config)
