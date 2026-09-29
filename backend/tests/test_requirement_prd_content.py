"""
R1 PRD 平台副本存储 — Red 阶段失败测试
=====================================
覆盖 DEVPLAN/R1.md「完成判据」表 5 条验证步骤:
1. 列存在 + ORM 模型加列
2. 迁移可升降级(conftest 自动 upgrade head 已覆盖升级;downgrade 手动验证)
3. MEDIUMTEXT 容量(1MB roundtrip)
4. 无 API 直写(PATCH 忽略 prd_content 字段)
5. 存量行兼容读(NULL 容错)

Red 阶段预期:测试失败(列不存在/字段缺失),不是语法错误。
"""
import uuid

import pytest
import sqlalchemy as sa

from app.models.project import Project
from app.models.requirement import Requirement


async def _mk_project_with_req(db_session, owner_id):
    """创建项目 + 需求(参照 test_bug_ui071_archive_500.py)"""
    project = Project(
        name="r1-prd项目",
        slug=f"r1p-{uuid.uuid4().hex[:6]}",
        owner_id=owner_id,
    )
    db_session.add(project)
    await db_session.flush()
    req = Requirement(
        req_id=str(uuid.uuid4()),
        title="PRD副本测试需求",
        description="d",
        status="draft",
        req_branch=f"req-{uuid.uuid4().hex[:8]}",
        created_by=owner_id,
        project_id=project.project_id,
    )
    db_session.add(req)
    await db_session.flush()
    return project, req


# ---------------------------------------------------------------------------
# 验证步骤 1: ORM 模型加列 + 列存在
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_orm_model_has_prd_content_column(db_session):
    """验证步骤 1: Requirement 模型有 prd_content 列,访问不报错"""
    # 尝试访问 prd_content 属性(列不存在会抛 AttributeError)
    assert hasattr(Requirement, "prd_content"), (
        "Requirement 模型缺少 prd_content 列"
    )
    # insert + select roundtrip 验证列实际存在
    req = Requirement(
        req_id=str(uuid.uuid4()),
        title="列存在测试",
        description="d",
        status="draft",
        req_branch=f"req-{uuid.uuid4().hex[:8]}",
        created_by="test-user",
        project_id="test-project",
    )
    db_session.add(req)
    await db_session.flush()
    # 访问 prd_content 应为 None(默认值)
    assert req.prd_content is None, "prd_content 默认值应为 None"


# ---------------------------------------------------------------------------
# 验证步骤 2: 迁移可升降级(列存在断言)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_prd_content_column_exists_in_db(db_session):
    """验证步骤 2: information_schema 断言 prd_content 列存在"""
    result = await db_session.execute(
        sa.text(
            "SELECT COUNT(*) FROM information_schema.columns "
            "WHERE table_schema = DATABASE() "
            "AND table_name = 'requirements' "
            "AND column_name = 'prd_content'"
        )
    )
    count = result.scalar()
    assert count == 1, (
        f"requirements 表应存在 prd_content 列,实际 count={count}"
    )


# ---------------------------------------------------------------------------
# 验证步骤 3: MEDIUMTEXT 容量(1MB roundtrip)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_prd_content_1mb_roundtrip(db_session):
    """验证步骤 3: 写入 100KB 文本 → 读回一致(必须经 DB 层 roundtrip)

    注:MEDIUMTEXT 物理上限 16MB,但 asyncmy 在 Windows 上对大结果集(>500KB)
    有连接丢失问题(Lost connection during query),故测试用 100KB 验证容量足够。
    """
    # 先验证列存在(列不存在时直接 fail,避免误判)
    assert hasattr(Requirement, "prd_content"), (
        "Requirement 模型缺少 prd_content 列,无法验证容量"
    )
    # 生成 100KB 文本(asyncmy Windows 限制,避免 >500KB 触发连接丢失)
    large_content = "A" * (100 * 1024)  # 100KB
    req_id = str(uuid.uuid4())
    # 用 raw SQL 插入(绕过 ORM 属性赋值假象),验证 DB 层真实容量
    await db_session.execute(
        sa.text(
            "INSERT INTO requirements (req_id, project_id, title, description, "
            "req_branch, created_by, status, prd_content) "
            "VALUES (:req_id, :pid, :title, :desc, :branch, :user, 'draft', :content)"
        ),
        {
            "req_id": req_id,
            "pid": "test-project",
            "title": "大容量测试",
            "desc": "d",
            "branch": f"req-{uuid.uuid4().hex[:8]}",
            "user": "test-user",
            "content": large_content,
        },
    )
    await db_session.flush()
    # 用 raw SQL 读回(绕过 ORM 缓存),验证 DB 层 roundtrip
    result = await db_session.execute(
        sa.text("SELECT prd_content FROM requirements WHERE req_id = :req_id"),
        {"req_id": req_id},
    )
    fetched_content = result.scalar()
    assert fetched_content == large_content, (
        f"prd_content DB 层 roundtrip 失败:期望长度 {len(large_content)}, "
        f"实际长度 {len(fetched_content or '')}"
    )


# ---------------------------------------------------------------------------
# 验证步骤 4: 无 API 直写(PATCH 忽略 prd_content)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_patch_ignores_prd_content(client, auth_headers, db_session, registered_user):
    """验证步骤 4: PATCH 带 prd_content 字段 → 200;库里 prd_content 仍为 NULL"""
    project, req = await _mk_project_with_req(db_session, registered_user["user_id"])
    # 确认初始 prd_content 为 NULL
    assert req.prd_content is None, "初始 prd_content 应为 NULL"
    # PATCH 请求体带 prd_content 字段(试图直写)
    resp = await client.patch(
        f"/api/requirements/{req.req_id}",
        headers=auth_headers,
        json={
            "title": "更新标题",
            "prd_content": "hacked content",  # 此字段应被 pydantic 忽略
        },
    )
    # 响应应为 200(pydantic 忽略未知字段,不报错)
    assert resp.status_code == 200, (
        f"PATCH 应返回 200,实际 {resp.status_code}: {resp.text[:200]}"
    )
    # 重新查询数据库,prd_content 应仍为 NULL(未被直写)
    await db_session.refresh(req)
    assert req.prd_content is None, (
        f"prd_content 不应被 PATCH 直写,实际值: {req.prd_content[:50] if req.prd_content else None}"
    )


# ---------------------------------------------------------------------------
# 验证步骤 5: 存量行兼容读(NULL 容错)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_prd_content_null_compatible(db_session):
    """验证步骤 5: 老需求行 prd_content=NULL 读取不报错"""
    # 创建需求,不设置 prd_content(默认 NULL)
    req = Requirement(
        req_id=str(uuid.uuid4()),
        title="存量兼容测试",
        description="d",
        status="draft",
        req_branch=f"req-{uuid.uuid4().hex[:8]}",
        created_by="test-user",
        project_id="test-project",
    )
    db_session.add(req)
    await db_session.flush()
    # 查询并访问 prd_content(NULL 应容错为 None)
    result = await db_session.execute(
        sa.select(Requirement).where(Requirement.req_id == req.req_id)
    )
    fetched_req = result.scalar_one()
    # NULL 容错:访问 prd_content 不报错,返回 None
    assert fetched_req.prd_content is None, (
        "prd_content=NULL 应容错为 None"
    )
    # truthy 判定(代码侧用 truthy 判空)
    assert not fetched_req.prd_content, (
        "prd_content=NULL 应 falsy"
    )
