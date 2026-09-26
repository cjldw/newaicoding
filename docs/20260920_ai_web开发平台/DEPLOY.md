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

## 2026-09-22 R9 Web 终端(实时 TTY)

- **类型**:数据库(alembic revision `b3d7f9a1c5e2`,down_revision `a9c1e5f7b2d4`)+ 前端依赖
- **数据库**:

  ```sql
  CREATE TABLE IF NOT EXISTS `terminal_sessions` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `session_id` CHAR(36) NOT NULL COMMENT '对外UUID',
    `task_id` CHAR(36) NOT NULL COMMENT '任务 id',
    `container_id` VARCHAR(64) NOT NULL COMMENT '容器 id',
    `runner_id` CHAR(36) NOT NULL COMMENT 'Runner id',
    `shell` VARCHAR(64) NOT NULL DEFAULT '/bin/bash' COMMENT 'shell',
    `created_by` CHAR(36) NOT NULL COMMENT '创建者 user_id',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `closed_at` DATETIME NULL COMMENT '关闭时间',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uq_terminal_sessions_session_id` (`session_id`),
    KEY `ix_terminal_sessions_task_id` (`task_id`),
    KEY `ix_terminal_sessions_container_id` (`container_id`),
    KEY `ix_terminal_sessions_runner_id` (`runner_id`)
  ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='终端会话表';
  ```

- **前端依赖**:xterm@5.3.0 / xterm-addon-fit@0.8.0 / xterm-addon-web-links@0.6.0(package-lock 已更新)
- **影响范围**:R9 终端全链路(REST 会话 + WS /ws/terminal/{session_id} + Runner pty);R4/R5 消费 terminal_service.push_ai_output 推送 SDK 事件回显
- **回滚方案**:`DROP TABLE terminal_sessions;`(内存会话态自然消失)

## 2026-09-22 R10 实时预览(仅任务内)

- **类型**:数据库(alembic revision `c8e2a6d9f1b4`,down_revision `b3d7f9a1c5e2`)
- **数据库**:

  ```sql
  CREATE TABLE IF NOT EXISTS `routes` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `route_id` CHAR(36) NOT NULL COMMENT '对外UUID',
    `host` VARCHAR(255) NOT NULL COMMENT '匹配 Host(Host 精确匹配)',
    `upstream` VARCHAR(255) NOT NULL COMMENT '上游 http://{runner_host}:{mapped_port}',
    `type` ENUM('preview','deploy') NOT NULL DEFAULT 'preview' COMMENT '路由类型',
    `task_id` CHAR(36) NULL COMMENT '任务 id',
    `project_id` CHAR(36) NOT NULL COMMENT '项目 id',
    `port` INT NOT NULL COMMENT '容器内端口',
    `status` ENUM('active','inactive') NOT NULL DEFAULT 'inactive' COMMENT '状态',
    `auth_required` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否需要鉴权',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uq_routes_route_id` (`route_id`),
    UNIQUE KEY `uq_routes_host` (`host`),
    KEY `ix_routes_task_id` (`task_id`),
    KEY `ix_routes_project_id` (`project_id`),
    KEY `ix_routes_type_status` (`type`,`status`)
  ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='网关路由表(R10 预览 / R15 网关 / R7 部署共用)';
  ```

- **影响范围**:R10 预览链路(Runner 端口探测回报 → 路由注册);R15 网关消费 route_service;R7 部署路由复用本表(type=deploy);容器销毁自动摘除预览路由
- **上线动作**:预览/部署泛域名 `*.{preview_base_domain}` / `*.{deploy_base_domain}` DNS A 记录指向网关(R15)
- **回滚方案**:`DROP TABLE routes;`

## 2026-09-22 R11 在线编辑器(双模式)

- **类型**:前端依赖(无数据库变更——文件树/内容实时读容器或 GitLab API,无持久化)
- **前端依赖**:@monaco-editor/react / react-diff-viewer-continued(package-lock 已更新)
- **容器镜像变更**:docker/devbox/Dockerfile 追加 `inotify-tools`(R11 文件 watcher 依赖;未装则 watcher 静默降级,前端手动刷新兜底)——需重新构建 `platform/devbox:v1`
- **影响范围**:R11 文件 API 8 个(项目模式只读 GitLab 浏览/任务模式容器文件 CRUD/Diff/变更清单 Q27/watcher WS 频道);Runner 新增 file_manager 消息处理(file_list/read_file/write_file/file_op/git_diff/git_changes,req_id 请求-响应协议)
- **回滚方案**:无 DB 回滚;镜像回退旧 tag(watcher 降级不影响主流程)

## 2026-09-22 R15 平台网关与域名

- **类型**:新组件(网关;routes 表已随 R10 建表,无新迁移)
- **新组件**:仓库 `gateway/` 目录(自研 Python 反向代理:`backend/app/core/gateway.py` 核心 + `gateway/main.py` 独立进程入口)
- **影响范围**:预览/部署域名流量入口;preview 鉴权(JWT+项目成员)/deploy 公开;WebSocket 透传(HMR/TTY);单 host QPS 限流(默认 100);404/403/502 异常页(带项目名与日志链接)
- **上线动作**:
  1. 网关进程部署:`GATEWAY_PORT=80 python3 gateway/main.py`(依赖 backend app 代码与 DATABASE_URL,实时查 routes 表)
  2. DNS:泛域名 `*.{preview_base_domain}` 与 `*.{deploy_base_domain}` A 记录指向网关
  3. 平台设置确认 `preview_base_domain` / `deploy_base_domain`(变更仅影响后续注册路由)
- **决策留痕**:V1 自研 Python 网关替代 Nginx/Traefik(动态路由直查 routes 表即时生效,无需 reload);HTTPS/CDN/WAF 范围外
- **回滚方案**:停网关进程回退代码;无 DB 变更

## 2026-09-22 R3 需求管理与打磨

- **类型**:数据库(alembic revision `d9b4f8e2a6c1`,down_revision `c8e2a6d9f1b4`)
- **数据库**:

  ```sql
  CREATE TABLE IF NOT EXISTS `requirements` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `req_id` CHAR(36) NOT NULL COMMENT '对外UUID',
    `project_id` CHAR(36) NOT NULL COMMENT '项目 id',
    `title` VARCHAR(128) NOT NULL COMMENT '标题',
    `background` TEXT NULL COMMENT '背景(Markdown)',
    `description` TEXT NOT NULL COMMENT '描述(Markdown)',
    `acceptance_criteria` TEXT NULL COMMENT '验收标准(Markdown)',
    `req_branch` VARCHAR(64) NOT NULL COMMENT '需求分支名',
    `prd_file_path` VARCHAR(255) NOT NULL DEFAULT '' COMMENT 'PRD repo 内路径(Q26 规则生成)',
    `status` ENUM('draft','polishing','reviewing','approved','in_progress','done','archived','rejected') NOT NULL DEFAULT 'draft' COMMENT '状态',
    `priority` ENUM('low','medium','high') NOT NULL DEFAULT 'medium' COMMENT '优先级',
    `created_by` CHAR(36) NOT NULL COMMENT '创建者 user_id',
    `reviewed_by` CHAR(36) NULL COMMENT '评审人 user_id',
    `reviewed_at` DATETIME NULL COMMENT '评审时间',
    `reject_reason` TEXT NULL COMMENT '驳回理由',
    `polish_task_id` CHAR(36) NULL COMMENT '当前打磨任务 id',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uq_requirements_req_id` (`req_id`),
    KEY `ix_requirements_project_id` (`project_id`),
    KEY `ix_requirements_req_branch` (`req_branch`),
    KEY `ix_requirements_status` (`status`),
    KEY `ix_requirements_created_by` (`created_by`)
  ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='需求表';
  ```

