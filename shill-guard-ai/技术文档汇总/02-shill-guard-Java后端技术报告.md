# shill-guard（Java 后端）技术报告

> 仓库：`D:\project\shill-guard`  
> 只读分析，未改代码。  
> **Maven 模块：9**；**`.java` 源文件合计：143**（不含 `target/`）。

---

## 1. 项目定位与内容概览

Spring Cloud 微服务后端：网关鉴权、用户与内容社区、举报与 AI 编排、通知、文件、管理后台。通过 **RestTemplate** 调用 Python Agent（`http://localhost:8000`）。

| 模块 | 端口 | 职责 | `.java` 约数 |
|------|------|------|-------------|
| shill-common | 库 | 实体、Result、JWT、MyBatis 配置、全局异常 | 21 |
| shill-gateway | 8080 | 路由、JWT 全局过滤器、CORS | 2 |
| shill-auth | 9001 | 注册登录验证码、JWT+Redis、默认头像 MinIO | 17 |
| shill-user | 9002 | 资料/关注/禁言辅助、私信 REST+WebSocket | 23 |
| shill-content | 9003 | 帖子评论点赞收藏历史举报；浏览量 MQ；敏感词 | 33 |
| shill-agent | 9004 | AI 审核/检测编排、禁言与风险记录、MQ | 25 |
| shill-notify | 9005 | 站内信 + MQ 消费 | 6 |
| shill-file | 9006 | MinIO 上传 | 3 |
| shill-admin | 9010 | 帖子/用户/角色菜单 RBAC | 13 |

**无独立 appeal（申诉）模块**（库表 status/文案有痕迹）。

父 POM：`com.shillguard:shill-guard:1.0.0`，Boot **3.2.5**，Cloud **2023.0.1**，Java **17**。

---

## 2. 技术栈（POM）

| 类别 | 技术 |
|------|------|
| 网关 | spring-cloud-starter-gateway |
| 注册配置 | Nacos Discovery（常见 `192.168.150.101:8848`） |
| ORM | MyBatis-Plus 3.5.7 + MySQL |
| 安全 | Spring Security（auth）、jjwt 0.12.5、BCrypt |
| 缓存 | Redis（token/OTP/帖子缓存/评论点赞 Set） |
| MQ | RabbitMQ Topic `shillguard.exchange` |
| 对象存储 | MinIO 8.5.9 |
| 文档 | Knife4j OpenAPI3 |
| 其它 | Hutool、Lombok、WebSocket、邮件、阿里云短信 |

OpenFeign 在 agent 声明/启用，**无 `@FeignClient` 实现**，AI 全 RestTemplate。

---

## 3. 网关路由（`shill-gateway`）

| 前缀 | 目标服务 |
|------|----------|
| `/api/auth/**` | auth |
| `/api/user/**`、`/api/chat/**`、`/ws/**` | user |
| `/api/content/**` | content |
| `/api/agent/**` | agent |
| `/api/admin/**` | admin |
| `/api/notify/**` | notify |
| `/api/file/**` | file |

### `AuthGlobalFilter`
| 方法 | 功能 |
|------|------|
| `filter` | 白名单放行；公开 GET 可选 JWT；其余强制 JWT；注入 `X-User-Id/Username/Role` |
| `extractToken` / `injectUserHeaders` / `writeErrorResponse` / `getOrder` | 辅助（order=-100） |

---

## 4. shill-common（21）

### 4.1 基础设施
| 文件 | 类/方法 | 功能 |
|------|---------|------|
| `MybatisPlusConfig` | `mybatisPlusInterceptor`；`AutoFillHandler` | 分页；自动填 created/updated |
| `Result` | `success/fail/isSuccess` | 统一响应 `{code,message,data}` |
| `ResultCode` | 枚举 | 业务错误码 |
| `BizException` | — | 带 code 业务异常 |
| `GlobalExceptionHandler` | 各 `@ExceptionHandler` | → Result |
| `JwtUtils` | `generateToken/parseToken/getUserId/Username/Role/isTokenValid` | HS256，默认约 7 天 |

### 4.2 实体 ↔ 表

| 实体 | 表 | 字段摘要 |
|------|-----|----------|
| `SysUser` | `sys_user` | 账号资料、role、status、warningLevel、关注赞藏计数、IP、时间 |
| `ContentPost` | `content_post` | 帖子正文媒体、状态、浏览赞评计数 |
| `ContentComment` | `content_comment` | 评论树、赞回计数、status、isTop、IP |
| `ContentReport` | `content_report` | 举报双方、对象、类目、审核状态 |
| `AgentMuteRecord` | `agent_mute_record` | 禁言证据、天数、起止、status |
| `SysNotification` | `sys_notification` | 站内信类型/已读 |
| `SysRole` / `SysMenu` / `SysRoleMenu` | RBAC 三表 | 角色菜单 |
| `ContentLike` | `content_like` | 赞目标类型 0评1帖 |
| `UserFollow` | `user_follow` | 关注 |
| `UserFavorite` / `UserFavoriteFolder` | 收藏 | |
| `UserViewHistory` | `user_view_history` | 浏览 |
| `UserRiskRecord` | `user_risk_record` | 异常分/快照/证据 |

