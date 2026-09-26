"""平台设置路由 - GET/PUT /api/admin/platform-settings(超管;R2;权限收口 R19)"""

from typing import Any, Dict

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import require_superadmin
from app.core.response import BizError, ErrCode, success
from app.database import get_db
from app.models.user import User
from app.services import gitlab_service, llm_service, platform_settings_service
from app.services.audit_service import audit_write  # R25 审计接入

router = APIRouter(prefix="/api/admin/platform-settings", tags=["平台管理"])


# -------------------------------------------------------------------
# GET /api/admin/platform-settings - 获取全部配置(敏感项打码)
# -------------------------------------------------------------------
@router.get("")
async def get_platform_settings(
    current_user: User = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
):
    """超管读取平台配置;gitlab_bot_token / gitlab_webhook_secret 打码回显,不回明文"""
    data = await platform_settings_service.get_all_masked(db)
    return success(data=data)


# -------------------------------------------------------------------
# PUT /api/admin/platform-settings - 部分更新(白名单 key;敏感项加密落盘)
# -------------------------------------------------------------------
@router.put("")
async def update_platform_settings(
    payload: Dict[str, Any],
    current_user: User = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
):
    """
    超管更新配置(部分更新 {key: value});仅白名单 key 可写,非法值 2007。
    变更即时生效(读取处实时查表)。R25:审计在 API 层接入(service 签名不改)。
    """
    # R23→R1: payload 含任一 llm_* 键时,先整批校验(2007)→ 连通性测试(失败 2008)→ 才落库。
    # R1 起齐备口径为四键(service.LLM_KEYS:base_url/api_key/models/default_model,旧键 llm_model 出局)
    provided = platform_settings_service.LLM_KEYS & payload.keys()
    if provided:
        # 齐备性前置:缺任一键 2007(必须先于下方取键,避免 KeyError)
        if provided != platform_settings_service.LLM_KEYS:
            raise BizError(ErrCode.PLATFORM_SETTING_INVALID, "平台默认模型需完整配置四项")
        # 逐键预校验(与 update_settings 同规则;提前到测试前,非法格式不必等网络超时)
        for key in provided:
            platform_settings_service.validate_setting_value(key, payload[key])
        # R1: 默认模型必须是 llm_models 已有项(归一化后比对;校验拒绝,先于连通测试)
        models = platform_settings_service.validate_setting_value("llm_models", payload["llm_models"])
        default_model = platform_settings_service.validate_setting_value(
            "llm_default_model", payload["llm_default_model"]
        )
        if default_model not in models:
            raise BizError(ErrCode.PLATFORM_SETTING_INVALID, "默认模型必须为模型名列表中的已有项")
        try:
            # R1: 连通测试对象=默认模型(其余模型名不做保存期测试,运行时报错沿用 R23 口径)
            await llm_service.test_connectivity(
                payload["llm_base_url"], payload["llm_api_key"], default_model
            )
        except BizError as e:
            # 项目级测试失败是 13001;平台默认保存失败用独立码 2008,便于前端区分文案
            raise BizError(ErrCode.PLATFORM_LLM_CONNECT_FAILED, e.message) from e
    updated = await platform_settings_service.update_settings(db, current_user.user_id, payload)
    # R25 审计:platform_settings.update(模式 C:operator 在 API 层;detail 只记键列表,
    # 不记值——值可能含 token/key,落 detail 即泄密)
    await audit_write(
        db, current_user, "platform_settings.update",
        target_type="platform_setting",
        detail={"updated_keys": updated},
    )
    return success(data={"updated": updated})


# -------------------------------------------------------------------
# POST /api/admin/platform-settings/test-connection - 测试 GitLab 连接
# -------------------------------------------------------------------
@router.post("/test-connection")
async def test_connection(
    current_user: User = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
):
    """用已保存的 gitlab_url + bot token 调 GitLab GET /api/v4/version 验证连通性"""
    gitlab_url, bot_token, _ = await platform_settings_service.get_gitlab_bot_config(db)
    result = await gitlab_service.bot_test_connection(bot_token, gitlab_url)
    return success(data=result)
