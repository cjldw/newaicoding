# ISSUES:知识条目手动添加(已验证问题归档)

> 从 BUGS.md 迁移的 verified 条目,保留上下文备查。

### BUG-KB-001:平台页创建的知识条目,列表看不到记录

- **严重程度**:一般(体验断裂)
- **关联页面**:平台知识库 /knowledge;项目知识库 /projects/{pid}/knowledge
- **问题描述**:平台页「新建条目」创建(选归属项目)成功后,用户在列表找不到记录。API 实证:条目正确落项目列表(7cd863fb 在项目 b9a3e4ff 列表 total=8 中),平台列表按设计仅含平台级(project_id IS NULL,total=0)——后端无 bug,属 UX 断裂(创建成功后无去向引导)
- **修复方案**:R1.F1——平台 scope 创建成功 Dialog 进成功态(CheckCircle+「前往项目知识库查看」跳转+「继续创建/关闭」),删除无效 platform-knowledge invalidate;项目 scope 行为不变。后端零改动
- **修复提交**:见 R1.F1
- **状态**:verified(真机回归 11/11 断言通过:创建→成功态→跳转→列表可见→清理 DELETE 200;截图 report/fix-r1f1/;console error=0)

### BUG-KB-002:知识条目页搜索栏与顶边重叠

- **严重程度**:一般(视觉缺陷)
- **关联页面**:/knowledge 等路由长页
- **问题描述**:路由内容无滚动容器,滚动发生在 body,长页搜索框滚入半透明 sticky 顶栏下方 27.7px(截图实证);并发流 `.main{overflow:hidden}` 掩盖现象但改为裁切内容
- **修复方案**:R2.F3——MainLayout Outlet 包 `.route-scroll{flex:1;min-height:0;overflow-y:auto}`,与并发流改动共存
- **状态**:verified(Playwright 实测滚动到底无重叠、四维管理/工作台布局不塌;截图 report/fix-r2f3/)

### BUG-KB-003:知识条目页缺「项目知识库/平台知识库」双 Tab

- **严重程度**:一般(用户指定信息架构)
- **关联页面**:/knowledge
- **问题描述**:用户要求侧栏「知识条目」进入后分双 Tab;原 Tab 被 isProjectScope 门控,平台 scope 无 Tab
- **修复方案**:R4.F2——去门控,平台 scope 增 scopePid+项目 Select(零后端);项目页行为不变
- **状态**:verified(Playwright 双 Tab 切换/项目列表 12 条/平台列表均通过;截图 report/fix-r4f2/)

### BUG-KB-004:知识库预览渲染缺口 + 编辑保存恒 500

- **严重程度**:一般(渲染器能力缺口)+ 高(编辑保存恒 500,顺带发现)
- **关联页面**:/projects/{pid}/knowledge-bases/{kbId}
- **问题描述**:布局已符合左树/右预览(260px/860px);真缺口=renderMarkdown 缺链接/有序列表包裹(编号串号)/引用/表格;另 kb_service.update_doc flush 后读 updated_at 触发 MissingGreenlet → 编辑保存恒 500(rename_kb 同病灶)
- **修复方案**:R2.F4——renderMarkdown 扩展四能力(javascript: 降级安全);update_doc/rename_kb flush 后 refresh
- **状态**:verified(TDD 2 用例 Red→Green,套件 5 passed;浏览器端到端 PUT 200 + 渲染实测;截图 report/fix-r2f4/)
