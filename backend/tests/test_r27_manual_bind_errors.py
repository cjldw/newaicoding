"""
R27 项目创建 manual 绑定修复与错误细分 — Red 阶段失败测试
==========================================================
覆盖 R27 完成判据 #1/#2/#3/#6(见 DEVPLAN/R27.md):
- 判据 #1 权限判定:max(project_access, group_access) >= Maintainer(40),四场景
  (仅 group=40 通过 / project=30+group=40 通过 / 均<40→2013 / permissions 全 null→2013)
- 判据 #2 五类错误细分:404→2011 / 403(含401 归并)→2012 / 网络异常→2014 /
  URL 解析失败→2002 / 200 但权限低→2013,message 按「枚举与字典映射」表逐字断言
- 判据 #3 add_repo 同口径:POST /api/projects/{id}/repos 走相同错误码族
- 判据 #6 message 不泄露敏感值:五类 message 无 bot token / 用户粘贴 path / 内部 host

文案来源:R27.md「枚举与字典映射」表文案列(逐字拷贝)。
GitLab mock 注入:沿用 conftest 现有方案 —— `with httpx.MockTransport(handler):` 进入
上下文时由 conftest autouse fixture 注入 gitlab_service._test_transport
(conftest.py:395-420),不自建注入机制。平台 GitLab 配置沿用既有测试的直插方式。
"""
import uuid

import httpx
import pytest

# ---------------------------------------------------------------------------
# 常量:平台 GitLab 配置(与 _seed_gitlab_settings 一致)+ R27 五类文案(逐字)
# ---------------------------------------------------------------------------
PLATFORM_GITLAB_URL = "https://gitlab.example.com"

# R27「枚举与字典映射」表文案列 —— 一字不差({gitlab_url} 按平台配置插值,仅 2011 使用)
MSG_2002_URL_INVALID = "仓库地址格式无效,请粘贴形如 http://{host}/{group}/{repo}.git 的地址"
MSG_2011_REPO_NOT_FOUND = (
    f"仓库不存在,请检查 group/repo 名称是否正确(仅支持平台 GitLab:{PLATFORM_GITLAB_URL})"
)
MSG_2012_REPO_FORBIDDEN = "平台 bot 无权访问该仓库,请联系管理员将平台 bot 加入仓库所在 group"
MSG_2013_PERM_LOW = "平台 bot 权限不足(需 Maintainer 及以上),请联系管理员调整"
MSG_2014_UNREACHABLE = "GitLab 服务连接失败,请稍后重试"

# 敏感值哨兵(判据 #6):这些值出现在 message 中即为泄露
BOT_TOKEN_SENTINEL = "glpat-test-token"            # _seed_gitlab_settings 写入的 bot token 明文
PASTE_HOST_SENTINEL = "10.0.0.42"                  # 用户粘贴 URL 的内部 host(非平台 gitlab_url)
PASTE_PATH_SENTINEL = "secret-group/secret-repo"   # 用户粘贴 URL 的内部 path

REPO_PATH_SENTINEL_GIT = f"http://{PASTE_HOST_SENTINEL}/{PASTE_PATH_SENTINEL}.git"


# ---------------------------------------------------------------------------
# 测试辅助:平台配置直插 + mock handler 工厂(沿用既有测试的写法)
# ---------------------------------------------------------------------------
async def _seed_gitlab_settings(db_session):
    """直插平台 GitLab 配置(gitlab_url / bot token(加密) / bot group_id)。
    不先 seed 则服务层 2001 拦截,走不到本点覆盖的错误细分逻辑。"""
    from app.core.encryption import encrypt_token
    from app.models.project import PlatformSetting

    db_session.add(PlatformSetting(key="gitlab_url", value=PLATFORM_GITLAB_URL, updated_by="test"))
    db_session.add(PlatformSetting(
        key="gitlab_bot_token",
        value={"__encrypted": encrypt_token(BOT_TOKEN_SENTINEL)},
        updated_by="test",
    ))
    db_session.add(PlatformSetting(key="gitlab_bot_group_id", value=1, updated_by="test"))
    await db_session.flush()


async def _insert_project(db_session, owner_id):
    """直插一条项目记录(add_repo 用例的前置项目),返回 Project ORM 对象"""
    from app.models.project import Project

    p = Project(
        name=f"R27 项目 {uuid.uuid4().hex[:6]}",
        slug=f"r27-{uuid.uuid4().hex[:8]}",
        owner_id=owner_id,
        status="active",
        visibility="private",
    )
    db_session.add(p)
    await db_session.flush()
    return p


def _permissions(project_level=None, group_level=None):
    """构造 GitLab project JSON 的 permissions 字段(两级各自可为 null)"""
    return {
        "project_access": {"access_level": project_level} if project_level is not None else None,
        "group_access": {"access_level": group_level} if group_level is not None else None,
    }


