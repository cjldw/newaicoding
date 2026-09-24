"""网关核心 - R15(自研 Python 反向代理,Host 精确匹配;D20 网关直连 Runner)

- HTTP:查 routes(host 匹配 + status=active)→ preview 鉴权(JWT + 项目成员)/
  deploy 公开 → httpx 流式转发 upstream
- WebSocket 透传(HMR/TTY):websockets 客户端双向桥接
- 限流:单 host QPS 上限(默认 100,内存滑窗)
- 异常页:404 未注册 / 403 非成员 / 502 Runner offline(带项目名与日志链接)
- 独立进程入口见 gateway/main.py;测试以 httpx ASGITransport 直连本 app
"""

import asyncio
import logging
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Optional

import httpx
from fastapi import Request, WebSocket
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_factory
from app.models.project import Project
from app.models.route import Route
from app.services import route_service

logger = logging.getLogger(__name__)

QPS_LIMIT_DEFAULT = 100  # 单 host QPS 上限(防爬/防滥用)

_html = """<!doctype html><html lang="zh"><meta charset="utf-8">
<title>{code} - 旗橙</title>
<body style="font-family:system-ui;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;background:#f4f4f5">
<div style="text-align:center">
<h1 style="font-size:48px;margin:0;color:#18181b">{code}</h1>
<p style="color:#71717a">{message}</p>
<p style="color:#a1a1aa;font-size:13px">项目:{project_name} · <a href="/logs">查看日志</a></p>
</div></body></html>"""


def _page(code: int, message: str, project_name: str = "-") -> HTMLResponse:
    return HTMLResponse(_html.format(code=code, message=message, project_name=project_name), status_code=code)


class _QpsLimiter:
    """单 host 滑窗限流(内存;网关单实例)"""

    def __init__(self, limit: int = QPS_LIMIT_DEFAULT):
        self.limit = limit
        self._hits: dict[str, deque] = defaultdict(deque)

    def allow(self, host: str) -> bool:
        now = time.monotonic()
        window = self._hits[host]
        while window and now - window[0] > 1.0:
            window.popleft()
        if len(window) >= self.limit:
            return False
        window.append(now)
        return True


class GatewayState:
    """网关运行时状态(注入 session factory,便于测试)"""

    def __init__(self, session_factory) -> None:
        self.session_factory = session_factory
        self.limiter = _QpsLimiter()
        self.http = httpx.AsyncClient(timeout=30.0)

    async def route_for_host(self, host: str) -> Optional[Route]:
        async with self.session_factory() as db:
            # Host 头可能带端口:先整串精确匹配,再退化为去端口匹配(deploy {host}:{port})
            route = await route_service.get_by_host(db, host)
            if route is None and ":" in host:
                route = await route_service.get_by_host(db, host.split(":", 1)[0])
            if route is not None:
                await db.refresh(route)
            return route

    async def project_name(self, project_id: str) -> str:
        async with self.session_factory() as db:
            result = await db.execute(select(Project.name).where(Project.project_id == project_id))
            return result.scalar_one_or_none() or "-"


state_holder: dict = {}


