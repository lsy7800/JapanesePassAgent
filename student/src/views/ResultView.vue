<script setup>
import { ref, reactive, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Loading } from '@element-plus/icons-vue'
import { marked } from 'marked'
import { getResult } from '../api/exam'
import { chatStream } from '../api/agent'
import { audioUrl } from '../utils/audio'
import { toolLabel } from '../utils/toolLabels'
import { sanitizeArticle, sanitizeContent, sanitizeMd } from '../utils/sanitize'

const props = defineProps({ id: { type: String, required: true } })
const router = useRouter()
const loading = ref(true)
const result = ref(null)
const accuracy = ref(0)

const judgeState = ref({})
const weakState = ref({ text: '', streaming: false, done: false, error: false })

// 等待超过这个时长仍无输出，补一句预期耗时，避免用户以为卡死
const SLOW_HINT_MS = 8000

// 当前活跃的流。EventSource.close() 不触发任何回调，所以必须自己记住
// 「怎么复位面板」——否则被抢占的面板 streaming 永远为 true，按钮一直转圈。
let active = null

/** 关闭当前流并复位其面板状态。 */
function stopActive() {
  if (!active) return
  const cur = active
  active = null
  clearTimeout(cur.slowTimer)
  cur.close?.()
  cur.reset?.()
}

/**
 * 接管一个面板的流式请求：统一处理阶段提示、慢响应兜底、错误与收尾。
 * @param {object} st  面板响应式状态对象
 * @param {string} message  发给 Agent 的指令
 * @param {string} failHint  错误提示前缀
 */
function runStream(st, message, failHint) {
  const rec = { reset: () => { st.streaming = false } }
  active = rec

  // 首 token 迟迟不来时补一句预期耗时
  rec.slowTimer = setTimeout(() => {
    if (st.streaming && !st.text) st.slow = true
  }, SLOW_HINT_MS)

  rec.close = chatStream(message, null, {
    onTool(name) {
      st.stage = toolLabel(name)
    },
    onToken(content) {
      st.text += content
      st.stage = ''
      st.slow = false
    },
    onError(detail, kind) {
      st.error = true
      // 网络中断的文案已足够自解释，服务端错误则加上场景前缀
      st.errorMsg = kind === 'network' ? detail : `${failHint}：${detail}`
    },
    onClose(reason) {
      clearTimeout(rec.slowTimer)
      st.streaming = false
      st.stage = ''
      st.slow = false
      if (reason === 'done') st.done = true
      if (active === rec) active = null
    },
  })
  return rec.close
}

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
    return sanitizeContent(s.replace(/\n/g, '<br/>'))
  }
  // 划线词若只是空格括号占位符（填空题的空），不加横线，避免给括号划线
  if (marked && String(marked).replace(/[（）()[\]\s　]/g, '')) {
    const esc = String(marked).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
    s = s.replace(new RegExp(esc, 'g'), (m) => `<u class="marked-word">${m}</u>`)
  }
  return sanitizeContent(s.replace(/\n/g, '<br/>'))
}

// 渲染文章（完形/阅读）：转义 + 高亮空号 （1）… + 下划线标记 【U】…【/U】+ 保留换行
// 注意：上面刻意放行了 DB 里存的 <table> 原始 HTML，那部分未经过滤，
// 所以最终结果必须过 sanitizeArticle
function renderArticle(article) {
  if (article == null) return ''
  let s = String(article)

  const htmlBlocks = []
  s = s.replace(/<table[\s\S]*?<\/table>/gi, (m) => {
    htmlBlocks.push(m)
    return `\x00HTML${htmlBlocks.length - 1}\x00`
  })

  s = s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')

  s = s.replace(/（\d+[a-zA-Z]?）/g, (m) => `<span class="cloze-blank">${m}</span>`)
  s = s.replace(/【U】([\s\S]*?)【\/U】/g, (_m, inner) => `<u class="reading-underline">${inner}</u>`)
  s = s.replace(/【文章A】/g, '<div class="article-label">文章A</div>')
  s = s.replace(/【文章B】/g, '<div class="article-label">文章B</div>')
  s = s.replace(/【BOX】\n?([\s\S]*?)\n?【\/BOX】/g, (_m, inner) => {
    return `<div class="info-box">${inner.replace(/\n/g, '<br/>')}</div>`
  })
  s = s.replace(/\x00HTML(\d+)\x00/g, (_, i) => htmlBlocks[Number(i)])

  return sanitizeArticle(s.replace(/\n/g, '<br/>'))
}


