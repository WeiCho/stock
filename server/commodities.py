"""
期貨 / 國際商品（黃金、原油）。

資料來源：
  - 台指期 / 小台 / 電子 / 金融期：FinMind TaiwanFuturesDaily
  - 三大法人留倉：FinMind TaiwanFuturesInstitutionalInvestors
  - 黃金 / 原油（USD）：Yahoo Finance v8 Chart API（不用 API key）

回傳結構與 /stock/{symbol}/price 對齊（{symbol, tf, data: Bar[]}），
讓前端 PriceChart 可以原樣重用。

不寫 SQLite（每天才更新一次，5 min in-memory cache 已夠用）。
"""

import logging
import ssl
from datetime import datetime, timedelta, timezone
from typing import Optional
import httpx

log = logging.getLogger("uvicorn.error")

# OpenSSL3 / Python 3.14：與其他模組一致放寬 X509_STRICT
try:
    import certifi
    _SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except Exception:
    _SSL_CTX = ssl.create_default_context()
_SSL_CTX.verify_flags &= ~ssl.VERIFY_X509_STRICT

FINMIND_BASE = "https://api.finmindtrade.com/api/v4/data"
YAHOO_BASE = "https://query1.finance.yahoo.com/v8/finance/chart"
HEADERS = {"User-Agent": "Mozilla/5.0 (TaiwanStockSkill/1.0)"}

# 支援符號表 — symbol → {label, source, params}
SUPPORTED: dict[str, dict] = {
    # 台股期貨（FinMind）
    "TX":  {"label": "台指期",   "source": "finmind", "data_id": "TX"},
    "MTX": {"label": "小台",     "source": "finmind", "data_id": "MTX"},
    "TE":  {"label": "電子期",   "source": "finmind", "data_id": "TE"},
    "TF":  {"label": "金融期",   "source": "finmind", "data_id": "TF"},
    # 國際商品（Yahoo Finance）
    "GC":  {"label": "黃金",     "source": "yahoo", "yahoo_id": "GC=F",      "currency": "USD"},
    "CL":  {"label": "原油WTI",  "source": "yahoo", "yahoo_id": "CL=F",      "currency": "USD"},
    "SI":  {"label": "白銀",     "source": "yahoo", "yahoo_id": "SI=F",      "currency": "USD"},
    "HG":  {"label": "銅",       "source": "yahoo", "yahoo_id": "HG=F",      "currency": "USD"},
    "XAUUSD": {"label": "黃金現貨", "source": "yahoo", "yahoo_id": "XAUUSD=X", "currency": "USD"},
    # 總體經濟指標（Yahoo Finance）
    "DXY":   {"label": "美元指數",    "source": "yahoo", "yahoo_id": "DX-Y.NYB", "currency": "INDEX"},
    "SPX":   {"label": "S&P 500",     "source": "yahoo", "yahoo_id": "^GSPC",    "currency": "USD"},
    "NDX":   {"label": "那斯達克",    "source": "yahoo", "yahoo_id": "^IXIC",    "currency": "USD"},
    "DJI":   {"label": "道瓊",        "source": "yahoo", "yahoo_id": "^DJI",     "currency": "USD"},
    "VIX":   {"label": "VIX 恐慌",    "source": "yahoo", "yahoo_id": "^VIX",     "currency": "INDEX"},
    "TNX":   {"label": "美10年公債",  "source": "yahoo", "yahoo_id": "^TNX",     "currency": "%"},  # Yahoo 已 × 10
    "FVX":   {"label": "美5年公債",   "source": "yahoo", "yahoo_id": "^FVX",     "currency": "%"},
    "BTC":   {"label": "比特幣",      "source": "yahoo", "yahoo_id": "BTC-USD",  "currency": "USD"},
    "ETH":   {"label": "以太幣",      "source": "yahoo", "yahoo_id": "ETH-USD",  "currency": "USD"},
}

# 5 分鐘 in-memory cache：key 為 f"{symbol}:{range}"
_CACHE: dict[str, tuple[datetime, dict]] = {}
_CACHE_TTL = timedelta(minutes=5)


def _cache_get(key: str) -> Optional[dict]:
    entry = _CACHE.get(key)
    if not entry:
        return None
    ts, value = entry
    if datetime.now(timezone.utc) - ts > _CACHE_TTL:
        return None
    return value


def _cache_set(key: str, value: dict) -> None:
    _CACHE[key] = (datetime.now(timezone.utc), value)


# ──────────────────────────────────────────────
# 來源 1：FinMind 台股期貨
# ──────────────────────────────────────────────

