
<template>
  <div class="knowledge-page">
    <header class="knowledge-header">
      <a-button @click="$router.back()">← 返回对话</a-button>
      <h2>📚 知识库管理</h2>
      <a-button type="primary" @click="showCreateModal = true">+ 新建知识库</a-button>
    </header>

    <div class="knowledge-content">
      <a-spin :spinning="loading">
        <a-empty v-if="knowledgeBases.length === 0 && !loading" description="还没有知识库，点击「新建知识库」开始吧！" />

        <div v-for="kb in knowledgeBases" :key="kb.id" class="kb-card">
          <div class="kb-card__header">
            <div class="kb-card__info">
              <h3>{{ kb.name }}</h3>
              <a-tag color="blue">{{ kb.doc_count }} 篇文档</a-tag>
            </div>
            <div class="kb-card__actions">
              <a-button size="small" @click="openUploadModal(kb.id)">📤 上传文档</a-button>
              <a-button size="small" @click="toggleDocs(kb.id)">
                {{ expandedKbId === kb.id ? '收起' : '查看文档' }}
              </a-button>
              <a-popconfirm title="确认删除该知识库？所有文档将一并删除。" @confirm="deleteKb(kb.id)">
                <a-button size="small" danger>删除</a-button>
              </a-popconfirm>
            </div>
          </div>
          <p v-if="kb.description" class="kb-card__desc">{{ kb.description }}</p>
          <div class="kb-card__meta">
            <span>创建于 {{ formatDate(kb.created_at) }}</span>
            <span>更新于 {{ formatDate(kb.updated_at) }}</span>
          </div>

          <!-- 展开的文档列表 -->
          <div v-if="expandedKbId === kb.id" class="doc-list">
            <a-spin :spinning="docsLoading">
              <a-empty v-if="docs.length === 0 && !docsLoading" description="暂无文档，点击上传添加" />
              <div v-for="doc in docs" :key="doc.id" class="doc-item">
                <div class="doc-item__info">
                  <span class="doc-item__name">📄 {{ doc.filename }}</span>
                  <a-tag :color="statusColor(doc.status)" size="small">{{ statusLabel(doc.status) }}</a-tag>
                  <span class="doc-item__meta">
                    {{ doc.chunk_count }} 分块
                    <template v-if="doc.file_size"> · {{ formatSize(doc.file_size) }}</template>
                  </span>
                </div>
                <a-popconfirm title="确认删除该文档？" @confirm="deleteDoc(kb.id, doc.id)">
                  <a-button size="small" danger>删除</a-button>
                </a-popconfirm>
              </div>
            </a-spin>
          </div>
        </div>
      </a-spin>
    </div>

    <!-- 新建知识库弹窗 -->
    <a-modal v-model:open="showCreateModal" title="新建知识库" @ok="createKb" :confirm-loading="submitting">
      <a-form layout="vertical">
        <a-form-item label="知识库名称" required>
          <a-input v-model:value="newKb.name" placeholder="如：408考研资料库" />
        </a-form-item>
        <a-form-item label="描述（可选）">
          <a-textarea v-model:value="newKb.description" placeholder="知识库说明..." :rows="3" />
        </a-form-item>
      </a-form>
    </a-modal>

    <!-- 上传文档弹窗 -->
    <a-modal
      v-model:open="showUploadModal"
      title="上传文档"
      :footer="null"
      @cancel="onUploadModalClose"
    >
      <a-upload-dragger
        :multiple="true"
        :accept="'.pdf,.txt'"
        :custom-request="handleUpload"
        :file-list="uploadFileList"
        @change="onUploadChange"
      >
        <p class="ant-upload-drag-icon">📁</p>
        <p class="ant-upload-text">点击或拖拽文件到此区域上传</p>
        <p class="ant-upload-hint">支持 PDF、TXT 格式文件</p>
      </a-upload-dragger>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { message } from 'ant-design-vue'
import type { UploadChangeParam, UploadFile } from 'ant-design-vue'
import { http } from '@/utils/http'
import type { KnowledgeBaseResponse, KnowledgeDocResponse } from '@/types'

const knowledgeBases = ref<KnowledgeBaseResponse[]>([])
const docs = ref<KnowledgeDocResponse[]>([])
const loading = ref(false)
const docsLoading = ref(false)
const submitting = ref(false)

const showCreateModal = ref(false)
const showUploadModal = ref(false)
const expandedKbId = ref<string | null>(null)
const uploadKbId = ref('')
const uploadFileList = ref<UploadFile[]>([])

const newKb = reactive({ name: '', description: '' })

onMounted(fetchKnowledgeBases)

async function fetchKnowledgeBases() {
  loading.value = true
  try {
    const { data } = await http.get<KnowledgeBaseResponse[]>('/api/v1/knowledge/')
    knowledgeBases.value = data
  } catch (e: any) {
    message.error('获取知识库列表失败')
  } finally {
    loading.value = false
  }
}

