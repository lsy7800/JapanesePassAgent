<script setup>
import { ref, reactive, computed, onUnmounted, watch, onMounted, nextTick } from 'vue'
import { useRouter, onBeforeRouteLeave } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Flag } from '@element-plus/icons-vue'
import { generateExam, submitExam, getCategories } from '../api/exam'

const router = useRouter()

const LEVEL_OPTIONS = ['N1', 'N2', 'N3', 'N4', 'N5']

const phase = ref('config')

const config = reactive({
  level: 'N1',
  categories: [],
  total_questions: 5,
  difficulty_range: null,
  time_limit_minutes: 0,
})
const useDifficulty = ref(false)
const diffMin = ref(1)
const diffMax = ref(9)

// 当前级别可选题型（按级别联动，只含可出题的）
const categoryOptions = ref([])
const catLoading = ref(false)

async function loadCategories() {
  catLoading.value = true
  try {
    const data = await getCategories(config.level, true)
    categoryOptions.value = data.items || []
    // 级别切换后，清掉已选中但当前级别不含的题型
    const valid = new Set(categoryOptions.value.map((c) => c.code))
    config.categories = config.categories.filter((c) => valid.has(c))
  } catch (e) {
    ElMessage.error('题型加载失败：' + (e.response?.data?.detail || e.message))
  } finally {
    catLoading.value = false
  }
}

// 按板块分组，供下拉分组展示
const groupedCategories = computed(() => {
  const groups = {}
  for (const c of categoryOptions.value) {
    ;(groups[c.section_label] ||= []).push(c)
  }
  return Object.entries(groups).map(([label, items]) => ({ label, items }))
})

watch(() => config.level, loadCategories)
onMounted(loadCategories)

const loading = ref(false)
const exam = ref(null)
const answers = reactive({})

const remaining = ref(0)
let timer = null

// ── 答题卡 / 标记 / 防误退 状态 ──
const flags = reactive({})        // seq -> true，标记待复查
const currentSeq = ref(1)         // 视口中最靠上的题号（答题卡高亮当前）
const showSheet = ref(true)       // 答题卡展开/收起
const submitted = ref(false)      // 已交卷（放行路由守卫，避免自跳被拦）
let warned5 = false               // 5 分钟提醒只触发一次
let warned1 = false               // 1 分钟提醒只触发一次

const answeredCount = computed(() => Object.keys(answers).length)
const flagCount = computed(() => Object.keys(flags).length)
const lowTime = computed(() => exam.value?.time_limit > 0 && remaining.value <= 60 && remaining.value > 0)

function toggleFlag(seq) {
  if (flags[seq]) delete flags[seq]
  else flags[seq] = true
}

function chipClass(seq) {
  return {
    answered: answers[seq] != null,
    flagged: flags[seq] === true,
    current: currentSeq.value === seq,
  }
}

