/**
 * TestCasesReview — 测试用例审阅页 /tasks/:taskId/cases
 * 从任务详情 extended_attributes.test_cases 读取用例列表
 * 支持编辑/删除/新增用例,“开始执行”调 confirm-cases 后跳回工作台
 */
import { useState, useMemo } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Textarea } from '@/components/ui/Textarea'
import {
  Table, TableHeader, TableBody, TableRow, TableHead, TableCell,
} from '@/components/ui/Table'
import { useTaskDetail } from '@/api/tasks'
import { useConfirmCases, type TestCase } from '@/api/testTasks'

interface ExtShape {
  test_cases?: TestCase[]
}

export default function TestCasesReview() {
  const { taskId = '' } = useParams<{ taskId: string }>()
  const nav = useNavigate()
  const { data: task } = useTaskDetail(taskId)
  const confirmMut = useConfirmCases(taskId)

  // 解析 extended_attributes.test_cases
  const initialCases = useMemo<TestCase[]>(() => {
    if (!task) return []
    const ext = (task as unknown as { extended_attributes?: ExtShape }).extended_attributes
    return ext?.test_cases ?? []
  }, [task])

  const [cases, setCases] = useState<TestCase[]>(initialCases)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [draft, setDraft] = useState<Partial<TestCase>>({})
  const [adding, setAdding] = useState(false)

  // 同步远端数据(首次加载)
  useMemo(() => {
    if (initialCases.length && !cases.length) setCases(initialCases)
  }, [initialCases])

  const startEdit = (c: TestCase) => {
    setEditingId(c.id)
    setDraft({ title: c.title, steps: c.steps, expected: c.expected })
  }
  const cancelEdit = () => { setEditingId(null); setDraft({}) }
  const saveEdit = () => {
    if (!editingId) return
    setCases((prev) => prev.map((c) =>
      c.id === editingId ? { ...c, ...draft } as TestCase : c
    ))
    cancelEdit()
  }
  const removeCase = (id: string) => {
    setCases((prev) => prev.filter((c) => c.id !== id))
  }
  const startAdd = () => {
    setAdding(true)
    setDraft({ title: '', steps: '', expected: '' })
  }
  const cancelAdd = () => { setAdding(false); setDraft({}) }
  const saveAdd = () => {
    if (!draft.title?.trim()) return
    const newCase: TestCase = {
      id: `local-${Date.now()}`,
      title: draft.title!.trim(),
      steps: draft.steps ?? '',
      expected: draft.expected ?? '',
      status: 'pending',
    }
    setCases((prev) => [...prev, newCase])
    cancelAdd()
  }

  const handleExecute = () => {
    confirmMut.mutate(
      { test_cases: cases.map((c) => ({
        id: c.id, title: c.title, steps: c.steps, expected: c.expected, status: c.status,
      })) },
      { onSuccess: () => nav(`/tasks/${taskId}`) },
    )
  }

  if (!task) {
    return <div className="container mx-auto px-4 py-6 text-text-muted">加载中...</div>
  }

  return (
    <div className="container mx-auto px-4 py-6 max-w-6xl">
      <div className="mb-6">
        <h1 className="text-2xl font-semibold text-text">测试用例审阅</h1>
        <p className="text-sm text-text-muted mt-1">任务:{task.title}</p>
      </div>

      <div className="border border-border rounded-lg overflow-hidden">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-[200px]">用例标题</TableHead>
              <TableHead>步骤</TableHead>
              <TableHead className="w-[200px]">预期结果</TableHead>
              <TableHead className="w-[140px]">操作</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {cases.map((c) => (
              <TableRow key={c.id}>
                {editingId === c.id ? (
                  <>
                    <TableCell>
                      <Input
                        value={draft.title ?? ''}
                        onChange={(e) => setDraft({ ...draft, title: e.target.value })}
                      />
                    </TableCell>
                    <TableCell>
                      <Textarea
                        value={draft.steps ?? ''}
                        onChange={(e) => setDraft({ ...draft, steps: e.target.value })}
                      />
                    </TableCell>
                    <TableCell>
                      <Input
                        value={draft.expected ?? ''}
                        onChange={(e) => setDraft({ ...draft, expected: e.target.value })}
                      />
                    </TableCell>
                    <TableCell>
                      <div className="flex gap-1">
                        <Button size="sm" variant="primary" onClick={saveEdit}>保存</Button>
                        <Button size="sm" variant="outline" onClick={cancelEdit}>取消</Button>
                      </div>
                    </TableCell>
                  </>
                ) : (
                  <>
                    <TableCell className="font-medium">{c.title}</TableCell>
                    <TableCell className="text-text-muted text-sm whitespace-pre-wrap">
                      {c.steps}
                    </TableCell>
                    <TableCell className="text-text-muted text-sm">{c.expected}</TableCell>
                    <TableCell>
                      <div className="flex gap-1">
                        <Button size="sm" variant="outline" onClick={() => startEdit(c)}>编辑</Button>
                        <Button size="sm" variant="outline" onClick={() => removeCase(c.id)}>删除</Button>
                      </div>
                    </TableCell>
                  </>
                )}
              </TableRow>
            ))}
            {adding && (
              <TableRow>
                <TableCell>
                  <Input
                    placeholder="用例标题"
                    value={draft.title ?? ''}
                    onChange={(e) => setDraft({ ...draft, title: e.target.value })}
                  />
                </TableCell>
                <TableCell>
                  <Textarea
                    placeholder="步骤"
                    value={draft.steps ?? ''}
                    onChange={(e) => setDraft({ ...draft, steps: e.target.value })}
                  />
                </TableCell>
                <TableCell>
                  <Input
                    placeholder="预期结果"
                    value={draft.expected ?? ''}
                    onChange={(e) => setDraft({ ...draft, expected: e.target.value })}
                  />
                </TableCell>
                <TableCell>
                  <div className="flex gap-1">
                    <Button size="sm" variant="primary" onClick={saveAdd}>保存</Button>
                    <Button size="sm" variant="outline" onClick={cancelAdd}>取消</Button>
                  </div>
                </TableCell>
              </TableRow>
            )}
            {cases.length === 0 && !adding && (
              <TableRow>
                <TableCell colSpan={4} className="text-center text-text-muted py-8">
                  暂无用例,请点击“新增用例”
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>

      <div className="flex justify-end gap-2 mt-4">
        <Button variant="outline" onClick={adding ? cancelAdd : startAdd}>
          新增用例
        </Button>
        <Button
          variant="primary"
          onClick={handleExecute}
          disabled={cases.length === 0 || confirmMut.isPending}
        >
          {confirmMut.isPending ? '提交中...' : '开始执行'}
        </Button>
      </div>
    </div>
  )
}
