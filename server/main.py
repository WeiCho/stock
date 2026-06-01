"""FastAPI 後端主程式。"""

from pathlib import Path
from dotenv import load_dotenv

# 讀取專案根目錄 .env（FUGLE / FRED / FINNHUB / SEC_CONTACT_EMAIL…）。
# 必須在 import 任何「會讀環境變數」的模組之前執行；override=False，不覆蓋已 export 的變數。
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from contextlib import asynccontextmanager
from datetime import date, timedelta
import asyncio
import threading
import time as _time

import pandas as pd
from fastapi import FastAPI, HTTPException, BackgroundTasks, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from sqlalchemy import select, func

# 路由用到的模組統一在頂層 import — 之前散在每個 route handler 裡面，
# 不只重複還會在每次 request 多一次 import lookup（雖然 Python 有 cache）。
import backtest as bt
import chip as chip_module
import commodities
import crypto
import finnhub
import fred
import fugle
import fugle_ws
import fundamentals_extra
import fx
import market_movers
import news_fundamental as nf
import outlook
import pine_exporter
import screen as screen_module
import sec
import taifex
import technical
import twse_openapi
import watchlist
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
# gzip 壓縮：> 500 bytes 的 response 自動壓縮（K 線 / 法人歷史等大資料減 70-80% 體積）
app.add_middleware(GZipMiddleware, minimum_size=500)


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
    with get_session() as session:
        name_row = session.execute(select(StockName).where(StockName.symbol == symbol)).scalar_one_or_none()
    name = name_row.name if name_row else None
    return {"symbol": symbol, "name": name, "tf": tf, "data": df_res.to_dict(orient="records")}


@app.get("/stock/{symbol}/intraday")
async def stock_intraday(symbol: str, timeframe: str = "5"):
    """個股盤中分鐘K（Fugle）。timeframe: 1/5/10/15/30/60 分鐘。需 FUGLE_API_KEY。"""
    if not fugle.available():
        raise HTTPException(status_code=503, detail="需設定 FUGLE_API_KEY")
    data = await fugle.intraday_candles(symbol, timeframe)
    if not data:
        raise HTTPException(status_code=503, detail="盤中資料暫時無法取得")
    return data


@app.get("/stock/{symbol}/quote")
async def stock_quote(symbol: str):
    """個股 / ETF 即時報價快照（Fugle，含五檔）。盤中即時、收盤後回最後一盤。需 FUGLE_API_KEY。"""
    if not fugle.available():
        raise HTTPException(status_code=503, detail="需設定 FUGLE_API_KEY")
    data = await fugle.quote(symbol)
    if not data:
        raise HTTPException(status_code=503, detail="即時報價暫時無法取得")
    return data


@app.websocket("/ws/quotes")
async def ws_quotes(ws: WebSocket):
    """多檔即時報價串流（自選清單 / movers 各列）。瀏覽器送 {action:'subscribe', symbols:[≤5]}，
    後端維護單一 Fugle WS（aggregates channel）並廣播回來。需 FUGLE_API_KEY。"""
    await ws.accept()
    if not fugle.available():
        await ws.send_json({"event": "error", "message": "需設定 FUGLE_API_KEY"})
        await ws.close()
        return
    client = fugle_ws.hub.add_client()

    async def pump():  # hub queue → 瀏覽器
        try:
            while True:
                await ws.send_json(await client.queue.get())
        except Exception:
            pass

    pumper = asyncio.create_task(pump())
    try:
        while True:
            data = await ws.receive_json()
            if isinstance(data, dict) and data.get("action") == "subscribe":
                await fugle_ws.hub.set_client_symbols(client, data.get("symbols") or [])
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        pumper.cancel()
        await fugle_ws.hub.remove_client(client)


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


