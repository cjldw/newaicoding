"""网关独立进程入口 - R15

    GATEWAY_PORT=80 python3 main.py

自研 Python 网关(R15 决策:V1 自研替代 Nginx/Traefik 配置管理,动态路由直查
routes 表,变更即时生效,无需 reload;Host 精确匹配,upstream 直连 Runner 宿主机)。
"""

import logging
import os

import uvicorn

from app.core.gateway import create_gateway_app

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

app = create_gateway_app()

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("GATEWAY_PORT", "80")))
