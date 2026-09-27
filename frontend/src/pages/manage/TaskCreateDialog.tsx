/**
 * TaskCreateDialog — 统一任务创建表单
 * R1:仅搭空壳(Dialog + 表单字段占位),统一 /manage/tasks 页头"新建任务"按钮的创建入口
 * 表单结构由后续需求点完善:
 * - R2   任务类型选择器(dev/test/release,注册机制)
 * - R3.2 可搜索的项目/需求选择器(后端搜索,参考 RelatedUserSelect)— 已实现
 * - R4   统一表单结构(公共字段:项目/需求/类型/标题/描述)
 * - R5   类型特有字段插槽(dev 无 / test 提示文案 / release 部署端口)
 */
import { useCallback, useState } from 'react'
import { Plus } from 'lucide-react'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/Dialog'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Textarea } from '@/components/ui/Textarea'
import { Select } from '@/components/ui/Select'
import { SearchableSelect } from '@/components/SearchableSelect'
import type { SearchableSelectOption } from '@/components/SearchableSelect'
import { searchProjects } from '@/api/projects'
import type { ProjectListItem } from '@/api/projects'
import { searchRequirements } from '@/api/requirements'
import type { RequirementListItem } from '@/api/requirements'
import type { TaskType } from '@/api/tasks'

/** R2:任务类型选项(dev/test/release,requirement 不走创建表单)— 文案照 R2 文案清单 */
const TASK_TYPE_OPTIONS: Array<{ label: string; value: Exclude<TaskType, 'requirement'> }> = [
  { label: '开发', value: 'dev' },
  { label: '测试', value: 'test' },
  { label: '发布', value: 'release' },
]

// R3.2:后端列表项 → 选择器选项(项目:名称+描述;需求:标题)
function toProjectOption(p: ProjectListItem): SearchableSelectOption {
  return { value: p.project_id, label: p.name, description: p.description || undefined }
}
function toRequirementOption(r: RequirementListItem): SearchableSelectOption {
  return { value: r.req_id, label: r.title }
}

interface TaskCreateDialogProps {
  open: boolean
  onClose: () => void
}

export function TaskCreateDialog({ open, onClose }: TaskCreateDialogProps) {
  // R2:任务类型(空串 = 未选择,显示 placeholder)
  const [type, setType] = useState<Exclude<TaskType, 'requirement'> | ''>('')
  // R3.2:项目/需求选择(保存完整 option,关闭面板后仍能回显 label)
  const [project, setProject] = useState<SearchableSelectOption | null>(null)
  const [requirement, setRequirement] = useState<SearchableSelectOption | null>(null)

  /** R2:切换类型时清空类型特有字段(公共字段保留);字段本体由 R5 插槽实现 */
  const handleTypeChange = (next: Exclude<TaskType, 'requirement'>) => {
    if (next === type) return
    setType(next)
    // TODO(R5):清空类型特有字段(deploy_port / test 提示文案等)
  }

  // R3.2:搜索走后端(debounce 300ms 在 SearchableSelect 内做)
  const fetchProjectOptions = useCallback(
    (q: string) => searchProjects(q).then((items) => items.map(toProjectOption)),
    [],
  )
  const fetchRequirementOptions = useCallback(
    (q: string) =>
      project
        ? searchRequirements(project.value, q).then((items) => items.map(toRequirementOption))
        : Promise.resolve([]),
    [project],
  )

  /** R3.2:切换项目时清空已选需求(需求选择器重置,重新加载该项目需求列表) */
  const handleProjectChange = (option: SearchableSelectOption) => {
    setProject(option)
    setRequirement(null)
  }

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) onClose() }}>
      <DialogContent onClose={onClose}>
        <DialogHeader>
          {/* 文案照 R1 文案清单:对话框标题 "新建任务 · 快速创建" */}
          <DialogTitle className="flex items-center gap-2"><Plus size={16} /> 新建任务 · 快速创建</DialogTitle>
        </DialogHeader>

        {/* TODO(R4):标题/描述与提交逻辑待 R4 实现;项目/需求选择器 R3.2 已落地 */}
        <div className="flex flex-col gap-4 py-2">
          {/* R3.2:可搜索项目选择器(文案照 R3.2 文案清单) */}
          <div className="flex flex-col gap-1.5">
            <label className="block text-sm font-medium text-text">
              关联项目 <span className="text-red-fg">*</span>
            </label>
            <SearchableSelect
              value={project}
              onChange={handleProjectChange}
              fetchOptions={fetchProjectOptions}
              placeholder="请选择项目"
              searchPlaceholder="搜索项目(名称)"
              emptyText="暂无项目,请先创建项目"
            />
          </div>
          {/* R3.2:可搜索需求选择器(跟随所选项目;未选项目时禁用) */}
          <div className="flex flex-col gap-1.5">
            <label className="block text-sm font-medium text-text">
              关联需求 <span className="text-red-fg">*</span>
            </label>
            <SearchableSelect
              value={requirement}
              onChange={setRequirement}
              fetchOptions={fetchRequirementOptions}
              disabled={!project}
              disabledPlaceholder="请先选择项目"
              placeholder="请选择需求"
              searchPlaceholder="搜索需求(标题/描述)"
              emptyText="该项目暂无可选需求"
            />
          </div>
          {/* R2:类型选择器(位于项目选择器之后),label + Select,flex-col gap-1.5 */}
          <div className="flex flex-col gap-1.5">
            <label className="block text-sm font-medium text-text">
              任务类型 <span className="text-red-fg">*</span>
            </label>
            <Select
              value={type}
              placeholder="请选择任务类型"
              options={TASK_TYPE_OPTIONS}
              onChange={(e) => handleTypeChange(e.target.value as Exclude<TaskType, 'requirement'>)}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <label className="block text-sm font-medium text-text">标题</label>
            <Input disabled placeholder="R4 实现:留空默认取需求标题(max 128)" />
          </div>
          <div className="flex flex-col gap-1.5">
            <label className="block text-sm font-medium text-text">描述</label>
            <Textarea disabled rows={3} placeholder="R4 实现:要让 AI 做什么(留空后端生成默认)" />
          </div>
          {/* TODO(R5):类型特有字段插槽区(按所选类型动态渲染) */}
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>取消</Button>
          {/* TODO(R4):提交逻辑 + 必填校验 + 成功后跳任务详情页并刷新列表 */}
          <Button variant="primary" disabled>创建</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
