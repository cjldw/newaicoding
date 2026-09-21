/**
 * TerminalPanel - 多 Tab 终端面板
 * - 空态"点击新建终端";右上"新建终端"按钮
 * - 每个 Tab 调 createSession 得 ws_url
 * - Tab 栏(x 关闭)+ 切换;关闭调 onClose(session_id)
 */
import { useCallback, useState } from 'react'
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
}

export function TerminalPanel({ createSession, onClose }: TerminalPanelProps) {
  const [tabs, setTabs] = useState<TerminalTab[]>([])
  const [activeId, setActiveId] = useState<string | null>(null)

  const handleCreate = useCallback(async () => {
    try {
      const { session_id, ws_url } = await createSession()
      setTabs((prev) => [...prev, { sessionId: session_id, wsUrl: ws_url }])
      setActiveId(session_id)
    } catch (err) {
      console.error('create terminal session failed', err)
    }
  }, [createSession])

  const handleClose = useCallback(
    (sessionId: string) => {
      setTabs((prev) => prev.filter((t) => t.sessionId !== sessionId))
      if (activeId === sessionId) {
        setTabs((prev) => {
          const next = prev.filter((t) => t.sessionId !== sessionId)
          setActiveId(next[0]?.sessionId ?? null)
          return prev
        })
      }
      onClose?.(sessionId)
    },
    [activeId, onClose],
  )

  // 空态
  if (tabs.length === 0) {
    return (
      <div className="flex flex-col w-full h-full items-center justify-center gap-3 bg-[#1e1e1e] text-zinc-400">
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
    <div className="flex flex-col w-full h-full min-h-0 bg-[#1e1e1e]">
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
        <button
          type="button"
          onClick={handleCreate}
          className="ml-2 px-2 py-0.5 text-xs rounded bg-zinc-700 text-zinc-100 hover:bg-zinc-600 shrink-0"
        >
          新建终端
        </button>
      </div>
      {/* 终端区 - 全宽高度自适应 */}
      <div className="flex-1 min-h-0">
        {active && <Terminal wsUrl={active.wsUrl} />}
      </div>
    </div>
  )
}
