<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Collection, SwitchButton } from '@element-plus/icons-vue'
import { useAuthStore } from './stores/auth'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const activeMenu = computed(() => {
  if (route.path.startsWith('/questions') || route.path === '/') return '/'
  return route.path
})

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
      <div class="brand">JLPT 管理后台</div>
      <el-menu :default-active="activeMenu" router class="aside-menu">
        <el-menu-item index="/">
          <el-icon><Collection /></el-icon>
          <span>题库管理</span>
        </el-menu-item>
      </el-menu>
      <div class="aside-footer">
        <div class="user-info">{{ auth.email }}</div>
        <el-button size="small" text @click="logout">
          <el-icon><SwitchButton /></el-icon> 退出
        </el-button>
      </div>
    </el-aside>
    <el-main class="app-main">
      <router-view />
    </el-main>
  </el-container>
</template>

<style>
body { margin: 0; }
.app-container { min-height: 100vh; }
.app-aside {
  background: #304156;
  color: #fff;
  display: flex;
  flex-direction: column;
}
.brand {
  height: 56px;
  line-height: 56px;
  text-align: center;
  font-size: 18px;
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
}
.user-info {
  font-size: 12px;
  color: #bfcbd9;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 110px;
}
.aside-footer .el-button { color: #bfcbd9; }
.aside-footer .el-button:hover { color: #fff; }
.app-main { background: #f5f7fa; }
</style>
