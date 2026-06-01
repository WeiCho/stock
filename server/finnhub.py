"""
Finnhub API 整合（個人免費 tier：60 calls/min）。

目前用途：
  - 經濟事件日曆（/calendar/economic）— 全球央行決策、CPI、NFP、零售銷售等
  - 個股財報日（/calendar/earnings）— 美股
  - 分析師評等（/stock/recommendation）— 美股

Key 由 .env 讀取（FINNHUB_API_KEY）。沒設 key 時所有函式回空 / available=False。
1 小時 in-memory cache（事件當日通常確認後不會再變）。
"""

import logging
import os
import ssl
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional
import httpx

log = logging.getLogger("uvicorn.error")
_REPO_ROOT = Path(__file__).resolve().parent.parent

try:
    import certifi
    _SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except Exception:
    _SSL_CTX = ssl.create_default_context()
_SSL_CTX.verify_flags &= ~ssl.VERIFY_X509_STRICT

BASE = "https://finnhub.io/api/v1"

# 我們關注的重點國家（其他過濾掉）
_IMPORTANT_COUNTRIES = {"US", "CN", "TW", "JP", "EU", "DE", "GB", "KR"}

# 重點關鍵字（影響台股的事件）
_HIGH_IMPACT_KEYWORDS = (
    "Interest Rate", "Fed", "FOMC", "Rate Decision",  # 利率決策
    "CPI", "PPI", "PCE", "Inflation",                   # 通膨
    "Nonfarm", "Unemployment", "Jobless",               # 就業
    "GDP", "Manufacturing PMI", "Services PMI",         # 景氣
    "Retail Sales", "Industrial Production",
    "TSMC", "Powell", "ECB", "BOJ",                    # 重要關鍵詞
)

_CACHE: dict[str, tuple[datetime, dict]] = {}
_CACHE_TTL = timedelta(hours=1)


def _api_key() -> Optional[str]:
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


def available() -> bool:
    return bool(_api_key())


def _cached_get(cache_key: str, path: str, params: dict) -> Optional[dict]:
    """GET + 1 小時 cache。失敗回 None。"""
    cached = _CACHE.get(cache_key)
    if cached and (datetime.now() - cached[0]) < _CACHE_TTL:
        return cached[1]

    key = _api_key()
    if not key:
        return None
    try:
        with httpx.Client(verify=_SSL_CTX, timeout=15) as client:
            resp = client.get(f"{BASE}{path}", params={**params, "token": key})
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        log.warning("Finnhub %s 失敗：%s", path, e)
        return None

    _CACHE[cache_key] = (datetime.now(), data)
    return data


# ──────────────────────────────────────────────
# 經濟事件日曆（最有價值）
# ──────────────────────────────────────────────

