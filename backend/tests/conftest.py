"""
R1 用户认证系统 — pytest 公共 fixture
=====================================
- event loop 管理(asyncio)
- httpx.AsyncClient 工厂(挂载到 FastAPI app)
- 测试隔离:每个测试前 truncate users 表
- 数据库 session 管理(async SQLAlchemy)

使用 .env 中配置的 MySQL 开发库(alembic 已 upgrade)。
"""
import asyncio
import os
import httpx
import pytest
import pytest_asyncio

# ---------------------------------------------------------------------------
# 环境变量(测试用,在 import app 模块之前设置)
# 注意: 不覆盖 DATABASE_URL,使用 .env 中已配置的 MySQL 开发库
# ---------------------------------------------------------------------------
os.environ.setdefault("JWT_SECRET_KEY", "test-jwt-secret-key-for-testing-only")
os.environ.setdefault(
    "PLATFORM_SECRET_KEY",
    "dGVzdC1wbGF0Zm9ybS1zZWNyZXQta2V5LTM1Ynl0ZXMh"  # base64(32 bytes)
)
os.environ.setdefault("GITLAB_INSTANCE_URL", "https://gitlab.example.com")

# ---------------------------------------------------------------------------
# event loop 策略:Windows 下用 ProactorEventLoop
# ---------------------------------------------------------------------------
if os.name == "nt":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())


# ---------------------------------------------------------------------------
# event loop fixture(pytest-asyncio)
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def event_loop_policy():
    """使用默认 event loop policy"""
    return asyncio.DefaultEventLoopPolicy()


@pytest.fixture(scope="session")
def event_loop():
    """创建 session 级别的 event loop,避免每个 test 重建"""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# ---------------------------------------------------------------------------
# 数据库 engine + session(使用 .env 中配置的 MySQL 开发库)
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture
async def engine():
    """
    创建 async SQLAlchemy engine(每个测试函数级)。
    使用 app 自身的 engine,确保与 app 代码共享同一个连接池。
    改为 function scope 避免 pytest-asyncio event loop 冲突。
    """
    from app.database import engine as app_engine, Base
    from app.models.user import User  # noqa: F401 — 确保 model 注册到 Base

    # 确保表存在(create_all 是幂等的,已存在则跳过)
    async with app_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield app_engine

    # 测试结束后清理:truncate users 表
    async with app_engine.begin() as conn:
        await conn.execute(User.__table__.delete())


@pytest_asyncio.fixture
async def db_session(engine):
    """
    每个测试独立的数据库 session,测试结束后 truncate users 表。
    保证测试间数据隔离。
    """
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.models.user import User
    from app.database import async_session_factory

    # 使用 app 的 session factory 创建 session
    async with async_session_factory() as session:
        yield session
        # truncate users 表(测试隔离)
        await session.execute(User.__table__.delete())
        await session.commit()


# ---------------------------------------------------------------------------
# httpx.AsyncClient(挂载 FastAPI app)
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture
async def client(db_session):
    """
    创建 httpx.AsyncClient,通过 ASGITransport 直接调用 FastAPI app,
    无需启动真实 HTTP 服务器。
    """
    import httpx
    from app.main import app
    from app.database import get_db

    # 覆盖依赖注入:使用测试专用 db_session
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac

    # 清理依赖覆盖
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# 辅助 fixture:创建已注册用户的快捷方法
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture
async def registered_user(client):
    """
    注册一个测试用户并返回用户信息。
    返回 dict: {phone, password, user_id, ...}
    """
    import uuid
    phone = f"138{str(uuid.uuid4().int)[:8]}"
    password = "Test1234"
    resp = await client.post("/api/auth/register", json={
        "phone": phone,
        "password": password,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 0
    return {
        "phone": phone,
        "password": password,
        "user_id": data["data"]["user_id"],
        "phone_masked": data["data"]["phone"],
    }


@pytest_asyncio.fixture
async def auth_headers(client, registered_user):
    """
    登录已注册用户,返回 Authorization header dict。
    """
    resp = await client.post("/api/auth/login", json={
        "phone": registered_user["phone"],
        "password": registered_user["password"],
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 0
    access_token = data["data"]["access_token"]
    return {"Authorization": f"Bearer {access_token}"}


# ---------------------------------------------------------------------------
# httpx.MockTransport 自动注入 fixture
# ---------------------------------------------------------------------------
# 测试中使用 `with httpx.MockTransport(handler):` 时,MockTransport 的
# __enter__/__exit__ 默认不做全局 patch。此 fixture 通过 monkey-patch
# MockTransport 的上下文管理器方法,将 mock transport 注入到 gitlab_service,
# 使其内部创建的 httpx.AsyncClient 使用 mock 而非真实网络。
# ---------------------------------------------------------------------------
_original_mt_enter = httpx.MockTransport.__enter__
_original_mt_exit = httpx.MockTransport.__exit__


@pytest.fixture(autouse=True)
def _patch_mock_transport_for_gitlab():
    """
    自动 patch httpx.MockTransport 的 __enter__/__exit__,
    使其在进入/退出上下文时同步设置/清除 gitlab_service._test_transport。
    """
    from app.services import gitlab_service

    def patched_enter(self):
        gitlab_service.set_test_transport(self)
        return _original_mt_enter(self)

    def patched_exit(self, *exc_info):
        try:
            return _original_mt_exit(self, *exc_info)
        finally:
            gitlab_service.set_test_transport(None)

    httpx.MockTransport.__enter__ = patched_enter
    httpx.MockTransport.__exit__ = patched_exit

    yield

    # 恢复原始方法
    httpx.MockTransport.__enter__ = _original_mt_enter
    httpx.MockTransport.__exit__ = _original_mt_exit
