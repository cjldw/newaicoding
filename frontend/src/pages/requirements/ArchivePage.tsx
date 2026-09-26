/**
 * ArchivePage — 需求归档页 /requirements/:reqId/archive
 * 结构:页头(返回 + 标题/状态 + 创建人/时间)+ 时间线卡 + 归档总结卡 + 关联知识条目表卡
 * R33.F6:全页从 shadcn Card/Tailwind 裸混迁移到 vp 统一卡片语言
 * (.card/.card-head/.card-body/.timeline/.tl-item,表格贴卡缘灰底贯通同 manage/*)
 */
import { useMemo } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { Archive, ArrowLeft, Check } from 'lucide-react'
import { Badge } from '@/components/ui/Badge'
import { BreadcrumbOverrideProvider, type CrumbItem } from '@/components/layout/Breadcrumb'
import { useRequirementDetail } from '@/api/requirements'
import {
  Table, TableHeader, TableBody, TableRow, TableHead, TableCell,
} from '@/components/ui/Table'
import {
  useArchive,
  type KnowledgeType,
  type KnowledgeStatus,
  type KnowledgeEntry,
} from '@/api/knowledge'

// 类型徽章映射
const typeBadgeMap: Record<KnowledgeType, { label: string; variant: 'primary' | 'secondary' | 'error' | 'outline' }> = {
  code_snippet: { label: '代码片段', variant: 'primary' },
  pattern: { label: '通用模式', variant: 'secondary' },
  pitfall: { label: '踩坑', variant: 'error' },
  doc: { label: '文档', variant: 'outline' },
}

// 状态徽章映射
const statusBadgeMap: Record<KnowledgeStatus, { label: string; variant: 'outline' | 'success' }> = {
  draft: { label: '草稿', variant: 'outline' },
  published: { label: '已发布', variant: 'success' },
}

function formatTime(iso: string): string {
  if (!iso) return '-'
  const d = new Date(iso)
  if (isNaN(d.getTime())) return iso
  return d.toLocaleString('zh-CN')
}

