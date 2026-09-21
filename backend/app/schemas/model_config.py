"""模型配置 Pydantic 模型 - R13 请求/响应 schema"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# 创建 / 更新 / 测试 请求体
# ---------------------------------------------------------------------------
class CreateModelConfigRequest(BaseModel):
    """POST /api/projects/{pid}/model-configs 请求体"""
    name: str = Field(min_length=1, max_length=64)
    base_url: str = Field(min_length=1, max_length=255)
    api_key: str = Field(min_length=1, max_length=255)
    model: str = Field(min_length=1, max_length=64)
    is_default: bool = False
    enabled: bool = True


class UpdateModelConfigRequest(BaseModel):
    """PATCH /api/projects/{pid}/model-configs/{config_id} 请求体(全部可选)"""
    name: Optional[str] = Field(default=None, min_length=1, max_length=64)
    base_url: Optional[str] = Field(default=None, min_length=1, max_length=255)
    api_key: Optional[str] = Field(default=None, min_length=1, max_length=255)
    model: Optional[str] = Field(default=None, min_length=1, max_length=64)
    is_default: Optional[bool] = None
    enabled: Optional[bool] = None


class TestModelConfigRequest(BaseModel):
    """POST /api/projects/{pid}/model-configs/test 请求体"""
    base_url: str = Field(min_length=1, max_length=255)
    api_key: str = Field(min_length=1, max_length=255)
    model: str = Field(min_length=1, max_length=64)


# ---------------------------------------------------------------------------
# 列表 / 单项响应
# ---------------------------------------------------------------------------
class ModelConfigCreator(BaseModel):
    user_id: str
    username: str


class ModelConfigItem(BaseModel):
    """配置项(api_key 只回打码;viewer 视角无 api_key_masked 字段)"""
    config_id: str
    name: str
    base_url: str
    api_key_masked: Optional[str] = None
    model: str
    is_default: bool
    enabled: bool
    created_by: ModelConfigCreator
    created_at: datetime


class ModelConfigListData(BaseModel):
    items: List[ModelConfigItem]


class TestModelConfigData(BaseModel):
    success: bool
    latency_ms: int
