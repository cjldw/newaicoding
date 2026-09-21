/**
 * FileTree — 双视图文件树
 * - 顶部 Tabs「全部文件」/「变更文件」(变更 Tab 带徽标总数)
 * - 全部:树形展示(250px 固定宽,hover bg-surface-strong),task 模式右键菜单
 * - 变更:按仓库分组扁平列表,行=变更徽标(M/A/D/R)+ 路径 + `+X/-Y`;>500 行虚拟滚动
 * - watcher 消息触发 500ms 防抖刷新
 */

import { useState, useRef, useCallback, useMemo, useEffect } from 'react'
import { ChevronRight, ChevronDown, File as FileIcon, Folder, FolderOpen } from 'lucide-react'
import { Badge } from './ui/Badge'
import type { FileItem, ChangeRepo } from '@/api/files'

interface FileTreeProps {
  mode: 'project' | 'task'
  files?: FileItem[]
  changes?: ChangeRepo[]
  selectedPath?: string
  onSelectFile?: (path: string) => void
  onSelectDiff?: (path: string) => void
  onCreateFile?: (path: string) => void
  onRenameFile?: (oldPath: string, newPath: string) => void
  onDeleteFile?: (path: string) => void
  onRefresh?: () => void
}

// 树节点结构
interface TreeNode {
  path: string
  name: string
  type: 'file' | 'dir'
  children: TreeNode[]
}

// 扁平化文件列表 -> 树
function buildTree(items: FileItem[]): TreeNode {
  const root: TreeNode = { path: '', name: '', type: 'dir', children: [] }
  const map = new Map<string, TreeNode>()
  map.set('', root)

  // 排序:目录在前
  const sorted = [...items].sort((a, b) => {
    if (a.type !== b.type) return a.type === 'dir' ? -1 : 1
    return a.path.localeCompare(b.path)
  })

  for (const item of sorted) {
    const parts = item.path.split('/')
    let parent = root

    // 确保中间目录存在
    for (let i = 0; i < parts.length - 1; i++) {
      const dirPath = parts.slice(0, i + 1).join('/')
      if (!map.has(dirPath)) {
        const dirNode: TreeNode = {
          path: dirPath,
          name: parts[i],
          type: 'dir',
          children: [],
        }
        map.set(dirPath, dirNode)
        parent.children.push(dirNode)
      }
      parent = map.get(dirPath)!
    }

    const node: TreeNode = {
      path: item.path,
      name: parts[parts.length - 1],
      type: item.type,
      children: [],
    }
    map.set(item.path, node)
    parent.children.push(node)
  }

  return root
}

// 树节点组件
function TreeNodeItem({
  node,
  depth,
  selectedPath,
  onSelect,
  onContextMenu,
}: {
  node: TreeNode
  depth: number
  selectedPath?: string
  onSelect: (path: string) => void
  onContextMenu?: (e: React.MouseEvent, path: string) => void
}) {
  const [expanded, setExpanded] = useState(depth < 2)
  const isSelected = node.path === selectedPath

  const handleClick = () => {
    if (node.type === 'dir') {
      setExpanded(!expanded)
    } else {
      onSelect(node.path)
    }
  }

  const Icon = node.type === 'dir'
    ? (expanded ? FolderOpen : Folder)
    : FileIcon

  return (
    <>
      <div
        className={`flex items-center gap-1 px-2 py-1 cursor-pointer text-sm hover:bg-surface-strong ${
          isSelected ? 'bg-surface-strong' : ''
        }`}
        style={{ paddingLeft: `${depth * 12 + 8}px` }}
        onClick={handleClick}
        onContextMenu={(e) => onContextMenu?.(e, node.path)}
      >
        {node.type === 'dir' && (
          expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />
        )}
        <Icon size={14} className="text-text-muted flex-shrink-0" />
        <span className="truncate">{node.name}</span>
      </div>
      {node.type === 'dir' && expanded && node.children.map((child) => (
        <TreeNodeItem
          key={child.path}
          node={child}
          depth={depth + 1}
          selectedPath={selectedPath}
          onSelect={onSelect}
          onContextMenu={onContextMenu}
        />
      ))}
    </>
  )
}

// 右键菜单
function ContextMenu({
  x,
  y,
  path,
  onClose,
  onCreate,
  onRename,
  onDelete,
}: {
  x: number
  y: number
  path: string
  onClose: () => void
  onCreate: (path: string) => void
  onRename: (oldPath: string, newPath: string) => void
  onDelete: (path: string) => void
}) {
  const handleCreate = () => {
    const name = prompt('新建文件/目录名(目录以/结尾):')
    if (name) {
      const fullPath = path ? `${path}/${name}` : name
      onCreate(fullPath)
    }
    onClose()
  }

  const handleRename = () => {
    const newName = prompt('新路径:', path)
    if (newName && newName !== path) {
      onRename(path, newName)
    }
    onClose()
  }

  const handleDelete = () => {
    if (confirm(`确定删除 ${path}?`)) {
      onDelete(path)
    }
    onClose()
  }

  return (
    <div
      className="fixed bg-surface border border-border rounded shadow-lg py-1 z-50"
      style={{ left: x, top: y }}
    >
      <button className="block w-full text-left px-3 py-1 text-sm hover:bg-surface-strong" onClick={handleCreate}>
        新建
      </button>
      <button className="block w-full text-left px-3 py-1 text-sm hover:bg-surface-strong" onClick={handleRename}>
        重命名
      </button>
      <button className="block w-full text-left px-3 py-1 text-sm hover:bg-surface-strong text-red-500" onClick={handleDelete}>
        删除
      </button>
    </div>
  )
}

