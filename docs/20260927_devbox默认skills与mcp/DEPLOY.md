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

> 说明:以下清单由 R2 轮次补充/最终确认(本 R1 轮仅占位保留,不随 R1 验收)。

- **类型**:配置(运营动作,零代码)
- **具体内容**:超管在平台设置页「自定义变量」配置以下变量(键名/值规范沿用现有校验:值 ≤2048、不占 13 个保留键):

  | 变量名 | 必填 | 说明 |
  |---|---|---|
  | ENV_MCP_MYSQL_DEV_HOST | 是 | dev 库主机 |
  | ENV_MCP_MYSQL_BETA_HOST | 是 | beta 库主机 |
  | ENV_MCP_MYSQL_PORT | 是 | 端口(dev/beta 共用;未配时容器侧 :-3306 兜底) |
  | ENV_MCP_MYSQL_USER | 是 | 账号(共用,**需 DBA 授予只读权限**) |
  | ENV_MCP_MYSQL_PASSWORD | 是 | 密码(共用) |
  | ENV_MCP_MYSQL_DATABASE | 是 | 默认库(共用) |
  | ENV_MCP_FIGMA_TOKEN | 否 | Figma personal access token(未配则 figma MCP 不可用) |
  | ENV_MCP_GITHUB_TOKEN | 否 | GitHub PAT(未配则 github MCP 不可用;2026-09-27 plan 补充确认) |
  | ENV_MCP_BRAVE_API_KEY | 否 | Brave Search API key(未配则 brave MCP 不可用;2026-09-27 plan 补充确认) |

- **前提(平台外运营)**:MySQL 账号需 DBA 侧授予只读权限(SELECT/SHOW)——只读第一道防线(D2)
- **影响范围**:配置后所有新起任务容器自动注入;缺变量静默降级(容器创建/任务执行不受阻)
- **回滚方案**:删除对应变量即可(下次创建容器不再注入)
