"""
R3(skills 市场安装)— 一键安装到项目 — QA TDD Red phase
====================================================================
依据 docs/20260926_skills市场安装/DEVPLAN/R3.md(接口契约 + 服务端行为规格 + 完成判据)
与 PRD-A R3。

被测对象(Green 待实现):
1. POST /api/projects/{pid}/skills/install-remote  body {market, ref}(api/projects.py,
   upload 旁;require_project_role editor+)
   - market 适配器 fetch_skill_md(ref):
     - modelscope:GET {base}/skills/{Path}/{Name}/resolve/master/SKILL.md(文本)
     - skillssh:GET {base}/api/download/{owner}/{repo}/{slug} → files[path=SKILL.md].contents
       (files>1 返回支撑文件数 extra_files,仅装 SKILL.md)
   - parse_skill_markdown 校验(frontmatter name/description/kebab-case)→ 失败 400 带原因
   - 同名覆盖入库(复用 upload_skill 覆盖语义:scope=project 不重复建行)+ project_skills 关联
   - skills 表迁移新列:source ENUM(platform/project/market)+ source_url VARCHAR(512)
   - content ≤256KB,超限 400;拉取失败/404/5xx/超时 → 502「市场暂不可用」
   - 响应 data:{skill_id, name, source:"market", source_url, extra_files:n}

测试注入点契约(沿用 R2 test_skill_market_search.py 先例):
- skill_market_service.set_test_transport(httpx.MockTransport)(已存在,R2 落地)
- 外呼打桩按 url.host 分路(modelscope.cn / skills.sh),MarketStub 记录每次外呼,
  未打桩 host 收到请求即 AssertionError(防实现打错 base/路径时静默通过)
"""
import uuid
from urllib.parse import unquote

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import delete, select

from app.models.project import PlatformSetting
from app.models.skill import ProjectSkill, Skill
from tests.test_projects_api import _insert_project
from tests.test_skill_market_search import (
    MS_HOST,
    SS_HOST,
    MARKET_MODELSCOPE,
    MARKET_SKILLSSH,
    MarketStub,
    _raise_connect_timeout,
)

INSTALL_URL = "/api/projects/{pid}/skills/install-remote"

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


async def _install(client, headers, pid, *, market=MARKET_MODELSCOPE, ref="@vercel-labs/find-skills"):
    """调 POST install-remote;入参 None 表示不携带该字段"""
    payload = {}
    if market is not None:
        payload["market"] = market
    if ref is not None:
        payload["ref"] = ref
    return await client.post(INSTALL_URL.format(pid=pid), headers=headers, json=payload)


def ms_skill_md(md: str):
    """modelscope resolve/master/SKILL.md 打桩:200 文本"""
    return lambda request: httpx.Response(200, text=md)


def ss_download(*path_contents):
    """skills.sh api/download 打桩:200 {files:[{path, contents}]}"""
    files = [{"path": p, "contents": c} for p, c in path_contents]
    return lambda request: httpx.Response(200, json={"files": files})


async def _project_skill_rows(db, project_id, name=None):
    stmt = select(Skill).where(Skill.scope == "project", Skill.project_id == project_id)
    if name is not None:
        stmt = stmt.where(Skill.name == name)
    return list((await db.execute(stmt)).scalars().all())


async def _link_rows(db, project_id):
    res = await db.execute(
        select(ProjectSkill).where(ProjectSkill.project_id == project_id)
    )
    return list(res.scalars().all())


# ---------------------------------------------------------------------------
# 1. 鉴权:未登录 401(不外呼)
# ---------------------------------------------------------------------------
class TestAuth:
    @pytest.mark.asyncio
    async def test_install_requires_login(self, client, db_session, market, registered_user):
        """无 JWT → 401;鉴权先行,不触发市场外呼、不入库"""
        project = await _insert_project(db_session, registered_user["user_id"])
        resp = await _install(client, {}, project.project_id)
        assert resp.status_code == 401
        assert market.calls == []


