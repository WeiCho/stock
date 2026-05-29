#!/usr/bin/env python3
"""
擷取多檔即時報價 — 驗證 Fugle WS streamer（/ws/quotes）是否真的在跳動。

需先把後端跑起來（./start.sh，或 PYTHONPATH=server uvicorn server.main:app ...）。
然後：
    ./.venv/bin/python scripts/capture_live_quotes.py
    ./.venv/bin/python scripts/capture_live_quotes.py --symbols 2330,0050,2454 --duration 90

連到後端 /ws/quotes，訂閱 ≤5 檔，把每一筆報價更新依時間印出，結束時列出每檔的
更新次數 + 首/末價。交易時段（週一~五 09:00–13:30 台北）會看到價格連續跳動 = 真的有
live ticks；盤後/週末則每檔只收到一筆 snapshot（最後一盤）。
"""
import argparse
import asyncio
import json
from datetime import datetime, timezone, timedelta

import websockets

TW = timezone(timedelta(hours=8))
DEFAULT_SYMBOLS = ["2330", "0050", "2317", "2454", "2412"]


def _trading_now() -> bool:
    now = datetime.now(TW)
    if now.weekday() >= 5:  # 週末
        return False
    hm = now.hour * 100 + now.minute
    return 900 <= hm <= 1330


async def run(url: str, symbols: list[str], duration: int) -> None:
    now_tw = datetime.now(TW)
    print(f"連線 {url}")
    print(f"訂閱 {symbols}（Fugle 免費上限 5）｜擷取 {duration}s｜"
          f"台北現在 {now_tw:%Y-%m-%d %H:%M:%S}（交易時段：{'是' if _trading_now() else '否'}）")
    print("-" * 70)
    counts = {s: 0 for s in symbols}
    first: dict[str, object] = {}
    last: dict[str, object] = {}
    try:
        async with websockets.connect(url) as ws:
            await ws.send(json.dumps({"action": "subscribe", "symbols": symbols[:5]}))
            loop = asyncio.get_event_loop()
            end = loop.time() + duration
            while loop.time() < end:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=max(1.0, end - loop.time()))
                except asyncio.TimeoutError:
                    break
                msg = json.loads(raw)
                if msg.get("event") == "error":
                    print("伺服器錯誤：", msg.get("message"))
                    return
                if msg.get("event") != "quote":
                    continue
                q = msg.get("quote") or {}
                sym = q.get("symbol")
                if sym not in counts:
                    continue
                counts[sym] += 1
                first.setdefault(sym, q.get("last"))
                last[sym] = q.get("last")
                b1 = (q.get("bids") or [{}])[0].get("price", "—")
                a1 = (q.get("asks") or [{}])[0].get("price", "—")
                pct = q.get("change_pct")
                ts = datetime.now(TW).strftime("%H:%M:%S")
                print(f"[{ts}] {sym:<7} last={str(q.get('last')):<10} "
                      f"chg={pct}%  買1={b1} 賣1={a1}")
    except Exception as e:
        print("client error:", repr(e))
        return

    print("-" * 70)
    print("摘要（更新次數 / 首價 → 末價）：")
    for s in symbols:
        moved = "" if first.get(s) == last.get(s) else "  ← 有跳動"
        print(f"  {s:<7} 更新 {counts[s]:>3} 次   {first.get(s)} → {last.get(s)}{moved}")
    total = sum(counts.values())
    moved = any(s in last and first.get(s) != last.get(s) for s in symbols)
    print("-" * 70)
    if moved:
        print("✅ 價格有跳動 = LIVE TICKS 流動中。")
    elif total:
        print("ℹ️ 有收到報價但價格未變動（盤後/週末顯示最後一盤，或當下無成交）；交易時段再跑可看到連續跳動。")
    else:
        print("⚠️ 沒收到任何報價 — 確認後端已啟動且 FUGLE_API_KEY 已設定。")


def main() -> None:
    ap = argparse.ArgumentParser(description="擷取多檔即時報價（驗證 Fugle WS streamer）")
    ap.add_argument("--url", default="ws://127.0.0.1:8000/ws/quotes")
    ap.add_argument("--symbols", default=",".join(DEFAULT_SYMBOLS), help="逗號分隔，≤5 檔")
    ap.add_argument("--duration", type=int, default=60, help="擷取秒數")
    a = ap.parse_args()
    syms = [s.strip() for s in a.symbols.split(",") if s.strip()][:5]
    asyncio.run(run(a.url, syms, a.duration))


if __name__ == "__main__":
    main()
