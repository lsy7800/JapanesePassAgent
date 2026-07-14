<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { EditPen, ChatDotRound, List, TrendCharts, MagicStick, ArrowRight } from '@element-plus/icons-vue'
import { useAuthStore } from '../stores/auth'
import { listExams, getWeakPoints, getHistoryTrend } from '../api/exam'

const router = useRouter()
const auth = useAuthStore()

// 时段问候
const greeting = computed(() => {
  const h = new Date().getHours()
  if (h < 6) return '夜深了'
  if (h < 12) return '早上好'
  if (h < 14) return '中午好'
  if (h < 18) return '下午好'
  return '晚上好'
})

// 每日轮换一句激励语（按星期取，稳定不跳变）
const MOTIVATIONS = [
  '每天一点点，合格就不远。',
  '坚持就是最好的天赋。',
  '今天的努力，是明天的底气。',
  '一题一进步，稳扎稳打。',
  '语言是积累的艺术，加油。',
  '慢慢来，比较快。',
  '你已经比昨天更强了。',
]
const motivation = computed(() => MOTIVATIONS[new Date().getDay() % MOTIVATIONS.length])

const userName = computed(() => (auth.email || '').split('@')[0] || '同学')

// 快捷入口
const ACTIONS = [
  { path: '/exam', icon: EditPen, title: '在线考试', desc: '组卷答题，实战演练', color: '#f59e0b' },
  { path: '/chat', icon: ChatDotRound, title: 'AI 助手', desc: '出题讲解，随问随答', color: '#3b82f6' },
  { path: '/history', icon: List, title: '考试历史', desc: '回顾每次作答记录', color: '#10b981' },
  { path: '/stats', icon: TrendCharts, title: '学习分析', desc: '趋势、薄弱点、错题集', color: '#8b5cf6' },
]

// 数据速览
const stat = ref({ total: 0, latestAccuracy: null, avgAccuracy: null })
const statLoading = ref(true)
// 薄弱点
const weakPoints = ref([])
const weakLoading = ref(true)

function accuracyOf(row) {
  if (!row || !row.total) return null
  return Math.round(((row.score || 0) / row.total) * 100)
}

async function loadStats() {
  try {
    const [exams, trend] = await Promise.all([
      listExams(1, 1),
      getHistoryTrend(50),
    ])
    const latest = exams.items?.[0]
    const points = trend.points || []
    const avg = points.length
      ? Math.round(points.reduce((s, p) => s + (p.accuracy || 0), 0) / points.length)
      : null
    stat.value = {
      total: exams.total || 0,
      latestAccuracy: accuracyOf(latest),
      avgAccuracy: avg,
    }
  } catch {
    // 首页容错，不弹错误
  } finally {
    statLoading.value = false
  }
}

async function loadWeak() {
  try {
    const data = await getWeakPoints(5)
    weakPoints.value = data.items || []
  } catch {
    // 忽略
  } finally {
    weakLoading.value = false
  }
}

function go(path) {
  router.push(path)
}

// 针对薄弱点一键智能组卷：跳到在线考试并预填 AI 需求
function smartFromWeak() {
  const names = weakPoints.value.slice(0, 3).map((w) => w.point).join('、')
  const req = names
    ? `针对我的薄弱点（${names}）出10道题，帮我查漏补缺`
    : '针对我的薄弱点出10道题，帮我查漏补缺'
  router.push({ path: '/exam', query: { ai: '1', req } })
}

onMounted(() => {
  loadStats()
  loadWeak()
})
</script>

