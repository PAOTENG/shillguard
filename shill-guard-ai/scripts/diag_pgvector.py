"""诊断脚本：检查 pgvector 迁移前提条件。

检查内容：
  1. psycopg2 / pgvector Python 包是否安装
  2. PostgreSQL 连接是否正常 + 版本
  3. vector 扩展是否已装（pgvector）
  4. 是否有权限创建 vector 扩展
  5. text-embedding-v3 实际输出维度（需要联网调 API）
  6. mem0 pgvector provider 依赖包是否齐全

运行命令（在项目根目录）：
  D:\\Environment\\Anaconda\\envs\\agent\\python.exe -X utf8 scripts/diag_pgvector.py
"""
import sys
import os

# 确保能 import app.config
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PASS = "[OK]  "
FAIL = "[FAIL]"
WARN = "[WARN]"
INFO = "[INFO]"

print("=" * 60)
print("  pgvector 迁移诊断脚本")
print("=" * 60)

# ── 1. Python 包检查 ──────────────────────────────────────────
print("\n[1] Python 包检查")

try:
    import psycopg2
    print(f"{PASS} psycopg2 已安装，版本: {psycopg2.__version__}")
except ImportError:
    print(f"{FAIL} psycopg2 未安装，请运行: pip install psycopg2-binary")

try:
    import pgvector
    ver = getattr(pgvector, "__version__", "已安装（版本未知）")
    print(f"{PASS} pgvector 已安装，版本: {ver}")
except ImportError:
    print(f"{FAIL} pgvector 未安装，请运行: pip install pgvector")

try:
    import psycopg2.extras
    print(f"{PASS} psycopg2.extras 可用")
except ImportError:
    print(f"{FAIL} psycopg2.extras 不可用")

# ── 2. PostgreSQL 连接 + 版本 ────────────────────────────────
print("\n[2] PostgreSQL 连接测试")

from app.config import settings

conn = None
try:
    import psycopg2
    conn = psycopg2.connect(
        host=settings.pg_host,
        port=settings.pg_port,
        dbname=settings.pg_dbname,
        user=settings.pg_user,
        password=settings.pg_password,
        connect_timeout=5,
    )
    cur = conn.cursor()
    cur.execute("SELECT version();")
    pg_version = cur.fetchone()[0]
    print(f"{PASS} 连接成功")
    print(f"{INFO} PG 版本: {pg_version[:60]}...")
except Exception as e:
    print(f"{FAIL} 连接失败: {e}")
    print("      请检查 PG 地址/端口/密码配置")
    conn = None

# ── 3. vector 扩展检查 ───────────────────────────────────────
print("\n[3] pgvector 扩展状态检查")

if conn:
    try:
        cur = conn.cursor()
        # 检查是否已安装（available 但未 create）
        cur.execute("SELECT * FROM pg_available_extensions WHERE name = 'vector';")
        row = cur.fetchone()
        if row:
            print(f"{PASS} vector 扩展在 PG 中可用（已安装到服务器）")
            print(f"{INFO} 扩展信息: name={row[0]}, default_version={row[1]}, installed_version={row[2]}")
        else:
            print(f"{FAIL} vector 扩展不在可用列表中")
            print(f"      需要在 PostgreSQL 服务器上安装 pgvector:")
            print(f"      Windows: https://github.com/pgvector/pgvector#windows")
            print(f"      Linux:   apt install postgresql-{{}}-pgvector 或 make install")
    except Exception as e:
        print(f"{FAIL} 查询扩展列表失败: {e}")

    # 检查是否已在当前数据库 CREATE
    try:
        cur.execute("SELECT extversion FROM pg_extension WHERE extname = 'vector';")
        row = cur.fetchone()
        if row:
            print(f"{PASS} vector 扩展已在数据库 '{settings.pg_dbname}' 中启用，版本: {row[0]}")
        else:
            print(f"{WARN} vector 扩展尚未在数据库中启用（需要 CREATE EXTENSION）")
    except Exception as e:
        print(f"{FAIL} 查询已启用扩展失败: {e}")

# ── 4. 尝试创建 vector 扩展（权限测试）───────────────────────
print("\n[4] 权限测试：尝试 CREATE EXTENSION IF NOT EXISTS vector")

if conn:
    try:
        conn.autocommit = False
        cur = conn.cursor()
        cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
        conn.commit()
        print(f"{PASS} CREATE EXTENSION 成功！当前用户有足够权限")
    except Exception as e:
        conn.rollback()
        print(f"{FAIL} CREATE EXTENSION 失败: {e}")
        if "superuser" in str(e).lower() or "permission" in str(e).lower():
            print(f"      需要 superuser 权限。解决方法：")
            print(f"      以 postgres 超级用户连接后执行:")
            print(f"      psql -U postgres -d {settings.pg_dbname} -c 'CREATE EXTENSION vector;'")

# ── 5. Embedding 维度检测 ────────────────────────────────────
print("\n[5] text-embedding-v3 输出维度检测")

try:
    import asyncio
    from langchain_openai import OpenAIEmbeddings

    async def check_embed_dims():
        embed = OpenAIEmbeddings(
            model=settings.embedding_model,
            api_key=settings.embed_api_key,
            base_url=settings.embed_base_url,
            check_embedding_ctx_length=False,
        )
        vec = await embed.aembed_query("test")
        return len(vec)

    dims = asyncio.run(check_embed_dims())
    print(f"{PASS} embedding 维度: {dims}")
    print(f"{INFO} mem0 pgvector 配置中 embedding_model_dims 应设为: {dims}")
except Exception as e:
    print(f"{WARN} 无法自动检测（可能是网络问题）: {e}")
    print(f"{INFO} text-embedding-v3 默认维度为 1536，mem0 配置请使用 1536")

# ── 6. mem0 pgvector 依赖包检查 ─────────────────────────────
print("\n[6] mem0 pgvector provider 依赖包")

deps = {
    "sqlalchemy": "SQLAlchemy（mem0 pgvector 必需）",
    "pgvector.sqlalchemy": "pgvector SQLAlchemy 类型（mem0 pgvector 必需）",
}

for module, desc in deps.items():
    try:
        __import__(module)
        print(f"{PASS} {desc}")
    except ImportError:
        print(f"{FAIL} {desc} - 请运行: pip install sqlalchemy pgvector")

# ── 汇总 ─────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("  诊断完成，请查看上方 [FAIL] 项目")
print("=" * 60)

if conn:
    conn.close()
