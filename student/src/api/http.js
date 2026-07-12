/**
 * 统一 axios 实例，自动注入 JWT Authorization 头。
 * 所有 API 模块从这里导入 http，而不是各自 axios.create()。
 */
import axios from 'axios'
import { useAuthStore } from '../stores/auth'

const http = axios.create({ baseURL: '/api/v1', timeout: 30000 })

http.interceptors.request.use((config) => {
  const auth = useAuthStore()
  if (auth.token) {
    config.headers.Authorization = `Bearer ${auth.token}`
  }
  return config
})

// 401 自动跳回登录页
http.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      const auth = useAuthStore()
      auth.logout()
      window.location.href = '/login'
    }
    return Promise.reject(err)
  },
)

export default http
