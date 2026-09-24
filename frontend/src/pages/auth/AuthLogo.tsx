/**
 * AuthLogo — auth 四页统一 LOGO 组件(R1.F2 / BUG-UI-067)
 * 品牌更名「旗橙」(2026-09-24):LOGO 换为橙子图标 OrangeMark + 品牌名"旗橙",
 * flex-col 水平居中;尺寸对齐注册页现值(48px),品牌名字号与登录页一致(18px/700)。
 */

import { OrangeMark } from '@/components/OrangeMark'

export function AuthLogo() {
  return (
    <div className="flex flex-col items-center">
      <OrangeMark size={48} />
      <b style={{ fontSize: 18, marginTop: 8 }}>旗橙</b>
    </div>
  )
}
