<template>
  <div class="plan-page">
    <header class="plan-header">
      <a-button @click="$router.back()">← 返回对话</a-button>
      <h2>📅 学习计划管理</h2>
      <a-button type="primary" @click="showCreateModal = true">+ 新建计划</a-button>
    </header>

    <div class="plan-content">
      <!-- 计划列表 -->
      <a-spin :spinning="loading">
        <div v-if="plans.length === 0" class="plan-empty">
          <p>还没有学习计划，点击「新建计划」开始吧！</p>
        </div>

        <div v-for="plan in plans" :key="plan.id" class="plan-card">
          <div class="plan-card__header">
            <h3>{{ plan.title }}</h3>
            <div class="plan-card__actions">
              <a-button size="small" @click="showAddTask(plan.id)">+ 任务</a-button>
              <a-popconfirm title="确认删除？" @confirm="deletePlan(plan.id)">
                <a-button size="small" danger>删除</a-button>
              </a-popconfirm>
            </div>
          </div>
          <p v-if="plan.description" class="plan-card__desc">{{ plan.description }}</p>

          <!-- 进度条 -->
          <a-progress
            :percent="getProgress(plan)"
            :format="() => `${getDoneCount(plan)}/${plan.tasks.length}`"
            size="small"
            style="margin: 8px 0"
          />

          <!-- 任务列表 -->
          <div class="task-list">
            <div
              v-for="task in plan.tasks"
              :key="task.id"
              class="task-item"
              :class="{ 'task-item--done': task.is_done }"
            >
              <a-checkbox
                :checked="task.is_done"
                :disabled="task.is_done"
                @change="markDone(plan.id, task.id)"
              />
              <span class="task-title">{{ task.title }}</span>
              <a-tag v-if="task.subject" size="small" color="blue">{{ task.subject }}</a-tag>
              <span v-if="task.is_done" class="task-done-time">
                ✅ {{ formatDate(task.done_at) }}
              </span>
            </div>
          </div>
        </div>
      </a-spin>
    </div>

    <!-- 新建计划弹窗 -->
    <a-modal v-model:open="showCreateModal" title="新建学习计划" @ok="createPlan" :confirm-loading="submitting">
      <a-form layout="vertical">
        <a-form-item label="计划标题" required>
          <a-input v-model:value="newPlan.title" placeholder="如：408两周冲刺计划" />
        </a-form-item>
        <a-form-item label="描述（可选）">
          <a-textarea v-model:value="newPlan.description" placeholder="计划说明..." :rows="3" />
        </a-form-item>
      </a-form>
    </a-modal>

    <!-- 新增任务弹窗 -->
    <a-modal v-model:open="showTaskModal" title="新增学习任务" @ok="addTask" :confirm-loading="submitting">
      <a-form layout="vertical">
        <a-form-item label="任务名称" required>
          <a-input v-model:value="newTask.title" placeholder="如：复习快速排序" />
        </a-form-item>
        <a-form-item label="科目">
          <a-select v-model:value="newTask.subject" placeholder="选择科目（可选）" allow-clear>
            <a-select-option value="数据结构">数据结构</a-select-option>
            <a-select-option value="操作系统">操作系统</a-select-option>
            <a-select-option value="计算机网络">计算机网络</a-select-option>
            <a-select-option value="计算机组成原理">计算机组成原理</a-select-option>
          </a-select>
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { message } from 'ant-design-vue'
import { http } from '@/utils/http'
import type { PlanResponse } from '@/types'

const plans   = ref<PlanResponse[]>([])
const loading = ref(false)
const submitting = ref(false)

const showCreateModal = ref(false)
const showTaskModal   = ref(false)
const currentPlanId   = ref('')

const newPlan = reactive({ title: '', description: '' })
const newTask = reactive({ title: '', subject: '' })

onMounted(fetchPlans)

async function fetchPlans() {
  loading.value = true
  try {
    const { data } = await http.get<PlanResponse[]>('/api/v1/plan/')
    // 每个计划单独获取详情（含任务列表）
    const details = await Promise.all(
      data.map(p => http.get<PlanResponse>(`/api/v1/plan/${p.id}`).then(r => r.data))
    )
    plans.value = details
  } finally {
    loading.value = false
  }
}

async function createPlan() {
  if (!newPlan.title.trim()) { message.warning('请输入计划标题'); return }
  submitting.value = true
  try {
    await http.post('/api/v1/plan/', { title: newPlan.title, description: newPlan.description || undefined })
    message.success('计划创建成功')
    showCreateModal.value = false
    newPlan.title = ''; newPlan.description = ''
    await fetchPlans()
  } finally { submitting.value = false }
}

async function deletePlan(planId: string) {
  await http.delete(`/api/v1/plan/${planId}`)
  message.success('已删除')
  await fetchPlans()
}

function showAddTask(planId: string) {
  currentPlanId.value = planId
  newTask.title = ''; newTask.subject = ''
  showTaskModal.value = true
}

async function addTask() {
  if (!newTask.title.trim()) { message.warning('请输入任务名称'); return }
  submitting.value = true
  try {
    await http.post(`/api/v1/plan/${currentPlanId.value}/tasks`, {
      title: newTask.title,
      subject: newTask.subject || undefined,
    })
    message.success('任务已添加')
    showTaskModal.value = false
    await fetchPlans()
  } finally { submitting.value = false }
}

async function markDone(planId: string, taskId: string) {
  await http.patch(`/api/v1/plan/${planId}/tasks/${taskId}/done`)
  message.success('已完成 ✅')
  await fetchPlans()
}

function getProgress(plan: PlanResponse) {
  if (!plan.tasks.length) return 0
  return Math.round((plan.tasks.filter(t => t.is_done).length / plan.tasks.length) * 100)
}
function getDoneCount(plan: PlanResponse) { return plan.tasks.filter(t => t.is_done).length }
function formatDate(d: string | null) { return d ? new Date(d).toLocaleDateString() : '' }
</script>

<style scoped>
.plan-page { min-height: 100vh; background: #f0f2f5; }
.plan-header {
  background: white;
  padding: 16px 24px;
  display: flex;
  align-items: center;
  gap: 16px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.06);
  position: sticky;
  top: 0;
  z-index: 10;
}
.plan-header h2 { flex: 1; margin: 0; text-align: center; font-size: 20px; }
.plan-content { max-width: 800px; margin: 24px auto; padding: 0 16px; }
.plan-empty { text-align: center; padding: 60px; color: #999; background: white; border-radius: 12px; }
.plan-card {
  background: white;
  border-radius: 12px;
  padding: 20px;
  margin-bottom: 16px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.06);
}
.plan-card__header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.plan-card__header h3 { margin: 0; font-size: 18px; }
.plan-card__actions { display: flex; gap: 8px; }
.plan-card__desc { color: #666; font-size: 14px; margin-bottom: 8px; }
.task-list { display: flex; flex-direction: column; gap: 8px; margin-top: 12px; }
.task-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  background: #fafafa;
  border-radius: 8px;
  transition: all 0.2s;
}
.task-item--done { opacity: 0.6; }
.task-item--done .task-title { text-decoration: line-through; }
.task-title { flex: 1; font-size: 14px; }
.task-done-time { font-size: 12px; color: #52c41a; }
</style>
