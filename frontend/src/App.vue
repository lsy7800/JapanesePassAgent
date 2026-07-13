<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Collection, SwitchButton, DataLine, User, Link } from '@element-plus/icons-vue'
import { useAuthStore } from './stores/auth'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const activeMenu = computed(() => {
  if (route.path.startsWith('/questions')) return '/questions'
  if (route.path.startsWith('/users')) return '/users'
  return '/'
})

const TITLE_MAP = {
  dashboard: '数据看板',
  list: '题库管理',
  create: '新建题组',
  detail: '题组详情',
  users: '用户管理',
}
const pageTitle = computed(() => TITLE_MAP[route.name] || 'JLPT 管理后台')

function logout() {
  auth.logout()
  router.push('/login')
}
</script>

<template>
  <div v-if="!auth.isLoggedIn">
    <router-view />
  </div>
  <el-container v-else class="app-container">
    <el-aside width="200px" class="app-aside">
      <div class="brand">
        <span class="brand-mark">管</span>
        <span>JLPT 管理后台</span>
      </div>
      <el-menu :default-active="activeMenu" router class="aside-menu">
        <el-menu-item index="/">
          <el-icon><DataLine /></el-icon>
          <span>数据看板</span>
        </el-menu-item>
        <el-menu-item index="/questions">
          <el-icon><Collection /></el-icon>
          <span>题库管理</span>
        </el-menu-item>
        <el-menu-item index="/users">
          <el-icon><User /></el-icon>
          <span>用户管理</span>
        </el-menu-item>
      </el-menu>
      <div class="aside-footer">
        <a href="https://github.com/lsy7800/JapanesePassAgent" target="_blank" rel="noopener" class="contact-link">
          <el-icon><Link /></el-icon>
          <span>GitHub 仓库</span>
        </a>
        <el-button class="logout-btn" text @click="logout">
          <el-icon><SwitchButton /></el-icon>
          <span>退出登录</span>
        </el-button>
      </div>
    </el-aside>

    <el-container class="main-container">
      <!-- 顶栏 -->
      <div class="topbar">
        <div class="topbar-title">{{ pageTitle }}</div>
        <div class="topbar-right">
          <span class="topbar-user" :title="auth.email">{{ auth.email }}</span>
          <el-button text class="topbar-logout" @click="logout">
            <el-icon><SwitchButton /></el-icon> 退出
          </el-button>
        </div>
      </div>

      <el-main class="app-main">
        <router-view />
      </el-main>

      <footer class="app-footer">
        <span>© 2026 JapanesePassAgent · JLPT 管理后台</span>
        <span class="footer-tech">
          FastAPI · Vue 3 · Element Plus
          <a href="https://github.com/lsy7800/JapanesePassAgent" target="_blank" rel="noopener" class="footer-link">GitHub</a>
        </span>
      </footer>
    </el-container>
  </el-container>
</template>

<style>
body { margin: 0; }
.app-container { height: 100vh; overflow: hidden; }
.app-aside {
  background: #0b0f19;
  color: #fff;
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
}
.brand {
  height: 56px;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 18px;
  font-size: 16px;
  font-weight: 600;
  color: #fff;
  background: #050709;
  flex-shrink: 0;
  letter-spacing: 0.5px;
}
.brand .brand-mark {
  width: 28px;
  height: 28px;
  border-radius: 8px;
  background: linear-gradient(135deg, #fcd34d 0%, #fbbf24 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  font-size: 14px;
}
.aside-menu {
  border-right: none;
  background: transparent;
  flex: 1;
  padding: 10px;
  box-sizing: border-box;
}
.aside-menu .el-menu-item {
  color: #8b93a7;
  height: 42px;
  line-height: 42px;
  margin: 4px 0;
  border-radius: 8px;
  padding: 0 14px !important;
}
.aside-menu .el-menu-item:hover {
  background: rgba(255, 255, 255, 0.08);
  color: #fff;
}
.aside-menu .el-menu-item.is-active {
  color: #fff;
  background: linear-gradient(135deg, #fbbf24 0%, #f59e0b 100%);
  box-shadow: 0 4px 12px rgba(245, 158, 11, 0.4);
}

/* ── 侧栏底部：联系方式 + 退出 ── */
.aside-footer {
  flex-shrink: 0;
  padding: 12px 14px;
  border-top: 1px solid rgba(255, 255, 255, 0.08);
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.contact-link {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  border-radius: 8px;
  color: #8b93a7;
  text-decoration: none;
  font-size: 13px;
  transition: all 0.2s;
}
.contact-link:hover {
  background: rgba(255, 255, 255, 0.08);
  color: #fbbf24;
}
.logout-btn {
  width: 100%;
  justify-content: flex-start;
  height: 38px;
  padding: 0 10px !important;
  border-radius: 8px;
  color: #8b93a7;
  font-size: 13px;
}
.logout-btn:hover {
  color: #fff;
  background: rgba(255, 255, 255, 0.08);
}

/* ── 主区 ── */
.main-container { flex: 1; min-width: 0; min-height: 0; flex-direction: column; }

/* ── 顶栏 ── */
.topbar {
  height: 56px;
  flex-shrink: 0;
  background: #fff;
  border-bottom: 1px solid #e5e9f2;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 32px;
}
.topbar-title { font-size: 17px; font-weight: 600; color: #1f2937; }
.topbar-right { display: flex; align-items: center; gap: 14px; }
.topbar-user {
  font-size: 13px;
  color: #64748b;
  max-width: 240px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.topbar-logout { color: #64748b; }
.topbar-logout:hover { color: #f59e0b; }

.app-main {
  background: #fbf9f4;
  padding: 24px 32px;
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overscroll-behavior: contain;
}

/* ── 页脚 ── */
.app-footer {
  flex-shrink: 0;
  height: 40px;
  background: #fff;
  border-top: 1px solid #eef0f5;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 32px;
  font-size: 12px;
  color: #94a3b8;
}
.footer-tech { display: flex; align-items: center; gap: 12px; }
.footer-link {
  color: #fbbf24;
  text-decoration: none;
  font-weight: 500;
}
.footer-link:hover { text-decoration: underline; }
</style>
