/**
 * 四维管理通用页面组件
 * 支持 requirements/dev/test/release 四个维度
 */
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import type { LucideIcon } from 'lucide-react'
import { useDimensionList, type DimensionItem } from '@/api/dashboard'

interface StatusOption {
  value: string
  label: string
}

interface DimensionPageProps {
  dimension: 'requirements' | 'dev' | 'test' | 'release'
  title: string
  statusOptions: StatusOption[]
  /** 页头标题图标(vp pageManage 的 conf.icn) */
  icon?: LucideIcon
  /** 页头标题下方说明行(vp pageManage 的 conf.desc) */
  desc?: string
}

export function DimensionPage({ dimension, title, statusOptions, icon: Icon, desc }: DimensionPageProps) {
  const navigate = useNavigate()
  const [status, setStatus] = useState<string>('')
  const [page, setPage] = useState(1)
  const pageSize = 20

  const { data, isLoading } = useDimensionList(dimension, { status, page, page_size: pageSize })

  const handleRowClick = (item: DimensionItem) => {
    // 根据维度跳转到对应详情页
    if (dimension === 'requirements') {
      navigate(`/requirements/${item.key}`)
    } else {
      navigate(`/tasks/${item.key}`)
    }
  }

  const handleStatusChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    setStatus(e.target.value)
    setPage(1) // 重置到第一页
  }

  const totalPages = data ? Math.ceil(data.total / pageSize) : 1

  return (
    <div className="page wide">
      <div className="page-head">
        <div>
          {/* vp pageManage 结构:icon + 标题,换行,说明(sub) */}
          <h1 className="flex items-center gap-2">
            {Icon && <Icon size={18} />}
            {title}
          </h1>
          {desc && <div className="sub">{desc}</div>}
        </div>
        <div className="acts">
          <select
            className="input"
            style={{ width: 'auto', minWidth: '120px' }}
            value={status}
            onChange={handleStatusChange}
          >
            <option value="">全部状态</option>
            {statusOptions.map(opt => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
        </div>
      </div>

      {isLoading ? (
        <div className="empty">加载中...</div>
      ) : !data || data.items.length === 0 ? (
        <div className="empty">暂无数据</div>
      ) : (
        <>
        <div className="card">
          <div className="scrollx">
            <table className="tbl">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>标题</th>
                  <th>状态</th>
                  <th>所属项目</th>
                  <th>更新时间</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map(item => (
                  <tr key={item.key} className="rowclick" onClick={() => handleRowClick(item)}>
                    <td>
                      <span className="mono">{item.key.slice(0, 8)}</span>
                    </td>
                    <td>{item.title}</td>
                    <td>
                      <span className={`bdg b-${getStatusColor(item.status)}`}>
                        {getStatusText(item.status, statusOptions)}
                      </span>
                    </td>
                    <td>{item.project.name}</td>
                    <td className="muted">{formatDate(item.updated_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="card-foot" style={{ justifyContent: 'center' }}>
            <button
              className="btn"
              disabled={page <= 1}
              onClick={() => setPage(p => Math.max(1, p - 1))}
            >
              上一页
            </button>
            <span className="muted small">
              第 {page} / {totalPages} 页,共 {data.total} 条
            </span>
            <button
              className="btn"
              disabled={page >= totalPages}
              onClick={() => setPage(p => p + 1)}
            >
              下一页
            </button>
          </div>
        </div>
        </>
      )}
    </div>
  )
}

// 辅助函数:根据状态返回颜色
function getStatusColor(status: string): string {
  const colorMap: Record<string, string> = {
    // 需求状态
    draft: 'zinc',
    polishing: 'blue',
    reviewing: 'amber',
    approved: 'green',
    in_progress: 'blue',
    done: 'green',
    archived: 'zinc',
    rejected: 'red',
    // 任务状态
    pending: 'zinc',
    running: 'blue',
    failed: 'red',
    cancelled: 'zinc',
    timeout: 'red',
    // 测试状态
    passed: 'green',
    cases_review: 'amber',
    // 发布状态
    deployed: 'green',
  }
  return colorMap[status] || 'zinc'
}

// 辅助函数:根据状态选项返回文本
function getStatusText(status: string, options: StatusOption[]): string {
  const opt = options.find(o => o.value === status)
  return opt?.label || status
}

// 辅助函数:格式化日期
function formatDate(dateStr: string): string {
  try {
    const date = new Date(dateStr)
    return date.toLocaleString('zh-CN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return dateStr
  }
}