export default function ArchivePage() {
  const { reqId = '' } = useParams<{ reqId: string }>()
  const nav = useNavigate()
  const { data: archive, isLoading } = useArchive(reqId)
  // R33.F7:面包屑 override —— 项目管理 / {需求标题} / 归档(与需求详情同构;
  // RequirementDetail 无 project_id 字段,项目名链路待后端补字段后升级;数据未就绪退回 pattern 链)
  const { data: req } = useRequirementDetail(reqId)

  const crumbs: CrumbItem[] = useMemo(() => [
    { label: '项目管理', href: '/projects' },
    { label: req?.title ?? '需求', href: `/requirements/${reqId}` },
    { label: '归档' },
  ], [req?.title, reqId])

  if (isLoading) {
    return (
      <div className="page wide">
        <div className="page-loading">加载中...</div>
      </div>
    )
  }
  if (!archive) {
    return (
      <div className="page wide">
        <div className="page-loading">暂无归档数据</div>
      </div>
    )
  }

  // R4 P1 修复:对齐后端 archive_service.get_archive_data 平铺响应(无嵌套 requirement,knowledge 键名)
  const { title, status, created_by, created_at, timeline, summary_file_path, knowledge } = archive

  return (
    <BreadcrumbOverrideProvider crumbs={crumbs}>
    <div className="page wide">
      {/* 返回 + 页头(与需求详情同构) */}
      <button className="btn btn-ghost btn-sm mb-4" onClick={() => nav(-1)}>
        <ArrowLeft size={14} /> 返回
      </button>
      <div className="page-head">
        <div className="flex-1">
          <div className="flex items-center gap-3 mb-2">
            <h1 className="flex items-center gap-2 text-2xl font-semibold text-text"><Archive size={18} /> {title}</h1>
            <Badge variant="outline">{status}</Badge>
          </div>
          <div className="text-sm text-text-muted">
            创建人: {created_by?.nickname || created_by?.username || '-'}
            <span className="mx-2">·</span>
            {formatTime(created_at)}
          </div>
        </div>
      </div>

      {/* 时间线卡(vp .timeline/.tl-item 体系,替换 Tailwind 手绘版) */}
      <div className="card mb-6">
        <div className="card-head"><span className="card-title">时间线</span></div>
        <div className="card-body">
          {timeline.length === 0 ? (
            <div className="empty">暂无时间线数据</div>
          ) : (
            <div className="timeline">
              {timeline.map((node, idx) => (
                <div key={idx} className="tl-item done">
                  <span className="tl-dot"><Check size={11} /></span>
                  <div className="tl-c">
                    <div className="tl-t">
                      <Badge variant="secondary">{node.type}</Badge>{' '}{node.description}
                    </div>
                    <div className="tl-m">
                      {formatTime(node.timestamp)}
                      {node.task_type ? ` · ${node.task_type}` : ''}
                    </div>
                  </div>
                  <span className="when">{formatTime(node.timestamp)}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* 归档总结卡 */}
      <div className="card mb-6">
        <div className="card-head"><span className="card-title">归档总结</span></div>
        <div className="card-body">
          {summary_file_path ? (
            <pre className="md-pre">{summary_file_path}</pre>
          ) : (
            <div className="empty">暂无</div>
          )}
        </div>
      </div>

      {/* 关联知识条目表卡(表格贴卡缘,灰底贯通同 manage/*;BUG-UI-079 口径) */}
      <div className="card mb-6">
        <div className="card-head"><span className="card-title">关联知识条目</span></div>
        {knowledge.length === 0 ? (
          <div className="empty">暂无关联知识条目</div>
        ) : (
          <div className="scrollx">
            <Table className="tbl">
              <TableHeader>
                <TableRow>
                  <TableHead className="w-[100px]">类型</TableHead>
                  <TableHead>标题</TableHead>
                  <TableHead className="w-[180px]">标签</TableHead>
                  <TableHead className="w-[90px]">状态</TableHead>
                  <TableHead className="ops">操作</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {knowledge.map((entry: KnowledgeEntry) => {
                  const tb = typeBadgeMap[entry.type] ?? typeBadgeMap.doc
                  const sb = statusBadgeMap[entry.status] ?? statusBadgeMap.draft
                  return (
                    <TableRow
                      key={entry.entry_id}
                      className="rowclick"
                      onClick={() => nav(entry.project_id
                        ? `/projects/${entry.project_id}/knowledge/${entry.entry_id}`
                        : `/knowledge/${entry.entry_id}`)}
                    >
                      <TableCell>
                        <Badge variant={tb.variant}>{tb.label}</Badge>
                      </TableCell>
                      <TableCell className="font-medium">{entry.title}</TableCell>
                      <TableCell>
                        <div className="flex flex-wrap gap-1">
                          {(entry.tags ?? []).map((tag, i) => (
                            <Badge key={i} variant="default">{tag}</Badge>
                          ))}
                          {(!entry.tags || entry.tags.length === 0) && (
                            <span className="text-text-muted text-sm">-</span>
                          )}
                        </div>
                      </TableCell>
                      <TableCell>
                        <Badge variant={sb.variant}>{sb.label}</Badge>
                      </TableCell>
                      <TableCell className="ops">
                        <button
                          className="btn btn-sm"
                          /* R4:查看接通条目详情(项目级/平台级按 entry.project_id 选路由,同列表卡片口径) */
                          onClick={(e) => {
                            e.stopPropagation()
                            nav(entry.project_id
                              ? `/projects/${entry.project_id}/knowledge/${entry.entry_id}`
                              : `/knowledge/${entry.entry_id}`)
                          }}
                        >
                          查看
                        </button>
                      </TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          </div>
        )}
      </div>
    </div>
    </BreadcrumbOverrideProvider>
  )
}
