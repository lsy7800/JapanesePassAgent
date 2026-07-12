import { createRouter, createWebHistory } from 'vue-router'

import QuestionList from '../views/QuestionList.vue'
import QuestionDetail from '../views/QuestionDetail.vue'

const routes = [
  { path: '/', name: 'list', component: QuestionList },
  { path: '/questions/:id', name: 'detail', component: QuestionDetail, props: true },
]

export default createRouter({
  history: createWebHistory(),
  routes,
})
