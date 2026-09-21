/**
 * ModelConfigManagement — 模型配置 Tab(R13)
 * - 操作栏:右侧"新建配置"按钮
 * - 配置 Table:配置名(带 default 徽章)/Base URL/模型/API Key(打码)/状态/创建人/创建时间/操作
 * - 新建/编辑对话框 + 删除确认对话框
 * - viewer 权限:隐藏操作按钮,api_key 列显示 "-"
 */

import { useState } from 'react'
import { Eye, EyeOff, Plus } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { Badge } from '@/components/ui/Badge'
import { Input } from '@/components/ui/Input'
import { Label } from '@/components/ui/Label'
import { Alert } from '@/components/ui/Alert'
import {
  Table, TableHeader, TableBody, TableRow, TableHead, TableCell,
} from '@/components/ui/Table'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
  DialogFooter,
} from '@/components/ui/Dialog'
import {
  useModelConfigs, useCreateModelConfig, useUpdateModelConfig,
  useDeleteModelConfig, useTestModelConfig,
  getModelConfigErrorMessage,
} from '@/api/projects'
import type { ModelConfig } from '@/api/projects'
import { useAuthStore } from '@/stores/authStore'
import { useProjectMembers } from '@/api/projects'

interface ModelConfigManagementProps {
  projectId: string
}

