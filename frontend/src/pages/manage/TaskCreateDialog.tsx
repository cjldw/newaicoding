/**
 * TaskCreateDialog — 统一任务创建表单
 * R1:仅搭空壳(Dialog + 表单字段占位),统一 /manage/tasks 页头"新建任务"按钮的创建入口
 * 表单结构由后续需求点完善:
 * - R2   任务类型选择器(dev/test/release,注册机制)
 * - R3.2 可搜索的项目/需求选择器(后端搜索,参考 RelatedUserSelect)
 * - R4   统一表单结构(公共字段:项目/需求/类型/标题/描述)
 * - R5   类型特有字段插槽(dev 无 / test 提示文案 / release 部署端口)
 */
import { useState } from 'react'
import { Plus } from 'lucide-react'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/Dialog'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Textarea } from '@/components/ui/Textarea'
import { Select } from '@/components/ui/Select'
import type { TaskType } from '@/api/tasks'

/** R2:任务类型选项(dev/test/release,requirement 不走创建表单)— 文案照 R2 文案清单 */
const TASK_TYPE_OPTIONS: Array<{ label: string; value: Exclude<TaskType, 'requirement'> }> = [
  { label: '开发', value: 'dev' },
  { label: '测试', value: 'test' },
  { label: '发布', value: 'release' },
]

interface TaskCreateDialogProps {
  open: boolean
  onClose: () => void
}

export function TaskCreateDialog({ open, onClose }: TaskCreateDialogProps) {
  // R2:任务类型(空串 = 未选择,显示 placeholder)
  const [type, setType] = useState<Exclude<TaskType, 'requirement'> | ''>('')

  /** R2:切换类型时清空类型特有字段(公共字段保留);字段本体由 R5 插槽实现 */
  const handleTypeChange = (next: Exclude<TaskType, 'requirement'>) => {
    if (next === type) return
    setType(next)
    // TODO(R5):清空类型特有字段(deploy_port / test 提示文案等)
  }

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) onClose() }}>
      <DialogContent onClose={onClose}>
        <DialogHeader>
          {/* 文案照 R1 文案清单:对话框标题 "新建任务 · 快速创建" */}
          <DialogTitle className="flex items-center gap-2"><Plus size={16} /> 新建任务 · 快速创建</DialogTitle>
        </DialogHeader>

        {/* TODO(R4):以下为公共字段占位,R2/R3.2/R4/R5 逐一替换为真实表单 */}
        <div className="flex flex-col gap-4 py-2">
          <div className="flex flex-col gap-1.5">
            <label className="block text-sm font-medium text-text">
              项目 <span className="text-red-fg">*</span>
            </label>
            <Input disabled placeholder="R3.2 实现:可搜索项目选择器" />
          </div>
          <div className="flex flex-col gap-1.5">
            <label className="block text-sm font-medium text-text">
              需求 <span className="text-red-fg">*</span>
            </label>
            <Input disabled placeholder="R3.2 实现:可搜索需求选择器(跟随所选项目)" />
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
