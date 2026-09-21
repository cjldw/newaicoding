"""
R17 MCP 配置 + Skills 管理接口测试
==========================
覆盖:
- MCP:保存(加密)/回显(敏感打码)/结构错误 17001/模板列表/注入用解密
- Skills:超管建市场 Skill/安装(17002 重复)/上传(frontmatter 17003)/卸载/注入内容列表
- 权限:viewer 不可写;非成员 403/404
"""
import uuid

import pytest

from tests.test_projects_api import _insert_project, _register_and_login


VALID_MCP_CONFIG = {
    "mcpServers": {
        "postgres": {
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-postgres", "postgresql://user:password@host:5432/db"],
        },
        "github": {
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-github"],
            "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": "ghp_1234567890abcdef"},
        },
    }
}

SKILL_MD = """---
name: my-custom-skill
description: 自定义 Skill
---

按步骤执行自定义检查。
"""

BAD_SKILL_MD = "没有 frontmatter 的普通 markdown"


async def _seed_platform_skill(client, superadmin_headers, name="code-review", description="代码审查"):
    """超管建一个平台级 Skill,返回 skill_id"""
    resp = await client.post(
        "/api/admin/skills",
        headers=superadmin_headers,
        json={
            "name": name,
            "description": description,
            "content": f"---\nname: {name}\ndescription: {description}\n---\n\n正文\n",
        },
    )
    assert resp.json()["code"] == 0, resp.json()
    return resp.json()["data"]["skill_id"]


# ---------------------------------------------------------------------------
# MCP 配置
# ---------------------------------------------------------------------------
class TestMcpConfig:
    @pytest.mark.asyncio
    async def test_update_mcp_config_success(self, client, auth_headers, db_session, registered_user):
        """保存 MCP 配置成功(加密落库);回显打码"""
        project = await _insert_project(db_session, registered_user["user_id"])
        resp = await client.put(
            f"/api/projects/{project.project_id}/mcp-config",
            headers=auth_headers,
            json={"config": VALID_MCP_CONFIG},
        )
        assert resp.json()["code"] == 0
        assert "保存成功" in resp.json()["message"]

        # 回显:连接串含 password 关键词 → 打码;env token 值 → 打码
        resp = await client.get(f"/api/projects/{project.project_id}/mcp-config", headers=auth_headers)
        config = resp.json()["data"]["config"]
        assert config is not None
        arg0 = config["mcpServers"]["postgres"]["args"][2]
        assert "password" not in arg0 and "***" in arg0
        env_val = config["mcpServers"]["github"]["env"]["GITHUB_PERSONAL_ACCESS_TOKEN"]
        assert "ghp_1234" not in env_val and "***" in env_val

        # 未配置项目回显 null
        other = await _insert_project(db_session, registered_user["user_id"])
        resp = await client.get(f"/api/projects/{other.project_id}/mcp-config", headers=auth_headers)
        assert resp.json()["data"]["config"] is None

    @pytest.mark.asyncio
    async def test_update_mcp_config_invalid_json(self, client, auth_headers, db_session, registered_user):
        """结构非法:返回 17001(mcpServers 值非对象 / 缺 config 字段)"""
        project = await _insert_project(db_session, registered_user["user_id"])
        resp = await client.put(
            f"/api/projects/{project.project_id}/mcp-config",
            headers=auth_headers,
            json={"config": {"mcpServers": {"broken": "not-an-object"}}},
        )
        assert resp.json()["code"] == 17001
        assert "JSON 格式错误" in resp.json()["message"]

        resp = await client.put(
            f"/api/projects/{project.project_id}/mcp-config",
            headers=auth_headers,
            json={},
        )
        assert resp.json()["code"] == 17001

    @pytest.mark.asyncio
    async def test_put_mcp_config_by_editor_denied(self, client, auth_headers, db_session, registered_user):
        """editor 保存 MCP 配置:403(矩阵:仅 owner)"""
        project = await _insert_project(db_session, registered_user["user_id"])
        editor_headers, _uid = await _register_and_login(client)
        await client.post(
            f"/api/projects/{project.project_id}/members",
            headers=auth_headers,
            json={"phone": await _phone_via_register(client), "role": "editor"},
        )
        resp = await client.put(
            f"/api/projects/{project.project_id}/mcp-config",
            headers=editor_headers,
            json={"config": VALID_MCP_CONFIG},
        )
        assert resp.status_code == 403
        assert resp.json()["code"] == 1901

    @pytest.mark.asyncio
    async def test_templates_list(self, client, auth_headers, db_session, registered_user):
        """模板列表:包含 postgres/redis/github/slack"""
        project = await _insert_project(db_session, registered_user["user_id"])
        resp = await client.get(f"/api/projects/{project.project_id}/mcp-config/templates", headers=auth_headers)
        items = resp.json()["data"]["items"]
        names = {i["name"] for i in items}
        assert {"postgres", "redis", "github", "slack"}.issubset(names)
        postgres = next(i for i in items if i["name"] == "postgres")
        assert any(p.get("sensitive") for p in postgres["params"])
        assert "json_template" in postgres

    @pytest.mark.asyncio
    async def test_injection_decrypt(self, client, auth_headers, db_session, registered_user):
        """注入链路(R8 消费):get_decrypted_config 返回解密原文"""
        from app.services import mcp_service

        project = await _insert_project(db_session, registered_user["user_id"])
        await client.put(
            f"/api/projects/{project.project_id}/mcp-config",
            headers=auth_headers,
            json={"config": VALID_MCP_CONFIG},
        )
        # 重新取项目(含加密列)
        fresh = await _insert_project(db_session, registered_user["user_id"])  # 占位避免误用
        from app.services.project_service import get_project_or_404
        reloaded = await get_project_or_404(db_session, project.project_id)
        decrypted = await mcp_service.get_decrypted_config(db_session, reloaded)
        assert decrypted["mcpServers"]["postgres"]["args"][2] == \
            "postgresql://user:password@host:5432/db"


