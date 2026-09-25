/**
 * 用户管理页 — R19 BUG-002
 * - 筛选:状态下拉 + 搜索(300ms 防抖)
 * - 工具栏:邀请新用户按钮
 * - 表格:手机号打码/昵称+头像/角色徽章/状态徽章/GitLab 绑定/注册时间/操作
 * - 分页:20/页
 * - 邀请对话框:生成 token + 复制
 * - 禁用确认对话框
 */

import { useState, useEffect, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Search, Copy, Check, Users, Plus } from 'lucide-react'
import {
  Table,
  TableHeader,
  TableBody,
  TableHead,
  TableRow,
  TableCell,
} from '@/components/ui/Table'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Select } from '@/components/ui/Select'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogFooter,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/Dialog'
import { adminUsersApi, adminInvitationsApi, type AdminUser } from '@/api/admin'
import { useToast } from '@/hooks/useToast'

export default function UserManagementPage() {
  const queryClient = useQueryClient()
  const [, showToast, ToastEl] = useToast()
  const [statusFilter, setStatusFilter] = useState('')
  const [searchInput, setSearchInput] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [page, setPage] = useState(1)
  const [inviteDialogOpen, setInviteDialogOpen] = useState(false)
  const [disableDialogOpen, setDisableDialogOpen] = useState(false)
  const [selectedUser, setSelectedUser] = useState<AdminUser | null>(null)
  const [invitationToken, setInvitationToken] = useState('')
  const [copied, setCopied] = useState(false)

  // 300ms 防抖
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedSearch(searchInput), 300)
    return () => clearTimeout(timer)
  }, [searchInput])

  // 查询用户列表
  const { data, isLoading } = useQuery({
    queryKey: ['admin-users', statusFilter, debouncedSearch, page],
    queryFn: () =>
      adminUsersApi.list({
        status: statusFilter || undefined,
        q: debouncedSearch || undefined,
        page,
        page_size: 20,
      }),
  })

  const users: AdminUser[] = data?.data?.items ?? []
  const total = data?.data?.total ?? 0
  const totalPages = Math.ceil(total / 20)

  // BUG-006 ②:唯一超管禁用按钮置灰
  // 判定策略:当前页可见超管数 === 1 且当前页即全量(total === users.length,说明无跨页数据)
  // 此时该超管为系统唯一超管,前端置灰 + title 提示。
  // 局限:若超管分布在多页(如 total > users.length 且当前页无超管),前端无法可靠判定,
  // 依赖服务端 19001 错误码兜底(见 updateStatusMutation.onError)。
  const isOnlySuperadminVisible = useMemo(() => {
    if (users.length === 0) return false
    const superadminsInPage = users.filter((u) => u.role === 'superadmin')
    if (superadminsInPage.length !== 1) return false
    // 仅当当前页即全量数据时才可判定"系统唯一"
    if (total !== users.length) return false
    return true
  }, [users, total])

  // 禁用/启用 mutation
  const updateStatusMutation = useMutation({
    mutationFn: ({ userId, status }: { userId: string; status: 'active' | 'disabled' }) =>
      adminUsersApi.updateStatus(userId, status),
    onSuccess: (resp) => {
      queryClient.invalidateQueries({ queryKey: ['admin-users'] })
      setDisableDialogOpen(false)
      setSelectedUser(null)
      const d = resp.data
      const msg =
        d.status === 'disabled'
          ? `已禁用,取消 ${d.cancelled_tasks} 个进行中任务`
          : '已启用'
      showToast('ok', msg)
    },
    onError: (err: any) => {
      if (err.code === 19001) {
        showToast('err', '最后一个超级管理员不可禁用')
      } else {
        showToast('err', err.message || '操作失败')
      }
    },
  })

  // 邀请 mutation
  const inviteMutation = useMutation({
    mutationFn: (phone: string) => adminInvitationsApi.create(phone),
    onSuccess: (resp) => {
      setInvitationToken(resp.data.invitation_token)
      queryClient.invalidateQueries({ queryKey: ['admin-invitations'] })
    },
    onError: (err: any) => showToast('err', err.message || '生成邀请失败'),
  })

  const handleInvite = () => {
    setInviteDialogOpen(true)
    setInvitationToken('')
    inviteMutation.mutate('')
  }

  const handleCopyToken = async () => {
    if (!invitationToken) return
    await navigator.clipboard.writeText(invitationToken)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const handleDisableClick = (user: AdminUser) => {
    setSelectedUser(user)
    setDisableDialogOpen(true)
  }

  const handleConfirmDisable = () => {
    if (!selectedUser) return
    updateStatusMutation.mutate({
      userId: selectedUser.user_id,
      status: 'disabled',
    })
  }

  const handleEnableClick = (user: AdminUser) => {
    updateStatusMutation.mutate({
      userId: user.user_id,
      status: 'active',
    })
  }

  const statusOptions = useMemo(
    () => [
      { label: '全部状态', value: '' },
      { label: '正常', value: 'active' },
      { label: '已禁用', value: 'disabled' },
    ],
    [],
  )

  const formatDate = (dateStr: string) => {
    const d = new Date(dateStr)
    return d.toLocaleString('zh-CN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    })
  }

  return (
    <div className="page wide">
      {/* 页头(对齐 vp:图标 + 标题 + 副标题;邀请按钮主色 btn-pri) */}
      <div className="page-head">
        <div>
          <h1 className="flex items-center gap-2"><Users size={18} /> 用户管理</h1>
          <div className="sub">平台级账号管理(仅超管)· 禁用即全失效:登录被拒 + 现有 JWT 立即失效(token_version)+ 进行中任务立即取消(销毁前强制 push)</div>
        </div>
        <div className="acts">
          <button className="btn btn-pri" onClick={handleInvite}><Plus className="w-4 h-4 mr-1" />邀请新用户</button>
        </div>
      </div>

      {/* 用户列表(筛选栏归位为卡片内顶部 .fbar 条,修复筛选控件与表格零间距相贴) */}
      <div className="card">
        <div className="fbar">
          <Select
            options={statusOptions}
            value={statusFilter}
            onChange={(e) => {
              setStatusFilter(e.target.value)
              setPage(1)
            }}
            className="w-40"
          />
          <div className="relative flex-1 max-w-sm">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-text-muted" />
            <Input
              placeholder="手机号/昵称"
              value={searchInput}
              onChange={(e) => {
                setSearchInput(e.target.value)
                setPage(1)
              }}
              className="pl-9"
            />
          </div>
        </div>
        <div className="scrollx">
          <Table className="tbl">
            {/* 宽屏列宽:固定列定宽,昵称列自适应吸收剩余空间 */}
            <colgroup>
              <col style={{ width: 140 }} />
              <col />
              <col style={{ width: 100 }} />
              <col style={{ width: 80 }} />
              <col style={{ width: 90 }} />
              <col style={{ width: 150 }} />
              <col style={{ width: 90 }} />
            </colgroup>
            <TableHeader>
              <TableRow>
                <TableHead>手机号</TableHead>
                <TableHead>昵称</TableHead>
                <TableHead>角色</TableHead>
                <TableHead>状态</TableHead>
                <TableHead>GitLab</TableHead>
                <TableHead>注册时间</TableHead>
                <TableHead className="ops">操作</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading ? (
                <TableRow>
                  <TableCell colSpan={7} className="text-center py-8 text-text-muted">
                    加载中...
                  </TableCell>
                </TableRow>
              ) : users.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={7} className="text-center py-8 text-text-muted">
                    暂无用户
                  </TableCell>
                </TableRow>
              ) : (
                users.map((user) => (
                  <TableRow key={user.user_id}>
                    <TableCell className="font-mono">{user.phone}</TableCell>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        {user.avatar_url ? (
                          <img
                            src={user.avatar_url}
                            alt={user.nickname || 'avatar'}
                            className="w-6 h-6 rounded-full"
                          />
                        ) : null}
                        <span>{user.nickname || '—'}</span>
                      </div>
                    </TableCell>
                    <TableCell>
                      {user.role === 'superadmin' ? (
                        <span className="bdg b-blue">超级管理员</span>
                      ) : (
                        <span className="text-text-muted">普通用户</span>
                      )}
                    </TableCell>
                    <TableCell>
                      {user.status === 'active' ? (
                        <span className="bdg b-green">正常</span>
                      ) : (
                        <span className="bdg b-red">已禁用</span>
                      )}
                    </TableCell>
                    <TableCell>
                      {user.gitlab_bound ? (
                        <span className="bdg b-green"><Check className="w-3 h-3" />已绑定</span>
                      ) : (
                        <span className="bdg b-amber">未绑定</span>
                      )}
                    </TableCell>
                    <TableCell className="text-text-muted">{formatDate(user.created_at)}</TableCell>
                    <TableCell className="ops">
                      {user.status === 'active' ? (
                        <button
                          className="btn btn-sm btn-danger"
                          onClick={() => handleDisableClick(user)}
                          disabled={user.role === 'superadmin' && isOnlySuperadminVisible}
                          title={
                            user.role === 'superadmin' && isOnlySuperadminVisible
                              ? '最后一个超级管理员不可禁用'
                              : undefined
                          }
                        >
                          禁用
                        </button>
                      ) : (
                        <button
                          className="btn btn-sm"
                          onClick={() => handleEnableClick(user)}
                        >
                          启用
                        </button>
                      )}
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </div>

        {/* 脚注:foot-split 左统计+规则 / 右分页(清理互挤的 marginLeft 内联) */}
        <div className="card-foot foot-split">
          <div className="flex items-center gap-3">
            <span className="small faint">共 {total} 条 · created_at 倒序 · 20/页</span>
            <span className="small faint">系统唯一超级管理员不可禁用</span>
          </div>
          {totalPages > 1 && (
            <div className="flex items-center gap-2">
              <button
                className="btn btn-sm"
                disabled={page === 1}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
              >
                上一页
              </button>
              <span className="small">{page} / {totalPages}</span>
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
      </div>

      {/* 邀请对话框 */}
      <Dialog open={inviteDialogOpen} onOpenChange={setInviteDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>邀请新用户</DialogTitle>
            <DialogDescription>
              生成一次性邀请令牌,7 天内有效。将令牌发送给被邀请人完成注册。
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            {invitationToken ? (
              <div className="space-y-3">
                <div className="text-sm font-medium text-text">邀请令牌</div>
                <div className="flex items-center gap-2">
                  <code className="flex-1 rounded-md bg-surface-strong px-3 py-2 font-mono text-sm text-text break-all">
                    {invitationToken}
                  </code>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={handleCopyToken}
                    className="shrink-0"
                  >
                    {copied ? (
                      <>
                        <Check className="h-4 w-4 mr-1" />
                        已复制
                      </>
                    ) : (
                      <>
                        <Copy className="h-4 w-4 mr-1" />
                        复制
                      </>
                    )}
                  </Button>
                </div>
                <div className="text-xs text-text-muted">
                  令牌有效期 7 天,使用后自动失效
                </div>
              </div>
            ) : (
              <div className="text-center py-4 text-text-muted">生成中...</div>
            )}
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setInviteDialogOpen(false)}>
              关闭
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* 禁用确认对话框 */}
      <Dialog open={disableDialogOpen} onOpenChange={setDisableDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>确认禁用</DialogTitle>
            <DialogDescription>
              确定禁用用户{' '}
              <span className="font-medium text-text">
                {selectedUser?.nickname || selectedUser?.phone}
              </span>{' '}
              吗?其现有登录将立即失效,进行中的任务将被取消。
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setDisableDialogOpen(false)}>
              取消
            </Button>
            <Button
              variant="danger"
              onClick={handleConfirmDisable}
              disabled={updateStatusMutation.isPending}
            >
              {updateStatusMutation.isPending ? '处理中...' : '确认禁用'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {ToastEl}
    </div>
  )
}
