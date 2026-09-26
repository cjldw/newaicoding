"""
R1 候选用户列表接口测试(owner 专属)
====================================
接口:GET /api/projects/{project_id}/candidate-users?q=&page=&page_size=

覆盖 DEVPLAN/R1.md 完成判据:
1. owner 200 + items 含 is_member 正确标记(1 已成员 + 1 非成员)
2. q=昵称片段 / 手机号片段 均命中
3. 分页正确(total/page/page_size 回显,跨页不重不漏)
4. phone 打码非明文(复用 mask_phone 口径)
5. editor / 非成员 403(1901)
6. 超管(非项目成员)可访问

脚手架照抄 test_project_members_api.py:
- _register_user:注册+登录普通用户
- _insert_member:直插成员行
- _insert_project(test_projects_api):直插项目
- 注意:auth_headers 首位注册用户=superadmin,owner 场景须另注册普通用户
"""
import uuid

import pytest

from tests.test_projects_api import _insert_project
from app.core.security import mask_phone


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
    from app.models.project_member import ProjectMember

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
    from sqlalchemy import text

    await db_session.execute(
        text("UPDATE users SET nickname = :n WHERE user_id = :uid"),
        {"n": nickname, "uid": user_id},
    )
    await db_session.flush()


async def _candidate_items(client, headers, project_id, query=""):
    """请求候选列表,返回 (resp, data)"""
    resp = await client.get(
        f"/api/projects/{project_id}/candidate-users{query}",
        headers=headers,
    )
    return resp, resp.json()


# ---------------------------------------------------------------------------
# 判据 1:owner 200 + is_member 标记
# ---------------------------------------------------------------------------
class TestOwnerListCandidates:
    @pytest.mark.asyncio
    async def test_owner_200_with_is_member_flags(self, client, db_session, registered_user):
        """owner 请求 200;已成员 is_member=True,非成员 is_member=False"""
        owner = await _register_user(client)
        project = await _insert_project(db_session, owner["user_id"])
        member = await _register_user(client)      # 将被拉入项目
        outsider = await _register_user(client)    # 保持非成员
        await _insert_member(db_session, project.project_id, member["user_id"], "editor")

        resp, data = await _candidate_items(client, owner["headers"], project.project_id)
        assert resp.status_code == 200
        assert data["code"] == 0
        items = data["data"]["items"]
        by_uid = {i["user_id"]: i for i in items}
        assert by_uid[member["user_id"]]["is_member"] is True
        assert by_uid[outsider["user_id"]]["is_member"] is False


# ---------------------------------------------------------------------------
# 判据 2:q 昵称 / 手机号模糊命中
# ---------------------------------------------------------------------------
class TestSearchFuzzy:
    @pytest.mark.asyncio
    async def test_q_matches_nickname_fragment(self, client, db_session, registered_user):
        """q=昵称片段:命中的用户返回,未命中的同昵称前缀用户不返回"""
        owner = await _register_user(client)
        project = await _insert_project(db_session, owner["user_id"])
        hit = await _register_user(client)
        miss = await _register_user(client)
        await _set_nickname(db_session, hit["user_id"], "墨提斯测试员甲")
        await _set_nickname(db_session, miss["user_id"], "墨兰参考员乙")

        resp, data = await _candidate_items(
            client, owner["headers"], project.project_id, "?q=提斯测试"
        )
        assert resp.status_code == 200
        assert data["code"] == 0
        got = {i["user_id"] for i in data["data"]["items"]}
        assert hit["user_id"] in got
        assert miss["user_id"] not in got

    @pytest.mark.asyncio
    async def test_q_matches_phone_fragment(self, client, db_session, registered_user):
        """q=手机号片段(LIKE):命中目标用户"""
        owner = await _register_user(client)
        project = await _insert_project(db_session, owner["user_id"])
        target = await _register_user(client)
        fragment = target["phone"][3:8]  # 中段 5 位随机片段

        resp, data = await _candidate_items(
            client, owner["headers"], project.project_id, f"?q={fragment}"
        )
        assert resp.status_code == 200
        assert data["code"] == 0
        got = {i["user_id"] for i in data["data"]["items"]}
        assert target["user_id"] in got


