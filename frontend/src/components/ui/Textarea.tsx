/**
 * Textarea — shadcn/ui New York 风格手写文本域
 * 使用 CSS 变量 token,与 globals.css 一致
 */

import * as React from 'react'

export interface TextareaProps extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {}

/**
 * 手写 Textarea 组件
 * - .input 基础样式(与 Input 一致)
 * - min-h-[80px] 保证最小高度
 * - 聚焦时 ring 效果
 */
const Textarea = React.forwardRef<HTMLTextAreaElement, TextareaProps>(
  ({ className = '', ...props }, ref) => {
    return (
      <textarea
        className={`input min-h-[80px] resize-y ${className}`}
        ref={ref}
        {...props}
      />
    )
  }
)
Textarea.displayName = 'Textarea'

export { Textarea }
