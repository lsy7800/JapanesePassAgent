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

// 当前流式消息索引，-1 表示没有进行中的消息
let streamingIdx = -1
// 关闭当前 SSE 连接的函数
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

  // 占位 assistant 消息，流式内容追加到这里
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
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    send()
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
          <div v-if="m.role === 'assistant'" class="md" v-html="renderMd(m.content)"></div>
          <span v-else>{{ m.content }}</span>

          <!-- 流式光标 -->
          <span v-if="m.streaming" class="cursor">▍</span>

          <!-- 工具调用标签 -->
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
        placeholder="输入问题，Enter 发送，Shift+Enter 换行"
        :disabled="sending"
        @keydown="onKeydown"
      />
      <el-button type="primary" :loading="sending" @click="send()">发送</el-button>
    </div>
  </div>
</template>

<style scoped>
.chat-wrap {
  display: flex;
  flex-direction: column;
  height: calc(100vh - 40px);
  max-width: 860px;
}
.chat-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 4px;
}
.chat-list {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
  background: #fff;
  border: 1px solid #ebeef5;
  border-radius: 8px;
}
.empty {
  color: #999;
  text-align: center;
  margin-top: 40px;
}
.examples {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: center;
  margin-top: 12px;
}
.msg-row {
  display: flex;
  margin-bottom: 14px;
}
.msg-row.user {
  justify-content: flex-end;
}
.msg-row.assistant {
  justify-content: flex-start;
}
.bubble {
  max-width: 78%;
  padding: 10px 14px;
  border-radius: 10px;
  line-height: 1.7;
  word-break: break-word;
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
.bubble.error {
  background: #fef0f0;
  color: #f56c6c;
}
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
  margin-top: 12px;
}
.chat-input .el-textarea {
  flex: 1;
}
.md :deep(table) {
  border-collapse: collapse;
  margin: 8px 0;
}
.md :deep(th),
.md :deep(td) {
  border: 1px solid #dcdfe6;
  padding: 6px 10px;
}
.md :deep(th) {
  background: #f5f7fa;
}
.md :deep(pre) {
  background: #f5f7fa;
  padding: 10px;
  border-radius: 6px;
  overflow-x: auto;
}
.md :deep(code) {
  background: #f5f7fa;
  padding: 1px 4px;
  border-radius: 3px;
}
.md :deep(p) {
  margin: 6px 0;
}
.md :deep(h1),
.md :deep(h2),
.md :deep(h3) {
  margin: 10px 0 6px;
}
</style>
