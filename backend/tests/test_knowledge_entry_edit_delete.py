"""
R3 条目编辑与删除(后端面)— Red 阶段失败测试
================================================
覆盖 DEVPLAN/R3.md「接口契约」「数据模型变更」「权限矩阵」「完成判据」:

1. PATCH /api/knowledge/{entry_id}(新增路由,当前不存在 → Red:405):
   - 人工条目创建者本人全字段编辑成功(title/type/tags/content/source_links)
   - 项目 owner/editor 可编辑他人人工条目;viewer → 403/1901
   - AI 条目字段白名单:PATCH content → 400 + 20013「AI 条目仅支持编辑标签」;PATCH tags → 200
   - 平台级条目:创建者本人(非超管)仍 403;超管成功
   - 历史行(created_by_user_id NULL):无创建者可判,viewer 403 / owner 可编(回落安全)
2. DELETE /api/knowledge/{entry_id}(新增路由,当前不存在 → Red:405):
   - 创建者本人 / 项目 owner / editor 删他人成功;viewer → 403
   - 平台级仅超管(创建者本人也不可);删除后 detail 404 + 项目列表移除
3. 数据模型变更:knowledge_entries.created_by_user_id CHAR(36) NULL
   - create 后直查 model 字段断言落 operator.user_id(迁移未建 → Red 断言失败)
4. detail permissions 新口径:创建者(低角色)can_edit/can_delete=true;
   AI 条目创建者 editable_fields==["tags"];非创建者 viewer=false、editor=true(存量基线);
   平台级创建者(非超管)false、超管 true(存量基线)

脚手架/fixture 照抄 test_knowledge_entry_create_code.py / test_knowledge_entry_detail.py:
首注册用户恒 superadmin(registered_user/auth_headers),「普通用户/创建者」一律用 _mk_user
后续注册用户;ProjectRepo 需 NOT NULL created_by。
Red 阶段迁移未创建:creator_user_id 走 setattr(列未迁移时不持久化、不炸 setup),
涉及「创建者判定」的用例预期因 405/断言失败而 Red;列落库用例用哨兵值断言(缺列 → 断言失败)。
"""
import uuid

import pytest
from sqlalchemy import select

KB_AI_ONLY_TAGS = 20013   # R3 契约:AI 条目仅支持编辑标签(携带其他字段 → 400 + 20013)


# ---------------------------------------------------------------------------
# 测试辅助:用户 / 项目 / repo / 成员 / 条目(沿用既有 R1/R2 测试写法)
# ---------------------------------------------------------------------------
async def _mk_user(client):
    """注册并登录一个新用户,返回 {headers, user_id}(首注册用户恒 superadmin,这里是后续普通用户)"""
    phone = f"135{str(uuid.uuid4().int)[:8]}"
    resp = await client.post("/api/auth/register", json={"phone": phone, "password": "Test1234"})
    assert resp.status_code == 200 and resp.json()["code"] == 0
    user_id = resp.json()["data"]["user_id"]
    resp = await client.post("/api/auth/login", json={"phone": phone, "password": "Test1234"})
    assert resp.status_code == 200
    headers = {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}
    return {"headers": headers, "user_id": user_id}


async def _mk_project(db_session, owner_id):
    from app.models.project import Project

    p = Project(
        name=f"R3 编辑删除项目 {uuid.uuid4().hex[:6]}",
        slug=f"r3e-{uuid.uuid4().hex[:8]}",
        owner_id=owner_id,
        status="active",
        visibility="private",
    )
    db_session.add(p)
    await db_session.flush()
    return p


async def _mk_repo(db_session, project_id, gitlab_repo_id=None):
    from app.models.project import ProjectRepo

    repo = ProjectRepo(
        project_id=project_id,
        role="main",
        gitlab_repo_url=f"https://gitlab.example.com/grp/repo-{uuid.uuid4().hex[:6]}.git",
        gitlab_repo_id=gitlab_repo_id or (uuid.uuid4().int % 100000),
        gitlab_bind_type="auto",
        created_by=str(uuid.uuid4()),   # project_repos.created_by NOT NULL(既有测试同款必填)
    )
    db_session.add(repo)
    await db_session.flush()
    return repo


