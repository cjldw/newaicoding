/**
 * Editor — Monaco 封装
 * - 深色主题 vs-dark
 * - 500ms 防抖 onChange 自动保存
 * - Ctrl+S 立即保存
 * - >2MB 只读提示
 */

import { useRef, useCallback, useEffect } from 'react'
import Editor, { loader, type OnMount } from '@monaco-editor/react'
// BUG-UI-065:默认走 jsdelivr CDN 加载 monaco,受限网络下 ERR_CONNECTION_RESET(编辑器空白)。
// 本地安装 monaco-editor 并 loader.config 指向本地包,vite 打包随应用分发,不再依赖 CDN。
import * as monaco from 'monaco-editor'

loader.config({ monaco })

interface EditorProps {
  value: string
  readOnly?: boolean
  onChange?: (value: string) => void
  onSave?: (value: string) => void
  language?: string
  path?: string
}

const MAX_SIZE = 2 * 1024 * 1024 // 2MB

export default function CodeEditor({
  value,
  readOnly = false,
  onChange,
  onSave,
  language,
  path,
}: EditorProps) {
  const editorRef = useRef<any>(null) // Monaco 类型命名空间未装 monaco-editor 包,用 any 兜底
  const debounceTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const onChangeRef = useRef(onChange)
  const onSaveRef = useRef(onSave)
  onChangeRef.current = onChange
  onSaveRef.current = onSave

  // 检测是否超大文件
  const isOversize = value.length > MAX_SIZE

  const handleMount: OnMount = useCallback((editorInstance) => {
    editorRef.current = editorInstance

    // Ctrl+S 立即保存
    editorInstance.addCommand(
      // eslint-disable-next-line no-bitwise
      2048 | 49, // KeyMod.CtrlCmd | KeyCode.KeyS
      () => {
        const val = editorInstance.getValue()
        onSaveRef.current?.(val)
      }
    )
  }, [])

  const handleChange = useCallback(
    (val: string | undefined) => {
      if (val === undefined || readOnly || isOversize) return
      // 500ms 防抖自动保存
      if (debounceTimer.current) clearTimeout(debounceTimer.current)
      debounceTimer.current = setTimeout(() => {
        onChangeRef.current?.(val)
        onSaveRef.current?.(val)
      }, 500)
    },
    [readOnly, isOversize]
  )

  // 清理 timer
  useEffect(() => {
    return () => {
      if (debounceTimer.current) clearTimeout(debounceTimer.current)
    }
  }, [])

  // 超大文件只读提示
  if (isOversize) {
    return (
      <div className="flex items-center justify-center h-full bg-[#1e1e1e] text-text-muted text-sm">
        只读模式,不可编辑
      </div>
    )
  }

  return (
    <Editor
      height="100%"
      language={language}
      path={path}
      value={value}
      theme="vs-dark"
      onChange={handleChange}
      onMount={handleMount}
      options={{
        readOnly,
        minimap: { enabled: false },
        fontSize: 14,
        lineNumbers: 'on',
        scrollBeyondLastLine: false,
        automaticLayout: true,
        tabSize: 2,
        wordWrap: 'on',
      }}
    />
  )
}
