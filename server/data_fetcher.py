"""
資料抓取層：TWSE / TPEx 官方開放資料。

個股日K、三大法人、加權指數皆走 TWSE/TPEx 官方 HTTP / OpenAPI endpoint，免付費 API。
"""

import ssl
import time
from datetime import date, datetime, timedelta
from typing import Optional
import httpx
import pandas as pd
from sqlalchemy import select, func
from db import DailyPrice, Institutional, IndexData, SyncLog, StockName, get_session

TWSE_BASE = "https://www.twse.com.tw"
TPEX_BASE = "https://www.tpex.org.tw"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; TaiwanStockBot/1.0)"}
REQUEST_DELAY = 1.2  # 秒，對 TWSE/TPEx 友善

# OpenSSL 3（Python 3.13+）預設啟用 X509 嚴格檢查，會因 TPEx 憑證鏈缺少
# Subject Key Identifier 而拒絕連線。放寬此擴充檢查，但仍完整驗證憑證與主機名稱。
try:
    import certifi
    _SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except Exception:
    _SSL_CTX = ssl.create_default_context()
_SSL_CTX.verify_flags &= ~ssl.VERIFY_X509_STRICT


def _client(timeout: float = 15) -> httpx.Client:
    """建立統一設定的 httpx Client（放寬 X509 嚴格檢查、跟隨轉址）。"""
    return httpx.Client(headers=HEADERS, timeout=timeout, verify=_SSL_CTX, follow_redirects=True)


def _sleep():
    time.sleep(REQUEST_DELAY)


def _num(v) -> float:
    """把 TWSE/TPEx 數字欄位轉 float：可能是含千分位逗號的字串，也可能是數字（0）或空字串。"""
    if isinstance(v, (int, float)):
        return float(v)
    return float(str(v).replace(",", "").strip() or 0)


# ──────────────────────────────────────────────
# 個股：上市（TWSE）日K
# ──────────────────────────────────────────────

def fetch_twse_stock_month(symbol: str, year: int, month: int) -> pd.DataFrame:
    """抓取上市個股單月日K，回傳 DataFrame(date, open, high, low, close, volume)。"""
    date_str = f"{year}{month:02d}01"
    url = f"{TWSE_BASE}/exchangeReport/STOCK_DAY"
    params = {"response": "json", "date": date_str, "stockNo": symbol}

    with _client(15) as client:
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
                "open": _num(row[3]),
                "high": _num(row[4]),
                "low": _num(row[5]),
                "close": _num(row[6]),
                "volume": _num(row[1]) / 1000,  # 股→張
            })
        except (ValueError, IndexError, TypeError, AttributeError):
            continue

    return pd.DataFrame(rows)


