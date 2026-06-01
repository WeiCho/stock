#!/usr/bin/env bash
#
# 交易時段自動擷取即時報價（給 crontab 用）。輸出附加到 log 檔。
# 只在台北平日 09:00–13:30 執行；後端沒跑就自己起一個、擷取完關掉（不動已在跑的後端）。
#
# 安裝（每分鐘檢查，交易時段內只在 10:00 那次真正擷取 — 見 crontab 設定）：
#   crontab 範例： 0 10 * * 1-5 /Users/greg/Desktop/Personal/stock/scripts/cron_capture.sh
#
# 注意：macOS 若在排程時間「睡眠」cron 不會觸發；終端機/ cron 可能需要「完全磁碟取用」權限。

set -u
cd "$(dirname "$0")/.." || exit 1
REPO="$(pwd)"
PY="$REPO/.venv/bin/python"
LOG="${LIVE_CAPTURE_LOG:-/tmp/live_quotes_capture.log}"

# 交易時段檢查（台北平日 09:00–13:30）
HM=$(( 10#$(TZ=Asia/Taipei date +%H%M) ))
DOW=$(TZ=Asia/Taipei date +%u)
if [ "$DOW" -gt 5 ] || [ "$HM" -lt 900 ] || [ "$HM" -gt 1330 ]; then
  exit 0
fi

echo "===== $(TZ=Asia/Taipei date '+%F %T %Z') 擷取開始 =====" >> "$LOG"
STARTED=""
if [ "$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/health 2>/dev/null)" != "200" ]; then
  PYTHONPATH="$REPO/server" "$PY" -m uvicorn server.main:app --host 127.0.0.1 --port 8000 >> "$LOG" 2>&1 &
  STARTED=$!
  for _ in $(seq 1 20); do
    [ "$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/health 2>/dev/null)" = "200" ] && break
    sleep 1
  done
fi

"$PY" "$REPO/scripts/capture_live_quotes.py" --duration 60 >> "$LOG" 2>&1

[ -n "$STARTED" ] && kill "$STARTED" 2>/dev/null
echo "===== 擷取結束 =====" >> "$LOG"
