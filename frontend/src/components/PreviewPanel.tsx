/**
 * PreviewPanel — 任务工作台预览区
 * - 空态: "服务未启动"
 * - 有 URL: 操作栏 + iframe 嵌入
 * - iframe 加载失败/超时(8s): Alert + 重试按钮
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { ExternalLink } from 'lucide-react'
import { Alert } from './ui/Alert'
import { Button } from './ui/Button'

interface PreviewPanelProps {
  previewUrl: string | null
}

const LOAD_TIMEOUT_MS = 8000

export function PreviewPanel({ previewUrl }: PreviewPanelProps) {
  const [loadFailed, setLoadFailed] = useState(false)
  const [iframeKey, setIframeKey] = useState(0)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // 每次 previewUrl 变化,重置失败态
  useEffect(() => {
    setLoadFailed(false)
    setIframeKey((k) => k + 1)
  }, [previewUrl])

  // 8s 超时检测
  useEffect(() => {
    if (!previewUrl || loadFailed) return
    timerRef.current = setTimeout(() => {
      setLoadFailed(true)
    }, LOAD_TIMEOUT_MS)
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current)
    }
  }, [previewUrl, loadFailed, iframeKey])

  const handleLoad = useCallback(() => {
    if (timerRef.current) clearTimeout(timerRef.current)
    setLoadFailed(false)
  }, [])

  const handleError = useCallback(() => {
    if (timerRef.current) clearTimeout(timerRef.current)
    setLoadFailed(true)
  }, [])

  const handleRetry = useCallback(() => {
    setLoadFailed(false)
    setIframeKey((k) => k + 1)
  }, [])

  const handleOpenNew = useCallback(() => {
    if (previewUrl) window.open(previewUrl, '_blank')
  }, [previewUrl])

  // 顶部小标题
  const header = (
    <div className="flex items-center justify-between px-3 h-8 shrink-0 border-b border-border">
      <span className="text-xs text-text-secondary font-medium">预览</span>
    </div>
  )

  // 空态: 服务未启动
  if (!previewUrl) {
    return (
      <div className="flex flex-col w-full h-full min-h-0">
        {header}
        <div className="flex-1 flex items-center justify-center text-text-secondary text-sm">
          服务未启动
        </div>
      </div>
    )
  }

  // 加载失败态
  if (loadFailed) {
    return (
      <div className="flex flex-col w-full h-full min-h-0">
        {header}
        <div className="flex-1 flex items-center justify-center p-4">
          <Alert variant="error" className="max-w-sm">
            <div className="flex flex-col gap-2">
              <span>加载失败,请重试或查看终端日志</span>
              <Button variant="outline" size="sm" onClick={handleRetry}>
                重试
              </Button>
            </div>
          </Alert>
        </div>
      </div>
    )
  }

  // 正常态: iframe 嵌入
  return (
    <div className="flex flex-col w-full h-full min-h-0">
      {/* 操作栏:左侧标题 + 右侧"在新窗口打开"按钮 */}
      <div className="flex items-center justify-between px-3 h-8 shrink-0 border-b border-border">
        <span className="text-xs text-text-secondary font-medium">预览</span>
        <Button variant="outline" size="sm" onClick={handleOpenNew}>
          <ExternalLink className="w-3.5 h-3.5 mr-1" />
          在新窗口打开
        </Button>
      </div>
      {/* iframe 全宽高度自适应 */}
      <div className="flex-1 min-h-0">
        <iframe
          key={iframeKey}
          src={previewUrl}
          title="预览"
          className="w-full h-full border border-border rounded-md"
          onLoad={handleLoad}
          onError={handleError}
        />
      </div>
    </div>
  )
}
