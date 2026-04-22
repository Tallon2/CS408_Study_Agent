/**
 * auth.ts — 用户认证 Pinia Store
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { http } from '@/utils/http'
import type { TokenResponse, UserResponse } from '@/types'

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string>(localStorage.getItem('access_token') || '')
  const user  = ref<UserResponse | null>(
    JSON.parse(localStorage.getItem('user_info') || 'null')
  )

  const isLoggedIn = computed(() => !!token.value)

  async function login(username: string, password: string) {
    const { data } = await http.post<TokenResponse>('/api/v1/auth/login', { username, password })
    token.value = data.access_token
    localStorage.setItem('access_token', data.access_token)
    // 立即拉取用户信息
    await fetchMe()
    return data
  }

  async function register(username: string, password: string, email?: string) {
    const { data } = await http.post<TokenResponse>('/api/v1/auth/register', { username, password, email })
    token.value = data.access_token
    localStorage.setItem('access_token', data.access_token)
    await fetchMe()
    return data
  }

  async function fetchMe() {
    try {
      const { data } = await http.get<UserResponse>('/api/v1/auth/me')
      user.value = data
      localStorage.setItem('user_info', JSON.stringify(data))
    } catch {
      logout()
    }
  }

  function logout() {
    token.value = ''
    user.value = null
    localStorage.removeItem('access_token')
    localStorage.removeItem('user_info')
  }

  return { token, user, isLoggedIn, login, register, fetchMe, logout }
})
