
<template>
  <div class="profile-page">
    <header class="profile-header">
      <a-button @click="$router.back()">← 返回对话</a-button>
      <h2>📊 学习画像</h2>
      <a-button @click="refreshProfile" :loading="loading">刷新数据</a-button>
    </header>

    <div class="profile-content">
      <a-spin :spinning="loading">
        <!-- 个人信息卡片 -->
        <div class="profile-card">
          <h3>👤 个人信息</h3>
          <div class="info-grid">
            <div class="info-item">
              <span class="info-label">用户名</span>
              <span class="info-value">{{ profileData.user.username }}</span>
            </div>
            <div class="info-item">
              <span class="info-label">注册时间</span>
              <span class="info-value">{{ formatDate(profileData.user.created_at) }}</span>
            </div>
            <div class="info-item">
              <span class="info-label">总会话数</span>
              <span class="info-value">{{ profileData.user.total_sessions }}</span>
            </div>
            <div class="info-item">
              <span class="info-label">最后活跃</span>
              <span class="info-value">{{ formatDate(profileData.user.last_active_at) }}</span>
            </div>
          </div>
          <div class="learning-style" v-if="profileData.learning_style">
            <span class="info-label">学习风格：</span>
            <a-tag color="purple">{{ profileData.learning_style }}</a-tag>
          </div>
        </div>

        <!-- 知识掌握概览 -->
        <div class="profile-card">
          <h3>📚 知识掌握概览</h3>
          <div class="progress-grid">
            <div
              v-for="(subject, name) in profileData.knowledge_graph"
              :key="name"
              class="progress-item"
            >
              <a-progress
                type="circle"
                :percent="getSubjectPercent(subject)"
                :size="100"
                :stroke-color="getSubjectColor(name as string)"
              >
                <template #format="{ percent }">
                  <span class="progress-text">{{ percent }}%</span>
                </template>
              </a-progress>
              <div class="progress-label">{{ name }}</div>
              <div class="progress-detail">
                <a-tag color="green" size="small">掌握 {{ subject.mastered.length }}</a-tag>
                <a-tag color="red" size="small">薄弱 {{ subject.struggling.length }}</a-tag>
                <a-tag color="blue" size="small">了解 {{ subject.introduced.length }}</a-tag>
              </div>
            </div>
          </div>
        </div>

        <!-- 知识图谱标签云 -->
        <div class="profile-card">
          <h3>🧠 知识图谱</h3>
          <div v-for="(subject, name) in profileData.knowledge_graph" :key="'tag-' + name" class="tag-section">
            <h4>{{ name }}</h4>
            <div class="tag-cloud">
              <a-tag v-for="k in subject.mastered" :key="'m-' + k" color="success">✅ {{ k }}</a-tag>
              <a-tag v-for="k in subject.struggling" :key="'s-' + k" color="error">⚠️ {{ k }}</a-tag>
              <a-tag v-for="k in subject.introduced" :key="'i-' + k" color="processing">💡 {{ k }}</a-tag>
              <span
                v-if="!subject.mastered.length && !subject.struggling.length && !subject.introduced.length"
                class="no-data"
              >暂无数据</span>
            </div>
          </div>
        </div>

        <!-- 学习模式与踩坑记录 -->
        <div class="profile-card">
          <h3>💡 学习模式与踩坑记录</h3>
          <div class="patterns-pitfalls">
            <div class="pp-section">
              <h4>✅ 学习模式 (Patterns)</h4>
              <div v-if="profileData.patterns.length === 0" class="no-data">暂无记录</div>
              <div
                v-for="(p, i) in profileData.patterns"
                :key="'pattern-' + i"
                class="pp-card pp-card--pattern"
              >
                <div class="pp-card__content">{{ p.content }}</div>
                <a-tag v-if="p.subject" color="green" size="small">{{ p.subject }}</a-tag>
              </div>
            </div>
            <div class="pp-section">
              <h4>⚠️ 踩坑记录 (Pitfalls)</h4>
              <div v-if="profileData.pitfalls.length === 0" class="no-data">暂无记录</div>
              <div
                v-for="(p, i) in profileData.pitfalls"
                :key="'pitfall-' + i"
                class="pp-card pp-card--pitfall"
              >
                <div class="pp-card__content">{{ p.content }}</div>
                <a-tag v-if="p.subject" color="orange" size="small">{{ p.subject }}</a-tag>
              </div>
            </div>
          </div>
        </div>

        <!-- 学习统计 -->
        <div class="profile-card">
          <h3>📈 学习统计</h3>
          <div class="stats-grid">
            <div class="stat-item">
              <div class="stat-number">{{ profileData.stats.study_count }}</div>
              <div class="stat-label">累计学习次数</div>
            </div>
            <div class="stat-item">
              <div class="stat-number stat-number--warn">{{ profileData.stats.weak_points }}</div>
              <div class="stat-label">薄弱点数量</div>
            </div>
            <div class="stat-item">
              <div class="stat-number stat-number--success">{{ profileData.stats.corrections }}</div>
              <div class="stat-label">已纠正数量</div>
            </div>
          </div>
        </div>
      </a-spin>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { message } from 'ant-design-vue'