def economic_calendar(days_ahead: int = 30, min_impact: str = "high") -> dict:
    """未來 N 天的全球經濟事件，過濾出高影響 + 重點國家。
    回傳 {available, events: [{date, time, country, event, impact, prev, estimate, actual, unit}]}。

    min_impact: 'low' | 'medium' | 'high' — 預設 'high' 只保留 Fed/CPI/NFP 等重大事件，
    medium 會多納入失業率、PMI 等。
    """
    if not available():
        return {"available": False, "events": [], "note": "需設定 FINNHUB_API_KEY"}

    today = date.today()
    end_date = today + timedelta(days=days_ahead)
    cache_key = f"econ:{today}:{end_date}:{min_impact}"
    raw = _cached_get(cache_key, "/calendar/economic", {
        "from": today.isoformat(),
        "to": end_date.isoformat(),
    })
    if raw is None:
        return {"available": True, "events": [], "error": "Finnhub 暫時無回應"}

    items = raw.get("economicCalendar") or []
    impact_rank = {"low": 0, "medium": 1, "high": 2}
    min_rank = impact_rank.get(min_impact, 1)

    out = []
    for e in items:
        country = e.get("country")
        impact = (e.get("impact") or "").lower()
        event_name = e.get("event", "")

        # 過濾規則（AND 邏輯）：
        # 1. 必須是重點國家（US/CN/TW/JP/EU/DE/GB/KR）
        # 2. 達到 impact 等級 OR 含關鍵字（Fed/CPI/NFP 等）
        if country not in _IMPORTANT_COUNTRIES:
            continue
        # 過濾地區/州級事件（德國 16 州 CPI 各自會發、美國各 Fed 區報告）
        _DE_STATES = ("Wuerttemberg", "Bavaria", "Hesse", "Brandenburg", "Saxony",
                      "Saarland", "Hamburg", "Berlin CPI", "North Rhine Westphalia",
                      "Lower Saxony", "Rhineland", "Mecklenburg", "Thuringia",
                      "Bremen", "Schleswig", "Anhalt")
        if any(x in event_name for x in _DE_STATES):
            continue
        # 過 Prel(初值) 跟 Final(終值) 同事件二選一（保留 Final，去掉 Prel 中間版本）
        if "Prel" in event_name and "Final" not in event_name:
            # 例：CPI YoY Prel 在 CPI YoY Final 前發布，市場通常聚焦終值
            # 但若沒有對應 Final 也要留 → 簡化：直接濾掉 Prel
            continue

        meets_impact = impact_rank.get(impact, 0) >= min_rank
        has_keyword = any(k.lower() in event_name.lower() for k in _HIGH_IMPACT_KEYWORDS)
        if not meets_impact and not has_keyword:
            continue

        # time 形如 "2026-05-29 00:00:00"；拆 date + time
        t_str = e.get("time", "")
        d_part, _, time_part = t_str.partition(" ")
        out.append({
            "date": d_part or today.isoformat(),
            "time": time_part[:5] if time_part else "",
            "country": country,
            "event": event_name,
            "impact": impact,
            "prev": e.get("prev"),
            "estimate": e.get("estimate"),
            "actual": e.get("actual"),
            "unit": e.get("unit"),
        })

    out.sort(key=lambda x: (x["date"], x["time"]))

    # 每天每國最多保留 3 個事件（避免同國多個變體刷屏）
    per_day_country: dict[tuple[str, str], int] = {}
    filtered = []
    for e in out:
        key = (e["date"], e["country"])
        if per_day_country.get(key, 0) >= 3:
            continue
        per_day_country[key] = per_day_country.get(key, 0) + 1
        filtered.append(e)

    return {"available": True, "events": filtered, "count": len(filtered), "min_impact": min_impact}


# ──────────────────────────────────────────────
# 個股財報日曆（美股）
# ──────────────────────────────────────────────

def earnings_calendar(symbol: str, days_back: int = 90, days_ahead: int = 90) -> dict:
    """單一美股近期 + 未來財報日。回傳 {symbol, earnings: [...]}"""
    if not available():
        return {"available": False, "earnings": []}

    today = date.today()
    cache_key = f"earn:{symbol}:{today}"
    raw = _cached_get(cache_key, "/calendar/earnings", {
        "from": (today - timedelta(days=days_back)).isoformat(),
        "to": (today + timedelta(days=days_ahead)).isoformat(),
        "symbol": symbol.upper(),
    })
    if raw is None:
        return {"available": True, "earnings": [], "error": "暫時無回應"}

    items = raw.get("earningsCalendar") or []
    return {"available": True, "symbol": symbol.upper(), "earnings": items}


# ──────────────────────────────────────────────
# 分析師評等（美股）
# ──────────────────────────────────────────────

def recommendations(symbol: str) -> dict:
    """個股分析師買進/賣出/持有評等的近 4 季變化。"""
    if not available():
        return {"available": False, "recommendations": []}

    cache_key = f"rec:{symbol.upper()}"
    raw = _cached_get(cache_key, "/stock/recommendation", {"symbol": symbol.upper()})
    if raw is None:
        return {"available": True, "recommendations": []}

    # Finnhub 回 list[{buy, hold, sell, strongBuy, strongSell, period, symbol}]
    return {"available": True, "symbol": symbol.upper(), "recommendations": raw or []}
