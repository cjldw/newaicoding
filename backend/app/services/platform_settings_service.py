"""平台设置服务 - 单例键值表的读取/更新/校验/加解密(R2;权限收口 R19)

约定:
- 敏感项(gitlab_bot_token / gitlab_webhook_secret)AES-256-GCM 加密落盘,
  value JSON 存 {"__encrypted": <base64>};GET 回显打码,不回明文
- 读取处实时查表(bot token / 根域名等变更即时生效,无需重启)
- 审计记录(platform_settings.update)留 TODO,R19 接入 audit_logs 后补
"""

import logging
import re
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.encryption import decrypt_token, encrypt_token
from app.core.response import BizError, ErrCode
from app.models.project import PlatformSetting

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 配置键白名单与校验规则
# ---------------------------------------------------------------------------
SENSITIVE_KEYS = {"gitlab_bot_token", "gitlab_webhook_secret"}

# 域名(合法主机名)正则:至少一个点分段,每段字母数字连字符,不以 - 开头/结尾
_HOSTNAME_RE = re.compile(r"^(?=.{1,253}$)(?!-)[A-Za-z0-9-]{1,63}(?<!-)(\.[A-Za-z0-9-]{1,63}(?<!-))+$")

# key → (类型, 校验+归一化函数, 说明)
SETTING_KEYS: dict[str, tuple[str, Any]] = {
    "gitlab_url": ("url", None),
    "gitlab_bot_token": ("secret", None),
    "gitlab_bot_group_id": ("int", (1, 10**9)),
    "gitlab_webhook_secret": ("secret", None),
    "preview_base_domain": ("domain", None),
    "deploy_base_domain": ("domain", None),
    "max_containers_total": ("int", (1, 10000)),
    "kb_max_pages_per_kb": ("int", (1, 100000)),
    "kb_max_file_mb": ("int", (1, 1024)),
}


def validate_setting_value(key: str, value: Any) -> Any:
    """
    校验并归一化单个配置值,非法抛 BizError(2007)。
    返回归一化后的值(int 强转等)。
    """
    # 未知配置键 → 2007(白名单外不可写)
    if key not in SETTING_KEYS:
        raise BizError(ErrCode.PLATFORM_SETTING_INVALID, f"非法配置键: {key}")

    vtype, range_ = SETTING_KEYS[key]

    # 域名:合法主机名
    if vtype == "domain":
        if not isinstance(value, str) or not _HOSTNAME_RE.match(value):
            raise BizError(ErrCode.PLATFORM_SETTING_INVALID, f"配置项 {key} 域名格式非法")
        return value

    # URL:http(s) 开头且非空
    if vtype == "url":
        if (
            not isinstance(value, str)
            or not value.strip()
            or not (value.startswith("http://") or value.startswith("https://"))
        ):
            raise BizError(ErrCode.PLATFORM_SETTING_INVALID, f"配置项 {key} 必须为 http(s) 地址且不能为空")
        return value.strip().rstrip("/")

    # 整数:范围内正整数(排除 bool);宽容接受可转 int 的数字字符串(BUG-008)
    if vtype == "int":
        if isinstance(value, bool):
            raise BizError(ErrCode.PLATFORM_SETTING_INVALID, f"配置项 {key} 必须为整数")
        if not isinstance(value, int):
            if not isinstance(value, str):
                raise BizError(ErrCode.PLATFORM_SETTING_INVALID, f"配置项 {key} 必须为整数")
            stripped = value.strip()
            try:
                value = int(stripped)
            except (ValueError, TypeError):
                raise BizError(ErrCode.PLATFORM_SETTING_INVALID, f"配置项 {key} 必须为整数")
        low, high = range_
        if not (low <= value <= high):
            raise BizError(ErrCode.PLATFORM_SETTING_INVALID, f"配置项 {key} 数值越界(允许 {low}-{high})")
        return value

    # secret/token:非空字符串
    if not isinstance(value, str) or not value.strip() or len(value) > 255:
        raise BizError(ErrCode.PLATFORM_SETTING_INVALID, f"配置项 {key} 不能为空且长度需在 255 以内")
    return value.strip()


