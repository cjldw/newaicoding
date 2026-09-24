/**
 * 审计日志页 — R19 BUG-002
 * - 筛选:时间范围(默认最近 7 天)/操作类型下拉
 * - 表格:时间/操作者+superadmin徽章/操作类型/项目/目标/详情 JSON 摘要悬浮/IP
 * - 分页:20/页,created_at 倒序
 */

import { useState, useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ScrollText } from 'lucide-react'
import {
  Table,
  TableHeader,
  TableBody,
  TableHead,
  TableRow,
  TableCell,
} from '@/components/ui/Table'
import { adminAuditLogsApi, adminUsersApi, type AuditLog } from '@/api/admin'
import { ApiError } from '@/api/client'

// 操作类型映射
const ACTION_TYPE_MAP: Record<string, string> = {
  user_disable: '禁用用户',
  user_enable: '启用用户',
  invitation_create: '创建邀请',
  invitation_revoke: '撤销邀请',
  runner_create: '创建 Runner',
  runner_delete: '删除 Runner',
  platform_settings_update: '更新平台设置',
  skill_publish: '发布技能',
  skill_unpublish: '下架技能',
}

// 危险操作 → b-red,其余 → b-zinc
const DANGEROUS_ACTIONS = new Set([
  'user_disable',
  'task_force_push',
  'review_reject',
])

// 时区钉死 GMT+8(BUG-039):与后端库内墙钟(DATETIME 存 +08:00 裸值)口径一致,
// 显式 Asia/Shanghai 格式化——不用 toISOString()(UTC),也不用无参 toLocaleString()(随浏览器时区)
const PLATFORM_TZ = 'Asia/Shanghai'

// Date → GMT+8 裸时间串 YYYY-MM-DDTHH:mm(datetime-local 原生格式,无时区后缀)
function formatGmt8(date: Date): string {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: PLATFORM_TZ,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
  }).formatToParts(date)
  const get = (type: string) => parts.find((p) => p.type === type)?.value ?? ''
  return `${get('year')}-${get('month')}-${get('day')}T${get('hour')}:${get('minute')}`
}

// 默认最近 7 天
function getDefaultDateRange() {
  return {
    start_time: formatGmt8(new Date(Date.now() - 7 * 86400000)),
    end_time: formatGmt8(new Date()),
  }
}