- **影响范围**:R3 需求全链路(状态机 draft→polishing→reviewing→approved;打磨容器经 R8 拉起;PRD 路径 Q26 规则)
- **回滚方案**:`DROP TABLE requirements;`

## 2026-09-22 R4 任务(统一执行单元)

- **类型**:数据库(alembic revision `e1f6b3a8d5c2`,down_revision `d9b4f8e2a6c1`)+ 前端依赖
- **数据库**:

  ```sql
  CREATE TABLE IF NOT EXISTS `tasks` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `task_id` CHAR(36) NOT NULL COMMENT '对外UUID',
    `req_id` CHAR(36) NOT NULL COMMENT '需求 id',
    `project_id` CHAR(36) NOT NULL COMMENT '项目 id',
    `type` ENUM('requirement','dev','test','release') NOT NULL COMMENT '任务类型',
    `title` VARCHAR(128) NOT NULL COMMENT '标题',
    `description` TEXT NOT NULL COMMENT '描述(AI 输入)',
    `base_branch` VARCHAR(64) NOT NULL COMMENT '基础分支',
    `work_branch` VARCHAR(64) NOT NULL COMMENT '工作分支',
    `status` ENUM('pending','running','done','failed','cancelled','timeout') NOT NULL DEFAULT 'pending' COMMENT '状态',
    `container_id` VARCHAR(64) NULL COMMENT '任务运行时 docker id',
    `runner_id` CHAR(36) NULL COMMENT 'Runner id',
    `conversation_id` CHAR(36) NOT NULL COMMENT 'Claude 会话 id',
    `created_by` CHAR(36) NOT NULL COMMENT '创建者 user_id',
    `started_at` DATETIME NULL COMMENT '开始时间',
    `finished_at` DATETIME NULL COMMENT '完成时间',
    `total_tokens_in` INT NOT NULL DEFAULT 0 COMMENT '输入 token',
    `total_tokens_out` INT NOT NULL DEFAULT 0 COMMENT '输出 token',
    `error_message` TEXT NULL COMMENT '错误信息',
    `last_commit_sha` VARCHAR(40) NULL COMMENT '最后 commit sha',
    `extended_attributes` JSON NULL COMMENT '扩展属性',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uq_tasks_task_id` (`task_id`),
    KEY `ix_tasks_req_id` (`req_id`),
    KEY `ix_tasks_project_id` (`project_id`),
    KEY `ix_tasks_type` (`type`),
    KEY `ix_tasks_status` (`status`),
    KEY `ix_tasks_container_id` (`container_id`),
    KEY `ix_tasks_runner_id` (`runner_id`),
    KEY `ix_tasks_created_by` (`created_by`)
  ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='任务表';

  CREATE TABLE IF NOT EXISTS `task_uploaded_files` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `file_id` CHAR(36) NOT NULL COMMENT '对外UUID',
    `task_id` CHAR(36) NOT NULL COMMENT '任务 id',
    `filename` VARCHAR(255) NOT NULL COMMENT '原始文件名',
    `stored_filename` VARCHAR(255) NOT NULL COMMENT '容器内实际文件名',
    `size` BIGINT UNSIGNED NOT NULL COMMENT '字节',
    `mime_type` VARCHAR(64) NOT NULL DEFAULT 'application/octet-stream' COMMENT 'MIME',
    `container_path` VARCHAR(255) NOT NULL COMMENT '容器内路径',
    `uploaded_by` CHAR(36) NOT NULL COMMENT '上传者 user_id',
    `uploaded_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '上传时间',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uq_task_uploaded_files_file_id` (`file_id`),
    KEY `ix_task_uploaded_files_task_id` (`task_id`)
  ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='任务附件表';

  CREATE TABLE IF NOT EXISTS `task_messages` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `message_id` CHAR(36) NOT NULL COMMENT '对外UUID',
    `task_id` CHAR(36) NOT NULL COMMENT '任务 id',
    `role` ENUM('user','assistant','tool') NOT NULL COMMENT '角色',
    `content` TEXT NOT NULL COMMENT '内容(Markdown)',
    `file_refs` JSON NULL COMMENT '文件引用',
    `tool_calls` JSON NULL COMMENT '工具调用',
    `tokens_in` INT NOT NULL DEFAULT 0 COMMENT '输入 token',
    `tokens_out` INT NOT NULL DEFAULT 0 COMMENT '输出 token',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uq_task_messages_message_id` (`message_id`),
    KEY `ix_task_messages_task_id` (`task_id`)
  ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='任务对话消息表';
  ```

