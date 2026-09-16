"""
诊断：为什么 agent 不记得名字？
直接用 psycopg3 连接，不走 app 池单例，不调 LLM 网络，快速出结果。
"""
import sys, os, asyncio, pickle, json

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── 读取配置（不启动 app） ────────────────────────────────────────────────────
from app.config import settings

DSN = (
    f"host={settings.pg_host} port={settings.pg_port} "
    f"dbname={settings.pg_dbname} user={settings.pg_user} "
    f"password={settings.pg_password}"
)
SEP = "=" * 68


async def main():
    import psycopg
    from psycopg.rows import dict_row

    aconn = await psycopg.AsyncConnection.connect(DSN, row_factory=dict_row, autocommit=True)

    # ── 1. chat_messages ──────────────────────────────────────────────────────
    print(SEP)
    print("【1】chat_messages 表（双轨存储）")
    print(SEP)
    async with aconn.cursor() as cur:
        # 最近3个会话
        try:
            await cur.execute("""
                SELECT thread_id, user_id, MAX(created_at) AS last_at, COUNT(*) AS cnt
                FROM chat_messages
                GROUP BY thread_id, user_id
                ORDER BY last_at DESC LIMIT 3
            """)
            sessions = await cur.fetchall()
        except Exception as e:
            sessions = []
            print(f"  ⚠️  查询失败: {e}")

    if not sessions:
        print("  ⚠️  chat_messages 表为空！双轨写入未生效")
        latest_uid = ""
        latest_tid = ""
    else:
        for s in sessions:
            print(f"  thread_id={s['thread_id']}  user_id={s['user_id']!r}  "
                  f"消息数={s['cnt']}  最后={s['last_at']}")
        latest_tid = sessions[0]['thread_id']
        latest_uid = sessions[0]['user_id']

        async with aconn.cursor() as cur:
            await cur.execute("""
                SELECT role, content, created_at FROM chat_messages
                WHERE thread_id = %s ORDER BY created_at ASC LIMIT 30
            """, (latest_tid,))
            msgs_ui = await cur.fetchall()

        print(f"\n  最新会话 {latest_tid} 的消息：")
        name_in_ui = False
        for r in msgs_ui:
            label = "[User]" if r['role'] == 'user' else "[AI  ]"
            txt = str(r['content'])
            if "张三" in txt:
                name_in_ui = True
            print(f"  {label} [{r['created_at'].strftime('%H:%M:%S')}] {txt[:110]}")
        has_name = "YES" if name_in_ui else "NO"
        print(f"\n  'Zhang San' in chat_messages: {has_name}")

    # ── 2. checkpoints：最新 checkpoint 里的 state ────────────────────────────
    print(f"\n{SEP}")
    print("【2】LangGraph checkpoints（state messages + summary）")
    print(SEP)
    async with aconn.cursor() as cur:
        try:
            await cur.execute("""
                SELECT thread_id, checkpoint_id, checkpoint, metadata
                FROM checkpoints
                ORDER BY checkpoint_id DESC LIMIT 5
            """)
            ckpts = await cur.fetchall()
        except Exception as e:
            ckpts = []
            print(f"  ⚠️  查询失败: {e}")

    if not ckpts:
        print("  ⚠️  checkpoints 表为空")
    else:
        for ck in ckpts[:3]:
            tid = ck['thread_id']
            print(f"\n  thread_id={tid}  ckpt_id={ck['checkpoint_id']}")
            # checkpoint 是 bytes（pickle/msgpack）
            raw = ck['checkpoint']
            if raw:
                try:
                    # LangGraph 用 msgpack；尝试 pickle 再尝试 json
                    try:
                        import msgpack
                        data = msgpack.unpackb(raw, raw=False)
                    except Exception:
                        try:
                            data = pickle.loads(raw)
                        except Exception:
                            data = json.loads(raw)

                    channel_values = data.get("channel_values", {})
                    msgs_in_state = channel_values.get("messages", [])
                    summary = channel_values.get("summary", "")
                    user_id_st = channel_values.get("user_id", "")

                    print(f"  user_id in state = {user_id_st!r}")
                    print(f"  messages 数量 = {len(msgs_in_state)}")
                    print(f"  summary = {summary!r}")

                    name_in_msgs = any("张三" in str(m) for m in msgs_in_state)
                    name_in_sum = "张三" in (summary or "")
                    print(f"  ZhangSan in messages: {'YES' if name_in_msgs else 'NO'}")
                    print(f"  ZhangSan in summary:  {'YES' if name_in_sum else 'NO'}")

                    # 列出 messages 的类型和内容摘要
                    if msgs_in_state:
                        print("  messages 列表：")
                        for i, m in enumerate(msgs_in_state):
                            mtype = type(m).__name__ if not isinstance(m, dict) else m.get("type", "?")
                            mcontent = ""
                            if isinstance(m, dict):
                                mcontent = str(m.get("content") or m.get("kwargs", {}).get("content", ""))
                            else:
                                mcontent = str(getattr(m, "content", ""))
                            print(f"    [{i}] {mtype}: {mcontent[:90]}")
                except Exception as e:
                    print(f"  ⚠️  解码 checkpoint 失败: {e}")
                    # 退路：直接打印原始 channel_values keys
                    print(f"  raw bytes length = {len(raw)}")
            else:
                print("  checkpoint 为空")

    # ── 3. checkpoint_writes（写入中间状态）────────────────────────────────────
    print(f"\n{SEP}")
    print("【3】checkpoint_writes（最新10条，检查 messages 增删）")
    print(SEP)
    async with aconn.cursor() as cur:
        try:
            await cur.execute("""
                SELECT thread_id, checkpoint_id, task_id, channel, type, blob
                FROM checkpoint_writes
                ORDER BY checkpoint_id DESC LIMIT 10
            """)
            writes = await cur.fetchall()
        except Exception as e:
            writes = []
            print(f"  ⚠️  查询失败: {e}")

    for w in writes:
        ch = w['channel']
        print(f"  thread={w['thread_id'][:30]}  channel={ch}  type={w['type']}")

    # ── 4. mem0 ChromaDB ──────────────────────────────────────────────────────
    print(f"\n{SEP}")
    print("【4】mem0 ChromaDB 记忆")
    print(SEP)
    if not os.path.exists(settings.mem0_chroma_path):
        print("  ⚠️  路径不存在，从未写入记忆")
    else:
        try:
            import chromadb
            client = chromadb.PersistentClient(path=settings.mem0_chroma_path)
            colls = client.list_collections()
            if not colls:
                print("  ⚠️  无集合（mem0 从未写入）")
            for cm in colls:
                col = client.get_collection(cm.name)
                cnt = col.count()
                print(f"\n  集合: {cm.name}  总条数: {cnt}")
                if cnt > 0:
                    items = col.get(limit=min(cnt, 30), include=["documents", "metadatas"])
                    docs = items.get("documents") or []
                    metas = items.get("metadatas") or []
                    name_found = False
                    for doc, meta in zip(docs, metas):
                        uid = meta.get("user_id", meta.get("agent_id", "?"))
                        flag = " ✅ 含张三！" if "张三" in str(doc) else ""
                        if flag:
                            name_found = True
                        print(f"    user={uid}  {str(doc)[:100]}{flag}")
                    if not name_found:
                        print("  NO ZhangSan memory found in mem0")
        except Exception as e:
            print(f"  ⚠️  读取失败: {e}")

    # ── 5. 综合判断 ───────────────────────────────────────────────────────────
    print(f"\n{SEP}")
    print("【5】综合诊断结论")
    print(SEP)

    await aconn.close()
    print("数据库连接已关闭。")


if __name__ == "__main__":
    asyncio.run(main())
