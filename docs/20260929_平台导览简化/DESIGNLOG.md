# 设计稿落地:平台导览去三角 icon

> 创建日期:2026-09-29
> 状态:完成

## 页面进度表

| 页面/区块 | 状态 | 设计规范文件 | 备注 |
|---|---|---|---|
| 侧栏"平台导览"去 Play icon | ✅ | (无设计稿,需求直述) | 2026-09-29 |
| TourDialog 弹窗标题去 Play icon | ✅ | (无设计稿,需求直述) | 2026-09-29 |

## 需求来源与口径更正

- 用户口述:左下角"平台导览"不要三角形 icon;点击后的 dialog 里对应 icon 也不要。
- **口径更正记录**:首轮误实现为"弹窗整体下线"(删了 TourDialog.tsx/useTourSteps.ts/CSS/自动弹出),已 git 还原;最终口径 = **仅删 icon,弹窗、「开始导览」按钮、首次登录自动弹出全部保留**。

## 改动清单

| 文件 | 操作 | 说明 |
|---|---|---|
| frontend/src/components/layout/MainLayout.tsx | 修改 | 侧栏标题删 `<Play size={12}/>`,lucide-react import 同步移除 |
| frontend/src/components/TourDialog.tsx | 修改 | 弹窗标题删 `<Play size={15}/>`,span 去 `tour-title-ico` 类,import 移除 |
| frontend/src/styles/globals.css | 修改 | `.tour-title-ico` 规则替换为一行注释(icon 已移除) |

## 占位与待办

- 无

## 核对记录(2026-09-29,浏览器实测,后端 8000 / 前端 5173)

- 侧栏「平台导览」与弹窗标题均无 SVG icon ✅
- 弹窗功能完好:「开始导览」可点开、首次登录自动弹出、无 console error ✅
- 截图:`report/01-dialog-no-icon.png`

## 待开发支持清单

- 无