export default function AuditLogsPage() {
  const defaultRange = useMemo(getDefaultDateRange, [])
  const [startTime, setStartTime] = useState(defaultRange.start_time)
  const [endTime, setEndTime] = useState(defaultRange.end_time)
  const [userIdFilter, setUserIdFilter] = useState('')
  const [actionTypeFilter, setActionTypeFilter] = useState('')
  const [page, setPage] = useState(1)

  // 获取用户列表用于筛选下拉
  const { data: usersData } = useQuery({
    queryKey: ['admin-users-for-audit'],
    queryFn: () => adminUsersApi.list({ page_size: 100 }),
  })
  const users = usersData?.data?.items ?? []

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['admin-audit-logs', startTime, endTime, userIdFilter, actionTypeFilter, page],
    queryFn: () =>
      adminAuditLogsApi.list({
        start_time: startTime || undefined,
        end_time: endTime || undefined,
        user_id: userIdFilter || undefined,
        action_type: actionTypeFilter || undefined,
        page,
        page_size: 20,
      }),
  })
  // 401/403(19002)→ 引导重新登录;其余(5xx/网络)→ 通用错误 + 重试(不再静默渲染空表)
  const isAuthError =
    error instanceof ApiError && (error.code === 401 || error.code === 403 || error.code === 19002)

  const logs = data?.data?.items ?? []
  const total = data?.data?.total ?? 0
  const totalPages = Math.ceil(total / 20)

  const actionTypeOptions = useMemo(
    () => [
      { label: '全部操作', value: '' },
      ...Object.entries(ACTION_TYPE_MAP).map(([value, label]) => ({
        label,
        value,
      })),
    ],
    [],
  )

  // 时间列:直接渲染后端 created_at 裸串(GMT+8 墙钟,无时区后缀);
  // 禁止经 new Date() 再格式化——那会被浏览器时区重解释(BUG-039 同根)
  const formatCreatedAt = (createdAt: string) => createdAt.replace('T', ' ')

  const formatDetail = (detail: Record<string, unknown> | null) => {
    if (!detail) return '—'
    return JSON.stringify(detail, null, 2)
  }

  return (
    <div className="page wide">
      {/* 页头(vp L1809 结构:icon + 标题,换行,说明 sub) */}
      <div className="page-head">
        <div>
          <h1 className="flex items-center gap-2"><ScrollText size={18} /> 审计日志</h1>
          <div className="sub">敏感操作全量留痕(仅超管可查)· 只读追加、不可删改 · 异步写入(失败重试,连续失败 critical 告警)· 保留 1 年</div>
        </div>
      </div>

      {/* 日志列表(筛选条 .fbar 归入卡片内顶部,对齐 DimensionPage 范式) */}
      <div className="card">
        <div className="fbar">
          <span className="bdg b-zinc">最近 7 天</span>
          <input
            type="datetime-local"
            className="input"
            value={startTime}
            onChange={(e) => {
              setStartTime(e.target.value)
              setPage(1)
            }}
          />
          <input
            type="datetime-local"
            className="input"
            value={endTime}
            onChange={(e) => {
              setEndTime(e.target.value)
              setPage(1)
            }}
          />
          <select
            className="input"
            value={userIdFilter}
            onChange={(e) => {
              setUserIdFilter(e.target.value)
              setPage(1)
            }}
          >
            <option value="">全部操作人</option>
            {users.map((u) => (
              <option key={u.user_id} value={u.user_id}>
                {u.nickname || u.phone}
              </option>
            ))}
          </select>
          <select
            className="input"
            value={actionTypeFilter}
            onChange={(e) => {
              setActionTypeFilter(e.target.value)
              setPage(1)
            }}
          >
            {actionTypeOptions.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
          <button
            className="btn btn-sm"
            onClick={() => {
              const range = getDefaultDateRange()
              setStartTime(range.start_time)
              setEndTime(range.end_time)
              setUserIdFilter('')
              setActionTypeFilter('')
              setPage(1)
            }}
          >
            重置
          </button>
          <button
            className="btn btn-sm btn-pri"
            disabled={!!startTime && !!endTime && startTime > endTime}
            title={!!startTime && !!endTime && startTime > endTime ? '开始时间晚于结束时间' : undefined}
            onClick={() => refetch()}
          >
            查询
          </button>
          {/* 统计文案:fbar 右侧 */}
          <span className="small faint" style={{ marginLeft: 'auto' }}>
            共 {total} 条 · created_at 倒序 · 20/页
          </span>
        </div>

        <div className="scrollx">
          <Table className="tbl">
            {/* 宽屏列宽:固定列定宽,目标列自适应吸收剩余空间,避免全宽拉稀 */}
            <colgroup>
              <col style={{ width: 150 }} />
              <col style={{ width: 130 }} />
              <col style={{ width: 110 }} />
              <col style={{ width: 110 }} />
              <col />
              <col style={{ width: 90 }} />
              <col style={{ width: 110 }} />
            </colgroup>
            <TableHeader>
              <TableRow>
                <TableHead>时间</TableHead>
                <TableHead>操作者</TableHead>
                <TableHead>操作类型</TableHead>
                <TableHead>项目</TableHead>
                <TableHead>目标</TableHead>
                <TableHead>详情</TableHead>
                <TableHead>IP</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading ? (
                <TableRow>
                  <TableCell colSpan={7} className="text-center py-8 text-text-muted">
                    加载中...
                  </TableCell>
                </TableRow>
              ) : isError ? (
                <TableRow>
                  <TableCell colSpan={7} className="text-center py-8">
                    <div className="text-text-muted">
                      {isAuthError
                        ? '登录已过期或无平台超管权限,请重新登录'
                        : `加载审计日志失败${error instanceof ApiError ? `:${error.message}` : ''}`}
                    </div>
                    <button className="btn btn-sm" style={{ marginTop: '8px' }} onClick={() => refetch()}>
                      重试
                    </button>
                  </TableCell>
                </TableRow>
              ) : logs.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={7} className="text-center py-8 text-text-muted">
                    暂无符合条件的日志
                  </TableCell>
                </TableRow>
              ) : (
                logs.map((log: AuditLog) => (
                  <TableRow key={log.log_id}>
                    <TableCell className="mono small muted" style={{ whiteSpace: 'nowrap' }}>
                      {formatCreatedAt(log.created_at)}
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-1.5">
                        <span className="small cell-txt">
                          {log.operator_nickname || log.user_id.slice(0, 8)}
                        </span>
                        {log.operator_role === 'superadmin' && (
                          <span
                            className="bdg b-blue"
                            style={{ fontSize: '10px', padding: '0 5px' }}
                          >
                            superadmin
                          </span>
                        )}
                      </div>
                    </TableCell>
                    <TableCell>
                      <span
                        className={`bdg ${DANGEROUS_ACTIONS.has(log.action_type) ? 'b-red' : 'b-zinc'}`}
                      >
                        {ACTION_TYPE_MAP[log.action_type] || log.action_type}
                      </span>
                    </TableCell>
                    <TableCell className="text-text-muted">
                      {log.project_id ? log.project_id.slice(0, 8) : '—'}
                    </TableCell>
                    <TableCell className="text-text-muted">
                      <span className="cell-txt">
                        {log.target_type && log.target_id
                          ? `${log.target_type}:${log.target_id.slice(0, 8)}`
                          : '—'}
                      </span>
                    </TableCell>
                    <TableCell>
                      {log.detail ? (
                        <div className="group relative">
                          <span className="cursor-help text-text-muted border-b border-dashed border-text-muted/30">
                            JSON 摘要
                          </span>
                          <div className="absolute z-50 hidden group-hover:block bottom-full left-0 mb-1 w-72 p-2 rounded-md bg-surface-strong border border-border shadow-lg">
                            <pre className="text-xs text-text font-mono whitespace-pre-wrap break-all">
                              {formatDetail(log.detail)}
                            </pre>
                          </div>
                        </div>
                      ) : (
                        <span className="text-text-muted">—</span>
                      )}
                    </TableCell>
                    <TableCell className="mono small muted">
                      {log.ip || '—'}
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </div>

        {/* 分页:移入 .card-foot */}
        {totalPages > 1 && (
          <div className="card-foot">
            <div className="flex items-center gap-2">
              <button
                className="btn btn-sm"
                disabled={page === 1}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
              >
                上一页
              </button>
              <span className="small">
                {page} / {totalPages}
              </span>
              <button
                className="btn btn-sm"
                disabled={page === totalPages}
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              >
                下一页
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
