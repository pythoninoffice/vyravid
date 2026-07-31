import axios from 'axios'
import type { AxiosInstance, AxiosRequestConfig } from 'axios'

const API_BASE_URL = import.meta.env.VITE_API_URL || (import.meta.env.PROD ? '' : 'http://localhost:8000')

const apiClient: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  timeout: 3600000,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Always attach local token (backend ignores it)
apiClient.interceptors.request.use((config) => {
  config.headers.Authorization = 'Bearer local-token'
  return config
})

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    // Never redirect to login in local mode
    return Promise.reject(error)
  }
)

export default apiClient

export const apiHelpers = {
  get: <T = any>(url: string, config?: AxiosRequestConfig) =>
    apiClient.get<T>(url, config),

  post: <T = any>(url: string, data?: any, config?: AxiosRequestConfig) =>
    apiClient.post<T>(url, data, config),

  put: <T = any>(url: string, data?: any, config?: AxiosRequestConfig) =>
    apiClient.put<T>(url, data, config),

  delete: <T = any>(url: string, config?: AxiosRequestConfig) =>
    apiClient.delete<T>(url, config),

  patch: <T = any>(url: string, data?: any, config?: AxiosRequestConfig) =>
    apiClient.patch<T>(url, data, config),
}
