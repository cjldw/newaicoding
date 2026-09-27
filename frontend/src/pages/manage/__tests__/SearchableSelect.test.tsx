/**
 * R3.2(可搜索的项目与需求选择器)失败测试(QA Red)
 * 规格来源:docs/20260927_任务新建菜单优化/DEVPLAN/R3.2.md
 *
 * 覆盖完成判据(5 项):
 *   1. 项目选择器支持搜索,搜索走后端接口(searchProjects(q))
 *   2. 需求选择器支持搜索,搜索走后端接口(searchRequirements(projectId, q))
 *   3. 切换项目时清空已选需求
 *   4. 空态和无匹配时显示对应文案(暂无项目,请先创建项目 / 该项目暂无可选需求 / 无匹配结果)
 *   5. 搜索 debounce 300ms
 *
 * 测试对象:TaskCreateDialog(直接渲染,R3.2 应以 SearchableSelect 替换项目/需求占位 Input);
 * 文案定位全部取自 R3.2 文案清单(label 关联项目/关联需求、placeholder 等)。
 *
 * 运行方式(测试栈为 QA 临时安装,--no-save 不改动 package.json):
 *   cd frontend && npm install --no-save vitest jsdom @testing-library/react @testing-library/dom
 *   npx vitest run src/pages/manage/__tests__/SearchableSelect.test.tsx
 */
/** @vitest-environment jsdom */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import type { Mock } from 'vitest'
import { render, screen, fireEvent, cleanup, waitFor, act } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { TaskCreateDialog } from '../TaskCreateDialog'
// R3.2 规格要求的搜索 API 封装(实现前不存在,经 vi.mock 工厂替换后可安全引用)
import { searchProjects, useProjectList } from '@/api/projects'
import { searchRequirements, requirementsApi } from '@/api/requirements'

// vitest 未开 globals,RTL 自动清理不生效,手动逐测清 DOM(防跨测渲染叠加)
afterEach(cleanup)

// ---- 夹具 ----
const OWNER = { user_id: 'u1', username: 'alice', nickname: 'Alice' }
const PROJECTS = [
  {
    project_id: 'proj-alpha',
    name: '项目Alpha',
    slug: 'alpha',
    description: '',
    status: 'active' as const,
    owner: OWNER,
    repo_count: 0,
    req_count: 2,
    member_count: 1,
    created_at: '2026-01-01T00:00:00Z',
  },
  {
    project_id: 'proj-beta',
    name: '项目Beta',
    slug: 'beta',
    description: '',
    status: 'active' as const,
    owner: OWNER,
    repo_count: 0,
    req_count: 1,
    member_count: 1,
    created_at: '2026-01-02T00:00:00Z',
  },
]
// 项目 → 需求列表(需求搜索按 title 过滤)
const REQUIREMENTS: Record<string, Array<Record<string, unknown>>> = {
  'proj-alpha': [
    {
      req_id: 'req-1',
      title: '登录页需求',
      status: 'approved',
      priority: 'high',
      created_by: OWNER,
      created_at: '2026-01-03T00:00:00Z',
    },
    {
      req_id: 'req-2',
      title: '支付流程需求',
      status: 'draft',
      priority: 'medium',
      created_by: OWNER,
      created_at: '2026-01-04T00:00:00Z',
    },
  ],
  'proj-beta': [
    {
      req_id: 'req-3',
      title: 'Beta 专属需求',
      status: 'draft',
      priority: 'low',
      created_by: OWNER,
      created_at: '2026-01-05T00:00:00Z',
    },
  ],
}

/**
 * 响应形态:与真实接口封装契约一致 ——
 *   searchProjects(q): Promise<ProjectListItem[]>
 *   searchRequirements(projectId, q): Promise<RequirementListItem[]>
 * (均返回纯数组;useProjectList 为 react-query hook,返回 { data } 形态)
 */

/** useProjectList(react-query hook)用的 { data } 形态 */
function listOf(items: Array<Record<string, unknown>>) {
  return { data: { items, total: items.length, page: 1, page_size: 20 } }
}

function filterProjects(q?: string) {
  const k = (q ?? '').trim().toLowerCase()
  if (!k) return PROJECTS
  return PROJECTS.filter((p) => p.name.toLowerCase().includes(k))
}

function filterRequirements(projectId?: string, q?: string) {
  const all = [...(REQUIREMENTS[projectId ?? ''] ?? (projectId ? [] : Object.values(REQUIREMENTS).flat()))]
  const k = (q ?? '').trim().toLowerCase()
  if (!k) return all
  return all.filter((r) => String(r.title).toLowerCase().includes(k))
}

// ---- API 层打桩:searchProjects/searchRequirements 为 R3.2 规格规定的接口封装 ----
vi.mock('@/api/projects', () => ({
  useProjectList: vi.fn(),
  useProjectMembers: vi.fn(() => ({ data: { items: [] } })),
  searchProjects: vi.fn(),
  projectsApi: { list: vi.fn(), search: vi.fn() },
}))

