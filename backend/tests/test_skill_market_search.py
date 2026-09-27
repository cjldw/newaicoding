"""
R2(skills 市场安装)— 市场搜索接口(后端代理)— QA TDD Red phase
====================================================================
依据 docs/20260926_skills市场安装/DEVPLAN/R2.md(接口契约 + 服务端行为规格 + 完成判据)
与 PRD-A R2(字段定义/异常边界)。

被测对象(Green 待实现):
1. app/services/skill_market_service.py —— httpx 双适配器
   - modelscope:PUT {base}/api/v1/dolphin/skills body {Query,PageSize,PageNumber:1}
     (⚠️ 过滤字段是 Query,不是 q/keyword)→ Data.SkillList 映射
     (name=Name, ref={Path}/{Name}, installs=DownloadCount, description 缺省 "")
   - skillssh:GET {base}/api/search?q=&limit= → skills[] 映射
     (name, ref={owner}/{repo}/{slug}, installs, description 缺省 "")
2. GET /api/skills/market/search(app/api/skills.py):
   - JWT(q 不校验登录先行:未登录 401)
   - q 必填(缺参/空串/纯空白 trim 后空 → 400);q 前后空格 trim 后透传
   - limit 默认 20、上限 50(>50 或 <1 → 400)
   - market 须在源列表(缺参/不在 → 400)
   - 市场超时/5xx → 502「市场暂不可用」
   - 内存缓存键 (market,q,limit) TTL 300s;命中不外呼;外呼失败不写缓存
   - 响应 data:{market, items:[{name,description,installs,ref,market}]}

测试注入点契约(沿用 gitlab_service._test_transport 先例,QA 与 rd-dev 对齐):
- skill_market_service.set_test_transport(transport: httpx.MockTransport | None)
- 缓存清理:优先 clear_cache();否则模块级 _cache dict(fixture 兜底 clear)

契约口径(QA 定稿,rd-dev 已对齐):
- market 入参/回显均为源的 type 值(modelscope|skillssh,按 R2 完成判据字面口径);
  item.market 同值——保证 R3 安装 {market, ref} 可用搜索结果原样回传(往返一致)
- skillssh 归一化 ref 取上游 skillId 字段(其值即 owner/repo/slug,R2.md 字面口径)
"""
import json

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import delete

from app.models.project import PlatformSetting

SEARCH_URL = "/api/skills/market/search"

# R1 默认两源种子(PRD 定稿):market 入参按 完成判据 口径传 type 值
MS_HOST = "modelscope.cn"  # base=https://modelscope.cn
SS_HOST = "skills.sh"  # base=https://skills.sh
MARKET_MODELSCOPE = "modelscope"
MARKET_SKILLSSH = "skillssh"

# 假下游数据(模拟真实市场返回壳内的原始字段)
MS_FIND_SKILLS = {
    "Name": "find-skills",
    "Path": "@vercel-labs",
    "DownloadCount": 4321,
    "Description": "Find skills on ModelScope",
    "ExtraRaw": "should-not-leak-or-matter",
}
SS_FIND_SKILLS = {
    "name": "find-skills",
    "description": "Find skills on skills.sh",
    "installs": 12345,
    "skillId": "vercel/labs/find-skills",  # 上游 skillId,值形如 owner/repo/slug
}


def ms_response(*skills) -> dict:
    """ModelScope dolphin PUT 响应壳:Data.SkillList"""
    return {"Success": True, "Data": {"SkillList": list(skills)}}


def ss_response(*skills) -> dict:
    """skills.sh GET /api/search 响应壳:skills[]"""
    return {"skills": list(skills)}


def _raise_connect_timeout(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectTimeout("simulated connect timeout", request=request)


def _raise_read_timeout(request: httpx.Request) -> httpx.Response:
    raise httpx.ReadTimeout("simulated read timeout", request=request)


def ms_ok(*skills):
    """modelscope 打桩:返回 Data.SkillList 壳"""
    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=ms_response(*skills))
    return _handler


def ss_ok(*skills):
    """skills.sh 打桩:返回 skills[] 壳"""
    def _handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=ss_response(*skills))
    return _handler


