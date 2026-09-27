"""
R5(系统级采集 probe_claude)— 平台侧采集接口 — QA TDD Red phase
================================================================
依据 docs/20260926_skills市场安装/DEVPLAN/R5.md(接口契约/服务端行为规格/完成判据)
与 docs/20260927_系统级skills与mcp列表/PRD.md R1。

被测对象(Green 待实现):
1. POST /api/admin/system-assets/collect(require_superadmin)
   - system_asset_service.collect:
     · asyncio.Lock 防并发;并发第二次等待后直接返回首次结果(不重复起容器)
     · request_runner 下发 probe_claude 并等待(契约超时 120s;本 seam 不可见该参数,
       以「死链 → send 异常 → request_runner 归一化 TimeoutError → 502」间接覆盖)
     · 覆盖入库 claude_system_assets(name/kind(skill,mcp)/detail JSON/
       collected_at/image_tag)
     · 响应 {skills:n, mcps:n, collected_at, image_tag}
2. 服务端行为规格(R5.md 负向探查):
   - 容器启动失败/exec 失败 → 502 可重试,旧数据保留(不因失败清库)
   - 并发采集 → 锁内串行,第二次等待后直接返回首次结果(只发一次 probe)
   - 采集结果为空 → 清空旧表入库 + 警告「镜像未内置」
   - Runner 离线 → 502「无可用 Runner」
   - 非超管 403(19002)/ 未登录 401

测试注入点(与 rd-dev 对齐的 seam,沿用 test_files_api 的注册表先例):
- 不 monkeypatch request_runner,而是向 runner_registry 注册 FakeWS 连接:
  真实 request_runner 下发 probe_claude 后,FakeWS 按 resolve_request 协议自动
  回报 result(claude_service/task_service/local_runner_service 均以
  runner_service.request_runner 模块属性方式调用,「注册表 + FakeWS」对两层
  实现细节都稳定)。
- 成功路径同时准备 DB Runner 行(status=online)与内存连接:调度取哪层都满足。
- 表 claude_system_assets 迁移未建时,按 R5.md 字段规格兜底建表并在测试结束即删
  (不阻塞 Green 的 Base.metadata.create_all;Green 落地真实模型后兜底自动失效)。

真机全链路(临时容器起→探→毁 + 镜像实际资产)依赖在线 Runner 与 devbox 镜像,
不在本轮(Runner 依赖,已注明);Runner 侧指令逻辑见 runner/tests/test_probe_claude.py。
"""
import asyncio
import json
import uuid
from datetime import datetime

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.models.runner import Runner
from app.services.runner_service import resolve_request, runner_registry

COLLECT_URL = "/api/admin/system-assets/collect"
TABLE = "claude_system_assets"

RUNNER_ID = "runner-probe-r5"

# 假 Runner 探测结果(R5.md 契约:{skills:[name...], mcps:[{name,transport...}]})
PROBE_DATA = {
    "skills": ["skill-a", "skill-b"],
    "mcps": [
        {"name": "fetch", "transport": "stdio", "command": "uvx mcp-server-fetch"},
    ],
    # 镜像标识:实现可取自 probe 结果,也可取自平台下发镜像名;二者均非空即满足契约
    "image_tag": "platform/devbox:v2",
}
EMPTY_PROBE_DATA = {"skills": [], "mcps": [], "image_tag": "platform/devbox:v2"}


# ---------------------------------------------------------------------------
# 假 Runner 传输层:真实 request_runner 下发 → 按 resolve_request 协议自动回报
# ---------------------------------------------------------------------------
class ProbeRunnerWS:
    """FakeWS:记录下发消息并自动回报 probe 结果。

    ok=True   → resolve_request(req_id, True, data=probe_data)(采集成功)
    ok=False  → resolve_request(req_id, False, error=error)(容器/exec 失败)
    dead=True → send_json 直接抛错(request_runner 归一化 TimeoutError → 探测不可达)
    """

    def __init__(self, *, ok=True, probe_data=None, error="", dead=False, delay=0.0):
        self.sent: list[dict] = []
        self.ok = ok
        self.probe_data = probe_data if probe_data is not None else PROBE_DATA
        self.error = error
        self.dead = dead
        self.delay = delay

    async def send_json(self, payload):
        self.sent.append(payload)
        if self.dead:
            raise RuntimeError("simulated dead runner link")
        req_id = payload.get("req_id")
        if not req_id:
            return
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.ok:
            resolve_request(req_id, True, data=self.probe_data)
        else:
            resolve_request(req_id, False, error=self.error or "probe exec failed")

    @property
    def probe_msgs(self) -> list[dict]:
        """平台下发的 probe_claude 指令(type 直发或 exec_tool+tool 两种接线均认)"""
        return [
            m for m in self.sent
            if m.get("type") == "probe_claude" or m.get("tool") == "probe_claude"
        ]


