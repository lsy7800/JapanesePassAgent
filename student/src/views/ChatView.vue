<script setup>
import { ref, nextTick, onMounted } from 'vue'
import { marked } from 'marked'
import { sanitizeMd } from '../utils/sanitize'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Download, Plus, Delete, ChatLineRound, Loading } from '@element-plus/icons-vue'
import {
  chatStream,
  listSessions,
  getSessionMessages,
  deleteSession,
  clearSessions,
} from '../api/agent'
import { downloadExam } from '../api/exam'
import { toolLabel } from '../utils/toolLabels'

const EXAMPLES = [
  '帮我出2道N1的题',
  '讲解一下 ば 和 たら 的区别',
  '给我看1道关于条件表达的题',
]

// 导出模式 → 按钮文案。三种模式各自产出一份独立文件，文案必须能区分，
// 否则用户看到两个按钮无从判断哪份是哪份。
const EXPORT_LABELS = {
  questions: '下载试卷',
  with_answers: '下载试卷（含答案）',
  answers_only: '下载答案',
}

const messages = ref([])
const input = ref('')
const sending = ref(false)
const sessionId = ref(null)
const listRef = ref(null)
const downloading = ref(false)
const sessions = ref([])
const loadingHistory = ref(false)
const clearingAll = ref(false)

let streamingIdx = -1
let closeStream = null

// marked 默认不过滤 HTML，AI 回复里的 <script>/<img onerror> 会原样进 DOM，
// 必须消毒后才能交给 v-html（token 存 localStorage，XSS 等于拿到 7 天凭证）
function renderMd(text) {
  return sanitizeMd(marked.parse(text || ''))
}

async function refreshSessions() {
  try {
    sessions.value = await listSessions()
  } catch {
    // 列表加载失败不阻塞对话
  }
}

async function openSession(sid) {
  if (sid === sessionId.value || sending.value) return
  closeStream?.()
  closeStream = null
  loadingHistory.value = true
  try {
    const rows = await getSessionMessages(sid)
    messages.value = rows.map((r) => ({
      role: r.role,
      content: r.content,
      exports: [],
    }))
    sessionId.value = sid
    scrollBottom()
  } catch (e) {
    ElMessage.error('加载会话失败：' + (e.response?.data?.detail || e.message))
  } finally {
    loadingHistory.value = false
  }
}

async function onDeleteSession(sid) {
  try {
    await ElMessageBox.confirm('确定删除这个会话？记录将无法恢复。', '删除会话', {
      type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消',
    })
  } catch {
    return
  }
  try {
    await deleteSession(sid)
    sessions.value = sessions.value.filter((s) => s.id !== sid)
    if (sid === sessionId.value) newSession()
    ElMessage.success('已删除')
  } catch (e) {
    ElMessage.error('删除失败：' + (e.response?.data?.detail || e.message))
  }
}

/** 清空全部对话记录。考试数据与题库不受影响，文案里说清楚以免用户误解。 */
async function onClearAll() {
  if (sessions.value.length === 0) {
    ElMessage.info('没有对话记录可清空')
    return
  }
  try {
    await ElMessageBox.confirm(
      `将删除全部 ${sessions.value.length} 个会话及其消息，不可恢复。` +
      '（你的考试记录与成绩不受影响）',
      '清空全部对话',
      {
        type: 'error',
        confirmButtonText: '我确定，全部删除',
        cancelButtonText: '取消',
        confirmButtonClass: 'el-button--danger',
      },
    )
  } catch {
    return // 用户取消
  }

  clearingAll.value = true
  try {
    const r = await clearSessions()
    sessions.value = []
    newSession()  // 复位当前对话，否则界面还停在一个已被删掉的会话上
    ElMessage.success(`已清空 ${r.deleted_sessions} 个会话`)
  } catch (e) {
    ElMessage.error('清空失败：' + (e.response?.data?.detail || e.message))
  } finally {
    clearingAll.value = false
  }
}

