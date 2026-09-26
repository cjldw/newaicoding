"""Runner 管理 Pydantic 模型 - R16"""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class CreateRunnerRequest(BaseModel):
    """POST /api/admin/runners 请求体"""
    name: str = Field(min_length=1, max_length=64)
    role: Literal["worker", "deploy"] = "worker"
    max_containers: int = Field(default=10, ge=1, le=100)
    # deploy 时必填(服务层校验)
    public_ip: Optional[str] = Field(default=None, max_length=64)
    # R32:任务类型标签(空/缺省=通用兜底;服务层 validate_tags 校验)
    tags: Optional[list[str]] = None


class CreateRunnerData(BaseModel):
    runner_id: str
    name: str
    token: str


class ResetTokenData(BaseModel):
    token: str


class RunnerItem(BaseModel):
    """Runner 列表项"""
    runner_id: str
    name: str
    role: str
    status: str
    last_heartbeat_at: Optional[datetime] = None
    machine_info: Optional[dict] = None
    current_containers: int
    max_containers: int
    public_ip: Optional[str] = None
    is_local: bool = False  # R31:本机快速创建标记
    tags: list[str] = []  # R32:任务类型标签(恒数组,NULL 存量折 [])
    created_at: datetime


class RunnerListData(BaseModel):
    items: list[RunnerItem]
