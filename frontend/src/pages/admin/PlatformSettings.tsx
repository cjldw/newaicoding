/**
 * PlatformSettings — 平台设置页(仅 superadmin 可见)
 * 三段式表单: GitLab 集成 / 域名配置 / 全局参数
 * 测试连接按钮: POST /api/admin/platform-settings/test-connection
 */

import { useState, useEffect } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { AlertCircle, CheckCircle2, Loader2, Wifi } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { api, ApiError } from '@/api/client'

// ---- Types ----
interface PlatformSettingsData {
  gitlab_url: string
  gitlab_bot_token: string
  gitlab_bot_group_id: string
  gitlab_webhook_secret: string
  preview_base_domain: string
  deploy_base_domain: string
  max_containers_total: number
  kb_max_pages_per_kb: number
  kb_max_file_mb: number
}

// 表单 schema
const formSchema = z.object({
  gitlab_url: z.string().url('请输入有效的 URL').or(z.literal('')),
  gitlab_bot_token: z.string(),
  gitlab_bot_group_id: z.string(),
  gitlab_webhook_secret: z.string(),
  preview_base_domain: z.string(),
  deploy_base_domain: z.string(),
  max_containers_total: z.coerce.number().min(1, '至少 1'),
  kb_max_pages_per_kb: z.coerce.number().min(1, '至少 1'),
  kb_max_file_mb: z.coerce.number().min(1, '至少 1'),
})

type FormValues = z.infer<typeof formSchema>

// 脱敏显示 token/secret: glpat-xxxxxxxxxxxx9x2f → glpat-••••••••9x2f
function maskSecret(val: string): string {
  if (!val || val.length < 8) return val
  const prefix = val.slice(0, 5)
  const suffix = val.slice(-4)
  return `${prefix}${'•'.repeat(8)}${suffix}`
}

