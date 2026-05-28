"""FastAPI 後端主程式。"""

from contextlib import asynccontextmanager
from datetime import date, timedelta
import threading
import time as _time

import pandas as pd
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, func

# 路由用到的模組統一在頂層 import — 之前散在每個 route handler 裡面，
# 不只重複還會在每次 request 多一次 import lookup（雖然 Python 有 cache）。
import backtest as bt
import chip as chip_module
import commodities
import fred
import fugle
import news_fundamental as nf
import outlook
import pine_exporter
import technical
from db import (
    IndexData, Institutional, StockName, StockIndustry,
    get_session, init_db,
)
from data_fetcher import (
    daily_update,
    ensure_stock_data,
    fetch_live_index,
    fetch_market_breadth,
    fetch_stock_industry,
    fetch_stock_list,
    fetch_taiex_finmind,
    get_price_df,
    resample_ohlc,
    search_stock,
)


def _startup_tasks():
    daily_update()
    # 股票清單為空、或缺少上櫃資料（舊版抓取失敗）時，重新抓一次清單；
    # 同時預先建立產業對照表，讓首次 /market/money-flow 不必在請求中同步抓 FinMind。
    with get_session() as session:
        total = session.execute(select(func.count()).select_from(StockName)).scalar_one()
        tpex = session.execute(
            select(func.count()).select_from(StockName).where(StockName.market == "tpex")
        ).scalar_one()
        industry = session.execute(select(func.count()).select_from(StockIndustry)).scalar_one()
        taiex = session.execute(
            select(func.count()).select_from(IndexData).where(IndexData.name == "TAIEX")
        ).scalar_one()
    if total == 0 or tpex == 0:
        fetch_stock_list()
    if industry == 0:
        from data_fetcher import fetch_stock_industry
        fetch_stock_industry()
    if taiex < 1000:  # 不足約 4 年 → 用 FinMind 一次補滿 5 年（供大盤走勢時間區間切換）
        from data_fetcher import fetch_taiex_finmind
        fetch_taiex_finmind(5)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    # 背景執行每日更新；用 daemon thread，讓 Ctrl+C 能立即關閉（不等補資料跑完）。
    # 中途被中斷也安全：bulk 同步標記只在補完才寫入，下次啟動會自動重試。
    threading.Thread(target=_startup_tasks, daemon=True).start()
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


@app.get("/market/big-orders")
async def market_big_orders(min_amount: int = 30000000, top_n: int = 8):
    """今日大單敲進（Fugle 逐筆）：掃描法人買超個股的大單（單筆 >= min_amount 元）。

    需設定 FUGLE_API_KEY；未設定則回 {available: False}。盤中即時、收盤後為最後一盤。
    """
    if not fugle.available():
        return {"available": False, "orders": []}

    # 觀察清單：今日法人買超的個股（大錢所在，最可能出現大單）
    mf = chip_module.market_money_flow(top_n=15)
    names, syms = {}, []
    if "error" not in mf:
        for r in mf.get("foreign_buy", []) + mf.get("trust_buy", []):
            if r["symbol"] not in names:
                names[r["symbol"]] = r["name"]
                syms.append(r["symbol"])

    orders = await fugle.scan_big_orders(syms[:12], min_amount=min_amount)
    for o in orders:
        o["name"] = names.get(o["symbol"], o["symbol"])
    return {"available": True, "min_amount": min_amount, "orders": orders[:top_n]}


@app.get("/market/index/live")
async def market_index_live():
    """即時加權指數（TWSE MIS，盤中每幾秒更新；非交易時段回最後狀態）。"""
    data = await fetch_live_index()
    if not data or data.get("index") is None:
        raise HTTPException(status_code=503, detail="即時指數暫時無法取得")
    return data


@app.get("/market/money-flow")
def market_money_flow(top_n: int = 10):
    """全市場法人資金動向 + 盤後大盤統計（漲跌家數、成交金額）。"""
    result = chip_module.market_money_flow(top_n)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    # 直接查「法人最新交易日」當天的大盤統計，省去回溯找日期的多次請求
    try:
        target = date.fromisoformat(result["date"])
    except (ValueError, KeyError):
        target = None
    result["market_stats"] = fetch_market_breadth(target)  # 盤後漲跌家數+成交金額；取不到為 {}
    sf = chip_module.sector_money_flow()                    # 類股資金流向；取不到為 {}
    result["sector_flow"] = sf if "error" not in sf else {}
    return result


# ──────────────────────────────────────────────
# 個股
# ──────────────────────────────────────────────

@app.get("/stock/{symbol}/price")
def stock_price(symbol: str, days: int = 60, tf: str = "1d"):
    """個股 K 線。tf: 1d / 3d / 5d / 1w / 3w / 1mo（由日K 重採樣；當日請改用 /intraday）。"""
    ensure_stock_data(symbol)
    df = get_price_df(symbol)
    if df.empty:
        raise HTTPException(status_code=404, detail=f"找不到 {symbol} 的資料")

    df_res = resample_ohlc(df.tail(days), tf).reset_index()
    if "date" not in df_res.columns and "index" in df_res.columns:
        df_res = df_res.rename(columns={"index": "date"})
    df_res["date"] = pd.to_datetime(df_res["date"]).dt.strftime("%Y-%m-%d")
    return {"symbol": symbol, "tf": tf, "data": df_res.to_dict(orient="records")}


