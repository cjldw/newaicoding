/**
 * Users API — 用户资料 / GitLab token
 */

import { api } from './client'
import type { UserInfo } from './auth'

export interface UpdateProfileRequest {
  nickname?: string
  avatar_url?: string
}

export interface BindGitLabTokenRequest {
  gitlab_token: string
}

export interface GitLabTokenStatus {
  bound: boolean
  gitlab_username: string | null
  scopes: string[]
}

export const usersApi = {
  getMe: () => api.get<UserInfo>('/users/me'),

  updateProfile: (data: UpdateProfileRequest) =>
    api.patch<UserInfo>('/users/me', data),

  getGitLabTokenStatus: () =>
    api.get<GitLabTokenStatus>('/users/me/gitlab-token'),

  bindGitLabToken: (data: BindGitLabTokenRequest) =>
    api.post<{ message: string }>('/users/me/gitlab-token', data),

  unbindGitLabToken: () =>
    api.delete<{ message: string }>('/users/me/gitlab-token'),
}
