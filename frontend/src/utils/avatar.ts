/**
 * 头像工具(R28)— 自 MainLayout 抽出,供顶栏/个人资料页复用
 * - getAvColor: 无头像(或加载失败)时按用户名 hash 取背景色
 * - getInitial: 首字母回退
 */

/** 头像背景色:按用户名/姓名首字映射(对齐 vp 原型,原 MainLayout.tsx:86-100) */
const AV_COLORS: Record<string, string> = {
  luowen: '#3b82f6', wangq: '#ec4899', liming: '#10b981',
  zhangy: '#f59e0b', chenx: '#8b5cf6',
}

export function getAvColor(name?: string): string {
  if (!name) return '#6b7280'
  const key = name.toLowerCase()
  for (const k of Object.keys(AV_COLORS)) {
    if (key.includes(k)) return AV_COLORS[k]
  }
  // 按首字符 hash 取色
  const palette = ['#3b82f6', '#ec4899', '#10b981', '#f59e0b', '#8b5cf6', '#ef4444', '#06b6d4']
  let h = 0
  for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) & 0x7fffffff
  return palette[h % palette.length]
}

/** 姓名首字(头像用) */
export function getInitial(name?: string | null): string {
  if (!name) return '?'
  return name.charAt(0)
}

/**
 * 头像加载失败记忆(BUG-UI-072 建议方案②/R28.F2,模块级 Set)
 * - 同一失效 avatar URL 会话内只请求一次:渲染时命中集合直接走首字母回退,不再发请求
 * - onError 时记入集合;换头像产生新 URL 自然不命中;会话级记忆,刷新后重试一次属可接受行为
 */
const failedAvatarUrls = new Set<string>()

/** 该 avatar URL 是否已记为加载失败(命中则渲染时跳过 <img>,不发请求) */
export function isAvatarUrlFailed(url?: string | null): boolean {
  return !!url && failedAvatarUrls.has(url)
}

/** 记录一次 avatar URL 加载失败(onError 回调里调用) */
export function markAvatarUrlFailed(url?: string | null): void {
  if (url) failedAvatarUrls.add(url)
}
