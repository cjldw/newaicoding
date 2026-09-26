# ISSUES:需求关联用户通知(已验证问题归档)

> 从 BUGS.md 迁移的 verified 条目。

### BUG-KB-006:首页任务卡最近列表恒空(前端取数 key 错位)

- **严重程度**:高(三张任务卡对所有用户恒 0/空,R21 起即存在)
- **关联页面**:工作台 /
- **问题描述**:后端 summary 返回键 dev_tasks/test_tasks/release_tasks,前端 Dashboard.tsx 按 'dev'/'test'/'release' 直取 → 恒得零块;需求卡因同名 requirements 侥幸正常。DB 实证该用户 dev=8 条,后端 R7 口径正确
- **修复方案**:R7.F1——DIMS 加 skey 映射替换两处取数(约 5 行,仅前端)
- **状态**:verified(Playwright:开发卡 total=8+5 行,test/release 与 API 一致,需求卡不回归,6/6 断言;截图 report/fix-r7f1/)
