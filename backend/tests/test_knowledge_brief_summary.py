"""
R4 列表摘要(summary)后端面 — Red 阶段失败测试
================================================
覆盖 DEVPLAN/R4.md「接口契约」「完成判据」「测试验证逻辑」:

1. GET /api/projects/{pid}/knowledge 与 GET /api/knowledge 列表项含 summary 字段
   (现 _entry_brief knowledge_service.py:23-34 无 summary → Red)
2. summary = content 去 markdown 标记(#/*/`/链接语法)后截前 100 字
   - 99/100/101 边界各一例(纯文本无标记,可全等断言 expected = content[:100])
   - 标记剔除用「含/不含」断言,兼容实现差异(是否折叠空白等)
   - 链接语法 [text](url) → 保留链接文字、隐藏 url(纯文本摘要语义)
3. A 型无 content 条目 summary 为空串(前端据 source_links 显示「关联代码 · n 个路径」
   占位,后端只给空串)
4. detail 回归:created_by_user_id(R4 契约「detail 同时返回 created_by_user_id 与
   permissions」,现 _entry_brief 未带 → Red)+ permissions 块(R3 已做,确认不破)

脚手架沿用 test_knowledge_entry_detail.py / test_knowledge_entry_create_code.py 写法。
"""
import uuid

import pytest

# 摘要截断长度(R4 契约:content 纯文本前 100 字)
SUMMARY_MAX_LEN = 100


# ---------------------------------------------------------------------------
# 测试辅助:用户 / 项目 / repo / 条目(沿用既有知识测试写法)
# ---------------------------------------------------------------------------
async def _mk_user(client):
    """注册并登录一个新用户,返回 {headers, user_id}"""
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
        name=f"R4 摘要项目 {uuid.uuid4().hex[:6]}",
        slug=f"r4s-{uuid.uuid4().hex[:8]}",
        owner_id=owner_id,
        status="active",
        visibility="private",
    )
    db_session.add(p)
    await db_session.flush()
    return p


async def _mk_repo(db_session, project_id):
    from app.models.project import ProjectRepo

    repo = ProjectRepo(
        project_id=project_id,
        role="main",
        gitlab_repo_url=f"https://gitlab.example.com/grp/repo-{uuid.uuid4().hex[:6]}.git",
        gitlab_repo_id=uuid.uuid4().int % 100000,
        gitlab_bind_type="auto",
        created_by=str(uuid.uuid4()),   # project_repos.created_by NOT NULL(既有测试同款必填)
    )
    db_session.add(repo)
    await db_session.flush()
    return repo


def _code_link(repo_id, branch="main", paths=None):
    """R1 定稿的 source_links code 对象(A 型条目)"""
    return [{"type": "code", "repo_id": repo_id, "branch": branch,
             "paths": paths or []}]


async def _create_entry(client, headers, project_id, **overrides):
    """POST /api/projects/{pid}/knowledge;缺省 B 型四字段,body 可覆盖"""
    payload = {
        "type": "code_snippet",
        "title": f"R4 条目 {uuid.uuid4().hex[:6]}",
        "content": "重试装饰器用法说明",
        "tags": ["python"],
    }
    payload.update(overrides)
    resp = await client.post(f"/api/projects/{project_id}/knowledge",
                             headers=headers, json=payload)
    assert resp.status_code == 200, f"创建条目应 200,实际 {resp.status_code} {resp.text[:160]}"
    body = resp.json()
    assert body["code"] == 0, f"code={body.get('code')} message={body.get('message')}"
    return body["data"]


async def _list_item_by_id(client, headers, list_url, entry_id) -> dict:
    """拉列表并按 entry_id 定位条目;返回列表项 dict"""
    resp = await client.get(list_url, headers=headers)
    assert resp.status_code == 200, f"列表应 200,实际 {resp.status_code}"
    data = resp.json()
    assert data["code"] == 0, f"code={data.get('code')} message={data.get('message')}"
    items = data["data"]["items"]
    item = next((i for i in items if i["entry_id"] == entry_id), None)
    assert item is not None, f"列表中应含条目 {entry_id},实际 {[i['entry_id'] for i in items]}"
    return item


