/**
 * FileTree — 双视图文件树
 * - 顶部 Tabs「全部文件」/「变更文件」(变更 Tab 带徽标总数)+ 刷新按钮
 * - 全部:
 *   - task 模式(懒加载树,R4.F6/BUG-070 复开):runner list_dir 为 find -maxdepth 1 单层返回
 *     (相对路径),目录展开时经 loadDir(dirFullPath) 按需拉取该层子级;树内统一使用
 *     容器绝对路径语义(rootPath 拼接),与 read/write/file_op 的裸 shell 路径要求对齐;
 *     子级三态行:加载中 / 加载失败(点击重试) / 空目录
 *   - project 模式(扁平回退):GitLab tree 一次性返回全路径嵌套列表,沿用 buildTree
 * - 变更:按仓库分组扁平列表,行=变更徽标(M/A/D/R)+ 路径 + `+X/-Y`;>500 行提示
 * - watcher 消息触发 500ms 防抖刷新(经 refreshNonce/onRefresh 外部驱动)
 */

import { useState, useRef, useCallback, useMemo, useEffect } from 'react'
import { ChevronRight, ChevronDown, File as FileIcon, Folder, FolderOpen, RefreshCw, Loader2 } from 'lucide-react'
import { Badge } from './ui/Badge'
import type { FileItem, ChangeRepo } from '@/api/files'

interface FileTreeProps {
  mode: 'project' | 'task'
  /** 根目录单层条目(task:相对 rootPath 路径;project:GitLab 全路径) */
  files?: FileItem[]
  /** 任务模式根目录绝对路径(默认 /workspace/main;懒加载路径拼接基准) */
  rootPath?: string
  /** 目录懒加载:返回该目录下单层子级(任务模式必传;缺省时回退扁平 buildTree) */
  loadDir?: (dirFullPath: string) => Promise<FileItem[]>
  /** 外部刷新令牌:值变化 → 清空已加载子级缓存,已展开目录自动重拉 */
  refreshNonce?: number
  changes?: ChangeRepo[]
  selectedPath?: string
  /** 文件点击回调:task 模式回传容器绝对路径 */
  onSelectFile?: (path: string) => void
  onSelectDiff?: (path: string) => void
  onCreateFile?: (path: string) => void
  onRenameFile?: (oldPath: string, newPath: string) => void
  onDeleteFile?: (path: string) => void
  onRefresh?: () => void
  /** 刷新中状态:显示旋转动画并禁用按钮 */
  isRefreshing?: boolean
}

// 懒加载树节点:fullPath 是 API 语义(容器绝对路径),name 仅用于展示
interface LazyNode {
  name: string
  fullPath: string
  type: 'file' | 'dir'
}

// —— project 模式回退用的扁平建树(GitLab tree 全路径;当前无消费方,保留防复用踩坑)——
interface TreeNode {
  path: string
  name: string
  type: 'file' | 'dir'
  children: TreeNode[]
}

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

// 相对路径条目 → 懒加载节点(绝对路径归一;兼容已绝对路径的条目)
function toLazyNode(item: FileItem, parentDir: string): LazyNode {
  const full = item.path.startsWith('/') ? item.path : `${parentDir}/${item.path}`
  return { name: item.path.split('/').pop() ?? item.path, fullPath: full, type: item.type }
}