# ---------------------------------------------------------------------------
# 表兜底 / 数据助手
# ---------------------------------------------------------------------------
async def _table_exists(db) -> bool:
    res = await db.execute(text(
        "SELECT COUNT(*) FROM information_schema.tables "
        f"WHERE table_schema = DATABASE() AND table_name = '{TABLE}'"
    ))
    return (res.scalar() or 0) > 0


async def _ensure_table(db) -> bool:
    """迁移缺失时按 R5.md 字段规格兜底建表;返回是否由本测试创建(Green 后自动失效)"""
    if await _table_exists(db):
        return False
    await db.execute(text(f"""
        CREATE TABLE {TABLE} (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(128) NOT NULL,
            kind ENUM('skill', 'mcp') NOT NULL,
            detail JSON NULL,
            collected_at DATETIME NOT NULL,
            image_tag VARCHAR(128) NULL
        ) DEFAULT CHARSET=utf8mb4
    """))
    await db.commit()
    return True


async def _clear_assets(db):
    if await _table_exists(db):
        await db.execute(text(f"DELETE FROM {TABLE}"))
        await db.commit()


async def _seed_old_assets(db):
    """模拟上一轮采集的旧数据(含本轮 probe 结果里不存在的 stale 项)"""
    for name, kind in (("stale-skill", "skill"), ("skill-a", "skill"), ("stale-mcp", "mcp")):
        await db.execute(text(
            f"INSERT INTO {TABLE} (name, kind, detail, collected_at, image_tag) "
            "VALUES (:n, :k, :d, NOW(), 'old-image:v0')"
        ), {"n": name, "k": kind, "d": json.dumps({"from": "previous-collect"})})
    await db.commit()


async def _asset_rows(db) -> list[dict]:
    res = await db.execute(text(
        f"SELECT name, kind, detail, image_tag, collected_at FROM {TABLE} ORDER BY id"
    ))
    return [dict(r._mapping) for r in res]


def _as_detail(v) -> dict:
    if isinstance(v, str):
        return json.loads(v)
    return v or {}


def _json_contains(obj, needle: str) -> bool:
    """警告文案可能落在 message/data 任意层,递归匹配(不锁响应结构)"""
    if isinstance(obj, str):
        return needle in obj
    if isinstance(obj, dict):
        return any(_json_contains(v, needle) for v in obj.values())
    if isinstance(obj, list):
        return any(_json_contains(v, needle) for v in obj)
    return False


def _assert_single_probe(ws: ProbeRunnerWS):
    """平台只下发一次 probe_claude 指令(start→exec→stop 在 Runner 侧单次调用内完成);
    R1:指令默认镜像应为 v2(路由不传 image,collect 用 DEFAULT_PROBE_IMAGE——
    钉住生产常量 system_asset_service.py 的 v2 默认)"""
    assert len(ws.probe_msgs) >= 1, f"未下发 probe_claude 指令,下发消息: {ws.sent}"
    assert len(ws.probe_msgs) == 1, (
        f"probe_claude 应单次调用完成,实际下发 {len(ws.probe_msgs)} 条: {ws.probe_msgs}"
    )
    assert ws.probe_msgs[0].get("image") == "platform/devbox:v2", (
        f"probe 指令默认镜像应为 v2,实际: {ws.probe_msgs[0].get('image')}"
    )


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture
async def asset_env(client, db_session):
    """采集环境:service 模块契约校验 + 表兜底 + 在线 Runner(DB 行 + 内存连接)。

    Red 阶段:app.services.system_asset_service 未创建 → 显式 fail(R5 契约)。
    """
    try:
        from app.services import system_asset_service as svc  # noqa: F401
    except ImportError as e:
        pytest.fail(f"app.services.system_asset_service 模块未创建(R5 契约): {e}")
    # 单飞/缓存模块状态在测试间兜底清零(并发/冷却语义不得跨用例泄漏)
    val = getattr(svc, "_last_result", None)
    if isinstance(val, dict):
        val.clear()

    created = await _ensure_table(db_session)
    await _clear_assets(db_session)

    ws = ProbeRunnerWS()
    runner_registry.register(RUNNER_ID, "worker", ws, "10.0.0.9")
    # DB 侧也备一个 online Runner(调度层若走 pick_runner_db 亦可用)
    db_session.add(Runner(
        runner_id=RUNNER_ID,
        name=f"probe-{uuid.uuid4().hex[:6]}",
        role="worker",
        token_hash="test-hash-not-a-real-token",
        status="online",
        current_containers=0,
        max_containers=5,
        created_by=str(uuid.uuid4()),
    ))
    await db_session.commit()

    yield {"ws": ws, "service": svc}

    runner_registry.unregister(RUNNER_ID)
    await _clear_assets(db_session)
    if created:
        # 本测试兜底建的表用后即删,避免阻塞 Green 真实模型/迁移的 create_all
        await db_session.execute(text(f"DROP TABLE IF EXISTS {TABLE}"))
        await db_session.commit()