async def _mk_member(db_session, project_id, user_id, role="viewer"):
    from app.models.project_member import ProjectMember

    m = ProjectMember(project_id=project_id, user_id=user_id, role=role,
                      invited_by=user_id)
    db_session.add(m)
    await db_session.flush()
    return m


async def _mk_entry(db_session, project_id, created_by="human", status="published",
                    title=None, type="code_snippet", creator_user_id=None, tags=None):
    """直插条目;creator_user_id → created_by_user_id(R3 目标列,迁移未建时 setattr 不持久化)"""
    from app.models.knowledge_entry import KnowledgeEntry

    e = KnowledgeEntry(
        project_id=project_id,
        req_id="manual",
        type=type,
        title=title or f"R3 条目 {uuid.uuid4().hex[:6]}",
        content="重试装饰器用法说明",
        tags=tags if tags is not None else ["python"],
        source_links=[],
        created_by=created_by,
        status=status,
    )
    if creator_user_id is not None:
        # R3 目标 model 列:created_by_user_id CHAR(36) NULL;Red 阶段列不存在时
        # 该 setattr 只是实例属性(不落库、不报错),Green 后自然持久化
        e.created_by_user_id = creator_user_id
    db_session.add(e)
    await db_session.flush()
    return e


async def _create_entry_api(client, headers, project_id, **overrides):
    """POST /api/projects/{pid}/knowledge(人工创建,直接 published;R1 存量接口)"""
    payload = {
        "type": "code_snippet",
        "title": f"R3 创建条目 {uuid.uuid4().hex[:6]}",
        "content": "重试装饰器用法说明",
        "tags": ["python"],
    }
    payload.update(overrides)
    resp = await client.post(f"/api/projects/{project_id}/knowledge",
                             json=payload, headers=headers)
    assert resp.status_code == 200, f"前置:人工创建应 200,实际 {resp.status_code} {resp.text[:160]}"
    assert resp.json()["code"] == 0, f"前置:创建失败 {resp.json()}"
    return resp.json()["data"]["entry_id"]


def _assert_biz_400(resp, code=None):
    """服务端校验失败契约:HTTP 400 + 统一响应体非零业务错误码(非 422/非 500)"""
    assert resp.status_code == 400, (
        f"应 400,实际 {resp.status_code}(校验未实现时通常 200;pydantic 拦截则 422)"
        f" body={resp.text[:160]}"
    )
    body = resp.json()
    assert body.get("code") not in (None, 0, 422, 500), (
        f"应返回业务错误码,实际 body={body}"
    )
    if code is not None:
        assert body["code"] == code, f"错误码应 {code},实际 {body.get('code')}"
    return body


async def _get_row(db_session, entry_id):
    from app.models.knowledge_entry import KnowledgeEntry

    return (await db_session.execute(
        select(KnowledgeEntry).where(KnowledgeEntry.entry_id == entry_id)
    )).scalars().one()


