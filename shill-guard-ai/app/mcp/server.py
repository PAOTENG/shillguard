"""ShillGuard MCP Server 入口：注册 tools 并通过 stdio 与 Cursor 通信。

【MCP 启动流程】
  Cursor 读取 .cursor/mcp.json →  spawn 本脚本子进程 → stdio JSON-RPC 通信

【Windows 特殊处理（项目踩坑记录）】
  1. chdir 到项目根：MCP 子进程 cwd 不一定是项目根，相对路径 ./data/chroma 会找不到
  2. HF 离线模式：避免 transformers 联网校验 huggingface.co 超时 70~120s
  3. SHILLGUARD_DISABLE_RERANK=1：无控制台子进程 import torch 会挂死
  4. print → stderr：stdio 模式下 stdout 是 JSON-RPC 通道，print 会破坏协议

【注册 tools】
  import tools_rag / tools_moderation / tools_detect 时 @mcp.tool() 装饰器自动注册

官方: https://modelcontextprotocol.io/
FastMCP: https://github.com/jlowin/fastmcp
"""
import os
import sys
import builtins
from pathlib import Path

# 修复1：切换到项目根目录
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
os.chdir(_PROJECT_ROOT)

# 修复1.5：HuggingFace 强制离线
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["HF_HUB_OFFLINE"] = "1"

# 修复2：MCP 路径跳过本地 torch reranker
os.environ["SHILLGUARD_DISABLE_RERANK"] = "1"

# 修复3：print 重定向到 stderr（stdout 留给 JSON-RPC）
_orig_print = builtins.print


def _print_to_stderr(*args, **kwargs):
    kwargs.setdefault("file", sys.stderr)
    _orig_print(*args, **kwargs)


builtins.print = _print_to_stderr

from app.mcp import mcp
from app.mcp import tools_rag          # noqa: E402,F401  注册 rag_search_laws
from app.mcp import tools_moderation   # noqa: E402,F401  注册 moderate_content
from app.mcp import tools_detect       # noqa: E402,F401  注册 detect_user_score, generate_evidence

if __name__ == "__main__":
    # mcp.run(): 【FastMCP 官方】启动 stdio transport，阻塞直到客户端断开
    mcp.run()