// 懒加载树节点组件:目录展开数据由父级 dirChildren/状态注入,本组件零自取数
function LazyNodeItem({
  node,
  depth,
  selectedPath,
  expandedDirs,
  dirChildren,
  loadingDirs,
  dirErrors,
  onToggleDir,
  onRetryDir,
  onSelect,
  onContextMenu,
}: {
  node: LazyNode
  depth: number
  selectedPath?: string
  expandedDirs: Set<string>
  dirChildren: Record<string, LazyNode[]>
  loadingDirs: Set<string>
  dirErrors: Record<string, string>
  onToggleDir: (fullPath: string) => void
  onRetryDir: (fullPath: string) => void
  onSelect: (fullPath: string) => void
  onContextMenu?: (e: React.MouseEvent, path: string) => void
}) {
  const isDir = node.type === 'dir'
  const expanded = isDir && expandedDirs.has(node.fullPath)
  const children = isDir ? dirChildren[node.fullPath] : undefined
  const loading = isDir && loadingDirs.has(node.fullPath)
  const error = isDir ? dirErrors[node.fullPath] : undefined
  const isSelected = node.fullPath === selectedPath

  const Icon = isDir ? (expanded ? FolderOpen : Folder) : FileIcon

  const handleClick = () => {
    // 目录只切展开态;数据由 FileTree 的 ensure-effect 统一补齐(单一代码路径)
    if (isDir) onToggleDir(node.fullPath)
    if (!isDir) onSelect(node.fullPath)
  }

  return (
    <>
      <div
        className={`flex items-center gap-1 px-2 py-1 cursor-pointer text-sm hover:bg-surface-strong ${
          isSelected ? 'bg-surface-strong' : ''
        }`}
        style={{ paddingLeft: `${depth * 12 + 8}px` }}
        onClick={handleClick}
        onContextMenu={(e) => onContextMenu?.(e, node.fullPath)}
      >
        {isDir && (expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />)}
        <Icon size={14} className="text-text-muted flex-shrink-0" />
        <span className="truncate">{node.name}</span>
      </div>
      {/* 子级三态:加载中 / 失败可重试(手动,避免 ensure-effect 自动无限重拉)/ 空目录 */}
      {isDir && expanded && loading && (
        <div className="px-2 py-1 text-xs text-text-muted" style={{ paddingLeft: `${(depth + 1) * 12 + 8}px` }}>
          加载中…
        </div>
      )}
      {isDir && expanded && !loading && error && (
        <div
          className="px-2 py-1 text-xs text-red-500 cursor-pointer hover:bg-surface-strong"
          style={{ paddingLeft: `${(depth + 1) * 12 + 8}px` }}
          title="点击重试"
          onClick={() => onRetryDir(node.fullPath)}
        >
          加载失败:{error}(点击重试)
        </div>
      )}
      {isDir && expanded && !loading && !error && children && children.length === 0 && (
        <div className="px-2 py-1 text-xs text-text-muted" style={{ paddingLeft: `${(depth + 1) * 12 + 8}px` }}>
          空目录
        </div>
      )}
      {isDir && expanded && !loading && !error && children && children.map((child) => (
        <LazyNodeItem
          key={child.fullPath}
          node={child}
          depth={depth + 1}
          selectedPath={selectedPath}
          expandedDirs={expandedDirs}
          dirChildren={dirChildren}
          loadingDirs={loadingDirs}
          dirErrors={dirErrors}
          onToggleDir={onToggleDir}
          onRetryDir={onRetryDir}
          onSelect={onSelect}
          onContextMenu={onContextMenu}
        />
      ))}
    </>
  )
}

// 树节点组件(project 模式回退;数据已全量在 props 中)
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

