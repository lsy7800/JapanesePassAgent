<script setup>
import { ref, onMounted, computed } from 'vue'
import { getWeakPoints, getHistoryTrend, getWrongQuestions } from '../api/exam'

// ── 薄弱点 ──
const weakPoints = ref([])
const weakLoading = ref(false)

async function loadWeakPoints() {
  weakLoading.value = true
  try {
    const data = await getWeakPoints(10)
    weakPoints.value = data.items || []
  } finally {
    weakLoading.value = false
  }
}

const maxWrong = computed(() =>
  weakPoints.value.length ? Math.max(...weakPoints.value.map((w) => w.wrong_count)) : 1
)

// ── 趋势 ──
const history = ref([])
const histLoading = ref(false)

async function loadHistory() {
  histLoading.value = true
  try {
    const data = await getHistoryTrend(20)
    history.value = data.points || []
  } finally {
    histLoading.value = false
  }
}

// ── 错题集 ──
const wrongItems = ref([])
const wrongTotal = ref(0)
const wrongLoading = ref(false)
const kpFilter = ref('')
const wrongPage = ref(1)
const pageSize = 10

async function loadWrongQuestions() {
  wrongLoading.value = true
  try {
    const data = await getWrongQuestions({
      page: wrongPage.value,
      page_size: pageSize,
      knowledge_point: kpFilter.value || undefined,
    })
    wrongItems.value = data.items || []
    wrongTotal.value = data.total || 0
  } finally {
    wrongLoading.value = false
  }
}

function onKpFilter() {
  wrongPage.value = 1
  loadWrongQuestions()
}

function onPageChange(p) {
  wrongPage.value = p
  loadWrongQuestions()
}

onMounted(() => {
  loadWeakPoints()
  loadHistory()
  loadWrongQuestions()
})

// 展开/折叠错题
const expanded = ref(new Set())
function toggle(id) {
  if (expanded.value.has(id)) expanded.value.delete(id)
  else expanded.value.add(id)
}

function accuracyColor(acc) {
  if (acc >= 80) return '#67c23a'
  if (acc >= 60) return '#e6a23c'
  return '#f56c6c'
}

function barColor(rate) {
  if (rate >= 70) return '#f56c6c'
  if (rate >= 40) return '#e6a23c'
  return '#409eff'
}
</script>

