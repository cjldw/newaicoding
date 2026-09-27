/**
 * SkillsMarket — 平台 Skills 管理(超管,R17;R4.F1 市场搜索安装;R6 系统级已安装区块)
 * - 标题"Skills 市场" + "新建 Skill"按钮
 * - Table:名称(chip+plug icon)/描述/创建人/创建时间/操作[编辑/删除]
 * - 「市场安装」对话框(R4.F1,照抄项目侧):页头「市场安装」按钮 → Dialog 内
 *   源 Select + useDebounce 防抖搜索 + 结果列表(安装量徽章 + 已装禁按:平台库同名/本会话刚装)
 *   + 安装进平台库(成功 toast「已安装到平台库,需新启任务容器生效」+ 平台库列表自动刷新)
 * - 「系统级已安装」区块(R6):镜像内置 skills/MCP 两列只读列表 + 采集时间/image_tag
 *   + 采集按钮(超管动作钮 Icon+文字次级,非 Plus 新建语义;loading 态,成功刷新列表)
 * - 新建/编辑对话框(名称 Input + 描述 Input + 内容 Textarea)
 * - 删除确认对话框
 */

import { useState } from 'react'
import { Plus, Pencil, Trash2, Plug, Blocks, Server, RefreshCw, Loader2, Store } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Label } from '@/components/ui/Label'
import { Textarea } from '@/components/ui/Textarea'
import { Alert } from '@/components/ui/Alert'
import { Select } from '@/components/ui/Select'
import {
  Table, TableHeader, TableBody, TableRow, TableHead, TableCell,
} from '@/components/ui/Table'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
  DialogFooter,
} from '@/components/ui/Dialog'
import {
  useAdminSkills, useCreateAdminSkill, useUpdateAdminSkill,
  useDeleteAdminSkill, useSystemAssets, useCollectSystemAssets,
  useMarketSources, useMarketSearch, useAdminInstallRemote,
  getSkillErrorMessage,
} from '@/api/skills'
import type { Skill, MarketSearchItem } from '@/api/skills'
import { ApiError } from '@/api/client'
import { useDebounce } from '@/hooks/useDebounce'
import { useToast } from '@/hooks/useToast'

/** 市场搜索/远程安装失败文案(R2/R3:17005=市场暂不可用;其余照 Skill 错误码) */
function getMarketErrorMessage(error: unknown): string {
  if (error instanceof ApiError && error.code === 17005) return '市场暂不可用'
  return getSkillErrorMessage(error)
}

