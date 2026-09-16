"""迁移脚本：将 LangGraph checkpointer 中的历史消息写入 chat_messages 双轨表。

【背景】
  之前 GET /ai/history 直接读 LangGraph checkpointer。
  现在改为读 chat_messages 表（双轨存储），但旧数据只在 checkpointer 里。
  本脚本一次性把 checkpointer 里的消息迁移到 chat_messages 表。

【运行方式】
  cd /d D:\Projects\shill-guard-ai
  D:\Environment\Anaconda\envs\agent\python.exe scripts/migrate_history.py

【注意】
  - 迁移是幂等的（多次运行会写入重复数据，建议只跑一次）
  - 需要 uvicorn 服务不在运行（或者可以运行，无所谓，只是读写 PG）
  - Windows 需要 SelectorEventLoop
"""
import asyncio
import sys
import os

# Windows psycopg3 需要 SelectorEventLoop
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.agents.chat.graph import get_graph, get_pg_pool
from app.agents.chat.history_store import ensure_table, append_message


async def migrate():
    print("初始化连接池和图...")
    pool = await get_pg_pool()
    await ensure_table(pool)   # 确保 chat_messages 表存在

    # 查出所有 thread_id
    async with pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT DISTINCT thread_id FROM checkpoints")
            rows = await cur.fetchall()

    thread_ids = [r["thread_id"] for r in rows]
    print(f"共找到 {len(thread_ids)} 个会话，开始迁移...\n")

    # 需要 graph 来读取 state
    graph = await get_graph()

    total_migrated = 0
    for tid in thread_ids:
        config = {"configurable": {"thread_id": tid}}
        try:
            state = await graph.aget_state(config)
        except Exception as e:
            print(f"  ✗ {tid}：读取 state 失败 ({e})")
            continue

        if not state or not state.values:
            print(f"  - {tid}：无消息，跳过")
            continue

        msgs = state.values.get("messages", [])
        count = 0
        for m in msgs:
            # 过滤 tool 消息、带 tool_calls 的 AI 消息
            if m.type == "tool":
                continue
            if m.type == "ai" and getattr(m, "tool_calls", None):
                continue

            role = "user" if m.type == "human" else "assistant"
            content = m.content if isinstance(m.content, str) else str(m.content)
            if not content.strip():
                continue

            await append_message(pool, tid, "", role, content)
            count += 1

        total_migrated += count
        print(f"  ✓ {tid[:40]}...：写入 {count} 条消息")

    print(f"\n迁移完成！共写入 {total_migrated} 条消息到 chat_messages 表。")
    print("刷新前端页面即可看到历史记录。")
    await pool.close()


if __name__ == "__main__":
    asyncio.run(migrate())
