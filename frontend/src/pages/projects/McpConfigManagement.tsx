/**
 * McpConfigManagement — MCP 配置 Tab(R17)
 * - 标题"MCP 配置" + "使用模板"按钮(secondary)
 * - JSON 编辑器(全宽 Textarea,等宽字体 font-mono,rows=20,实时 JSON.parse 校验)
 * - 底部提示"配置将注入到任务容器的 `~/.claude/config.json`"
 * - 保存按钮(primary 右下角,viewer 隐藏)
 * - 使用模板对话框(模板卡片列表 → 动态参数表单 → 生成按钮填入编辑器)
 */

import { useState, useEffect, useMemo } from 'react'
import { FileJson, Plug } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { Textarea } from '@/components/ui/Textarea'
import { Input } from '@/components/ui/Input'
import { Label } from '@/components/ui/Label'
import { Alert } from '@/components/ui/Alert'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
  DialogFooter,
} from '@/components/ui/Dialog'
import {
  useMcpConfig, useUpdateMcpConfig, useMcpTemplates,
  getSkillErrorMessage,
} from '@/api/skills'
import type { McpTemplate, McpTemplateParam } from '@/api/skills'
import { useAuthStore } from '@/stores/authStore'
import { useProjectMembers } from '@/api/projects'

interface McpConfigManagementProps {
  projectId: string
}