class MarketStub:
    """假市场端点:按 url.host 分路(modelscope.cn / skills.sh),记录每次外呼。
    未打桩的 host 收到请求 → 直接 AssertionError(防止实现打错 base/路径时静默通过)。"""

    def __init__(self):
        self.calls: list[dict] = []
        self.rules: dict[str, object] = {}

    async def __call__(self, request: httpx.Request) -> httpx.Response:
        body = None
        if request.content:
            try:
                body = json.loads(request.content)
            except ValueError:
                body = request.content.decode("utf-8", "replace")
        self.calls.append(
            {
                "method": request.method,
                "url": str(request.url),
                "host": request.url.host,
                "path": request.url.path,
                "json": body,
                "params": dict(request.url.params),
            }
        )
        fn = self.rules.get(request.url.host)
        if fn is None:
            raise AssertionError(f"MockTransport 收到未打桩的外呼: {request.method} {request.url}")
        out = fn(request)
        if not isinstance(out, httpx.Response):
            out = await out
        return out


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture
async def clean_platform_settings(db_session):
    """确保「未配置」前提:清空 platform_settings → 走 R1 默认两源种子"""
    await db_session.execute(delete(PlatformSetting))
    await db_session.commit()
    yield db_session


@pytest_asyncio.fixture
async def market(client, clean_platform_settings):
    """安装市场外呼 mock,返回 MarketStub(测试按 host 打桩/断言外呼)。
    契约:skill_market_service 暴露 set_test_transport()(gitlab_service 先例);
    缓存清理优先 clear_cache(),否则兜底清模块级 _cache。"""
    try:
        from app.services import skill_market_service as svc
    except ImportError as e:
        pytest.fail(f"app.services.skill_market_service 模块未创建(R2 契约): {e}")
    if not hasattr(svc, "set_test_transport"):
        pytest.fail("skill_market_service 缺少测试注入点 set_test_transport()(gitlab_service 先例)")

    def _reset_cache():
        if hasattr(svc, "clear_cache"):
            svc.clear_cache()
        elif hasattr(svc, "_cache"):
            svc._cache.clear()
        else:
            pytest.fail("skill_market_service 需暴露 clear_cache() 或模块级 _cache(测试注入点)")

    _reset_cache()
    stub = MarketStub()
    svc.set_test_transport(httpx.MockTransport(stub))
    yield stub
    svc.set_test_transport(None)
    _reset_cache()


async def _search(client, auth_headers, *, market=MARKET_MODELSCOPE, q="find-skills", limit=None):
    """调 GET /api/skills/market/search;入参 None 表示不携带该 query 参数"""
    params = {}
    if market is not None:
        params["market"] = market
    if q is not None:
        params["q"] = q
    if limit is not None:
        params["limit"] = limit
    return await client.get(SEARCH_URL, params=params, headers=auth_headers)


# ---------------------------------------------------------------------------
# 1. JWT:未登录 401(且不外呼)
# ---------------------------------------------------------------------------
class TestAuth:
    @pytest.mark.asyncio
    async def test_search_requires_login(self, client, market):
        """未登录(无 JWT)→ 401;鉴权先行,不触发市场外呼"""
        resp = await client.get(
            SEARCH_URL, params={"market": MARKET_MODELSCOPE, "q": "find-skills"}
        )
        assert resp.status_code == 401
        assert market.calls == []


