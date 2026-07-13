<script setup>
import { ref, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { EditPen, ChatDotRound, SwitchButton, List, TrendCharts, Expand, Link, Fold } from '@element-plus/icons-vue'
import { useAuthStore } from './stores/auth'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const activeMenu = computed(() => route.path)
const drawerOpen = ref(false)
const collapsed = ref(localStorage.getItem('sidebar_collapsed') === '1')

function toggleCollapse() {
  collapsed.value = !collapsed.value
  localStorage.setItem('sidebar_collapsed', collapsed.value ? '1' : '0')
}

const NAV_ITEMS = [
  { index: '/exam',    icon: EditPen,      label: '在线考试' },
  { index: '/chat',    icon: ChatDotRound, label: 'AI 助手' },
  { index: '/history', icon: List,         label: '考试历史' },
  { index: '/stats',   icon: TrendCharts,  label: '学习分析' },
]

const TITLE_MAP = {
  exam: '在线考试',
  chat: 'AI 助手',
  history: '考试历史',
  result: '考试结果',
  stats: '学习分析',
}
const pageTitle = computed(() => TITLE_MAP[route.name] || 'JLPT 学习系统')

function logout() {
  auth.logout()
  router.push('/login')
}

function navigate(path) {
  router.push(path)
  drawerOpen.value = false
}
</script>

<template>
  <div v-if="!auth.isLoggedIn">
    <router-view />
  </div>

  <el-container v-else class="app-container">
    <!-- ── 桌面侧边栏 ── -->
    <el-aside class="app-aside desktop-aside" :class="{ collapsed }" :width="collapsed ? '64px' : '200px'">
      <div class="brand">
        <span class="brand-mark">あ</span>
        <span v-show="!collapsed">JLPT 学习系统</span>
      </div>
      <el-menu :default-active="activeMenu" router class="aside-menu" :collapse="collapsed" :collapse-transition="false">
        <el-menu-item v-for="item in NAV_ITEMS" :key="item.index" :index="item.index">
          <el-icon><component :is="item.icon" /></el-icon>
          <template #title>{{ item.label }}</template>
        </el-menu-item>
      </el-menu>
      <div class="aside-footer">
        <a href="https://github.com/lsy7800/JapanesePassAgent" target="_blank" rel="noopener" class="contact-link" :title="collapsed ? 'GitHub 仓库' : ''">
          <el-icon><Link /></el-icon>
          <span v-show="!collapsed">GitHub 仓库</span>
        </a>
        <el-button class="logout-btn" text @click="logout" :title="collapsed ? '退出登录' : ''">
          <el-icon><SwitchButton /></el-icon>
          <span v-show="!collapsed">退出登录</span>
        </el-button>
      </div>
    </el-aside>

    <!-- ── 主内容区 ── -->
    <el-container class="main-container">
      <!-- 桌面顶栏 -->
      <div class="topbar desktop-topbar">
        <div class="topbar-left">
          <el-button text class="collapse-btn" @click="toggleCollapse" :title="collapsed ? '展开侧栏' : '收起侧栏'">
            <el-icon size="18"><Fold v-if="!collapsed" /><Expand v-else /></el-icon>
          </el-button>
          <div class="topbar-title">{{ pageTitle }}</div>
        </div>
        <div class="topbar-right">
          <span class="topbar-user" :title="auth.email">{{ auth.email }}</span>
          <el-button text class="topbar-logout" @click="logout">
            <el-icon><SwitchButton /></el-icon> 退出
          </el-button>
        </div>
      </div>

      <!-- 移动端顶部导航栏 -->
      <div class="mobile-header">
        <el-button class="hamburger" text @click="drawerOpen = true">
          <el-icon size="22"><Expand /></el-icon>
        </el-button>
        <span class="mobile-title">{{ pageTitle }}</span>
        <el-button size="small" text class="mobile-logout" @click="logout">
          <el-icon><SwitchButton /></el-icon>
        </el-button>
      </div>

      <el-main class="app-main">
        <router-view />
      </el-main>

      <footer v-if="route.name !== 'chat'" class="app-footer">
        <span>© 2026 JapanesePassAgent · JLPT 智能题库系统</span>
        <span class="footer-tech">
          FastAPI · Vue 3 · LangGraph
          <a href="https://github.com/lsy7800/JapanesePassAgent" target="_blank" rel="noopener" class="footer-link">GitHub</a>
        </span>
      </footer>
    </el-container>

    <!-- 移动端抽屉导航 -->
    <el-drawer
      v-model="drawerOpen"
      direction="ltr"
      size="200px"
      :with-header="false"
      class="nav-drawer"
    >
      <div class="drawer-brand">
        <span class="brand-mark">あ</span>
        <span>JLPT 学习系统</span>
      </div>
      <div
        v-for="item in NAV_ITEMS"
        :key="item.index"
        class="drawer-item"
        :class="{ active: activeMenu === item.index }"
        @click="navigate(item.index)"
      >
        <el-icon><component :is="item.icon" /></el-icon>
        <span>{{ item.label }}</span>
      </div>
      <div class="drawer-footer">
        <div class="user-info">{{ auth.email }}</div>
        <el-button size="small" text @click="logout">
          <el-icon><SwitchButton /></el-icon> 退出
        </el-button>
      </div>
    </el-drawer>
  </el-container>
</template>

<style>
* { box-sizing: border-box; }
body { margin: 0; }

.app-container { height: 100vh; overflow: hidden; }

/* ── 桌面侧边栏 ── */
.app-aside {
  background: #0b0f19;
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  transition: width 0.25s ease;
  overflow: hidden;
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
  white-space: nowrap;
}
.app-aside.collapsed .brand { padding: 0; justify-content: center; }
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
/* 折叠态：菜单项图标居中，去掉左内边距 */
.app-aside.collapsed .aside-menu { padding: 10px 0; }
.app-aside.collapsed .aside-menu .el-menu-item {
  padding: 0 !important;
  justify-content: center;
  margin: 4px 10px;
  width: calc(100% - 20px);
  min-width: 0;
}
.app-aside.collapsed .aside-menu .el-menu-item .el-icon {
  margin: 0 !important;
  width: auto;
}
.app-aside.collapsed .aside-menu .el-menu-item .el-tooltip__trigger {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
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
.app-aside.collapsed .aside-footer { padding: 12px 8px; }
.app-aside.collapsed .contact-link,
.app-aside.collapsed .logout-btn { justify-content: center; padding: 6px 0 !important; }
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

/* ── 桌面顶栏 ── */
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
.topbar-left { display: flex; align-items: center; gap: 12px; }
.collapse-btn { color: #64748b; padding: 6px; }
.collapse-btn:hover { color: #f59e0b; }
.topbar-right { display: flex; align-items: center; gap: 14px; }
.topbar-user {
  font-size: 13px;
  color: #64748b;
  max-width: 220px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.topbar-logout { color: #64748b; }
.topbar-logout:hover { color: #f59e0b; }

.user-info {
  font-size: 12px;
  color: #bfcbd9;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
  flex: 1;
}

/* ── 主区域 ── */
.main-container { flex: 1; min-width: 0; min-height: 0; flex-direction: column; }
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

/* ── 移动端顶部栏（默认隐藏） ── */
.mobile-header { display: none; }

/* ── 抽屉样式 ── */
.nav-drawer .el-drawer__body { padding: 0; display: flex; flex-direction: column; }
.drawer-brand {
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
.drawer-brand .brand-mark {
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
.drawer-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 14px;
  height: 42px;
  margin: 4px 10px;
  border-radius: 8px;
  cursor: pointer;
  color: #8b93a7;
  background: transparent;
  font-size: 14px;
  transition: all 0.2s;
}
.drawer-item:hover {
  background: rgba(255, 255, 255, 0.08);
  color: #fff;
}
.drawer-item.active {
  background: linear-gradient(135deg, #fbbf24 0%, #f59e0b 100%);
  color: #fff;
  box-shadow: 0 4px 12px rgba(245, 158, 11, 0.4);
}
.drawer-footer {
  margin-top: auto;
  padding: 12px 16px;
  border-top: 1px solid #f59e0b;
  background: #0b0f19;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
}
.drawer-footer .user-info { color: #bfcbd9; }
.drawer-footer .el-button { color: #bfcbd9; }

/* ── 移动端断点 ── */
@media (max-width: 640px) {
  .desktop-aside { display: none; }
  .desktop-topbar { display: none; }
  .mobile-header {
    display: flex;
    align-items: center;
    background: #0b0f19;
    padding: 0 12px;
    height: 50px;
    flex-shrink: 0;
    gap: 8px;
  }
  .hamburger { color: #fff; padding: 4px; }
  .mobile-title {
    flex: 1;
    color: #fff;
    font-size: 15px;
    font-weight: 600;
  }
  .mobile-logout { color: #bfcbd9; }
  .app-main { padding: 16px; }
}
</style>
