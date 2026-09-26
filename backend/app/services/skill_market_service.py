"""Skills 市场服务 - R2 市场搜索后端代理(httpx 双适配器)

契约(docs/20260926_skills市场安装/DEVPLAN/R2.md):
- GET /api/skills/market/search?market=&q=&limit= 代理双市场并归一化为
  [{name, description, installs, ref, market}]
- 适配器:
  - modelscope: PUT {base}/api/v1/dolphin/skills body {Query, PageSize, PageNumber:1}
    (⚠️ 过滤字段是 Query)→ Data.SkillList(name=Name, ref=Path/Name, installs=DownloadCount)
  - skillssh: GET {base}/api/search?q=&limit= → skills[](ref=skillId=owner/repo/slug, installs)
- 市场源(R1): type/base 读 platform_settings 的 skill_market_sources,
  未配置时读取层兜底默认两源种子(platform_settings_service.default_skill_market_sources)
- 缓存: 进程内内存 TTL 300s(上限 512 条,满即清),键 (market, q, limit);
  仅缓存成功结果,外呼失败/上游软失败(Success:false、缺 skills 壳)不写缓存
- 降级: 上游超时/非 200/响应不可解析/软失败 → BizError(17005, 502)「市场暂不可用」
- 隔离: 适配器异常互不传染(单市场失败仅影响该 market 查询,不写共享状态)
"""

import logging
import time
from copy import deepcopy
from typing import Any, Optional

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.response import BizError, ErrCode
from app.services import platform_settings_service

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------
# 上游外呼超时(R2 契约:5s)
HTTP_TIMEOUT = 5.0

# limit 校验(R2 契约:上限 50;默认值/整数解析在 API 层,越界走 BizError 400 而非 FastAPI 422)
LIMIT_MAX = 50

# 进程内内存缓存:TTL 300s,键 (market, q_trimmed, limit),值 (过期时刻, 响应 data);
# 容量上限防膨胀(仿 knowledge_service._code_cache 先例:满即整体清空)
CACHE_TTL_SECONDS = 300.0
CACHE_MAX_ENTRIES = 512
_cache: dict[tuple, tuple[float, dict]] = {}

# ---------------------------------------------------------------------------
# 测试用 mock transport 注入点(gitlab_service._test_transport 先例)
# ---------------------------------------------------------------------------
_test_transport: Optional[httpx.MockTransport] = None


def set_test_transport(transport: Optional[httpx.MockTransport]) -> None:
    """供测试 fixture 调用,设置/清除 mock transport;同时清缓存防跨用例污染"""
    global _test_transport
    _test_transport = transport
    _cache.clear()


def _get_client() -> httpx.AsyncClient:
    """
    获取 httpx.AsyncClient(gitlab_service 先例):
    - 测试环境(_test_transport 非 None):使用 mock transport
    - 正常环境:普通 AsyncClient(5s 超时)
    - follow_redirects:base 配了会 30x 的域名(如 www→apex)时跟随重定向,
      否则该市场会永久 502 且日志难辨配置错还是故障
    """
    if _test_transport is not None:
        return httpx.AsyncClient(
            transport=_test_transport, timeout=HTTP_TIMEOUT, follow_redirects=True
        )
    return httpx.AsyncClient(timeout=HTTP_TIMEOUT, follow_redirects=True)


# ---------------------------------------------------------------------------
# 错误构造(R2 错误码:17004 参数非法 400 / 17005 市场不可用 502)
# ---------------------------------------------------------------------------
def _param_invalid(msg: str) -> BizError:
    return BizError(ErrCode.SKILL_MARKET_PARAM_INVALID, msg, status_code=400)


def _unavailable() -> BizError:
    return BizError(ErrCode.SKILL_MARKET_UNAVAILABLE, "市场暂不可用,请稍后重试", status_code=502)


# ---------------------------------------------------------------------------
# 内存 TTL 缓存(仅缓存成功结果;命中不外呼,失败不写缓存)
# ---------------------------------------------------------------------------
def _cache_get(key: tuple) -> Optional[dict]:
    hit = _cache.get(key)
    if hit is None:
        return None
    expires_at, value = hit
    if time.monotonic() >= expires_at:
        _cache.pop(key, None)
        return None
    return deepcopy(value)


