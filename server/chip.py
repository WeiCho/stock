"""
籌碼面分析模組：三大法人
個股分析 + 全市場掃描。
"""

from datetime import date, timedelta
import pandas as pd
from sqlalchemy import select, func
from db import Institutional, get_session
from data_fetcher import get_institutional_df


def _latest_institutional_date() -> date | None:
    with get_session() as session:
        d = session.execute(select(func.max(Institutional.date))).scalar_one_or_none()
    return d


# ──────────────────────────────────────────────
# 個股籌碼分析
# ──────────────────────────────────────────────

def _count_consecutive(series: pd.Series) -> int:
    """計算最新一筆起，連續正值（買超）或連續負值（賣超）的天數。"""
    if series.empty:
        return 0
    direction = 1 if series.iloc[-1] > 0 else -1
    count = 0
    for v in reversed(series.tolist()):
        if v * direction > 0:
            count += 1
        else:
            break
    return count * direction  # 正=連買N天, 負=連賣N天


def analyze(symbol: str, days: int = 30) -> dict:
    """個股三大法人籌碼分析。"""
    latest = _latest_institutional_date()
    if latest is None:
        return {"error": "法人資料尚未下載"}

    # 從最新有資料的日期往前 days 天取資料
    cutoff = latest - timedelta(days=days)
    with get_session() as session:
        rows = session.execute(
            select(Institutional)
            .where(
                Institutional.symbol == symbol,
                Institutional.date >= cutoff,
            )
            .order_by(Institutional.date)
        ).scalars().all()

    if not rows:
        return {"error": f"找不到 {symbol} 的法人資料，該股可能無三大法人資料（ETF/權證除外）"}

    df = pd.DataFrame([{
        "date": r.date,
        "foreign": r.foreign_buy,
        "trust": r.trust_buy,
        "dealer": r.dealer_buy,
        "total": r.total_buy,
    } for r in rows])

    last = df.iloc[-1]

    def _cum(col, n):
        return round(df[col].tail(n).sum(), 0)

    foreign_consec = _count_consecutive(df["foreign"])
    trust_consec = _count_consecutive(df["trust"])

    # 方向描述
    def _trend_label(consec: int) -> str:
        if consec >= 5:
            return f"連續買超 {consec} 天"
        if consec >= 1:
            return f"近期買超（{consec} 天）"
        if consec <= -5:
            return f"連續賣超 {abs(consec)} 天"
        if consec <= -1:
            return f"近期賣超（{abs(consec)} 天）"
        return "持平"

    # 合力方向
    total_5d = _cum("total", 5)
    if total_5d > 500:
        summary = "三大法人近5日合力買超，籌碼偏多"
    elif total_5d < -500:
        summary = "三大法人近5日合力賣超，籌碼偏空"
    elif df["foreign"].tail(5).sum() > 0 and df["trust"].tail(5).sum() > 0:
        summary = "外資投信同向買超，籌碼偏多"
    else:
        summary = "三大法人方向分歧，觀望為宜"

    return {
        "symbol": symbol,
        "date": str(last["date"]),
        "foreign": {
            "today": round(last["foreign"], 0),
            "consecutive_days": foreign_consec,
            "cum_5d": _cum("foreign", 5),
            "cum_10d": _cum("foreign", 10),
            "cum_20d": _cum("foreign", 20),
            "trend": _trend_label(foreign_consec),
        },
        "trust": {
            "today": round(last["trust"], 0),
            "consecutive_days": trust_consec,
            "cum_5d": _cum("trust", 5),
            "trend": _trend_label(trust_consec),
        },
        "dealer": {
            "today": round(last["dealer"], 0),
            "trend": "買超" if last["dealer"] > 0 else "賣超",
        },
        "total_today": round(last["total"], 0),
        "summary": summary,
        "history": [
            {
                "date": str(r["date"]),
                "foreign": r["foreign"],
                "trust": r["trust"],
                "dealer": r["dealer"],
                "total": r["total"],
            }
            for r in df.to_dict(orient="records")
        ],
    }


# ──────────────────────────────────────────────
# 全市場掃描
# ──────────────────────────────────────────────

def scan_bulk(
    min_foreign_days: int = 0,
    min_trust_days: int = 0,
    min_total_5d: float = 0,
    top_n: int = 20,
    order_by: str = "total",  # foreign | trust | total
) -> list[dict]:
    """
    全市場掃描三大法人，回傳符合條件的股票。
    使用最新一個交易日的 bulk 資料 + 近期連買天數統計。
    """
    latest = _latest_institutional_date()
    if latest is None:
        return []

    # 取最近 30 天做連買天數統計
    cutoff = latest - timedelta(days=30)
    with get_session() as session:
        rows = session.execute(
            select(Institutional)
            .where(Institutional.date >= cutoff)
            .order_by(Institutional.symbol, Institutional.date)
        ).scalars().all()

    if not rows:
        return []

    # 按 symbol 分組
    from collections import defaultdict
    groups: dict[str, list] = defaultdict(list)
    for r in rows:
        groups[r.symbol].append({
            "date": r.date,
            "foreign": r.foreign_buy,
            "trust": r.trust_buy,
            "total": r.total_buy,
        })

    results = []
    for symbol, records in groups.items():
        df = pd.DataFrame(records).sort_values("date")
        if df.empty or df.iloc[-1]["date"] != latest:
            continue  # 最新一天沒資料的跳過

        last = df.iloc[-1]
        f_consec = _count_consecutive(df["foreign"])
        t_consec = _count_consecutive(df["trust"])
        total_5d = df["total"].tail(5).sum()

        if f_consec < min_foreign_days:
            continue
        if t_consec < min_trust_days:
            continue
        if total_5d < min_total_5d:
            continue

        results.append({
            "symbol": symbol,
            "foreign_today": round(last["foreign"], 0),
            "trust_today": round(last["trust"], 0),
            "total_today": round(last["total"], 0),
            "foreign_consecutive": f_consec,
            "trust_consecutive": t_consec,
            "total_5d": round(total_5d, 0),
        })

    # 排序
    sort_key = {
        "foreign": lambda x: x["foreign_today"],
        "trust": lambda x: x["trust_today"],
        "total": lambda x: x["total_today"],
    }.get(order_by, lambda x: x["total_today"])

    results.sort(key=sort_key, reverse=True)
    return results[:top_n]
