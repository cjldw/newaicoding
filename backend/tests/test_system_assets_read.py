"""
R6(系统级只读展示)— GET /api/system-assets — QA TDD Red phase
================================================================
依据 docs/20260926_skills市场安装/DEVPLAN/R6.md(接口契约/完成判据):
    GET /api/system-assets(JWT):
      - 已采集 → {skills:[...], mcps:[...], collected_at, image_tag}
      - 未采集 → {collected:false}
    鉴权域:JWT 即可(任意登录用户可读;采集写入仍超管专属,见 R5 测试)。
    数据域:响应与 claude_system_assets 表内容一致(R5 已入库的快照)。

被测对象(Green 待实现,当前 404 → Red):
1. GET /api/system-assets(注意前缀与 R5 的 /api/admin/system-assets 不同)
2. 服务端行为:
   · 未登录(无 JWT)→ 401
   · 普通登录用户 → 200 可读(JWT 即可;R6 完成判据3:成员仅见展示不可采集)
   · 表空(从未采集)→ data.collected is False
   · 表有 2 skill + 1 mcp 行 → data.skills/mcps 名称与表一致,
     collected_at / image_tag 与表一致(两处展示一致的数据源)

数据注入:直接按 R5 落库字段写 claude_system_assets(模型已随 R5 合并,
engine fixture create_all 建表;db_session 清理列表不含此表 → 本文件自行清)。
真容器探测链路不在本轮(R5 已覆盖),此处只测读侧。
"""
import json
import uuid
from datetime import datetime

import pytest
import pytest_asyncio
from sqlalchemy import text

READ_URL = "/api/system-assets"
COLLECT_URL = "/api/admin/system-assets/collect"
TABLE = "claude_system_assets"

# 一次采集快照:2 skill + 1 mcp(R6 验证规格)
SEED_IMAGE_TAG = "platform/devbox:v2"
SEED_COLLECTED_AT = "2026-09-27 10:00:00"


async def _clear_assets(db):
    await db.execute(text(f"DELETE FROM {TABLE}"))
    await db.commit()


async def _seed_snapshot(db):
    """按 R5 落库字段规格造一次采集快照(2 skill + 1 mcp,同 collected_at/image_tag)"""
    rows = [
        ("skill-a", "skill", {"source": "/root/.claude/skills/skill-a"}),
        ("skill-b", "skill", {"source": "/root/.claude/skills/skill-b"}),
        ("fetch", "mcp", {"transport": "stdio", "command": "uvx mcp-server-fetch"}),
    ]
    for name, kind, detail in rows:
        await db.execute(text(
            f"INSERT INTO {TABLE} (name, kind, detail, collected_at, image_tag) "
            "VALUES (:n, :k, :d, :ts, :img)"
        ), {
            "n": name, "k": kind, "d": json.dumps(detail),
            "ts": SEED_COLLECTED_AT, "img": SEED_IMAGE_TAG,
        })
    await db.commit()


async def _table_rows(db) -> list[dict]:
    res = await db.execute(text(
        f"SELECT name, kind, detail, collected_at, image_tag FROM {TABLE} ORDER BY id"
    ))
    return [dict(r._mapping) for r in res]


def _names(items) -> list[str]:
    """列表项形状不锁(是否带 detail 等由 Green 定),仅要求可取到名称"""
    out = []
    for it in items:
        assert isinstance(it, dict), f"列表项应为对象: {it!r}"
        assert "name" in it, f"列表项缺 name(UI 展示依赖): {it!r}"
        out.append(it["name"])
    return sorted(out)


@pytest_asyncio.fixture
async def read_env(client, db_session):
    """读侧环境:清空快照表(前置/后置),返回 db 句柄"""
    await _clear_assets(db_session)
    yield {"db": db_session}
    await _clear_assets(db_session)


# ---------------------------------------------------------------------------
# 1. 鉴权:未登录 401;普通登录用户 JWT 即可读(非超管专属)
# ---------------------------------------------------------------------------
class TestReadAuth:
    @pytest.mark.asyncio
    async def test_read_requires_login(self, client):
        """未登录(无 JWT)→ 401(鉴权先行,不触达数据)"""
        resp = await client.get(READ_URL)
        assert resp.status_code == 401, resp.text

    @pytest.mark.asyncio
    async def test_read_allowed_for_normal_user(self, client, auth_headers, second_user_headers, read_env):
        """普通登录用户 → 200(JWT 即可读;系统级列表对项目侧只读展示开放)
        (auth_headers 先占「首个用户=superadmin」bootstrap 位,second_user_headers
        才是普通用户——R5 collect 文件同款 setup)"""
        resp = await client.get(READ_URL, headers=second_user_headers)
        assert resp.status_code == 200, resp.text
        assert resp.json()["code"] == 0, resp.text


# ---------------------------------------------------------------------------
# 2. 未采集态:表空 → {collected:false}(引导态数据源)
# ---------------------------------------------------------------------------
class TestNotCollected:
    @pytest.mark.asyncio
    async def test_empty_table_returns_collected_false(self, client, superadmin_headers, read_env):
        """从未采集(表空)→ 200;data.collected is False"""
        resp = await client.get(READ_URL, headers=superadmin_headers)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["code"] == 0, body
        assert body["data"].get("collected") is False, body


