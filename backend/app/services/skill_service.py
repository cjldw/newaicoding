"""Skills 服务 - R17(平台市场/项目安装/上传/卸载/超管 CRUD/任务注入)"""

import logging
import re
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.response import BizError, ErrCode
from app.models.project import Project
from app.models.skill import ProjectSkill, Skill
from app.models.user import User

logger = logging.getLogger(__name__)

_NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


# ---------------------------------------------------------------------------
# frontmatter 解析(避免 pyyaml 依赖,手工解析 frontmatter 头部的 name/description)
# ---------------------------------------------------------------------------
def parse_skill_markdown(content: str) -> tuple[str, str, str]:
    """
    解析 Claude Code Skill 原生格式:
    ---
    name: skill-name
    description: 一句话描述
    ---

    Markdown 正文
    返回 (name, description, body)。
    缺 frontmatter / name / description → BizError(17003)。
    """
    text = content.strip()
    if not text.startswith("---"):
        raise BizError(ErrCode.SKILL_FORMAT_INVALID, "文件格式错误:缺少 YAML frontmatter 的 name 或 description")

    end = text.find("\n---", 3)
    if end == -1:
        raise BizError(ErrCode.SKILL_FORMAT_INVALID, "文件格式错误:缺少 YAML frontmatter 的 name 或 description")

    header = text[3:end]
    body = text[end + 4:].strip()

    name = description = None
    for line in header.splitlines():
        stripped = line.strip()
        if stripped.startswith("name:"):
            name = stripped[len("name:"):].strip().strip("'\"")
        elif stripped.startswith("description:"):
            description = stripped[len("description:"):].strip().strip("'\"")

    if not name or not description:
        raise BizError(ErrCode.SKILL_FORMAT_INVALID, "文件格式错误:缺少 YAML frontmatter 的 name 或 description")

    if not _NAME_RE.match(name):
        raise BizError(ErrCode.SKILL_FORMAT_INVALID, "文件格式错误:name 必须为 kebab-case(小写字母数字与 -)")

    return name, description, body


# ---------------------------------------------------------------------------
# 数据组装
# ---------------------------------------------------------------------------
async def _user_brief(db: AsyncSession, user_id: str) -> dict:
    result = await db.execute(select(User).where(User.user_id == user_id))
    u = result.scalar_one_or_none()
    return {"user_id": user_id, "username": (u.gitlab_username or "") if u else ""}


async def _market_item(db: AsyncSession, skill: Skill) -> dict:
    return {
        "skill_id": skill.skill_id,
        "name": skill.name,
        "description": skill.description,
        "scope": skill.scope,
        "created_by": await _user_brief(db, skill.created_by),
        "created_at": skill.created_at,
    }


# ---------------------------------------------------------------------------
# 市场与详情
# ---------------------------------------------------------------------------
async def list_market_skills(db: AsyncSession) -> list[dict]:
    """平台级 Skills 市场(scope=platform)"""
    result = await db.execute(
        select(Skill)
        .where(Skill.scope == "platform")
        .order_by(Skill.created_at.asc(), Skill.id.asc())
    )
    return [await _market_item(db, s) for s in result.scalars().all()]


async def get_skill_detail(db: AsyncSession, skill_id: str) -> dict:
    """Skill 详情(含 content)"""
    result = await db.execute(select(Skill).where(Skill.skill_id == skill_id))
    skill = result.scalar_one_or_none()
    if skill is None:
        raise BizError(404, "Skill 不存在", status_code=404)
    item = await _market_item(db, skill)
    item["content"] = skill.content
    return item


