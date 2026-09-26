"""项目路由 - R2 项目管理(列表/创建/详情/更新/删除/归档/仓库绑定解绑)"""

from fastapi import APIRouter, Depends, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import get_current_user
from app.core.response import BizError, ErrCode, success
from app.database import get_db
from app.models.user import User
from app.schemas.project import (
    AddRepoRequest,
    CreateProjectRequest,
    UpdateProjectRequest,
)
from app.schemas.project_member import (
    ChangeRoleRequest,
    InviteMemberRequest,
    TransferOwnershipRequest,
)
from app.schemas.model_config import (
    CreateModelConfigRequest,
    TestModelConfigRequest,
    UpdateModelConfigRequest,
)
from app.schemas.skill import InstallSkillRequest
from app.services import (
    llm_service,
    mcp_service,
    model_config_service,
    project_member_service,
    project_service,
    skill_service,
)

router = APIRouter(prefix="/api/projects", tags=["项目"])


# -------------------------------------------------------------------
# GET /api/projects - 项目列表(分页)
# -------------------------------------------------------------------
@router.get("")
async def list_projects(
    status: str = Query(default="active"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """项目列表(口径:我创建的项目;status=active 默认)"""
    data = await project_service.list_projects(db, current_user, status, page, page_size)
    return success(data=data)


# -------------------------------------------------------------------
# POST /api/projects - 创建项目(auto/manual 绑定主仓库)
# -------------------------------------------------------------------
@router.post("")
async def create_project(
    req: CreateProjectRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """创建项目并绑定主仓库;成功返回 project_id/slug/main_repo"""
    data = await project_service.create_project(db, current_user, req)
    return success(data=data, message="项目创建成功")


# -------------------------------------------------------------------
# GET /api/projects/{project_id} - 项目详情
# -------------------------------------------------------------------
@router.get("/{project_id}")
async def get_project(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """项目详情(owner/成员/超管/internal 可见;private 非成员 404)"""
    project = await project_service.get_project_or_404(db, project_id)
    from app.services.project_member_service import get_project_role

    role = await get_project_role(db, project, current_user)
    project_service._ensure_can_view(project, current_user, role)
    data = await project_service.build_detail(db, project)
    return success(data=data)


# -------------------------------------------------------------------
# PATCH /api/projects/{project_id} - 更新项目
# -------------------------------------------------------------------
@router.patch("/{project_id}")
async def update_project(
    project_id: str,
    req: UpdateProjectRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """更新项目(name/description/default_branch/visibility;仅 owner)"""
    data = await project_service.update_project(db, current_user, project_id, req)
    return success(data=data, message="更新成功")


# -------------------------------------------------------------------
# DELETE /api/projects/{project_id} - 删除项目(软删 7 天)
# -------------------------------------------------------------------
@router.delete("/{project_id}")
async def delete_project(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """软删项目(status=deleted,列表隐藏;7 天后物理删除,不动 GitLab repo)"""
    await project_service.delete_project(db, current_user, project_id)
    return success(message="项目已删除(软删,7天后物理删除)")


# -------------------------------------------------------------------
# POST /api/projects/{project_id}/archive - 归档项目
# -------------------------------------------------------------------
@router.post("/{project_id}/archive")
async def archive_project(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """归档项目(只读;容器停止/部署下线在 R8/R7 联动)"""
    await project_service.archive_project(db, current_user, project_id)
    return success(message="项目已归档")


# -------------------------------------------------------------------
# POST /api/projects/{project_id}/repos - 追加绑定仓库
# -------------------------------------------------------------------
@router.post("/{project_id}/repos")
async def add_repo(
    project_id: str,
    req: AddRepoRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """追加绑定仓库(test/docs/other;bot 校验权限;同 repo 不可重复绑定)"""
    data = await project_service.add_repo(db, current_user, project_id, req)
    return success(data=data, message="仓库绑定成功")


# -------------------------------------------------------------------
# DELETE /api/projects/{project_id}/repos/{repo_id} - 解绑仓库
# -------------------------------------------------------------------
@router.delete("/{project_id}/repos/{repo_id}")
async def unbind_repo(
    project_id: str,
    repo_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """解绑仓库(main 不可解绑;解绑后不动 GitLab repo)"""
    await project_service.unbind_repo(db, current_user, project_id, repo_id)
    return success(message="仓库已解绑")


# ===================================================================
# R12 项目成员与协作
# ===================================================================

# -------------------------------------------------------------------
# GET /api/projects/{project_id}/members - 成员列表
# -------------------------------------------------------------------
@router.get("/{project_id}/members")
async def list_members(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """成员列表(项目成员可见;owner 行懒回填)"""
    project = await project_service.get_project_or_404(db, project_id)
    items = await project_member_service.list_members(db, project, current_user)
    return success(data={"items": items})


# -------------------------------------------------------------------
# GET /api/projects/{project_id}/candidate-users - 候选用户列表(R1 成员批量邀请)
# -------------------------------------------------------------------
@router.get("/{project_id}/candidate-users")
async def list_candidate_users(
    project_id: str,
    q: str = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """候选用户列表(owner/超管;全量平台用户分页+phone/nickname 模糊;is_member/status 供前端禁选)"""
    project = await project_service.get_project_or_404(db, project_id)
    data = await project_member_service.list_candidate_users(db, project, current_user, q, page, page_size)
    return success(data=data)


# -------------------------------------------------------------------
# POST /api/projects/{project_id}/members - 邀请成员(手机号精确搜索)
# -------------------------------------------------------------------
@router.post("/{project_id}/members")
async def invite_member(
    project_id: str,
    req: InviteMemberRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """owner 邀请已注册用户为 editor/viewer;同步加到所有绑定 repo"""
    project = await project_service.get_project_or_404(db, project_id)
    data = await project_member_service.invite_member(db, project, current_user, req.phone, req.role)
    return success(data=data, message="邀请成功")


# -------------------------------------------------------------------
# DELETE /api/projects/{project_id}/members/{member_user_id} - 移除成员
# -------------------------------------------------------------------
@router.delete("/{project_id}/members/{member_user_id}")
async def remove_member(
    project_id: str,
    member_user_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """owner 移除成员(最后一个 owner 不可移除);同步从所有绑定 repo 移除"""
    project = await project_service.get_project_or_404(db, project_id)
    await project_member_service.remove_member(db, project, current_user, member_user_id)
    return success(message="成员已移除")


# -------------------------------------------------------------------
# PATCH /api/projects/{project_id}/members/{member_user_id} - 改角色
# -------------------------------------------------------------------
@router.patch("/{project_id}/members/{member_user_id}")
async def change_member_role(
    project_id: str,
    member_user_id: str,
    req: ChangeRoleRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """owner 改成员角色(owner/editor/viewer);同步 GitLab access_level"""
    project = await project_service.get_project_or_404(db, project_id)
    data = await project_member_service.change_member_role(db, project, current_user, member_user_id, req.role)
    return success(data=data, message="角色已更新")


# -------------------------------------------------------------------
# POST /api/projects/{project_id}/transfer-ownership - 转让 owner
# -------------------------------------------------------------------
@router.post("/{project_id}/transfer-ownership")
async def transfer_ownership(
    project_id: str,
    req: TransferOwnershipRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """owner 转让(目标必须是成员);原 owner 降为 editor"""
    project = await project_service.get_project_or_404(db, project_id)
    await project_member_service.transfer_ownership(db, project, current_user, req.new_owner_user_id)
    return success(message="转让成功,您已降为 editor")


# ===================================================================
# R13 模型接入(项目级 url+key,主/备多组)
# ===================================================================

# -------------------------------------------------------------------
# GET /api/projects/{project_id}/model-configs - 配置列表
# -------------------------------------------------------------------
@router.get("/{project_id}/model-configs")
async def list_model_configs(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """成员可看;viewer 视角不含 api_key 字段(打码也不回)"""
    project = await project_service.get_project_or_404(db, project_id)
    role = await project_member_service.get_project_role(db, project, current_user)
    if not role and project.visibility != "internal":
        raise BizError(404, "项目不存在", status_code=404)
    items = await model_config_service.list_configs(db, project, role or "viewer")
    return success(data={"items": items})


# -------------------------------------------------------------------
# GET /api/projects/{project_id}/model-configs/resolvable - 生效配置查询(R23)
# -------------------------------------------------------------------
@router.get("/{project_id}/model-configs/resolvable")
async def get_resolvable_model_config(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """回退链当前生效配置(project/platform/none);成员可读(含 viewer);api_key 仅打码"""
    project = await project_service.get_project_or_404(db, project_id)
    role = await project_member_service.get_project_role(db, project, current_user)
    if not role and project.visibility != "internal":
        raise BizError(404, "项目不存在", status_code=404)
    try:
        resolved = await llm_service.resolve_config(db, project.project_id)
    except BizError:
        # 13005(项目与平台均未配置)→ none 态:不抛错,供前端做入口禁用与提示判定
        return success(data={
            "effective_source": "none",
            "base_url": None,
            "model": None,
            "api_key_masked": None,
        })
    return success(data={
        "effective_source": resolved.get("source", "project"),
        "base_url": resolved["base_url"],
        "model": resolved["model"],
        "api_key_masked": model_config_service.mask_api_key(resolved["api_key"]),
    })


# -------------------------------------------------------------------
# POST /api/projects/{project_id}/model-configs - 创建配置
# -------------------------------------------------------------------
@router.post("/{project_id}/model-configs")
async def create_model_config(
    project_id: str,
    req: CreateModelConfigRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """owner 创建;保存前连通性测试(13001);重名 13002;default 冲突 13003"""
    project = await project_service.get_project_or_404(db, project_id)
    await project_member_service.require_project_role(db, project, current_user, "owner")
    data = await model_config_service.create_config(db, project, current_user, req)
    return success(data=data, message="配置创建成功")


# -------------------------------------------------------------------
# POST /api/projects/{project_id}/model-configs/test - 连通性测试
# -------------------------------------------------------------------
@router.post("/{project_id}/model-configs/test")
async def test_model_config(
    project_id: str,
    req: TestModelConfigRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """owner 测试连接(GET {base_url}/models);失败 13001"""
    project = await project_service.get_project_or_404(db, project_id)
    await project_member_service.require_project_role(db, project, current_user, "owner")
    data = await llm_service.test_connectivity(req.base_url, req.api_key, req.model)
    return success(data=data, message=f"连接成功({data['latency_ms']}ms)")


# -------------------------------------------------------------------
# PATCH /api/projects/{project_id}/model-configs/{config_id} - 更新配置
# -------------------------------------------------------------------
@router.patch("/{project_id}/model-configs/{config_id}")
async def update_model_config(
    project_id: str,
    config_id: str,
    req: UpdateModelConfigRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """owner 更新;api_key 重加密;连接要素变更重测;default 冲突 13003"""
    project = await project_service.get_project_or_404(db, project_id)
    await project_member_service.require_project_role(db, project, current_user, "owner")
    data = await model_config_service.update_config(db, project, current_user, config_id, req)
    return success(data=data, message="配置更新成功")


# -------------------------------------------------------------------
# DELETE /api/projects/{project_id}/model-configs/{config_id} - 删除配置
# -------------------------------------------------------------------
@router.delete("/{project_id}/model-configs/{config_id}")
async def delete_model_config(
    project_id: str,
    config_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """owner 删除;default 不可删(13004,需先指定新 default)"""
    project = await project_service.get_project_or_404(db, project_id)
    await project_member_service.require_project_role(db, project, current_user, "owner")
    await model_config_service.delete_config(db, project, current_user, config_id)
    return success(message="配置已删除")


# ===================================================================
# R17 MCP 配置 + Skills 管理(项目侧)
# ===================================================================

# -------------------------------------------------------------------
# GET /api/projects/{project_id}/mcp-config - 获取 MCP 配置(打码)
# -------------------------------------------------------------------
@router.get("/{project_id}/mcp-config")
async def get_mcp_config(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """项目成员可看;敏感信息打码(前 4 + *** + 后 4)"""
    project = await project_service.get_project_or_404(db, project_id)
    await project_member_service.require_project_role(db, project, current_user, "viewer")
    config = await mcp_service.get_config_masked(db, project)
    return success(data={"config": config})


# -------------------------------------------------------------------
# PUT /api/projects/{project_id}/mcp-config - 更新 MCP 配置
# -------------------------------------------------------------------
@router.put("/{project_id}/mcp-config")
async def put_mcp_config(
    project_id: str,
    payload: dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """owner 保存;结构校验(17001)→ AES-GCM 加密落库;任务创建时解密注入容器"""
    project = await project_service.get_project_or_404(db, project_id)
    await project_member_service.require_project_role(db, project, current_user, "owner")
    config_json = payload.get("config")
    if config_json is None:
        raise BizError(ErrCode.MCP_JSON_INVALID, "JSON 格式错误:缺少 config 字段")
    await mcp_service.save_config(db, project, config_json)
    return success(message="保存成功")


# -------------------------------------------------------------------
# GET /api/projects/{project_id}/mcp-config/templates - 模板列表
# -------------------------------------------------------------------
@router.get("/{project_id}/mcp-config/templates")
async def list_mcp_templates(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """常用 MCP server 模板(前端填参数 → 按 json_template 生成配置填入编辑器)"""
    project = await project_service.get_project_or_404(db, project_id)
    await project_member_service.require_project_role(db, project, current_user, "viewer")
    return success(data={"items": mcp_service.MCP_TEMPLATES})


# -------------------------------------------------------------------
# GET /api/projects/{project_id}/skills - 项目已安装 Skills
# -------------------------------------------------------------------
@router.get("/{project_id}/skills")
async def list_project_skills(
    project_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """项目成员可看已安装 Skills 列表"""
    project = await project_service.get_project_or_404(db, project_id)
    await project_member_service.require_project_role(db, project, current_user, "viewer")
    items = await skill_service.list_installed(db, project)
    return success(data={"items": items})


# -------------------------------------------------------------------
# POST /api/projects/{project_id}/skills - 安装平台级 Skill
# -------------------------------------------------------------------
@router.post("/{project_id}/skills")
async def install_project_skill(
    project_id: str,
    req: InstallSkillRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """owner/editor 安装;重复安装 17002"""
    project = await project_service.get_project_or_404(db, project_id)
    await project_member_service.require_project_role(db, project, current_user, "editor")
    await skill_service.install_skill(db, project, current_user, req.skill_id)
    return success(message="安装成功")


# -------------------------------------------------------------------
# POST /api/projects/{project_id}/skills/upload - 上传项目级自定义 Skill
# -------------------------------------------------------------------
@router.post("/{project_id}/skills/upload")
async def upload_project_skill(
    project_id: str,
    file: UploadFile,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """owner/editor 上传 .md(校验 frontmatter,17003);上传即安装"""
    project = await project_service.get_project_or_404(db, project_id)
    await project_member_service.require_project_role(db, project, current_user, "editor")
    raw = await file.read()
    try:
        content = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise BizError(ErrCode.SKILL_FORMAT_INVALID, "文件格式错误:必须为 UTF-8 编码的 .md 文件")
    data = await skill_service.upload_skill(db, project, current_user, file.filename or "", content)
    return success(data=data, message="上传成功")


# -------------------------------------------------------------------
# DELETE /api/projects/{project_id}/skills/{skill_id} - 卸载 Skill
# -------------------------------------------------------------------
@router.delete("/{project_id}/skills/{skill_id}")
async def uninstall_project_skill(
    project_id: str,
    skill_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """owner/editor 卸载(删关联记录)"""
    project = await project_service.get_project_or_404(db, project_id)
    await project_member_service.require_project_role(db, project, current_user, "editor")
    await skill_service.uninstall_skill(db, project, current_user, skill_id)
    return success(message="卸载成功")
