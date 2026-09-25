# DEPLOY:知识条目手动添加与 Markdown 查看

> 创建日期:2026-09-25
> 消费:rd-ship 上线阶段;rd-dev 实施时逐条核对

## 数据库变更

### R3:knowledge_entries 增加创建者列

迁移:`e8f4a2c6b9d1_r32_knowledge_author.py`(down_revision="c7d3e9b5a2f4")

```sql
-- upgrade
ALTER TABLE knowledge_entries
  ADD COLUMN created_by_user_id CHAR(36) NULL COMMENT '创建者用户ID(历史行NULL,仅owner/editor/超管可编删)'
  AFTER created_by;

-- downgrade
ALTER TABLE knowledge_entries DROP COLUMN created_by_user_id;
```

- 存量行:NULL,不做回填(历史 AI/人工条目创建者不可考,按 R3 权限矩阵回落 owner/editor/超管)
- 索引:不加(编辑/删除按 entry_id 主键定位,created_by_user_id 仅判定用)
- 执行方式:上线前 `alembic upgrade head`(幂等),**严禁 create_all 混用**

## 配置/环境

- 无新增环境变量;GitLab 拉取沿用平台级 `gitlab_bot_token`(平台设置已配)

## 依赖

- 后端:无新增 pip 依赖
- 前端:无新增 npm 依赖(monaco/markdown 渲染器均为存量)

## 上线检查单

1. `alembic upgrade head` 执行成功,`knowledge_entries.created_by_user_id` 存在
2. 新创建人工条目该行落 user_id;历史行 NULL 不受影响
3. 核心链路走查:建 A 型条目 → 详情代码区递归树渲染 → 编辑 → 删除;B 型建 → markdown 详情 → 摘要列表
