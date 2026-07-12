import http from './http'

export function generateExam(payload) {
  return http.post('/exams/generate', payload).then((r) => r.data)
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