@app.get("/stock/{symbol}/intraday")
async def stock_intraday(symbol: str, timeframe: str = "5"):
    """個股盤中分鐘K（Fugle）。timeframe: 1/5/10/15/30/60 分鐘。需 FUGLE_API_KEY。"""
    if not fugle.available():
        raise HTTPException(status_code=503, detail="需設定 FUGLE_API_KEY")
    data = await fugle.intraday_candles(symbol, timeframe)
    if not data:
        raise HTTPException(status_code=503, detail="盤中資料暫時無法取得")
    return data


@app.get("/market/index/intraday")
async def market_index_intraday(timeframe: str = "5"):
    """加權指數盤中分鐘K（Fugle IX0001）。timeframe: 1/5/10/15/30/60 分鐘。"""
    if not fugle.available():
        raise HTTPException(status_code=503, detail="需設定 FUGLE_API_KEY")
    data = await fugle.intraday_candles("IX0001", timeframe)
    if not data:
        raise HTTPException(status_code=503, detail="盤中資料暫時無法取得")
    return data


@app.get("/stock/{symbol}/technical")
def stock_technical(symbol: str, timeframe: str = "daily"):
    """個股技術面分析。timeframe: daily | weekly"""
    result = technical.analyze(symbol, timeframe)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@app.get("/stock/{symbol}/outlook")
def stock_outlook(symbol: str):
    """綜合研判：技術面 + 籌碼面 + 歷史回測 → 方向偏向、加權依據、預期區間。"""
    result = outlook.analyze(symbol)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@app.get("/stock/{symbol}/chip")
def stock_chip_detail(symbol: str, days: int = 30):
    """個股三大法人籌碼分析。"""
    result = chip_module.analyze(symbol, days)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@app.get("/stock/{symbol}/backtest")
def stock_backtest(symbol: str, signal: str = "ma_cross", hold: str = "5,10,20,60"):
    """個股回測勝率統計。signal 可用值見 /backtest/signals"""
    hold_days = [int(d) for d in hold.split(",") if d.strip().isdigit()]
    result = bt.run(symbol, signal, hold_days)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.get("/stock/{symbol}/pine")
def stock_pine(symbol: str, signal: str = "ma_cross"):
    """輸出回測結果的 Pine Script。"""
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
    news = nf.fetch_news(symbol, company_name, limit)
    return {"symbol": symbol, "news": news}


@app.get("/stock/{symbol}/fundamentals")
def stock_fundamentals(symbol: str):
    """個股基本面指標。"""
    return nf.fetch_fundamentals(symbol)


@app.get("/market/global")
def market_global_news(category: str = "all", per_cat: int = 8):
    """全球盤勢新聞（亞/歐/美 + 地緣政治）。category=all 或 asia/europe/us/geopol。
    結果以 30 分鐘 in-memory 快取，避免每次 refresh 都打 Google News。"""
    return nf.fetch_global_news(category=category, per_cat=per_cat)


# ──────────────────────────────────────────────
# 期貨 / 國際商品
# ──────────────────────────────────────────────

@app.get("/market/commodities")
def market_commodities():
    """支援的期貨/商品清單。"""
    return {
        "items": [
            {"symbol": s, "label": v["label"], "source": v["source"], "currency": v.get("currency", "TWD")}
            for s, v in commodities.SUPPORTED.items()
        ]
    }


@app.get("/market/commodity/{symbol}/price")
def commodity_price(symbol: str, days: int = 365, tf: str = "1d"):
    """單一商品/期貨 K 線（含績效摘要 perf）。
    tf: intraday / 1d / 3d / 5d / 1w / 2w / 3w / 1mo（intraday 限 Yahoo 商品）。"""
    result = commodities.fetch_history(symbol.upper(), days=days, tf=tf)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    if not result.get("data"):
        raise HTTPException(status_code=503, detail="商品資料暫時無法取得")
    # perf 只算在日線/長線（tf=1d）；其他 tf 的 perf 由前端用相同 days 另查或不顯示
    if tf in ("1d", None) and not result.get("perf"):
        result["perf"] = commodities.perf_summary(result["data"])
    return result


@app.get("/market/futures/institutional")
def futures_institutional(symbol: str = "TX", days: int = 30):
    """期貨三大法人留倉淨口數（外資/投信/自營商）。僅支援 FinMind 台股期貨符號。"""
    result = commodities.fetch_institutional(symbol.upper(), days=days)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.get("/market/macro/economic")
def macro_economic():
    """美國總體經濟指標（CPI / GDP / NFP / Fed Funds / 失業率 / PCE）。
    需 FRED_API_KEY；沒設時 available=False、indicators=[]。"""
    return fred.summary()


@app.get("/market/macro/series/{series_id}")
def macro_series(series_id: str, years: int = 3):
    """單一 FRED series 完整時間序列（前端可畫迷你走勢圖）。"""
    result = fred.get_series(series_id.upper(), years=years)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


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
    return bt.list_signals()


@app.get("/market/chip-scan")
def market_chip_scan(
    min_foreign_days: int = 3,
    min_trust_days: int = 0,
    top_n: int = 20,
    order_by: str = "total",
):
    """全市場三大法人掃描。"""
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

    fetch_stock_list()
    with get_session() as session:
        symbols = [r.symbol for r in session.execute(select(StockName)).scalars().all()]

    for symbol in symbols:
        ensure_stock_data(symbol)
        _time.sleep(1.2)


@app.get("/health")
def health():
    return {"status": "ok"}