# ---------------------------------------------------------------------------
# 1. 权限:未登录 401 / 非超管 403(鉴权先行,不触发采集)
# ---------------------------------------------------------------------------
class TestAuth:
    @pytest.mark.asyncio
    async def test_collect_requires_login(self, client):
        """未登录(无 JWT)→ 401;鉴权先行(不注册任何 Runner,采集不可达)"""
        runner_registry.unregister(RUNNER_ID)  # 防御:确保无可用 Runner
        resp = await client.post(COLLECT_URL)
        assert resp.status_code == 401, resp.text

    @pytest.mark.asyncio
    async def test_collect_forbidden_for_non_superadmin(self, client, auth_headers, second_user_headers):
        """普通登录用户 → 403 code=19002(require_superadmin 平台 Guard)
        (auth_headers 先注册占住「首个用户=superadmin」bootstrap 位,second_user_headers
        才是普通用户——test_platform_settings_api 同款 setup,断言语义不变)"""
        runner_registry.unregister(RUNNER_ID)  # 防御:确保无可用 Runner
        resp = await client.post(COLLECT_URL, headers=second_user_headers)
        assert resp.status_code == 403, resp.text
        assert resp.json()["code"] == 19002


# ---------------------------------------------------------------------------
# 2. 超管成功:probe 结果覆盖入库,响应 {skills:n, mcps:n, collected_at, image_tag}
# ---------------------------------------------------------------------------
class TestCollectSuccess:
    @pytest.mark.asyncio
    async def test_success_response_contract(self, client, superadmin_headers, asset_env):
        """完成判据1(mock 版):200 + code=0;data 含 skills=2/mcps=1/collected_at/image_tag"""
        resp = await client.post(COLLECT_URL, headers=superadmin_headers)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["code"] == 0, body
        data = body["data"]
        assert {"skills", "mcps", "collected_at", "image_tag"} <= set(data.keys()), data
        assert data["skills"] == 2
        assert data["mcps"] == 1
        assert isinstance(data["collected_at"], str) and data["collected_at"]
        assert isinstance(data["image_tag"], str) and data["image_tag"]
        _assert_single_probe(asset_env["ws"])

    @pytest.mark.asyncio
    async def test_success_persists_rows(self, client, superadmin_headers, asset_env, db_session):
        """probe 结果入库:2 skill + 1 mcp;kind/detail/image_tag/collected_at 落库"""
        resp = await client.post(COLLECT_URL, headers=superadmin_headers)
        assert resp.status_code == 200, resp.text
        rows = await _asset_rows(db_session)
        assert len(rows) == 3, rows
        skills = sorted(r["name"] for r in rows if r["kind"] == "skill")
        mcps = [r for r in rows if r["kind"] == "mcp"]
        assert skills == ["skill-a", "skill-b"]
        assert len(mcps) == 1
        # detail 存探测原文(传输类型/命令等):不锁内部结构,校验探测值在原文中
        assert "stdio" in json.dumps(_as_detail(mcps[0]["detail"]), ensure_ascii=False), mcps[0]
        assert mcps[0]["image_tag"]  # 镜像标识落库
        collected = mcps[0]["collected_at"]
        assert collected is not None
        if isinstance(collected, datetime):
            # 采集时间为本次(与现在差 < 10 分钟,而非旧数据残留)
            assert abs((datetime.now() - collected).total_seconds()) < 600