# ---------------------------------------------------------------------------
# 1. PATCH /api/knowledge/{entry_id} — 人工条目权限矩阵
# ---------------------------------------------------------------------------
class TestPatchHumanEntry:
    @pytest.mark.asyncio
    async def test_creator_edits_own_entry_all_fields(self, client, auth_headers,
                                                      db_session, registered_user):
        """创建者本人(项目 viewer 角色)全字段编辑成功(PRD:title/type/tags/content/代码引用)
        完成判据:人工条目创建者编辑 title/content 成功;PATCH 后详情刷新"""
        project = await _mk_project(db_session, registered_user["user_id"])
        creator = await _mk_user(client)
        await _mk_member(db_session, project.project_id, creator["user_id"], role="viewer")
        repo = await _mk_repo(db_session, project.project_id)
        entry_id = await _create_entry_api(client, creator["headers"], project.project_id)

        new_paths = ["backend/app/services/retry.py"]
        resp = await client.patch(
            f"/api/knowledge/{entry_id}",
            json={
                "title": "创建者改过的新标题",
                "type": "pattern",
                "tags": ["architecture", "retry"],
                "content": "# 创建者改过的正文\n\nMarkdown",
                "source_links": [{"type": "code", "repo_id": repo.repo_id,
                                  "branch": "main", "paths": new_paths}],
            },
            headers=creator["headers"],
        )
        assert resp.status_code == 200, (
            f"创建者编辑自己的人工条目应 200,实际 {resp.status_code}"
            f"(PATCH 路由未实现时 405){resp.text[:160]}"
        )
        assert resp.json()["code"] == 0, f"code={resp.json().get('code')}"

        # 落库核对:五字段全部生效
        row = await _get_row(db_session, entry_id)
        assert row.title == "创建者改过的新标题", f"title 应已更新,实际 {row.title}"
        assert row.type == "pattern", f"type 应已更新,实际 {row.type}"
        assert row.tags == ["architecture", "retry"], f"tags 应已更新,实际 {row.tags}"
        assert row.content == "# 创建者改过的正文\n\nMarkdown", (
            f"content 应已更新,实际 {row.content!r}"
        )
        assert row.source_links == [{"type": "code", "repo_id": repo.repo_id,
                                     "branch": "main", "paths": new_paths}], (
            f"source_links 应已更新,实际 {row.source_links!r}"
        )

        # 完成判据:PATCH 后详情刷新(creator 是 viewer 角色成员,可读)
        detail = await client.get(f"/api/knowledge/{entry_id}", headers=creator["headers"])
        assert detail.status_code == 200
        body = detail.json()["data"]
        assert body["title"] == "创建者改过的新标题", (
            f"详情应返回编辑后标题,实际 {body.get('title')}"
        )
        assert body["content"] == "# 创建者改过的正文\n\nMarkdown"

    @pytest.mark.asyncio
    async def test_owner_edits_others_human_entry(self, client, db_session, registered_user):
        """项目 owner(projects.owner_id,非超管)可编辑他人人工条目(权限矩阵 owner ✅)
        (registered_user 仅占用首注册 superadmin 引导位,owner 判定走 project.owner_id)"""
        owner = await _mk_user(client)
        project = await _mk_project(db_session, owner["user_id"])
        entry = await _mk_entry(db_session, project.project_id)   # 他人创建(无 created_by_user_id)

        resp = await client.patch(
            f"/api/knowledge/{entry.entry_id}",
            json={"title": "owner 改的新标题", "content": "owner 改的正文"},
            headers=owner["headers"],
        )
        assert resp.status_code == 200, (
            f"项目 owner 编辑他人人工条目应 200,实际 {resp.status_code}{resp.text[:160]}"
        )
        row = await _get_row(db_session, entry.entry_id)
        assert row.title == "owner 改的新标题" and row.content == "owner 改的正文", (
            f"owner 编辑应落库,实际 title={row.title} content={row.content!r}"
        )

    @pytest.mark.asyncio
    async def test_editor_edits_others_human_entry(self, client, auth_headers,
                                                   db_session, registered_user):
        """项目 editor 成员可编辑他人人工条目(权限矩阵 editor ✅)"""
        project = await _mk_project(db_session, registered_user["user_id"])
        entry = await _mk_entry(db_session, project.project_id)
        editor = await _mk_user(client)
        await _mk_member(db_session, project.project_id, editor["user_id"], role="editor")

        resp = await client.patch(
            f"/api/knowledge/{entry.entry_id}",
            json={"title": "editor 改的新标题"},
            headers=editor["headers"],
        )
        assert resp.status_code == 200, (
            f"项目 editor 编辑他人人工条目应 200,实际 {resp.status_code}{resp.text[:160]}"
        )
        row = await _get_row(db_session, entry.entry_id)
        assert row.title == "editor 改的新标题", f"editor 编辑应落库,实际 {row.title}"

    @pytest.mark.asyncio
    async def test_viewer_patch_others_entry_403(self, client, auth_headers,
                                                 db_session, registered_user):
        """非创建者 viewer → 403 code=1901(权限矩阵 viewer ❌;完成判据异常分支)"""
        project = await _mk_project(db_session, registered_user["user_id"])
        entry = await _mk_entry(db_session, project.project_id)
        viewer = await _mk_user(client)
        await _mk_member(db_session, project.project_id, viewer["user_id"], role="viewer")

        resp = await client.patch(
            f"/api/knowledge/{entry.entry_id}",
            json={"title": "viewer 不该改得动"},
            headers=viewer["headers"],
        )
        assert resp.status_code == 403, (
            f"viewer 编辑他人条目应 403,实际 {resp.status_code}"
            f"(PATCH 路由未实现时 405){resp.text[:160]}"
        )
        assert resp.json()["code"] == 1901
        row = await _get_row(db_session, entry.entry_id)
        assert row.title == entry.title, "403 后条目标题不应被改动"

    @pytest.mark.asyncio
    async def test_platform_entry_patch_creator_still_403_superadmin_ok(self, client,
                                                                        db_session,
                                                                        registered_user):
        """平台级条目:创建者本人(非超管)PATCH → 403;超管 → 200 且落库(矩阵:仅超管)
        (registered_user 占首注册 superadmin 引导位,creator 才是普通用户)"""
        creator = await _mk_user(client)
        entry = await _mk_entry(db_session, None, title="平台级条目",
                                creator_user_id=creator["user_id"])

        resp_creator = await client.patch(
            f"/api/knowledge/{entry.entry_id}",
            json={"title": "创建者想改平台级"},
            headers=creator["headers"],
        )
        assert resp_creator.status_code == 403, (
            f"平台级条目创建者本人(非超管)应 403,实际 {resp_creator.status_code}"
            f"{resp_creator.text[:160]}"
        )

        superadmin = await _mk_superadmin_user(client, db_session)

        resp_admin = await client.patch(
            f"/api/knowledge/{entry.entry_id}",
            json={"title": "超管改的平台级标题"},
            headers=superadmin["headers"],
        )
        assert resp_admin.status_code == 200, (
            f"超管编辑平台级条目应 200,实际 {resp_admin.status_code}{resp_admin.text[:160]}"
        )
        row = await _get_row(db_session, entry.entry_id)
        assert row.title == "超管改的平台级标题", f"超管编辑应落库,实际 {row.title}"

    @pytest.mark.asyncio
    async def test_historical_entry_null_creator_viewer_403_owner_ok(self, client,
                                                                     db_session,
                                                                     registered_user):
        """历史行(created_by_user_id NULL):无创建者可判 → viewer 403(回落安全),
        owner 仍可编(存量行策略;完成判据:创建者不可编,owner 可编)
        (registered_user 占引导位,owner 走 project.owner_id 非超管路径)"""
        owner = await _mk_user(client)
        project = await _mk_project(db_session, owner["user_id"])
        entry = await _mk_entry(db_session, project.project_id,
                                title="历史存量条目")   # 不带 created_by_user_id = 历史行
        viewer = await _mk_user(client)
        await _mk_member(db_session, project.project_id, viewer["user_id"], role="viewer")

        resp_viewer = await client.patch(
            f"/api/knowledge/{entry.entry_id}",
            json={"title": "历史行 viewer 不该改得动"},
            headers=viewer["headers"],
        )
        assert resp_viewer.status_code == 403, (
            f"历史行(NULL 创建者)viewer 应 403(回落按角色判),实际 {resp_viewer.status_code}"
            f"{resp_viewer.text[:160]}"
        )

        resp_owner = await client.patch(
            f"/api/knowledge/{entry.entry_id}",
            json={"title": "历史行 owner 改的标题"},
            headers=owner["headers"],
        )
        assert resp_owner.status_code == 200, (
            f"历史行 owner 应可编辑(回落不应收紧到全部拒绝),实际 {resp_owner.status_code}"
            f"{resp_owner.text[:160]}"
        )
        row = await _get_row(db_session, entry.entry_id)
        assert row.title == "历史行 owner 改的标题"


