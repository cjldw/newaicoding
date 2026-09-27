/**
 * RequirementEditDialog — 需求编辑弹窗(R5.F1:自 manage/DimensionPage 内联版抽为共享组件)
 * manage 四维需求行(/manage/requirements)与项目详情页需求列表(/projects/{pid})共用
 * 语义要点(与 R2.F1 口径一致):
 * - 回填全部可改字段;不含项目选择器 / 需求分支 / PRD 路径(创建后绑定,不可修改)
 * - 提交走 requirementsApi.update(PATCH),恒传 delivery_date(PATCH 缺省即置 NULL,防静默清空)
 * - 评审中:后端对 title/description 一律 400 → 前置禁用输入,提交不带这两字段
 * - 成功后失效四维列表(['dimension'])、需求详情、项目维需求列表(['requirements'] 前缀)
 */
import { useEffect, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Pencil, Plus, Trash2 } from 'lucide-react'
import { useProjectMembers } from '@/api/projects'
import {
  requirementsApi, useRequirementDetail,
  type UpdateRequirementRequest, type RequirementPriority,
} from '@/api/requirements'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/Dialog'
import { Alert } from '@/components/ui/Alert'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Textarea } from '@/components/ui/Textarea'
import { Select } from '@/components/ui/Select'
import { RelatedUserSelect } from './RelatedUserSelect'

// 原型链接约束(与创建弹窗同口径:label ≤20 可空 / url http(s):// 开头 / 最多 10 条)
const MAX_PROTOTYPE_LINKS = 10
const PROTOTYPE_URL_PATTERN = /^https?:\/\//i
// 表单行形态(label 空串;提交时非空才带,空行整行剔除)
interface PrototypeLinkDraft { label: string; url: string }

function isPrototypeLinkRowError(row: PrototypeLinkDraft): boolean {
  const url = row.url.trim()
  if (url !== '') return !PROTOTYPE_URL_PATTERN.test(url)
  return row.label.trim() !== '' // 有标签无 URL = 半填行,同样拦截
}

// 空表单(关弹重置用;useState 惰性初始化需工厂,引用类型字段不能共享同一对象)
function emptyRequirementForm() {
  return {
    title: '',
    background: '',
    description: '',
    acceptance_criteria: '',
    priority: 'medium' as RequirementPriority,
    req_branch: '',
    delivery_date: '', // input[type=date] 原生值 YYYY-MM-DD;空串=不设置
    related_user_ids: [] as string[], // 关联用户(项目成员多选)
    prototype_links: [] as PrototypeLinkDraft[], // 原型链接(标签可选 + URL 必填)
  }
}

interface RequirementEditDialogProps {
  reqId: string
  /** 归属项目 id(关联用户候选 = 该项目成员;manage 维传 item.project.project_id,项目详情页传路由 pid) */
  projectId: string
  onClose: () => void
}

