import http from './http'

/**
 * 题目列表（分页 + 筛选）
 * @param {object} params { type, level, difficulty_min, difficulty_max, knowledge_point, page, page_size }
 * @returns {Promise<{items, page, page_size, total}>}
 */
export function listQuestions(params) {
  // 过滤掉空值，避免发送 type=&level= 这类空参数
  const clean = {}
  for (const [k, v] of Object.entries(params || {})) {
    if (v !== '' && v !== null && v !== undefined) clean[k] = v
  }
  return http.get('/questions', { params: clean }).then((r) => r.data)
}

/** 获取完整题组 */
export function getQuestion(groupId) {
  return http.get(`/questions/${groupId}`).then((r) => r.data)
}

/** 创建题组 */
export function createQuestion(payload) {
  return http.post('/questions', payload).then((r) => r.data)
}

/** 全量替换题组（保存校对结果） */
export function updateQuestion(groupId, payload) {
  return http.put(`/questions/${groupId}`, payload).then((r) => r.data)
}

/** 删除题组 */
export function deleteQuestion(groupId) {
  return http.delete(`/questions/${groupId}`)
}

/** 题库批次列表及各自题数 */
export function listSources() {
  return http.get('/sources').then((r) => r.data)
}
