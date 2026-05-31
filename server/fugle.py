"""
Fugle Market Data：盤中即時報價 / 逐筆成交，用來偵測「大單敲進」。

Token 由環境變數 FUGLE_API_KEY 提供（亦會從專案根目錄 .env 讀取）。
逐筆 /intraday/trades 一次回最近 ~500 筆；盤中輪詢即可即時抓到大單，
非交易時段則回最後一盤的成交。收盤集合競價（serial 99999999）會排除。
"""

import asyncio
import logging
import os
import ssl
from datetime import datetime, timezone, timedelta
from pathlib import Path
import httpx

log = logging.getLogger("uvicorn.error")

FUGLE_BASE = "https://api.fugle.tw/marketdata/v1.0/stock"
_REPO_ROOT = Path(__file__).resolve().parent.parent
_AUCTION_SERIAL = 99999999
_TW = timezone(timedelta(hours=8))


def _tw_hhmm(epoch_us) -> int | None:
    """epoch 微秒 → 台北時間的 HHMM（例如 930 = 09:30）。"""
    try:
        dt = datetime.fromtimestamp(epoch_us / 1_000_000, _TW)
        return dt.hour * 100 + dt.minute
    except Exception:
        return None


def _tw_time_str(epoch_us) -> str | None:
    """epoch 微秒 → 台北時間 HH:MM:SS（即時報價時戳顯示用）。"""
    try:
        return datetime.fromtimestamp(epoch_us / 1_000_000, _TW).strftime("%H:%M:%S")
    except Exception:
        return None

try:
    import certifi
    _SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except Exception:
    _SSL_CTX = ssl.create_default_context()
_SSL_CTX.verify_flags &= ~ssl.VERIFY_X509_STRICT


def _api_key() -> str | None:
    key = os.environ.get("FUGLE_API_KEY")
    if key:
        return key
    env = _REPO_ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.startswith("FUGLE_API_KEY="):
                return line.split("=", 1)[1].strip()
    return None


def available() -> bool:
    return bool(_api_key())


def _big_from_trades(data: dict, min_amount: int) -> list[dict]:
    """從逐筆資料挑出大單：排除集合競價（serial 99999999）與開盤(09:00)/收盤(>=13:25)時段。"""
    out = []
    for t in (data.get("data") or []):
        if t.get("serial") == _AUCTION_SERIAL:
            continue
        hm = _tw_hhmm(t.get("time"))
        if hm is None or hm <= 900 or hm >= 1325:  # 只取盤中連續交易
            continue
        size = t.get("size") or 0       # 張
        price = t.get("price") or 0     # 元
        amount = size * price * 1000    # 1 張 = 1000 股
        if amount >= min_amount:
            out.append({"price": price, "size": size, "amount": round(amount), "time": t.get("time")})
    return out


async def _scan_one(client: httpx.AsyncClient, symbol: str, min_amount: int, per_symbol: int):
    try:
        resp = await client.get(f"{FUGLE_BASE}/intraday/trades/{symbol}", params={"limit": 1000})
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        log.info("Fugle trades %s 抓取失敗（跳過該股，不影響全市場掃描）：%s", symbol, e)
        return None
    bigs = _big_from_trades(data, min_amount)
    if not bigs:
        return None
    bigs.sort(key=lambda x: -x["amount"])
    return {
        "symbol": symbol, "count": len(bigs),
        "max_amount": bigs[0]["amount"], "max_size": bigs[0]["size"], "price": bigs[0]["price"],
        "trades": bigs[:per_symbol],
    }


