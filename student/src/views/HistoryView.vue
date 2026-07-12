<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { listExams } from '../api/exam'

const router = useRouter()
const loading = ref(false)
const items = ref([])
const total = ref(0)
const page = ref(1)
const PAGE_SIZE = 20

function accuracy(item) {
  if (!item.total) return '—'
  return Math.round((item.score / item.total) * 100) + '%'
}

function accuracyType(item) {
  const pct = item.total ? (item.score / item.total) * 100 : 0
  if (pct >= 80) return 'success'
  if (pct >= 60) return 'warning'
  return 'danger'
}

async function load() {
  loading.value = true
  try {
    const data = await listExams(page.value, PAGE_SIZE)
    items.value = data.items
    total.value = data.total
  } catch (e) {
    ElMessage.error('加载失败：' + (e.response?.data?.detail || e.message))
  } finally {
    loading.value = false
  }
}

function viewResult(id) {
  router.push(`/result/${id}`)
}

onMounted(load)
</script>

<template>
  <div class="history-wrap">
    <div class="history-head">
      <b>考试历史</b>
      <span class="sub">共 {{ total }} 次已提交</span>
    </div>

    <el-empty v-if="!loading && items.length === 0" description="还没有考试记录，去考一套吧" >
      <el-button type="primary" @click="router.push('/exam')">去考试</el-button>
    </el-empty>

    <el-table v-else v-loading="loading" :data="items" stripe style="width:100%">
      <el-table-column prop="submitted_at" label="提交时间" width="160" />
      <el-table-column prop="level" label="级别" width="80">
        <template #default="{ row }">
          <el-tag size="small" type="info">{{ row.level || '综合' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="total" label="题数" width="70" align="center" />
      <el-table-column label="得分" width="90" align="center">
        <template #default="{ row }">
          <b>{{ row.score }}</b> / {{ row.total }}
        </template>
      </el-table-column>
      <el-table-column label="正确率" width="100" align="center">
        <template #default="{ row }">
          <el-tag :type="accuracyType(row)" size="small">{{ accuracy(row) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" align="center">
        <template #default="{ row }">
          <el-button size="small" type="primary" link @click="viewResult(row.id)">查看详情</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div v-if="total > PAGE_SIZE" class="pagination">
      <el-pagination
        v-model:current-page="page"
        :page-size="PAGE_SIZE"
        :total="total"
        layout="prev, pager, next"
        @current-change="load"
      />
    </div>
  </div>
</template>

<style scoped>
.history-wrap {
  max-width: 820px;
}
.history-head {
  display: flex;
  align-items: baseline;
  gap: 12px;
  margin-bottom: 16px;
}
.sub {
  font-size: 13px;
  color: #909399;
}
.pagination {
  margin-top: 16px;
  display: flex;
  justify-content: center;
}
</style>
