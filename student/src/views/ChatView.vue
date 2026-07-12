<script setup>
import { ref, nextTick } from 'vue'
import { marked } from 'marked'
import { ElMessage } from 'element-plus'
import { chatStream } from '../api/agent'

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

let streamingIdx = -1
let closeStream = null

function renderMd(text) {
  return marked.parse(text || '')
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

  messages.value.push({ role: 'user', content: msg })
  scrollBottom()

  messages.value.push({ role: 'assistant', content: '', tools: [], streaming: true })
  streamingIdx = messages.value.length - 1
  sending.value = true

  closeStream = chatStream(msg, sessionId.value, {
    onToken(content) {
      messages.value[streamingIdx].content += content
      scrollBottom()
    },
    onTool(name) {
      messages.value[streamingIdx].tools.push(name)
    },
    onDone(sid) {
      sessionId.value = sid
      messages.value[streamingIdx].streaming = false
      streamingIdx = -1
      closeStream = null
      sending.value = false
      scrollBottom()
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
</script>

<template>
  <div class="chat-wrap">
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
</template>

<style scoped>
.chat-wrap {
  display: flex;
  flex-direction: column;
  /* 填满 el-main，el-main 默认 padding 20px 上下，高度 100vh - 50px header（移动）或 0（桌面） */
  height: calc(100vh - 60px);
  max-width: 860px;
  margin: 0 auto;
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
  background: #409eff;
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
  color: #409eff;
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
.md :deep(pre) { background: #f5f7fa; padding: 10px; border-radius: 6px; overflow-x: auto; }
.md :deep(code) { background: #f5f7fa; padding: 1px 4px; border-radius: 3px; font-size: 13px; }
/* 表格可横向滚动，不撑破气泡 */
.md :deep(table) {
  border-collapse: collapse;
  min-width: 100%;
  display: block;
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
}
.md :deep(th),.md :deep(td) { border: 1px solid #dcdfe6; padding: 6px 10px; white-space: nowrap; }
.md :deep(th) { background: #f5f7fa; }

@media (max-width: 640px) {
  /* 移动端：减去顶部导航栏 50px 和 el-main padding 24px */
  .chat-wrap { height: calc(100vh - 50px - 24px); }
  .bubble { max-width: 90%; }
  .send-btn { height: 52px; }
}
</style>