# ---------------------------------------------------------------------------
# 项目已安装 / 安装 / 上传 / 卸载
# ---------------------------------------------------------------------------
async def list_installed(db: AsyncSession, project: Project) -> list[dict]:
    """项目已安装 Skills(关联 skills 表)"""
    result = await db.execute(
        select(ProjectSkill, Skill)
        .join(Skill, Skill.skill_id == ProjectSkill.skill_id)
        .where(ProjectSkill.project_id == project.project_id)
        .order_by(ProjectSkill.installed_at.asc(), ProjectSkill.id.asc())
    )
    items = []
    for ps, skill in result.all():
        items.append({
            "skill_id": skill.skill_id,
            "name": skill.name,
            "description": skill.description,
            "scope": skill.scope,
            "installed_by": await _user_brief(db, ps.installed_by),
            "installed_at": ps.installed_at,
        })
    return items


async def install_skill(db: AsyncSession, project: Project, operator: User, skill_id: str) -> None:
    """安装平台级 Skill(重复安装 → 17002)"""
    result = await db.execute(select(Skill).where(Skill.skill_id == skill_id))
    skill = result.scalar_one_or_none()
    if skill is None:
        raise BizError(404, "Skill 不存在", status_code=404)

    dup = await db.execute(
        select(ProjectSkill.id).where(
            ProjectSkill.project_id == project.project_id,
            ProjectSkill.skill_id == skill_id,
        ).limit(1)
    )
    if dup.scalar_one_or_none() is not None:
        raise BizError(ErrCode.SKILL_ALREADY_INSTALLED, "已安装过该 Skill")

    db.add(ProjectSkill(
        project_id=project.project_id,
        skill_id=skill_id,
        installed_by=operator.user_id,
    ))
    await db.flush()
    logger.info("安装 Skill project=%s skill=%s by=%s", project.project_id, skill.name, operator.user_id)


async def upload_skill(
    db: AsyncSession,
    project: Project,
    operator: User,
    filename: str,
    content: str,
) -> dict:
    """
    上传项目级自定义 Skill(.md)。
    - 校验 frontmatter(17003)
    - 同项目同名:覆盖式更新内容(V1 无版本管理);同名平台 Skill 不受影响
      (注入时项目级覆盖平台级)
    """
    if not filename.endswith(".md"):
        raise BizError(ErrCode.SKILL_FORMAT_INVALID, "文件格式错误:缺少 YAML frontmatter 的 name 或 description")

    name, description, _body = parse_skill_markdown(content)

    # 同项目同名 → 覆盖更新(V1 覆盖式更新,不做版本管理)
    result = await db.execute(
        select(Skill).where(
            Skill.scope == "project",
            Skill.project_id == project.project_id,
            Skill.name == name,
        )
    )
    skill = result.scalar_one_or_none()
    if skill is not None:
        skill.description = description
        skill.content = content
        await db.flush()
    else:
        skill = Skill(
            name=name,
            description=description,
            content=content,
            scope="project",
            project_id=project.project_id,
            created_by=operator.user_id,
        )
        db.add(skill)
        await db.flush()
        # 上传即安装(写关联)
        db.add(ProjectSkill(
            project_id=project.project_id,
            skill_id=skill.skill_id,
            installed_by=operator.user_id,
        ))
        await db.flush()

    logger.info("上传 Skill project=%s name=%s by=%s", project.project_id, name, operator.user_id)
    return {"skill_id": skill.skill_id, "name": name, "description": description}


async def uninstall_skill(db: AsyncSession, project: Project, operator: User, skill_id: str) -> None:
    """卸载 Skill:仅删除项目关联记录(GitLab/Git 不涉及;Skill 记录保留)"""
    result = await db.execute(
        select(ProjectSkill).where(
            ProjectSkill.project_id == project.project_id,
            ProjectSkill.skill_id == skill_id,
        )
    )
    rel = result.scalar_one_or_none()
    if rel is None:
        raise BizError(404, "该项目未安装此 Skill", status_code=404)

    await db.delete(rel)
    await db.flush()
    logger.info("卸载 Skill project=%s skill=%s by=%s", project.project_id, skill_id, operator.user_id)


