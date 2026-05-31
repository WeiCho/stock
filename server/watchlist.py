"""
Watchlist + 條件記錄 / 評估。

當下做的：
- CRUD watchlist（加/刪 symbol）
- CRUD alert conditions（加/刪 條件）
- evaluate_all()：跑當前所有條件，回 [triggered=true/false, current_value, threshold]
  → 前端 render 時直接看「目前狀態」，不 push 通知

未來 Go alert engine 接這張 alert_conditions 直接消費，做 per-tick 觸發 + push。
"""

from datetime import datetime
from sqlalchemy import select, delete
from db import Watchlist, AlertCondition, StockName, get_session
import technical


# ──────────────────────────────────────────────
# Watchlist CRUD
# ──────────────────────────────────────────────

def list_watchlist() -> list[dict]:
    """回 watchlist + 對應股票中文名稱。"""
    with get_session() as session:
        items = session.execute(select(Watchlist).order_by(Watchlist.added_at.desc())).scalars().all()
        # join 中文名
        names = {n.symbol: n.name for n in session.execute(select(StockName)).scalars().all()}
        return [
            {"id": w.id, "symbol": w.symbol, "name": names.get(w.symbol, w.symbol),
             "note": w.note, "added_at": w.added_at.isoformat()}
            for w in items
        ]


def add_watchlist(symbol: str, note: str | None = None) -> dict:
    """加入 symbol。若已存在則 no-op（回現有的）。"""
    symbol = symbol.strip().upper()
    if not symbol:
        return {"error": "symbol 不可為空"}
    with get_session() as session:
        existing = session.execute(
            select(Watchlist).where(Watchlist.symbol == symbol)
        ).scalar_one_or_none()
        if existing:
            return {"id": existing.id, "symbol": existing.symbol, "note": existing.note,
                    "added_at": existing.added_at.isoformat(), "already_exists": True}
        row = Watchlist(symbol=symbol, note=note, added_at=datetime.utcnow())
        session.add(row)
        session.commit()
        return {"id": row.id, "symbol": symbol, "note": note,
                "added_at": row.added_at.isoformat()}


def remove_watchlist(symbol: str) -> dict:
    """刪除 watchlist 項目（連同其下所有 conditions）。"""
    symbol = symbol.strip().upper()
    with get_session() as session:
        session.execute(delete(Watchlist).where(Watchlist.symbol == symbol))
        session.execute(delete(AlertCondition).where(AlertCondition.symbol == symbol))
        session.commit()
    return {"symbol": symbol, "removed": True}


# ──────────────────────────────────────────────
# Alert Conditions CRUD
# ──────────────────────────────────────────────

_VALID_INDICATORS = {"rsi", "kd_k", "kd_d", "macd_hist", "close"}
_VALID_OPS = {"lt", "gt"}  # cross_up / cross_down 留給未來 Go engine 做


def list_conditions(symbol: str | None = None) -> list[dict]:
    """列出條件。指定 symbol 則只回該股的。"""
    with get_session() as session:
        q = select(AlertCondition)
        if symbol:
            q = q.where(AlertCondition.symbol == symbol.upper())
        rows = session.execute(q.order_by(AlertCondition.created_at.desc())).scalars().all()
        return [
            {"id": c.id, "symbol": c.symbol, "indicator": c.indicator, "op": c.op,
             "threshold": c.threshold, "enabled": c.enabled,
             "created_at": c.created_at.isoformat()}
            for c in rows
        ]


def add_condition(symbol: str, indicator: str, op: str, threshold: float) -> dict:
    symbol = symbol.strip().upper()
    if indicator not in _VALID_INDICATORS:
        return {"error": f"indicator 必須是 {sorted(_VALID_INDICATORS)}"}
    if op not in _VALID_OPS:
        return {"error": f"op 必須是 {sorted(_VALID_OPS)}"}
    with get_session() as session:
        row = AlertCondition(symbol=symbol, indicator=indicator, op=op,
                              threshold=float(threshold), enabled=True,
                              created_at=datetime.utcnow())
        session.add(row)
        session.commit()
        return {"id": row.id, "symbol": symbol, "indicator": indicator, "op": op,
                "threshold": threshold, "enabled": True}


def remove_condition(condition_id: int) -> dict:
    with get_session() as session:
        session.execute(delete(AlertCondition).where(AlertCondition.id == condition_id))
        session.commit()
    return {"id": condition_id, "removed": True}


# ──────────────────────────────────────────────
# 條件評估：跑當下技術面，看是否觸發
# ──────────────────────────────────────────────

def _current_value(symbol: str, indicator: str) -> float | None:
    """從 technical.analyze 拿當前值。indicator: rsi / kd_k / kd_d / macd_hist / close。"""
    result = technical.analyze(symbol, "daily")
    if "error" in result:
        return None
    if indicator == "rsi":
        return result.get("rsi")
    if indicator == "kd_k":
        return (result.get("kd") or {}).get("k")
    if indicator == "kd_d":
        return (result.get("kd") or {}).get("d")
    if indicator == "macd_hist":
        return (result.get("macd") or {}).get("hist")
    if indicator == "close":
        return result.get("close")
    return None


def _evaluate(op: str, current: float | None, threshold: float) -> bool:
    if current is None:
        return False
    if op == "lt":
        return current < threshold
    if op == "gt":
        return current > threshold
    return False


def evaluate_all() -> dict:
    """跑所有啟用的條件，回每條的目前狀態。給前端 render 用。"""
    conds = list_conditions()
    out = []
    # 同一支股票多個條件 → 緩存 technical.analyze 結果，避免重複算
    cache: dict[str, dict] = {}

    for c in conds:
        if not c["enabled"]:
            continue
        sym = c["symbol"]
        if sym not in cache:
            cache[sym] = technical.analyze(sym, "daily")
        tech = cache[sym]

        # 取值
        val = None
        if "error" not in tech:
            ind = c["indicator"]
            if ind == "rsi": val = tech.get("rsi")
            elif ind == "kd_k": val = (tech.get("kd") or {}).get("k")
            elif ind == "kd_d": val = (tech.get("kd") or {}).get("d")
            elif ind == "macd_hist": val = (tech.get("macd") or {}).get("hist")
            elif ind == "close": val = tech.get("close")

        triggered = _evaluate(c["op"], val, c["threshold"])
        out.append({
            **c,
            "current_value": val,
            "triggered": triggered,
            "as_of": tech.get("date") if "error" not in tech else None,
        })

    return {"conditions": out, "count": len(out),
            "triggered_count": sum(1 for x in out if x["triggered"])}