@app.get("/stock/{symbol}/pattern-scan")
def stock_pattern_scan(symbol: str):
    """三線交纏帶量突破 MA60 型態掃描。"""
    from backtest import _ma_tangle_breakout_mask, _ma60_bonus

    ensure_stock_data(symbol)
    daily = get_price_df(symbol)
    if daily.empty:
        raise HTTPException(status_code=404, detail=f"找不到 {symbol} 的資料")

    daily.index = pd.to_datetime(daily.index)
    df = daily.copy()
    close  = df["close"]
    volume = df["volume"]

    def _slope(series, n=3):
        v = series.dropna()
        if len(v) < n + 1:
            return None
        return round(float(v.iloc[-1] - v.iloc[-(n + 1)]), 4)

    ma5      = close.rolling(5).mean()
    ma10     = close.rolling(10).mean()
    ma20     = close.rolling(20).mean()
    ma60     = close.rolling(60).mean()
    vol_ma20 = volume.rolling(20).mean()

    mask    = _ma_tangle_breakout_mask(df).fillna(False)
    dates   = df.index[mask].tolist()
    now     = bool(mask.iloc[-1]) if len(mask) else False
    ma60_up = bool(_ma60_bonus(df).iloc[-1]) if len(df) >= 65 else False

    # ── 各條件診斷值（以今日為視角）
    cur_close  = round(float(close.iloc[-1]), 2)   if len(close) >= 1  else None
    prev_close = round(float(close.iloc[-2]), 2)   if len(close) >= 2  else None
    day2_close = round(float(close.iloc[-3]), 2)   if len(close) >= 3  else None
    cur_ma60   = round(float(ma60.iloc[-1]),  2)   if len(close) >= 60 else None
    prev_ma60  = round(float(ma60.iloc[-2]),  2)   if len(close) >= 61 else None
    day2_ma60  = round(float(ma60.iloc[-3]),  2)   if len(close) >= 62 else None

    # 三線交纏：今日 MA5/10/20 差距 < 收盤 3%
    three_vals = [ma5.iloc[-1], ma10.iloc[-1], ma20.iloc[-1]] if len(close) >= 20 else []
    three_spread = round(float(max(three_vals) - min(three_vals)), 2) if three_vals and all(pd.notna(v) for v in three_vals) else None
    tangle_threshold = round(float(cur_close * 0.03), 2) if cur_close else None
    cond_tangle = three_spread is not None and tangle_threshold is not None and three_spread < tangle_threshold

    # 收盤接近 MA60（差距 < 收盤 3%，尚未突破）
    ma60_gap = round(abs(cur_close - cur_ma60), 2) if cur_close and cur_ma60 else None
    ma60_gap_threshold = round(float(cur_close * 0.03), 2) if cur_close else None
    cond_near_ma60 = ma60_gap is not None and ma60_gap_threshold is not None and ma60_gap < ma60_gap_threshold

    # 收盤站上 MA5/10/20 三線
    cond_above_three = (
        three_vals and cur_close is not None
        and all(cur_close > float(v) for v in three_vals)
    )

    # 蓄勢中：三線交纏 + 收盤站上三線 + 距 MA60 < 3%（尚未突破）
    setup_triggered = cond_tangle and bool(cond_above_three) and cond_near_ma60

    # 今日與昨日均站上 MA60（連續 2 日）
    cond_above_ma60 = (cur_close is not None and cur_ma60 is not None and cur_close > cur_ma60 and
                       prev_close is not None and prev_ma60 is not None and prev_close > prev_ma60)

    # 前天在 MA60 以下（突破剛發生）
    cond_first_break = day2_close is not None and day2_ma60 is not None and day2_close <= day2_ma60

    # 昨日帶量：昨量 > 20 日均量 × 1.5
    prev_vol    = round(float(volume.iloc[-2]))      if len(volume) >= 2  else None
    prev_vol_ma = round(float(vol_ma20.iloc[-2]))    if len(volume) >= 21 else None
    vol_threshold = round(prev_vol_ma * 1.5)         if prev_vol_ma else None
    cond_volume = prev_vol is not None and vol_threshold is not None and prev_vol > vol_threshold

    label = (
        "突破完成（MA60 上斜，力道最強）" if now and ma60_up
        else "突破完成（MA60 下斜，領先突破）" if now
        else "蓄勢中，等待帶量突破 MA60" if setup_triggered
        else "尚未形成"
    )

    # ── 觸發後回測勝率（冷卻期去重，確保樣本獨立）
    daily_index = daily.index
    backtest_stats = []
    for n in [5, 10, 20]:
        returns = []
        cooldown_until = None
        for trigger_date in sorted(dates):
            if cooldown_until is not None and pd.Timestamp(trigger_date) <= cooldown_until:
                continue
            prior = daily_index[daily_index <= trigger_date]
            if len(prior) == 0:
                continue
            entry_date = prior[-1]
            future = daily_index[daily_index > entry_date]
            if len(future) < n:
                continue
            entry_price = float(daily.loc[entry_date, "close"])
            exit_price  = float(daily.loc[future[n - 1], "close"])
            if not entry_price:
                continue
            returns.append((exit_price - entry_price) / entry_price * 100)
            cooldown_until = future[n - 1]
        if returns:
            wins = sum(1 for r in returns if r > 0)
            backtest_stats.append({
                "hold_days":    n,
                "sample_count": len(returns),
                "win_rate":     round(wins / len(returns) * 100, 1),
                "avg_return":   round(sum(returns) / len(returns), 2),
                "max_gain":     round(max(returns), 2),
                "max_loss":     round(min(returns), 2),
            })

    pattern = {
        "pattern": "ma_tangle_breakout",
        "pattern_name": "三線交纏帶量突破",
        "description": "MA5/MA10/MA20 三線差距 < 3%（交纏蓄勢），昨日帶量（> 均量 1.5 倍）突破 MA60，今日確認站穩，前天仍在 MA60 以下。",
        "total_triggers": len(dates),
        "trigger_dates": [pd.Timestamp(d).strftime("%Y-%m-%d") for d in dates],
        "backtest_stats": backtest_stats,
        "current": {
            "triggered": now,
            "setup_triggered": setup_triggered,
            "ma60_bonus": ma60_up,
            "ma60_direction": "up" if ma60_up else "down",
            "label": label,
        },
        "diagnostics": {
            "ma5_slope":  _slope(ma5),
            "ma10_slope": _slope(ma10),
            "ma20_slope": _slope(ma20),
            "ma60_slope": _slope(ma60),
            "close":      cur_close,
            "ma20":       cur_ma60,
            "ma60":       cur_ma60,
            "ma_spread":  three_spread,
            "ma60_gap":       ma60_gap,
            "ma60_gap_pct":   round(ma60_gap / cur_close * 100, 2) if ma60_gap and cur_close else None,
            "prev_close": prev_close,
            "prev_ma60":  day2_ma60,
            "prev_vol":       prev_vol,
            "vol_ma20":       prev_vol_ma,
            "vol_threshold":  vol_threshold,
            "cond_tangle":       cond_tangle,
            "cond_above_three":  bool(cond_above_three),
            "cond_near_ma60":    cond_near_ma60,
            "cond_short_up":     True,
            "cond_above_ma20":  cond_above_ma60,
            "cond_first_break": cond_first_break,
            "cond_support":     cond_volume,
        },
    }

    return {
        "symbol": symbol,
        **pattern,
        "patterns": [pattern],
    }


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


