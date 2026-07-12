import axios from 'axios'

const http = axios.create({ baseURL: '/api/v1', timeout: 60000 })

export function chat(message, sessionId = null, context = null) {
  return http.post('/agent/chat', { message, session_id: sessionId, context }).then((r) => r.data)
}
