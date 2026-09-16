"""
第二轮诊断：
1. 解码 checkpoint_writes 的 msgpack 内容，看 summary / processed_context 实际是什么
2. 打印 mem0 的完整 metadata（documents 是 None，但 metadata 可能有内容）
3. 直接调 mem0.search() 新 API 看能不能找到张三
"""
import sys, os, asyncio
import msgpack

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings

DSN = (
    f"host={settings.pg_host} port={settings.pg_port} "
    f"dbname={settings.pg_dbname} user={settings.pg_user} "
    f"password={settings.pg_password}"
)
SEP = "=" * 68
TARGET_THREAD = "chat_1783863748692"


async def main():
    import psycopg
    from psycopg.rows import dict_row

    aconn = await psycopg.AsyncConnection.connect(DSN, row_factory=dict_row, autocommit=True)

    # ── 1. 解码 checkpoint_writes 里的关键 channel ───────────────────────────
    print(SEP)
    print(f"【1】checkpoint_writes 解码  thread={TARGET_THREAD}")
    print(SEP)

    async with aconn.cursor() as cur:
        await cur.execute("""
            SELECT task_id, channel, type, blob
            FROM checkpoint_writes
            WHERE thread_id = %s
            ORDER BY checkpoint_id DESC
            LIMIT 50
        """, (TARGET_THREAD,))
        writes = await cur.fetchall()

    for w in writes:
        ch = w['channel']
        tp = w['type']
        blob = w['blob']
        if tp != 'msgpack' or blob is None:
            continue
        # 只关心这几个关键 channel
        if ch not in ('summary', 'processed_context', 'long_term_memories', 'messages'):
            continue
        try:
            val = msgpack.unpackb(blob, raw=False)
            if ch == 'messages':
                # messages 是列表，只打印第一条的摘要
                if isinstance(val, list):
                    print(f"  channel=messages  count={len(val)}")
                    for i, m in enumerate(val[:3]):
                        mtype = m.get('type', '?') if isinstance(m, dict) else type(m).__name__
                        mcontent = ""
                        if isinstance(m, dict):
                            mcontent = str(m.get('content') or m.get('kwargs', {}).get('content', ''))[:80]
                        print(f"    [{i}] {mtype}: {mcontent}")
                else:
                    print(f"  channel=messages (not list): {str(val)[:100]}")
            else:
                print(f"  channel={ch}: {repr(str(val))[:200]}")
        except Exception as e:
            print(f"  channel={ch}  解码失败: {e}  blob_len={len(blob) if blob else 0}")

    # ── 2. mem0 ChromaDB 完整 metadata ───────────────────────────────────────
    print(f"\n{SEP}")
    print("【2】mem0 ChromaDB 完整 metadata（每条记录）")
    print(SEP)

    if os.path.exists(settings.mem0_chroma_path):
        import chromadb
        client = chromadb.PersistentClient(path=settings.mem0_chroma_path)
        for cm in client.list_collections():
            col = client.get_collection(cm.name)
            cnt = col.count()
            if cnt == 0 or cm.name == 'mem0migrations':
                continue
            print(f"\n  集合: {cm.name}  总条数={cnt}")
            # 查询指定 user_id 的条目
            try:
                result = col.get(
                    where={"user_id": TARGET_THREAD},
                    include=["documents", "metadatas"],
                )
                docs = result.get("documents") or []
                metas = result.get("metadatas") or []
                print(f"  user_id={TARGET_THREAD!r} 的条目数: {len(docs)}")
                for doc, meta in zip(docs, metas):
                    print(f"    doc={repr(doc)[:100]}  meta={meta}")
            except Exception as e:
                print(f"  查询失败: {e}")

            # 打印所有条目的 metadata（全量，不超过20条）
            all_items = col.get(limit=20, include=["documents", "metadatas"])
            all_docs = all_items.get("documents") or []
            all_metas = all_items.get("metadatas") or []
            print(f"\n  全量前20条（metadata 完整）：")
            for doc, meta in zip(all_docs, all_metas):
                print(f"    doc={repr(str(doc))[:80]}  meta_keys={list(meta.keys())}  data={str(meta)[:150]}")

    # ── 3. 直接调 mem0 search 看结果 ─────────────────────────────────────────
    print(f"\n{SEP}")
    print("【3】mem0.search() 新 API 直接测试")
    print(SEP)

    if not settings.mem0_enabled:
        print("  mem0 已禁用")
    else:
        from mem0 import Memory
        from app.agents.chat.memory import _build_mem0_config
        try:
            m = Memory.from_config(_build_mem0_config())

            # 查 TARGET_THREAD
            print(f"  搜索 user_id={TARGET_THREAD!r} 中 '我叫什么名字'")
            try:
                r1 = m.search("我叫什么名字", filters={"user_id": TARGET_THREAD}, limit=5)
                items1 = r1.get("results", []) if isinstance(r1, dict) else (r1 or [])
                print(f"  结果数={len(items1)}")
                for item in items1:
                    print(f"    {item}")
            except Exception as e:
                print(f"  搜索失败: {e}")

            # 查 test_user_001（有记录的用户）
            print(f"\n  搜索 user_id='test_user_001' 中 '我叫什么名字'")
            try:
                r2 = m.search("我叫什么名字", filters={"user_id": "test_user_001"}, limit=3)
                items2 = r2.get("results", []) if isinstance(r2, dict) else (r2 or [])
                print(f"  结果数={len(items2)}")
                for item in items2:
                    print(f"    memory={item.get('memory','?')}  score={item.get('score','?')}")
            except Exception as e:
                print(f"  搜索失败: {e}")

            # 列出该用户全部记忆
            print(f"\n  列出 user_id={TARGET_THREAD!r} 的全部记忆")
            try:
                all_mems = m.get_all(filters={"user_id": TARGET_THREAD})
                mems_list = all_mems.get("results", []) if isinstance(all_mems, dict) else (all_mems or [])
                print(f"  总条数={len(mems_list)}")
                for mem in mems_list:
                    print(f"    {mem.get('memory','?')}")
            except Exception as e:
                # 旧版 API 可能不支持 filters=
                try:
                    all_mems = m.get_all(user_id=TARGET_THREAD)
                    mems_list = all_mems.get("results", []) if isinstance(all_mems, dict) else (all_mems or [])
                    print(f"  总条数={len(mems_list)}")
                    for mem in mems_list:
                        print(f"    {mem.get('memory','?')}")
                except Exception as e2:
                    print(f"  失败: {e2}")

        except Exception as e:
            print(f"  mem0 初始化失败: {e}")

    print(f"\n{SEP}")
    print("第二轮诊断完成。")
    print(SEP)

    await aconn.close()


if __name__ == "__main__":
    asyncio.run(main())
