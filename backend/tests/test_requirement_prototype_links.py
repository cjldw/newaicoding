"""
R4 原型链接字段(多条)— TDD Red 测试
==========================================
覆盖(DEVPLAN/R4.md 完成判据 + 接口契约):
1. 创建带 prototype_links=[{label:"原型",url:"https://x"},{label:"",url:"https://y"}]
   → 200,详情返回 2 条(label 空串保留,不转 None 丢字段)
2. 超 10 条(第 11 条)→ 400(整组显式拒绝,与关联用户静默剔除不同)
3. url 非 http(s)(ftp://x、纯文本)→ 400
4. label 超 20 字 → 截断 20(分片口径:截断,非 400)
5. PATCH 更新增/删链接生效;空数组 = 清空
6. R1 回归:tests/test_requirement_related_users.py 独立文件,不在本文件覆盖

注意(Red 阶段):requirements.prototype_links 列 / schema 字段 / service 校验
均未实现 —— Pydantic 忽略未知字段后详情无 prototype_links 键(KeyError),
校验类用例预期 200≠400 断言失败。Green 后全部转绿。
"""
import uuid

import httpx
import pytest

from tests.test_requirements_api import _gitlab_branch_handler, _setup_project


# ---------------------------------------------------------------------------
# 辅助(照抄 test_requirement_related_users.py fixture 口径)
# ---------------------------------------------------------------------------
async def _create_requirement(client, auth_headers, project, payload: dict) -> httpx.Response:
    """创建需求(GitLab mock 建分支),返回原始 Response(R4 需断言 400)"""
    calls: list = []
    with httpx.MockTransport(_gitlab_branch_handler(calls)):
        return await client.post(
            f"/api/projects/{project.project_id}/requirements",
            headers=auth_headers,
            json=payload,
        )


async def _get_detail(client, auth_headers, req_id: str) -> dict:
    resp = await client.get(f"/api/requirements/{req_id}", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]


def _assert_400(resp: httpx.Response) -> None:
    """整组显式拒绝口径:HTTP 400 + body code=400"""
    body = resp.json()
    assert resp.status_code == 400, f"应 400,实际 {resp.status_code}: {body}"
    assert body["code"] == 400, body


# ---------------------------------------------------------------------------
# 1. 创建带 2 条链接(含空 label)→ 详情返回 2 条,label 空保留
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_create_with_two_links_keeps_empty_label(client, auth_headers, db_session, registered_user):
    """创建带 2 条 prototype_links → 200,详情 2 条;空 label 保留不丢"""
    project = await _setup_project(db_session, registered_user)

    resp = await _create_requirement(client, auth_headers, project, {
        "title": "原型链接需求",
        "description": "d",
        "prototype_links": [
            {"label": "原型", "url": "https://example.com/proto"},
            {"label": "", "url": "https://example.com/y"},
        ],
    })
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["code"] == 0, body

    detail = await _get_detail(client, auth_headers, body["data"]["req_id"])
    links = detail["prototype_links"]  # Red: KeyError(字段未实现)
    assert isinstance(links, list) and len(links) == 2, links
    assert links[0] == {"label": "原型", "url": "https://example.com/proto"}, links[0]
    assert links[1]["label"] == "", f"空 label 应保留(空串),实际 {links[1]!r}"
    assert links[1]["url"] == "https://example.com/y", links[1]


# ---------------------------------------------------------------------------
# 2. 超 10 条 → 400(第 11 条拒绝,整组)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_create_with_eleven_links_rejected(client, auth_headers, db_session, registered_user):
    """prototype_links 传 11 条 → 400,整组拒绝"""
    project = await _setup_project(db_session, registered_user)
    links = [{"label": f"L{i}", "url": f"https://example.com/{i}"} for i in range(11)]

    resp = await _create_requirement(client, auth_headers, project, {
        "title": "超链接上限",
        "description": "d",
        "prototype_links": links,
    })
    _assert_400(resp)  # Red: 字段被忽略 → 200 ≠ 400


