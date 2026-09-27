/**
 * TaskCreateDialog 统一创建表单测试(QA)
 * - R1(统一任务创建入口)失败测试(QA Red):/manage/tasks 页头仅一个「新建任务」按钮 → 打开统一创建表单
 * - R4(统一表单结构):公共字段(项目/需求/类型/标题/描述)显示与顺序、必填红色星号、
 *   必填校验拦截、提交成功跳转任务详情页、取消关闭、接口错误提示
 * 规格来源:
 *   docs/20260927_任务新建菜单优化/DEVPLAN/R1.md
 *   docs/20260927_任务新建菜单优化/DEVPLAN/R4.md
 *
 * 验证 /manage/tasks(TasksManage)页:
 *   1. 页头仅显示一个「新建任务」按钮
 *   2. 点击按钮打开统一创建表单(对话框标题「新建任务」,R4 文案清单将 R1 的「· 快速创建」后缀去掉)
 *   3. 原有三个分类型按钮(新建开发任务/新建测试任务/新建发布任务)不再显示
 *
 * 运行方式(测试栈为 QA 临时安装,--no-save 不改动 package.json):
 *   cd frontend && npm install --no-save vitest jsdom @testing-library/react @testing-library/dom
 *   npx vitest run src/pages/manage/__tests__/TaskCreateDialog.test.tsx
 */
/** @vitest-environment jsdom */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { TasksManage } from '../ManagePages'
import { TaskCreateDialog } from '../TaskCreateDialog'
import { createTask } from '@/api/tasks'
import { searchProjects } from '@/api/projects'
import type { ProjectListItem } from '@/api/projects'
import { searchRequirements } from '@/api/requirements'
import type { RequirementListItem } from '@/api/requirements'

// vitest 未开 globals,RTL 自动清理不生效,手动逐测清 DOM(防跨测渲染叠加)
afterEach(cleanup)

// ---- API 层打桩:只渲染真实组件树,数据全部置空,避免测试触网 ----
vi.mock('@/api/dashboard', () => ({
  useDimensionList: () => ({ data: { items: [], total: 0 }, isLoading: false }),
}))