export function McpConfigManagement({ projectId }: McpConfigManagementProps) {
  const { data: mcpData, isLoading } = useMcpConfig(projectId)
  const { data: templates } = useMcpTemplates(projectId)
  const updateMcp = useUpdateMcpConfig(projectId)
  const { data: membersData } = useProjectMembers(projectId)
  const user = useAuthStore(state => state.user)
  const currentMember = membersData?.items.find(m => m.user_id === user?.user_id)
  const isViewer = currentMember?.role === 'viewer'

  const [text, setText] = useState('')
  const [parseError, setParseError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)
  const [templateOpen, setTemplateOpen] = useState(false)
  const [selectedTemplate, setSelectedTemplate] = useState<McpTemplate | null>(null)
  const [paramValues, setParamValues] = useState<Record<string, string>>({})

  // 初始化 JSON 文本
  useEffect(() => {
    if (mcpData?.config) {
      setText(JSON.stringify(mcpData.config, null, 2))
    }
  }, [mcpData])

  // 实时 JSON 校验
  useEffect(() => {
    if (!text.trim()) {
      setParseError(null)
      return
    }
    try {
      JSON.parse(text)
      setParseError(null)
    } catch (e) {
      const msg = (e as Error).message
      // 提取行号
      const match = msg.match(/position (\d+)/)
      let lineInfo = ''
      if (match) {
        const pos = parseInt(match[1], 10)
        const lines = text.slice(0, pos).split('\n')
        lineInfo = `第 ${lines.length} 行`
      }
      setParseError(`JSON 格式错误:${lineInfo || msg}`)
    }
  }, [text])

  function handleSave() {
    if (parseError) return
    try {
      const config = JSON.parse(text)
      updateMcp.mutate({ config }, {
        onSuccess: () => setSuccess('保存成功'),
        onError: (err) => setSuccess(getSkillErrorMessage(err)),
      })
    } catch {
      // 校验已在 useEffect 中处理
    }
  }

  function handleSelectTemplate(tpl: McpTemplate) {
    setSelectedTemplate(tpl)
    // 预填默认值
    const defaults: Record<string, string> = {}
    tpl.params.forEach(p => {
      if (p.default !== undefined) defaults[p.name] = String(p.default)
      else defaults[p.name] = ''
    })
    setParamValues(defaults)
  }

  function handleGenerate() {
    if (!selectedTemplate) return
    // 构造模板 JSON:用参数值填充
    const serverConfig: Record<string, unknown> = {
      command: 'npx',
      args: [`-y`, `@modelcontextprotocol/server-${selectedTemplate.name}`],
    }
    // 将参数拼入 args 的 URL 或 env(简化:以 postgres 为例,构造 URL)
    if (selectedTemplate.name === 'postgres') {
      const { host, port, user: u, password, database } = paramValues
      const url = `postgresql://${u}:${password}@${host}:${port || '5432'}/${database}`
      serverConfig.args = ['-y', '@modelcontextprotocol/server-postgres', url]
    }
    const config = { mcpServers: { [selectedTemplate.name]: serverConfig } }
    setText(JSON.stringify(config, null, 2))
    setTemplateOpen(false)
    setSelectedTemplate(null)
  }

  const hintParts = useMemo(() => {
    const parts = '配置将注入到任务容器的 `~/.claude/config.json`'.split('`')
    return parts
  }, [])

  if (isLoading) {
    return <div className="text-text-muted py-8">加载中...</div>
  }

  return (
    <div className="space-y-4">
      {/* 操作栏 */}
      <div className="flex items-center justify-between">
        {/* R2.F8(BUG-UI-068):Tab 内区块标题补 icon(ProjectDetail 设置页内嵌,无独立页壳) */}
        <h2 className="text-lg font-semibold text-text flex items-center gap-2"><Plug size={18} /> MCP 配置</h2>
        <Button variant="outline" size="sm" onClick={() => setTemplateOpen(true)}>
          <FileJson className="w-4 h-4 mr-2" />
          使用模板
        </Button>
      </div>

      {/* JSON 编辑器 */}
      <div className="space-y-2">
        <Textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={20}
          className="font-mono text-sm w-full"
          placeholder='{"mcpServers": {}}'
          readOnly={isViewer}
        />
        {parseError && (
          <Alert variant="error">{parseError}</Alert>
        )}
      </div>

      {/* 底部提示 */}
      <p className="text-sm text-text-muted">
        {hintParts.map((part, i) =>
          i % 2 === 1
            ? <code key={i} className="font-mono text-xs bg-surface-strong px-1 py-0.5 rounded">{part}</code>
            : <span key={i}>{part}</span>
        )}
      </p>

      {success && (
        <Alert variant={success.includes('错误') || success.includes('失败') ? 'error' : 'success'}>
          {success}
        </Alert>
      )}

      {/* 保存按钮 */}
      {!isViewer && (
        <div className="flex justify-end">
          <Button
            size="sm"
            onClick={handleSave}
            disabled={!!parseError || updateMcp.isPending}
          >
            {updateMcp.isPending ? '保存中...' : '保存'}
          </Button>
        </div>
      )}

      {/* 使用模板对话框 */}
      <Dialog open={templateOpen} onOpenChange={setTemplateOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>使用模板</DialogTitle>
            <DialogDescription>选择一个模板快速生成 MCP 配置</DialogDescription>
          </DialogHeader>

          {!selectedTemplate ? (
            <div className="space-y-2 max-h-[400px] overflow-y-auto">
              {(templates ?? []).map(tpl => (
                <button
                  key={tpl.name}
                  className="w-full text-left p-3 border border-border rounded-md hover:bg-surface-strong transition-colors"
                  onClick={() => handleSelectTemplate(tpl)}
                >
                  <div className="font-medium text-text">{tpl.display_name}</div>
                  <div className="text-sm text-text-muted mt-1">{tpl.description}</div>
                </button>
              ))}
              {(templates ?? []).length === 0 && (
                <p className="text-center text-text-muted py-4">暂无模板</p>
              )}
            </div>
          ) : (
            <div className="space-y-4">
              <div className="text-sm text-text-muted">
                模板: <span className="font-medium text-text">{selectedTemplate.display_name}</span>
              </div>
              <div className="space-y-3">
                {selectedTemplate.params.map(param => (
                  <ParamField
                    key={param.name}
                    param={param}
                    value={paramValues[param.name] ?? ''}
                    onChange={(v) => setParamValues(prev => ({ ...prev, [param.name]: v }))}
                  />
                ))}
              </div>
              <DialogFooter>
                <Button variant="ghost" onClick={() => setSelectedTemplate(null)}>
                  返回
                </Button>
                <Button variant="primary" onClick={handleGenerate}>生成</Button>
              </DialogFooter>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  )
}

function ParamField({ param, value, onChange }: {
  param: McpTemplateParam
  value: string
  onChange: (v: string) => void
}) {
  const inputType = param.type === 'number' ? 'number' : param.sensitive ? 'password' : 'text'
  return (
    <div className="space-y-1">
      <Label className="text-sm">
        {param.name}
        {param.required && <span className="text-red-fg ml-1">*</span>}
      </Label>
      <Input
        type={inputType}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={param.default !== undefined ? String(param.default) : ''}
      />
    </div>
  )
}
