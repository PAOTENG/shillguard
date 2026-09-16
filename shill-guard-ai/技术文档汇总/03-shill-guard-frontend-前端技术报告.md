# shill-guard-frontend（前端）技术报告

> 仓库：`D:\project\shill-guard-frontend`  
> 只读分析，未改代码。  
> `src/` 下约 **48** 个源文件：`.vue` 24 + `.ts` 23 + `.css` 1。

---

## 1. 项目定位与内容概览

Vue 3 SPA：类小红书的社区前台（首页/发帖/评论/关注/私信）+ ShillGuard 管理后台（检测、禁言、举报审核、RBAC、RAG/AI 工具、政策情报）。

| 项 | 值 |
|----|-----|
| 框架 | Vue 3.4 + TypeScript + Vite 5 |
| 路由 | Vue Router 4（WebHistory） |
| 状态 | Pinia |
| UI | Element Plus + Icons |
| HTTP | Axios（`baseURL=/api`） |
| 开发端口 | `3000` |

### 1.1 `src/` 树

```
src/
├── App.vue, main.ts
├── api/          http + 各业务 API
├── components/   ThumbsUp.vue
├── composables/  theme / SSE / download / aiChatFile
├── router/       index.ts
├── store/        user / chat / aiChat
├── styles/       global.css
└── views/        用户页 + admin/ + layout/
```

### 1.2 Vite 代理（`vite.config.ts`）

| 前缀 | 目标 |
|------|------|
| `/api` | `http://localhost:8080`（Java Gateway） |
| `/ws` | `ws://localhost:8080`（私信） |
| `/ai` | `http://localhost:8000`（Python） |
| `/policy-api` | `http://localhost:8001`（政策情报，去前缀） |

注意：部分 AI 调用 **直连** `http://localhost:8000`（如 `aiSearch.ts` / `writer.ts`），不经 `/ai` 代理。

---

## 2. 脚本与依赖（`package.json`）

**Scripts：** `dev`=`vite`；`build`=`vue-tsc && vite build`；`preview`=`vite preview`。

**dependencies：** vue、vue-router、pinia、element-plus、@element-plus/icons-vue、axios、marked、highlight.js。

**devDependencies：** vite、@vitejs/plugin-vue、typescript、vue-tsc、unplugin-auto-import、unplugin-vue-components。

---

## 3. 入口与全局

| 文件 | 符号/内容 | 功能 |
|------|-----------|------|
| `main.ts` | createApp | 注册 Pinia/Router/ElementPlus/icons，`initTheme()`，挂载 `#app` |
| `App.vue` | `<router-view />` | 根壳 |
| `styles/global.css` | CSS 变量 | 明暗主题、主色约 `#FF2442`、全局重置 |

---

## 4. 路由（`router/index.ts`）

| Path | Name | 守卫 | 页面职责 |
|------|------|------|----------|
| `/login` | Login | 公开 | 登录注册 |
| `/` | Home | — | 信息流 |
| `/post/:id` | PostDetail | — | 帖子详情+评论+举报 |
| `/search` | Search | 公开 | 搜帖/人/AI 对话 |
| `/publish` | Publish | requiresAuth | 发图文/视频+AI 续写 |
| `/profile` | Profile | requiresAuth | 个人中心 |
| `/friends` | Friends | requiresAuth | 私信好友列表 |
| `/chat/:id` | Chat | requiresAuth | 一对一聊天 |
| `/user/:id` | UserProfile | 公开 | 他人主页 |
| `/admin` | AdminDashboard | auth+admin | 恶意用户检测台 |
| `/admin/mute` | AdminMute | admin | 禁言管理 |
| `/admin/users` | AdminUsers | admin | 用户管理 |
| `/admin/reports` | AdminReports | admin | 举报审核 |
| `/admin/posts` | AdminPosts | admin | 帖子管理 |
| `/admin/videos` | AdminVideos | admin | 视频管理 |
| `/admin/roles` | AdminRoles | admin | 角色菜单 |
| `/admin/ai-chat` | AdminAiChat | admin | AI 对话测试 |
| `/admin/ai-kb` | AdminAiKb | admin | 知识库 |
| `/admin/ai-tests` | AdminAiTests | admin | 测题生成 |
| `/admin/policy-agent` | AdminPolicyAgent | admin | 政策情报 |

**守卫逻辑：**  
- `requiresAuth`：无 token → `/login`  
- `requiresAdmin`：`role < 2` → `/`  
- 管理员判定与 store 一致：`role >= 2`