import { http } from '@/utils/http'

// ---------- 类型定义 ----------
interface SubjectKnowledge {
  mastered: string[]
  struggling: string[]
  introduced: string[]
}

interface PatternItem {
  content: string
  subject: string
}

interface ProfileUser {
  username: string
  created_at?: string
  total_sessions: number
  last_active_at?: string
}

interface ProfileStats {
  study_count: number
  weak_points: number
  corrections: number
}

interface ProfileData {
  user: ProfileUser
  knowledge_graph: Record<string, SubjectKnowledge>
  learning_style: string
  patterns: PatternItem[]
  pitfalls: PatternItem[]
  stats: ProfileStats
}

// ---------- Mock 数据 ----------
const mockData: ProfileData = {
  user: {
    username: '学习者',
    created_at: new Date().toISOString(),
    total_sessions: 15,
    last_active_at: new Date().toISOString(),
  },
  knowledge_graph: {
    '数据结构': {
      mastered: ['快速排序', '二叉树', '链表', '栈与队列'],
      struggling: ['图算法', '红黑树'],
      introduced: ['B+树', '跳表'],
    },
    '操作系统': {
      mastered: ['进程管理', '虚拟内存'],
      struggling: ['死锁', '磁盘调度'],
      introduced: ['信号量', '文件系统'],
    },
    '计算机网络': {
      mastered: ['TCP三次握手', 'HTTP协议'],
      struggling: ['拥塞控制'],
      introduced: ['DNS解析', 'HTTPS原理'],
    },
    '计算机组成原理': {
      mastered: ['补码运算'],
      struggling: ['流水线冲突', 'Cache映射'],
      introduced: ['总线仲裁', '中断系统'],
    },
  },
  learning_style: '理论+实践结合',
  patterns: [
    { content: '善于通过类比理解抽象概念，如用生活场景类比操作系统调度', subject: '操作系统' },
    { content: '习惯先理解原理再做题巩固，对算法类知识掌握较快', subject: '数据结构' },
    { content: '喜欢画图辅助理解网络协议的交互过程', subject: '计算机网络' },
  ],
  pitfalls: [
    { content: '容易混淆进程和线程的区别，尤其在资源共享方面', subject: '操作系统' },
    { content: '对图的邻接矩阵和邻接表存储方式理解不够深入', subject: '数据结构' },
    { content: '总是记混 TCP 和 UDP 的具体区别细节', subject: '计算机网络' },
    { content: '补码运算中的溢出判断经常出错', subject: '计算机组成原理' },
  ],
  stats: {
    study_count: 42,
    weak_points: 5,
    corrections: 12,
  },
}

// ---------- 状态 ----------
const loading = ref(false)
const profileData = reactive<ProfileData>(JSON.parse(JSON.stringify(mockData)))

// ---------- 科目配色 ----------
const subjectColors: Record<string, string> = {
  '数据结构': '#1890ff',
  '操作系统': '#52c41a',
  '计算机网络': '#faad14',
  '计算机组成原理': '#722ed1',
}

