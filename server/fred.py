"""
FRED（St. Louis Fed）經濟資料整合 — 給總經頁用。

Key 由 .env 提供（FRED_API_KEY）；沒設 key 時所有函式都回 None，前端會顯示「需設定」。

回傳的時間序列維持 FRED 原樣（[{date, value}]），讓前端可以自己畫小走勢圖；
另外提供 `summary()` 彙總常用指標的「最新值 + 月增 + 年增」，給 MacroPanel 一次抓全部。
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

# OpenSSL3 / Python 3.14：與其他模組一致
try:
    import certifi
    _SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except Exception:
    _SSL_CTX = ssl.create_default_context()
_SSL_CTX.verify_flags &= ~ssl.VERIFY_X509_STRICT

FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"

# 5 個核心經濟指標 — 對應總經頁的 Macro 框架
# series_id → {label, unit, frequency, note}
SERIES = {
    "CPIAUCSL":  {"label": "CPI 消費者物價",   "unit": "指數 (1982-84=100)", "freq": "monthly",   "note": "通膨主指標"},
    "PCE":       {"label": "PCE 個人消費",     "unit": "十億 USD",          "freq": "monthly",   "note": "Fed 偏好的通膨衡量"},
    "GDP":       {"label": "GDP",              "unit": "十億 USD",          "freq": "quarterly", "note": "經濟成長"},
    "PAYEMS":    {"label": "非農就業",         "unit": "千人",              "freq": "monthly",   "note": "勞動市場熱度"},
    "UNRATE":    {"label": "失業率",           "unit": "%",                 "freq": "monthly",   "note": "勞動市場（反向）"},
    "DFF":       {"label": "Fed Funds Rate",   "unit": "%",                 "freq": "daily",     "note": "Fed 政策利率"},
    "DGS2":      {"label": "美 2Y 公債利率",   "unit": "%",                 "freq": "daily",     "note": "短端利率，反映 Fed 預期"},
    "DGS10":     {"label": "美 10Y 公債利率",  "unit": "%",                 "freq": "daily",     "note": "長端利率，反映通膨/成長預期"},
}

# 1 小時 in-memory cache（FRED 月頻資料一天才更新一次，但加減快取省 quota）
_CACHE: dict[str, tuple[datetime, dict]] = {}
_CACHE_TTL = timedelta(hours=1)


def _api_key() -> Optional[str]:
    key = os.environ.get("FRED_API_KEY")
    if key:
        return key
    env = _REPO_ROOT / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.startswith("FRED_API_KEY="):
                v = line.split("=", 1)[1].strip()
                return v or None
    return None


def available() -> bool:
    return bool(_api_key())


def _fetch_series(series_id: str, years: int = 3) -> list[dict]:
    """抓 FRED series 觀測值。失敗回空 list。"""
    key = _api_key()
    if not key:
        return []
    start = (date.today() - timedelta(days=365 * years)).isoformat()
    try:
        with httpx.Client(verify=_SSL_CTX, timeout=15) as client:
            resp = client.get(FRED_BASE, params={
                "series_id": series_id,
                "api_key": key,
                "file_type": "json",
                "observation_start": start,
            })
            resp.raise_for_status()
            payload = resp.json()
    except Exception as e:
        log.warning("FRED %s 抓取失敗：%s", series_id, e)
        return []

    rows = payload.get("observations") or []
    out = []
    for r in rows:
        v = r.get("value")
        if v in (".", None, ""):  # FRED 用 "." 表示缺值
            continue
        try:
            out.append({"date": r["date"], "value": float(v)})
        except (ValueError, KeyError):
            continue
    return out


def get_series(series_id: str, years: int = 3) -> dict:
    """回傳單一 series：{series_id, label, unit, freq, data: [{date, value}]}。"""
    if series_id not in SERIES:
        return {"error": f"未知 series '{series_id}'，可用：{list(SERIES)}"}
    cache_key = f"{series_id}:{years}"
    cached = _CACHE.get(cache_key)
    if cached and (datetime.now() - cached[0]) < _CACHE_TTL:
        return cached[1]

    meta = SERIES[series_id]
    data = _fetch_series(series_id, years)
    result = {
        "series_id": series_id,
        "label": meta["label"],
        "unit": meta["unit"],
        "freq": meta["freq"],
        "note": meta["note"],
        "data": data,
    }
    if data:
        _CACHE[cache_key] = (datetime.now(), result)
    return result


# ──────────────────────────────────────────────
# 衍生指標：殖利率曲線（10Y - 2Y spread）
# ──────────────────────────────────────────────

def yield_curve(years: int = 5) -> dict:
    """美 10Y - 2Y 公債利差。倒掛（< 0）歷史上是衰退預警，平均提前 6-18 個月。
    回傳 {data: [{date, value}], latest, status: 'normal'|'flat'|'inverted'}。"""
    dgs10 = get_series("DGS10", years=years).get("data") or []
    dgs2 = get_series("DGS2", years=years).get("data") or []
    if not dgs10 or not dgs2:
        return {"data": [], "latest": None, "status": "unavailable",
                "note": "FRED 暫時無法取得；通常 1-2 分鐘內恢復"}

    # 用日期做 inner join
    m2 = {r["date"]: r["value"] for r in dgs2}
    spread = []
    for r in dgs10:
        v2 = m2.get(r["date"])
        if v2 is not None:
            spread.append({"date": r["date"], "value": round(r["value"] - v2, 3)})

    latest = spread[-1]["value"] if spread else None
    if latest is None:
        status = "unavailable"
    elif latest < -0.1:
        status = "inverted"   # 倒掛 — 強烈衰退訊號
    elif latest < 0.3:
        status = "flat"       # 趨平 — 警戒
    else:
        status = "normal"

    return {
        "data": spread,
        "latest": latest,
        "status": status,
        "note": {
            "inverted": "⚠ 殖利率倒掛：歷史上 6-18 個月內常出現衰退",
            "flat": "曲線趨平：景氣動能放緩警戒",
            "normal": "正常曲線：景氣擴張階段",
            "unavailable": "資料暫時無法取得",
        }[status],
    }


def _change_pct(curr: float, base: float) -> Optional[float]:
    if base == 0 or base is None:
        return None
    return round((curr - base) / base * 100, 2)


def summary() -> dict:
    """彙總 6 個核心指標的「最新值 / 月增 / 年增」。給 MacroPanel 一次拿。
    沒有 key 時回 {available: False}。"""
    if not available():
        return {"available": False, "indicators": []}

    out = []
    for sid in SERIES:
        s = get_series(sid, years=3)
        data = s.get("data") or []
        if not data:
            continue
        latest = data[-1]
        # 找 1 個月前 / 12 個月前的觀測值
        latest_date = datetime.fromisoformat(latest["date"]).date()
        mom_target = latest_date - timedelta(days=35)  # 寬一點窗，月頻資料對齊
        yoy_target = latest_date - timedelta(days=365)

        mom_obs = next((r for r in reversed(data[:-1])
                        if datetime.fromisoformat(r["date"]).date() <= mom_target), None)
        yoy_obs = next((r for r in reversed(data[:-1])
                        if datetime.fromisoformat(r["date"]).date() <= yoy_target), None)

        out.append({
            "series_id": sid,
            "label": s["label"],
            "unit": s["unit"],
            "note": s["note"],
            "latest_date": latest["date"],
            "latest_value": latest["value"],
            "mom_change_pct": _change_pct(latest["value"], mom_obs["value"]) if mom_obs else None,
            "yoy_change_pct": _change_pct(latest["value"], yoy_obs["value"]) if yoy_obs else None,
        })
    return {"available": True, "indicators": out}