---

## 5. API 模块逐文件

### `api/http.ts`
| 导出 | 功能 |
|------|------|
| `http`（default） | Axios：`/api`；Bearer；`code===200` 解包；401 清 token 去登录 |

### `api/auth.ts`
| 导出 | 功能 |
|------|------|
| 类型 `LoginParams/RegisterParams/LoginResult` | 认证类型 |
| `login/register/logout/sendCode/autoLogin` | 对应 `/auth/*` |

### `api/user.ts`
| 导出 | 功能 |
|------|------|
| `getProfile/updateProfile/getUserPosts/getUserList/searchUsers` | 资料与列表 |
| `updateUserStatus/followUser/unfollowUser` | 状态与关注 |
| `getMyFollowings/Followers/getUserProfile/getUserStats/getUserNames` | 社交统计 |
| `useUserNames` | 管理端 ID→昵称缓存 |

### `api/post.ts`
| 导出 | 功能 |
|------|------|
| `getPostList/Detail/createPost/getMyPosts/deletePost` | 帖子 CRUD |
| `likePost/unlikePost` | 帖赞 |
| `getComments/addComment/deleteComment/likeComment/unlikeComment/getReplies` | 评论 |

### `api/interaction.ts`
| 导出 | 功能 |
|------|------|
| 收藏夹 CRUD、`favoritePost/unfavoritePost/getFavoritePosts` | 收藏 |
| `getViewHistory/getLikedPosts` | 历史 |

### `api/file.ts`
| 导出 | 功能 |
|------|------|
| `uploadImage/uploadVideo/uploadChatFile/uploadAvatar` | multipart → Java file 服务 |

### `api/chat.ts`
| 导出 | 功能 |
|------|------|
| 类型 Friend/Message/Sticker | 私信模型 |
| `getFriends/getHistory/sendMessage/sendMediaMessage/markRead/getUnreadCount` | 聊天 REST |
| `getMyStickers/addSticker/deleteSticker` | 表情包 |

### `api/report.ts`
| 导出 | 功能 |
|------|------|
| `submitReport/moderateReport/getCommentDetail/getLatestMute/manualMuteUser/updateReportStatus` | 举报与审核联动 |
| 类型 `ModerateResult` 等 | 展示 AI 结果 |

### `api/admin.ts`
| 导出 | 功能 |
|------|------|
| 帖子 status、用户角色/状态/重置密码 | 管理用户帖子 |
| 角色 CRUD、菜单、`assignRoleMenus` | RBAC |

### `api/agent.ts`
| 导出 | 功能 |
|------|------|
| `triggerDetect/triggerDetectStream` | 批量检测（含 SSE） |
| `getMuteList/manualMute/cancelMute` | 禁言 |
| `getStats` | **已定义，视图中未使用** |

### `api/aiSearch.ts`
| 导出 | 功能 |
|------|------|
| `streamAiSearch` | 直连 `localhost:8000/ai/chat` SSE |

### `api/writer.ts`
| 导出 | 功能 |
|------|------|
| `streamWrite` | 直连 `/ai/write` SSE |

### `api/ragAdmin.ts`
| 导出 | 功能 |
|------|------|
| `getDocList/uploadToKb/deleteDoc/sendChatMessage/generateTests` | 经 `/ai` 代理的 RAG 管理与测题 |

### `api/policyApi.ts`
| 导出 | 功能 |
|------|------|
| `getCategoryTree/listPolicies/generateReport/submitReportFeedback/triggerCrawl` | PolicyRadar `:8001` |

---

## 6. Store（Pinia）

### `store/user.ts` — `useUserStore`
| 成员 | 功能 |
|------|------|
| `userInfo` / `token`（localStorage） | 登录态 |
| `setUser/setToken/clear` | 写入清理 |
| `isLoggedIn` / `isAdmin` | `role>=2` |

### `store/chat.ts` — `useChatStore`
| 成员 | 功能 |
|------|------|
| WS 连接 `/ws/chat?token=` | 全局单例、重连 |
| 注册页面 handler | 收消息分发 |
| send 文本/媒体 | WS 优先，失败 REST |
| 桌面通知 | 后台提示 |

### `store/aiChat.ts` — `useAiChatStore`
| 成员 | 功能 |
|------|------|
| 会话消息/历史 | AI 搜索对话状态 |
| ask/reanswer/拉历史 | 调 Python chat/history API |

---

## 7. Composables

