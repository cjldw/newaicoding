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
  MODIFY COLUMN type ENUM('review_approved','task_created','task_status_changed','requirement_status_changed','req_delivery_reminder', '<补齐现有全部枚举值>') NOT NULL COMMENT '通知类型';
```

> ⚠️ MODIFY ENUM 必须先 `SHOW COLUMNS` 抄全现有枚举值再追加新值,漏值会截断数据;上线前在测试库演练。

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