def _repo_json(permissions=None, include_permissions=True):
    """构造 GET /api/v4/projects/{encoded path} 的 200 响应体"""
    body = {
        "id": 789,
        "name": PASTE_PATH_SENTINEL.split("/")[1],
        "path_with_namespace": PASTE_PATH_SENTINEL,
        "http_url_to_repo": f"{REPO_PATH_SENTINEL_GIT}",
        "default_branch": "master",
    }
    if include_permissions:
        body["permissions"] = permissions if permissions is not None else _permissions()
    return body


def mock_get_repo(status_code=200, repo_payload=None):
    """模拟 GET /api/v4/projects/{url-encoded path}(bot_get_repo_by_path 查仓库);
    其余 GitLab 请求(如 /users、/members)一律 404——非关键步骤,流程自行降级跳过"""
    async def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and "/api/v4/projects/" in str(request.url):
            if status_code == 200:
                return httpx.Response(
                    status_code=200,
                    json=repo_payload if repo_payload is not None else _repo_json(),
                )
            return httpx.Response(status_code=status_code, json={"message": "error"})
        return httpx.Response(status_code=404)
    return handler


def mock_network_error():
    """模拟 GitLab 网络异常(ConnectError ∈ httpx.HTTPError 家族)"""
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")
    return handler


async def _create_manual(client, headers, repo_url):
    """POST /api/projects(manual 绑定主仓库)"""
    return await client.post(
        "/api/projects",
        headers=headers,
        json={
            "name": f"R27 项目 {uuid.uuid4().hex[:6]}",
            "visibility": "private",
            "main_repo": {"bind_type": "manual", "gitlab_repo_url": repo_url},
        },
    )


async def _add_repo(client, headers, project_id, repo_url):
    """POST /api/projects/{id}/repos(追加绑定仓库)"""
    return await client.post(
        f"/api/projects/{project_id}/repos",
        headers=headers,
        json={"role": "test", "gitlab_repo_url": repo_url},
    )


# ---------------------------------------------------------------------------
# 判据 #1:max(project_access, group_access) 权限判定四场景
# ---------------------------------------------------------------------------
class TestPermMaxProjectGroupAccess:
    """bot access_level 取 max(project_access, group_access),≥ 40 通过"""

    @pytest.mark.asyncio
    async def test_group_access_40_only_passes(self, client, auth_headers, db_session):
        """仅 group_access=40(project_access null)→ 创建成功(本点修复的缺陷场景)"""
        await _seed_gitlab_settings(db_session)
        payload = _repo_json(_permissions(project_level=None, group_level=40))
        with httpx.MockTransport(mock_get_repo(200, payload)):
            resp = await _create_manual(client, auth_headers, REPO_PATH_SENTINEL_GIT)
        data = resp.json()
        assert data["code"] == 0, (
            f"仅 group 继承 Maintainer 应创建成功,实际 code={data['code']} message={data['message']}"
        )
        assert data["data"]["main_repo"]["gitlab_repo_id"] == 789
        # 原断言 main_repo.gitlab_bind_type 与 R27 契约「成功结构不变」冲突(响应 main_repo
        # 仅 repo_id/gitlab_repo_url/gitlab_repo_id 三键),以分片为准;
        # 语义等价改查落库记录(db_session 与 app 经 dependency_overrides 共享同一事务)
        from sqlalchemy import select

        from app.models.project import ProjectRepo

        repo_row = (
            await db_session.execute(
                select(ProjectRepo).where(ProjectRepo.gitlab_repo_id == 789)
            )
        ).scalar_one()
        assert repo_row.gitlab_bind_type == "manual"

    @pytest.mark.asyncio
    async def test_project_30_group_40_passes(self, client, auth_headers, db_session):
        """project=30(Developer)+ group=40(Maintainer)→ max=40 创建成功"""
        await _seed_gitlab_settings(db_session)
        payload = _repo_json(_permissions(project_level=30, group_level=40))
        with httpx.MockTransport(mock_get_repo(200, payload)):
            resp = await _create_manual(client, auth_headers, REPO_PATH_SENTINEL_GIT)
        data = resp.json()
        assert data["code"] == 0, (
            f"max(30,40)=40 应创建成功,实际 code={data['code']} message={data['message']}"
        )

    @pytest.mark.asyncio
    async def test_both_below_40_returns_2013(self, client, auth_headers, db_session):
        """project=30 + group=30 → max=30 <40 → 2013 + 权限不足文案(逐字)"""
        await _seed_gitlab_settings(db_session)
        payload = _repo_json(_permissions(project_level=30, group_level=30))
        with httpx.MockTransport(mock_get_repo(200, payload)):
            resp = await _create_manual(client, auth_headers, REPO_PATH_SENTINEL_GIT)
        data = resp.json()
        assert data["code"] == 2013, f"max(30,30)<40 应返回 2013,实际 code={data['code']}"
        assert data["message"] == MSG_2013_PERM_LOW

    @pytest.mark.asyncio
    async def test_permissions_all_null_returns_2013(self, client, auth_headers, db_session):
        """permissions 两级全 null → 2013 + 权限不足文案(逐字)"""
        await _seed_gitlab_settings(db_session)
        payload = _repo_json(_permissions(project_level=None, group_level=None))
        with httpx.MockTransport(mock_get_repo(200, payload)):
            resp = await _create_manual(client, auth_headers, REPO_PATH_SENTINEL_GIT)
        data = resp.json()
        assert data["code"] == 2013, f"permissions 全 null 应返回 2013,实际 code={data['code']}"
        assert data["message"] == MSG_2013_PERM_LOW

    @pytest.mark.asyncio
    async def test_permissions_key_absent_returns_2013(self, client, auth_headers, db_session):
        """响应体无 permissions 键(整体缺省)→ 2013(实现要点:permissions 可能为 null)"""
        await _seed_gitlab_settings(db_session)
        payload = _repo_json(include_permissions=False)
        with httpx.MockTransport(mock_get_repo(200, payload)):
            resp = await _create_manual(client, auth_headers, REPO_PATH_SENTINEL_GIT)
        data = resp.json()
        assert data["code"] == 2013, f"permissions 缺省应返回 2013,实际 code={data['code']}"
        assert data["message"] == MSG_2013_PERM_LOW


