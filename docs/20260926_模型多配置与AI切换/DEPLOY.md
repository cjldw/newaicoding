# DEPLOY:模型多配置与 AI 对话切换(数据库变更)

> 需求:./PRD.md · 计划:./DEVPLAN.md
> 类型:alembic 单迁移(新增一个 revision,`down_revision='de60f84752af'`,当前链头 R33)
> 说明:上线时本节由 `/rd-ship` 并入 `docs/20260920_ai_web开发平台/DEPLOY.md` 主部署文档

## 变更 1:model_configs 支持一条配置挂多模型名(R2)

```sql
ALTER TABLE model_configs ADD COLUMN models TEXT NULL
  COMMENT '模型名列表 JSON 数组(如 ["gpt-4o","deepseek-chat"];NULL=存量行,读取层兼容用 model 列)';
ALTER TABLE model_configs ADD COLUMN default_model VARCHAR(64) NULL
  COMMENT '配置内默认模型(必须存在于 models;NULL=存量行,读取层兼容用 model 列)';
```

- 影响范围:项目模型配置 CRUD、回退链解析(`decrypt_config` 读 default_model)、任务执行模型解析
- 存量行处理:两列保持 NULL,**代码兼容读**(`models` 空 → `[model]`;`default_model` 空 → `model`),不回填;新写入时 `model` 列继续双写 = default_model
- 回滚方案:

```sql
ALTER TABLE model_configs DROP COLUMN models;
ALTER TABLE model_configs DROP COLUMN default_model;
-- model 列保留,回滚后回到 R13 单模型语义(存量数据无损)
```

## 变更 2:任务对话模型选择与消息留痕(R3.1)

```sql
ALTER TABLE tasks ADD COLUMN chat_config_id CHAR(36) NULL DEFAULT NULL
  COMMENT '对话所选模型配置 config_id(NULL=回退链或平台模型)';
ALTER TABLE tasks ADD COLUMN chat_model VARCHAR(64) NULL DEFAULT NULL
  COMMENT '对话所选模型名(chat_config_id 为空且本列非空=平台模型)';
ALTER TABLE task_messages ADD COLUMN model VARCHAR(64) NULL DEFAULT NULL
  COMMENT '本条 AI 回复实际所用模型名(仅 assistant 消息写入)';
```

- 影响范围:任务对话模型切换、消息执行模型解析、消息历史展示
- 存量行处理:三列 NULL,**代码兼容读**(NULL → 回退链解析,与现行为一致;消息无 model → 前端不展示小字),不回填
- 回滚方案:

```sql
ALTER TABLE tasks DROP COLUMN chat_config_id;
ALTER TABLE tasks DROP COLUMN chat_model;
ALTER TABLE task_messages DROP COLUMN model;
```

## 变更 3:platform_settings 新键(无 DDL)

- `llm_models`(JSON 数组)、`llm_default_model`(字符串):`platform_settings.value` 为 JSON 列,新键走白名单注册,**零 DDL**
- `llm_model` 旧键保留不删;读取层兼容(`llm_models` 缺失且旧键有值 → `[旧值]`)

## alembic 迁移约定

- 新文件:`backend/alembic/versions/<rev>_r34_multi_model_chat_switch.py`
- `revision` = 新生成;`down_revision = 'de60f84752af'`
- `upgrade()`:上述 5 条 `op.add_column`(model_configs 两列 / tasks 两列 / task_messages 一列)
- `downgrade()`:对应 `op.drop_column` × 5
