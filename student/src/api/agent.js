import axios from 'axios'

const http = axios.create({ baseURL: '/api/v1', timeout: 60000 })

// 同步接口（保留，备用）
export function chat(message, sessionId = null, context = null) {
  return http.post('/agent/chat', { message, session_id: sessionId, context }).then((r) => r.data)
}

/**
 * SSE 流式对话
 *
 * @param {string}   message        用户消息
 * @param {string|null} sessionId   会话ID
 * @param {object}   callbacks      { onToken, onTool, onDone, onError }
 *   - onToken(content: string)     每个文字 token
 *   - onTool(name, args)           工具调用事件
 *   - onDone(sessionId: string)    流结束，带最终 session_id
 *   - onError(detail: string)      错误
 * @returns {function} close        调用以提前关闭连接
 */
export function chatStream(message, sessionId, callbacks = {}) {
  const { onToken, onTool, onDone, onError } = callbacks

  const params = new URLSearchParams({ message })
  if (sessionId) params.set('session_id', sessionId)

  const url = `/api/v1/agent/stream?${params.toString()}`
  const es = new EventSource(url)

  es.onmessage = (e) => {
    let payload
    try {
      payload = JSON.parse(e.data)
    } catch {
      return
    }

    if (payload.type === 'token') {
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