// marked 不过滤 HTML，LLM 输出必须消毒后才能交给 v-html
function renderMd(text) {
  return sanitizeMd(marked.parse(text || ''))
}

// AI 解析结果一律以【原文翻译】/【判断】等小节开头；裁掉模型可能带出的开场白
// （“好的，我来分析…”“正在调用工具…”），保证只显示解析正文
function renderJudge(text) {
  let s = text || ''
  const first = s.indexOf('【')
  if (first > 0) s = s.slice(first)
  return sanitizeMd(marked.parse(s))
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
  stopActive()

  const opts = {}
  for (const o of q.options) opts[o.label] = o.content

  const ctx = item.article ? `文章：${item.article}\n本题为文章中第（${q.sub_seq}）空。\n` : ''
  const articleHint = item.article
    ? '（本题含文章，把 article 参数一并传入，翻译原文并结合文章讲解）'
    : ''
  const message = `分析下面这道题，用 answer_judge 工具。${articleHint}直接输出工具返回的解析内容即可，不要写任何开场白、思考过程或“正在调用工具”之类的说明文字。
${ctx}题目：${q.content || '（见文章空格）'}
选项：${Object.entries(opts).map(([k, v]) => `${k.toUpperCase()}. ${v}`).join('  ')}
正确答案：${q.correct_answer}
我的答案：${q.user_answer || '未作答'}
解析参考：${q.analysis || '无'}`

  // 用 reactive 对象持有面板状态，交给 runStream 统一更新
  judgeState.value[q.no] = reactive({
    text: '', streaming: true, done: false, error: false, errorMsg: '', stage: '', slow: false,
  })
  runStream(judgeState.value[q.no], message, 'AI 解析失败')
}

function analyzeWeak() {
  if (weakState.value.streaming) return
  stopActive()
  weakState.value = reactive({
    text: '', streaming: true, done: false, error: false, errorMsg: '', stage: '', slow: false,
  })
  runStream(
    weakState.value,
    `请用 analyze_weak_points 工具分析试卷 ${props.id} 的薄弱知识点`,
    '薄弱点分析失败',
  )
}

