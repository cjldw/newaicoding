# devbox 任务容器镜像(platform/devbox)

任务容器基础镜像:预装 Claude CLI、研发常用工具链、平台官方 Skills、rd-flow plugin 与 6 个 MCP server 预置配置。AI 任务容器一律以本镜像启动,`/workspace` 为工作目录。

- **基础镜像**:`devcontainers/typescript-node:dev-bookworm`(node+git 内置,python3 由 apt 补装;默认用户 `node`,uid 1000,`HOME=/home/node`)
- **当前 tag**:`v2`(R1/R2);默认拉取地址 `registry.cn-hangzhou.aliyuncs.com/zhanqinet/devbox:v2`(R5 起为代码默认,可经平台设置项 `container_image` 覆盖,见下文)
- **构建定义**:[Dockerfile](./Dockerfile)(context = 仓库根)

## 预装内容

| 类别 | 内容 |
|---|---|
| 运行时 | Claude CLI(`@anthropic-ai/claude-code`)、python3 + pip(fastapi/uvicorn/sqlalchemy/pytest/requests/httpx)、npm -g `vite` |
| MCP server 包(npm -g,本地直连,禁运行时 npx 外网拉取) | `@modelcontextprotocol/server-filesystem` / `server-github` / `server-brave-search`、`@benborla29/mcp-server-mysql`(bin `mcp-server-mysql`)、`figma-developer-mcp` |
| 平台 Skills | `/home/node/.claude/skills/<name>/SKILL.md` 目录式:`code-review` / `refactoring` / `writing-tests` |
| Plugin | `rd-flow@rd-flow`(构建期自 marketplace `http://47.111.69.64/ai/rd-flow.git` 安装,ARG 可换源) |
| MCP 预置配置 | `/home/node/.claude.json` 顶层 `mcpServers` 恰 6 条:`mysql_dev` / `mysql_beta` / `figma` / `filesystem` / `github` / `brave-search`(与项目级合并时同名键项目级覆盖,预置项不被整段抹除) |

## MCP 环境变量说明与配置

### 配置入口

超管登录平台 → **管理后台 → 平台设置 → 自定义变量**(即 `custom_env_vars`),逐条添加下表键值后保存。变量随**下次容器创建**注入容器 environment,预置 MCP 配置在容器内按当时 env 实时展开 `${VAR}` 引用。

键名规则(平台校验):`^[A-Za-z_][A-Za-z0-9_]*$`;≤50 键;单值 ≤2048 字符;不得占用 13 个系统保留键(`GITLAB_*` / `LLM_*` / `ANTHROPIC_*` / `TASK_ID` / `PROJECT_ID` / `REQ_ID` / `PRD_FILE_PATH`)。

### 变量清单(9 个)

| 变量名 | 必填 | 说明 |
|---|---|---|
| `ENV_MCP_MYSQL_DEV_HOST` | 是 | dev 库主机 |
| `ENV_MCP_MYSQL_BETA_HOST` | 是 | beta 库主机 |
| `ENV_MCP_MYSQL_PORT` | 是 | 端口(dev/beta 共用;预置配置带 `${ENV_MCP_MYSQL_PORT:-3306}` 兜底) |
| `ENV_MCP_MYSQL_USER` | 是 | 账号(共用,**需只读权限**,见安全) |
| `ENV_MCP_MYSQL_PASSWORD` | 是 | 密码(共用) |
| `ENV_MCP_MYSQL_DATABASE` | 是 | 默认库(共用) |
| `ENV_MCP_FIGMA_TOKEN` | 否 | Figma API token(未配则 figma MCP 不可用) |
| `ENV_MCP_GITHUB_TOKEN` | 否 | GitHub PAT(未配则 github MCP 可启动但调用报错) |
| `ENV_MCP_BRAVE_API_KEY` | 否 | Brave Search API key(未配则 brave-search 可启动但调用报错) |

> 命名勿混:预置配置内 MySQL 密码字段是 `MYSQL_PASS`(包约定),平台变量名是 `ENV_MCP_MYSQL_PASSWORD`,经 `${VAR}` 引用衔接。

### 预置 server → 变量映射

