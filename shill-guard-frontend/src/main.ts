import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
// Element Plus 官方深色主题变量（html.dark 时生效）
import 'element-plus/theme-chalk/dark/css-vars.css'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'
import '@/styles/global.css'
import App from './App.vue'
import router from './router'
import { initTheme } from '@/composables/useTheme'

const app = createApp(App)

for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component)
}

app.use(createPinia())
app.use(router)
app.use(ElementPlus)
// 在挂载前应用主题，避免闪屏
initTheme()
app.mount('#app')
