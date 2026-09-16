<template>
  <div class="login-page">
    <!-- 左侧品牌面板 -->
    <div class="brand-panel">
      <div class="brand-content">
        <div class="brand-logo">🛡️ ShillGuard</div>
        <h1 class="brand-title">发现真实<br/>守护社区</h1>
        <p class="brand-desc">基于 AI 智能检测水军评论，让每一条内容都真实可信</p>
        <div class="brand-features">
          <div class="feature-item"><span>🤖</span> AI 智能检测水军群组</div>
          <div class="feature-item"><span>🔒</span> 自动禁言 + 人工审核</div>
          <div class="feature-item"><span>📊</span> 实时数据监控面板</div>
        </div>
      </div>
      <div class="deco-circle c1"></div>
      <div class="deco-circle c2"></div>
      <div class="deco-circle c3"></div>
    </div>

    <!-- 右侧表单面板 -->
    <div class="form-panel">
      <div class="form-container">
        <div class="form-header">
          <h2>{{ isLogin ? '欢迎回来 👋' : '加入我们 🎉' }}</h2>
          <p>{{ isLogin ? '登录账号，探索真实内容' : '注册账号，开始发现' }}</p>
        </div>

        <el-form :model="form" :rules="currentRules" ref="formRef" size="large">
          <el-form-item prop="username">
            <el-input v-model="form.username" :placeholder="isLogin ? '手机号/邮箱/账号登录' : '用户名'" :prefix-icon="User" class="custom-input" />
          </el-form-item>
          <el-form-item prop="nickname" v-if="!isLogin">
            <el-input v-model="form.nickname" placeholder="昵称（选填）" :prefix-icon="EditPen" class="custom-input" />
          </el-form-item>
          <el-form-item prop="password">
            <el-input v-model="form.password" type="password" placeholder="密码" :prefix-icon="Lock" show-password class="custom-input" @keyup.enter="handleSubmit" />
          </el-form-item>

          <!-- 自动登录（仅登录态）：勾选后需输入验证码 -->
          <div class="auto-login-row" v-if="isLogin">
            <el-checkbox v-model="form.autoLogin" size="small">自动登录</el-checkbox>
            <span class="auto-login-hint">勾选后需用手机号或邮箱接收验证码</span>
          </div>

          <!-- 验证码输入（勾选自动登录后出现） -->
          <el-form-item v-if="isLogin && form.autoLogin" prop="code" class="code-row">
            <el-input v-model="form.code" placeholder="请输入 6 位验证码" :prefix-icon="Key" class="custom-input code-input" maxlength="6" />
            <el-button class="send-code-btn" :disabled="countdown > 0 || sendingCode" @click="onSendCode">
              {{ countdown > 0 ? `${countdown}s` : '获取验证码' }}
            </el-button>
          </el-form-item>

          <el-button class="submit-btn" type="primary" :loading="loading" @click="handleSubmit" style="width:100%;height:48px;font-size:16px;border-radius:24px;margin-top:8px">
            {{ isLogin ? '登 录' : '注 册' }}
          </el-button>
        </el-form>

        <div class="form-switch">
          <span>{{ isLogin ? '还没有账号？' : '已有账号？' }}</span>
          <a @click="toggleMode">{{ isLogin ? '立即注册' : '去登录' }}</a>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { User, Lock, EditPen, Key } from '@element-plus/icons-vue'
import { login, register, sendCode, autoLogin } from '@/api/auth'
import { useUserStore } from '@/store/user'

const router = useRouter()
const userStore = useUserStore()
const isLogin = ref(true)
const loading = ref(false)
const formRef = ref()

const form = reactive({
  username: '',
  password: '',
  nickname: '',
  autoLogin: false,
  code: '',
})

// 验证码倒计时
const countdown = ref(0)
const sendingCode = ref(false)
let timer: any = null

function startCountdown() {
  countdown.value = 60
  timer = setInterval(() => {
    countdown.value--
    if (countdown.value <= 0) {
      clearInterval(timer)
      timer = null
    }
  }, 1000)
}
onBeforeUnmount(() => { if (timer) clearInterval(timer) })

const loginRules = {
  username: [{ required: true, message: '请输入手机号/邮箱/账号', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }]
}
const registerRules = {
  username: [{ required: true, min: 3, max: 20, message: '用户名3-20位', trigger: 'blur' }],
  password: [{ required: true, min: 6, message: '密码至少6位', trigger: 'blur' }]
}
const currentRules = computed(() => isLogin.value ? loginRules : registerRules)

function toggleMode() {
  isLogin.value = !isLogin.value
  form.username = ''
  form.password = ''
  form.nickname = ''
  form.autoLogin = false
  form.code = ''
  formRef.value?.clearValidate()
}

async function onSendCode() {
  if (!form.username.trim()) {
    ElMessage.warning('请先输入手机号或邮箱')
    return
  }
  sendingCode.value = true
  try {
    await sendCode(form.username.trim())
    ElMessage.success('验证码已发送，请注意查收')
    startCountdown()
  } catch {
    // 错误由 http 拦截器提示（如账号不支持、格式错误、频率过快）
  } finally {
    sendingCode.value = false
  }
}

