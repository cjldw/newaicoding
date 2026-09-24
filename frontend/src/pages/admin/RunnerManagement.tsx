/**
 * RunnerManagement — Runner 管理页(超管,R16)
 * - 标题"Runner 管理" + "新建 Runner"按钮(primary)
 * - Table: 名称/角色徽章/状态徽章/当前容器数/机器信息/最后心跳/操作
 * - 新建 Runner 对话框(名称/角色/最大容器数/deploy 时公网 IP)
 * - 创建成功对话框(token + 启动命令示例,宽 600px)
 * - 重置 token 确认对话框
 */

import { useState } from 'react'
import { Plus, Copy, RefreshCcw, Ban, Trash2, Server, Terminal, Play, Square, RotateCcw } from 'lucide-react'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { Label } from '@/components/ui/Label'
import { Select } from '@/components/ui/Select'
import { Alert } from '@/components/ui/Alert'
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from '@/components/ui/Table'
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from '@/components/ui/Dialog'
import { TerminalPanel } from '@/components/TerminalPanel'
import {
  useRunners, useCreateRunner, useResetRunnerToken, useDisableRunner, useDeleteRunner,
  useCreateLocalRunner, useStartRunner, useStopRunner, useRestartRunner,
  getRunnerErrorMessage,
} from '@/api/admin/runners'
import { createRunnerShellSession, closeTerminalSession, type TerminalSession } from '@/api/terminal'
import type { Runner } from '@/api/admin/runners'

const ROLE_OPTIONS = [
  { label: '工作节点(跑任务容器)', value: 'worker' },
  { label: '部署节点(跑部署容器,需公网 IP)', value: 'deploy' },
]
// 角色徽章:worker → b-zinc,deploy → b-blue
const ROLE_BADGE: Record<string, { label: string; cls: string }> = {
  worker: { label: '工作节点', cls: 'bdg b-zinc' },
  deploy: { label: '部署节点', cls: 'bdg b-blue' },
}
// 状态徽章:online → b-green,offline → b-amber,disabled → b-zinc
const STATUS_BADGE: Record<string, { label: string; cls: string }> = {
  online: { label: '在线', cls: 'bdg b-green' },
  offline: { label: '离线', cls: 'bdg b-amber' },
  disabled: { label: '禁用', cls: 'bdg b-zinc' },
}

function formatTime(s: string | null) {
  if (!s) return '-'
  return new Date(s).toLocaleString('zh-CN')
}

function formatMachine(r: Runner) {
  const m = r.machine_info
  if (!m) return '-'
  // R16.F4(BUG-045):两行展示——行1 资源容量;行2 环境(仅新字段存在时渲染,
  // 旧 runner 数据只有既有字段则优雅降级为一行)
  const line1 =
    `CPU ${m.cpu_count} 核 / 内存 ${m.mem_total_gb}GB` +
    (m.disk_total_gb != null ? ` / 磁盘 ${m.disk_total_gb}GB` : '')
  const line2 = [m.os_version, m.hostname, m.ip].filter(Boolean).join(' · ')
  return (
    <span>
      {line1}
      {line2 ? (
        <>
          <br />
          <span className="text-xs">{line2}</span>
        </>
      ) : null}
    </span>
  )
}