关键枚举（注释约定）：  
role 0用户/1复核员/2管理员/3超管；user status 0正常/1禁言/2封禁；post 0正常/1删/2审/3拒；report 0待处理…；mute status 1生效/2解除/3已申诉（流程未实现）。

---

## 5. shill-auth（17）

### Controller `AuthController`
| 接口 | 功能 |
|------|------|
| `POST /api/auth/login` | 密码登录 → JWT + Redis `user:token:{userId}` |
| `POST /api/auth/auto-login` | 密码+OTP → 更长有效期 token |
| `POST /api/auth/send-code` | 发短信/邮件验证码 |
| `POST /api/auth/register` | BCrypt 注册 + 默认头像上传 MinIO |
| `POST /api/auth/logout` | 删 Redis token |

### Service
| 类 | 方法 | 功能 |
|----|------|------|
| `AuthServiceImpl` | `login/autoLogin/sendCode/register/logout` | 认证主流程 |
| `VerificationCodeService` | `sendAndStore/verify` | 6 位码 Redis 5min + 限流 |
| `NotificationServiceImpl` | `sendSmsCode/sendEmailCode` | 阿里云短信 / JavaMail |

### 其它
`SecurityConfig`（BCrypt + 放行 auth）、`MinioConfig`、`IdentifierUtils`（手机/邮箱/用户名）、`AvatarGenerator.generate`、DTO/VO（Login/Register/SendCode/LoginVO）、`UserMapper`。

---

## 6. shill-user（23）

### `UserController` `/api/user`
| 方法路径 | 功能 |
|----------|------|
| GET `/me`, `/{userId}`, `/search`, `/profile/{id}`, `/stats/{id}`, `/names`, `/list` | 资料/搜索/统计/管理列表 |
| PUT `/me`, `/{id}/mute`, `/{id}/unmute` | 改资料、禁言/解禁辅助 |
| POST/DELETE `/follow/{targetId}`；GET followings/followers | 关注 |

### `ChatController` `/api/chat`
| 方法 | 功能 |
|------|------|
| friends / messages / unread / stickers CRUD | 好友与历史、未读、表情包 |
| send / read | 发消息、已读 |

### Service
| 类 | 方法要点 |
|----|----------|
| `FollowServiceImpl` | follow/unfollow/isFollowing/列表/stats |
| `ChatServiceImpl` | send（文字/表情/文件+关注规则）、friends、history、markRead、unread、贴纸 |

### WebSocket
| 类 | 功能 |
|----|------|
| `WebSocketConfig` | 注册 `/ws/chat` |
| `ChatHandshakeInterceptor` | query JWT → session |
| `ChatWebSocketHandler` | 连接/消息/关闭；落库；推送 |
| `OnlineSessionRegistry` | 内存 userId→session |

本地实体：`ChatMessage`→`chat_message`；`ChatSticker`→`chat_sticker`。

---

## 7. shill-content（33）

### Controllers
| 类 | 基路径 | 能力 |
|----|--------|------|
| `PostController` | `/api/content/posts` | 列表详情发帖我的删除赞 |
| `CommentController` | `/api/content/comments` | 评论树回复增删赞详情 |
| `ReportController` | `/api/content/reports` | 列表改状态提交举报 |
| `FavoriteController` | `/api/content/favorites` | 收藏夹与收藏 |
| `HistoryController` | `/api/content/history` | 浏览/赞过历史 |

### Service 方法要点
| 类 | 公开方法 |
|----|----------|
| `PostServiceImpl` | pageList（Redis 首页缓存）、pageMyPosts、getDetail（发 MQ `post.view`）、createPost（敏感词审）、delete、like/unlike |
| `CommentServiceImpl` | 分页/回复/add（禁言校验）/delete/like（Redis Set）/detail |
| `ReportServiceImpl` | pageList、updateStatus、submitReport |
| `FavoriteServiceImpl` | 夹 CRUD + 收藏翻页 |
| `HistoryServiceImpl` | recordView、历史页 |
| `PostEnricher` | 补作者与 isLiked/isFavorited |

### MQ
| 类 | 功能 |
|----|------|
| `RabbitMqConfig` | 声明 TopicExchange `shillguard.exchange` |
| `PostViewConsumer` | `post.view.queue` / key `post.view` → 浏览+1 + 历史 |

### 工具
`SensitiveWordChecker.findSensitiveWords/isClean`；各类 DTO/VO（PostCreate、CommentCreate、PostVO、CommentVO、PostPublishResultVO）。

---

## 8. shill-agent（25）— 与 Python 对接核心

### `AgentController` `/api/agent`

| 方法 | 路径 | 功能 |
|------|------|------|
| `triggerDetect` | POST `/detect/trigger` | 手动触发检测（MQ，失败 HTTP 回落） |
| `muteList` | GET `/mute/records` | 禁言记录分页 |
| `manualMute` | POST `/mute` | 人工禁言（可连带隐藏内容） |
| `unmute` | DELETE `/mute/{muteId}` | 解除禁言 |
| `moderateReport` | POST `/moderate/{reportId}` | AI 审核举报 |
| `latestMute` | GET `/mute/latest` | 最近禁言+证据 |
| `detectMaliciousUsers` | POST `/detect-users` | 批量检测当日内容 |
| `detectMaliciousUsersStream` | POST `/detect-users/stream` | SSE 透传 |

