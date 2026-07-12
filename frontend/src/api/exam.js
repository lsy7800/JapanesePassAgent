import axios from 'axios'

const http = axios.create({ baseURL: '/api/v1', timeout: 30000 })

/**
 * 智能组卷
 * @param {object} payload { level, types, total_questions, difficulty_range, time_limit_minutes }
 * @returns {Promise<ExamOut>} { id, level, total, time_limit, status, items }
 */
export function generateExam(payload) {
  return http.post('/exams/generate', payload).then((r) => r.data)
}

/** 获取试卷（不含答案） */
export function getExam(examId) {
  return http.get(`/exams/${examId}`).then((r) => r.data)
}

/**
 * 提交作答判分
 * @param {number} examId
 * @param {Array<{seq:number, answer:string}>} answers
 */
export function submitExam(examId, answers) {
  return http.post(`/exams/${examId}/submit`, { answers }).then((r) => r.data)
}

/** 获取考试结果（含答案与解析） */
export function getResult(examId) {
  return http.get(`/exams/${examId}/result`).then((r) => r.data)
}
