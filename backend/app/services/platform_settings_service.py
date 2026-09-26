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

from cryptography.exceptions import InvalidTag
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.encryption import decrypt_token, encrypt_token
from app.core.response import BizError, ErrCode
from app.models.project import PlatformSetting

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 配置键白名单与校验规则
# ---------------------------------------------------------------------------
SENSITIVE_KEYS = {"gitlab_bot_token", "gitlab_webhook_secret", "llm_api_key"}

# R23: llm_* 整批保存(不支持只更新一键);R1 模型单值升级为列表+默认项,扩为四键。
# 旧键 llm_model 移出白名单(不再受理写入),存量数据走读取层兼容(见 get_setting)
LLM_KEYS = {"llm_base_url", "llm_api_key", "llm_models", "llm_default_model"}

# R8.F4(BUG-036):自定义环境变量键名规则(合法 shell 变量名)
_ENV_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
# 自定义变量数量上限(防设置页灌爆容器 env)
CUSTOM_ENV_MAX_KEYS = 50
# R1: 模型名列表数量上限(llm_models)
LLM_MODELS_MAX = 10
# 系统注入键(R8.F4:自定义变量不得占用,防覆盖 LLM/GitLab/任务上下文)
RESERVED_ENV_KEYS = {
    "GITLAB_TOKEN", "GITLAB_INSTANCE_URL",
    "LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL", "LLM_URL",
    "ANTHROPIC_BASE_URL", "ANTHROPIC_API_KEY", "ANTHROPIC_MODEL",
    "TASK_ID", "PROJECT_ID", "REQ_ID", "PRD_FILE_PATH",
}

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
    # R23: 平台默认 LLM 配置(四键齐备才生效;R1 模型升级为列表+默认项)
    "llm_base_url": ("url", None),
    "llm_api_key": ("secret", None),
    # R1: 模型名列表(JSON 字符串数组,每项 1-64 字符、去重、≤10)
    "llm_models": ("strlist", None),
    "llm_default_model": ("str", None),
    # R8.F4(BUG-036): 自定义容器环境变量(多组 KV,启动任务时全量注入)
    "custom_env_vars": ("envmap", None),
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

    # R8.F4: 自定义环境变量表(dict[str,str];空 dict=清空)
    if vtype == "envmap":
        return _validate_custom_env(value)

    # R1: 字符串数组(每项 str 1-64、去重、≤10;专用于 llm_models)
    if vtype == "strlist":
        return _validate_strlist(key, value)

    # R23: str 类型(非空、strip、≤64 字符)
    if vtype == "str":
        if not isinstance(value, str) or not value.strip():
            raise BizError(ErrCode.PLATFORM_SETTING_INVALID, f"配置项 {key} 不能为空")
        return value.strip()[:64]

    # secret/token:非空字符串
    if not isinstance(value, str) or not value.strip() or len(value) > 255:
        raise BizError(ErrCode.PLATFORM_SETTING_INVALID, f"配置项 {key} 不能为空且长度需在 255 以内")
    return value.strip()


def _validate_custom_env(value: Any) -> dict:
    """
    R8.F4(BUG-036):custom_env_vars 校验——必须为 {str: str} 字典。
    规则:键名匹配 shell 变量名、≤50 组、值 ≤2048 字符、不得占用系统保留键。
    空 dict 合法(=清空)。错误文案只暴露键名,不回显值(值可能含密文)。
    设计留痕:本键**不进 SENSITIVE_KEYS**——密文回显会让编辑不可用(用户需看值来改),
    且该设置页仅超管可见,与"审计不落值"(R25 决策④)共同构成安全边界。
    """
    if not isinstance(value, dict):
        raise BizError(ErrCode.PLATFORM_SETTING_INVALID, "配置项 custom_env_vars 必须为键值对象")
    if len(value) > CUSTOM_ENV_MAX_KEYS:
        raise BizError(
            ErrCode.PLATFORM_SETTING_INVALID,
            f"自定义变量数量超限(最多 {CUSTOM_ENV_MAX_KEYS} 个)",
        )
    result: dict[str, str] = {}
    for k, v in value.items():
        if not isinstance(k, str) or not _ENV_KEY_RE.match(k):
            raise BizError(
                ErrCode.PLATFORM_SETTING_INVALID,
                f"变量名 {k!r} 非法(须匹配 [A-Za-z_][A-Za-z0-9_]*)",
            )
        # 保留名拒写:防覆盖平台注入的 LLM/GitLab/任务上下文
        if k in RESERVED_ENV_KEYS:
            raise BizError(
                ErrCode.PLATFORM_SETTING_INVALID,
                f"变量名 {k} 为系统保留",
            )
        if not isinstance(v, str):
            raise BizError(
                ErrCode.PLATFORM_SETTING_INVALID,
                f"变量 {k} 的值必须为字符串",
            )
        if len(v) > 2048:
            raise BizError(
                ErrCode.PLATFORM_SETTING_INVALID,
                f"变量 {k} 的值超长(≤2048 字符)",
            )
        result[k] = v
    return result