export function RequirementEditDialog({ reqId, projectId, onClose }: RequirementEditDialogProps) {
  const queryClient = useQueryClient()
  const [formData, setFormData] = useState(emptyRequirementForm)
  const [errorMsg, setErrorMsg] = useState<string | null>(null)
  // 详情到达只回填一次(refetch 不覆盖编辑中表单)
  const [filledReqId, setFilledReqId] = useState('')

  const { data: detail } = useRequirementDetail(reqId)
  // 关联用户候选 = 所属项目成员全量(与创建弹窗同源)
  const { data: membersData } = useProjectMembers(projectId)
  const members = membersData?.items ?? []
  const reviewing = detail?.status === 'reviewing'

  useEffect(() => {
    if (detail && detail.req_id !== filledReqId) {
      setFilledReqId(detail.req_id)
      setFormData({
        ...emptyRequirementForm(),
        title: detail.title,
        background: detail.background || '',
        description: detail.description || '',
        acceptance_criteria: detail.acceptance_criteria || '',
        priority: detail.priority,
        delivery_date: detail.delivery_date || '',
        related_user_ids: detail.related_user_ids ? [...detail.related_user_ids] : [],
        prototype_links: (detail.prototype_links || []).map((l) => ({ label: l.label || '', url: l.url })),
      })
    }
  }, [detail, filledReqId])

  // 原型链接行操作(追加/删除/编辑,与创建弹窗同逻辑)
  function addPrototypeLink() {
    setFormData((f) => ({
      ...f,
      prototype_links: [...f.prototype_links, { label: '', url: '' }],
    }))
  }
  function removePrototypeLink(idx: number) {
    setFormData((f) => ({
      ...f,
      prototype_links: f.prototype_links.filter((_, i) => i !== idx),
    }))
  }
  function updatePrototypeLink(idx: number, patch: Partial<PrototypeLinkDraft>) {
    setFormData((f) => ({
      ...f,
      prototype_links: f.prototype_links.map((row, i) => (i === idx ? { ...row, ...patch } : row)),
    }))
  }

  const close = () => {
    setFormData(emptyRequirementForm())
    setFilledReqId('')
    setErrorMsg(null)
    onClose()
  }

  const mutation = useMutation({
    mutationFn: async () => {
      const payload: UpdateRequirementRequest = {
        background: formData.background.trim(),
        acceptance_criteria: formData.acceptance_criteria.trim(),
        priority: formData.priority,
        // 恒传:PATCH 缺省 delivery_date 即置 NULL,不传会静默清空交付时间
        delivery_date: formData.delivery_date || null,
        related_user_ids: formData.related_user_ids, // 空数组照传(全量覆盖口径)
        prototype_links: formData.prototype_links
          .filter((row) => row.label.trim() !== '' || row.url.trim() !== '')
          .map((row) => ({
            label: row.label.trim() || null,
            url: row.url.trim(),
          })),
      }
      if (reviewing) {
        // 评审中:后端对 title/description 一律 400(值未变也拒),缺省 = 不动
      } else {
        payload.title = formData.title.trim()
        payload.description = formData.description.trim()
      }
      return requirementsApi.update(reqId, payload).then((r) => r.data)
    },
    onSuccess: () => {
      // 四维列表 + 需求详情 + 项目维需求列表(['requirements'] 前缀,两页共用兜全)
      queryClient.invalidateQueries({ queryKey: ['dimension'] })
      queryClient.invalidateQueries({ queryKey: ['requirement', reqId] })
      queryClient.invalidateQueries({ queryKey: ['requirements'] })
      close()
    },
    onError: (err: Error) => {
      setErrorMsg(err?.message || '保存失败')
    },
  })

  function handleSubmit() {
    if (!formData.title.trim() || !formData.description.trim()) {
      setErrorMsg('标题和描述为必填项')
      return
    }
    // URL 行内校验(与创建弹窗同口径)
    if (formData.prototype_links.some(isPrototypeLinkRowError)) {
      setErrorMsg('URL 需以 http(s):// 开头')
      return
    }
    setErrorMsg(null)
    mutation.mutate()
  }

  return (
    <Dialog open onOpenChange={(o) => { if (!o) close() }}>
      <DialogContent onClose={close}>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2"><Pencil size={16} /> 编辑需求</DialogTitle>
        </DialogHeader>

        {errorMsg && <Alert variant="error" onClose={() => setErrorMsg(null)}>{errorMsg}</Alert>}
        {!detail && <div className="hint">加载需求详情...</div>}

        <div className="flex flex-col gap-4 py-2">
          <div className="flex flex-col gap-1.5">
            <label className="block text-sm font-medium text-text">
              标题 <span className="text-red-fg">*</span>
            </label>
            <Input
              value={formData.title}
              onChange={(e) => setFormData({ ...formData, title: e.target.value })}
              maxLength={128}
              disabled={reviewing}
              placeholder="输入需求标题"
            />
            {/* 需求分支/PRD 路径创建后绑定,不可修改,编辑弹窗不出现 */}
            {reviewing && (
              <div className="hint">评审中需求不可修改标题与描述;如需调整请先结束评审</div>
            )}
          </div>
          <div className="flex flex-col gap-1.5">
            <label className="block text-sm font-medium text-text">背景</label>
            <Textarea
              value={formData.background}
              onChange={(e) => setFormData({ ...formData, background: e.target.value })}
              placeholder="需求背景(可选)"
              rows={2}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <label className="block text-sm font-medium text-text">
              描述 <span className="text-red-fg">*</span>
            </label>
            <Textarea
              value={formData.description}
              onChange={(e) => setFormData({ ...formData, description: e.target.value })}
              placeholder="详细描述需求内容"
              rows={3}
              disabled={reviewing}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <label className="block text-sm font-medium text-text">验收标准</label>
            <Textarea
              value={formData.acceptance_criteria}
              onChange={(e) => setFormData({ ...formData, acceptance_criteria: e.target.value })}
              placeholder="验收标准(可选)"
              rows={2}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <label className="block text-sm font-medium text-text">优先级</label>
            <Select
              value={formData.priority}
              onChange={(e) => setFormData({ ...formData, priority: (e.target.value as RequirementPriority) })}
              options={[
                { label: '低', value: 'low' },
                { label: '中', value: 'medium' },
                { label: '高', value: 'high' },
              ]}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <label className="block text-sm font-medium text-text">
              交付时间 <span className="text-xs font-normal text-text-muted">(可选)</span>
            </label>
            <Input
              type="date"
              value={formData.delivery_date}
              onChange={(e) => setFormData({ ...formData, delivery_date: e.target.value })}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <label className="block text-sm font-medium text-text">
              关联用户 <span className="text-xs font-normal text-text-muted">(可选)</span>
            </label>
            <RelatedUserSelect
              members={members}
              value={formData.related_user_ids}
              onChange={(ids) => setFormData({ ...formData, related_user_ids: ids })}
            />
          </div>
          {/* 原型链接行组(与创建弹窗同结构:标签可选 + URL 必填;≤10 条) */}
          <div className="flex flex-col gap-1.5">
            <label className="block text-sm font-medium text-text">
              原型链接 <span className="text-xs font-normal text-text-muted">(可选)</span>
            </label>
            <div className="space-y-2">
              {formData.prototype_links.map((row, idx) => {
                const rowError = isPrototypeLinkRowError(row)
                return (
                  <div key={idx} className="flex items-start gap-2">
                    <Input
                      value={row.label}
                      onChange={(e) => updatePrototypeLink(idx, { label: e.target.value })}
                      placeholder="链接标签(可选)"
                      maxLength={20}
                      className="w-40 shrink-0"
                      aria-label={`链接 ${idx + 1} 标签`}
                    />
                    <div className="flex-1 min-w-0">
                      <Input
                        value={row.url}
                        onChange={(e) => updatePrototypeLink(idx, { url: e.target.value })}
                        placeholder="URL"
                        className={rowError ? 'border-red-border' : undefined}
                        aria-label={`链接 ${idx + 1} URL`}
                      />
                      {rowError && (
                        <div className="mt-1 text-xs text-red-fg">URL 需以 http(s):// 开头</div>
                      )}
                    </div>
                    <button
                      type="button"
                      className="btn btn-sm btn-ghost icon-btn shrink-0"
                      title="删除"
                      aria-label={`删除链接 ${idx + 1}`}
                      onClick={() => removePrototypeLink(idx)}
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                )
              })}
            </div>
            <div className="mt-2 flex items-center gap-2">
              <Button
                variant="default"
                size="sm"
                onClick={addPrototypeLink}
                disabled={formData.prototype_links.length >= MAX_PROTOTYPE_LINKS}
              >
                <Plus className="w-3.5 h-3.5 mr-1" />
                添加链接
              </Button>
              {formData.prototype_links.length >= MAX_PROTOTYPE_LINKS && (
                <span className="text-xs text-text-muted">最多 10 条</span>
              )}
            </div>
          </div>
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={close}>取消</Button>
          <Button
            variant="primary"
            disabled={mutation.isPending || !detail}
            onClick={handleSubmit}
          >
            {mutation.isPending ? '保存中…' : '保存'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
