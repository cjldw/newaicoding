/**
 * OrangeMark — 品牌 Logo「旗橙」:橙子 + 三角小旗(2026-09-27 重绘)
 * 设计:橙色渐变果身 + 沿球面弧线的弯月高光;果顶短梗作旗杆,橙渐变三角小旗
 *       向右上展开,呼应品牌名「旗」字;去掉旧版果皮噪点/蒂凹,14px 小尺寸依然干净。
 * viewBox 32×32,尺寸由 size 控制;深色方块底(侧栏/认证页/favicon)与
 * 浅色圆底(对话头像)均适配 —— 果身亮橙,深/浅底对比度都足够。
 */

export function OrangeMark({ size = 17 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden style={{ display: 'block' }}>
      <defs>
        <radialGradient id="orangeBody" cx="38%" cy="32%" r="78%">
          <stop offset="0%" stopColor="#fdba74" />
          <stop offset="55%" stopColor="#f97316" />
          <stop offset="100%" stopColor="#ea580c" />
        </radialGradient>
        <linearGradient id="flagWing" x1="0" y1="0" x2="1" y2="0.2">
          <stop offset="0%" stopColor="#fdba74" />
          <stop offset="100%" stopColor="#f97316" />
        </linearGradient>
      </defs>
      {/* 果身:橙子(径向渐变,左上受光) */}
      <circle cx="16" cy="18.6" r="9.6" fill="url(#orangeBody)" />
      {/* 弯月高光:沿球面左上弧线,圆头端点 */}
      <path
        d="M 8.95 16.04 A 7.5 7.5 0 0 1 13.44 11.55"
        stroke="#ffffff"
        strokeWidth="1.7"
        strokeLinecap="round"
        fill="none"
        opacity="0.32"
      />
      {/* 旗杆:短梗插入果顶 */}
      <rect x="15.45" y="3.8" width="1.3" height="5.6" rx="0.65" fill="#c2410c" />
      {/* 三角小旗:向右上展开(品牌「旗」字) */}
      <path d="M16.75 3.9 L25.6 6.1 L16.75 8.3 Z" fill="url(#flagWing)" />
    </svg>
  )
}
