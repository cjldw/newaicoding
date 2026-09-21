"""
R15 网关测试(ASGI 直连网关 app;httpx ASGITransport)
==========================
- 预览鉴权(成员 200 / 非成员 403 / 未登录 403)
- 部署公开访问
- 404 未注册 / 502 Runner offline 页
- deploy_host 冲突(15001)+ Host 含端口匹配
- QPS 限流
- preview host 按 preview_base_domain 拼接(Q28)
"""
import uuid

import httpx
import pytest
import sqlalchemy

from app.core import gateway as gateway_module
from app.core.gateway import create_gateway_app
from app.core.security import create_access_token
from app.models.project import Project
from app.models.route import Route
from app.models.user import User
from app.services import route_service
from app.services.runner_service import runner_registry


class _SingleSessionFactory:
    """把测试 db_session 包成 session factory(网关 handler 用)"""

    def __init__(self, session):
        self.session = session

    def __call__(self):
        # 真实 async_sessionmaker() 返回 AsyncSession(支持 async with);
        # 这里返回自身并实现 async 上下文协议,契约一致。
        return self

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, *args):
        return False


@pytest.fixture
def gateway_client(db_session, monkeypatch):
    """网关 ASGI 测试客户端(注入测试 session factory)"""
    factory = _SingleSessionFactory(db_session)
    monkeypatch.setattr(gateway_module, "async_session_factory", factory)
    app = create_gateway_app(factory)
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://gw")


def _mk_route(db_session, host, project_id, upstream="http://10.0.0.9:21001",
              type="preview", status="active", auth_required=True):
    r = Route(
        host=host, upstream=upstream, type=type,
        task_id=f"task-{uuid.uuid4().hex[:6]}", project_id=project_id,
        port=5173, status=status, auth_required=auth_required,
    )
    db_session.add(r)
    return r


@pytest.mark.asyncio
async def test_preview_host_uses_configured_domain(client, auth_headers, db_session, registered_user, monkeypatch):
    """Q28:preview host 按 preview_base_domain 拼接"""
    await db_session.execute(
        sqlalchemy.text("INSERT INTO platform_settings (`key`, `value`, `updated_by`) VALUES ('preview_base_domain', '\"pv.example.com\"', 't')")
    )
    domain = await route_service.get_preview_base_domain(db_session)
    assert domain == "pv.example.com"


@pytest.mark.asyncio
async def test_preview_auth_required(gateway_client, client, db_session, registered_user, monkeypatch):
    """预览鉴权:非成员 403 / 成员(owner)200 转发"""
    project = Project(
        name="网关项目", slug=f"gw-{uuid.uuid4().hex[:6]}", owner_id=registered_user["user_id"],
    )
    db_session.add(project)
    await db_session.flush()
    host = f"{project.slug}--t1--5173.preview.example.com"
    _mk_route(db_session, host, project.project_id)
    await db_session.flush()

    # 上游 mock(绕过真实 Runner):monkeypatch http client request
    async def fake_request(method, url, **kwargs):
        return httpx.Response(200, text="PREVIEW_OK", headers={"content-type": "text/html"})

    gateway_app = gateway_module.state_holder["app"]
    monkeypatch.setattr(gateway_app.state.gateway.http, "request", fake_request)

    # 未登录 → 403
    resp = await gateway_client.get("/", headers={"host": host})
    assert resp.status_code == 403

    # owner → 200 转发
    user = (await db_session.execute(
        sqlalchemy.select(User).where(User.user_id == registered_user["user_id"])
    )).scalars().first()
    token = create_access_token(user.user_id, user.token_version)
    probe = await route_service.get_by_host(db_session, host)
    print("PROBE pre-call2 route:", probe.status if probe else None)
    resp = await gateway_client.get("/", headers={"host": host}, cookies={"qc_token": token})
    print("PROBE call2:", resp.status_code, resp.text[:80])
    assert resp.status_code == 200
    assert resp.text == "PREVIEW_OK"

    # 非成员 → 403(注册走主应用 client;网关不承载 /api)
    from tests.test_projects_api import _register_and_login
    other_headers, _uid = await _register_and_login(client)
    other_token = other_headers["Authorization"].replace("Bearer ", "")
    resp = await gateway_client.get("/", headers={"host": host}, cookies={"qc_token": other_token})
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_deploy_public_access(gateway_client, db_session, registered_user):
    """部署路由:公开访问(不鉴权)"""
    project = Project(
        name="部署项目", slug=f"dp-{uuid.uuid4().hex[:6]}", owner_id=registered_user["user_id"],
    )
    db_session.add(project)
    await db_session.flush()

    route = await route_service.register_deploy_route(
        db_session,
        project_id=project.project_id, task_id="task-dp",
        container_id="docker-dp", runner_id="r-dp",
        deploy_host=f"{project.slug}.deploy.example.com",
        deploy_port=10080,
        upstream="http://10.0.0.9:22001",
    )
    assert route.auth_required is False

    async def fake(method, url, **kw):
        return httpx.Response(200, text="DEPLOY_OK")

    gw_app = gateway_module.state_holder["app"]
    gw_app.state.gateway.http.request = fake

    resp = await gateway_client.get("/", headers={"host": f"{project.slug}.deploy.example.com:10080"})
    assert resp.status_code == 200
    assert resp.text == "DEPLOY_OK"