async function onDownload(exp) {
  if (downloading.value) return
  downloading.value = true
  try {
    await downloadExam(exp.exam_id, { mode: exp.mode })
  } catch (e) {
    ElMessage.error('下载失败：' + (e.response?.data?.detail || e.message))
  } finally {
    downloading.value = false
  }
}

async function scrollBottom() {
  await nextTick()
  const el = listRef.value
  if (el) el.scrollTop = el.scrollHeight
}

async function send(text) {
  const msg = (text ?? input.value).trim()
  if (!msg || sending.value) return
  input.value = ''

  const isNew = sessionId.value == null
  messages.value.push({ role: 'user', content: msg })
  scrollBottom()

  messages.value.push({
    role: 'assistant', content: '', stage: '', exports: [], streaming: true,
  })
  streamingIdx = messages.value.length - 1
  sending.value = true

  closeStream = chatStream(msg, sessionId.value, {
    onSession(sid) {
      // 后端在流最开始返回 session_id，立即持久化并刷新列表
      sessionId.value = sid
      if (isNew) refreshSessions()
    },
    onToken(content) {
      messages.value[streamingIdx].content += content
      messages.value[streamingIdx].stage = ''
      scrollBottom()
    },
    onTool(name, args) {
      messages.value[streamingIdx].stage = toolLabel(name)
      // 捕获导出工具调用 → 渲染下载按钮（exam_id 来自工具参数，可靠）
      if (name === 'export_exam' && args && args.exam_id != null) {
        // mode 是新参数；旧调用只有 with_answers，做一次兼容映射
        const mode = args.mode || (args.with_answers ? 'with_answers' : 'questions')
        const list = messages.value[streamingIdx].exports
        // 同一张卷的同一模式只保留一个按钮：模型偶尔会对同一 mode 重复调用，
        // 不去重就会冒出两个一模一样的下载按钮
        if (!list.some((e) => e.exam_id === args.exam_id && e.mode === mode)) {
          list.push({ exam_id: args.exam_id, mode })
        }
      }
    },
    onDone(sid) {
      sessionId.value = sid
      scrollBottom()
      refreshSessions() // 刷新标题/排序
    },
    onError(detail, kind) {
      if (streamingIdx >= 0) messages.value[streamingIdx].error = true
      // 网络中断的文案已自解释，服务端错误才加场景前缀
      ElMessage.error(kind === 'network' ? detail : '对话失败：' + detail)
    },
    // 正常结束/出错/主动取消都会走到这里，状态复位收在一处，
    // 避免 close() 后 streaming 残留为 true 导致输入框一直禁用
    onClose() {
      if (streamingIdx >= 0) {
        messages.value[streamingIdx].streaming = false
        messages.value[streamingIdx].stage = ''
      }
      streamingIdx = -1
      closeStream = null
      sending.value = false
    },
  })
}

function stopStream() {
  closeStream?.()  // 触发 onClose('abort') 完成状态复位
}

function onKeydown(e) {
  // 移动端不拦截 Enter（软键盘换行），桌面端 Enter 发送
  if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
    const isMobile = window.matchMedia('(max-width: 640px)').matches
    if (!isMobile) {
      e.preventDefault()
      send()
    }
  }
}

function newSession() {
  closeStream?.()
  closeStream = null
  messages.value = []
  sessionId.value = null
  sending.value = false
  streamingIdx = -1
}

onMounted(refreshSessions)
</script>