async def intraday_candles(symbol: str, timeframe: str = "5") -> dict | None:
    """Fugle 盤中分鐘 K（stock 或大盤 IX0001）。timeframe: '1'/'5'/'10'/'15'/'30'/'60'。
    並行抓 candles + quote → 回傳合併（data + previousClose 等）。
    candles 抓不到才回 None；quote 失敗只是少了昨收，candles 仍會回傳。
    所有失敗都會 log，方便除錯 Fugle 端問題（401/429/5xx 等）。
    """
    key = _api_key()
    if not key:
        log.warning("Fugle: 未設定 FUGLE_API_KEY，無法取得盤中資料")
        return None
    async with httpx.AsyncClient(timeout=8, verify=_SSL_CTX, headers={"X-API-KEY": key}) as client:
        async def _candles():
            r = await client.get(f"{FUGLE_BASE}/intraday/candles/{symbol}",
                                 params={"timeframe": timeframe})
            r.raise_for_status()
            return r.json()
        async def _quote():
            r = await client.get(f"{FUGLE_BASE}/intraday/quote/{symbol}")
            r.raise_for_status()
            return r.json()
        # return_exceptions=True：quote 失敗不影響 candles
        candles, quote = await asyncio.gather(_candles(), _quote(), return_exceptions=True)
    if isinstance(candles, Exception):
        # candles 抓不到是真失敗，記錄狀態碼/錯誤訊息
        if isinstance(candles, httpx.HTTPStatusError):
            body = candles.response.text[:200].replace("\n", " ").replace("\r", " ")
            log.warning("Fugle candles %s 失敗 HTTP %s：%s",
                        symbol, candles.response.status_code, body)
        else:
            log.warning("Fugle candles %s 失敗：%s", symbol, candles)
        return None
    # quote 是錦上添花，失敗就 log 但 candles 還是回傳
    if isinstance(quote, Exception):
        log.info("Fugle quote %s 失敗（candles 仍可用）：%s", symbol, quote)
        quote = None
    # quote 欄位：previousClose / openPrice / closePrice / highPrice / lowPrice / change / changePercent
    if quote:
        for k in ("previousClose", "openPrice", "closePrice", "highPrice", "lowPrice", "change", "changePercent"):
            v = quote.get(k)
            if v is not None:
                candles[k] = v
    return candles


def _shape_quote(symbol: str, q: dict) -> dict:
    """把 Fugle /intraday/quote 原始回應整理成精簡的即時報價（含五檔）。純函式，方便測試。"""
    total = q.get("total") or {}

    def _levels(side: str) -> list[dict]:
        return [{"price": x.get("price"), "size": x.get("size")} for x in (q.get(side) or [])]

    return {
        "symbol": symbol,
        "last": q.get("lastPrice") if q.get("lastPrice") is not None else q.get("closePrice"),
        "previousClose": q.get("previousClose"),
        "open": q.get("openPrice"),
        "high": q.get("highPrice"),
        "low": q.get("lowPrice"),
        "avg": q.get("avgPrice"),
        "change": q.get("change"),
        "change_pct": q.get("changePercent"),
        "volume": total.get("tradeVolume"),
        "bids": _levels("bids"),
        "asks": _levels("asks"),
        "time": _tw_time_str(q.get("lastUpdated")),
    }


async def quote(symbol: str) -> dict | None:
    """個股 / ETF 即時報價快照（Fugle /intraday/quote，含五檔）。盤中即時、收盤後回最後一盤。
    ETF 與一般個股是同一組 endpoint，無需特殊處理。失敗回 None（含狀態碼 log）。"""
    key = _api_key()
    if not key:
        log.warning("Fugle: 未設定 FUGLE_API_KEY，無法取得即時報價")
        return None
    try:
        async with httpx.AsyncClient(timeout=6, verify=_SSL_CTX,
                                     headers={"X-API-KEY": key}) as client:
            r = await client.get(f"{FUGLE_BASE}/intraday/quote/{symbol}")
            r.raise_for_status()
            raw = r.json()
    except httpx.HTTPStatusError as e:
        body = e.response.text[:200].replace("\n", " ").replace("\r", " ")
        log.warning("Fugle quote %s 失敗 HTTP %s：%s", symbol, e.response.status_code, body)
        return None
    except Exception as e:
        log.warning("Fugle quote %s 失敗：%s", symbol, e)
        return None
    return _shape_quote(symbol, raw)


async def scan_big_orders(symbols: list[str], min_amount: int = 30_000_000,
                          per_symbol: int = 3) -> list[dict]:
    """並行掃描多檔的逐筆大單（async：可取消、快）。回傳有大單的個股，依最大單金額排序。"""
    key = _api_key()
    if not key or not symbols:
        return []
    async with httpx.AsyncClient(timeout=6, verify=_SSL_CTX, headers={"X-API-KEY": key}) as client:
        res = await asyncio.gather(*[_scan_one(client, s, min_amount, per_symbol) for s in symbols])
    out = [r for r in res if r]
    out.sort(key=lambda x: -x["max_amount"])
    return out
