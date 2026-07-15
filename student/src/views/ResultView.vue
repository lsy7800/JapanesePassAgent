<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { marked } from 'marked'
import { getResult } from '../api/exam'
import { chatStream } from '../api/agent'

const props = defineProps({ id: { type: String, required: true } })
const router = useRouter()
const loading = ref(true)
const result = ref(null)
const accuracy = ref(0)

const judgeState = ref({})
const weakState = ref({ text: '', streaming: false, done: false, error: false })

let closeCurrentStream = null

// 渲染题干：划线词标金色下划线（先转义防 XSS）
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
  return s.replace(/\n/g, '<br/>')
}

// 渲染文章（完形/阅读）：转义 + 高亮空号 （1）… + 下划线标记 【U】…【/U】+ 保留换行
function renderArticle(article) {
  if (article == null) return ''
  let s = String(article)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
  s = s.replace(/（\d+[a-zA-Z]?）/g, (m) => `<span class="cloze-blank">${m}</span>`)
  s = s.replace(/【U】([\s\S]*?)【\/U】/g, (_m, inner) => `<u class="reading-underline">${inner}</u>`)
  return s.replace(/\n/g, '<br/>')
}

function renderMd(text) {
  return marked.parse(text || '')
}

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

function judgeItem(item, q) {
  if (judgeState.value[q.no]?.streaming) return
  closeCurrentStream?.()

  const opts = {}
  for (const o of q.options) opts[o.label] = o.content

  const ctx = item.article ? `文章：${item.article}\n本题为文章中第（${q.sub_seq}）空。\n` : ''
  const message = `请用 answer_judge 工具分析这道题：
${ctx}题目：${q.content || '（见文章空格）'}
选项：${Object.entries(opts).map(([k, v]) => `${k.toUpperCase()}. ${v}`).join('  ')}
正确答案：${q.correct_answer}
我的答案：${q.user_answer || '未作答'}
解析参考：${q.analysis || '无'}`

  judgeState.value[q.no] = { text: '', streaming: true, error: false }

  closeCurrentStream = chatStream(message, null, {
    onToken(content) { judgeState.value[q.no].text += content },
    onDone() {
      judgeState.value[q.no].streaming = false
      closeCurrentStream = null
    },
    onError(detail) {
      judgeState.value[q.no].streaming = false
      judgeState.value[q.no].error = true
      ElMessage.error('AI 解析失败：' + detail)
      closeCurrentStream = null
    },
  })
}

function analyzeWeak() {
  if (weakState.value.streaming) return
  closeCurrentStream?.()
  weakState.value = { text: '', streaming: true, done: false, error: false }

  closeCurrentStream = chatStream(
    `请用 analyze_weak_points 工具分析试卷 ${props.id} 的薄弱知识点`,
    null,
    {
      onToken(content) { weakState.value.text += content },
      onDone() {
        weakState.value.streaming = false
        weakState.value.done = true
        closeCurrentStream = null
      },
      onError(detail) {
        weakState.value.streaming = false
        weakState.value.error = true
        ElMessage.error('薄弱点分析失败：' + detail)
        closeCurrentStream = null
      },
    },
  )
}

onMounted(load)
</script>

<template>
  <div v-loading="loading" class="result-wrap">
    <template v-if="result">
      <!-- 得分卡 -->
      <el-card shadow="never" class="score-card">
        <div class="score-body">
          <div class="score-left">
            <div class="score-num">{{ result.score }} / {{ result.total }}</div>
            <div class="score-label">正确率 {{ accuracy }}%</div>
          </div>
          <div class="score-actions">
            <el-tag type="info" size="small">{{ result.level || '综合' }}</el-tag>
            <el-button size="small" @click="router.push('/history')">返回历史</el-button>
            <el-button size="small" type="primary" @click="router.push('/exam')">再考一套</el-button>
          </div>
        </div>
      </el-card>

      <!-- 每张卡片：单选题 1 子题；完形题文章 + N 子题 -->
      <el-card v-for="item in result.items" :key="item.group_id" shadow="never" class="q-card">
        <div v-if="item.article" class="q-article" v-html="renderArticle(item.article)"></div>

        <div
          v-for="q in item.questions"
          :key="q.no"
          class="sub-q"
        >
          <div class="q-title">
            <span class="q-seq">第 {{ q.no }} 题</span>
            <el-tag v-if="item.article" size="small" type="warning">（{{ q.sub_seq }}）</el-tag>
            <el-tag :type="q.is_correct ? 'success' : 'danger'" size="small">
              {{ q.is_correct ? '正确' : '错误' }}
            </el-tag>
            <el-button
              v-if="!q.is_correct"
              size="small"
              type="primary"
              plain
              :loading="judgeState[q.no]?.streaming"
              class="ai-btn"
              @click="judgeItem(item, q)"
            >
              {{ judgeState[q.no]?.text ? '重新解析' : 'AI 解析' }}
            </el-button>
          </div>

          <div v-if="q.content" class="q-content" v-html="renderContent(q.content, q.marked)"></div>

          <div class="opt-list">
            <div
              v-for="opt in q.options"
              :key="opt.label"
              class="opt-row"
              :class="{
                correct: opt.label === q.correct_answer,
                wrong: opt.label === q.user_answer && !q.is_correct,
              }"
            >
              {{ opt.label.toUpperCase() }}. {{ opt.content }}
              <span v-if="opt.label === q.correct_answer" class="mark">✓ 正确答案</span>
              <span v-else-if="opt.label === q.user_answer" class="mark">✗ 你的答案</span>
            </div>
          </div>

          <div v-if="!q.user_answer" class="unanswered">（未作答）</div>
          <div v-if="q.analysis" class="analysis">{{ q.analysis }}</div>

          <div v-if="judgeState[q.no]?.text || judgeState[q.no]?.streaming" class="ai-analysis">
            <div class="ai-label">🤖 AI 解析</div>
            <div class="md" v-html="renderMd(judgeState[q.no].text)" />
            <span v-if="judgeState[q.no]?.streaming" class="cursor">▍</span>
          </div>
        </div>
      </el-card>

      <!-- 薄弱点分析卡 -->
      <el-card shadow="never" class="weak-card">
        <template #header>
          <div class="weak-head">
            <span>📊 薄弱点分析</span>
            <el-button
              type="primary"
              size="small"
              :loading="weakState.streaming"
              :disabled="result.score === result.total"
              @click="analyzeWeak"
            >
              {{ weakState.done ? '重新分析' : '开始分析' }}
            </el-button>
          </div>
        </template>

        <div v-if="result.score === result.total" class="weak-perfect">
          全部答对，没有薄弱点 🎉
        </div>
        <div v-else-if="!weakState.text && !weakState.streaming" class="weak-empty">
          点击「开始分析」，AI 将根据错题分析你的知识薄弱点
        </div>
        <div v-else>
          <div class="md" v-html="renderMd(weakState.text)" />
          <span v-if="weakState.streaming" class="cursor">▍</span>
        </div>
      </el-card>
    </template>
  </div>
