"""
R2 批量邀请接口测试(owner 专属,整体事务)
==========================================
接口:POST /api/projects/{project_id}/members/batch
请求:{user_ids: string[], role: "editor"|"viewer"}
响应 200:{added: n, role, users: [{user_id, nickname}]}

覆盖 DEVPLAN/R2.md 完成判据 7 条 + 并发撞车(IntegrityError 兜底路径):
1. 2 个新用户批量加入成功:200 added=2,成员表 2 行+审计 2 条,GitLab 同步触发
2. 含已成员用户 → 整批 400,errors 列该用户,成员表零新增
3. 含 disabled 用户 → 整批 400 逐条原因「用户已停用」
4. 现成员 49 + 选 3 → 400 超上限(整批拒绝,零新增)
5. user_ids 含不存在 id → 400 逐条「用户不存在」
6. 空 list / 超 50 / 含重复 → 400
7. editor 调用 403(1901)
8. 并发撞车:预检通过后唯一键被占 → IntegrityError → 整批回滚 400「部分用户刚被加入,请刷新重试」

⚠️ 契约冲突登记(判据 6「含重复 → 400」vs R2.md 行为规格「user_ids 重复:服务端
静默去重」):本套件按完成判据(测试验证逻辑指定的验收清单)+ PRD 错误表
(PRD.md:46 含重复 → 400)编码,用例 test_duplicates_400;
若定稿改为静默去重,须先改 PRD/判据再翻绿,不得静默改测试。

错误码:沿用 app/core/response.py ErrCode 已定稿的批量专用段
(12006 空 / 12007 超 50 / 12008 预检失败 / 12009 并发撞车),容量超限整批 12003(与单邀请同码)。

脚手架照抄 test_member_candidates.py / test_project_members_api.py:
- _register_user:注册+登录普通用户
- _insert_member:直插成员行
- _insert_project/_insert_repo/_seed_gitlab_settings(test_projects_api)
- 注意:auth_headers 首位注册用户=superadmin,owner 场景须另注册普通用户;
  每条用例都注入 registered_user fixture 占住「首位用户=superadmin」bootstrap 位。

共享远程测试库:串行单进程运行;GitLab 同步一律 httpx.MockTransport,不发真实请求。
"""
import uuid
import urllib.parse

import pytest
import httpx
import sqlalchemy as sa
from sqlalchemy import select, text
from sqlalchemy.orm import Session as SASession

from tests.test_projects_api import (
    _insert_project,
    _insert_repo,
    _seed_gitlab_settings,
)
from app.core.response import ErrCode
from app.models.project_member import ProjectMember
from app.models.audit_log import AuditLog


async def _register_user(client):
    """注册普通用户(非首位),返回 {headers, phone, user_id}"""
    phone = f"136{str(uuid.uuid4().int)[:8]}"
    resp = await client.post("/api/auth/register", json={"phone": phone, "password": "Test1234"})
    assert resp.status_code == 200 and resp.json()["code"] == 0
    user_id = resp.json()["data"]["user_id"]
    resp = await client.post("/api/auth/login", json={"phone": phone, "password": "Test1234"})
    assert resp.status_code == 200
    headers = {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}
    return {"headers": headers, "phone": phone, "user_id": user_id}


async def _insert_member(db_session, project_id, user_id, role="viewer", invited_by=None):
    """直插成员行(造数据用,绕过邀请流程)"""
    m = ProjectMember(
        project_id=project_id,
        user_id=user_id,
        role=role,
        invited_by=invited_by or user_id,
    )
    db_session.add(m)
    await db_session.flush()
    return m


async def _set_nickname(db_session, user_id, nickname):
    """直改 users.nickname(造数用,绕过资料接口)"""
    await db_session.execute(
        text("UPDATE users SET nickname = :n WHERE user_id = :uid"),
        {"n": nickname, "uid": user_id},
    )
    await db_session.flush()