- **前端依赖**:react-dropzone 如引入(package-lock 为准)
- **AI 执行路径决策**:claude-agent-sdk 未装(pip 受限)→ V1 走 CLI 兜底(容器内 `claude -p` 非交互,Runner exec_tool 通道);SDK adapter 接口已预留(claude_service.ClaudeSdkAdapter),装包后切换
- **影响范围**:R4 任务全链路;R3 打磨已切换到 tasks 表(type=requirement);R5/R6/R7 复用 create_task + extended_attributes
- **回滚方案**:`DROP TABLE task_messages; DROP TABLE task_uploaded_files; DROP TABLE tasks;`(顺序不可反)

## 2026-09-22 R4 前端任务工作台(补充条目,无 DB 变更)

- **类型**:前端(TaskDetail 三栏工作台 / TaskChat 对话框(@引用+附件)/ ActivityStream 活动流 / TaskCreateDialog)
- **影响范围**:/tasks/{task_id} 工作台;RequirementDetail 创建任务入口
- **回滚方案**:随代码回滚

## 2026-09-22 R5 开发任务(type=dev)

- **类型**:纯代码(无 DB/配置变更——复用 R4 tasks 表,fix_context 存 extended_attributes JSON)
- **影响范围**:POST /api/tasks/{test_task_id}/reject-to-dev(测试驳回回开发);send_message 首条消息自动注入【修复上下文】
- **回滚方案**:随代码回滚

## 2026-09-22 R6 测试任务(type=test)

- **类型**:数据库迁移(alembic revision `f2a7c9e4b8d1`,down_revision `e1f6b3a8d5c2`;tasks.status 枚举扩展)
- **数据库**:

  ```sql
  ALTER TABLE `tasks` MODIFY COLUMN `status`
    ENUM('pending','running','cases_review','passed','done','failed','cancelled','timeout')
    NOT NULL DEFAULT 'pending' COMMENT '状态(R6 扩展 cases_review/passed)';
  ```

- **影响范围**:R6 测试任务全链路(创建前置 dev-done/确认用例/接受失败豁免/驳回回开发回环);新状态 cases_review(用例审阅)与 passed(通过,含豁免标记入 extended_attributes)
- **开发库同步说明**:开发库表结构历史由 create_all 维护,本次以 `alembic stamp head` 对齐版本号(f2a7c9e4b8d1)并手工执行等价 ALTER;上线库走标准 alembic upgrade
- **回滚方案**:先 `UPDATE tasks SET status='pending' WHERE status='cases_review'; UPDATE tasks SET status='done' WHERE status='passed';` 再执行 downgrade ALTER

## 2026-09-22 R7 发布任务(type=release)

- **类型**:纯代码(无 DB 变更——deploy_host/deploy_port/deploy_phase 等存 tasks.extended_attributes;路由复用 R10 routes 表)
- **影响范围**:
  - POST /api/requirements/{req_id}/tasks(type=release):前置 test passed(4001)、deploy_port 10000-10099 全平台唯一(7001)、deploy_host 合法主机名+唯一(7003)、同时部署 ≤5(7002)
  - POST /api/tasks/{task_id}/run-release:merge→脚本→健康检查→路由注册→需求 done 推进
  - POST /api/tasks/{task_id}/offline:路由摘除+容器销毁
  - GET /api/tasks/check-port:端口冲突实时检测
  - Runner 新增 git_merge / deploy_run 消息处理
- **部署语义**:release 容器不销毁持续对外服务;发布任务固定调度在 role=deploy Runner;URL 端口为路由标识,V1 网关监听 80(端口直连形态由网关侧扩展)
- **回滚方案**:随代码回滚;路由摘除即下线

## 2026-09-22 R14 归档与知识库

