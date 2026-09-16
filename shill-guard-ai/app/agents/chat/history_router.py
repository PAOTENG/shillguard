"""历史对话 API：从双轨存储（chat_messages 表）读取会话记录。

============================================================================
本文件对应总体流程的哪一部分
============================================================================
对应 __init__.py 总体流程编号 ⑬（对外只读接口，独立于主对话链路）：
  - GET /ai/history/{thread_id}  —— get_history()：取单会话完整历史
  - GET /ai/conversations        —— list_conversations()：取最近 N 个会话摘要

调用关系：
  - app/main.py 挂载本文件的 router。
  - 本文件调 history_store.py::get_messages 读历史，调 graph.py::get_pg_pool 取连接池。
  - 严格只读 chat_messages 表，不碰 checkpointer，保证历史不被摘要压缩影响。
执行入口：前端 GET 上述两个接口 → 对应函数 → 返回 JSON。

============================================================================
【双轨存储架构（工业标准）】
  ┌─────────────────────────────────────────────┐
  │  UI 展示层：chat_messages 表（本文件读取）   │
  │  - append-only，永不压缩，永不删除          │
  │  - 存储完整 user + assistant 消息原文       │
  ├─────────────────────────────────────────────┤
  │  LLM 工作记忆：LangGraph checkpointer       │
  │  - 可被摘要压缩，RemoveMessage 删旧消息     │
  │  - 只供 LangGraph 内部使用，前端不直接读    │
  └─────────────────────────────────────────────┘

  分离原因：checkpointer 摘要后旧消息消失，UI 历史会断裂。
  chat_messages 表永远保存完整记录，解决这个经典反模式。

【接口】
  GET /ai/history/{thread_id}  — 从 chat_messages 读取完整对话历史
  GET /ai/conversations        — 最近 N 个会话摘要（标题/最后消息/时间）
"""
# datetime/timezone/timedelta：构造北京时间（UTC+8）格式化时间
from datetime import datetime, timezone, timedelta

# APIRouter：路由对象；Query：查询参数校验（limit 范围限制）
from fastapi import APIRouter, Query

# get_pg_pool：取 PG 连接池（graph.py 单例，与 checkpointer 共用）
from app.agents.chat.graph import get_pg_pool
# get_messages：从 chat_messages 表读取某会话历史
from app.agents.chat.history_store import get_messages

# FastAPI 路由对象，由 app/main.py 挂载
router = APIRouter()

# 北京时间时区（UTC+8），用于把数据库时间转为本地时间展示
BJ = timezone(timedelta(hours=8))


@router.get("/history/{thread_id}")
async def get_history(thread_id: str):
    """获取单个 thread 的完整对话历史（从 chat_messages 双轨表读取）。

    【功能 / 流程定位】
      总体流程 ⑬ 之接口1，前端 GET /ai/history/{thread_id} 触发。
      本函数结束后直接返回 JSON 给前端，无后续流程。

    【思路】
      与 LangGraph checkpointer 完全解耦：即使 checkpointer 被摘要压缩，
      此接口返回的历史始终完整（读 chat_messages append-only 表）。

    参数:
        thread_id: 会话 ID（路径参数）

    返回:
        {"thread_id": ..., "messages": [{"role","content","created_at"}, ...]}
    """
    # 取 PG 连接池
    pool = await get_pg_pool()
    # 读该会话完整历史（history_store::get_messages，按时间正序）
    messages = await get_messages(pool, thread_id)
    # 返回 JSON：会话 ID + 消息列表
    return {"thread_id": thread_id, "messages": messages}


@router.get("/conversations")
async def list_conversations(limit: int = Query(20, ge=1, le=100)):
    """列出最近更新的对话会话（从 chat_messages 双轨表读取，与 checkpointer 解耦）。

    【功能 / 流程定位】
      总体流程 ⑬ 之接口2，前端 GET /ai/conversations 触发。
      本函数结束后返回最近 N 个会话摘要列表给前端，无后续流程。

    【思路 / 代码流程】
      每个 thread_id 取：
        - title：第一条 user 消息（最多50字）
        - last_message：最新一条消息（最多100字）
        - last_time：最新消息时间
      1. 先 SQL 聚合每个 thread 的最新时间，按时间倒序取最近 N 个
      2. 逐 thread 调 get_messages 取消息，提取标题和最后一条
      3. 按 last_time 倒序排列返回

    参数:
        limit: 返回会话数量（1~100，默认 20，Query 校验）

    返回:
        {"conversations": [{"thread_id","title","last_message","last_time"}, ...]}
    """
    # 取 PG 连接池
    pool = await get_pg_pool()
    # ── Step1：聚合每个 thread 的最新时间，取最近 N 个 thread ──
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            # 每个 thread_id 取最新消息时间，按时间倒序返回最近的 N 个会话
            # MAX(created_at) AS last_ts：每会话最新时间
            # GROUP BY thread_id：按会话聚合
            # ORDER BY last_ts DESC：最新在前
            # LIMIT %s：限制数量
            await cur.execute(
                """
                SELECT thread_id, MAX(created_at) AS last_ts
                FROM chat_messages
                GROUP BY thread_id
                ORDER BY last_ts DESC
                LIMIT %s
                """,
                (limit,),
            )
            # 取全部聚合行
            thread_rows = await cur.fetchall()

    # ── Step2：逐 thread 提取标题/最后消息/时间 ──
    conversations = []
    for row in thread_rows:
        # 当前会话 ID
        tid = row["thread_id"]
        # last_time 默认空串
        last_time = ""
        if row["last_ts"]:
            try:
                # 数据库时间转北京时间字符串展示
                last_time = row["last_ts"].astimezone(BJ).strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                # 转换失败兜底：直接 str
                last_time = str(row["last_ts"])

        # 获取该 thread 的消息列表，提取标题和最后一条
        # get_messages：按时间正序返回，limit=200 防超长
        msgs = await get_messages(pool, tid, limit=200)
        # title：第一条 user 消息（最多50字）
        title = ""
        # last_msg：遍历结束后停在最后一条消息
        last_msg = ""
        for m in msgs:
            # 第一条 user 消息作为会话标题
            if m["role"] == "user" and not title:
                title = m["content"][:50]
            # 每次覆盖，循环结束后即最后一条
            last_msg = m["content"][:100]

        # 组装该会话摘要
        conversations.append({
            "thread_id": tid,
            "title": title,
            "last_message": last_msg,
            "last_time": last_time,
        })

    # ── Step3：按最新时间倒序排列（字符串排序兜底，确保顺序稳定）──
    conversations.sort(key=lambda x: x["last_time"], reverse=True)
    # 返回会话列表
    return {"conversations": conversations}
