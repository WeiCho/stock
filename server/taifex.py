"""
TAIFEX 期貨/選擇權衍生指標。

Put/Call Ratio (PCR)：
  - PCR(volume) = put 成交量 / call 成交量；> 1.2 過度恐慌（反向看多）、< 0.7 過度樂觀
  - PCR(OI) = put 未平倉 / call 未平倉；衡量 hedge 部位偏向

資料源：FinMind TaiwanOptionDaily（TXO 台指選擇權，免費）。
官方 TAIFEX 也有 CSV 下載但是 Big5 編碼 + 表單 POST，比較麻煩。

30 分鐘 in-memory cache（日頻資料）。
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
_CACHE_TTL = timedelta(minutes=30)


def _classify_pcr(v: float) -> tuple[str, str]:
    """PCR 區間 → (label, note)。台股 TXO 經驗值。"""
    if v >= 1.4:
        return "extreme_bearish", "⚠ 極度悲觀（put 大幅多於 call）：反向買入訊號"
    if v >= 1.1:
        return "bearish", "偏空氛圍，避險買權多"
    if v >= 0.9:
        return "neutral", "中性，多空均衡"
    if v >= 0.7:
        return "bullish", "偏多氛圍，買 call 居多"
    return "extreme_bullish", "⚠ 極度樂觀（call 大幅多於 put）：反向賣出警戒"


def fetch_pcr(days: int = 30) -> dict:
    """近 N 天台指選擇權 PCR（成交量比 + 未平倉比）。
    回傳 {data: [{date, pcr_volume, pcr_oi}], latest: {...}}。"""
    cache_key = f"pcr:{days}"
    cached = _CACHE.get(cache_key)
    if cached and (datetime.now() - cached[0]) < _CACHE_TTL:
        return cached[1]

    start = (datetime.now(timezone.utc).date() - timedelta(days=days)).isoformat()
    try:
        with httpx.Client(headers=HEADERS, verify=_SSL_CTX, timeout=20) as client:
            resp = client.get(FINMIND_BASE, params={
                "dataset": "TaiwanOptionDaily",
                "data_id": "TXO",
                "start_date": start,
            })
            resp.raise_for_status()
            rows = resp.json().get("data", [])
    except Exception as e:
        log.warning("FinMind TaiwanOptionDaily 抓取失敗：%s", e)
        return {"data": [], "latest": None, "error": str(e)}

    # 按日期 group，計算每天的 PCR
    # 只看 position session（正規盤），排除盤後夜盤
    daily: dict[str, dict] = {}
    for r in rows:
        if r.get("trading_session") != "position":
            continue
        if (r.get("volume") or 0) == 0 and (r.get("open_interest") or 0) == 0:
            continue
        d = r["date"]
        cp = r.get("call_put")  # 'call' or 'put'
        if cp not in ("call", "put"):
            continue
        slot = daily.setdefault(d, {
            "date": d,
            "call_vol": 0, "put_vol": 0,
            "call_oi": 0, "put_oi": 0,
        })
        slot[f"{cp}_vol"] += r.get("volume") or 0
        slot[f"{cp}_oi"] += r.get("open_interest") or 0

    series = []
    for d in sorted(daily.keys()):
        s = daily[d]
        pcr_vol = round(s["put_vol"] / s["call_vol"], 3) if s["call_vol"] > 0 else None
        pcr_oi = round(s["put_oi"] / s["call_oi"], 3) if s["call_oi"] > 0 else None
        series.append({
            "date": d,
            "pcr_volume": pcr_vol,
            "pcr_oi": pcr_oi,
            "call_volume": s["call_vol"],
            "put_volume": s["put_vol"],
        })

    if not series:
        return {"data": [], "latest": None}

    last = series[-1]
    latest_summary = {**last}
    if last["pcr_volume"] is not None:
        cat, note = _classify_pcr(last["pcr_volume"])
        latest_summary["volume_category"] = cat
        latest_summary["note"] = note

    result = {"data": series, "latest": latest_summary}
    _CACHE[cache_key] = (datetime.now(), result)
    return result