def _fetch_finmind_futures(data_id: str, days: int) -> list[dict]:
    """抓 N 天台股期貨日K。同一日多個合約 → 取最大成交量者（近月／最活躍）。"""
    start = (datetime.now(timezone.utc).date() - timedelta(days=days)).isoformat()
    try:
        with httpx.Client(headers=HEADERS, verify=_SSL_CTX, timeout=15) as client:
            resp = client.get(FINMIND_BASE, params={
                "dataset": "TaiwanFuturesDaily",
                "data_id": data_id,
                "start_date": start,
            })
            resp.raise_for_status()
            rows = resp.json().get("data", [])
    except Exception as e:
        log.warning("FinMind 期貨 %s 抓取失敗：%s", data_id, e)
        return []

    # 過濾盤後 + 同日取最大成交量合約（=最活躍 ≈ 近月）
    by_date: dict[str, dict] = {}
    for r in rows:
        if r.get("trading_session") and r["trading_session"] != "position":
            continue
        if (r.get("volume") or 0) == 0:
            continue
        d = r["date"]
        if d not in by_date or r["volume"] > by_date[d]["volume"]:
            by_date[d] = r

    bars = []
    for d in sorted(by_date.keys()):
        r = by_date[d]
        bars.append({
            "date": d,
            "open": float(r.get("open") or 0),
            "high": float(r.get("max") or 0),
            "low": float(r.get("min") or 0),
            "close": float(r.get("close") or 0),
            "volume": int(r.get("volume") or 0),
        })
    return bars


# ──────────────────────────────────────────────
# 來源 2：Yahoo Finance 國際商品
# ──────────────────────────────────────────────

def _fetch_yahoo_chart(yahoo_id: str, days: int, interval: str = "1d") -> tuple[list[dict], dict]:
    """Yahoo Finance v8 Chart API。回傳 (bars, meta)，失敗回 ([], {})。
    interval='5m' / '15m' 等盤中時，自動把 range 切到 '1d' / '5d'（Yahoo 對 intraday 限資料量）。"""
    # 盤中 interval：用較短 range
    if interval != "1d":
        rng = "1d" if interval in ("1m", "2m", "5m") else "5d"
    elif days <= 1:    rng = "1d"
    elif days <= 5:  rng = "5d"
    elif days <= 30: rng = "1mo"
    elif days <= 90: rng = "3mo"
    elif days <= 180: rng = "6mo"
    elif days <= 365: rng = "1y"
    elif days <= 730: rng = "2y"
    elif days <= 1825: rng = "5y"
    else: rng = "10y"

    try:
        with httpx.Client(headers=HEADERS, verify=_SSL_CTX, timeout=15) as client:
            resp = client.get(f"{YAHOO_BASE}/{yahoo_id}", params={
                "range": rng, "interval": interval,
            })
            resp.raise_for_status()
            payload = resp.json()
    except Exception as e:
        log.warning("Yahoo Finance %s (%s) 抓取失敗：%s", yahoo_id, interval, e)
        return [], {}

    result = (payload.get("chart") or {}).get("result") or []
    if not result:
        return [], {}
    r = result[0]
    meta = r.get("meta") or {}
    ts = r.get("timestamp") or []
    q = ((r.get("indicators") or {}).get("quote") or [{}])[0]
    closes = q.get("close") or []
    opens = q.get("open") or []
    highs = q.get("high") or []
    lows = q.get("low") or []
    vols = q.get("volume") or []

    # intraday：保留完整 ISO datetime 給前端畫 HH:MM 軸；日線：只取日期
    intraday = interval != "1d"
    bars = []
    for i, t in enumerate(ts):
        if i >= len(closes) or closes[i] is None:
            continue
        dt = datetime.fromtimestamp(t, tz=timezone.utc)
        d = dt.isoformat() if intraday else dt.date().isoformat()
        bars.append({
            "date": d,
            "open": float(opens[i] or closes[i]),
            "high": float(highs[i] or closes[i]),
            "low": float(lows[i] or closes[i]),
            "close": float(closes[i]),
            "volume": int(vols[i] or 0),
        })
    return bars, meta


# ──────────────────────────────────────────────
# 對外：取得單一商品的 K 線（自動路由到對應來源 + cache）
# ──────────────────────────────────────────────

