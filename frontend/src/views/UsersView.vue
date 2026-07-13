<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useAuthStore } from '../stores/auth'
import { listUsers, updateUser } from '../api/admin'

const auth = useAuthStore()

const loading = ref(false)
const rows = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)

const filters = reactive({ q: '', role: '' })

const ROLE_OPTIONS = [
  { value: 'student', label: '学生' },
  { value: 'admin', label: '管理员' },
]

// 是否是当前登录管理员自己（按邮箱唯一）
const isSelf = (row) => row.email === auth.email

async function load() {
  loading.value = true
  try {
    const data = await listUsers({
      q: filters.q,
      role: filters.role,
      page: page.value,
      page_size: pageSize.value,
    })
    rows.value = data.items
    total.value = data.total
  } catch (e) {
    ElMessage.error('加载失败：' + (e.response?.data?.detail || e.message))
  } finally {
    loading.value = false
  }
}

function onSearch() {
  page.value = 1
  load()
}

function onReset() {
  filters.q = ''
  filters.role = ''
  page.value = 1
  load()
}

function onPageChange(p) {
  page.value = p
  load()
}

async function onRoleChange(row, newRole) {
  const oldRole = row.role
  try {
    const updated = await updateUser(row.id, { role: newRole })
    Object.assign(row, updated)
    ElMessage.success(`已将 ${row.email} 设为${newRole === 'admin' ? '管理员' : '学生'}`)
  } catch (e) {
    row.role = oldRole // 回滚
    ElMessage.error('修改失败：' + (e.response?.data?.detail || e.message))
  }
}

async function onToggleActive(row) {
  const next = !row.is_active
  const action = next ? '启用' : '停用'
  try {
    await ElMessageBox.confirm(`确定${action}账号 ${row.email}？`, `${action}确认`, {
      type: next ? 'info' : 'warning',
      confirmButtonText: action,
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  try {
    const updated = await updateUser(row.id, { is_active: next })
    Object.assign(row, updated)
    ElMessage.success(`已${action}`)
  } catch (e) {
    ElMessage.error(`${action}失败：` + (e.response?.data?.detail || e.message))
  }
}

onMounted(load)
</script>

<template>
  <div>
    <el-card shadow="never" class="filter-card">
      <el-form :inline="true" :model="filters" @submit.prevent>
        <el-form-item label="邮箱">
          <el-input
            v-model="filters.q"
            placeholder="邮箱关键词"
            clearable
            style="width: 200px"
            @keyup.enter="onSearch"
          />
        </el-form-item>
        <el-form-item label="角色">
          <el-select v-model="filters.role" placeholder="全部" clearable style="width: 120px">
            <el-option v-for="r in ROLE_OPTIONS" :key="r.value" :label="r.label" :value="r.value" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="onSearch">查询</el-button>
          <el-button @click="onReset">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-table :data="rows" v-loading="loading" border stripe style="margin-top: 16px">
      <el-table-column prop="id" label="ID" width="70" />
      <el-table-column prop="email" label="邮箱" min-width="200" show-overflow-tooltip>
        <template #default="{ row }">
          {{ row.email }}
          <el-tag v-if="isSelf(row)" size="small" type="success" effect="plain" style="margin-left: 4px">
            我
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="角色" width="140">
        <template #default="{ row }">
          <el-select
            :model-value="row.role"
            size="small"
            :disabled="isSelf(row)"
            style="width: 110px"
            @change="(v) => onRoleChange(row, v)"
          >
            <el-option v-for="r in ROLE_OPTIONS" :key="r.value" :label="r.label" :value="r.value" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column prop="exam_count" label="答卷数" width="90" align="center" />
      <el-table-column prop="created_at" label="注册时间" width="160" />
      <el-table-column label="状态" width="90" align="center">
        <template #default="{ row }">
          <el-tag :type="row.is_active ? 'success' : 'info'" size="small">
            {{ row.is_active ? '启用' : '停用' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="100" fixed="right" align="center">
        <template #default="{ row }">
          <el-button
            link
            :type="row.is_active ? 'danger' : 'primary'"
            :disabled="isSelf(row)"
            @click="onToggleActive(row)"
          >
            {{ row.is_active ? '停用' : '启用' }}
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-pagination
      style="margin-top: 16px; justify-content: flex-end"
      layout="total, prev, pager, next"
      :total="total"
      :page-size="pageSize"
      :current-page="page"
      @current-change="onPageChange"
    />
  </div>
</template>

<style scoped>
.page-title { margin: 0 0 16px; font-size: 20px; font-weight: 600; color: #303133; }
.filter-card { background: #fafafa; }
</style>
