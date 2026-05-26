"""FastAPI 後端主程式。"""

from contextlib import asynccontextmanager
from datetime import date
from typing import Optional
import asyncio

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware

from db import init_db
from data_fetcher import (
    daily_update,
    ensure_stock_data,
    fetch_daily_institutional_bulk,
    fetch_stock_list,
    get_institutional_df,
    get_price_df,
    search_stock,
)


def _startup_tasks():
    daily_update()
    # 若 stock_names 表是空的則抓一次股票清單
    from sqlalchemy import select, func
    from db import StockName, get_session
    with get_session() as session:
        count = session.execute(select(func.count()).select_from(StockName)).scalar_one()
    if count == 0:
        fetch_stock_list()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    loop = asyncio.get_event_loop()
    loop.run_in_executor(None, _startup_tasks)
    yield


app = FastAPI(title="Taiwan Stock API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ──────────────────────────────────────────────
# 大盤 / 市場
# ──────────────────────────────────────────────

@app.get("/market/institutional")
def market_institutional(top: int = 20, order: str = "desc"):
    """三大法人全市場最近交易日買賣超排行。"""
    from sqlalchemy import select, func
    from db import Institutional, get_session

    with get_session() as session:
        # 取最新有資料的日期
        latest_date = session.execute(
            select(func.max(Institutional.date))
        ).scalar_one_or_none()

        if latest_date is None:
            raise HTTPException(status_code=404, detail="法人資料尚未下載，請稍後再試")

        rows = session.execute(
            select(Institutional)
            .where(Institutional.date == latest_date)
            .order_by(
                Institutional.total_buy.desc() if order == "desc"
                else Institutional.total_buy.asc()
            )
            .limit(top)
        ).scalars().all()

    if not rows:
        raise HTTPException(status_code=404, detail="法人資料尚未更新，請稍後再試")

    return {
        "data": [
            {
                "symbol": r.symbol,
                "foreign_buy": r.foreign_buy,
                "trust_buy": r.trust_buy,
                "dealer_buy": r.dealer_buy,
                "total_buy": r.total_buy,
            }
            for r in rows
        ],
        "date": str(latest_date),
    }


@app.get("/market/index")
def market_index(days: int = 90):
    """加權指數近 N 天走勢。"""
    from sqlalchemy import select
    from db import IndexData, get_session
    from datetime import timedelta

    cutoff = date.today() - timedelta(days=days)
    with get_session() as session:
        rows = session.execute(
            select(IndexData)
            .where(IndexData.name == "TAIEX", IndexData.date >= cutoff)
            .order_by(IndexData.date)
        ).scalars().all()

    return {
        "data": [{"date": str(r.date), "close": r.close} for r in rows],
        "name": "TAIEX",
    }


# ──────────────────────────────────────────────
# 個股
# ──────────────────────────────────────────────

@app.get("/stock/{symbol}/price")
def stock_price(symbol: str, days: int = 60):
    """個股日K（若尚未下載則觸發歷史資料抓取）。"""
    ensure_stock_data(symbol)
    df = get_price_df(symbol)
    if df.empty:
        raise HTTPException(status_code=404, detail=f"找不到 {symbol} 的資料")

    df_tail = df.tail(days).reset_index()
    return {
        "symbol": symbol,
        "data": df_tail.to_dict(orient="records"),
    }


@app.get("/stock/{symbol}/technical")
def stock_technical(symbol: str, timeframe: str = "daily"):
    """個股技術面分析。timeframe: daily | weekly"""
    import technical
    result = technical.analyze(symbol, timeframe)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@app.get("/stock/{symbol}/chip")
def stock_chip_detail(symbol: str, days: int = 30):
    """個股三大法人籌碼分析。"""
    import chip as chip_module
    result = chip_module.analyze(symbol, days)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@app.get("/stock/{symbol}/backtest")
def stock_backtest(symbol: str, signal: str = "ma_cross", hold: str = "5,10,20,60"):
    """個股回測勝率統計。signal 可用值見 /backtest/signals"""
    import backtest as bt
    hold_days = [int(d) for d in hold.split(",") if d.strip().isdigit()]
    result = bt.run(symbol, signal, hold_days)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.get("/stock/{symbol}/pine")
def stock_pine(symbol: str, signal: str = "ma_cross"):
    """輸出回測結果的 Pine Script。"""
    import backtest as bt
    import pine_exporter
    bt_result = bt.run(symbol, signal)
    if "error" in bt_result:
        raise HTTPException(status_code=400, detail=bt_result["error"])
    result = pine_exporter.export(
        symbol, signal, bt_result["signal_name"], bt_result.get("stats", [])
    )
    return result


@app.get("/stock/{symbol}/news")
def stock_news(symbol: str, company_name: str = "", limit: int = 10):
    """個股新聞列表。"""
    import news_fundamental as nf
    news = nf.fetch_news(symbol, company_name, limit)
    return {"symbol": symbol, "news": news}


@app.get("/stock/{symbol}/fundamentals")
def stock_fundamentals(symbol: str):
    """個股基本面指標。"""
    import news_fundamental as nf
    return nf.fetch_fundamentals(symbol)


@app.get("/stock/search")
def stock_search(q: str = "", limit: int = 10):
    """用股票代碼或中文名稱模糊搜尋，回傳 [{symbol, name, market}]。"""
    if not q.strip():
        return {"results": []}
    results = search_stock(q.strip(), limit=limit)
    return {"results": results}


@app.get("/stock/{symbol}")
def stock_full(symbol: str, company_name: str = ""):
    """完整個股分析：技術面 + 籌碼面 + 新聞基本面。"""
    import technical
    import chip as chip_module
    import news_fundamental as nf

    tech = technical.analyze(symbol, "daily")
    tech_weekly = technical.analyze(symbol, "weekly")
    chip_data = chip_module.analyze(symbol)
    summary = nf.summarize(symbol, company_name)

    return {
        "symbol": symbol,
        "company_name": company_name,
        "technical": {"daily": tech, "weekly": tech_weekly},
        "chip": chip_data,
        "fundamentals": summary["fundamentals"],
        "news": summary["news_list"][:5],
    }


@app.get("/backtest/signals")
def backtest_signals():
    """列出所有支援的回測訊號。"""
    import backtest as bt
    return bt.list_signals()


@app.get("/market/chip-scan")
def market_chip_scan(
    min_foreign_days: int = 3,
    min_trust_days: int = 0,
    top_n: int = 20,
    order_by: str = "total",
):
    """全市場三大法人掃描。"""
    import chip as chip_module
    results = chip_module.scan_bulk(
        min_foreign_days=min_foreign_days,
        min_trust_days=min_trust_days,
        top_n=top_n,
        order_by=order_by,
    )
    return {"data": results, "count": len(results)}


# ──────────────────────────────────────────────
# 管理
# ──────────────────────────────────────────────

@app.post("/admin/init-all")
def admin_init_all(background_tasks: BackgroundTasks):
    """觸發全台股歷史資料下載（背景執行）。"""
    background_tasks.add_task(_run_init_all)
    return {"status": "started", "message": "全市場歷史資料下載已在背景執行，請稍後查詢進度"}


def _run_init_all():
    """背景任務：爬取全台股清單並下載個股歷史。"""
    import time
    from sqlalchemy import select
    from db import StockName, get_session

    fetch_stock_list()
    with get_session() as session:
        symbols = [r.symbol for r in session.execute(select(StockName)).scalars().all()]

    for symbol in symbols:
        ensure_stock_data(symbol)
        time.sleep(1.2)


@app.get("/health")
def health():
    return {"status": "ok"}
