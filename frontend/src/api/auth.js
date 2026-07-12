import axios from 'axios'

const http = axios.create({ baseURL: '/api/v1', timeout: 10000 })

export function login(email, password) {
  return http.post('/auth/login', { email, password }).then((r) => r.data)
}

export function register(email, password, role = 'admin') {
  return http.post('/auth/register', { email, password, role }).then((r) => r.data)
}
