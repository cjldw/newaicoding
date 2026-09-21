# DEPLOY.md — 发布变更清单

> 由 `/rd-dev` 阶段追加,`/rd-ship` 上线阶段统一消费。SQL 均为可直接执行全文。

## 2026-09-21 R1 用户与账号体系

- **类型**:数据库 + 配置 + 依赖

### 1. 数据库(全文可直接执行)

> 开发库(120.27.217.194:3306/aicoding)已通过 alembic 执行同等变更(migration `2c13321fa03e` 建表 + `b7e2a1c3d4f5` 加列,本 DDL 已合并两步)。

```sql
CREATE TABLE IF NOT EXISTS `users` (
  `id`                     BIGINT        NOT NULL AUTO_INCREMENT COMMENT '内部自增ID',
  `user_id`                CHAR(36)      NOT NULL                COMMENT '对外UUID(业务主键)',
  `phone`                  VARCHAR(11)   NOT NULL                COMMENT '手机号(登录名)',
  `password_hash`          VARCHAR(255)  NOT NULL                COMMENT 'bcrypt密码哈希(cost=12)',
  `nickname`               VARCHAR(32)   DEFAULT NULL            COMMENT '显示名',
  `avatar_url`             VARCHAR(255)  DEFAULT NULL            COMMENT '头像URL',
  `status`                 ENUM('active','disabled')
                                         NOT NULL DEFAULT 'active'  COMMENT '状态: active-正常 / disabled-禁用',
  `role`                   ENUM('superadmin','user')
                                         NOT NULL DEFAULT 'user'    COMMENT '平台角色: superadmin-超管 / user-普通用户',
  `token_version`          INT           NOT NULL DEFAULT 0      COMMENT '会话版本号(登录/改密/禁用时+1,使旧 token 立即失效)',
  `login_fail_count`       INT           NOT NULL DEFAULT 0      COMMENT '连续登录失败次数(达5次触发锁定)',
  `locked_until`           DATETIME      DEFAULT NULL            COMMENT '锁定截止时间(null表示未锁定)',
  `gitlab_username`        VARCHAR(64)   DEFAULT NULL            COMMENT 'GitLab用户名',
  `gitlab_token_encrypted` TEXT          DEFAULT NULL            COMMENT 'AES-256-GCM加密的GitLab Personal Access Token',
  `gitlab_token_scopes`    JSON          DEFAULT NULL            COMMENT 'GitLab token scope列表,如["api","read_user"]',
  `gitlab_token_bound_at`  DATETIME      DEFAULT NULL            COMMENT 'GitLab token绑定时间',
  `created_at`             DATETIME      NOT NULL DEFAULT (NOW()) COMMENT '创建时间',
  `updated_at`             DATETIME      NOT NULL DEFAULT (NOW()) ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_user_id` (`user_id`),
  UNIQUE KEY `uk_phone`    (`phone`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
  COMMENT='R1 - 用户表';
```

- **影响范围**:`aicoding.users`(新增表;后续需求点复用)
- **回滚方案**:`DROP TABLE IF EXISTS users;`(上线窗口内回滚;一旦有业务数据改用归档表)

### 2. 配置 / 环境变量(backend/.env,不入库;仓库留 .env.example)

| 变量 | 值(开发环境) | 说明 |
|---|---|---|
| DATABASE_URL | `mysql+asyncmy://develop:Develop%40123@120.27.217.194:3306/aicoding?charset=utf8mb4` | 密码含 `@` 需 URL 编码为 `%40` |
| REDIS_URL | `redis://121.43.42.203:6379/0` | R1 仅占位,未使用 |
| PLATFORM_SECRET_KEY | 64 位 hex(开发随机值,见 backend/.env) | AES-256-GCM 密钥;**生产必须更换** |
| JWT_SECRET_KEY | 64 位 hex(开发随机值,见 backend/.env) | JWT 签名;**生产必须更换** |
| JWT_ACCESS_TOKEN_EXPIRE_MINUTES | 120 | access 2h |
| JWT_REFRESH_TOKEN_EXPIRE_DAYS | 7 | refresh 7d |
| ENVIRONMENT | development | - |

- **影响范围**:后端全部服务的配置读取(pydantic-settings)
- **回滚方案**:无需回滚(纯新增配置项)
- **安全提示**:真实密钥不写入本文件,以部署机 `.env` 为准;上线时由 `/rd-ship` 重新生成生产密钥

### 3. 依赖

- 后端(backend/pyproject.toml):fastapi / uvicorn[standard] / sqlalchemy[asyncio] / asyncmy / alembic / pydantic / pydantic-settings / pyjwt / passlib[bcrypt] / bcrypt>=4.0,<5.0(**5.x 与 passlib 1.7.4 不兼容,已锁定 4.x**) / cryptography / httpx / python-multipart;dev:pytest / pytest-asyncio / ruff
- 前端(frontend/package.json):react18 / react-router-dom v6 / @tanstack/react-query / zustand / react-hook-form / zod / @hookform/resolvers / tailwindcss 3.4 / lucide-react(详见 package.json)
- **回滚方案**:随代码回滚 package-lock / pyproject

## 2026-09-21 R2 项目管理(绑定 GitLab,支持多仓库)

- **类型**:数据库(alembic revision `a7d21c9e5f40`,down_revision `b7e2a1c3d4f5`)
- **具体内容**:

  ```sql
  -- 1. 项目表
  CREATE TABLE IF NOT EXISTS `projects` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `project_id` CHAR(36) NOT NULL COMMENT '对外UUID',
    `name` VARCHAR(64) NOT NULL COMMENT '显示名(同用户下唯一由服务层校验)',
    `slug` VARCHAR(64) NOT NULL COMMENT '全局唯一,小写字母数字-,子域/主仓库名',
    `description` VARCHAR(255) NULL DEFAULT '' COMMENT '描述',
    `default_branch` VARCHAR(64) NOT NULL DEFAULT 'master' COMMENT '项目默认分支',
    `visibility` ENUM('private','internal') NOT NULL DEFAULT 'private' COMMENT '可见性',
    `owner_id` CHAR(36) NOT NULL COMMENT '创建者 user_id',
    `status` ENUM('active','archived','deleted') NOT NULL DEFAULT 'active' COMMENT '状态',
    `mcp_config_encrypted` TEXT NULL COMMENT 'AES-GCM 加密的项目级 MCP 配置(R17 用)',
    `deleted_at` DATETIME NULL COMMENT '软删时间(7 天后物理删除定时任务用)',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uq_projects_project_id` (`project_id`),
    UNIQUE KEY `uq_projects_slug` (`slug`),
    KEY `ix_projects_owner_id` (`owner_id`),
    KEY `ix_projects_status` (`status`)
  ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='项目表';

  -- 2. 项目-仓库关联表(main 每项目唯一由服务层保证:MySQL 无部分唯一索引;
  --    同 repo 不可重复绑定由 uq_project_gitlab_repo 硬保证)
  CREATE TABLE IF NOT EXISTS `project_repos` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `repo_id` CHAR(36) NOT NULL COMMENT '平台内部对外UUID',
    `project_id` CHAR(36) NOT NULL COMMENT '项目 id',
    `role` ENUM('main','test','docs','other') NOT NULL COMMENT '仓库角色',
    `gitlab_repo_url` VARCHAR(255) NOT NULL COMMENT 'GitLab 仓库 URL',
    `gitlab_repo_id` INT NOT NULL COMMENT 'GitLab 内部 id',
    `gitlab_bind_type` ENUM('auto','manual') NOT NULL DEFAULT 'auto' COMMENT '绑定方式',
    `created_by` CHAR(36) NOT NULL COMMENT '绑定时操作人 user_id',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '绑定时间',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uq_project_repos_repo_id` (`repo_id`),
    UNIQUE KEY `uq_project_gitlab_repo` (`project_id`,`gitlab_repo_id`),
    KEY `ix_project_repos_project_id` (`project_id`),
    KEY `ix_project_repos_project_role` (`project_id`,`role`)
  ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='项目-仓库关联表';

  -- 3. 平台设置单例键值表(敏感项 AES-256-GCM 加密后存 JSON)
  CREATE TABLE IF NOT EXISTS `platform_settings` (
    `key` VARCHAR(64) NOT NULL COMMENT '配置键(白名单枚举)',
    `value` JSON NOT NULL COMMENT '配置值;敏感项存 {"__encrypted": "<base64>"}',
    `updated_by` CHAR(36) NOT NULL COMMENT '最近修改人(超管)',
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`key`)
  ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='平台设置表';
  ```

- **影响范围**:R2 项目管理全部接口;项目创建前置依赖 `platform_settings` 配置 `gitlab_url` / `gitlab_bot_token`(未配置返回 2001,项目创建入口禁用)
- **上线后配置动作**:超管登录 → 平台管理 → 平台设置,录入 `gitlab_url` / `gitlab_bot_token`(scope=api)/ `gitlab_bot_group_id`(auto 建仓必配)/ `gitlab_webhook_secret`;两个根域名 `preview_base_domain` / `deploy_base_domain` 有默认值可不配
- **回滚方案**:`DROP TABLE platform_settings; DROP TABLE project_repos; DROP TABLE projects;`(顺序不可反,注意先备份)

## 2026-09-21 R12 项目成员与协作

- **类型**:数据库(alembic revision `c2e8b4d7a910`,down_revision `a7d21c9e5f40`)
- **具体内容**:

  ```sql
  CREATE TABLE IF NOT EXISTS `project_members` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `project_id` CHAR(36) NOT NULL COMMENT '项目 id',
    `user_id` CHAR(36) NOT NULL COMMENT '用户 id',
    `role` ENUM('owner','editor','viewer') NOT NULL DEFAULT 'viewer' COMMENT '角色',
    `invited_by` CHAR(36) NOT NULL COMMENT '邀请人 user_id',
    `joined_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '加入时间',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uq_project_member_user` (`project_id`,`user_id`),
    KEY `ix_project_members_project_id` (`project_id`),
    KEY `ix_project_members_user_id` (`user_id`)
  ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='项目成员表';
  ```

- **影响范围**:R12 成员管理接口;R2 项目接口权限判定升级(查看=成员,追加绑定仓库=editor+,其余 owner;超管=虚拟 owner 不落成员行);新增 GET /api/users/search(手机号精确搜索)
- **回滚方案**:`DROP TABLE project_members;`(并回退 R2 接口权限判定相关代码)

## 2026-09-22 R13 模型接入(项目级 url+key)

- **类型**:数据库(alembic revision `d4f9a1e2b6c8`,down_revision `c2e8b4d7a910`)
- **具体内容**:

  ```sql
  CREATE TABLE IF NOT EXISTS `model_configs` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `config_id` CHAR(36) NOT NULL COMMENT '对外UUID',
    `project_id` CHAR(36) NOT NULL COMMENT '项目 id',
    `name` VARCHAR(64) NOT NULL COMMENT '配置名',
    `base_url` VARCHAR(255) NOT NULL COMMENT 'OpenAI 兼容 endpoint',
    `api_key_encrypted` TEXT NOT NULL COMMENT 'AES-GCM 加密的 api_key',
    `model` VARCHAR(64) NOT NULL COMMENT '模型名',
    `is_default` TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否默认(同项目最多一个,服务层保证)',
    `enabled` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否启用',
    `created_by` CHAR(36) NOT NULL COMMENT '创建者 user_id',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uq_model_configs_config_id` (`config_id`),
    UNIQUE KEY `uq_model_config_name` (`project_id`,`name`),
    KEY `ix_model_configs_project_id` (`project_id`)
  ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='项目级模型配置表';
  ```

- **影响范围**:R13 模型配置接口(5 个);llm_service.resolve_config 供 R4/R5 任务执行消费;LLM_ENV_KEYS 契约供 R8 容器 env 注入消费
- **回滚方案**:`DROP TABLE model_configs;`

## 2026-09-22 R17 MCP server 与 Skills 管理

- **类型**:数据库(alembic revision `e5a8c3f1d2b7`,down_revision `d4f9a1e2b6c8`)+ 容器镜像
- **数据库**:

  ```sql
  CREATE TABLE IF NOT EXISTS `skills` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `skill_id` CHAR(36) NOT NULL COMMENT '对外UUID',
    `name` VARCHAR(64) NOT NULL COMMENT 'Skill 名(kebab-case)',
    `description` VARCHAR(255) NOT NULL COMMENT '一句话描述',
    `content` TEXT NOT NULL COMMENT 'Markdown 正文(YAML frontmatter + 正文)',
    `scope` ENUM('platform','project') NOT NULL DEFAULT 'platform' COMMENT '作用域',
    `project_id` CHAR(36) NULL COMMENT 'scope=project 时必填',
    `created_by` CHAR(36) NOT NULL COMMENT '创建者 user_id',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uq_skills_skill_id` (`skill_id`),
    KEY `ix_skills_scope` (`scope`),
    KEY `ix_skills_project_id` (`project_id`),
    KEY `ix_skills_scope_project_name` (`scope`,`project_id`,`name`)
  ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Skills 表';

  CREATE TABLE IF NOT EXISTS `project_skills` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `project_id` CHAR(36) NOT NULL COMMENT '项目 id',
    `skill_id` CHAR(36) NOT NULL COMMENT 'Skill id',
    `installed_by` CHAR(36) NOT NULL COMMENT '安装人 user_id',
    `installed_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '安装时间',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uq_project_skill` (`project_id`,`skill_id`),
    KEY `ix_project_skills_project_id` (`project_id`),
    KEY `ix_project_skills_skill_id` (`skill_id`)
  ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='项目-Skill 安装关联表';
  ```

  注:`projects.mcp_config_encrypted` 列已随 R2 建表存在,本点无 ALTER。
- **容器镜像**:`docker/devbox/Dockerfile`(预装 5 个 MCP server + 3 个官方 Skills 到 `/home/codespace/.claude/skills/`),上线时构建 `platform/devbox:v1` 并推送镜像仓库
- **影响范围**:R17 全部接口;R8 任务创建时消费 `mcp_service.get_decrypted_config` 与 `skill_service.list_project_skill_contents` 注入容器
- **回滚方案**:`DROP TABLE project_skills; DROP TABLE skills;`(顺序不可反);镜像回退旧 tag

## 2026-09-22 R8 任务级容器(执行沙箱,Runner 架构)

- **类型**:数据库(alembic revision `f6b9d2e4a1c3`,down_revision `e5a8c3f1d2b7`)+ 新组件(Runner)
- **数据库**:

  ```sql
  CREATE TABLE IF NOT EXISTS `containers` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `container_id` VARCHAR(64) NOT NULL COMMENT 'Runner 上的 docker id',
    `task_id` CHAR(36) NULL COMMENT '任务 id(部署中容器可空)',
    `runner_id` CHAR(36) NOT NULL COMMENT '运行该容器的 Runner id',
    `project_id` CHAR(36) NOT NULL COMMENT '项目 id',
    `status` ENUM('creating','running','stopped','failed','destroyed') NOT NULL DEFAULT 'creating' COMMENT '状态',
    `image` VARCHAR(255) NOT NULL DEFAULT 'platform/devbox:v1' COMMENT '镜像',
    `cpu_limit` VARCHAR(16) NOT NULL DEFAULT '2c' COMMENT 'CPU 限制',
    `mem_limit` VARCHAR(16) NOT NULL DEFAULT '4g' COMMENT '内存限制',
    `disk_limit` VARCHAR(16) NOT NULL DEFAULT '10g' COMMENT '磁盘限制',
    `exposed_ports` JSON NOT NULL COMMENT '容器内端口列表 [5173, 8000]',
    `runner_host_port_5173` BIGINT UNSIGNED NULL COMMENT '映射到 5173 的宿主机端口',
    `runner_host_port_8000` BIGINT UNSIGNED NULL COMMENT '映射到 8000 的宿主机端口',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `destroyed_at` DATETIME NULL COMMENT '销毁时间',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uq_containers_container_id` (`container_id`),
    KEY `ix_containers_task_id` (`task_id`),
    KEY `ix_containers_runner_id` (`runner_id`),
    KEY `ix_containers_project_id` (`project_id`),
    KEY `ix_containers_status` (`status`)
  ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='任务容器表';
  ```

- **新组件**:仓库 `runner/` 目录(Runner 主进程 + Docker SDK 容器管理);依赖 `docker`/`websockets`(仅 Runner 机器安装,见 runner/requirements.txt,不入平台 pyproject)
- **配置新增**:`RUNNER_TOKEN`(Runner 接入共享密钥,R8 最小版,R16 升级 per-runner token);`RUNNER_PORT_RANGE_*`(端口映射范围)
- **影响范围**:R8 平台调度/回报处理;R4 任务执行将调用 `container_service.schedule_and_start`;网关(R15)直连 `runner_host:mapped_port`
- **上线动作**:① 构建镜像 `platform/devbox:v1`(docker/devbox/Dockerfile)推仓库;② Runner 机器部署 runner/ 并配置 PLATFORM_URL/RUNNER_TOKEN/RUNNER_ID/RUNNER_ROLE/RUNNER_HOST
- **回滚方案**:`DROP TABLE containers;`;Runner 停进程即可(平台标记 Runner offline)

## 2026-09-22 R16 Runner 管理(分布式容器执行)

- **类型**:数据库(alembic revision `a9c1e5f7b2d4`,down_revision `f6b9d2e4a1c3`)+ 配置变更
- **数据库**:

  ```sql
  CREATE TABLE IF NOT EXISTS `runners` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `runner_id` CHAR(36) NOT NULL COMMENT '对外UUID',
    `name` VARCHAR(64) NOT NULL COMMENT 'Runner 名',
    `role` ENUM('worker','deploy') NOT NULL DEFAULT 'worker' COMMENT '角色',
    `token_hash` VARCHAR(255) NOT NULL COMMENT 'Runner token bcrypt hash(不存明文)',
    `status` ENUM('online','offline','disabled') NOT NULL DEFAULT 'offline' COMMENT '状态',
    `last_heartbeat_at` DATETIME NULL COMMENT '最后心跳时间',
    `machine_info` JSON NULL COMMENT '{os,arch,cpu_count,mem_total_gb,docker_version}',
    `current_containers` INT NOT NULL DEFAULT 0 COMMENT '当前运行容器数',
    `max_containers` INT NOT NULL DEFAULT 10 COMMENT '最大容器数',
    `public_ip` VARCHAR(64) NULL COMMENT 'deploy Runner 公网 IP',
    `created_by` CHAR(36) NOT NULL COMMENT '创建者超管 user_id',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uq_runners_runner_id` (`runner_id`),
    UNIQUE KEY `uq_runners_name` (`name`),
    KEY `ix_runners_role` (`role`),
    KEY `ix_runners_status` (`status`)
  ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Runner 注册表';
  ```

- **配置变更**:`RUNNER_TOKEN` 共享密钥已废弃(R8 过渡方案)——改为超管在 Runner 管理页创建 per-runner token(plt-runner-*,bcrypt 存储,仅显示一次);部署 Runner 时使用新流程
- **镜像**:`docker/runner/Dockerfile` 构建 `platform/runner:v1`
- **影响范围**:R8 调度切换为 DB 注册表(pick_runner_db);WS /ws/runner 注册协议升级(token+machine_info 注册/心跳时间戳/恢复对账 sync);main.py 增加每 60s 心跳超时巡检任务
- **回滚方案**:`DROP TABLE runners;` + 回退 R8 版 WS 鉴权代码
