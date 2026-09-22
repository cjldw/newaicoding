/**
 * ArchivePage — 需求归档页 /requirements/:reqId/archive
 * 结构:页面标题 + 需求信息卡片 + 时间线 + 归档总结 + 关联知识条目 Table
 */
import { useParams } from 'react-router-dom'
import { Card } from '@/components/ui/Card'
import { Badge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
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
  const { data: archive, isLoading } = useArchive(reqId)

  if (isLoading) {
    return <div className="container mx-auto px-4 py-6 text-text-muted">加载中...</div>
  }
  if (!archive) {
    return <div className="container mx-auto px-4 py-6 text-text-muted">暂无归档数据</div>
  }

  const { requirement, timeline, summary_file_path, knowledge_entries } = archive

  return (
    <div className="page wide">
      {/* 页面标题 */}
      <div className="page-head">
        <h1 className="text-2xl font-semibold text-text">需求归档</h1>
      </div>

      {/* 需求信息卡片 */}
      <Card className="p-5 mb-6">
        <div className="flex items-center gap-3 mb-3">
          <h2 className="text-lg font-semibold text-text">{requirement.title}</h2>
          <Badge variant="outline">archived</Badge>
        </div>
        <div className="flex gap-6 text-sm text-text-muted">
          <span>创建人:{requirement.created_by?.nickname ?? requirement.created_by?.username ?? '-'}</span>
          <span>创建时间:{formatTime(requirement.created_at)}</span>
        </div>
      </Card>

      {/* 时间线视图 */}
      <Card className="p-5 mb-6">
        <h3 className="text-base font-semibold text-text mb-4">时间线</h3>
        <div className="relative pl-6">
          {/* 垂直线 */}
          <div className="absolute left-[7px] top-0 bottom-0 w-px bg-border" />
          <div className="flex flex-col" style={{ gap: '16px' }}>
            {timeline.map((node, idx) => (
              <div key={idx} className="relative flex items-start gap-3">
                {/* 节点圆点 */}
                <div className="absolute -left-6 top-1.5 w-3.5 h-3.5 rounded-full bg-primary border-2 border-surface" />
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-0.5">
                    <Badge variant="secondary">{node.type}</Badge>
                    <span className="text-sm text-text">{node.description}</span>
                  </div>
                  <div className="text-xs text-text-muted">
                    {formatTime(node.created_at)}
                    {node.operator ? ` · ${node.operator}` : ''}
                  </div>
                </div>
              </div>
            ))}
            {timeline.length === 0 && (
              <div className="text-sm text-text-muted py-2">暂无时间线数据</div>
            )}
          </div>
        </div>
      </Card>

      {/* 归档总结卡片 */}
      <Card className="p-5 mb-6">
        <h3 className="text-base font-semibold text-text mb-3">归档总结</h3>
        {summary_file_path ? (
          <pre className="text-sm text-text bg-surface-strong rounded p-3 whitespace-pre-wrap font-mono">
            {summary_file_path}
          </pre>
        ) : (
          <div className="text-sm text-text-muted">暂无</div>
        )}
      </Card>

      {/* 关联知识条目列表 */}
      <div className="card">
        <h3 className="text-base font-semibold text-text mb-4">关联知识条目</h3>
        <div className="scrollx">
          <Table className="tbl">
            <TableHeader>
              <TableRow>
                <TableHead className="w-[100px]">类型</TableHead>
                <TableHead>标题</TableHead>
                <TableHead className="w-[180px]">标签</TableHead>
                <TableHead className="w-[90px]">状态</TableHead>
                <TableHead className="w-[80px]">操作</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {knowledge_entries.map((entry: KnowledgeEntry) => {
                const tb = typeBadgeMap[entry.type] ?? typeBadgeMap.doc
                const sb = statusBadgeMap[entry.status] ?? statusBadgeMap.draft
                return (
                  <TableRow key={entry.entry_id}>
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
                    <TableCell>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => {/* 查看:跳详情弹层或展开(预留) */ }}
                      >
                        查看
                      </Button>
                    </TableCell>
                  </TableRow>
                )
              })}
              {knowledge_entries.length === 0 && (
                <TableRow>
                  <TableCell colSpan={5} className="text-center text-text-muted py-8">
                    暂无关联知识条目
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </div>
      </div>
    </div>
  )
}
