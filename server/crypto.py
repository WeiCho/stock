"""
CoinGecko 加密貨幣整合（免費 public API，30 calls/min，無需 key）。

提供：
- top 10 by market cap + 24h change
- 全球統計（總市值、BTC dominance、ETH dominance）

5 分鐘 in-memory cache。
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

BASE = "https://api.coingecko.com/api/v3"
HEADERS = {"User-Agent": "TaiwanStockSkill/1.0", "Accept": "application/json"}

_CACHE: dict[str, tuple[datetime, dict]] = {}
_CACHE_TTL = timedelta(minutes=5)


def _cached_get(cache_key: str, path: str, params: dict | None = None) -> dict | list | None:
    cached = _CACHE.get(cache_key)
    if cached and (datetime.now() - cached[0]) < _CACHE_TTL:
        return cached[1]
    try:
        with httpx.Client(headers=HEADERS, verify=_SSL_CTX, timeout=10) as client:
            resp = client.get(f"{BASE}{path}", params=params or {})
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        log.warning("CoinGecko %s 失敗：%s", path, e)
        return None
    _CACHE[cache_key] = (datetime.now(), data)
    return data


def top_markets(limit: int = 10) -> dict:
    """Top N 加密貨幣（市值排序）+ 24h 變化。"""
    data = _cached_get(f"top:{limit}", "/coins/markets", {
        "vs_currency": "usd",
        "order": "market_cap_desc",
        "per_page": limit,
        "page": 1,
        "sparkline": "false",
        "price_change_percentage": "24h,7d,30d",
    })
    if not data:
        return {"items": [], "available": False}
    items = [
        {
            "symbol": c.get("symbol", "").upper(),
            "name": c.get("name"),
            "price": c.get("current_price"),
            "market_cap": c.get("market_cap"),
            "market_cap_rank": c.get("market_cap_rank"),
            "volume_24h": c.get("total_volume"),
            "change_24h_pct": c.get("price_change_percentage_24h"),
            "change_7d_pct": c.get("price_change_percentage_7d_in_currency"),
            "change_30d_pct": c.get("price_change_percentage_30d_in_currency"),
            "image": c.get("image"),
        }
        for c in data
    ]
    return {"items": items, "available": True, "count": len(items)}


def global_stats() -> dict:
    """全球加密市場：總市值、BTC/ETH dominance、活躍幣種數。"""
    data = _cached_get("global", "/global", None)
    if not data:
        return {"available": False}
    d = data.get("data", {}) if isinstance(data, dict) else {}
    return {
        "available": True,
        "total_market_cap_usd": (d.get("total_market_cap") or {}).get("usd"),
        "total_volume_24h_usd": (d.get("total_volume") or {}).get("usd"),
        "btc_dominance": (d.get("market_cap_percentage") or {}).get("btc"),
        "eth_dominance": (d.get("market_cap_percentage") or {}).get("eth"),
        "active_cryptocurrencies": d.get("active_cryptocurrencies"),
        "markets": d.get("markets"),
        "market_cap_change_pct_24h": d.get("market_cap_change_percentage_24h_usd"),
    }
