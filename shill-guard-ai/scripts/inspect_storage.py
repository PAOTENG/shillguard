"""深度检查所有数据实际存储位置。

运行命令：
  D:\\Environment\\Anaconda\\envs\\agent\\python.exe -X utf8 scripts/inspect_storage.py
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import psycopg2
from app.config import settings

conn = psycopg2.connect(
    host=settings.pg_host, port=settings.pg_port,
    dbname=settings.pg_dbname, user=settings.pg_user,
    password=settings.pg_password,
)
cur = conn.cursor()

SEP = "=" * 60

# ── 1. chat_messages ──────────────────────────────────────────
print(SEP)
print("[1] chat_messages — UI 对话历史")
cur.execute("SELECT COUNT(*) FROM chat_messages")
print(f"  总行数: {cur.fetchone()[0]}")
cur.execute("SELECT id, thread_id, user_id, role, LEFT(content,40), created_at FROM chat_messages ORDER BY created_at DESC LIMIT 3")
rows = cur.fetchall()
if rows:
    print("  最近3条记录:")
    for r in rows:
        print(f"    id={r[0]} thread={r[1][:20]} role={r[3]} content='{r[4]}...'")
else:
    print("  (空表)")

# ── 2. checkpoints ────────────────────────────────────────────
print(SEP)
print("[2] checkpoints — LangGraph 检查点元信息")
cur.execute("SELECT COUNT(*) FROM checkpoints")
print(f"  总行数: {cur.fetchone()[0]}")
cur.execute("SELECT thread_id, checkpoint_id, jsonb_object_keys(checkpoint) FROM checkpoints LIMIT 1")
row = cur.fetchone()
if row:
    print(f"  示例 thread_id: {row[0][:30]}")
    print(f"  checkpoint jsonb 顶层 key: {row[2]}")
    # 查所有 key
    cur.execute("SELECT DISTINCT jsonb_object_keys(checkpoint) FROM checkpoints")
    keys = [r[0] for r in cur.fetchall()]
    print(f"  checkpoint 所有 jsonb key: {keys}")
    cur.execute("SELECT DISTINCT jsonb_object_keys(metadata) FROM checkpoints")
    mkeys = [r[0] for r in cur.fetchall()]
    print(f"  metadata 所有 jsonb key: {mkeys}")
else:
    print("  (空表)")

# ── 3. checkpoint_blobs ───────────────────────────────────────
print(SEP)
print("[3] checkpoint_blobs — ChatState 各字段序列化存储")
cur.execute("SELECT COUNT(*) FROM checkpoint_blobs")
print(f"  总行数: {cur.fetchone()[0]}")
cur.execute("SELECT DISTINCT channel FROM checkpoint_blobs ORDER BY channel")
channels = [r[0] for r in cur.fetchall()]
print(f"  所有 channel 值（即 ChatState 字段名）: {channels}")

# 检查 summary channel 是否存在
cur.execute("SELECT COUNT(*) FROM checkpoint_blobs WHERE channel = 'summary'")
summary_count = cur.fetchone()[0]
print(f"  channel='summary' 的行数: {summary_count}")

# 检查有没有 type != NULL 的 blob 来判断序列化格式
cur.execute("SELECT DISTINCT type FROM checkpoint_blobs LIMIT 10")
types = [r[0] for r in cur.fetchall()]
print(f"  blob type 值: {types}")

# 尝试解码一个 blob 看看内容
cur.execute("SELECT channel, type, blob FROM checkpoint_blobs WHERE channel NOT IN ('__start__') LIMIT 5")
blobs = cur.fetchall()
print("  部分 blob 内容预览（尝试解码）:")
for channel, btype, blob in blobs:
    if btype == 'json' and blob:
        try:
            content = json.loads(blob.decode('utf-8') if isinstance(blob, bytes) else blob)
            preview = str(content)[:80]
        except Exception as e:
            preview = f"(json解码失败: {e})"
    elif btype == 'msgpack' and blob:
        try:
            import msgpack
            content = msgpack.unpackb(blob, raw=False)
            preview = str(content)[:80]
        except Exception as e:
            try:
                preview = blob[:40].hex()
            except:
                preview = "(无法解码)"
    elif blob:
        preview = blob[:40].hex() if isinstance(blob, bytes) else str(blob)[:80]
    else:
        preview = "(NULL)"
    print(f"    channel='{channel}' type={btype} → {preview}")

# ── 4. checkpoint_writes ──────────────────────────────────────
print(SEP)
print("[4] checkpoint_writes — 节点写操作记录")
cur.execute("SELECT COUNT(*) FROM checkpoint_writes")
print(f"  总行数: {cur.fetchone()[0]}")
cur.execute("SELECT DISTINCT channel FROM checkpoint_writes ORDER BY channel")
wchannels = [r[0] for r in cur.fetchall()]
print(f"  所有 channel 值: {wchannels}")

cur.execute("SELECT COUNT(*) FROM checkpoint_writes WHERE channel = 'summary'")
print(f"  channel='summary' 的行数: {cur.fetchone()[0]}")

# 尝试解码 writes 里的 summary
cur.execute("SELECT channel, type, blob FROM checkpoint_writes WHERE channel='summary' LIMIT 3")
wrows = cur.fetchall()
if wrows:
    print("  summary channel 内容预览:")
    for channel, wtype, blob in wrows:
        if wtype == 'msgpack' and blob:
            try:
                import msgpack
                content = msgpack.unpackb(blob, raw=False)
                print(f"    → {str(content)[:120]}")
            except Exception as e:
                print(f"    → msgpack解码失败: {e}, hex: {blob[:30].hex()}")
        elif blob:
            print(f"    → type={wtype}, hex: {blob[:30].hex()}")

# ── 5. shillguard_mem0 ────────────────────────────────────────
print(SEP)
print("[5] shillguard_mem0 — mem0 用户长期记忆")
cur.execute("SELECT COUNT(*) FROM shillguard_mem0")
print(f"  总行数: {cur.fetchone()[0]}")
cur.execute("SELECT id, payload FROM shillguard_mem0 LIMIT 5")
rows = cur.fetchall()
if rows:
    print("  前5条记忆内容:")
    for r in rows:
        payload = r[1] if isinstance(r[1], dict) else {}
        print(f"    id={str(r[0])[:8]}... payload={str(payload)[:100]}")
else:
    print("  (空表，尚无记忆)")

# ── 6. shillguard_mem0_entities ──────────────────────────────
print(SEP)
print("[6] shillguard_mem0_entities — mem0 实体关系")
cur.execute("SELECT COUNT(*) FROM shillguard_mem0_entities")
print(f"  总行数: {cur.fetchone()[0]}")

# ── 汇总结论 ──────────────────────────────────────────────────
print(SEP)
print("[结论] 数据存储位置汇总")
print("  UI对话历史  → chat_messages.content")
print("  LangGraph状态 → checkpoint_blobs (channel=各字段名, blob=序列化值)")
print("  mem0记忆    → shillguard_mem0.payload + vector列")
print()
print("  注意：checkpoint_blobs.channel 实际存在的值见上方 [3]")
print("  如果没有 channel='summary'，说明当前会话还未触发摘要压缩")
print("  (摘要压缩触发条件：历史消息 > max_messages_before_summary=8)")

conn.close()
