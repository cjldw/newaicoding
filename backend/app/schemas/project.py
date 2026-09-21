"""项目 Pydantic 模型 - R2 请求/响应 schema"""

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# 创建项目
# ---------------------------------------------------------------------------
class MainRepoBind(BaseModel):
    """主仓库绑定参数"""
    bind_type: Literal["auto", "manual"] = "auto"
    # manual 时必填(服务层校验)
    gitlab_repo_url: Optional[str] = None


class CreateProjectRequest(BaseModel):
    """POST /api/projects 请求体"""
    name: str = Field(min_length=1, max_length=64)
    description: Optional[str] = Field(default=None, max_length=255)
    visibility: Literal["private", "internal"] = "private"
    default_branch: str = Field(default="master", max_length=64)
    main_repo: MainRepoBind = MainRepoBind()


class MainRepoBrief(BaseModel):
    """创建响应中的主仓库摘要"""
    repo_id: str
    gitlab_repo_url: str
    gitlab_repo_id: int


class CreateProjectResponse(BaseModel):
    """POST /api/projects 响应 data"""
    project_id: str
    slug: str
    main_repo: MainRepoBrief


# ---------------------------------------------------------------------------
# 项目列表
# ---------------------------------------------------------------------------
class ProjectOwnerBrief(BaseModel):
    """项目 owner 摘要"""
    user_id: str
    username: str
    nickname: Optional[str] = None


class ProjectListItem(BaseModel):
    """项目列表条目"""
    project_id: str
    name: str
    slug: str
    description: Optional[str] = None
    status: str
    owner: ProjectOwnerBrief
    repo_count: int
    created_at: datetime


class ProjectListData(BaseModel):
    """GET /api/projects 响应 data(分页)"""
    items: List[ProjectListItem]
    total: int
    page: int
    page_size: int


# ---------------------------------------------------------------------------
# 仓库
# ---------------------------------------------------------------------------
class RepoItem(BaseModel):
    """项目详情中的仓库条目"""
    repo_id: str
    role: str
    gitlab_repo_url: str
    gitlab_repo_id: int
    gitlab_bind_type: str


class RepoBindResponse(BaseModel):
    """POST /api/projects/{pid}/repos 响应 data"""
    repo_id: str
    role: str
    gitlab_repo_url: str
    gitlab_repo_id: int


class AddRepoRequest(BaseModel):
    """POST /api/projects/{pid}/repos 请求体(main 不允许经此接口绑定)"""
    role: Literal["test", "docs", "other"]
    gitlab_repo_url: str = Field(min_length=1, max_length=255)


# ---------------------------------------------------------------------------
# 项目详情 / 更新
# ---------------------------------------------------------------------------
class ProjectDetailData(BaseModel):
    """GET /api/projects/{pid} 响应 data"""
    project_id: str
    name: str
    slug: str
    description: Optional[str] = None
    status: str
    visibility: str
    default_branch: str
    owner: ProjectOwnerBrief
    repos: List[RepoItem]
    created_at: datetime
    updated_at: datetime


class UpdateProjectRequest(BaseModel):
    """PATCH /api/projects/{pid} 请求体(全部可选)"""
    name: Optional[str] = Field(default=None, min_length=1, max_length=64)
    description: Optional[str] = Field(default=None, max_length=255)
    default_branch: Optional[str] = Field(default=None, max_length=64)
    visibility: Optional[Literal["private", "internal"]] = None


# ---------------------------------------------------------------------------
# 平台设置
# ---------------------------------------------------------------------------
class UpdatePlatformSettingsRequest(BaseModel):
    """PUT /api/admin/platform-settings 请求体(部分更新,{key: value})"""
    model_config = {"extra": "allow"}

    # 字段不声明,由服务层做白名单 + 类型校验(extra 保留原始 dict)
