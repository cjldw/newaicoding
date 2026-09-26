import { useEffect, useState } from "react";

/**
 * 防抖值 hook:值停止变化 delay 毫秒后才同步(输入联想/分支预览等场景)
 */
export function useDebounce<T>(value: T, delay = 300): T {
  const [debounced, setDebounced] = useState(value);

  useEffect(() => {
    // 值连续变化时只保留最后一次定时器(清理上一个)
    const timer = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);

  return debounced;
}
