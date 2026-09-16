"""AgentEval 运行前环境初始化（与 app.mcp.server 一致）。"""
import builtins
import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent


def bootstrap() -> Path:
    """切换 cwd、设置离线/RAG 环境、重定向 print 到 stderr。"""
    os.chdir(_REPO_ROOT)
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))

    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("SHILLGUARD_DISABLE_RERANK", "1")

    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    _orig_print = builtins.print

    def _print_to_stderr(*args, **kwargs):
        kwargs.setdefault("file", sys.stderr)
        _orig_print(*args, **kwargs)

    builtins.print = _print_to_stderr
    return _REPO_ROOT
