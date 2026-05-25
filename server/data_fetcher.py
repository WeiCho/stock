"""
資料抓取層：TWSE / TPEx / Fugle

所有歷史資料走 TWSE/TPEx 官方 HTTP endpoint，不消耗 Fugle token。
Fugle token 僅用於盤中即時報價。
"""

import time
import asyncio
from datetime import date, datetime, timedelta
from typing import Optional
import httpx
import pandas as pd
from sqlalchemy import select, delete
from db import DailyPrice, Institutional, IndexData, SyncLog, get_session

TWSE_BASE = "https://www.twse.com.tw"
TPEX_BASE = "https://www.tpex.org.tw"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; TaiwanStockBot/1.0)"}
REQUEST_DELAY = 1.2  # 秒，對 TWSE/TPEx 友善


def _sleep():
    time.sleep(REQUEST_DELAY)


# ──────────────────────────────────────────────
# 個股：上市（TWSE）日K
# ──────────────────────────────────────────────

def fetch_twse_stock_month(symbol: str, year: int, month: int) -> pd.DataFrame:
    """抓取上市個股單月日K，回傳 DataFrame(date, open, high, low, close, volume)。"""
    date_str = f"{year}{month:02d}01"
    url = f"{TWSE_BASE}/exchangeReport/STOCK_DAY"
    params = {"response": "json", "date": date_str, "stockNo": symbol}

    with httpx.Client(headers=HEADERS, timeout=15) as client:
        resp = client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()

    if data.get("stat") != "OK" or not data.get("data"):
        return pd.DataFrame()

    rows = []
    for row in data["data"]:
        try:
            # TWSE 日期格式：民國年/月/日
            y, m, d = row[0].split("/")
            real_date = date(int(y) + 1911, int(m), int(d))
            rows.append({
                "date": real_date,
                "open": float(row[3].replace(",", "")),
                "high": float(row[4].replace(",", "")),
                "low": float(row[5].replace(",", "")),
                "close": float(row[6].replace(",", "")),
                "volume": float(row[1].replace(",", "")) / 1000,  # 股→張
            })
        except (ValueError, IndexError):
            continue

    return pd.DataFrame(rows)


def fetch_stock_history(symbol: str, years: int = 10, market: str = "twse") -> int:
    """抓取個股 N 年歷史日K 並寫入 SQLite，回傳新增筆數。"""
    today = date.today()
    months_to_fetch = years * 12
    inserted = 0

    with get_session() as session:
        for i in range(months_to_fetch):
            target = today.replace(day=1) - timedelta(days=i * 30)
            y, m = target.year, target.month

            if market == "twse":
                df = fetch_twse_stock_month(symbol, y, m)
            else:
                df = fetch_tpex_stock_month(symbol, y, m)

            _sleep()

            for _, row in df.iterrows():
                existing = session.execute(
                    select(DailyPrice).where(
                        DailyPrice.symbol == symbol,
                        DailyPrice.date == row["date"]
                    )
                ).scalar_one_or_none()
                if existing is None:
                    session.add(DailyPrice(
                        symbol=symbol,
                        date=row["date"],
                        open=row["open"],
                        high=row["high"],
                        low=row["low"],
                        close=row["close"],
                        volume=row["volume"],
                    ))
                    inserted += 1

        # 更新同步時間
        log = session.execute(
            select(SyncLog).where(
                SyncLog.symbol == symbol,
                SyncLog.data_type == "price"
            )
        ).scalar_one_or_none()
        if log:
            log.last_synced = datetime.utcnow()
        else:
            session.add(SyncLog(symbol=symbol, data_type="price", last_synced=datetime.utcnow()))

        session.commit()

    return inserted


# ──────────────────────────────────────────────
# 個股：上櫃（TPEx）日K
# ──────────────────────────────────────────────