onMounted(load)
onUnmounted(stopActive)  // 离开页面时断开未完成的流，避免连接泄漏
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
      <!-- 入场延迟按下标递增，只错开前 5 张：整场卷有 40+ 张，
           线性递增会让末尾等好几秒才出现 -->
      <el-card
        v-for="(item, idx) in result.items"
        :key="item.group_id"
        shadow="never"
        class="q-card"
        :style="{ animationDelay: `${Math.min(idx, 5) * 50}ms` }"
      >
        <!-- 听力题：音频播放器 -->
        <div v-if="item.audio_url" class="q-audio">
          <audio controls preload="none" :src="audioUrl(item.audio_url)"></audio>
        </div>
        <!-- 听力题结果页展示原文脚本供对照复习；完形/阅读题展示文章 -->
        <div v-if="item.article" class="q-article" :class="{ 'listening-script': item.audio_url }">
          <div v-if="item.audio_url" class="script-label">听力原文</div>
          <div v-html="renderArticle(item.article)"></div>
        </div>

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
            <template v-if="!q.is_correct">
              <el-button
                v-if="judgeState[q.no]?.streaming"
                size="small"
                class="ai-btn"
                @click="stopActive"
              >
                停止
              </el-button>
              <el-button
                v-else
                size="small"
                type="primary"
                plain
                class="ai-btn"
                @click="judgeItem(item, q)"
              >
                {{ judgeState[q.no]?.text ? '重新解析' : 'AI 解析' }}
              </el-button>
            </template>
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

          <div
            v-if="judgeState[q.no]?.text || judgeState[q.no]?.streaming || judgeState[q.no]?.error"
            class="ai-analysis"
          >
            <div class="ai-label">🤖 AI 解析</div>

            <!-- 首 token 前：阶段提示 + 骨架屏，替代此前的空白面板 -->
            <div v-if="judgeState[q.no].streaming && !judgeState[q.no].text" class="ai-waiting">
              <div class="ai-stage-line">
                <el-icon class="is-loading"><Loading /></el-icon>
                <span>{{ judgeState[q.no].stage || '正在准备解析…' }}</span>
              </div>
              <div v-if="judgeState[q.no].slow" class="ai-slow-hint">
                模型正在逐句处理，通常需要 10~30 秒，可以先看看其他题目
              </div>
              <el-skeleton :rows="3" animated class="ai-skeleton" />
            </div>

            <div v-if="judgeState[q.no].text" class="md" v-html="renderJudge(judgeState[q.no].text)" />
            <span v-if="judgeState[q.no].streaming && judgeState[q.no].text" class="cursor">▍</span>

            <!-- 出错：保留已收到的部分内容，并给重试入口 -->
            <div v-if="judgeState[q.no].error" class="ai-error">
              <span class="ai-error-msg">{{ judgeState[q.no].errorMsg }}</span>
              <el-button size="small" type="primary" plain @click="judgeItem(item, q)">
                重试
              </el-button>
            </div>
          </div>
        </div>
      </el-card>

      <!-- 薄弱点分析卡 -->
      <el-card shadow="never" class="weak-card">
        <template #header>
          <div class="weak-head">
            <span>📊 薄弱点分析</span>
            <el-button v-if="weakState.streaming" size="small" @click="stopActive">
              停止
            </el-button>
            <el-button
              v-else
              type="primary"
              size="small"
              :disabled="result.score === result.total"
              @click="analyzeWeak"
            >
              {{ weakState.done || weakState.text ? '重新分析' : '开始分析' }}
            </el-button>
          </div>
        </template>

        <div v-if="result.score === result.total" class="weak-perfect">
          全部答对，没有薄弱点 🎉
        </div>
        <div
          v-else-if="!weakState.text && !weakState.streaming && !weakState.error"
          class="weak-empty"
        >
          点击「开始分析」，AI 将根据错题分析你的知识薄弱点
        </div>
        <div v-else>
          <!-- 首 token 前：阶段提示 + 骨架屏 -->
          <div v-if="weakState.streaming && !weakState.text" class="ai-waiting">
            <div class="ai-stage-line">
              <el-icon class="is-loading"><Loading /></el-icon>
              <span>{{ weakState.stage || '正在准备分析…' }}</span>
            </div>
            <div v-if="weakState.slow" class="ai-slow-hint">
              正在归纳全卷错题，通常需要 10~30 秒
            </div>
            <el-skeleton :rows="4" animated class="ai-skeleton" />
          </div>

          <div v-if="weakState.text" class="md" v-html="renderMd(weakState.text)" />
          <span v-if="weakState.streaming && weakState.text" class="cursor">▍</span>

          <div v-if="weakState.error" class="ai-error">
            <span class="ai-error-msg">{{ weakState.errorMsg }}</span>
            <el-button size="small" type="primary" plain @click="analyzeWeak">重试</el-button>
          </div>
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
.score-card { animation: fade-up var(--dur-slow) var(--ease-out); }
.score-body {
  display: flex;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
}
.score-left { flex: 1; min-width: 100px; }
/* 分数是这一页的主角，回弹放大一次让它"落地有声" */
.score-num {
  font-size: 30px;
  font-weight: 700;
  color: #f59e0b;
  animation: score-pop var(--dur-slow) var(--ease-spring) 80ms backwards;
}
@keyframes score-pop {
  from { opacity: 0; transform: scale(0.7); }
  to   { opacity: 1; transform: scale(1); }
}
.score-label { color: #999; margin-top: 4px; font-size: 13px; }
.score-actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }

/* 题目卡：前几张错开落位。
   延迟由模板按 v-for 下标内联绑定，不用 nth-of-type —— 同级的 score-card /
   weak-card 渲染出来也是 div，选择器序号会随卡片增减而错位。 */
.q-card {
  margin-top: 14px;
  animation: fade-up var(--dur-slow) var(--ease-out) backwards;
}
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

/* 听力题音频播放器 */
.q-audio { margin-bottom: 14px; }
.q-audio audio { width: 100%; height: 40px; }
/* 听力原文脚本标签 */
.script-label {
  font-size: 13px;
  font-weight: 600;
  color: #909399;
  margin-bottom: 6px;
}

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
/* 信息检索：Markdown 表格 */
.q-article :deep(.info-table) {
  border-collapse: collapse;
  width: 100%;
  margin: 8px 0;
  font-size: 14px;
}
.q-article :deep(.info-table th),
.q-article :deep(.info-table td) {
  border: 1px solid #d1d5db;
  padding: 6px 10px;
  text-align: left;
  vertical-align: top;
}
.q-article :deep(.info-table thead th) {
  background: #f3f4f6;
  font-weight: 600;
}
.q-article :deep(.info-table tbody tr:nth-child(even)) {
  background: #fafafa;
}
/* 信息检索：边框信息块 */
.q-article :deep(.info-box) {
  border: 1px solid #d1d5db;
  border-radius: 4px;
  padding: 10px 14px;
  margin: 8px 0;
  background: #fff;
  line-height: 1.8;
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
/* ✓/✗ 标记比选项本身晚一点浮现，视线先看选项再看判定 */
.opt-row .mark {
  margin-left: 8px;
  font-size: 12px;
  font-weight: 600;
  animation: fade-in var(--dur-slow) var(--ease-out) 120ms backwards;
}
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

/* AI 解析面板：点「AI 解析」后出现，滑入而非突然占位 */
.ai-analysis {
  margin-top: 12px;
  padding: 12px 14px;
  background: #fbf9f4;
  border-left: 3px solid #f59e0b;
  border-radius: 0 6px 6px 0;
  animation: fade-up var(--dur-base) var(--ease-out);
}
.ai-label { font-size: 12px; color: #f59e0b; font-weight: 600; margin-bottom: 6px; }

/* 首 token 前的等待区：阶段提示 + 骨架屏 */
.ai-stage-line {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: #b45309;
  font-weight: 600;
}
/* 阶段文字呼吸，表明还在跑（骨架屏自带动画，这里只补文字） */
.ai-stage-line span { animation: breathe 1.6s var(--ease-in-out) infinite; }
@keyframes breathe {
  0%, 100% { opacity: 1; }
  50%      { opacity: 0.55; }
}
.ai-slow-hint {
  font-size: 12px;
  color: #909399;
  line-height: 1.6;
  margin-top: 4px;
  /* 慢速提示是 8 秒后才出现的安抚文案，淡入进来不打断阅读 */
  animation: fade-in var(--dur-slow) var(--ease-out);
}
.ai-skeleton { margin-top: 10px; }

/* 出错提示：保留已收到的内容，附重试入口 */
.ai-error {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px dashed #e4d9c3;
  animation: fade-up var(--dur-base) var(--ease-out);
}
.ai-error-msg { font-size: 13px; color: #f56c6c; flex: 1; min-width: 180px; }

.weak-card { margin-top: 20px; }
.weak-head { display: flex; align-items: center; justify-content: space-between; }
.weak-empty  { color: #999; text-align: center; padding: 20px 0; }
/* 全对是值得庆祝的结果，给一次回弹入场 */
.weak-perfect {
  color: #67c23a;
  text-align: center;
  padding: 20px 0;
  font-weight: 600;
  animation: score-pop var(--dur-slow) var(--ease-spring);
}

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