</template>

<style scoped>
.result-wrap {
  max-width: 820px;
  margin: 0 auto;
}

/* 得分卡 */
.score-body {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
}
.score-left { flex: 1; min-width: 100px; }
.score-num { font-size: 30px; font-weight: 700; color: #f59e0b; }
.score-label { color: #999; margin-top: 4px; font-size: 13px; }
.score-actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }

/* 题目卡 */
.q-card { margin-top: 14px; }
.q-title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
  flex-wrap: wrap;
}
.q-seq { font-weight: 600; }
.ai-btn { margin-left: auto; }
.q-content { font-size: 15px; line-height: 1.7; margin-bottom: 12px; }

/* 完形题文章块 */
.q-article {
  font-family: "Yu Mincho", "YuMincho", "MS Mincho", "Hiragino Mincho ProN", "Songti SC", SimSun, serif;
  font-size: 15px;
  line-height: 1.9;
  margin-bottom: 14px;
  padding: 14px 16px;
  background: #fbfaf7;
  border-left: 3px solid #f59e0b;
  border-radius: 6px;
  word-break: break-word;
}
/* 完形空号高亮 */
.q-article :deep(.cloze-blank) {
  color: #d97706;
  font-weight: 700;
  padding: 0 1px;
}
/* 阅读文章下划线（问句引用的划线词） */
.q-article :deep(.reading-underline) {
  text-decoration: underline;
  text-decoration-thickness: 2px;
  text-underline-offset: 3px;
}
/* 子题块：完形题一卡多子题，用虚线分隔 */
.sub-q + .sub-q { margin-top: 14px; padding-top: 14px; border-top: 1px dashed #ebeef5; }

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

.opt-list { display: flex; flex-direction: column; gap: 8px; }
.opt-row {
  padding: 8px 12px;
  border-radius: 6px;
  background: #fbf9f4;
  line-height: 1.6;
  word-break: break-word;
}
.opt-row.correct { background: #f0f9eb; color: #67c23a; }
.opt-row.wrong   { background: #fef0f0; color: #f56c6c; }
.opt-row .mark   { margin-left: 8px; font-size: 12px; font-weight: 600; }
.unanswered { color: #e6a23c; margin-top: 8px; font-size: 13px; }
.analysis {
  margin-top: 12px;
  padding: 10px 12px;
  background: #fafafa;
  border-left: 3px solid #f59e0b;
  white-space: pre-wrap;
  line-height: 1.7;
  color: #555;
  font-size: 13px;
}

.ai-analysis {
  margin-top: 12px;
  padding: 12px 14px;
  background: #fbf9f4;
  border-left: 3px solid #f59e0b;
  border-radius: 0 6px 6px 0;
}
.ai-label { font-size: 12px; color: #f59e0b; font-weight: 600; margin-bottom: 6px; }

.weak-card { margin-top: 20px; }
.weak-head { display: flex; align-items: center; justify-content: space-between; }
.weak-empty  { color: #999; text-align: center; padding: 20px 0; }
.weak-perfect { color: #67c23a; text-align: center; padding: 20px 0; font-weight: 600; }

/* 流式光标 */
.cursor {
  display: inline-block;
  animation: blink 0.8s step-end infinite;
  color: #f59e0b;
  font-weight: 700;
  margin-left: 1px;
}
@keyframes blink {
  0%, 100% { opacity: 1; }
  50%       { opacity: 0; }
}

/* markdown */
.md :deep(p)  { margin: 6px 0; }
.md :deep(h1),.md :deep(h2),.md :deep(h3) { margin: 10px 0 6px; }
.md :deep(ul),.md :deep(ol) { padding-left: 20px; margin: 6px 0; }
.md :deep(li) { margin: 4px 0; line-height: 1.6; }
.md :deep(pre) { background: #fbf9f4; padding: 10px; border-radius: 6px; overflow-x: auto; }
.md :deep(code) { background: #fbf9f4; padding: 1px 4px; border-radius: 3px; font-size: 13px; }
.md :deep(table) {
  border-collapse: collapse;
  display: block;
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
  min-width: 100%;
}
.md :deep(th),.md :deep(td) {
  border: 1px solid #dcdfe6;
  padding: 6px 10px;
  white-space: nowrap;
}
.md :deep(th) { background: #fbf9f4; }

@media (max-width: 480px) {
  .score-num { font-size: 26px; }
  .q-content { font-size: 14px; }
  .ai-btn { width: 100%; margin-left: 0; margin-top: 4px; }
}
</style>