# ---------------------------------------------------------------------------
# 3. 重复采集:覆盖旧数据,不重复建行
# ---------------------------------------------------------------------------
class TestCollectOverwrite:
    @pytest.mark.asyncio
    async def test_recollect_overwrites_without_duplicates(self, client, superadmin_headers, asset_env, db_session):
        """完成判据2:旧数据(stale-skill/stale-mcp/skill-a)被本轮结果整体覆盖:
        stale 项消失、无重复行、image_tag 更新为新标识"""
        await _seed_old_assets(db_session)

        resp = await client.post(COLLECT_URL, headers=superadmin_headers)
        assert resp.status_code == 200, resp.text
        assert resp.json()["code"] == 0, resp.text

        rows = await _asset_rows(db_session)
        names = sorted(r["name"] for r in rows)
        # 恰为本轮 probe 结果(2 skill + 1 mcp),旧 stale 项被清、同名不重复
        assert names == ["fetch", "skill-a", "skill-b"], rows
        assert "old-image:v0" not in {r["image_tag"] for r in rows}


# ---------------------------------------------------------------------------
# 4. 并发采集:锁内串行,第二次等待后直接返回首次结果(不重复起容器)
# ---------------------------------------------------------------------------
class TestCollectConcurrencyLock:
    @pytest.mark.asyncio
    async def test_concurrent_collects_single_probe(self, client, superadmin_headers, asset_env):
        """完成判据3:并发二次点击 → 仅下发 1 条 probe(第二次不重复起容器),
        两次请求均 200 且第二次等待后返回首次结果(collected_at 一致)"""
        # 慢探测:让首个请求在 probe 处停留,第二个请求在其间到达
        asset_env["ws"].delay = 0.4

        # 并发请求各自持独立 DB session(共享 session 不耐并发)
        from app.database import async_session_factory, get_db

        async def _fresh_session():
            async with async_session_factory() as s:
                yield s

        app = client._transport.app
        app.dependency_overrides[get_db] = _fresh_session

        async def _call():
            return await client.post(COLLECT_URL, headers=superadmin_headers)

        r1, r2 = await asyncio.wait_for(asyncio.gather(_call(), _call()), timeout=20)
        assert r1.status_code == 200, r1.text
        assert r2.status_code == 200, r2.text
        assert r1.json()["code"] == 0 and r2.json()["code"] == 0

        # 只起一次容器(只下发一次 probe)
        assert len(asset_env["ws"].probe_msgs) == 1, (
            f"并发采集应串行复用首次结果,实际下发 {len(asset_env['ws'].probe_msgs)} 条 probe"
        )
        # 第二次直接返回首次结果:collected_at 一致
        assert r1.json()["data"]["collected_at"] == r2.json()["data"]["collected_at"]


