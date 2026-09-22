/**
 * TestReport — 测试报告页 /tasks/:taskId/report
 * 统计卡片(总用例数/通过数/失败数/通过率)+ 用例 Table + 失败时操作栏
 */
import { useState, useMemo } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Textarea } from '@/components/ui/Textarea'
import { Badge } from '@/components/ui/Badge'
import { Card } from '@/components/ui/Card'
import {
  Table, TableHeader, TableBody, TableRow, TableHead, TableCell,
} from '@/components/ui/Table'
import { useTaskDetail } from '@/api/tasks'
import { useAcceptFailure, useRejectToDev, type TestCase } from '@/api/testTasks'

interface ExtShape {
  test_cases?: TestCase[]
}

const statusBadge: Record<string, { label: string; variant: 'success' | 'error' | 'default' }> = {
  passed: { label: '通过', variant: 'success' },
  failed: { label: '失败', variant: 'error' },
  pending: { label: '待执行', variant: 'default' },
}

export default function TestReport() {
  const { taskId = '' } = useParams<{ taskId: string }>()
  const nav = useNavigate()
  const { data: task } = useTaskDetail(taskId)
  const acceptMut = useAcceptFailure(taskId)
  const rejectMut = useRejectToDev(taskId)

  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [showAccept, setShowAccept] = useState(false)
  const [reason, setReason] = useState('')
  const [rejectTitle, setRejectTitle] = useState('')
  const [rejectDesc, setRejectDesc] = useState('')
  const [showReject, setShowReject] = useState(false)

  const cases = useMemo<TestCase[]>(() => {
    if (!task) return []
    const ext = (task as unknown as { extended_attributes?: ExtShape }).extended_attributes
    return ext?.test_cases ?? []
  }, [task])

  const stats = useMemo(() => {
    const total = cases.length
    const passed = cases.filter((c) => c.status === 'passed').length
    const failed = cases.filter((c) => c.status === 'failed').length
    const rate = total ? Math.round((passed / total) * 100) : 0
    return { total, passed, failed, rate }
  }, [cases])

  const hasFailed = stats.failed > 0

  const handleAccept = () => {
    if (!reason.trim()) return
    acceptMut.mutate(
      { reason: reason.trim() },
      { onSuccess: () => nav(`/tasks/${taskId}`) },
    )
  }

  const handleReject = () => {
    if (!rejectTitle.trim()) return
    rejectMut.mutate(
      { title: rejectTitle.trim(), description: rejectDesc.trim() },
      { onSuccess: (res) => nav(`/tasks/${res.task_id}`) },
    )
  }

  if (!task) {
    return <div className="container mx-auto px-4 py-6 text-text-muted">加载中...</div>
  }

  return (
    <div className="page wide">
      <div className="page-head">
        <h1 className="text-2xl font-semibold text-text">测试报告</h1>
        <p className="text-sm text-text-muted mt-1">任务:{task.title}</p>
      </div>

      {/* 统计卡片 */}
      <div className="grid grid-cols-4 gap-4 mb-6">
        <Card className="p-4">
          <div className="text-sm text-text-muted">总用例数</div>
          <div className="text-2xl font-bold text-text mt-1">{stats.total}</div>
        </Card>
        <Card className="p-4">
          <div className="text-sm text-text-muted">通过数</div>
          <div className="text-2xl font-bold text-green-600 mt-1">{stats.passed}</div>
        </Card>
        <Card className="p-4">
          <div className="text-sm text-text-muted">失败数</div>
          <div className="text-2xl font-bold text-red-600 mt-1">{stats.failed}</div>
        </Card>
        <Card className="p-4">
          <div className="text-sm text-text-muted">通过率</div>
          <div className="text-2xl font-bold text-primary mt-1">{stats.rate}%</div>
        </Card>
      </div>

      {/* 用例列表 */}
      <div className="card">
      <div className="scrollx">
        <Table className="tbl">
          <TableHeader>
            <TableRow>
              <TableHead>用例标题</TableHead>
              <TableHead className="w-[100px]">状态</TableHead>
              <TableHead className="w-[100px]">日志</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {cases.map((c) => {
              const sb = statusBadge[c.status] ?? statusBadge.pending
              const expanded = expandedId === c.id
              return (
                <>
                  <TableRow key={c.id} className="cursor-pointer hover:bg-surface-hover">
                    <TableCell className="font-medium">{c.title}</TableCell>
                    <TableCell>
                      <Badge variant={sb.variant}>{sb.label}</Badge>
                    </TableCell>
                    <TableCell>
                      {c.log ? (
                        <button
                          className="text-primary text-sm underline"
                          onClick={() => setExpandedId(expanded ? null : c.id)}
                        >
                          {expanded ? '收起' : '查看'}
                        </button>
                      ) : (
                        <span className="text-text-muted text-sm">-</span>
                      )}
                    </TableCell>
                  </TableRow>
                  {expanded && c.log && (
                    <TableRow>
                      <TableCell colSpan={3} className="bg-surface-hover">
                        <pre className="text-xs text-text-muted whitespace-pre-wrap p-3">
                          {c.log}
                        </pre>
                      </TableCell>
                    </TableRow>
                  )}
                </>
              )
            })}
            {cases.length === 0 && (
              <TableRow>
                <TableCell colSpan={3} className="text-center text-text-muted py-8">
                  暂无用例数据
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>
      </div>

      {/* 失败时操作栏 */}
      {hasFailed && (
        <div className="flex justify-end gap-2">
          {!showAccept ? (
            <Button variant="outline" onClick={() => setShowAccept(true)}>
              接受失败
            </Button>
          ) : (
            <div className="flex flex-col gap-2 w-[400px]">
              <label className="text-sm font-medium text-text">豁免理由</label>
              <Textarea
                placeholder="请输入接受失败的理由"
                value={reason}
                onChange={(e) => setReason(e.target.value)}
              />
              <div className="flex gap-2 justify-end">
                <Button variant="outline" onClick={() => { setShowAccept(false); setReason('') }}>
                  取消
                </Button>
                <Button
                  variant="outline"
                  onClick={handleAccept}
                  disabled={!reason.trim() || acceptMut.isPending}
                >
                  {acceptMut.isPending ? '提交中...' : '确认'}
                </Button>
              </div>
            </div>
          )}

          {!showReject ? (
            <Button variant="primary" onClick={() => setShowReject(true)}>
              驳回回开发
            </Button>
          ) : (
            <div className="flex flex-col gap-2 w-[400px]">
              <Input
                placeholder="问题标题"
                value={rejectTitle}
                onChange={(e) => setRejectTitle(e.target.value)}
              />
              <Textarea
                placeholder="问题描述"
                value={rejectDesc}
                onChange={(e) => setRejectDesc(e.target.value)}
              />
              <div className="flex gap-2 justify-end">
                <Button variant="outline" onClick={() => { setShowReject(false); setRejectTitle(''); setRejectDesc('') }}>
                  取消
                </Button>
                <Button
                  variant="primary"
                  onClick={handleReject}
                  disabled={!rejectTitle.trim() || rejectMut.isPending}
                >
                  {rejectMut.isPending ? '提交中...' : '确认驳回'}
                </Button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
