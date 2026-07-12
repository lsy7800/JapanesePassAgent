<script setup>
import { ref, reactive } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '../stores/auth'
import { login, register } from '../api/auth'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()

const mode = ref('login')
const loading = ref(false)
const form = reactive({ email: '', password: '', confirm: '' })

async function submit() {
  if (!form.email || !form.password) {
    ElMessage.warning('请填写邮箱和密码')
    return
  }
  if (mode.value === 'register' && form.password !== form.confirm) {
    ElMessage.warning('两次密码不一致')
    return
  }
  loading.value = true
  try {
    const data = mode.value === 'login'
      ? await login(form.email, form.password)
      : await register(form.email, form.password)
    auth.setAuth(data)
    ElMessage.success(mode.value === 'login' ? '登录成功' : '注册成功')
    const redirect = route.query.redirect || '/exam'
    router.push(redirect)
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '操作失败')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login-wrap">
    <el-card class="login-card" shadow="always">
      <div class="login-title">JLPT 学习系统</div>

      <el-form @submit.prevent="submit" label-position="top">
        <el-form-item label="邮箱">
          <el-input v-model="form.email" type="email" placeholder="your@email.com" autocomplete="email" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input v-model="form.password" type="password" placeholder="至少6位" show-password @keydown.enter="submit" />
        </el-form-item>
        <el-form-item v-if="mode === 'register'" label="确认密码">
          <el-input v-model="form.confirm" type="password" placeholder="再输一次" show-password @keydown.enter="submit" />
        </el-form-item>
        <el-button type="primary" :loading="loading" style="width:100%" @click="submit">
          {{ mode === 'login' ? '登录' : '注册' }}
        </el-button>
      </el-form>

      <div class="login-switch">
        <span v-if="mode === 'login'">
          没有账号？<el-button link @click="mode = 'register'">注册</el-button>
        </span>
        <span v-else>
          已有账号？<el-button link @click="mode = 'login'">登录</el-button>
        </span>
      </div>
    </el-card>
  </div>
</template>

<style scoped>
.login-wrap {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #f5f7fa;
  padding: 16px;
}
.login-card {
  width: 100%;
  max-width: 380px;
}
.login-title {
  text-align: center;
  font-size: 22px;
  font-weight: 700;
  margin-bottom: 24px;
  color: #303133;
}
.login-switch {
  text-align: center;
  margin-top: 16px;
  font-size: 13px;
  color: #909399;
}
</style>
