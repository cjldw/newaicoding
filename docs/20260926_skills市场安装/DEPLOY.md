# DEPLOY:Skills 市场安装 + 系统级列表

> 创建日期:2026-09-26;消费:/rd-ship

## 数据库变更

迁移(alembic;skills 两列落地为 `b8e4d2f6a9c1_r3skills_install_source.py`,down_revision=`f8b2d4a6c1e3`,精确回填已在迁移内以 op.execute 执行;开发库/测试库均已升级至 b8e4d2f6a9c1):

```sql
-- upgrade
ALTER TABLE skills
  ADD COLUMN source ENUM('platform','project','market') NOT NULL DEFAULT 'platform' COMMENT '来源' AFTER scope,
  ADD COLUMN source_url VARCHAR(512) NULL COMMENT '市场来源URL' AFTER source;
-- 存量回填:source 默认 platform 已兼容(project scope 存量行按 scope 区分——如需精确回填:
-- UPDATE skills SET source='project' WHERE scope='project'; 在迁移内以 op.execute 执行)
CREATE TABLE claude_system_assets (
  id BIGINT PRIMARY KEY AUTO_INCREMENT,
  name VARCHAR(128) NOT NULL COMMENT 'skill目录名/mcp名',
  kind ENUM('skill','mcp') NOT NULL COMMENT '类别',
  detail JSON NULL COMMENT '探测原文',
  collected_at DATETIME NOT NULL COMMENT '采集时间',
  image_tag VARCHAR(128) NULL COMMENT '镜像标识',
  KEY idx_kind (kind)
) COMMENT='系统级已安装(容器探测)';
-- downgrade
DROP TABLE claude_system_assets;
ALTER TABLE skills DROP COLUMN source_url, DROP COLUMN source;
```

## 配置/依赖

- platform_settings 运行时白名单写入 skill_market_sources(默认两源种子,无需 SQL)
- 后端无新增 pip 依赖(httpx 已有)

## 上线检查单

1. alembic upgrade head;skills.source/source_url 存在,claude_system_assets 建表
2. 存量 skills 行 source 回填正确(project 库标 project)
3. 市场搜索双源可用(外网连通 skills.sh/modelscope.cn)
4. 超管采集系统级列表成功;AI 对话 /skills /mcp 候选含系统内置项
5. 安装 skill 后新启任务容器,skill 注入 /root/.claude/skills/ 生效
