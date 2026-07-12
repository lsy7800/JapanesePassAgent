<script setup>
import { ref, reactive, computed, onUnmounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { generateExam, submitExam } from '../api/exam'

const LABELS = ['a', 'b', 'c', 'd']
const LEVEL_OPTIONS = ['N1', 'N2', 'N3', 'N4', 'N5']
const TYPE_OPTIONS = [
  { value: 'single_choice', label: '单项选择' },
  { value: 'cloze', label: '完形填空' },
  { value: 'reading', label: '阅读理解' },
]

// 阶段：config 配置 / answering 答题 / result 结果
const phase = ref('config')

const config = reactive({
  level: 'N1',
  types: [],
  total_questions: 5,
  difficulty_range: null,
  time_limit_minutes: 0,
})
const useDifficulty = ref(false)
const diffMin = ref(1)
const diffMax = ref(9)

const loading = ref(false)
const exam = ref(null)
const answers = reactive({})
const result = ref(null)

const remaining = ref(0)
let timer = null

const answeredCount = computed(() => Object.keys(answers).length)

function typeLabel(v) {
  return TYPE_OPTIONS.find((t) => t.value === v)?.label || v
}

function fmtTime(sec) {
  const m = Math.floor(sec / 60)
  const s = sec % 60
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

async function onGenerate() {
  const payload = {
    level: config.level || null,
    types: config.types,
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
    phase.value = 'answering'
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
    if (remaining.value <= 0) {
      clearInterval(timer)
      timer = null
      ElMessage.warning('时间到，自动交卷')
      doSubmit()
    }
  }, 1000)
}

function stopTimer() {
  if (timer) {
    clearInterval(timer)
    timer = null
  }
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
    } catch {
      return
    }
  }
  doSubmit()
}

async function doSubmit() {
  stopTimer()
  const payload = Object.entries(answers).map(([seq, answer]) => ({ seq: Number(seq), answer }))
  if (payload.length === 0) {
    ElMessage.info('未作答任何题目')
  }
  loading.value = true
  try {
    const data = await submitExam(exam.value.id, payload.length ? payload : [{ seq: 1, answer: 'a' }])
    result.value = data
    phase.value = 'result'
  } catch (e) {
    ElMessage.error('交卷失败：' + (e.response?.data?.detail || e.message))
  } finally {
    loading.value = false
  }
}

function restart() {
  stopTimer()
  exam.value = null
  result.value = null
  Object.keys(answers).forEach((k) => delete answers[k])
  phase.value = 'config'
}

const accuracy = computed(() => {
  if (!result.value || !result.value.total) return 0
  return Math.round((result.value.score / result.value.total) * 100)
})

onUnmounted(stopTimer)
</script>