export function ModelConfigManagement({ projectId }: ModelConfigManagementProps) {
  const { data, isLoading } = useModelConfigs(projectId)
  const { data: membersData } = useProjectMembers(projectId)
  const createConfig = useCreateModelConfig()
  const updateConfig = useUpdateModelConfig()
  const deleteConfig = useDeleteModelConfig()
  const testConfig = useTestModelConfig()

  const user = useAuthStore(state => state.user)
  const currentMember = membersData?.items.find(m => m.user_id === user?.user_id)
  const isViewer = currentMember?.role === 'viewer'

  const [dialogOpen, setDialogOpen] = useState(false)
  const [editingConfig, setEditingConfig] = useState<ModelConfig | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<ModelConfig | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)

  // 表单状态
  const [formData, setFormData] = useState({
    name: '',
    base_url: '',
    api_key: '',
    model: '',
    is_default: false,
    enabled: true,
  })
  const [showApiKey, setShowApiKey] = useState(false)
  const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null)
  const [testing, setTesting] = useState(false)

  const configs = data?.items ?? []
  const hasDefault = configs.some(c => c.is_default)

  function resetForm() {
    setFormData({
      name: '', base_url: '', api_key: '', model: '',
      is_default: false, enabled: true,
    })
    setShowApiKey(false)
    setTestResult(null)
    setError(null)
  }

  function handleCreate() {
    resetForm()
    setEditingConfig(null)
    setDialogOpen(true)
  }

  function handleEdit(config: ModelConfig) {
    resetForm()
    setEditingConfig(config)
    setFormData({
      name: config.name,
      base_url: config.base_url,
      api_key: '',
      model: config.model,
      is_default: config.is_default,
      enabled: config.enabled,
    })
    setDialogOpen(true)
  }

  async function handleSubmit() {
    setError(null)
    try {
      if (editingConfig) {
        await updateConfig.mutateAsync({
          projectId,
          configId: editingConfig.config_id,
          data: {
            name: formData.name,
            base_url: formData.base_url,
            ...(formData.api_key && { api_key: formData.api_key }),
            model: formData.model,
            is_default: formData.is_default,
            enabled: formData.enabled,
          },
        })
        setSuccess('配置更新成功')
      } else {
        await createConfig.mutateAsync({
          projectId,
          data: formData,
        })
        setSuccess('配置创建成功')
      }
      setDialogOpen(false)
      resetForm()
    } catch (e) {
      setError(getModelConfigErrorMessage(e))
    }
  }

  async function handleDelete() {
    if (!deleteTarget) return
    setError(null)
    try {
      await deleteConfig.mutateAsync({
        projectId,
        configId: deleteTarget.config_id,
      })
      setSuccess('配置已删除')
      setDeleteTarget(null)
    } catch (e) {
      setError(getModelConfigErrorMessage(e))
    }
  }

  async function handleTest() {
    if (!formData.base_url || !formData.api_key || !formData.model) {
      setError('请填写 Base URL、API Key 和模型')
      return
    }
    setTesting(true)
    setTestResult(null)
    setError(null)
    try {
      const startTime = Date.now()
      const result = await testConfig.mutateAsync({
        projectId,
        data: {
          base_url: formData.base_url,
          api_key: formData.api_key,
          model: formData.model,
        },
      })
      const latency = result.latency_ms || (Date.now() - startTime)
      setTestResult({ success: true, message: `连接成功(${latency}ms)` })
    } catch (e) {
      setTestResult({ success: false, message: getModelConfigErrorMessage(e) })
    } finally {
      setTesting(false)
    }
  }

  function formatTime(iso: string) {
    try { return new Date(iso).toLocaleDateString('zh-CN') } catch { return iso }
  }

  if (isLoading) return <div className="text-text-muted py-8">加载中...</div>

  return (
    <div>
      {/* 成功提示 */}
      {success && (
        <Alert variant="success" className="mb-4">
          {success}
        </Alert>
      )}
      {/* 错误提示 */}
      {error && (
        <Alert variant="error" className="mb-4">
          {error}
        </Alert>
      )}

      {/* 操作栏 */}
      {!isViewer && (
        <div className="flex justify-end mb-4">
          <Button onClick={handleCreate}>
            <Plus className="w-4 h-4 mr-2" />
            新建配置
          </Button>
        </div>
      )}

      {/* 配置列表 */}
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>配置名</TableHead>
            <TableHead>Base URL</TableHead>
            <TableHead>模型</TableHead>
            <TableHead>API Key</TableHead>
            <TableHead>状态</TableHead>
            <TableHead>创建人</TableHead>
            <TableHead>创建时间</TableHead>
            <TableHead className="w-[200px]">操作</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {configs.map((config) => (
            <TableRow key={config.config_id}>
              <TableCell>
                <div className="flex items-center gap-2">
                  <span className="font-medium text-text">{config.name}</span>
                  {config.is_default && (
                    <Badge variant="primary">默认</Badge>
                  )}
                </div>
              </TableCell>
              <TableCell className="text-text-muted text-xs">
                {config.base_url}
              </TableCell>
              <TableCell className="text-text-muted">
                {config.model}
              </TableCell>
              <TableCell className="text-text-muted text-xs">
                {isViewer ? '-' : config.api_key_masked}
              </TableCell>
              <TableCell>
                <Badge variant={config.enabled ? 'secondary' : 'outline'}>
                  {config.enabled ? '启用' : '禁用'}
                </Badge>
              </TableCell>
              <TableCell className="text-text-muted">
                {config.created_by.username}
              </TableCell>
              <TableCell className="text-text-muted text-xs">
                {formatTime(config.created_at)}
              </TableCell>
              <TableCell className="w-[200px]">
                {!isViewer && (
                  <div className="flex items-center gap-1">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleEdit(config)}
                    >
                      编辑
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      disabled={config.is_default}
                      onClick={() => setDeleteTarget(config)}
                    >
                      删除
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => {
                        setEditingConfig(config)
                        setFormData({
                          name: config.name,
                          base_url: config.base_url,
                          api_key: '',
                          model: config.model,
                          is_default: config.is_default,
                          enabled: config.enabled,
                        })
                        setTestResult(null)
                        setError(null)
                        handleTest()
                      }}
                    >
                      测试
                    </Button>
                  </div>
                )}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>

      {/* 新建/编辑对话框 */}
      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="max-w-[500px]">
          <DialogHeader>
            <DialogTitle>
              {editingConfig ? '编辑配置' : '新建配置'}
            </DialogTitle>
            <DialogDescription>
              {editingConfig ? '修改模型配置信息' : '创建新的模型配置'}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <Label htmlFor="name">配置名</Label>
              <Input
                id="name"
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                placeholder="如:主用 Claude"
              />
            </div>
            <div>
              <Label htmlFor="base_url">Base URL</Label>
              <Input
                id="base_url"
                value={formData.base_url}
                onChange={(e) => setFormData({ ...formData, base_url: e.target.value })}
                placeholder="https://api.anthropic.com"
              />
            </div>
            <div>
              <Label htmlFor="api_key">API Key</Label>
              <div className="relative">
                <Input
                  id="api_key"
                  type={showApiKey ? 'text' : 'password'}
                  value={formData.api_key}
                  onChange={(e) => setFormData({ ...formData, api_key: e.target.value })}
                  placeholder="sk-xxx"
                  className="pr-10"
                />
                <button
                  type="button"
                  onClick={() => setShowApiKey(!showApiKey)}
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-text-muted hover:text-text"
                >
                  {showApiKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>
            <div>
              <Label htmlFor="model">模型</Label>
              <Input
                id="model"
                value={formData.model}
                onChange={(e) => setFormData({ ...formData, model: e.target.value })}
                placeholder="claude-sonnet-5"
              />
            </div>
            <div className="flex items-center gap-4">
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={formData.is_default}
                  onChange={(e) => {
                    setFormData({ ...formData, is_default: e.target.checked })
                    if (e.target.checked && hasDefault) {
                      setError('将替换当前默认配置')
                    }
                  }}
                  className="rounded border-border"
                />
                <span className="text-sm text-text">设为默认</span>
              </label>
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={formData.enabled}
                  onChange={(e) => setFormData({ ...formData, enabled: e.target.checked })}
                  className="rounded border-border"
                />
                <span className="text-sm text-text">启用</span>
              </label>
            </div>
            {testResult && (
              <Alert variant={testResult.success ? 'success' : 'error'}>
                {testResult.message}
              </Alert>
            )}
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setDialogOpen(false)}>
              取消
            </Button>
            <Button
              variant="default"
              onClick={handleTest}
              disabled={testing}
            >
              {testing ? '测试中...' : '测试连接'}
            </Button>
            <Button onClick={handleSubmit}>
              保存
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* 删除确认对话框 */}
      <Dialog open={!!deleteTarget} onOpenChange={() => setDeleteTarget(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>删除配置</DialogTitle>
            <DialogDescription>
              确定删除配置 {deleteTarget?.name} 吗?
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setDeleteTarget(null)}>
              取消
            </Button>
            <Button
              variant="primary"
              className="bg-error hover:bg-error/90"
              onClick={handleDelete}
            >
              确定
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
