/**
 * Users API — 用户资料 / GitLab token
 */

import { api } from './client'
import type { UserInfo } from './auth'

export interface UpdateProfileRequest {
  nickname?: string
  /** R28:传 null 表示移除头像(后端同时清空 avatar_file_path) */
  avatar_url?: string | null
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

  /** R28:上传头像(multipart/form-data,字段名 file),成功返回平台头像 URL */
  uploadAvatar: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return api.post<{ avatar_url: string }>('/users/me/avatar', form)
  },

  getGitLabTokenStatus: () =>
    api.get<GitLabTokenStatus>('/users/me/gitlab-token'),

  bindGitLabToken: (data: BindGitLabTokenRequest) =>
    api.post<{ message: string }>('/users/me/gitlab-token', data),

  unbindGitLabToken: () =>
    api.delete<{ message: string }>('/users/me/gitlab-token'),

  /** 按手机号精确搜索用户(邀请成员用) */
  searchUserByPhone: (phone: string) =>
    api.get<SearchedUser | null>(`/users/search?phone=${encodeURIComponent(phone)}`),
}

/** 手机号搜索结果 */
export interface SearchedUser {
  user_id: string
  phone_masked: string
  nickname: string
  avatar_url: string
}
