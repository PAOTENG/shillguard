# ShillGuard — Three-Repo Setup

Social-media shill detection platform. Local OS is Windows; use **cmd**.

| Repo | Role | Port |
|------|------|------|
| `D:\project\shill-guard-frontend` | Vue frontend | 3000 |
| `D:\project\shill-guard` | Java microservices | Gateway 18080, services 9001–9010 |
| `D:\project\shill-guard-ai` | Python Agent | 8000 |

Deeper architecture/API notes: `技术文档汇总/`. Middleware credentials: `中间件访问信息.txt`.

---

## 1. Local runtime (install first)

| Software | Version | Local path (reuse if already installed) |
|----------|---------|------------------------------------------|
| JDK | **17** | `D:\Environment\JAVA17` |
| Maven | **3.9.16** | `D:\Environment\Maven3.9.16\apache-maven-3.9.16` |
| Node.js | **18+** (Vite 5) | `D:\app\Node` |
| Python | **≥ 3.11** | `D:\Environment\Anaconda\envs\agent\python.exe` |
| Docker Desktop | any recent | Run middleware here; do not mix with `rag-stack` |

Do **not** use the system `python`. Always use the `agent` conda env above.

---

## 2. Packages per repo

### Frontend `shill-guard-frontend`

```bat
cd /d D:\project\shill-guard-frontend
npm install
```

| Package | Version |
|---------|---------|
| vue | ^3.4.21 |
| vue-router | ^4.3.2 |
| pinia | ^2.1.7 |
| element-plus | ^2.7.3 |
| @element-plus/icons-vue | ^2.3.1 |
| axios | ^1.6.8 |
| marked | ^18.0.6 |
| highlight.js | ^11.11.1 |
| vite | ^5.2.10 |
| typescript | ^5.4.5 |
| vue-tsc | ^2.0.13 |
| @vitejs/plugin-vue | ^5.0.4 |
| unplugin-auto-import | ^0.17.6 |
| unplugin-vue-components | ^0.27.0 |

### Java `shill-guard`

Open the project in IDEA and let Maven resolve the parent POM. Core versions:

| Item | Version |
|------|---------|
| Java | 17 |
| Spring Boot | 3.2.5 |
| Spring Cloud | 2023.0.1 |
| Spring Cloud Alibaba / Nacos | 2023.0.1.0 |
| MyBatis-Plus | 3.5.7 |
| JWT (jjwt) | 0.12.5 |
| MinIO SDK | 8.5.9 |
| Knife4j | 4.4.0 |
| Hutool | 5.8.25 |

Modules: `common` / `gateway` / `auth` / `user` / `content` / `agent` / `notify` / `file` / `admin`.

First-time install from the repo root:

```bat
cd /d D:\project\shill-guard
mvn -DskipTests install
```

### Python `shill-guard-ai`

```bat
cd /d D:\project\shill-guard-ai
D:\Environment\Anaconda\envs\agent\python.exe -m pip install -e .
```

Main `pyproject.toml` deps (`requires-python >= 3.11`):

| Package | Version |
|---------|---------|
| fastapi | >=0.115 |
| uvicorn[standard] | >=0.32 |
| pydantic-settings | >=2.5 |
| langgraph | >=0.2.50 |
| langchain-openai / langchain-core | >=0.2 / >=0.3 |
| chromadb / langchain-chroma | >=0.5 / >=0.1 |
| mem0ai | >=0.1.0 |
| aio-pika | >=9.4 |
| redis | >=5.0 |
| httpx | >=0.27 |
| tiktoken | >=0.7 |
| python-dotenv | >=1.0 |
| pypdf / python-docx / python-multipart | >=4.0 / >=1.1 / >=0.0.9 |
| alibabacloud_green20220302 | >=3.2.4 |
| agent-memory-guard | >=0.3.0 |

Copy `.env.example` to `.env` and fill in the LLM key. Middleware hosts are `127.0.0.1` (see `.env` / `中间件访问信息.txt`).

On Windows, start with `run.py` only. Do not run `uvicorn` directly (event-loop vs psycopg mismatch).

---

## 3. Middleware (Docker Desktop)

Keep this stack isolated from local `rag-stack` (ES on `:9200`). ShillGuard ES is mapped to **9201**; MinIO console is **19001**.

```bat
cd /d D:\project\agent项目选择\deploy
docker compose -p shill-guard -f docker-compose.desktop.yml up -d
```

| Image | Host ports | Credentials |
|-------|------------|-------------|
| mysql:8.0 | 3306 | root / shillguard123 |
| redis:7.2 | 6379 | password shillguard123 |
| nacos/nacos-server:v2.3.2 | 8848 / 9848 | nacos / nacos |
| rabbitmq:3.13-management | 5672 / 15672 | admin / shillguard123 |
| minio RELEASE.2024-11-07 | 9000 / 19001 | minioadmin / shillguard123 |
| pgvector/pgvector:pg16 | 5432 | postgres / shillguard123 |
| elasticsearch:8.14.3 | 9201 | no auth |

Consoles: Nacos `http://127.0.0.1:8848/nacos`, RabbitMQ `http://127.0.0.1:15672`, MinIO `http://127.0.0.1:19001`.

Host **8080 is held by Windows svchost — do not kill it**. The Java gateway uses **18080**.

---

## 4. Start order

1. Docker middleware  
2. Python Agent  
3. Java microservices (IDEA)  
4. Frontend  

### Python

```bat
cd /d D:\project\shill-guard-ai
D:\Environment\Anaconda\envs\agent\python.exe run.py
```

Health check: `http://127.0.0.1:8000/health`

### Java (IDEA)

Rebuild every module first. Start order:

`auth(9001)` → `user(9002)` → `content(9003)` → `agent(9004)` → `notify(9005)` → `file(9006)` → `admin(9010)` → **gateway(18080) last**

`shill-agent` calls Python `:8000`, so the Agent must be up first.

Test account: `superadmin` / `123456` (login via auth `:9001` or gateway `/api/auth/login`).

If a port is already in use:

```bat
netstat -ano | findstr ":9001"
taskkill /PID <PID> /F
```

### Frontend

```bat
cd /d D:\project\shill-guard-frontend
npm run dev
```

Browser: `http://localhost:3000`  
Vite proxy: `/api` and `/ws` → `18080`; `/ai` → `8000`.

---

## 5. Call graph (short)

```
Browser :3000
  ├─ /api /ws  → Java gateway :18080 → auth/user/content/agent/...
  └─ /ai       → Python :8000
                    ↑
              Java shill-agent calls /ai/moderate etc.
```

---

## 6. More docs

| File | Content |
|------|---------|
| `中间件访问信息.txt` | Middleware URLs and accounts |
| `启动文件命令.txt` | Startup command notes |
| `技术文档汇总/00-三端总览与联调关系.md` | Three-repo overview and main flows |
| `技术文档汇总/01-shill-guard-ai-Python-Agent技术报告.md` | Python modules |
| `技术文档汇总/02-shill-guard-Java后端技术报告.md` | Java modules |
| `技术文档汇总/03-shill-guard-frontend-前端技术报告.md` | Frontend pages |
| `技术文档汇总/05-技术栈逐项说明.md` | LangGraph / RAG / MCP |
| `技术文档汇总/06-全部数据落在D盘-目录与环境变量.md` | D-drive env layout |