# ---------------------------------------------------------------------------
# 2. PATCH — AI 条目字段白名单(正文归档产物不可改)
# ---------------------------------------------------------------------------
class TestPatchAiEntry:
    @pytest.mark.asyncio
    async def test_ai_entry_patch_content_returns_400_20013(self, client, auth_headers,
                                                            db_session, registered_user):
        """AI 条目 PATCH content → 400 + 20013「AI 条目仅支持编辑标签」(完成判据异常分支)"""
        project = await _mk_project(db_session, registered_user["user_id"])
        entry = await _mk_entry(db_session, project.project_id, created_by="ai",
                                title="AI 归档条目")
        editor = await _mk_user(client)
        await _mk_member(db_session, project.project_id, editor["user_id"], role="editor")

        resp = await client.patch(
            f"/api/knowledge/{entry.entry_id}",
            json={"content": "试图篡改 AI 归档正文"},
            headers=editor["headers"],
        )
        body = _assert_biz_400(resp, KB_AI_ONLY_TAGS)
        assert "仅" in (body.get("message") or ""), (
            f"message 应提示仅支持编辑标签,实际 {body.get('message')!r}"
        )
        row = await _get_row(db_session, entry.entry_id)
        assert row.content == entry.content, "400 后 AI 条目正文不应被改动"

    @pytest.mark.asyncio
    async def test_ai_entry_patch_tags_success(self, client, auth_headers,
                                               db_session, registered_user):
        """AI 条目 PATCH tags → 200 且落库(完成判据正常分支);正文保持不变"""
        project = await _mk_project(db_session, registered_user["user_id"])
        entry = await _mk_entry(db_session, project.project_id, created_by="ai")
        editor = await _mk_user(client)
        await _mk_member(db_session, project.project_id, editor["user_id"], role="editor")

        resp = await client.patch(
            f"/api/knowledge/{entry.entry_id}",
            json={"tags": ["ai", "归档"]},
            headers=editor["headers"],
        )
        assert resp.status_code == 200, (
            f"AI 条目 PATCH tags 应 200,实际 {resp.status_code}{resp.text[:160]}"
        )
        row = await _get_row(db_session, entry.entry_id)
        assert row.tags == ["ai", "归档"], f"AI 条目 tags 应更新,实际 {row.tags}"
        assert row.content == entry.content, "AI 条目正文不应被连带改动"