# ---------------------------------------------------------------------------
# 2. 参数校验:q 必填 / market 须在源列表 / limit 默认 20 上限 50
# ---------------------------------------------------------------------------
class TestParamValidation:
    @pytest.mark.asyncio
    async def test_q_missing_400(self, client, auth_headers, market):
        """缺 q 参数 → 400(契约「q 必填」;不允许 422),且不外呼"""
        resp = await _search(client, auth_headers, q=None)
        assert resp.status_code == 400, resp.text
        assert resp.json()["code"] != 0
        assert market.calls == []

    @pytest.mark.asyncio
    async def test_q_empty_400(self, client, auth_headers, market):
        """q=空串 → 400,且不外呼"""
        resp = await _search(client, auth_headers, q="")
        assert resp.status_code == 400, resp.text
        assert market.calls == []

    @pytest.mark.asyncio
    async def test_q_whitespace_only_400(self, client, auth_headers, market):
        """q=纯空白(trim 后为空)→ 400,且不外呼"""
        resp = await _search(client, auth_headers, q="   ")
        assert resp.status_code == 400, resp.text
        assert market.calls == []

    @pytest.mark.asyncio
    async def test_market_missing_400(self, client, auth_headers, market):
        """缺 market 参数 → 400(不在源列表),且不外呼"""
        resp = await _search(client, auth_headers, market=None)
        assert resp.status_code == 400, resp.text
        assert market.calls == []

    @pytest.mark.asyncio
    async def test_market_unknown_400(self, client, auth_headers, market):
        """market=github(不在源列表)→ 400,且不外呼"""
        resp = await _search(client, auth_headers, market="github")
        assert resp.status_code == 400, resp.text
        assert market.calls == []

    @pytest.mark.asyncio
    async def test_limit_over_50_400(self, client, auth_headers, market):
        """limit=51(超上限 50)→ 400,且不外呼"""
        resp = await _search(client, auth_headers, limit=51)
        assert resp.status_code == 400, resp.text
        assert market.calls == []

    @pytest.mark.asyncio
    async def test_limit_zero_400(self, client, auth_headers, market):
        """limit=0(<1)→ 400,且不外呼"""
        resp = await _search(client, auth_headers, limit=0)
        assert resp.status_code == 400, resp.text
        assert market.calls == []

    @pytest.mark.asyncio
    async def test_limit_non_integer_400(self, client, auth_headers, market):
        """limit=abc(非整数)→ 400/17004 而非 FastAPI 422,且不外呼"""
        resp = await _search(client, auth_headers, limit="abc")
        assert resp.status_code == 400, resp.text
        body = resp.json()
        assert body["code"] == 17004
        assert market.calls == []

    @pytest.mark.asyncio
    async def test_limit_float_400(self, client, auth_headers, market):
        """limit=1.5(浮点串)→ 400/17004 而非 FastAPI 422,且不外呼"""
        resp = await _search(client, auth_headers, limit="1.5")
        assert resp.status_code == 400, resp.text
        assert resp.json()["code"] == 17004
        assert market.calls == []

    @pytest.mark.asyncio
    async def test_limit_default_20_downstream(self, client, auth_headers, market):
        """不带 limit → 默认 20 透传下游(ModelScope PageSize=20)"""
        market.rules[MS_HOST] = ms_ok(MS_FIND_SKILLS)
        resp = await _search(client, auth_headers, limit=None)
        assert resp.status_code == 200, resp.text
        assert market.calls[0]["json"]["PageSize"] == 20

    @pytest.mark.asyncio
    async def test_limit_50_boundary_ok(self, client, auth_headers, market):
        """limit=50(边界)→ 200,50 透传下游"""
        market.rules[MS_HOST] = ms_ok(MS_FIND_SKILLS)
        resp = await _search(client, auth_headers, limit=50)
        assert resp.status_code == 200, resp.text
        assert market.calls[0]["json"]["PageSize"] == 50

    @pytest.mark.asyncio
    async def test_q_trimmed_downstream(self, client, auth_headers, market):
        """q 前后空格 trim 后透传(Query=find-skills,非 '  find-skills  ')"""
        market.rules[MS_HOST] = ms_ok(MS_FIND_SKILLS)
        resp = await _search(client, auth_headers, q="  find-skills  ")
        assert resp.status_code == 200, resp.text
        assert market.calls[0]["json"]["Query"] == "find-skills"


