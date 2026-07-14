<script setup>
import { ref, nextTick, onMounted } from 'vue'
import { marked } from 'marked'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Download, Plus, Delete, ChatLineRound } from '@element-plus/icons-vue'
import { chatStream, listSessions, getSessionMessages, deleteSession } from '../api/agent'
import { downloadExam } from '../api/exam'

const EXAMPLES = [
  '帮我出2道N1的题',
  '讲解一下 ば 和 たら 的区别',
  '给我看1道关于条件表达的题',
]

const messages = ref([])
const input = ref('')
const sending = ref(false)
const sessionId = ref(null)
const listRef = ref(null)
const downloading = ref(false)
const sessions = ref([])
const loadingHistory = ref(false)

let streamingIdx = -1
let closeStream = null

function renderMd(text) {
  return marked.parse(text || '')
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
      tools: [],
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

async function onDownload(exp) {
  if (downloading.value) return
  downloading.value = true
  try {
    await downloadExam(exp.exam_id, { withAnswers: exp.with_answers })
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

  messages.value.push({ role: 'assistant', content: '', tools: [], exports: [], streaming: true })
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
      scrollBottom()
    },
    onTool(name, args) {
      messages.value[streamingIdx].tools.push(name)
      // 捕获导出工具调用 → 渲染下载按钮（exam_id 来自工具参数，可靠）
      if (name === 'export_exam' && args && args.exam_id != null) {
        messages.value[streamingIdx].exports.push({
          exam_id: args.exam_id,
          with_answers: !!args.with_answers,
        })
      }
    },
    onDone(sid) {
      sessionId.value = sid
      messages.value[streamingIdx].streaming = false
      streamingIdx = -1
      closeStream = null
      sending.value = false
      scrollBottom()
      refreshSessions() // 刷新标题/排序
    },
    onError(detail) {
      messages.value[streamingIdx].streaming = false
      messages.value[streamingIdx].error = true
      streamingIdx = -1
      closeStream = null
      sending.value = false
      ElMessage.error('对话失败：' + detail)
    },
  })
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
        <div v-if="sessions.length === 0" class="session-empty">暂无历史会话</div>
      </div>
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
            <div v-if="m.tools && m.tools.length" class="tools">
              <el-tag v-for="(t, ti) in m.tools" :key="ti" size="small" type="info" effect="plain">
                🔧 {{ t }}
              </el-tag>
            </div>
            <!-- 导出下载按钮：来自 export_exam 工具调用 -->
            <div v-if="m.exports && m.exports.length" class="exports">
              <el-button
                v-for="(exp, ei) in m.exports"
                :key="ei"
                type="primary"
                class="dl-btn"
                size="small"
                :loading="downloading"
                @click="onDownload(exp)"
              >
                <el-icon style="margin-right: 4px"><Download /></el-icon>
                下载试卷{{ exp.with_answers ? '（含答案）' : '' }}
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
        <el-button type="primary" :loading="sending" class="send-btn" @click="send()">发送</el-button>
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
  transition: background 0.15s;
}
.session-item:hover { background: #f5f7fa; }
.session-item.active { background: #fef3e2; color: #b45309; font-weight: 500; }
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
  transition: opacity 0.15s, color 0.15s;
}
.session-item:hover .s-del { opacity: 1; }
.session-item .s-del:hover { color: #f56c6c; }
.session-empty { color: #c0c4cc; font-size: 13px; text-align: center; margin-top: 20px; }

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
}
.examples {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: center;
  margin-top: 12px;
}

.msg-row { display: flex; margin-bottom: 12px; }
.msg-row.user { justify-content: flex-end; }
.msg-row.assistant { justify-content: flex-start; }

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

.tools {
  margin-top: 8px;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.exports {
  margin-top: 10px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
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
