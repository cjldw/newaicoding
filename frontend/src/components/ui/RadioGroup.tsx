/**
 * RadioGroup — shadcn/ui New York 风格手写单选组(无 Radix)
 * 使用原生 radio input + 自定义圆形样式
 */

export interface RadioOption {
  label: string
  value: string
}

export interface RadioGroupProps {
  name: string
  options: RadioOption[]
  value: string
  onChange: (value: string) => void
  className?: string
  disabled?: boolean
}

/**
 * 手写 RadioGroup 组件
 * - 原生 radio input 保证可访问性
 * - 自定义圆形指示器: 外圈 border + 内圈填充
 * - 选中时外圈 border-primary, 内圈 bg-primary
 * - 水平排列, gap-4
 */
function RadioGroup({ name, options, value, onChange, className = '', disabled }: RadioGroupProps) {
  return (
    <div className={`flex gap-4 ${className}`} role="radiogroup">
      {options.map((opt) => {
        const checked = value === opt.value
        return (
          <label
            key={opt.value}
            className={`flex items-center gap-2 cursor-pointer text-sm ${disabled ? 'opacity-50 cursor-not-allowed' : ''}`}
          >
            <span
              className={`relative flex items-center justify-center w-4 h-4 rounded-full border transition-colors ${
                checked ? 'border-primary' : 'border-border'
              }`}
            >
              <input
                type="radio"
                name={name}
                value={opt.value}
                checked={checked}
                onChange={() => onChange(opt.value)}
                disabled={disabled}
                className="absolute inset-0 w-full h-full opacity-0 cursor-pointer disabled:cursor-not-allowed"
              />
              {/* 内圈填充 */}
              <span
                className={`w-2 h-2 rounded-full transition-colors ${
                  checked ? 'bg-primary' : 'bg-transparent'
                }`}
              />
            </span>
            <span className="text-text">{opt.label}</span>
          </label>
        )
      })}
    </div>
  )
}

export { RadioGroup }
