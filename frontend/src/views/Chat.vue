<template>
  <div class="chat-page">
    <!-- 顶部导航栏 -->
    <header class="chat-header">
      <div class="chat-header__left">
        <span class="logo">🤖 408 学习助手</span>
      </div>
      <div class="chat-header__center">
        <a-button size="small" @click="quickAction('帮我出一道关于操作系统的练习题')">📝 出题</a-button>
        <a-button size="small" @click="quickAction('我接下来应该复习什么薄弱点')">🔍 推荐复习</a-button>
        <a-button size="small" @click="$router.push('/plan')">📅 学习计划</a-button>
        <a-button size="small" @click="$router.push('/profile')">📊 学习画像</a-button>
        <a-button size="small" @click="$router.push('/knowledge')">📚 知识库</a-button>
      </div>
      <div class="chat-header__right">
        <span class="username">👤 {{ auth.user?.username }}</span>
        <a-button size="small" danger @click="handleLogout">退出</a-button>
      </div>
    </header>

    <!-- 主体：左侧对话 + 右侧面板 -->
    <main class="chat-main">
      <!-- 左侧：消息区 -->
      <div class="chat-messages-wrap">
        <div class="chat-messages" ref="messagesRef">
          <div v-if="chat.messages.length === 0" class="chat-empty">
            <div class="chat-empty__icon">🎓</div>
            <h3>你好！我是 408 学习助手</h3>
            <p>我可以帮你讲解知识点、出题练习、制定复习计划</p>
            <div class="chat-empty__tips">
              <a-tag @click="quickAction('请讲解一下快速排序算法')" style="cursor:pointer">快速排序</a-tag>
              <a-tag @click="quickAction('什么是进程和线程的区别？')" style="cursor:pointer">进程与线程</a-tag>
              <a-tag @click="quickAction('解释 TCP 三次握手')" style="cursor:pointer">TCP三次握手</a-tag>
            </div>
          </div>
          <ChatBubble
            v-for="(msg, i) in chat.messages"
            :key="i"
            :message="msg"
            :isStreaming="chat.streaming && i === chat.messages.length - 1 && msg.role === 'assistant'"
          />
        </div>

        <!-- 输入区 -->
        <div class="chat-input-wrap">
          <a-textarea
            v-model:value="inputText"
            placeholder="输入问题，按 Enter 发送（Shift+Enter 换行）"
            :auto-size="{ minRows: 1, maxRows: 4 }"
            :disabled="chat.loading"
            @keydown.enter.exact.prevent="handleSend"
            class="chat-input"
          />
          <a-button
            v-if="!chat.streaming"
            type="primary"
            size="large"
            :loading="chat.loading"
            :disabled="!inputText.trim()"
            @click="handleSend"
            class="chat-send-btn"
          >
            发送
          </a-button>
          <a-button
            v-else
            danger
            size="large"
            @click="chat.stopStreaming()"
            class="chat-send-btn"
          >
            ⏹ 停止
          </a-button>
        </div>
      </div>

      <!-- 右侧：RAG 可视化面板 -->
      <aside class="chat-sidebar">
        <RAGProcessPanel
          :events="chat.pipelineEvents"
          :isStreaming="chat.streaming"
          :isDone="!chat.streaming && chat.pipelineEvents.length > 0"
        />

        <!-- 会话操作 -->
        <div class="sidebar-actions">
          <a-popconfirm title="确认重置会话？学习记录将保存" @confirm="handleReset">
            <a-button block>🔄 重置会话</a-button>
          </a-popconfirm>
        </div>
      </aside>
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref, nextTick, watch, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { useAuthStore } from '@/stores/auth'
import { useChatStore } from '@/stores/chat'
import ChatBubble from '@/components/ChatBubble.vue'
import RAGProcessPanel from '@/components/RAGProcessPanel.vue'

const router = useRouter()
const auth   = useAuthStore()
const chat   = useChatStore()

const inputText  = ref('')
const messagesRef = ref<HTMLElement>()

onMounted(() => { chat.loadHistory() })

// 消息更新时自动滚动到底部
watch(
  () => chat.messages.length,
  () => nextTick(() => {
    if (messagesRef.value) {
      messagesRef.value.scrollTop = messagesRef.value.scrollHeight
    }
  })
)

// 流式输出内容变化时也自动滚动（messages.length 不变但内容在增长）
watch(
  () => chat.currentStreamContent,
  () => nextTick(() => {
    if (messagesRef.value) {
      messagesRef.value.scrollTop = messagesRef.value.scrollHeight
    }
  })
)

async function handleSend() {
  if (!inputText.value.trim() || chat.loading) return
  const msg = inputText.value.trim()
  inputText.value = ''
  await chat.sendMessage(msg)
}

function quickAction(msg: string) {
  inputText.value = msg
  handleSend()
}

async function handleReset() {
  await chat.resetSession()
  message.success('会话已重置，学习记录已保存')
}

function handleLogout() {
  auth.logout()
  router.push('/login')
}
</script>

<style scoped>
.chat-page { height: 100vh; display: flex; flex-direction: column; background: #f0f2f5; }
.chat-header {
  height: 56px;
  background: white;
  border-bottom: 1px solid #e8e8e8;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 20px;
  flex-shrink: 0;
  box-shadow: 0 2px 8px rgba(0,0,0,0.06);
}
.logo { font-size: 18px; font-weight: 700; color: #1a1a2e; }
.chat-header__center { display: flex; gap: 8px; }
.chat-header__right { display: flex; align-items: center; gap: 12px; }
.username { font-size: 14px; color: #666; }

.chat-main { flex: 1; display: flex; overflow: hidden; padding: 16px; gap: 16px; }

.chat-messages-wrap {
  flex: 1;
  display: flex;
  flex-direction: column;
  background: white;
  border-radius: 12px;
  overflow: hidden;
  box-shadow: 0 2px 8px rgba(0,0,0,0.06);
}
.chat-messages { flex: 1; overflow-y: auto; padding: 20px; }
.chat-empty { text-align: center; padding: 60px 20px; color: #999; }
.chat-empty__icon { font-size: 56px; margin-bottom: 16px; }
.chat-empty h3 { font-size: 20px; color: #333; margin-bottom: 8px; }
.chat-empty__tips { margin-top: 20px; display: flex; gap: 8px; justify-content: center; flex-wrap: wrap; }

.chat-input-wrap {
  display: flex;
  gap: 10px;
  padding: 12px 16px;
  border-top: 1px solid #f0f0f0;
  background: #fafafa;
}
.chat-input { flex: 1; border-radius: 8px; resize: none; }
.chat-send-btn { flex-shrink: 0; height: auto; border-radius: 8px; }

.chat-sidebar { width: 320px; display: flex; flex-direction: column; gap: 12px; flex-shrink: 0; }
.sidebar-actions { }
</style>
