<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { getResult } from '../api/exam'

const props = defineProps({ id: { type: String, required: true } })
const router = useRouter()
const loading = ref(true)
const result = ref(null)

const accuracy = ref(0)

async function load() {
  try {
    result.value = await getResult(Number(props.id))
    accuracy.value = result.value.total
      ? Math.round((result.value.score / result.value.total) * 100)
      : 0
  } catch (e) {
    ElMessage.error('加载失败：' + (e.response?.data?.detail || e.message))
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div v-loading="loading" class="result-wrap">
    <template v-if="result">
      <el-card shadow="never" class="score-card">
        <div class="score-main">
          <div class="score-num">{{ result.score }} / {{ result.total }}</div>
          <div class="score-label">正确率 {{ accuracy }}%</div>
        </div>
        <div class="score-meta">
          <el-tag type="info" size="small">{{ result.level || '综合' }}</el-tag>
        </div>
        <el-button @click="router.push('/history')">返回历史</el-button>
        <el-button type="primary" @click="router.push('/exam')">再考一套</el-button>
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
    </template>
  </div>
</template>

<style scoped>
.result-wrap { max-width: 820px; }
.score-card :deep(.el-card__body) {
  display: flex;
  align-items: center;
  gap: 20px;
  flex-wrap: wrap;
}
.score-main { flex: 1; }
.score-num { font-size: 32px; font-weight: 700; color: #409eff; }
.score-label { color: #999; margin-top: 4px; }
.score-meta { display: flex; gap: 8px; align-items: center; }
.q-card { margin-top: 16px; }
.q-title { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }
.q-seq { font-weight: 600; }
.q-content { font-size: 16px; line-height: 1.7; margin-bottom: 14px; }
.opt-list { display: flex; flex-direction: column; gap: 8px; }
.opt-row { padding: 8px 12px; border-radius: 6px; background: #f5f7fa; line-height: 1.6; }
.opt-row.correct { background: #f0f9eb; color: #67c23a; }
.opt-row.wrong { background: #fef0f0; color: #f56c6c; }
.opt-row .mark { margin-left: 8px; font-size: 12px; font-weight: 600; }
.unanswered { color: #e6a23c; margin-top: 8px; }
.analysis {
  margin-top: 12px; padding: 12px;
  background: #fafafa; border-left: 3px solid #409eff;
  white-space: pre-wrap; line-height: 1.7; color: #555;
}
</style>
