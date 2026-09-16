"""
Chat Agent 性能测试脚本
测量每个节点的耗时，找出瓶颈。

运行前确保 uvicorn 已启动（端口 8000）。
用法：
    D:\Environment\Anaconda\envs\agent\python.exe -X utf8 scripts/perf_test.py
"""
import asyncio
import sys
import os
import time
import json
import statistics

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SEP  = "=" * 68
SEP2 = "-" * 68
BASE_URL = "http://127.0.0.1:8000"

# 测试用的 thread_id（独立，不影响真实会话）
TEST_THREAD = "perf_test_thread_001"
TEST_USER   = "perf_test_user_001"

# ── 颜色辅助（Windows cmd 可能不支持，加 try）─────────────────────────────────
def fmt(ms: float, warn=2000, bad=5000) -> str:
    if ms >= bad:
        return f"{ms:.0f}ms [SLOW]"
    elif ms >= warn:
        return f"{ms:.0f}ms [WARN]"
    else:
        return f"{ms:.0f}ms [OK]"


# ─────────────────────────────────────────────────────────────────────────────
# Part 1: HTTP 端到端测试（TTFT + 总耗时）
# ─────────────────────────────────────────────────────────────────────────────

async def http_chat(message: str, thread_id: str = TEST_THREAD, user_id: str = TEST_USER):
    """发送一条消息，返回 (ttft_ms, total_ms, full_response)。"""
    import aiohttp
    url = f"{BASE_URL}/ai/chat"
    data = aiohttp.FormData()
    data.add_field("message", message)
    data.add_field("thread_id", thread_id)
    data.add_field("user_id", user_id)

    t0 = time.perf_counter()
    ttft_ms = None
    full_response = []

    async with aiohttp.ClientSession() as session:
        async with session.post(url, data=data, timeout=aiohttp.ClientTimeout(total=120)) as resp:
            if resp.status != 200:
                body = await resp.text()
                raise RuntimeError(f"HTTP {resp.status}: {body[:200]}")
            async for line in resp.content:
                line = line.decode("utf-8", errors="replace").strip()
                if not line.startswith("data: "):
                    continue
                payload = line[6:]
                if payload == "[DONE]":
                    break
                try:
                    obj = json.loads(payload)
                    delta = obj.get("delta", "")
                    if delta:
                        if ttft_ms is None:
                            ttft_ms = (time.perf_counter() - t0) * 1000
                        full_response.append(delta)
                except Exception:
                    pass

    total_ms = (time.perf_counter() - t0) * 1000
    return ttft_ms or total_ms, total_ms, "".join(full_response)


async def run_http_tests():
    print(SEP)
    print("【Part 1】HTTP 端到端性能（TTFT + 总耗时）")
    print(SEP)

    test_cases = [
        ("简单问候（无 RAG / 无记忆）",   "你好"),
        ("平台知识查询（触发 RAG）",       "小红书笔记被删除了怎么申诉？"),
        ("代码生成（长回答）",             "写一个Python冒泡排序"),
        ("记忆相关（依赖上下文）",         "我之前说我叫什么名字来着？"),
    ]

    results = []
    for label, msg in test_cases:
        print(f"\n  测试：{label}")
        print(f"  消息：{msg}")
        try:
            t_start = time.perf_counter()
            ttft, total, reply = await http_chat(msg)
            results.append((label, ttft, total))
            print(f"  TTFT    = {fmt(ttft, warn=2000, bad=5000)}")
            print(f"  总耗时  = {fmt(total, warn=5000, bad=15000)}")
            print(f"  回复    = {reply[:80]}{'...' if len(reply)>80 else ''}")
        except Exception as e:
            print(f"  ERROR: {e}")
            results.append((label, -1, -1))

    print(f"\n{SEP2}")
    print("  汇总：")
    for label, ttft, total in results:
        if ttft < 0:
            print(f"  {label:30s}  FAILED")
        else:
            print(f"  {label:30s}  TTFT={fmt(ttft)}  Total={fmt(total, warn=8000, bad=20000)}")
    return results


# ─────────────────────────────────────────────────────────────────────────────
# Part 2: 各组件独立计时
# ─────────────────────────────────────────────────────────────────────────────