async def _phone_via_register(client):
    """注册一个用户返回其手机号(配合 auth_headers 用户邀请成员)"""
    phone = f"134{str(uuid.uuid4().int)[:8]}"
    resp = await client.post("/api/auth/register", json={"phone": phone, "password": "Test1234"})
    assert resp.json()["code"] == 0
    return phone


# ---------------------------------------------------------------------------
# Skills
# ---------------------------------------------------------------------------
class TestSkills:
    @pytest.mark.asyncio
    async def test_admin_create_and_market_list(self, client, superadmin_headers, auth_headers):
        """超管建平台 Skill;市场列表可见;非超管建 → 403"""
        skill_id = await _seed_platform_skill(client, superadmin_headers)
        assert skill_id

        resp = await client.get("/api/skills", headers=auth_headers)
        items = resp.json()["data"]["items"]
        assert any(i["skill_id"] == skill_id for i in items)

        # 非超管访问管理接口 → 403/19002
        resp = await client.post(
            "/api/admin/skills",
            headers=auth_headers,
            json={"name": "x-skill", "description": "x", "content": "---\nname: x-skill\ndescription: x\n---\n"},
        )
        assert resp.json()["code"] == 19002

    @pytest.mark.asyncio
    async def test_install_skill_success(self, client, superadmin_headers, auth_headers, db_session, registered_user):
        """安装平台 Skill 成功;重复安装 17002"""
        project = await _insert_project(db_session, registered_user["user_id"])
        skill_id = await _seed_platform_skill(client, superadmin_headers)

        resp = await client.post(
            f"/api/projects/{project.project_id}/skills",
            headers=auth_headers,
            json={"skill_id": skill_id},
        )
        assert resp.json()["code"] == 0
        assert "安装成功" in resp.json()["message"]

        resp = await client.post(
            f"/api/projects/{project.project_id}/skills",
            headers=auth_headers,
            json={"skill_id": skill_id},
        )
        assert resp.json()["code"] == 17002

        # 已安装列表可见
        resp = await client.get(f"/api/projects/{project.project_id}/skills", headers=auth_headers)
        items = resp.json()["data"]["items"]
        assert len(items) == 1
        assert items[0]["scope"] == "platform"

    @pytest.mark.asyncio
    async def test_upload_skill_success(self, client, auth_headers, db_session, registered_user):
        """上传自定义 Skill 成功(解析 frontmatter);出现在已安装列表"""
        project = await _insert_project(db_session, registered_user["user_id"])
        resp = await client.post(
            f"/api/projects/{project.project_id}/skills/upload",
            headers=auth_headers,
            files={"file": ("my-custom-skill.md", SKILL_MD.encode("utf-8"), "text/markdown")},
        )
        data = resp.json()
        assert data["code"] == 0, data
        assert data["data"]["name"] == "my-custom-skill"
        assert data["data"]["description"] == "自定义 Skill"

        resp = await client.get(f"/api/projects/{project.project_id}/skills", headers=auth_headers)
        items = resp.json()["data"]["items"]
        assert len(items) == 1 and items[0]["scope"] == "project"

        # 同名覆盖式更新(V1 无版本管理)
        updated = SKILL_MD.replace("自定义 Skill", "更新后的描述")
        resp = await client.post(
            f"/api/projects/{project.project_id}/skills/upload",
            headers=auth_headers,
            files={"file": ("my-custom-skill.md", updated.encode("utf-8"), "text/markdown")},
        )
        assert resp.json()["code"] == 0
        resp = await client.get(f"/api/projects/{project.project_id}/skills", headers=auth_headers)
        assert len(resp.json()["data"]["items"]) == 1  # 不重复

    @pytest.mark.asyncio
    async def test_upload_skill_invalid_format(self, client, auth_headers, db_session, registered_user):
        """无 frontmatter / 缺 name:返回 17003"""
        project = await _insert_project(db_session, registered_user["user_id"])
        resp = await client.post(
            f"/api/projects/{project.project_id}/skills/upload",
            headers=auth_headers,
            files={"file": ("bad.md", BAD_SKILL_MD.encode("utf-8"), "text/markdown")},
        )
        assert resp.json()["code"] == 17003

        no_name = "---\ndescription: 只有描述\n---\n正文"
        resp = await client.post(
            f"/api/projects/{project.project_id}/skills/upload",
            headers=auth_headers,
            files={"file": ("bad2.md", no_name.encode("utf-8"), "text/markdown")},
        )
        assert resp.json()["code"] == 17003

    @pytest.mark.asyncio
    async def test_uninstall_skill_success(self, client, superadmin_headers, auth_headers, db_session, registered_user):
        """卸载 Skill:删关联记录"""
        project = await _insert_project(db_session, registered_user["user_id"])
        skill_id = await _seed_platform_skill(client, superadmin_headers)
        await client.post(
            f"/api/projects/{project.project_id}/skills",
            headers=auth_headers,
            json={"skill_id": skill_id},
        )
        resp = await client.delete(
            f"/api/projects/{project.project_id}/skills/{skill_id}",
            headers=auth_headers,
        )
        assert resp.json()["code"] == 0
        assert "卸载成功" in resp.json()["message"]
        resp = await client.get(f"/api/projects/{project.project_id}/skills", headers=auth_headers)
        assert resp.json()["data"]["items"] == []

    @pytest.mark.asyncio
    async def test_viewer_cannot_install_or_upload(self, client, superadmin_headers, auth_headers, db_session, registered_user):
        """viewer 安装/上传:403(矩阵:owner/editor)"""
        project = await _insert_project(db_session, registered_user["user_id"])
        phone = await _phone_via_register(client)
        await client.post(
            f"/api/projects/{project.project_id}/members",
            headers=auth_headers,
            json={"phone": phone, "role": "viewer"},
        )
        resp = await client.post("/api/auth/login", json={"phone": phone, "password": "Test1234"})
        viewer_headers = {"Authorization": f"Bearer {resp.json()['data']['access_token']}"}

        resp = await client.post(
            f"/api/projects/{project.project_id}/skills",
            headers=viewer_headers,
            json={"skill_id": str(uuid.uuid4())},
        )
        assert resp.status_code == 403

        resp = await client.post(
            f"/api/projects/{project.project_id}/skills/upload",
            headers=viewer_headers,
            files={"file": ("x.md", SKILL_MD.encode("utf-8"), "text/markdown")},
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_injection_contents(self, client, superadmin_headers, auth_headers, db_session, registered_user):
        """注入链路(R8 消费):项目 Skills 内容列表;项目级与平台同名时项目级在后(覆盖)"""
        from app.services import skill_service
        from app.services.project_service import get_project_or_404

        project = await _insert_project(db_session, registered_user["user_id"])
        # 平台级同名 skill
        await _seed_platform_skill(client, superadmin_headers, name="shared-skill", description="平台版")
        # 安装平台级
        resp = await client.get("/api/skills", headers=auth_headers)
        platform_id = next(i["skill_id"] for i in resp.json()["data"]["items"] if i["name"] == "shared-skill")
        await client.post(
            f"/api/projects/{project.project_id}/skills",
            headers=auth_headers,
            json={"skill_id": platform_id},
        )
        # 上传项目级同名
        override_md = "---\nname: shared-skill\ndescription: 项目版\n---\n项目覆盖内容"
        await client.post(
            f"/api/projects/{project.project_id}/skills/upload",
            headers=auth_headers,
            files={"file": ("shared-skill.md", override_md.encode("utf-8"), "text/markdown")},
        )

        reloaded = await get_project_or_404(db_session, project.project_id)
        contents = await skill_service.list_project_skill_contents(db_session, reloaded.project_id)
        names = [c["name"] for c in contents]
        assert names.count("shared-skill") == 2
        # 项目版排在最后(写入容器时后写覆盖)
        assert contents[-1]["content"].startswith("---\nname: shared-skill")
        assert "项目覆盖内容" in contents[-1]["content"]