# ---------------------------------------------------------------------------
# 3. DELETE /api/knowledge/{entry_id}
# ---------------------------------------------------------------------------
class TestDeleteEntry:
    @pytest.mark.asyncio
    async def test_creator_deletes_own_entry_then_detail_404_list_clean(self, client,
                                                                        db_session,
                                                                        registered_user):
        """创建者删自己的人工条目成功;删除后 detail 404 + 项目列表移除(完成判据)"""
        project = await _mk_project(db_session, registered_user["user_id"])
        creator = await _mk_user(client)
        await _mk_member(db_session, project.project_id, creator["user_id"], role="viewer")
        entry_id = await _create_entry_api(client, creator["headers"], project.project_id)

        resp = await client.delete(f"/api/knowledge/{entry_id}", headers=creator["headers"])
        assert resp.status_code == 200, (
            f"创建者删除自己的条目应 200,实际 {resp.status_code}"
            f"(DELETE 路由未实现时 405){resp.text[:160]}"
        )
        assert resp.json()["code"] == 0

        detail = await client.get(f"/api/knowledge/{entry_id}", headers=creator["headers"])
        assert detail.status_code == 404, (
            f"删除后详情应 404,实际 {detail.status_code}"
        )
        listing = await client.get(
            f"/api/projects/{project.project_id}/knowledge", headers=creator["headers"])
        assert listing.status_code == 200
        ids = [it["entry_id"] for it in listing.json()["data"]["items"]]
        assert entry_id not in ids, f"删除后项目列表不应再含该条目,实际 {ids}"

    @pytest.mark.asyncio
    async def test_owner_deletes_others_entry(self, client, db_session, registered_user):
        """项目 owner 删他人条目成功;删除后 detail 404(矩阵:owner ✅;
        registered_user 占引导位,owner 判定走 project.owner_id)"""
        owner = await _mk_user(client)
        project = await _mk_project(db_session, owner["user_id"])
        entry = await _mk_entry(db_session, project.project_id)

        resp = await client.delete(f"/api/knowledge/{entry.entry_id}", headers=owner["headers"])
        assert resp.status_code == 200, (
            f"项目 owner 删除他人条目应 200,实际 {resp.status_code}{resp.text[:160]}"
        )
        detail = await client.get(f"/api/knowledge/{entry.entry_id}", headers=owner["headers"])
        assert detail.status_code == 404, f"删除后详情应 404,实际 {detail.status_code}"

    @pytest.mark.asyncio
    async def test_editor_deletes_others_entry(self, client, auth_headers,
                                               db_session, registered_user):
        """项目 editor 删他人条目成功(R3 口径:owner/editor 可删,B1 收口)"""
        project = await _mk_project(db_session, registered_user["user_id"])
        entry = await _mk_entry(db_session, project.project_id)
        editor = await _mk_user(client)
        await _mk_member(db_session, project.project_id, editor["user_id"], role="editor")

        resp = await client.delete(f"/api/knowledge/{entry.entry_id}", headers=editor["headers"])
        assert resp.status_code == 200, (
            f"项目 editor 删除他人条目应 200,实际 {resp.status_code}{resp.text[:160]}"
        )

    @pytest.mark.asyncio
    async def test_viewer_delete_403_and_entry_survives(self, client, auth_headers,
                                                        db_session, registered_user):
        """viewer 删他人条目 → 403/1901,且条目未被删除(异常分支)"""
        project = await _mk_project(db_session, registered_user["user_id"])
        entry = await _mk_entry(db_session, project.project_id)
        viewer = await _mk_user(client)
        await _mk_member(db_session, project.project_id, viewer["user_id"], role="viewer")

        resp = await client.delete(f"/api/knowledge/{entry.entry_id}", headers=viewer["headers"])
        assert resp.status_code == 403, (
            f"viewer 删除他人条目应 403,实际 {resp.status_code}"
            f"(DELETE 路由未实现时 405){resp.text[:160]}"
        )
        assert resp.json()["code"] == 1901
        row = await _get_row(db_session, entry.entry_id)
        assert row.entry_id == entry.entry_id, "403 后条目不应被删除"

    @pytest.mark.asyncio
    async def test_platform_entry_delete_creator_not_allowed_superadmin_ok(self, client,
                                                                           db_session,
                                                                           registered_user):
        """平台级条目:创建者本人(非超管)DELETE → 403;超管删除成功 → detail 404
        (完成判据:平台级非超管 DELETE 403,超管删除成功;矩阵:创建者本人 ❌;
        registered_user 占首注册 superadmin 引导位,creator 才是普通用户)"""
        creator = await _mk_user(client)
        entry = await _mk_entry(db_session, None, title="平台级待删条目",
                                creator_user_id=creator["user_id"])
        superadmin = await _mk_superadmin_user(client, db_session)

        resp_creator = await client.delete(
            f"/api/knowledge/{entry.entry_id}", headers=creator["headers"])
        assert resp_creator.status_code == 403, (
            f"平台级条目创建者本人(非超管)删除应 403,实际 {resp_creator.status_code}"
            f"{resp_creator.text[:160]}"
        )
        row = await _get_row(db_session, entry.entry_id)
        assert row.entry_id == entry.entry_id, "403 后平台级条目不应被删除"

        resp_admin = await client.delete(
            f"/api/knowledge/{entry.entry_id}", headers=superadmin["headers"])
        assert resp_admin.status_code == 200, (
            f"超管删除平台级条目应 200,实际 {resp_admin.status_code}{resp_admin.text[:160]}"
        )
        detail = await client.get(f"/api/knowledge/{entry.entry_id}",
                                  headers=superadmin["headers"])
        assert detail.status_code == 404, f"超管删除后详情应 404,实际 {detail.status_code}"


