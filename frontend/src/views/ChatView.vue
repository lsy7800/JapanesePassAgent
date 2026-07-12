<script setup>
import { ref, nextTick } from 'vue'
import { marked } from 'marked'
import { ElMessage } from 'element-plus'
import { chat } from '../api/agent'

const EXAMPLES = [
  '帮我出2道N1的题',
  '讲解一下 ば 和 たら 的区别',
  '给我看1道关于条件表达的题',
]

const messages = ref([]) // { role: 'user'|'assistant', content, tools?: [] }
const input = ref('')
const sending = ref(false)
const sessionId = ref(null)
const listRef = ref(null)

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

  sending.value = true
  try {
    const data = await chat(msg, sessionId.value)
    sessionId.value = data.session_id
    messages.value.push({
      role: 'assistant',
      content: data.reply,
      tools: (data.tool_calls || []).map((t) => t.tool),
    })
    scrollBottom()
  } catch (e) {
    ElMessage.error('对话失败：' + (e.response?.data?.detail || e.message))
  } finally {
    sending.value = false
  }
}

function onKeydown(e) {
  // Enter 发送，Shift+Enter 换行
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    send()
  }
}

function newSession() {
  messages.value = []
  sessionId.value = null
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
        <div class="bubble">
          <div v-if="m.role === 'assistant'" class="md" v-html="renderMd(m.content)"></div>
          <span v-else>{{ m.content }}</span>
          <div v-if="m.tools && m.tools.length" class="tools">
            <el-tag v-for="(t, ti) in m.tools" :key="ti" size="small" type="info" effect="plain">🔧 {{ t }}</el-tag>
          </div>
        </div>
      </div>

      <div v-if="sending" class="msg-row assistant">
        <div class="bubble typing">思考中…</div>
      </div>
    </div>

    <div class="chat-input">
      <el-input
        v-model="input"
        type="textarea"
        :rows="2"
        resize="none"
        placeholder="输入问题，Enter 发送，Shift+Enter 换行"
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
.bubble.typing {
  color: #999;
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
/* Markdown 渲染样式 */
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