# ---------------------------------------------------------------------------
# 5. 失败:容器/exec 失败 → 502 可重试,旧数据保留
# ---------------------------------------------------------------------------
class TestCollectFailure:
    @pytest.mark.asyncio
    async def test_exec_failure_502_keeps_old_data(self, client, superadmin_headers, asset_env, db_session):
        """Runner 回报 ok=False(exec 失败)→ 502 可重试;旧采集数据不清库"""
        await _seed_old_assets(db_session)
        asset_env["ws"].ok = False
        asset_env["ws"].error = "probe exec failed: exit 1"

        resp = await client.post(COLLECT_URL, headers=superadmin_headers)
        assert resp.status_code == 502, resp.text
        assert resp.json()["code"] != 0

        rows = await _asset_rows(db_session)
        assert sorted(r["name"] for r in rows) == ["skill-a", "stale-mcp", "stale-skill"]
        assert all(r["image_tag"] == "old-image:v0" for r in rows)

    @pytest.mark.asyncio
    async def test_probe_unreachable_502_keeps_old_data(self, client, superadmin_headers, asset_env, db_session):
        """探测不可达(死链 → TimeoutError)→ 502;旧数据保留(失败不清库)"""
        await _seed_old_assets(db_session)
        asset_env["ws"].dead = True

        resp = await client.post(COLLECT_URL, headers=superadmin_headers)
        assert resp.status_code == 502, resp.text
        assert resp.json()["code"] != 0

        rows = await _asset_rows(db_session)
        assert len(rows) == 3  # 旧数据未被清

    @pytest.mark.asyncio
    async def test_timeout_cooldown_blocks_immediate_retry(self, client, superadmin_headers, asset_env):
        """超时后冷却窗口内重试 → 立即 502「上次采集仍在进行」,且不再下发 probe
        (Runner 侧 probe 线程可能仍在跑,不堆叠临时容器;窗口=COLLECT_TIMEOUT)"""
        asset_env["ws"].dead = True
        r1 = await client.post(COLLECT_URL, headers=superadmin_headers)
        assert r1.status_code == 502, r1.text
        sent_after_first = len(asset_env["ws"].sent)

        r2 = await client.post(COLLECT_URL, headers=superadmin_headers)
        assert r2.status_code == 502, r2.text
        assert "上次采集仍在进行" in r2.json()["message"], r2.json()
        # 冷却窗口内不再下发任何 probe(不堆叠)
        assert len(asset_env["ws"].sent) == sent_after_first, asset_env["ws"].sent

    @pytest.mark.asyncio
    async def test_side_failure_keeps_failed_side_old_data(self, client, superadmin_headers, asset_env, db_session):
        """部分结果语义(PRD R1):单侧探测失败 → 失败侧旧库保留,成功侧覆盖,响应带警告"""
        await _seed_old_assets(db_session)
        asset_env["ws"].probe_data = {
            "skills": [],
            "mcps": [{"name": "fetch", "transport": "stdio"}],
            "failed_sides": ["skills"],
            "warnings": ["skills 探测失败(exit 1),该侧保留原有数据"],
        }

        resp = await client.post(COLLECT_URL, headers=superadmin_headers)
        assert resp.status_code == 200, resp.text
        assert resp.json()["code"] == 0, resp.text

        rows = await _asset_rows(db_session)
        skills = sorted(r["name"] for r in rows if r["kind"] == "skill")
        mcps = [r["name"] for r in rows if r["kind"] == "mcp"]
        assert skills == ["skill-a", "stale-skill"], rows   # 失败侧旧库保留(未清)
        assert mcps == ["fetch"], rows                       # 成功侧已覆盖(stale-mcp 被清)
        assert _json_contains(resp.json(), "skills 探测失败"), resp.json()  # 响应带警告


# ---------------------------------------------------------------------------
# 6. Runner 离线 → 502「无可用 Runner」
# ---------------------------------------------------------------------------
class TestRunnerOffline:
    @pytest.mark.asyncio
    async def test_no_runner_502(self, client, superadmin_headers):
        """内存注册表与 DB 均无在线 Runner → 502,提示无可用 Runner"""
        runner_registry.unregister(RUNNER_ID)  # 防御:确保无可用 Runner
        resp = await client.post(COLLECT_URL, headers=superadmin_headers)
        assert resp.status_code == 502, resp.text
        body = resp.json()
        assert body["code"] != 0
        assert "无可用 Runner" in body["message"]


# ---------------------------------------------------------------------------
# 7. 采集结果为空 → 清空旧表入库 + 警告「镜像未内置」
# ---------------------------------------------------------------------------
class TestEmptyCollect:
    @pytest.mark.asyncio
    async def test_empty_result_clears_table_with_warning(self, client, superadmin_headers, asset_env, db_session):
        """空结果仍为成功采集(200):清空旧表后入库 0 行;响应含「镜像未内置」警告"""
        await _seed_old_assets(db_session)
        asset_env["ws"].probe_data = EMPTY_PROBE_DATA

        resp = await client.post(COLLECT_URL, headers=superadmin_headers)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["code"] == 0, body
        assert body["data"]["skills"] == 0
        assert body["data"]["mcps"] == 0

        rows = await _asset_rows(db_session)
        assert rows == []  # 旧表已清空(空结果覆盖)

        # 警告「镜像未内置」(R5.md 状态域;落 message/data 任意位置均可)
        assert _json_contains(body, "镜像未内置"), body