async def _set_gitlab_username(db_session, user_id, gitlab_username):
    """直改 users.gitlab_username(造数用,触发 GitLab 同步路径)"""
    await db_session.execute(
        text("UPDATE users SET gitlab_username = :u WHERE user_id = :uid"),
        {"u": gitlab_username, "uid": user_id},
    )
    await db_session.flush()


async def _batch_invite(client, headers, project_id, user_ids, role="editor"):
    """POST /members/batch 快捷封装"""
    return await client.post(
        f"/api/projects/{project_id}/members/batch",
        headers=headers,
        json={"user_ids": user_ids, "role": role},
    )


async def _member_uids(db_session, project_id):
    """项目成员 user_id 全集"""
    rows = await db_session.execute(
        select(ProjectMember.user_id).where(ProjectMember.project_id == project_id)
    )
    return set(rows.scalars().all())


async def _add_audits(db_session, project_id):
    """项目 project_member.add 审计行全量"""
    rows = await db_session.execute(
        select(AuditLog).where(
            AuditLog.project_id == project_id,
            AuditLog.action_type == "project_member.add",
        )
    )
    return rows.scalars().all()


# ---------------------------------------------------------------------------
# 判据 1:批量成功 200,成员表+审计+GitLab 同步全落地
# ---------------------------------------------------------------------------
class TestBatchInviteSuccess:
    @pytest.mark.asyncio
    async def test_two_users_success_member_audit_sync(
        self, client, db_session, registered_user
    ):
        """2 个新用户批量加入:200 added=2;成员表 2 行(invited_by=owner);
        审计 project_member.add 2 条;GitLab lookup+add member 触发"""
        await _seed_gitlab_settings(db_session)
        owner = await _register_user(client)
        project = await _insert_project(db_session, owner["user_id"])
        await _insert_repo(db_session, project.project_id, owner["user_id"], role="main", gitlab_repo_id=777)
        u1 = await _register_user(client)
        u2 = await _register_user(client)
        await _set_nickname(db_session, u1["user_id"], "批量测试员一")
        await _set_nickname(db_session, u2["user_id"], "批量测试员二")
        await _set_gitlab_username(db_session, u1["user_id"], "batch_user_a")
        await _set_gitlab_username(db_session, u2["user_id"], "batch_user_b")

        calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append((request.method, str(request.url)))
            url = str(request.url)
            if request.method == "GET" and "/api/v4/users" in url:
                qs = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
                uname = qs.get("username", [""])[0]
                gid = {"batch_user_a": 901, "batch_user_b": 902}.get(uname, 0)
                return httpx.Response(200, json=[{"id": gid, "username": uname}])
            if request.method == "POST" and "/members" in url:
                return httpx.Response(201, json={"message": "201 Created"})
            return httpx.Response(404)

        with httpx.MockTransport(handler):
            resp = await _batch_invite(
                client, owner["headers"], project.project_id,
                [u1["user_id"], u2["user_id"]], role="editor",
            )

        # 响应契约
        assert resp.status_code == 200
        data = resp.json()
        assert data["code"] == 0
        assert data["data"]["added"] == 2
        assert data["data"]["role"] == "editor"
        users_by_uid = {u["user_id"]: u for u in data["data"]["users"]}
        assert users_by_uid[u1["user_id"]]["nickname"] == "批量测试员一"
        assert users_by_uid[u2["user_id"]]["nickname"] == "批量测试员二"

        # 成员表 2 行:角色=请求 role,invited_by=操作者(owner)
        uids = await _member_uids(db_session, project.project_id)
        assert uids == {u1["user_id"], u2["user_id"]}
        rows = (await db_session.execute(
            select(ProjectMember).where(ProjectMember.project_id == project.project_id)
        )).scalars().all()
        assert {m.role for m in rows} == {"editor"}
        assert {m.invited_by for m in rows} == {owner["user_id"]}

        # 审计逐条 2 条:target_id 对应用户,detail.role 同请求
        audits = await _add_audits(db_session, project.project_id)
        assert {a.target_id for a in audits} == {u1["user_id"], u2["user_id"]}
        assert all(a.detail["role"] == "editor" for a in audits)

        # GitLab 同步触发:逐用户 lookup + add member(1 repo × 2 用户)
        assert any(m == "GET" and "username=batch_user_a" in u for m, u in calls)
        assert any(m == "GET" and "username=batch_user_b" in u for m, u in calls)
        assert sum(1 for m, u in calls if m == "POST" and "/members" in u) >= 2


