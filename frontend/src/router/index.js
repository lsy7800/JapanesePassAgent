import { createRouter, createWebHistory } from 'vue-router'

import QuestionList from '../views/QuestionList.vue'
import QuestionDetail from '../views/QuestionDetail.vue'
import ExamView from '../views/ExamView.vue'
import ChatView from '../views/ChatView.vue'

const routes = [
  { path: '/', name: 'list', component: QuestionList },
  { path: '/questions/:id', name: 'detail', component: QuestionDetail, props: true },
  { path: '/exam', name: 'exam', component: ExamView },
  { path: '/chat', name: 'chat', component: ChatView },
]

export default createRouter({
  history: createWebHistory(),
  routes,
})
