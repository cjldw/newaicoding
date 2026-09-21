"""
R10 实时预览测试(平台侧)
==========================
- 端口监听 → 注册路由(host/upstream/status=active)
- 端口关闭 → 路由 inactive
- 容器销毁 → 路由摘除(URL 失效)
- 预览鉴权(非成员 False;成员 True)
- 预览列表接口
"""
import uuid

import pytest
from sqlalchemy import select

from app.models.container import Container
from app.models.project import Project
from app.models.route import Route
from app.services import preview_service, route_service
from app.services.runner_service import runner_registry


async def _setup(db_session, registered_user, runner_host="10.0.0.9"):
    """项目 + running 容器(含端口映射)+ 在线 Runner 连接"""
    from app.services.runner_service import runner_registry

    project = Project(
        name="预览项目", slug=f"pv-{uuid.uuid4().hex[:6]}",
        owner_id=registered_user["user_id"],
    )
    db_session.add(project)
    await db_session.flush()
    task_id = f"task-{uuid.uuid4().hex[:8]}"
    container = Container(
        container_id=f"docker-{uuid.uuid4().hex[:10]}",
        task_id=task_id,
        runner_id="runner-pv",
        project_id=project.project_id,
        status="running",
        exposed_ports=[5173, 8000],
        runner_host_port_5173=21001,
        runner_host_port_8000=21002,
    )
    db_session.add(container)
    await db_session.flush()

    conn = runner_registry.register("runner-pv", "worker", None, runner_host)
    return project, container, conn


@pytest.mark.asyncio
async def test_port_listening_register_route(client, auth_headers, db_session, registered_user):
    """端口监听:注册路由(host/upstream/active)+ 预览列表可见"""
    project, container, conn = await _setup(db_session, registered_user)

    await preview_service.handle_port_listening(db_session, container.container_id, 5173)

    routes = (await db_session.execute(select(Route))).scalars().all()
    assert len(routes) == 1
    route = routes[0]
    assert route.host == f"{project.slug}--{container.task_id}--5173.{await route_service.get_preview_base_domain(db_session)}"
    assert route.upstream == "http://10.0.0.9:21001"
    assert route.status == "active"
    assert route.type == "preview"

    # 预览列表接口(owner 可见)
    resp = await client.get(f"/api/tasks/{container.task_id}/previews", headers=auth_headers)
    items = resp.json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["port"] == 5173
    assert items[0]["status"] == "active"

    runner_registry.unregister("runner-pv")


@pytest.mark.asyncio
async def test_port_closed_unregister_route(client, auth_headers, db_session, registered_user):
    """端口关闭:路由置 inactive(显示"服务未启动")"""
    project, container, conn = await _setup(db_session, registered_user)
    await preview_service.handle_port_listening(db_session, container.container_id, 8000)

    await preview_service.handle_port_closed(db_session, container.container_id, 8000)
    route = (await db_session.execute(select(Route))).scalars().first()
    assert route.status == "inactive"
    runner_registry.unregister("runner-pv")


@pytest.mark.asyncio
async def test_container_destroyed_removes_routes(client, auth_headers, db_session, registered_user):
    """容器销毁:预览路由摘除(URL 失效)"""
    project, container, conn = await _setup(db_session, registered_user)
    await preview_service.handle_port_listening(db_session, container.container_id, 5173)
    assert len((await db_session.execute(select(Route))).scalars().all()) == 1

    await container_service_destroy(db_session, container.container_id)
    assert len((await db_session.execute(select(Route))).scalars().all()) == 0
    runner_registry.unregister("runner-pv")


async def container_service_destroy(db_session, container_id):
    from app.services import container_service

    await container_service.handle_container_stopped(db_session, container_id)


@pytest.mark.asyncio
async def test_preview_auth_required(client, auth_headers, db_session, registered_user):
    """预览鉴权:非成员 False;owner True;未登录 False"""
    from tests.test_projects_api import _register_and_login

    project, container, conn = await _setup(db_session, registered_user)
    await preview_service.handle_port_listening(db_session, container.container_id, 5173)

    owner = await db_session.execute(
        Project.__table__.select().where(Project.project_id == project.project_id)
    )
    _ = owner.first()

    from app.models.user import User

    owner_user = (await db_session.execute(
        User.__table__.select().where(User.user_id == registered_user["user_id"])
    )).mappings().first()

    class _U:
        user_id = owner_user["user_id"]
        role = owner_user["role"]

    host = f"{project.slug}--{container.task_id}--5173.{await route_service.get_preview_base_domain(db_session)}"
    assert await route_service.check_preview_access(db_session, host, _U()) is True

    # 非成员(新注册用户)→ False
    other_headers, other_id = await _register_and_login(client)

    class _U2:
        user_id = other_id
        role = "user"

    assert await route_service.check_preview_access(db_session, host, _U2()) is False
    # 未登录 → False
    assert await route_service.check_preview_access(db_session, host, None) is False
    # 不存在的 host → False
    assert await route_service.check_preview_access(db_session, "no-such.example.com", _U()) is False
    runner_registry.unregister("runner-pv")
