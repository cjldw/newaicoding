/**
 * PlatformSettings — 平台设置页(R24 布局改版)
 * 左分类导航(4 组,200px 定宽)+ 右侧单卡片(max-w-2xl 672px)
 * 各分组独立保存/测试连接;切换分组丢弃未保存修改
 *
 * 分组:
 *  1. GitLab 集成 — gitlab_url / gitlab_bot_token / gitlab_bot_group_id / gitlab_webhook_secret + 测试连接
 *  2. 域名配置 — preview_base_domain / deploy_base_domain
 *  3. 全局参数 — max_containers_total / kb_max_pages_per_kb / kb_max_file_mb
 *  4. 模型默认配置(R23/R1)— llm_base_url / llm_api_key / llm_models(≤10 个模型名 tag,先测后入列)
 *     / llm_default_model(四键齐备校验 + 2008 连通测试)
 *  5. 自定义变量(R8.F4)— custom_env_vars(KV 表,任务容器启动时全量注入)
 *
 * 敏感键(gitlab_bot_token / gitlab_webhook_secret / llm_api_key)按分片④「打码回显值只读展示」:
 * 服务端打码值以 readOnly 展示,点「更换」进入编辑态输入新值;未编辑时该键不进 payload
 * (后端为部分更新,不发即保留原值——防止打码串回写覆盖真实密钥)。
 */

import { useState, useEffect, useCallback, useRef } from 'react'
import { useForm } from 'react-hook-form'
import type { UseFormRegisterReturn } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import {
  AlertCircle,
  CheckCircle2,
  Loader2,
  Wifi,
  SlidersHorizontal,
  Server,
  Globe,
  Brain,
  Braces,
  Plus,
  Star,
  Trash2,
  X,
} from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Badge } from '@/components/ui/Badge'
import { useToast } from '@/hooks/useToast'
import { api, ApiError } from '@/api/client'
import type { PlatformSettings as PlatformSettingsData } from '@/api/admin'

// ---- 分组定义 ----
type GroupKey = 'gitlab' | 'domain' | 'global' | 'llm' | 'vars'

const navItems: { key: GroupKey; label: string; icon: typeof Server }[] = [
  { key: 'gitlab', label: 'GitLab 集成', icon: Server },
  { key: 'domain', label: '域名配置', icon: Globe },
  { key: 'global', label: '全局参数', icon: SlidersHorizontal },
  { key: 'llm', label: '模型默认配置', icon: Brain },
  { key: 'vars', label: '自定义变量', icon: Braces },
]

// ---- 各分组表单 schema ----

// 1. GitLab 集成
const gitlabSchema = z.object({
  gitlab_url: z.string().url('请输入有效的 URL').or(z.literal('')),
  gitlab_bot_token: z.string(),
  gitlab_bot_group_id: z.string(),
  gitlab_webhook_secret: z.string(),
})
type GitlabValues = z.infer<typeof gitlabSchema>

// 2. 域名配置
const domainSchema = z.object({
  preview_base_domain: z.string(),
  deploy_base_domain: z.string(),
})
type DomainValues = z.infer<typeof domainSchema>

// 3. 全局参数
const globalSchema = z.object({
  max_containers_total: z.coerce.number().min(1, '至少 1'),
  kb_max_pages_per_kb: z.coerce.number().min(1, '至少 1'),
  kb_max_file_mb: z.coerce.number().min(1, '至少 1'),
})
type GlobalValues = z.infer<typeof globalSchema>

// 4. 模型默认配置(R23/R1:models/default_model 为表单本地编辑态,随「保存」整批 PUT)
const llmSchema = z.object({
  llm_base_url: z.string(),
  llm_api_key: z.string(),
  models: z.array(z.string()),
  default_model: z.string(),
})
type LlmValues = z.infer<typeof llmSchema>

// R1:模型名列表上限(与后端 llm_models ≤10 同口径)
const LLM_MODELS_MAX = 10

// 5. 自定义变量(R8.F4:客户端预检规则与后端 _validate_custom_env 同口径)
const ENV_KEY_RE = /^[A-Za-z_][A-Za-z0-9_]*$/
// 系统保留键(与后端 RESERVED_ENV_KEYS 同步维护)
const RESERVED_ENV_KEYS = new Set([
  'GITLAB_TOKEN', 'GITLAB_INSTANCE_URL',
  'LLM_BASE_URL', 'LLM_API_KEY', 'LLM_MODEL', 'LLM_URL',
  'ANTHROPIC_BASE_URL', 'ANTHROPIC_API_KEY', 'ANTHROPIC_MODEL',
  'TASK_ID', 'PROJECT_ID', 'REQ_ID', 'PRD_FILE_PATH',
])
const CUSTOM_ENV_MAX_KEYS = 50

// KV 编辑行(受控 state,非 useForm——行数动态,表单库收益为负)
interface VarRow {
  id: number
  key: string
  value: string
}

