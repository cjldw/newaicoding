"""GitLab 服务 - token 验证、用户信息获取"""

import logging
from typing import Optional

import httpx

from app.core.response import BizError, ErrCode

logger = logging.getLogger(__name__)

# GitLab API 基础 URL（默认 gitlab.com，可配置）
GITLAB_API_BASE = "https://gitlab.com/api/v4"

# ---------------------------------------------------------------------------
# 测试用 mock client 注入点
# ---------------------------------------------------------------------------
# 当 conftest.py 中的 autouse fixture 检测到 `with httpx.MockTransport(...)` 时，
# 会将 MockTransport 实例设置到此处，使 gitlab_service 的 HTTP 请求走 mock。
_test_transport: Optional[httpx.MockTransport] = None


def set_test_transport(transport: Optional[httpx.MockTransport]) -> None:
    """供 conftest fixture 调用，设置/清除测试用 mock transport。"""
    global _test_transport
    _test_transport = transport


def _get_client() -> httpx.AsyncClient:
    """
    获取 httpx.AsyncClient：
    - 测试环境（_test_transport 非 None）：使用 mock transport
    - 正常环境：创建普通 AsyncClient
    """
    if _test_transport is not None:
        return httpx.AsyncClient(transport=_test_transport, timeout=15.0)
    return httpx.AsyncClient(timeout=15.0, verify=False)


# ---------------------------------------------------------------------------
# 必要的 scope 要求（AND 逻辑：必须同时具备）
# ---------------------------------------------------------------------------
REQUIRED_SCOPES = ["read_repository", "write_repository"]


class GitlabService:
    """GitLab 集成服务"""

    # -------------------------------------------------------------------
    # 验证 GitLab token 并获取用户信息
    # -------------------------------------------------------------------
    @staticmethod
    async def verify_token(gitlab_token: str) -> dict:
        """
        调用 GitLab API 验证 personal access token:
        - GET /api/v4/user → 获取用户名 + 从 X-Token-Scopes 响应头获取 scope
        返回 {"username": str, "scopes": list[str]}
        失败时抛出 BizError
        """
        headers = {"Authorization": f"Bearer {gitlab_token}"}

        client = _get_client()
        try:
            # 获取用户信息（同时从响应头提取 scope）
            try:
                resp = await client.get(
                    f"{GITLAB_API_BASE}/user",
                    headers=headers,
                )
            except httpx.HTTPError as e:
                logger.warning("GitLab API 请求失败: %s", e)
                raise BizError(ErrCode.GITLAB_TOKEN_INVALID, "GitLab 服务连接失败")

            if resp.status_code == 401:
                raise BizError(ErrCode.GITLAB_TOKEN_INVALID, "GitLab token 无效或已过期")
            if resp.status_code != 200:
                logger.warning("GitLab /user 返回 %s: %s", resp.status_code, resp.text[:200])
                raise BizError(ErrCode.GITLAB_TOKEN_INVALID, "GitLab token 验证失败")

            user_data = resp.json()
            username = user_data.get("username", "")

            # 从 X-Token-Scopes 响应头获取 scope 列表
            scopes_header = resp.headers.get("X-Token-Scopes", "")
            scopes = scopes_header.split() if scopes_header else []

        finally:
            await client.aclose()

        return {"username": username, "scopes": scopes}

    @staticmethod
    def check_required_scopes(scopes: list[str]) -> bool:
        """
        检查 token 是否包含所需 scope（AND 逻辑）。
        R1 要求: 必须同时具备 read_repository 和 write_repository。
        """
        if not scopes:
            return False
        return all(s in scopes for s in REQUIRED_SCOPES)


# ---------------------------------------------------------------------------
# R2 平台 bot 操作(bot token 来自 platform_settings,读取处实时查表)
# ---------------------------------------------------------------------------
# 访问级别常量(GitLab): 30=Developer 40=Maintainer
ACCESS_LEVEL_DEVELOPER = 30
ACCESS_LEVEL_MAINTAINER = 40


def _bot_headers(bot_token: str) -> dict:
    """平台 bot token 请求头"""
    return {"Authorization": f"Bearer {bot_token}"}


async def bot_create_repo(
    bot_token: str,
    gitlab_url: str,
    name: str,
    namespace_id: int,
    default_branch: str,
    visibility: str = "private",
) -> dict:
    """
    平台 bot 建仓库:POST /api/v4/projects
    返回 GitLab project JSON(id/http_url_to_repo/...);非 2xx 抛 BizError(2002)。
    """
    client = _get_client()
    try:
        resp = await client.post(
            f"{gitlab_url.rstrip('/')}/api/v4/projects",
            headers=_bot_headers(bot_token),
            json={
                "name": name,
                "path": name,
                "namespace_id": namespace_id,
                "default_branch": default_branch,
                "visibility": visibility,
            },
        )
    except httpx.HTTPError as e:
        logger.warning("GitLab 建仓请求失败: %s", e)
        raise BizError(ErrCode.REPO_URL_INVALID, "GitLab 服务连接失败")
    finally:
        await client.aclose()

    if resp.status_code not in (200, 201):
        logger.warning("GitLab 建仓失败 %s: %s", resp.status_code, resp.text[:200])
        raise BizError(ErrCode.REPO_URL_INVALID, "仓库创建失败(GitLab 返回错误)")
    return resp.json()