# ---------------------------------------------------------------------------
# 判据 2b:分页正确
# ---------------------------------------------------------------------------
class TestPagination:
    @pytest.mark.asyncio
    async def test_pagination_correct(self, client, db_session, registered_user):
        """page/page_size 回显正确;跨页不重不漏;total 与实际用户数一致"""
        owner = await _register_user(client)
        project = await _insert_project(db_session, owner["user_id"])
        created = [await _register_user(client) for _ in range(4)]
        # 本测试注册用户总数 = registered_user(fixture) + owner + 4 = 6
        expected_uids = {registered_user["user_id"], owner["user_id"]} | {
            c["user_id"] for c in created
        }

        seen = set()
        for page in (1, 2, 3):
            resp, data = await _candidate_items(
                client,
                owner["headers"],
                project.project_id,
                f"?page={page}&page_size=2",
            )
            assert resp.status_code == 200
            assert data["code"] == 0
            assert data["data"]["page"] == page
            assert data["data"]["page_size"] == 2
            assert data["data"]["total"] == 6
            page_uids = {i["user_id"] for i in data["data"]["items"]}
            assert len(data["data"]["items"]) == 2
            assert page_uids.isdisjoint(seen)  # 不重
            seen |= page_uids
        assert seen == expected_uids  # 不漏


# ---------------------------------------------------------------------------
# 判据 3:phone 打码非明文
# ---------------------------------------------------------------------------
class TestPhoneMasked:
    @pytest.mark.asyncio
    async def test_phone_masked_not_plaintext(self, client, db_session, registered_user):
        """items.phone 为打码格式(前3+****+后4),响应中无明文手机号"""
        owner = await _register_user(client)
        project = await _insert_project(db_session, owner["user_id"])
        target = await _register_user(client)

        resp, data = await _candidate_items(client, owner["headers"], project.project_id)
        assert resp.status_code == 200
        raw_text = resp.text
        assert target["phone"] not in raw_text  # 非明文
        by_uid = {i["user_id"]: i for i in data["data"]["items"]}
        item = by_uid[target["user_id"]]
        assert item["phone"] == mask_phone(target["phone"])
        assert item["phone"].startswith(target["phone"][:3])
        assert "****" in item["phone"]
        assert item["phone"].endswith(target["phone"][-4:])


# ---------------------------------------------------------------------------
# 判据 4:editor / 非成员 403
# ---------------------------------------------------------------------------
class TestForbiddenForNonOwner:
    @pytest.mark.asyncio
    async def test_editor_403(self, client, db_session, registered_user):
        """项目 editor(成员但非 owner)访问:403 / 1901"""
        owner = await _register_user(client)
        project = await _insert_project(db_session, owner["user_id"])
        editor = await _register_user(client)
        await _insert_member(db_session, project.project_id, editor["user_id"], "editor")

        resp, data = await _candidate_items(client, editor["headers"], project.project_id)
        assert resp.status_code == 403
        assert data["code"] == 1901

    @pytest.mark.asyncio
    async def test_non_member_403(self, client, db_session, registered_user):
        """非成员(已注册但不在项目)访问:403 / 1901"""
        owner = await _register_user(client)
        project = await _insert_project(db_session, owner["user_id"])
        outsider = await _register_user(client)

        resp, data = await _candidate_items(client, outsider["headers"], project.project_id)
        assert resp.status_code == 403
        assert data["code"] == 1901


# ---------------------------------------------------------------------------
# 判据 5:超管(非项目成员)可访问
# ---------------------------------------------------------------------------
class TestSuperadminBypass:
    @pytest.mark.asyncio
    async def test_superadmin_non_member_200(self, client, db_session, registered_user, superadmin_headers):
        """超管非项目成员:经 get_project_role 旁路可访问,返回 200"""
        owner = await _register_user(client)
        project = await _insert_project(db_session, owner["user_id"])
        target = await _register_user(client)

        resp, data = await _candidate_items(client, superadmin_headers, project.project_id)
        assert resp.status_code == 200
        assert data["code"] == 0
        got = {i["user_id"] for i in data["data"]["items"]}
        assert target["user_id"] in got
