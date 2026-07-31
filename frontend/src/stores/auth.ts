/**
 * Local-mode auth store — always authenticated as the fixed local user.
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'

const LOCAL_USER = {
  id: '00000000-0000-0000-0000-000000000001',
  email: 'local@openvid.local',
  first_name: 'Local User',
  last_name: undefined as string | undefined,
  type: 'local',
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
  email_confirmed_at: new Date().toISOString(),
  watermark_logo_url: null as string | null,
}

export const useAuthStore = defineStore('auth', () => {
  const user = ref(LOCAL_USER)
  const isAuthenticated = ref(true)
  const isLoading = ref(false)
  const error = ref<string | null>(null)
  const accessToken = ref<string | null>('local-token')
  const refreshToken = ref<string | null>('local-refresh')

  // Seed tokens so axios interceptors never force a login redirect
  if (typeof localStorage !== 'undefined') {
    localStorage.setItem('access_token', 'local-token')
    localStorage.setItem('refresh_token', 'local-refresh')
  }

  const setTokens = (tokens: { access_token: string; refresh_token: string }) => {
    accessToken.value = tokens.access_token
    refreshToken.value = tokens.refresh_token
    localStorage.setItem('access_token', tokens.access_token)
    localStorage.setItem('refresh_token', tokens.refresh_token)
  }

  const clearTokens = () => {
    // no-op in local mode — stay logged in
  }

  const handleTokenExpiration = () => {
    // no-op in local mode
  }

  async function login() {
    isAuthenticated.value = true
    user.value = LOCAL_USER
    return { user: user.value }
  }

  async function register() {
    return login()
  }

  async function logout() {
    // stay logged in locally
    return true
  }

  async function checkAuth() {
    isAuthenticated.value = true
    user.value = LOCAL_USER
    return true
  }

  async function getProfile() {
    return LOCAL_USER
  }

  async function updateProfile(data: Partial<typeof LOCAL_USER>) {
    user.value = { ...user.value, ...data }
    return user.value
  }

  function setupAuthListener() {
    return () => {}
  }

  function startPeriodicAuthCheck() {
    return () => {}
  }

  return {
    user,
    isAuthenticated,
    isLoading,
    error,
    accessToken,
    refreshToken,
    setTokens,
    clearTokens,
    handleTokenExpiration,
    login,
    register,
    logout,
    checkAuth,
    getProfile,
    updateProfile,
    setupAuthListener,
    startPeriodicAuthCheck,
  }
})
