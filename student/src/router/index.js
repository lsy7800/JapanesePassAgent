import { createRouter, createWebHistory } from 'vue-router'

import ExamView from '../views/ExamView.vue'
import ChatView from '../views/ChatView.vue'

const routes = [
  { path: '/', redirect: '/exam' },
  { path: '/exam', name: 'exam', component: ExamView },
  { path: '/chat', name: 'chat', component: ChatView },
]

export default createRouter({
  history: createWebHistory(),
  routes,
})