@app.get("/market/macro/yield-curve")
def macro_yield_curve(years: int = 5):
    """美 10Y - 2Y 殖利率利差。倒掛 = 衰退預警。需 FRED_API_KEY。"""
    return fred.yield_curve(years=years)


@app.get("/market/crypto/top")
def market_crypto_top(limit: int = 10):
    """加密貨幣 top N（CoinGecko 免費 API）。"""
    return crypto.top_markets(limit=limit)


@app.get("/market/crypto/global")
def market_crypto_global():
    """加密貨幣全球統計（總市值、BTC/ETH dominance）。"""
    return crypto.global_stats()


@app.get("/market/fx")
def market_fx(base: str = "USD"):
    """匯率（USD 對 TWD/JPY/CNY/EUR/GBP/HKD/SGD）。"""
    return fx.latest_rates(base=base)


@app.get("/market/movers")
def market_movers_rank(top: int = 10):
    """全市場今日動態：成交額前 N / 漲幅前 N / 跌幅前 N / 成交量前 N + 漲跌停家數統計。
    資料 T+0（盤後才有，盤中查到的是上一交易日資料）。"""
    return market_movers.market_movers(top_n=top)


@app.get("/market/valuation")
def market_valuation(top: int = 10):
    """全市場估值篩選（TWSE OpenAPI 官方，免費、免 key、免額度）：低本益比 + 高殖利率 各前 N。
    僅上市；最近一交易日快照。"""
    return twse_openapi.valuation_screen(top_n=top)


