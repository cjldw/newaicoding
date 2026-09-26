/**
 * useDebounce — 值防抖(输入停顿 delay 毫秒后才同步,R1.F2 分支预览接口防抖用)
 */
import { useEffect, useState } from 'react'

export function useDebounce<T>(value: T, delay = 300): T {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay)
    return () => clearTimeout(timer)
  }, [value, delay])
  return debounced
}
