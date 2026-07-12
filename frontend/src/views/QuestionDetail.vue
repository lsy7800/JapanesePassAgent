<script setup>
import { ref, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { getQuestion, updateQuestion } from '../api/questions'

const props = defineProps({ id: { type: [String, Number], required: true } })
const router = useRouter()

const LABELS = ['a', 'b', 'c', 'd']
const LEVEL_OPTIONS = ['N1', 'N2', 'N3', 'N4', 'N5']
const TYPE_OPTIONS = [
  { value: 'single_choice', label: '单项选择' },
  { value: 'cloze', label: '完形填空' },
  { value: 'reading', label: '阅读理解' },
]

const loading = ref(false)
const saving = ref(false)
// 编辑态：把后端题组规整为表单友好的形状（选项固定 a/b/c/d 顺序）
const form = reactive({
  id: null,
  type: 'single_choice',
  article: null,
  level: '',
  exam_date: '',
  difficulty: 0,
  knowledge_points: [],
  questions: [],
})

// 富文本字段当前为纯文本字符串；若后端返回数组（未来富文本），转成 JSON 字符串占位编辑
const asText = (v) => (v == null ? '' : typeof v === 'string' ? v : JSON.stringify(v))

function normalizeQuestion(q) {
  const byLabel = {}
  for (const o of q.options || []) byLabel[o.label] = o.content
  return {
    seq: q.seq ?? 1,
    content: asText(q.content),
    marked: q.marked || '',
    answer: q.answer || 'a',
    analysis: asText(q.analysis),
    options: LABELS.map((label) => ({ label, content: asText(byLabel[label]) })),
  }
}

const newKp = ref('')
function addKp() {
  const v = newKp.value.trim()
  if (v && !form.knowledge_points.includes(v)) form.knowledge_points.push(v)
  newKp.value = ''
}
function removeKp(kp) {
  form.knowledge_points = form.knowledge_points.filter((x) => x !== kp)
}

async function load() {
  loading.value = true
  try {
    const g = await getQuestion(props.id)
    form.id = g.id
    form.type = g.type
    form.article = g.article
    form.level = g.level || ''
    form.exam_date = g.exam_date || ''
    form.difficulty = g.difficulty ?? 0
    form.knowledge_points = [...(g.knowledge_points || [])]
    form.questions = (g.questions || []).map(normalizeQuestion)
  } catch (e) {
    ElMessage.error('加载失败：' + (e.response?.data?.detail || e.message))
  } finally {
    loading.value = false
  }
}

function validate() {
  for (const [i, q] of form.questions.entries()) {
    if (!LABELS.includes(q.answer)) return `第 ${i + 1} 题答案必须是 a/b/c/d`
    for (const o of q.options) {
      if (o.content === '' || o.content == null) return `第 ${i + 1} 题选项 ${o.label} 不能为空`
    }
  }
  return null
}

async function onSave() {
  const err = validate()
  if (err) {
    ElMessage.warning(err)
    return
  }
  saving.value = true
  try {
    // 组装 PUT body（全量替换，形状与后端 QuestionGroupCreate 一致）
    const payload = {
      type: form.type,
      article: form.article,
      level: form.level,
      exam_date: form.exam_date,
      difficulty: form.difficulty,
      knowledge_points: form.knowledge_points,
      questions: form.questions.map((q) => ({
        seq: q.seq,
        content: q.content,
        marked: q.marked,
        answer: q.answer,
        analysis: q.analysis,
        options: q.options.map((o) => ({ label: o.label, content: o.content })),
      })),
    }
    await updateQuestion(form.id, payload)
    ElMessage.success('已保存')
  } catch (e) {
    ElMessage.error('保存失败：' + (e.response?.data?.detail || e.message))
  } finally {
    saving.value = false
  }
}

function goBack() {
  router.push({ name: 'list' })
}

onMounted(load)
</script>

<template>
  <div v-loading="loading">
    <el-page-header @back="goBack" :content="`题组 #${form.id ?? ''}`" style="margin-bottom: 16px" />

    <el-form label-width="90px" style="max-width: 900px">
      <!-- 题组级字段 -->
      <el-card shadow="never" style="margin-bottom: 16px">
        <template #header>题组信息</template>
        <el-form-item label="题型">
          <el-select v-model="form.type" style="width: 160px">
            <el-option v-for="t in TYPE_OPTIONS" :key="t.value" :label="t.label" :value="t.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="级别">
          <el-select v-model="form.level" clearable style="width: 120px">
            <el-option v-for="l in LEVEL_OPTIONS" :key="l" :label="l" :value="l" />
          </el-select>
        </el-form-item>
        <el-form-item label="考试日期">
          <el-input v-model="form.exam_date" placeholder="如 2023-07" style="width: 160px" />
        </el-form-item>
        <el-form-item label="难度">
          <el-input-number v-model="form.difficulty" :min="0" :max="9" />
        </el-form-item>
        <el-form-item label="知识点">
          <div>
            <el-tag
              v-for="kp in form.knowledge_points"
              :key="kp"
              closable
              @close="removeKp(kp)"
              style="margin: 2px"
            >{{ kp }}</el-tag>
            <el-input
              v-model="newKp"
              size="small"
              placeholder="+ 新增知识点，回车"
              style="width: 160px; margin-left: 4px"
              @keyup.enter="addKp"
            />
          </div>
        </el-form-item>
        <el-form-item v-if="form.type !== 'single_choice'" label="文章">
          <el-input v-model="form.article" type="textarea" :rows="4" />
        </el-form-item>
      </el-card>

      <!-- 子题 -->
      <el-card v-for="(q, qi) in form.questions" :key="qi" shadow="never" style="margin-bottom: 16px">
        <template #header>子题 {{ q.seq }}</template>
        <el-form-item label="题干">
          <el-input v-model="q.content" type="textarea" :rows="2" />
        </el-form-item>
        <el-form-item label="划线词">
          <el-input v-model="q.marked" style="width: 240px" />
        </el-form-item>
        <el-form-item v-for="o in q.options" :key="o.label" :label="`选项 ${o.label.toUpperCase()}`">
          <el-input v-model="o.content" />
        </el-form-item>
        <el-form-item label="答案">
          <el-radio-group v-model="q.answer">
            <el-radio v-for="l in LABELS" :key="l" :value="l">{{ l.toUpperCase() }}</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="解析">
          <el-input v-model="q.analysis" type="textarea" :rows="4" />
        </el-form-item>
      </el-card>

      <div style="text-align: right">
        <el-button @click="goBack">返回列表</el-button>
        <el-button type="primary" :loading="saving" @click="onSave">保存校对</el-button>
      </div>
    </el-form>
  </div>
</template>