# ---------------------------------------------------------------------------
# 3. modelscope 适配器:PUT 契约 + Data.SkillList 归一化
# ---------------------------------------------------------------------------
class TestModelscopeAdapter:
    @pytest.mark.asyncio
    async def test_request_contract_put_body(self, client, auth_headers, market):
        """PUT {base}/api/v1/dolphin/skills;body {Query,PageSize,PageNumber:1}
        ⚠️ 过滤字段是 Query(不是 q/keyword);base 取自 R1 默认种子"""
        market.rules[MS_HOST] = ms_ok(MS_FIND_SKILLS)
        resp = await _search(client, auth_headers, market=MARKET_MODELSCOPE, q="find-skills", limit=20)
        assert resp.status_code == 200, resp.text
        assert len(market.calls) == 1
        call = market.calls[0]
        assert call["method"] == "PUT"
        assert call["host"] == MS_HOST
        assert call["path"] == "/api/v1/dolphin/skills"
        assert call["json"]["Query"] == "find-skills"
        assert call["json"]["PageSize"] == 20
        assert call["json"]["PageNumber"] == 1

    @pytest.mark.asyncio
    async def test_normalization_map(self, client, auth_headers, market):
        """完成判据1:market=modelscope q=find-skills → 含 @vercel-labs/find-skills。
        Data.SkillList → [{name,description,installs,ref,market}];
        name=Name / ref={Path}/{Name} / installs=DownloadCount / market=源 type 值
        (market 回显入参值,保证 R3 安装 {market,ref} 原样回传往返一致)"""
        market.rules[MS_HOST] = ms_ok(MS_FIND_SKILLS)
        resp = await _search(client, auth_headers, market=MARKET_MODELSCOPE, q="find-skills")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["code"] == 0, body
        data = body["data"]
        assert data["market"] == "modelscope"
        items = data["items"]
        assert len(items) == 1
        it = items[0]
        assert {"name", "description", "installs", "ref", "market"} <= set(it.keys())
        assert it["name"] == "find-skills"
        assert it["ref"] == "@vercel-labs/find-skills"  # {Path}/{Name}
        assert it["installs"] == 4321  # DownloadCount
        assert it["description"] == "Find skills on ModelScope"
        assert it["market"] == "modelscope"

    @pytest.mark.asyncio
    async def test_description_missing_becomes_empty(self, client, auth_headers, market):
        """上游未返回描述 → description=""(PRD:market 未返回则空)"""
        raw = {"Name": "no-desc", "Path": "org/repo", "DownloadCount": 1}
        market.rules[MS_HOST] = ms_ok(raw)
        resp = await _search(client, auth_headers, market=MARKET_MODELSCOPE, q="no-desc")
        assert resp.status_code == 200, resp.text
        it = resp.json()["data"]["items"][0]
        assert it["description"] == ""
        assert it["ref"] == "org/repo/no-desc"


# ---------------------------------------------------------------------------
# 4. skillssh 适配器:GET 契约 + skills[] 归一化
# ---------------------------------------------------------------------------
class TestSkillsshAdapter:
    @pytest.mark.asyncio
    async def test_request_contract_get_params(self, client, auth_headers, market):
        """GET {base}/api/search?q=&limit=;base 取自 R1 默认种子"""
        market.rules[SS_HOST] = ss_ok(SS_FIND_SKILLS)
        resp = await _search(client, auth_headers, market=MARKET_SKILLSSH, q="find-skills", limit=30)
        assert resp.status_code == 200, resp.text
        assert len(market.calls) == 1
        call = market.calls[0]
        assert call["method"] == "GET"
        assert call["host"] == SS_HOST
        assert call["path"] == "/api/search"
        assert call["params"]["q"] == "find-skills"
        assert call["params"]["limit"] == "30"

    @pytest.mark.asyncio
    async def test_normalization_map(self, client, auth_headers, market):
        """完成判据2:market=skillssh → items 含 installs 字段。
        skills[] → [{name,description,installs,ref,market}];
        ref=上游 skillId(值形如 owner/repo/slug,R2.md 字面口径);market=源 type 值"""
        market.rules[SS_HOST] = ss_ok(SS_FIND_SKILLS)
        resp = await _search(client, auth_headers, market=MARKET_SKILLSSH, q="find-skills")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["code"] == 0, body
        data = body["data"]
        assert data["market"] == "skillssh"
        items = data["items"]
        assert len(items) == 1
        it = items[0]
        assert {"name", "description", "installs", "ref", "market"} <= set(it.keys())
        assert it["name"] == "find-skills"
        assert it["ref"] == "vercel/labs/find-skills"  # 上游 skillId
        assert it["installs"] == 12345
        assert it["description"] == "Find skills on skills.sh"
        assert it["market"] == "skillssh"

    @pytest.mark.asyncio
    async def test_description_missing_becomes_empty(self, client, auth_headers, market):
        """上游未返回描述 → description=""(PRD:market 未返回则空)"""
        raw = {"name": "no-desc", "installs": 7, "skillId": "o/r/s"}
        market.rules[SS_HOST] = ss_ok(raw)
        resp = await _search(client, auth_headers, market=MARKET_SKILLSSH, q="no-desc")
        assert resp.status_code == 200, resp.text
        it = resp.json()["data"]["items"][0]
        assert it["description"] == ""
        assert it["ref"] == "o/r/s"
        assert it["installs"] == 7

    @pytest.mark.asyncio
    async def test_q_special_chars_encoded_passthrough(self, client, auth_headers, market):
        """特殊字符 q(URL encode 原样传递):下游收到的 q 与原始串等值"""
        market.rules[SS_HOST] = ss_ok(SS_FIND_SKILLS)
        raw_q = "c++ & rust=ok 100%"
        resp = await _search(client, auth_headers, market=MARKET_SKILLSSH, q=raw_q)
        assert resp.status_code == 200, resp.text
        assert market.calls[0]["params"]["q"] == raw_q


