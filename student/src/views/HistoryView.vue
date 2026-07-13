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
      <span class="sub">共 {{ total }} 次已提交</span>
    </div>

    <el-empty v-if="!loading && items.length === 0" description="还没有考试记录，去考一套吧">
      <el-button type="primary" @click="router.push('/exam')">去考试</el-button>
    </el-empty>

    <template v-else>
      <!-- 桌面：表格 -->
      <el-table
        v-loading="loading"
        :data="items"
        stripe
        style="width:100%"
        class="desktop-table"
      >
        <el-table-column prop="submitted_at" label="提交时间" min-width="140" />
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
        <el-table-column label="正确率" width="90" align="center">
          <template #default="{ row }">
            <el-tag :type="accuracyType(row)" size="small">{{ accuracy(row) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="90" align="center">
          <template #default="{ row }">
            <el-button size="small" type="primary" link @click="viewResult(row.id)">详情</el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 移动端：卡片列表 -->
      <div v-loading="loading" class="mobile-list">
        <div
          v-for="row in items"
          :key="row.id"
          class="history-card"
          @click="viewResult(row.id)"
        >
          <div class="hc-top">
            <el-tag size="small" type="info">{{ row.level || '综合' }}</el-tag>
            <el-tag :type="accuracyType(row)" size="small">{{ accuracy(row) }}</el-tag>
            <span class="hc-score"><b>{{ row.score }}</b>/{{ row.total }}</span>
          </div>
          <div class="hc-time">{{ row.submitted_at }}</div>
        </div>
      </div>
    </template>

    <div v-if="total > PAGE_SIZE" class="pagination">
      <el-pagination
        v-model:current-page="page"
        :page-size="PAGE_SIZE"
        :total="total"
        layout="prev, pager, next"
        small
        @current-change="load"
      />
    </div>
  </div>
</template>

<style scoped>
.history-wrap {
  max-width: 820px;
  margin: 0 auto;
}
.history-head {
  display: flex;
  align-items: baseline;
  gap: 12px;
  margin-bottom: 16px;
}
.sub { font-size: 13px; color: #909399; }
.pagination { margin-top: 16px; display: flex; justify-content: center; }

/* 移动端卡片默认隐藏 */
.mobile-list { display: none; }

.history-card {
  background: #fff;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  padding: 12px 14px;
  margin-bottom: 10px;
  cursor: pointer;
  transition: box-shadow 0.2s;
  active-transform: scale(0.99);
}
.history-card:active { box-shadow: 0 0 0 2px #f59e0b40; }
.hc-top {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}
.hc-score { margin-left: auto; font-size: 15px; color: #303133; }
.hc-time { font-size: 12px; color: #909399; }

@media (max-width: 640px) {
  .desktop-table { display: none; }
  .mobile-list { display: block; }
}
</style>