# ---------------------------------------------------------------------------
# 平台级 Skills 管理(超管)
# ---------------------------------------------------------------------------
async def admin_create_skill(db: AsyncSession, operator: User, name: str, description: str, content: str) -> dict:
    """超管创建平台级 Skill(platform 作用域内 name 唯一)"""
    if not _NAME_RE.match(name):
        raise BizError(ErrCode.SKILL_FORMAT_INVALID, "name 必须为 kebab-case(小写字母数字与 -)")

    dup = await db.execute(
        select(Skill.id).where(Skill.scope == "platform", Skill.name == name).limit(1)
    )
    if dup.scalar_one_or_none() is not None:
        raise BizError(ErrCode.CONFIG_NAME_DUPLICATE, "同名平台级 Skill 已存在")

    skill = Skill(
        name=name,
        description=description,
        content=content,
        scope="platform",
        project_id=None,
        created_by=operator.user_id,
    )
    db.add(skill)
    await db.flush()
    # created_at 为服务端生成,flush 后过期;显式异步刷新避免 MissingGreenlet
    await db.refresh(skill)
    logger.info("平台 Skill 创建 name=%s by=%s", name, operator.user_id)
    return await _market_item(db, skill)


async def admin_update_skill(db: AsyncSession, operator: User, skill_id: str, req) -> dict:
    """超管更新平台级 Skill"""
    result = await db.execute(
        select(Skill).where(Skill.skill_id == skill_id, Skill.scope == "platform")
    )
    skill = result.scalar_one_or_none()
    if skill is None:
        raise BizError(404, "Skill 不存在", status_code=404)

    if req.name is not None and req.name != skill.name:
        if not _NAME_RE.match(req.name):
            raise BizError(ErrCode.SKILL_FORMAT_INVALID, "name 必须为 kebab-case(小写字母数字与 -)")
        dup = await db.execute(
            select(Skill.id).where(
                Skill.scope == "platform", Skill.name == req.name, Skill.skill_id != skill_id
            ).limit(1)
        )
        if dup.scalar_one_or_none() is not None:
            raise BizError(ErrCode.CONFIG_NAME_DUPLICATE, "同名平台级 Skill 已存在")
        skill.name = req.name
    if req.description is not None:
        skill.description = req.description
    if req.content is not None:
        skill.content = req.content

    await db.flush()
    logger.info("平台 Skill 更新 skill=%s by=%s", skill_id, operator.user_id)
    return await _market_item(db, skill)


async def admin_delete_skill(db: AsyncSession, operator: User, skill_id: str) -> None:
    """超管删除平台级 Skill(级联删安装关联)"""
    result = await db.execute(
        select(Skill).where(Skill.skill_id == skill_id, Skill.scope == "platform")
    )
    skill = result.scalar_one_or_none()
    if skill is None:
        raise BizError(404, "Skill 不存在", status_code=404)

    from sqlalchemy import delete as sa_delete

    await db.execute(sa_delete(ProjectSkill).where(ProjectSkill.skill_id == skill_id))
    await db.delete(skill)
    await db.flush()
    logger.info("平台 Skill 删除 skill=%s by=%s", skill_id, operator.user_id)


# ---------------------------------------------------------------------------
# 注入(R8 任务创建时消费)
# ---------------------------------------------------------------------------
async def list_project_skill_contents(db: AsyncSession, project_id: str) -> List[dict]:
    """
    任务创建链路:项目已安装 Skills 的内容列表 [{name, content}]。
    调用方写入容器 ~/.claude/skills/{name}.md(项目级覆盖镜像预装同名;
    平台与项目同名的,项目级 Skill 排在后面写入即覆盖)。
    """
    result = await db.execute(
        select(Skill)
        .join(ProjectSkill, ProjectSkill.skill_id == Skill.skill_id)
        .where(ProjectSkill.project_id == project_id)
        .order_by(Skill.scope.asc(), Skill.id.asc())  # 升序:platform 在前、project 在后,写入容器时后写覆盖(项目级覆盖同名)
    )
    return [{"name": s.name, "content": s.content} for s in result.scalars().all()]
