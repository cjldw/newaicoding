/**
 * MemberManagement — 成员管理 Tab(R12;R3 邀请 Dialog 重构为选择式)
 * - 操作栏:右侧"邀请成员"按钮
 * - 成员 Table:头像+用户名(昵称副标题)/角色徽章/邀请人/加入时间/操作
 * - 对话框:邀请成员(搜索+分页候选多选+统一角色)/改角色/移除确认 + 转让 owner
 */

import { useState, useEffect } from 'react'
import { UserPlus } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { Input } from '@/components/ui/Input'
import { Label } from '@/components/ui/Label'
import { Select } from '@/components/ui/Select'
import { Avatar } from '@/components/ui/Avatar'
import { Alert } from '@/components/ui/Alert'
import { Checkbox } from '@/components/ui/Checkbox'
import { RadioGroup } from '@/components/ui/RadioGroup'
import {
  Table, TableHeader, TableBody, TableRow, TableHead, TableCell,
} from '@/components/ui/Table'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
  DialogFooter,
} from '@/components/ui/Dialog'
import {
  useProjectMembers, useBatchInviteMember, useCandidateUsers,
  useRemoveMember, useChangeMemberRole, useTransferOwnership,
  getMemberErrorMessage, getBatchInviteErrors,
} from '@/api/projects'
import type { ProjectMember, CandidateUser, BatchInviteErrorItem } from '@/api/projects'
import { useDebounce } from '@/hooks/useDebounce'
import { useToast } from '@/hooks/useToast'

const roleBadgeMap: Record<string, { label: string; variant: 'primary' | 'secondary' | 'outline' }> = {
  owner: { label: '所有者', variant: 'primary' },
  editor: { label: '编辑者', variant: 'secondary' },
  viewer: { label: '观察者', variant: 'outline' },
}

const roleSelectOptions = [
  { value: 'owner', label: '所有者' },
  { value: 'editor', label: '编辑者' },
  { value: 'viewer', label: '观察者' },
]

/** R3 文案清单:角色组 editor=「编辑」viewer=「查看」 */
const inviteRoleOptions = [
  { value: 'editor', label: '编辑' },
  { value: 'viewer', label: '查看' },
]

/** 候选列表每页条数(与后端 candidate-users 默认一致) */
const CANDIDATE_PAGE_SIZE = 20

interface MemberManagementProps {
  projectId: string
}

/** 可勾选 = 非成员且未停用(is_member/status 由候选接口标记) */
function isSelectable(c: CandidateUser): boolean {
  return !c.is_member && c.status !== 'disabled'
}

