<script setup>
import { ref, reactive } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '../stores/auth'
import { login } from '../api/auth'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()

const loading = ref(false)
const form = reactive({ email: '', password: '' })

async function submit() {
  if (!form.email || !form.password) {
    ElMessage.warning('请填写邮箱和密码')
    return
  }
  loading.value = true
  try {
    const data = await login(form.email, form.password)
    if (data.role !== 'admin') {
      ElMessage.error('无管理员权限')
      return
    }
    auth.setAuth(data)
    const redirect = route.query.redirect || '/'
    router.push(redirect)
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '邮箱或密码错误')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login-wrap">
    <div class="login-card">
      <div class="brand-mark">
        <svg viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <rect x="3" y="3" width="7" height="7" rx="1"/>
          <rect x="14" y="3" width="7" height="7" rx="1"/>
          <rect x="14" y="14" width="7" height="7" rx="1"/>
          <rect x="3" y="14" width="7" height="7" rx="1"/>
        </svg>
      </div>
      <h1 class="login-title">JLPT 管理后台</h1>
      <p class="login-sub">题库校对 · 用户管理 · 数据分析</p>

      <el-form @submit.prevent="submit" label-position="top" class="login-form">
        <el-form-item label="邮箱">
          <el-input v-model="form.email" type="email" placeholder="admin@example.com" autocomplete="email" size="large" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input v-model="form.password" type="password" placeholder="密码" show-password size="large" @keydown.enter="submit" />
        </el-form-item>
        <el-button type="primary" :loading="loading" size="large" class="submit-btn" @click="submit">登录</el-button>
      </el-form>
    </div>
  </div>
</template>

<style scoped>
.login-wrap {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background:
    radial-gradient(circle at 15% 20%, rgba(252, 211, 77, 0.28), transparent 40%),
    radial-gradient(circle at 85% 80%, rgba(245, 158, 11, 0.25), transparent 45%),
    linear-gradient(135deg, #fbf9f4 0%, #fbf9f4 100%);
  padding: 24px;
}
.login-card {
  width: 100%;
  max-width: 400px;
  background: #fff;
  border-radius: 20px;
  padding: 40px 36px 32px;
  box-shadow: 0 20px 60px rgba(245, 158, 11, 0.18), 0 4px 12px rgba(15, 23, 42, 0.06);
}
.brand-mark {
  width: 56px;
  height: 56px;
  margin: 0 auto 18px;
  border-radius: 16px;
  background: linear-gradient(135deg, #fbbf24 0%, #f59e0b 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 8px 20px rgba(245, 158, 11, 0.35);
}
.login-title {
  text-align: center;
  font-size: 22px;
  font-weight: 700;
  color: #1f2937;
  margin: 0 0 6px;
  letter-spacing: 0.5px;
}
.login-sub {
  text-align: center;
  font-size: 13px;
  color: #94a3b8;
  margin: 0 0 28px;
}
.login-form :deep(.el-form-item__label) {
  font-weight: 500;
  color: #475569;
  padding-bottom: 4px;
}
.submit-btn {
  width: 100%;
  margin-top: 6px;
  font-size: 15px;
  font-weight: 600;
  height: 44px;
}
</style>
