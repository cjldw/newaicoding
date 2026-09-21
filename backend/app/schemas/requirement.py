"""需求 Pydantic 模型 - R3"""

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field

Priority = Literal["low", "medium", "high"]


class CreateRequirementRequest(BaseModel):
    """POST /api/projects/{pid}/requirements 请求体"""
    title: str = Field(min_length=1, max_length=128)
    background: Optional[str] = None
    description: str = Field(min_length=1)
    acceptance_criteria: Optional[str] = None
    priority: Priority = "medium"
    req_branch: Optional[str] = Field(default=None, max_length=64)


class UpdateRequirementRequest(BaseModel):
    """PATCH /api/requirements/{req_id} 请求体(评审中不可编辑由服务层校验)"""
    title: Optional[str] = Field(default=None, min_length=1, max_length=128)
    background: Optional[str] = None
    description: Optional[str] = Field(default=None, min_length=1)
    acceptance_criteria: Optional[str] = None
    priority: Optional[Priority] = None


class ReviewRequest(BaseModel):
    """POST /api/requirements/{req_id}/review 请求体"""
    approved: bool
    reject_reason: Optional[str] = None


class CancelRequest(BaseModel):
    reason: str = Field(min_length=1)


class RequirementCreator(BaseModel):
    user_id: str
    username: str
    nickname: Optional[str] = None


class RequirementListItem(BaseModel):
    req_id: str
    title: str
    status: str
    priority: str
    created_by: RequirementCreator
    created_at: datetime


class RequirementListData(BaseModel):
    items: List[RequirementListItem]
    total: int
    page: int
    page_size: int


class RequirementTaskBrief(BaseModel):
    task_id: str
    type: str
    title: str
    status: str


class RequirementDetailData(BaseModel):
    req_id: str
    title: str
    background: Optional[str] = None
    description: str
    acceptance_criteria: Optional[str] = None
    status: str
    priority: str
    req_branch: str
    prd_file_path: str
    created_by: RequirementCreator
    reviewed_by: Optional[RequirementCreator] = None
    reviewed_at: Optional[datetime] = None
    reject_reason: Optional[str] = None
    polish_task_id: Optional[str] = None
    tasks: List[RequirementTaskBrief]
    created_at: datetime
    updated_at: datetime
