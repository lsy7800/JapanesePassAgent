<script setup>
import { ref, reactive, computed, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { generateExam, submitExam } from '../api/exam'

const router = useRouter()

const LEVEL_OPTIONS = ['N1', 'N2', 'N3', 'N4', 'N5']
const TYPE_OPTIONS = [
  { value: 'single_choice', label: '单项选择' },
  { value: 'cloze', label: '完形填空' },
  { value: 'reading', label: '阅读理解' },
]

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

const remaining = ref(0)
let timer = null

const answeredCount = computed(() => Object.keys(answers).length)

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
    router.push(`/result/${data.id}`)
  } catch (e) {
    ElMessage.error('交卷失败：' + (e.response?.data?.detail || e.message))
    loading.value = false
  }
}

function restart() {
  stopTimer()
  exam.value = null
  Object.keys(answers).forEach((k) => delete answers[k])
  phase.value = 'config'
}

onUnmounted(stopTimer)
</script>

<template>
  <div class="exam-wrap">
    <!-- 组卷配置 -->
    <el-card v-if="phase === 'config'" shadow="never">
      <template #header><b>组卷配置</b></template>
      <el-form label-position="top" class="config-form">
        <div class="form-row">
          <el-form-item label="级别" class="form-item-sm">
            <el-select v-model="config.level" clearable style="width:100%">
              <el-option v-for="l in LEVEL_OPTIONS" :key="l" :label="l" :value="l" />
            </el-select>
          </el-form-item>
          <el-form-item label="题目数" class="form-item-sm">
            <el-input-number v-model="config.total_questions" :min="1" :max="50" style="width:100%" />
          </el-form-item>
        </div>

        <el-form-item label="题型">
          <el-select v-model="config.types" multiple placeholder="全部题型" style="width:100%">
            <el-option v-for="t in TYPE_OPTIONS" :key="t.value" :label="t.label" :value="t.value" />
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
        <div class="answer-bar">
          <span class="bar-info">
            共 {{ exam.total }} 题 · 已答 <b>{{ answeredCount }}</b>/{{ exam.total }}
          </span>
          <span v-if="exam.time_limit > 0" class="timer">⏱ {{ fmtTime(remaining) }}</span>
          <el-button type="primary" size="small" :loading="loading" @click="onSubmit">交卷</el-button>
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
  display: flex;
  align-items: center;
  gap: 12px;
  background: #fff;
  padding: 10px 14px;
  border-bottom: 1px solid #ebeef5;
  box-shadow: 0 2px 8px rgba(0,0,0,.05);
}
.bar-info { flex: 1; font-size: 13px; }
.timer { color: #e6a23c; font-weight: 600; font-size: 13px; }

.q-card { margin-top: 14px; }
.q-title { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; }
.q-seq { font-weight: 600; }
.q-content { font-size: 15px; line-height: 1.7; margin-bottom: 14px; }
.q-options { display: flex; flex-direction: column; gap: 10px; }
.q-option { height: auto; white-space: normal; line-height: 1.6; }

@media (max-width: 480px) {
  .form-row { grid-template-columns: 1fr; }
  .diff-num { width: 80px; }
  .q-content { font-size: 14px; }
}
</style>
