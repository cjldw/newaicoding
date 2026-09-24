import { useCallback, useEffect, useState } from 'react'

/**
 * R30 黑白主题切换 hook。
 *
 * 行为契约(DEVPLAN/R30.md「业务/交互规则」):
 * - 首次访问(localStorage 无值):跟随系统 prefers-color-scheme,不落盘 → 系统变更实时跟随
 * - 用户点击切换:即时生效 + 写 localStorage('theme'),此后不再跟随系统
 * - localStorage 被禁用:静默失败,每次访问跟随系统(V1 接受)
 * - 浏览器不支持 matchMedia:默认亮色
 *
 * 注:分片实现要点 2 的示例代码在 effect 里无条件写 localStorage,会使
 * "首次访问跟随系统"退化为"首次访问即固化"——以同分片「业务/交互规则」
 * 表为准,持久化只发生在用户显式切换(toggle)时。
 */
export type Theme = 'light' | 'dark'

const THEME_KEY = 'theme'

function readPersisted(): string | null {
  // localStorage 被禁用/隐私模式:静默降级为跟随系统
  try {
    return localStorage.getItem(THEME_KEY)
  } catch {
    return null
  }
}

/** 初始主题:已持久化(light/dark)→ 用存储值;否则跟随系统;不支持 matchMedia → 亮色 */
function detectInitialTheme(): Theme {
  const saved = readPersisted()
  if (saved === 'light' || saved === 'dark') {
    return saved
  }
  try {
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
  } catch {
    return 'light'
  }
}

export function useTheme() {
  const [theme, setTheme] = useState<Theme>(detectInitialTheme)

  // 主题应用:每次变化即时写 <html data-theme>(无页面刷新,CSS 变量随之切换)
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
  }, [theme])

  // 系统主题变更监听:handler 内实时复查 localStorage——
  // 用户切换(light/dark 落盘)后自动停跟随,无需重建监听
  useEffect(() => {
    let media: MediaQueryList
    try {
      media = window.matchMedia('(prefers-color-scheme: dark)')
    } catch {
      // 浏览器不支持 matchMedia:保持默认亮色,不监听
      return
    }
    const handler = (e: MediaQueryListEvent) => {
      const persisted = readPersisted()
      // 仅当用户未显式选择时跟随系统(交互规则第 3/4 行)
      if (persisted === 'light' || persisted === 'dark') {
        return
      }
      setTheme(e.matches ? 'dark' : 'light')
    }
    media.addEventListener('change', handler)
    return () => media.removeEventListener('change', handler)
  }, [])

  // 切换:更新状态 + 持久化用户选择(localStorage 禁用时静默失败)
  const toggle = useCallback(() => {
    setTheme(prev => {
      const next: Theme = prev === 'light' ? 'dark' : 'light'
      try {
        localStorage.setItem(THEME_KEY, next)
      } catch {
        // 静默失败:本主题仅当前会话生效(V1 接受,分片「错误处理行」)
      }
      return next
    })
  }, [])

  return { theme, toggle }
}
