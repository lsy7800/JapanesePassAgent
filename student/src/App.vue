<script setup>
import { ref, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { EditPen, ChatDotRound, SwitchButton, List, TrendCharts, Expand } from '@element-plus/icons-vue'
import { useAuthStore } from './stores/auth'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const activeMenu = computed(() => route.path)
const drawerOpen = ref(false)

const NAV_ITEMS = [
  { index: '/exam',    icon: EditPen,      label: '在线考试' },
  { index: '/chat',    icon: ChatDotRound, label: 'AI 助手' },
  { index: '/history', icon: List,         label: '考试历史' },
  { index: '/stats',   icon: TrendCharts,  label: '学习分析' },
]

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
    <el-aside class="app-aside desktop-aside" width="200px">
      <div class="brand">JLPT 学习系统</div>
      <el-menu :default-active="activeMenu" router class="aside-menu">
        <el-menu-item v-for="item in NAV_ITEMS" :key="item.index" :index="item.index">
          <el-icon><component :is="item.icon" /></el-icon>
          <span>{{ item.label }}</span>
        </el-menu-item>
      </el-menu>
      <div class="aside-footer">
        <div class="user-info" :title="auth.email">{{ auth.email }}</div>
        <el-button size="small" text @click="logout">
          <el-icon><SwitchButton /></el-icon> 退出
        </el-button>
      </div>
    </el-aside>

    <!-- ── 主内容区 ── -->
    <el-container class="main-container">
      <!-- 移动端顶部导航栏 -->
      <div class="mobile-header">
        <el-button class="hamburger" text @click="drawerOpen = true">
          <el-icon size="22"><Expand /></el-icon>
        </el-button>
        <span class="mobile-title">JLPT 学习系统</span>
        <el-button size="small" text class="mobile-logout" @click="logout">
          <el-icon><SwitchButton /></el-icon>
        </el-button>
      </div>

      <el-main class="app-main">
        <router-view />
      </el-main>
    </el-container>

    <!-- 移动端抽屉导航 -->
    <el-drawer
      v-model="drawerOpen"
      direction="ltr"
      size="200px"
      :with-header="false"
      class="nav-drawer"
    >
      <div class="drawer-brand">JLPT 学习系统</div>
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

.app-container { min-height: 100vh; }

/* ── 桌面侧边栏 ── */
.app-aside {
  background: #304156;
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
}
.brand {
  height: 56px;
  line-height: 56px;
  text-align: center;
  font-size: 17px;
  font-weight: 600;
  color: #fff;
  background: #263445;
  flex-shrink: 0;
}
.aside-menu {
  border-right: none;
  background: #304156;
  flex: 1;
}
.aside-menu .el-menu-item { color: #bfcbd9; }
.aside-menu .el-menu-item.is-active { color: #fff; background: #409eff; }
.aside-menu .el-menu-item:hover { background: #263445; }
.aside-footer {
  padding: 12px 16px;
  border-top: 1px solid #3d5166;
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-shrink: 0;
  gap: 6px;
}
.user-info {
  font-size: 12px;
  color: #bfcbd9;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
  flex: 1;
}
.aside-footer .el-button { color: #bfcbd9; flex-shrink: 0; }
.aside-footer .el-button:hover { color: #fff; }

/* ── 主区域 ── */
.main-container { flex: 1; min-width: 0; flex-direction: column; }
.app-main { background: #f5f7fa; padding: 20px; }

/* ── 移动端顶部栏（默认隐藏） ── */
.mobile-header { display: none; }

/* ── 抽屉样式 ── */
.nav-drawer .el-drawer__body { padding: 0; display: flex; flex-direction: column; }
.drawer-brand {
  height: 56px;
  line-height: 56px;
  padding: 0 20px;
  font-size: 16px;
  font-weight: 600;
  color: #fff;
  background: #263445;
  flex-shrink: 0;
}
.drawer-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px 20px;
  cursor: pointer;
  color: #bfcbd9;
  background: #304156;
  font-size: 14px;
  transition: background 0.2s;
}
.drawer-item:hover,
.drawer-item.active {
  background: #409eff;
  color: #fff;
}
.drawer-footer {
  margin-top: auto;
  padding: 12px 16px;
  border-top: 1px solid #3d5166;
  background: #304156;
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
  .mobile-header {
    display: flex;
    align-items: center;
    background: #304156;
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
  .app-main { padding: 12px; }
}
</style>
