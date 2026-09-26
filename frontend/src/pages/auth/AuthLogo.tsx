/**
 * AuthLogo — auth 四页统一 LOGO 组件(R1.F2 / BUG-UI-067)
 * 品牌更名「旗橙」(2026-09-24):橙子图标 OrangeMark 承托于 56px 深色圆角方块
 * (#18181B,与 favicon 同稿,radius 14px = rx 8/32 等比),方块居左、品牌名 + 副标语
 * 在右侧同行纵向成组(2026-09-25 反馈:logo 和字体在同一行)。
 * 2026-09-25 登录页视觉优化:去内联样式收敛为 globals.css .auth-* 类,四页共用只动视觉不动接口。
 */

import { OrangeMark } from '@/components/OrangeMark'

export function AuthLogo() {
  return (
    <div className="auth-logo">
      <div className="auth-logo-mark">
        <OrangeMark size={32} />
      </div>
      <b className="auth-brand">旗橙</b>
      <span className="auth-tagline">AI Web 开发平台</span>
    </div>
  )
}