# ---------------------------------------------------------------------------
# 2. modelscope 源:resolve/master/SKILL.md → 入库 + 关联
# ---------------------------------------------------------------------------
class TestModelscopeInstall:
    @pytest.mark.asyncio
    async def test_install_success_end_to_end(
        self, client, auth_headers, db_session, market, registered_user
    ):
        """完成判据1:market=modelscope ref=@vercel-labs/find-skills → 200;
        外呼 GET {base}/skills/@vercel-labs/find-skills/resolve/master/SKILL.md;
        入库 scope=project + source=market + source_url;project_skills 关联建立;
        响应 data:{skill_id,name,source:"market",source_url,extra_files}"""
        market.rules[MS_HOST] = ms_skill_md(FIND_SKILLS_MD)
        project = await _insert_project(db_session, registered_user["user_id"])

        resp = await _install(client, auth_headers, project.project_id)
        assert resp.status_code == 200, resp.text
        assert resp.json()["code"] == 0, resp.json()

        # 外呼契约:1 次 GET,modelscope 域,resolve/master/SKILL.md 路径
        assert len(market.calls) == 1
        call = market.calls[0]
        assert call["method"] == "GET"
        assert call["host"] == MS_HOST
        assert unquote(call["path"]) == "/skills/@vercel-labs/find-skills/resolve/master/SKILL.md"

        # 响应契约
        data = resp.json()["data"]
        assert data["name"] == "find-skills"
        assert data["source"] == "market"
        assert data["source_url"] == call["url"]
        assert data["extra_files"] == 0

        # 入库:scope=project + source=market + source_url
        skills = await _project_skill_rows(db_session, project.project_id, "find-skills")
        assert len(skills) == 1
        sk = skills[0]
        assert sk.skill_id == data["skill_id"]
        assert sk.source == "market"
        assert sk.source_url == call["url"]
        assert sk.content == FIND_SKILLS_MD
        assert sk.created_by == registered_user["user_id"]

        # project_skills 关联建立
        links = await _link_rows(db_session, project.project_id)
        assert len(links) == 1
        assert links[0].skill_id == sk.skill_id
        assert links[0].installed_by == registered_user["user_id"]

    @pytest.mark.asyncio
    async def test_unknown_market_400_no_outbound(
        self, client, auth_headers, db_session, market, registered_user
    ):
        """market=github(不在源列表)→ 400,不外呼、不入库"""
        project = await _insert_project(db_session, registered_user["user_id"])
        resp = await _install(client, auth_headers, project.project_id, market="github")
        assert resp.status_code == 400, resp.text
        assert resp.json()["code"] != 0
        assert market.calls == []
        assert await _project_skill_rows(db_session, project.project_id) == []

    @pytest.mark.asyncio
    async def test_empty_ref_400_no_outbound(
        self, client, auth_headers, db_session, market, registered_user
    ):
        """ref=空串 → 400,不外呼、不入库"""
        project = await _insert_project(db_session, registered_user["user_id"])
        resp = await _install(client, auth_headers, project.project_id, ref="")
        assert resp.status_code == 400, resp.text
        assert market.calls == []
        assert await _project_skill_rows(db_session, project.project_id) == []


