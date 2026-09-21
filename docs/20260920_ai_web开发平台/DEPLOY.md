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
