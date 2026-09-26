"""
R5 交付时间字段(delivery_date)— TDD Red 测试
==========================================
覆盖(DEVPLAN/R5.md 接口契约 + 完成判据):
1. 创建带 delivery_date="2026-10-15" → 200,详情返回该日期(ISO 口径按 schema 实际,断言含值)
2. 不传 / 显式 None → 创建成功,detail 含 delivery_date 键且为空
3. PATCH 设置日期生效;PATCH 置 null 清空生效
4. 非法日期字符串 "not-a-date" → 422(pydantic date 校验)
5. R1/R4 回归:tests/test_requirement_related_users.py、tests/test_requirement_prototype_links.py
   独立既有文件,由 qa-red 命令单独跑,不在本文件重复

注意(Red 阶段):requirements.delivery_date 列已随 R1 迁移预置于 model,
但 Create/Update/Response schema 均无该字段 —— Pydantic 忽略未知字段后:
- 创建/PATCH 传入的日期被静默丢弃
- 详情无 delivery_date 键(KeyError / `"delivery_date" in detail` 失败)
- "not-a-date" 被忽略 → 200 ≠ 422
Green 后全部转绿。
"""
import httpx
import pytest

from tests.test_requirements_api import _gitlab_branch_handler, _setup_project


# ---------------------------------------------------------------------------
# 辅助(与 test_requirement_prototype_links.py 同口径)
# ---------------------------------------------------------------------------
async def _create_requirement(client, auth_headers, project, payload: dict) -> httpx.Response:
    """创建需求(GitLab mock 建分支),返回原始 Response"""
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


def _assert_date_value(detail: dict, expect: str) -> None:
    """响应 schema 必须含 delivery_date 键,且值含 expect(ISO 日期容错 T00:00:00 后缀)"""
    assert "delivery_date" in detail, f"响应缺 delivery_date 字段: keys={sorted(detail)}"
    val = detail["delivery_date"]
    assert val is not None, f"delivery_date 应为 {expect},实际 None"
    assert expect in str(val), f"delivery_date 应含 {expect},实际 {val!r}"


# ---------------------------------------------------------------------------
# 1. 创建带 delivery_date → 200,详情返回该日期
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_create_with_delivery_date_roundtrip(client, auth_headers, db_session, registered_user):
    """创建带 delivery_date="2026-10-15" → 200;详情返回含 "2026-10-15" 的日期值"""
    project = await _setup_project(db_session, registered_user)

    resp = await _create_requirement(client, auth_headers, project, {
        "title": "交付时间需求",
        "description": "d",
        "delivery_date": "2026-10-15",
    })
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["code"] == 0, body

    detail = await _get_detail(client, auth_headers, body["data"]["req_id"])
    _assert_date_value(detail, "2026-10-15")  # Red: 响应无 delivery_date 键


@pytest.mark.asyncio
async def test_create_delivery_date_past_allowed(client, auth_headers, db_session, registered_user):
    """契约:无「早于今天」限制 → 过去日期 2020-01-01 也应 200 并回读"""
    project = await _setup_project(db_session, registered_user)

    resp = await _create_requirement(client, auth_headers, project, {
        "title": "过去日期允许",
        "description": "d",
        "delivery_date": "2020-01-01",
    })
    assert resp.status_code == 200, resp.text

    detail = await _get_detail(client, auth_headers, resp.json()["data"]["req_id"])
    _assert_date_value(detail, "2020-01-01")


# ---------------------------------------------------------------------------
# 2. 不传 / None → 创建成功,delivery_date 为空
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_create_without_delivery_date_empty(client, auth_headers, db_session, registered_user):
    """不传 delivery_date → 创建 200,详情 delivery_date 键存在且为空(None)"""
    project = await _setup_project(db_session, registered_user)

    resp = await _create_requirement(client, auth_headers, project, {
        "title": "无交付时间",
        "description": "d",
    })
    assert resp.status_code == 200, resp.text

    detail = await _get_detail(client, auth_headers, resp.json()["data"]["req_id"])
    assert "delivery_date" in detail, f"响应缺 delivery_date 字段: keys={sorted(detail)}"
    assert detail["delivery_date"] in (None, ""), f"应为空,实际 {detail['delivery_date']!r}"


