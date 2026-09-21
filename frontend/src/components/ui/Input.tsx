import * as React from 'react'

export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {}

/**
 * shadcn/ui New York 风格输入框
 * - .input 基础样式
 * - 聚焦时双层 ring + border-ring
 * - placeholder 颜色 text-text-muted
 */
const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ className = '', ...props }, ref) => {
    return (
      <input
        className={`input ${className}`}
        ref={ref}
        {...props}
      />
    )
  }
)
Input.displayName = 'Input'

export { Input }