async def bot_get_repo_by_path(
    bot_token: str,
    gitlab_url: str,
    repo_path: str,
) -> dict:
    """
    平台 bot 按 path 查仓库:GET /api/v4/projects/{url-encoded path}
    (GitLab 支持 GET /projects/{encoded path_with_namespace},无需先搜索出 id)
    返回 project JSON;404/无权限/网络错误抛 BizError(2002)。
    """
    from urllib.parse import quote

    encoded = quote(repo_path, safe="")
    client = _get_client()
    try:
        resp = await client.get(
            f"{gitlab_url.rstrip('/')}/api/v4/projects/{encoded}",
            headers=_bot_headers(bot_token),
        )
    except httpx.HTTPError as e:
        logger.warning("GitLab 查询仓库失败: %s", e)
        raise BizError(ErrCode.REPO_URL_INVALID, "GitLab 服务连接失败")
    finally:
        await client.aclose()

    if resp.status_code != 200:
        logger.info("GitLab 查询仓库 %s 返回 %s", repo_path, resp.status_code)
        raise BizError(ErrCode.REPO_URL_INVALID, "仓库 URL 无效或无权限")
    return resp.json()


def bot_check_repo_permission(project_json: dict, min_level: int = ACCESS_LEVEL_MAINTAINER) -> bool:
    """
    检查 bot 对仓库的权限:permissions.project_access.access_level >= min_level
    (read+write+merge 要求至少 Maintainer=40)。
    """
    perms = (project_json.get("permissions") or {}).get("project_access") or {}
    level = perms.get("access_level") or 0
    return level >= min_level


async def bot_add_member(
    bot_token: str,
    gitlab_url: str,
    repo_id: int,
    gitlab_user_id: int,
    access_level: int,
) -> None:
    """
    平台 bot 加成员:POST /api/v4/projects/{id}/members
    失败不抛异常(非关键步骤,只记 warning,后续可补偿重试)。
    """
    client = _get_client()
    try:
        resp = await client.post(
            f"{gitlab_url.rstrip('/')}/api/v4/projects/{repo_id}/members",
            headers=_bot_headers(bot_token),
            json={"user_id": gitlab_user_id, "access_level": access_level},
        )
        if resp.status_code not in (200, 201):
            # 409 = 已是成员,跳过即可
            if resp.status_code == 409:
                logger.info("GitLab 成员 %s 已在仓库 %s 中,跳过", gitlab_user_id, repo_id)
            else:
                logger.warning(
                    "GitLab 加成员失败 repo=%s user=%s %s: %s",
                    repo_id, gitlab_user_id, resp.status_code, resp.text[:200],
                )
    except httpx.HTTPError as e:
        logger.warning("GitLab 加成员请求失败(忽略): %s", e)
    finally:
        await client.aclose()


async def bot_lookup_user_id_by_username(
    bot_token: str,
    gitlab_url: str,
    username: str,
) -> Optional[int]:
    """
    按 GitLab username 查用户 id:GET /api/v4/users?username={u}(精确匹配)
    查不到返回 None(调用方自行降级)。
    """
    client = _get_client()
    try:
        resp = await client.get(
            f"{gitlab_url.rstrip('/')}/api/v4/users",
            headers=_bot_headers(bot_token),
            params={"username": username},
        )
        if resp.status_code != 200:
            return None
        items = resp.json()
        for it in items:
            if it.get("username") == username:
                return it.get("id")
        return None
    except httpx.HTTPError as e:
        logger.warning("GitLab 查用户失败(忽略): %s", e)
        return None
    finally:
        await client.aclose()


async def bot_init_readme(
    bot_token: str,
    gitlab_url: str,
    repo_id: int,
    branch: str,
) -> None:
    """
    初始化仓库 README.md:POST /api/v4/projects/{id}/repository/commits
    失败不抛异常(非关键步骤,只记 warning)。
    """
    client = _get_client()
    try:
        resp = await client.post(
            f"{gitlab_url.rstrip('/')}/api/v4/projects/{repo_id}/repository/commits",
            headers=_bot_headers(bot_token),
            json={
                "branch": branch,
                "commit_message": "init: README",
                "actions": [
                    {"action": "create", "file_path": "README.md", "content": f"# {repo_id}\n"},
                ],
            },
        )
        if resp.status_code not in (200, 201):
            logger.warning("GitLab 初始化 README 失败 repo=%s %s: %s", repo_id, resp.status_code, resp.text[:200])
    except httpx.HTTPError as e:
        logger.warning("GitLab 初始化 README 请求失败(忽略): %s", e)
    finally:
        await client.aclose()


async def bot_test_connection(bot_token: str, gitlab_url: str) -> dict:
    """
    平台设置"测试连接":GET /api/v4/version
    返回 {"ok": bool, "version": str|None, "message": str}
    """
    client = _get_client()
    try:
        resp = await client.get(
            f"{gitlab_url.rstrip('/')}/api/v4/version",
            headers=_bot_headers(bot_token),
        )
        if resp.status_code == 200:
            return {"ok": True, "version": resp.json().get("version"), "message": "连接成功"}
        return {"ok": False, "version": None, "message": f"GitLab 返回 {resp.status_code},请检查 token 与地址"}
    except httpx.HTTPError as e:
        return {"ok": False, "version": None, "message": f"连接失败:{e}"}
    finally:
        await client.aclose()
