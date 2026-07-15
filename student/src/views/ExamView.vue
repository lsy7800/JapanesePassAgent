<script setup>
import { ref, reactive, computed, onUnmounted, watch, onMounted, nextTick } from 'vue'
import { useRouter, useRoute, onBeforeRouteLeave } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Flag } from '@element-plus/icons-vue'
import { generateExam, submitExam, getCategories, smartGenerateExam } from '../api/exam'

const router = useRouter()
const route = useRoute()

const LEVEL_OPTIONS = ['N1', 'N2', 'N3', 'N4', 'N5']

const phase = ref('config')

// 组卷模式：manual 手动 / ai 智能
const mode = ref('manual')

// AI 智能组卷
const AI_EXAMPLES = [
  '针对我的薄弱点出10道题，帮我查漏补缺',
  '汉字读音和词汇辨析各出5道',
  '来一套 N1 综合模拟，10 道题',
  '多出几道我最近容易错的题型',
]
const ai = reactive({
  level: 'N1',
  requirement: '',
  time_limit_minutes: 0,
})
const rationale = ref('')
const shortfalls = ref([])
const showRationale = ref(true)

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
onMounted(() => {
  loadCategories()
  // 从首页「针对弱项智能组卷」跳入：预填 AI 模式与需求
  if (route.query.ai === '1') {
    mode.value = 'ai'
    if (typeof route.query.req === 'string') ai.requirement = route.query.req
  }
})

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

// 所有可评分子题展平（单选题一卡一题；完形题一卡文章 + N 题）——答题卡/计数/定位以子题全局题号 no 为键
const allQuestions = computed(() => (exam.value?.items || []).flatMap((it) => it.questions || []))
const answeredCount = computed(() => allQuestions.value.filter((q) => answers[q.no] != null).length)
const flagCount = computed(() => Object.keys(flags).length)
const lowTime = computed(() => exam.value?.time_limit > 0 && remaining.value <= 60 && remaining.value > 0)

function toggleFlag(no) {
  if (flags[no]) delete flags[no]
  else flags[no] = true
}

function chipClass(no) {
  return {
    answered: answers[no] != null,
    flagged: flags[no] === true,
    current: currentSeq.value === no,
  }
}

