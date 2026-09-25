# ISSUES:知识条目手动添加(已验证问题归档)

> 从 BUGS.md 迁移的 verified 条目,保留上下文备查。

### BUG-KB-001:平台页创建的知识条目,列表看不到记录

- **严重程度**:一般(体验断裂)
- **关联页面**:平台知识库 /knowledge;项目知识库 /projects/{pid}/knowledge
- **问题描述**:平台页「新建条目」创建(选归属项目)成功后,用户在列表找不到记录。API 实证:条目正确落项目列表(7cd863fb 在项目 b9a3e4ff 列表 total=8 中),平台列表按设计仅含平台级(project_id IS NULL,total=0)——后端无 bug,属 UX 断裂(创建成功后无去向引导)
- **修复方案**:R1.F1——平台 scope 创建成功 Dialog 进成功态(CheckCircle+「前往项目知识库查看」跳转+「继续创建/关闭」),删除无效 platform-knowledge invalidate;项目 scope 行为不变。后端零改动
- **修复提交**:见 R1.F1
- **状态**:verified(真机回归 11/11 断言通过:创建→成功态→跳转→列表可见→清理 DELETE 200;截图 report/fix-r1f1/;console error=0)
