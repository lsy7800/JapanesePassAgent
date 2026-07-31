<script setup>
import { ref, onMounted, computed } from 'vue'
import { ArrowDown } from '@element-plus/icons-vue'
import { getWeakPoints, getHistoryTrend, getWrongQuestions } from '../api/exam'
import { collapseEnter, collapseLeave } from '../utils/collapse'

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
  return '#f59e0b'
}
</script>

<template>
  <div class="stats-page">
    <!-- 薄弱知识点 -->
    <el-card class="section-card" v-loading="weakLoading">
      <template #header>
        <span class="card-title">薄弱知识点 Top 10</span>
        <span class="card-sub">（基于历史错题聚合）</span>
      </template>
      <div v-if="!weakPoints.length && !weakLoading" class="empty-hint">
        暂无数据，完成并提交考试后自动统计
      </div>
      <!-- 逐条错开生长，Top 10 依次铺开比一次性全出更易读。
           延迟写成自定义属性 --d：CSS 变量会继承，行和条内的 .bar-fill
           都能读到同一个值，不必两处各写一遍 -->
      <div
        v-for="(w, i) in weakPoints"
        :key="w.point"
        class="bar-row"
        :style="{ '--d': `${i * 45}ms` }"
      >
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
          <!-- 柱子从左到右依次长起来；--d 见 .bar-row 处的说明 -->
          <div
            v-for="(p, i) in history"
            :key="p.exam_id"
            class="trend-col"
            :style="{ '--d': `${Math.min(i, 12) * 40}ms` }"
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
          <!-- 固定用 ArrowDown 靠 CSS 旋转 180°，比互换 ArrowUp/ArrowDown 两个组件更顺滑
               （组件替换是新建元素，无法过渡） -->
          <el-icon class="expand-icon" :class="{ open: expanded.has(item.group_id) }">
            <ArrowDown />
          </el-icon>
        </div>

        <!-- 展开/收起做高度过渡。内容高度不定（选项数、解析长短各异），
             所以在 JS 钩子里量出真实高度，纯 CSS 的 max-height 猜值会让动画提前结束 -->
        <transition name="detail" @enter="collapseEnter" @leave="collapseLeave">
          <div v-if="expanded.has(item.group_id)" class="wrong-detail">
            <!-- 内边距放在这一层：外层折叠到 height:0 时不能带纵向 padding，否则收不干净 -->
            <div class="detail-inner">
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
        </transition>
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
/* 三张分析卡依次落位 */
.section-card {
  margin-bottom: 20px;
  animation: fade-up var(--dur-slow) var(--ease-out) backwards;
}
.section-card:nth-of-type(2) { animation-delay: 70ms; }
.section-card:nth-of-type(3) { animation-delay: 140ms; }
.card-title { font-weight: 600; font-size: 15px; }
.card-sub { font-size: 12px; color: #909399; margin-left: 8px; }
.empty-hint { text-align: center; color: #909399; padding: 28px 0; }

/* ── 薄弱点条形图 ── */
/* --d 由模板按下标注入；这里给个 0ms 兜底，避免变量缺失时 animation-delay 失效 */
.bar-row {
  display: flex;
  align-items: center;
  margin-bottom: 10px;
  gap: 8px;
  animation: fade-in var(--dur-base) var(--ease-out) var(--d, 0ms) backwards;
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
/* width 由 :style 内联绑定，首次渲染初值即终值，transition 不会触发。
   改用 scaleX 动画：终态 scaleX(1) 就是绑定的 width，与具体数值无关。
   保留 width 的 transition，供筛选后数值变化时平滑过渡。 */
.bar-fill {
  height: 100%;
  border-radius: 7px;
  transition: width var(--dur-slow) var(--ease-out);
  min-width: 4px;
  transform-origin: left center;
  animation: bar-grow var(--dur-slow) var(--ease-out) var(--d, 0ms) backwards;
}
@keyframes bar-grow {
  from { transform: scaleX(0); }
  to   { transform: scaleX(1); }
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
/* 同 .bar-fill：height 由内联 style 绑定，首次渲染没有过渡起点，
   所以用 scaleY 从底部长起来。transform-origin 取 bottom，柱子才是"往上生长"。 */
.trend-bar-fill {
  width: 100%;
  border-radius: 4px 4px 0 0;
  transition: height var(--dur-slow) var(--ease-out);
  transform-origin: center bottom;
  animation: col-grow var(--dur-slow) var(--ease-out) var(--d, 0ms) backwards;
}
@keyframes col-grow {
  from { transform: scaleY(0); }
  to   { transform: scaleY(1); }
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
  transition: border-color var(--dur-base) var(--ease-out);
}
.wrong-item:hover { border-color: #fde68a; }
.wrong-top {
  display: flex;
  align-items: center;
  padding: 10px 12px;
  cursor: pointer;
  gap: 8px;
  background: #fafafa;
  transition: background-color var(--dur-base) var(--ease-out);
  min-height: 44px;
}
.wrong-top:hover { background: #fbf9f4; }
/* 原来是 #e0e7ff（蓝紫），与黑金主题不搭，改成主色淡金 */
.wrong-top:active { background: #fef3c7; transition-duration: var(--dur-fast); }
.level-tag { flex-shrink: 0; }
.wrong-content {
  flex: 1;
  font-size: 13px;
  color: #303133;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.expand-icon {
  flex-shrink: 0;
  color: #909399;
  transition: transform var(--dur-base) var(--ease-out), color var(--dur-base) var(--ease-out);
}
.expand-icon.open { transform: rotate(180deg); color: #f59e0b; }

/* 高度由 collapse.js 的钩子写入内联样式，这里只负责过渡与裁剪。
   注意 padding 移到了内层 .detail-inner —— 折叠到 height:0 时外层若带纵向 padding，
   仍会留下 24px 的高度，收不干净。 */
.wrong-detail {
  border-top: 1px solid #e4e7ed;
  background: #fff;
  overflow: hidden;
  transition: height var(--dur-base) var(--ease-in-out),
              opacity var(--dur-base) var(--ease-in-out);
}
.detail-inner { padding: 12px 14px; }
.detail-enter-from,
.detail-leave-to { opacity: 0; }
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
  transition: transform var(--dur-base) var(--ease-out),
              border-color var(--dur-base) var(--ease-out);
}
.kp-tag:hover { transform: translateY(-1px); border-color: #f59e0b; }
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
