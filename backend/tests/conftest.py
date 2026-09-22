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
    from app.models.project import Project, ProjectRepo, PlatformSetting  # noqa: F401 — R2 表注册
    from app.models.project_member import ProjectMember  # noqa: F401 — R12 表注册
    from app.models.model_config import ModelConfig  # noqa: F401 — R13 表注册
    from app.models.skill import Skill, ProjectSkill  # noqa: F401 — R17 表注册
    from app.models.container import Container  # noqa: F401 — R8 表注册
    from app.models.runner import Runner  # noqa: F401 — R16 表注册
    from app.models.terminal import TerminalSession  # noqa: F401 — R9 表注册
    from app.models.route import Route  # noqa: F401 — R10 表注册
    from app.models.requirement import Requirement  # noqa: F401 — R3 表注册
    from app.models.task import Task, TaskUploadedFile, TaskMessage  # noqa: F401 — R4 表注册
    from app.models.knowledge_entry import KnowledgeEntry  # noqa: F401 — R14 表注册
    from app.models.knowledge_base import KnowledgeBase, KnowledgeDoc  # noqa: F401 — R20 表注册
    from app.models.notification import Notification, UserNotificationSettings  # noqa: F401 — R18 表注册

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
    每个测试独立的数据库 session,测试结束后清理 R1/R2 全部业务表。
    保证测试间数据隔离(users/projects/project_repos/platform_settings)。
    """
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy import delete
    from app.models.user import User
    from app.models.project import Project, ProjectRepo, PlatformSetting
    from app.models.project_member import ProjectMember
    from app.models.model_config import ModelConfig
    from app.models.skill import Skill, ProjectSkill
    from app.models.container import Container
    from app.models.runner import Runner
    from app.models.terminal import TerminalSession
    from app.models.route import Route
    from app.models.requirement import Requirement
    from app.models.task import Task, TaskUploadedFile, TaskMessage
    from app.models.knowledge_entry import KnowledgeEntry
    from app.models.knowledge_base import KnowledgeBase, KnowledgeDoc
    from app.models.notification import Notification, UserNotificationSettings
    from app.database import async_session_factory

    # 使用 app 的 session factory 创建 session
    async with async_session_factory() as session:
        yield session
        # truncate 全部业务表(测试隔离;platform_settings 必须清,否则
        # 前序测试写入的 bot token 会污染后续 2001 未配置场景)
        await session.execute(delete(PlatformSetting))
        await session.execute(delete(Route))
        await session.execute(delete(KnowledgeEntry))
        await session.execute(delete(KnowledgeDoc))
        await session.execute(delete(KnowledgeBase))
        await session.execute(delete(Notification))
        await session.execute(delete(UserNotificationSettings))
        await session.execute(delete(TaskMessage))
        await session.execute(delete(TaskUploadedFile))
        await session.execute(delete(Task))
        await session.execute(delete(Requirement))
        await session.execute(delete(TerminalSession))
        await session.execute(delete(ProjectSkill))
        await session.execute(delete(Skill))
        await session.execute(delete(ModelConfig))
        await session.execute(delete(ProjectMember))
        await session.execute(delete(ProjectRepo))
        await session.execute(delete(Project))
        await session.execute(delete(Container))
        await session.execute(delete(Runner))
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


@pytest_asyncio.fixture
async def superadmin_headers(client, db_session):
    """
    注册一个用户并将其 role 提升为 superadmin,然后登录返回 Authorization header dict。
    User 模型的 role 列是 SAEnum("superadmin", "user"),不是布尔 is_superadmin。
    """
    import uuid
    from sqlalchemy import text
    from app.models.user import User

    phone = f"139{str(uuid.uuid4().int)[:8]}"
    password = "Admin1234"
    resp = await client.post("/api/auth/register", json={
        "phone": phone,
        "password": password,
    })
    assert resp.status_code == 200
    reg_data = resp.json()
    assert reg_data["code"] == 0
    user_id = reg_data["data"]["user_id"]

    # 直接通过 SQL 将 role 设为 superadmin(绕过 ORM 枚举校验)
    await db_session.execute(
        text("UPDATE users SET role = 'superadmin' WHERE user_id = :uid"),
        {"uid": user_id},
    )
    await db_session.commit()

    # 登录获取 token
    resp = await client.post("/api/auth/login", json={
        "phone": phone,
        "password": password,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["code"] == 0
    access_token = data["data"]["access_token"]
    return {"Authorization": f"Bearer {access_token}"}


@pytest_asyncio.fixture
async def second_user_headers(client):
    """
    第二个注册用户的 Authorization header。
    注意:R1 注册逻辑是"首个注册用户 = superadmin"(bootstrap),
    所以非超管场景必须用第二个注册用户(role=user)。
    """
    import uuid
    phone = f"137{str(uuid.uuid4().int)[:8]}"
    password = "Test1234"
    resp = await client.post("/api/auth/register", json={"phone": phone, "password": password})
    assert resp.status_code == 200
    assert resp.json()["code"] == 0
    resp = await client.post("/api/auth/login", json={"phone": phone, "password": password})
    assert resp.status_code == 200
    access_token = resp.json()["data"]["access_token"]
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
