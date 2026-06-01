"""
外匯匯率（exchangerate-api.com 免費 public，無需 key）。

提供：
- 即時匯率：USD 對 TWD/JPY/CNY/EUR/GBP/HKD/SGD
- 歷史匯率（API 限制只有最新）

對台股最重要的是 USD/TWD（出口股 EPS 敏感）。

1 小時 in-memory cache（匯率日內變化小，1 hr 夠新鮮）。
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

BASE = "https://api.exchangerate-api.com/v4/latest"
HEADERS = {"User-Agent": "TaiwanStockSkill/1.0"}

# 對台股研究最相關的幣別
_DEFAULT_TARGETS = ["TWD", "JPY", "CNY", "EUR", "GBP", "HKD", "SGD"]

_CACHE: dict[str, tuple[datetime, dict]] = {}
_CACHE_TTL = timedelta(hours=1)


def latest_rates(base: str = "USD", targets: list[str] | None = None) -> dict:
    """匯率 — 1 個 base 兌多個 target。
    回 {base, date, rates: {TWD: 31.43, JPY: ...}}。"""
    if targets is None:
        targets = _DEFAULT_TARGETS

    cache_key = f"fx:{base}"
    cached = _CACHE.get(cache_key)
    if cached and (datetime.now() - cached[0]) < _CACHE_TTL:
        data = cached[1]
    else:
        try:
            with httpx.Client(headers=HEADERS, verify=_SSL_CTX, timeout=10) as client:
                resp = client.get(f"{BASE}/{base.upper()}")
                resp.raise_for_status()
                data = resp.json()
        except Exception as e:
            log.warning("FX %s 抓取失敗：%s", base, e)
            return {"base": base, "rates": {}, "available": False}
        _CACHE[cache_key] = (datetime.now(), data)

    all_rates = data.get("rates", {})
    rates = {t: all_rates.get(t) for t in targets if t in all_rates}
    return {
        "base": data.get("base_code") or data.get("base") or base.upper(),
        "date": data.get("date") or data.get("time_last_update_utc"),
        "rates": rates,
        "available": True,
    }