# ---------------------------------------------------------------------------
# 8. R4:plugin 条目落库(kind=skill + detail.source="plugin")与覆盖语义
#    (docs/20260927_devbox默认skills与mcp/DEVPLAN/R4.md,QA TDD Red phase;
#    2026-09-27 契约微调:probe 响应 plugin_skills/plugin_commands 独立字段承载
#    plugin 条目(skills 保持平台存量语义),plugin commands 以 kind="skill" 落库)
# ---------------------------------------------------------------------------
PLUGIN_PROBE_DATA = {
    "skills": ["skill-a"],
    "plugin_skills": [],                       # R4 新增:plugin 提供的 skills 名
    "plugin_commands": ["flow-status", "flow-run"],  # R4 新增:plugin 提供的 commands 名
    "mcps": [
        {"name": "fetch", "transport": "stdio", "command": "uvx mcp-server-fetch"},
    ],
    "failed_sides": [],
    "warnings": [],
    "image_tag": "platform/devbox:v2",
}


class TestR4PluginEntries:
    @pytest.mark.asyncio
    async def test_plugin_commands_persist_as_skill_rows_with_source(
        self, client, superadmin_headers, asset_env, db_session
    ):
        """R4 落库形态(2026-09-27 用户确认):probe.plugin_commands 条目以 kind="skill" 落库,
        detail 内 source="plugin"(+原始类型 command 标记);平台 skills 落库语义不变
        (detail 不被误标 plugin);mcps 落库语义不变(detail=探测原文,不加 source);
        响应 skills 计数含 commands(3 = 2 plugin commands + 1 平台 skill)"""
        asset_env["ws"].probe_data = PLUGIN_PROBE_DATA

        resp = await client.post(COLLECT_URL, headers=superadmin_headers)
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["skills"] == 3, (
            f"响应 skills 计数应含 plugin commands(2+1),实际: {data}"
        )

        rows = await _asset_rows(db_session)
        skills = sorted(r["name"] for r in rows if r["kind"] == "skill")
        assert skills == ["flow-run", "flow-status", "skill-a"], (
            f"plugin commands 应以 kind=skill 落库,实际 skill 行: {skills}"
        )
        by_name = {r["name"]: r for r in rows}
        for cmd in ("flow-status", "flow-run"):
            detail = _as_detail(by_name[cmd]["detail"])
            assert detail.get("source") == "plugin", (
                f"{cmd} detail 应带 source=plugin,实际: {detail}"
            )
            assert "command" in json.dumps(detail, ensure_ascii=False), (
                f"{cmd} detail 应保留原始类型 command 标记,实际: {detail}"
            )
        # 平台 skill / mcp 不被误标 plugin(落库语义不变)
        assert _as_detail(by_name["skill-a"]["detail"]).get("source") != "plugin", (
            f"平台 skill 不得被标 plugin: {by_name['skill-a']}"
        )
        assert "source" not in _as_detail(by_name["fetch"]["detail"]), (
            f"mcp detail 应为探测原文(不加 source),实际: {by_name['fetch']}"
        )

    @pytest.mark.asyncio
    async def test_recollect_with_plugin_entries_overwrites(
        self, client, superadmin_headers, asset_env, db_session
    ):
        """R4 判据5(先清后插扩展到 plugin 条目):上一轮 plugin 旧行(含同名
        flow-status 旧 plugin 行)与平台旧行整体被本轮覆盖;同名 plugin command
        只留本轮一行;image_tag 更新"""
        for name, kind in (("stale-skill", "skill"), ("flow-status", "skill"), ("stale-mcp", "mcp")):
            await db_session.execute(text(
                f"INSERT INTO {TABLE} (name, kind, detail, collected_at, image_tag) "
                "VALUES (:n, :k, :d, NOW(), 'old-image:v0')"
            ), {"n": name, "k": kind, "d": json.dumps({"from": "previous-collect"})})
        await db_session.commit()
        asset_env["ws"].probe_data = PLUGIN_PROBE_DATA

        resp = await client.post(COLLECT_URL, headers=superadmin_headers)
        assert resp.status_code == 200, resp.text
        assert resp.json()["code"] == 0, resp.text

        rows = await _asset_rows(db_session)
        names = sorted(r["name"] for r in rows)
        # 恰为本轮结果(2 plugin commands + 1 平台 skill + 1 mcp),stale 双双被清
        assert names == ["fetch", "flow-run", "flow-status", "skill-a"], rows
        assert sum(1 for r in rows if r["name"] == "flow-status") == 1, (
            f"同名 plugin command 应只留本轮一行(先清后插),实际: {rows}"
        )
        assert "old-image:v0" not in {r["image_tag"] for r in rows}

    @pytest.mark.asyncio
    async def test_same_name_platform_and_plugin_skill_two_rows(
        self, client, superadmin_headers, asset_env, db_session
    ):
        """R4 判据6:平台与 plugin 同名条目 → 落库两行并存(先清后插不去重)。
        2026-09-27 契约微调同步改钉:同名并列由 skills(平台)+ plugin_skills 两字段
        各一条承载(原「同一列表重复两次」形态随扁平 ∪ 契约一并作废),且两行来源可辨
        (平台行无 plugin 标记,plugin 行 detail.source="plugin")"""
        asset_env["ws"].probe_data = {
            "skills": ["dup-skill"],
            "plugin_skills": ["dup-skill"],
            "plugin_commands": [],
            "mcps": [{"name": "fetch", "transport": "stdio"}],
            "image_tag": "platform/devbox:v2",
        }

        resp = await client.post(COLLECT_URL, headers=superadmin_headers)
        assert resp.status_code == 200, resp.text
        assert resp.json()["code"] == 0, resp.text
        assert resp.json()["data"]["skills"] == 2, resp.json()["data"]

        rows = await _asset_rows(db_session)
        dup = [r for r in rows if r["name"] == "dup-skill" and r["kind"] == "skill"]
        assert len(dup) == 2, f"同名条目应两行并存(如实并列不去重),实际: {rows}"
        sources = sorted(_as_detail(r["detail"]).get("source", "platform") for r in dup)
        assert sources == ["platform", "plugin"], (
            f"同名两行应来源可辨(平台无标记 + plugin 标记),实际: {dup}"
        )

    @pytest.mark.asyncio
    async def test_plugin_skills_persist_with_source_and_original_kind(
        self, client, superadmin_headers, asset_env, db_session
    ):
        """R4 契约微调(2026-09-27)补测:probe.plugin_skills 条目同样以 kind="skill" 落库,
        detail.source="plugin" + original_kind="skill"(与 commands 的 original_kind="command"
        区分原始类型);响应 skills 计数含 plugin skills(2 = 1 平台 + 1 plugin)"""
        asset_env["ws"].probe_data = {
            "skills": ["skill-a"],
            "plugin_skills": ["rd-arch"],
            "plugin_commands": [],
            "mcps": [{"name": "fetch", "transport": "stdio"}],
            "image_tag": "platform/devbox:v2",
        }

        resp = await client.post(COLLECT_URL, headers=superadmin_headers)
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["skills"] == 2, resp.json()["data"]

        rows = await _asset_rows(db_session)
        skills = sorted(r["name"] for r in rows if r["kind"] == "skill")
        assert skills == ["rd-arch", "skill-a"], (
            f"plugin skills 应以 kind=skill 落库,实际 skill 行: {skills}"
        )
        by_name = {r["name"]: r for r in rows}
        detail = _as_detail(by_name["rd-arch"]["detail"])
        assert detail.get("source") == "plugin", (
            f"rd-arch detail 应带 source=plugin,实际: {detail}"
        )
        assert detail.get("original_kind") == "skill", (
            f"rd-arch detail 应保留原始类型 skill 标记,实际: {detail}"
        )
        assert _as_detail(by_name["skill-a"]["detail"]).get("source") != "plugin", (
            f"平台 skill 不得被标 plugin: {by_name['skill-a']}"
        )


class TestR4Constants:
    def test_default_probe_image_binding_v2(self):
        """R4 要点4(tag 三层同步):DEFAULT_PROBE_IMAGE 绑定断言。R1 的 D5 批次已把
        本常量升 v2(代码精查确认)→ 本用例为现状绿护栏(绑定当前值防回退);
        Red 校验由其余 plugin/落库用例承担"""
        try:
            from app.services import system_asset_service as svc
        except ImportError as e:
            pytest.fail(f"app.services.system_asset_service 模块未创建: {e}")
        assert svc.DEFAULT_PROBE_IMAGE == "platform/devbox:v2", (
            f"DEFAULT_PROBE_IMAGE 应绑定 v2,实际: {svc.DEFAULT_PROBE_IMAGE}"
        )
