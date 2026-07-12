import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'

import LoginView from '../views/LoginView.vue'
import QuestionList from '../views/QuestionList.vue'
import QuestionDetail from '../views/QuestionDetail.vue'

const routes = [
  { path: '/login', name: 'login', component: LoginView, meta: { public: true } },
  { path: '/', name: 'list', component: QuestionList },
  { path: '/questions/:id', name: 'detail', component: QuestionDetail, props: true },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to) => {
  const auth = useAuthStore()
  if (!to.meta.public && !auth.isLoggedIn) {
    return { path: '/login', query: { redirect: to.fullPath } }
  }
  // 非 admin 拒绝访问（已登录但角色不对时也踢回登录页）
  if (!to.meta.public && auth.isLoggedIn && auth.role !== 'admin') {
    return { path: '/login' }
  }
})

export default router
