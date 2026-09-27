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

# 预装 MCP server(R2 追加 2 个,bin 名已实测:@benborla29/mcp-server-mysql 2.0.9 → bin mcp-server-mysql;
# figma-developer-mcp 0.13.2 → bin figma-developer-mcp,纯 stdio。离线直连 npm -g bin,不经 npx)
# mysql 条目预置配置故意不设 ALLOW_INSERT/UPDATE/DELETE/DDL_OPERATION → 包默认 SELECT-only(只读第二道防线)
RUN npm install -g \
    @benborla29/mcp-server-mysql \
    figma-developer-mcp

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

# 预置系统级 MCP 配置(R2):user-scope /home/node/.claude.json 顶层 mcpServers 恰 6 条,
# 内容与 docs/20260927_devbox默认skills与mcp/DEVPLAN/R2.md「接口契约」交付物 JSON 逐字一致
# 归属探明:基础镜像(devcontainers/typescript-node)无 .claude.json;该文件由上方 R1 plugin RUN
# 以 node 身份首建(CLI 顶层状态,如 pluginUsage;marketplace/plugin 安装态在 ~/.claude/plugins/,不在此文件)
# → 采用「合并写入」:仅整体替换顶层 mcpServers,其余顶层键保留(勿破坏既有层);以 node 身份写,归属 node:node,
#    不动 /home/node/.claude/(skills 与 plugin 段)。文件内仅 ${VAR} 引用文本,凭据不进镜像(可 docker history 抽验)
RUN printf '%s\n' \
'  {' \
'    "mcpServers": {' \
'      "mysql_dev": {' \
'        "type": "stdio",' \
'        "command": "mcp-server-mysql",' \
'        "env": {' \
'          "MYSQL_HOST": "${ENV_MCP_MYSQL_DEV_HOST}",' \
'          "MYSQL_PORT": "${ENV_MCP_MYSQL_PORT:-3306}",' \
'          "MYSQL_USER": "${ENV_MCP_MYSQL_USER}",' \
'          "MYSQL_PASS": "${ENV_MCP_MYSQL_PASSWORD}",' \
'          "MYSQL_DB": "${ENV_MCP_MYSQL_DATABASE}"' \
'        }' \
'      },' \
'      "mysql_beta": {' \
'        "type": "stdio",' \
'        "command": "mcp-server-mysql",' \
'        "env": {' \
'          "MYSQL_HOST": "${ENV_MCP_MYSQL_BETA_HOST}",' \
'          "MYSQL_PORT": "${ENV_MCP_MYSQL_PORT:-3306}",' \
'          "MYSQL_USER": "${ENV_MCP_MYSQL_USER}",' \
'          "MYSQL_PASS": "${ENV_MCP_MYSQL_PASSWORD}",' \
'          "MYSQL_DB": "${ENV_MCP_MYSQL_DATABASE}"' \
'        }' \
'      },' \
'      "figma": {' \
'        "type": "stdio",' \
'        "command": "figma-developer-mcp",' \
'        "args": ["--stdio"],' \
'        "env": { "FIGMA_API_KEY": "${ENV_MCP_FIGMA_TOKEN}" }' \
'      },' \
'      "filesystem": {' \
'        "type": "stdio",' \
'        "command": "mcp-server-filesystem",' \
'        "args": ["/workspace"]' \
'      },' \
'      "github": {' \
'        "type": "stdio",' \
'        "command": "mcp-server-github",' \
'        "env": { "GITHUB_PERSONAL_ACCESS_TOKEN": "${ENV_MCP_GITHUB_TOKEN}" }' \
'      },' \
'      "brave-search": {' \
'        "type": "stdio",' \
'        "command": "mcp-server-brave-search",' \
'        "env": { "BRAVE_API_KEY": "${ENV_MCP_BRAVE_API_KEY}" }' \
'      }' \
'    }' \
'  }' > /tmp/mcp-preset.json \
    && node -e 'const fs=require("fs");const p="/home/node/.claude.json";const t=fs.readFileSync("/tmp/mcp-preset.json","utf8");const preset=JSON.parse(t);let cfg=null;try{cfg=JSON.parse(fs.readFileSync(p,"utf8"))}catch(e){}const has=cfg&&typeof cfg==="object"&&Object.keys(cfg).length>0;fs.writeFileSync(p,has?JSON.stringify(Object.assign({},cfg,{mcpServers:preset.mcpServers}),null,2)+"\n":t);' \
    && rm -f /tmp/mcp-preset.json \
    && node -e 'const c=JSON.parse(require("fs").readFileSync("/home/node/.claude.json","utf8"));const k=Object.keys(c.mcpServers||{}).sort().join(",");process.exit(k==="brave-search,figma,filesystem,github,mysql_beta,mysql_dev"?0:1)'

WORKDIR /workspace
# 任务容器需常驻前台进程(docker run -d 后 exec/clone 依赖容器存活;BUG-028:CMD bash 无 TTY 秒退)
CMD ["sleep", "infinity"]