# ---------------------------------------------------------------------------
# 5. 市场超时/5xx → 502「市场暂不可用」
# ---------------------------------------------------------------------------
class TestMarketUnavailable:
    @pytest.mark.asyncio
    async def test_modelscope_timeout_502(self, client, auth_headers, market):
        """modelscope 连接超时 → 502,文案「市场暂不可用」(不 5xx 挂死)"""
        market.rules[MS_HOST] = _raise_connect_timeout
        resp = await _search(client, auth_headers, market=MARKET_MODELSCOPE)
        assert resp.status_code == 502, resp.text
        assert "市场暂不可用" in resp.json()["message"]

    @pytest.mark.asyncio
    async def test_skillssh_timeout_502(self, client, auth_headers, market):
        """skills.sh 读超时 → 502「市场暂不可用」"""
        market.rules[SS_HOST] = _raise_read_timeout
        resp = await _search(client, auth_headers, market=MARKET_SKILLSSH)
        assert resp.status_code == 502, resp.text
        assert "市场暂不可用" in resp.json()["message"]

    @pytest.mark.asyncio
    async def test_modelscope_500_502(self, client, auth_headers, market):
        """modelscope 返回 500 → 502「市场暂不可用」"""
        market.rules[MS_HOST] = lambda req: httpx.Response(500, json={"message": "boom"})
        resp = await _search(client, auth_headers, market=MARKET_MODELSCOPE)
        assert resp.status_code == 502, resp.text
        assert "市场暂不可用" in resp.json()["message"]


# ---------------------------------------------------------------------------
# 6. 适配器异常互不传染(单市场失败仅影响该 market 查询)
# ---------------------------------------------------------------------------
class TestAdapterIsolation:
    @pytest.mark.asyncio
    async def test_modelscope_failure_does_not_affect_skillssh(self, client, auth_headers, market):
        """modelscope 挂 → skillssh 查询照常 200;modelscope 502;skillssh 换 q 仍真实外呼成功"""
        market.rules[MS_HOST] = _raise_connect_timeout
        market.rules[SS_HOST] = ss_ok(SS_FIND_SKILLS)

        r1 = await _search(client, auth_headers, market=MARKET_SKILLSSH, q="a")
        assert r1.status_code == 200, r1.text

        r2 = await _search(client, auth_headers, market=MARKET_MODELSCOPE, q="a")
        assert r2.status_code == 502

        # 换 q 绕开缓存,证明 skillssh 适配器未被 modelscope 的异常污染(仍可外呼)
        r3 = await _search(client, auth_headers, market=MARKET_SKILLSSH, q="b")
        assert r3.status_code == 200, r3.text
        ss_calls = [c for c in market.calls if c["host"] == SS_HOST]
        assert len(ss_calls) == 2  # r1 + r3,均真实外呼


