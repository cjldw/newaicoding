"""需求 Pydantic 模型 - R3"""

from datetime import date, datetime
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
    # R1 关联用户:项目成员 id 列表,非必填默认 [];非成员 id 由服务层静默剔除
    related_user_ids: Optional[List[str]] = None
    # R4 原型链接:[{label≤20 可空, url http(s)}] ≤10;条数/URL 校验由服务层显式 400
    prototype_links: Optional[List[dict]] = None
    # R5 交付时间:date 类型天然校验非法字符串(422);无「早于今天」限制(PRD 口径)
    delivery_date: Optional[date] = None


class UpdateRequirementRequest(BaseModel):
    """PATCH /api/requirements/{req_id} 请求体(评审中不可编辑由服务层校验)"""
    title: Optional[str] = Field(default=None, min_length=1, max_length=128)
    background: Optional[str] = None
    description: Optional[str] = Field(default=None, min_length=1)
    acceptance_criteria: Optional[str] = None
    priority: Optional[Priority] = None
    # R4 原型链接:不传 = 不动;传 [] = 清空(校验同创建,由服务层做)
    prototype_links: Optional[List[dict]] = None
    # R5 交付时间:None/缺省 → NULL(清空 = 置 NULL);非法字符串由 date 类型 422
    delivery_date: Optional[date] = None


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
    related_user_ids: List[str] = Field(default_factory=list)  # R1 关联用户(空/None 归一为 [])
    prototype_links: List[dict] = Field(default_factory=list)  # R4 原型链接(空/None 归一为 [])
    delivery_date: Optional[date] = None  # R5 交付时间(空 = None,详情侧无值不渲染行由前端处理)
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