async def run_component_tests():
    print(f"\n{SEP}")
    print("【Part 2】各组件独立计时")
    print(SEP)

    from app.config import settings
    from app.agents.chat.memory import search_memories
    from app.rag.retriever import retrieve
    from app.llm import get_llm, get_expander_llm
    from langchain_core.messages import SystemMessage, HumanMessage

    component_results = {}

    # ── 2-1. PostgreSQL 连接延迟 ─────────────────────────────────────────────
    print("\n  [2-1] PostgreSQL 连接池 + 查询延迟")
    import psycopg
    from psycopg.rows import dict_row
    DSN = (f"host={settings.pg_host} port={settings.pg_port} "
           f"dbname={settings.pg_dbname} user={settings.pg_user} "
           f"password={settings.pg_password}")
    t = time.perf_counter()
    conn = await psycopg.AsyncConnection.connect(DSN, row_factory=dict_row, autocommit=True)
    t_connect = (time.perf_counter() - t) * 1000

    t = time.perf_counter()
    async with conn.cursor() as cur:
        await cur.execute("SELECT COUNT(*) as n FROM checkpoints")
        row = await cur.fetchone()
    t_query = (time.perf_counter() - t) * 1000
    await conn.close()

    print(f"    连接建立  = {fmt(t_connect, warn=100, bad=500)}")
    print(f"    简单查询  = {fmt(t_query, warn=50, bad=200)}")
    component_results["pg_connect"] = t_connect
    component_results["pg_query"]   = t_query

    # ── 2-2. Embedding 延迟 ──────────────────────────────────────────────────
    print("\n  [2-2] Embedding API 延迟（百炼）")
    from app.rag.retriever import _get_embed  # 复用已有实例（check_embedding_ctx_length=False）
    embedder = _get_embed()
    query = "怎么发笔记？"
    samples = []
    for i in range(2):
        t = time.perf_counter()
        try:
            await embedder.aembed_query(query)
            elapsed = (time.perf_counter() - t) * 1000
            samples.append(elapsed)
            print(f"    embedding 第{i+1}次 = {fmt(elapsed, warn=300, bad=1000)}")
        except Exception as e:
            elapsed = (time.perf_counter() - t) * 1000
            print(f"    embedding 第{i+1}次失败: {e}  耗时={elapsed:.0f}ms")
    if samples:
        avg = statistics.mean(samples)
        print(f"    embedding 均值 = {fmt(avg, warn=300, bad=1000)}")
        component_results["embed"] = avg

    # ── 2-3. RAG 检索 (embed + BM25 + rerank) ───────────────────────────────
    print("\n  [2-3] RAG 检索全链路（embed + BM25 + rerank）")
    t = time.perf_counter()
    snippets = await retrieve(query)
    t_rag = (time.perf_counter() - t) * 1000
    print(f"    RAG total = {fmt(t_rag, warn=500, bad=2000)}  命中={len(snippets)} chunks")
    component_results["rag"] = t_rag

    # ── 2-4. mem0 search ────────────────────────────────────────────────────
    print("\n  [2-4] mem0 语义检索")
    t = time.perf_counter()
    mems = await search_memories("我叫什么名字", TEST_USER)
    t_mem0 = (time.perf_counter() - t) * 1000
    print(f"    mem0.search = {fmt(t_mem0, warn=300, bad=1000)}  结果: {mems[:60] if mems else '(空)'}")
    component_results["mem0"] = t_mem0

    # ── 2-5. Worker LLM（context_processor）────────────────────────────────
    print("\n  [2-5] Worker LLM（context_processor，prompt JSON 模式）")
    worker_system = (
        "你是信息提炼助手。根据用户当前问题，从背景信息中提取唯一一句相关的事实。\n"
        '必须只返回如下 JSON：{"has_relevant_context": true, "background_fact": "单句事实"}'
    )
    worker_user = (
        "用户问题：我叫什么名字？\n\n"
        "背景信息：\n[用户此前发言]\n我叫张三\n\n"
        "请按 JSON 格式返回。"
    )
    llm_worker = get_expander_llm()
    times_worker = []
    for i in range(2):
        t = time.perf_counter()
        try:
            resp = await llm_worker.ainvoke([
                SystemMessage(content=worker_system),
                HumanMessage(content=worker_user),
            ])
            elapsed = (time.perf_counter() - t) * 1000
            times_worker.append(elapsed)
            print(f"    Worker LLM 第{i+1}次 = {fmt(elapsed, warn=2000, bad=8000)}")
            if i == 0:
                print(f"    回复前100字: {str(resp.content)[:100]}")
        except Exception as e:
            elapsed = (time.perf_counter() - t) * 1000
            print(f"    Worker LLM 第{i+1}次失败: {e}  耗时={elapsed:.0f}ms")
            times_worker.append(elapsed)
    if times_worker:
        component_results["worker_llm"] = statistics.mean(times_worker)

    # ── 2-6. Main LLM TTFT（流式）──────────────────────────────────────────
    print("\n  [2-6] Main LLM TTFT（流式，简单问题）")
    llm_main = get_llm()
    simple_msgs = [
        SystemMessage(content="你是 ShillGuard AI 助手。"),
        HumanMessage(content="你好，今天天气怎么样？（不需要联网，随便回答）"),
    ]
    t0 = time.perf_counter()
    ttft_main = None
    total_tokens = 0
    try:
        async for chunk in llm_main.astream(simple_msgs):
            if chunk.content and ttft_main is None:
                ttft_main = (time.perf_counter() - t0) * 1000
            total_tokens += 1
        t_main_total = (time.perf_counter() - t0) * 1000
        print(f"    Main LLM TTFT  = {fmt(ttft_main or 0, warn=2000, bad=5000)}")
        print(f"    Main LLM total = {fmt(t_main_total, warn=5000, bad=15000)}  chunks={total_tokens}")
        component_results["main_llm_ttft"]  = ttft_main or 0
        component_results["main_llm_total"] = t_main_total
    except Exception as e:
        print(f"    Main LLM 失败: {e}")

    # ── 2-7. 完整节点链路模拟（不走 HTTP，直接调 graph 函数）────────────────
    print(f"\n  [2-7] LangGraph 节点链路模拟（不包含 Main LLM，仅前置节点）")
    from app.agents.chat.memory import format_user_said_history
    fake_state = {
        "messages": [HumanMessage(content="怎么发笔记？")],
        "summary": "",
        "long_term_memories": "",
        "rag_context": "",
        "processed_context": "",
        "user_id": TEST_USER,
        "doc_context": "",
    }

    t = time.perf_counter()
    mems2 = await search_memories("怎么发笔记？", TEST_USER)
    t_node_mem0 = (time.perf_counter() - t) * 1000

    t = time.perf_counter()
    snips = await retrieve("怎么发笔记？")
    t_node_rag = (time.perf_counter() - t) * 1000

    print(f"    memory_node (mem0 search) = {fmt(t_node_mem0, warn=500, bad=2000)}")
    print(f"    rag_node                  = {fmt(t_node_rag, warn=500, bad=2000)}")
    print(f"    合计前置节点              = {fmt(t_node_mem0 + t_node_rag, warn=1000, bad=3000)}")

    # ── 汇总 ─────────────────────────────────────────────────────────────────
    print(f"\n{SEP2}")
    print("  组件耗时汇总：")
    labels = [
        ("pg_connect",    "PostgreSQL 建连",        100,  500),
        ("pg_query",      "PostgreSQL 简单查询",      50,  200),
        ("embed",         "Embedding API",           300, 1000),
        ("rag",           "RAG 全链路",              500, 2000),
        ("mem0",          "mem0 search",             300, 1000),
        ("worker_llm",    "Worker LLM（JSON提炼）", 2000, 8000),
        ("main_llm_ttft", "Main LLM TTFT",          2000, 5000),
        ("main_llm_total","Main LLM 总耗时",        5000,15000),
    ]
    for key, name, warn, bad in labels:
        ms = component_results.get(key)
        if ms is not None:
            print(f"  {name:28s} = {fmt(ms, warn=warn, bad=bad)}")

    return component_results


