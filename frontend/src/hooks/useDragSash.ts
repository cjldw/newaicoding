/**
 * useDragSash — 工作台分隔条拖拽(R4.F2 / BUG-UI-065)
 * - 水平 sash(调宽度):mousedown 记录起点,mousemove 增量更新并 clamp,mouseup 解绑
 * - 垂直 sash(调高度):horizontal=false,按 y 增量
 * - invert:拖拽方向与尺寸增长相反(如右栏:向左拖 = 增宽)
 */
import { useCallback, useRef, useState } from 'react'

interface SashOptions {
  min: number
  max: number
  /** true = 向左/上拖增大(右侧栏、底部向上) */
  invert?: boolean
  /** true = 调宽度(默认);false = 调高度 */
  horizontal?: boolean
}

export function useDragSash(
  initial: number,
  { min, max, invert = false, horizontal = true }: SashOptions,
): readonly [number, (e: React.MouseEvent) => void] {
  const [size, setSize] = useState(initial)
  const dragging = useRef(false)
  const startPos = useRef(0)
  const startSize = useRef(0)

  const onMouseDown = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault()
      dragging.current = true
      startPos.current = horizontal ? e.clientX : e.clientY
      startSize.current = size

      const onMove = (ev: MouseEvent) => {
        if (!dragging.current) return
        const delta = (horizontal ? ev.clientX : ev.clientY) - startPos.current
        const raw = startSize.current + (invert ? -delta : delta)
        setSize(Math.min(max, Math.max(min, raw)))
      }
      const onUp = () => {
        dragging.current = false
        document.removeEventListener('mousemove', onMove)
        document.removeEventListener('mouseup', onUp)
      }
      document.addEventListener('mousemove', onMove)
      document.addEventListener('mouseup', onUp)
    },
    [size, min, max, invert, horizontal],
  )

  return [size, onMouseDown] as const
}
