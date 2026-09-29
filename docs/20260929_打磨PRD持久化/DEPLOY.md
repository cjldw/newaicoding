# DEPLOY:打磨 PRD 持久化(20260929)

> 由 /rd-plan 建立,/rd-dev 继续追加,最终由 /rd-ship 在上线阶段消费。
> 数据库:MySQL(asyncmy);迁移工具 alembic(当前 head `b4f8e2a9c1d7`)。

## 变更清单

| # | 需求点 | 类型 | 内容 |
|---|---|---|---|
| 1 | R1 | 加列 | requirements 加 prd_content MEDIUMTEXT NULL |

## SQL

### 1. R1:requirements 加 prd_content 列(RD-20260929)

> 已落 alembic 迁移文件(`backend/alembic/versions/{revision}_prd_content.py`,down_revision=`b4f8e2a9c1d7`);此处为上线检查用的同文 SQL。迁移幂等性说明:alembic 版本表控制,重复执行 no-op。

```sql
ALTER TABLE `requirements`
  ADD COLUMN `prd_content` MEDIUMTEXT NULL
  COMMENT 'PRD.md 平台副本(最新值);NULL=尚无副本'
  AFTER `prd_file_path`;
```

回滚:

```sql
ALTER TABLE `requirements` DROP COLUMN `prd_content`;
```

存量行处理:全部 NULL,不回填(源在容器的才拉得到,回传机制 R2 上线后自然建立);代码兼容读(NULL → 预览走「库无副本」分支)。

## 上线检查单

- [ ] `alembic upgrade head` 成功(先核对当前版本 = `b4f8e2a9c1d7`)
- [ ] information_schema 确认 `requirements.prd_content` 存在且类型 MEDIUMTEXT
- [ ] 存量需求详情页打开无 500(NULL 兼容读)