export function SkillsMarket() {
  const { data: skills, isLoading } = useAdminSkills()
  const createSkill = useCreateAdminSkill()
  const updateSkill = useUpdateAdminSkill()
  const deleteSkill = useDeleteAdminSkill()
  // ---- R6:系统级已安装(镜像内置快照只读;采集=超管动作,成功 invalidate 自动刷新列表)----
  const { data: systemAssets } = useSystemAssets()
  const collectAssets = useCollectSystemAssets()
  // ---- R4.F1:市场搜索安装(照抄项目侧 Dialog:页头按钮 + 源 Select + 防抖搜索 + 结果列表,安装进平台库)----
  const [, showToast, ToastEl] = useToast()
  const [marketOpen, setMarketOpen] = useState(false)
  const [searchInput, setSearchInput] = useState('')
  const searchQ = useDebounce(searchInput.trim(), 300)
  const [marketType, setMarketType] = useState('')
  const [remoteInstalled, setRemoteInstalled] = useState<Set<string>>(new Set())
  // R4:市场源(R1 裸数组)+ 防抖搜索 + 远程安装(Dialog 打开且 q 防抖后非空才发)
  const { data: marketSources } = useMarketSources()
  const activeMarket = marketType || marketSources?.[0]?.type || ''
  const searchEnabled = marketOpen && activeMarket !== '' && searchQ !== ''
  const marketSearch = useMarketSearch(activeMarket, searchQ, searchEnabled)
  const installRemote = useAdminInstallRemote()
  // 已装比对(命中平台库列表 name 即禁按;本会话刚装的 ref 兜底,防列表刷新竞态)
  const installedNames = new Set((skills ?? []).map(s => s.name))
  const sourceOptions = (marketSources ?? []).map(s => ({ label: s.name, value: s.type }))

  const [dialogOpen, setDialogOpen] = useState(false)
  const [editing, setEditing] = useState<Skill | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<Skill | null>(null)
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null)

  const [formData, setFormData] = useState({
    name: '',
    description: '',
    content: '',
  })

  function resetForm() {
    setFormData({ name: '', description: '', content: '' })
  }

  function handleCreate() {
    resetForm()
    setEditing(null)
    setDialogOpen(true)
  }

  function handleEdit(skill: Skill) {
    resetForm()
    setEditing(skill)
    setFormData({
      name: skill.name,
      description: skill.description,
      content: skill.content ?? '',
    })
    setDialogOpen(true)
  }

  async function handleSubmit() {
    if (!formData.name.trim() || !formData.description.trim()) {
      setMessage({ type: 'error', text: '名称和描述不能为空' })
      return
    }
    try {
      if (editing) {
        await updateSkill.mutateAsync({
          id: editing.skill_id,
          data: formData,
        })
        setMessage({ type: 'success', text: '更新成功' })
      } else {
        await createSkill.mutateAsync(formData)
        setMessage({ type: 'success', text: '创建成功' })
      }
      setDialogOpen(false)
      resetForm()
    } catch (e) {
      setMessage({ type: 'error', text: getSkillErrorMessage(e) })
    }
  }

  async function handleDelete() {
    if (!deleteTarget) return
    try {
      await deleteSkill.mutateAsync(deleteTarget.skill_id)
      setMessage({ type: 'success', text: '删除成功' })
      setDeleteTarget(null)
    } catch (e) {
      setMessage({ type: 'error', text: getSkillErrorMessage(e) })
    }
  }

  /** R4.F1:市场远程安装成功——Dialog 不关,该行标「已安装」+ toast + 平台库列表 invalidate 自动刷新 */
  function handleInstallRemote(item: MarketSearchItem) {
    installRemote.mutate({ market: item.market, ref: item.ref }, {
      onSuccess: () => {
        setRemoteInstalled(prev => new Set(prev).add(`${item.market}:${item.ref}`))
        showToast('ok', '已安装到平台库,需新启任务容器生效')
      },
      onError: (err) => showToast('err', getMarketErrorMessage(err)),
    })
  }

  /** R6:触发系统级采集(临时容器探测,耗时可达 120s;成功后列表经 invalidate 自动刷新) */
  function handleCollect() {
    collectAssets.mutate(undefined, {
      onSuccess: (data) => {
        setMessage({
          type: 'success',
          text: `采集成功:Skills ${data.skills} 个、MCP ${data.mcps} 个`
            + (data.warning ? `(${data.warning})` : ''),
        })
      },
      onError: (err) => {
        setMessage({
          type: 'error',
          text: err instanceof ApiError ? err.message : '采集失败',
        })
      },
    })
  }

  function formatDate(dateStr: string): string {
    try {
      return new Date(dateStr).toLocaleString('zh-CN')
    } catch {
      return dateStr
    }
  }

  return (
    <div className="page wide">
      {/* 操作栏(vp 无独立 Skills 页,页头按 vp 页头语言补 icon+说明,文案自拟留痕) */}
      <div className="page-head">
        <div>
          <h1 className="flex items-center gap-2"><Blocks size={18} /> Skills 市场</h1>
          <div className="sub">平台级 MCP Skills 管理:注册、启停与项目授权(仅超管)</div>
        </div>
        <div className="acts">
          <Button
            variant="primary"
            onClick={() => {
              setSearchInput('')
              setMarketType('')
              setRemoteInstalled(new Set())
              setMarketOpen(true)
            }}
          >
            <Store className="w-4 h-4 mr-1" />
            从市场安装
          </Button>
          <Button variant="primary" onClick={handleCreate}>
            <Plus className="w-4 h-4 mr-1" />
            新建 Skill
          </Button>
        </div>
      </div>

      {message && (
        <Alert variant={message.type}>{message.text}</Alert>
      )}

      {/* 列表 */}
      {isLoading ? (
        <div className="text-text-muted py-8">加载中...</div>
      ) : (
        /* §6.4 #1:加 .card > .scrollx 包裹 */
        <div className="card">
        <div className="scrollx">
          <Table className="tbl">
            <TableHeader>
              <TableRow>
                <TableHead>名称</TableHead>
                <TableHead>描述</TableHead>
                <TableHead>创建人</TableHead>
                <TableHead>创建时间</TableHead>
                <TableHead className="ops">操作</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {(skills ?? []).map(skill => (
                <TableRow key={skill.skill_id}>
                  {/* §6.4 #2:名称列用 .chip + plug icon */}
                  <TableCell className="font-medium text-text">
                    <span className="chip"><Plug className="w-3 h-3" />{skill.name}</span>
                  </TableCell>
                  <TableCell className="text-text-muted">
                    <span className="cell-txt">{skill.description}</span>
                  </TableCell>
                  <TableCell className="text-text-muted">
                    {skill.created_by?.username ?? '-'}
                  </TableCell>
                  <TableCell className="text-text-muted">
                    {skill.created_at ? formatDate(skill.created_at) : '-'}
                  </TableCell>
                  <TableCell className="ops">
                    <div className="flex gap-2 justify-end">
                      {/* §6.4 #3:操作按钮改 .btn.btn-sm / .btn.btn-sm.btn-danger */}
                      <button className="btn btn-sm" onClick={() => handleEdit(skill)}>
                        <Pencil className="w-4 h-4 mr-1" />
                        编辑
                      </button>
                      <button
                        className="btn btn-sm btn-danger"
                        onClick={() => setDeleteTarget(skill)}
                      >
                        <Trash2 className="w-3.5 h-3.5 mr-1" />
                        删除
                      </button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
              {(skills ?? []).length === 0 && (
                <TableRow>
                  <TableCell colSpan={5} className="text-center text-text-muted py-8">
                    暂无平台 Skills
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </div>
        </div>
      )}

      {/* R6:系统级已安装(镜像内置快照,只读;采集按钮为超管动作钮 Icon+文字次级) */}
      <div className="mt-6">
        <div className="card">
          <div className="card-head">
            <span className="card-title"><Server size={15} /> 系统级已安装</span>
            <div className="right">
              <Button
                variant="outline"
                size="sm"
                onClick={handleCollect}
                disabled={collectAssets.isPending}
              >
                {collectAssets.isPending
                  ? <Loader2 className="w-4 h-4 mr-1 animate-spin" />
                  : <RefreshCw className="w-4 h-4 mr-1" />}
                {collectAssets.isPending ? '采集中...' : '采集'}
              </Button>
            </div>
          </div>
          <div className="card-body">
            {systemAssets?.collected ? (
              <>
                <p className="text-sm text-text-muted flex items-center gap-2 flex-wrap">
                  <span>
                    采集于 {systemAssets.collected_at ? formatDate(systemAssets.collected_at) : '-'}
                  </span>
                  {systemAssets.image_tag && (
                    <code className="font-mono text-xs bg-surface-strong px-1 py-0.5 rounded">
                      {systemAssets.image_tag}
                    </code>
                  )}
                </p>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mt-3">
                  <div>
                    <span className="bdg b-zinc">Skills({(systemAssets.skills ?? []).length})</span>
                    <div className="chip-row mt-2">
                      {(systemAssets.skills ?? []).map(s => (
                        <span key={s.name} className="chip">{s.name}</span>
                      ))}
                      {(systemAssets.skills ?? []).length === 0 && (
                        <span className="text-sm text-text-muted">镜像未内置 Skills</span>
                      )}
                    </div>
                  </div>
                  <div>
                    <span className="bdg b-zinc">MCP({(systemAssets.mcps ?? []).length})</span>
                    <div className="chip-row mt-2">
                      {(systemAssets.mcps ?? []).map(m => (
                        <span key={m.name} className="chip">{m.name}</span>
                      ))}
                      {(systemAssets.mcps ?? []).length === 0 && (
                        <span className="text-sm text-text-muted">镜像未内置 MCP</span>
                      )}
                    </div>
                  </div>
                </div>
              </>
            ) : (
              <p className="text-center text-text-muted py-6">暂未采集</p>
            )}
          </div>
        </div>
      </div>

      {/* R4.F1:市场安装对话框(照抄项目侧 R4 搜索 Tab 结构:源 Select + 防抖搜索 + 结果列表;安装进平台库) */}
      <Dialog open={marketOpen} onOpenChange={setMarketOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>从市场安装</DialogTitle>
            <DialogDescription>
              从市场搜索 Skill 安装进平台库(平台级,项目可从平台库安装)
            </DialogDescription>
          </DialogHeader>
          <div className="mt-3 space-y-3">
            {/* 市场源(R1)+ 搜索词(300ms 防抖) */}
            <div className="flex gap-2">
              <Select
                className="w-[150px] flex-none"
                options={sourceOptions}
                value={activeMarket}
                onChange={(e) => setMarketType(e.target.value)}
              />
              <Input
                className="flex-1"
                placeholder="搜索市场 skill…"
                value={searchInput}
                onChange={(e) => setSearchInput(e.target.value)}
              />
            </div>
            <div className="space-y-2 max-h-[400px] overflow-y-auto">
              {searchQ === '' ? (
                <p className="text-center text-text-muted py-4">请输入搜索词</p>
              ) : marketSearch.isLoading ? (
                <p className="text-center text-text-muted py-4">搜索中...</p>
              ) : marketSearch.isError ? (
                <Alert variant="error">{getMarketErrorMessage(marketSearch.error)}</Alert>
              ) : (marketSearch.data?.items ?? []).length === 0 ? (
                <p className="text-center text-text-muted py-4">未找到匹配 skill</p>
              ) : (
                (marketSearch.data?.items ?? []).map(item => {
                  const installedItem =
                    installedNames.has(item.name) ||
                    remoteInstalled.has(`${item.market}:${item.ref}`)
                  return (
                    <div
                      key={`${item.market}:${item.ref}`}
                      className="flex items-center justify-between p-3 border border-border rounded-md"
                    >
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="font-medium text-text">{item.name}</span>
                          <span className="bdg b-zinc">{item.installs} 次安装</span>
                        </div>
                        <div className="text-sm text-text-muted mt-1 truncate">
                          {item.description}
                        </div>
                      </div>
                      <Button
                        size="sm"
                        className="ml-3 flex-none"
                        onClick={() => handleInstallRemote(item)}
                        disabled={installedItem || installRemote.isPending}
                      >
                        {installedItem ? '已安装' : '安装'}
                      </Button>
                    </div>
                  )
                })
              )}
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* 新建/编辑对话框 */}
      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="max-w-[560px]">
          <DialogHeader>
            <DialogTitle>{editing ? '编辑 Skill' : '新建 Skill'}</DialogTitle>
            <DialogDescription>
              {editing ? '修改平台 Skill 信息' : '创建新的平台级 Skill'}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-1">
              <Label>名称</Label>
              <Input
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                placeholder="如:code-review"
              />
            </div>
            <div className="space-y-1">
              <Label>描述</Label>
              <Input
                value={formData.description}
                onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                placeholder="一句话说明 Skill 的用途"
              />
            </div>
            <div className="space-y-1">
              <Label>内容</Label>
              <Textarea
                value={formData.content}
                onChange={(e) => setFormData({ ...formData, content: e.target.value })}
                rows={10}
                className="font-mono text-sm"
                placeholder="# Skill 内容(Markdown,需包含 YAML frontmatter)"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setDialogOpen(false)}>
              取消
            </Button>
            <Button
              variant="primary"
              onClick={handleSubmit}
              disabled={createSkill.isPending || updateSkill.isPending}
            >
              {editing ? '保存' : '创建'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* 删除确认对话框 */}
      <Dialog open={!!deleteTarget} onOpenChange={() => setDeleteTarget(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>确认删除</DialogTitle>
            <DialogDescription>
              确定要删除 Skill "{deleteTarget?.name}" 吗?此操作不可恢复。
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setDeleteTarget(null)}>
              取消
            </Button>
            <Button
              variant="danger"
              onClick={handleDelete}
              disabled={deleteSkill.isPending}
            >
              删除
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* R4.F1:市场安装结果 toast */}
      {ToastEl}
    </div>
  )
}
