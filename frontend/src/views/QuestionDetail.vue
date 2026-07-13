<script setup>
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { getQuestion, updateQuestion, createQuestion, listCategories } from '../api/questions'

const props = defineProps({ id: { type: [String, Number], default: null } })
const router = useRouter()

const isCreate = computed(() => props.id == null)

const LABELS = ['a', 'b', 'c', 'd']
const LEVEL_OPTIONS = ['N1', 'N2', 'N3', 'N4', 'N5']
const TYPE_OPTIONS = [
  { value: 'single_choice', label: '单项选择' },
  { value: 'cloze', label: '完形填空' },
  { value: 'reading', label: '阅读理解' },
]

const loading = ref(false)
const saving = ref(false)
const form = reactive({
  id: null,
  type: 'single_choice',
  category: null,
  article: null,
  level: '',
  exam_date: '',
  difficulty: 0,
  knowledge_points: [],
  questions: [],
})

// 题型选项（按当前级别联动；全部题型可选，含不可出题的，方便校对标注）
const categoryOptions = ref([])
async function loadCategoryOptions(clearInvalid = true) {
  try {
    const data = await listCategories(form.level || undefined, false)
    categoryOptions.value = data.items || []
    // 级别变化后，若已选题型不在新级别则清空（load 回填时不清）
    if (clearInvalid && form.category && !categoryOptions.value.some((c) => c.code === form.category)) {
      form.category = null
    }
  } catch {
    // 加载失败不阻塞
  }
}
const groupedCategories = computed(() => {
  const groups = {}
  for (const c of categoryOptions.value) (groups[c.section_label] ||= []).push(c)
  return Object.entries(groups).map(([label, items]) => ({ label, items }))
})
// 用户手动改级别才联动清空；load 期间不挂 watch
let levelWatchOn = false
watch(() => form.level, () => { if (levelWatchOn) loadCategoryOptions(true) })

const asText = (v) => (v == null ? '' : typeof v === 'string' ? v : JSON.stringify(v))

function blankQuestion(seq) {
  return {
    seq,
    content: '',
    marked: '',
    answer: 'a',
    analysis: '',
    options: LABELS.map((label) => ({ label, content: '' })),
  }
}

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

// 子题增删
function addQuestion() {
  form.questions.push(blankQuestion(form.questions.length + 1))
}
function removeQuestion(idx) {
  form.questions.splice(idx, 1)
  // 重排 seq，保持连续
  form.questions.forEach((q, i) => (q.seq = i + 1))
}

async function load() {
  loading.value = true
  try {
    const g = await getQuestion(props.id)
    form.id = g.id
    form.type = g.type
    form.level = g.level || ''
    form.article = g.article
    form.exam_date = g.exam_date || ''
    form.difficulty = g.difficulty ?? 0
    form.knowledge_points = [...(g.knowledge_points || [])]
    form.questions = (g.questions || []).map(normalizeQuestion)
    // 先按级别载入题型选项，再回填 category，避免被 watch 清空
    await loadCategoryOptions(false)
    form.category = g.category || null
    levelWatchOn = true
  } catch (e) {
    ElMessage.error('加载失败：' + (e.response?.data?.detail || e.message))
  } finally {
    loading.value = false
  }
}

function validate() {
  if (!form.questions.length) return '至少需要一道子题'
  for (const [i, q] of form.questions.entries()) {
    if (!q.content || q.content.trim() === '') return `第 ${i + 1} 题题干不能为空`
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
    const payload = {
      type: form.type,
      category: form.category || null,
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
    if (isCreate.value) {
      const created = await createQuestion(payload)
      ElMessage.success('创建成功')
      // 跳转到新建题组的编辑页
      router.replace({ name: 'detail', params: { id: created.id } })
    } else {
      await updateQuestion(form.id, payload)
      ElMessage.success('已保存')
    }
  } catch (e) {
    ElMessage.error('保存失败：' + (e.response?.data?.detail || e.message))
  } finally {
    saving.value = false
  }
}

function goBack() {
  router.push({ name: 'list' })
}

onMounted(() => {
  if (isCreate.value) {
    form.questions = [blankQuestion(1)]
    loadCategoryOptions(false)
    levelWatchOn = true
  } else {
    load()
  }
})
</script>

<template>
  <div v-loading="loading">
    <el-page-header
      @back="goBack"
      :content="isCreate ? '新建题组' : `题组 #${form.id ?? ''}`"
      style="margin-bottom: 16px"
    />

    <el-form label-width="90px" style="max-width: 900px">
      <!-- 题组级字段 -->
      <el-card shadow="never" style="margin-bottom: 16px">
        <template #header>题组信息</template>
        <el-form-item label="级别">
          <el-select v-model="form.level" clearable style="width: 120px">
            <el-option v-for="l in LEVEL_OPTIONS" :key="l" :label="l" :value="l" />
          </el-select>
        </el-form-item>
        <el-form-item label="题型">
          <el-select
            v-model="form.category"
            clearable
            filterable
            :disabled="!form.level"
            :placeholder="form.level ? '选择 JLPT 题型' : '请先选择级别'"
            style="width: 260px"
          >
            <el-option-group v-for="g in groupedCategories" :key="g.label" :label="g.label">
              <el-option v-for="c in g.items" :key="c.code" :label="c.name" :value="c.code" />
            </el-option-group>
          </el-select>
        </el-form-item>
        <el-form-item label="结构">
          <el-select v-model="form.type" style="width: 160px">
            <el-option v-for="t in TYPE_OPTIONS" :key="t.value" :label="t.label" :value="t.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="考试日期">
          <el-date-picker
            v-model="form.exam_date"
            type="month"
            placeholder="选择年月"
            format="YYYY-MM"
            value-format="YYYY-MM"
            style="width: 160px"
          />
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
          <el-input v-model="form.article" type="textarea" :rows="4" class="jp-input" />
        </el-form-item>
      </el-card>

      <!-- 子题 -->
      <el-card v-for="(q, qi) in form.questions" :key="qi" shadow="never" style="margin-bottom: 16px">
        <template #header>
          <div class="q-card-head">
            <span>子题 {{ q.seq }}</span>
            <el-button
              link
              type="danger"
              :disabled="form.questions.length <= 1"
              @click="removeQuestion(qi)"
            >删除子题</el-button>
          </div>
        </template>
        <el-form-item label="题干">
          <el-input v-model="q.content" type="textarea" :rows="2" class="jp-input" />
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

      <div style="margin-bottom: 16px">
        <el-button plain @click="addQuestion">
          <el-icon style="margin-right: 4px"><Plus /></el-icon>增加子题
        </el-button>
      </div>

      <div style="text-align: right">
        <el-button @click="goBack">返回列表</el-button>
        <el-button type="primary" :loading="saving" @click="onSave">
          {{ isCreate ? '创建题组' : '保存校对' }}
        </el-button>
      </div>
    </el-form>
  </div>
</template>

<style scoped>
.q-card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
</style>