# ─────────────────────────────────────────────────────────────────────────────
# Part 3: 多轮对话压力测试（找出多轮后的耗时增长）
# ─────────────────────────────────────────────────────────────────────────────

async def run_multiturn_test():
    print(f"\n{SEP}")
    print("【Part 3】多轮对话耗时（观察轮次增多后是否变慢）")
    print(SEP)

    thread_id = f"perf_multi_{int(time.time())}"
    messages = [
        "你好，我叫性能测试用户",
        "今天几号？",
        "怎么发小红书笔记？",
        "我之前说我叫什么？",
        "再给我讲讲笔记审核规则",
    ]

    prev_total = None
    for i, msg in enumerate(messages, 1):
        try:
            ttft, total, reply = await http_chat(msg, thread_id=thread_id, user_id=thread_id)
            trend = ""
            if prev_total is not None:
                delta = total - prev_total
                trend = f"  (较上轮 {'+'if delta>=0 else ''}{delta:.0f}ms)"
            print(f"  第{i}轮  TTFT={fmt(ttft)}  Total={fmt(total, warn=8000, bad=20000)}{trend}")
            print(f"         Q: {msg[:40]}  A: {reply[:60]}")
            prev_total = total
        except Exception as e:
            print(f"  第{i}轮  ERROR: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

async def main():
    print(SEP)
    print("Chat Agent 性能诊断报告")
    print(f"目标服务: {BASE_URL}")
    print(SEP)

    # 先检查服务是否在线
    import aiohttp
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(f"{BASE_URL}/health", timeout=aiohttp.ClientTimeout(total=3)) as r:
                pass
        print("服务在线\n")
    except Exception:
        # /health 可能不存在，尝试根路径
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(BASE_URL, timeout=aiohttp.ClientTimeout(total=3)) as r:
                    pass
            print("服务在线\n")
        except Exception:
            print("警告：无法连接服务，Part 1 和 Part 3 将跳过（仅运行组件测试）\n")

    # Part 2 必跑（直接导入模块，不需要服务在线）
    comp = await run_component_tests()

    # Part 1 和 3：需要服务在线
    try:
        await run_http_tests()
        await run_multiturn_test()
    except Exception as e:
        print(f"\n  跳过 HTTP 测试（服务未启动或出错）: {e}")

    print(f"\n{SEP}")
    print("诊断完成。重点看 [SLOW] / [WARN] 标记的条目。")
    print(SEP)


if __name__ == "__main__":
    # 检查 aiohttp
    try:
        import aiohttp
    except ImportError:
        print("缺少 aiohttp，正在安装...")
        import subprocess
        subprocess.run([sys.executable, "-m", "pip", "install", "aiohttp", "-q"])
        import aiohttp

    asyncio.run(main())