| server | command | 引用的环境变量 |
|---|---|---|
| `mysql_dev` | `mcp-server-mysql` | `MYSQL_HOST=${ENV_MCP_MYSQL_DEV_HOST}` `MYSQL_PORT=${ENV_MCP_MYSQL_PORT:-3306}` `MYSQL_USER=${ENV_MCP_MYSQL_USER}` `MYSQL_PASS=${ENV_MCP_MYSQL_PASSWORD}` `MYSQL_DB=${ENV_MCP_MYSQL_DATABASE}` |
| `mysql_beta` | `mcp-server-mysql` | 同上,HOST 用 `ENV_MCP_MYSQL_BETA_HOST` |
| `figma` | `figma-developer-mcp --stdio` | `FIGMA_API_KEY=${ENV_MCP_FIGMA_TOKEN}` |
| `filesystem` | `mcp-server-filesystem /workspace` | 无凭据(仅工作区读写) |
| `github` | `mcp-server-github` | `GITHUB_PERSONAL_ACCESS_TOKEN=${ENV_MCP_GITHUB_TOKEN}` |
| `brave-search` | `mcp-server-brave-search` | `BRAVE_API_KEY=${ENV_MCP_BRAVE_API_KEY}` |

### 静默降级

任一可选变量未配置时,对应条目**仍保留**在预置配置中(不裁剪),`${VAR}` 未设按字面透传,该 server 启动/连接失败——**容器创建与任务执行不受阻**,仅对话中调用对应 MCP 时报错。补配变量后**新起容器**即生效(存量容器不变)。

### 安全约定

- **MySQL 只读双层防线**:① DBA 侧为 `ENV_MCP_MYSQL_USER` 仅授 `SELECT`/`SHOW`(根本);② 预置条目故意不设 `ALLOW_INSERT`/`ALLOW_UPDATE`/`ALLOW_DELETE`/`ALLOW_DDL_OPERATION`(`@benborla29/mcp-server-mysql` 默认 SELECT-only)。缺一不可
- **凭据不进镜像**:`/home/node/.claude.json` 内仅 `${VAR}` 引用文本,可 `docker history` 抽验
- **网络前提**:容器需可达 MySQL(dev/beta)与 `api.figma.com`(figma 取数)

## 镜像地址与后台切换(R5)

- 代码默认镜像:`registry.cn-hangzhou.aliyuncs.com/zhanqinet/devbox:v2`(backend `container_service.DEFAULT_IMAGE`,probe 同步)
- 超管可在 **平台设置 → 全局参数 → 任务容器镜像**(`container_image` 设置项)改为任意带 tag 的镜像引用;**留空 = 回落默认**。改动仅影响之后新起的容器,存量/运行中容器不受影响
- Runner 机器需可 pull 该地址;私有命名空间需先 `docker login`

## 构建与推送

```bash
# 默认 marketplace(context=仓库根;免登录已实测)
docker build -t platform/devbox:v2 -f docker/devbox/Dockerfile .

# 换源/自定义 marketplace(仅构建期生效;不锁版本,跟随 marketplace 默认)
docker build -t platform/devbox:v2 \
  --build-arg RD_FLOW_MARKETPLACE=http://47.111.69.64/ai/rd-flow.git \
  -f docker/devbox/Dockerfile .

# 推送(按实际 registry 调整;推送后同步核对平台 container_image 设置/代码默认地址)
docker tag platform/devbox:v2 registry.cn-hangzhou.aliyuncs.com/zhanqinet/devbox:v2
docker push registry.cn-hangzhou.aliyuncs.com/zhanqinet/devbox:v2
```

不可达 marketplace 会**构建期显式失败**(docker RUN 默认行为,不静默跳过)。

## 容器内自检

```bash
docker run --rm --entrypoint bash platform/devbox:v2 -c "
  ls /home/node/.claude/skills/ &&
  claude plugin list | grep rd-flow &&
  node -e 'const k=Object.keys(JSON.parse(require(\"fs\").readFileSync(\"/home/node/.claude.json\")).mcpServers).sort().join(\",\");process.exit(k===\"brave-search,figma,filesystem,github,mysql_beta,mysql_dev\"?0:1)' &&
  echo OK"
```

预期输出 `OK`(skills 3 目录 / plugin 可见 / mcpServers 6 键集合正确)。

## 相关文档

- 计划与决策:[docs/20260927_devbox默认skills与mcp/DEVPLAN.md](../../docs/20260927_devbox默认skills与mcp/DEVPLAN.md)
- 发布动作(migration / 运营清单):[docs/20260927_devbox默认skills与mcp/DEPLOY.md](../../docs/20260927_devbox默认skills与mcp/DEPLOY.md)
