# 旗程任务容器镜像(R8.F1 / BUG-026:原 mcr devcontainer/universal:linux 已被微软退役,
# 基础镜像重建为 devcontainers/typescript-node——node+git 内置,python3 由 apt 补装)
# 构建(context=仓库根):docker build -t platform/devbox:v2 -f docker/devbox/Dockerfile .
# 可选覆盖 marketplace 地址:--build-arg RD_FLOW_MARKETPLACE=<git 地址>(不传用下方默认)
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

# 预装平台官方 Skills(按 R17/R1;任务创建时项目级 Skills 覆盖同名)
# 目录式 <name>/SKILL.md(与 claude CLI 加载约定及 probe -type d 探测口径一致)
# 基础镜像默认用户为 node(uid 1000,HOME=/home/node;R8.F1 实测:非 vscode/codespace)
RUN mkdir -p /workspace && chown -R node:node /workspace
COPY docker/devbox/skills/ /home/node/.claude/skills/
RUN chown -R node:node /home/node/.claude

# 预装 rd-flow plugin(R1):marketplace 地址做成 ARG,构建机不可达时构建显式失败(docker RUN 默认行为,不静默跳过)
ARG RD_FLOW_MARKETPLACE=http://47.111.69.64/ai/rd-flow.git

USER node
# 以运行用户(node)安装,落盘到 /home/node/.claude/plugins/;构建期 claude CLI 子命令免登录(已实测,Claude Code 2.1.278)
# 末段 grep -q rd-flow 失败即构建失败(安装可见性显式断言);版本不锁定,跟随 marketplace 默认
RUN claude plugin marketplace add ${RD_FLOW_MARKETPLACE} \
    && claude plugin install rd-flow@rd-flow \
    && claude plugin list | grep -q rd-flow

WORKDIR /workspace
# 任务容器需常驻前台进程(docker run -d 后 exec/clone 依赖容器存活;BUG-028:CMD bash 无 TTY 秒退)
CMD ["sleep", "infinity"]