function applyLogin(data: any) {
  userStore.setToken(data.token)
  userStore.setUser({
    userId: data.userId,
    username: data.username,
    nickname: data.nickname,
    avatarUrl: data.avatarUrl,
    role: data.role,
  })
}

async function handleSubmit() {
  await formRef.value?.validate()
  loading.value = true
  try {
    if (isLogin.value) {
      if (form.autoLogin) {
        // 自动登录：需验证码
        if (!form.code.trim()) {
          ElMessage.warning('请输入验证码')
          return
        }
        const res: any = await autoLogin({
          identifier: form.username.trim(),
          password: form.password,
          code: form.code.trim(),
        })
        applyLogin(res.data)
        ElMessage.success('登录成功（30 天内自动登录）')
        router.push(res.data.role >= 2 ? '/admin' : '/')
      } else {
        const res: any = await login({ username: form.username.trim(), password: form.password })
        applyLogin(res.data)
        ElMessage.success('登录成功')
        router.push(res.data.role >= 2 ? '/admin' : '/')
      }
    } else {
      await register({ username: form.username, password: form.password, nickname: form.nickname })
      ElMessage.success('注册成功，请登录')
      toggleMode()
    }
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
* { box-sizing: border-box; }
.login-page {
  min-height: 100vh;
  display: flex;
  font-family: -apple-system, BlinkMacSystemFont, 'PingFang SC', 'Helvetica Neue', sans-serif;
}
.brand-panel {
  flex: 1;
  background: linear-gradient(145deg, #FF2442 0%, #ff6b7a 50%, #ff9fa8 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  overflow: hidden;
  min-width: 480px;
}
.brand-content {
  position: relative;
  z-index: 2;
  color: white;
  padding: 60px;
  max-width: 480px;
}
.brand-logo {
  font-size: 22px;
  font-weight: 700;
  letter-spacing: 1px;
  margin-bottom: 40px;
  opacity: 0.95;
}
.brand-title {
  font-size: 52px;
  font-weight: 800;
  line-height: 1.2;
  margin: 0 0 20px;
  letter-spacing: -1px;
}
.brand-desc {
  font-size: 17px;
  opacity: 0.85;
  line-height: 1.7;
  margin: 0 0 40px;
}
.brand-features {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.feature-item {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 15px;
  opacity: 0.9;
  background: rgba(255,255,255,0.15);
  padding: 12px 18px;
  border-radius: 12px;
  backdrop-filter: blur(4px);
}
.deco-circle {
  position: absolute;
  border-radius: 50%;
  background: rgba(255,255,255,0.1);
}
.c1 { width: 400px; height: 400px; bottom: -150px; right: -100px; }
.c2 { width: 250px; height: 250px; top: -80px; right: 80px; }
.c3 { width: 150px; height: 150px; top: 30%; left: -50px; background: rgba(255,255,255,0.06); }

.form-panel {
  width: 480px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #fff;
  padding: 40px;
}
.form-container {
  width: 100%;
  max-width: 360px;
}
.form-header {
  margin-bottom: 36px;
}
.form-header h2 {
  font-size: 28px;
  font-weight: 700;
  color: #1a1a1a;
  margin: 0 0 8px;
}
.form-header p {
  color: #888;
  font-size: 15px;
  margin: 0;
}
:deep(.custom-input .el-input__wrapper) {
  border-radius: 12px;
  padding: 4px 16px;
  box-shadow: none;
  border: 1.5px solid #ebebeb;
  transition: border-color 0.2s;
}
:deep(.custom-input .el-input__wrapper:hover),
:deep(.custom-input .el-input__wrapper.is-focus) {
  border-color: #FF2442;
  box-shadow: 0 0 0 3px rgba(255,36,66,0.08);
}
:deep(.el-form-item) { margin-bottom: 18px; }
.submit-btn { background: #FF2442 !important; border-color: #FF2442 !important; }
.submit-btn:hover { background: #e01f3a !important; border-color: #e01f3a !important; transform: translateY(-1px); box-shadow: 0 4px 16px rgba(255,36,66,0.3); }

.auto-login-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: -4px 0 14px;
}
.auto-login-hint {
  font-size: 12px;
  color: #aaa;
}

/* 验证码行 */
.code-row :deep(.el-form-item__content) { display: flex; gap: 10px; }
.code-input { flex: 1; }
.send-code-btn {
  flex-shrink: 0;
  width: 120px;
  border-radius: 12px !important;
  border: 1.5px solid #FF2442 !important;
  color: #FF2442 !important;
  background: #fff !important;
}
.send-code-btn:not(:disabled):hover { background: #fff5f6 !important; }
.send-code-btn:disabled { border-color: #ddd !important; color: #999 !important; cursor: not-allowed; }

.form-switch {
  text-align: center;
  margin-top: 24px;
  color: #888;
  font-size: 14px;
}
.form-switch a {
  color: #FF2442;
  cursor: pointer;
  font-weight: 600;
  margin-left: 4px;
}
.form-switch a:hover { text-decoration: underline; }
</style>
