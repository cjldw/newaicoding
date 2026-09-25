# BUGS:知识条目手动添加

> 活跃问题台账;verified 后迁移 ISSUES.md。

## UI 相关问题

### BUG-KB-005:知识详情页点击目录项后,hover 高亮落在错误的大纲条目上

- **页面**:`/projects/:pid/knowledge/:eid` 正文大纲目录(左栏 `.md-toc`)
- **严重级**:低(纯视觉,鼠标再次移动即自愈,无功能影响)
- **复现**(1440x900,大纲 ≥2 条):
  1. 鼠标点击目录第 2 项(如「背景」),页面平滑滚动;
  2. 滚动期间 sticky 目录列在固定不动的鼠标指针下方整体上移,滚动结束后 Chromium 按指针最后坐标重算 `:hover`,导致**非点击项**(实测为第 4 项「环境要求」)呈现 hover 底色,点击的目标项反而不高亮。
- **证据**:Playwright 实测 `document.querySelectorAll('.md-toc-item:hover')` = ["环境要求"],而点击的是「背景」;复现脚本 `docs/20260924_知识条目手动添加/.scratch/toc-verify.mjs`(2026-09-25)。
- **根因**:`.md-toc{position:sticky}` + 目录项仅有 `:hover` 样式、无持久化的 active 态;容器滚动与指针静止叠加造成 hover 错位。
- **修复建议**(任选):
  - 点击目录项后给该项加持久 active 高亮(scrollspy 或点击态),既符合直觉也顺带覆盖 hover 错位;
  - 或目录项 hover 改由 JS mouseenter 管理,滚动结束后按真实指针位置重算。
- **状态**:open(2026-09-25,R28.F2 目录验收时发现)
