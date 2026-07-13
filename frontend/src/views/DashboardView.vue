<script setup>
import { ref, onMounted, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { Collection, User, EditPen, TrendCharts } from '@element-plus/icons-vue'
import { getOverview, getAdminWeakPoints } from '../api/admin'

const loading = ref(false)
const overview = ref(null)
const weakPoints = ref([])

const TYPE_LABEL = {
  single_choice: '单项选择',
  cloze: '完形填空',
  reading: '阅读理解',
}

const cards = computed(() => {
  const o = overview.value
  if (!o) return []
  return [
    { label: '题库题组', value: o.total_questions, icon: Collection, color: '#f59e0b' },
    { label: '注册用户', value: o.total_users, icon: User, color: '#67c23a' },
    { label: '已提交考试', value: o.total_exams, icon: EditPen, color: '#e6a23c' },
    { label: '平均正确率', value: o.avg_accuracy + '%', icon: TrendCharts, color: '#f56c6c' },
  ]
})

const maxLevel = computed(() =>
  overview.value?.by_level?.length
    ? Math.max(...overview.value.by_level.map((l) => l.count))
    : 1
)
const maxWrong = computed(() =>
  weakPoints.value.length ? Math.max(...weakPoints.value.map((w) => w.wrong_count)) : 1
)

function barColor(rate) {
  if (rate >= 70) return '#f56c6c'
  if (rate >= 40) return '#e6a23c'
  return '#f59e0b'
}

async function load() {
  loading.value = true
  try {
    const [ov, wp] = await Promise.all([getOverview(), getAdminWeakPoints(10)])
    overview.value = ov
    weakPoints.value = wp.items || []
  } catch (e) {
    ElMessage.error('加载失败：' + (e.response?.data?.detail || e.message))
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div v-loading="loading" class="dashboard">
    <!-- 概览卡片 -->
    <div class="cards">
      <el-card v-for="c in cards" :key="c.label" shadow="hover" class="stat-card">
        <div class="stat-inner">
          <div class="stat-icon" :style="{ background: c.color }">
            <el-icon :size="22"><component :is="c.icon" /></el-icon>
          </div>
          <div class="stat-text">
            <div class="stat-value">{{ c.value }}</div>
            <div class="stat-label">{{ c.label }}</div>
          </div>
        </div>
      </el-card>
    </div>

    <div class="charts">
      <!-- 级别分布 -->
      <el-card shadow="never" class="chart-card">
        <template #header><b>各级别题量分布</b></template>
        <div v-if="!overview?.by_level?.length" class="empty-hint">暂无数据</div>
        <div v-for="l in overview?.by_level || []" :key="l.label" class="dist-row">
          <div class="dist-label">{{ l.label }}</div>
          <div class="dist-track">
            <div class="dist-fill" :style="{ width: Math.round((l.count / maxLevel) * 100) + '%' }" />
          </div>
          <div class="dist-count">{{ l.count }}</div>
        </div>

        <el-divider v-if="overview?.by_type?.length" />
        <div v-if="overview?.by_type?.length" class="type-dist">
          <el-tag
            v-for="t in overview.by_type"
            :key="t.label"
            type="info"
            effect="plain"
            class="type-tag"
          >
            {{ TYPE_LABEL[t.label] || t.label }}：{{ t.count }}
          </el-tag>
        </div>
      </el-card>

      <!-- 平台薄弱点 -->
      <el-card shadow="never" class="chart-card">
        <template #header><b>平台薄弱知识点 Top 10</b></template>
        <div v-if="!weakPoints.length" class="empty-hint">暂无错题数据</div>
        <div v-for="w in weakPoints" :key="w.point" class="bar-row">
          <div class="bar-label" :title="w.point">{{ w.point }}</div>
          <div class="bar-track">
            <div
              class="bar-fill"
              :style="{
                width: Math.round((w.wrong_count / maxWrong) * 100) + '%',
                background: barColor(w.error_rate),
              }"
            />
          </div>
          <div class="bar-meta">
            错{{ w.wrong_count }}/共{{ w.total_count }}
            <span :style="{ color: barColor(w.error_rate), fontWeight: 600 }">{{ w.error_rate }}%</span>
          </div>
        </div>
      </el-card>
    </div>
  </div>
</template>

<style scoped>
.dashboard { max-width: 1100px; }
.page-title { margin: 0 0 20px; font-size: 20px; font-weight: 600; color: #303133; }

/* 概览卡片 */
.cards {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 16px;
  margin-bottom: 20px;
}
.stat-inner { display: flex; align-items: center; gap: 14px; }
.stat-icon {
  width: 48px;
  height: 48px;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  flex-shrink: 0;
}
.stat-value { font-size: 26px; font-weight: 700; color: #303133; line-height: 1.2; }
.stat-label { font-size: 13px; color: #909399; margin-top: 2px; }

/* 图表区 */
.charts {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
}
.chart-card { min-width: 0; }
.empty-hint { text-align: center; color: #909399; padding: 24px 0; }

/* 级别分布 */
.dist-row { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }
.dist-label { width: 48px; flex-shrink: 0; font-size: 13px; color: #303133; }
.dist-track { flex: 1; min-width: 0; height: 16px; background: #f0f2f5; border-radius: 8px; overflow: hidden; }
.dist-fill { height: 100%; background: #f59e0b; border-radius: 8px; transition: width .4s; min-width: 4px; }
.dist-count { width: 40px; flex-shrink: 0; text-align: right; font-size: 13px; color: #606266; }
.type-dist { display: flex; flex-wrap: wrap; gap: 8px; }

/* 薄弱点条形 */
.bar-row { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; }
.bar-label {
  width: 96px;
  flex-shrink: 0;
  font-size: 12px;
  color: #303133;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  text-align: right;
}
.bar-track { flex: 1; min-width: 0; height: 14px; background: #f0f2f5; border-radius: 7px; overflow: hidden; }
.bar-fill { height: 100%; border-radius: 7px; transition: width .4s; min-width: 4px; }
.bar-meta { width: 108px; flex-shrink: 0; font-size: 11px; color: #606266; white-space: nowrap; }

@media (max-width: 900px) {
  .charts { grid-template-columns: 1fr; }
}
</style>