### `AgentServiceImpl` 方法清单

| 方法 | 功能 |
|------|------|
| `triggerDetect` | MQ `agent.detect.trigger`；失败 `POST {python}/detect/trigger` |
| `manualMute` | 写禁言、用户 status=1、MQ `user.mute`、隐藏内容/评论 |
| `unmute` | mute status=2 |
| `getLatestMuteByUser` | 最近一条 |
| `moderateReport` | 组包→Python 审核轮询→`applyAction` |
| `detectMaliciousUsers` | 聚合当日内容→Python detect→警告/禁言+证据 |
| `detectMaliciousUsersStream` | SSE 中继 |
| `callPythonModerate`（私有） | POST `/ai/moderate` + GET result 轮询（约≤120s） |
| `callPythonDetect` | POST `/ai/detect-users` |
| `callEvidenceAgent` | POST `/ai/detect-evidence` |
| `callPythonDetectStream` | POST `/ai/detect-users-stream` |
| `applyAction` | auto_mute / manual_review / none |
| `saveRiskRecord` / `muteForDetection` / `hideReportedContent` / `hideAllCommentsOfUser` | 持久化与隐藏 |

### 配置与 DTO
- `RestTemplateConfig`：连接 5s / 读 30s  
- `RabbitMqConfig`：声明 `ai.moderate.queue` ↔ `ai.moderate.request`（给 Python Worker）  
- DTO：`Moderate*DTO`、`DetectUsers*DTO`、`DetectEvidence*DTO`、`DetectResultVO` 等与 Python schemas 对齐  
- Mapper：Mute/Report/Post/Comment/Risk/SysUser 状态更新  

配置项：`agent.python-service-url=http://localhost:8000`。

---

## 9. shill-notify（6）

| 类 | 方法/职责 |
|----|-----------|
| `NotifyController` | GET list/unread；PUT read/read-all |
| `NotifyServiceImpl` | 分页、未读、已读、保存 |
| `MuteNotifyConsumer` | `user.mute`→noticeType=1；`comment.created`→type=2 |
| `NotificationMapper` | BaseMapper |

---

## 10. shill-file（3）

| 类 | 方法 |
|----|------|
| `FileController` | POST `/api/file/image|video|avatar|chat-file`（大小与扩展名限制）→ MinIO URL |
| `MinioConfig` | `minioClient` |
| `FileApplication` | 启动 + Nacos |

---

## 11. shill-admin（13）

| Controller | 能力 |
|------------|------|
| `PostAdminController` | 帖子分页；改 status |
| `UserAdminController` | 用户分页；改角色/状态；重置密码 |
| `RoleAdminController` | 角色 CRUD；菜单树；角色菜单分配 |

`AdminServiceImpl` 实现上述；预设角色 0–3 不可删；禁言/封禁同步。`PasswordConfig` 提供 BCrypt。

---

## 12. RabbitMQ 路由键（汇总）

| Routing Key | 生产者 | 消费者 |
|-------------|--------|--------|
| `post.view` | content | content PostViewConsumer |
| `user.mute` | agent | notify |
| `comment.created` | （内容侧发） | notify |
| `agent.detect.trigger` | agent | （及 HTTP 回落） |
| `ai.moderate.request` | Python 发布 | Python 消费（Java 声明队列便于可见） |

Exchange：`shillguard.exchange`（Topic）。

---

## 13. Java → Python HTTP 对照表

| Method | Path | 用途 |
|--------|------|------|
| POST | `/ai/moderate` | 提交审核拿 taskId |
| GET | `/ai/moderate/result/{taskId}` | 轮询结果 |
| POST | `/ai/detect-users` | 批量打分 |
| POST | `/ai/detect-users-stream` | SSE 打分 |
| POST | `/ai/detect-evidence` | 证据 |
| POST | `/detect/trigger` | 检测触发回落（注意路径是否与 Python 实际暴露一致，复查时核对） |

---

## 14. 数据库与脚本

常见库名：`shill_guard`。SQL 脚本中可见 `schema` / `risk_schema` / `rbac_schema`；部分社交表可能仅实体存在、脚本分散——复查上线时应对齐 DDL。

基础设施主机（yml 常见）：MySQL/Redis/RabbitMQ/MinIO/Nacos → `192.168.150.101`。

---

## 15. 复查检查清单

- [ ] Gateway 白名单与新接口  
- [ ] `X-User-*` 头被服务信任，内网暴露面  
- [ ] agent DTO 与 Python schemas 字段同步  
- [ ] Feign 死依赖是否清理  
- [ ] 申诉流程是否补模块  
- [ ] chat/like/favorite 表是否有完整 DDL  
- [ ] `/detect/trigger` Python 侧是否真实存在  

本报告为 Java 仓第一轮全量盘点，便于与 `01`/`03` 交叉核对。