function jumpTo(seq) {
  const el = document.getElementById(`q-${seq}`)
  if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

// 滚动监听追踪当前题：滚动容器是 .app-main（非 window），
// 用捕获阶段监听 scroll 才能捕捉到内层容器的滚动事件。
let scrollRaf = null

function currentRefY() {
  // 以粘性答题栏底部为基准线；未取到时回退固定值
  const bar = document.querySelector('.answer-bar')
  return (bar ? bar.getBoundingClientRect().bottom : 120) + 8
}

function updateCurrent() {
  if (!exam.value) return
  const refY = currentRefY()
  let cur = exam.value.items[0]?.seq ?? 1
  for (const item of exam.value.items) {
    const el = document.getElementById(`q-${item.seq}`)
    if (!el) continue
    // 顶部已越过基准线的最后一题 = 当前占据视口顶部的题
    if (el.getBoundingClientRect().top - refY <= 1) cur = item.seq
    else break
  }
  currentSeq.value = cur
}

function onScroll() {
  if (scrollRaf) return
  scrollRaf = requestAnimationFrame(() => {
    scrollRaf = null
    updateCurrent()
  })
}

function setupScrollSpy() {
  teardownScrollSpy()
  window.addEventListener('scroll', onScroll, true) // 捕获阶段，兼容内层滚动容器
  updateCurrent()
}

function teardownScrollSpy() {
  window.removeEventListener('scroll', onScroll, true)
  if (scrollRaf) { cancelAnimationFrame(scrollRaf); scrollRaf = null }
}

// ── 防误退：刷新/关页原生拦截 ──
function beforeUnloadHandler(e) {
  e.preventDefault()
  e.returnValue = ''
}

function armGuards() {
  window.addEventListener('beforeunload', beforeUnloadHandler)
}

function disarmGuards() {
  window.removeEventListener('beforeunload', beforeUnloadHandler)
}

// 路由离开确认（考试进行中且未交卷时）
onBeforeRouteLeave(async () => {
  if (phase.value !== 'answering' || submitted.value) return true
  try {
    await ElMessageBox.confirm('考试进行中，离开将丢失当前作答，确定离开？', '离开考试', {
      type: 'warning',
      confirmButtonText: '离开',
      cancelButtonText: '继续答题',
    })
    disarmGuards()
    return true
  } catch {
    return false
  }
})

// 渲染题干：把划线词 marked 标成金色下划线（先转义防 XSS）
function renderContent(content, marked) {
  if (content == null) return ''
  let s = String(content)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
  if (marked) {
    const esc = String(marked).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
    s = s.replace(new RegExp(esc, 'g'), (m) => `<u class="marked-word">${m}</u>`)
  }
  // 保留换行
  return s.replace(/\n/g, '<br/>')
}

function fmtTime(sec) {
  const m = Math.floor(sec / 60)
  const s = sec % 60
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

async function onGenerate() {
  const payload = {
    level: config.level || null,
    categories: config.categories,
    total_questions: config.total_questions,
    time_limit_minutes: config.time_limit_minutes,
  }
  if (useDifficulty.value) payload.difficulty_range = [diffMin.value, diffMax.value]

  loading.value = true
  try {
    const data = await generateExam(payload)
    if (!data.total) {
      ElMessage.warning('没有符合条件的题目，请调整组卷条件')
      return
    }
    exam.value = data
    Object.keys(answers).forEach((k) => delete answers[k])
    Object.keys(flags).forEach((k) => delete flags[k])
    currentSeq.value = 1
    warned5 = warned1 = false
    submitted.value = false
    phase.value = 'answering'
    armGuards()
    await nextTick()
    setupScrollSpy()
    if (data.time_limit > 0) startTimer(data.time_limit * 60)
  } catch (e) {
    ElMessage.error('组卷失败：' + (e.response?.data?.detail || e.message))
  } finally {
    loading.value = false
  }
}

function startTimer(sec) {
  remaining.value = sec
  timer = setInterval(() => {
    remaining.value -= 1
    // 计时预警：5 分钟 / 1 分钟各提醒一次
    if (!warned5 && remaining.value === 300) {
      warned5 = true
      ElMessage.warning('还剩 5 分钟')
    }
    if (!warned1 && remaining.value === 60) {
      warned1 = true
      ElMessage.warning({ message: '还剩 1 分钟，请尽快检查', duration: 4000 })
    }
    if (remaining.value <= 0) {
      clearInterval(timer)
      timer = null
      ElMessage.warning('时间到，自动交卷')
      doSubmit()
    }
  }, 1000)
}

function stopTimer() {
  if (timer) { clearInterval(timer); timer = null }
}

async function onSubmit() {
  const unanswered = exam.value.total - answeredCount.value
  if (unanswered > 0) {
    try {
      await ElMessageBox.confirm(`还有 ${unanswered} 题未作答，确定交卷？`, '确认交卷', {
        type: 'warning',
        confirmButtonText: '交卷',
        cancelButtonText: '继续答题',
      })
    } catch { return }
  }
  doSubmit()
}

async function doSubmit() {
  stopTimer()
  const payload = Object.entries(answers).map(([seq, answer]) => ({ seq: Number(seq), answer }))
  loading.value = true
  try {
    const data = await submitExam(exam.value.id, payload.length ? payload : [{ seq: 1, answer: 'a' }])
    // 交卷成功：放行守卫后再跳转结果页
    submitted.value = true
    disarmGuards()
    teardownScrollSpy()
    router.push(`/result/${data.id}`)
  } catch (e) {
    ElMessage.error('交卷失败：' + (e.response?.data?.detail || e.message))
    loading.value = false
  }
}

function restart() {
  stopTimer()
  disarmGuards()
  teardownScrollSpy()
  submitted.value = true // 主动返回配置页，不再触发离开确认
  exam.value = null
  Object.keys(answers).forEach((k) => delete answers[k])
  Object.keys(flags).forEach((k) => delete flags[k])
  phase.value = 'config'
}

onUnmounted(() => {
  stopTimer()
  disarmGuards()
  teardownScrollSpy()
})
</script>

<template>
  <div class="exam-wrap">
    <!-- 组卷配置 -->
    <el-card v-if="phase === 'config'" shadow="never">
      <template #header><b>组卷配置</b></template>
      <el-form label-position="top" class="config-form">
        <div class="form-row">
          <el-form-item label="级别" class="form-item-sm">
            <el-select v-model="config.level" style="width:100%">
              <el-option v-for="l in LEVEL_OPTIONS" :key="l" :label="l" :value="l" />
            </el-select>
          </el-form-item>
          <el-form-item label="题目数" class="form-item-sm">
            <el-input-number v-model="config.total_questions" :min="1" :max="50" style="width:100%" />
          </el-form-item>
        </div>

        <el-form-item label="题型（不选＝该级别全部）">
          <el-select
            v-model="config.categories"
            multiple
            clearable
            collapse-tags
            collapse-tags-tooltip
            placeholder="全部题型"
            style="width:100%"
            :loading="catLoading"
          >
            <el-option-group v-for="g in groupedCategories" :key="g.label" :label="g.label">
              <el-option v-for="c in g.items" :key="c.code" :label="c.name" :value="c.code" />
            </el-option-group>
          </el-select>
        </el-form-item>

        <el-form-item label="限定难度">
          <div class="difficulty-row">
            <el-switch v-model="useDifficulty" />
            <template v-if="useDifficulty">
              <el-input-number v-model="diffMin" :min="0" :max="9" class="diff-num" />
              <span class="sep">—</span>
              <el-input-number v-model="diffMax" :min="0" :max="9" class="diff-num" />
            </template>
          </div>
        </el-form-item>

        <el-form-item label="限时（分钟，0 为不限时）">
          <el-input-number v-model="config.time_limit_minutes" :min="0" :max="180" style="width:100%" />
        </el-form-item>

        <el-form-item>
          <el-button type="primary" :loading="loading" style="width:100%" @click="onGenerate">
            开始考试
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 答题阶段 -->
    <div v-else-if="phase === 'answering'">
      <el-affix :offset="0">
        <div class="answer-bar" :class="{ 'low-time': lowTime }">
          <div class="bar-top">
            <span class="bar-info">
              共 {{ exam.total }} 题 · 已答 <b>{{ answeredCount }}</b>/{{ exam.total }}
              <span v-if="flagCount" class="flag-info">· 标记 {{ flagCount }}</span>
            </span>
            <span v-if="exam.time_limit > 0" class="timer" :class="{ low: lowTime }">
              ⏱ {{ fmtTime(remaining) }}
            </span>
            <el-button text size="small" class="sheet-toggle" @click="showSheet = !showSheet">
              {{ showSheet ? '收起' : '答题卡' }}
            </el-button>
            <el-button type="primary" size="small" :loading="loading" @click="onSubmit">交卷</el-button>
          </div>
          <!-- 答题卡：题号网格 -->
          <div v-show="showSheet" class="answer-sheet">
            <button
              v-for="item in exam.items"
              :key="item.seq"
              type="button"
              class="chip"
              :class="chipClass(item.seq)"
              @click="jumpTo(item.seq)"
            >{{ item.seq }}</button>
          </div>
          <div v-show="showSheet" class="sheet-legend">
            <span><i class="dot answered"></i>已答</span>
            <span><i class="dot"></i>未答</span>
            <span><i class="dot flagged"></i>标记</span>
          </div>
        </div>
      </el-affix>

      <el-card
        v-for="item in exam.items"
        :key="item.seq"
        :id="`q-${item.seq}`"
        :data-seq="item.seq"
        shadow="never"
        class="q-card"
      >
        <div class="q-title">
          <span class="q-seq">第 {{ item.seq }} 题</span>
          <el-tag size="small" type="info">{{ item.level }}</el-tag>
          <span class="q-spacer"></span>
          <el-button
            text
            size="small"
            class="flag-btn"
            :class="{ active: flags[item.seq] }"
            @click="toggleFlag(item.seq)"
          >
            <el-icon><Flag /></el-icon>
            {{ flags[item.seq] ? '已标记' : '标记' }}
          </el-button>
        </div>
        <div class="q-content" v-html="renderContent(item.content, item.marked)"></div>
        <el-radio-group v-model="answers[item.seq]" class="q-options">
          <el-radio
            v-for="opt in item.options"
            :key="opt.label"
            :value="opt.label"
            class="q-option"
          >{{ opt.label.toUpperCase() }}. {{ opt.content }}</el-radio>
        </el-radio-group>
      </el-card>
    </div>
  </div>
</template>

<style scoped>
.exam-wrap {
  max-width: 820px;
  margin: 0 auto;
}

/* 配置表单 */
.config-form { max-width: 560px; }
.form-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0 16px;
}
.difficulty-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.diff-num { width: 90px; }
.sep { color: #909399; }

/* 答题栏 */
.answer-bar {
  background: #fff;
  padding: 10px 14px;
  border-bottom: 1px solid #ebeef5;
  box-shadow: 0 2px 8px rgba(0,0,0,.05);
}
.answer-bar.low-time { box-shadow: 0 2px 10px rgba(245,108,108,.35); }
.bar-top {
  display: flex;
  align-items: center;
  gap: 12px;
}
.bar-info { flex: 1; font-size: 13px; }
.flag-info { color: #e6a23c; }
.timer { color: #e6a23c; font-weight: 600; font-size: 13px; }
.timer.low {
  color: #f56c6c;
  animation: pulse 1s ease-in-out infinite;
}
@keyframes pulse {
  0%, 100% { opacity: 1; }
  50%      { opacity: 0.35; }
}
.sheet-toggle { padding: 0 4px; }

/* 答题卡：题号网格 */
.answer-sheet {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 10px;
  max-height: 132px;
  overflow-y: auto;
}
.chip {
  width: 34px;
  height: 34px;
  border: 1px solid #dcdfe6;
  border-radius: 7px;
  background: #fff;
  color: #606266;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.15s;
  padding: 0;
}
.chip:hover { border-color: #fbbf24; }
.chip.answered {
  background: #f59e0b;
  border-color: #f59e0b;
  color: #fff;
  font-weight: 600;
}
.chip.flagged {
  border-color: #e6a23c;
  border-width: 2px;
  box-shadow: inset 0 0 0 1px #fff;
}
.chip.current {
  outline: 2px solid #422006;
  outline-offset: 1px;
}
.sheet-legend {
  display: flex;
  gap: 16px;
  margin-top: 8px;
  font-size: 12px;
  color: #909399;
}
.sheet-legend span { display: flex; align-items: center; gap: 4px; }
.sheet-legend .dot {
  width: 12px; height: 12px; border-radius: 3px;
  border: 1px solid #dcdfe6; background: #fff; display: inline-block;
}
.sheet-legend .dot.answered { background: #f59e0b; border-color: #f59e0b; }
.sheet-legend .dot.flagged { border-color: #e6a23c; border-width: 2px; }

.q-card {
  margin-top: 14px;
  scroll-margin-top: 160px; /* 跳转时避开粘性答题栏 */
}
.q-title { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; }
.q-seq { font-weight: 600; }
.q-spacer { flex: 1; }
.flag-btn { color: #909399; }
.flag-btn.active { color: #e6a23c; font-weight: 600; }
.q-content { font-size: 15px; line-height: 1.9; margin-bottom: 16px; word-break: break-word; }

/* 选项：左对齐的块状行，圆圈顶部对齐首行，整行可点 */
.q-options {
  display: flex;
  flex-direction: column;
  gap: 8px;
  align-items: stretch;
}
.q-option {
  width: 100%;
  height: auto !important;
  margin-right: 0 !important;
  padding: 10px 12px !important;
  border: 1px solid #e5e9f2;
  border-radius: 8px;
  background: #fafbfc;
  line-height: 1.7;
  white-space: normal;
  align-items: flex-start; /* 圆圈顶部对齐首行，多行文本不再居中 */
  transition: all 0.2s;
}
.q-option:hover {
  border-color: #fbbf24;
  background: #fffbeb;
}
.q-option.is-checked {
  border-color: #f59e0b;
  background: #fff7e6;
}
.q-option :deep(.el-radio__label) {
  padding-left: 8px;
  white-space: normal;
  word-break: break-word;
  line-height: 1.7;
}
.q-option :deep(.el-radio__input) {
  margin-top: 4px; /* 视觉对齐首行文字基线 */
}

@media (max-width: 480px) {
  .form-row { grid-template-columns: 1fr; }
  .diff-num { width: 80px; }
  .q-content { font-size: 14px; }
  .bar-top { flex-wrap: wrap; gap: 8px 10px; }
  .bar-info { flex-basis: 100%; }
  .answer-sheet { max-height: 108px; }
  .chip { width: 30px; height: 30px; font-size: 12px; }
  .q-card { scroll-margin-top: 200px; }
}
</style>
