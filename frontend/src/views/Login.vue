<template>
  <div class="login-container">
    <div class="login-card">
      <!-- Logo 区域 -->
      <div class="login-header">
        <div class="logo">🤖</div>
        <h1 class="title">408 学习助手</h1>
        <p class="subtitle">LangGraph 驱动的 AI 备考系统</p>
      </div>

      <!-- Tab 切换：登录 / 注册 -->
      <a-tabs v-model:activeKey="activeTab" centered>
        <!-- 登录 Tab -->
        <a-tab-pane key="login" tab="登录">
          <a-form
            :model="loginForm"
            @finish="handleLogin"
            layout="vertical"
          >
            <a-form-item name="username" :rules="[{ required: true, message: '请输入用户名' }]">
              <a-input
                v-model:value="loginForm.username"
                placeholder="用户名"
                size="large"
                prefix="👤"
              />
            </a-form-item>
            <a-form-item name="password" :rules="[{ required: true, message: '请输入密码' }]">
              <a-input-password
                v-model:value="loginForm.password"
                placeholder="密码"
                size="large"
                prefix="🔒"
              />
            </a-form-item>
            <a-button
              type="primary"
              html-type="submit"
              size="large"
              block
              :loading="loading"
            >
              登录
            </a-button>
          </a-form>
        </a-tab-pane>

        <!-- 注册 Tab -->
        <a-tab-pane key="register" tab="注册">
          <a-form
            :model="registerForm"
            @finish="handleRegister"
            layout="vertical"
          >
            <a-form-item name="username" :rules="[{ required: true, min: 3, message: '用户名至少3个字符' }]">
              <a-input v-model:value="registerForm.username" placeholder="用户名（至少3位）" size="large" prefix="👤" />
            </a-form-item>
            <a-form-item name="password" :rules="[{ required: true, min: 6, message: '密码至少6位' }]">
              <a-input-password v-model:value="registerForm.password" placeholder="密码（至少6位）" size="large" prefix="🔒" />
            </a-form-item>
            <a-form-item name="email">
              <a-input v-model:value="registerForm.email" placeholder="邮箱（可选）" size="large" prefix="📧" />
            </a-form-item>
            <a-button type="primary" html-type="submit" size="large" block :loading="loading">
              注册并登录
            </a-button>
          </a-form>
        </a-tab-pane>
      </a-tabs>

      <!-- 错误提示 -->
      <a-alert v-if="error" :message="error" type="error" show-icon class="error-alert" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const auth   = useAuthStore()

const activeTab = ref('login')
const loading   = ref(false)
const error     = ref('')

const loginForm    = reactive({ username: '', password: '' })
const registerForm = reactive({ username: '', password: '', email: '' })

async function handleLogin() {
  loading.value = true
  error.value   = ''
  try {
    await auth.login(loginForm.username, loginForm.password)
    message.success('登录成功！')
    router.push('/')
  } catch (e: unknown) {
    const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
    error.value = msg || '登录失败，请检查用户名和密码'
  } finally {
    loading.value = false
  }
}

async function handleRegister() {
  loading.value = true
  error.value   = ''
  try {
    await auth.register(registerForm.username, registerForm.password, registerForm.email || undefined)
    message.success('注册成功！')
    router.push('/')
  } catch (e: unknown) {
    const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
    error.value = msg || '注册失败，请稍后重试'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-container {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
}
.login-card {
  width: 400px;
  background: white;
  border-radius: 16px;
  padding: 40px 36px;
  box-shadow: 0 20px 60px rgba(0,0,0,0.2);
}
.login-header { text-align: center; margin-bottom: 32px; }
.logo { font-size: 48px; margin-bottom: 12px; }
.title { font-size: 24px; font-weight: 700; color: #1a1a2e; margin-bottom: 6px; }
.subtitle { color: #666; font-size: 14px; }
.error-alert { margin-top: 16px; }
</style>