def fetch_stock_history(symbol: str, years: int = 10, market: str = "twse") -> int:
    """抓取個股 N 年歷史日K 並寫入 SQLite，回傳新增筆數。"""
    today = date.today()
    months_to_fetch = years * 12

    with get_session() as session:
        # 先一次查出已有日期，避免逐列 SELECT（10 年約 2400 列）
        existing_dates = set(session.execute(
            select(DailyPrice.date).where(DailyPrice.symbol == symbol)
        ).scalars().all())

        new_rows = []
        empty_recent = 0
        for i in range(months_to_fetch):
            # 以「曆月」往前推，避免用 30 天近似造成整月被跳過（例如 2 月）。
            target = _month_offset(today, i)
            y, m = target.year, target.month

            if market == "twse":
                df = fetch_twse_stock_month(symbol, y, m)
            else:
                df = fetch_tpex_stock_month(symbol, y, m)

            _sleep()

            # 最近月份連續抓不到、且原本也無資料 → 該檔大概不在此市場（或代碼無效），
            # 提早結束以免對著無效/錯市場的股票空轉整整 10 年（240 次請求）。
            if df.empty:
                if not new_rows and not existing_dates:
                    empty_recent += 1
                    if empty_recent >= 3:
                        break
                continue

            for _, row in df.iterrows():
                if row["date"] in existing_dates:
                    continue
                existing_dates.add(row["date"])
                new_rows.append(DailyPrice(
                    symbol=symbol,
                    date=row["date"],
                    open=row["open"],
                    high=row["high"],
                    low=row["low"],
                    close=row["close"],
                    volume=row["volume"],
                ))

        session.add_all(new_rows)
        inserted = len(new_rows)

        # 僅在實際抓到資料時記錄同步時間，否則保持未同步以便之後重試
        # （例如把上櫃股票誤判為上市而抓到空資料的情況）。
        if inserted > 0:
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
    """抓取上櫃個股單月日K（TPEx 新版 tradingStock JSON 端點）。

    舊的 st43_print.php 已停用（404）。新端點：
      /www/zh-tw/afterTrading/tradingStock?code=&date=YYYY/MM/01&id=&response=json
    回傳欄位：日期 / 成交張數 / 成交仟元 / 開 / 高 / 低 / 收 / 漲跌 / 筆數
    （成交量單位已是「張」，故不需再除以 1000）。
    """
    url = f"{TPEX_BASE}/www/zh-tw/afterTrading/tradingStock"
    params = {
        "code": symbol,
        "date": f"{year}/{month:02d}/01",
        "id": "",
        "response": "json",
    }

    try:
        with _client(15) as client:
            resp = client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception:
        return pd.DataFrame()

    tables = data.get("tables") or []
    if not tables or not tables[0].get("data"):
        return pd.DataFrame()

    rows = []
    for row in tables[0]["data"]:
        try:
            y, m, d = row[0].split("/")
            real_date = date(int(y) + 1911, int(m), int(d))
            rows.append({
                "date": real_date,
                "open": _num(row[3]),
                "high": _num(row[4]),
                "low": _num(row[5]),
                "close": _num(row[6]),
                "volume": _num(row[1]),  # 成交張數（已是張）
            })
        except (ValueError, IndexError, TypeError, AttributeError):
            continue

    return pd.DataFrame(rows)


# ──────────────────────────────────────────────
# 全市場：三大法人每日 bulk（一 call 涵蓋全台股）
# ──────────────────────────────────────────────

def fetch_daily_institutional_bulk(target_date: Optional[date] = None) -> int:
    """抓取全市場「單日」三大法人買賣超並寫入 SQLite，回傳新增筆數。

    僅負責抓一天的資料；同步狀態標記由 daily_update 統一管理。
    當天若尚未公布（盤後 T86 通常於收盤後才更新）會回傳 0。
    """
    if target_date is None:
        target_date = date.today()

    url = f"{TWSE_BASE}/fund/T86"
    params = {"response": "json", "date": target_date.strftime("%Y%m%d"), "selectType": "ALL"}

    try:
        with _client(20) as client:
            resp = client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception:
        return 0

    if data.get("stat") != "OK" or not data.get("data"):
        return 0

    with get_session() as session:
        # 一次查出當日已存在的代碼，避免逐列 SELECT（全市場約 1.6 萬列）
        existing = set(session.execute(
            select(Institutional.symbol).where(Institutional.date == target_date)
        ).scalars().all())

        new_rows = []
        for row in data["data"]:
            try:
                symbol = row[0].strip()
                if symbol in existing:
                    continue
                # T86 欄位（股數）：外資=外陸資[4]+外資自營商[7]；投信[10]；自營商合計[11]（自行+避險）。
                # 原本用 [14]（僅自營商自行買賣）會漏掉避險部位，導致自營商與三大法人合計錯誤。
                # 欄位可能是字串（含逗號）或數字 0，故以 _num 統一轉換。
                foreign = (_num(row[4]) + _num(row[7])) / 1000
                trust = _num(row[10]) / 1000
                dealer = _num(row[11]) / 1000
                new_rows.append(Institutional(
                    symbol=symbol,
                    date=target_date,
                    foreign_buy=foreign,
                    trust_buy=trust,
                    dealer_buy=dealer,
                    total_buy=foreign + trust + dealer,
                ))
            except (ValueError, IndexError, TypeError, AttributeError):
                continue

        session.add_all(new_rows)
        session.commit()

    return len(new_rows)


