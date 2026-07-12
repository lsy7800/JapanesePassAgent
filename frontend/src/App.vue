<script setup>
</script>

<template>
  <el-container class="app-container">
    <el-header class="app-header">
      <span class="title">JLPT 题库管理系统</span>
      <span class="subtitle">查阅 · 校对</span>
    </el-header>
    <el-main>
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
.app-header {
  display: flex;
  align-items: baseline;
  gap: 12px;
  background: #409eff;
  color: #fff;
}
.app-header .title {
  font-size: 20px;
  font-weight: 600;
}
.app-header .subtitle {
  font-size: 13px;
  opacity: 0.85;
}
</style>