- **类型**:数据库(alembic revision `a3c8e7f2b9d4`,down_revision `f2a7c9e4b8d1`)
- **数据库**:

  ```sql
  CREATE TABLE IF NOT EXISTS `knowledge_entries` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `entry_id` CHAR(36) NOT NULL COMMENT '对外UUID',
    `project_id` CHAR(36) NULL COMMENT '项目 id(null=平台级)',
    `req_id` CHAR(36) NOT NULL COMMENT '来源需求 id',
    `type` ENUM('code_snippet','pattern','pitfall','doc') NOT NULL COMMENT '类型',
    `title` VARCHAR(128) NOT NULL COMMENT '标题',
    `content` TEXT NOT NULL COMMENT '内容(Markdown)',
    `tags` JSON NULL COMMENT '标签数组',
    `source_links` JSON NULL COMMENT '关联链接',
    `created_by` ENUM('ai','human') NOT NULL DEFAULT 'ai' COMMENT '创建者类型',
    `status` ENUM('draft','published') NOT NULL DEFAULT 'draft' COMMENT '状态',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uq_knowledge_entries_entry_id` (`entry_id`),
    KEY `ix_knowledge_entries_project_id` (`project_id`),
    KEY `ix_knowledge_entries_req_id` (`req_id`),
    KEY `ix_knowledge_entries_type` (`type`),
    KEY `ix_knowledge_entries_status` (`status`),
    KEY `ix_knowledge_project_status` (`project_id`,`status`),
    FULLTEXT KEY `ft_knowledge_title_content` (`title`,`content`) WITH PARSER ngram
  ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='知识条目表';
  ```

- **影响范围**:R14 归档(时间线/总结路径/自动归档 done→archived)+ 知识库(项目/平台两级,FULLTEXT 检索,发布/提升);R7 完成链自动触发归档
- **回滚方案**:`DROP TABLE knowledge_entries;`(先 DROP FULLTEXT 索引或直接 DROP TABLE)

## 2026-09-22 R20 项目知识库管理

- **类型**:数据库(alembic revision `b5d9e1f4a7c3`,down_revision `a3c8e7f2b9d4`)
- **数据库**:

  ```sql
  CREATE TABLE IF NOT EXISTS `knowledge_bases` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `kb_id` CHAR(36) NOT NULL COMMENT '对外UUID',
    `project_id` CHAR(36) NOT NULL COMMENT '项目 id',
    `name` VARCHAR(64) NOT NULL COMMENT '显示名(同项目唯一)',
    `description` VARCHAR(255) NULL DEFAULT '' COMMENT '描述',
    `source_type` ENUM('blank','repo_import') NOT NULL DEFAULT 'blank' COMMENT '类型',
    `source_config` JSON NULL COMMENT '{repo_id,branch,paths}',
    `import_status` ENUM('idle','importing','done','failed') NOT NULL DEFAULT 'idle' COMMENT '导入状态',
    `import_error` VARCHAR(255) NULL COMMENT '最近失败原因',
    `last_synced_at` DATETIME NULL COMMENT '最近导入/同步时间',
    `created_by` CHAR(36) NOT NULL COMMENT '创建者',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uq_knowledge_bases_kb_id` (`kb_id`),
    UNIQUE KEY `uq_kb_project_name` (`project_id`,`name`),
    KEY `ix_knowledge_bases_project_id` (`project_id`),
    KEY `ix_knowledge_bases_import_status` (`import_status`),
    KEY `ix_knowledge_bases_created_by` (`created_by`)
  ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='项目知识库空间表';

  CREATE TABLE IF NOT EXISTS `knowledge_docs` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `doc_id` CHAR(36) NOT NULL COMMENT '对外UUID',
    `kb_id` CHAR(36) NOT NULL COMMENT '所属知识库',
    `title` VARCHAR(128) NOT NULL COMMENT '页面标题',
    `path` VARCHAR(255) NOT NULL COMMENT '树形路径(同库唯一)',
    `content` TEXT NOT NULL COMMENT 'Markdown 正文',
    `sort_order` INT NOT NULL DEFAULT 0 COMMENT '同级排序',
    `source_file_path` VARCHAR(255) NULL COMMENT '导入来源路径',
    `created_by` CHAR(36) NOT NULL COMMENT '创建者',
    `updated_by` CHAR(36) NOT NULL COMMENT '更新者',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uq_knowledge_docs_doc_id` (`doc_id`),
    UNIQUE KEY `uq_kb_doc_path` (`kb_id`,`path`),
    KEY `ix_knowledge_docs_kb_id` (`kb_id`),
    FULLTEXT KEY `ft_kb_docs_title_content` (`title`,`content`) WITH PARSER ngram
  ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='知识库页面表';
  ```

- **影响范围**:R20 知识库空间全链路(建库/导入同步[后台任务]/页面 CRUD/搜索);repo_import 写操作含超管一律 403 20002
- **通知依赖**:R18 站内信未落地,当前导入结果仅 logger 钩子(_notify_import_done)
- **回滚方案**:`DROP TABLE knowledge_docs; DROP TABLE knowledge_bases;`

## 2026-09-22 R18 站内信与通知

- **类型**:数据库(alembic revision `c4b1d7e9f2a6`,down_revision `b5d9e1f4a7c3`;projects 表加钉钉字段)
- **数据库**:

  ```sql
  CREATE TABLE IF NOT EXISTS `notifications` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `notification_id` CHAR(36) NOT NULL COMMENT '对外UUID',
    `recipient_id` CHAR(36) NOT NULL COMMENT '接收人 user_id',
    `type` ENUM('deploy_failed','runner_offline','task_failed','push_failed','review_approved','review_rejected','invited_to_project','task_done','deployed') NOT NULL COMMENT '通知类型',
    `level` ENUM('critical','normal','info') NOT NULL DEFAULT 'normal' COMMENT '级别',
    `title` VARCHAR(255) NOT NULL COMMENT '标题',
    `content` TEXT NOT NULL COMMENT '内容(Markdown)',
    `link` VARCHAR(255) NULL COMMENT '跳转链接',
    `project_id` CHAR(36) NULL COMMENT '关联项目 id',
    `task_id` CHAR(36) NULL COMMENT '关联任务 id',
    `read_at` DATETIME NULL COMMENT '已读时间',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uq_notifications_notification_id` (`notification_id`),
    KEY `ix_notifications_recipient_id` (`recipient_id`),
    KEY `ix_notifications_type` (`type`),
    KEY `ix_notifications_level` (`level`),
    KEY `ix_notifications_project_id` (`project_id`),
    KEY `ix_notifications_task_id` (`task_id`),
    KEY `ix_notifications_read_at` (`read_at`),
    KEY `ix_notifications_created_at` (`created_at`)
  ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='站内通知表';

  CREATE TABLE IF NOT EXISTS `user_notification_settings` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `user_id` CHAR(36) NOT NULL COMMENT '用户 id',
    `dingtalk_webhook` VARCHAR(255) NULL COMMENT '钉钉 webhook URL',
    `dingtalk_enabled` TINYINT(1) NOT NULL DEFAULT 0 COMMENT '启用钉钉',
    `realtime_toast_enabled` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '实时 toast',
    `dingtalk_fail_count` INT NOT NULL DEFAULT 0 COMMENT '连续失败次数',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uq_user_notification_settings_user` (`user_id`)
  ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户通知设置表';

  ALTER TABLE `projects`
    ADD COLUMN `dingtalk_webhook` VARCHAR(255) NULL COMMENT '项目钉钉群 webhook' AFTER `mcp_config_encrypted`,
    ADD COLUMN `dingtalk_enabled` TINYINT(1) NOT NULL DEFAULT 0 COMMENT '启用项目钉钉通知' AFTER `dingtalk_webhook`;
  ```

- **影响范围**:R18 通知全链路(发送/钉钉/WebSocket 推送);R20 导入完成通知钩子(_notify_import_done)
- **回滚方案**:先还原 projects 列:`ALTER TABLE projects DROP COLUMN dingtalk_enabled, DROP COLUMN dingtalk_webhook;` 再 `DROP TABLE user_notification_settings; DROP TABLE notifications;`

## 2026-09-22 R19 平台角色与权限体系

- **类型**:数据库(alembic revision `d6e3f9a1c8b5`,down_revision `c4b1d7e9f2a6`)
- **数据库**:

  ```sql
  CREATE TABLE IF NOT EXISTS `audit_logs` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `log_id` CHAR(36) NOT NULL COMMENT '对外UUID',
    `user_id` CHAR(36) NOT NULL COMMENT '操作者 user_id',
    `operator_role` VARCHAR(20) NOT NULL COMMENT '操作时平台角色快照',
    `action_type` VARCHAR(64) NOT NULL COMMENT '操作类型',
    `project_id` CHAR(36) NULL COMMENT '关联项目',
    `target_type` VARCHAR(64) NULL COMMENT '目标类型',
    `target_id` VARCHAR(64) NULL COMMENT '目标 id',
    `detail` JSON NULL COMMENT '变更详情',
    `ip` VARCHAR(45) NULL COMMENT '操作来源 IP',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '操作时间',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uq_audit_logs_log_id` (`log_id`),
    KEY `ix_audit_logs_user_id` (`user_id`),
    KEY `ix_audit_logs_action_type` (`action_type`),
    KEY `ix_audit_logs_project_id` (`project_id`),
    KEY `ix_audit_logs_created_at` (`created_at`)
  ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='审计日志表(只读追加,保留 1 年)';

  CREATE TABLE IF NOT EXISTS `invitations` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `invitation_id` CHAR(36) NOT NULL COMMENT '对外UUID',
    `token_hash` VARCHAR(255) NOT NULL COMMENT '邀请 token 哈希(明文仅返回一次)',
    `invited_phone` VARCHAR(11) NULL COMMENT '被邀请人手机号(可空)',
    `status` ENUM('pending','used','revoked') NOT NULL DEFAULT 'pending' COMMENT '状态',
    `expires_at` DATETIME NOT NULL COMMENT '过期时间(7 天)',
    `used_by` CHAR(36) NULL COMMENT '使用者 user_id',
    `created_by` CHAR(36) NOT NULL COMMENT '邀请人超管 user_id',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uq_invitations_invitation_id` (`invitation_id`),
    KEY `ix_invitations_status` (`status`)
  ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='平台注册邀请表';
  ```

- **影响范围**:用户管理/平台邀请/审计查询 API(超管);禁用链路(status+token_version+取消任务);审计异步写入与 365 天保留清理任务;users_admin 挂入主路由
- **部署动作**:main.py lifespan 挂心跳巡检与审计异步注入(已实现);/api/admin/* 建议网关层加 60 req/min 频控(19004 预留)
- **回滚方案**:`DROP TABLE invitations; DROP TABLE audit_logs;`(顺序不可反)

## 2026-09-23 R9.F1 任务页终端自动进入 claude 与对话同一会话

- **类型**:数据库(alembic revision `a7b2c8d9e1f3`,down_revision `f2a7c9e4b8d1`)
- **数据库**:

  ```sql
  ALTER TABLE tasks ADD COLUMN claude_session_id VARCHAR(64) NULL DEFAULT NULL COMMENT '任务级 claude 会话 ID(uuid4,对话/终端共享)';
  ```

- **影响范围**:R9.F1 任务级 claude_session_id 持久化(--session-id/--resume 接线)
- **回滚方案**:`ALTER TABLE tasks DROP COLUMN claude_session_id;`

## 2026-09-23 R28 用户信息修改增强(昵称、头像本地上传)

- **类型**:数据库(alembic revision `b2e8f4a6c9d1`,down_revision `a7b2c8d9e1f3`)
- **数据库**:

  ```sql
  ALTER TABLE users ADD COLUMN avatar_file_path VARCHAR(255) NULL DEFAULT NULL COMMENT '本地上传的文件存储路径';
  ```

- **影响范围**:R28 头像上传/访问/移除链路(POST /api/users/me/avatar、GET /api/files/avatars/{filename}、PATCH /api/users/me avatar_url=null 双清空)
- **回滚方案**:`ALTER TABLE users DROP COLUMN avatar_file_path;`(代码回滚后旧列不碍事)

## 2026-09-22 R21+R22 工作台与四维管理菜单

- **类型**:纯代码(无 DB 变更——聚合查询直查 requirements/tasks/project_members/projects)
- **影响范围**:
  - GET /api/dashboard/summary(四卡片统计 + 每类 recent ≤5;created_by=me 口径;超管=全部 active 项目)
  - GET /api/dashboard/requirements、GET /api/dashboard/tasks/{dev|test|release}(四维列表,status 过滤+分页)
- **前端**:Dashboard 工作台已有页面接 dashboard summary 数据;四维列表由 dashboard_views 路由承载
- **回滚方案**:随代码回滚

## 2026-09-22 R22 四维管理菜单(补充条目,无 DB 变更)

- **类型**:纯代码
- **影响范围**:GET /api/dashboard/requirements、GET /api/dashboard/tasks/{dev|test|release}(四维列表,created_by=me + 可见项目过滤 + status 过滤 + 分页)
- **回滚方案**:随代码回滚

---

# 发布检查单 2026-09-22

> 生成:/rd-ship | 目标库:aicoding(120.27.217.194:3306,即当前唯一库,开发=目标同库)
> 发布方式:**手动部署**(全仓无 .gitlab-ci.yml;若后续建 CI,以新 pipeline 为准更新本节)

## 0. 阻塞项(发布前必须处理)

- [x] **⚠️ 阻塞(已修复 2026-09-22 rd-fix/R16.F1,BUG-007 fixed)**:~~docker/runner/Dockerfile 缺文件~~ COPY 已补齐 4 文件;**首次 `docker build platform/runner:v1` 成功后 BUG-007 置 verified**(本机引擎未运行,构建冒烟留待部署机)
- [ ] UI 原型对齐迭代未完成(DESIGNLOG.md 页面进度表存在 pending 项)——不影响功能,影响视觉一致性;用户知情接受带此遗留上线,后续 `/rd-ui` 续做

## 1. 前置检查

- [x] DEVPLAN.md 进度表 22/22 需求点 ✅
- [x] BUGS.md 无活跃问题(6 个 rd-fix 问题全部 verified,移入 ISSUES.md)
- [ ] CI 可触发:**不适用(无 CI)**;手动部署路径见 §4
- [ ] 生产密钥重新生成:`PLATFORM_SECRET_KEY` / `JWT_SECRET_KEY` 均为开发随机值,**生产 .env 必须换新**(64 位 hex;换 JWT_SECRET_KEY 会使所有现有登录态失效,属预期)

## 2. 数据库变更(按执行顺序)

**目标库现状(2026-09-22 只读核对,已通过)**:
- 23 张业务表全部存在(users/projects/project_repos/platform_settings/project_members/model_configs/skills/project_skills/containers/runners/terminal_sessions/routes/requirements/tasks/task_uploaded_files/task_messages/knowledge_entries/knowledge_bases/knowledge_docs/notifications/user_notification_settings/audit_logs/invitations)+ alembic_version
- `alembic_version.version_num = d6e3f9a1c8b5`(= head,R19)✅
- 关键列抽查 ✅:`tasks.status` 已含 `cases_review/passed`(R6 ALTER);`projects.dingtalk_webhook/dingtalk_enabled` 已存在(R18);`users.role/token_version` 已存在(R1)
- 数据量:users=2,runners=1,其余业务表 0 行(准新库,无存量数据迁移问题)

- [x] **当前目标库(aicoding)无需再执行任何 DDL**——开发期已通过 create_all + alembic 全链应用并核对(上方现状核对即证据)
- [ ] **若部署全新环境**,按以下顺序执行(全文见上文各需求点条目;每步先 `SHOW CREATE TABLE` 核对前一步成功):
  1. R1 建表 `users` → 2. R2 建表 `projects`/`project_repos`/`platform_settings` → 3. R12 建表 `project_members` → 4. R13 建表 `model_configs` → 5. R17 建表 `skills`/`project_skills` → 6. R8 建表 `containers` → 7. R16 建表 `runners` → 8. R9 建表 `terminal_sessions` → 9. R10 建表 `routes` → 10. R3 建表 `requirements` → 11. R4 建表 `tasks`/`task_uploaded_files`/`task_messages` → 12. R6 ALTER `tasks.status` 枚举扩展(必须在 R4 之后) → 13. R14 建表 `knowledge_entries`(FULLTEXT ngram) → 14. R20 建表 `knowledge_bases`/`knowledge_docs` → 15. R18 建表 `notifications`/`user_notification_settings` + ALTER `projects` 加钉钉两列 → 16. R19 建表 `audit_logs`/`invitations`
  17. `INSERT INTO aicoding.alembic_version(version_num) VALUES('d6e3f9a1c8b5')`(或直接 `alembic upgrade head` 替代 1-16 全部步骤,推荐)

## 3. 配置 / 环境变量变更

- [ ] **backend/.env**(部署机,不入库;仓库仅 .env.example):
  - `DATABASE_URL`(生产凭据;密码含特殊字符需 URL 编码)
  - `PLATFORM_SECRET_KEY` / `JWT_SECRET_KEY` → **新随机 64 位 hex(生产必须换)**
  - `REDIS_URL`(R1 仅占位,可不配)
  - `ENVIRONMENT=production`
- [ ] **gateway 进程**:`DATABASE_URL`(实时查 routes 表)、`GATEWAY_PORT=80`
- [ ] **前端**:`vite build` 产物指向后端 API 地址(按部署形态配 nginx/静态托管反代 `/api` 与 `/ws`)
- [ ] **Runner(见 §5)**:`PLATFORM_URL` / `RUNNER_TOKEN` / `RUNNER_ROLE` / `RUNNER_HOST`
- [ ] **DNS**:泛域名 `*.{preview_base_domain}` 与 `*.{deploy_base_domain}` A 记录 → 网关机器 IP

## 4. 代码发布(手动,无 CI)

- [ ] **后端**:`backend/` 部署 → `alembic upgrade head`(幂等,当前已在 head 则无操作)→ 启动 `uvicorn app.main:app`(main.py lifespan 自动挂 Runner 心跳巡检 + 审计异步写入)
- [ ] **前端**:`frontend/` → `npm run build` → 产物部署静态托管(反代 `/api`、`/ws` 到后端)
- [ ] **网关**:`gateway/` → `GATEWAY_PORT=80 python3 gateway/main.py`(依赖 backend app 代码,与后端同机或同代码部署)
- [ ] **Runner 机器**:见 §5
- [ ] **镜像**(Docker 任一可联网机器构建后推送/导入目标机器):
  - [ ] `docker build -t platform/devbox:v1 -f docker/devbox/Dockerfile .`(**注意 build context 为仓库根**,Dockerfile 内 `COPY skills/` 相对根;R8.F1 2026-09-23:基础镜像已换 `devcontainers/typescript-node:dev-bookworm`——原 universal 退役,默认用户 node,CMD sleep infinity 保活,skills/ 目录已建占位;实测构建+保活+E2E 全通)
  - [ ] `docker build -t platform/runner:v1 -f docker/runner/Dockerfile runner/`(**先完成 §0 Dockerfile 修复**)

## 5. Runner 部署专项(每台 Runner 机器执行)

**架构**:Runner 主动 WebSocket 出站连接平台 `/ws/runner`(无需平台入站 Runner);Runner 本机调 Docker SDK 拉起任务容器;网关直连 `runner_host:mapped_port`。

**前置(每台机器)**:
- [ ] 已安装 Docker Engine 且当前用户可访问 `/var/run/docker.sock`(或容器方式挂载该 sock)
- [ ] 网络连通:机器 → 平台 `PLATFORM_URL` 出站可达;网关 → 本机 `20000-29999` 入站可达(preview);deploy 角色另需公网 IP 真实可达 + `10000-10099` 入站放行
- [ ] 平台侧:超管登录 → 平台管理 → Runner 管理 → 创建 Runner(worker/deploy 角色)→ **复制一次性 token `plt-runner-*`(仅显示一次,库中只存 bcrypt hash)**

**方式 A:容器化部署(推荐)**
```bash
# 构建(任一机器,先完成 §0 Dockerfile 修复)
docker build -t platform/runner:v1 -f docker/runner/Dockerfile runner/

