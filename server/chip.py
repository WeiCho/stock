"""
籌碼面分析模組：三大法人
個股分析 + 全市場掃描。
"""

from datetime import date, timedelta
import pandas as pd
from sqlalchemy import select, func
from db import Institutional, StockName, get_session
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

        # 門檻為 0 時代表「不過濾該維度」，避免把賣超（負連續天數）的股票一併濾掉
        if min_foreign_days > 0 and f_consec < min_foreign_days:
            continue
        if min_trust_days > 0 and t_consec < min_trust_days:
            continue
        if min_total_5d and total_5d < min_total_5d:
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


# ──────────────────────────────────────────────
# 全市場資金動向（大盤總覽用）
# ──────────────────────────────────────────────

def market_money_flow(top_n: int = 10) -> dict:
    """全市場法人資金動向：當日三大法人合計淨額（張）＋ 外資/投信買超賣超排行（含股名）。

    註：資料來自 TWSE T86，僅含上市；用來回答「整體資金流入或流出、外資與投信在買哪些」。
    """
    latest = _latest_institutional_date()
    if latest is None:
        return {"error": "法人資料尚未下載"}

    with get_session() as session:
        sums = session.execute(
            select(
                func.sum(Institutional.foreign_buy),
                func.sum(Institutional.trust_buy),
                func.sum(Institutional.dealer_buy),
            ).where(Institutional.date == latest)
        ).one()

        if sums[0] is None:
            return {"error": "法人資料尚未更新，請稍後再試"}

        def _top(col, desc: bool):
            order = col.desc() if desc else col.asc()
            return session.execute(
                select(Institutional)
                .where(Institutional.date == latest)
                .order_by(order)
                .limit(top_n)
            ).scalars().all()

        foreign_buy = _top(Institutional.foreign_buy, True)
        foreign_sell = _top(Institutional.foreign_buy, False)
        trust_buy = _top(Institutional.trust_buy, True)
        trust_sell = _top(Institutional.trust_buy, False)

        syms = {r.symbol for r in foreign_buy + foreign_sell + trust_buy + trust_sell}
        names = {
            s.symbol: s.name
            for s in session.execute(
                select(StockName).where(StockName.symbol.in_(syms))
            ).scalars().all()
        }

    def _fmt(r):
        return {
            "symbol": r.symbol,
            "name": names.get(r.symbol, r.symbol),
            "foreign": round(r.foreign_buy),
            "trust": round(r.trust_buy),
            "dealer": round(r.dealer_buy),
            "total": round(r.total_buy),
        }

    foreign_total, trust_total, dealer_total = round(sums[0]), round(sums[1]), round(sums[2])
    return {
        "date": str(latest),
        "summary": {
            "foreign": foreign_total,
            "trust": trust_total,
            "dealer": dealer_total,
            "total": foreign_total + trust_total + dealer_total,
        },
        "foreign_buy": [_fmt(r) for r in foreign_buy],
        "foreign_sell": [_fmt(r) for r in foreign_sell],
        "trust_buy": [_fmt(r) for r in trust_buy],
        "trust_sell": [_fmt(r) for r in trust_sell],
    }


def sector_money_flow(top_n: int = 8) -> dict:
    """類股資金流向：以最近交易日，依產業別彙總三大法人淨買賣超（張），看資金流入/流出哪些類股。"""
    from collections import defaultdict
    from data_fetcher import get_industry_map

    latest = _latest_institutional_date()
    if latest is None:
        return {"error": "法人資料尚未下載"}

    industry = get_industry_map()
    with get_session() as session:
        rows = session.execute(
            select(Institutional).where(Institutional.date == latest)
        ).scalars().all()
    if not rows:
        return {"error": "法人資料尚未更新"}

    agg = defaultdict(lambda: {"total": 0.0, "foreign": 0.0, "trust": 0.0, "count": 0})
    for r in rows:
        ind = industry.get(r.symbol)
        if not ind:
            continue
        a = agg[ind]
        a["total"] += r.total_buy
        a["foreign"] += r.foreign_buy
        a["trust"] += r.trust_buy
        a["count"] += 1

    sectors = [
        {"industry": k, "total": round(v["total"]), "foreign": round(v["foreign"]),
         "trust": round(v["trust"]), "count": v["count"]}
        for k, v in agg.items()
    ]
    sectors.sort(key=lambda x: x["total"], reverse=True)
    return {
        "date": str(latest),
        "inflow": [s for s in sectors if s["total"] > 0][:top_n],
        "outflow": [s for s in reversed(sectors) if s["total"] < 0][:top_n],
    }