@app.get("/market/screen")
def market_screen(exclude_overbought: bool = True, min_foreign_days: int = 3,
                  top: int = 15, mode: str = "momentum"):
    """偏多候選多因子掃描：動能(放量/漲幅) + 籌碼(外資連買) + 技術(均線/訊號) + 估值。
    mode=momentum（動能）| steady（穩步走多/慢慢長：強制未過熱 + 多頭 + 低波動加權，附 outlook 預期區間）。
    exclude_overbought=True 排除 RSI 過熱者（找「尚未噴出」的較早設定）。研究訊號，非投資建議。"""
    return screen_module.bullish_screen(
        exclude_overbought=exclude_overbought, min_foreign_days=min_foreign_days, top=top, mode=mode)


@app.get("/market/futures/pcr")
def futures_pcr(days: int = 30):
    """台指選擇權 Put/Call Ratio（成交量比 + 未平倉比）。資料源 FinMind。"""
    return taifex.fetch_pcr(days=days)


@app.get("/market/macro/calendar")
def macro_calendar(days_ahead: int = 30, min_impact: str = "medium"):
    """未來 N 天全球經濟事件日曆（FOMC / CPI / NFP / 央行決策等）。
    min_impact: low / medium / high。資料源 Finnhub，需 FINNHUB_API_KEY。"""
    return finnhub.economic_calendar(days_ahead=days_ahead, min_impact=min_impact)


@app.get("/stock/{symbol}/earnings")
def stock_earnings(symbol: str, days_back: int = 90, days_ahead: int = 90):
    """個股財報日曆（主要美股）。需 FINNHUB_API_KEY。"""
    return finnhub.earnings_calendar(symbol, days_back=days_back, days_ahead=days_ahead)


@app.get("/stock/{symbol}/recommendations")
def stock_recommendations(symbol: str):
    """個股分析師評等趨勢（主要美股）。需 FINNHUB_API_KEY。"""
    return finnhub.recommendations(symbol)


@app.get("/stock/{symbol}/insider")
def stock_insider(symbol: str, limit: int = 20):
    """美股內部人交易（SEC EDGAR Form 4）。免費，無需 key。"""
    return sec.insider_transactions(symbol, limit=limit)


@app.get("/stock/{symbol}/monthly-revenue")
def stock_monthly_revenue(symbol: str, months: int = 24):
    """月營收（MOPS）+ MoM/YoY。每月 10 號公布上月。"""
    return fundamentals_extra.monthly_revenue(symbol, months_back=months)


@app.get("/stock/{symbol}/foreign-holding")
def stock_foreign_holding(symbol: str, weeks: int = 26):
    """外資持股比率（集保，週頻）+ 4 週變化。"""
    return fundamentals_extra.foreign_shareholding(symbol, weeks_back=weeks)


@app.get("/stock/{symbol}/margin-short")
def stock_margin_short(symbol: str, days: int = 30):
    """融資融券餘額（每日序列走 FinMind）。另附 TWSE 官方最新一日 `official_latest`
    （免 FinMind 額度）。融資=散戶借錢買；融券=散戶放空。"""
    result = fundamentals_extra.margin_short(symbol, days_back=days)
    if isinstance(result, dict):
        official = twse_openapi.margin_for(symbol)
        if official:
            result["official_latest"] = {**official, "source": "TWSE OpenAPI"}
    return result


@app.get("/stock/{symbol}/valuation")
def stock_valuation(symbol: str):
    """個股本益比 / 股價淨值比 / 殖利率（TWSE OpenAPI 官方，免費免額度；僅上市）。"""
    return twse_openapi.valuation_for(symbol)


@app.get("/stock/{symbol}/securities-lending")
def stock_securities_lending(symbol: str, days: int = 30):
    """借券賣出餘額（每日，外資放空主要管道）。"""
    return fundamentals_extra.securities_lending(symbol, days_back=days)


# ──────────────────────────────────────────────
# Watchlist + 條件記錄
# ──────────────────────────────────────────────

from pydantic import BaseModel  # noqa: E402


