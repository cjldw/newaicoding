/**
 * 终端会话 API
 * - 创建/关闭终端会话
 */
import { api } from './client'

export interface TerminalSession {
  session_id: string
  ws_url: string
}

/** 创建终端会话 */
export async function createTerminalSession(
  taskId: string,
  shell = '/bin/bash',
): Promise<TerminalSession> {
  const res = await api.post<TerminalSession>(
    `/tasks/${taskId}/terminal-sessions`,
    { shell },
  )
  return res.data
}

/** 关闭终端会话 */
export async function closeTerminalSession(sessionId: string): Promise<void> {
  await api.delete(`/terminal-sessions/${sessionId}`)
}

/** R26:创建 Runner 宿主 shell 会话(超管;POST /api/admin/runners/{id}/shell-sessions)
 *  R26.F2(BUG-047):force=true → 强制关闭该 Runner 活跃会话后新建(6002 时前端按钮用) */
export async function createRunnerShellSession(runnerId: string, force = false): Promise<TerminalSession> {
  const res = await api.post<TerminalSession>(
    `/admin/runners/${runnerId}/shell-sessions${force ? '?force=true' : ''}`,
    {},
  )
  return res.data
}