vi.mock('@/api/projects', () => ({
  useProjectList: () => ({ data: { items: [] } }),
  useProjectMembers: () => ({ data: { items: [] } }),
  // R3.2/R4:统一表单的项目选择器走后端搜索
  searchProjects: vi.fn(),
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
  // R3.2/R4:统一表单的需求选择器走后端搜索
  searchRequirements: vi.fn(),
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

  it('点击「新建任务」打开统一创建表单(标题:新建任务)', async () => {
    renderTasksManage()
    const btn = screen.queryByRole('button', { name: '新建任务' })
    expect(btn).not.toBeNull() // 入口按钮必须存在
    fireEvent.click(btn!)
    // R4 文案清单:对话框标题「新建任务」(heading 角色定位,与页头同名按钮区分)
    expect(await screen.findByRole('heading', { name: '新建任务' })).not.toBeNull()
  })

  it('原有三个分类型按钮不再显示', () => {
    renderTasksManage()
    for (const label of ['新建开发任务', '新建测试任务', '新建发布任务']) {
      // exact:false 子串匹配,连「(快速创建)」后缀的旧按钮一并拦截
      expect(screen.queryByText(label, { exact: false })).toBeNull()
    }
  })
})

// ============================== R4 统一表单结构 ==============================

// ---- 测试数据:仅含组件运行时读取的字段,其余字段以断言绕开(测试桩不需要全量类型) ----
const PROJECTS = [
  { project_id: 'p1', name: '项目A', description: '描述A' },
  { project_id: 'p2', name: '项目B', description: '' },
] as unknown as ProjectListItem[]

const REQUIREMENTS = [
  { req_id: 'r1', title: '需求一' },
  { req_id: 'r2', title: '需求二' },
] as unknown as RequirementListItem[]

/** 路由探针:断言提交成功后跳转任务详情页 /tasks/:taskId */
function LocationProbe() {
  const location = useLocation()
  return <div data-testid="location-probe">{location.pathname}</div>
}

/** 直接挂载统一创建表单(R4 以表单为单位验证),返回 onClose 桩与重开渲染函数 */
function renderDialog(open = true) {
  const onClose = vi.fn()
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const ui = (isOpen: boolean) => (
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={['/manage/tasks']}>
        <TaskCreateDialog open={isOpen} onClose={onClose} />
        <LocationProbe />
      </MemoryRouter>
    </QueryClientProvider>
  )
  const utils = render(ui(open))
  return { ...utils, onClose, rerenderOpen: (o: boolean) => utils.rerender(ui(o)) }
}

/** 在可搜索下拉(SearchableSelect)中选一项:点开触发框 → 等选项出现 → 点选 */
async function pickOption(triggerText: string, optionText: string) {
  fireEvent.click(screen.getByText(triggerText))
  fireEvent.click(await screen.findByText(optionText))
}

/** 选择任务类型:对话框内唯一的原生 select(R2 选择器) */
function selectTaskType(value: 'dev' | 'test' | 'release') {
  const select = screen.getByRole('dialog').querySelector('select')
  if (!select) throw new Error('对话框内未找到任务类型下拉')
  fireEvent.change(select, { target: { value } })
}

/** 对话框内所有 label 的规整文本(去空白与必填星号) */
function labelNames(dialog: HTMLElement): string[] {
  return Array.from(dialog.querySelectorAll('label')).map((el) =>
    (el.textContent ?? '').replace(/[\s*]/g, ''),
  )
}

describe('R4 统一表单结构(TaskCreateDialog)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(searchProjects).mockResolvedValue(PROJECTS)
    vi.mocked(searchRequirements).mockResolvedValue(REQUIREMENTS)
    vi.mocked(createTask).mockResolvedValue({ task_id: 't-123' })
  })

  it('1. 打开创建表单:公共字段全部显示且顺序正确(项目→需求→类型→标题→描述)', async () => {
    renderDialog()
    const dialog = screen.getByRole('dialog')

    // 字段顺序(单列布局,从上到下):label 在 DOM 中的下标必须严格递增
    const names = labelNames(dialog)
    const order = ['关联项目', '关联需求', '任务类型', '任务标题', '任务描述'].map((n) =>
      names.indexOf(n),
    )
    expect(order.every((i) => i >= 0)).toBe(true)
    expect([...order].sort((a, b) => a - b)).toEqual(order)

    // 标题/描述 placeholder 照 R4 文案清单
    expect(screen.queryByPlaceholderText('留空默认取需求标题')).not.toBeNull()
    expect(screen.queryByPlaceholderText('本次要让 AI 做什么?')).not.toBeNull()
  })

  it('2. 必填字段(项目/需求/类型)label 显示红色星号,可选字段(标题/描述)不显示', () => {
    renderDialog()
    const dialog = screen.getByRole('dialog')
    const findLabel = (name: string) =>
      Array.from(dialog.querySelectorAll('label')).find(
        (el) => (el.textContent ?? '').replace(/[\s*]/g, '') === name,
      )

    for (const name of ['关联项目', '关联需求', '任务类型']) {
      const star = findLabel(name)?.querySelector('span.text-red-fg')
      expect(star, `${name} 缺少红色必填星号`).toBeTruthy()
      expect(star?.textContent).toBe('*')
    }
    for (const name of ['任务标题', '任务描述']) {
      expect(findLabel(name)?.querySelector('span.text-red-fg')).toBeNull()
    }
  })

  it('3. 不填必填字段直接提交:依次拦截并提示「请选择关联项目/需求/任务类型」,不调 createTask', async () => {
    renderDialog()
    const submit = () => fireEvent.click(screen.getByRole('button', { name: '创建' }))

    // 未选项目 → 拦截并提示
    submit()
    expect(screen.queryByText('请选择关联项目')).not.toBeNull()

    // 已选项目、未选需求 → 拦截并提示
    await pickOption('请选择项目', '项目A')
    submit()
    expect(screen.queryByText('请选择关联需求')).not.toBeNull()

    // 已选需求、未选类型 → 拦截并提示(须排除 select 内同名的 placeholder option 文本)
    await pickOption('请选择需求', '需求一')
    submit()
    const matches = screen.queryAllByText('请选择任务类型')
    expect(matches.some((el) => el.tagName !== 'OPTION')).toBe(true)

    // 校验拦截:始终未发出创建请求
    expect(createTask).not.toHaveBeenCalled()
  })

  it('4. 填写完整表单提交:调 createTask 并跳转任务详情页 /tasks/t-123', async () => {
    const { onClose } = renderDialog()
    await pickOption('请选择项目', '项目A')
    await pickOption('请选择需求', '需求一')
    selectTaskType('dev')
    fireEvent.change(screen.getByPlaceholderText('留空默认取需求标题'), {
      target: { value: '统一表单标题' },
    })
    fireEvent.change(screen.getByPlaceholderText('本次要让 AI 做什么?'), {
      target: { value: '统一表单描述' },
    })
    fireEvent.click(screen.getByRole('button', { name: '创建' }))

    await waitFor(() => expect(createTask).toHaveBeenCalledTimes(1))
    const [reqId, payload] = vi.mocked(createTask).mock.calls[0]
    expect(reqId).toBe('r1')
    expect(payload).toMatchObject({ type: 'dev', title: '统一表单标题', description: '统一表单描述' })

    // 成功后关闭对话框并跳转任务详情页
    await waitFor(() =>
      expect(screen.getByTestId('location-probe').textContent).toBe('/tasks/t-123'),
    )
    expect(onClose).toHaveBeenCalled()
  })

  it('5. 点击取消按钮:触发 onClose,父组件置 open=false 后对话框从 DOM 移除', () => {
    const { onClose, rerenderOpen } = renderDialog()
    fireEvent.click(screen.getByRole('button', { name: '取消' }))
    expect(onClose).toHaveBeenCalledTimes(1)
    rerenderOpen(false)
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  it('6. 接口返回错误:显示「创建失败:…」Alert,对话框不关闭、表单保持', async () => {
    const { onClose } = renderDialog()
    vi.mocked(createTask).mockRejectedValueOnce(new Error('并发超限'))
    await pickOption('请选择项目', '项目A')
    await pickOption('请选择需求', '需求一')
    selectTaskType('dev')
    fireEvent.change(screen.getByPlaceholderText('留空默认取需求标题'), {
      target: { value: '统一表单标题' },
    })
    fireEvent.click(screen.getByRole('button', { name: '创建' }))

    expect(await screen.findByText(/创建失败/)).toBeTruthy()
    expect(onClose).not.toHaveBeenCalled()
    // 表单保持:已填标题不丢失
    expect((screen.getByPlaceholderText('留空默认取需求标题') as HTMLInputElement).value).toBe(
      '统一表单标题',
    )
  })
})
