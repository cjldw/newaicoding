# 设计稿落地:登录页视觉优化(去业余感:Logo + 字体)

> 创建日期:2026-09-25
> 状态:完成
> 分支:main(改动仅在 main 上)

## 页面进度表

| 页面/区块 | 状态 | 设计规范文件 | 备注 |
|---|---|---|---|
| AuthLogo 品牌区(登录/注册/找回/重置共用) | ✅ | 本文件「设计规范要点」 | 用户定案:深色圆角方块 |
| 登录页标题区与细节 | ✅ | 本文件「设计规范要点」 | 标题层级 + 内联样式收敛 |

## 设计稿来源

- 无外部设计稿;用户口述优化诉求「login 页面看起来不这么业余,logo+字体有点粗糙」
- 品牌基线:favicon `frontend/public/logo.svg` 与侧栏 `.logo-mark` 的深色方块 + 橙子语言

## 设计规范要点(用户定案 2026-09-25)

- Logo 承托:56px 深色圆角方块 `#18181B`(zinc-900,与 favicon rx=8/32 等比 → 圆角 14px),OrangeMark 32px 居中
- 品牌名「旗橙」:20px / font-weight 600 / letter-spacing 0.02em / color var(--text)
- 副标语「AI Web 开发平台」:12px / var(--muted)
- 登录标题区:主标题「登录」20px/600 + muted 副标题;内联 style 收敛为 class
- 链接:hover 过渡(透明度/下划线),不再 12px 纯蓝裸链

## 改动清单

| 文件 | 操作 | 说明 |
|---|---|---|
| frontend/src/pages/auth/AuthLogo.tsx | 修改 | 深色方块承托 + 品牌名排版升级 |
| frontend/src/pages/auth/Login.tsx | 修改 | 标题层级 + 内联样式收敛(登录逻辑不动) |
| frontend/src/styles/globals.css | 修改 | auth 品牌区样式 + 链接过渡 |

## 占位与待办

- (无)

## 待开发支持清单

- (无,纯前端视觉改动,不涉及接口)