vi.mock('@/api/requirements', () => ({
  requirementsApi: {
    list: vi.fn(),
    detail: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    branchPreview: vi.fn(),
  },
  searchRequirements: vi.fn(),
  useBranchPreview: vi.fn(() => ({ data: undefined })),
  useRequirementDetail: vi.fn(() => ({ data: undefined })),
  useRequirementList: vi.fn(() => ({ data: { items: [], total: 0 } })),
}))

const searchProjectsMock = searchProjects as unknown as Mock
const searchRequirementsMock = searchRequirements as unknown as Mock
const useProjectListMock = useProjectList as unknown as Mock
const reqListApiMock = requirementsApi.list as unknown as Mock

/** 恢复默认夹具(测试内切换空态/无匹配夹具后调用,避免污染后续断言) */
function restoreFixtures() {
  useProjectListMock.mockReturnValue(listOf(PROJECTS))
  searchProjectsMock.mockImplementation(async (q?: string) => filterProjects(q))
  reqListApiMock.mockImplementation(async (params?: { project_id?: string; q?: string }) =>
    filterRequirements(params?.project_id, params?.q),
  )
  searchRequirementsMock.mockImplementation(async (projectId?: string, q?: string) =>
    filterRequirements(projectId, q),
  )
}

beforeEach(() => {
  vi.clearAllMocks() // 清调用历史(判据5 按调用计数断言,防跨用例累积)
  restoreFixtures()
})

// ---- 渲染与定位辅助 ----
function renderDialog() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <TaskCreateDialog open onClose={() => {}} />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

/** 触发框定位:优先按文案文本(样板 RelatedUserSelect 为文本 span),兼容 placeholder 形态 */
function getTrigger(text: string, message: string): HTMLElement {
  const el = screen.queryByText(text) ?? screen.queryByPlaceholderText(text)
  expect(el, message).not.toBeNull()
  return el as HTMLElement
}

/** 展开项目搜索面板,返回面板内搜索框 */
function openProjectPanel(): HTMLElement {
  fireEvent.click(
    getTrigger('请选择项目', '缺少项目选择器触发框(文案「请选择项目」,R3.2 文案清单)。当前实现仍是 R1 占位 disabled Input,未接 SearchableSelect'),
  )
  const input = screen.queryByPlaceholderText('搜索项目(名称)')
  expect(input, '点击项目选择器后未展开搜索面板(缺少「搜索项目(名称)」搜索框)').not.toBeNull()
  return input as HTMLElement
}

/** 展开需求搜索面板,返回面板内搜索框 */
function openRequirementPanel(): HTMLElement {
  fireEvent.click(
    getTrigger('请选择需求', '缺少需求选择器触发框(文案「请选择需求」,R3.2 文案清单)'),
  )
  const input = screen.queryByPlaceholderText('搜索需求(标题/描述)')
  expect(input, '点击需求选择器后未展开搜索面板(缺少「搜索需求(标题/描述)」搜索框)').not.toBeNull()
  return input as HTMLElement
}

