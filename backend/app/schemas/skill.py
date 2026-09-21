"""Skills Pydantic 模型 - R17 请求/响应 schema"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import UploadFile
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# MCP 配置
# ---------------------------------------------------------------------------
class McpConfigPayload(BaseModel):
    """PUT /api/projects/{pid}/mcp-config 请求体(结构自由,服务层校验 JSON)"""
    model_config = {"extra": "allow"}


class TemplateParam(BaseModel):
    name: str
    type: str  # string / number
    required: bool = True
    default: Optional[Any] = None
    sensitive: bool = False


class McpTemplateItem(BaseModel):
    """MCP 配置模板(前端填参数 → 按 json_template 生成配置)"""
    name: str
    display_name: str
    description: str
    params: List[TemplateParam]
    # 生成的 JSON 骨架:参数以 {{param}} 占位,前端替换后得到完整配置
    json_template: Dict[str, Any]


# ---------------------------------------------------------------------------
# Skills
# ---------------------------------------------------------------------------
class InstallSkillRequest(BaseModel):
    """POST /api/projects/{pid}/skills 请求体"""
    skill_id: str = Field(min_length=1, max_length=36)


class SkillCreator(BaseModel):
    user_id: str
    username: str


class MarketSkillItem(BaseModel):
    """平台级 Skills 市场条目"""
    skill_id: str
    name: str
    description: str
    scope: str
    created_by: SkillCreator
    created_at: datetime


class MarketSkillListData(BaseModel):
    items: List[MarketSkillItem]


class InstalledSkillItem(BaseModel):
    """项目已安装 Skill 条目"""
    skill_id: str
    name: str
    description: str
    scope: str
    installed_by: SkillCreator
    installed_at: datetime


class InstalledSkillListData(BaseModel):
    items: List[InstalledSkillItem]


class UploadSkillData(BaseModel):
    skill_id: str
    name: str
    description: str


class SkillDetailData(BaseModel):
    """Skill 详情(含 content)"""
    skill_id: str
    name: str
    description: str
    content: str
    scope: str


# ---------------------------------------------------------------------------
# 平台级 Skills 管理(超管)
# ---------------------------------------------------------------------------
class AdminCreateSkillRequest(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    description: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1)


class AdminUpdateSkillRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=64)
    description: Optional[str] = Field(default=None, min_length=1, max_length=255)
    content: Optional[str] = None
