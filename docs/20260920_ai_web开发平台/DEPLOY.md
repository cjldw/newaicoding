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
