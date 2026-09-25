"""GitLab 服务 - token 验证、用户信息获取"""

import logging
from typing import Optional

import httpx

from app.core.response import (
    BizError,
    ErrCode,
    MSG_GITLAB_UNREACHABLE,
    MSG_REPO_FORBIDDEN,
    MSG_REPO_NOT_FOUND,
)

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
    async def verify_token(gitlab_token: str, api_base: Optional[str] = None) -> dict:
        """
        调用 GitLab API 验证 personal access token:
        - GET /api/v4/user → 获取用户名 + 从 X-Token-Scopes 响应头获取 scope
        - api_base:自建 GitLab 的 API 基址(如 http://gitlab.example.com/api/v4);
          None 时回落默认 GITLAB_API_BASE(BUG-015:自建环境必须由调用方传入平台配置的 gitlab_url)
        返回 {"username": str, "scopes": list[str]}
        失败时抛出 BizError
        """
        # BUG-012:GitLab PAT 仅认 PRIVATE-TOKEN 头(Bearer 仅适用于 OAuth token)
        headers = {"PRIVATE-TOKEN": gitlab_token}
        # BUG-015:校验目标实例以调用方传入为准,未传入才用模块默认值
        base = (api_base or GITLAB_API_BASE).rstrip("/")

        client = _get_client()
        try:
            # 获取用户信息（同时从响应头提取 scope）
            try:
                resp = await client.get(
                    f"{base}/user",
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
            # BUG-016:GitLab 12.x 之前 /user 响应不带 X-Token-Scopes 头(实测 v11.7 为 None),
            # 且旧版无 personal_access_tokens 自省接口(404)——scope 无法判定时置
            # ["unknown"] 而非空列表,避免有效 token 在旧版实例上被误判缺权限
            scopes_header = resp.headers.get("X-Token-Scopes", "")
            scopes = scopes_header.split() if scopes_header else ["unknown"]

        finally:
            await client.aclose()

        return {"username": username, "scopes": scopes}

    @staticmethod
    def check_required_scopes(scopes: list[str]) -> bool:
        """
        检查 token 是否包含所需 scope（AND 逻辑）。
        R1 要求: 必须同时具备 read_repository 和 write_repository。
        BUG-016:scopes == ["unknown"] 表示实例过旧无法自省 scope,放行——
        真实权限不足由后续实际 GitLab 操作的 401/403 兜底暴露。
        """
        if not scopes:
            return False
        if scopes == ["unknown"]:
            return True
        return all(s in scopes for s in REQUIRED_SCOPES)


# ---------------------------------------------------------------------------
# R2 平台 bot 操作(bot token 来自 platform_settings,读取处实时查表)
# ---------------------------------------------------------------------------
# 访问级别常量(GitLab): 30=Developer 40=Maintainer
ACCESS_LEVEL_DEVELOPER = 30
ACCESS_LEVEL_MAINTAINER = 40


def _bot_headers(bot_token: str) -> dict:
    """平台 bot token 请求头

    BUG-012:GitLab PAT 仅认 PRIVATE-TOKEN 头;Authorization: Bearer 仅适用于
    OAuth2 access token,用于 PAT 会恒 401(curl 实证 2026-09-22)。
    """
    return {"PRIVATE-TOKEN": bot_token}


_VIS_ORDER = {"private": 0, "internal": 1, "public": 2}


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

    BUG-013:GitLab 规则"仓库可见性 ≤ 组可见性"(private<internal<public)——
    私有组内建 internal/public 仓库会被拒("internal is not allowed in a private
    group.");建仓前读 group 可见性,请求超出时自动降级。
    """
    client = _get_client()
    try:
        # 读目标 group 可见性,请求超出则降级(读失败不阻断,交给建仓报错兜底)
        try:
            g = await client.get(
                f"{gitlab_url.rstrip('/')}/api/v4/groups/{namespace_id}",
                headers=_bot_headers(bot_token),
            )
            if g.status_code == 200:
                gv = (g.json() or {}).get("visibility", "private")
                if _VIS_ORDER.get(visibility, 0) > _VIS_ORDER.get(gv, 0):
                    logger.info("GitLab 建仓可见性降级 %s -> %s(namespace %s)", visibility, gv, namespace_id)
                    visibility = gv
        except httpx.HTTPError as e:
            logger.warning("读取 GitLab group 可见性失败(忽略,按原 visibility 建仓): %s", e)

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
    返回 project JSON;失败按原因细分(R27):
    404→2011(仓库不存在) / 401|403→2012(bot 无访问权限,归并防枚举) /
    其他非 200→2014(GitLab 连接失败兜底) / httpx 网络异常→2014。
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
        logger.warning("GitLab 查询仓库失败(网络异常): %s", e)
        raise BizError(ErrCode.GITLAB_UNREACHABLE, MSG_GITLAB_UNREACHABLE)
    finally:
        await client.aclose()

    logger.info("GitLab 查询仓库 %s 返回 %s", repo_path, resp.status_code)
    if resp.status_code == 404:
        # 2011:仓库不存在(含 GitLab 对无权限仓库返回 404 的口径);文案仅含平台 gitlab_url
        raise BizError(
            ErrCode.REPO_NOT_FOUND,
            MSG_REPO_NOT_FOUND.format(gitlab_url=gitlab_url),
        )
    if resp.status_code in (401, 403):
        # 2012:bot 无访问权限;401/403 归并同一文案(防仓库枚举)
        raise BizError(ErrCode.REPO_FORBIDDEN, MSG_REPO_FORBIDDEN)
    if resp.status_code != 200:
        # 2014 兜底:5xx 等其他异常状态按 GitLab 连接失败处理
        raise BizError(ErrCode.GITLAB_UNREACHABLE, MSG_GITLAB_UNREACHABLE)
    return resp.json()


def bot_check_repo_permission(project_json: dict, min_level: int = ACCESS_LEVEL_MAINTAINER) -> bool:
    """
    检查 bot 对仓库的权限(R27 修复:取 max(project_access, group_access)):
    access_level = max(permissions.project_access?.access_level or 0,
                       permissions.group_access?.access_level or 0) >= min_level
    (read+write+merge 要求至少 Maintainer=40;group 继承时 project_access 可能为 null,
     两层各自可空、permissions 整体可缺省,均视为 0。group_access 为 GitLab 已聚合的
     继承链最大值,不自行递归。)
    """
    perms = project_json.get("permissions") or {}
    project_level = (perms.get("project_access") or {}).get("access_level") or 0
    group_level = (perms.get("group_access") or {}).get("access_level") or 0
    return max(project_level, group_level) >= min_level


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


async def bot_remove_member(
    bot_token: str,
    gitlab_url: str,
    repo_id: int,
    gitlab_user_id: int,
) -> None:
    """
    平台 bot 移除 repo 成员:DELETE /api/v4/projects/{id}/members/{gitlab_user_id}
    失败不抛异常(非关键步骤,只记 warning;404=本就不是成员,忽略)。
    """
    client = _get_client()
    try:
        resp = await client.delete(
            f"{gitlab_url.rstrip('/')}/api/v4/projects/{repo_id}/members/{gitlab_user_id}",
            headers=_bot_headers(bot_token),
        )
        if resp.status_code not in (200, 204, 404):
            logger.warning(
                "GitLab 移除成员失败 repo=%s user=%s %s: %s",
                repo_id, gitlab_user_id, resp.status_code, resp.text[:200],
            )
    except httpx.HTTPError as e:
        logger.warning("GitLab 移除成员请求失败(忽略): %s", e)
    finally:
        await client.aclose()


async def bot_update_member_level(
    bot_token: str,
    gitlab_url: str,
    repo_id: int,
    gitlab_user_id: int,
    access_level: int,
) -> None:
    """
    平台 bot 修改 repo 成员权限:PUT /api/v4/projects/{id}/members/{gitlab_user_id}
    失败不抛异常(非关键步骤;404=不是成员,降级为尝试直接添加)。
    """
    client = _get_client()
    try:
        resp = await client.put(
            f"{gitlab_url.rstrip('/')}/api/v4/projects/{repo_id}/members/{gitlab_user_id}",
            headers=_bot_headers(bot_token),
            json={"access_level": access_level},
        )
        if resp.status_code == 404:
            # 不是成员 → 直接添加
            await client.aclose()
            await bot_add_member(bot_token, gitlab_url, repo_id, gitlab_user_id, access_level)
            return
        if resp.status_code not in (200, 201):
            logger.warning(
                "GitLab 改成员权限失败 repo=%s user=%s %s: %s",
                repo_id, gitlab_user_id, resp.status_code, resp.text[:200],
            )
    except httpx.HTTPError as e:
        logger.warning("GitLab 改成员权限请求失败(忽略): %s", e)
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


# ---------------------------------------------------------------------------
# R11 项目模式:仓库浏览(GitLab API,bot token;只读)
# ---------------------------------------------------------------------------
async def bot_create_branch(bot_token: str, gitlab_url: str, repo_id: int, branch: str, ref: str) -> dict:
    """
    建分支(R3 创建需求):POST /api/v4/projects/{id}/repository/branches
    body {branch, ref};分支已存在(400)视为成功幂等;其他错误抛 2002。
    """
    client = _get_client()
    try:
        resp = await client.post(
            f"{gitlab_url.rstrip('/')}/api/v4/projects/{repo_id}/repository/branches",
            headers=_bot_headers(bot_token),
            json={"branch": branch, "ref": ref},
        )
        if resp.status_code in (200, 201):
            return resp.json()
        if resp.status_code == 400 and "already exists" in resp.text:
            logger.info("GitLab 分支已存在(幂等) repo=%s branch=%s", repo_id, branch)
            return {}
        logger.warning("GitLab 建分支失败 repo=%s %s: %s", repo_id, resp.status_code, resp.text[:200])
        raise BizError(ErrCode.REPO_URL_INVALID, "需求分支创建失败")
    except httpx.HTTPError as e:
        logger.warning("GitLab 建分支连接失败: %s", e)
        raise BizError(ErrCode.REPO_URL_INVALID, "GitLab 服务连接失败")
    finally:
        await client.aclose()


async def bot_get_tree(bot_token: str, gitlab_url: str, repo_id: int,
                       ref: str, path: str, recursive: bool = False) -> list:
    """
    仓库文件树:GET /api/v4/projects/{id}/repository/tree?ref&path
    recursive=True 时递归取全树(R2 条目详情目录拉全用)。
    GitLab 单页 ≤100 条,此处按 page 循环拉齐(短页即止);失败(分支/路径不存在)抛 BizError。
    """
    from app.core.response import BizError

    client = _get_client()
    try:
        entries: list = []
        page = 1
        while True:
            params = {"ref": ref, "path": path or "", "per_page": 100, "page": page}
            if recursive:
                params["recursive"] = "true"
            resp = await client.get(
                f"{gitlab_url.rstrip('/')}/api/v4/projects/{repo_id}/repository/tree",
                headers=_bot_headers(bot_token),
                params=params,
            )
            if resp.status_code == 200:
                batch = resp.json() or []
                entries.extend(batch)
                if len(batch) < 100:   # 短页 = 最后一页
                    return entries
                page += 1
                continue
            if resp.status_code == 404:
                return []
            logger.warning("GitLab tree 失败 repo=%s %s: %s", repo_id, resp.status_code, resp.text[:200])
            raise BizError(ErrCode.TERMINAL_UNAVAILABLE, "无法加载,请稍后重试")
    except httpx.HTTPError as e:
        logger.warning("GitLab tree 连接失败: %s", e)
        raise BizError(ErrCode.TERMINAL_UNAVAILABLE, "无法加载,请稍后重试")
    finally:
        await client.aclose()


async def bot_get_file(bot_token: str, gitlab_url: str, repo_id: int, ref: str, path: str) -> dict:
    """
    文件内容:GET /api/v4/projects/{id}/repository/files/{encoded path}?ref=
    返回 GitLab JSON(content=base64,size);404 → BizError(404)。
    """
    from urllib.parse import quote

    from app.core.response import BizError

    encoded = quote(path, safe="")
    client = _get_client()
    try:
        resp = await client.get(
            f"{gitlab_url.rstrip('/')}/api/v4/projects/{repo_id}/repository/files/{encoded}",
            headers=_bot_headers(bot_token),
            params={"ref": ref},
        )
        if resp.status_code == 200:
            return resp.json()
        if resp.status_code == 404:
            raise BizError(404, "文件不存在", status_code=404)
        logger.warning("GitLab file 失败 %s: %s", path, resp.status_code)
        raise BizError(ErrCode.TERMINAL_UNAVAILABLE, "无法加载,请稍后重试")
    except httpx.HTTPError as e:
        logger.warning("GitLab file 连接失败: %s", e)
        raise BizError(ErrCode.TERMINAL_UNAVAILABLE, "无法加载,请稍后重试")
    finally:
        await client.aclose()


# ---------------------------------------------------------------------------
# R1 手动添加双类型:分支列表(关联代码 Dialog 下拉)
# ---------------------------------------------------------------------------
async def bot_list_branches(bot_token: str, gitlab_url: str, repo_id: int) -> list:
    """
    分支列表:GET /api/v4/projects/{id}/repository/branches?per_page=100
    返回 GitLab 原始数组([{name, default, commit...}]),裁剪/default 置顶由调用方负责;
    非 200 / 网络异常 → BizError(2014,写法同 bot_get_file)。
    """
    client = _get_client()
    try:
        resp = await client.get(
            f"{gitlab_url.rstrip('/')}/api/v4/projects/{repo_id}/repository/branches",
            headers=_bot_headers(bot_token),
            params={"per_page": 100},
        )
        if resp.status_code == 200:
            return resp.json() or []
        logger.warning("GitLab branches 失败 repo=%s %s: %s", repo_id, resp.status_code, resp.text[:200])
        raise BizError(ErrCode.GITLAB_UNREACHABLE, MSG_GITLAB_UNREACHABLE)
    except httpx.HTTPError as e:
        logger.warning("GitLab branches 连接失败: %s", e)
        raise BizError(ErrCode.GITLAB_UNREACHABLE, MSG_GITLAB_UNREACHABLE)
    finally:
        await client.aclose()