def _validate_strlist(key: str, value: Any) -> list:
    """
    R1:strlist 校验——JSON 字符串数组,每项非空 1-64 字符(与 str 同规)。
    上限 LLM_MODELS_MAX 个(超限 13008);列表内去重(重复 13009,不静默合并);
    空列表拒绝 2007(未配置语义=键缺失,而非空数组)。
    """
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise BizError(ErrCode.PLATFORM_SETTING_INVALID, f"配置项 {key} 必须为字符串数组")
    if not value:
        raise BizError(ErrCode.PLATFORM_SETTING_INVALID, f"配置项 {key} 至少需要 1 项")
    if len(value) > LLM_MODELS_MAX:
        raise BizError(
            ErrCode.LLM_MODELS_LIMIT,
            f"配置项 {key} 数量超上限(最多 {LLM_MODELS_MAX} 个)",
        )
    items: list = []
    for v in value:
        item = v.strip()
        if not item or len(item) > 64:
            raise BizError(
                ErrCode.PLATFORM_SETTING_INVALID,
                f"配置项 {key} 每项需为 1-64 字符的非空字符串",
            )
        items.append(item)
    if len(set(items)) != len(items):
        raise BizError(ErrCode.LLM_MODEL_DUPLICATE, f"配置项 {key} 存在重复项")
    return items


def mask_sensitive(value: str) -> str:
    """
    敏感值打码回显:保留前 5 位 + 固定掩码 + 后 4 位,如 glpat-••••••••9x2f。
    过短则全部打码。
    """
    if len(value) <= 8:
        return "•" * len(value)
    return f"{value[:5]}••••••••{value[-4:]}"


def _decode_stored(key: str, stored: Any) -> Optional[str]:
    """从 value JSON 还原明文:敏感项解密,普通项原样。
    BUG-038:单键解密失败(密钥轮换/密文损坏)视为「已失效需重置」,
    折叠为 None 走既有未配置语义(2001/13005),不再打挂 GET 等消费方。
    """
    if stored is None:
        return None
    if key in SENSITIVE_KEYS and isinstance(stored, dict) and "__encrypted" in stored:
        try:
            return decrypt_token(stored["__encrypted"])
        except (InvalidTag, ValueError):
            # InvalidTag=密钥不匹配(如 .env 密钥轮换后存量密文);
            # ValueError 覆盖密文损坏(base64 的 binascii.Error)与解出乱码
            # (UnicodeDecodeError),二者均为其子类。只记键名,不落明文/密文。
            logger.warning(
                "平台配置 %s 解密失败(密文失效需重置:密钥轮换或密文损坏),按未配置处理", key
            )
            return None
    return stored


def _encode_stored(key: str, value: Any) -> Any:
    """写入 value JSON:敏感项加密为 {"__encrypted": b64},普通项原样"""
    if key in SENSITIVE_KEYS:
        return {"__encrypted": encrypt_token(str(value))}
    return value


# ---------------------------------------------------------------------------
# 读取
# ---------------------------------------------------------------------------
async def _get_decoded(db: AsyncSession, key: str) -> Any:
    """按 key 查表并解密为明文;未配置返回 None(不含读取层兼容)"""
    result = await db.execute(select(PlatformSetting).where(PlatformSetting.key == key))
    row = result.scalar_one_or_none()
    if row is None:
        return None
    return _decode_stored(key, row.value)


async def _llm_read_compat(db: AsyncSession, key: str, value: Any) -> Any:
    """
    R1 存量单值读取层兼容(无回填脚本,老数据行为不变):
    - llm_models 缺失(或空)且旧键 llm_model 有值 → 包装 [旧值]
    - llm_default_model 缺失 → 取(兼容后的)模型列表第一项(存量默认=旧值)
    同时服务于 _resolve_platform_config 与 GET(经 get_setting / get_all_masked)。
    """
    if value:
        return value
    if key == "llm_models":
        legacy = await _get_decoded(db, "llm_model")
        return [legacy] if legacy else None
    # llm_default_model:缺失时取兼容后的列表第一项
    models = await get_setting(db, "llm_models")
    return models[0] if isinstance(models, list) and models else None


async def get_setting(db: AsyncSession, key: str) -> Any:
    """读取单个配置(解密后明文);未配置返回 None。
    R1: llm_models / llm_default_model 走存量兼容(见 _llm_read_compat)"""
    value = await _get_decoded(db, key)
    if key in ("llm_models", "llm_default_model"):
        return await _llm_read_compat(db, key, value)
    return value


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
    # R1 存量兼容映射:llm_models 缺失且旧键 llm_model 有值 → 补 [旧值](旧键原样
    # 保留);llm_default_model 缺失 → 列表第一项(与 get_setting 兼容口径一致)
    if not out.get("llm_models") and out.get("llm_model"):
        out["llm_models"] = [out["llm_model"]]
    if not out.get("llm_default_model"):
        models = out.get("llm_models")
        if isinstance(models, list) and models:
            out["llm_default_model"] = models[0]
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
    返回成功更新的 key 列表。审计由 API 层接入(R25:模式 C,operator 在 API 层)。
    """
    # R1: llm_* 四键必须齐备(整体保存,不支持只更新一键;缺一整批拒绝)
    provided_llm = LLM_KEYS & payload.keys()
    if provided_llm and provided_llm != LLM_KEYS:
        raise BizError(ErrCode.PLATFORM_SETTING_INVALID, "平台默认模型需完整配置四项")

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
    # R25:审计已在 API 层接入(platform_settings.update,detail 记键列表不记值)
    logger.info("平台设置更新 keys=%s by=%s", updated, updated_by)
    return updated
