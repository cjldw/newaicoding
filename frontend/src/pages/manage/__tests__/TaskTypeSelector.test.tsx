/**
 * R2(任务类型选择器)失败测试(QA Red)
 * 规格来源:docs/20260927_任务新建菜单优化/DEVPLAN/R2.md
 *
 * 验证统一创建表单(TaskCreateDialog)内:
 *   1. 类型选择器显示 开发(dev)/测试(test)/发布(release) 三个选项,placeholder「请选择任务类型」
 *   2. 选择类型后表单 type 字段更新(选择器受控值变为 dev/test/release)
 *   3. 切换类型时清空类型特有字段(release 部署端口:填值 → 切走 → 切回,值必须为空)
 *
 * 运行方式(测试栈为 QA 临时安装,--no-save 不改动 package.json):
 *   cd frontend && npm install --no-save vitest jsdom @testing-library/react @testing-library/dom
 *   npx vitest run src/pages/manage/__tests__/TaskTypeSelector.test.tsx
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

function renderOpenDialog() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <TasksManage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
  fireEvent.click(screen.getByRole('button', { name: '新建任务' }))
  // R4 文案清单:对话框标题「新建任务」(heading 定位,与页头同名按钮区分)
  return screen.findByRole('heading', { name: '新建任务' })
}

/** 定位任务类型选择器:含「请选择任务类型」占位或 开发/测试/发布 选项的原生 <select> */
function getTypeSelect(): HTMLSelectElement {
  const selects = Array.from(document.querySelectorAll('select'))
  const hit = selects.find(
    (s) =>
      /请选择任务类型/.test(s.textContent ?? '') ||
      Array.from(s.options).some((o) => ['开发', '测试', '发布'].includes(o.textContent ?? '')),
  )
  if (!hit) {
    throw new Error(
      '未找到任务类型选择器(期望原生 <select>:placeholder「请选择任务类型」+ 开发/测试/发布 选项)',
    )
  }
  return hit
}

/** 定位 release 类型特有字段:部署端口输入框(R5 文案清单:placeholder 10000-10099) */
function queryDeployPortInput(): HTMLInputElement | null {
  return (
    screen.queryByPlaceholderText('10000-10099') ??
    (screen.queryByLabelText('部署端口') as HTMLInputElement | null)
  )
}

describe('R2 任务类型选择器(TaskCreateDialog)', () => {
  it('类型选择器显示开发/测试/发布三个选项,默认 placeholder「请选择任务类型」', async () => {
    await renderOpenDialog()
    const select = getTypeSelect()
    // placeholder option:存在、disabled、值为空
    const ph = Array.from(select.options).find((o) => o.textContent === '请选择任务类型')
    expect(ph, '缺少 placeholder 选项「请选择任务类型」').toBeTruthy()
    expect(ph!.disabled).toBe(true)
    expect(ph!.value).toBe('')
    expect(select.value).toBe('') // 默认未选中,显示 placeholder
    // 三个类型选项:文案与枚举值一一对应(开发=dev / 测试=test / 发布=release)
    const opts = new Map(
      Array.from(select.options)
        .filter((o) => !o.disabled)
        .map((o) => [o.textContent, o.value]),
    )
    expect(opts.get('开发')).toBe('dev')
    expect(opts.get('测试')).toBe('test')
    expect(opts.get('发布')).toBe('release')
    expect(opts.size).toBe(3)
  })

  it('选择类型后更新表单 type 字段(dev/test/release)', async () => {
    await renderOpenDialog()
    const select = getTypeSelect()
    for (const [label, value] of [
      ['开发', 'dev'],
      ['测试', 'test'],
      ['发布', 'release'],
    ] as const) {
      fireEvent.change(select, { target: { value } })
      // 受控绑定:选择后选择器值(即表单 type 字段)必须稳定为对应枚举值
      expect(select.value, `选择「${label}」后 type 应为 '${value}'`).toBe(value)
    }
  })

  it('切换类型时清空类型特有字段(部署端口 填值→切走→切回 为空)', async () => {
    await renderOpenDialog()
    const select = getTypeSelect()
    // release:显示部署端口输入框并填值
    fireEvent.change(select, { target: { value: 'release' } })
    const port = queryDeployPortInput()
    expect(port, '选择「发布」后应显示部署端口输入框(placeholder 10000-10099)').not.toBeNull()
    fireEvent.change(port!, { target: { value: '10001' } })
    expect(port!.value).toBe('10001')
    // 切到 test:类型特有字段被清空(输入框卸载,或保留但值为空)
    fireEvent.change(select, { target: { value: 'test' } })
    const portAfterSwitch = queryDeployPortInput()
    if (portAfterSwitch) expect(portAfterSwitch.value).toBe('')
    // 切回 release:部署端口必须为空,不得残留上一次填写的 10001
    fireEvent.change(select, { target: { value: 'release' } })
    const portBack = queryDeployPortInput()
    expect(portBack, '切回「发布」后应重新显示部署端口输入框').not.toBeNull()
    expect(portBack!.value).toBe('')
  })
})
