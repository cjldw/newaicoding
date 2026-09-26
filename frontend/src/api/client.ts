/**
 * API 客户端封装
 * - 统一响应结构: { code, data, message }
 * - 自动携带 JWT (从 authStore 读取)
 * - 401 时自动清除 token
 */

import { useAuthStore } from '@/stores/authStore'

export interface ApiResponse<T = unknown> {
  code: number
  data: T
  message: string
}

export class ApiError extends Error {
  constructor(
    public code: number,
    message: string,
    /** 业务错误附带数据(如 R2 批量邀请 400 的 {errors:[{user_id, reason}]}) */
    public data?: unknown,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

const BASE_URL = '/api'

async function request<T>(
  url: string,
  options: RequestInit = {},
): Promise<ApiResponse<T>> {
  const token = useAuthStore.getState().token

  // R28:multipart(FormData)时交由浏览器自动设置 Content-Type(含 boundary)
  const isFormData = typeof FormData !== 'undefined' && options.body instanceof FormData

  const headers: Record<string, string> = {
    ...(isFormData ? {} : { 'Content-Type': 'application/json' }),
    ...(options.headers as Record<string, string> || {}),
  }

  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }

  const response = await fetch(`${BASE_URL}${url}`, {
    ...options,
    headers,
  })

  // 401 → 清除 token,跳登录
  if (response.status === 401) {
    useAuthStore.getState().logout()
    window.location.href = '/login'
    throw new ApiError(401, '登录已过期')
  }

  const json: ApiResponse<T> = await response.json()

  if (json.code !== 0) {
    throw new ApiError(json.code, json.message, json.data)
  }

  return json
}

/** R28:FormData 原样作为 body,其余 JSON 序列化 */
function encodeBody(body: unknown): BodyInit | undefined {
  if (body == null) return undefined
  if (typeof FormData !== 'undefined' && body instanceof FormData) return body
  return JSON.stringify(body)
}

export const api = {
  get: <T>(url: string) => request<T>(url, { method: 'GET' }),
  post: <T>(url: string, body?: unknown) =>
    request<T>(url, { method: 'POST', body: encodeBody(body) }),
  put: <T>(url: string, body?: unknown) =>
    request<T>(url, { method: 'PUT', body: encodeBody(body) }),
  patch: <T>(url: string, body?: unknown) =>
    request<T>(url, { method: 'PATCH', body: encodeBody(body) }),
  delete: <T>(url: string) => request<T>(url, { method: 'DELETE' }),
}