# ---------------------------------------------------------------------------
# 判据 2/3/5:预检失败 → 整批 400,data.errors 逐条列原因,成员表零新增
# ---------------------------------------------------------------------------
class TestBatchPrecheckWholeBatchReject:
    @pytest.mark.asyncio
    async def test_already_member_rejects_whole_batch(self, client, db_session, registered_user):
        """含已成员用户:整批 400(12008),errors 列该用户;同行的新用户也不得入库"""
        owner = await _register_user(client)
        project = await _insert_project(db_session, owner["user_id"])
        member = await _register_user(client)
        newcomer = await _register_user(client)
        await _insert_member(db_session, project.project_id, member["user_id"], "viewer")

        resp = await _batch_invite(
            client, owner["headers"], project.project_id,
            [member["user_id"], newcomer["user_id"]],
        )
        assert resp.status_code == 400
        data = resp.json()
        assert data["code"] == ErrCode.BATCH_INVITE_PRECHECK_FAILED
        err_by_uid = {e["user_id"]: e["reason"] for e in data["data"]["errors"]}
        assert member["user_id"] in err_by_uid
        assert "成员" in err_by_uid[member["user_id"]]
        assert newcomer["user_id"] not in err_by_uid  # 新用户本身合规,整批拒绝而非逐条报错
        assert await _member_uids(db_session, project.project_id) == {member["user_id"]}

    @pytest.mark.asyncio
    async def test_disabled_user_listed_with_reason(self, client, db_session, registered_user):
        """含 disabled 用户:整批 400,errors 逐条列「用户已停用」;零新增"""
        owner = await _register_user(client)
        project = await _insert_project(db_session, owner["user_id"])
        disabled = await _register_user(client)
        active = await _register_user(client)
        await db_session.execute(
            text("UPDATE users SET status = 'disabled' WHERE user_id = :uid"),
            {"uid": disabled["user_id"]},
        )
        await db_session.flush()

        resp = await _batch_invite(
            client, owner["headers"], project.project_id,
            [disabled["user_id"], active["user_id"]],
        )
        assert resp.status_code == 400
        data = resp.json()
        assert data["code"] == ErrCode.BATCH_INVITE_PRECHECK_FAILED
        err_by_uid = {e["user_id"]: e["reason"] for e in data["data"]["errors"]}
        assert "已停用" in err_by_uid[disabled["user_id"]]
        assert active["user_id"] not in err_by_uid
        assert await _member_uids(db_session, project.project_id) == set()

    @pytest.mark.asyncio
    async def test_nonexistent_user_listed_not_found(self, client, db_session, registered_user):
        """含不存在 id:整批 400,errors 逐条「用户不存在」;合规用户零新增"""
        owner = await _register_user(client)
        project = await _insert_project(db_session, owner["user_id"])
        real = await _register_user(client)
        ghost = "00000000-0000-0000-0000-999999999999"

        resp = await _batch_invite(
            client, owner["headers"], project.project_id,
            [real["user_id"], ghost],
        )
        assert resp.status_code == 400
        data = resp.json()
        assert data["code"] == ErrCode.BATCH_INVITE_PRECHECK_FAILED
        err_by_uid = {e["user_id"]: e["reason"] for e in data["data"]["errors"]}
        assert "不存在" in err_by_uid[ghost]
        assert real["user_id"] not in err_by_uid
        assert await _member_uids(db_session, project.project_id) == set()


