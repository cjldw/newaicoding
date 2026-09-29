# DEPLOY:devbox 镜像默认 rd-flow plugin 与 MySQL/Figma MCP 预装

> 消费方:/rd-ship 上线阶段统一执行。以下均为**发布时需要额外动作**的条目;纯代码改动不在此列。

## 2026-09-27 R1/R2 devbox 镜像 v2 构建与推送

- **类型**:依赖 / 配置(镜像)
- **具体内容**:
  ```bash
  # 仓库根为构建 context;tag 升 v2(D5 拍板),marketplace 地址可覆盖(R1 分片 ARG)
  docker build -t platform/devbox:v2 \
    --build-arg RD_FLOW_MARKETPLACE=http://47.111.69.64/ai/rd-flow.git \
    -f docker/devbox/Dockerfile .
  # 等效:不传 ARG 用镜像内默认地址(与上一行同值)
  docker build -t platform/devbox:v2 -f docker/devbox/Dockerfile .
  docker push <registry>/platform/devbox:v2   # 按实际 registry 调整
  ```
  - 构建机要求:可访问 marketplace 地址(git 可达);无需任何 Anthropic 凭据(免登录已实测)
  - ARG 用法:`RD_FLOW_MARKETPLACE` 仅构建期生效,换源/升级=重建镜像(不锁版本,跟随 marketplace 默认)
- **影响范围**:所有新起任务容器(存量 v1 容器不受影响,跑完销毁)
- **回滚方案**:存量常量回退涉及 6 处代码 + migration downgrade;镜像层回滚=重新以 v1 Dockerfile 构建推 v2 前 tag(或保留 v1 镜像不删,改回常量)

## 2026-09-27 R1 containers.image 列默认变更

- **类型**:数据库
- **具体内容**(MySQL;alembic migration 已落地:`backend/alembic/versions/e9b3f7c1a6d4_r1_container_image_default_v2.py`,down_revision=`9c7762778c30`;本条为等效 SQL):
  ```sql
  ALTER TABLE containers ALTER COLUMN image SET DEFAULT 'platform/devbox:v2';
  ```
  执行方式:`alembic upgrade head`(开发库 upgrade/downgrade 验证后随发布执行;仅列默认元数据操作,存量行 image 值不改)
- **影响范围**:仅列默认值;**存量行 image 值不改**(存量 v1 容器自然销毁,D5 拍板);应用层 default 同步改,双写一致
- **回滚方案**:`alembic downgrade -1`(或 `alembic downgrade 9c7762778c30`;等效 SQL `ALTER TABLE containers ALTER COLUMN image SET DEFAULT 'platform/devbox:v1';`,恢复 v1 默认)

## 2026-09-27 R2 运营配置:平台「自定义变量」新增 MCP 凭据变量

> 2026-09-27 R2 已落实(本节自 R1 占位转正式):预置 MCP 配置已随镜像构建期写入容器 `/home/node/.claude.json`(顶层 `mcpServers` 恰 6 条:mysql_dev / mysql_beta / figma / filesystem / github / brave-search,内容与 `DEVPLAN/R2.md`「接口契约」交付物 JSON 逐字一致;文件内仅 `${VAR}` 引用文本,凭据不进镜像)。本节为其配套运营动作,发布时需执行。

