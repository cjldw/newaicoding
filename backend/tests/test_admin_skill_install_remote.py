"""
R4.F1(admin「Skills 市场」市场搜索安装到平台库)— QA TDD Red phase
====================================================================
依据 docs/20260926_skills市场安装/DEVPLAN/R4.F1.md(接口契约 + 权限矩阵 + 完成判据)。

被测对象(Green 待实现):
1. POST /api/admin/skills/install-remote  body {market, ref}(api/admin/skills.py,
   require_superadmin;R3 项目侧 install-remote 的平台库版)
   - 复用 skill_market_service.fetch_skill_md(market 适配器外呼拉 SKILL.md,
     502「市场暂不可用」/256KB 400 口径同 R3)→ parse_skill_markdown 校验(400 17003)
   - 入库 scope=platform(source=market + source_url;**无 project_skills 关联**,
     之后全项目可从平台库二级安装)
   - 同名覆盖(平台库已有同名 → 覆盖更新不重复建行,skill_id 保持不变——
     项目侧二级安装引用不悬空)
   - 审计(platform 级,无 project_id)
   - 响应同 R3 形态:data:{skill_id, name, source:"market", source_url, extra_files}

测试注入点契约(照抄 R3 test_skill_install_remote.py seam 先例):
- skill_market_service.set_test_transport(httpx.MockTransport)(R2 落地,已存在)
- 外呼打桩按 url.host 分路(modelscope.cn / skills.sh),MarketStub 记录每次外呼,
  未打桩 host 收到请求即 AssertionError(防实现打错 base/路径时静默通过)
- 超管:conftest.superadmin_headers;普通用户:registered_user(首注册=bootstrap
  superadmin)之后内联注册的第二个用户(role=user)→ 403 code=19002
"""
from urllib.parse import unquote

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import delete, select

from app.models.audit_log import AuditLog
from app.models.project import PlatformSetting
from app.models.skill import ProjectSkill, Skill
from app.models.user import User
from tests.test_skill_market_search import (
    MS_HOST,
    SS_HOST,
    MARKET_MODELSCOPE,
    MARKET_SKILLSSH,
    MarketStub,
)

INSTALL_URL = "/api/admin/skills/install-remote"

# 下游 SKILL.md 样例(合法 frontmatter)
FIND_SKILLS_MD = """---
name: find-skills
description: Find skills on ModelScope
---

按步骤帮助用户发现并安装合适的 Skill。
"""
FIND_SKILLS_MD_V2 = """---
name: find-skills
description: Find skills on ModelScope (updated)
---

更新后的正文内容 v2。
"""
README_MD = "# find-skills\n\n支撑文件(不应入库)。\n"
RUN_SH = "#!/bin/sh\necho helper\n"


# ---------------------------------------------------------------------------
# fixtures / helpers
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture
async def market(db_session):
    """市场外呼 mock:清 platform_settings 走 R1 默认种子 base,注入 MockTransport。
    复用 R2 的 MarketStub(按 host 打桩 + 外呼记录);set_test_transport 自带清缓存。"""
    await db_session.execute(delete(PlatformSetting))
    await db_session.commit()

    from app.services import skill_market_service as svc

    stub = MarketStub()
    svc.set_test_transport(httpx.MockTransport(stub))
    yield stub
    svc.set_test_transport(None)


async def _install(client, headers, *, market=MARKET_MODELSCOPE, ref="@vercel-labs/find-skills"):
    """调 POST /api/admin/skills/install-remote;入参 None 表示不携带该字段"""
    payload = {}
    if market is not None:
        payload["market"] = market
    if ref is not None:
        payload["ref"] = ref
    return await client.post(INSTALL_URL, headers=headers, json=payload)


def ms_skill_md(md: str):
    """modelscope resolve/master/SKILL.md 打桩:200 文本"""
    return lambda request: httpx.Response(200, text=md)


def ss_download(*path_contents):
    """skills.sh api/download 打桩:200 {files:[{path, contents}]}"""
    files = [{"path": p, "contents": c} for p, c in path_contents]
    return lambda request: httpx.Response(200, json={"files": files})


async def _platform_skill_rows(db, name=None):
    """平台官方库(scope=platform)行;name 传参则过滤"""
    stmt = select(Skill).where(Skill.scope == "platform")
    if name is not None:
        stmt = stmt.where(Skill.name == name)
    return list((await db.execute(stmt)).scalars().all())


async def _link_rows(db, skill_id=None):
    """project_skills 关联行(全表或按 skill_id);平台库安装必须恒为空"""
    stmt = select(ProjectSkill)
    if skill_id is not None:
        stmt = stmt.where(ProjectSkill.skill_id == skill_id)
    return list((await db.execute(stmt)).scalars().all())


