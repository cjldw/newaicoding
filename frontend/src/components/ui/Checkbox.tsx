/**
 * Checkbox — shadcn/ui New York 风格手写复选框(无 Radix;R3 全站首个)
 * 使用原生 checkbox input + 自定义方框对勾,写法参照 RadioGroup
 * - 受控:checked / onChange(checked) / disabled
 * - label 可点(整体包在 <label> 内)
 */

import * as React from 'react'

export interface CheckboxProps {
  checked: boolean
  onChange: (checked: boolean) => void
  disabled?: boolean
  /** label 内容(整体可点击;不传则为纯方框) */
  label?: React.ReactNode
  className?: string
  'aria-label'?: string
}

function Checkbox({
  checked,
  onChange,
  disabled = false,
  label,
  className = '',
  ...props
}: CheckboxProps) {
  return (
    <label
      className={`inline-flex items-center gap-2 ${disabled ? 'cursor-not-allowed opacity-50' : 'cursor-pointer'} ${className}`}
    >
      <span
        className={`relative flex items-center justify-center w-4 h-4 rounded border transition-colors ${
          checked ? 'border-primary bg-primary' : 'border-border bg-transparent'
        }`}
      >
        <input
          type="checkbox"
          checked={checked}
          disabled={disabled}
          onChange={(e) => onChange(e.target.checked)}
          className="absolute inset-0 w-full h-full opacity-0 cursor-pointer disabled:cursor-not-allowed"
          {...props}
        />
        {/* 对勾(选中时白描边,与 btn-pri 的 text-white 同源) */}
        {checked && (
          <svg
            viewBox="0 0 12 12"
            className="w-3 h-3 text-white pointer-events-none"
            fill="none"
            stroke="currentColor"
            strokeWidth={2}
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <path d="M2.5 6.5L5 9l4.5-5.5" />
          </svg>
        )}
      </span>
      {label != null && <span className="text-sm text-text">{label}</span>}
    </label>
  )
}

export { Checkbox }
