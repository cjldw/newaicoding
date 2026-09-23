"""
R25 审计日志全量接入 — P0 批次(登录 6 事件 + 终端破坏性命令)
==============================================================
覆盖 R25.md 完成判据:
1. 登录成功 + 4 类失败分支审计(user_not_found 用占位 user_id)
7. 终端破坏性命令(detail 含 matched_pattern + 输入前 200 字符;TODO 已删)
8. 审计写失败不阻塞业务
11. 敏感值不外泄(detail 无手机号明文/密码)

断言策略:
- 事务内事件(login_success / register):audit_write flush 进 db_session(测试
  override 的 get_db 不 commit)→ 用 db_session 查询断言
- spawn 事件(4 类登录失败 / terminal):独立会话 commit → 独立会话轮询断言
"""
import asyncio
import uuid

import pytest
from sqlalchemy import select, delete

from app.database import async_session_factory
from app.models.audit_log import AuditLog
from app.models.user import User
from app.core.security import hash_password
from app.services import auth_service
from app.services.terminal_service import (
    TerminalConnection,
    TerminalRegistry,
    audit_destructive_input,
)

# 与 auth_service 同源的占位 user_id(断言用字面量,防常量漂移)
PLACEHOLDER_UID = "00000000-0000-0000-0000-000000000000"

_next_phone = [0]


def _phone() -> str:
    """唯一测试手机号(每用例独立,防串扰)"""
    _next_phone[0] += 1
    return f"137{int(uuid.uuid4().int % 1e8):08d}"[:11]


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------
async def _spawn_rows(action_type: str, timeout: float = 2.0) -> list:
    """轮询独立会话已 commit 的 spawn 审计行"""
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        async with async_session_factory() as s:
            rows = (await s.execute(
                select(AuditLog).where(AuditLog.action_type == action_type)
            )).scalars().all()
        if rows:
            return list(rows)
        await asyncio.sleep(0.05)
    return []


async def _db_rows(db_session, action_type: str) -> list:
    """查询事务内(flush 未 commit)审计行"""
    rows = (await db_session.execute(
        select(AuditLog).where(AuditLog.action_type == action_type)
    )).scalars().all()
    return list(rows)


async def _make_user(db_session, status: str = "active", locked_until=None) -> User:
    """直插用户(绕过 API;用于 disabled/locked 分支)"""
    user = User(
        phone=_phone(),
        password_hash=hash_password("Test1234"),
        role="user",
        token_version=0,
        status=status,
        locked_until=locked_until,
    )
    db_session.add(user)
    await db_session.flush()
    return user


# ---------------------------------------------------------------------------
# 判据 1:登录成功 + 4 类失败分支
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_login_success_writes_audit(client, db_session):
    """登录成功 → auth.login_success(事务内,含 ip;detail 无密码)"""
    phone = _phone()
    resp = await client.post("/api/auth/register", json={"phone": phone, "password": "Test1234"})
    assert resp.json()["code"] == 0

    resp = await client.post("/api/auth/login", json={"phone": phone, "password": "Test1234"})
    assert resp.json()["code"] == 0

    rows = await _db_rows(db_session, "auth.login_success")
    assert len(rows) == 1
    row = rows[0]
    assert row.ip is not None  # ASGI transport 注入 client 地址
    assert (row.detail or {}).get("password") is None  # 判据 11:无密码


@pytest.mark.asyncio
async def test_login_fail_not_found_uses_placeholder(client):
    """用户不存在 → 占位 user_id + role=anonymous + detail.reason;手机号不落 detail"""
    phone = _phone()
    resp = await client.post("/api/auth/login", json={"phone": phone, "password": "Whatever1"})
    assert resp.json()["code"] != 0

    rows = await _spawn_rows("auth.login_fail_not_found")
    assert len(rows) == 1
    row = rows[0]
    assert row.user_id == PLACEHOLDER_UID
    assert row.operator_role == "anonymous"
    assert row.detail.get("reason") == "user_not_found"
    assert phone not in str(row.detail)  # 判据 11


@pytest.mark.asyncio
async def test_login_fail_disabled(client, db_session):
    """禁用账号登录 → auth.login_fail_disabled(真实 user_id)"""
    user = await _make_user(db_session, status="disabled")
    resp = await client.post("/api/auth/login", json={"phone": user.phone, "password": "Test1234"})
    assert resp.json()["code"] != 0

    rows = await _spawn_rows("auth.login_fail_disabled")
    assert len(rows) == 1
    assert rows[0].user_id == user.user_id
    assert rows[0].operator_role == "user"


@pytest.mark.asyncio
async def test_login_fail_locked(client, db_session):
    """锁定中登录 → auth.login_fail_locked(detail.remaining_seconds > 0)"""
    from datetime import datetime, timedelta, timezone

    user = await _make_user(
        db_session,
        locked_until=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(minutes=5),
    )
    resp = await client.post("/api/auth/login", json={"phone": user.phone, "password": "Test1234"})
    assert resp.json()["code"] != 0

    rows = await _spawn_rows("auth.login_fail_locked")
    assert len(rows) == 1
    assert rows[0].user_id == user.user_id
    assert rows[0].detail.get("remaining_seconds", 0) > 0


@pytest.mark.asyncio
async def test_login_fail_wrong_password(client, db_session):
    """密码错误(未达阈值)→ auth.login_fail_wrong_password"""
    user = await _make_user(db_session)
    resp = await client.post("/api/auth/login", json={"phone": user.phone, "password": "WrongPass1"})
    assert resp.json()["code"] != 0

    rows = await _spawn_rows("auth.login_fail_wrong_password")
    assert len(rows) == 1
    assert rows[0].user_id == user.user_id
    assert rows[0].detail.get("reason") == "wrong_password"
    assert rows[0].detail.get("locked_triggered") is None