@pytest.mark.asyncio
async def test_deploy_host_unique_conflict(db_session, registered_user):
    """deploy_host 全平台唯一:冲突拒绝 15001"""
    project = Project(
        name="p", slug=f"pc-{uuid.uuid4().hex[:6]}", owner_id=registered_user["user_id"],
    )
    db_session.add(project)
    await db_session.flush()

    await route_service.register_deploy_route(
        db_session, project_id=project.project_id, task_id="t1",
        container_id="c1", runner_id="r1",
        deploy_host="app.example.com", deploy_port=10000, upstream="http://10.0.0.1:20001",
    )
    with pytest.raises(Exception) as exc_info:
        await route_service.register_deploy_route(
            db_session, project_id=project.project_id, task_id="t2",
            container_id="c2", runner_id="r1",
            deploy_host="app.example.com", deploy_port=10000, upstream="http://10.0.0.1:20002",
        )
    assert getattr(exc_info.value, "code", None) == 15001


@pytest.mark.asyncio
async def test_not_found_and_offline_502(gateway_client, db_session, registered_user, monkeypatch):
    """未注册 host → 404;上游不可达 → 502 带 Runner offline 提示"""
    project = Project(
        name="离线项目", slug=f"off-{uuid.uuid4().hex[:6]}", owner_id=registered_user["user_id"],
    )
    db_session.add(project)
    await db_session.flush()
    host = f"{project.slug}--t2--5173.preview.example.com"
    _mk_route(db_session, host, project.project_id)
    await db_session.flush()

    # 404(从未注册的 host)
    resp = await gateway_client.get("/", headers={"host": "never-registered.preview.example.com"})
    assert resp.status_code == 404

    # 502(上游连接失败;先带 owner cookie 通过鉴权层)
    user = (await db_session.execute(
        sqlalchemy.select(User).where(User.user_id == registered_user["user_id"])
    )).scalars().first()
    token = create_access_token(user.user_id, user.token_version)

    async def fail_request(method, url, **kwargs):
        raise httpx.ConnectError("down")

    gw_app = gateway_module.state_holder["app"]
    gw_app.state.gateway.http.request = fail_request
    resp = await gateway_client.get("/", headers={"host": host}, cookies={"qc_token": token})
    assert resp.status_code == 502
    assert "Runner offline" in resp.text


@pytest.mark.asyncio
async def test_qps_limit(gateway_client, db_session, registered_user):
    """单 host QPS 上限:超过返回 429"""
    project = Project(
        name="q", slug=f"q-{uuid.uuid4().hex[:6]}", owner_id=registered_user["user_id"],
    )
    db_session.add(project)
    await db_session.flush()
    host = f"{project.slug}--t3--5173.preview.example.com"
    _mk_route(db_session, host, project.project_id)
    await db_session.flush()

    from app.core.gateway import _QpsLimiter

    limiter = _QpsLimiter(limit=3)
    assert limiter.allow(host) is True
    assert limiter.allow(host) is True
    assert limiter.allow(host) is True
    assert limiter.allow(host) is False
    assert limiter.allow("other.host") is True  # 其他 host 不受影响