@pytest.mark.asyncio
async def test_create_delivery_date_explicit_none_empty(client, auth_headers, db_session, registered_user):
    """显式传 delivery_date=None → 创建 200,详情为空"""
    project = await _setup_project(db_session, registered_user)

    resp = await _create_requirement(client, auth_headers, project, {
        "title": "显式None",
        "description": "d",
        "delivery_date": None,
    })
    assert resp.status_code == 200, resp.text

    detail = await _get_detail(client, auth_headers, resp.json()["data"]["req_id"])
    assert "delivery_date" in detail, f"响应缺 delivery_date 字段: keys={sorted(detail)}"
    assert detail["delivery_date"] in (None, ""), f"应为空,实际 {detail['delivery_date']!r}"


# ---------------------------------------------------------------------------
# 3. PATCH 设置 / 置 null 清空
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_patch_set_then_null_delivery_date(client, auth_headers, db_session, registered_user):
    """PATCH 设 2026-12-01 生效;再 PATCH null 清空生效"""
    project = await _setup_project(db_session, registered_user)

    resp = await _create_requirement(client, auth_headers, project, {
        "title": "交付时间编辑", "description": "d",
    })
    assert resp.status_code == 200, resp.text
    req_id = resp.json()["data"]["req_id"]

    # PATCH 设置
    resp = await client.patch(
        f"/api/requirements/{req_id}",
        headers=auth_headers,
        json={"delivery_date": "2026-12-01"},
    )
    assert resp.status_code == 200, resp.text
    detail = await _get_detail(client, auth_headers, req_id)
    _assert_date_value(detail, "2026-12-01")  # Red: 字段被忽略 → 响应无键

    # PATCH 置 null 清空
    resp = await client.patch(
        f"/api/requirements/{req_id}",
        headers=auth_headers,
        json={"delivery_date": None},
    )
    assert resp.status_code == 200, resp.text
    detail = await _get_detail(client, auth_headers, req_id)
    assert "delivery_date" in detail, f"响应缺 delivery_date 字段: keys={sorted(detail)}"
    assert detail["delivery_date"] in (None, ""), f"置 null 应清空,实际 {detail['delivery_date']!r}"


# ---------------------------------------------------------------------------
# 4. 非法日期字符串 → 422(pydantic 校验)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
@pytest.mark.parametrize("bad_date", ["not-a-date", "2026-13-40", "15/10/2026"])
async def test_create_invalid_delivery_date_422(client, auth_headers, db_session, registered_user, bad_date):
    """delivery_date 非法字符串 → 422(类型为 date,pydantic 校验拒绝)"""
    project = await _setup_project(db_session, registered_user)

    resp = await _create_requirement(client, auth_headers, project, {
        "title": "非法日期",
        "description": "d",
        "delivery_date": bad_date,
    })
    assert resp.status_code == 422, f"应 422,实际 {resp.status_code}: {resp.text}"  # Red: 被忽略 → 200


@pytest.mark.asyncio
async def test_patch_invalid_delivery_date_422(client, auth_headers, db_session, registered_user):
    """PATCH 非法日期同样 422"""
    project = await _setup_project(db_session, registered_user)

    resp = await _create_requirement(client, auth_headers, project, {
        "title": "PATCH非法日期", "description": "d",
    })
    assert resp.status_code == 200, resp.text
    req_id = resp.json()["data"]["req_id"]

    resp = await client.patch(
        f"/api/requirements/{req_id}",
        headers=auth_headers,
        json={"delivery_date": "not-a-date"},
    )
    assert resp.status_code == 422, f"应 422,实际 {resp.status_code}: {resp.text}"  # Red: 200