def backfill_institutional(lookback_days: int = 12, min_days: int = 5) -> dict:
    """往前補抓最近數個交易日的三大法人 bulk，讓 server 一啟動就有可用資料。

    成功取得 min_days 天資料後即停止；最多回溯 lookback_days 個日曆日，
    因此遇到連假也能往前找到最近的交易日。
    """
    today = date.today()
    days_with_data = 0
    total = 0
    for i in range(lookback_days + 1):
        d = today - timedelta(days=i)
        if d.weekday() >= 5:   # 週末跳過
            continue
        n = fetch_daily_institutional_bulk(d)
        _sleep()
        if n > 0:
            days_with_data += 1
            total += n
            if days_with_data >= min_days:
                break
    return {"days": days_with_data, "records": total}


# ──────────────────────────────────────────────
# 大盤指數：加權 + 櫃買
# ──────────────────────────────────────────────

def _month_offset(base: date, months_back: int) -> date:
    """回傳 base 往前 months_back 個月的月份第一天。"""
    y, m = base.year, base.month - months_back
    while m <= 0:
        m += 12
        y -= 1
    return date(y, m, 1)


def fetch_taiex_history(months: int = 12) -> int:
    """抓取加權指數歷史，以月為單位逐月抓取。
    MI_5MINS_HIST 每次查詢回傳指定月份的每日 OHLC，欄位順序：日期/開/高/低/收。
    """
    inserted = 0
    today = date.today()

    with get_session() as session:
        for i in range(months):
            target = _month_offset(today, i)
            date_str = target.strftime("%Y%m%d")

            url = f"{TWSE_BASE}/indicesReport/MI_5MINS_HIST"
            params = {"response": "json", "date": date_str}

            try:
                with _client(15) as client:
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
                    close = _num(row[4])  # row[4] = 收盤價
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
                except (ValueError, IndexError, TypeError, AttributeError):
                    continue

        session.commit()

    return inserted


# ──────────────────────────────────────────────
# 判斷市場別（上市 / 上櫃）
# ──────────────────────────────────────────────