# ---------------------------------------------------------------------------
# 1. 列表项含 summary 字段(项目库 / 平台库)
# ---------------------------------------------------------------------------
class TestListBriefHasSummary:
    @pytest.mark.asyncio
    async def test_project_list_item_has_summary(self, client, auth_headers, db_session,
                                                 registered_user):
        """GET /projects/{pid}/knowledge 列表项含 summary 字段(R4 契约)"""
        project = await _mk_project(db_session, registered_user["user_id"])
        entry = await _create_entry(client, auth_headers, project.project_id,
                                    content="# 重试装饰器\n用 *tenacity* 的 `retry`")

        item = await _list_item_by_id(
            client, auth_headers, f"/api/projects/{project.project_id}/knowledge",
            entry["entry_id"])
        assert "summary" in item, (
            f"项目库列表项缺 summary 字段(R4 契约):keys={sorted(item.keys())}"
        )
        assert isinstance(item["summary"], str), f"summary 应为字符串,实际 {item['summary']!r}"

    @pytest.mark.asyncio
    async def test_platform_list_item_has_summary(self, client, auth_headers, db_session,
                                                  registered_user):
        """GET /knowledge 平台库列表项含 summary 字段(提升平台级后可见)"""
        project = await _mk_project(db_session, registered_user["user_id"])
        entry = await _create_entry(client, auth_headers, project.project_id,
                                    content="cursor 分页模式说明")
        resp = await client.post(f"/api/knowledge/{entry['entry_id']}/promote",
                                 headers=auth_headers)
        assert resp.json()["code"] == 0, f"提升平台级应成功:{resp.text[:120]}"

        item = await _list_item_by_id(client, auth_headers, "/api/knowledge",
                                      entry["entry_id"])
        assert "summary" in item, (
            f"平台库列表项缺 summary 字段(R4 契约):keys={sorted(item.keys())}"
        )


# ---------------------------------------------------------------------------
# 2. markdown 标记剔除(#/*/`/链接语法)
# ---------------------------------------------------------------------------
class TestSummaryStripsMarkdown:
    @pytest.mark.asyncio
    async def test_hash_asterisk_backtick_removed(self, client, auth_headers, db_session,
                                                  registered_user):
        """summary 不含 #/*/` 标记字符,正文文字保留(契约:简单剔除,不做完整渲染)"""
        project = await _mk_project(db_session, registered_user["user_id"])
        entry = await _create_entry(
            client, auth_headers, project.project_id,
            content="# Redis 缓存实践 *必读* 用 `pipeline` 批量提交")

        item = await _list_item_by_id(
            client, auth_headers, f"/api/projects/{project.project_id}/knowledge",
            entry["entry_id"])
        summary = item.get("summary")
        assert summary is not None, f"缺 summary 字段:{sorted(item.keys())}"
        for mark in ("#", "*", "`"):
            assert mark not in summary, f"summary 不应含 markdown 标记 {mark!r},实际 {summary!r}"
        assert "Redis 缓存实践" in summary, f"标题文字应保留,实际 {summary!r}"
        assert "pipeline" in summary, f"行内代码文字应保留,实际 {summary!r}"

    @pytest.mark.asyncio
    async def test_link_syntax_removed(self, client, auth_headers, db_session,
                                       registered_user):
        """链接语法 [text](url) → 保留链接文字、url 不出现在纯文本摘要中"""
        project = await _mk_project(db_session, registered_user["user_id"])
        entry = await _create_entry(
            client, auth_headers, project.project_id,
            content="参见 [tenacity 文档](https://docs.example.com/retry) 的重试说明")

        item = await _list_item_by_id(
            client, auth_headers, f"/api/projects/{project.project_id}/knowledge",
            entry["entry_id"])
        summary = item.get("summary")
        assert summary is not None, f"缺 summary 字段:{sorted(item.keys())}"
        assert "](" not in summary, f"summary 不应残留链接语法 ]( ,实际 {summary!r}"
        assert "https://docs.example.com/retry" not in summary, (
            f"纯文本摘要不应出现链接 url,实际 {summary!r}"
        )
        assert "tenacity 文档" in summary, f"链接文字应保留,实际 {summary!r}"