<template>
  <div class="stats-page">
    <h2 class="page-title">学习分析</h2>

    <!-- 薄弱知识点 -->
    <el-card class="section-card" v-loading="weakLoading">
      <template #header>
        <span class="card-title">薄弱知识点 Top 10</span>
        <span class="card-sub">（基于历史错题聚合）</span>
      </template>
      <div v-if="!weakPoints.length && !weakLoading" class="empty-hint">
        暂无数据，完成并提交考试后自动统计
      </div>
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
          <span class="error-rate" :style="{ color: barColor(w.error_rate) }">
            {{ w.error_rate }}%
          </span>
        </div>
      </div>
    </el-card>

    <!-- 正确率趋势 -->
    <el-card class="section-card" v-loading="histLoading">
      <template #header>
        <span class="card-title">近期考试趋势</span>
        <span class="card-sub">（最近 {{ history.length }} 次）</span>
      </template>
      <div v-if="!history.length && !histLoading" class="empty-hint">
        暂无历史考试数据
      </div>
      <div v-else class="trend-wrap">
        <div class="trend-chart">
          <div
            v-for="p in history"
            :key="p.exam_id"
            class="trend-col"
            :title="`${p.date}  ${p.level}  ${p.score}/${p.total}  ${p.accuracy}%`"
          >
            <div class="trend-bar-outer">
              <div
                class="trend-bar-fill"
                :style="{
                  height: p.accuracy + '%',
                  background: accuracyColor(p.accuracy),
                }"
              />
            </div>
            <div class="trend-label">{{ p.accuracy }}%</div>
            <div class="trend-date">{{ p.date }}</div>
          </div>
        </div>
        <div class="trend-legend">
          <span class="dot" style="background:#67c23a" />≥80%
          <span class="dot" style="background:#e6a23c" />≥60%
          <span class="dot" style="background:#f56c6c" />&lt;60%
        </div>
      </div>
    </el-card>

    <!-- 错题集 -->
    <el-card class="section-card" v-loading="wrongLoading">
      <template #header>
        <div class="wrong-header">
          <span class="card-title">错题集</span>
          <div class="filter-row">
            <el-input
              v-model="kpFilter"
              placeholder="知识点筛选"
              size="small"
              clearable
              class="kp-input"
              @clear="onKpFilter"
              @keyup.enter="onKpFilter"
            />
            <el-button size="small" type="primary" @click="onKpFilter">筛选</el-button>
          </div>
        </div>
      </template>

      <div v-if="!wrongItems.length && !wrongLoading" class="empty-hint">
        {{ kpFilter ? `没有匹配「${kpFilter}」的错题` : '暂无错题记录，继续加油！' }}
      </div>

      <div v-for="item in wrongItems" :key="item.group_id" class="wrong-item">
        <div class="wrong-top" @click="toggle(item.group_id)">
          <el-tag size="small" :type="item.level <= 'N3' ? 'danger' : 'warning'" class="level-tag">
            {{ item.level }}
          </el-tag>
          <span class="wrong-content">{{ item.content }}</span>
          <el-icon class="expand-icon">
            <component :is="expanded.has(item.group_id) ? 'ArrowUp' : 'ArrowDown'" />
          </el-icon>
        </div>

        <div v-if="expanded.has(item.group_id)" class="wrong-detail">
          <div class="options-grid">
            <div
              v-for="(text, label) in item.options"
              :key="label"
              class="option-item"
              :class="{ correct: label === item.correct_answer }"
            >
              <span class="option-label">{{ label.toUpperCase() }}.</span> {{ text }}
            </div>
          </div>
          <div class="correct-line">正确答案：{{ item.correct_answer.toUpperCase() }}</div>
          <div v-if="item.analysis" class="analysis-text">{{ item.analysis }}</div>
          <div class="kp-tags">
            <el-tag
              v-for="kp in item.knowledge_points"
              :key="kp"
              size="small"
              type="info"
              class="kp-tag"
              @click="kpFilter = kp; onKpFilter()"
            >{{ kp }}</el-tag>
          </div>
        </div>
      </div>

      <el-pagination
        v-if="wrongTotal > pageSize"
        :total="wrongTotal"
        :page-size="pageSize"
        :current-page="wrongPage"
        layout="prev, pager, next"
        small
        class="wrong-pagination"
        @current-change="onPageChange"
      />
    </el-card>
  </div>
</template>