# ---------------------------------------------------------------------------
# 3. skillssh 源:api/download 取 files[path=SKILL.md].contents
# ---------------------------------------------------------------------------
class TestSkillsshInstall:
    @pytest.mark.asyncio
    async def test_install_success_single_file(
        self, client, auth_headers, db_session, market, registered_user
    ):
        """完成判据2:market=skillssh ref={owner}/{repo}/{slug} → 200「安装成功」;
        外呼 GET {base}/api/download/vercel/labs/find-skills 取 files[path=SKILL.md].contents"""
        market.rules[SS_HOST] = ss_download(("SKILL.md", FIND_SKILLS_MD))
        project = await _insert_project(db_session, registered_user["user_id"])

        resp = await _install(
            client, auth_headers, project.project_id,
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

        skills = await _project_skill_rows(db_session, project.project_id, "find-skills")
        assert len(skills) == 1
        assert skills[0].content == FIND_SKILLS_MD
        assert skills[0].source == "market"
        links = await _link_rows(db_session, project.project_id)
        assert len(links) == 1
        assert links[0].skill_id == skills[0].skill_id

    @pytest.mark.asyncio
    async def test_multi_files_extra_files_reported_only_skill_md_installed(
        self, client, auth_headers, db_session, market, registered_user
    ):
        """完成判据5:files>1 → 仍 200 但 extra_files>1(支撑文件数),仅装 SKILL.md;
        README/scripts 不入库(skill 内容=SKILL.md contents)"""
        market.rules[SS_HOST] = ss_download(
            ("SKILL.md", FIND_SKILLS_MD),
            ("README.md", README_MD),
            ("scripts/run.sh", RUN_SH),
        )
        project = await _insert_project(db_session, registered_user["user_id"])

        resp = await _install(
            client, auth_headers, project.project_id,
            market=MARKET_SKILLSSH, ref="vercel/labs/find-skills",
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["extra_files"] == 2  # 支撑文件数(除 SKILL.md 外)
        assert data["name"] == "find-skills"

        skills = await _project_skill_rows(db_session, project.project_id)
        assert len(skills) == 1  # 仅装 SKILL.md,不重复建行
        assert skills[0].content == FIND_SKILLS_MD


# ---------------------------------------------------------------------------
# 4. 同名重复安装 → 覆盖更新不重复建行(幂等)
# ---------------------------------------------------------------------------
class TestIdempotentOverwrite:
    @pytest.mark.asyncio
    async def test_reinstall_same_name_overwrites(
        self, client, auth_headers, db_session, market, registered_user
    ):
        """完成判据3:同名重复安装 → 覆盖内容,skills/project_skills 均不重复建行;
        skill_id 保持不变(upload_skill 覆盖语义),描述/正文更新为第二次拉取结果"""
        project = await _insert_project(db_session, registered_user["user_id"])
        market.rules[MS_HOST] = ms_skill_md(FIND_SKILLS_MD)

        r1 = await _install(client, auth_headers, project.project_id)
        assert r1.status_code == 200, r1.text
        skill_id_1 = r1.json()["data"]["skill_id"]

        market.rules[MS_HOST] = ms_skill_md(FIND_SKILLS_MD_V2)
        r2 = await _install(client, auth_headers, project.project_id)
        assert r2.status_code == 200, r2.text
        assert r2.json()["code"] == 0

        skills = await _project_skill_rows(db_session, project.project_id, "find-skills")
        assert len(skills) == 1  # 覆盖更新,不重复建行
        sk = skills[0]
        assert sk.skill_id == skill_id_1
        assert sk.description == "Find skills on ModelScope (updated)"
        assert sk.content == FIND_SKILLS_MD_V2

        links = await _link_rows(db_session, project.project_id)
        assert len(links) == 1  # 关联也不重复
        assert links[0].skill_id == skill_id_1


# ---------------------------------------------------------------------------
# 5. 拉取失败(404/5xx/超时)→ 502「市场暂不可用」,不入库
# ---------------------------------------------------------------------------
class TestFetchFailure:
    @pytest.mark.asyncio
    async def test_modelscope_404_502(self, client, auth_headers, db_session, market, registered_user):
        """modelscope 返回 404 → 502「市场暂不可用」;不建任何行"""
        market.rules[MS_HOST] = lambda req: httpx.Response(404, json={"message": "not found"})
        project = await _insert_project(db_session, registered_user["user_id"])
        resp = await _install(client, auth_headers, project.project_id)
        assert resp.status_code == 502, resp.text
        assert "市场暂不可用" in resp.json()["message"]
        assert await _project_skill_rows(db_session, project.project_id) == []
        assert await _link_rows(db_session, project.project_id) == []

    @pytest.mark.asyncio
    async def test_modelscope_500_502(self, client, auth_headers, db_session, market, registered_user):
        """modelscope 返回 500 → 502「市场暂不可用」"""
        market.rules[MS_HOST] = lambda req: httpx.Response(500, json={"message": "boom"})
        project = await _insert_project(db_session, registered_user["user_id"])
        resp = await _install(client, auth_headers, project.project_id)
        assert resp.status_code == 502, resp.text
        assert "市场暂不可用" in resp.json()["message"]
        assert await _project_skill_rows(db_session, project.project_id) == []

    @pytest.mark.asyncio
    async def test_skillssh_500_502(self, client, auth_headers, db_session, market, registered_user):
        """skills.sh 返回 500 → 502「市场暂不可用」"""
        market.rules[SS_HOST] = lambda req: httpx.Response(500, json={"message": "boom"})
        project = await _insert_project(db_session, registered_user["user_id"])
        resp = await _install(
            client, auth_headers, project.project_id,
            market=MARKET_SKILLSSH, ref="vercel/labs/find-skills",
        )
        assert resp.status_code == 502, resp.text
        assert "市场暂不可用" in resp.json()["message"]
        assert await _project_skill_rows(db_session, project.project_id) == []

    @pytest.mark.asyncio
    async def test_modelscope_timeout_502(self, client, auth_headers, db_session, market, registered_user):
        """modelscope 连接超时 → 502「市场暂不可用」(不 5xx 挂死)"""
        market.rules[MS_HOST] = _raise_connect_timeout
        project = await _insert_project(db_session, registered_user["user_id"])
        resp = await _install(client, auth_headers, project.project_id)
        assert resp.status_code == 502, resp.text
        assert "市场暂不可用" in resp.json()["message"]
        assert await _project_skill_rows(db_session, project.project_id) == []


# ---------------------------------------------------------------------------
# 6. 内容校验(frontmatter / 256KB):市场内容是 prompt 注入面,校验强制
# ---------------------------------------------------------------------------
class TestContentValidation:
    @pytest.mark.asyncio
    async def test_missing_name_400(self, client, auth_headers, db_session, market, registered_user):
        """frontmatter 缺 name → 400(17003)带原因;不入库"""
        market.rules[MS_HOST] = ms_skill_md("---\ndescription: 缺名字\n---\n\n正文\n")
        project = await _insert_project(db_session, registered_user["user_id"])
        resp = await _install(client, auth_headers, project.project_id)
        assert resp.status_code == 400, resp.text
        body = resp.json()
        assert body["code"] == 17003
        assert body["message"]
        assert await _project_skill_rows(db_session, project.project_id) == []

    @pytest.mark.asyncio
    async def test_missing_description_400(self, client, auth_headers, db_session, market, registered_user):
        """frontmatter 缺 description → 400(17003);不入库"""
        market.rules[MS_HOST] = ms_skill_md("---\nname: no-desc-skill\n---\n\n正文\n")
        project = await _insert_project(db_session, registered_user["user_id"])
        resp = await _install(client, auth_headers, project.project_id)
        assert resp.status_code == 400, resp.text
        assert resp.json()["code"] == 17003
        assert await _project_skill_rows(db_session, project.project_id) == []

    @pytest.mark.asyncio
    async def test_no_frontmatter_400(self, client, auth_headers, db_session, market, registered_user):
        """无 frontmatter 纯 markdown → 400(17003);不入库"""
        market.rules[MS_HOST] = ms_skill_md("没有 frontmatter 的普通 markdown")
        project = await _insert_project(db_session, registered_user["user_id"])
        resp = await _install(client, auth_headers, project.project_id)
        assert resp.status_code == 400, resp.text
        assert resp.json()["code"] == 17003
        assert await _project_skill_rows(db_session, project.project_id) == []

    @pytest.mark.asyncio
    async def test_non_kebab_name_400(self, client, auth_headers, db_session, market, registered_user):
        """name 非 kebab-case(Find Skills)→ 400(17003);不入库"""
        market.rules[MS_HOST] = ms_skill_md("---\nname: Find Skills\ndescription: x\n---\n\n正文\n")
        project = await _insert_project(db_session, registered_user["user_id"])
        resp = await _install(client, auth_headers, project.project_id)
        assert resp.status_code == 400, resp.text
        assert resp.json()["code"] == 17003
        assert await _project_skill_rows(db_session, project.project_id) == []

    @staticmethod
    def _md_with_body_bytes(total_bytes: int) -> str:
        """合法 frontmatter + 正文填充到指定总字节数(ASCII:字节数=字符数)"""
        base = "---\nname: big-skill\ndescription: 大内容边界\n---\n\n"
        assert total_bytes >= len(base)
        return base + "a" * (total_bytes - len(base))

    @pytest.mark.asyncio
    async def test_content_over_256kb_400(self, client, auth_headers, db_session, market, registered_user):
        """content > 256KB(262145B)→ 400;不入库"""
        market.rules[MS_HOST] = ms_skill_md(self._md_with_body_bytes(256 * 1024 + 1))
        project = await _insert_project(db_session, registered_user["user_id"])
        resp = await _install(client, auth_headers, project.project_id)
        assert resp.status_code == 400, resp.text
        assert resp.json()["code"] != 0
        assert await _project_skill_rows(db_session, project.project_id) == []

    @pytest.mark.asyncio
    async def test_content_exactly_256kb_ok(self, client, auth_headers, db_session, market, registered_user):
        """边界:content 恰好 256KB(契约 ≤256KB 允许)→ 200"""
        market.rules[MS_HOST] = ms_skill_md(self._md_with_body_bytes(256 * 1024))
        project = await _insert_project(db_session, registered_user["user_id"])
        resp = await _install(client, auth_headers, project.project_id)
        assert resp.status_code == 200, resp.text
        assert resp.json()["data"]["name"] == "big-skill"


# ---------------------------------------------------------------------------
# 7. 权限:viewer 403(鉴权/权限先行,不外呼、不入库)
# ---------------------------------------------------------------------------
class TestPermission:
    @pytest.mark.asyncio
    async def test_viewer_403(self, client, auth_headers, db_session, market, registered_user):
        """viewer 安装 → 403;权限先行,不触发市场外呼、不入库"""
        from tests.test_skills_mcp_api import _phone_via_register

        project = await _insert_project(db_session, registered_user["user_id"])
        phone = await _phone_via_register(client)
        await client.post(
            f"/api/projects/{project.project_id}/members",
            headers=auth_headers,
            json={"phone": phone, "role": "viewer"},
        )
        resp = await client.post("/api/auth/login", json={"phone": phone, "password": "Test1234"})
        assert resp.json()["code"] == 0
        viewer_headers = {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}

        market.rules[MS_HOST] = ms_skill_md(FIND_SKILLS_MD)
        resp = await _install(client, viewer_headers, project.project_id)
        assert resp.status_code == 403, resp.text
        assert market.calls == []
        assert await _project_skill_rows(db_session, project.project_id) == []
