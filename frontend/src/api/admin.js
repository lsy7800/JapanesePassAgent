import http from './http'

// ── 概览统计 ──
export function getOverview() {
  return http.get('/admin/stats/overview').then((r) => r.data)
}

// ── 平台薄弱知识点 ──
export function getAdminWeakPoints(limit = 10) {
  return http.get('/admin/stats/weak-points', { params: { limit } }).then((r) => r.data)
}

// ── 用户管理 ──
export function listUsers(params) {
  const clean = {}
  for (const [k, v] of Object.entries(params || {})) {
    if (v !== '' && v !== null && v !== undefined) clean[k] = v
  }
  return http.get('/admin/users', { params: clean }).then((r) => r.data)
}

export function updateUser(id, payload) {
  return http.patch(`/admin/users/${id}`, payload).then((r) => r.data)
}
