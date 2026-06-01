"""
美股支援。
- 判斷 ticker（無數字 + 1-5 字母 + 可帶點，如 BRK.A）
- 抓 Yahoo Finance v8 Chart API 寫進 daily_price（跟台股共用 schema）
- Finnhub /search 找美股代碼

寫進 daily_price 後，現有的 technical.analyze / backtest / outlook 全部「自動相容」，
chip 籌碼面會因為 institutional 表無資料自然 degrade。
"""

import logging
import os
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional
import httpx
import ssl

from sqlalchemy import insert, select
from db import DailyPrice, StockName, SyncLog, get_session

log = logging.getLogger("uvicorn.error")
_REPO_ROOT = Path(__file__).resolve().parent.parent

try:
    import certifi
    _SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except Exception:
    _SSL_CTX = ssl.create_default_context()
_SSL_CTX.verify_flags &= ~ssl.VERIFY_X509_STRICT

YAHOO_BASE = "https://query1.finance.yahoo.com/v8/finance/chart"
FINNHUB_BASE = "https://finnhub.io/api/v1"
HEADERS = {"User-Agent": "Mozilla/5.0 (TaiwanStockSkill/1.0)"}


def is_us_stock(symbol: str) -> bool:
    """美股 ticker 識別：1-5 個字母（可帶一個點，如 BRK.A）。
    台股則含數字（2330 / 0050 / 00735）→ 自動排除。"""
    if not symbol:
        return False
    s = symbol.replace(".", "").replace("-", "")
    return 1 <= len(s) <= 5 and s.isalpha()


def _finnhub_key() -> Optional[str]:
    key = os.environ.get("FINNHUB_API_KEY")
    if key:
        return key
    env = _REPO_ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.startswith("FINNHUB_API_KEY="):
                v = line.split("=", 1)[1].strip()
                return v or None
    return None


# ──────────────────────────────────────────────
# 抓 Yahoo → 寫 daily_price
# ──────────────────────────────────────────────

def _fetch_yahoo_us(symbol: str, years: int = 10) -> list[dict]:
    """抓 Yahoo Chart API 的 OHLCV。回 bars list。"""
    if years <= 1: rng = "1y"
    elif years <= 2: rng = "2y"
    elif years <= 5: rng = "5y"
    else: rng = "10y"

    try:
        with httpx.Client(headers=HEADERS, verify=_SSL_CTX, timeout=15) as client:
            resp = client.get(f"{YAHOO_BASE}/{symbol}", params={
                "range": rng, "interval": "1d",
            })
            resp.raise_for_status()
            payload = resp.json()
    except Exception as e:
        log.warning("Yahoo Finance %s 抓取失敗：%s", symbol, e)
        return []

    result = (payload.get("chart") or {}).get("result") or []
    if not result:
        return []
    r = result[0]
    ts = r.get("timestamp") or []
    q = ((r.get("indicators") or {}).get("quote") or [{}])[0]
    closes = q.get("close") or []
    opens = q.get("open") or []
    highs = q.get("high") or []
    lows = q.get("low") or []
    vols = q.get("volume") or []

    bars = []
    for i, t in enumerate(ts):
        if i >= len(closes) or closes[i] is None:
            continue
        d = datetime.fromtimestamp(t).date()
        bars.append({
            "date": d,
            "open": float(opens[i] or closes[i]),
            "high": float(highs[i] or closes[i]),
            "low": float(lows[i] or closes[i]),
            "close": float(closes[i]),
            "volume": float(vols[i] or 0) / 1000,  # 跟台股一致用「張」（1000 股）
        })
    return bars


def ensure_us_stock_data(symbol: str, years: int = 10) -> int:
    """抓美股歷史 K 線寫進 daily_price + 註冊 stock_names。已有 sync_log 則跳過。
    回傳新增筆數。"""
    sym = symbol.upper()

    # 已同步過今天就跳過（避免重複抓）
    with get_session() as session:
        sync = session.execute(
            select(SyncLog).where(SyncLog.symbol == sym, SyncLog.data_type == "price")
        ).scalar_one_or_none()
        if sync and (datetime.utcnow() - sync.last_synced).days < 1:
            return 0

    bars = _fetch_yahoo_us(sym, years=years)
    if not bars:
        return 0

    with get_session() as session:
        existing_dates = set(session.execute(
            select(DailyPrice.date).where(DailyPrice.symbol == sym)
        ).scalars().all())

        new_rows = [
            {"symbol": sym, "date": b["date"], "open": b["open"], "high": b["high"],
             "low": b["low"], "close": b["close"], "volume": b["volume"]}
            for b in bars if b["date"] not in existing_dates
        ]

        if new_rows:
            session.execute(insert(DailyPrice).prefix_with("OR IGNORE"), new_rows)

        # 註冊 stock_names — 用 Finnhub 抓公司全名（如 "Apple Inc"），抓不到才退回 ticker
        name_row = session.execute(
            select(StockName).where(StockName.symbol == sym)
        ).scalar_one_or_none()
        if not name_row:
            company_name = fetch_company_name(sym) or sym
            session.add(StockName(symbol=sym, name=company_name, market="us"))
        elif name_row.name == sym:
            # 已存在但 name 仍是 symbol（舊資料）→ 補抓公司全名
            real_name = fetch_company_name(sym)
            if real_name:
                name_row.name = real_name

        # sync_log
        sync_row = session.execute(
            select(SyncLog).where(SyncLog.symbol == sym, SyncLog.data_type == "price")
        ).scalar_one_or_none()
        if sync_row:
            sync_row.last_synced = datetime.utcnow()
        else:
            session.add(SyncLog(symbol=sym, data_type="price", last_synced=datetime.utcnow()))

        session.commit()
        return len(new_rows)


# ──────────────────────────────────────────────
# Finnhub search → 找美股代碼
# ──────────────────────────────────────────────

def search_us(query: str, limit: int = 8) -> list[dict]:
    """用 Finnhub /search 找美股 ticker。回 [{symbol, name, market: 'us'}]。"""
    key = _finnhub_key()
    if not key:
        return []
    try:
        with httpx.Client(verify=_SSL_CTX, timeout=8) as client:
            resp = client.get(f"{FINNHUB_BASE}/search", params={
                "q": query, "token": key, "exchange": "US",
            })
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        log.warning("Finnhub search %s 失敗：%s", query, e)
        return []

    results = data.get("result") or []
    out = []
    for r in results:
        sym = r.get("symbol", "")
        # 只要 Common Stock，過濾 ADR / Warrant / Note
        if r.get("type") not in ("Common Stock", "ADR"):
            continue
        if "." in sym or len(sym) > 5:  # 過 BRK.A 之類非主流
            continue
        out.append({
            "symbol": sym,
            "name": r.get("description", sym),
            "market": "us",
        })
        if len(out) >= limit:
            break
    return out


# ──────────────────────────────────────────────
# Helper：更新 stock name（公司全名）
# ──────────────────────────────────────────────

def fetch_company_name(symbol: str) -> Optional[str]:
    """Finnhub /stock/profile2 拿公司全名。失敗回 None。"""
    key = _finnhub_key()
    if not key:
        return None
    try:
        with httpx.Client(verify=_SSL_CTX, timeout=8) as client:
            resp = client.get(f"{FINNHUB_BASE}/stock/profile2",
                              params={"symbol": symbol.upper(), "token": key})
            resp.raise_for_status()
            data = resp.json()
        return data.get("name") or None
    except Exception:
        return None
