/**
 * SkillsManagement — Skills 管理 Tab(R17)
 * - 标题"Skills 管理" + "从市场安装"(secondary) + "上传自定义"(primary)按钮(viewer 隐藏)
 * - 已安装 Table:Skill 名/描述/来源徽章(platform=secondary/project=primary)/安装人/安装时间/操作[查看/卸载]
 * - 市场安装对话框 + 上传对话框 + Skill 详情对话框
 */

import { useState } from 'react'
import { Upload, Store, Eye, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { Alert } from '@/components/ui/Alert'
import {
  Table, TableHeader, TableBody, TableRow, TableHead, TableCell,
} from '@/components/ui/Table'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
  DialogFooter,
} from '@/components/ui/Dialog'
import {
  useInstalledSkills, useSkillMarket, useInstallSkill, useUploadSkill,
  useUninstallSkill, getSkillErrorMessage,
} from '@/api/skills'
import type { Skill } from '@/api/skills'
import { useAuthStore } from '@/stores/authStore'
import { useProjectMembers } from '@/api/projects'

interface SkillsManagementProps {
  projectId: string
}

export function SkillsManagement({ projectId }: SkillsManagementProps) {
  const { data: installed, isLoading } = useInstalledSkills(projectId)
  const { data: marketSkills } = useSkillMarket()
  const installSkill = useInstallSkill(projectId)
  const uploadSkill = useUploadSkill(projectId)
  const uninstallSkill = useUninstallSkill(projectId)
  const { data: membersData } = useProjectMembers(projectId)
  const user = useAuthStore(state => state.user)
  const currentMember = membersData?.items.find(m => m.user_id === user?.user_id)
  const isViewer = currentMember?.role === 'viewer'

  const [marketOpen, setMarketOpen] = useState(false)
  const [uploadOpen, setUploadOpen] = useState(false)
  const [detailSkill, setDetailSkill] = useState<Skill | null>(null)
  const [uninstallTarget, setUninstallTarget] = useState<Skill | null>(null)
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null)

  function handleInstall(skillId: string) {
    installSkill.mutate(skillId, {
      onSuccess: () => {
        setMessage({ type: 'success', text: '安装成功' })
        setMarketOpen(false)
      },
      onError: (err) => setMessage({ type: 'error', text: getSkillErrorMessage(err) }),
    })
  }

  function handleUpload() {
    if (!selectedFile) return
    uploadSkill.mutate(selectedFile, {
      onSuccess: () => {
        setMessage({ type: 'success', text: '上传成功' })
        setUploadOpen(false)
        setSelectedFile(null)
      },
      onError: (err) => setMessage({ type: 'error', text: getSkillErrorMessage(err) }),
    })
  }

  function handleUninstall() {
    if (!uninstallTarget) return
    uninstallSkill.mutate(uninstallTarget.skill_id, {
      onSuccess: () => {
        setMessage({ type: 'success', text: '卸载成功' })
        setUninstallTarget(null)
      },
      onError: (err) => setMessage({ type: 'error', text: getSkillErrorMessage(err) }),
    })
  }

  function formatFileSize(bytes: number): string {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  }

  function formatDate(dateStr: string): string {
    try {
      return new Date(dateStr).toLocaleString('zh-CN')
    } catch {
      return dateStr
    }
  }

  return (
    <div>
      {/* 页头 */}
      <div className="page-head">
        <div>
          <h1 className="flex items-center gap-2"><Store size={18} /> Skills 管理</h1>
          <div className="sub">项目已安装的 Skills:查看、卸载与新增</div>
        </div>
        {!isViewer && (
          <div className="acts">
            <Button variant="outline" size="sm" onClick={() => setMarketOpen(true)}>
              <Store className="w-4 h-4 mr-1" />
              从市场安装
            </Button>
            <Button size="sm" onClick={() => setUploadOpen(true)}>
              <Upload className="w-4 h-4 mr-1" />
              上传自定义
            </Button>
          </div>
        )}
      </div>

      {/* 已安装列表 */}
      {isLoading ? (
        <div className="text-text-muted py-8">加载中...</div>
      ) : (
        <div className="card">
        <div className="scrollx">
        <Table className="tbl">
          <TableHeader>
            <TableRow>
              <TableHead>Skill 名</TableHead>
              <TableHead>描述</TableHead>
              <TableHead>来源</TableHead>
              <TableHead>安装人</TableHead>
              <TableHead>安装时间</TableHead>
              <TableHead className="w-[150px]">操作</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {(installed ?? []).map(skill => (
              <TableRow key={skill.skill_id}>
                <TableCell className="font-medium text-text">{skill.name}</TableCell>
                <TableCell className="text-text-muted">{skill.description}</TableCell>
                <TableCell>
                  <Badge variant={skill.scope === 'platform' ? 'secondary' : 'default'}>
                    {skill.scope === 'platform' ? '平台' : '项目'}
                  </Badge>
                </TableCell>
                <TableCell className="text-text-muted">
                  {skill.installed_by?.username ?? '-'}
                </TableCell>
                <TableCell className="text-text-muted">
                  {skill.installed_at ? formatDate(skill.installed_at) : '-'}
                </TableCell>
                <TableCell>
                  <div className="flex gap-2">
                    <Button variant="ghost" size="sm" onClick={() => setDetailSkill(skill)}>
                      <Eye className="w-4 h-4 mr-1" />
                      查看
                    </Button>
                    {!isViewer && (
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setUninstallTarget(skill)}
                        className="text-error hover:text-error"
                      >
                        <Trash2 className="w-4 h-4 mr-1" />
                        卸载
                      </Button>
                    )}
                  </div>
                </TableCell>
              </TableRow>
            ))}
            {(installed ?? []).length === 0 && (
              <TableRow>
                <TableCell colSpan={6} className="text-center text-text-muted py-8">
                  暂无已安装的 Skills
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
        </div>
        </div>
      )}

      {message && (
        <Alert variant={message.type === 'success' ? 'success' : 'error'}>
          {message.text}
        </Alert>
      )}

      {/* 市场安装对话框 */}
      <Dialog open={marketOpen} onOpenChange={setMarketOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>从市场安装</DialogTitle>
            <DialogDescription>选择平台级 Skill 安装到本项目</DialogDescription>
          </DialogHeader>
          <div className="space-y-2 max-h-[400px] overflow-y-auto">
            {(marketSkills ?? []).map(skill => (
              <div
                key={skill.skill_id}
                className="flex items-center justify-between p-3 border border-border rounded-md"
              >
                <div className="flex-1">
                  <div className="font-medium text-text">{skill.name}</div>
                  <div className="text-sm text-text-muted mt-1">{skill.description}</div>
                </div>
                <Button
                  size="sm"
                  onClick={() => handleInstall(skill.skill_id)}
                  disabled={installSkill.isPending}
                >
                  安装
                </Button>
              </div>
            ))}
            {(marketSkills ?? []).length === 0 && (
              <p className="text-center text-text-muted py-4">暂无可安装的 Skills</p>
            )}
          </div>
        </DialogContent>
      </Dialog>

      {/* 上传自定义对话框 */}
      <Dialog open={uploadOpen} onOpenChange={setUploadOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>上传自定义 Skill</DialogTitle>
            <DialogDescription>上传 .md 文件,需包含 YAML frontmatter(name/description)</DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <input
              type="file"
              accept=".md"
              onChange={(e) => setSelectedFile(e.target.files?.[0] ?? null)}
              className="block w-full text-sm text-text-muted file:mr-4 file:py-2 file:px-4 file:rounded-md file:border-0 file:text-sm file:font-medium file:bg-primary/10 file:text-primary hover:file:bg-primary/20"
            />
            {selectedFile && (
              <p className="text-sm text-text-muted">
                已选择: {selectedFile.name} ({formatFileSize(selectedFile.size)})
              </p>
            )}
          </div>
          <DialogFooter>
            <Button variant="outline" size="sm" onClick={() => setUploadOpen(false)}>
              取消
            </Button>
            <Button
              size="sm"
              onClick={handleUpload}
              disabled={!selectedFile || uploadSkill.isPending}
            >
              上传
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Skill 详情对话框 */}
      <Dialog open={!!detailSkill} onOpenChange={(open) => !open && setDetailSkill(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Skill 详情</DialogTitle>
            <DialogDescription>{detailSkill?.name}</DialogDescription>
          </DialogHeader>
          <pre className="font-mono text-xs bg-surface-strong p-4 rounded-md overflow-auto max-h-[400px]">
            {detailSkill?.content ?? '无内容'}
          </pre>
        </DialogContent>
      </Dialog>

      {/* 卸载确认对话框 */}
      <Dialog open={!!uninstallTarget} onOpenChange={(open) => !open && setUninstallTarget(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>确认卸载</DialogTitle>
            <DialogDescription>
              确定要卸载 Skill "{uninstallTarget?.name}" 吗?
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" size="sm" onClick={() => setUninstallTarget(null)}>
              取消
            </Button>
            <Button
              size="sm"
              variant="primary"
              className="bg-error hover:bg-error/90"
              onClick={handleUninstall}
              disabled={uninstallSkill.isPending}
            >
              卸载
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