| 文件 | 导出 | 功能 |
|------|------|------|
| `useTheme.ts` | `initTheme/toggleTheme/useTheme` | `html.dark` + localStorage `sg-theme` |
| `useSSE.ts` | `useSSE`→`readSSE` | 解析 `data: {delta}` / `[DONE]` |
| `useDownloadDir.ts` | `useDownloadDir` | File System Access + IndexedDB 下载目录 |
| `useAiChatFile.ts` | `useAiChatFile` | 布局与搜索页共享待传附件 |

---

## 8. 组件与布局

| 文件 | 要点 | 功能 |
|------|------|------|
| `components/ThumbsUp.vue` | SVG | 点赞图标 |
| `layout/MainLayout.vue` | `goAiChat/handleSearch/handleCommand` + WS watch | 用户壳：导航、搜/AI、主题、头像菜单 |
| `layout/AdminLayout.vue` | `navItems/handleLogout` | 管理侧栏 |

---

## 9. 用户侧 Views（函数级要点）

| 文件 | 关键函数/行为 | 职责 |
|------|----------------|------|
| `LoginView.vue` | `handleSubmit/onSendCode/applyLogin/toggleMode` | 登录注册+验证码自动登录 |
| `HomeView.vue` | `loadPosts/selectTopic/toggleFav` | 话题瀑布流 |
| `PostDetailView.vue` | 赞藏评回复举报、AI 续写辅助 | 详情页 |
| `PublishView.vue` | `handleSubmit`、上传、`handleAiWrite` | 发布 |
| `SearchView.vue` | `searchPosts/searchUsersFn/sendAiMessage` | 三 Tab 搜索 |
| `ProfileView.vue` | 改资料头像、多 Tab 内容 | 我的 |
| `UserView.vue` | `loadUser/loadPosts/toggleFollow` | 他人主页 |
| `FriendsView.vue` | `load/goChat` | 好友进聊天 |
| `ChatView.vue` | `load/onSend`、贴纸文件、关注门槛 | 私信 UI |

---

## 10. 管理侧 Views

| 文件 | 关键行为 | 职责 |
|------|----------|------|
| `DashboardView.vue` | `triggerDetect` SSE、`handleEvent`、`loadRecentMutes` | 检测控制台 |
| `MuteManageView.vue` | `loadList/handleUnmute/handleManualMute` | 禁言台账 |
| `UserManageView.vue` | 改角色/状态/封禁/重置密码 | 用户表 |
| `ReportManageView.vue` | AI 审核、忽略、人工通过/禁言、证据下载 | 举报队列 |
| `PostManageView.vue` | 列表删恢复详情 | 帖子治理 |
| `VideoManageView.vue` | 按 postType 筛视频 | 视频治理 |
| `RoleManageView.vue` | 角色 CRUD + 菜单树 | RBAC |
| `AiChatTestView.vue` | `handleSend` + markdown | AI 联调 |
| `KnowledgeBaseView.vue` | 上传列表删 | RAG 文档 |
| `TestCaseGenView.vue` | `handleGenerate` SSE | 测题生成 |
| `PolicyAgentView.vue` | 表单→`generateReport` SSE、反馈评分 | 政策情报 |

---

## 11. 前后端契约假设

1. Java 统一信封：`{ code, message, data }`，成功 `code === 200`。  
2. 鉴权：`Authorization: Bearer <token>`；网关校验后下游信 `X-User-*`。  
3. 超时：检测/审核类请求前端可达 120s–300s（LLM/RAG）。  
4. AI 双通道：社区治理经 Java agent；对话/续写/部分 RAG **直连 Python**。

---

## 12. 本地启动（cmd）

```bat
cd /d d:\project\shill-guard-frontend
npm install
npm run dev
```

浏览器：`http://localhost:3000`。需同时起 Gateway `:8080` 与 Python `:8000`（及依赖中间件）。

---

## 13. 复查检查清单

- [ ] 新增页面是否进 router + 守卫  
- [ ] 直连 `:8000` 是否在部署环境改代理/环境变量（CORS）  
- [ ] `getStats` 死代码是否清理或接 Dashboard  
- [ ] admin 角色阈值与 Java `role` 枚举一致  
- [ ] SSE 事件字段与 Java/Python 流协议一致  
- [ ] PolicyRadar `:8001` 服务是否在本机可用  

本报告为前端仓第一轮全量盘点，可与 `00`/`01`/`02` 交叉核对联调路径。