def mask_sensitive(value: str) -> str:
    """
    敏感值打码回显:保留前 5 位 + 固定掩码 + 后 4 位,如 glpat-••••••••9x2f。
    过短则全部打码。
    """
    if len(value) <= 8:
        return "•" * len(value)
    return f"{value[:5]}••••••••{value[-4:]}"


def _decode_stored(key: str, stored: Any) -> Optional[str]:
    """从 value JSON 还原明文:敏感项解密,普通项原样"""
    if stored is None:
        return None
    if key in SENSITIVE_KEYS and isinstance(stored, dict) and "__encrypted" in stored:
        return decrypt_token(stored["__encrypted"])
    return stored


def _encode_stored(key: str, value: Any) -> Any:
    """写入 value JSON:敏感项加密为 {"__encrypted": b64},普通项原样"""
    if key in SENSITIVE_KEYS:
        return {"__encrypted": encrypt_token(str(value))}
    return value


# ---------------------------------------------------------------------------
# 读取
# ---------------------------------------------------------------------------
async def get_setting(db: AsyncSession, key: str) -> Any:
    """读取单个配置(解密后明文);未配置返回 None"""
    result = await db.execute(select(PlatformSetting).where(PlatformSetting.key == key))
    row = result.scalar_one_or_none()
    if row is None:
        return None
    return _decode_stored(key, row.value)


async def get_all_masked(db: AsyncSession) -> dict:
    """
    GET 接口用:返回全部已配置键值;敏感项打码。
    未配置的键不返回(前端按缺失渲染占位;避免敏感键为 None 时的歧义)。
    """
    result = await db.execute(select(PlatformSetting))
    rows = result.scalars().all()
    out: dict = {}
    for row in rows:
        plain = _decode_stored(row.key, row.value)
        if plain is None:
            continue
        out[row.key] = mask_sensitive(plain) if row.key in SENSITIVE_KEYS else plain
    return out


async def get_gitlab_bot_config(db: AsyncSession) -> tuple[str, str, Optional[int]]:
    """
    读取平台 GitLab 集成配置(gitlab_url / bot token / bot group_id)。
    url 或 token 未配置 → BizError(2001)(项目创建入口禁用的后端依据)。
    """
    gitlab_url = await get_setting(db, "gitlab_url")
    bot_token = await get_setting(db, "gitlab_bot_token")
    group_id = await get_setting(db, "gitlab_bot_group_id")

    # 平台 GitLab 未配置:项目创建/分支管理等全部失败(2001 引导超管配置)
    if not gitlab_url or not bot_token:
        raise BizError(ErrCode.BOT_TOKEN_NOT_CONFIGURED, "平台 GitLab 未配置,请联系管理员")
    return gitlab_url, bot_token, group_id


# ---------------------------------------------------------------------------
# 更新
# ---------------------------------------------------------------------------
async def update_settings(db: AsyncSession, updated_by: str, payload: dict) -> list[str]:
    """
    PUT 接口用:白名单 + 类型校验后 UPSERT;敏感项加密落盘。
    返回成功更新的 key 列表。审计留 TODO(R19)。
    """
    # 先整体校验,任一非法则整批拒绝(避免部分写入)
    validated: dict[str, Any] = {}
    for key, value in payload.items():
        validated[key] = validate_setting_value(key, value)

    updated: list[str] = []
    for key, value in validated.items():
        result = await db.execute(select(PlatformSetting).where(PlatformSetting.key == key))
        row = result.scalar_one_or_none()
        if row is None:
            row = PlatformSetting(key=key, value=_encode_stored(key, value), updated_by=updated_by)
            db.add(row)
        else:
            row.value = _encode_stored(key, value)
            row.updated_by = updated_by
        updated.append(key)

    await db.flush()
    # TODO(R19): 审计记录 platform_settings.update(操作人/变更键列表,异步队列写 audit_logs)
    logger.info("平台设置更新 keys=%s by=%s", updated, updated_by)
    return updated
