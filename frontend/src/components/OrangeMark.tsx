/**
 * OrangeMark — 品牌 Logo「旗橙」:一颗橙子(用户定案 2026-09-24,替代原三段升旗)
 * 设计:橙色渐变果身 + 高光 + 绿叶短梗;viewBox 32×32,尺寸由 size 控制。
 * 说明:侧栏深色方块底(.logo-mark 容器提供)与登录/认证页白底均适配 ——
 * 橙子主体为亮橙色,在深/浅底上对比度都足够。
 */

export function OrangeMark({ size = 17 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden style={{ display: 'block' }}>
      {/* 果身:橙子(径向渐变,左上受光) */}
      <defs>
        <radialGradient id="orangeBody" cx="38%" cy="34%" r="72%">
          <stop offset="0%" stopColor="#fdba74" />
          <stop offset="55%" stopColor="#f97316" />
          <stop offset="100%" stopColor="#ea580c" />
        </radialGradient>
      </defs>
      <circle cx="16" cy="18.5" r="11" fill="url(#orangeBody)" />
      {/* 果蒂凹点 */}
      <ellipse cx="16" cy="8.6" rx="1.8" ry="1.1" fill="#c2410c" opacity="0.55" />
      {/* 短梗 */}
      <rect x="15.3" y="5.2" width="1.4" height="3.4" rx="0.7" fill="#92400e" />
      {/* 叶:向右上方舒展 */}
      <path
        d="M17 6.6 C20.4 4.2 24.4 4.4 26.6 5.6 C25 8.6 20.6 9.6 17.6 8.2 Z"
        fill="#16a34a"
      />
      <path d="M17.9 6.9 C20.6 5.9 23.2 5.8 25.3 6.2" stroke="#15803d" strokeWidth="0.6" fill="none" opacity="0.7" />
      {/* 高光 */}
      <ellipse cx="11.6" cy="15" rx="2.4" ry="3.4" fill="#ffffff" opacity="0.35" transform="rotate(-24 11.6 15)" />
      {/* 橙皮质感点 */}
      <g fill="#c2410c" opacity="0.28">
        <circle cx="19.5" cy="15.5" r="0.5" />
        <circle cx="21" cy="19" r="0.5" />
        <circle cx="18" cy="23" r="0.5" />
        <circle cx="13.5" cy="24" r="0.5" />
        <circle cx="12" cy="20" r="0.5" />
      </g>
    </svg>
  )
}