# ---------------------------------------------------------------------------
# 6.5 上游软失败(Success:false / 缺 skills 壳)→ 502 且不写缓存
# ---------------------------------------------------------------------------
class TestSoftFailure:
    @pytest.mark.asyncio
    async def test_modelscope_success_false_502_not_cached(self, client, auth_headers, market):
        """上游 200+{"Success":false,"Data":null}(故障期软失败)→ 502「市场暂不可用」;
        不写缓存:恢复后同 (market,q,limit) 重新外呼成功"""
        market.rules[MS_HOST] = lambda req: httpx.Response(200, json={"Success": False, "Data": None})
        r1 = await _search(client, auth_headers, market=MARKET_MODELSCOPE, q="find-skills")
        assert r1.status_code == 502, r1.text
        assert "市场暂不可用" in r1.json()["message"]

        market.rules[MS_HOST] = ms_ok(MS_FIND_SKILLS)
        r2 = await _search(client, auth_headers, market=MARKET_MODELSCOPE, q="find-skills")
        assert r2.status_code == 200, r2.text
        assert len(market.calls) == 2  # 软失败未被缓存 → 第二次真实外呼
        assert r2.json()["data"]["items"][0]["ref"] == "@vercel-labs/find-skills"

    @pytest.mark.asyncio
    async def test_skillssh_missing_skills_key_502_not_cached(self, client, auth_headers, market):
        """skillssh 200 但缺 skills 键(软失败)→ 502 且不写缓存;
        边界:{"skills": []} 仍为合法空结果 200(不误伤)"""
        market.rules[SS_HOST] = lambda req: httpx.Response(200, json={"skills": []})
        r0 = await _search(client, auth_headers, market=MARKET_SKILLSSH, q="empty")
        assert r0.status_code == 200, r0.text
        assert r0.json()["data"]["items"] == []

        market.rules[SS_HOST] = lambda req: httpx.Response(200, json={"note": "oops"})
        r1 = await _search(client, auth_headers, market=MARKET_SKILLSSH, q="find-skills")
        assert r1.status_code == 502, r1.text
        assert "市场暂不可用" in r1.json()["message"]

        market.rules[SS_HOST] = ss_ok(SS_FIND_SKILLS)
        r2 = await _search(client, auth_headers, market=MARKET_SKILLSSH, q="find-skills")
        assert r2.status_code == 200, r2.text
        assert len(market.calls) == 3  # r0 空结果 + r1 软失败 + r2 恢复,均真实外呼
        assert r2.json()["data"]["items"][0]["ref"] == "vercel/labs/find-skills"


# ---------------------------------------------------------------------------
# 7. 内存缓存:键 (market,q,limit);命中不外呼;失败不写缓存
# ---------------------------------------------------------------------------
class TestCache:
    @pytest.mark.asyncio
    async def test_cache_hit_no_second_outbound(self, client, auth_headers, market):
        """完成判据4:同 (market,q,limit) 两次查询 → 仅 1 次外呼,两次响应一致"""
        market.rules[MS_HOST] = ms_ok(MS_FIND_SKILLS)
        r1 = await _search(client, auth_headers, market=MARKET_MODELSCOPE, q="find-skills", limit=20)
        r2 = await _search(client, auth_headers, market=MARKET_MODELSCOPE, q="find-skills", limit=20)
        assert r1.status_code == 200 and r2.status_code == 200
        assert len(market.calls) == 1
        assert r1.json() == r2.json()

    @pytest.mark.asyncio
    async def test_cache_key_includes_limit(self, client, auth_headers, market):
        """缓存键含 limit:同 q 不同 limit → 两次真实外呼(PageSize 分别 20/50)"""
        market.rules[MS_HOST] = ms_ok(MS_FIND_SKILLS)
        r1 = await _search(client, auth_headers, market=MARKET_MODELSCOPE, q="find-skills", limit=20)
        r2 = await _search(client, auth_headers, market=MARKET_MODELSCOPE, q="find-skills", limit=50)
        assert r1.status_code == 200 and r2.status_code == 200
        assert len(market.calls) == 2
        assert [c["json"]["PageSize"] for c in market.calls] == [20, 50]

    @pytest.mark.asyncio
    async def test_failed_outbound_not_cached(self, client, auth_headers, market):
        """外呼失败不写缓存:先超时 502,恢复后同键查询重新外呼成功(即时透传)"""
        market.rules[MS_HOST] = _raise_connect_timeout
        r1 = await _search(client, auth_headers, market=MARKET_MODELSCOPE, q="find-skills")
        assert r1.status_code == 502

        market.rules[MS_HOST] = ms_ok(MS_FIND_SKILLS)
        r2 = await _search(client, auth_headers, market=MARKET_MODELSCOPE, q="find-skills")
        assert r2.status_code == 200, r2.text
        assert len(market.calls) == 2  # 失败未被缓存 → 第二次真实外呼
        assert r2.json()["data"]["items"][0]["ref"] == "@vercel-labs/find-skills"
