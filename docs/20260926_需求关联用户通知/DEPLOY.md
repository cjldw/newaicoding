# DEPLOY:需求关联用户/原型链接/交付时间

> 创建日期:2026-09-26

## 数据库变更

迁移文件(alembic,down_revision 以当时 head 为准):

```sql
-- upgrade
ALTER TABLE requirements
  ADD COLUMN related_user_ids JSON NULL COMMENT '关联用户ID列表' AFTER priority,
  ADD COLUMN prototype_links JSON NULL COMMENT '原型链接[{label,url}]' AFTER related_user_ids,
  ADD COLUMN delivery_date DATE NULL COMMENT '交付截止日' AFTER prototype_links;
ALTER TABLE notifications
  MODIFY COLUMN type ENUM('deploy_failed','runner_offline','task_failed','push_failed',
                          'review_approved','review_rejected','invited_to_project',
                          'task_done','deployed','req_delivery_reminder') NOT NULL COMMENT '通知类型';
```

> ⚠️ MODIFY ENUM 必须先 `SHOW COLUMNS` 抄全现有枚举值再追加新值,漏值会截断数据;上线前在测试库演练。
> R6:该语句已落 alembic 迁移 f8b2d4a6c1e3(全文与回滚见 .scratch/R6/deploy-sql.md);
> 测试库/开发库均已应用(开发库 aicoding head=f8b2d4a6c1e3,2026-09-26 `alembic current` 核对),
> 上线环境执行 alembic upgrade head。

```sql
-- downgrade
ALTER TABLE requirements
  DROP COLUMN related_user_ids,
  DROP COLUMN prototype_links,
  DROP COLUMN delivery_date;
-- notifications.type 的 downgrade 需确认无新类型存量行后再缩回
```

- 存量行:三新列 NULL=未设置,不回填
- 平台设置:运行时白名单写入 req_delivery_reminder_last_date(无需 SQL)

## 配置/依赖

- 无新增

## 上线检查单

1. alembic upgrade head 成功;requirements 三列存在
2. 创建需求带关联用户/链接/交付时间保存回显正常
3. 评审通过 → 关联用户收到站内信
4. 巡检 last_run_date 写入 platform_settings;同日重启不重发