export function RunnerManagement() {
  const { data: runners, isLoading } = useRunners()
  const createRunner = useCreateRunner()
  const resetToken = useResetRunnerToken()
  const disableRunner = useDisableRunner()
  const deleteRunner = useDeleteRunner()
  // R31:本机快速创建与生命周期
  const createLocalRunner = useCreateLocalRunner()
  const startRunner = useStartRunner()
  const stopRunner = useStopRunner()
  const restartRunner = useRestartRunner()

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

  // R31:快速创建弹窗(名称/最大容器数)+ 提交 pending;本机行操作 pending(runner_id)
  const [localOpen, setLocalOpen] = useState(false)
  const [localForm, setLocalForm] = useState({ name: '', max_containers: 10 })
  const [localErr, setLocalErr] = useState<string | null>(null)
  const [localBusy, setLocalBusy] = useState(false)
  const [runnerBusy, setRunnerBusy] = useState<string | null>(null)
  // R31:本机删除二次确认(代停语义提示)
  const [localDeleteTarget, setLocalDeleteTarget] = useState<Runner | null>(null)

  // R26:Runner 宿主终端(shell 会话;并发上限 1 由后端 6002 把关)
  const [shellRunner, setShellRunner] = useState<Runner | null>(null)
  const [shellSession, setShellSession] = useState<TerminalSession | null>(null)
  const [shellErr, setShellErr] = useState<string | null>(null)
  // R26.F2(BUG-047):记录创建失败的业务码;6002 时 Dialog 内提供「强制关闭并新建」
  const [shellErrCode, setShellErrCode] = useState<number | null>(null)
  const [shellOpening, setShellOpening] = useState(false)

  /** 打开终端:先 POST 建会话(按钮 loading 至返回);失败在 Dialog 内展示 6001/6002/6003 文案;
   *  force=true(R26.F2)→ 后端先强制关闭该 Runner 活跃会话再新建 */
  async function openShell(r: Runner, force = false) {
    setShellOpening(true)
    setShellErr(null)
    setShellErrCode(null)
    setShellSession(null)
    setShellRunner(r)
    try {
      setShellSession(await createRunnerShellSession(r.runner_id, force))
    } catch (e) {
      setShellErr(getRunnerErrorMessage(e) || '终端创建失败')
      setShellErrCode((e as { code?: number })?.code ?? null)
    } finally {
      setShellOpening(false)
    }
  }

  /** Dialog 关闭:WS close → 销毁会话(Runner 侧 kill pty;无残留) */
  function closeShellDialog() {
    if (shellSession) closeTerminalSession(shellSession.session_id).catch(() => {})
    setShellRunner(null)
    setShellSession(null)
    setShellErr(null)
  }

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

  // ---- R31:本机快速创建 / 启动 / 停止 / 重启 / 代停删除 ----

  /** 快速创建提交:错误直显后端 message(16002 细分文案);Dialog 不关、输入保留 */
  async function handleCreateLocal() {
    setLocalBusy(true)
    setLocalErr(null)
    try {
      const res = await createLocalRunner.mutateAsync({
        name: localForm.name.trim() || undefined,
        max_containers: localForm.max_containers,
      })
      setLocalOpen(false)
      const st = res.data.status
      setMsg({
        type: 'success',
        text: st === 'online' ? `Runner ${res.data.name} 已创建并上线` : `Runner 已启动但未完成注册,可在列表查看状态或重试启动`,
      })
    } catch (e) {
      setLocalErr(getRunnerErrorMessage(e))
    } finally {
      setLocalBusy(false)
    }
  }

  async function handleStart(r: Runner) {
    setRunnerBusy(r.runner_id)
    try { await startRunner.mutateAsync(r.runner_id); setMsg({ type: 'success', text: 'Runner 已启动' }) }
    catch (e) { setMsg({ type: 'error', text: getRunnerErrorMessage(e) }) }
    finally { setRunnerBusy(null) }
  }

  /** 停止无二次确认(分片交互流程:秒级操作;防重=按钮 disabled+busy) */
  async function handleStop(r: Runner) {
    setRunnerBusy(r.runner_id)
    try { await stopRunner.mutateAsync(r.runner_id); setMsg({ type: 'success', text: 'Runner 已停止' }) }
    catch (e) { setMsg({ type: 'error', text: getRunnerErrorMessage(e) }) }
    finally { setRunnerBusy(null) }
  }

  async function handleRestart(r: Runner) {
    setRunnerBusy(r.runner_id)
    try { await restartRunner.mutateAsync(r.runner_id); setMsg({ type: 'success', text: 'Runner 已重启' }) }
    catch (e) { setMsg({ type: 'error', text: getRunnerErrorMessage(e) }) }
    finally { setRunnerBusy(null) }
  }

  /** 本机行删除 = 代停流程(先停全部容器),长 pending(≤60s) */
  async function handleLocalDeleteConfirmed() {
    if (!localDeleteTarget) return
    const r = localDeleteTarget
    setRunnerBusy(r.runner_id)
    try {
      await deleteRunner.mutateAsync(r.runner_id)
      setLocalDeleteTarget(null)
      setMsg({ type: 'success', text: 'Runner 已删除' })
    } catch (e) {
      // 16004:代停失败,runner 保留;留在确认框外的全局错误 + 关闭确认框
      setLocalDeleteTarget(null)
      setMsg({ type: 'error', text: getRunnerErrorMessage(e) })
    } finally {
      setRunnerBusy(null)
    }
  }

  function copyToken(t: string) { navigator.clipboard.writeText(t) }

  const startupCmd = `docker run -d \\
  -e PLATFORM_URL=wss://platform.example.com/ws/runner \\
  -e RUNNER_TOKEN=${createdToken || 'plt-runner-xxx'} \\
  -v /var/run/docker.sock:/var/run/docker.sock \\
  --name ${createdName || 'runner-beijing-01'} \\
  platform/runner:v1`

  return (
    <div className="page wide">
      <div className="page-head">
        {/* vp L1569 结构:icon + 标题,换行,说明(sub) */}
        <div>
          <h1 className="flex items-center gap-2"><Server size={18} /> Runner 管理</h1>
          <div className="sub">Runner 是容器执行的代理节点,主动 WebSocket 连接平台;调度策略:最少负载 · 部署任务固定 role=deploy</div>
        </div>
        <div className="acts">
          {/* R31:本机快速创建(与远程 token 流程并存) */}
          <Button variant="primary" onClick={() => { setLocalForm({ name: '', max_containers: 10 }); setLocalErr(null); setLocalOpen(true) }}>
            <Plus className="w-4 h-4 mr-1" />快速创建(本机)
          </Button>
          <Button variant="primary" onClick={openCreate}><Plus className="w-4 h-4 mr-1" />新建 Runner</Button>
        </div>
      </div>
      {msg && <Alert variant={msg.type} onClose={() => setMsg(null)}>{msg.text}</Alert>}
      {/* §6.3 #1:加 .card > .scrollx 包裹,对齐 /admin/users 模式 */}
      <div className="card">
      <div className="scrollx">
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
              const busy = runnerBusy === r.runner_id
              return (
                /* §6.3 #2:移除 opacity-50,改用 .b-amber 徽章区分 offline */
                <TableRow key={r.runner_id}>
                  <TableCell className="font-medium">{r.name}</TableCell>
                  <TableCell><span className={rb.cls}>{rb.label}</span></TableCell>
                  <TableCell>
                    <span className={sb.cls}>{sb.label}</span>
                    {/* R31:本机快速创建标记 chip */}
                    {r.is_local && <span className="chip" style={{ marginLeft: 6 }}>本机</span>}
                  </TableCell>
                  <TableCell>{r.current_containers}/{r.max_containers}</TableCell>
                  <TableCell className="text-text-muted">{formatMachine(r)}</TableCell>
                  <TableCell className="text-text-muted">{formatTime(r.last_heartbeat_at)}</TableCell>
                  <TableCell className="text-right" style={{ whiteSpace: 'nowrap' }}>
                    {/* §6.3 #3:操作按钮改 .btn.btn-sm / .btn.btn-sm.btn-danger */}
                    {/* R26:终端按钮(仅 online 可点;非 online 置灰 title 提示)——本机/远程均可用 */}
                    <button
                      className="btn btn-sm"
                      disabled={r.status !== 'online' || shellOpening}
                      title={r.status !== 'online' ? 'Runner 不在线' : undefined}
                      onClick={() => openShell(r)}
                    ><Terminal className="w-3.5 h-3.5 mr-1" />终端</button>
                    {' '}
                    {r.is_local ? (
                      /* R31:本机行——启动/停止/重启/删除(代停确认);无 重置token/禁用(token 内部化) */
                      <>
                        {r.status === 'online' ? (
                          <>
                            <button className="btn btn-sm" disabled={busy} title="停止 runner 进程(容器不动)" onClick={() => handleStop(r)}><Square className="w-3.5 h-3.5 mr-1" />{busy ? '停止中…' : '停止'}</button>
                            {' '}
                            <button className="btn btn-sm" disabled={busy} onClick={() => handleRestart(r)}><RotateCcw className="w-3.5 h-3.5 mr-1" />{busy ? '重启中…' : '重启'}</button>
                          </>
                        ) : r.status === 'offline' ? (
                          <button className="btn btn-sm" disabled={busy} onClick={() => handleStart(r)}><Play className="w-3.5 h-3.5 mr-1" />{busy ? '启动中…' : '启动'}</button>
                        ) : (
                          <>
                            <button className="btn btn-sm" disabled title="已禁用的 Runner 不可启动"><Play className="w-3.5 h-3.5 mr-1" />启动</button>
                            {' '}
                            <button className="btn btn-sm" disabled title="已禁用的 Runner 不可停止"><Square className="w-3.5 h-3.5 mr-1" />停止</button>
                          </>
                        )}
                        {' '}
                        <button className="btn btn-sm btn-danger" disabled={busy} onClick={() => setLocalDeleteTarget(r)}><Trash2 className="w-3.5 h-3.5 mr-1" />删除</button>
                      </>
                    ) : (
                      /* 远程行:R16 原操作,零改动 */
                      <>
                        <button className="btn btn-sm" onClick={() => { setResetTarget(r); setResetOpen(true) }}><RefreshCcw className="w-3.5 h-3.5 mr-1" />重置 token</button>
                        {' '}
                        <button className="btn btn-sm" onClick={() => handleDisable(r)}><Ban className="w-3.5 h-3.5 mr-1" />禁用</button>
                        {' '}
                        <button className="btn btn-sm btn-danger" onClick={() => handleDelete(r)}><Trash2 className="w-3.5 h-3.5 mr-1" />删除</button>
                      </>
                    )}
                  </TableCell>
                </TableRow>
              )
            })}
            {!isLoading && !runners?.length && <TableRow><TableCell colSpan={7} className="text-center py-8 text-text-muted">暂无 Runner</TableCell></TableRow>}
          </TableBody>
        </Table>
      </div>
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

      {/* R31:快速创建本机 Runner(最小表单:名称留空自动生成 + 最大容器数;token 平台内部注入不可见) */}
      <Dialog open={localOpen} onOpenChange={(o) => { if (!o) { setLocalOpen(false); setLocalErr(null) } }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>快速创建本机 Runner</DialogTitle>
            <DialogDescription>在本机直接启动 runner 进程并注册上线;无需复制 token</DialogDescription>
          </DialogHeader>
          {localErr && <Alert variant="error" className="mt-2">{localErr}</Alert>}
          <div className="space-y-4 pt-2">
            <div className="space-y-1.5"><Label>名称</Label><Input placeholder="留空自动生成 local-xxxxxxxx" value={localForm.name} onChange={e => setLocalForm(f => ({ ...f, name: e.target.value }))} /></div>
            <div className="space-y-1.5"><Label>最大容器数</Label><Input type="number" min={1} max={100} value={localForm.max_containers} onChange={e => setLocalForm(f => ({ ...f, max_containers: Number(e.target.value) || 10 }))} /></div>
          </div>
          <DialogFooter className="pt-4">
            <Button variant="ghost" onClick={() => { setLocalOpen(false); setLocalErr(null) }}>取消</Button>
            <Button variant="primary" disabled={localBusy} onClick={handleCreateLocal}>{localBusy ? '启动中…' : '创建并启动'}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* R31:本机删除二次确认(代停语义提示;远程行维持直删无确认) */}
      <Dialog open={!!localDeleteTarget} onOpenChange={(o) => { if (!o) setLocalDeleteTarget(null) }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>删除本机 Runner</DialogTitle>
            <DialogDescription>本机 Runner 将先停止其全部任务容器再删除,确认?</DialogDescription>
          </DialogHeader>
          <DialogFooter className="pt-4">
            <Button variant="ghost" onClick={() => setLocalDeleteTarget(null)}>取消</Button>
            <Button variant="primary" disabled={!!localDeleteTarget && runnerBusy === localDeleteTarget.runner_id} onClick={handleLocalDeleteConfirmed}>
              {localDeleteTarget && runnerBusy === localDeleteTarget.runner_id ? '停止容器中…' : '确认删除'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* R26:Runner 宿主终端(Dialog 80vw×80vh;xterm 容器 --term-bg 由 Terminal 组件处理;
          断线写"Runner 连接中断"且不自动重连(terminalReconnect=false) */}
      <Dialog open={!!shellRunner} onOpenChange={(o) => { if (!o) closeShellDialog() }}>
        <DialogContent className="w-[80vw] max-w-[80vw]">
          <DialogHeader>
            <DialogTitle>Runner 终端 · {shellRunner?.name}</DialogTitle>
            <DialogDescription>Runner 容器内 shell;关闭对话框即销毁会话</DialogDescription>
          </DialogHeader>
          {shellErr ? (
            <div className="pt-2">
              <Alert variant="error">{shellErr}</Alert>
              <DialogFooter className="pt-4">
                {/* R26.F2(BUG-047):6002=已有会话未关 → 提供「强制关闭并新建」一键代清 */}
                {shellErrCode === 6002 && shellRunner && (
                  <Button
                    variant="primary"
                    disabled={shellOpening}
                    onClick={() => openShell(shellRunner, true)}
                  >强制关闭并新建</Button>
                )}
                <Button variant="ghost" onClick={closeShellDialog}>关闭</Button>
              </DialogFooter>
            </div>
          ) : shellSession ? (
            <div className="h-[70vh] min-h-0 flex flex-col">
              <TerminalPanel
                createSession={async () => shellSession}
                onClose={(sid) => { closeTerminalSession(sid).catch(() => {}) }}
                terminalReconnect={false}
                terminalCloseMessage="Runner 连接中断"
              />
            </div>
          ) : (
            <div className="py-10 text-center text-sm text-text-muted">正在建立会话…</div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  )
}