<template>
  <div class="exam-wrap">
    <!-- 阶段1：组卷配置 -->
    <el-card v-if="phase === 'config'" shadow="never">
      <template #header><b>组卷配置</b></template>
      <el-form label-width="100px" style="max-width: 560px">
        <el-form-item label="级别">
          <el-select v-model="config.level" clearable style="width: 160px">
            <el-option v-for="l in LEVEL_OPTIONS" :key="l" :label="l" :value="l" />
          </el-select>
        </el-form-item>
        <el-form-item label="题型">
          <el-select v-model="config.types" multiple placeholder="全部" style="width: 320px">
            <el-option v-for="t in TYPE_OPTIONS" :key="t.value" :label="t.label" :value="t.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="题目数">
          <el-input-number v-model="config.total_questions" :min="1" :max="50" />
        </el-form-item>
        <el-form-item label="限定难度">
          <el-switch v-model="useDifficulty" />
          <template v-if="useDifficulty">
            <el-input-number v-model="diffMin" :min="0" :max="9" style="width: 100px; margin-left: 12px" />
            <span style="margin: 0 6px">-</span>
            <el-input-number v-model="diffMax" :min="0" :max="9" style="width: 100px" />
          </template>
        </el-form-item>
        <el-form-item label="限时(分钟)">
          <el-input-number v-model="config.time_limit_minutes" :min="0" :max="180" />
          <span style="margin-left: 8px; color: #999">0 为不限时</span>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="loading" @click="onGenerate">开始考试</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 阶段2：答题 -->
    <div v-else-if="phase === 'answering'">
      <el-affix :offset="0">
        <div class="answer-bar">
          <span>共 {{ exam.total }} 题 · 已答 <b>{{ answeredCount }}</b> / {{ exam.total }}</span>
          <span v-if="exam.time_limit > 0" class="timer">⏱ {{ fmtTime(remaining) }}</span>
          <el-button type="primary" :loading="loading" @click="onSubmit">交卷</el-button>
        </div>
      </el-affix>
      <el-card v-for="item in exam.items" :key="item.seq" shadow="never" class="q-card">
        <div class="q-title">
          <span class="q-seq">第 {{ item.seq }} 题</span>
          <el-tag size="small" type="info">{{ item.level }}</el-tag>
        </div>
        <div class="q-content">{{ item.content }}</div>
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

    <!-- 阶段3：结果 -->
    <div v-else-if="phase === 'result'">
      <el-card shadow="never" class="score-card">
        <div class="score-main">
          <div class="score-num">{{ result.score }} / {{ result.total }}</div>
          <div class="score-label">正确率 {{ accuracy }}%</div>
        </div>
        <el-button type="primary" @click="restart">再考一套</el-button>
      </el-card>

      <el-card v-for="item in result.items" :key="item.seq" shadow="never" class="q-card">
        <div class="q-title">
          <span class="q-seq">第 {{ item.seq }} 题</span>
          <el-tag :type="item.is_correct ? 'success' : 'danger'" size="small">
            {{ item.is_correct ? '正确' : '错误' }}
          </el-tag>
        </div>
        <div class="q-content">{{ item.content }}</div>
        <div class="opt-list">
          <div
            v-for="opt in item.options"
            :key="opt.label"
            class="opt-row"
            :class="{
              correct: opt.label === item.correct_answer,
              wrong: opt.label === item.user_answer && !item.is_correct,
            }"
          >
            {{ opt.label.toUpperCase() }}. {{ opt.content }}
            <span v-if="opt.label === item.correct_answer" class="mark">✓ 正确答案</span>
            <span v-else-if="opt.label === item.user_answer" class="mark">✗ 你的答案</span>
          </div>
        </div>
        <div v-if="!item.user_answer" class="unanswered">（未作答）</div>
        <div v-if="item.analysis" class="analysis">{{ item.analysis }}</div>
      </el-card>
    </div>
  </div>
</template>

<style scoped>
.exam-wrap {
  max-width: 820px;
}
.answer-bar {
  display: flex;
  align-items: center;
  gap: 20px;
  background: #fff;
  padding: 12px 16px;
  border-bottom: 1px solid #ebeef5;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05);
}
.answer-bar .timer {
  color: #e6a23c;
  font-weight: 600;
}
.answer-bar .el-button {
  margin-left: auto;
}
.q-card {
  margin-top: 16px;
}
.q-title {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}
.q-seq {
  font-weight: 600;
}
.q-content {
  font-size: 16px;
  line-height: 1.7;
  margin-bottom: 14px;
}
.q-options {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.q-option {
  height: auto;
  white-space: normal;
  line-height: 1.6;
}
.opt-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.opt-row {
  padding: 8px 12px;
  border-radius: 6px;
  background: #f5f7fa;
  line-height: 1.6;
}
.opt-row.correct {
  background: #f0f9eb;
  color: #67c23a;
}
.opt-row.wrong {
  background: #fef0f0;
  color: #f56c6c;
}
.opt-row .mark {
  margin-left: 8px;
  font-size: 12px;
  font-weight: 600;
}
.unanswered {
  color: #e6a23c;
  margin-top: 8px;
}
.analysis {
  margin-top: 12px;
  padding: 12px;
  background: #fafafa;
  border-left: 3px solid #409eff;
  white-space: pre-wrap;
  line-height: 1.7;
  color: #555;
}
.score-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.score-card :deep(.el-card__body) {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
}
.score-num {
  font-size: 32px;
  font-weight: 700;
  color: #409eff;
}
.score-label {
  color: #999;
  margin-top: 4px;
}
</style>