def _cache_set(key: tuple, value: dict) -> None:
    if len(_cache) >= CACHE_MAX_ENTRIES:
        _cache.clear()   # 简单防膨胀:满即整体清空(容量远大于正常并发查询数)
    _cache[key] = (time.monotonic() + CACHE_TTL_SECONDS, deepcopy(value))


def _coerce_int(v: Any) -> int:
    """installs 兜底:可转则 int(含数字字符串/浮点),否则按 0(前端按数字排序/展示)"""
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


# ---------------------------------------------------------------------------
# 适配器(双市场各自独立:异常在适配器内收口为 502,互不传染)
# ---------------------------------------------------------------------------
def _normalize_modelscope(body: Any) -> list[dict]:
    """Data.SkillList → [{name, description, installs, ref, market}]"""
    data = body.get("Data") if isinstance(body, dict) else None
    skill_list = data.get("SkillList") if isinstance(data, dict) else None
    skill_list = skill_list if isinstance(skill_list, list) else []
    items: list[dict] = []
    for s in skill_list:
        if not isinstance(s, dict):
            continue
        name = str(s.get("Name") or "")
        path = str(s.get("Path") or "")
        items.append(
            {
                "name": name,
                "description": str(s.get("Description") or ""),
                "installs": _coerce_int(s.get("DownloadCount")),
                "ref": f"{path}/{name}" if path else name,
                "market": "modelscope",
            }
        )
    return items


def _normalize_skillssh(body: Any) -> list[dict]:
    """skills[] → [{name, description, installs, ref=skillId, market}]"""
    skills = body.get("skills") if isinstance(body, dict) else None
    skills = skills if isinstance(skills, list) else []
    items: list[dict] = []
    for s in skills:
        if not isinstance(s, dict):
            continue
        items.append(
            {
                "name": str(s.get("name") or ""),
                "description": str(s.get("description") or ""),
                "installs": _coerce_int(s.get("installs")),
                "ref": str(s.get("skillId") or ""),
                "market": "skillssh",
            }
        )
    return items


async def _search_modelscope(source: dict, q: str, limit: int) -> list[dict]:
    """ModelScope 适配器:PUT {base}/api/v1/dolphin/skills,过滤字段是 Query"""
    url = f"{source['base']}/api/v1/dolphin/skills"
    payload = {"Query": q, "PageSize": limit, "PageNumber": 1}
    started = time.monotonic()
    client = _get_client()
    try:
        try:
            resp = await client.put(url, json=payload)
        except httpx.HTTPError as e:
            logger.warning("[skill_market] modelscope 外呼异常 url=%s err=%s", url, e)
            raise _unavailable() from e
        if resp.status_code != 200:
            logger.warning(
                "[skill_market] modelscope 上游非200 status=%s url=%s body=%s",
                resp.status_code, url, resp.text[:200],
            )
            raise _unavailable()
        try:
            body = resp.json()
        except ValueError as e:
            logger.warning("[skill_market] modelscope 响应非 JSON url=%s", url)
            raise _unavailable() from e
        # 壳软失败(Success 显式 false,故障期上游常见 200+{"Success":false,"Data":null})
        # → 502 且不写缓存,避免把「故障」当「无结果」缓存 300s
        if isinstance(body, dict) and body.get("Success") is False:
            logger.warning(
                "[skill_market] modelscope 软失败 Success=false url=%s body=%s",
                url, resp.text[:200],
            )
            raise _unavailable()
        items = _normalize_modelscope(body)
        logger.info(
            "[skill_market] modelscope 搜索完成 q=%r limit=%s items=%s 耗时=%.3fs",
            q, limit, len(items), time.monotonic() - started,
        )
        return items
    finally:
        await client.aclose()