# 目标 Runner 机器运行(worker 角色示例)
docker run -d --name runner-01 --restart unless-stopped \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -e PLATFORM_URL=wss://<平台域名或IP:端口>/ws/runner \
  -e RUNNER_TOKEN=plt-runner-xxxx \
  -e RUNNER_ID=runner-01 \
  -e RUNNER_ROLE=worker \
  -e RUNNER_HOST=<本机被网关访问的IP> \
  platform/runner:v1
```
deploy 角色差异:`RUNNER_ROLE=deploy` + `RUNNER_HOST` 填**真实公网 IP**(会写入 runners.public_ip,供部署 URL 直连)。

**方式 B:裸机部署(systemd 托管)**
```bash
pip3 install -r runner/requirements.txt   # docker>=6.0, websockets>=11.0
# 环境变量同方式 A(PLATFORM_URL/RUNNER_TOKEN/RUNNER_ID/RUNNER_ROLE/RUNNER_HOST)
python3 main.py                            # 建议配 systemd unit:Restart=always
```

**运行时行为(核对要点)**:
- 注册:`register{token, machine_info, host}` → 平台返回 `register_success(runner_id)`;身份由 **token** 决定(RUNNER_ID 仅日志标识)
- 心跳:30s 一跳;平台 60s 未收到判 **offline**,>5min 漂移拒绝;Runner 断线指数退避自动重连
- 对账:重连后 `sync` 上报本地容器列表,状态以 Runner 为准
- 端口:任务容器 preview 随机映射宿主机 **20000-29999**;部署容器固定 **10000-10099**(deploy Runner)

**部署后验证**:
- [ ] 平台 Runner 管理页该 Runner `online`,`machine_info`(os/arch/cpu/mem/docker_version)已上报
- [ ] `docker stop runner-01` → 60s 后页面转 `offline`;`docker start` 后自动恢复 `online`
- [ ] 创建测试任务 → 容器在本机 `docker ps` 可见,状态 running,端口在 20000-29999 区间
- [ ] 任务工作台:终端可连接(pty)、预览路由可访问、文件树可读

**Runner 下线/回滚**:`docker stop && docker rm runner-01`(或停 systemd);平台侧标记 offline,不影响平台其余功能;已运行容器按容器级销毁处理。

## 6. 上线后配置动作(平台内,顺序执行)

- [ ] 首个注册用户自动成为 superadmin(R1 bootstrap;当前库已有 2 用户,确认超管账号归属)
- [ ] 超管 → 平台设置,录入 `gitlab_url` / `gitlab_bot_token`(scope=api)/ `gitlab_bot_group_id` / `gitlab_webhook_secret`(**当前 platform_settings=0 行,不配置则项目创建全局禁用 2001**)
- [ ] 确认 `preview_base_domain` / `deploy_base_domain`(有默认值)
- [ ] Runner 管理创建 Runner 并按 §5 部署(当前 runners 表已有 1 条记录,确认是否复用)

## 7. 验证步骤(上线后逐项执行)

- [ ] 健康检查:`GET /health` → 200
- [ ] OpenAPI 可达:`GET /docs`、`GET /openapi.json`
- [ ] 登录冒烟:`POST /api/auth/login`(测试账号)→ code=0 + 双 token
- [ ] 核心链路冒烟(依赖 §6 已配置):建项目 → 建需求 → 打磨任务拉起(容器 running)→ 终端连接 → 预览路由 → 测试任务 → 发布任务(URL 可达 + 需求 done)→ 归档 + 知识条目
- [ ] 前端页面可达:登录页 / Dashboard / 项目列表 / 四维管理 / 管理后台五页
- [ ] WebSocket:终端 TTY 可交互;通知 toast 通道连通

## 8. 回滚方案

- **代码**:各组件回退上一版本镜像/产物重启(后端/前端/网关/Runner 相互独立,可单独回滚)
- **数据库**:全部变更为**纯新增**(CREATE TABLE IF NOT EXISTS / 加列 / 枚举扩展),代码回滚后旧表不碍事,**无需逆向 DDL**;仅在全量废弃时按建表逆序 DROP(先备份)
- 唯一非纯新增:`tasks.status` 枚举扩展(R6)——回滚前必须先归并数据:`UPDATE tasks SET status='pending' WHERE status='cases_review'; UPDATE tasks SET status='done' WHERE status='passed';` 再执行 downgrade ALTER
- 数据不可逆操作(项目/需求/任务的 GitLab 侧建仓、分支删除)不在本平台回滚范围内,需 GitLab 侧人工处理

## 9. 回滚验证(高风险项评估)

- 本次变更全为新增表/加列,**无不可逆 SQL、无大改表、无核心链路重构** → 免演练
- [ ] (若部署新环境执行了 §2 全量 DDL)测试环境演练一次:代码回退 + §8 数据归并 + 健康检查/登录冒烟重跑

## 10. 风险与遗留

- **Dockerfile 阻塞项**(§0):未修复则 Runner 镜像无法启动
- UI 原型对齐迭代未完成(DESIGNLOG.md 进度表 pending 项),用户知情接受
- AI 执行路径:claude-agent-sdk 未安装(pip 网络受限),V1 走容器内 `claude -p` CLI 兜底;装包后切 SDK adapter
- R20 知识库导入完成通知仅 logger 钩子(R18 通知已在,钩子待接)
- 开发库历史由 create_all 维护 + alembic stamp 对齐;全新环境必须走 `alembic upgrade head`,勿混用两种方式
- 网关 V1 仅 HTTP(HTTPS/CDN/WAF 范围外);Runner 机器不部署反代(直连形态)


## R31 追加(2026-09-24,增量5)— runners 表加 is_local 列

- **迁移**:`c7d3e9b5a2f4_r31_is_local.py`(down=b2e8f4a6c9d1);`alembic upgrade head` 幂等
- **SQL(全新环境手写等价)**:
  ```sql
  ALTER TABLE runners ADD COLUMN is_local TINYINT(1) NOT NULL DEFAULT 0 COMMENT '本机快速创建标记(R31)';
  ```
- **存量行处理**:默认 0(=远程 token 型),无需回填
- **已执行**:开发库 aicoding 已 upgrade(head=c7d3e9b5a2f4);测试库 aicoding_test 已手工补列(conftest create_all 不加列,环境陷阱#2)
- **配置**:无新增;R31 本机 runner 的 PLATFORM_URL 固定注入 `ws://127.0.0.1:8000/ws/runner`(E1 已知限制:平台非 8000 端口/多网卡场景 V2 平台设置化)
- **依赖**:无新增(runner 侧 docker/websockets 既有;preflight 运行时探测)

## R32 追加(2026-09-24,增量6)— runners 表加 tags JSON 列

- **迁移**:`d8e4f2a6b9c3_r32_runner_tags.py`(down_revision=c7d3e9b5a2f4);`alembic upgrade head` 幂等
- **SQL(全新环境手写等价)**:
  ```sql
  ALTER TABLE runners ADD COLUMN tags JSON NULL COMMENT '任务类型标签(R32);NULL/空=兜底接所有 worker 任务';
  ```
- **存量行处理**:NULL=兜底接所有 worker 任务,代码兼容读 `runner.tags or []`,无需回填
- **已执行**:2026-09-24 rd-dev 阶段——dev 库 aicoding 已 `alembic upgrade head`(c7d3e9b5a2f4 → d8e4f2a6b9c3);测试库 aicoding_test 已手工补列(conftest create_all 不加列,环境陷阱#2)
- **配置**:无新增;**依赖**:无新增
