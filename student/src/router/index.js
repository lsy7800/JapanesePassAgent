import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'

import LoginView from '../views/LoginView.vue'
import ExamView from '../views/ExamView.vue'
import ChatView from '../views/ChatView.vue'
import HistoryView from '../views/HistoryView.vue'
import ResultView from '../views/ResultView.vue'
import StatsView from '../views/StatsView.vue'

const routes = [
  { path: '/login', name: 'login', component: LoginView, meta: { public: true } },
  { path: '/', redirect: '/exam' },
  { path: '/exam', name: 'exam', component: ExamView },
  { path: '/chat', name: 'chat', component: ChatView },
  { path: '/history', name: 'history', component: HistoryView },
  { path: '/result/:id', name: 'result', component: ResultView, props: true },
  { path: '/stats', name: 'stats', component: StatsView },
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
})

export default router
