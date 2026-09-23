/**
 * useToast — 简易全局 toast hook
 * 基于 globals.css 的 .toast-wrap / .toast 样式
 */

import { useState, useEffect, useCallback } from 'react'

export type ToastType = 'ok' | 'err' | 'info'

export interface ToastState {
  type: ToastType
  text: string
}

/**
 * 返回 [toast, showToast, ToastEl]
 * - toast: 当前状态(null 表示隐藏)
 * - showToast(type, text): 显示 toast
 * - ToastEl: 渲染元素,放在 JSX 末尾即可
 */
export function useToast(autoHideMs = 2500) {
  const [toast, setToast] = useState<ToastState | null>(null)

  useEffect(() => {
    if (!toast) return
    const t = setTimeout(() => setToast(null), autoHideMs)
    return () => clearTimeout(t)
  }, [toast, autoHideMs])

  const showToast = useCallback((type: ToastType, text: string) => {
    setToast({ type, text })
  }, [])

  const ToastEl = toast ? (
    <div className="toast-wrap" style={{ zIndex: 9999 }}>
      <div className={`toast toast-${toast.type}`}>
        {toast.text}
      </div>
    </div>
  ) : null

  return [toast, showToast, ToastEl] as const
}