async def _search_skillssh(source: dict, q: str, limit: int) -> list[dict]:
    """skills.sh 适配器:GET {base}/api/search?q=&limit="""
    url = f"{source['base']}/api/search"
    params = {"q": q, "limit": limit}
    started = time.monotonic()
    client = _get_client()
    try:
        try:
            resp = await client.get(url, params=params)
        except httpx.HTTPError as e:
            logger.warning("[skill_market] skillssh 外呼异常 url=%s err=%s", url, e)
            raise _unavailable() from e
        if resp.status_code != 200:
            logger.warning(
                "[skill_market] skillssh 上游非200 status=%s url=%s body=%s",
                resp.status_code, url, resp.text[:200],
            )
            raise _unavailable()
        try:
            body = resp.json()
        except ValueError as e:
            logger.warning("[skill_market] skillssh 响应非 JSON url=%s", url)
            raise _unavailable() from e
        # 壳软失败(缺 skills 键/非数组)→ 502 且不写缓存({"skills": []} 仍为合法空结果)
        skills = body.get("skills") if isinstance(body, dict) else None
        if not isinstance(skills, list):
            logger.warning(
                "[skill_market] skillssh 软失败 缺 skills 壳 url=%s body=%s",
                url, resp.text[:200],
            )
            raise _unavailable()
        items = _normalize_skillssh(body)
        logger.info(
            "[skill_market] skillssh 搜索完成 q=%r limit=%s items=%s 耗时=%.3fs",
            q, limit, len(items), time.monotonic() - started,
        )
        return items
    finally:
        await client.aclose()


# 市场分支分发表(type → 适配器;新增市场源类型在此注册)
_ADAPTERS = {
    "modelscope": _search_modelscope,
    "skillssh": _search_skillssh,
}


# ---------------------------------------------------------------------------
# 服务入口(api 层调用)
# ---------------------------------------------------------------------------
async def search(db: AsyncSession, market: str, q: str, limit: int) -> dict:
    """
    市场搜索(R2):校验 → 源解析(R1)→ 缓存 → 适配器外呼 → 归一化。
    limit 由 API 层解析为整数(默认 20),此处仅做范围兜底校验;
    返回 {"market": ..., "items": [...]};校验失败 400(17004),上游失败 502(17005)。
    """
    started = time.monotonic()
    logger.info("[skill_market] 搜索入口 market=%r q=%r limit=%r", market, q, limit)

    # 1. 参数校验(先于外呼/缓存;q 前后空格 trim)
    q = (q or "").strip()
    if not q:
        raise _param_invalid("搜索词 q 不能为空")
    if not (1 <= limit <= LIMIT_MAX):
        raise _param_invalid(f"limit 需在 1-{LIMIT_MAX} 之间")
    market = (market or "").strip()

    # 2. market 须在源列表(R1 platform_settings;读取层未配置时兜底默认两源种子,永非空)
    sources = await platform_settings_service.get_setting(db, "skill_market_sources")
    source = next(
        (s for s in sources if isinstance(s, dict) and s.get("type") == market), None
    )
    if source is None:
        logger.info("[skill_market] market 不在源列表 market=%r sources=%s", market, sources)
        raise _param_invalid(f"市场 {market or '(空)'} 不在可用源列表")

    # 3. 缓存命中不外呼(键含 market,跨市场互不串扰)
    key = (market, q, limit)
    cached = _cache_get(key)
    if cached is not None:
        logger.info("[skill_market] 缓存命中 market=%s q=%r limit=%s", market, q, limit)
        return cached

    # 4. 分发适配器(单市场失败仅影响该 market;失败/软失败不写缓存,即时透传 502)
    adapter = _ADAPTERS.get(market)
    try:
        items = await adapter(source, q, limit)
    except BizError:
        raise  # 502 已在适配器内收口,原样透传
    except Exception as e:
        logger.exception("[skill_market] 适配器未预期异常 market=%s", market)
        raise _unavailable() from e

    result = {"market": market, "items": items}
    # _cache_set 存入的是深拷贝,此处直接返回原对象即可(不重复拷贝一次)
    _cache_set(key, result)
    logger.info(
        "[skill_market] 搜索完成 market=%s q=%r limit=%s items=%s 总耗时=%.3fs",
        market, q, limit, len(items), time.monotonic() - started,
    )
    return result
