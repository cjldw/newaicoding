/**
 * MemberManagement — 成员管理 Tab(R12)
 * - 操作栏:右侧"邀请成员"按钮
 * - 成员 Table:头像+用户名(昵称副标题)/角色徽章/邀请人/加入时间/操作
 * - 三个对话框:邀请成员/改角色/移除确认 + 转让 owner
 */

import { useState, useEffect, useRef } from 'react'
import { UserPlus } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { Input } from '@/components/ui/Input'
import { Label } from '@/components/ui/Label'
import { Select } from '@/components/ui/Select'
import { Avatar } from '@/components/ui/Avatar'
import { Alert } from '@/components/ui/Alert'
import {
  Table, TableHeader, TableBody, TableRow, TableHead, TableCell,
} from '@/components/ui/Table'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
  DialogFooter,
} from '@/components/ui/Dialog'
import {
  useProjectMembers, useInviteMember, useRemoveMember,
  useChangeMemberRole, useTransferOwnership,
  getMemberErrorMessage,
} from '@/api/projects'
import type { ProjectMember } from '@/api/projects'
import { usersApi } from '@/api/users'
import type { SearchedUser } from '@/api/users'

const roleBadgeMap: Record<string, { label: string; variant: 'primary' | 'secondary' | 'outline' }> = {
  owner: { label: '所有者', variant: 'primary' },
  editor: { label: '编辑者', variant: 'secondary' },
  viewer: { label: '观察者', variant: 'outline' },
}

const roleDescMap: Record<string, string> = {
  editor: '编辑者(可编辑需求/任务/代码)',
  viewer: '观察者(只读)',
}

const roleSelectOptions = [
  { value: 'owner', label: '所有者' },
  { value: 'editor', label: '编辑者' },
  { value: 'viewer', label: '观察者' },
]

const inviteRoleOptions = [
  { value: 'editor', label: roleDescMap.editor },
  { value: 'viewer', label: roleDescMap.viewer },
]

interface MemberManagementProps {
  projectId: string
}

export function MemberManagement({ projectId }: MemberManagementProps) {
  const { data, isLoading } = useProjectMembers(projectId)
  const inviteMember = useInviteMember()
  const removeMember = useRemoveMember()
  const changeRole = useChangeMemberRole()
  const transferOwnership = useTransferOwnership()

  const [inviteOpen, setInviteOpen] = useState(false)
  const [changeTarget, setChangeTarget] = useState<ProjectMember | null>(null)
  const [removeTarget, setRemoveTarget] = useState<ProjectMember | null>(null)
  const [transferTarget, setTransferTarget] = useState<ProjectMember | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)

  // 邀请对话框状态
  const [phone, setPhone] = useState('')
  const [searchedUser, setSearchedUser] = useState<SearchedUser | null>(null)
  const [searching, setSearching] = useState(false)
  const [searchNoResult, setSearchNoResult] = useState(false)
  const [inviteRole, setInviteRole] = useState<'editor' | 'viewer'>('editor')

  // 改角色对话框状态
  const [newRole, setNewRole] = useState<'owner' | 'editor' | 'viewer'>('editor')

  const members = data?.items ?? []
  const ownerCount = members.filter(m => m.role === 'owner').length

  // 防抖搜索(300ms)
  const debounceRef = useRef<ReturnType<typeof setTimeout>>()
  useEffect(() => {
    if (!inviteOpen) return
    if (debounceRef.current) clearTimeout(debounceRef.current)
    if (!phone.trim()) {
      setSearchedUser(null); setSearchNoResult(false); setSearching(false)
      return
    }
    setSearching(true)
    debounceRef.current = setTimeout(async () => {
      try {
        const res = await usersApi.searchUserByPhone(phone.trim())
        const user = res.data
        if (user) { setSearchedUser(user); setSearchNoResult(false) }
        else { setSearchedUser(null); setSearchNoResult(true) }
      } catch {
        setSearchedUser(null); setSearchNoResult(true)
      } finally { setSearching(false) }
    }, 300)
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current) }
  }, [phone, inviteOpen])

  function resetInviteDialog() {
    setPhone(''); setSearchedUser(null); setSearchNoResult(false)
    setInviteRole('editor'); setError(null)
  }

  async function handleInvite() {
    if (!searchedUser) return
    setError(null)
    try {
      await inviteMember.mutateAsync({
        projectId, data: { phone: phone.trim(), role: inviteRole },
      })
      setSuccess('邀请成功')
      setInviteOpen(false); resetInviteDialog()
    } catch (e) {
      setError(getMemberErrorMessage(e))
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

      {/* 邀请成员对话框 */}
      <Dialog open={inviteOpen} onOpenChange={(o) => { setInviteOpen(o); if (!o) resetInviteDialog() }}>
        <DialogContent className="w-[500px]">
          <DialogHeader>
            <DialogTitle>邀请成员</DialogTitle>
            <DialogDescription>通过手机号搜索并邀请用户加入项目</DialogDescription>
          </DialogHeader>
          <div className="dlg-form">
            <div className="field">
              <Label>手机号</Label>
              <Input
                placeholder="输入手机号搜索"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
              />
              {searching && <div className="text-xs text-text-muted">搜索中...</div>}
              {searchNoResult && !searching && (
                <div className="text-xs text-red-fg">该手机号未注册</div>
              )}
              {searchedUser && (
                <div className="flex items-center gap-2 p-2 border border-border rounded-md">
                  <Avatar src={searchedUser.avatar_url} alt={searchedUser.nickname} size={28} />
                  <div className="text-sm">
                    <div className="font-medium">{searchedUser.nickname}</div>
                    <div className="text-xs text-text-muted">{searchedUser.phone_masked}</div>
                  </div>
                </div>
              )}
            </div>
            <div className="field">
              <Label>角色</Label>
              <Select
                options={inviteRoleOptions}
                value={inviteRole}
                onChange={(e) => setInviteRole(e.target.value as 'editor' | 'viewer')}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => { setInviteOpen(false); resetInviteDialog() }}>
              取消
            </Button>
            <Button
              variant="primary"
              disabled={!searchedUser || inviteMember.isPending}
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
    </div>
  )
}
