/**
 * RelatedUserSelect — R1/R2 共用「关联用户」多选下拉
 * - R1 创建对话框(RequirementList)与 R2 详情编辑对话框(RequirementDetail)共用同一实现
 * - 触发框:复用 .input 类,已选项以 .chip(头像+昵称+×)内嵌展示
 * - 下拉面板:对齐 ProjectDetail 操作菜单写法(bg-surface border-border shadow-lg z-10)
 * - 候选行:头像+昵称+角色徽章(对齐成员管理/邀请候选行样式),支持昵称/用户名搜索
 * - 全部现有 token,零新视觉
 */

import { useState, useEffect, useRef } from 'react'
import { ChevronDown, Check, X } from 'lucide-react'
import { Input } from '@/components/ui/Input'
import { Avatar } from '@/components/ui/Avatar'
import { Badge } from '@/components/ui/Badge'
import type { ProjectMember } from '@/api/projects'

// R1:成员角色徽章映射(与 MemberManagement roleBadgeMap 同口径)
const roleBadgeMap: Record<string, { label: string; variant: 'primary' | 'secondary' | 'outline' }> = {
  owner: { label: '所有者', variant: 'primary' },
  editor: { label: '编辑者', variant: 'secondary' },
  viewer: { label: '观察者', variant: 'outline' },
}

export function RelatedUserSelect({
  members,
  value,
  onChange,
}: {
  members: ProjectMember[]
  value: string[]
  onChange: (ids: string[]) => void
}) {
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState('')
  const wrapRef = useRef<HTMLDivElement>(null)

  // 点击面板外关闭
  useEffect(() => {
    if (!open) return
    function onDocMouseDown(e: MouseEvent) {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onDocMouseDown)
    return () => document.removeEventListener('mousedown', onDocMouseDown)
  }, [open])

  const toggle = (userId: string) => {
    onChange(
      value.includes(userId)
        ? value.filter((id) => id !== userId)
        : [...value, userId],
    )
  }

  // 搜索定位(昵称/用户名,不区分大小写)
  const keyword = search.trim().toLowerCase()
  const candidates = members.filter((m) =>
    !keyword ||
    (m.nickname || '').toLowerCase().includes(keyword) ||
    m.username.toLowerCase().includes(keyword),
  )
  const selectedMembers = value
    .map((id) => members.find((m) => m.user_id === id))
    .filter((m): m is ProjectMember => !!m)

  return (
    <div className="relative" ref={wrapRef}>
      {/* 触发框:已选 chips 内嵌在 .input 框内 */}
      <div
        className="input flex items-center flex-wrap gap-1.5 cursor-pointer min-h-[34px]"
        onClick={() => setOpen((o) => !o)}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') setOpen((o) => !o) }}
      >
        {selectedMembers.length === 0 ? (
          <span className="text-text-muted">选择关联用户(项目成员,可多选)</span>
        ) : (
          selectedMembers.map((m) => (
            <span key={m.user_id} className="chip" onClick={(e) => e.stopPropagation()}>
              <Avatar src={m.avatar_url} alt={m.nickname || m.username} size={16} />
              {m.nickname || m.username}
              <button
                type="button"
                className="hover:text-red-fg"
                aria-label={`移除 ${m.nickname || m.username}`}
                onClick={(e) => { e.stopPropagation(); toggle(m.user_id) }}
              >
                <X className="w-3 h-3" />
              </button>
            </span>
          ))
        )}
        <ChevronDown className="w-4 h-4 text-text-muted ml-auto shrink-0" />
      </div>

      {/* 下拉面板:搜索 + 成员候选列表(头像+昵称+角色徽章+勾选态) */}
      {open && (
        <div className="absolute left-0 right-0 top-full mt-1 z-10 bg-surface border border-border rounded-md shadow-lg overflow-hidden">
          <div className="p-2 border-b border-border">
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="搜索成员(昵称/用户名)"
              className="h-8 text-xs"
            />
          </div>
          <div className="max-h-60 overflow-y-auto py-1">
            {candidates.length === 0 ? (
              <div className="px-3 py-4 text-sm text-text-muted text-center">无匹配成员</div>
            ) : (
              candidates.map((m) => {
                const rb = roleBadgeMap[m.role] ?? roleBadgeMap.viewer
                const checked = value.includes(m.user_id)
                return (
                  <button
                    key={m.user_id}
                    type="button"
                    className="flex w-full items-center gap-2 px-3 py-2 text-sm hover:bg-surface-strong text-text text-left"
                    onClick={() => toggle(m.user_id)}
                  >
                    <Avatar src={m.avatar_url} alt={m.nickname || m.username} size={24} />
                    <span className="flex flex-col min-w-0 flex-1">
                      <span className="truncate">{m.nickname || m.username}</span>
                      {m.nickname && m.username !== m.nickname && (
                        <span className="text-xs text-text-muted truncate">@{m.username}</span>
                      )}
                    </span>
                    <Badge variant={rb.variant}>{rb.label}</Badge>
                    {checked && <Check className="w-4 h-4 text-primary shrink-0" />}
                  </button>
                )
              })
            )}
          </div>
        </div>
      )}
    </div>
  )
}