class WatchlistItem(BaseModel):
    symbol: str
    note: str | None = None


class ConditionItem(BaseModel):
    symbol: str
    indicator: str  # rsi / kd_k / kd_d / macd_hist / close
    op: str         # lt / gt
    threshold: float


@app.get("/watchlist")
def watchlist_list():
    """關注清單。"""
    return {"items": watchlist.list_watchlist()}


@app.post("/watchlist")
def watchlist_add(payload: WatchlistItem):
    """加入 symbol 到關注清單。"""
    return watchlist.add_watchlist(payload.symbol, payload.note)


@app.delete("/watchlist/{symbol}")
def watchlist_remove(symbol: str):
    """從關注清單移除（連同所有條件）。"""
    return watchlist.remove_watchlist(symbol)


@app.get("/watchlist/conditions")
def watchlist_conditions(symbol: str | None = None):
    """列條件（指定 symbol 則只回該股）。"""
    return {"items": watchlist.list_conditions(symbol)}


@app.post("/watchlist/conditions")
def watchlist_add_condition(payload: ConditionItem):
    """新增條件。indicator: rsi/kd_k/kd_d/macd_hist/close；op: lt/gt"""
    result = watchlist.add_condition(payload.symbol, payload.indicator, payload.op, payload.threshold)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@app.delete("/watchlist/conditions/{cid}")
def watchlist_remove_condition(cid: int):
    """刪條件。"""
    return watchlist.remove_condition(cid)


@app.get("/watchlist/status")
def watchlist_status():
    """評估所有啟用條件，回每條的目前值 + 是否觸發。"""
    return watchlist.evaluate_all()


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


@app.get("/market/pattern-scan")
def market_pattern_scan(mode: str = "both"):
    """全市場三線交纏帶量突破型態掃描。mode: triggered | setup | both（預設）。
    掃描 DB 中有日線資料的全部股票，回傳今日觸發或蓄勢中的個股清單。
    第一次執行可能需要數分鐘（依股票數量而定）。"""
    result = bt.scan_pattern_market(mode=mode)
    return result


@app.get("/market/weekly-w-bottom-scan")
def market_weekly_w_bottom_scan():
    """全市場週線W底突破掃描。"""
    return bt.scan_weekly_w_bottom()


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
# 類股前3產業個股下載 + 型態掃描
# ──────────────────────────────────────────────

def _get_sector_top3_symbols(top_n: int = 3) -> dict:
    """取資金流入前 top_n 產業的個股代碼清單，回傳 {industry: [symbol, ...]}。"""
    from data_fetcher import get_industry_map
    flow = chip_module.sector_money_flow(top_n=top_n)
    if "error" in flow:
        return {}
    top_industries = {s["industry"] for s in flow["inflow"][:top_n]}
    industry_map = get_industry_map()
    result: dict = {ind: [] for ind in top_industries}
    for symbol, ind in industry_map.items():
        if ind in top_industries:
            result[ind].append(symbol)
    return result


@app.post("/admin/download-sector-top3")
def admin_download_sector_top3(background_tasks: BackgroundTasks):
    """下載資金流入前3產業的個股歷史資料進 DB（背景執行）。"""
    sector_stocks = _get_sector_top3_symbols()
    if not sector_stocks:
        raise HTTPException(status_code=503, detail="法人資料尚未更新，無法取得類股排行")
    all_symbols = [s for symbols in sector_stocks.values() for s in symbols]
    unique = list(dict.fromkeys(all_symbols))
    background_tasks.add_task(_run_download_symbols, unique)
    summary = {ind: len(syms) for ind, syms in sector_stocks.items()}
    return {
        "status": "started",
        "total_symbols": len(unique),
        "sectors": summary,
        "message": f"共 {len(unique)} 支個股歷史資料下載已在背景執行",
    }


def _run_download_symbols(symbols: list):
    for symbol in symbols:
        ensure_stock_data(symbol)
        _time.sleep(1.2)