<template>
  <div class="chat-layout">
    <!-- 历史会话侧栏 -->
    <aside class="session-pane">
      <el-button class="new-btn" type="primary" @click="newSession">
        <el-icon style="margin-right: 4px"><Plus /></el-icon>新会话
      </el-button>
      <div class="session-list">
        <!-- transition-group：删除会话时其余项平滑上移，而非瞬间跳位 -->
        <transition-group name="sess">
          <div
            v-for="s in sessions"
            :key="s.id"
            class="session-item"
            :class="{ active: s.id === sessionId }"
            @click="openSession(s.id)"
          >
            <el-icon class="s-icon"><ChatLineRound /></el-icon>
            <span class="s-title">{{ s.title }}</span>
            <el-icon class="s-del" @click.stop="onDeleteSession(s.id)"><Delete /></el-icon>
          </div>
        </transition-group>
        <div v-if="sessions.length === 0" class="session-empty">暂无历史会话</div>
      </div>
      <!-- 清空按钮放列表底部：与「新会话」拉开距离，降低误点概率 -->
      <el-button
        v-if="sessions.length"
        class="clear-btn"
        size="small"
        text
        type="danger"
        :loading="clearingAll"
        @click="onClearAll"
      >
        <el-icon style="margin-right: 4px"><Delete /></el-icon>清空全部对话
      </el-button>
    </aside>

    <!-- 对话主区 -->
    <div class="chat-wrap" v-loading="loadingHistory">
      <div class="chat-head">
        <b>AI 学习助手</b>
        <el-button size="small" text @click="newSession">新会话</el-button>
      </div>

      <div ref="listRef" class="chat-list">
        <div v-if="messages.length === 0" class="empty">
          <p>我是你的 JLPT 学习助手，可以帮你出题、组卷、讲解语法。试试：</p>
          <div class="examples">
            <el-button v-for="ex in EXAMPLES" :key="ex" size="small" round @click="send(ex)">{{ ex }}</el-button>
          </div>
        </div>

        <div v-for="(m, i) in messages" :key="i" class="msg-row" :class="m.role">
          <div class="bubble" :class="{ error: m.error }">
            <div v-if="m.role === 'assistant'" class="md" v-html="renderMd(m.content)" />
            <span v-else>{{ m.content }}</span>
            <span v-if="m.streaming" class="cursor">▍</span>
            <!-- 首 token 前显示当前在做什么；工具名对学生无意义，故映射成中文文案 -->
            <div v-if="m.streaming && !m.content" class="waiting">
              <el-icon class="is-loading"><Loading /></el-icon>
              <span>{{ m.stage || '正在思考…' }}</span>
            </div>
            <!-- 导出下载按钮：来自 export_exam 工具调用 -->
            <div v-if="m.exports && m.exports.length" class="exports">
              <el-button
                v-for="(exp, ei) in m.exports"
                :key="`${exp.exam_id}-${exp.mode}-${ei}`"
                type="primary"
                class="dl-btn"
                size="small"
                :loading="downloading"
                @click="onDownload(exp)"
              >
                <el-icon style="margin-right: 4px"><Download /></el-icon>
                {{ EXPORT_LABELS[exp.mode] || '下载试卷' }}
              </el-button>
            </div>
          </div>
        </div>
      </div>

      <div class="chat-input">
        <el-input
          v-model="input"
          type="textarea"
          :rows="2"
          resize="none"
          placeholder="输入问题…"
          :disabled="sending"
          @keydown="onKeydown"
        />
        <!-- 发送 ↔ 停止 交叉淡入。mode=out-in 避免两个按钮同时占位把输入框挤窄 -->
        <transition name="btn-swap" mode="out-in">
          <el-button v-if="sending" key="stop" class="send-btn" @click="stopStream">停止</el-button>
          <el-button v-else key="send" type="primary" class="send-btn" @click="send()">发送</el-button>
        </transition>
      </div>
    </div>
  </div>
</template>

<style scoped>
.chat-layout {
  display: flex;
  gap: 16px;
  height: 100%;
  max-width: 1200px;
  margin: 0 auto;
}

