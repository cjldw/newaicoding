/**
 * Avatar — 头像组件(头像图 + 首字母 fallback)
 * - 显示用户头像,无头像时显示用户名首字母
 * - 支持尺寸:size(默认 32px)
 */

import * as React from 'react'
import { isAvatarUrlFailed, markAvatarUrlFailed } from '@/utils/avatar'

export interface AvatarProps extends React.HTMLAttributes<HTMLDivElement> {
  src?: string | null
  alt?: string
  size?: number
}

const Avatar = React.forwardRef<HTMLDivElement, AvatarProps>(
  ({ className = '', src, alt = '', size = 32, ...props }, ref) => {
    const [imgError, setImgError] = React.useState(false)
    const initial = alt ? alt.charAt(0).toUpperCase() : '?'

    // BUG-UI-072:已记忆为加载失败的 URL 直接走首字母回退,不再发请求
    const showFallback = !src || imgError || isAvatarUrlFailed(src)

    return (
      <div
        ref={ref}
        className={`relative inline-flex items-center justify-center overflow-hidden rounded-full bg-surface-strong border border-border ${className}`}
        style={{ width: size, height: size, fontSize: size * 0.4 }}
        {...props}
      >
        {showFallback ? (
          <span className="font-medium text-text-muted select-none">{initial}</span>
        ) : (
          <img
            src={src}
            alt={alt}
            className="absolute inset-0 w-full h-full object-cover"
            onError={() => {
              markAvatarUrlFailed(src) // 记忆失效 URL,重挂载不再重复请求
              setImgError(true)
            }}
          />
        )}
      </div>
    )
  }
)
Avatar.displayName = 'Avatar'

export { Avatar }