@pytest.mark.asyncio
async def test_create_with_exactly_ten_links_ok(client, auth_headers, db_session, registered_user):
    """边界:恰好 10 条 → 200(上限含等号)"""
    project = await _setup_project(db_session, registered_user)
    links = [{"label": f"L{i}", "url": f"https://example.com/{i}"} for i in range(10)]

    resp = await _create_requirement(client, auth_headers, project, {
        "title": "十条链接边界",
        "description": "d",
        "prototype_links": links,
    })
    assert resp.status_code == 200, resp.text
    detail = await _get_detail(client, auth_headers, resp.json()["data"]["req_id"])
    assert len(detail["prototype_links"]) == 10, detail  # Red: KeyError


# ---------------------------------------------------------------------------
# 3. url 非 http(s) → 400
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize("bad_url", ["ftp://example.com/x", "纯文本不是URL", "javascript:alert(1)"])
async def test_create_with_non_http_url_rejected(client, auth_headers, db_session, registered_user, bad_url):
    """url 不以 http(s):// 开头(ftp://、纯文本、javascript:)→ 400"""
    project = await _setup_project(db_session, registered_user)

    resp = await _create_requirement(client, auth_headers, project, {
        "title": "非法URL",
        "description": "d",
        "prototype_links": [{"label": "原型", "url": bad_url}],
    })
    _assert_400(resp)  # Red: 字段被忽略 → 200 ≠ 400


# ---------------------------------------------------------------------------
# 4. label 超 20 字 → 截断 20(分片口径:截断)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_create_label_over_20_truncated(client, auth_headers, db_session, registered_user):
    """label 25 字 → 截断为前 20 字,创建 200"""
    project = await _setup_project(db_session, registered_user)
    long_label = "标" * 25  # 25 个汉字

    resp = await _create_requirement(client, auth_headers, project, {
        "title": "label截断",
        "description": "d",
        "prototype_links": [{"label": long_label, "url": "https://example.com/x"}],
    })
    assert resp.status_code == 200, resp.text

    detail = await _get_detail(client, auth_headers, resp.json()["data"]["req_id"])
    links = detail["prototype_links"]  # Red: KeyError
    assert len(links) == 1, links
    assert links[0]["label"] == "标" * 20, f"应截断 20 字,实际 {links[0]['label']!r}"


# ---------------------------------------------------------------------------
# 5. PATCH 更新:增/删生效;空数组 = 清空
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_patch_links_add_remove_and_clear(client, auth_headers, db_session, registered_user):
    """PATCH 增链接 → 3 条;再删 1 条 → 2 条;空数组 → 清空 []"""
    project = await _setup_project(db_session, registered_user)
    req_id = None

    # 初建 2 条
    resp = await _create_requirement(client, auth_headers, project, {
        "title": "链接编辑需求",
        "description": "d",
        "prototype_links": [
            {"label": "原型", "url": "https://example.com/a"},
            {"label": "设计", "url": "https://example.com/b"},
        ],
    })
    assert resp.status_code == 200, resp.text
    req_id = resp.json()["data"]["req_id"]

    # PATCH 增第 3 条 → 3 条
    resp = await client.patch(
        f"/api/requirements/{req_id}",
        headers=auth_headers,
        json={"prototype_links": [
            {"label": "原型", "url": "https://example.com/a"},
            {"label": "设计", "url": "https://example.com/b"},
            {"label": "视觉稿", "url": "https://example.com/c"},
        ]},
    )
    assert resp.status_code == 200, resp.text
    detail = await _get_detail(client, auth_headers, req_id)
    links = detail["prototype_links"]  # Red: KeyError
    assert len(links) == 3 and links[-1]["label"] == "视觉稿", links

    # PATCH 删中间 1 条(保留原型+视觉稿)→ 2 条
    resp = await client.patch(
        f"/api/requirements/{req_id}",
        headers=auth_headers,
        json={"prototype_links": [
            {"label": "原型", "url": "https://example.com/a"},
            {"label": "视觉稿", "url": "https://example.com/c"},
        ]},
    )
    assert resp.status_code == 200, resp.text
    detail = await _get_detail(client, auth_headers, req_id)
    assert [l["label"] for l in detail["prototype_links"]] == ["原型", "视觉稿"], detail

    # PATCH 空数组 → 清空
    resp = await client.patch(
        f"/api/requirements/{req_id}",
        headers=auth_headers,
        json={"prototype_links": []},
    )
    assert resp.status_code == 200, resp.text
    detail = await _get_detail(client, auth_headers, req_id)
    assert detail["prototype_links"] == [], f"空数组应清空,实际 {detail['prototype_links']!r}"
