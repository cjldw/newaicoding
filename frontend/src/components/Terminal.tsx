/**
 * Terminal 组件 - xterm.js 封装
 * - WebSocket 连接终端 pty
 * - 支持 resize / input / output / ai_output 协议
 * - 断线 3 秒自动重连
 */
import { useEffect, useRef } from 'react'
import { Terminal as XTerm } from 'xterm'
import { FitAddon } from 'xterm-addon-fit'
import { WebLinksAddon } from 'xterm-addon-web-links'
import 'xterm/css/xterm.css'
import { useAuthStore } from '@/stores/authStore'

interface TerminalProps {
  wsUrl: string
  onOpen?: () => void
  /** 挂载后回传 xterm 实例(供面板导出日志/全屏适配),卸载时回传 null */
  attachTerm?: (term: XTerm | null) => void
}

/** 将 http(s) URL 转为 ws(s) */
function toWsUrl(httpUrl: string): string {
  return httpUrl.replace(/^http/, 'ws')
}

/** 构建带 token 的完整 WebSocket URL */
function buildWsUrl(raw: string): string {
  const token = useAuthStore.getState().token
  const base = raw.startsWith('ws') ? raw : toWsUrl(raw)
  // 相对路径补全 host
  const abs = base.startsWith('/') ? `${location.origin.replace(/^http/, 'ws')}${base}` : base
  return token ? `${abs}${abs.includes('?') ? '&' : '?'}token=${token}` : abs
}

export function Terminal({ wsUrl, onOpen, attachTerm }: TerminalProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  // ref 中转避免 attachTerm 变化触发 effect 重跑(ws 重连)
  const attachRef = useRef(attachTerm)
  attachRef.current = attachTerm

  useEffect(() => {
    const el = containerRef.current
    if (!el) return

    const term = new XTerm({
      theme: { background: '#1e1e1e' },
      fontFamily: 'var(--font-mono)',
      scrollback: 5000,
      cursorBlink: true,
    })
    const fitAddon = new FitAddon()
    const webLinksAddon = new WebLinksAddon()
    term.loadAddon(fitAddon)
    term.loadAddon(webLinksAddon)
    term.open(el)
    // 初始 fit
    requestAnimationFrame(() => fitAddon.fit())
    // 回传实例(BUG-UI-064:面板导出日志用)
    attachRef.current?.(term)

    let ws: WebSocket | null = null
    let disposed = false
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null

    const sendResize = () => {
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({
          type: 'resize',
          cols: term.cols,
          rows: term.rows,
        }))
      }
    }

    // ResizeObserver → fit + 发送 resize
    const ro = new ResizeObserver(() => {
      fitAddon.fit()
      sendResize()
    })
    ro.observe(el)

    // xterm onData → 发送 input(本地不回显)
    const dataDisposable = term.onData((data) => {
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'input', data }))
      }
    })

    const connect = () => {
      if (disposed) return
      ws = new WebSocket(buildWsUrl(wsUrl))
      ws.onopen = () => {
        sendResize()
        onOpen?.()
      }
      ws.onmessage = (ev) => {
        try {
          const msg = JSON.parse(ev.data)
          if (msg.type === 'output' && typeof msg.data === 'string') {
            term.write(msg.data)
          } else if (msg.type === 'ai_output' && typeof msg.data === 'string') {
            // ai_output 青色高亮写入(前缀 [ai] 已含)
            term.write(`\x1b[36m${msg.data}\x1b[0m`)
          }
        } catch {
          // 非 JSON 直接写入
          term.write(ev.data)
        }
      }
      ws.onclose = () => {
        if (disposed) return
        // 3 秒后重连(attach 复用 pty)
        reconnectTimer = setTimeout(connect, 3000)
      }
    }

    connect()

    return () => {
      disposed = true
      attachRef.current?.(null)
      if (reconnectTimer) clearTimeout(reconnectTimer)
      dataDisposable.dispose()
      ro.disconnect()
      ws?.close()
      term.dispose()
    }
  }, [wsUrl, onOpen])

  return (
    <div
      ref={containerRef}
      className="w-full h-full min-h-0 flex-1"
      style={{ background: '#1e1e1e' }}
    />
  )
}