- **类型**:配置(运营动作,零代码)
- **具体内容**:超管在平台设置页「自定义变量」配置以下变量(键名/值规范沿用现有校验:键名 `^[A-Za-z_][A-Za-z0-9_]*$`、≤50 键、值 ≤2048、不占 13 个保留键):

  | 变量名 | 必填 | 说明 |
  |---|---|---|
  | ENV_MCP_MYSQL_DEV_HOST | 是 | dev 库主机 |
  | ENV_MCP_MYSQL_BETA_HOST | 是 | beta 库主机 |
  | ENV_MCP_MYSQL_PORT | 是 | 端口(dev/beta 共用;配置侧带 :-3306 兜底) |
  | ENV_MCP_MYSQL_USER | 是 | 账号(共用,需只读权限) |
  | ENV_MCP_MYSQL_PASSWORD | 是 | 密码(共用) |
  | ENV_MCP_MYSQL_DATABASE | 是 | 默认库(共用) |
  | ENV_MCP_FIGMA_TOKEN | 否 | Figma API token(未配则 figma MCP 不可用) |
  | ENV_MCP_GITHUB_TOKEN | 否 | GitHub PAT(未配则 github MCP 静默降级) |
  | ENV_MCP_BRAVE_API_KEY | 否 | Brave Search API key(未配则 brave MCP 静默降级) |

  - 末两行为 plan 阶段补充确认变量(2026-09-27 用户拍板)——存量 github/brave-search 激活必须有凭据源
  - 注:预置配置内 MySQL 密码字段是 `MYSQL_PASS`(包约定),平台变量名是 `ENV_MCP_MYSQL_PASSWORD`,二者经 `${VAR}` 引用衔接,勿混

- **前提(平台外运营,DBA)**:MySQL 账号(dev/beta 两库)需 DBA 侧授予只读权限(SELECT/SHOW)——只读第一道防线(D2);第二道防线=镜像预置条目故意不设 ALLOW_INSERT/UPDATE/DELETE/DDL_OPERATION(`@benborla29/mcp-server-mysql` 默认 SELECT-only),双保险缺一不可。Figma 取数需容器可达 api.figma.com
- **静默降级**:任一变量未配置时,对应 MCP 条目仍保留在预置配置中(不裁剪),`${VAR}` 未设按字面透传+告警,该 server 启动/连接失败——**容器创建与任务执行不受阻**,仅对话中使用对应 MCP 时报连接失败(github/brave-search 未配 token 时可启动但调用报错)。补配变量后新起容器即生效
- **影响范围**:配置后所有新起任务容器自动注入(custom_env_vars 铺底 → 容器 environment,预置配置加载拉起 server 时按当时容器 env 实时展开 `${VAR}`);存量 v1 容器不受影响(无预置配置)
- **回滚方案**:删除对应变量即可(下次创建容器不再注入;预置配置条目不随之删除,转入静默降级态)

## 2026-09-28 R5 containers.image 列默认切 aliyun registry + container_image 设置项

- **类型**:数据库 + 配置(运营动作)
- **具体内容**(MySQL;alembic migration 已落地:`backend/alembic/versions/b4f8e2a9c1d7_container_image_default_aliyun.py`,down_revision=`e9b3f7c1a6d4`;本条为等效 SQL):
  ```sql
  ALTER TABLE containers ALTER COLUMN image SET DEFAULT 'registry.cn-hangzhou.aliyuncs.com/zhanqinet/devbox:v2';
  ```
  执行方式:`alembic upgrade head`(仅列默认元数据操作,存量行 image 值不改)
- **container_image 设置项**:超管后台「全局参数」组新增「任务容器镜像」;值须为**带 tag** 的 docker 引用(≤255)。镜像解析链:`显式传参 > container_image 设置 > 代码默认(同上行 aliyun 地址)`;**留空 = 未配置回落默认**(前端不发空串)。probe 采集(系统级 skills/MCP 列表)走同一设置
- **生效语义**:镜像在容器创建时刻定格——改设置/默认值只影响之后新起的容器,存量与运行中容器不受影响
- **前提(平台外运营)**:Runner 机器需可 pull `registry.cn-hangzhou.aliyuncs.com/zhanqinet/devbox:v2`(镜像已由用户推送);zhanqinet 命名空间若为私有,各 Runner 机需先 `docker login registry.cn-hangzhou.aliyuncs.com`
- **影响范围**:所有新起任务容器与 probe 临时容器
- **回滚方案**:`alembic downgrade -1`(列默认回退 `platform/devbox:v2`);设置项删除即转常量兜底(代码默认随发版已切 aliyun,如需回 v2 语义需回退代码)