// ---------- 方法 ----------
function getSubjectPercent(subject: SubjectKnowledge): number {
  const total = subject.mastered.length + subject.struggling.length + subject.introduced.length
  if (total === 0) return 0
  return Math.round((subject.mastered.length / total) * 100)
}

function getSubjectColor(name: string): string {
  return subjectColors[name] || '#1890ff'
}

function formatDate(d?: string): string {
  if (!d) return '—'
  return new Date(d).toLocaleDateString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

async function fetchProfile() {
  loading.value = true
  try {
    const { data } = await http.get<ProfileData>('/api/v1/profile/')
    Object.assign(profileData, data)
    message.success('画像数据已更新')
  } catch {
    // API 不可用时使用 mock 数据优雅降级
    Object.assign(profileData, JSON.parse(JSON.stringify(mockData)))
    message.info('使用示例数据展示（后端画像接口暂未就绪）')
  } finally {
    loading.value = false
  }
}

async function refreshProfile() {
  await fetchProfile()
}

onMounted(() => {
  fetchProfile()
})
</script>

<style scoped>
.profile-page { min-height: 100vh; background: #f0f2f5; }

.profile-header {
  background: white;
  padding: 16px 24px;
  display: flex;
  align-items: center;
  gap: 16px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
  position: sticky;
  top: 0;
  z-index: 10;
}
.profile-header h2 { flex: 1; margin: 0; text-align: center; font-size: 20px; }

.profile-content { max-width: 960px; margin: 24px auto; padding: 0 16px; }

.profile-card {
  background: white;
  border-radius: 12px;
  padding: 24px;
  margin-bottom: 16px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}
.profile-card h3 { margin: 0 0 16px; font-size: 18px; }

/* 个人信息 */
.info-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 16px;
  margin-bottom: 12px;
}
.info-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 12px;
  background: #fafafa;
  border-radius: 8px;
}
.info-label { font-size: 12px; color: #999; }
.info-value { font-size: 16px; font-weight: 600; color: #333; }
.learning-style { display: flex; align-items: center; gap: 8px; margin-top: 8px; }

/* 知识掌握环形进度 */
.progress-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 24px;
  justify-items: center;
}
.progress-item { text-align: center; }
.progress-text { font-size: 14px; font-weight: 700; }
.progress-label { margin-top: 8px; font-size: 15px; font-weight: 600; color: #333; }
.progress-detail { margin-top: 8px; display: flex; flex-wrap: wrap; gap: 4px; justify-content: center; }

/* 知识图谱标签云 */
.tag-section { margin-bottom: 16px; }
.tag-section:last-child { margin-bottom: 0; }
.tag-section h4 { margin: 0 0 8px; font-size: 15px; color: #555; }
.tag-cloud { display: flex; flex-wrap: wrap; gap: 8px; }

/* 学习模式 / 踩坑记录 */
.patterns-pitfalls { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; }
@media (max-width: 640px) { .patterns-pitfalls { grid-template-columns: 1fr; } }
.pp-section h4 { margin: 0 0 12px; font-size: 15px; }
.pp-card {
  padding: 12px 16px;
  border-radius: 8px;
  margin-bottom: 10px;
  display: flex;
  align-items: flex-start;
  gap: 10px;
  justify-content: space-between;
}
.pp-card--pattern { background: #f6ffed; border-left: 3px solid #52c41a; }
.pp-card--pitfall { background: #fff7e6; border-left: 3px solid #faad14; }
.pp-card__content { flex: 1; font-size: 14px; color: #333; line-height: 1.6; }

/* 学习统计 */
.stats-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
  text-align: center;
}
.stat-item {
  padding: 20px;
  background: #fafafa;
  border-radius: 8px;
}
.stat-number { font-size: 32px; font-weight: 700; color: #1890ff; }
.stat-number--warn { color: #faad14; }
.stat-number--success { color: #52c41a; }
.stat-label { font-size: 14px; color: #666; margin-top: 8px; }

.no-data { color: #999; font-size: 14px; padding: 8px 0; }
</style>
