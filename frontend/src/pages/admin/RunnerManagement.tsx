/**
 * RunnerManagement — Runner 管理页(超管,R16)
 * - 标题"Runner 管理" + "新建 Runner"按钮(primary)
 * - Table: 名称/角色徽章/状态徽章/当前容器数/机器信息/最后心跳/操作
 * - 新建 Runner 对话框(名称/角色/最大容器数/deploy 时公网 IP)
 * - 创建成功对话框(token + 启动命令示例,宽 600px)
 * - 重置 token 确认对话框
 */

import { useState } from 'react'
import { Plus, Copy, RefreshCcw, Ban, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Label } from '@/components/ui/Label'
import { Select } from '@/components/ui/Select'
import { Badge } from '@/components/ui/Badge'
import { Alert } from '@/components/ui/Alert'
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from '@/components/ui/Table'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/Dialog'
import {
  useRunners, useCreateRunner, useResetRunnerToken, useDisableRunner, useDeleteRunner,
  getRunnerErrorMessage,
} from '@/api/admin/runners'
import type { Runner } from '@/api/admin/runners'

const ROLE_OPTIONS = [
  { label: '工作节点(跑任务容器)', value: 'worker' },
  { label: '部署节点(跑部署容器,需公网 IP)', value: 'deploy' },
]
const ROLE_BADGE: Record<string, { label: string; variant: 'secondary' | 'primary' }> = {
  worker: { label: '工作节点', variant: 'secondary' },
  deploy: { label: '部署节点', variant: 'primary' },
}
const STATUS_BADGE: Record<string, { label: string; variant: 'success' | 'secondary' | 'outline' }> = {
  online: { label: '在线', variant: 'success' },
  offline: { label: '离线', variant: 'secondary' },
  disabled: { label: '禁用', variant: 'outline' },
}

function formatTime(s: string | null) {
  if (!s) return '-'
  return new Date(s).toLocaleString('zh-CN')
}

function formatMachine(r: Runner) {
  const m = r.machine_info
  if (!m) return '-'
  return `CPU ${m.cpu_count} 核 / 内存 ${m.mem_total_gb}GB`
}

