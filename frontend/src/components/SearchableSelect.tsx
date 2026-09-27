/**
 * SearchableSelect — 通用单选可搜索下拉(R3.2)
 * - 参考实现:RelatedUserSelect(搜索面板交互);触发框复用 .input 类,零新视觉
 * - 下拉面板:对齐 ProjectDetail 操作菜单写法(bg-surface border-border shadow-lg z-10)
 * - 搜索走后端:keyword 经 useDebounce(300ms) 后调 fetchOptions,空 keyword 返回前 20 条
 * - 状态:加载中「加载中...」/ 空态 emptyText / 无匹配 noMatchText / 失败 errorText
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import { ChevronDown, Check } from 'lucide-react'
import { Input } from '@/components/ui/Input'
import { useDebounce } from '@/hooks/useDebounce'

export interface SearchableSelectOption {
  value: string
  /** 触发框与选项行主文案 */
  label: string
  /** 选项行次文案(可选,次行小字) */
  description?: string
  /** 选项行右侧徽章(可选) */
  badge?: React.ReactNode
}

interface SearchableSelectProps {
  /** 当前已选项(null = 未选,显示 placeholder) */
  value: SearchableSelectOption | null
  /** 选中回调(单选;选中后面板关闭) */
  onChange: (option: SearchableSelectOption) => void
  /**
   * 后端搜索函数:q 为空串时返回默认列表(前 20 条)。
   * 注意:组件按「每次展开都重新拉取」处理,函数体内部无需缓存
   */
  fetchOptions: (q: string) => Promise<SearchableSelectOption[]>
  /** 触发框 placeholder */
  placeholder?: string
  /** 面板搜索框 placeholder */
  searchPlaceholder?: string
  /** 空态文案(无关键词且列表为空) */
  emptyText?: string
  /** 搜索无匹配文案(有关键词但结果为空) */
  noMatchText?: string
  /** 搜索接口失败文案 */
  errorText?: string
  /** 禁用态(如:未选项目时的需求选择器) */
  disabled?: boolean
  /** 禁用态触发框文案(缺省用 placeholder) */
  disabledPlaceholder?: string
}

export function SearchableSelect({
  value,
  onChange,
  fetchOptions,
  placeholder = '请选择',
  searchPlaceholder = '搜索',
  emptyText = '暂无数据',
  noMatchText = '无匹配结果',
  errorText = '搜索失败,请重试',
  disabled = false,
  disabledPlaceholder,
}: SearchableSelectProps) {
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState('')
  const [options, setOptions] = useState<SearchableSelectOption[]>([])
  const [loading, setLoading] = useState(false)
  const [failed, setFailed] = useState(false)
  const wrapRef = useRef<HTMLDivElement>(null)
  // R3.2:debounce 300ms 后调后端搜索(规格要求)
  const debouncedSearch = useDebounce(search.trim(), 300)

  // 点击面板外关闭
  useEffect(() => {
    if (!open) return
    function onDocMouseDown(e: MouseEvent) {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onDocMouseDown)
    return () => document.removeEventListener('mousedown', onDocMouseDown)
  }, [open])

  // 展开/关键词变化 → 拉取列表;cancelled 标记防过期响应覆盖新结果
  useEffect(() => {
    if (!open) return
    let cancelled = false
    setLoading(true)
    setFailed(false)
    fetchOptions(debouncedSearch)
      .then((items) => {
        if (cancelled) return
        setOptions(items)
      })
      .catch(() => {
        if (cancelled) return
        setOptions([])
        setFailed(true)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [open, debouncedSearch, fetchOptions])

  // 每次展开重置搜索词,显示默认前 20 条
  const toggleOpen = useCallback(() => {
    setOpen((prev) => {
      if (!prev) setSearch('')
      return !prev
    })
  }, [])

  const pick = (option: SearchableSelectOption) => {
    onChange(option)
    setOpen(false)
  }

  const keyword = debouncedSearch

  return (
    <div className="relative" ref={wrapRef}>
      {/* 触发框:复用 .input 类,显示已选值 + 下拉箭头 */}
      <div
        className={`input flex items-center justify-between gap-2 cursor-pointer min-h-[34px] ${
          disabled ? 'opacity-60 cursor-not-allowed' : ''
        }`}
        onClick={() => { if (!disabled) toggleOpen() }}
        role="button"
        tabIndex={disabled ? -1 : 0}
        aria-disabled={disabled}
        onKeyDown={(e) => {
          if (disabled) return
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault()
            toggleOpen()
          }
        }}
      >
        {value ? (
          <span className="truncate">{value.label}</span>
        ) : (
          <span className="text-text-muted">{disabled ? (disabledPlaceholder ?? placeholder) : placeholder}</span>
        )}
        <ChevronDown className="w-4 h-4 text-text-muted ml-auto shrink-0" />
      </div>

      {/* 下拉面板:搜索框 + 滚动列表(max-h-60) */}
      {open && (
        <div className="absolute left-0 right-0 top-full mt-1 z-10 bg-surface border border-border rounded-md shadow-lg overflow-hidden">
          <div className="p-2 border-b border-border">
            <Input
              autoFocus
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder={searchPlaceholder}
              className="h-8 text-xs"
            />
          </div>
          <div className="max-h-60 overflow-y-auto py-1">
            {loading ? (
              <div className="px-3 py-4 text-sm text-text-muted text-center">加载中...</div>
            ) : failed ? (
              <div className="px-3 py-4 text-sm text-red-fg text-center">{errorText}</div>
            ) : options.length === 0 ? (
              <div className="px-3 py-4 text-sm text-text-muted text-center">
                {keyword ? noMatchText : emptyText}
              </div>
            ) : (
              options.map((opt) => {
                const checked = value?.value === opt.value
                return (
                  <button
                    key={opt.value}
                    type="button"
                    className="flex w-full items-center gap-2 px-3 py-2 text-sm hover:bg-surface-strong text-text text-left"
                    onClick={() => pick(opt)}
                  >
                    <span className="flex flex-col min-w-0 flex-1">
                      <span className="truncate">{opt.label}</span>
                      {opt.description && (
                        <span className="text-xs text-text-muted truncate">{opt.description}</span>
                      )}
                    </span>
                    {opt.badge}
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
