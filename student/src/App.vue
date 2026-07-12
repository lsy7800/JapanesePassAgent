<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { EditPen, ChatDotRound } from '@element-plus/icons-vue'

const route = useRoute()
const activeMenu = computed(() => route.path)
</script>

<template>
  <el-container class="app-container">
    <el-aside width="200px" class="app-aside">
      <div class="brand">JLPT 学习系统</div>
      <el-menu :default-active="activeMenu" router class="aside-menu">
        <el-menu-item index="/exam">
          <el-icon><EditPen /></el-icon>
          <span>在线考试</span>
        </el-menu-item>
        <el-menu-item index="/chat">
          <el-icon><ChatDotRound /></el-icon>
          <span>AI 助手</span>
        </el-menu-item>
      </el-menu>
    </el-aside>
    <el-main class="app-main">
      <router-view />
    </el-main>
  </el-container>
</template>

<style>
body {
  margin: 0;
}
.app-container {
  min-height: 100vh;
}
.app-aside {
  background: #304156;
  color: #fff;
}
.brand {
  height: 56px;
  line-height: 56px;
  text-align: center;
  font-size: 18px;
  font-weight: 600;
  color: #fff;
  background: #263445;
}
.aside-menu {
  border-right: none;
  background: #304156;
}
.aside-menu .el-menu-item {
  color: #bfcbd9;
}
.aside-menu .el-menu-item.is-active {
  color: #fff;
  background: #409eff;
}
.aside-menu .el-menu-item:hover {
  background: #263445;
}
.app-main {
  background: #f5f7fa;
}
</style>
