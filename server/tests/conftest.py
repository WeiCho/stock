"""
測試共用：把 server/ 加進 sys.path 讓測試可以 `import backtest` 等模組。
跑法：cd <repo>; ./.venv/bin/python -m pytest server/tests -v
"""
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
