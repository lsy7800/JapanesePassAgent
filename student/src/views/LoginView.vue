<script setup>
import { ref, reactive } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '../stores/auth'
import { login, register } from '../api/auth'
import { collapseEnter, collapseLeave } from '../utils/collapse'

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
    const redirect = route.query.redirect || '/home'
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
    <div class="login-card">
      <div class="brand-mark">
        <svg viewBox="0 0 24 24" width="30" height="30" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/>
          <path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/>
        </svg>
      </div>
      <h1 class="login-title">JLPT 学习系统</h1>
      <p class="login-sub">日语能力考试 · 智能题库与 AI 辅导</p>

      <el-form @submit.prevent="submit" label-position="top" class="login-form">
        <el-form-item label="邮箱">
          <el-input v-model="form.email" type="email" placeholder="your@email.com" autocomplete="email" size="large" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input v-model="form.password" type="password" placeholder="至少6位" show-password size="large" @keydown.enter="submit" />
        </el-form-item>
        <!-- 切到注册时"确认密码"展开而非突然插入，卡片高度变化不跳 -->
        <transition name="confirm" @enter="collapseEnter" @leave="collapseLeave">
          <div v-if="mode === 'register'" class="confirm-wrap">
            <el-form-item label="确认密码">
              <el-input v-model="form.confirm" type="password" placeholder="再输一次" show-password size="large" @keydown.enter="submit" />
            </el-form-item>
          </div>
        </transition>
        <el-button type="primary" :loading="loading" size="large" class="submit-btn" @click="submit">
          {{ mode === 'login' ? '登录' : '注册' }}
        </el-button>
      </el-form>

      <div class="login-switch">
        <span v-if="mode === 'login'">
          还没有账号？<el-button link type="primary" @click="mode = 'register'">立即注册</el-button>
        </span>
        <span v-else>
          已有账号？<el-button link type="primary" @click="mode = 'login'">返回登录</el-button>
        </span>
      </div>
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
  animation: card-in 0.42s var(--ease-out);
}
@keyframes card-in {
  from { opacity: 0; transform: translateY(16px) scale(0.98); }
  to   { opacity: 1; transform: none; }
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
  animation: pop-check 0.42s var(--ease-spring) 100ms backwards;
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
/* 高度由 collapse.js 钩子写入内联样式；这里只负责裁剪与过渡。
   el-form-item 自带 margin-bottom，放在内层不影响 height:0 的收拢。 */
.confirm-wrap {
  overflow: hidden;
  transition: height var(--dur-base) var(--ease-in-out),
              opacity var(--dur-base) var(--ease-in-out);
}
.confirm-enter-from,
.confirm-leave-to { opacity: 0; }
.submit-btn {
  width: 100%;
  margin-top: 6px;
  font-size: 15px;
  font-weight: 600;
  height: 44px;
}
.login-switch {
  text-align: center;
  margin-top: 22px;
  font-size: 13px;
  color: #94a3b8;
}
</style>
