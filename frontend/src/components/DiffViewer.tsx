/**
 * DiffViewer — 差异查看器封装
 * - 深色主题
 * - 「接受」/「拒绝」按钮
 * - 查看 Diff 提示
 */

import { useMemo } from 'react'
import ReactDiffViewer, { DiffMethod } from 'react-diff-viewer-continued'
import { Button } from './ui/Button'

interface DiffViewerProps {
  oldValue: string
  newValue: string
  oldTitle?: string
  newTitle?: string
  onAccept?: () => void
  onReject?: () => void
  splitView?: boolean
}

export default function DiffViewer({
  oldValue,
  newValue,
  oldTitle = '原始版本',
  newTitle = '修改版本',
  onAccept,
  onReject,
  splitView = true,
}: DiffViewerProps) {
  // 深色主题样式
  const darkTheme = useMemo(
    () => ({
      variables: {
        dark: {
          diffViewerBackground: '#1e1e1e',
          diffViewerColor: '#d4d4d4',
          addedBackground: '#1e3a1e',
          addedColor: '#d4d4d4',
          removedBackground: '#3a1e1e',
          removedColor: '#d4d4d4',
          wordAddedBackground: '#2d4a2d',
          wordAddedColor: '#d4d4d4',
          wordRemovedBackground: '#4a2d2d',
          wordRemovedColor: '#d4d4d4',
          addedGutterBackground: '#1e3a1e',
          addedGutterColor: '#d4d4d4',
          removedGutterBackground: '#3a1e1e',
          removedGutterColor: '#d4d4d4',
          gutterBackground: '#252526',
          gutterBackgroundDark: '#252526',
          highlightBackground: '#264f78',
          highlightColor: '#d4d4d4',
          codeFoldGutterBackground: '#252526',
          codeFoldBackground: '#252526',
          emptyLineBackground: '#1e1e1e',
        },
      },
    }),
    []
  )

  return (
    <div className="flex flex-col h-full bg-[#1e1e1e]">
      {/* 操作栏 */}
      {(onAccept || onReject) && (
        <div className="flex items-center justify-between px-4 py-2 border-b border-border bg-surface">
          <div className="text-sm text-text-muted">AI 修改了此文件</div>
          <div className="flex gap-2">
            {onReject && (
              <Button variant="outline" size="sm" onClick={onReject}>
                拒绝
              </Button>
            )}
            {onAccept && (
              <Button variant="primary" size="sm" onClick={onAccept}>
                接受
              </Button>
            )}
          </div>
        </div>
      )}

      {/* Diff 视图 */}
      <div className="flex-1 overflow-auto">
        <ReactDiffViewer
          oldValue={oldValue}
          newValue={newValue}
          splitView={splitView}
          leftTitle={oldTitle}
          rightTitle={newTitle}
          compareMethod={DiffMethod.WORDS}
          useDarkTheme={true}
          styles={darkTheme}
          showDiffOnly={false}
        />
      </div>
    </div>
  )
}
