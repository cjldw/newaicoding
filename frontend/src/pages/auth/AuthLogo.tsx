/**
 * AuthLogo — auth 四页统一 LOGO 组件(R1.F2 / BUG-UI-067)
 * 用户指令:登录页 LOGO 改居中,且忘记密码/注册页与登录页使用一致的 LOGO 图。
 * 实现:LOGO 图(/logo.svg,三段升旗标)+ 品牌名"旗程",flex-col 水平居中;
 * 尺寸对齐注册页现值(w-12 h-12),品牌名字号对齐登录页现值(18px/700)。
 */

export function AuthLogo() {
  return (
    <div className="flex flex-col items-center">
      <img src="/logo.svg" alt="旗程 Logo" className="w-12 h-12" />
      <b style={{ fontSize: 18, marginTop: 8 }}>旗程</b>
    </div>
  )
}