<template>
  <div class="home-wrap">
    <!-- 问候 + 激励 -->
    <section class="hero">
      <div class="hero-text">
        <h1>{{ greeting }}，{{ userName }} 👋</h1>
        <p>{{ motivation }}</p>
      </div>
      <el-button type="primary" size="large" class="hero-cta" @click="go('/exam')">
        开始今天的练习<el-icon class="el-icon--right"><ArrowRight /></el-icon>
      </el-button>
    </section>

    <!-- 数据速览 -->
    <section class="stat-row" v-loading="statLoading">
      <div class="stat-card">
        <div class="stat-num">{{ stat.total }}</div>
        <div class="stat-label">累计考试</div>
      </div>
      <div class="stat-card">
        <div class="stat-num">
          <template v-if="stat.latestAccuracy != null">{{ stat.latestAccuracy }}<small>%</small></template>
          <template v-else>—</template>
        </div>
        <div class="stat-label">最近正确率</div>
      </div>
      <div class="stat-card">
        <div class="stat-num">
          <template v-if="stat.avgAccuracy != null">{{ stat.avgAccuracy }}<small>%</small></template>
          <template v-else>—</template>
        </div>
        <div class="stat-label">平均正确率</div>
      </div>
    </section>

    <!-- 快捷入口 -->
    <section class="actions">
      <div
        v-for="a in ACTIONS"
        :key="a.path"
        class="action-card"
        @click="go(a.path)"
      >
        <div class="action-icon" :style="{ background: a.color }">
          <el-icon><component :is="a.icon" /></el-icon>
        </div>
        <div class="action-body">
          <div class="action-title">{{ a.title }}</div>
          <div class="action-desc">{{ a.desc }}</div>
        </div>
        <el-icon class="action-arrow"><ArrowRight /></el-icon>
      </div>
    </section>

    <!-- 薄弱点速览 -->
    <section class="weak-card" v-loading="weakLoading">
      <div class="weak-head">
        <b>薄弱点速览</b>
        <el-button
          v-if="weakPoints.length"
          type="primary"
          size="small"
          class="weak-btn"
          @click="smartFromWeak"
        >
          <el-icon style="margin-right: 4px"><MagicStick /></el-icon>针对弱项智能组卷
        </el-button>
      </div>
      <div v-if="weakPoints.length" class="weak-list">
        <div v-for="w in weakPoints" :key="w.point" class="weak-item">
          <span class="weak-name">{{ w.point }}</span>
          <div class="weak-bar">
            <div class="weak-bar-fill" :style="{ width: w.error_rate + '%' }"></div>
          </div>
          <span class="weak-rate">错误率 {{ w.error_rate }}%</span>
        </div>
      </div>
      <div v-else-if="!weakLoading" class="weak-empty">
        还没有足够数据分析薄弱点，多做几套题就能看到啦。
      </div>
    </section>
  </div>
</template>

<style scoped>
.home-wrap {
  max-width: 880px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 18px;
}

/* Hero */
.hero {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  background: linear-gradient(120deg, #fff7e6 0%, #fffdf7 100%);
  border: 1px solid #fde68a;
  border-radius: 14px;
  padding: 24px 26px;
}
.hero-text h1 { margin: 0 0 6px; font-size: 24px; color: #422006; }
.hero-text p { margin: 0; color: #92660e; font-size: 14px; }
.hero-cta { --el-button-text-color: #422006; --el-button-hover-text-color: #422006; font-weight: 600; }

/* 数据速览 */
.stat-row { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; }
.stat-card {
  background: #fff;
  border: 1px solid #ebeef5;
  border-radius: 12px;
  padding: 18px;
  text-align: center;
}
.stat-num { font-size: 30px; font-weight: 700; color: #f59e0b; line-height: 1.2; }
.stat-num small { font-size: 15px; margin-left: 1px; }
.stat-label { margin-top: 4px; font-size: 13px; color: #909399; }

/* 快捷入口 */
.actions { display: grid; grid-template-columns: repeat(2, 1fr); gap: 14px; }
.action-card {
  display: flex;
  align-items: center;
  gap: 14px;
  background: #fff;
  border: 1px solid #ebeef5;
  border-radius: 12px;
  padding: 16px 18px;
  cursor: pointer;
  transition: all 0.18s;
}
.action-card:hover {
  border-color: #fbbf24;
  box-shadow: 0 4px 14px rgba(245, 158, 11, 0.15);
  transform: translateY(-2px);
}
.action-icon {
  width: 44px; height: 44px;
  border-radius: 11px;
  display: flex; align-items: center; justify-content: center;
  color: #fff; font-size: 22px;
  flex-shrink: 0;
}
.action-body { flex: 1; min-width: 0; }
.action-title { font-weight: 600; color: #303133; }
.action-desc { font-size: 12px; color: #909399; margin-top: 2px; }
.action-arrow { color: #c0c4cc; }

/* 薄弱点 */
.weak-card {
  background: #fff;
  border: 1px solid #ebeef5;
  border-radius: 12px;
  padding: 18px 20px;
}
.weak-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.weak-btn { --el-button-text-color: #422006; --el-button-hover-text-color: #422006; font-weight: 600; }
.weak-list { display: flex; flex-direction: column; gap: 10px; }
.weak-item { display: flex; align-items: center; gap: 12px; font-size: 13px; }
.weak-name { width: 96px; flex-shrink: 0; color: #303133; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.weak-bar { flex: 1; height: 8px; background: #f0f2f5; border-radius: 4px; overflow: hidden; }
.weak-bar-fill { height: 100%; background: linear-gradient(90deg, #fbbf24, #f56c6c); border-radius: 4px; }
.weak-rate { width: 84px; flex-shrink: 0; text-align: right; color: #909399; }
.weak-empty { color: #c0c4cc; font-size: 13px; text-align: center; padding: 10px 0; }

@media (max-width: 640px) {
  .hero { flex-direction: column; align-items: flex-start; }
  .hero-cta { width: 100%; }
  .actions { grid-template-columns: 1fr; }
  .weak-name { width: 72px; }
  .weak-rate { width: 72px; }
}
</style>
