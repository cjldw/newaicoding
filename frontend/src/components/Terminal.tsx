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
  /**
   * R26:断线是否 3s 自动重连(默认 true=任务终端既有行为)。
   * Runner shell 会话传 false:断线写"Runner 连接中断"且不重连(判据 11)。
   */
  reconnect?: boolean
  /** 断线且 reconnect=false 时写入 xterm 的提示文案 */
  closeMessage?: string
  /**
   * 终端全屏(2026-09-26):宿主面板全屏切换计数(每次切换 +1)。
   * 变化时延迟双 rAF 走 safeFit(fit + 后端 resize 同步),与 ResizeObserver
   * 形成双保险——容器尺寸变化本会触发 RO,此信号兜底切换当帧布局未稳/尺寸
   * 恰好未变导致 RO 不回调的边角;退出全屏同样触发。挂载首跑跳过(挂载期
   * fit 由 open 双 rAF 路径负责)。
   */
  fitSignal?: number
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

export function Terminal({ wsUrl, onOpen, attachTerm, reconnect = true, closeMessage, fitSignal }: TerminalProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  // ref 中转避免 attachTerm 变化触发 effect 重跑(ws 重连)
  const attachRef = useRef(attachTerm)
  attachRef.current = attachTerm
  // 全屏 refit 入口:主 effect 建好 safeFit 后回填,fitSignal effect 经此触发
  const safeFitRef = useRef<(() => void) | null>(null)

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
    // BUG-046:open 延迟双 rAF(见下方 openFrame 注释),此处先建实例与监听
    let ws: WebSocket | null = null
    let disposed = false
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null

    // BUG-046:fit 统一守卫——Runner 终端 Dialog(150ms 动画)/面板布局期间容器
    // 尺寸未稳,过早 fit 会撞上 xterm RenderService 未就绪
    // (RenderService.ts dimensions undefined 崩溃);safeFit 统一守卫
    const safeFit = () => {
      if (disposed) return
      // 尺寸守卫:容器未布局/动画中(width/height 为 0)绝不 fit
      if (el.clientWidth <= 0 || el.clientHeight <= 0) return
      try {
        fitAddon.fit()
        sendResize()
      } catch {
        // 渲染器尚未就绪:忽略本轮,ResizeObserver 下一帧会再次触发
      }
    }
    const sendResize = () => {
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({
          type: 'resize',
          cols: term.cols,
          rows: term.rows,
        }))
      }
    }
    // 回填 ref,供 fitSignal(全屏切换)effect 触发(dispose 后 safeFit 仍受 disposed 守卫)
    safeFitRef.current = safeFit

    // ResizeObserver → fit + 发送 resize
    // BUG-046:observe 后首帧立即回调 + Dialog 动画期间频繁回调,统一走 safeFit 守卫
    // (此前无守卫,动画期 fit 直接抛 TypeError 导致终端白屏)
    const ro = new ResizeObserver(() => safeFit())
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
        // R26:reconnect=false(Runner shell)→ 写断线文案,不自动重连(判据 11)
        if (!reconnect) {
          term.write(`\r\n\x1b[31m${closeMessage || '连接已断开'}\x1b[0m\r\n`)
          return
        }
        // 3 秒后重连(attach 复用 pty)
        reconnectTimer = setTimeout(connect, 3000)
      }
    }

    // BUG-046:open 延迟双 rAF——① 等 Dialog 150ms 动画/布局稳定后再 open+fit;
    // ② React StrictMode 开发期双挂载:首挂载若同步 open(),xterm Viewport 内部
    // 调度的 rAF 刷新会在 dispose 后读已置空的 _renderService,抛同款
    // dimensions undefined;延迟后首挂载 dispose 前未 open,rAF 回调按 disposed
    // 跳过,僵尸实例不再产生(生产构建无 StrictMode,时序差异无感)
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        if (disposed) return
        term.open(el)
        // 回传实例(BUG-UI-064:面板导出日志用)
        attachRef.current?.(term)
        safeFit()
        connect()
      })
    })

    return () => {
      disposed = true
      attachRef.current?.(null)
      if (reconnectTimer) clearTimeout(reconnectTimer)
      dataDisposable.dispose()
      ro.disconnect()
      ws?.close()
      term.dispose()
    }
  }, [wsUrl, onOpen, reconnect, closeMessage])

  // 全屏切换 → 确定性 refit(见 fitSignal 注释):双 rAF 等 fixed 覆盖层布局稳定后 safeFit
  // (safeFit 内部:尺寸守卫 + fitAddon.fit() + ws resize 同步后端,退出全屏同路径)
  const prevFitSignal = useRef<number | undefined>(undefined)
  useEffect(() => {
    const changed = prevFitSignal.current !== undefined && prevFitSignal.current !== fitSignal
    prevFitSignal.current = fitSignal
    if (!changed) return
    let raf2 = 0
    const raf1 = requestAnimationFrame(() => {
      raf2 = requestAnimationFrame(() => safeFitRef.current?.())
    })
    return () => {
      cancelAnimationFrame(raf1)
      cancelAnimationFrame(raf2)
    }
  }, [fitSignal])

  return (
    <div
      ref={containerRef}
      className="w-full h-full min-h-0 flex-1"
      style={{ background: '#1e1e1e' }}
    />
  )
}