# ---------------------------------------------------------------------------
# 判据 4:现成员 49 + 选 3 → 400 超上限(整批,零新增)
# ---------------------------------------------------------------------------
class TestBatchCapacityLimit:
    @pytest.mark.asyncio
    async def test_49_members_plus_3_rejected(self, client, db_session, registered_user):
        """49 现成员(owner 行+48 直插)再选 3:400(12003,与单邀请同码),零新增"""
        owner = await _register_user(client)
        project = await _insert_project(db_session, owner["user_id"])
        await _insert_member(db_session, project.project_id, owner["user_id"], "owner")
        for i in range(48):
            await _insert_member(
                db_session, project.project_id, f"00000000-0000-0000-0000-{i:012d}", "viewer"
            )
        newcomers = [await _register_user(client) for _ in range(3)]

        resp = await _batch_invite(
            client, owner["headers"], project.project_id,
            [u["user_id"] for u in newcomers],
        )
        assert resp.status_code == 400
        data = resp.json()
        assert data["code"] == ErrCode.MEMBER_LIMIT_EXCEEDED
        assert "上限" in data["message"]
        before = {f"00000000-0000-0000-0000-{i:012d}" for i in range(48)} | {owner["user_id"]}
        assert await _member_uids(db_session, project.project_id) == before


# ---------------------------------------------------------------------------
# 判据 6:空 list / 超 50 / 含重复 → 400
# ---------------------------------------------------------------------------
class TestBatchRequestValidation:
    @pytest.mark.asyncio
    async def test_empty_list_400(self, client, db_session, registered_user):
        """空 user_ids:400(12006)"""
        owner = await _register_user(client)
        project = await _insert_project(db_session, owner["user_id"])

        resp = await _batch_invite(client, owner["headers"], project.project_id, [])
        assert resp.status_code == 400
        assert resp.json()["code"] == ErrCode.BATCH_INVITE_EMPTY

    @pytest.mark.asyncio
    async def test_over_50_400(self, client, db_session, registered_user):
        """单次 51 个(互不重复):400(12007),不走预查逐条"""
        owner = await _register_user(client)
        project = await _insert_project(db_session, owner["user_id"])
        fifty_one = [f"00000000-0000-0000-0000-{i:012d}" for i in range(51)]

        resp = await _batch_invite(client, owner["headers"], project.project_id, fifty_one)
        assert resp.status_code == 400
        data = resp.json()
        assert data["code"] == ErrCode.BATCH_INVITE_TOO_MANY
        assert any(k in data["message"] for k in ("最多", "上限"))

    @pytest.mark.asyncio
    async def test_duplicates_400(self, client, db_session, registered_user):
        """含重复 user_ids:400(判据 6 / PRD.md:46 错误表)

        ⚠️ 契约冲突探针:R2.md 行为规格写「服务端静默去重」,但完成判据 6 与
        PRD 错误表均写「含重复 → 400」。本用例按验收清单(判据 6)编码;
        若定稿翻转为静默去重,须先改 PRD/R2.md 判据再同步翻绿本用例。
        """
        owner = await _register_user(client)
        project = await _insert_project(db_session, owner["user_id"])
        u1 = await _register_user(client)
        u2 = await _register_user(client)

        resp = await _batch_invite(
            client, owner["headers"], project.project_id,
            [u1["user_id"], u1["user_id"], u2["user_id"]],
        )
        assert resp.status_code == 400
        data = resp.json()
        assert data["code"] != 0
        assert await _member_uids(db_session, project.project_id) == set()


