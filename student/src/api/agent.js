import http from './http'
import { useAuthStore } from '../stores/auth'

// 同步接口（保留，备用）
export function chat(message, sessionId = null, context = null) {
  return http.post('/agent/chat', { message, session_id: sessionId, context }).then((r) => r.data)
}

// ── 会话管理 ──
/** 当前用户的会话列表 */
export function listSessions() {
  return http.get('/sessions').then((r) => r.data)
}

/** 某会话的全部消息 */
export function getSessionMessages(sessionId) {
  return http.get(`/sessions/${sessionId}/messages`).then((r) => r.data)
}

/** 重命名会话 */
export function renameSession(sessionId, title) {
  return http.patch(`/sessions/${sessionId}`, { title }).then((r) => r.data)
}

/** 删除会话 */
export function deleteSession(sessionId) {
  return http.delete(`/sessions/${sessionId}`).then((r) => r.data)
}

/**
 * SSE 流式对话
 * EventSource 不支持自定义 Header，token 通过 query 参数传递。
 *
 * @param {string}   message
 * @param {number|null} sessionId
 * @param {object}   callbacks  { onSession, onToken, onTool, onDone, onError }
 * @returns {function} close — 调用以提前关闭连接
 */
export function chatStream(message, sessionId, callbacks = {}) {
  const { onSession, onToken, onTool, onDone, onError } = callbacks
  const auth = useAuthStore()

  const params = new URLSearchParams({ message, token: auth.token || '' })
  if (sessionId) params.set('session_id', sessionId)

  const url = `/api/v1/agent/stream?${params.toString()}`
  const es = new EventSource(url)

  es.onmessage = (e) => {
    let payload
    try { payload = JSON.parse(e.data) } catch { return }

    if (payload.type === 'session') {
      onSession?.(payload.session_id)
    } else if (payload.type === 'token') {
      onToken?.(payload.content)
    } else if (payload.type === 'tool') {
      onTool?.(payload.name, payload.args)
    } else if (payload.type === 'done') {
      es.close()
      onDone?.(payload.session_id)
    } else if (payload.type === 'error') {
      es.close()
      onError?.(payload.detail)
    }
  }

  es.onerror = () => {
    es.close()
    onError?.('连接中断')
  }

  return () => es.close()
}
