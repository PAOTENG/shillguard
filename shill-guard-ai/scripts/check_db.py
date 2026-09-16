"""解码 ExtType(code=5)，提取 LangChain 消息的真实文本"""
import psycopg
import msgpack

conn = psycopg.connect(
        host="127.0.0.1", port=5432,
    dbname="shillguard", user="postgres", password="shillguard123",
)
cur = conn.cursor()

THREAD_ID = "chat_1783066458289"


def extract_messages_from_exttype(data: bytes):
    """ExtType(code=5) 的 data 本身又是一个 msgpack 流，
    解码后是一个 list：[module_name, class_name, kwargs_dict, ...]"""
    inner = msgpack.unpackb(data, raw=False, strict_map_key=False)
    # inner 通常是: [module, classname, kwargs] 或带更多元素
    return inner


def parse_msg(obj):
    """递归找 ExtType(code=5) 并解析成可读结构"""
    if isinstance(obj, msgpack.ExtType) and obj.code == 5:
        inner = extract_messages_from_exttype(obj.data)
        # inner = [module, classname, kwargs_dict]
        if isinstance(inner, list) and len(inner) >= 3:
            module, classname, kwargs = inner[0], inner[1], inner[2]
            content = kwargs.get("content", "") if isinstance(kwargs, dict) else ""
            msg_type = kwargs.get("type", "") if isinstance(kwargs, dict) else ""
            msg_id = kwargs.get("id", "") if isinstance(kwargs, dict) else ""
            result = {
                "class": f"{module}.{classname}",
                "type": msg_type,
                "content": content,
                "id": msg_id,
            }
            # 其他字段
            if isinstance(kwargs, dict):
                for k, v in kwargs.items():
                    if k not in ("content", "type", "id"):
                        result[k] = v
            return result
        return {"raw_inner": inner}
    if isinstance(obj, dict):
        return {k: parse_msg(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [parse_msg(item) for item in obj]
    return obj


print("=" * 70)
print("完整对话内容（从 checkpoint_blobs 解码）")
print("=" * 70)

# 取最新一条 messages blob（含完整对话）
cur.execute("""
    SELECT channel, version, type, blob
    FROM checkpoint_blobs
    WHERE thread_id = %s AND channel = 'messages'
    ORDER BY version DESC
    LIMIT 1
""", (THREAD_ID,))
row = cur.fetchone()
if row:
    channel, version, mtype, blob = row
    print(f"最新 messages blob: version={version}, {len(blob)} bytes\n")
    unpacked = msgpack.unpackb(blob, raw=False, strict_map_key=False)
    parsed = parse_msg(unpacked)
    print(f"消息条数: {len(parsed)}\n")
    for i, m in enumerate(parsed):
        print(f"--- 消息 {i+1} ---")
        print(f"  class:   {m.get('class')}")
        print(f"  type:    {m.get('type')}")
        print(f"  id:      {m.get('id')}")
        print(f"  content: {m.get('content')[:500]}")
        # 其他字段
        for k, v in m.items():
            if k not in ("class", "type", "id", "content"):
                print(f"  {k}: {repr(v)[:150]}")
        print()

print("=" * 70)
print("从 checkpoint_writes 看每一轮新增的消息")
print("=" * 70)

cur.execute("""
    SELECT checkpoint_id, task_id, idx, blob
    FROM checkpoint_writes
    WHERE thread_id = %s AND channel = 'messages'
    ORDER BY checkpoint_id, idx
""", (THREAD_ID,))
rows = cur.fetchall()
for i, (cp_id, task_id, idx, blob) in enumerate(rows):
    print(f"\n--- write {i+1} (step 增量) ---")
    print(f"  checkpoint_id: {cp_id}")
    unpacked = msgpack.unpackb(blob, raw=False, strict_map_key=False)
    parsed = parse_msg(unpacked)
    for m in parsed:
        print(f"  → [{m.get('type')}] {m.get('content','')[:300]}")

conn.close()
print("\n=== 完成 ===")