def fetch_tpex_stock_month(symbol: str, year: int, month: int) -> pd.DataFrame:
    """抓取上櫃個股單月日K。TPEx 使用民國年。"""
    roc_year = year - 1911
    url = f"{TPEX_BASE}/web/stock/aftertrading/daily_trading_info/st43_print.php"
    params = {
        "l": "zh-tw",
        "d": f"{roc_year}/{month:02d}",
        "stkno": symbol,
        "output": "json",
    }

    with httpx.Client(headers=HEADERS, timeout=15) as client:
        resp = client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()

    tables = data.get("aaData", [])
    if not tables:
        return pd.DataFrame()

    rows = []
    for row in tables:
        try:
            y, m, d = row[0].split("/")
            real_date = date(int(y) + 1911, int(m), int(d))
            rows.append({
                "date": real_date,
                "open": float(row[4].replace(",", "")),
                "high": float(row[5].replace(",", "")),
                "low": float(row[6].replace(",", "")),
                "close": float(row[7].replace(",", "")),
                "volume": float(row[1].replace(",", "")),
            })
        except (ValueError, IndexError):
            continue

    return pd.DataFrame(rows)


# ──────────────────────────────────────────────
# 全市場：三大法人每日 bulk（一 call 涵蓋全台股）
# ──────────────────────────────────────────────

def fetch_daily_institutional_bulk(target_date: Optional[date] = None) -> int:
    """抓取全市場當日三大法人買賣超，寫入 SQLite，回傳新增筆數。"""
    if target_date is None:
        target_date = date.today()

    date_str = target_date.strftime("%Y%m%d")
    url = f"{TWSE_BASE}/fund/T86"
    params = {"response": "json", "date": date_str, "selectType": "ALL"}

    with httpx.Client(headers=HEADERS, timeout=20) as client:
        resp = client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()

    if data.get("stat") != "OK" or not data.get("data"):
        return 0

    inserted = 0
    with get_session() as session:
        for row in data["data"]:
            try:
                symbol = row[0].strip()
                foreign = float(row[4].replace(",", "")) / 1000  # 股→張
                trust = float(row[10].replace(",", "")) / 1000
                dealer = float(row[14].replace(",", "")) / 1000
                total = foreign + trust + dealer

                existing = session.execute(
                    select(Institutional).where(
                        Institutional.symbol == symbol,
                        Institutional.date == target_date
                    )
                ).scalar_one_or_none()

                if existing is None:
                    session.add(Institutional(
                        symbol=symbol,
                        date=target_date,
                        foreign_buy=foreign,
                        trust_buy=trust,
                        dealer_buy=dealer,
                        total_buy=total,
                    ))
                    inserted += 1

            except (ValueError, IndexError):
                continue

        # 更新 bulk 同步時間
        log = session.execute(
            select(SyncLog).where(
                SyncLog.symbol == "__bulk__",
                SyncLog.data_type == "institutional_bulk"
            )
        ).scalar_one_or_none()
        if log:
            log.last_synced = datetime.utcnow()
        else:
            session.add(SyncLog(
                symbol="__bulk__",
                data_type="institutional_bulk",
                last_synced=datetime.utcnow()
            ))

        session.commit()

    return inserted


# ──────────────────────────────────────────────
# 大盤指數：加權 + 櫃買
# ──────────────────────────────────────────────

def fetch_taiex_history(years: int = 10) -> int:
    """抓取加權指數歷史，以年為單位。"""
    inserted = 0
    current_year = date.today().year

    with get_session() as session:
        for y in range(current_year, current_year - years, -1):
            url = f"{TWSE_BASE}/indicesReport/MI_5MINS_HIST"
            params = {"response": "json", "date": f"{y}0101"}

            try:
                with httpx.Client(headers=HEADERS, timeout=15) as client:
                    resp = client.get(url, params=params)
                    resp.raise_for_status()
                    data = resp.json()
            except Exception:
                _sleep()
                continue

            _sleep()

            for row in data.get("data", []):
                try:
                    parts = row[0].split("/")
                    real_date = date(int(parts[0]) + 1911, int(parts[1]), int(parts[2]))
                    close = float(row[1].replace(",", ""))
                    existing = session.execute(
                        select(IndexData).where(
                            IndexData.name == "TAIEX",
                            IndexData.date == real_date
                        )
                    ).scalar_one_or_none()
                    if existing is None:
                        session.add(IndexData(
                            name="TAIEX",
                            date=real_date,
                            close=close,
                            volume=0,
                            change=0,
                        ))
                        inserted += 1
                except (ValueError, IndexError):
                    continue

        session.commit()

    return inserted


