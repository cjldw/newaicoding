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