/* ── 历史会话侧栏 ── */
.session-pane {
  width: 240px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  background: #fff;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  padding: 12px;
  overflow: hidden;
}
.new-btn { width: 100%; margin-bottom: 12px; flex-shrink: 0; }
/* + 图标 hover 旋转，呼应"新建" */
.new-btn :deep(.el-icon) { transition: transform var(--dur-slow) var(--ease-spring); }
.new-btn:hover :deep(.el-icon) { transform: rotate(90deg); }
/* 金色实心按钮配深色文字，对比度更高、清晰可读（避免金底白字发虚） */
.new-btn,
.dl-btn {
  --el-button-text-color: #422006;
  --el-button-hover-text-color: #422006;
  font-weight: 600;
}
.session-list {
  flex: 1;
  overflow-y: auto;
  overscroll-behavior: contain;
  margin: 0 -6px;
  padding: 0 6px;
  /* 离场项用 position:absolute 脱离流，需要这里做定位参照 */
  position: relative;
}
/* 清空按钮固定在侧栏底部，与列表用分隔线隔开 */
.clear-btn {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid #f0f0f0;
  width: 100%;
  border-radius: 0;
}
.session-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 8px;
  cursor: pointer;
  color: #606266;
  font-size: 13px;
  position: relative;
  transition: background-color var(--dur-base) var(--ease-out),
              color var(--dur-base) var(--ease-out),
              transform var(--dur-base) var(--ease-out);
}
.session-item:hover { background: #f5f7fa; }
.session-item:active { transform: scale(0.98); transition-duration: var(--dur-fast); }
.session-item.active { background: #fef3e2; color: #b45309; font-weight: 500; }
/* 选中项左侧金色竖条从中间展开，标出"当前在这个会话" */
.session-item.active::before {
  content: '';
  position: absolute;
  left: 2px;
  top: 50%;
  width: 3px;
  height: 60%;
  border-radius: 2px;
  background: #f59e0b;
  transform: translateY(-50%);
  animation: bar-expand var(--dur-base) var(--ease-out);
}
@keyframes bar-expand {
  from { height: 0; }
  to   { height: 60%; }
}
.session-item .s-icon { flex-shrink: 0; font-size: 14px; }
.session-item .s-title {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.session-item .s-del {
  flex-shrink: 0;
  opacity: 0;
  color: #c0c4cc;
  transition: opacity var(--dur-base) var(--ease-out),
              color var(--dur-base) var(--ease-out),
              transform var(--dur-base) var(--ease-spring);
}
.session-item:hover .s-del { opacity: 1; }
.session-item .s-del:hover { color: #f56c6c; transform: scale(1.2); }
.session-item .s-del:active { transform: scale(0.9); transition-duration: var(--dur-fast); }
.session-empty {
  color: #c0c4cc;
  font-size: 13px;
  text-align: center;
  margin-top: 20px;
  animation: fade-in var(--dur-slow) var(--ease-out);
}

/* 会话列表增删：离场项脱离文档流（position:absolute），
   剩下的项才能用 .sess-move 平滑补位而不是瞬间跳上来 */
.sess-enter-active { transition: opacity var(--dur-base) var(--ease-out), transform var(--dur-base) var(--ease-out); }
.sess-leave-active { transition: opacity var(--dur-fast) var(--ease-in-out), transform var(--dur-fast) var(--ease-in-out); position: absolute; width: calc(100% - 12px); }
.sess-enter-from { opacity: 0; transform: translateX(-10px); }
.sess-leave-to { opacity: 0; transform: translateX(-10px); }
.sess-move { transition: transform var(--dur-base) var(--ease-out); }

.chat-wrap {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  /* 填满 app-main 内容区，由内部 .chat-list 滚动，避免页面整体滚动 */
  height: 100%;
}

.chat-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 2px 10px;
  flex-shrink: 0;
}

.chat-list {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
  background: #fff;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  overscroll-behavior: contain;
  -webkit-overflow-scrolling: touch;
}

.empty {
  color: #999;
  text-align: center;
  margin-top: 40px;
  padding: 0 8px;
  animation: fade-up var(--dur-slow) var(--ease-out);
}
.examples {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: center;
  margin-top: 12px;
}
/* 示例问句依次浮现，引导视线落到"可以点这个" */
.examples :deep(.el-button) {
  animation: fade-up var(--dur-slow) var(--ease-out) backwards;
}
.examples :deep(.el-button:nth-child(2)) { animation-delay: 70ms; }
.examples :deep(.el-button:nth-child(3)) { animation-delay: 140ms; }

.msg-row { display: flex; margin-bottom: 12px; }
/* 气泡从各自那一侧滑入，方向暗示"谁在说话"。
   动画挂在 .bubble 上而非 .msg-row：行是 flex 容器，
   给它加 transform 会让子元素的对齐在动画期间抖动。 */
.msg-row.user { justify-content: flex-end; }
.msg-row.assistant { justify-content: flex-start; }
.msg-row.user .bubble { animation: bubble-in-right var(--dur-base) var(--ease-out); }
.msg-row.assistant .bubble { animation: bubble-in-left var(--dur-base) var(--ease-out); }
@keyframes bubble-in-right {
  from { opacity: 0; transform: translate(8px, 6px) scale(0.97); }
  to   { opacity: 1; transform: none; }
}
@keyframes bubble-in-left {
  from { opacity: 0; transform: translate(-8px, 6px) scale(0.97); }
  to   { opacity: 1; transform: none; }
}

.bubble {
  max-width: 82%;
  padding: 10px 14px;
  border-radius: 10px;
  line-height: 1.7;
  word-break: break-word;
  overflow-x: hidden;
}
.msg-row.user .bubble {
  background: #f59e0b;
  color: #fff;
  white-space: pre-wrap;
}
.msg-row.assistant .bubble {
  background: #f4f4f5;
  color: #303133;
}
.bubble.error { background: #fef0f0; color: #f56c6c; }

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

/* 首 token 前的等待提示。文字随阶段变化，做一次呼吸让它显得"在动" */
.waiting {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: #b45309;
  animation: fade-in var(--dur-base) var(--ease-out);
}
.waiting span { animation: breathe 1.6s var(--ease-in-out) infinite; }
@keyframes breathe {
  0%, 100% { opacity: 1; }
  50%      { opacity: 0.55; }
}

.exports {
  margin-top: 10px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
/* 下载按钮在工具调用后才出现，给一次回弹入场提示"可以下载了" */
.dl-btn { animation: pop-in var(--dur-slow) var(--ease-spring); }
@keyframes pop-in {
  from { opacity: 0; transform: scale(0.85); }
  to   { opacity: 1; transform: scale(1); }
}

.chat-input {
  display: flex;
  gap: 8px;
  align-items: flex-end;
  margin-top: 10px;
  flex-shrink: 0;
}
.chat-input :deep(.el-textarea) { flex: 1; min-width: 0; }
.send-btn { flex-shrink: 0; height: 60px; }
/* 发送 ↔ 停止 交叉淡入。时长取 fast：这里是高频操作，动画长了会挡手 */
.btn-swap-enter-active,
.btn-swap-leave-active {
  transition: opacity var(--dur-fast) var(--ease-out), transform var(--dur-fast) var(--ease-out);
}
.btn-swap-enter-from,
.btn-swap-leave-to { opacity: 0; transform: scale(0.94); }

/* markdown 内容 */
.md :deep(p)  { margin: 6px 0; }
.md :deep(h1),.md :deep(h2),.md :deep(h3) { margin: 10px 0 6px; }
.md :deep(ul),.md :deep(ol) { padding-left: 20px; margin: 6px 0; }
.md :deep(li) { margin: 4px 0; line-height: 1.6; }
.md :deep(pre) { background: #fbf9f4; padding: 10px; border-radius: 6px; overflow-x: auto; }
.md :deep(code) { background: #fbf9f4; padding: 1px 4px; border-radius: 3px; font-size: 13px; }
/* 表格可横向滚动，不撑破气泡 */
.md :deep(table) {
  border-collapse: collapse;
  min-width: 100%;
  display: block;
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
}
.md :deep(th),.md :deep(td) { border: 1px solid #dcdfe6; padding: 6px 10px; white-space: nowrap; }
.md :deep(th) { background: #fbf9f4; }

@media (max-width: 640px) {
  /* 移动端：隐藏会话侧栏，聚焦对话；历史通过「新会话」按钮管理 */
  .session-pane { display: none; }
  .chat-wrap { height: 100%; }
  .bubble { max-width: 90%; }
  .send-btn { height: 52px; }
}
</style>
