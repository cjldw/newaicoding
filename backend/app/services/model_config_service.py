"""模型配置服务 - R13 CRUD + 打码 + default 唯一保证"""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.encryption import encrypt_token
from app.core.response import BizError, ErrCode
from app.models.model_config import ModelConfig
from app.models.project import Project
from app.models.user import User
from app.services import llm_service

logger = logging.getLogger(__name__)


def mask_api_key(api_key: str) -> str:
    """key 打码:前 4 + *** + 后 4(如 sk-1234567890abcdef → sk-1***cdef);过短全 *"""
    if len(api_key) <= 8:
        return "*" * len(api_key)
    return f"{api_key[:4]}***{api_key[-4:]}"


async def _creator_brief(db: AsyncSession, user_id: str) -> dict:
    result = await db.execute(select(User).where(User.user_id == user_id))
    u = result.scalar_one_or_none()
    return {"user_id": user_id, "username": (u.gitlab_username or "") if u else ""}


async def _config_item(db: AsyncSession, config: ModelConfig, include_key: bool = True) -> dict:
    """列表项组装;api_key 只回打码(viewer 视角 include_key=False 时不出该字段)"""
    item = {
        "config_id": config.config_id,
        "name": config.name,
        "base_url": config.base_url,
        "model": config.model,
        "is_default": bool(config.is_default),
        "enabled": bool(config.enabled),
        "created_by": await _creator_brief(db, config.created_by),
        "created_at": config.created_at,
    }
    if include_key:
        # 解密仅为打码展示(明文不落日志/不回接口)
        try:
            from app.core.encryption import decrypt_token
            item["api_key_masked"] = mask_api_key(decrypt_token(config.api_key_encrypted))
        except Exception:
            item["api_key_masked"] = "****"
    return item


async def _get_config_or_404(db: AsyncSession, project_id: str, config_id: str) -> ModelConfig:
    result = await db.execute(
        select(ModelConfig).where(
            ModelConfig.config_id == config_id,
            ModelConfig.project_id == project_id,
        )
    )
    config = result.scalar_one_or_none()
    if config is None:
        raise BizError(404, "配置不存在", status_code=404)
    return config


async def _ensure_no_duplicate_name(db: AsyncSession, project_id: str, name: str, exclude_config_id: str = None) -> None:
    """同项目配置名唯一(13002)"""
    from sqlalchemy import and_

    conds = [ModelConfig.project_id == project_id, ModelConfig.name == name]
    if exclude_config_id:
        conds.append(ModelConfig.config_id != exclude_config_id)
    result = await db.execute(select(ModelConfig.id).where(*conds).limit(1))
    if result.scalar_one_or_none() is not None:
        raise BizError(ErrCode.CONFIG_NAME_DUPLICATE, "配置名已存在")


async def list_configs(db: AsyncSession, project: Project, operator_role: str) -> list[dict]:
    """配置列表(成员可看;viewer 不含 api_key 字段)"""
    result = await db.execute(
        select(ModelConfig)
        .where(ModelConfig.project_id == project.project_id)
        .order_by(ModelConfig.is_default.desc(), ModelConfig.created_at.asc(), ModelConfig.id.asc())
    )
    configs = result.scalars().all()
    include_key = operator_role != "viewer"
    return [await _config_item(db, c, include_key=include_key) for c in configs]


async def create_config(db: AsyncSession, project, operator: User, req) -> dict:
    """owner 创建配置;保存前连通性测试(失败拒绝,13001)"""
    logger.info("创建模型配置 project=%s name=%s by=%s", project.project_id, req.name, operator.user_id)

    # 同项目配置名唯一(13002)
    await _ensure_no_duplicate_name(db, project.project_id, req.name)

    # 同项目最多一个 default(13003;服务层保证,MySQL 无部分唯一索引)
    if req.is_default:
        dup = await db.execute(
            select(ModelConfig.id).where(
                ModelConfig.project_id == project.project_id,
                ModelConfig.is_default.is_(True),
            ).limit(1)
        )
        if dup.scalar_one_or_none() is not None:
            raise BizError(ErrCode.CONFIG_DEFAULT_EXISTS, "已有默认配置,请先取消原默认")

    # 连通性测试(失败拒绝;13001)
    await llm_service.test_connectivity(req.base_url, req.api_key, req.model)

    config = ModelConfig(
        project_id=project.project_id,
        name=req.name,
        base_url=req.base_url.rstrip("/"),
        api_key_encrypted=encrypt_token(req.api_key),
        model=req.model,
        is_default=req.is_default,
        enabled=req.enabled,
        created_by=operator.user_id,
    )
    db.add(config)
    await db.flush()
    # created_at/updated_at 为服务端生成,flush 后属性过期,显式异步刷新
    # (否则后续属性访问触发同步 IO → MissingGreenlet)
    await db.refresh(config)

    logger.info("模型配置创建完成 config=%s project=%s", config.config_id, project.project_id)
    return await _config_item(db, config)


async def update_config(db: AsyncSession, project, operator: User, config_id: str, req) -> dict:
    """owner 更新配置;base_url/api_key 变更时重新连通性测试;default 冲突 13003"""
    config = await _get_config_or_404(db, project.project_id, config_id)

    if req.name is not None and req.name != config.name:
        await _ensure_no_duplicate_name(db, project.project_id, req.name, exclude_config_id=config.config_id)
        config.name = req.name
    if req.base_url is not None:
        config.base_url = req.base_url.rstrip("/")
    if req.model is not None:
        config.model = req.model
    if req.api_key is not None:
        # 更新时重新加密
        config.api_key_encrypted = encrypt_token(req.api_key)
    if req.is_default is not None:
        if req.is_default and not config.is_default:
            dup = await db.execute(
                select(ModelConfig.id).where(
                    ModelConfig.project_id == project.project_id,
                    ModelConfig.is_default.is_(True),
                    ModelConfig.config_id != config.config_id,
                ).limit(1)
            )
            if dup.scalar_one_or_none() is not None:
                raise BizError(ErrCode.CONFIG_DEFAULT_EXISTS, "已有默认配置,请先取消原默认")
        config.is_default = req.is_default
    if req.enabled is not None:
        config.enabled = req.enabled

    # 连接要素变更 → 重新测试(仅改名/启用状态不重测)
    if req.base_url is not None or req.api_key is not None:
        from app.core.encryption import decrypt_token
        await llm_service.test_connectivity(
            config.base_url, decrypt_token(config.api_key_encrypted), config.model
        )

    await db.flush()
    await db.refresh(config)
    logger.info("模型配置更新 config=%s by=%s", config_id, operator.user_id)
    return await _config_item(db, config)


async def delete_config(db: AsyncSession, project, operator: User, config_id: str) -> None:
    """owner 删除配置;default 不可删(13004,需先指定新 default)"""
    config = await _get_config_or_404(db, project.project_id, config_id)
    if config.is_default:
        raise BizError(ErrCode.CONFIG_DEFAULT_UNDELETABLE, "不可删除默认配置,请先指定新默认")

    await db.delete(config)
    await db.flush()
    logger.info("模型配置删除 config=%s by=%s", config_id, operator.user_id)