describe('R3.2 可搜索的项目与需求选择器(TaskCreateDialog)', () => {
  it('判据1 项目选择器:输入关键词 debounce 后走后端搜索接口并更新列表', async () => {
    renderDialog()
    // 文案清单:label 关联项目
    expect(screen.queryByText('关联项目'), '缺少「关联项目」label(仍为 R1 占位「项目」)').not.toBeNull()
    const input = openProjectPanel()
    // 展开面板即加载项目列表
    expect(await screen.findByText('项目Alpha'), '展开项目面板后未加载项目列表').not.toBeNull()
    // 输入关键词 → searchProjects(q) 后端搜索,列表更新为搜索结果(Beta 被过滤)
    fireEvent.change(input, { target: { value: 'Alpha' } })
    await waitFor(
      () => expect(screen.queryByText('项目Beta'), '搜索后列表未按后端结果更新(干扰项未被过滤)').toBeNull(),
      { timeout: 2000 },
    )
    expect(screen.queryByText('项目Alpha'), '搜索结果应保留匹配项').not.toBeNull()
    expect(
      searchProjectsMock,
      '项目搜索必须走后端接口封装 searchProjects(q) —— 规格接口契约 GET /api/projects?q={keyword}',
    ).toHaveBeenCalledWith('Alpha')
  })

  it('判据2 需求选择器:选中项目后输入关键词走后端搜索接口(携带 project_id)', async () => {
    renderDialog()
    // 文案清单:label 关联需求
    expect(screen.queryByText('关联需求'), '缺少「关联需求」label(仍为 R1 占位「需求」)').not.toBeNull()
    // 先选项目 Alpha
    openProjectPanel()
    fireEvent.click(await screen.findByText('项目Alpha'))
    // 展开需求面板,显示该项目需求列表
    const reqInput = openRequirementPanel()
    expect(await screen.findByText('登录页需求'), '展开需求面板后未加载该项目需求列表').not.toBeNull()
    // 输入关键词 → searchRequirements(projectId, q),列表更新(登录页需求被过滤)
    fireEvent.change(reqInput, { target: { value: '支付' } })
    await waitFor(
      () => expect(screen.queryByText('登录页需求'), '搜索后列表未按后端结果更新').toBeNull(),
      { timeout: 2000 },
    )
    expect(screen.queryByText('支付流程需求'), '搜索结果应保留匹配项').not.toBeNull()
    expect(
      searchRequirementsMock,
      '需求搜索必须走后端接口封装 searchRequirements(projectId, q),且携带所选项目 id —— 规格接口契约 GET /api/requirements?project_id={projectId}&q={keyword}',
    ).toHaveBeenCalledWith('proj-alpha', '支付')
  })

  it('判据3 切换项目时清空已选需求(需求选择器重置并加载新项目列表)', async () => {
    renderDialog()
    // 选项目 Alpha
    openProjectPanel()
    fireEvent.click(await screen.findByText('项目Alpha'))
    // 选需求「登录页需求」
    openRequirementPanel()
    fireEvent.click(await screen.findByText('登录页需求'))
    expect(
      screen.queryByText('请选择需求'),
      '选择需求后触发框应显示已选需求(placeholder 消失)',
    ).toBeNull()
    // 切换项目为 Beta
    fireEvent.click(screen.getByText('项目Alpha'))
    fireEvent.click(await screen.findByText('项目Beta'))
    // 已选需求被清空:触发框回到「请选择需求」,不再显示「登录页需求」
    expect(
      await screen.findByText('请选择需求'),
      '切换项目后未清空已选需求(触发框未重置为「请选择需求」)',
    ).not.toBeNull()
    expect(screen.queryByText('登录页需求'), '切换项目后已选需求残留').toBeNull()
    // 重置后重新展开需求面板:应加载 Beta 的需求列表
    openRequirementPanel()
    expect(await screen.findByText('Beta 专属需求'), '切换项目后需求面板未加载新项目需求').not.toBeNull()
    expect(screen.queryByText('登录页需求'), '新项目需求列表不应包含前一个项目的需求').toBeNull()
  })

  it('判据4 空态与无匹配显示对应文案(暂无项目 / 无匹配结果 / 该项目暂无可选需求)', async () => {
    // 阶段1:项目列表为空 → 「暂无项目,请先创建项目」
    useProjectListMock.mockReturnValue(listOf([]))
    searchProjectsMock.mockImplementation(async () => [])
    renderDialog()
    openProjectPanel()
    expect(
      await screen.findByText('暂无项目,请先创建项目'),
      '项目列表为空时未显示「暂无项目,请先创建项目」',
    ).not.toBeNull()
    cleanup()

    // 阶段2:有项目,搜索无匹配 → 「无匹配结果」(恢复默认夹具)
    restoreFixtures()
    renderDialog()
    const input = openProjectPanel()
    expect(await screen.findByText('项目Alpha')).not.toBeNull()
    fireEvent.change(input, { target: { value: '不存在的项目名' } })
    expect(await screen.findByText('无匹配结果', {}, { timeout: 2000 }), '搜索无匹配时未显示「无匹配结果」').not.toBeNull()
    cleanup()

    // 阶段3:选中项目后需求列表为空 → 「该项目暂无可选需求」(项目夹具恢复,需求夹具置空)
    restoreFixtures()
    searchRequirementsMock.mockImplementation(async () => [])
    reqListApiMock.mockImplementation(async () => [])
    renderDialog()
    openProjectPanel()
    fireEvent.click(await screen.findByText('项目Alpha'))
    openRequirementPanel()
    expect(
      await screen.findByText('该项目暂无可选需求'),
      '需求列表为空时未显示「该项目暂无可选需求」',
    ).not.toBeNull()
  })

  it('判据5 项目搜索 debounce 300ms:输入后立即不请求,299ms 仍未请求,300ms 恰好一次', async () => {
    vi.useFakeTimers()
    try {
      renderDialog()
      await act(async () => {}) // flush 挂起的微任务(面板/初始加载)
      const input = openProjectPanel()
      await act(async () => {}) // 初始列表加载 settle
      const callsFor = (q: string) => searchProjectsMock.mock.calls.filter((c) => c[0] === q).length
      fireEvent.change(input, { target: { value: 'Alpha' } })
      expect(callsFor('Alpha'), '输入后立即发起后端请求,未做 debounce').toBe(0)
      act(() => {
        vi.advanceTimersByTime(299)
      })
      await act(async () => {})
      expect(callsFor('Alpha'), '299ms 即发起请求,不满足 debounce 300ms 规格').toBe(0)
      act(() => {
        vi.advanceTimersByTime(1)
      })
      await act(async () => {})
      expect(callsFor('Alpha'), '300ms 后应恰好发起一次后端搜索请求').toBe(1)
    } finally {
      vi.useRealTimers()
    }
  })
})
