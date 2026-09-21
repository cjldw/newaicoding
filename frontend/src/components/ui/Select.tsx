/**
 * Select — shadcn/ui New York 风格手写下拉选择(无 Radix)
 * 使用原生 <select> + 自定义样式,支持 label + 错误态
 */

import * as React from 'react'
import { ChevronDown } from 'lucide-react'

export interface SelectOption {
  label: string
  value: string
}

export interface SelectProps extends Omit<React.SelectHTMLAttributes<HTMLSelectElement>, 'children'> {
  options: SelectOption[]
  placeholder?: string
  error?: string
}

/**
 * 手写 Select 组件
 * - 原生 <select> 保证可访问性
 * - 自定义外观: border-border bg-surface text-text
 * - 右侧 chevron-down 图标
 * - 聚焦时 ring 效果
 */
const Select = React.forwardRef<HTMLSelectElement, SelectProps>(
  ({ className = '', options, placeholder, error, ...props }, ref) => {
    return (
      <div className="relative">
        <select
          ref={ref}
          className={`input appearance-none pr-8 ${error ? 'border-red-500' : ''} ${className}`}
          {...props}
        >
          {placeholder && (
            <option value="" disabled>
              {placeholder}
            </option>
          )}
          {options.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
        {/* 下拉箭头图标 */}
        <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 w-4 h-4 text-text-muted pointer-events-none" />
      </div>
    )
  }
)
Select.displayName = 'Select'

export { Select }