export function MemberManagement({ projectId }: MemberManagementProps) {
  const { data, isLoading } = useProjectMembers(projectId)
  const batchInvite = useBatchInviteMember()
  const removeMember = useRemoveMember()
  const changeRole = useChangeMemberRole()
  const transferOwnership = useTransferOwnership()
  const [, showToast, ToastEl] = useToast()

  const [inviteOpen, setInviteOpen] = useState(false)
  const [changeTarget, setChangeTarget] = useState<ProjectMember | null>(null)
  const [removeTarget, setRemoveTarget] = useState<ProjectMember | null>(null)
  const [transferTarget, setTransferTarget] = useState<ProjectMember | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)

  // 邀请对话框状态(R3 选择式)
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  /** 已选 user_id 集合(跨页保留) */
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  /** user_id → 昵称(整批失败 Alert 渲染「{昵称}:{原因}」用;随各页加载累积) */
  const [candidateNames, setCandidateNames] = useState<Record<string, string>>({})
  const [inviteRole, setInviteRole] = useState<'editor' | 'viewer'>('viewer')
  /** 整批 400 的逐条原因(Dialog 内 Alert,不关窗) */
  const [batchErrors, setBatchErrors] = useState<BatchInviteErrorItem[] | null>(null)
  /** 非逐条形态的错误(403/网络等) */
  const [inviteError, setInviteError] = useState<string | null>(null)

  // 改角色对话框状态
  const [newRole, setNewRole] = useState<'owner' | 'editor' | 'viewer'>('editor')

  const members = data?.items ?? []
  const ownerCount = members.filter(m => m.role === 'owner').length

  // 搜索 300ms 防抖;关键词变化回第一页
  const debouncedSearch = useDebounce(search, 300)
  useEffect(() => { setPage(1) }, [debouncedSearch])

  const candidates = useCandidateUsers(
    projectId,
    { q: debouncedSearch.trim(), page, page_size: CANDIDATE_PAGE_SIZE },
    inviteOpen,
  )

  const candidateItems = candidates.data?.items ?? []
  const candidateTotal = candidates.data?.total ?? 0
  const totalPages = Math.max(1, Math.ceil(candidateTotal / CANDIDATE_PAGE_SIZE))
  const pageSelectable = candidateItems.filter(isSelectable)
  const pageAllSelected = pageSelectable.length > 0
    && pageSelectable.every(c => selectedIds.has(c.user_id))

  // 累积记录候选昵称(跨页已选用户在失败 Alert 中能显示昵称)
  useEffect(() => {
    if (candidateItems.length === 0) return
    setCandidateNames((prev) => {
      let changed = false
      const next = { ...prev }
      for (const it of candidateItems) {
        if (next[it.user_id] !== it.nickname) { next[it.user_id] = it.nickname; changed = true }
      }
      return changed ? next : prev
    })
  }, [candidates.data])

  function toggleCandidate(c: CandidateUser, checked: boolean) {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (checked) next.add(c.user_id)
      else next.delete(c.user_id)
      return next
    })
  }

  /** 全选当前页:只勾选可选项(已是成员/已停用不动) */
  function togglePageAll(checked: boolean) {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      for (const c of pageSelectable) {
        if (checked) next.add(c.user_id)
        else next.delete(c.user_id)
      }
      return next
    })
  }

  function resetInviteDialog() {
    setSearch(''); setPage(1); setSelectedIds(new Set())
    setInviteRole('viewer'); setInviteError(null); setBatchErrors(null)
  }

  async function handleInvite() {
    if (selectedIds.size === 0) return
    setInviteError(null); setBatchErrors(null)
    try {
      const res = await batchInvite.mutateAsync({
        projectId,
        data: { user_ids: [...selectedIds], role: inviteRole },
      })
      showToast('ok', `已添加 ${res.added} 名成员`)
      setInviteOpen(false); resetInviteDialog()
    } catch (e) {
      // 整批失败:Dialog 内 Alert 逐条原因,不关窗(列表不刷新)
      const errors = getBatchInviteErrors(e)
      if (errors) setBatchErrors(errors)
      else setInviteError(getMemberErrorMessage(e))
    }
  }

  async function handleChangeRole() {
    if (!changeTarget) return
    setError(null)
    try {
      await changeRole.mutateAsync({
        projectId, userId: changeTarget.user_id, data: { role: newRole },
      })
      setSuccess('角色已更新'); setChangeTarget(null)
    } catch (e) { setError(getMemberErrorMessage(e)) }
  }

  async function handleRemove() {
    if (!removeTarget) return
    setError(null)
    try {
      await removeMember.mutateAsync({ projectId, userId: removeTarget.user_id })
      setSuccess('成员已移除'); setRemoveTarget(null)
    } catch (e) { setError(getMemberErrorMessage(e)) }
  }

  async function handleTransfer() {
    if (!transferTarget) return
    setError(null)
    try {
      await transferOwnership.mutateAsync({
        projectId, data: { new_owner_user_id: transferTarget.user_id },
      })
      setSuccess('转让成功,您已降为 editor'); setTransferTarget(null)
    } catch (e) { setError(getMemberErrorMessage(e)) }
  }

  function formatTime(iso: string) {
    try { return new Date(iso).toLocaleDateString('zh-CN') } catch { return iso }
  }

  if (isLoading) return <div className="text-text-muted py-8">加载中...</div>

  return (
    <div>
      {/* 页头(对齐 vp:icon + 标题 + sub) */}
      <div className="page-head">
        <div>
          <h1 className="flex items-center gap-2"><UserPlus size={18} /> 成员</h1>
          <div className="sub">项目成员管理:邀请、角色分配与移除</div>
        </div>
        <div className="acts">
          <Button variant="primary" onClick={() => { setInviteOpen(true); resetInviteDialog() }}>
            <UserPlus className="w-4 h-4 mr-1" />
            邀请成员
          </Button>
        </div>
      </div>

      {/* 成功提示 */}
      {success && (
        <Alert variant="success" className="mb-4">
          {success}
        </Alert>
      )}
      {/* 错误提示 */}
      {error && (
        <Alert variant="error" className="mb-4">
          {error}
        </Alert>
      )}

      {/* 成员列表 */}
      <div className="card">
      <div className="scrollx">
      <Table className="tbl">
        <TableHeader>
          <TableRow>
            <TableHead>用户</TableHead>
            <TableHead>角色</TableHead>
            <TableHead>邀请人</TableHead>
            <TableHead>加入时间</TableHead>
            <TableHead className="ops">操作</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {members.map((m) => {
            const rb = roleBadgeMap[m.role] ?? roleBadgeMap.viewer
            const isLastOwner = m.role === 'owner' && ownerCount === 1
            return (
              <TableRow key={m.user_id}>
                <TableCell>
                  <div className="flex items-center gap-3">
                    <Avatar src={m.avatar_url} alt={m.nickname || m.username} size={32} />
                    <div>
                      <div className="font-medium text-text">{m.username}</div>
                      {m.nickname && (
                        <div className="text-xs text-text-muted">{m.nickname}</div>
                      )}
                    </div>
                  </div>
                </TableCell>
                <TableCell>
                  <Badge variant={rb.variant}>{rb.label}</Badge>
                </TableCell>
                <TableCell className="text-text-muted">
                  {m.invited_by?.username ?? '-'}
                </TableCell>
                <TableCell className="text-text-muted">{formatTime(m.joined_at)}</TableCell>
                <TableCell className="ops">
                  <div className="flex items-center justify-end gap-1">
                    <button
                      className="btn btn-sm"
                      onClick={() => { setChangeTarget(m); setNewRole(m.role); setError(null) }}
                    >
                      改角色
                    </button>
                    {m.role !== 'owner' && (
                      <button
                        className="btn btn-sm"
                        onClick={() => { setTransferTarget(m); setError(null) }}
                      >
                        转让
                      </button>
                    )}
                    <button
                      className="btn btn-sm btn-danger"
                      disabled={isLastOwner}
                      onClick={() => { setRemoveTarget(m); setError(null) }}
                    >
                      移除
                    </button>
                  </div>
                </TableCell>
              </TableRow>
            )
          })}
        </TableBody>
      </Table>
      </div>
      {members.length === 0 && <div className="empty">暂无成员</div>}
      </div>

      {/* 邀请成员对话框(R3 选择式:搜索+分页候选多选+统一角色) */}
      <Dialog open={inviteOpen} onOpenChange={(o) => { setInviteOpen(o); if (!o) resetInviteDialog() }}>
        <DialogContent className="w-[520px]">
          <DialogHeader>
            <DialogTitle>邀请成员</DialogTitle>
            <DialogDescription>搜索平台用户,勾选后以统一角色批量加入项目</DialogDescription>
          </DialogHeader>

          {/* 整批失败:逐条「{昵称}:{原因}」,不关窗 */}
          {batchErrors && (
            <Alert variant="error" className="mt-4">
              <div className="font-medium">添加失败</div>
              <ul className="mt-1 space-y-0.5">
                {batchErrors.map((it) => (
                  <li key={it.user_id}>
                    {candidateNames[it.user_id] ?? it.user_id}:{it.reason}
                  </li>
                ))}
              </ul>
            </Alert>
          )}
          {inviteError && (
            <Alert variant="error" className="mt-4">{inviteError}</Alert>
          )}

          <div className="mt-4">
            <Input
              placeholder="搜索昵称或手机号"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>

          {/* 候选列表(Checkbox+头像+昵称+打码手机号;禁选置灰标原因) */}
          <div className="mt-3 max-h-[320px] overflow-y-auto rounded-md border border-border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-10">
                    <Checkbox
                      checked={pageAllSelected}
                      disabled={pageSelectable.length === 0}
                      onChange={togglePageAll}
                      aria-label="全选当前页"
                    />
                  </TableHead>
                  <TableHead>用户</TableHead>
                  <TableHead>手机号</TableHead>
                  <TableHead>状态</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {candidateItems.map((c) => {
                  const selectable = isSelectable(c)
                  return (
                    <TableRow key={c.user_id} className={selectable ? '' : 'opacity-60'}>
                      <TableCell>
                        <Checkbox
                          checked={selectedIds.has(c.user_id)}
                          disabled={!selectable}
                          onChange={(checked) => toggleCandidate(c, checked)}
                          aria-label={`选择 ${c.nickname}`}
                        />
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center gap-2">
                          <Avatar src={c.avatar_url} alt={c.nickname} size={28} />
                          <span className={`text-sm truncate ${selectable ? 'text-text' : 'text-text-muted'}`}>
                            {c.nickname}
                          </span>
                        </div>
                      </TableCell>
                      <TableCell className="text-text-muted whitespace-nowrap">{c.phone}</TableCell>
                      <TableCell className="whitespace-nowrap">
                        {c.is_member ? (
                          <span className="text-xs text-text-muted">已是成员</span>
                        ) : c.status === 'disabled' ? (
                          <span className="text-xs text-text-muted">已停用</span>
                        ) : null}
                      </TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
            {candidates.isLoading && (
              <div className="px-3 py-6 text-center text-sm text-text-muted">加载中...</div>
            )}
            {!candidates.isLoading && candidateItems.length === 0 && (
              <div className="px-3 py-6 text-center text-sm text-text-muted">未找到匹配用户</div>
            )}
          </div>

          {/* 分页器 */}
          <div className="mt-2 flex items-center justify-between">
            <span className="text-xs text-text-muted">共 {candidateTotal} 人</span>
            {totalPages > 1 && (
              <div className="flex items-center gap-2">
                <button
                  className="btn btn-sm"
                  disabled={page === 1}
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                >
                  上一页
                </button>
                <span className="text-xs text-text-muted">{page} / {totalPages}</span>
                <button
                  className="btn btn-sm"
                  disabled={page === totalPages}
                  onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                >
                  下一页
                </button>
              </div>
            )}
          </div>

          {/* 统一角色 + 已选计数 */}
          <div className="mt-4 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <Label>角色</Label>
              <RadioGroup
                name="invite-role"
                options={inviteRoleOptions}
                value={inviteRole}
                onChange={(v) => setInviteRole(v as 'editor' | 'viewer')}
              />
            </div>
            <span className="text-sm text-text-muted">已选 {selectedIds.size} 人</span>
          </div>

          <DialogFooter>
            <Button variant="ghost" onClick={() => { setInviteOpen(false); resetInviteDialog() }}>
              取消
            </Button>
            <Button
              variant="primary"
              disabled={selectedIds.size === 0 || batchInvite.isPending}
              title={selectedIds.size === 0 ? '请先选择成员' : undefined}
              onClick={handleInvite}
            >
              邀请
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* 改角色对话框 */}
      <Dialog open={!!changeTarget} onOpenChange={() => setChangeTarget(null)}>
        <DialogContent className="w-[500px]">
          <DialogHeader>
            <DialogTitle>修改角色</DialogTitle>
            <DialogDescription>修改成员 {changeTarget?.username} 的角色</DialogDescription>
          </DialogHeader>
          <div className="dlg-form">
            <div className="field">
              <Label>当前角色</Label>
              <div>
                <Badge variant={(roleBadgeMap[changeTarget?.role ?? 'viewer'] ?? roleBadgeMap.viewer).variant}>
                  {roleBadgeMap[changeTarget?.role ?? 'viewer']?.label}
                </Badge>
              </div>
            </div>
            <div className="field">
              <Label>新角色</Label>
              <Select
                options={roleSelectOptions}
                value={newRole}
                onChange={(e) => setNewRole(e.target.value as 'owner' | 'editor' | 'viewer')}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setChangeTarget(null)}>取消</Button>
            <Button
              variant="primary"
              disabled={changeRole.isPending || newRole === changeTarget?.role}
              onClick={handleChangeRole}
            >
              确定
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* 移除确认对话框 */}
      <Dialog open={!!removeTarget} onOpenChange={() => setRemoveTarget(null)}>
        <DialogContent className="w-[500px]">
          <DialogHeader>
            <DialogTitle>移除成员</DialogTitle>
            <DialogDescription>
              确定移除成员 {removeTarget?.username} 吗?移除后该用户将无法访问本项目
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setRemoveTarget(null)}>取消</Button>
            <Button
              variant="danger"
              disabled={removeMember.isPending}
              onClick={handleRemove}
            >
              确定
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* 转让 owner 确认对话框 */}
      <Dialog open={!!transferTarget} onOpenChange={() => setTransferTarget(null)}>
        <DialogContent className="w-[500px]">
          <DialogHeader>
            <DialogTitle>转让所有者</DialogTitle>
            <DialogDescription>
              确定将所有者权限转让给 {transferTarget?.username} 吗?转让后您将降为编辑者。
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setTransferTarget(null)}>取消</Button>
            <Button
              variant="primary"
              disabled={transferOwnership.isPending}
              onClick={handleTransfer}
            >
              确定
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {ToastEl}
    </div>
  )
}