async def _superadmin_ids(db) -> set:
    res = await db.execute(select(User.user_id).where(User.role == "superadmin"))
    return set(res.scalars().all())


# ---------------------------------------------------------------------------
# 1. 鉴权:未登录 401(不外呼)
# ---------------------------------------------------------------------------
class TestAuth:
    @pytest.mark.asyncio
    async def test_install_requires_login(self, client, db_session, market):
        """无 JWT → 401;鉴权先行,不触发市场外呼、不入库"""
        resp = await _install(client, {})
        assert resp.status_code == 401, resp.text
        assert market.calls == []
        assert await _platform_skill_rows(db_session) == []


# ---------------------------------------------------------------------------
# 2. 超管 modelscope 安装进平台库(主链路)
# ---------------------------------------------------------------------------
class TestModelscopeInstall:
    @pytest.mark.asyncio
    async def test_install_success_end_to_end(
        self, client, superadmin_headers, db_session, market
    ):
        """R4.F1 主链路:超管 {market:"modelscope", ref:"@vercel-labs/find-skills"} → 200;
        外呼 GET {base}/skills/@vercel-labs/find-skills/resolve/master/SKILL.md;
        入库 scope=platform + source=market + source_url,**无 project_skills 关联**;
        响应同 R3 形态 data:{skill_id,name,source:"market",source_url,extra_files};审计"""
        market.rules[MS_HOST] = ms_skill_md(FIND_SKILLS_MD)

        resp = await _install(client, superadmin_headers)
        assert resp.status_code == 200, resp.text
        assert resp.json()["code"] == 0, resp.json()

        # 外呼契约:1 次 GET,modelscope 域,resolve/master/SKILL.md 路径
        assert len(market.calls) == 1
        call = market.calls[0]
        assert call["method"] == "GET"
        assert call["host"] == MS_HOST
        assert unquote(call["path"]) == "/skills/@vercel-labs/find-skills/resolve/master/SKILL.md"

        # 响应契约(同 R3 形态 + extra_files)
        data = resp.json()["data"]
        assert data["name"] == "find-skills"
        assert data["source"] == "market"
        assert data["source_url"] == call["url"]
        assert data["extra_files"] == 0

        # 入库:scope=platform + source=market + source_url,不挂任何项目
        skills = await _platform_skill_rows(db_session, "find-skills")
        assert len(skills) == 1
        sk = skills[0]
        assert sk.skill_id == data["skill_id"]
        assert sk.scope == "platform"
        assert sk.project_id is None
        assert sk.source == "market"
        assert sk.source_url == call["url"]
        assert sk.content == FIND_SKILLS_MD
        assert sk.description == "Find skills on ModelScope"
        assert sk.created_by in await _superadmin_ids(db_session)

        # **无 project_skills 关联**(全表为空——平台库安装不产生项目侧关联)
        assert await _link_rows(db_session) == []

        # 审计(platform 级,无 project_id)
        audits = list(
            (await db_session.execute(
                select(AuditLog).where(AuditLog.target_id == sk.skill_id)
            )).scalars().all()
        )
        assert len(audits) == 1
        assert audits[0].project_id is None

    @pytest.mark.asyncio
    async def test_platform_list_shows_market_source(
        self, client, superadmin_headers, db_session, market
    ):
        """完成判据「列表出现 source=market」:安装后 GET /api/admin/skills
        平台库列表该项带 source="market" + source_url(前端来源列数据源)"""
        market.rules[MS_HOST] = ms_skill_md(FIND_SKILLS_MD)
        resp = await _install(client, superadmin_headers)
        assert resp.status_code == 200, resp.text

        resp = await client.get("/api/admin/skills", headers=superadmin_headers)
        assert resp.status_code == 200, resp.text
        items = [it for it in resp.json()["data"]["items"] if it["name"] == "find-skills"]
        assert len(items) == 1
        assert items[0]["scope"] == "platform"
        assert items[0]["source"] == "market"
        assert items[0]["source_url"]