function jumpTo(no) {
  const el = document.getElementById(`q-${no}`)
  if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

// 滚动监听追踪当前题：滚动容器是 .app-main（非 window），
// 用捕获阶段监听 scroll 才能捕捉到内层容器的滚动事件。
let scrollRaf = null

function updateCurrent() {
  const qs = allQuestions.value
  if (!qs.length) return
  // 已滚到底：强制高亮最后一题。最后一题下方无内容可滚，其标题永远越不过基准线，
  // 否则滚到底也只停在倒数第二题。兼容 .app-main 与窗口两种滚动容器。
  const scrollers = [document.querySelector('.app-main'), document.scrollingElement].filter(Boolean)
  const bottomed = scrollers.some(
    (el) => el.scrollHeight > el.clientHeight && el.scrollHeight - el.scrollTop - el.clientHeight <= 4,
  )
  if (bottomed) {
    currentSeq.value = qs[qs.length - 1].no
    return
  }
  const bar = document.querySelector('.answer-bar')
  const barBottom = bar ? bar.getBoundingClientRect().bottom : 100
  // 基准线取阅读区（粘性栏下方）约 40% 处，贴合"正在看的题"，避免高线导致滞后
  const line = barBottom + (window.innerHeight - barBottom) * 0.4
  let cur = qs[0].no
  for (const q of qs) {
    const el = document.getElementById(`q-${q.no}`)
    if (!el) continue
    // 标题已越过基准线的最后一题 = 当前题
    if (el.getBoundingClientRect().top <= line) cur = q.no
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
  // 排序题（grammar_order）：题干含空位标记 ＿＿ / ＿★＿，渲染成槽位，★ 处金色高亮
  if (s.includes('＿★＿')) {
    s = s
      .replace(/＿★＿/g, '<span class="sort-slot sort-slot--star"><i>★</i></span>')
      .replace(/＿＿/g, '<span class="sort-slot"></span>')
    return s.replace(/\n/g, '<br/>')
  }
  // 划线词若只是空格括号占位符（填空题的空），不加横线，避免给括号划线
  if (marked && String(marked).replace(/[（）()[\]\s　]/g, '')) {
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
    rationale.value = ''
    shortfalls.value = []
    await enterAnswering(data)
  } catch (e) {
    ElMessage.error('组卷失败：' + (e.response?.data?.detail || e.message))
  } finally {
    loading.value = false
  }
}

async function onSmartGenerate() {
  const req = ai.requirement.trim()
  if (!req) {
    ElMessage.warning('请先描述你的组卷需求')
    return
  }
  loading.value = true
  try {
    const data = await smartGenerateExam({
      requirement: req,
      level: ai.level || null,
      time_limit_minutes: ai.time_limit_minutes,
    })
    if (!data.total) {
      ElMessage.warning('没有符合条件的题目，请调整需求')
      return
    }
    rationale.value = data.rationale || ''
    shortfalls.value = data.shortfalls || []
    showRationale.value = true
    await enterAnswering(data)
  } catch (e) {
    ElMessage.error('智能组卷失败：' + (e.response?.data?.detail || e.message))
  } finally {
    loading.value = false
  }
}

// 进入作答阶段：手动/智能组卷共用（倒计时、答题卡、防误退整套）
async function enterAnswering(data) {
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
      <template #header>
        <div class="config-head">
          <b>组卷配置</b>
          <el-radio-group v-model="mode" size="small">
            <el-radio-button value="manual">手动组卷</el-radio-button>
            <el-radio-button value="ai">AI 智能组卷</el-radio-button>
          </el-radio-group>
        </div>
      </template>

      <!-- 手动组卷 -->
      <el-form v-show="mode === 'manual'" label-position="top" class="config-form">
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

      <!-- AI 智能组卷 -->
      <el-form v-show="mode === 'ai'" label-position="top" class="config-form">
        <div class="ai-hint">
          用自然语言描述你想练什么，AI 会结合你的历史薄弱点智能组卷。
        </div>
        <div class="form-row">
          <el-form-item label="级别" class="form-item-sm">
            <el-select v-model="ai.level" style="width:100%">
              <el-option v-for="l in LEVEL_OPTIONS" :key="l" :label="l" :value="l" />
            </el-select>
          </el-form-item>
          <el-form-item label="限时（分钟，0 不限）" class="form-item-sm">
            <el-input-number v-model="ai.time_limit_minutes" :min="0" :max="180" style="width:100%" />
          </el-form-item>
        </div>

        <el-form-item label="组卷需求">
          <el-input
            v-model="ai.requirement"
            type="textarea"
            :rows="3"
            maxlength="500"
            show-word-limit
            placeholder="例如：针对我的薄弱点出10道题，帮我查漏补缺"
          />
        </el-form-item>

        <el-form-item label="快捷示例">
          <div class="ai-examples">
            <el-tag
              v-for="ex in AI_EXAMPLES"
              :key="ex"
              class="ai-example"
              effect="plain"
              round
              @click="ai.requirement = ex"
            >{{ ex }}</el-tag>
          </div>
        </el-form-item>

        <el-form-item>
          <el-button type="primary" :loading="loading" style="width:100%" @click="onSmartGenerate">
            AI 生成并开始
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
          <!-- 答题卡：题号网格（以全局子题号 no 为单位） -->
          <div v-show="showSheet" class="answer-sheet">
            <button
              v-for="q in allQuestions"
              :key="q.no"
              type="button"
              class="chip"
              :class="chipClass(q.no)"
              @click="jumpTo(q.no)"
            >{{ q.no }}</button>
          </div>
          <div v-show="showSheet" class="sheet-legend">
            <span><i class="dot answered"></i>已答</span>
            <span><i class="dot"></i>未答</span>
            <span><i class="dot flagged"></i>标记</span>
          </div>
        </div>
      </el-affix>

      <!-- AI 组卷说明 -->
      <el-alert
        v-if="rationale && showRationale"
        class="rationale-alert"
        type="warning"
        :closable="true"
        show-icon
        @close="showRationale = false"
      >
        <template #title>
          <span class="rationale-title">🤖 AI 组卷说明</span>
        </template>
        <div class="rationale-body">{{ rationale }}</div>
        <div v-if="shortfalls.length" class="rationale-short">
          注：{{ shortfalls.join('；') }}
        </div>
      </el-alert>

      <el-card
        v-for="item in exam.items"
        :key="item.group_id"
        shadow="never"
        class="q-card"
      >
        <!-- 完形题：先展示文章（内含 （N） 空） -->
        <div v-if="item.article" class="q-article" v-html="renderContent(item.article, '')"></div>

        <!-- 子题：单选题 1 道；完形题 N 道 -->
        <div
          v-for="q in item.questions"
          :key="q.no"
          :id="`q-${q.no}`"
          :data-seq="q.no"
          class="sub-q"
        >
          <div class="q-title">
            <span class="q-seq">第 {{ q.no }} 题</span>
            <el-tag v-if="item.article" size="small" type="warning">（{{ q.sub_seq }}）</el-tag>
            <el-tag v-else size="small" type="info">{{ item.level }}</el-tag>
            <span class="q-spacer"></span>
            <el-button
              text
              size="small"
              class="flag-btn"
              :class="{ active: flags[q.no] }"
              @click="toggleFlag(q.no)"
            >
              <el-icon><Flag /></el-icon>
              {{ flags[q.no] ? '已标记' : '标记' }}
            </el-button>
          </div>
          <div v-if="q.content" class="q-content" v-html="renderContent(q.content, q.marked)"></div>
          <el-radio-group v-model="answers[q.no]" class="q-options">
            <el-radio
              v-for="opt in q.options"
              :key="opt.label"
              :value="opt.label"
              class="q-option"
            >{{ opt.label.toUpperCase() }}. {{ opt.content }}</el-radio>
          </el-radio-group>
        </div>
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
.config-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}
.config-form { max-width: 560px; }
.ai-hint {
  font-size: 13px;
  color: #909399;
  background: #fffbeb;
  border: 1px solid #fde68a;
  border-radius: 8px;
  padding: 8px 12px;
  margin-bottom: 14px;
}
.ai-examples {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.ai-example { cursor: pointer; transition: all 0.15s; }
.ai-example:hover { border-color: #f59e0b; color: #b45309; }

/* AI 组卷说明条 */
.rationale-alert { margin-bottom: 14px; }
.rationale-title { font-weight: 600; }
.rationale-body { font-size: 13px; line-height: 1.6; }
.rationale-short { font-size: 12px; color: #b45309; margin-top: 4px; }
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
  border-color: #f59e0b;
  transform: translateY(-2px) scale(1.08);
  box-shadow: 0 3px 10px rgba(245, 158, 11, 0.45);
  font-weight: 700;
  z-index: 1;
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
/* 完形题文章块 */
.q-article {
  font-size: 15px;
  line-height: 1.9;
  margin-bottom: 16px;
  padding: 14px 16px;
  background: #fbfaf7;
  border-left: 3px solid #f59e0b;
  border-radius: 6px;
  word-break: break-word;
}
/* 子题块：完形题一卡多子题，用虚线分隔；跳转锚点在子题上，需避开粘性栏 */
.sub-q { scroll-margin-top: 160px; }
.sub-q + .sub-q { margin-top: 8px; padding-top: 12px; border-top: 1px dashed #ebeef5; }
.q-title { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; }
.q-seq { font-weight: 600; }
.q-spacer { flex: 1; }
.flag-btn { color: #909399; }
.flag-btn.active { color: #e6a23c; font-weight: 600; }
.q-content { font-size: 15px; line-height: 1.9; margin-bottom: 16px; word-break: break-word; }

/* 排序题空位槽（grammar_order） */
.q-content :deep(.sort-slot) {
  display: inline-block;
  position: relative;
  min-width: 46px;
  height: 1.25em;
  margin: 0 3px;
  /* 空 inline-block 以底边对齐文字基线，星标槽的 ★ 绝对定位后同为空盒 → 底线对齐 */
  vertical-align: baseline;
  border-bottom: 2px solid #c0c4cc;
}
.q-content :deep(.sort-slot--star) {
  border-bottom-color: #f59e0b;
  background: rgba(245, 158, 11, 0.12);
  border-radius: 4px 4px 0 0;
}
.q-content :deep(.sort-slot--star i) {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 1px;
  text-align: center;
  font-size: 0.8em;
  line-height: 1;
  color: #d97706;
  font-style: normal;
  font-weight: 700;
  pointer-events: none;
}

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
