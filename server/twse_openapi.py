"""
TWSE OpenAPI（openapi.twse.com.tw）整合 — 官方、免費、免 API key、無日額度限制。

⚠ 性質：這些 *_ALL / opendata endpoint 是「最近一個交易日 / 最近一期」的**快照**，
不是歷史時間序列；且僅含**上市（TWSE）**，上櫃（TPEx）需另接 TPEx OpenAPI。
歷史回補仍走 FinMind / 爬蟲；此模組補的是「全市場當前橫斷面」（估值篩選、官方最新值）。

10 分鐘 in-memory cache（日頻資料一天才更新一次）。日期為民國年（YYYMMDD）。
"""

import logging
import ssl
from datetime import datetime, timedelta

import httpx

log = logging.getLogger("uvicorn.error")

BASE = "https://openapi.twse.com.tw/v1"

try:
    import certifi
    _SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except Exception:
    _SSL_CTX = ssl.create_default_context()
_SSL_CTX.verify_flags &= ~ssl.VERIFY_X509_STRICT

HEADERS = {"User-Agent": "Mozilla/5.0 (TaiwanStockSkill/1.0)", "Accept": "application/json"}

_CACHE: dict[str, tuple[datetime, list[dict]]] = {}
_CACHE_TTL = timedelta(minutes=10)


def _roc_to_ad(d: str) -> str:
    """民國 YYYMMDD → 西元 YYYY-MM-DD（無法解析回空字串）。"""
    d = str(d or "").strip()
    if len(d) == 7:
        return f"{int(d[:3]) + 1911}-{d[3:5]}-{d[5:7]}"
    return ""


def _f(s) -> float | None:
    """官方欄位 float 解析；空字串 / '--' / 逗號千分位都處理。"""
    if s is None:
        return None
    t = str(s).strip().replace(",", "")
    if t in ("", "--", "—", "N/A"):
        return None
    try:
        return float(t)
    except (ValueError, TypeError):
        return None


def _get(path: str) -> list[dict]:
    """GET BASE/path，10 分鐘 cache。失敗回 []（log warning）。"""
    cached = _CACHE.get(path)
    if cached and (datetime.now() - cached[0]) < _CACHE_TTL:
        return cached[1]
    try:
        with httpx.Client(headers=HEADERS, verify=_SSL_CTX, timeout=20) as client:
            resp = client.get(f"{BASE}/{path}")
            resp.raise_for_status()
            raw = resp.json()
        if not isinstance(raw, list):
            raise ValueError("非預期回應格式")
    except Exception as e:
        log.warning("TWSE OpenAPI %s 抓取失敗：%s", path, e)
        return []
    _CACHE[path] = (datetime.now(), raw)
    return raw


# ──────────────────────────────────────────────
# 估值：本益比 / 股價淨值比 / 殖利率（BWIBBU_ALL）
# ──────────────────────────────────────────────

def valuation() -> dict:
    """全上市股票的 PER / PBR / 殖利率（官方）。回 {available, date, items:[...]}。"""
    raw = _get("exchangeReport/BWIBBU_ALL")
    if not raw:
        return {"available": False, "date": "", "items": []}
    items = [{
        "symbol": (r.get("Code") or "").strip(),
        "name": (r.get("Name") or "").strip(),
        "per": _f(r.get("PEratio")),
        "pbr": _f(r.get("PBratio")),
        "dividend_yield": _f(r.get("DividendYield")),
    } for r in raw if (r.get("Code") or "").strip()]
    return {"available": True, "date": _roc_to_ad(raw[0].get("Date", "")), "items": items}


def valuation_for(symbol: str) -> dict:
    """單一個股的官方估值。未上市 / 查無回 {available: False}。"""
    v = valuation()
    if not v["available"]:
        return {"available": False, "symbol": symbol}
    for it in v["items"]:
        if it["symbol"] == symbol:
            return {"available": True, "symbol": symbol, "date": v["date"],
                    "name": it["name"], "per": it["per"], "pbr": it["pbr"],
                    "dividend_yield": it["dividend_yield"]}
    return {"available": False, "symbol": symbol}


def valuation_screen(top_n: int = 10) -> dict:
    """全市場估值篩選：低本益比 + 高殖利率 排行（過濾無效 / 非正值）。"""
    v = valuation()
    if not v["available"]:
        return {"available": False, "date": "", "low_per": [], "high_yield": []}
    items = v["items"]
    low_per = sorted((i for i in items if i["per"] and i["per"] > 0),
                     key=lambda i: i["per"])[:top_n]
    high_yield = sorted((i for i in items if i["dividend_yield"] and i["dividend_yield"] > 0),
                        key=lambda i: -i["dividend_yield"])[:top_n]
    return {"available": True, "date": v["date"], "low_per": low_per, "high_yield": high_yield}


# ──────────────────────────────────────────────
# 融資融券（MI_MARGN）— 官方最新一日餘額
# ──────────────────────────────────────────────

def _margin_rows() -> dict[str, dict]:
    raw = _get("exchangeReport/MI_MARGN")
    out: dict[str, dict] = {}
    for r in raw:
        code = (r.get("股票代號") or "").strip()
        if not code:
            continue
        m_today = _f(r.get("融資今日餘額"))
        m_prev = _f(r.get("融資前日餘額"))
        s_today = _f(r.get("融券今日餘額"))
        s_prev = _f(r.get("融券前日餘額"))
        out[code] = {
            "symbol": code,
            "name": (r.get("股票名稱") or "").strip(),
            "margin_balance": m_today,
            "margin_change": (m_today - m_prev) if (m_today is not None and m_prev is not None) else None,
            "short_balance": s_today,
            "short_change": (s_today - s_prev) if (s_today is not None and s_prev is not None) else None,
        }
    return out


def margin_for(symbol: str) -> dict | None:
    """單一個股的官方最新融資融券餘額（無資料回 None）。"""
    return _margin_rows().get(symbol)
