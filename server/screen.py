"""
偏多候選多因子掃描 — 把 movers（動能）+ chip 連買（籌碼）+ technical（技術）+ 估值
收斂成一份「目前出現偏多設定」的候選清單，可調濾網。

⚠ 研究訊號，非投資建議；EOD 資料；技術訊號取「最新一根 K」，不跑 10 年回測（求即時）。
10 分鐘 in-memory cache（key = 濾網參數）。
"""

import logging
from datetime import datetime, timedelta

import chip as chip_module
import market_movers
import technical
import twse_openapi

log = logging.getLogger("uvicorn.error")

_CACHE: dict[str, tuple[datetime, dict]] = {}
_CACHE_TTL = timedelta(minutes=10)


def score_candidate(*, trend: str | None, signals: list[dict], rsi: float | None,
                    foreign_days: int = 0, trust_days: int = 0, in_momentum: bool = False
                    ) -> tuple[int, bool, list[str]]:
    """純函式：依多因子算偏多分數。回 (score, overbought, reasons)。
    score 越高越偏多；overbought=True 代表 RSI 過熱（追高風險，可被濾網排除）。"""
    score = 0
    reasons: list[str] = []

    if trend == "多頭排列":
        score += 2
        reasons.append("均線多頭排列")
    elif trend == "空頭排列":
        score -= 2

    for s in signals:
        if s.get("type") == "bullish":
            score += 1
            reasons.append(s.get("name", ""))
        elif s.get("type") == "bearish":
            score -= 1

    if foreign_days >= 5:
        score += 3
        reasons.append(f"外資連買{foreign_days}日")
    elif foreign_days >= 3:
        score += 2
        reasons.append(f"外資連買{foreign_days}日")
    if trust_days >= 3:
        score += 1
        reasons.append(f"投信連買{trust_days}日")

    if in_momentum:
        score += 1
        reasons.append("放量/漲幅入榜")

    overbought = (rsi is not None and rsi > 70) or any(s.get("code") == "rsi_overbought" for s in signals)
    # 去重保序
    seen, uniq = set(), []
    for r in reasons:
        if r and r not in seen:
            seen.add(r)
            uniq.append(r)
    return score, overbought, uniq


def _foreign_days_map(min_days: int) -> dict[str, int]:
    """{symbol: 外資連買天數}（只含達門檻者）。"""
    out: dict[str, int] = {}
    try:
        rows = chip_module.scan_bulk(min_foreign_days=min_days)
        rows = rows if isinstance(rows, list) else (rows or {}).get("results", [])
        for r in rows or []:
            s = r.get("symbol")
            if s:
                out[s] = r.get("foreign_days") or r.get("consecutive_days") or min_days
    except Exception as e:
        log.warning("screen: chip.scan_bulk 失敗：%s", e)
    return out


def bullish_screen(exclude_overbought: bool = True, min_foreign_days: int = 3,
                   top: int = 15) -> dict:
    """偏多候選掃描。exclude_overbought=True 會濾掉 RSI 過熱者（找更早的設定）。"""
    ck = f"{exclude_overbought}:{min_foreign_days}:{top}"
    cached = _CACHE.get(ck)
    if cached and (datetime.now() - cached[0]) < _CACHE_TTL:
        return cached[1]

    val = {it["symbol"]: it for it in (twse_openapi.valuation().get("items") or [])}
    mv = market_movers.market_movers(top_n=15)
    momentum: set[str] = set()
    names: dict[str, str] = {}
    for k in ("gainers", "by_volume", "by_value"):
        for r in (mv.get(k) or [])[:10]:
            momentum.add(r["symbol"])
            names[r["symbol"]] = r.get("name", "")

    fmap = _foreign_days_map(min_foreign_days)
    candidates = set(momentum) | set(fmap.keys())

    items = []
    for sym in list(candidates)[:40]:  # 上限，避免單次掃太多（含 ensure_stock_data）
        try:
            tech = technical.analyze(sym, "daily")
            if "error" in tech:
                continue
        except Exception:
            continue
        score, overbought, reasons = score_candidate(
            trend=tech.get("trend"), signals=tech.get("signals", []), rsi=tech.get("rsi"),
            foreign_days=fmap.get(sym, 0), in_momentum=sym in momentum)
        if score <= 0:
            continue
        if exclude_overbought and overbought:
            continue
        v = val.get(sym, {})
        items.append({
            "symbol": sym, "name": names.get(sym) or v.get("name", ""),
            "score": score, "overbought": overbought, "reasons": reasons,
            "per": v.get("per"), "dividend_yield": v.get("dividend_yield"),
            "foreign_days": fmap.get(sym, 0),
            "close": tech.get("close"), "rsi": tech.get("rsi"),
        })

    items.sort(key=lambda x: -x["score"])
    result = {
        "available": True,
        "date": mv.get("date", ""),
        "filters": {"exclude_overbought": exclude_overbought, "min_foreign_days": min_foreign_days},
        "disclaimer": "研究訊號，非投資建議；EOD 資料、技術訊號取最新一根 K，未跑回測，過去不代表未來。",
        "items": items[:top],
    }
    _CACHE[ck] = (datetime.now(), result)
    return result
