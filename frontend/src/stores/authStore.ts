/**
 * Auth Store — JWT + 当前用户
 * - Zustand 管理
 * - token 持久化到 localStorage
 */

import { create } from 'zustand'
import type { UserInfo } from '@/api/auth'

interface AuthState {
  token: string | null
  refreshToken: string | null
  user: UserInfo | null
  setAuth: (token: string, refreshToken: string, user: UserInfo) => void
  setUser: (user: UserInfo) => void
  logout: () => void
}

export const useAuthStore = create<AuthState>((set) => ({
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
}))