// ---- 工具函数 ----

// ========================================================================
export function PlatformSettings() {
  const [loading, setLoading] = useState(true)
  const [activeGroup, setActiveGroup] = useState<GroupKey>('gitlab')

  // 各分组独立保存状态
  const [gitlabSaving, setGitlabSaving] = useState(false)
  const [domainSaving, setDomainSaving] = useState(false)
  const [globalSaving, setGlobalSaving] = useState(false)
  const [llmSaving, setLlmSaving] = useState(false)
  const [varsSaving, setVarsSaving] = useState(false)

  // GitLab 测试连接
  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState<{ ok: boolean; message: string } | null>(null)

  // 各分组独立错误/成功提示
  const [gitlabMsg, setGitlabMsg] = useState<{ type: 'error' | 'success'; text: string } | null>(null)
  const [domainMsg, setDomainMsg] = useState<{ type: 'error' | 'success'; text: string } | null>(null)
  const [globalMsg, setGlobalMsg] = useState<{ type: 'error' | 'success'; text: string } | null>(null)
  const [llmMsg, setLlmMsg] = useState<{ type: 'error' | 'success'; text: string } | null>(null)
  const [varsMsg, setVarsMsg] = useState<{ type: 'error' | 'success'; text: string } | null>(null)
  // R8.F4:自定义变量 KV 编辑行(服务端值加载后转行数组;保存成功后以服务端回显重灌)
  const [varRows, setVarRows] = useState<VarRow[]>([])
  const varRowSeq = useRef(0)

  // 敏感键编辑态(R24 分片④:打码回显 readOnly,点「更换」才进入编辑,防止打码串回写覆盖真值)
  const [editingGitlabToken, setEditingGitlabToken] = useState(false)
  const [editingWebhookSecret, setEditingWebhookSecret] = useState(false)
  const [editingLlmKey, setEditingLlmKey] = useState(false)

  // R1:模型名 tag 输入组(模型名输入为表单外本地态,入列后进 llmForm.models;瞬时提示走 toast)
  const [, showToast, ToastEl] = useToast()
  const [modelInput, setModelInput] = useState('')
  const [addingModel, setAddingModel] = useState(false)

  // 防重守卫(判据 6):disabled 属性经 React 重渲染才生效,同 tick 连点拦不住;
  // in-flight ref 锁保证同一动作(分组保存/测试连接)任一时刻仅放行一次
  const inflightRef = useRef<Set<string>>(new Set())
  const tryLock = (key: string): boolean => {
    if (inflightRef.current.has(key)) return false
    inflightRef.current.add(key)
    return true
  }
  const unlock = (key: string) => {
    inflightRef.current.delete(key)
  }

  // 各分组独立 useForm(切换分组时 reset 回服务端值 → 丢弃未保存修改)
  const gitlabForm = useForm<GitlabValues>({ resolver: zodResolver(gitlabSchema) })
  const domainForm = useForm<DomainValues>({ resolver: zodResolver(domainSchema) })
  const globalForm = useForm<GlobalValues>({ resolver: zodResolver(globalSchema) })
  const llmForm = useForm<LlmValues>({ resolver: zodResolver(llmSchema) })

  // 服务端原始数据缓存(切换分组时用于 reset)
  const [serverData, setServerData] = useState<PlatformSettingsData | null>(null)

  // ---- 加载全量配置(一次 GET,分发到各分组 form)----
  /** withLoading=true 首次进入显示加载态;保存成功后以 false 静默刷新(更新打码回显值) */
  const loadData = useCallback(async (withLoading: boolean) => {
    try {
      const res = await api.get<PlatformSettingsData>('/admin/platform-settings')
      const d = res.data
      setServerData(d)
      resetAllForms(d)
    } catch {
      setGitlabMsg({ type: 'error', text: '加载平台配置失败' })
    } finally {
      if (withLoading) setLoading(false)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    loadData(true)
  }, [loadData])

  /** 将服务端数据分发到四个 form + 变量行(敏感键不回填打码串——readOnly 展示直读 serverData,form 内保持空) */
  function resetAllForms(d: PlatformSettingsData) {
    gitlabForm.reset({
      gitlab_url: d.gitlab_url ?? '',
      gitlab_bot_token: '',
      gitlab_bot_group_id: d.gitlab_bot_group_id != null ? String(d.gitlab_bot_group_id) : '',
      gitlab_webhook_secret: '',
    })
    domainForm.reset({
      preview_base_domain: d.preview_base_domain ?? '',
      deploy_base_domain: d.deploy_base_domain ?? '',
    })
    globalForm.reset({
      max_containers_total: d.max_containers_total ?? 100,
      kb_max_pages_per_kb: d.kb_max_pages_per_kb ?? 50,
      kb_max_file_mb: d.kb_max_file_mb ?? 10,
    })
    llmForm.reset({
      llm_base_url: d.llm_base_url ?? '',
      llm_api_key: '',
      // R1:模型名列表从 GET 兼容数据初始化(服务端已做 llm_model 旧键 → llm_models 映射;
      // 前端再兜底一层:仅旧键回显时包装 [旧值]),default 取显式值或列表第一项
      models:
        d.llm_models && d.llm_models.length > 0 ? d.llm_models : d.llm_model ? [d.llm_model] : [],
      default_model: d.llm_default_model ?? d.llm_models?.[0] ?? d.llm_model ?? '',
    })
    // R8.F4:custom_env_vars 原样回显(非敏感),转 KV 行
    setVarRows(
      Object.entries(d.custom_env_vars ?? {}).map(([k, v]) => ({
        id: ++varRowSeq.current,
        key: k,
        value: v,
      })),
    )
  }

  /** 切换分组:reset 所有分组 form 回服务端值(丢弃未保存修改),并复位敏感键编辑态 */
  const switchGroup = useCallback(
    (group: GroupKey) => {
      if (group === activeGroup || !serverData) return
      setActiveGroup(group)
      // 切走时 reset 表单(丢弃未保存值)
      resetAllForms(serverData)
      setEditingGitlabToken(false)
      setEditingWebhookSecret(false)
      setEditingLlmKey(false)
      // 清除所有分组的提示消息
      setGitlabMsg(null)
      setDomainMsg(null)
      setGlobalMsg(null)
      setLlmMsg(null)
      setVarsMsg(null)
      setTestResult(null)
    },
    [activeGroup, serverData, gitlabForm, domainForm, globalForm, llmForm],
  )

  // ---- 各分组保存 ----

  /** 1. GitLab 集成保存(含 BUG-008/009 group_id int 强转) */
  const onGitlabSubmit = gitlabForm.handleSubmit(async (values) => {
    if (!tryLock('gitlab')) return
    setGitlabSaving(true)
    setGitlabMsg(null)
    try {
      // BUG-008/009:group_id 后端要求 int;前端 Input 产出字符串,提交前强转
      const payload: Record<string, unknown> = { ...values }
      const rawGroupId = (values.gitlab_bot_group_id ?? '').toString().trim()
      if (rawGroupId === '') {
        delete payload.gitlab_bot_group_id
      } else {
        const parsed = Number(rawGroupId)
        if (Number.isFinite(parsed) && Number.isInteger(parsed)) {
          payload.gitlab_bot_group_id = parsed
        }
        // 非数字:仍按原字符串发送,后端会返回 2007
      }
      // R24 分片④:敏感键打码回显只读——仅在「更换」编辑态输入了新值才提交;
      // 未编辑则从 payload 剔除(后端部分更新,不发即保留原值,防止打码串回写覆盖真值)
      if (!editingGitlabToken || !values.gitlab_bot_token.trim()) {
        delete payload.gitlab_bot_token
      }
      if (!editingWebhookSecret || !values.gitlab_webhook_secret.trim()) {
        delete payload.gitlab_webhook_secret
      }
      await api.put('/admin/platform-settings', payload)
      setGitlabMsg({ type: 'success', text: '保存成功' })
      setEditingGitlabToken(false)
      setEditingWebhookSecret(false)
      setTimeout(() => setGitlabMsg(null), 3000)
      // 静默刷新:更新打码回显值与新值的打码形态一致
      loadData(false)
    } catch (err) {
      setGitlabMsg({ type: 'error', text: err instanceof ApiError ? err.message : '保存失败' })
    } finally {
      unlock('gitlab')
      setGitlabSaving(false)
    }
  })

  /** 2. 域名配置保存 */
  const onDomainSubmit = domainForm.handleSubmit(async (values) => {
    if (!tryLock('domain')) return
    setDomainSaving(true)
    setDomainMsg(null)
    try {
      await api.put('/admin/platform-settings', values)
      setDomainMsg({ type: 'success', text: '保存成功' })
      setTimeout(() => setDomainMsg(null), 3000)
    } catch (err) {
      setDomainMsg({ type: 'error', text: err instanceof ApiError ? err.message : '保存失败' })
    } finally {
      unlock('domain')
      setDomainSaving(false)
    }
  })

  /** 3. 全局参数保存 */
  const onGlobalSubmit = globalForm.handleSubmit(async (values) => {
    if (!tryLock('global')) return
    setGlobalSaving(true)
    setGlobalMsg(null)
    try {
      await api.put('/admin/platform-settings', values)
      setGlobalMsg({ type: 'success', text: '保存成功' })
      setTimeout(() => setGlobalMsg(null), 3000)
    } catch (err) {
      setGlobalMsg({ type: 'error', text: err instanceof ApiError ? err.message : '保存失败' })
    } finally {
      unlock('global')
      setGlobalSaving(false)
    }
  })

  /** 4. 模型默认配置保存(R1:四键齐备前端校验(缺项标红/空列表拦截)+ 服务端 2008 连通测试) */
  const onLlmSubmit = llmForm.handleSubmit(async (values) => {
    if (!tryLock('llm')) return
    setLlmSaving(true)
    setLlmMsg(null)
    try {
      const base = values.llm_base_url.trim()
      const key = values.llm_api_key.trim()
      const models = values.models
      // R1:模型名列表非空(空列表语义=未配置,直接拦截)
      if (models.length === 0) {
        showToast('err', '请至少添加一个模型名')
        setLlmSaving(false)
        return
      }
      // R1 契约:四键齐备整批保存(缺一整批拒绝 2007);缺项逐字段标红
      // 注:llm_api_key 永不回显完整(R23),已有配置时更新任意键都需重输完整 key(打码值不参与提交)
      const missing: { field: 'llm_base_url' | 'llm_api_key'; msg: string }[] = []
      if (!base) missing.push({ field: 'llm_base_url', msg: '必填' })
      if (!key) missing.push({ field: 'llm_api_key', msg: '需输入完整 API Key(打码值不参与提交)' })
      if (missing.length > 0) {
        for (const m of missing) {
          llmForm.setError(m.field, { type: 'manual', message: m.msg })
        }
        setLlmMsg({ type: 'error', text: '平台默认模型需完整配置四项' })
        setLlmSaving(false)
        return
      }
      // default_model 必须 ∈ llm_models(本地操作已保证;防御性兜底取第一项)
      const defaultModel = models.includes(values.default_model) ? values.default_model : models[0]
      await api.put('/admin/platform-settings', {
        llm_base_url: base,
        llm_api_key: key,
        llm_models: models,
        llm_default_model: defaultModel,
      })
      setLlmMsg({ type: 'success', text: '保存成功' })
      setEditingLlmKey(false)
      setTimeout(() => setLlmMsg(null), 3000)
      // 静默刷新:更新打码回显值与模型列表回显一致
      loadData(false)
    } catch (err) {
      // 2007/2008/13008/13009 错误 message 由服务端透传
      const text = err instanceof ApiError ? err.message : '保存失败'
      setLlmMsg({ type: 'error', text })
    } finally {
      unlock('llm')
      setLlmSaving(false)
    }
  })

  /** R1:添加模型名 tag —— 先调 test-connection(按钮转"测试中..."),成功才入列;失败 toast 保留输入 */
  async function handleAddModel() {
    const name = modelInput.trim()
    if (!name) return
    const models = llmForm.getValues('models') ?? []
    // 前端拦截:超限(13008 口径)/重复(13009 口径)
    if (models.length >= LLM_MODELS_MAX) {
      showToast('err', `模型名数量已达上限(${LLM_MODELS_MAX} 个)`)
      return
    }
    if (models.includes(name)) {
      showToast('err', '该模型已存在')
      return
    }
    if (!tryLock('llm-add')) return
    setAddingModel(true)
    try {
      const res = await api.post<{ success: boolean }>('/admin/platform-settings/test-connection', {
        base_url: llmForm.getValues('llm_base_url').trim(),
        api_key: llmForm.getValues('llm_api_key').trim(),
        model: name,
      })
      // HTTP 200 但 success=false:沿用 2008 口径文案,输入保留
      if (res.data?.success === false) {
        showToast('err', '连接失败,请检查 Base URL 和 API Key')
        return
      }
      const next = [...models, name]
      llmForm.setValue('models', next)
      // 第一个添加项自动设为默认
      if (next.length === 1) llmForm.setValue('default_model', name)
      setModelInput('')
    } catch (err) {
      // 2008 message 透传给 toast;模型名不入列
      showToast('err', err instanceof ApiError ? err.message : '连接失败,请检查 Base URL 和 API Key')
    } finally {
      unlock('llm-add')
      setAddingModel(false)
    }
  }

  /** R1:删除模型名 tag —— 仅剩 1 项不可删(由 X disabled 保证);删默认项自动顺延第一项并提示 */
  function removeModel(name: string) {
    const models = llmForm.getValues('models') ?? []
    if (models.length <= 1) return
    const next = models.filter((m) => m !== name)
    llmForm.setValue('models', next)
    if (llmForm.getValues('default_model') === name) {
      const nextDefault = next[0]
      llmForm.setValue('default_model', nextDefault)
      showToast('ok', `已将 ${nextDefault} 设为默认`)
    }
  }

  /** R1:tag Star 设为默认(纯本地编辑态,「默认」徽章迁移;随保存整批提交) */
  function handleSetDefault(name: string) {
    llmForm.setValue('default_model', name)
  }

  /** R8.F4(BUG-036):自定义变量保存 —— 客户端预检(与后端 2007 同口径)后单键 PUT */
  async function handleVarsSave() {
    if (!tryLock('vars')) return
    setVarsSaving(true)
    setVarsMsg(null)
    try {
      const errors: string[] = []
      const payload: Record<string, string> = {}
      for (const row of varRows) {
        const k = row.key.trim()
        if (!k) {
          errors.push('存在空变量名')
          continue
        }
        if (!ENV_KEY_RE.test(k)) {
          errors.push(`变量名 ${k} 非法(须匹配 [A-Za-z_][A-Za-z0-9_]*)`)
          continue
        }
        if (RESERVED_ENV_KEYS.has(k)) {
          errors.push(`变量名 ${k} 为系统保留`)
          continue
        }
        if (row.value.length > 2048) {
          errors.push(`变量 ${k} 的值超长(≤2048 字符)`)
          continue
        }
        if (k in payload) {
          errors.push(`变量名 ${k} 重复`)
          continue
        }
        payload[k] = row.value
      }
      if (Object.keys(payload).length > CUSTOM_ENV_MAX_KEYS) {
        errors.push(`自定义变量数量超限(最多 ${CUSTOM_ENV_MAX_KEYS} 个)`)
      }
      if (errors.length > 0) {
        setVarsMsg({ type: 'error', text: errors[0] })
        return
      }
      // 全删空集合 → 存 {}(清空);未配置过的空表不发请求
      if (Object.keys(payload).length === 0 && !serverData?.custom_env_vars) {
        setVarsMsg({ type: 'error', text: '至少添加一个变量,或删除全部后无需保存' })
        return
      }
      await api.put('/admin/platform-settings', { custom_env_vars: payload })
      setVarsMsg({ type: 'success', text: '保存成功,新任务容器启动时生效' })
      setTimeout(() => setVarsMsg(null), 3000)
      loadData(false)
    } catch (err) {
      setVarsMsg({ type: 'error', text: err instanceof ApiError ? err.message : '保存失败' })
    } finally {
      unlock('vars')
      setVarsSaving(false)
    }
  }

  /** GitLab 测试连接(BUG-010:以 ok 字段为准;in-flight 锁防同 tick 连点) */
  async function handleTestConnection() {
    if (!tryLock('test')) return
    setTesting(true)
    setTestResult(null)
    try {
      const res = await api.post<{ ok: boolean; message: string }>(
        '/admin/platform-settings/test-connection',
      )
      // BUG-010:以接口返回的 ok 为准——GitLab 侧连通失败(如 401)时 data.ok=false
      setTestResult({
        ok: res.data?.ok === true,
        message: res.data?.message ?? (res.data?.ok ? '连接成功' : '测试失败'),
      })
    } catch (err) {
      setTestResult({
        ok: false,
        message: err instanceof ApiError ? err.message : '连接失败',
      })
    } finally {
      unlock('test')
      setTesting(false)
    }
  }

  // ---- 加载态 ----
  if (loading) {
    return (
      <div className="page-loading">
        <Loader2 className="w-4 h-4 animate-spin" />
        加载中…
      </div>
    )
  }

  // ---- 通用 UI 片段 ----

  /** 分组消息条(错误/成功;语义 token 三件套 red/green,见 globals.css 的 red/green 变量) */
  const renderMsg = (msg: { type: 'error' | 'success'; text: string } | null) => {
    if (!msg) return null
    const isError = msg.type === 'error'
    return (
      <div
        className={`flex items-${isError ? 'start' : 'center'} gap-2 p-3 rounded-md ${
          isError ? 'bg-red-bg border border-red-border' : 'bg-green-bg border border-green-border'
        }`}
      >
        {isError ? (
          <AlertCircle className="w-4 h-4 text-red-fg mt-0.5 flex-shrink-0" />
        ) : (
          <CheckCircle2 className="w-4 h-4 text-green-fg" />
        )}
        <p className={`text-sm ${isError ? 'text-red-fg' : 'text-green-fg'}`}>{msg.text}</p>
      </div>
    )
  }

  /** 表单字段通用渲染 */
  const renderField = (props: {
    label: string
    error?: string
    children: React.ReactNode
  }) => (
    <div className="space-y-1">
      <label className="text-sm font-medium text-text">{props.label}</label>
      {props.children}
      {props.error && <p className="text-xs text-red-fg">{props.error}</p>}
    </div>
  )

  /**
   * 敏感键字段渲染(R24 分片④:打码回显值只读展示,点「更换」进入编辑态)
   * - 服务端已配置(maskedValue 非空)且非编辑态:readOnly Input 直显打码串 + 「更换」
   * - 编辑态/未配置:可编辑 password Input(maskedValue 存在时 placeholder 提示「输入新值」)+ 「取消」
   */
  const renderSecretField = (opts: {
    label: string
    maskedValue: string | null
    editing: boolean
    onStart: () => void
    onCancel: () => void
    field: UseFormRegisterReturn
    error?: string
  }) => (
    <div className="space-y-1">
      <label className="text-sm font-medium text-text">{opts.label}</label>
      {opts.maskedValue && !opts.editing ? (
        <div className="flex items-center gap-2" key="ro">
          <Input value={opts.maskedValue} readOnly className="flex-1" />
          <Button type="button" variant="ghost" onClick={opts.onStart}>
            更换
          </Button>
        </div>
      ) : (
        <div className="flex items-center gap-2" key="edit">
          <Input
            type="password"
            placeholder={opts.maskedValue ? '输入新值' : ''}
            {...opts.field}
            className="flex-1"
          />
          {opts.maskedValue && (
            <Button type="button" variant="ghost" onClick={opts.onCancel}>
              取消
            </Button>
          )}
        </div>
      )}
      {opts.error && <p className="text-xs text-red-fg">{opts.error}</p>}
    </div>
  )

  // ---- 各分组内容 ----
  const gitlabErrors = gitlabForm.formState.errors
  const globalErrors = globalForm.formState.errors

  const renderGitlab = () => (
    <>
      <h2 className="text-lg font-semibold text-text">GitLab 集成</h2>
      <p className="text-sm text-text-muted mt-1">
        配置 GitLab 实例地址、Bot 账号与 Webhook 密钥
      </p>

      {/* 保存结果消息条:表单上方(分片交互流程:失败 banner / 成功提示,输入保留) */}
      {renderMsg(gitlabMsg)}

      <form onSubmit={onGitlabSubmit} className="space-y-3 mt-6">
        {renderField({
          label: 'GitLab URL',
          error: gitlabErrors.gitlab_url?.message,
          children: (
            <Input
              placeholder="https://gitlab.example.com"
              {...gitlabForm.register('gitlab_url')}
            />
          ),
        })}

        {renderSecretField({
          label: 'Bot Token',
          maskedValue: serverData?.gitlab_bot_token ?? null,
          editing: editingGitlabToken,
          onStart: () => setEditingGitlabToken(true),
          onCancel: () => {
            setEditingGitlabToken(false)
            gitlabForm.setValue('gitlab_bot_token', '')
          },
          field: gitlabForm.register('gitlab_bot_token'),
          error: gitlabErrors.gitlab_bot_token?.message,
        })}

        {renderField({
          label: 'Bot Group ID',
          children: (
            <Input
              placeholder="例如: 12345"
              {...gitlabForm.register('gitlab_bot_group_id')}
            />
          ),
        })}

        {renderSecretField({
          label: 'Webhook Secret',
          maskedValue: serverData?.gitlab_webhook_secret ?? null,
          editing: editingWebhookSecret,
          onStart: () => setEditingWebhookSecret(true),
          onCancel: () => {
            setEditingWebhookSecret(false)
            gitlabForm.setValue('gitlab_webhook_secret', '')
          },
          field: gitlabForm.register('gitlab_webhook_secret'),
          error: gitlabErrors.gitlab_webhook_secret?.message,
        })}

        {/* 测试连接 */}
        <div className="flex items-center gap-3 pt-2">
          <Button type="button" variant="ghost" onClick={handleTestConnection} disabled={testing}>
            {testing ? (
              <Loader2 className="w-4 h-4 mr-2 animate-spin" />
            ) : (
              <Wifi className="w-4 h-4 mr-2" />
            )}
            测试连接
          </Button>
          {testResult && (
            <span
              className={`flex items-center gap-1 text-sm ${
                testResult.ok ? 'text-green-fg' : 'text-red-fg'
              }`}
            >
              {testResult.ok ? (
                <CheckCircle2 className="w-4 h-4" />
              ) : (
                <AlertCircle className="w-4 h-4" />
              )}
              {testResult.message}
            </span>
          )}
        </div>

        <div className="flex justify-end pt-2">
          <button type="submit" className="btn btn-pri" disabled={gitlabSaving}>
            {gitlabSaving ? '保存中...' : '保存'}
          </button>
        </div>
      </form>
    </>
  )

  const renderDomain = () => (
    <>
      <h2 className="text-lg font-semibold text-text">域名配置</h2>
      <p className="text-sm text-text-muted mt-1">配置预览与部署环境的基础域名</p>

      {/* 保存结果消息条:表单上方 */}
      {renderMsg(domainMsg)}

      <form onSubmit={onDomainSubmit} className="space-y-3 mt-6">
        {renderField({
          label: '预览环境基础域名',
          children: (
            <Input
              placeholder="例如: preview.example.com"
              {...domainForm.register('preview_base_domain')}
            />
          ),
        })}

        {renderField({
          label: '部署环境基础域名',
          children: (
            <Input
              placeholder="例如: app.example.com"
              {...domainForm.register('deploy_base_domain')}
            />
          ),
        })}

        <div className="flex justify-end pt-2">
          <button type="submit" className="btn btn-pri" disabled={domainSaving}>
            {domainSaving ? '保存中...' : '保存'}
          </button>
        </div>
      </form>
    </>
  )

  const renderGlobal = () => (
    <>
      <h2 className="text-lg font-semibold text-text">全局参数</h2>
      <p className="text-sm text-text-muted mt-1">系统级资源配额与限制</p>

      {/* 保存结果消息条:表单上方 */}
      {renderMsg(globalMsg)}

      <form onSubmit={onGlobalSubmit} className="space-y-3 mt-6">
        {renderField({
          label: '最大容器总数',
          error: globalErrors.max_containers_total?.message,
          children: (
            <Input type="number" {...globalForm.register('max_containers_total')} />
          ),
        })}

        {renderField({
          label: '每个知识库最大页数',
          error: globalErrors.kb_max_pages_per_kb?.message,
          children: (
            <Input type="number" {...globalForm.register('kb_max_pages_per_kb')} />
          ),
        })}

        {renderField({
          label: '知识库单文件上限(MB)',
          error: globalErrors.kb_max_file_mb?.message,
          children: (
            <Input type="number" {...globalForm.register('kb_max_file_mb')} />
          ),
        })}

        <div className="flex justify-end pt-2">
          <button type="submit" className="btn btn-pri" disabled={globalSaving}>
            {globalSaving ? '保存中...' : '保存'}
          </button>
        </div>
      </form>
    </>
  )

  const renderLlm = () => {
    const llmErrors = llmForm.formState.errors
    // R1:watch 驱动 tag 列表/默认徽章随本地编辑态重渲染
    const models = llmForm.watch('models') ?? []
    const defaultModel = llmForm.watch('default_model')
    return (
      <>
        <h2 className="text-lg font-semibold text-text">模型默认配置</h2>
        <p className="text-sm text-text-muted mt-1">
          平台级默认 LLM 接入;一个 Base URL 与 API Key 下可配置多个模型供任务对话切换
        </p>

        {/* 保存结果消息条:表单上方(R23:失败 banner 值保留) */}
        {renderMsg(llmMsg)}

        <form onSubmit={onLlmSubmit} className="space-y-3 mt-6">
          {renderField({
            label: 'Base URL',
            error: llmErrors.llm_base_url?.message,
            children: (
              <Input
                placeholder="https://api.openai.com/v1"
                {...llmForm.register('llm_base_url')}
              />
            ),
          })}

          {renderSecretField({
            label: 'API Key',
            maskedValue: serverData?.llm_api_key ?? null,
            editing: editingLlmKey,
            onStart: () => setEditingLlmKey(true),
            onCancel: () => {
              setEditingLlmKey(false)
              llmForm.setValue('llm_api_key', '')
            },
            field: llmForm.register('llm_api_key'),
            error: llmErrors.llm_api_key?.message,
          })}

          {/* R1:模型名 tag 输入组(输入框 + 「添加」按钮;点添加/Enter 先测后入列) */}
          {renderField({
            label: '模型名',
            error: llmErrors.models?.message,
            children: (
              <div className="space-y-2">
                <div className="flex gap-2">
                  <Input
                    className="flex-1"
                    placeholder="例如: gpt-4o 后回车添加"
                    value={modelInput}
                    maxLength={64}
                    onChange={(e) => setModelInput(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') {
                        e.preventDefault()
                        handleAddModel()
                      }
                    }}
                  />
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    disabled={!modelInput.trim() || addingModel}
                    onClick={handleAddModel}
                  >
                    {addingModel ? (
                      <Loader2 className="w-4 h-4 mr-1 animate-spin" />
                    ) : (
                      <Plus className="w-4 h-4 mr-1" />
                    )}
                    {addingModel ? '测试中...' : '添加'}
                  </Button>
                </div>

                {/* tag 列表(空时隐藏):.chip + 模型名 + 默认徽章 + hover Star(设默认)/X(删除) */}
                {models.length > 0 && (
                  <div className="flex flex-wrap gap-1.5">
                    {models.map((m) => {
                      const isDefault = m === defaultModel
                      return (
                        <span key={m} className="chip group">
                          <span>{m}</span>
                          {isDefault && <Badge variant="primary">默认</Badge>}
                          <button
                            type="button"
                            className="text-text-muted hover:text-text opacity-0 group-hover:opacity-100 transition-opacity disabled:opacity-45 disabled:cursor-not-allowed"
                            title="设为默认"
                            aria-label={`将 ${m} 设为默认`}
                            disabled={isDefault}
                            onClick={() => handleSetDefault(m)}
                          >
                            <Star className="w-3 h-3" />
                          </button>
                          <button
                            type="button"
                            className="hover:text-red-fg opacity-0 group-hover:opacity-100 transition-opacity disabled:opacity-45 disabled:cursor-not-allowed"
                            title="删除"
                            aria-label={`删除 ${m}`}
                            disabled={models.length === 1}
                            onClick={() => removeModel(m)}
                          >
                            <X className="w-3 h-3" />
                          </button>
                        </span>
                      )
                    })}
                  </div>
                )}
              </div>
            ),
          })}

          <div className="flex justify-end pt-2">
            <button type="submit" className="btn btn-pri" disabled={llmSaving}>
              {llmSaving ? '保存中...' : '保存'}
            </button>
          </div>
        </form>
      </>
    )
  }

  /** 5. 自定义变量(R8.F4:KV 行编辑,任务容器启动时全量注入) */
  const renderVars = () => (
    <>
      <h2 className="text-lg font-semibold text-text">自定义变量</h2>
      <p className="text-sm text-text-muted mt-1">
        平台级环境变量,任务容器启动时全量注入(系统保留名不可占用;修改仅对新任务生效)
      </p>

      {/* 保存结果消息条:表单上方 */}
      {renderMsg(varsMsg)}

      <div className="space-y-2 mt-6">
        {varRows.map((row) => (
          <div key={row.id} className="flex items-center gap-2">
            <Input
              className="flex-1 font-mono"
              placeholder="变量名,如 HTTP_PROXY"
              value={row.key}
              onChange={(e) =>
                setVarRows((rs) => rs.map((r) => (r.id === row.id ? { ...r, key: e.target.value } : r)))
              }
            />
            <Input
              className="flex-[2]"
              placeholder="变量值"
              value={row.value}
              onChange={(e) =>
                setVarRows((rs) => rs.map((r) => (r.id === row.id ? { ...r, value: e.target.value } : r)))
              }
            />
            <Button
              type="button"
              variant="ghost"
              aria-label="删除变量"
              onClick={() => setVarRows((rs) => rs.filter((r) => r.id !== row.id))}
            >
              <Trash2 className="w-4 h-4" />
            </Button>
          </div>
        ))}

        <Button
          type="button"
          variant="ghost"
          disabled={varRows.length >= CUSTOM_ENV_MAX_KEYS}
          onClick={() =>
            setVarRows((rs) => [...rs, { id: ++varRowSeq.current, key: '', value: '' }])
          }
        >
          <Plus className="w-4 h-4 mr-2" />
          添加变量
        </Button>

        <div className="flex justify-end pt-2">
          <button type="button" className="btn btn-pri" onClick={handleVarsSave} disabled={varsSaving}>
            {varsSaving ? '保存中...' : '保存'}
          </button>
        </div>
      </div>
    </>
  )

  const groupContent: Record<GroupKey, () => React.ReactNode> = {
    gitlab: renderGitlab,
    domain: renderDomain,
    global: renderGlobal,
    llm: renderLlm,
    vars: renderVars,
  }

  // ---- 主渲染 ----
  return (
    <div className="page wide">
      {/* 页头(R2.F2 规范:icon + 标题 + 说明) */}
      <div className="page-head">
        <div>
          <h1 className="flex items-center gap-2">
            <SlidersHorizontal size={18} />
            平台设置
          </h1>
          <div className="sub">
            平台级全局配置:GitLab 实例与 Bot、域名、容器配额与默认模型(仅超管)
          </div>
        </div>
      </div>

      {/* 主体:左导航(200px 定宽,hug 高,bg-surface)+ 右内容卡片(max-w 672px);区块间 16px(布局②) */}
      <div className="flex gap-4 items-start">
        {/* 左导航(200px 定宽,hug 高,bg-surface) */}
        <nav className="w-[200px] flex-shrink-0">
          <ul className="space-y-1 bg-surface border border-border rounded-lg p-2">
            {navItems.map((item) => {
              const isActive = activeGroup === item.key
              const Icon = item.icon
              return (
                <li key={item.key}>
                  <button
                    type="button"
                    onClick={() => switchGroup(item.key)}
                    className={`w-full flex items-center gap-2 text-sm text-left px-3 py-2 transition-colors border-l-2 ${
                      isActive
                        ? 'bg-surface-strong text-text font-semibold border-primary'
                        : 'border-transparent text-text hover:bg-surface-strong'
                    }`}
                  >
                    <Icon className="w-4 h-4" />
                    {item.label}
                  </button>
                </li>
              )
            })}
          </ul>
        </nav>

        {/* 右内容区(单卡片,max-w 672px;区块间 16px,布局②) */}
        <div className="flex-1 min-w-0">
          <div className="bg-surface border border-border rounded-lg shadow-sm max-w-[672px] p-6">
            {groupContent[activeGroup]()}
          {/* R1:模型名交互瞬时提示(测试失败/重复/超限/默认顺延) */}
          {ToastEl}
        </div>
      </div>
    </div>
  )
}
