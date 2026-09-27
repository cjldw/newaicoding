/**
 * R1(统一任务创建入口)失败测试(QA Red)
 * 规格来源:docs/20260927_任务新建菜单优化/DEVPLAN/R1.md
 *
 * 验证 /manage/tasks(TasksManage)页:
 *   1. 页头仅显示一个「新建任务」按钮
 *   2. 点击按钮打开统一创建表单(对话框标题「新建任务 · 快速创建」)
 *   3. 原有三个分类型按钮(新建开发任务/新建测试任务/新建发布任务)不再显示
 *
 * 运行方式(测试栈为 QA 临时安装,--no-save 不改动 package.json):
 *   cd frontend && npm install --no-save vitest jsdom @testing-library/react @testing-library/dom
 *   npx vitest run src/pages/manage/__tests__/TaskCreateDialog.test.tsx
 */
/** @vitest-environment jsdom */
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, fireEvent, cleanup } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { TasksManage } from '../ManagePages'

// vitest 未开 globals,RTL 自动清理不生效,手动逐测清 DOM(防跨测渲染叠加)
afterEach(cleanup)

// ---- API 层打桩:只渲染真实组件树,数据全部置空,避免测试触网 ----
vi.mock('@/api/dashboard', () => ({
  useDimensionList: () => ({ data: { items: [], total: 0 }, isLoading: false }),
}))

vi.mock('@/api/projects', () => ({
  useProjectList: () => ({ data: { items: [] } }),
  useProjectMembers: () => ({ data: { items: [] } }),
}))

vi.mock('@/api/requirements', () => ({
  useBranchPreview: () => ({ data: undefined }),
  useRequirementDetail: () => ({ data: undefined }),
  requirementsApi: {
    list: vi.fn().mockResolvedValue({ data: { items: [], total: 0 } }),
    detail: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    branchPreview: vi.fn(),
  },
}))

vi.mock('@/api/tasks', () => ({
  createTask: vi.fn(),
  useTaskDetail: () => ({ data: undefined }),
  useUpdateTask: () => ({ mutate: vi.fn(), isPending: false }),
}))

function renderTasksManage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <TasksManage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('R1 统一任务创建入口(/manage/tasks)', () => {
  it('页头仅显示一个「新建任务」按钮', () => {
    renderTasksManage()
    const btns = screen.queryAllByRole('button', { name: '新建任务' })
    expect(btns).toHaveLength(1)
  })

  it('点击「新建任务」打开统一创建表单(标题:新建任务 · 快速创建)', async () => {
    renderTasksManage()
    const btn = screen.queryByRole('button', { name: '新建任务' })
    expect(btn).not.toBeNull() // 入口按钮必须存在
    fireEvent.click(btn!)
    expect(await screen.findByText('新建任务 · 快速创建')).not.toBeNull()
  })

  it('原有三个分类型按钮不再显示', () => {
    renderTasksManage()
    for (const label of ['新建开发任务', '新建测试任务', '新建发布任务']) {
      // exact:false 子串匹配,连「(快速创建)」后缀的旧按钮一并拦截
      expect(screen.queryByText(label, { exact: false })).toBeNull()
    }
  })
})
