<script setup>
import { ref, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { listQuestions, deleteQuestion, listSources } from '../api/questions'

const router = useRouter()

const TYPE_OPTIONS = [
  { value: 'single_choice', label: '单项选择' },
  { value: 'cloze', label: '完形填空' },
  { value: 'reading', label: '阅读理解' },
]
const LEVEL_OPTIONS = ['N1', 'N2', 'N3', 'N4', 'N5']

const sources = ref([]) // [{ source, count }]

const filters = reactive({
  source: '',
  type: '',
  level: '',
  difficulty_min: null,
  difficulty_max: null,
  knowledge_point: '',
})

const loading = ref(false)
const rows = ref([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)

const typeLabel = (v) => TYPE_OPTIONS.find((t) => t.value === v)?.label || v

async function load() {
  loading.value = true
  try {
    const data = await listQuestions({
      ...filters,
      page: page.value,
      page_size: pageSize.value,
    })
    rows.value = data.items
    total.value = data.total
  } catch (e) {
    ElMessage.error('加载失败：' + (e.response?.data?.detail || e.message))
  } finally {
    loading.value = false
  }
}

function onSearch() {
  page.value = 1
  load()
}

function onReset() {
  filters.source = ''
  filters.type = ''
  filters.level = ''
  filters.difficulty_min = null
  filters.difficulty_max = null
  filters.knowledge_point = ''
  page.value = 1
  load()
}

function onPageChange(p) {
  page.value = p
  load()
}

function goDetail(id) {
  router.push({ name: 'detail', params: { id } })
}

async function onDelete(row) {
  try {
    await ElMessageBox.confirm(`确定删除题组 #${row.id}？此操作不可恢复。`, '删除确认', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
  } catch {
    return // 用户取消
  }
  try {
    await deleteQuestion(row.id)
    ElMessage.success('已删除')
    // 删除后若当前页空了则回退一页
    if (rows.value.length === 1 && page.value > 1) page.value -= 1
    load()
  } catch (e) {
    ElMessage.error('删除失败：' + (e.response?.data?.detail || e.message))
  }
}

async function loadSources() {
  try {
    sources.value = await listSources()
  } catch {
    // 批次统计失败不阻塞主列表
  }
}

// 切换批次时立即重新查询（下拉即筛选，无需再点查询）
function onSourceChange() {
  page.value = 1
  load()
}

onMounted(() => {
  loadSources()
  load()
})
</script>

<template>
  <div>
    <el-card shadow="never" class="filter-card">
      <el-form :inline="true" :model="filters">
        <el-form-item label="批次">
          <el-select v-model="filters.source" placeholder="全部批次" clearable style="width: 220px" @change="onSourceChange">
            <el-option
              v-for="s in sources"
              :key="s.source"
              :label="`${s.source}（${s.count}题）`"
              :value="s.source"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="题型">
          <el-select v-model="filters.type" placeholder="全部" clearable style="width: 140px">
            <el-option v-for="t in TYPE_OPTIONS" :key="t.value" :label="t.label" :value="t.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="级别">
          <el-select v-model="filters.level" placeholder="全部" clearable style="width: 100px">
            <el-option v-for="l in LEVEL_OPTIONS" :key="l" :label="l" :value="l" />
          </el-select>
        </el-form-item>
        <el-form-item label="难度">
          <el-input-number v-model="filters.difficulty_min" :min="0" :max="9" placeholder="min" controls-position="right" style="width: 100px" />
          <span style="margin: 0 6px">-</span>
          <el-input-number v-model="filters.difficulty_max" :min="0" :max="9" placeholder="max" controls-position="right" style="width: 100px" />
        </el-form-item>
        <el-form-item label="知识点">
          <el-input v-model="filters.knowledge_point" placeholder="关键词" clearable style="width: 140px" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="onSearch">查询</el-button>
          <el-button @click="onReset">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-table :data="rows" v-loading="loading" border stripe style="margin-top: 16px">
      <el-table-column prop="id" label="ID" width="80" />
      <el-table-column prop="source" label="批次" width="180" show-overflow-tooltip />
      <el-table-column label="题型" width="110">
        <template #default="{ row }">{{ typeLabel(row.type) }}</template>
      </el-table-column>
      <el-table-column prop="level" label="级别" width="80" />
      <el-table-column prop="difficulty" label="难度" width="80" />
      <el-table-column prop="exam_date" label="考试日期" width="110" />
      <el-table-column label="知识点" min-width="200">
        <template #default="{ row }">
          <el-tag v-for="kp in row.knowledge_points" :key="kp" size="small" style="margin: 2px">{{ kp }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="170" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="goDetail(row.id)">查看/校对</el-button>
          <el-button link type="danger" @click="onDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-pagination
      style="margin-top: 16px; justify-content: flex-end"
      layout="total, prev, pager, next"
      :total="total"
      :page-size="pageSize"
      :current-page="page"
      @current-change="onPageChange"
    />
  </div>
</template>

<style scoped>
.filter-card {
  background: #fafafa;
}
</style>
