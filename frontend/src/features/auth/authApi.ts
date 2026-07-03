import { apiClient } from '@/lib/apiClient'
import type { SessionUser } from '@/types/auth'

export interface RegisterPayload {
  organization_name: string
  tier: 'basic' | 'pro' | 'enterprise'
  email: string
  password: string
}

export interface LoginPayload {
  email: string
  password: string
}

interface TokenResponse {
  access_token: string
  token_type: string
}

export const authApi = {
  register: (payload: RegisterPayload) => apiClient.post<TokenResponse>('/auth/register', payload),
  login: (payload: LoginPayload) => apiClient.post<TokenResponse>('/auth/login', payload),
  me: () => apiClient.get<SessionUser>('/auth/me'),
}