# ---------------------------------------------------------------------------
# 4. 数据模型变更:created_by_user_id 落库(迁移后列存在;create 写 operator.user_id)
# ---------------------------------------------------------------------------
class TestCreatedByUserIdColumn:
    @pytest.mark.asyncio
    async def test_created_by_user_id_persisted_after_create(self, client, db_session,
                                                             registered_user):
        """完成判据:新创建条目 created_by_user_id 正确落库=create 操作人 user_id
        (Red:迁移/模型列未建,直查 model 字段命中哨兵 → 断言失败)"""
        project = await _mk_project(db_session, registered_user["user_id"])
        creator = await _mk_user(client)
        await _mk_member(db_session, project.project_id, creator["user_id"], role="viewer")

        entry_id = await _create_entry_api(client, creator["headers"], project.project_id)
        row = await _get_row(db_session, entry_id)
        assert row.created_by == "human"

        persisted = getattr(row, "created_by_user_id", "<column-missing>")
        assert persisted == creator["user_id"], (
            f"create 后 created_by_user_id 应落操作人 {creator['user_id']},"
            f"实际 {persisted!r}('<column-missing>' = 模型尚无该列,迁移未创建)"
        )


# ---------------------------------------------------------------------------
# 5. detail permissions 新口径(R3:创建者维度 + can_delete)
# ---------------------------------------------------------------------------
class TestDetailPermissionsR3:
    @pytest.mark.asyncio
    async def test_creator_low_role_can_edit_delete_true(self, client, db_session,
                                                         registered_user):
        """创建者本人(项目 viewer 角色)detail permissions:can_edit=true / can_delete=true
        (R3 新口径:创建者 ✅ 不依赖项目角色;现实现按角色算 → Red)"""
        project = await _mk_project(db_session, registered_user["user_id"])
        creator = await _mk_user(client)
        await _mk_member(db_session, project.project_id, creator["user_id"], role="viewer")
        entry_id = await _create_entry_api(client, creator["headers"], project.project_id)

        detail = await client.get(f"/api/knowledge/{entry_id}", headers=creator["headers"])
        assert detail.status_code == 200
        perms = detail.json()["data"].get("permissions")
        assert perms is not None, "detail 响应缺 permissions 块"
        assert perms.get("can_edit") is True, (
            f"创建者本人(低角色)can_edit 应 True(R3 创建者口径),实际 {perms}"
        )
        assert perms.get("can_delete") is True, (
            f"创建者本人(低角色)can_delete 应 True(R3 创建者口径),实际 {perms}"
        )

    @pytest.mark.asyncio
    async def test_ai_entry_creator_permissions_tags_only(self, client, db_session,
                                                          registered_user):
        """AI 条目创建者(低角色):can_edit=true 但 editable_fields==['tags'](矩阵:仅 tags;
        registered_user 占引导位,creator 为普通用户)"""
        owner = await _mk_user(client)
        project = await _mk_project(db_session, owner["user_id"])
        creator = await _mk_user(client)
        await _mk_member(db_session, project.project_id, creator["user_id"], role="viewer")
        entry = await _mk_entry(db_session, project.project_id, created_by="ai",
                                creator_user_id=creator["user_id"])

        detail = await client.get(f"/api/knowledge/{entry.entry_id}",
                                  headers=creator["headers"])
        assert detail.status_code == 200
        perms = detail.json()["data"].get("permissions")
        assert perms is not None, "detail 响应缺 permissions 块"
        assert perms.get("can_edit") is True, (
            f"AI 条目创建者 can_edit 应 True(仅 tags 范围),实际 {perms}"
        )
        assert perms.get("editable_fields") == ["tags"], (
            f"AI 条目创建者 editable_fields 应仅 ['tags'],实际 {perms.get('editable_fields')}"
        )

    @pytest.mark.asyncio
    async def test_non_creator_viewer_false_editor_true(self, client, auth_headers,
                                                        db_session, registered_user):
        """非创建者口径回归基线:viewer false/false、editor true/true(可删;存量已实现,
        预期基线 Green,R3 改动不得破坏)"""
        project = await _mk_project(db_session, registered_user["user_id"])
        entry = await _mk_entry(db_session, project.project_id)
        viewer = await _mk_user(client)
        editor = await _mk_user(client)
        await _mk_member(db_session, project.project_id, viewer["user_id"], role="viewer")
        await _mk_member(db_session, project.project_id, editor["user_id"], role="editor")

        pv = (await client.get(f"/api/knowledge/{entry.entry_id}",
                               headers=viewer["headers"])).json()["data"]["permissions"]
        assert pv.get("can_delete") is False, f"非创建者 viewer can_delete 应 False,实际 {pv}"
        assert pv.get("can_edit") is False, f"非创建者 viewer can_edit 应 False,实际 {pv}"

        pe = (await client.get(f"/api/knowledge/{entry.entry_id}",
                               headers=editor["headers"])).json()["data"]["permissions"]
        assert pe.get("can_delete") is True, f"editor can_delete 应 True,实际 {pe}"
        assert pe.get("can_edit") is True, f"editor can_edit 应 True,实际 {pe}"

    @pytest.mark.asyncio
    async def test_platform_entry_permissions_creator_false_superadmin_true(self, client,
                                                                            db_session,
                                                                            registered_user):
        """平台级条目 permissions 基线:普通用户(含创建者本人)false/false,超管 true/true
        (registered_user 占首注册 superadmin 引导位,creator 为普通用户)"""
        creator = await _mk_user(client)
        entry = await _mk_entry(db_session, None, title="平台级权限条目",
                                creator_user_id=creator["user_id"])
        superadmin = await _mk_superadmin_user(client, db_session)

        pc = (await client.get(f"/api/knowledge/{entry.entry_id}",
                               headers=creator["headers"])).json()["data"]["permissions"]
        assert pc.get("can_edit") is False and pc.get("can_delete") is False, (
            f"平台级创建者(非超管)应 false/false,实际 {pc}"
        )

        pa = (await client.get(f"/api/knowledge/{entry.entry_id}",
                               headers=superadmin["headers"])).json()["data"]["permissions"]
        assert pa.get("can_edit") is True and pa.get("can_delete") is True, (
            f"平台级超管应 true/true,实际 {pa}"
        )


# ---------------------------------------------------------------------------
# 辅助:造一个非首注册的超管(superadmin_headers fixture 逻辑的用户版,可复用多次)
# ---------------------------------------------------------------------------
async def _mk_superadmin_user(client, db_session):
    import uuid

    from sqlalchemy import text

    phone = f"139{str(uuid.uuid4().int)[:8]}"
    password = "Admin1234"
    resp = await client.post("/api/auth/register", json={"phone": phone, "password": password})
    assert resp.status_code == 200 and resp.json()["code"] == 0
    user_id = resp.json()["data"]["user_id"]
    await db_session.execute(
        text("UPDATE users SET role = 'superadmin' WHERE user_id = :uid"), {"uid": user_id})
    await db_session.commit()
    resp = await client.post("/api/auth/login", json={"phone": phone, "password": password})
    assert resp.status_code == 200
    return {"headers": {"Authorization": f"Bearer {resp.json()['data']['access_token']}"},
            "user_id": user_id}
