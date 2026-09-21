import * as React from 'react'

export interface CardProps extends React.HTMLAttributes<HTMLDivElement> {}

/**
 * shadcn/ui New York 风格卡片
 * - .card 样式: bg-surface border border-border rounded-lg shadow-sm p-6
 */
const Card = React.forwardRef<HTMLDivElement, CardProps>(
  ({ className = '', children, ...props }, ref) => {
    return (
      <div
        className={`card ${className}`}
        ref={ref}
        {...props}
      >
        {children}
      </div>
    )
  }
)
Card.displayName = 'Card'

export { Card }
