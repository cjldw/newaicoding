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


def container_base_url(base_url: str) -> str:
    """
    容器内可达性改写(BUG-034):平台配置的 base_url 若指向宿主机回环
    (127.0.0.1 / localhost / [::1]),注入容器后 127.0.0.1 = 容器自身,
    claude CLI 连接直接 ECONNREFUSED(实证:平台连通性测试通过但容器内
    全部失败)。注入容器前改写为 host.docker.internal(Docker Desktop
    默认提供,指向宿主机);仅改写注入值,平台存储配置与连通性测试不动。
    仅改写 scheme:// 后紧跟的回环 host,避免误伤路径/查询中的同形字符串。
    """
    import re

    if not base_url:
        return base_url
    return re.sub(
        r"^(https?://)(127\.0\.0\.1|localhost|\[::1\])(?=[:/]|$)",
        r"\1host.docker.internal",
        base_url,
        flags=re.IGNORECASE,
    )

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
    任务执行时解析配置(R23 回退链):
      会话级 config_id → 项目 default(enabled)→ 平台默认(llm_* 三键)。
    全部不可用 → BizError(13005;语义:项目与平台均未配置,入口禁用并引导)。
    返回体含 source 字段("project" | "platform"),供调用方留痕排障,不进容器 env。
    """
    from sqlalchemy import select

    if config_id is not None:
        result = await db.execute(
            select(ModelConfig).where(ModelConfig.config_id == config_id)
        )
        config = result.scalar_one_or_none()
        if config is not None:
            resolved = decrypt_config(config)
            resolved["source"] = "project"
            return resolved
        # 会话级指定失效时同样走回退链(项目级 → 平台级)
        logger.info("会话级配置 %s 不存在,走回退链", config_id)

    result = await db.execute(
        select(ModelConfig).where(
            ModelConfig.project_id == project_id,
            ModelConfig.is_default.is_(True),
            ModelConfig.enabled.is_(True),
        )
    )
    config = result.scalar_one_or_none()
    if config is not None:
        resolved = decrypt_config(config)
        resolved["source"] = "project"
        return resolved

    # R23: 项目级无可用配置 → 回退平台默认
    return await _resolve_platform_config(db)


async def _resolve_platform_config(db) -> dict:
    """
    R23: 平台默认 LLM 回退(llm_base_url / llm_api_key + R1 的 llm_models /
    llm_default_model,四键齐备才生效)。
    R1: 模型经 service 读取层兼容(存量单值 llm_model → [旧值];default 缺失 →
    列表第一项),返回 model=默认模型。
    任一缺失 → 13005;部分键存在(手工改库等异常)按未配置处理并告警。
    """
    from app.services.platform_settings_service import get_setting

    base_url = await get_setting(db, "llm_base_url")
    api_key = await get_setting(db, "llm_api_key")
    models = await get_setting(db, "llm_models")
    model = await get_setting(db, "llm_default_model")

    # 部分键存在:视为未配置,告警便于排查脏数据
    present = [name for name, value in
               (("llm_base_url", base_url), ("llm_api_key", api_key),
                ("llm_models", models), ("llm_default_model", model)) if value]
    if present and len(present) < 4:
        logger.warning("平台默认 LLM 配置不完整(仅 %s),按未配置处理", present)

    if not base_url or not api_key or not models or not model:
        raise BizError(
            13005,
            "项目与平台均未配置模型,请联系管理员配置平台默认或在项目设置中添加模型配置",
        )
    return {"base_url": base_url, "api_key": api_key, "model": model, "source": "platform"}