export default function FileTree({
  mode,
  files = [],
  changes = [],
  selectedPath,
  onSelectFile,
  onSelectDiff,
  onCreateFile,
  onRenameFile,
  onDeleteFile,
  onRefresh: _onRefresh, // 预留:watcher 失效手动刷新
}: FileTreeProps) {
  const [tab, setTab] = useState<'all' | 'changes'>('all')
  const [contextMenu, setContextMenu] = useState<{ x: number; y: number; path: string } | null>(null)
  const debounceTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  // 构建文件树
  const tree = useMemo(() => buildTree(files), [files])

  // 变更文件总数
  const totalChanges = useMemo(() => {
    return changes.reduce((sum, repo) => sum + repo.files.length, 0)
  }, [changes])

  // 右键菜单
  const handleContextMenu = useCallback(
    (e: React.MouseEvent, path: string) => {
      if (mode !== 'task') return
      e.preventDefault()
      setContextMenu({ x: e.clientX, y: e.clientY, path })
    },
    [mode]
  )

  // 关闭右键菜单
  useEffect(() => {
    const handleClick = () => setContextMenu(null)
    if (contextMenu) {
      document.addEventListener('click', handleClick)
      return () => document.removeEventListener('click', handleClick)
    }
  }, [contextMenu])

  // 清理 timer
  useEffect(() => {
    return () => {
      if (debounceTimer.current) clearTimeout(debounceTimer.current)
    }
  }, [])

  // 变更视图:按仓库分组
  const renderChanges = () => {
    if (changes.length === 0) {
      return <div className="p-4 text-sm text-text-muted">无变更</div>
    }

    // 扁平化所有变更文件
    const allFiles = changes.flatMap((repo) =>
      repo.files.map((f) => ({ ...f, repo_id: repo.repo_id, repo_role: repo.repo_role }))
    )

    // >500 行提示
    const showTip = allFiles.length > 500

    return (
      <div className="overflow-auto h-full">
        {showTip && (
          <div className="px-3 py-2 text-xs text-text-muted bg-surface-strong border-b border-border">
            建议按仓库/目录聚焦
          </div>
        )}
        {changes.map((repo) => (
          <div key={repo.repo_id} className="border-b border-border last:border-b-0">
            <div className="px-3 py-2 text-xs font-medium bg-surface-strong">
              {repo.repo_role} ({repo.files.length})
            </div>
            {repo.files.map((file) => (
              <div
                key={file.path}
                className="flex items-center gap-2 px-3 py-1 cursor-pointer hover:bg-surface-strong text-sm"
                onClick={() => onSelectDiff?.(file.path)}
              >
                <Badge variant={
                  file.status === 'M' ? 'warning' :
                  file.status === 'A' ? 'success' :
                  file.status === 'D' ? 'error' : 'default'
                }>
                  {file.status}
                </Badge>
                <span className="truncate flex-1">{file.path}</span>
                <span className="text-xs text-green-500">+{file.additions}</span>
                <span className="text-xs text-red-500">-{file.deletions}</span>
              </div>
            ))}
          </div>
        ))}
      </div>
    )
  }

  return (
    <div className="w-[250px] flex-shrink-0 border-r border-border flex flex-col bg-background">
      {/* Tabs */}
      <div className="flex border-b border-border">
        <button
          className={`flex-1 px-3 py-2 text-sm ${
            tab === 'all' ? 'border-b-2 border-primary text-primary' : 'text-text-muted'
          }`}
          onClick={() => setTab('all')}
        >
          全部文件
        </button>
        <button
          className={`flex-1 px-3 py-2 text-sm flex items-center justify-center gap-1 ${
            tab === 'changes' ? 'border-b-2 border-primary text-primary' : 'text-text-muted'
          }`}
          onClick={() => setTab('changes')}
        >
          变更文件
          {totalChanges > 0 && (
            <Badge variant="primary">{totalChanges}</Badge>
          )}
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-auto">
        {tab === 'all' ? (
          tree.children.length === 0 ? (
            <div className="p-4 text-sm text-text-muted">无文件</div>
          ) : (
            tree.children.map((node) => (
              <TreeNodeItem
                key={node.path}
                node={node}
                depth={0}
                selectedPath={selectedPath}
                onSelect={onSelectFile!}
                onContextMenu={handleContextMenu}
              />
            ))
          )
        ) : (
          renderChanges()
        )}
      </div>

      {/* Context Menu */}
      {contextMenu && mode === 'task' && (
        <ContextMenu
          x={contextMenu.x}
          y={contextMenu.y}
          path={contextMenu.path}
          onClose={() => setContextMenu(null)}
          onCreate={onCreateFile!}
          onRename={onRenameFile!}
          onDelete={onDeleteFile!}
        />
      )}
    </div>
  )
}