// 右键菜单(路径来自 LazyNodeItem/TreeNodeItem,task 模式下为容器绝对路径)
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
  rootPath = '/workspace/main',
  loadDir,
  refreshNonce = 0,
  changes = [],
  selectedPath,
  onSelectFile,
  onSelectDiff,
  onCreateFile,
  onRenameFile,
  onDeleteFile,
  onRefresh,
  isRefreshing,
}: FileTreeProps) {
  const [tab, setTab] = useState<'all' | 'changes'>('all')
  const [contextMenu, setContextMenu] = useState<{ x: number; y: number; path: string } | null>(null)
  const debounceTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  // —— 懒加载树状态(均以目录绝对路径为键;值为已归一的 LazyNode,R39 修正:
  //     曾直接存原始 FileItem 致 node.name/fullPath undefined → 子级渲染空名行)——
  const [expandedDirs, setExpandedDirs] = useState<Set<string>>(new Set())
  const [dirChildren, setDirChildren] = useState<Record<string, LazyNode[]>>({})
  const [loadingDirs, setLoadingDirs] = useState<Set<string>>(new Set())
  const [dirErrors, setDirErrors] = useState<Record<string, string>>({})

  // project 模式回退:扁平全量建树
  const legacyTree = useMemo(() => buildTree(files), [files])
  // task 模式:根层子级(files 为相对 rootPath 的单层条目)
  const rootChildren = useMemo(() => files.map((f) => toLazyNode(f, rootPath)), [files, rootPath])

  // 拉取目录子级;失败落 dirErrors(等待手动重试,不走自动重试避免风暴)
  const fetchDir = useCallback(async (dir: string) => {
    if (!loadDir) return
    setLoadingDirs((prev) => new Set(prev).add(dir))
    setDirErrors((prev) => {
      if (!(dir in prev)) return prev
      const next = { ...prev }
      delete next[dir]
      return next
    })
    try {
      const items = await loadDir(dir)
      // R39 修正:原始 FileItem(path 为相对当前目录的路径)必须先归一为 LazyNode
      // (绝对 fullPath + basename name),否则子级行 name/fullPath 均为 undefined
      setDirChildren((prev) => ({ ...prev, [dir]: items.map((it) => toLazyNode(it, dir)) }))
    } catch (e) {
      setDirErrors((prev) => ({ ...prev, [dir]: e instanceof Error ? e.message : String(e) }))
    } finally {
      setLoadingDirs((prev) => {
        const next = new Set(prev)
        next.delete(dir)
        return next
      })
    }
  }, [loadDir])

  // 补数保证:任何「已展开且无数据且无错误」的目录都会被拉取——
  // 展开、refreshNonce 清缓存、重试后的重拉,全部经由这一条 effect 收口(无散落触发点)
  useEffect(() => {
    if (!loadDir) return
    for (const dir of expandedDirs) {
      if (dirChildren[dir] !== undefined) continue // 已有数据(含空数组)
      if (loadingDirs.has(dir)) continue // 在拉
      if (dirErrors[dir]) continue // 失败态等手动重试
      fetchDir(dir)
    }
  }, [expandedDirs, dirChildren, loadingDirs, dirErrors, loadDir, fetchDir, refreshNonce])

  // 外部刷新:清空子级缓存与错误(保留展开状态),由补数 effect 自动重拉已展开目录
  const firstNonce = useRef(true)
  useEffect(() => {
    if (firstNonce.current) {
      firstNonce.current = false
      return
    }
    setDirChildren({})
    setDirErrors({})
  }, [refreshNonce])

  const toggleDir = useCallback((dir: string) => {
    setExpandedDirs((prev) => {
      const next = new Set(prev)
      // 已展开 → 折叠(早退);未展开 → 展开(数据由补数 effect 拉取)
      if (next.has(dir)) {
        next.delete(dir)
        return next
      }
      next.add(dir)
      return next
    })
  }, [])

  // 构建文件树(project 回退)
  const tree = legacyTree

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

  // 全部文件视图:task 懒加载树 / project 扁平回退
  const renderAll = () => {
    if (loadDir) {
      if (rootChildren.length === 0) {
        return <div className="p-4 text-sm text-text-muted">无文件</div>
      }
      return rootChildren.map((node) => (
        <LazyNodeItem
          key={node.fullPath}
          node={node}
          depth={0}
          selectedPath={selectedPath}
          expandedDirs={expandedDirs}
          dirChildren={dirChildren}
          loadingDirs={loadingDirs}
          dirErrors={dirErrors}
          onToggleDir={toggleDir}
          onRetryDir={fetchDir}
          onSelect={onSelectFile!}
          onContextMenu={handleContextMenu}
        />
      ))
    }
    if (tree.children.length === 0) {
      return <div className="p-4 text-sm text-text-muted">无文件</div>
    }
    return tree.children.map((node) => (
      <TreeNodeItem
        key={node.path}
        node={node}
        depth={0}
        selectedPath={selectedPath}
        onSelect={onSelectFile!}
        onContextMenu={handleContextMenu}
      />
    ))
  }

  return (
    <div className="w-full min-w-0 border-r border-border flex flex-col bg-background">
      {/* Tabs(R33.F4:.ft-tabs/.ft-tab 与中/右栏 .tabs 等高 34px,底线同 y 对齐;末位刷新按钮) */}
      <div className="ft-tabs">
        <button
          className={`ft-tab${tab === 'all' ? ' on' : ''}`}
          onClick={() => setTab('all')}
        >
          全部文件
        </button>
        <button
          className={`ft-tab${tab === 'changes' ? ' on' : ''}`}
          onClick={() => setTab('changes')}
        >
          变更文件
          {totalChanges > 0 && (
            <Badge variant="primary">{totalChanges}</Badge>
          )}
        </button>
        <button
          className="ft-tab"
          style={{ marginLeft: 'auto' }}
          title="刷新文件树"
          disabled={isRefreshing}
          onClick={() => onRefresh?.()}
        >
          {isRefreshing ? <Loader2 size={13} className="animate-spin" /> : <RefreshCw size={13} />}
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-auto">
        {tab === 'all' ? renderAll() : renderChanges()}
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