# ---------------------------------------------------------------------------
# 3. skillssh 源:api/download 取 files[path=SKILL.md].contents
# ---------------------------------------------------------------------------
class TestSkillsshInstall:
    @pytest.mark.asyncio
    async def test_install_success_single_file(
        self, client, superadmin_headers, db_session, market
    ):
        """market=skillssh ref={owner}/{repo}/{slug} → 200;
        外呼 GET {base}/api/download/vercel/labs/find-skills 取 files[path=SKILL.md].contents;
        入库 scope=platform + source=market,无关联"""
        market.rules[SS_HOST] = ss_download(("SKILL.md", FIND_SKILLS_MD))

        resp = await _install(
            client, superadmin_headers,
            market=MARKET_SKILLSSH, ref="vercel/labs/find-skills",
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["code"] == 0, resp.json()

        assert len(market.calls) == 1
        call = market.calls[0]
        assert call["method"] == "GET"
        assert call["host"] == SS_HOST
        assert call["path"] == "/api/download/vercel/labs/find-skills"

        data = resp.json()["data"]
        assert data["name"] == "find-skills"
        assert data["source"] == "market"
        assert data["source_url"] == call["url"]
        assert data["extra_files"] == 0

        skills = await _platform_skill_rows(db_session, "find-skills")
        assert len(skills) == 1
        assert skills[0].scope == "platform"
        assert skills[0].source == "market"
        assert skills[0].content == FIND_SKILLS_MD
        assert await _link_rows(db_session, skills[0].skill_id) == []

    @pytest.mark.asyncio
    async def test_multi_files_extra_files_reported_only_skill_md_installed(
        self, client, superadmin_headers, db_session, market
    ):
        """files>1 → 仍 200 但 extra_files=2(支撑文件数),仅装 SKILL.md;
        README/scripts 不入库(skill 内容=SKILL.md contents)"""
        market.rules[SS_HOST] = ss_download(
            ("SKILL.md", FIND_SKILLS_MD),
            ("README.md", README_MD),
            ("scripts/run.sh", RUN_SH),
        )

        resp = await _install(
            client, superadmin_headers,
            market=MARKET_SKILLSSH, ref="vercel/labs/find-skills",
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["extra_files"] == 2  # 支撑文件数(除 SKILL.md 外)
        assert data["name"] == "find-skills"

        skills = await _platform_skill_rows(db_session)
        assert len(skills) == 1  # 仅装 SKILL.md,不重复建行
        assert skills[0].content == FIND_SKILLS_MD


# ---------------------------------------------------------------------------
# 4. 同名覆盖:平台库已有同名 → 覆盖更新不重复建行(skill_id 不变)
# ---------------------------------------------------------------------------
class TestOverwriteExistingPlatform:
    @pytest.mark.asyncio
    async def test_same_name_overwrites_existing_platform_skill(
        self, client, superadmin_headers, db_session, market
    ):
        """平台库已有同名(超管 CRUD 手工创建)→ 市场安装覆盖该行:
        不重复建行、skill_id 保持不变(项目侧二级安装引用不悬空),
        description/content/source/source_url 更新为本次拉取结果"""
        # 平台库预置同名 Skill(超管 CRUD 建行语义)
        resp = await client.post(
            "/api/admin/skills",
            headers=superadmin_headers,
            json={
                "name": "find-skills",
                "description": "手工创建的平台 Skill",
                "content": "---\nname: find-skills\ndescription: 手工创建的平台 Skill\n---\n\n手工内容\n",
            },
        )
        assert resp.status_code == 200, resp.text
        seeded_skill_id = resp.json()["data"]["skill_id"]

        market.rules[MS_HOST] = ms_skill_md(FIND_SKILLS_MD_V2)
        resp = await _install(client, superadmin_headers)
        assert resp.status_code == 200, resp.text
        assert resp.json()["code"] == 0

        skills = await _platform_skill_rows(db_session, "find-skills")
        assert len(skills) == 1  # 覆盖更新,不重复建行
        sk = skills[0]
        assert sk.skill_id == seeded_skill_id  # 原地覆盖,skill_id 不变
        assert sk.description == "Find skills on ModelScope (updated)"
        assert sk.content == FIND_SKILLS_MD_V2
        assert sk.source == "market"
        assert sk.source_url == market.calls[0]["url"]
        assert await _link_rows(db_session, sk.skill_id) == []


# ---------------------------------------------------------------------------
# 5. 权限:非 superadmin 403(鉴权/权限先行,不外呼、不入库)
# ---------------------------------------------------------------------------
class TestPermission:
    @pytest.mark.asyncio
    async def test_non_superadmin_403(
        # 注意顺序:auth_headers(registered_user=首注册 bootstrap superadmin)
        # 先于 second_user_headers 实例化,保证后者是第二个注册用户(role=user)
        self, client, auth_headers, second_user_headers, db_session, market
    ):
        """普通登录用户安装 → 403 code=19002;权限先行,不触发市场外呼、不入库"""
        market.rules[MS_HOST] = ms_skill_md(FIND_SKILLS_MD)
        resp = await _install(client, second_user_headers)
        assert resp.status_code == 403, resp.text
        assert resp.json()["code"] == 19002
        assert market.calls == []
        assert await _platform_skill_rows(db_session) == []


# ---------------------------------------------------------------------------
# 6. 拉取失败(404/5xx)→ 502「市场暂不可用」,不入库
# ---------------------------------------------------------------------------
class TestFetchFailure:
    @pytest.mark.asyncio
    async def test_modelscope_404_502(self, client, superadmin_headers, db_session, market):
        """modelscope 返回 404 → 502「市场暂不可用」;不建任何行"""
        market.rules[MS_HOST] = lambda req: httpx.Response(404, json={"message": "not found"})
        resp = await _install(client, superadmin_headers)
        assert resp.status_code == 502, resp.text
        assert "市场暂不可用" in resp.json()["message"]
        assert await _platform_skill_rows(db_session) == []

    @pytest.mark.asyncio
    async def test_skillssh_500_502(self, client, superadmin_headers, db_session, market):
        """skills.sh 返回 500 → 502「市场暂不可用」"""
        market.rules[SS_HOST] = lambda req: httpx.Response(500, json={"message": "boom"})
        resp = await _install(
            client, superadmin_headers,
            market=MARKET_SKILLSSH, ref="vercel/labs/find-skills",
        )
        assert resp.status_code == 502, resp.text
        assert "市场暂不可用" in resp.json()["message"]
        assert await _platform_skill_rows(db_session) == []


# ---------------------------------------------------------------------------
# 7. 内容校验(frontmatter / 256KB):市场内容是 prompt 注入面,校验强制
# ---------------------------------------------------------------------------
class TestContentValidation:
    @pytest.mark.asyncio
    async def test_missing_name_400(self, client, superadmin_headers, db_session, market):
        """frontmatter 缺 name → 400(17003)带原因;不入库"""
        market.rules[MS_HOST] = ms_skill_md("---\ndescription: 缺名字\n---\n\n正文\n")
        resp = await _install(client, superadmin_headers)
        assert resp.status_code == 400, resp.text
        body = resp.json()
        assert body["code"] == 17003
        assert body["message"]
        assert await _platform_skill_rows(db_session) == []

    @pytest.mark.asyncio
    async def test_no_frontmatter_400(self, client, superadmin_headers, db_session, market):
        """无 frontmatter 纯 markdown → 400(17003);不入库"""
        market.rules[MS_HOST] = ms_skill_md("没有 frontmatter 的普通 markdown")
        resp = await _install(client, superadmin_headers)
        assert resp.status_code == 400, resp.text
        assert resp.json()["code"] == 17003
        assert await _platform_skill_rows(db_session) == []

    @staticmethod
    def _md_with_body_bytes(total_bytes: int) -> str:
        """合法 frontmatter + 正文填充到指定总字节数(ASCII:字节数=字符数)"""
        base = "---\nname: big-skill\ndescription: 大内容边界\n---\n\n"
        assert total_bytes >= len(base)
        return base + "a" * (total_bytes - len(base))

    @pytest.mark.asyncio
    async def test_content_over_256kb_400(self, client, superadmin_headers, db_session, market):
        """content > 256KB(262145B)→ 400;不入库"""
        market.rules[MS_HOST] = ms_skill_md(self._md_with_body_bytes(256 * 1024 + 1))
        resp = await _install(client, superadmin_headers)
        assert resp.status_code == 400, resp.text
        assert resp.json()["code"] != 0
        assert await _platform_skill_rows(db_session) == []

    @pytest.mark.asyncio
    async def test_content_exactly_256kb_ok(self, client, superadmin_headers, db_session, market):
        """边界:content 恰好 256KB(契约 ≤256KB 允许)→ 200 入库"""
        market.rules[MS_HOST] = ms_skill_md(self._md_with_body_bytes(256 * 1024))
        resp = await _install(client, superadmin_headers)
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["name"] == "big-skill"


# ---------------------------------------------------------------------------
# 8. 参数校验(market 不在源列表 / ref 空):参数先行,不外呼、不入库
# ---------------------------------------------------------------------------
class TestParamValidation:
    @pytest.mark.asyncio
    async def test_unknown_market_400_no_outbound(
        self, client, superadmin_headers, db_session, market
    ):
        """market=github(不在源列表)→ 400,不外呼、不入库"""
        resp = await _install(client, superadmin_headers, market="github")
        assert resp.status_code == 400, resp.text
        assert resp.json()["code"] != 0
        assert market.calls == []
        assert await _platform_skill_rows(db_session) == []

    @pytest.mark.asyncio
    async def test_empty_ref_400_no_outbound(
        self, client, superadmin_headers, db_session, market
    ):
        """ref=空串 → 400,不外呼、不入库"""
        resp = await _install(client, superadmin_headers, ref="")
        assert resp.status_code == 400, resp.text
        assert market.calls == []
        assert await _platform_skill_rows(db_session) == []
