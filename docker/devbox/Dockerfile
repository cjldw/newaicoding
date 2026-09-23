# 旗程任务容器镜像(R8.F1 / BUG-026:原 mcr devcontainer/universal:linux 已被微软退役,
# 基础镜像重建为 devcontainers/typescript-node——node+git 内置,python3 由 apt 补装)
# 构建:docker build -t platform/devbox:v1 -f docker/devbox/Dockerfile .(context=仓库根,COPY skills/ 依赖)
FROM mcr.microsoft.com/devcontainers/typescript-node:dev-bookworm

USER root

# 系统依赖:python3/pip(R8 任务执行)+ inotify-tools(R11 文件 watcher)
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 python3-pip inotify-tools \
    && rm -rf /var/lib/apt/lists/*

# Claude CLI
RUN npm install -g @anthropic-ai/claude-code

# 预装高频 Python 包(--break-system-packages:Debian 12 PEP 668 外部管理环境)
RUN pip3 install --break-system-packages \
    fastapi uvicorn sqlalchemy pytest requests httpx

# 预装高频 npm 包(create-react-app 已停止维护,R8.F1 移除;任务模板走 vite)
RUN npm install -g vite

# 预装常用 MCP server(R8.F1 修正:server-git/server-sqlite 已从 npm 退役,官方形态转 Python,
# 实证 npm view 空;仅保留 npm 存续的 3 个,git/sqlite 留待 R17 契约层按 uvx 形态接)
RUN npm install -g \
    @modelcontextprotocol/server-filesystem \
    @modelcontextprotocol/server-github \
    @modelcontextprotocol/server-brave-search

# 预装平台官方 Skills(按 R17;任务创建时项目级 Skills 覆盖同名)
# 基础镜像默认用户为 node(uid 1000,HOME=/home/node;R8.F1 实测:非 vscode/codespace)
RUN mkdir -p /workspace && chown -R node:node /workspace
COPY skills/ /home/node/.claude/skills/
RUN chown -R node:node /home/node/.claude

USER node
WORKDIR /workspace
# 任务容器需常驻前台进程(docker run -d 后 exec/clone 依赖容器存活;BUG-028:CMD bash 无 TTY 秒退)
CMD ["sleep", "infinity"]