# ---------------------------------------------------------------------------
# 判据 #2:五类错误细分(POST /api/projects manual 分支,message 逐字断言)
# ---------------------------------------------------------------------------
class TestCreateManualErrorRefinement:
    """bot_get_repo_by_path 按状态码/异常细分,project_service 不再折叠 2002"""

    @pytest.mark.asyncio
    async def test_repo_404_returns_2011(self, client, auth_headers, db_session):
        """GitLab 查仓库 404 → 2011,文案含平台 GitLab 地址(逐字)"""
        await _seed_gitlab_settings(db_session)
        with httpx.MockTransport(mock_get_repo(404)):
            resp = await _create_manual(client, auth_headers, REPO_PATH_SENTINEL_GIT)
        data = resp.json()
        assert data["code"] == 2011, f"404 应返回 2011,实际 code={data['code']}"
        assert data["message"] == MSG_2011_REPO_NOT_FOUND

    @pytest.mark.asyncio
    async def test_repo_403_returns_2012(self, client, auth_headers, db_session):
        """GitLab 查仓库 403 → 2012(bot 无访问权限,逐字)"""
        await _seed_gitlab_settings(db_session)
        with httpx.MockTransport(mock_get_repo(403)):
            resp = await _create_manual(client, auth_headers, REPO_PATH_SENTINEL_GIT)
        data = resp.json()
        assert data["code"] == 2012, f"403 应返回 2012,实际 code={data['code']}"
        assert data["message"] == MSG_2012_REPO_FORBIDDEN

    @pytest.mark.asyncio
    async def test_repo_401_returns_2012(self, client, auth_headers, db_session):
        """GitLab 查仓库 401 → 与 403 归并为 2012(防枚举,同一文案)"""
        await _seed_gitlab_settings(db_session)
        with httpx.MockTransport(mock_get_repo(401)):
            resp = await _create_manual(client, auth_headers, REPO_PATH_SENTINEL_GIT)
        data = resp.json()
        assert data["code"] == 2012, f"401 应归并 2012,实际 code={data['code']}"
        assert data["message"] == MSG_2012_REPO_FORBIDDEN

    @pytest.mark.asyncio
    async def test_network_error_returns_2014(self, client, auth_headers, db_session):
        """httpx 网络异常(ConnectError)→ 2014,不再与 URL 非法同码(逐字)"""
        await _seed_gitlab_settings(db_session)
        with httpx.MockTransport(mock_network_error()):
            resp = await _create_manual(client, auth_headers, REPO_PATH_SENTINEL_GIT)
        data = resp.json()
        assert data["code"] == 2014, f"网络异常应返回 2014,实际 code={data['code']}"
        assert data["message"] == MSG_2014_UNREACHABLE

    @pytest.mark.asyncio
    async def test_url_parse_failure_returns_2002(self, client, auth_headers, db_session):
        """parse_repo_path 解析失败(host 无 path)→ 2002 语义收窄:URL 格式非法(逐字)"""
        await _seed_gitlab_settings(db_session)
        with httpx.MockTransport(mock_get_repo(200)):
            resp = await _create_manual(client, auth_headers, "https://gitlab.example.com")
        data = resp.json()
        assert data["code"] == 2002, f"URL 解析失败应返回 2002,实际 code={data['code']}"
        assert data["message"] == MSG_2002_URL_INVALID

    @pytest.mark.asyncio
    async def test_low_permission_returns_2013(self, client, auth_headers, db_session):
        """200 但仅 project_access=30(<40)→ 2013,不再折叠 2002(逐字)"""
        await _seed_gitlab_settings(db_session)
        payload = _repo_json(_permissions(project_level=30, group_level=None))
        with httpx.MockTransport(mock_get_repo(200, payload)):
            resp = await _create_manual(client, auth_headers, REPO_PATH_SENTINEL_GIT)
        data = resp.json()
        assert data["code"] == 2013, f"权限低于 Maintainer 应返回 2013,实际 code={data['code']}"
        assert data["message"] == MSG_2013_PERM_LOW


