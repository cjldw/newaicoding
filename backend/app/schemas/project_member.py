"""项目成员 Pydantic 模型 - R12 请求/响应 schema"""

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


MemberRole = Literal["owner", "editor", "viewer"]


# ---------------------------------------------------------------------------
# 邀请 / 改角色 / 转让 请求体
# ---------------------------------------------------------------------------
class InviteMemberRequest(BaseModel):
    """POST /api/projects/{pid}/members 请求体(手机号精确搜索,后端按 phone 查 users)"""
    phone: str = Field(min_length=1, max_length=11)
    role: Literal["editor", "viewer"]  # 邀请只能给 editor/viewer;owner 通过转让产生


class BatchInviteMemberRequest(BaseModel):
    """POST /api/projects/{pid}/members/batch 请求体(R2 批量邀请;整体事务)
    非空/≤50/含重复在 service 预检校验(违反 → 400 整批拒绝,不做静默去重)"""
    user_ids: List[str] = Field(default_factory=list)
    role: Literal["editor", "viewer"]  # 与单邀请同:只能 editor/viewer


class ChangeRoleRequest(BaseModel):
    """PATCH /api/projects/{pid}/members/{user_id} 请求体"""
    role: MemberRole


class TransferOwnershipRequest(BaseModel):
    """POST /api/projects/{pid}/transfer-ownership 请求体"""
    new_owner_user_id: str = Field(min_length=1, max_length=36)


# ---------------------------------------------------------------------------
# 成员列表 / 单项
# ---------------------------------------------------------------------------
class InvitedByBrief(BaseModel):
    """邀请人摘要"""
    user_id: str
    username: str


class MemberItem(BaseModel):
    """成员列表条目"""
    user_id: str
    username: str
    nickname: Optional[str] = None
    avatar_url: Optional[str] = None
    role: str
    invited_by: InvitedByBrief
    joined_at: datetime


class MemberListData(BaseModel):
    """GET /api/projects/{pid}/members 响应 data"""
    items: List[MemberItem]


class InviteMemberData(BaseModel):
    """POST /api/projects/{pid}/members 响应 data"""
    user_id: str
    username: str
    role: str


class ChangeRoleData(BaseModel):
    """PATCH 响应 data(同成员列表项)"""
    user_id: str
    username: str
    nickname: Optional[str] = None
    avatar_url: Optional[str] = None
    role: str
    invited_by: InvitedByBrief
    joined_at: datetime
