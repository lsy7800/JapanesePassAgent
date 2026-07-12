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
    <el-card class="login-card" shadow="always">
      <div class="login-title">JLPT 管理后台</div>
      <el-form @submit.prevent="submit" label-position="top">
        <el-form-item label="邮箱">
          <el-input v-model="form.email" type="email" placeholder="admin@example.com" autocomplete="email" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input v-model="form.password" type="password" placeholder="密码" show-password @keydown.enter="submit" />
        </el-form-item>
        <el-button type="primary" :loading="loading" style="width:100%" @click="submit">登录</el-button>
      </el-form>
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
}
.login-card {
  width: 360px;
}
.login-title {
  text-align: center;
  font-size: 22px;
  font-weight: 700;
  margin-bottom: 24px;
  color: #303133;
}
</style>
