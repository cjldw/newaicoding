/**
 * Auth Store — JWT + 当前用户
 * - Zustand 管理
 * - token 持久化到 localStorage
 * - hydrate: 启动时若有 token 但 user 为 null,调 getMe 恢复 user
 */

import { create } from 'zustand'
import type { UserInfo } from '@/api/auth'
import { usersApi } from '@/api/users'

interface AuthState {
  token: string | null
  refreshToken: string | null
  user: UserInfo | null
  setAuth: (token: string, refreshToken: string, user: UserInfo) => void
  setUser: (user: UserInfo) => void
  logout: () => void
  /** 恢复 user:有 token 但 user 为 null 时调 getMe;失败则登出 */
  hydrate: () => Promise<void>
}

export const useAuthStore = create<AuthState>((set, get) => ({
  token: localStorage.getItem('access_token'),
  refreshToken: localStorage.getItem('refresh_token'),
  user: null,

  setAuth: (token: string, refreshToken: string, user: UserInfo) => {
    localStorage.setItem('access_token', token)
    localStorage.setItem('refresh_token', refreshToken)
    set({ token, refreshToken, user })
  },

  setUser: (user: UserInfo) => {
    set({ user })
  },

  logout: () => {
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
    set({ token: null, refreshToken: null, user: null })
  },

  hydrate: async () => {
    const { token, user } = get()
    // 无 token 或 user 已恢复,无需操作
    if (!token || user) return
    try {
      const resp = await usersApi.getMe()
      set({ user: resp.data })
    } catch {
      // 401 或其他错误 → token 已失效,登出
      get().logout()
    }
  },
}))