export function PlatformSettings() {
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)
  const [testResult, setTestResult] = useState<{ ok: boolean; message: string } | null>(null)

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isDirty },
  } = useForm<FormValues>({
    resolver: zodResolver(formSchema),
  })

  // 加载当前配置
  useEffect(() => {
    async function load() {
      try {
        const res = await api.get<PlatformSettingsData>('/admin/platform-settings')
        const d = res.data
        reset({
          gitlab_url: d.gitlab_url ?? '',
          gitlab_bot_token: d.gitlab_bot_token ?? '',
          gitlab_bot_group_id: d.gitlab_bot_group_id ?? '',
          gitlab_webhook_secret: d.gitlab_webhook_secret ?? '',
          preview_base_domain: d.preview_base_domain ?? '',
          deploy_base_domain: d.deploy_base_domain ?? '',
          max_containers_total: d.max_containers_total ?? 100,
          kb_max_pages_per_kb: d.kb_max_pages_per_kb ?? 50,
          kb_max_file_mb: d.kb_max_file_mb ?? 10,
        })
      } catch {
        setError('加载平台配置失败')
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [reset])

  async function onSubmit(values: FormValues) {
    setSaving(true)
    setError(null)
    setSuccess(null)
    try {
      await api.put('/admin/platform-settings', values)
      setSuccess('保存成功')
      setTimeout(() => setSuccess(null), 3000)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : '保存失败')
    } finally {
      setSaving(false)
    }
  }

  async function handleTestConnection() {
    setTesting(true)
    setTestResult(null)
    try {
      const res = await api.post<{ ok: boolean; message: string }>(
        '/admin/platform-settings/test-connection',
      )
      setTestResult({ ok: true, message: res.data?.message ?? '连接成功' })
    } catch (err) {
      setTestResult({
        ok: false,
        message: err instanceof ApiError ? err.message : '连接失败',
      })
    } finally {
      setTesting(false)
    }
  }

  if (loading) {
    return <div className="page text-text-muted">加载中...</div>
  }

  return (
    <div className="page">
      <div className="page-head">
        <h1>平台设置</h1>
      </div>

      <form onSubmit={handleSubmit(onSubmit)} className="space-y-8">
        {/* Section 1: GitLab 集成 */}
        <section className="card">
          <div className="card-head">
            <div className="card-title">GitLab 集成</div>
          </div>
          <div className="card-body space-y-4">

          <div className="space-y-1">
            <label className="text-sm font-medium text-text">GitLab URL</label>
            <Input
              placeholder="https://gitlab.example.com"
              {...register('gitlab_url')}
            />
            {errors.gitlab_url && (
              <p className="text-xs text-error">{errors.gitlab_url.message}</p>
            )}
          </div>

          <div className="space-y-1">
            <label className="text-sm font-medium text-text">Bot Token</label>
            <Input
              type="password"
              placeholder="glpat-xxxxxxxxxxxx"
              {...register('gitlab_bot_token')}
            />
            <p className="text-xs text-text-muted">
              当前值: {maskSecret('glpat-xxxxxxxxxxxx9x2f')}
            </p>
          </div>

          <div className="space-y-1">
            <label className="text-sm font-medium text-text">Bot Group ID</label>
            <Input
              placeholder="例如: 12345"
              {...register('gitlab_bot_group_id')}
            />
          </div>

          <div className="space-y-1">
            <label className="text-sm font-medium text-text">Webhook Secret</label>
            <Input
              type="password"
              placeholder="webhook secret"
              {...register('gitlab_webhook_secret')}
            />
          </div>

          {/* 测试连接 */}
          <div className="flex items-center gap-3">
            <Button
              type="button"
              variant="ghost"
              onClick={handleTestConnection}
              disabled={testing}
            >
              {testing ? (
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
              ) : (
                <Wifi className="w-4 h-4 mr-2" />
              )}
              测试连接
            </Button>
            {testResult && (
              <span className={`flex items-center gap-1 text-sm ${testResult.ok ? 'text-success' : 'text-error'}`}>
                {testResult.ok ? (
                  <CheckCircle2 className="w-4 h-4" />
                ) : (
                  <AlertCircle className="w-4 h-4" />
                )}
                {testResult.message}
              </span>
            )}
          </div>
          </div>
        </section>

        {/* Section 2: 域名配置 */}
        <section className="card">
          <div className="card-head">
            <div className="card-title">域名配置</div>
          </div>
          <div className="card-body space-y-4">

          <div className="space-y-1">
            <label className="text-sm font-medium text-text">预览环境基础域名</label>
            <Input
              placeholder="例如: preview.example.com"
              {...register('preview_base_domain')}
            />
          </div>

          <div className="space-y-1">
            <label className="text-sm font-medium text-text">部署环境基础域名</label>
            <Input
              placeholder="例如: app.example.com"
              {...register('deploy_base_domain')}
            />
          </div>
          </div>
        </section>

        {/* Section 3: 全局参数 */}
        <section className="card">
          <div className="card-head">
            <div className="card-title">全局参数</div>
          </div>
          <div className="card-body space-y-4">

          <div className="space-y-1">
            <label className="text-sm font-medium text-text">最大容器总数</label>
            <Input
              type="number"
              {...register('max_containers_total')}
            />
            {errors.max_containers_total && (
              <p className="text-xs text-error">{errors.max_containers_total.message}</p>
            )}
          </div>

          <div className="space-y-1">
            <label className="text-sm font-medium text-text">每个知识库最大页数</label>
            <Input
              type="number"
              {...register('kb_max_pages_per_kb')}
            />
            {errors.kb_max_pages_per_kb && (
              <p className="text-xs text-error">{errors.kb_max_pages_per_kb.message}</p>
            )}
          </div>

          <div className="space-y-1">
            <label className="text-sm font-medium text-text">知识库单文件上限(MB)</label>
            <Input
              type="number"
              {...register('kb_max_file_mb')}
            />
            {errors.kb_max_file_mb && (
              <p className="text-xs text-error">{errors.kb_max_file_mb.message}</p>
            )}
          </div>
          </div>
        </section>

        {/* 全局错误/成功 */}
        {error && (
          <div className="flex items-start gap-2 p-3 rounded-md bg-error/10 border border-error/20">
            <AlertCircle className="w-4 h-4 text-error mt-0.5 flex-shrink-0" />
            <p className="text-sm text-error">{error}</p>
          </div>
        )}
        {success && (
          <div className="flex items-center gap-2 p-3 rounded-md bg-success/10 border border-success/20">
            <CheckCircle2 className="w-4 h-4 text-success" />
            <p className="text-sm text-success">{success}</p>
          </div>
        )}

        {/* 保存按钮 */}
        <div className="flex justify-end">
          <Button
            type="submit"
            variant="primary"
            disabled={saving || !isDirty}
          >
            {saving ? '保存中...' : '保存配置'}
          </Button>
        </div>
      </form>
    </div>
  )
}
