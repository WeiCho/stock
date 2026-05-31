"""
全市場「今日動態」— 成交額/漲跌幅 ranking。

資料源：TWSE STOCK_DAY_ALL（上市，~1100 支）+ TPEx OpenAPI（上櫃，~800 支），
直接從原始 endpoint 抓盤後資料，5 分鐘 cache。

注意：盤中 TWSE 不提供「全市場 + 漲跌幅」公開 endpoint（要付費 MIS），所以這個
資料是 T+0（當日收盤後 ~16:00 才有），盤中查到的是「昨日資料」。
"""

import logging
import ssl
from datetime import datetime, timedelta
import httpx

log = logging.getLogger("uvicorn.error")

try:
    import certifi
    _SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except Exception:
    _SSL_CTX = ssl.create_default_context()
_SSL_CTX.verify_flags &= ~ssl.VERIFY_X509_STRICT

TWSE_URL = "https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL"
HEADERS = {"User-Agent": "Mozilla/5.0 (TaiwanStockSkill/1.0)"}

_CACHE: dict[str, tuple[datetime, tuple[list[dict], str]]] = {}
_CACHE_TTL = timedelta(minutes=5)


def _roc_to_ad(d: str) -> str:
    """民國 YYYMMDD → 西元 YYYY-MM-DD（無法解析回空字串）。"""
    d = str(d)
    if len(d) == 7:
        return f"{int(d[:3]) + 1911}-{d[3:5]}-{d[5:7]}"
    return ""


def _parse_float(s: str) -> float | None:
    if not s or s in ("--", "—"):
        return None
    try:
        return float(str(s).replace(",", ""))
    except (ValueError, TypeError):
        return None


def _fetch_all_stocks() -> tuple[list[dict], str]:
    """抓 TWSE 全市場日資料，normalize 成統一 dict。回 (rows, 西元日期)。"""
    cached = _CACHE.get("twse_all")
    if cached and (datetime.now() - cached[0]) < _CACHE_TTL:
        return cached[1]

    try:
        with httpx.Client(headers=HEADERS, verify=_SSL_CTX, timeout=20) as client:
            resp = client.get(TWSE_URL)
            resp.raise_for_status()
            raw = resp.json()
    except Exception as e:
        log.warning("TWSE STOCK_DAY_ALL 抓取失敗：%s", e)
        return [], ""

    # 日期取自原始 payload 第 1 筆（TWSE 用民國年 YYYMMDD），與 rows 一起 cache，
    # 避免之後為了拿日期再打一次 API。
    date = _roc_to_ad(raw[0].get("Date", "")) if raw else ""

    out = []
    for r in raw:
        code = str(r.get("Code", "")).strip()
        # 只保留 4-5 位純數字代碼（過濾 ETF / 權證 等非主要股票）
        if not code.isdigit() or len(code) not in (4, 5):
            continue
        close = _parse_float(r.get("ClosingPrice"))
        change = _parse_float(r.get("Change"))
        if close is None or change is None or close == 0:
            continue
        change_pct = round(change / (close - change) * 100, 2) if (close - change) != 0 else 0
        out.append({
            "symbol": code,
            "name": r.get("Name", "").strip(),
            "close": close,
            "change": change,
            "change_pct": change_pct,
            "volume": _parse_float(r.get("TradeVolume")) or 0,  # 股
            "trade_value": _parse_float(r.get("TradeValue")) or 0,  # 元
            "transactions": int(_parse_float(r.get("Transaction")) or 0),
        })

    _CACHE["twse_all"] = (datetime.now(), (out, date))
    return out, date


def market_movers(top_n: int = 10) -> dict:
    """回 {date, by_value, gainers, losers, by_volume}。每個 top_n 筆。"""
    rows, date = _fetch_all_stocks()
    if not rows:
        return {"available": False, "by_value": [], "gainers": [], "losers": [], "by_volume": []}

    # 過濾：去掉成交金額太小的（避免冷門股噪音）
    rows = [r for r in rows if r["trade_value"] >= 1_000_000]  # 至少 100 萬

    by_value = sorted(rows, key=lambda r: -r["trade_value"])[:top_n]
    gainers = sorted(rows, key=lambda r: -r["change_pct"])[:top_n]
    losers = sorted(rows, key=lambda r: r["change_pct"])[:top_n]
    by_volume = sorted(rows, key=lambda r: -r["volume"])[:top_n]

    # 漲跌停家數統計
    up_count = sum(1 for r in rows if r["change_pct"] > 0)
    down_count = sum(1 for r in rows if r["change_pct"] < 0)
    flat_count = sum(1 for r in rows if r["change_pct"] == 0)
    limit_up = sum(1 for r in rows if r["change_pct"] >= 9.9)  # 漲停 ~10%
    limit_down = sum(1 for r in rows if r["change_pct"] <= -9.9)

    return {
        "available": True,
        "date": date,
        "total_stocks": len(rows),
        "breadth": {
            "up": up_count,
            "down": down_count,
            "flat": flat_count,
            "limit_up": limit_up,
            "limit_down": limit_down,
        },
        "by_value": by_value,
        "gainers": gainers,
        "losers": losers,
        "by_volume": by_volume,
    }
