#!/usr/bin/env bash
#
# 一鍵啟動：自動建立環境，並同時啟動 FastAPI 後端與 React 前端。
#
#   ./start.sh
#
# 首次執行會建立 Python 虛擬環境、安裝後端與前端相依套件（需數分鐘）；
# 之後僅啟動服務。按 Ctrl+C 會一併關閉前後端。
#
# 環境變數：
#   PYTHON=python3.12 ./start.sh   指定 Python 直譯器（預設 python3）

set -euo pipefail
cd "$(dirname "$0")"

PYTHON="${PYTHON:-python3}"
BACKEND_PORT="${BACKEND_PORT:-8000}"

# ── 1) Python 後端環境 ───────────────────────────────
if [ ! -d .venv ]; then
  echo "▶ 建立 Python 虛擬環境並安裝後端相依…"
  "$PYTHON" -m venv .venv
  ./.venv/bin/python -m pip install -q --upgrade pip
  ./.venv/bin/python -m pip install -q -r requirements.txt
fi

# ── 2) 前端相依 ──────────────────────────────────────
if [ ! -d web/node_modules ]; then
  echo "▶ 安裝前端相依（npm install）…"
  (cd web && npm install)
fi

# ── 3) 同時啟動前後端，Ctrl+C 一併關閉 ────────────────
cleanup() {
  trap - INT TERM           # 移除 trap，避免再次觸發自己
  echo
  echo "▶ 關閉前後端…"
  kill "$BACKEND_PID" "$FRONTEND_PID" "$OPEN_PID" 2>/dev/null
  # 等前後端真正結束，輸出才不會蓋在提示字元之後（不必再按 Enter）
  wait "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null
}
trap cleanup INT TERM

echo "▶ 後端  → http://localhost:${BACKEND_PORT}"
echo "▶ 前端  → http://localhost:5173"
echo "（首次查詢個股會下載 10 年歷史，需稍候；按 Ctrl+C 結束）"
echo

PYTHONPATH=server ./.venv/bin/python -m uvicorn server.main:app \
  --host 0.0.0.0 --port "${BACKEND_PORT}" --timeout-graceful-shutdown 3 &
BACKEND_PID=$!

# exec：讓子 shell 直接變成 npm，kill 才能確實把 vite 一起收掉（不留孤兒）
( cd web && exec npm run dev ) &
FRONTEND_PID=$!

# macOS：稍候自動開啟瀏覽器（非 macOS 或無 open 指令則略過）
OPEN_PID=""
if command -v open >/dev/null 2>&1; then
  (sleep 4 && open "http://localhost:5173") &
  OPEN_PID=$!
fi

wait
