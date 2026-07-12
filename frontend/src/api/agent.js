import axios from 'axios'

const http = axios.create({ baseURL: '/api/v1', timeout: 60000 })

/**
 * 与 Agent 对话（同步）
 * @param {string} message 用户消息
 * @param {string|null} sessionId 会话ID，续聊时传上一次返回的 session_id
 * @param {object|null} context 附加上下文，如 { current_question_id: 42 }
 * @returns {Promise<{reply, session_id, tool_calls}>}
 */
export function chat(message, sessionId = null, context = null) {
  const body = { message }
  if (sessionId) body.session_id = sessionId
  if (context) body.context = context
  return http.post('/agent/chat', body).then((r) => r.data)
}
