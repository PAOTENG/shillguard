"""三层记忆系统测试脚本。

测试内容：
  1. 发送多轮对话，触发摘要压缩（需要 > max_messages_before_summary 条消息）
  2. 用 LangGraph Python API 读取 state，验证 summary / long_term_memories 字段
  3. 查询 mem0 的 ChromaDB 文件验证记忆是否已提取

使用方式：
  先启动 FastAPI 服务，然后运行：
  D:\Environment\Anaconda\envs\agent\python.exe scripts\test_chat_memory.py
"""
import sys
import asyncio
import selectors
import json
import time
import httpx

sys.path.insert(0, ".")

# Windows 必须切换为 SelectorEventLoop，psycopg3 不支持 ProactorEventLoop
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# ── 配置 ──────────────────────────────────────────────────────────────────────
BASE_URL = "http://localhost:8000"
THREAD_ID = f"test_memory_{int(time.time())}"   # 每次测试用新的 thread_id
USER_ID = "test_user_001"                        # 固定 user_id，方便验证 mem0
# 发 12 条消息，超过默认阈值 10，触发摘要
MESSAGES = [
    "你好，我叫小明",
    "我最近在学 Python",
    "我喜欢用 FastAPI 写后端",
    "我的项目叫 ShillGuard，是一个内容审核平台",
    "我用的数据库是 PostgreSQL",
    "我不太喜欢 MySQL",
    "我住在北京",
    "我平时早上 9 点上班",
    "我最喜欢的编程语言是 Python，其次是 Java",
    "我正在学习 LangGraph",
    "你还记得我叫什么名字吗？",   # 第11条，触发摘要，测试摘要是否生效
    "我之前说我喜欢什么编程语言？",  # 第12条，测试长期记忆
]


# ── 1. 发送对话 ───────────────────────────────────────────────────────────────

async def send_message(client: httpx.AsyncClient, message: str, idx: int) -> str:
    """发送单条消息，收集完整 SSE 响应。"""
    full = []
    try:
        async with client.stream(
            "POST",
            f"{BASE_URL}/ai/chat",
            data={"message": message, "thread_id": THREAD_ID, "user_id": USER_ID},
            timeout=httpx.Timeout(120.0, connect=10.0),  # 摘要压缩会多一次 LLM 调用，要留足时间
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if line.startswith("data: ") and "[DONE]" not in line:
                    payload = json.loads(line[6:])
                    full.append(payload.get("delta", ""))
    except Exception as e:
        print(f"  [错误] 发送失败: {e}")
        return ""
    answer = "".join(full)
    print(f"  [{idx:02d}] 问: {message[:30]}...")
    print(f"       答: {answer[:80]}{'...' if len(answer) > 80 else ''}")
    return answer


async def run_conversation():
    print("=" * 60)
    print(f"开始测试对话  thread_id={THREAD_ID}  user_id={USER_ID}")
    print("=" * 60)
    async with httpx.AsyncClient() as client:
        for i, msg in enumerate(MESSAGES, 1):
            await send_message(client, msg, i)
            await asyncio.sleep(0.5)
    print("\n[对话结束] 等待 3 秒让 mem0 异步写入完成...")
    await asyncio.sleep(3)


# ── 2. 用 LangGraph API 验证 state（最准确的方式）──────────────────────────────

async def check_langgraph_state():
    """直接用 LangGraph Python API 读取 state，查看 summary 等字段。

    比 SQL 更可靠：不依赖表结构，LangGraph 负责反序列化。
    """
    print("\n" + "=" * 60)
    print("验证 LangGraph State（包含摘要和记忆字段）")
    print("=" * 60)
    try:
        from app.agents.chat.graph import get_graph

        graph = await get_graph()
        config = {"configurable": {"thread_id": THREAD_ID}}
        state = await graph.aget_state(config)

        if not state or not state.values:
            print("[警告] 未找到对应 thread_id 的 state，请确认对话已完成")
            return

        values = state.values
        msg_count = len(values.get("messages", []))
        summary = values.get("summary", "")
        lt_mem = values.get("long_term_memories", "")
        user_id = values.get("user_id", "")

        print(f"thread_id          : {THREAD_ID}")
        print(f"消息总条数         : {msg_count}")
        print(f"user_id            : {user_id}")
        print()

        if summary:
            print(f"[OK] summary（摘要）已生成：\n{summary}")
        else:
            print(f"[信息] summary 为空（消息数={msg_count}，阈值=10，未达到或摘要失败）")

        print()
        if lt_mem:
            print(f"[OK] long_term_memories（mem0）：\n{lt_mem}")
        else:
            print("[信息] long_term_memories 为空（mem0 未检索到记忆，属正常初始状态）")

    except Exception as e:
        print(f"[错误] LangGraph state 读取失败: {e}")
        import traceback; traceback.print_exc()


# ── 3. 验证 mem0 ChromaDB ─────────────────────────────────────────────────────

def check_mem0():
    """检查 mem0 的 ChromaDB 中是否已提取到该用户的记忆。"""
    print("\n" + "=" * 60)
    print("验证 mem0 长期记忆（ChromaDB）")
    print("=" * 60)
    try:
        from app.agents.chat.memory import get_mem0

        mem0 = get_mem0()
        # 新版 mem0 get_all 用 filters 而不是直接传 user_id
        result = mem0.get_all(filters={"user_id": USER_ID})
        items = result.get("results", []) if isinstance(result, dict) else (result or [])

        if not items:
            print("[信息] mem0 暂无记忆（可能异步写入还未完成，稍后再试）")
        else:
            print(f"[OK] mem0 已提取到 {len(items)} 条记忆：")
            for i, m in enumerate(items, 1):
                text = m.get("memory") or m.get("text", "")
                print(f"  {i}. {text}")
    except Exception as e:
        print(f"[错误] mem0 查询失败: {e}")
        import traceback; traceback.print_exc()


# ── 主入口 ────────────────────────────────────────────────────────────────────

async def main():
    await run_conversation()
    await check_langgraph_state()
    check_mem0()

    print("\n" + "=" * 60)
    print("参考 SQL（在 DBeaver/Navicat 查看原始数据）：")
    print("=" * 60)
    print(f"""
-- 查看所有 checkpoint（LangGraph 每轮对话存一条）
SELECT thread_id, checkpoint_id, checkpoint_ns
FROM checkpoints
WHERE thread_id = '{THREAD_ID}'
ORDER BY checkpoint_id DESC
LIMIT 5;

-- 查看各字段的 channel blob（summary / messages / user_id 各一行）
SELECT thread_id, channel, type
FROM checkpoint_blobs
WHERE thread_id = '{THREAD_ID}'
ORDER BY channel;
""")


if __name__ == "__main__":
    asyncio.run(main())
