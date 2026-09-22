/**
 * Auth API — 登录 / 注册 / 找回密码 / 重置密码
 */

import { api } from './client'

export interface LoginRequest {
  phone: string
  password: string
}

export interface LoginResponse {
  access_token: string
  refresh_token: string
  user: UserInfo
}

export interface RegisterRequest {
  phone: string
  password: string
  invite_code?: string
}

export interface RegisterResponse {
  user_id: number
}

export interface SendSmsCodeRequest {
  phone: string
}

export interface ResetPasswordRequest {
  phone: string
  sms_code: string
  new_password: string
}

export interface UserInfo {
  user_id: string
  phone: string
  nickname: string | null
  avatar_url: string | null
  role: string  // 'superadmin' | 'user'
  gitlab_username?: string | null
  gitlab_token_bound?: boolean
  gitlab_token_scopes?: string[]
  gitlab_token_bound_at?: string | null
}

export const authApi = {
  login: (data: LoginRequest) =>
    api.post<LoginResponse>('/auth/login', data),

  register: (data: RegisterRequest) =>
    api.post<RegisterResponse>('/auth/register', data),

  sendSmsCode: (data: SendSmsCodeRequest) =>
    api.post<{ message: string }>('/auth/send-sms-code', data),

  resetPassword: (data: ResetPasswordRequest) =>
    api.post<{ message: string }>('/auth/reset-password', data),

  refreshToken: (refresh_token: string) =>
    api.post<{ access_token: string }>('/auth/refresh', { refresh_token }),
}
