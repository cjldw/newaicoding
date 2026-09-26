/**
 * TerminalPanel - 多 Tab 终端面板
 * - 空态"点击新建终端";右上"新建终端"按钮
 * - 每个 Tab 调 createSession 得 ws_url
 * - Tab 栏(x 关闭)+ 切换;关闭调 onClose(session_id)
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { Download, Maximize2, Minimize2 } from 'lucide-react'
import { Terminal } from './Terminal'

interface TerminalTab {
  sessionId: string
  wsUrl: string
}

interface TerminalPanelProps {
  /** 创建终端会话,返回 {session_id, ws_url} */
  createSession: () => Promise<{ session_id: string; ws_url: string }>
  /** 关闭终端会话 */
  onClose?: (sessionId: string) => void
  /** 全屏(BUG-UI-064:CSS 提升为 fixed 覆盖层,面板不重挂载,xterm 缓冲保留) */
  fullscreen?: boolean
  /** 全屏切换;不传(如 Runner shell Dialog)则不渲染全屏按钮 */
  onToggleFullscreen?: () => void
  /** R26:透传 Terminal(断线行为;默认不传=任务终端既有行为) */
  terminalReconnect?: boolean
  terminalCloseMessage?: string
}

export function TerminalPanel({ createSession, onClose, fullscreen = false, onToggleFullscreen, terminalReconnect, terminalCloseMessage }: TerminalPanelProps) {
  const [tabs, setTabs] = useState<TerminalTab[]>([])
  const [activeId, setActiveId] = useState<string | null>(null)
  const [toast, setToast] = useState<string | null>(null)
  const termRef = useRef<import('xterm').Terminal | null>(null)
  // 终端全屏(对齐对话,2026-09-26):切换计数透传 Terminal → 确定性 refit。
  // ResizeObserver 是常规路径(尺寸变化必触发);fitSignal 兜底「切换当帧布局未稳/同尺寸
  // 不回调」的边角,退出全屏同样触发。首帧 +1 由 Terminal 的 skip-initial 守卫忽略。
  const [fitTick, setFitTick] = useState(0)
  useEffect(() => {
    setFitTick((t) => t + 1)
  }, [fullscreen])

  // toast 自动消失
  useEffect(() => {
    if (!toast) return
    const t = setTimeout(() => setToast(null), 3000)
    return () => clearTimeout(t)
  }, [toast])

  const handleCreate = useCallback(async () => {
    try {
      const { session_id, ws_url } = await createSession()
      setTabs((prev) => [...prev, { sessionId: session_id, wsUrl: ws_url }])
      setActiveId(session_id)
    } catch (err) {
      console.error('create terminal session failed', err)
      // 用户可见错误提示,环境无 Runner 时终端创建必然失败
      const msg = err instanceof Error ? err.message : '终端创建失败'
      setToast(`终端创建失败:${msg}`)
    }
  }, [createSession])

  const handleClose = useCallback(
    (sessionId: string) => {
      // BUG-UI-065:原实现两次 setTabs 且第二次 return prev 覆盖过滤结果(tab 关不掉)
      const next = tabs.filter((t) => t.sessionId !== sessionId)
      setTabs(next)
      if (activeId === sessionId) setActiveId(next[0]?.sessionId ?? null)
      onClose?.(sessionId)
    },
    [tabs, activeId, onClose],
  )

  // 导出当前会话日志(BUG-UI-064:序列化 xterm buffer 为 .log 下载)
  const handleExport = useCallback(() => {
    const term = termRef.current
    if (!term) return
    const buf = term.buffer.active
    const lines: string[] = []
    for (let i = 0; i < buf.length; i++) {
      lines.push(buf.getLine(i)?.translateToString(true) ?? '')
    }
    const blob = new Blob([lines.join('\n')], { type: 'text/plain;charset=utf-8' })
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = `terminal-${(activeId ?? 'session').slice(0, 8)}.log`
    a.click()
    URL.revokeObjectURL(a.href)
  }, [activeId])

  // 空态(占位态也容忍全屏切换:fullscreen 时同样提升为 fixed 覆盖层,
  // 否则全屏中关掉最后一个 Tab 会内联回落、TaskDetail 的 fullscreen 态悬空)
  if (tabs.length === 0) {
    return (
      <div
        className={`flex flex-col w-full h-full items-center justify-center gap-3 bg-[#1e1e1e] text-zinc-400${fullscreen ? ' fixed inset-0 z-[60] p-2' : ' relative'}`}
      >
        {toast && (
          <div className="toast-wrap"><div className="toast">{toast}</div></div>
        )}
        {onToggleFullscreen && (
          <button
            type="button"
            title={fullscreen ? '退出全屏' : '全屏'}
            className="absolute top-2 right-2 px-1.5 py-0.5 text-zinc-400 hover:text-zinc-100"
            onClick={onToggleFullscreen}
          >
            {fullscreen ? <Minimize2 className="w-3.5 h-3.5" /> : <Maximize2 className="w-3.5 h-3.5" />}
          </button>
        )}
        <span>点击新建终端</span>
        <button
          type="button"
          onClick={handleCreate}
          className="px-3 py-1 text-sm rounded bg-zinc-700 text-zinc-100 hover:bg-zinc-600"
        >
          新建终端
        </button>
      </div>
    )
  }

  const active = tabs.find((t) => t.sessionId === activeId) ?? tabs[0]

  return (
    <div
      className={`flex flex-col w-full h-full min-h-0 bg-[#1e1e1e]${fullscreen ? ' fixed inset-0 z-[60] p-2' : ''}`}
    >
      {toast && (
        <div className="toast-wrap"><div className="toast">{toast}</div></div>
      )}
      {/* Tab 栏 */}
      <div className="flex items-center justify-between border-b border-zinc-700 px-2 h-8 shrink-0">
        <div className="flex items-center gap-1 overflow-x-auto">
          {tabs.map((tab) => (
            <div
              key={tab.sessionId}
              className={`flex items-center gap-1 px-2 py-1 text-xs cursor-pointer rounded-t ${
                tab.sessionId === active.sessionId
                  ? 'bg-zinc-800 text-zinc-100'
                  : 'text-zinc-400 hover:text-zinc-200'
              }`}
              onClick={() => setActiveId(tab.sessionId)}
            >
              <span>终端</span>
              <button
                type="button"
                className="ml-1 text-zinc-500 hover:text-zinc-100"
                onClick={(e) => {
                  e.stopPropagation()
                  handleClose(tab.sessionId)
                }}
              >
                ×
              </button>
            </div>
          ))}
        </div>
        <div className="flex items-center gap-1 shrink-0">
          <button
            type="button"
            title="导出会话日志"
            className="px-1.5 py-0.5 text-zinc-400 hover:text-zinc-100"
            onClick={handleExport}
          >
            <Download className="w-3.5 h-3.5" />
          </button>
          <button
            type="button"
            onClick={handleCreate}
            className="px-2 py-0.5 text-xs rounded bg-zinc-700 text-zinc-100 hover:bg-zinc-600"
          >
            新建终端
          </button>
          {/* 终端全屏(对齐对话):仅宿主传入 onToggleFullscreen 时渲染(Runner shell Dialog 不支持全屏,避免死按钮) */}
          {onToggleFullscreen && (
            <button
              type="button"
              title={fullscreen ? '退出全屏' : '全屏'}
              className="px-1.5 py-0.5 text-zinc-400 hover:text-zinc-100"
              onClick={onToggleFullscreen}
            >
              {fullscreen ? <Minimize2 className="w-3.5 h-3.5" /> : <Maximize2 className="w-3.5 h-3.5" />}
            </button>
          )}
        </div>
      </div>
      {/* 终端区 - 全宽高度自适应 */}
      <div className="flex-1 min-h-0">
        {active && (
          <Terminal
            wsUrl={active.wsUrl}
            attachTerm={(t) => { termRef.current = t }}
            reconnect={terminalReconnect}
            closeMessage={terminalCloseMessage}
            fitSignal={fitTick}
          />
        )}
      </div>
    </div>
  )
}