@pytest.mark.asyncio
async def test_login_fail_threshold_triggers_lock_flag(client, db_session):
    """连错达阈值 → wrong_password 留痕且末条 locked_triggered=True;再试 → locked"""
    from datetime import datetime, timedelta, timezone

    user = await _make_user(db_session)
    # 连错 5 次(第 5 次触发锁定)
    for _ in range(auth_service.AuthService.MAX_LOGIN_FAIL_COUNT):
        resp = await client.post("/api/auth/login", json={"phone": user.phone, "password": "WrongPass1"})
        assert resp.json()["code"] != 0

    # 语义断言:多次失败均有留痕(幂等口径允许重复,不逐条计数——spawn 异步时序不脆弱)
    async def _locked_flag_row(timeout: float = 5.0):
        deadline = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < deadline:
            rows = await _spawn_rows("auth.login_fail_wrong_password", timeout=0.1)
            flagged = [r for r in rows if r.detail.get("locked_triggered") is True]
            if flagged:
                return rows, flagged[0]
            await asyncio.sleep(0.05)
        return [], None

    rows, flagged = await _locked_flag_row()
    assert len(rows) >= 2  # 多次失败留痕
    assert flagged is not None  # 达阈值的末次失败记录了锁定副作用

    # 锁定后即使用正确密码 → login_fail_locked
    resp = await client.post("/api/auth/login", json={"phone": user.phone, "password": "Test1234"})
    assert resp.json()["code"] != 0
    locked_rows = await _spawn_rows("auth.login_fail_locked")
    assert len(locked_rows) >= 1
    # 锁定字段确已落库(供后续过期清理逻辑)
    await db_session.refresh(user)
    assert user.locked_until is not None
    assert datetime.now(timezone.utc).replace(tzinfo=None) < user.locked_until.replace(tzinfo=None)


@pytest.mark.asyncio
async def test_register_writes_audit(client, db_session):
    """注册 → auth.register(detail.role;无手机号明文)"""
    phone = _phone()
    resp = await client.post("/api/auth/register", json={"phone": phone, "password": "Test1234"})
    assert resp.json()["code"] == 0

    rows = await _db_rows(db_session, "auth.register")
    assert len(rows) == 1
    assert rows[0].detail.get("role") in ("user", "superadmin")
    assert phone not in str(rows[0].detail)  # 判据 11:手机号不落审计 detail


# ---------------------------------------------------------------------------
# 判据 7:终端破坏性命令
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_destructive_command_writes_audit():
    """rm -rf 输入 → terminal.destructive_command(matched_pattern + input_head≤200)"""
    # audit_destructive_input 从模块级 registry 取连接(审计归因),须用单例注册
    from app.services.terminal_service import terminal_registry

    session_id = f"s-{uuid.uuid4().int % 1e6}"
    conn = TerminalConnection(
        session_id=session_id,
        task_id="t-1",
        runner_id="r-1",
        user_id="u-test-1",
        websocket=None,  # 审计路径不触达 websocket
        role="editor",
    )
    terminal_registry.put(conn)

    payload = "rm -rf /tmp/some-dir && echo done"
    # 直接调判定函数(与 forward_input_to_runner :107 同一入口)
    audit_destructive_input(session_id, payload)

    rows = await _spawn_rows("terminal.destructive_command")
    assert len(rows) == 1
    row = rows[0]
    assert row.user_id == "u-test-1"
    assert row.operator_role == "editor"
    assert row.target_type == "terminal_session"
    assert row.target_id == session_id
    assert row.detail.get("matched_pattern") == "rm -rf"
    assert row.detail.get("input_head", "").startswith("rm -rf /tmp/some-dir")
    assert len(row.detail.get("input_head", "")) <= 200

    # 非破坏性命令不产生审计
    audit_destructive_input(session_id, "ls -la && echo hi")
    rows_after = await _spawn_rows("terminal.destructive_command", timeout=0.6)
    assert len(rows_after) == 1  # 仍是之前那一条

    # 清理模块级注册表,避免污染其他用例
    terminal_registry.pop(session_id)


# ---------------------------------------------------------------------------
# 判据 8:审计写失败不阻塞业务
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_audit_write_failure_does_not_block_login(client, db_session, monkeypatch):
    """spawn 写失败(工厂抛错)→ 登录业务响应不受影响"""
    # 零重试间隔(避免用例等待 1s/5s/30s)
    monkeypatch.setattr(auth_service, "_AUDIT_RETRY_DELAYS", (0, 0, 0), raising=False)
    from app.services import audit_service
    monkeypatch.setattr(audit_service, "_AUDIT_RETRY_DELAYS", (0, 0, 0), raising=False)

    def _boom(*args, **kwargs):
        raise RuntimeError("db unavailable (injected)")

    # auth_service 命名空间内的 factory 引用替换为抛错工厂
    monkeypatch.setattr(auth_service, "async_session_factory", _boom)

    phone = _phone()
    resp = await client.post("/api/auth/register", json={"phone": phone, "password": "Test1234"})
    assert resp.json()["code"] == 0

    # 错误密码登录:审计写失败,但业务响应正常返回(非 5xx)
    resp = await client.post("/api/auth/login", json={"phone": phone, "password": "WrongPass1"})
    body = resp.json()
    assert resp.status_code == 200  # BizError 默认 HTTP 200(统一响应封装)
    assert body["code"] != 0  # 业务码=凭据错误