async function createKb() {
  if (!newKb.name.trim()) { message.warning('请输入知识库名称'); return }
  submitting.value = true
  try {
    await http.post('/api/v1/knowledge/', {
      name: newKb.name,
      description: newKb.description || undefined,
    })
    message.success('知识库创建成功')
    showCreateModal.value = false
    newKb.name = ''
    newKb.description = ''
    await fetchKnowledgeBases()
  } catch (e: any) {
    message.error('创建失败：' + (e.response?.data?.detail || e.message))
  } finally {
    submitting.value = false
  }
}

async function deleteKb(kbId: string) {
  try {
    await http.delete(`/api/v1/knowledge/${kbId}`)
    message.success('知识库已删除')
    if (expandedKbId.value === kbId) {
      expandedKbId.value = null
      docs.value = []
    }
    await fetchKnowledgeBases()
  } catch (e: any) {
    message.error('删除失败')
  }
}

async function fetchDocs(kbId: string) {
  docsLoading.value = true
  try {
    const { data } = await http.get<KnowledgeDocResponse[]>(`/api/v1/knowledge/${kbId}/docs`)
    docs.value = data
  } catch (e: any) {
    message.error('获取文档列表失败')
    docs.value = []
  } finally {
    docsLoading.value = false
  }
}

async function toggleDocs(kbId: string) {
  if (expandedKbId.value === kbId) {
    expandedKbId.value = null
    docs.value = []
  } else {
    expandedKbId.value = kbId
    await fetchDocs(kbId)
  }
}

function openUploadModal(kbId: string) {
  uploadKbId.value = kbId
  uploadFileList.value = []
  showUploadModal.value = true
}

function onUploadModalClose() {
  uploadFileList.value = []
  // 上传完成后刷新列表
  fetchKnowledgeBases()
  if (expandedKbId.value) {
    fetchDocs(expandedKbId.value)
  }
}

function handleUpload(options: any) {
  const { file, onSuccess, onError, onProgress } = options
  const formData = new FormData()
  formData.append('file', file)

  http.post(`/api/v1/knowledge/${uploadKbId.value}/docs/upload`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    onUploadProgress: (e: any) => {
      if (e.total) {
        onProgress({ percent: Math.round((e.loaded / e.total) * 100) })
      }
    },
  })
    .then((res) => {
      onSuccess(res.data)
      message.success(`${file.name} 上传成功`)
    })
    .catch((err) => {
      onError(err)
      message.error(`${file.name} 上传失败`)
    })
}

function onUploadChange(info: UploadChangeParam) {
  uploadFileList.value = info.fileList
}

async function deleteDoc(kbId: string, docId: string) {
  try {
    await http.delete(`/api/v1/knowledge/${kbId}/docs/${docId}`)
    message.success('文档已删除')
    await fetchDocs(kbId)
    await fetchKnowledgeBases()
  } catch (e: any) {
    message.error('删除失败')
  }
}

function statusColor(status: string) {
  const map: Record<string, string> = {
    indexed: 'green',
    indexing: 'blue',
    failed: 'red',
    pending: 'default',
  }
  return map[status] || 'default'
}

function statusLabel(status: string) {
  const map: Record<string, string> = {
    indexed: '已索引',
    indexing: '索引中',
    failed: '失败',
    pending: '待处理',
  }
  return map[status] || status
}

function formatDate(d: string) {
  return d ? new Date(d).toLocaleDateString() : ''
}

function formatSize(bytes: number) {
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
}
</script>

<style scoped>
.knowledge-page { min-height: 100vh; background: #f0f2f5; }

.knowledge-header {
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
.knowledge-header h2 { flex: 1; margin: 0; text-align: center; font-size: 20px; }

.knowledge-content { max-width: 800px; margin: 24px auto; padding: 0 16px; }

.kb-card {
  background: white;
  border-radius: 12px;
  padding: 20px;
  margin-bottom: 16px;
  box-shadow: 0 2px 8px rgba(0,0,0,0.06);
}

.kb-card__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.kb-card__info {
  display: flex;
  align-items: center;
  gap: 10px;
}
.kb-card__info h3 { margin: 0; font-size: 18px; }

.kb-card__actions { display: flex; gap: 8px; }

.kb-card__desc { color: #666; font-size: 14px; margin-bottom: 8px; }

.kb-card__meta {
  display: flex;
  gap: 16px;
  font-size: 12px;
  color: #999;
  margin-top: 4px;
}

.doc-list {
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid #f0f0f0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.doc-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px;
  background: #fafafa;
  border-radius: 8px;
  transition: all 0.2s;
}
.doc-item:hover { background: #f5f5f5; }

.doc-item__info {
  display: flex;
  align-items: center;
  gap: 10px;
  flex: 1;
  min-width: 0;
}

.doc-item__name {
  font-size: 14px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.doc-item__meta {
  font-size: 12px;
  color: #999;
  white-space: nowrap;
}
</style>
