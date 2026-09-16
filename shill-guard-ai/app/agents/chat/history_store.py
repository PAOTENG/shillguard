"""双轨存储：UI 对话历史的独立 PostgreSQL 表（chat_messages）。

============================================================================
本文件对应总体流程的哪一部分
============================================================================
对应 __init__.py 总体流程编号 ⑫（被 ①②③ 与 ⑬ 调用）：
  - ensure_table()    —— 建表+索引：被 graph.py::build_graph 启动时调用
  - append_message()  —— 追加一条消息：被 router.py::chat / event_stream 调用
  - get_messages()    —— 读单会话历史：被 history_router.py::get_history/list_conversations 调用

调用关系：
  - graph.py 启动时 ensure_table(pool) 建表；
  - router.py 每轮对话 append_message 写 user + assistant 消息；
  - history_router.py 用 get_messages 读取展示。
本文件是双轨存储之"UI 历史轨"的数据访问层，无独立运行入口。

============================================================================
【工业标准模式（来自 LangGraph Forum 生产实践）】
  LangGraph checkpointer（PostgresSaver）是 LLM 的工作记忆：
    - 可被 SummarizationMiddleware / 手写摘要节点压缩
    - 摘要时会 RemoveMessage 删除旧消息
    - 只供 LLM 用，前端不应直接读

  chat_messages 表是 UI 展示历史：
    - append-only，永不删除，永不压缩
    - 前端始终从这里读取完整对话记录
    - 与 checkpointer 严格解耦

  这解决了：checkpointer 摘要 → 旧消息消失 → UI 历史被清空 的经典反模式。

【表结构】
  chat_messages(
    id         BIGSERIAL PRIMARY KEY,
    thread_id  TEXT NOT NULL,          -- 会话 ID（与 LangGraph thread_id 对应）
    user_id    TEXT NOT NULL DEFAULT '',  -- 用户 ID（供按用户查询）
    role       TEXT NOT NULL,          -- 'user' | 'assistant'
    content    TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
  )
"""
# AsyncConnectionPool：psycopg3 异步连接池类型注解（pool.connection()/cursor()）
from psycopg_pool import AsyncConnectionPool


async def ensure_table(pool: AsyncConnectionPool) -> None:
    """初次启动时确保 chat_messages 表及索引存在（幂等）。

    【功能 / 流程定位】
      总体流程 ⑫ 的建表步骤，被 graph.py::build_graph 启动时调用一次。
      本函数结束后，chat_messages 表与两个索引必定存在，可安全 append/get。
      下一步：build_graph 继续 compile 图。

    【思路】
      psycopg3 不允许单次 execute 包含多条 SQL，每条语句单独执行。
      用 CREATE TABLE IF NOT EXISTS / CREATE INDEX IF NOT EXISTS 保证幂等（重复启动不报错）。

    参数:
        pool: PostgreSQL 异步连接池
    """
    # 三条 DDL：建表 + 两个索引；IF NOT EXISTS 保证幂等
    statements = [
        # 建表：id 自增主键；thread_id/user_id/role/content 必填；created_at 默认当前时间
        """
        CREATE TABLE IF NOT EXISTS chat_messages (
            id         BIGSERIAL PRIMARY KEY,
            thread_id  TEXT NOT NULL,
            user_id    TEXT NOT NULL DEFAULT '',
            role       TEXT NOT NULL,
            content    TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """,
        # 索引1：按 thread_id + created_at 升序，加速"取某会话按时间正序历史"
        """
        CREATE INDEX IF NOT EXISTS idx_chat_messages_thread
            ON chat_messages (thread_id, created_at ASC)
        """,
        # 索引2：按 user_id + created_at 降序，加速"某用户最近会话"查询
        """
        CREATE INDEX IF NOT EXISTS idx_chat_messages_user
            ON chat_messages (user_id, created_at DESC)
        """,
    ]
    # async with 取一条连接（用完自动归还连接池）
    async with pool.connection() as conn:
        # 在连接上打开游标
        async with conn.cursor() as cur:
            # 逐条执行 DDL（psycopg3 不支持一次 execute 多条）
            for sql in statements:
                await cur.execute(sql)


async def append_message(
    pool: AsyncConnectionPool,
    thread_id: str,
    user_id: str,
    role: str,
    content: str,
) -> None:
    """向 chat_messages 表追加一条消息（append-only）。

    【功能 / 流程定位】
      总体流程 ⑫ 的写入步骤，被 router.py::chat（写 user）和 event_stream finally（写 assistant）调用。
      本函数结束后，chat_messages 表多一条记录，UI 历史更新。
      无"下一个函数"——这是一次写入动作的终点。

    【思路】
      append-only：只 INSERT，不 UPDATE/DELETE，保证 UI 历史永不丢失。
      空内容直接跳过，避免空消息污染历史。
      连接池 autocommit=True，无需手动 commit。

    参数:
        pool:      PostgreSQL 异步连接池
        thread_id: 会话 ID
        user_id:   用户 ID（空则存 ""）
        role:      'user' | 'assistant'
        content:   消息文本
    """
    # 空内容跳过（含纯空白）
    if not content or not content.strip():
        return
    # 取连接
    async with pool.connection() as conn:
        # 开游标
        async with conn.cursor() as cur:
            # 参数化 INSERT：用 %s 占位符防 SQL 注入；content.strip() 去首尾空白
            await cur.execute(
                "INSERT INTO chat_messages (thread_id, user_id, role, content) "
                "VALUES (%s, %s, %s, %s)",
                (thread_id, user_id or "", role, content.strip()),
            )


async def get_messages(
    pool: AsyncConnectionPool,
    thread_id: str,
    limit: int = 200,
) -> list[dict]:
    """获取某会话的完整对话历史（按时间正序）。

    【功能 / 流程定位】
      总体流程 ⑫ 的读取步骤，被 history_router.py::get_history 和 list_conversations 调用。
      本函数结束后，调用方拿到 dict 列表，直接返回给前端或提取标题/最后消息。

    【思路】
      按 thread_id 过滤，created_at 升序（时间正序，符合对话阅读顺序），LIMIT 防超长。
      created_at 转为 ISO 字符串，方便 JSON 序列化返回前端。

    参数:
        pool:      PostgreSQL 异步连接池
        thread_id: 会话 ID
        limit:     最多返回条数（默认 200）

    返回:
        [{"role": "user"|"assistant", "content": "...", "created_at": "ISO时间"}]
    """
    # 取连接
    async with pool.connection() as conn:
        # 开游标
        async with conn.cursor() as cur:
            # 参数化查询：按 thread_id 过滤、时间升序、LIMIT 限流
            await cur.execute(
                "SELECT role, content, created_at FROM chat_messages "
                "WHERE thread_id = %s ORDER BY created_at ASC LIMIT %s",
                (thread_id, limit),
            )
            # fetchall：取全部结果行（dict_row，每行是 dict）
            rows = await cur.fetchall()
    # 组装返回列表
    result = []
    for row in rows:
        result.append({
            "role": row["role"],                                   # 角色
            "content": row["content"],                             # 内容
            # created_at 转 ISO 字符串；空值兜底为 ""
            "created_at": row["created_at"].isoformat() if row.get("created_at") else "",
        })
    # 返回历史列表
    return result