def fetch_history(symbol: str, days: int = 365, tf: str = "1d") -> dict:
    """回傳 {symbol, label, data: Bar[], previousClose, currency, tf}。
    tf 支援：
      - 'intraday'：當日 5 分鐘 K（Yahoo only；FinMind 期貨無 intraday → 回錯誤）
      - '1d'（預設）：日線
      - '3d' / '5d' / '1w' / '2w' / '3w' / '1mo'：日線重採樣（用 data_fetcher.resample_ohlc）
    """
    if symbol not in SUPPORTED:
        return {"error": f"不支援的商品 '{symbol}'，可用：{list(SUPPORTED)}"}

    cache_key = f"{symbol}:{tf}:{days}"
    cached = _cache_get(cache_key)
    if cached:
        return cached

    info = SUPPORTED[symbol]
    label = info["label"]
    out: dict = {"symbol": symbol, "label": label, "tf": tf}

    # ── 盤中 intraday：Yahoo only，固定 5min interval ──
    if tf == "intraday":
        if info["source"] != "yahoo":
            return {"error": f"{symbol} 無盤中資料（FinMind 期貨無 intraday；需 Fugle 期貨 plan）"}
        bars, meta = _fetch_yahoo_chart(info["yahoo_id"], days=1, interval="5m")
        out["data"] = bars
        out["currency"] = meta.get("currency") or info.get("currency", "USD")
        out["previousClose"] = meta.get("chartPreviousClose") or meta.get("previousClose")
        out["regularMarketPrice"] = meta.get("regularMarketPrice")
        if out.get("data"):
            _cache_set(cache_key, out)
        return out

    # ── 一般日線（或從日線 resample 出 3d/5d/週/月）──
    if info["source"] == "finmind":
        bars = _fetch_finmind_futures(info["data_id"], days)
        out["currency"] = "TWD"
    else:
        bars, meta = _fetch_yahoo_chart(info["yahoo_id"], days)
        out["currency"] = meta.get("currency") or info.get("currency", "USD")
        out["regularMarketPrice"] = meta.get("regularMarketPrice")
        if meta.get("chartPreviousClose") is not None:
            out["previousClose"] = meta.get("chartPreviousClose")

    # 重採樣（3d / 5d / 1w / 2w / 3w / 1mo）
    if tf not in ("1d", None) and bars:
        import pandas as pd
        from data_fetcher import resample_ohlc
        df = pd.DataFrame(bars).set_index("date")
        df.index = pd.to_datetime(df.index)
        bars = resample_ohlc(df, tf).reset_index().rename(columns={"index": "date"})
        bars["date"] = pd.to_datetime(bars["date"]).dt.strftime("%Y-%m-%d")
        bars = bars.to_dict(orient="records")

    out["data"] = bars
    # 日線模式才用前一根當 previousClose（intraday 已單獨處理）
    if "previousClose" not in out and len(bars) >= 2:
        out["previousClose"] = bars[-2]["close"]

    if out.get("data"):
        _cache_set(cache_key, out)
    return out


# ──────────────────────────────────────────────
# 期貨三大法人留倉
# ──────────────────────────────────────────────

def fetch_institutional(symbol: str = "TX", days: int = 30) -> dict:
    """三大法人在期貨的「未平倉口數」(long_open_interest - short_open_interest)。
    回傳 {symbol, data: [{date, foreign_net, trust_net, dealer_net}]}。"""
    if symbol not in SUPPORTED or SUPPORTED[symbol]["source"] != "finmind":
        return {"error": f"{symbol} 不是 FinMind 期貨符號"}

    start = (datetime.now(timezone.utc).date() - timedelta(days=days)).isoformat()
    try:
        with httpx.Client(headers=HEADERS, verify=_SSL_CTX, timeout=15) as client:
            resp = client.get(FINMIND_BASE, params={
                "dataset": "TaiwanFuturesInstitutionalInvestors",
                "data_id": symbol, "start_date": start,
            })
            resp.raise_for_status()
            rows = resp.json().get("data", [])
    except Exception as e:
        log.warning("FinMind 期貨法人 %s 抓取失敗：%s", symbol, e)
        return {"symbol": symbol, "data": []}

    # 三大法人 ID 對應：外資 / 投信 / 自營商
    KEY_MAP = {"外資": "foreign", "投信": "trust", "自營商": "dealer"}
    by_date: dict[str, dict] = {}
    for r in rows:
        d = r.get("date")
        who = KEY_MAP.get(r.get("institutional_investors", ""))
        if not d or not who:
            continue
        net = (r.get("long_open_interest_balance_volume") or 0) - (r.get("short_open_interest_balance_volume") or 0)
        by_date.setdefault(d, {"date": d})[f"{who}_net"] = net

    return {
        "symbol": symbol, "label": SUPPORTED[symbol]["label"],
        "data": [by_date[d] for d in sorted(by_date)],
    }


# ──────────────────────────────────────────────
# 績效摘要（模仿 TradingView XAUUSD 那頁的 1d/5d/1m/6m/YTD/1y/5y/10y）
# ──────────────────────────────────────────────

def perf_summary(bars: list[dict]) -> dict:
    """從日K 序列計算各時間區段的累積報酬率（%）。"""
    if len(bars) < 2:
        return {}
    last = bars[-1]["close"]
    today = datetime.fromisoformat(bars[-1]["date"]).date()
    targets = {
        "1d": 1, "5d": 5, "1mo": 30, "6mo": 180,
        "ytd": (today - today.replace(month=1, day=1)).days,
        "1y": 365, "5y": 365 * 5, "10y": 365 * 10,
    }
    out = {}
    for label, lookback_days in targets.items():
        if lookback_days <= 0:
            continue
        target_date = today - timedelta(days=lookback_days)
        # 找最接近 target_date 的歷史 bar
        base = next((b for b in bars if datetime.fromisoformat(b["date"]).date() >= target_date), None)
        if base and base["close"] > 0:
            out[label] = round((last - base["close"]) / base["close"] * 100, 2)
    return out