# ---------------------------------------------------------------------------
# 判据 7 + 权限矩阵:editor 403;超管旁路 ✅
# ---------------------------------------------------------------------------
class TestBatchPermission:
    @pytest.mark.asyncio
    async def test_editor_403(self, client, db_session, registered_user):
        """项目 editor 调批量邀请:403 / 1901,零新增"""
        owner = await _register_user(client)
        project = await _insert_project(db_session, owner["user_id"])
        editor = await _register_user(client)
        target = await _register_user(client)
        await _insert_member(db_session, project.project_id, editor["user_id"], "editor")

        resp = await _batch_invite(
            client, editor["headers"], project.project_id, [target["user_id"]],
        )
        assert resp.status_code == 403
        assert resp.json()["code"] == 1901
        assert await _member_uids(db_session, project.project_id) == {editor["user_id"]}

    @pytest.mark.asyncio
    async def test_non_member_403(self, client, db_session, registered_user):
        """非成员(已注册不在项目)调批量邀请:403 / 1901(权限矩阵 editor/viewer/非成员 403)"""
        owner = await _register_user(client)
        project = await _insert_project(db_session, owner["user_id"])
        outsider = await _register_user(client)
        target = await _register_user(client)

        resp = await _batch_invite(
            client, outsider["headers"], project.project_id, [target["user_id"]],
        )
        assert resp.status_code == 403
        assert resp.json()["code"] == 1901

    @pytest.mark.asyncio
    async def test_superadmin_non_member_200(self, client, db_session, registered_user, superadmin_headers):
        """超管(非项目成员)旁路 ✅(权限矩阵;同 invite 的 get_project_role 虚拟 owner)"""
        owner = await _register_user(client)
        project = await _insert_project(db_session, owner["user_id"])
        target = await _register_user(client)

        resp = await _batch_invite(
            client, superadmin_headers, project.project_id, [target["user_id"]], role="viewer",
        )
        assert resp.status_code == 200
        assert resp.json()["code"] == 0
        assert resp.json()["data"]["added"] == 1
        assert await _member_uids(db_session, project.project_id) == {target["user_id"]}


# ---------------------------------------------------------------------------
# 并发撞车:预检通过后唯一键 uq_project_member_user 被占
# → IntegrityError → 整批回滚 400「部分用户刚被加入,请刷新重试」
# ---------------------------------------------------------------------------
class TestBatchConcurrencyConflict:
    @pytest.mark.asyncio
    async def test_unique_key_race_rolls_back_whole_batch(self, client, db_session, registered_user):
        """并发撞车用例(双事务模拟的等价实现):

        竞态窗口 = 预检(读)之后、批量 INSERT 落库之前,另一请求抢先提交了
        同一 (project_id, user_id)。直接跨连接模拟会撞 InnoDB 唯一键锁等待,
        故等价实现:经 SQLAlchemy before_flush 事件在同一连接同一事务内
        先插入撞车行(u1),批量 INSERT 随即撞唯一键 → IntegrityError
        → 断言整体回滚(两人都不入库、无审计)+ 400/12009 文案。
        """
        owner = await _register_user(client)
        project = await _insert_project(db_session, owner["user_id"])
        u1 = await _register_user(client)
        u2 = await _register_user(client)

        target_sync_session = db_session.sync_session
        armed = [True]

        def _inject_race_winner(session, flush_context, instances):
            """批量 INSERT flush 前,同事务注入已抢到唯一键的撞车行(仅一次)"""
            if not armed[0] or session is not target_sync_session:
                return
            armed[0] = False
            session.connection().execute(
                text(
                    "INSERT INTO project_members (project_id, user_id, role, invited_by) "
                    "VALUES (:p, :u, 'viewer', :u)"
                ),
                {"p": project.project_id, "u": u1["user_id"]},
            )

        sa.event.listen(SASession, "before_flush", _inject_race_winner)
        try:
            resp = await _batch_invite(
                client, owner["headers"], project.project_id,
                [u1["user_id"], u2["user_id"]],
            )
        finally:
            sa.event.remove(SASession, "before_flush", _inject_race_winner)

        assert resp.status_code == 400
        data = resp.json()
        assert data["code"] == ErrCode.BATCH_INVITE_CONFLICT
        assert "刚被加入" in data["message"]
        assert "刷新重试" in data["message"]

        # 整批回滚:不留半批(u1 撞车行一并回滚),无审计落库
        assert await _member_uids(db_session, project.project_id) == set()
        assert await _add_audits(db_session, project.project_id) == []
        await db_session.rollback()  # 防御:会话已由服务层回滚,此处复位避免 teardown 噪声
