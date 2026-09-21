/**
 * SkillsMarket — 平台 Skills 管理(超管,R17)
 * - 标题"Skills 市场" + "新建 Skill"按钮
 * - Table:名称/描述/创建人/创建时间/操作[编辑/删除]
 * - 新建/编辑对话框(名称 Input + 描述 Input + 内容 Textarea)
 * - 删除确认对话框
 */

import { useState } from 'react'
import { Plus, Pencil, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Label } from '@/components/ui/Label'
import { Textarea } from '@/components/ui/Textarea'
import { Alert } from '@/components/ui/Alert'
import {
  Table, TableHeader, TableBody, TableRow, TableHead, TableCell,
} from '@/components/ui/Table'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
  DialogFooter,
} from '@/components/ui/Dialog'
import {
  useAdminSkills, useCreateAdminSkill, useUpdateAdminSkill,
  useDeleteAdminSkill, getSkillErrorMessage,
} from '@/api/skills'
import type { Skill } from '@/api/skills'

export function SkillsMarket() {
  const { data: skills, isLoading } = useAdminSkills()
  const createSkill = useCreateAdminSkill()
  const updateSkill = useUpdateAdminSkill()
  const deleteSkill = useDeleteAdminSkill()

  const [dialogOpen, setDialogOpen] = useState(false)
  const [editing, setEditing] = useState<Skill | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<Skill | null>(null)
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null)

  const [formData, setFormData] = useState({
    name: '',
    description: '',
    content: '',
  })

  function resetForm() {
    setFormData({ name: '', description: '', content: '' })
  }

  function handleCreate() {
    resetForm()
    setEditing(null)
    setDialogOpen(true)
  }

  function handleEdit(skill: Skill) {
    resetForm()
    setEditing(skill)
    setFormData({
      name: skill.name,
      description: skill.description,
      content: skill.content ?? '',
    })
    setDialogOpen(true)
  }

  async function handleSubmit() {
    if (!formData.name.trim() || !formData.description.trim()) {
      setMessage({ type: 'error', text: '名称和描述不能为空' })
      return
    }
    try {
      if (editing) {
        await updateSkill.mutateAsync({
          id: editing.skill_id,
          data: formData,
        })
        setMessage({ type: 'success', text: '更新成功' })
      } else {
        await createSkill.mutateAsync(formData)
        setMessage({ type: 'success', text: '创建成功' })
      }
      setDialogOpen(false)
      resetForm()
    } catch (e) {
      setMessage({ type: 'error', text: getSkillErrorMessage(e) })
    }
  }

  async function handleDelete() {
    if (!deleteTarget) return
    try {
      await deleteSkill.mutateAsync(deleteTarget.skill_id)
      setMessage({ type: 'success', text: '删除成功' })
      setDeleteTarget(null)
    } catch (e) {
      setMessage({ type: 'error', text: getSkillErrorMessage(e) })
    }
  }

  function formatDate(dateStr: string): string {
    try {
      return new Date(dateStr).toLocaleString('zh-CN')
    } catch {
      return dateStr
    }
  }

  return (
    <div className="container mx-auto px-4 py-6 space-y-4">
      {/* 操作栏 */}
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-text">Skills 市场</h1>
        <Button size="sm" onClick={handleCreate}>
          <Plus className="w-4 h-4 mr-2" />
          新建 Skill
        </Button>
      </div>

      {message && (
        <Alert variant={message.type}>{message.text}</Alert>
      )}

      {/* 列表 */}
      {isLoading ? (
        <div className="text-text-muted py-8">加载中...</div>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>名称</TableHead>
              <TableHead>描述</TableHead>
              <TableHead>创建人</TableHead>
              <TableHead>创建时间</TableHead>
              <TableHead className="w-[150px]">操作</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {(skills ?? []).map(skill => (
              <TableRow key={skill.skill_id}>
                <TableCell className="font-medium text-text">{skill.name}</TableCell>
                <TableCell className="text-text-muted">{skill.description}</TableCell>
                <TableCell className="text-text-muted">
                  {skill.created_by?.username ?? '-'}
                </TableCell>
                <TableCell className="text-text-muted">
                  {skill.created_at ? formatDate(skill.created_at) : '-'}
                </TableCell>
                <TableCell>
                  <div className="flex gap-2">
                    <Button variant="ghost" size="sm" onClick={() => handleEdit(skill)}>
                      <Pencil className="w-4 h-4 mr-1" />
                      编辑
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setDeleteTarget(skill)}
                      className="text-error hover:text-error"
                    >
                      <Trash2 className="w-4 h-4 mr-1" />
                      删除
                    </Button>
                  </div>
                </TableCell>
              </TableRow>
            ))}
            {(skills ?? []).length === 0 && (
              <TableRow>
                <TableCell colSpan={5} className="text-center text-text-muted py-8">
                  暂无平台 Skills
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      )}

      {/* 新建/编辑对话框 */}
      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="max-w-[560px]">
          <DialogHeader>
            <DialogTitle>{editing ? '编辑 Skill' : '新建 Skill'}</DialogTitle>
            <DialogDescription>
              {editing ? '修改平台 Skill 信息' : '创建新的平台级 Skill'}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div className="space-y-1">
              <Label>名称</Label>
              <Input
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                placeholder="如:code-review"
              />
            </div>
            <div className="space-y-1">
              <Label>描述</Label>
              <Input
                value={formData.description}
                onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                placeholder="一句话说明 Skill 的用途"
              />
            </div>
            <div className="space-y-1">
              <Label>内容</Label>
              <Textarea
                value={formData.content}
                onChange={(e) => setFormData({ ...formData, content: e.target.value })}
                rows={10}
                className="font-mono text-sm"
                placeholder="# Skill 内容(Markdown,需包含 YAML frontmatter)"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" size="sm" onClick={() => setDialogOpen(false)}>
              取消
            </Button>
            <Button
              size="sm"
              onClick={handleSubmit}
              disabled={createSkill.isPending || updateSkill.isPending}
            >
              {editing ? '保存' : '创建'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* 删除确认对话框 */}
      <Dialog open={!!deleteTarget} onOpenChange={() => setDeleteTarget(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>确认删除</DialogTitle>
            <DialogDescription>
              确定要删除 Skill "{deleteTarget?.name}" 吗?此操作不可恢复。
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" size="sm" onClick={() => setDeleteTarget(null)}>
              取消
            </Button>
            <Button
              size="sm"
              variant="primary"
              className="bg-error hover:bg-error/90"
              onClick={handleDelete}
              disabled={deleteSkill.isPending}
            >
              删除
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
