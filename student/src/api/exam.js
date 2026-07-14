import http from './http'

// 题型列表（可按级别过滤、只取可出题的）
export function getCategories(level, examableOnly = true) {
  return http
    .get('/categories', { params: { level: level || undefined, examable_only: examableOnly } })
    .then((r) => r.data)
}

export function generateExam(payload) {
  return http.post('/exams/generate', payload).then((r) => r.data)
}

// AI 智能组卷：按自然语言需求 + 用户薄弱点，由后端 LLM 规划并落库
export function smartGenerateExam(payload) {
  return http.post('/exams/smart-generate', payload).then((r) => r.data)
}

export function getExam(id) {
  return http.get(`/exams/${id}`).then((r) => r.data)
}

export function submitExam(examId, answers) {
  return http.post(`/exams/${examId}/submit`, { answers }).then((r) => r.data)
}

export function getResult(examId) {
  return http.get(`/exams/${examId}/result`).then((r) => r.data)
}

export function listExams(page = 1, pageSize = 20) {
  return http.get('/exams', { params: { page, page_size: pageSize } }).then((r) => r.data)
}

// ── 学习分析 ──

export function getWeakPoints(limit = 10) {
  return http.get('/stats/weak-points', { params: { limit } }).then((r) => r.data)
}

export function getHistoryTrend(limit = 20) {
  return http.get('/stats/history', { params: { limit } }).then((r) => r.data)
}

export function getWrongQuestions(payload = {}) {
  return http.post('/review/wrong-questions', payload).then((r) => r.data)
}

// ── 试卷导出（带 JWT 拉 blob，触发浏览器下载，token 不进 URL）──
export async function downloadExam(examId, { withAnswers = false } = {}) {
  const res = await http.get(`/exams/${examId}/export`, {
    params: { format: 'markdown', with_answers: withAnswers },
    responseType: 'blob',
  })
  // 从 Content-Disposition 解析文件名，回退到默认名
  let filename = `JLPT_exam_${examId}.md`
  const cd = res.headers['content-disposition'] || ''
  const m = /filename\*=UTF-8''([^;]+)/i.exec(cd)
  if (m) {
    try { filename = decodeURIComponent(m[1]) } catch { /* 保留默认 */ }
  }
  const blob = new Blob([res.data], { type: 'text/markdown;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}


