import axios from 'axios'

const http = axios.create({ baseURL: '/api/v1', timeout: 30000 })

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