# ---------------------------------------------------------------------------
# 2b. 截断边界:99 / 100 / 101(纯文本无标记,expected 全等)
# ---------------------------------------------------------------------------
class TestSummaryTruncate100:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("n", [99, 100, 101], ids=["99字不截", "100字不截", "101字截100"])
    async def test_truncation_boundary(self, client, auth_headers, db_session,
                                       registered_user, n):
        """纯文本 content 前 100 字截断:≤100 全等保留,101 截为前 100 字"""
        project = await _mk_project(db_session, registered_user["user_id"])
        content = "字" * n
        entry = await _create_entry(client, auth_headers, project.project_id,
                                    content=content)

        item = await _list_item_by_id(
            client, auth_headers, f"/api/projects/{project.project_id}/knowledge",
            entry["entry_id"])
        summary = item.get("summary")
        assert summary is not None, f"缺 summary 字段:{sorted(item.keys())}"
        expected = content[:SUMMARY_MAX_LEN]
        assert summary == expected, (
            f"{n} 字 content 的 summary 应为前 {min(n, SUMMARY_MAX_LEN)} 字"
            f"({len(expected)} 字),实际 {len(summary)} 字:{summary[:20]!r}..."
        )
        assert len(summary) <= SUMMARY_MAX_LEN, (
            f"summary 长度应 ≤{SUMMARY_MAX_LEN},实际 {len(summary)}"
        )


# ---------------------------------------------------------------------------
# 3. A 型无 content 条目:summary 为空串(前端按 source_links 显示占位)
# ---------------------------------------------------------------------------
class TestTypeAEmptySummary:
    @pytest.mark.asyncio
    async def test_type_a_no_content_summary_empty(self, client, auth_headers, db_session,
                                                   registered_user):
        """A 型(关联代码)content="" → 列表 summary == ""(空串,非缺失/null)"""
        project = await _mk_project(db_session, registered_user["user_id"])
        repo = await _mk_repo(db_session, project.project_id)
        entry = await _create_entry(
            client, auth_headers, project.project_id,
            content="", type="code_snippet",
            source_links=_code_link(repo.repo_id, paths=["backend/app/services/",
                                                          "backend/app/api/knowledge.py"]))

        item = await _list_item_by_id(
            client, auth_headers, f"/api/projects/{project.project_id}/knowledge",
            entry["entry_id"])
        summary = item.get("summary")
        assert summary is not None, f"缺 summary 字段:{sorted(item.keys())}"
        assert summary == "", (
            f"A 型无 content 条目 summary 应为空串(前端据 source_links 显示占位),"
            f"实际 {summary!r}"
        )


# ---------------------------------------------------------------------------
# 4. detail 回归:created_by_user_id(R4 契约补齐)+ permissions(R3 已做,确认不破)
# ---------------------------------------------------------------------------
class TestDetailRegression:
    @pytest.mark.asyncio
    async def test_detail_has_created_by_user_id(self, client, auth_headers, db_session,
                                                 registered_user):
        """detail 返回 created_by_user_id == 创建者用户 id(R4 契约;现 _entry_brief 未带 → Red)"""
        project = await _mk_project(db_session, registered_user["user_id"])
        entry = await _create_entry(client, auth_headers, project.project_id,
                                    content="创建者核对用条目")

        resp = await client.get(f"/api/knowledge/{entry['entry_id']}", headers=auth_headers)
        assert resp.status_code == 200, f"detail 应 200,实际 {resp.status_code}"
        data = resp.json()
        assert data["code"] == 0
        body = data["data"]
        assert body.get("created_by_user_id") == registered_user["user_id"], (
            f"detail 应返回 created_by_user_id(创建者 {registered_user['user_id']}),"
            f"实际 {body.get('created_by_user_id')!r};keys={sorted(body.keys())}"
        )

    @pytest.mark.asyncio
    async def test_detail_permissions_block_intact(self, client, auth_headers, db_session,
                                                   registered_user):
        """回归确认不破:R3 permissions 块仍在,创建者(owner)可编可删、全字段可编辑"""
        project = await _mk_project(db_session, registered_user["user_id"])
        entry = await _create_entry(client, auth_headers, project.project_id,
                                    content="permissions 回归用条目")

        resp = await client.get(f"/api/knowledge/{entry['entry_id']}", headers=auth_headers)
        assert resp.status_code == 200
        body = resp.json()["data"]
        perms = body.get("permissions")
        assert perms is not None, (
            f"detail 响应缺 permissions 块(R3 回归破坏):keys={sorted(body.keys())}"
        )
        assert perms.get("can_edit") is True, f"创建者(owner) can_edit 应 True,实际 {perms}"
        assert perms.get("can_delete") is True, f"创建者(owner) can_delete 应 True,实际 {perms}"
        fields = set(perms.get("editable_fields") or [])
        assert {"title", "content", "tags"} <= fields, (
            f"人工条目 editable_fields 应含 title/content/tags,实际 {sorted(fields)}"
        )