def get_market(symbol: str) -> Optional[str]:
    """從股票清單查詢市場別（twse / tpex）。查不到回傳 None。

    注意：不能用「4 碼數字＝上市」這種啟發式判斷，因為大量上櫃股票
    （如 5274、6488、8069）也是 4 碼，會被誤判為上市而抓到空資料。
    """
    with get_session() as session:
        rec = session.execute(
            select(StockName).where(StockName.symbol == symbol)
        ).scalar_one_or_none()
    return rec.market if rec else None


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

    # 補抓最近數個交易日的法人資料（今天盤後資料可能尚未公布）
    inst = backfill_institutional()
    index_count = fetch_taiex_history(months=6)

    # 取得任何法人資料後才標記今日已同步，避免「今天尚未公布」時提前鎖定而當日不再重試
    if inst["days"] > 0:
        with get_session() as session:
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
                    last_synced=datetime.utcnow(),
                ))
            session.commit()

    return {
        "status": "updated",
        "date": str(today),
        "institutional_days": inst["days"],
        "institutional_records": inst["records"],
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
    依股票清單判斷市場別，先試最可能的市場，抓不到再試另一個，
    因此上櫃 4 碼股票也能正確下載。回傳 True 表示資料就緒。
    """
    with get_session() as session:
        has_data = session.execute(
            select(DailyPrice.id).where(DailyPrice.symbol == symbol).limit(1)
        ).first() is not None

    if has_data:
        return True

    # 依市場別決定嘗試順序；清單查不到則兩個市場都試。
    market = get_market(symbol)
    order = {
        "twse": ["twse", "tpex"],
        "tpex": ["tpex", "twse"],
    }.get(market, ["twse", "tpex"])

    inserted = 0
    for mkt in order:
        inserted = fetch_stock_history(symbol, years=10, market=mkt)
        if inserted > 0:
            break

    return inserted > 0


# ──────────────────────────────────────────────
# 股票清單（代碼 ↔ 中文名稱）
# ──────────────────────────────────────────────

def _is_tradable_stock(symbol: str) -> bool:
    """只保留個股（4 碼數字）、特別股（4 碼數字+字母）與 ETF/ETN（00 開頭），
    過濾掉 6 碼權證等衍生性商品，避免污染清單與搜尋結果。"""
    if symbol.startswith("00"):
        return True
    return len(symbol) in (4, 5) and symbol[:4].isdigit()


def fetch_stock_list() -> int:
    """
    從 TWSE 與 TPEx 抓取全部掛牌股票清單，寫入 stock_names 表。
    回傳寫入筆數。
    """
    stocks: list[dict] = []

    # 上市（TWSE）
    try:
        url = f"{TWSE_BASE}/exchangeReport/STOCK_DAY_ALL"
        with _client(20) as client:
            resp = client.get(url, params={"response": "json"})
            resp.raise_for_status()
            data = resp.json()
        for row in data.get("data", []):
            symbol = row[0].strip()
            name = row[1].strip()
            if symbol and name and _is_tradable_stock(symbol):
                stocks.append({"symbol": symbol, "name": name, "market": "twse"})
    except Exception:
        pass

    _sleep()

    # 上櫃（TPEx）— 改用官方 OpenAPI（舊的 otc_quotes_no1430.htm 已停用）
    try:
        url = f"{TPEX_BASE}/openapi/v1/tpex_mainboard_daily_close_quotes"
        with _client(30) as client:
            resp = client.get(url)
            resp.raise_for_status()
            data = resp.json()
        for row in data:
            symbol = str(row.get("SecuritiesCompanyCode", "")).strip()
            name = str(row.get("CompanyName", "")).strip()
            if symbol and name and _is_tradable_stock(symbol):
                stocks.append({"symbol": symbol, "name": name, "market": "tpex"})
    except Exception:
        pass

    if not stocks:
        return 0

    with get_session() as session:
        existing = {r.symbol for r in session.execute(select(StockName)).scalars().all()}
        new_records = [
            StockName(symbol=s["symbol"], name=s["name"], market=s["market"])
            for s in stocks if s["symbol"] not in existing
        ]
        # 更新已存在的名稱
        for s in stocks:
            if s["symbol"] in existing:
                rec = session.execute(
                    select(StockName).where(StockName.symbol == s["symbol"])
                ).scalar_one_or_none()
                if rec and rec.name != s["name"]:
                    rec.name = s["name"]
        session.add_all(new_records)
        session.commit()

    return len(stocks)


def search_stock(query: str, limit: int = 10) -> list[dict]:
    """
    用代碼或中文名稱模糊搜尋股票，回傳 [{symbol, name, market}]。
    """
    q = query.strip()
    with get_session() as session:
        if q.isdigit():
            rows = session.execute(
                select(StockName)
                .where(StockName.symbol.like(f"{q}%"))
                .order_by(func.length(StockName.symbol), StockName.symbol)
                .limit(limit)
            ).scalars().all()
        else:
            # 以名稱長度排序，讓「元太」這類本尊排在「元太○○購01」等衍生商品之前
            rows = session.execute(
                select(StockName)
                .where(StockName.name.like(f"%{q}%"))
                .order_by(func.length(StockName.name), StockName.symbol)
                .limit(limit)
            ).scalars().all()
    return [{"symbol": r.symbol, "name": r.name, "market": r.market} for r in rows]
