"""MCP 配置服务 - R17 项目级 MCP server 配置(加密存储/打码回显/模板)

- 存储链路:前端 JSON → 校验(json.loads,错误携带行号)→ AES-256-GCM 加密
  → projects.mcp_config_encrypted(R2 已建列)
- 读取链路:解密 → 敏感值打码 → 返回
- 注入链路(R8 消费):get_decrypted_config() → 与镜像预装合并(项目级覆盖同名)
  → 写容器 ~/.claude/config.json
"""

import json
import logging
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.encryption import decrypt_token, encrypt_token
from app.core.response import BizError, ErrCode
from app.models.project import Project

logger = logging.getLogger(__name__)

# 敏感关键词:出现这些关键词的值在接口返回时打码(前 4 + *** + 后 4)
SENSITIVE_KEYWORDS = ("password", "token", "key", "secret", "passwd", "pwd")

# ---------------------------------------------------------------------------
# 常用 MCP server 模板(json_template 中 {{param}} 由前端替换)
# ---------------------------------------------------------------------------
MCP_TEMPLATES: list[dict] = [
    {
        "name": "postgres",
        "display_name": "PostgreSQL",
        "description": "PostgreSQL 数据库",
        "params": [
            {"name": "host", "type": "string", "required": True},
            {"name": "port", "type": "number", "required": True, "default": 5432},
            {"name": "user", "type": "string", "required": True},
            {"name": "password", "type": "string", "required": True, "sensitive": True},
            {"name": "database", "type": "string", "required": True},
        ],
        "json_template": {
            "mcpServers": {
                "postgres": {
                    "command": "npx",
                    "args": [
                        "-y",
                        "@modelcontextprotocol/server-postgres",
                        "postgresql://{{user}}:{{password}}@{{host}}:{{port}}/{{database}}",
                    ],
                }
            }
        },
    },
    {
        "name": "redis",
        "display_name": "Redis",
        "description": "Redis 缓存数据库",
        "params": [
            {"name": "host", "type": "string", "required": True},
            {"name": "port", "type": "number", "required": True, "default": 6379},
            {"name": "password", "type": "string", "required": False, "sensitive": True},
        ],
        "json_template": {
            "mcpServers": {
                "redis": {
                    "command": "npx",
                    "args": ["-y", "@modelcontextprotocol/server-redis", "redis://{{host}}:{{port}}"],
                }
            }
        },
    },
    {
        "name": "github",
        "display_name": "GitHub",
        "description": "GitHub 仓库操作(注意:平台 V1 仅对接 GitLab,此模板用于任务内访问 GitHub)",
        "params": [
            {"name": "token", "type": "string", "required": True, "sensitive": True},
        ],
        "json_template": {
            "mcpServers": {
                "github": {
                    "command": "npx",
                    "args": ["-y", "@modelcontextprotocol/server-github"],
                    "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": "{{token}}"},
                }
            }
        },
    },
    {
        "name": "slack",
        "display_name": "Slack",
        "description": "Slack 消息通道",
        "params": [
            {"name": "bot_token", "type": "string", "required": True, "sensitive": True},
            {"name": "team_id", "type": "string", "required": True},
        ],
        "json_template": {
            "mcpServers": {
                "slack": {
                    "command": "npx",
                    "args": ["-y", "@modelcontextprotocol/server-slack"],
                    "env": {
                        "SLACK_BOT_TOKEN": "{{bot_token}}",
                        "SLACK_TEAM_ID": "{{team_id}}",
                    },
                }
            }
        },
    },
]


# ---------------------------------------------------------------------------
# 校验与打码
# ---------------------------------------------------------------------------
def validate_and_encode(config_json: Any) -> str:
    """
    PUT 保存链路:JSON 结构校验(非法抛 17001,携带行号)→ 序列化 → AES-GCM 加密。
    config_json 已由 FastAPI 解析为 dict/list(传输层保证合法 JSON),
    这里补结构校验:mcpServers 必须是对象字典。
    """
    if not isinstance(config_json, dict):
        raise BizError(ErrCode.MCP_JSON_INVALID, "JSON 格式错误:根节点必须为对象")
    servers = config_json.get("mcpServers", {})
    if not isinstance(servers, dict):
        # 行号信息:整体结构错误定位为第 1 行(细粒度行号仅对纯文本解析有意义)
        raise BizError(ErrCode.MCP_JSON_INVALID, "JSON 格式错误:第 1 行 mcpServers 必须为对象")
    for server_name, server_cfg in servers.items():
        if not isinstance(server_cfg, dict):
            raise BizError(
                ErrCode.MCP_JSON_INVALID,
                f"JSON 格式错误:mcpServers.{server_name} 必须为对象",
            )
    payload = json.dumps(config_json, ensure_ascii=False)
    return encrypt_token(payload)


def parse_config_text(text: str) -> Any:
    """前端原始文本解析(保留行号错误信息用;API 层已由 Pydantic 解析时一般走不到)"""
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise BizError(ErrCode.MCP_JSON_INVALID, f"JSON 格式错误:第 {e.lineno} 行")


def _mask_value(value: str) -> str:
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}***{value[-4:]}"


def _is_sensitive(text: str) -> bool:
    lowered = text.lower()
    return any(k in lowered for k in SENSITIVE_KEYWORDS)


def mask_config(config: dict) -> dict:
    """
    GET 回显链路:遍历 mcpServers 的 args(list)与 env(dict),
    值/键含敏感关键词 → 打码(前 4 + *** + 后 4)。
    """
    import copy

    masked = copy.deepcopy(config)
    for server_cfg in (masked.get("mcpServers") or {}).values():
        if not isinstance(server_cfg, dict):
            continue
        args = server_cfg.get("args")
        if isinstance(args, list):
            server_cfg["args"] = [
                _mask_value(a) if isinstance(a, str) and _is_sensitive(a) else a for a in args
            ]
        env = server_cfg.get("env")
        if isinstance(env, dict):
            server_cfg["env"] = {
                k: (_mask_value(str(v)) if _is_sensitive(k) else v) for k, v in env.items()
            }
    return masked


# ---------------------------------------------------------------------------
# 读写(R17 接口用)
# ---------------------------------------------------------------------------
async def get_config_masked(db: AsyncSession, project: Project) -> Optional[dict]:
    """读取项目 MCP 配置(解密后打码);未配置返回 None"""
    if not project.mcp_config_encrypted:
        return None
    try:
        config = json.loads(decrypt_token(project.mcp_config_encrypted))
    except Exception:
        logger.warning("MCP 配置解密失败 project=%s", project.project_id)
        return None
    return mask_config(config)


async def save_config(db: AsyncSession, project: Project, config_json: dict) -> None:
    """保存项目 MCP 配置(校验 + 加密落库)"""
    project.mcp_config_encrypted = validate_and_encode(config_json)
    await db.flush()
    logger.info("MCP 配置保存 project=%s", project.project_id)


# ---------------------------------------------------------------------------
# 注入(R8 任务创建时消费)
# ---------------------------------------------------------------------------
async def get_decrypted_config(db: AsyncSession, project: Project) -> Optional[dict]:
    """
    任务创建链路:解密项目级 MCP 配置(不打码)。
    调用方与镜像预装的 ~/.claude/config.json 合并(项目级覆盖同名 server)。
    """
    if not project.mcp_config_encrypted:
        return None
    try:
        return json.loads(decrypt_token(project.mcp_config_encrypted))
    except Exception:
        logger.warning("MCP 配置解密失败(注入时跳过)project=%s", project.project_id)
        return None
