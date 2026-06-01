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
import outlook
import technical
import twse_openapi
from data_fetcher import get_price_df

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


def _chip_map(min_days: int) -> dict[str, dict]:
    """{symbol: {'foreign': 外資連買天數, 'trust': 投信連買天數}}（只含外資達門檻者）。
    注意：chip.scan_bulk 的鍵是 foreign_consecutive / trust_consecutive。"""
    out: dict[str, dict] = {}
    try:
        rows = chip_module.scan_bulk(min_foreign_days=min_days, top_n=40)
        for r in rows or []:
            s = r.get("symbol")
            if s:
                out[s] = {"foreign": r.get("foreign_consecutive", 0) or 0,
                          "trust": r.get("trust_consecutive", 0) or 0}
    except Exception as e:
        log.warning("screen: chip.scan_bulk 失敗：%s", e)
    return out


def _recent_vol(symbol: str) -> float | None:
    """近 20 日「日報酬標準差(%)」當波動度指標；越低代表走勢越穩（適合『慢慢長』）。"""
    try:
        df = get_price_df(symbol)
        if df is None or df.empty or len(df) < 21:
            return None
        r = df["close"].pct_change().tail(20)
        return round(float(r.std()) * 100, 2)
    except Exception:
        return None


def _low_vol_bonus(vol: float | None) -> int:
    """低波動加分：越穩給越多（穩步走多的核心）。"""
    if vol is None:
        return 0
    if vol < 2.0:
        return 3
    if vol < 3.0:
        return 2
    if vol < 4.0:
        return 1
    return 0


def bullish_screen(exclude_overbought: bool = True, min_foreign_days: int = 3,
                   top: int = 15, mode: str = "momentum") -> dict:
    """偏多候選掃描。
    mode='momentum'（預設）：放量 / 連買 / 技術偏多，依分數排序。
    mode='steady'（穩步走多 / 慢慢長）：強制未過熱 + 需多頭排列 + 「低波動」加權，
        並對入選者附 outlook 預期區間（依 10 年回測，故只對 finalists 跑）。
    exclude_overbought=True 濾掉 RSI 過熱者（找更早、尚未噴出的設定）。"""
    if mode == "steady":
        exclude_overbought = True  # 穩步走多必然未過熱
    ck = f"{mode}:{exclude_overbought}:{min_foreign_days}:{top}"
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

    cmap = _chip_map(min_foreign_days)
    candidates = set(momentum) | set(cmap.keys())

    items = []
    for sym in list(candidates)[:40]:  # 上限，避免單次掃太多（含 ensure_stock_data）
        try:
            tech = technical.analyze(sym, "daily")
            if "error" in tech:
                continue
        except Exception:
            continue
        cm = cmap.get(sym, {})
        score, overbought, reasons = score_candidate(
            trend=tech.get("trend"), signals=tech.get("signals", []), rsi=tech.get("rsi"),
            foreign_days=cm.get("foreign", 0), trust_days=cm.get("trust", 0),
            in_momentum=sym in momentum)
        if score <= 0:
            continue
        if exclude_overbought and overbought:
            continue
        trend = tech.get("trend")
        vol = None
        if mode == "steady":
            if trend != "多頭排列":          # 穩步走多需多頭結構
                continue
            vol = _recent_vol(sym)
            score += _low_vol_bonus(vol)
            if vol is not None and vol < 3.0:
                reasons.append(f"低波動({vol}%)")
        v = val.get(sym, {})
        items.append({
            "symbol": sym, "name": names.get(sym) or v.get("name", ""),
            "score": score, "overbought": overbought, "reasons": reasons,
            "per": v.get("per"), "dividend_yield": v.get("dividend_yield"),
            "foreign_days": cm.get("foreign", 0),
            "close": tech.get("close"), "rsi": tech.get("rsi"),
            "trend": trend, "volatility": vol,
        })

    # 分數高優先；穩步走多模式同分時波動低者優先
    items.sort(key=lambda x: (-x["score"], x["volatility"] if x.get("volatility") is not None else 999))
    items = items[:top]

    if mode == "steady":  # 對入選者附 outlook 預期區間（回測較慢，只對 finalists 跑）
        for it in items:
            try:
                o = outlook.analyze(it["symbol"])
                exp = o.get("expected") if isinstance(o, dict) else None
                if exp:
                    it["expected"] = {k: exp.get(k) for k in
                                      ("target", "range_low", "range_high", "win_rate", "basis")}
            except Exception:
                pass

    result = {
        "available": True,
        "mode": mode,
        "date": mv.get("date", ""),
        "filters": {"exclude_overbought": exclude_overbought, "min_foreign_days": min_foreign_days, "mode": mode},
        "disclaimer": "研究訊號，非投資建議；EOD 資料，過去不代表未來。",
        "items": items,
    }
    _CACHE[ck] = (datetime.now(), result)
    return result