<style scoped>
.stats-page {
  max-width: 900px;
  margin: 0 auto;
}
.page-title {
  margin: 0 0 20px;
  font-size: 20px;
  font-weight: 600;
  color: #303133;
}
.section-card { margin-bottom: 20px; }
.card-title { font-weight: 600; font-size: 15px; }
.card-sub { font-size: 12px; color: #909399; margin-left: 8px; }
.empty-hint { text-align: center; color: #909399; padding: 28px 0; }

/* ── 薄弱点条形图 ── */
.bar-row {
  display: flex;
  align-items: center;
  margin-bottom: 10px;
  gap: 8px;
}
.bar-label {
  width: 100px;
  flex-shrink: 0;
  font-size: 12px;
  color: #303133;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  text-align: right;
}
.bar-track {
  flex: 1;
  min-width: 0;
  height: 14px;
  background: #f0f2f5;
  border-radius: 7px;
  overflow: hidden;
}
.bar-fill {
  height: 100%;
  border-radius: 7px;
  transition: width 0.4s;
  min-width: 4px;
}
.bar-meta {
  width: 100px;
  flex-shrink: 0;
  font-size: 11px;
  color: #606266;
  white-space: nowrap;
}
.error-rate { font-weight: 600; margin-left: 4px; }

/* ── 趋势图 ── */
.trend-wrap { overflow-x: auto; -webkit-overflow-scrolling: touch; }
.trend-chart {
  display: flex;
  align-items: flex-end;
  gap: 6px;
  min-height: 120px;
  padding-bottom: 4px;
  min-width: max-content;
}
.trend-col {
  display: flex;
  flex-direction: column;
  align-items: center;
  width: 40px;
  flex-shrink: 0;
}
.trend-bar-outer {
  width: 24px;
  height: 80px;
  background: #f0f2f5;
  border-radius: 4px 4px 0 0;
  display: flex;
  align-items: flex-end;
  overflow: hidden;
}
.trend-bar-fill {
  width: 100%;
  border-radius: 4px 4px 0 0;
  transition: height 0.4s;
}
.trend-label { font-size: 11px; color: #606266; margin-top: 4px; }
.trend-date {
  font-size: 10px;
  color: #909399;
  white-space: nowrap;
  transform: rotate(-45deg);
  transform-origin: top left;
  margin-top: 8px;
  margin-left: 4px;
  width: 48px;
}
.trend-legend {
  margin-top: 30px;
  font-size: 12px;
  color: #606266;
  display: flex;
  gap: 14px;
  flex-wrap: wrap;
}
.dot {
  display: inline-block;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  margin-right: 3px;
  vertical-align: middle;
}

/* ── 错题集 ── */
.wrong-header { display: flex; align-items: center; justify-content: space-between; gap: 10px; flex-wrap: wrap; }
.filter-row { display: flex; align-items: center; gap: 6px; }
.kp-input { width: 160px; }

.wrong-item {
  border: 1px solid #e4e7ed;
  border-radius: 6px;
  margin-bottom: 10px;
  overflow: hidden;
}
.wrong-top {
  display: flex;
  align-items: center;
  padding: 10px 12px;
  cursor: pointer;
  gap: 8px;
  background: #fafafa;
  transition: background 0.2s;
  min-height: 44px;
}
.wrong-top:hover { background: #f0f5ff; }
.wrong-top:active { background: #e8f0fe; }
.level-tag { flex-shrink: 0; }
.wrong-content {
  flex: 1;
  font-size: 13px;
  color: #303133;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.expand-icon { flex-shrink: 0; color: #909399; }

.wrong-detail {
  padding: 12px 14px;
  border-top: 1px solid #e4e7ed;
  background: #fff;
}
.options-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 6px;
  margin-bottom: 10px;
}
.option-item {
  font-size: 13px;
  color: #606266;
  padding: 4px 8px;
  border-radius: 4px;
  border: 1px solid transparent;
  word-break: break-all;
}
.option-item.correct {
  border-color: #67c23a;
  background: #f0f9eb;
  color: #67c23a;
  font-weight: 600;
}
.option-label { font-weight: 600; }
.correct-line { font-size: 13px; font-weight: 600; color: #67c23a; margin-bottom: 8px; }
.analysis-text {
  font-size: 13px;
  color: #606266;
  line-height: 1.7;
  margin-bottom: 8px;
  white-space: pre-wrap;
}
.kp-tags { margin-top: 4px; }
.kp-tag {
  margin-right: 4px;
  margin-top: 4px;
  cursor: pointer;
  min-height: 28px;
}
.wrong-pagination { margin-top: 14px; text-align: center; }

/* ── 移动端 ── */
@media (max-width: 640px) {
  .page-title { font-size: 17px; margin-bottom: 14px; }
  .bar-label { width: 72px; font-size: 11px; }
  .bar-meta { width: 76px; font-size: 10px; }
  .options-grid { grid-template-columns: 1fr; }
  .kp-input { width: 120px; }
}
</style>