# ---------------------------------------------------------------------------
# 3. 已采集态:响应与 claude_system_assets 表内容一致(2 skill + 1 mcp)
# ---------------------------------------------------------------------------
class TestCollected:
    @pytest.mark.asyncio
    async def test_contract_keys_and_shape(self, client, superadmin_headers, read_env):
        """已采集 → data 含 skills/mcps/collected_at/image_tag;名称/镜像与表一致"""
        await _seed_snapshot(read_env["db"])

        resp = await client.get(READ_URL, headers=superadmin_headers)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["code"] == 0, body
        data = body["data"]

        assert {"skills", "mcps", "collected_at", "image_tag"} <= set(data.keys()), data
        assert _names(data["skills"]) == ["skill-a", "skill-b"], data["skills"]
        assert _names(data["mcps"]) == ["fetch"], data["mcps"]
        assert data["image_tag"] == SEED_IMAGE_TAG, data
        assert isinstance(data["collected_at"], str) and data["collected_at"], data
        # N1 回归:ISO「T」形态(Safari new Date() 对空格分隔格式解析 Invalid Date)
        assert "T" in data["collected_at"], data["collected_at"]

    @pytest.mark.asyncio
    async def test_response_matches_table_rows(self, client, second_user_headers, read_env, db_session):
        """完成判据1(数据源):GET 结果与表行一致(普通用户视角再验一次)"""
        await _seed_snapshot(db_session)
        rows = await _table_rows(db_session)
        assert len(rows) == 3

        resp = await client.get(READ_URL, headers=second_user_headers)
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]

        db_skills = sorted(r["name"] for r in rows if r["kind"] == "skill")
        db_mcps = sorted(r["name"] for r in rows if r["kind"] == "mcp")
        assert _names(data["skills"]) == db_skills
        assert _names(data["mcps"]) == db_mcps
        assert data["image_tag"] == rows[0]["image_tag"]
        # collected_at 为表内采集时间(序列化形态不锁,含日期即视为同源)
        assert str(rows[0]["collected_at"])[:10] in str(data["collected_at"]), (
            rows[0]["collected_at"], data["collected_at"],
        )


# ---------------------------------------------------------------------------
# 4. 完成判据3(异常口径):普通成员仅见展示,不可触发采集
# ---------------------------------------------------------------------------
class TestMemberReadOnly:
    @pytest.mark.asyncio
    async def test_member_can_read_but_not_collect(self, client, auth_headers, second_user_headers, read_env):
        """同一普通用户:GET 200 可读;POST collect 403(写口仍超管专属)
        (auth_headers 先注册占住 bootstrap 位,second_user_headers 才是普通用户)"""
        r_read = await client.get(READ_URL, headers=second_user_headers)
        assert r_read.status_code == 200, r_read.text

        r_collect = await client.post(COLLECT_URL, headers=second_user_headers)
        assert r_collect.status_code == 403, r_collect.text
        assert r_collect.json()["code"] == 19002, r_collect.text


# ---------------------------------------------------------------------------
# 5. R4 回归:plugin 条目(kind=skill + detail.source="plugin")读侧零改动透出
# ---------------------------------------------------------------------------
class TestR4PluginRowsRead:
    @pytest.mark.asyncio
    async def test_plugin_sourced_skill_served_with_detail_passthrough(self, client, superadmin_headers, read_env):
        """R4 回归(读侧零改动):plugin 条目以 kind=skill 落库后,GET /api/system-assets
        的 skills 列表照常透出,detail.source="plugin" 原样透传
        (系统级列表 / AI /skills 候选的内置徽标数据源;现状即满足 → 回归护栏)"""
        db = read_env["db"]
        rows = [
            ("flow-status", "skill", {"name": "flow-status", "source": "plugin", "original_kind": "command"}),
            ("skill-a", "skill", {"name": "skill-a"}),
            ("fetch", "mcp", {"transport": "stdio", "command": "uvx mcp-server-fetch"}),
        ]
        for name, kind, detail in rows:
            await db.execute(text(
                f"INSERT INTO {TABLE} (name, kind, detail, collected_at, image_tag) "
                "VALUES (:n, :k, :d, :ts, :img)"
            ), {"n": name, "k": kind, "d": json.dumps(detail), "ts": SEED_COLLECTED_AT, "img": SEED_IMAGE_TAG})
        await db.commit()

        resp = await client.get(READ_URL, headers=superadmin_headers)
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]

        assert _names(data["skills"]) == ["flow-status", "skill-a"], data["skills"]
        item = next(it for it in data["skills"] if it["name"] == "flow-status")
        detail = item["detail"]
        if isinstance(detail, str):
            detail = json.loads(detail)
        assert detail.get("source") == "plugin", f"plugin 条目 detail 应原样透传: {item}"
        assert _names(data["mcps"]) == ["fetch"], data["mcps"]