export function RunnerManagement() {
  const { data: runners, isLoading } = useRunners()
  const createRunner = useCreateRunner()
  const resetToken = useResetRunnerToken()
  const disableRunner = useDisableRunner()
  const deleteRunner = useDeleteRunner()

  const [createOpen, setCreateOpen] = useState(false)
  const [successOpen, setSuccessOpen] = useState(false)
  const [resetOpen, setResetOpen] = useState(false)
  const [resetSuccessOpen, setResetSuccessOpen] = useState(false)
  const [form, setForm] = useState({ name: '', role: 'worker' as 'worker' | 'deploy', max_containers: 10, public_ip: '' })
  const [createdToken, setCreatedToken] = useState('')
  const [createdName, setCreatedName] = useState('')
  const [resetTokenValue, setResetTokenValue] = useState('')
  const [resetTarget, setResetTarget] = useState<Runner | null>(null)
  const [msg, setMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null)

  function openCreate() {
    setForm({ name: '', role: 'worker', max_containers: 10, public_ip: '' })
    setCreateOpen(true)
  }

  async function handleCreate() {
    if (!form.name.trim()) { setMsg({ type: 'error', text: '名称不能为空' }); return }
    if (form.role === 'deploy' && !form.public_ip.trim()) { setMsg({ type: 'error', text: '公网 IP 不能为空' }); return }
    try {
      const payload = { name: form.name.trim(), role: form.role, max_containers: form.max_containers, ...(form.role === 'deploy' ? { public_ip: form.public_ip.trim() } : {}) }
      const res = await createRunner.mutateAsync(payload)
      setCreatedToken(res.data.token)
      setCreatedName(res.data.name)
      setCreateOpen(false)
      setSuccessOpen(true)
      setMsg({ type: 'success', text: 'Runner 创建成功' })
    } catch (e) { setMsg({ type: 'error', text: getRunnerErrorMessage(e) }) }
  }

  async function handleResetConfirm() {
    if (!resetTarget) return
    try {
      const res = await resetToken.mutateAsync(resetTarget.runner_id)
      setResetTokenValue(res.data.token)
      setResetOpen(false)
      setResetSuccessOpen(true)
      setMsg({ type: 'success', text: 'token 已重置,旧 token 已失效' })
    } catch (e) { setMsg({ type: 'error', text: getRunnerErrorMessage(e) }) }
  }

  async function handleDisable(r: Runner) {
    try { await disableRunner.mutateAsync(r.runner_id); setMsg({ type: 'success', text: 'Runner 已禁用' }) }
    catch (e) { setMsg({ type: 'error', text: getRunnerErrorMessage(e) }) }
  }

  async function handleDelete(r: Runner) {
    try { await deleteRunner.mutateAsync(r.runner_id); setMsg({ type: 'success', text: 'Runner 已删除' }) }
    catch (e) { setMsg({ type: 'error', text: getRunnerErrorMessage(e) }) }
  }

  function copyToken(t: string) { navigator.clipboard.writeText(t) }

  const startupCmd = `docker run -d \\
  -e PLATFORM_URL=wss://platform.example.com/ws/runner \\
  -e RUNNER_TOKEN=${createdToken || 'plt-runner-xxx'} \\
  -v /var/run/docker.sock:/var/run/docker.sock \\
  --name ${createdName || 'runner-beijing-01'} \\
  platform/runner:v1`

  return (
    <div className="page">
      <div className="page-head">
        <h1>Runner 管理</h1>
        <div className="acts">
          <Button variant="primary" onClick={openCreate}><Plus className="w-4 h-4 mr-1" />新建 Runner</Button>
        </div>
      </div>
      {msg && <Alert variant={msg.type} onClose={() => setMsg(null)}>{msg.text}</Alert>}
      <div className="border border-border rounded-lg overflow-hidden">
        <Table className="tbl">
          <TableHeader>
            <TableRow>
              <TableHead>名称</TableHead><TableHead>角色</TableHead><TableHead>状态</TableHead>
              <TableHead>当前容器数</TableHead><TableHead>机器信息</TableHead><TableHead>最后心跳</TableHead>
              <TableHead className="text-right">操作</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading && <TableRow><TableCell colSpan={7} className="text-center py-8 text-text-muted">加载中…</TableCell></TableRow>}
            {runners?.map(r => {
              const rb = ROLE_BADGE[r.role]; const sb = STATUS_BADGE[r.status]
              return (
                <TableRow key={r.runner_id} className={r.status === 'offline' ? 'opacity-50' : ''}>
                  <TableCell className="font-medium">{r.name}</TableCell>
                  <TableCell><Badge variant={rb.variant}>{rb.label}</Badge></TableCell>
                  <TableCell><Badge variant={sb.variant}>{sb.label}</Badge></TableCell>
                  <TableCell>{r.current_containers}/{r.max_containers}</TableCell>
                  <TableCell className="text-text-muted">{formatMachine(r)}</TableCell>
                  <TableCell className="text-text-muted">{formatTime(r.last_heartbeat_at)}</TableCell>
                  <TableCell className="text-right space-x-2">
                    <Button variant="ghost" size="sm" onClick={() => { setResetTarget(r); setResetOpen(true) }}><RefreshCcw className="w-3.5 h-3.5 mr-1" />重置 token</Button>
                    <Button variant="ghost" size="sm" onClick={() => handleDisable(r)}><Ban className="w-3.5 h-3.5 mr-1" />禁用</Button>
                    <Button variant="danger" size="sm" onClick={() => handleDelete(r)}><Trash2 className="w-3.5 h-3.5 mr-1" />删除</Button>
                  </TableCell>
                </TableRow>
              )
            })}
            {!isLoading && !runners?.length && <TableRow><TableCell colSpan={7} className="text-center py-8 text-text-muted">暂无 Runner</TableCell></TableRow>}
          </TableBody>
        </Table>
      </div>

      {/* 新建 Runner 对话框 */}
      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent>
          <DialogHeader><DialogTitle>新建 Runner</DialogTitle><DialogDescription>创建一个新的 Runner 节点</DialogDescription></DialogHeader>
          <div className="space-y-4 pt-2">
            <div className="space-y-1.5"><Label>名称</Label><Input placeholder="如:runner-beijing-01" value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} /></div>
            <div className="space-y-1.5"><Label>角色</Label><Select options={ROLE_OPTIONS} value={form.role} onChange={e => setForm(f => ({ ...f, role: e.target.value as 'worker' | 'deploy' }))} /></div>
            <div className="space-y-1.5"><Label>最大容器数</Label><Input type="number" value={form.max_containers} onChange={e => setForm(f => ({ ...f, max_containers: Number(e.target.value) || 10 }))} /></div>
            {form.role === 'deploy' && <div className="space-y-1.5"><Label>公网 IP</Label><Input placeholder="部署 URL 将指向该 IP" value={form.public_ip} onChange={e => setForm(f => ({ ...f, public_ip: e.target.value }))} /></div>}
          </div>
          <DialogFooter className="pt-4"><Button variant="ghost" onClick={() => setCreateOpen(false)}>取消</Button><Button variant="primary" onClick={handleCreate}>创建</Button></DialogFooter>
        </DialogContent>
      </Dialog>

      {/* 创建成功对话框 */}
      <Dialog open={successOpen} onOpenChange={setSuccessOpen}>
        <DialogContent className="w-[600px]">
          <DialogHeader><DialogTitle>Runner 创建成功</DialogTitle><DialogDescription>请保存 token(仅显示一次)</DialogDescription></DialogHeader>
          <div className="space-y-4 pt-2">
            <div className="flex items-center gap-2"><code className="flex-1 font-mono text-sm bg-surface-strong border border-border rounded px-3 py-2 break-all">{createdToken}</code><Button variant="ghost" size="sm" onClick={() => copyToken(createdToken)}><Copy className="w-3.5 h-3.5 mr-1" />点击复制</Button></div>
            <div className="space-y-1.5"><Label>启动命令示例</Label><pre className="font-mono text-xs bg-surface-strong border border-border rounded p-3 overflow-x-auto whitespace-pre">{startupCmd}</pre></div>
          </div>
          <DialogFooter className="pt-2"><Button variant="primary" onClick={() => setSuccessOpen(false)}>关闭</Button></DialogFooter>
        </DialogContent>
      </Dialog>

      {/* 重置 token 确认 */}
      <Dialog open={resetOpen} onOpenChange={setResetOpen}>
        <DialogContent>
          <DialogHeader><DialogTitle>重置 token</DialogTitle><DialogDescription>重置后旧 token 将失效,Runner 需用新 token 重启</DialogDescription></DialogHeader>
          <DialogFooter className="pt-4"><Button variant="ghost" onClick={() => setResetOpen(false)}>取消</Button><Button variant="primary" onClick={handleResetConfirm}>确定</Button></DialogFooter>
        </DialogContent>
      </Dialog>

      {/* 重置成功 */}
      <Dialog open={resetSuccessOpen} onOpenChange={setResetSuccessOpen}>
        <DialogContent className="w-[600px]">
          <DialogHeader><DialogTitle>token 已重置</DialogTitle><DialogDescription>请保存新 token(仅显示一次)</DialogDescription></DialogHeader>
          <div className="flex items-center gap-2 pt-2"><code className="flex-1 font-mono text-sm bg-surface-strong border border-border rounded px-3 py-2 break-all">{resetTokenValue}</code><Button variant="ghost" size="sm" onClick={() => copyToken(resetTokenValue)}><Copy className="w-3.5 h-3.5 mr-1" />点击复制</Button></div>
          <DialogFooter className="pt-2"><Button variant="primary" onClick={() => setResetSuccessOpen(false)}>关闭</Button></DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