# ---------------------------------------------------------------------------
# 判据 #3:add_repo 同口径(POST /api/projects/{id}/repos)
# ---------------------------------------------------------------------------
class TestAddRepoSameErrorFamily:
    """追加绑定仓库走同一套判定与错误码"""

    @pytest.mark.asyncio
    async def test_add_repo_404_returns_2011(self, client, auth_headers, db_session, registered_user):
        """追加绑定:GitLab 查仓库 404 → 2011(逐字)"""
        await _seed_gitlab_settings(db_session)
        project = await _insert_project(db_session, registered_user["user_id"])
        with httpx.MockTransport(mock_get_repo(404)):
            resp = await _add_repo(client, auth_headers, project.project_id, REPO_PATH_SENTINEL_GIT)
        data = resp.json()
        assert data["code"] == 2011, f"add_repo 404 应返回 2011,实际 code={data['code']}"
        assert data["message"] == MSG_2011_REPO_NOT_FOUND

    @pytest.mark.asyncio
    async def test_add_repo_low_permission_returns_2013(self, client, auth_headers, db_session, registered_user):
        """追加绑定:200 但权限低(30)→ 2013(逐字)"""
        await _seed_gitlab_settings(db_session)
        project = await _insert_project(db_session, registered_user["user_id"])
        payload = _repo_json(_permissions(project_level=30, group_level=None))
        with httpx.MockTransport(mock_get_repo(200, payload)):
            resp = await _add_repo(client, auth_headers, project.project_id, REPO_PATH_SENTINEL_GIT)
        data = resp.json()
        assert data["code"] == 2013, f"add_repo 权限低应返回 2013,实际 code={data['code']}"
        assert data["message"] == MSG_2013_PERM_LOW


# ---------------------------------------------------------------------------
# 判据 #6:message 不泄露敏感值(bot token / 用户粘贴 path / 内部 host)
# ---------------------------------------------------------------------------
# 五类场景统一粘贴含哨兵值的 URL,断言 message 中不出现任何哨兵
_LEAK_CASES = [
    pytest.param(2011, mock_get_repo(404), REPO_PATH_SENTINEL_GIT,
                 id="2011-repo-not-found"),
    pytest.param(2012, mock_get_repo(403), REPO_PATH_SENTINEL_GIT,
                 id="2012-repo-forbidden"),
    pytest.param(2014, mock_network_error(), REPO_PATH_SENTINEL_GIT,
                 id="2014-unreachable"),
    # 无 scheme/无 host 点号 → parse_repo_path 失败(哨兵 path 本身不合法,触发 2002)
    pytest.param(2002, mock_get_repo(200), PASTE_PATH_SENTINEL,
                 id="2002-url-invalid"),
    pytest.param(2013, mock_get_repo(200, _repo_json(_permissions(30, None))), REPO_PATH_SENTINEL_GIT,
                 id="2013-perm-low"),
]


class TestMessageNoSensitiveLeak:
    """五类 message 均不含 bot token / 用户粘贴的 path / 用户粘贴的内部 host"""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("expected_code,handler,pasted_url", _LEAK_CASES)
    async def test_message_hides_token_and_pasted_values(
        self, client, auth_headers, db_session, expected_code, handler, pasted_url,
    ):
        await _seed_gitlab_settings(db_session)
        with httpx.MockTransport(handler):
            resp = await _create_manual(client, auth_headers, pasted_url)
        data = resp.json()
        assert data["code"] == expected_code, (
            f"应返回 {expected_code},实际 code={data['code']} message={data['message']}"
        )
        message = data["message"]
        assert BOT_TOKEN_SENTINEL not in message, "message 泄露 bot token"
        assert PASTE_PATH_SENTINEL not in message, "message 泄露用户粘贴的 repo path"
        assert PASTE_HOST_SENTINEL not in message, "message 泄露用户粘贴的内部 host"