def create_gateway_app(session_factory=async_session_factory):
    """构建网关 ASGI 应用(Starlette/FastAPI;测试可注入 session factory)"""
    from fastapi import FastAPI

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    state_holder["app"] = app
    app.state.gateway = GatewayState(session_factory)

    @app.get("/healthz")
    async def healthz():
        return {"status": "ok"}

    # -----------------------------------------------------------------
    # WebSocket 透传(HMR/TTY)
    # -----------------------------------------------------------------
    @app.websocket("/ws")
    async def proxy_ws(websocket: WebSocket):
        gateway: GatewayState = app.state.gateway
        host = (websocket.headers.get("host") or "").split(":", 1)[0]
        async with gateway.session_factory() as db:
            route = await route_service.get_by_host(db, host)
        if route is None or route.status != "active":
            await websocket.close(code=4404)
            return
        # 上游 ws://host:port/原路径
        upstream = route.upstream.replace("http://", "ws://").replace("https://", "wss://")
        upstream_ws = f"{upstream}{websocket.url.path}?{websocket.url.query}"

        import websockets as _ws

        try:
            async with _ws.connect(upstream_ws) as upstream_conn:
                await websocket.accept()

                async def pump_client():
                    while True:
                        data = await websocket.receive_text()
                        await upstream_conn.send(data)

                async def pump_upstream():
                    while True:
                        data = await upstream_conn.recv()
                        await websocket.send_text(data if isinstance(data, str) else data.decode())

                done, pending = await asyncio.wait(
                    [asyncio.create_task(pump_client()), asyncio.create_task(pump_upstream())],
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for task in pending:
                    task.cancel()
        except Exception as e:
            logger.warning("WS 透传失败 host=%s: %s", host, e)
            try:
                await websocket.close(code=1502)
            except Exception:
                pass

    # -----------------------------------------------------------------
    # HTTP 反向代理
    # -----------------------------------------------------------------
    @app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"])
    async def proxy(request: Request, path: str):
        gateway: GatewayState = app.state.gateway
        host_header = request.headers.get("host", "")
        host = host_header.split(":", 1)[0]

        # 限流
        if not gateway.limiter.allow(host):
            return JSONResponse({"code": 1429, "message": "请求过于频繁"}, status_code=429)

        async with gateway.session_factory() as db:
            # Host 含端口(deploy {host}:{port})先整串匹配,再退化去端口匹配
            route = await gateway.route_for_host(host_header)
            if route is None or route.status != "active":
                return _page(404, "服务未启动或已下线")
            if route.auth_required:
                # 预览鉴权:JWT(cookie/query/Authorization)+ 项目成员
                token = (
                    request.query_params.get("auth_token")
                    or request.cookies.get("qc_token")
                    or (request.headers.get("authorization", "").replace("Bearer ", "", 1) or None)
                )
                user = await _authenticate(db, token)
                allowed = await route_service.check_preview_access(db, host, user)
                if not allowed:
                    return _page(403, "无权访问该项目预览", await gateway.project_name(route.project_id))

        url = f"{route.upstream}/{path}"
        if request.url.query:
            url += f"?{request.url.query}"

        headers = {
            k: v for k, v in request.headers.items()
            if k.lower() not in ("host", "connection", "upgrade", "content-length")
        }
        body = await request.body()
        try:
            upstream_resp = await gateway.http.request(
                request.method, url, headers=headers, content=body, follow_redirects=False,
            )
        except httpx.HTTPError:
            # Runner offline / 上游不可达:路由保留,502 + 明确提示
            return _page(502, "Runner offline,服务暂不可达", await gateway.project_name(route.project_id))

        if upstream_resp.status_code >= 500:
            return _page(502, "上游服务错误", await gateway.project_name(route.project_id))

        resp_headers = {
            k: v for k, v in upstream_resp.headers.items()
            if k.lower() not in ("content-length", "transfer-encoding", "connection")
        }
        return HTMLResponse(
            content=upstream_resp.content,
            status_code=upstream_resp.status_code,
            headers=resp_headers,
            media_type=upstream_resp.headers.get("content-type"),
        )

    return app


async def _authenticate(db: AsyncSession, token: str):
    """网关侧 JWT 校验(JWT + token_version + 状态)"""
    import jwt as pyjwt

    from app.core.security import decode_token
    from app.models.user import User

    if not token:
        return None
    try:
        payload = decode_token(token)
    except pyjwt.PyJWTError:
        return None
    if payload.get("type") != "access":
        return None
    result = await db.execute(select(User).where(User.user_id == payload.get("sub", "")))
    user = result.scalar_one_or_none()
    if user is None or user.token_version != payload.get("token_version") or user.status == "disabled":
        return None
    return user