# ──────────────────────────────────────────────
# 判斷市場別（上市 / 上櫃）
# ──────────────────────────────────────────────

def detect_market(symbol: str) -> str:
    """
    簡易判斷：4 碼數字且開頭 1-9 → TWSE 上市
    開頭為英文或五碼以上 → TPEx 上櫃
    實際應查詢 TWSE/TPEx 股票清單確認。
    """
    if symbol.isdigit() and len(symbol) == 4:
        return "twse"
    return "tpex"


# ──────────────────────────────────────────────
# 每日增量更新（server 啟動時呼叫）
# ──────────────────────────────────────────────

def daily_update() -> dict:
    """
    檢查今日是否已更新，若否則執行：
    1. 三大法人全市場 bulk
    2. 加權指數（只抓最近一年補漏）
    回傳更新結果摘要。
    """
    today = date.today()

    with get_session() as session:
        bulk_log = session.execute(
            select(SyncLog).where(
                SyncLog.symbol == "__bulk__",
                SyncLog.data_type == "institutional_bulk"
            )
        ).scalar_one_or_none()

    already_updated = (
        bulk_log is not None and
        bulk_log.last_synced.date() >= today
    )

    if already_updated:
        return {"status": "already_up_to_date", "date": str(today)}

    institutional_count = fetch_daily_institutional_bulk(today)
    _sleep()
    index_count = fetch_taiex_history(years=1)

    return {
        "status": "updated",
        "date": str(today),
        "institutional_records": institutional_count,
        "index_records": index_count,
    }


# ──────────────────────────────────────────────
# 取得 SQLite 中已有的個股資料（供模組讀取）
# ──────────────────────────────────────────────

def get_price_df(symbol: str) -> pd.DataFrame:
    """從 SQLite 讀取個股所有日K，回傳排序後的 DataFrame。"""
    with get_session() as session:
        rows = session.execute(
            select(DailyPrice)
            .where(DailyPrice.symbol == symbol)
            .order_by(DailyPrice.date)
        ).scalars().all()

    if not rows:
        return pd.DataFrame()

    return pd.DataFrame([{
        "date": r.date,
        "open": r.open,
        "high": r.high,
        "low": r.low,
        "close": r.close,
        "volume": r.volume,
    } for r in rows]).set_index("date")


def get_institutional_df(symbol: str, days: int = 60) -> pd.DataFrame:
    """從 SQLite 讀取個股三大法人近 N 天資料。"""
    cutoff = date.today() - timedelta(days=days)
    with get_session() as session:
        rows = session.execute(
            select(Institutional)
            .where(
                Institutional.symbol == symbol,
                Institutional.date >= cutoff
            )
            .order_by(Institutional.date)
        ).scalars().all()

    if not rows:
        return pd.DataFrame()

    return pd.DataFrame([{
        "date": r.date,
        "foreign_buy": r.foreign_buy,
        "trust_buy": r.trust_buy,
        "dealer_buy": r.dealer_buy,
        "total_buy": r.total_buy,
    } for r in rows]).set_index("date")


def ensure_stock_data(symbol: str) -> bool:
    """
    確保個股資料存在；若尚未下載則觸發歷史資料抓取。
    回傳 True 表示資料就緒。
    """
    with get_session() as session:
        log = session.execute(
            select(SyncLog).where(
                SyncLog.symbol == symbol,
                SyncLog.data_type == "price"
            )
        ).scalar_one_or_none()

    if log is None:
        market = detect_market(symbol)
        fetch_stock_history(symbol, years=10, market=market)

    return True
