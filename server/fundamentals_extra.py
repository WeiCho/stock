"""
台股「進階基本面 + 籌碼」整合（補強現有 fundamentals.py）：

- 月營收（MOPS）— 含 MoM / YoY 趨勢
- 外資持股比率（集保結算所，週頻）— 外資進場/退場訊號
- 融資融券餘額（每日）— 散戶信用部位
- 借券賣出餘額（每日）— 機構放空部位

全部走 FinMind 免費 dataset。1 小時 in-memory cache。
"""

import logging
from datetime import datetime, timedelta, timezone
import ssl
import httpx

log = logging.getLogger("uvicorn.error")

try:
    import certifi
    _SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except Exception:
    _SSL_CTX = ssl.create_default_context()
_SSL_CTX.verify_flags &= ~ssl.VERIFY_X509_STRICT

FINMIND_BASE = "https://api.finmindtrade.com/api/v4/data"
HEADERS = {"User-Agent": "Mozilla/5.0 (TaiwanStockSkill/1.0)"}

_CACHE: dict[str, tuple[datetime, dict]] = {}
_CACHE_TTL = timedelta(hours=1)


def _cached_fetch(cache_key: str, params: dict) -> list[dict]:
    cached = _CACHE.get(cache_key)
    if cached and (datetime.now() - cached[0]) < _CACHE_TTL:
        return cached[1].get("data", [])
    try:
        with httpx.Client(headers=HEADERS, verify=_SSL_CTX, timeout=15) as client:
            resp = client.get(FINMIND_BASE, params=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        log.warning("FinMind %s 失敗：%s", params.get("dataset"), e)
        return []
    _CACHE[cache_key] = (datetime.now(), data)
    return data.get("data", [])


# ──────────────────────────────────────────────
# 月營收（MOPS，每月 10 號公布上月）
# ──────────────────────────────────────────────

def monthly_revenue(symbol: str, months_back: int = 24) -> dict:
    """回傳近 N 個月營收 + MoM / YoY 變化。
    revenue 單位：元。"""
    start = (datetime.now(timezone.utc).date() - timedelta(days=months_back * 35)).isoformat()
    rows = _cached_fetch(f"mom_rev:{symbol}:{months_back}", {
        "dataset": "TaiwanStockMonthRevenue",
        "data_id": symbol.upper(),
        "start_date": start,
    })
    if not rows:
        return {"symbol": symbol.upper(), "data": []}

    # 按 year+month 排序
    rows.sort(key=lambda r: (r["revenue_year"], r["revenue_month"]))
    out = []
    for i, r in enumerate(rows):
        revenue = r["revenue"]
        # MoM
        mom = None
        if i > 0 and rows[i - 1]["revenue"]:
            mom = round((revenue - rows[i - 1]["revenue"]) / rows[i - 1]["revenue"] * 100, 2)
        # YoY: 找 12 個月前同月份
        yoy = None
        target_y, target_m = r["revenue_year"] - 1, r["revenue_month"]
        yoy_row = next((x for x in rows if x["revenue_year"] == target_y and x["revenue_month"] == target_m), None)
        if yoy_row and yoy_row["revenue"]:
            yoy = round((revenue - yoy_row["revenue"]) / yoy_row["revenue"] * 100, 2)
        out.append({
            "year": r["revenue_year"],
            "month": r["revenue_month"],
            "date": r["date"],
            "revenue": revenue,
            "revenue_億": round(revenue / 1e8, 1),  # 易讀
            "mom_pct": mom,
            "yoy_pct": yoy,
        })

    # 最新一筆 summary
    latest = out[-1] if out else None
    summary = None
    if latest:
        summary = {
            **latest,
            "note": _revenue_signal(latest),
        }
    return {"symbol": symbol.upper(), "data": out[-months_back:], "latest": summary}


def _revenue_signal(latest: dict) -> str:
    """簡單分類：MoM + YoY 都升 / 都降 / 混合。"""
    mom, yoy = latest.get("mom_pct"), latest.get("yoy_pct")
    if mom is None or yoy is None:
        return "資料不足"
    if mom >= 5 and yoy >= 10:
        return "🔥 月增 + 年增雙位數，動能強"
    if mom < -5 and yoy < -10:
        return "⚠ 月減 + 年減雙位數，動能弱"
    if yoy >= 10:
        return "年增雙位數，長線正向"
    if yoy < -10:
        return "年減雙位數，需追蹤原因"
    return "持平"


# ──────────────────────────────────────────────
# 外資持股比率（集保，週頻）
# ──────────────────────────────────────────────

def foreign_shareholding(symbol: str, weeks_back: int = 26) -> dict:
    """近 N 週外資持股比率變化。比率上升 = 外資增持（偏多）。"""
    start = (datetime.now(timezone.utc).date() - timedelta(days=weeks_back * 7)).isoformat()
    rows = _cached_fetch(f"foreign_hold:{symbol}:{weeks_back}", {
        "dataset": "TaiwanStockShareholding",
        "data_id": symbol.upper(),
        "start_date": start,
    })
    if not rows:
        return {"symbol": symbol.upper(), "data": []}

    rows.sort(key=lambda r: r["date"])
    out = [{
        "date": r["date"],
        "foreign_ratio": r.get("ForeignInvestmentSharesRatio"),       # 已認購比率（外資持股 / 發行股數）
        "foreign_remain_ratio": r.get("ForeignInvestmentRemainRatio"),# 剩餘可投資比率
        "shares_issued": r.get("NumberOfSharesIssued"),
    } for r in rows]

    latest = out[-1] if out else None
    summary = None
    if latest and len(out) >= 4:
        # 比較 4 週前
        old = out[-4]
        if old["foreign_ratio"] and latest["foreign_ratio"]:
            change = round(latest["foreign_ratio"] - old["foreign_ratio"], 2)
            summary = {
                **latest,
                "change_4w_pp": change,  # 百分點變化
                "note": ("📈 外資增持" if change > 0.5
                         else "📉 外資減持" if change < -0.5
                         else "持平"),
            }
    return {"symbol": symbol.upper(), "data": out, "latest": summary or latest}


# ──────────────────────────────────────────────
# 融資融券餘額（信用交易，每日）
# ──────────────────────────────────────────────

def margin_short(symbol: str, days_back: int = 30) -> dict:
    """近 N 天融資融券餘額。
    融資餘額（散戶借錢買進） / 融券餘額（散戶放空，未平倉空單）。
    融資增 = 散戶追多；融券增 = 散戶看空。"""
    start = (datetime.now(timezone.utc).date() - timedelta(days=days_back)).isoformat()
    rows = _cached_fetch(f"margin:{symbol}:{days_back}", {
        "dataset": "TaiwanStockMarginPurchaseShortSale",
        "data_id": symbol.upper(),
        "start_date": start,
    })
    if not rows:
        return {"symbol": symbol.upper(), "data": []}

    rows.sort(key=lambda r: r["date"])
    out = [{
        "date": r["date"],
        "margin_balance": r.get("MarginPurchaseTodayBalance"),    # 融資餘額（張）
        "margin_change": (r.get("MarginPurchaseTodayBalance", 0)
                          - r.get("MarginPurchaseYesterdayBalance", 0)),
        "short_balance": r.get("ShortSaleTodayBalance"),          # 融券餘額（張）
        "short_change": (r.get("ShortSaleTodayBalance", 0)
                         - r.get("ShortSaleYesterdayBalance", 0)),
    } for r in rows]

    latest = out[-1] if out else None
    return {"symbol": symbol.upper(), "data": out, "latest": latest}


# ──────────────────────────────────────────────
# 借券賣出餘額（機構放空，每日）
# ──────────────────────────────────────────────

def securities_lending(symbol: str, days_back: int = 30) -> dict:
    """近 N 天借券賣出餘額（透過券商借券放空，主要外資使用）。
    上升 = 機構建立空單；下降 = 機構回補。"""
    start = (datetime.now(timezone.utc).date() - timedelta(days=days_back)).isoformat()
    rows = _cached_fetch(f"sec_lend:{symbol}:{days_back}", {
        "dataset": "TaiwanStockSecuritiesLending",
        "data_id": symbol.upper(),
        "start_date": start,
    })
    if not rows:
        return {"symbol": symbol.upper(), "data": []}

    # 按日 group volume（每天可能有多筆 transaction）
    by_date: dict[str, dict] = {}
    for r in rows:
        d = r["date"]
        slot = by_date.setdefault(d, {"date": d, "volume": 0, "avg_fee_rate": 0, "count": 0})
        slot["volume"] += r.get("volume") or 0
        slot["avg_fee_rate"] += r.get("fee_rate") or 0
        slot["count"] += 1
    for s in by_date.values():
        if s["count"] > 0:
            s["avg_fee_rate"] = round(s["avg_fee_rate"] / s["count"], 4)
            del s["count"]

    out = [by_date[d] for d in sorted(by_date)]
    return {"symbol": symbol.upper(), "data": out, "latest": out[-1] if out else None}