@app.get("/market/sector-top3/pattern-scan")
def sector_top3_pattern_scan(top_n: int = 3):
    """對資金流入前 top_n 產業的個股批次跑三線交纏型態掃描，回傳有訊號的個股。"""
    from backtest import _ma_tangle_breakout_mask, _ma60_bonus

    sector_stocks = _get_sector_top3_symbols(top_n=top_n)
    if not sector_stocks:
        raise HTTPException(status_code=503, detail="法人資料尚未更新，無法取得類股排行")

    all_symbols = [s for syms in sector_stocks.values() for s in syms]
    unique = list(dict.fromkeys(all_symbols))

    # 反查 symbol → industry
    sym_to_ind = {s: ind for ind, syms in sector_stocks.items() for s in syms}

    results = []
    for symbol in unique:
        try:
            daily = get_price_df(symbol)
            if daily is None or daily.empty or len(daily) < 65:
                continue
            daily.index = pd.to_datetime(daily.index)
            close  = daily["close"]
            volume = daily["volume"]
            ma5    = close.rolling(5).mean()
            ma10   = close.rolling(10).mean()
            ma20   = close.rolling(20).mean()
            ma60   = close.rolling(60).mean()
            vol_ma20 = volume.rolling(20).mean()

            mask   = _ma_tangle_breakout_mask(daily).fillna(False)
            now    = bool(mask.iloc[-1])
            ma60_up = bool(_ma60_bonus(daily).iloc[-1])

            cur_close  = float(close.iloc[-1])
            cur_ma60   = float(ma60.iloc[-1])
            prev_close = float(close.iloc[-2])
            prev_ma60  = float(ma60.iloc[-2])

            three_vals = [float(ma5.iloc[-1]), float(ma10.iloc[-1]), float(ma20.iloc[-1])]
            three_spread = max(three_vals) - min(three_vals)
            cond_tangle  = pd.notna(ma5.iloc[-1]) and three_spread < cur_close * 0.03
            ma60_gap     = abs(cur_close - cur_ma60)
            cond_near_ma60 = ma60_gap < cur_close * 0.03
            setup = cond_tangle and cond_near_ma60

            if not now and not setup:
                continue

            label = (
                "突破完成（MA60 上斜，力道最強）" if now and ma60_up
                else "突破完成（MA60 下斜）" if now
                else "蓄勢中，等待帶量突破 MA60"
            )

            # 基本回測勝率（5 日）
            dates = daily.index[mask].tolist()
            win_rate_5 = None
            if dates:
                returns = []
                cooldown_until = None
                for tdate in sorted(dates):
                    if cooldown_until and pd.Timestamp(tdate) <= cooldown_until:
                        continue
                    prior = daily.index[daily.index <= tdate]
                    if len(prior) == 0:
                        continue
                    future = daily.index[daily.index > prior[-1]]
                    if len(future) < 5:
                        continue
                    ep = float(daily.loc[prior[-1], "close"])
                    xp = float(daily.loc[future[4], "close"])
                    if not ep:
                        continue
                    returns.append((xp - ep) / ep * 100)
                    cooldown_until = future[4]
                if returns:
                    wins = sum(1 for r in returns if r > 0)
                    win_rate_5 = round(wins / len(returns) * 100, 1)

            # 取股名
            with get_session() as session:
                name_row = session.execute(
                    select(StockName).where(StockName.symbol == symbol)
                ).scalar_one_or_none()
            name = name_row.name if name_row else symbol

            results.append({
                "symbol":        symbol,
                "name":          name,
                "industry":      sym_to_ind.get(symbol, ""),
                "triggered":     now,
                "setup_triggered": setup,
                "ma60_bonus":    ma60_up,
                "label":         label,
                "close":         round(cur_close, 2),
                "ma60":          round(cur_ma60, 2),
                "ma60_gap_pct":  round(ma60_gap / cur_close * 100, 2),
                "win_rate_5d":   win_rate_5,
                "total_triggers": int(mask.sum()),
            })
        except Exception:
            continue

    results.sort(key=lambda x: (not x["triggered"], not x["setup_triggered"], -(x["win_rate_5d"] or 0)))

    return {
        "date": chip_module.sector_money_flow(top_n=top_n).get("date"),
        "top_industries": list(sector_stocks.keys()),
        "total_scanned": len(unique),
        "triggered_count": sum(1 for r in results if r["triggered"]),
        "setup_count":     sum(1 for r in results if r["setup_triggered"] and not r["triggered"]),
        "results":         results,
    }


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
