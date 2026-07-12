import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

const TOKEN_KEY = 'jlpt_token'
const USER_KEY = 'jlpt_user'

export const useAuthStore = defineStore('auth', () => {
  const token = ref(localStorage.getItem(TOKEN_KEY) || '')
  const user = ref(JSON.parse(localStorage.getItem(USER_KEY) || 'null'))

  const isLoggedIn = computed(() => !!token.value)
  const role = computed(() => user.value?.role || '')
  const email = computed(() => user.value?.email || '')

  function setAuth(data) {
    token.value = data.access_token
    user.value = { email: data.email, role: data.role }
    localStorage.setItem(TOKEN_KEY, data.access_token)
    localStorage.setItem(USER_KEY, JSON.stringify(user.value))
  }

  function logout() {
    token.value = ''
    user.value = null
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(USER_KEY)
  }

  return { token, user, isLoggedIn, role, email, setAuth, logout }
})
