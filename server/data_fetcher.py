"""
資料抓取層：TWSE / TPEx 官方開放資料。

個股日K、三大法人、加權指數皆走 TWSE/TPEx 官方 HTTP / OpenAPI endpoint，免付費 API。
"""

import logging
import ssl
import time
from datetime import date, datetime, timedelta
from typing import Optional
import httpx
import pandas as pd
from sqlalchemy import select, func, insert
from db import DailyPrice, Institutional, IndexData, SyncLog, StockName, StockIndustry, get_session

# 用 uvicorn 既有的 logger，啟動時即可在 console 看到（CLI 下則退回 root，仍會印 warning）
log = logging.getLogger("uvicorn.error")

TWSE_BASE = "https://www.twse.com.tw"
TPEX_BASE = "https://www.tpex.org.tw"
FINMIND_BASE = "https://api.finmindtrade.com/api/v4/data"
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
        try:
            data = resp.json()
        except Exception:
            return pd.DataFrame()

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

            try:
                if market == "twse":
                    df = fetch_twse_stock_month(symbol, y, m)
                else:
                    df = fetch_tpex_stock_month(symbol, y, m)
            except Exception:
                _sleep()
                continue

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
                new_rows.append({
                    "symbol": symbol,
                    "date": row["date"],
                    "open": row["open"],
                    "high": row["high"],
                    "low": row["low"],
                    "close": row["close"],
                    "volume": row["volume"],
                })

        # 使用 INSERT OR IGNORE 避免並發請求或重複抓取造成 UNIQUE constraint 錯誤
        if new_rows:
            session.execute(
                insert(DailyPrice).prefix_with("OR IGNORE"),
                new_rows,
            )
        inserted = len(new_rows)

        # 僅在實際抓到資料時記錄同步時間，否則保持未同步以便之後重試
        # （例如把上櫃股票誤判為上市而抓到空資料的情況）。
        if inserted > 0:
            # 變數名避開 `log` — 函式內任何位置出現 `log =` 都會讓整個函式的 `log` 變 local，
            # 讓 except 分支的 `log.warning(...)` 變成 UnboundLocalError
            sync_row = session.execute(
                select(SyncLog).where(
                    SyncLog.symbol == symbol,
                    SyncLog.data_type == "price"
                )
            ).scalar_one_or_none()
            if sync_row:
                sync_row.last_synced = datetime.utcnow()
            else:
                session.add(SyncLog(symbol=symbol, data_type="price", last_synced=datetime.utcnow()))

        session.commit()

    return inserted


# ──────────────────────────────────────────────
# 個股：FinMind 一次抓取整段歷史（最快，作為首選）
# ──────────────────────────────────────────────

def fetch_finmind_price_history(symbol: str, years: int = 10) -> int:
    """用 FinMind TaiwanStockPrice 單一請求抓完整段歷史日K（上市櫃皆可）。

    比逐月爬 TWSE/TPEx（約 120 次請求、~150 秒）快上百倍（約 1 秒）。
    成功回傳新增筆數；無資料或失敗（含被限流）回傳 -1，呼叫端可改用爬蟲。
    """
    start = (date.today() - timedelta(days=365 * years + 30)).isoformat()
    try:
        with _client(30) as client:
            resp = client.get(FINMIND_BASE, params={
                "dataset": "TaiwanStockPrice",
                "data_id": symbol,
                "start_date": start,
            })
            resp.raise_for_status()
            payload = resp.json()
    except Exception as e:
        log.warning("FinMind 抓 %s 價格失敗，改用爬蟲：%s", symbol, e)
        return -1

    rows = payload.get("data") or []
    if not rows:
        return -1  # 沒資料或被限流 → 交給 TWSE/TPEx 爬蟲

    with get_session() as session:
        existing_dates = set(session.execute(
            select(DailyPrice.date).where(DailyPrice.symbol == symbol)
        ).scalars().all())

        new_rows = []
        for r in rows:
            try:
                d = date.fromisoformat(r["date"])
                if d in existing_dates:
                    continue
                existing_dates.add(d)
                new_rows.append({
                    "symbol": symbol,
                    "date": d,
                    "open": _num(r["open"]),
                    "high": _num(r["max"]),   # FinMind 用 max/min 表示最高/最低
                    "low": _num(r["min"]),
                    "close": _num(r["close"]),
                    "volume": _num(r["Trading_Volume"]) / 1000,  # 股→張
                })
            except (ValueError, KeyError, TypeError):
                continue

        if new_rows:
            session.execute(insert(DailyPrice).prefix_with("OR IGNORE"), new_rows)
            sync_row = session.execute(
                select(SyncLog).where(SyncLog.symbol == symbol, SyncLog.data_type == "price")
            ).scalar_one_or_none()
            if sync_row:
                sync_row.last_synced = datetime.utcnow()
            else:
                session.add(SyncLog(symbol=symbol, data_type="price", last_synced=datetime.utcnow()))
        session.commit()

    return len(new_rows)


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
    except Exception as e:
        log.warning("TPEx tradingStock %s %d/%d 抓取失敗：%s", symbol, year, month, e)
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
    except Exception as e:
        log.warning("TWSE T86 %s 抓三大法人失敗：%s", target_date, e)
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
                new_rows.append({
                    "symbol": symbol,
                    "date": target_date,
                    "foreign_buy": foreign,
                    "trust_buy": trust,
                    "dealer_buy": dealer,
                    "total_buy": foreign + trust + dealer,
                })
            except (ValueError, IndexError, TypeError, AttributeError):
                continue

        if new_rows:
            session.execute(
                insert(Institutional).prefix_with("OR IGNORE"),
                new_rows,
            )
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


def fetch_market_breadth(target_date: Optional[date] = None) -> dict:
    """TWSE MI_INDEX(type=MS) 大盤統計：上市股票漲跌家數 + 全市場成交金額（盤後資料）。

    未指定日期則從今天往前找最近有資料的交易日。回傳
    {date, turnover(元), up, down, unchanged}；取不到回傳 {}。
    """
    candidates = [target_date] if target_date else [date.today() - timedelta(days=i) for i in range(8)]
    for d in candidates:
        if d is None or d.weekday() >= 5:
            continue
        try:
            with _client(6) as client:
                resp = client.get(
                    f"{TWSE_BASE}/exchangeReport/MI_INDEX",
                    params={"response": "json", "date": d.strftime("%Y%m%d"), "type": "MS"},
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as e:
            log.info("MI_INDEX MS %s 抓盤後概況失敗（嘗試前一日）：%s", d, e)
            continue
        if data.get("stat") != "OK":
            continue

        turnover = None
        up = down = unchanged = None
        for t in data.get("tables") or []:
            fields = t.get("fields") or []
            rows = t.get("data") or []
            # 成交金額：加總各「編號類別」列（避免抓到合計列重複計算）
            if "成交金額(元)" in fields:
                idx = fields.index("成交金額(元)")
                total = 0.0
                for r in rows:
                    if str(r[0]).strip()[:1].isdigit():
                        total += _num(r[idx])
                turnover = total
            # 漲跌家數：取「股票」欄（上市個股）
            if fields[:1] == ["類型"] and "股票" in fields:
                col = fields.index("股票")

                def _count(label):
                    row = next((r for r in rows if str(r[0]).startswith(label)), None)
                    if not row:
                        return None
                    try:
                        return int(str(row[col]).split("(")[0].replace(",", "").strip())
                    except (ValueError, IndexError):
                        return None

                up, down, unchanged = _count("上漲"), _count("下跌"), _count("持平")

        if turnover is not None or up is not None:
            return {
                "date": d.isoformat(),
                "turnover": turnover,
                "up": up,
                "down": down,
                "unchanged": unchanged,
            }
    return {}


async def fetch_live_index() -> dict:
    """TWSE MIS 即時加權指數（盤中每幾秒更新；非交易時段回最後狀態）。

    回傳 {index, prev_close, change, change_pct, open, high, low, time, date}；
    取不到時回傳 {}。註：三大法人為盤後資料，無對應的即時版本。

    用 async + 較短 timeout：此端點被前端每 20 秒輪詢，做成可取消的非同步請求，
    伺服器關閉時不會卡在無法中斷的同步執行緒裡。
    """
    url = "https://mis.twse.com.tw/stock/api/getStockInfo.jsp"
    params = {"ex_ch": "tse_t00.tw", "json": "1", "delay": "0"}
    headers = {**HEADERS, "Referer": "https://mis.twse.com.tw/stock/index.jsp"}
    try:
        async with httpx.AsyncClient(headers=headers, timeout=6, verify=_SSL_CTX,
                                     follow_redirects=True) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        log.warning("TWSE MIS 即時加權指數抓取失敗：%s", e)
        return {}

    arr = data.get("msgArray") or []
    if not arr:
        return {}
    x = arr[0]

    def g(key):
        v = x.get(key, "")
        try:
            return float(str(v).replace(",", ""))
        except (ValueError, TypeError):
            return None

    index = g("z")
    if index is None:  # 盤前 / 尚無成交價時退回開盤或昨收
        index = g("o") or g("y")
    prev = g("y")
    change = round(index - prev, 2) if (index is not None and prev is not None) else None
    change_pct = round(change / prev * 100, 2) if (change is not None and prev) else None

    return {
        "index": index,
        "prev_close": prev,
        "change": change,
        "change_pct": change_pct,
        "open": g("o"),
        "high": g("h"),
        "low": g("l"),
        "time": x.get("t"),
        "date": x.get("d"),
    }


def fetch_taiex_finmind(years: int = 5) -> int:
    """用 FinMind 一次抓取加權指數日線（數年），寫入 index_data。回傳新增筆數。

    供大盤走勢的時間區間（1月～5年）使用；比逐月爬 TWSE 快很多（一個請求 vs 數十次）。
    """
    start = (date.today() - timedelta(days=365 * years + 30)).isoformat()
    try:
        with _client(30) as client:
            resp = client.get(FINMIND_BASE, params={
                "dataset": "TaiwanStockPrice", "data_id": "TAIEX", "start_date": start,
            })
            resp.raise_for_status()
            rows = resp.json().get("data", [])
    except Exception as e:
        log.warning("FinMind TAIEX 歷史抓取失敗：%s", e)
        return 0
    if not rows:
        return 0

    with get_session() as session:
        existing = set(session.execute(
            select(IndexData.date).where(IndexData.name == "TAIEX")
        ).scalars().all())
        new_rows = []
        for r in rows:
            try:
                d = date.fromisoformat(r["date"])
                if d in existing:
                    continue
                existing.add(d)
                new_rows.append({
                    "name": "TAIEX", "date": d,
                    "close": _num(r["close"]), "volume": 0, "change": _num(r.get("spread", 0)),
                })
            except (ValueError, KeyError, TypeError):
                continue
        if new_rows:
            session.execute(insert(IndexData).prefix_with("OR IGNORE"), new_rows)
        session.commit()
    return len(new_rows)


def fetch_taiex_history(months: int = 12) -> int:
    """抓取加權指數歷史，以月為單位逐月抓取。
    MI_5MINS_HIST 每次查詢回傳指定月份的每日 OHLC，欄位順序：日期/開/高/低/收。
    """
    today = date.today()

    with get_session() as session:
        # INSERT OR IGNORE 的結果在 ORM 批次插入下沒有可靠的 rowcount，
        # 改用前後筆數差計算實際新增數。
        before = session.execute(
            select(func.count()).select_from(IndexData).where(IndexData.name == "TAIEX")
        ).scalar_one()
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
            except Exception as e:
                log.info("TWSE MI_5MINS_HIST %s 抓取失敗（重試下一月）：%s", date_str, e)
                _sleep()
                continue

            _sleep()

            batch = []
            for row in data.get("data", []):
                try:
                    parts = row[0].split("/")
                    real_date = date(int(parts[0]) + 1911, int(parts[1]), int(parts[2]))
                    close = _num(row[4])  # row[4] = 收盤價
                    batch.append({
                        "name": "TAIEX",
                        "date": real_date,
                        "close": close,
                        "volume": 0,
                        "change": 0,
                    })
                except (ValueError, IndexError, TypeError, AttributeError):
                    continue
            if batch:
                session.execute(
                    insert(IndexData).prefix_with("OR IGNORE"),
                    batch,
                )

        after = session.execute(
            select(func.count()).select_from(IndexData).where(IndexData.name == "TAIEX")
        ).scalar_one()
        session.commit()

    return after - before


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
            # NB: 變數名避開 `log` — 否則會在 function-scope 遮蔽模組頂層 logger，
            # 當 inst["days"]==0 時整個 if 跳過，下方 log.info 會炸 UnboundLocalError
            sync_row = session.execute(
                select(SyncLog).where(
                    SyncLog.symbol == "__bulk__",
                    SyncLog.data_type == "institutional_bulk"
                )
            ).scalar_one_or_none()
            if sync_row:
                sync_row.last_synced = datetime.utcnow()
            else:
                session.add(SyncLog(
                    symbol="__bulk__",
                    data_type="institutional_bulk",
                    last_synced=datetime.utcnow(),
                ))
            session.commit()

    log.info("每日更新：法人 %s 個交易日 / %s 筆，加權指數 +%s 筆",
             inst["days"], inst["records"], index_count)
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

def resample_ohlc(df: pd.DataFrame, tf: str) -> pd.DataFrame:
    """以日K 為基礎重採樣為其他時間框架。tf: 1d / 3d / 5d / 1w / 3w / 1mo（其他回原樣）。

    3d / 5d 以「交易日」分桶（非曆日），3w 以週K 再分桶 3 根，1mo 以曆月。
    """
    if df.empty or tf in (None, "1d", "daily"):
        return df
    d = df.copy()
    d.index = pd.to_datetime(d.index)
    ohlc = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}

    if tf == "1mo":
        return d.resample("ME").agg(ohlc).dropna()
    if tf in ("1w", "weekly"):
        return d.resample("W-FRI").agg(ohlc).dropna()
    if tf in ("2w", "3w"):
        n = int(tf[:-1])  # 2 或 3
        w = d.resample("W-FRI").agg(ohlc).dropna()
        if w.empty:
            return w
        buckets = [i // n for i in range(len(w))]
        out = w.groupby(buckets).agg(ohlc)
        out.index = pd.Index([w.index[min((i + 1) * n - 1, len(w) - 1)] for i in range(len(out))])
        return out
    if tf in ("3d", "5d"):
        n = int(tf[:-1])
        buckets = [i // n for i in range(len(d))]
        out = d.groupby(buckets).agg(ohlc)
        out.index = pd.Index([d.index[min((i + 1) * n - 1, len(d) - 1)] for i in range(len(out))])
        return out
    return d


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
    優先用 FinMind 單一請求抓完整段歷史（最快，約 1 秒）；失敗或被限流時，
    再依股票清單的市場別逐月爬 TWSE/TPEx（上櫃 4 碼股票也能正確下載）。
    回傳 True 表示資料就緒。
    """
    with get_session() as session:
        has_data = session.execute(
            select(DailyPrice.id).where(DailyPrice.symbol == symbol).limit(1)
        ).first() is not None

    if has_data:
        return True

    log.info("首次查詢 %s，開始下載 10 年歷史…", symbol)
    # 1) 首選 FinMind（單一請求，免逐月爬 ~120 次）
    n = fetch_finmind_price_history(symbol, years=10)
    if n > 0:
        log.info("%s 歷史下載完成：FinMind %d 筆", symbol, n)
        return True

    # 2) 退回 TWSE/TPEx 爬蟲；依市場別決定嘗試順序，清單查不到則兩個市場都試。
    log.info("%s FinMind 無資料，改用 TWSE/TPEx 逐月爬取…", symbol)
    market = get_market(symbol)
    order = {
        "twse": ["twse", "tpex"],
        "tpex": ["tpex", "twse"],
    }.get(market, ["twse", "tpex"])

    inserted = 0
    for mkt in order:
        try:
            inserted = fetch_stock_history(symbol, years=10, market=mkt)
        except Exception as e:
            log.warning("%s %s 爬取例外：%s", symbol, mkt, e)
            inserted = 0
        if inserted > 0:
            break

    if inserted > 0:
        log.info("%s 歷史下載完成：%s %d 筆", symbol, mkt, inserted)
    else:
        log.warning("%s 歷史下載失敗：FinMind 與 TWSE/TPEx 皆無資料（代碼可能無效）", symbol)
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
    except Exception as e:
        log.warning("TWSE 上市股票清單抓取失敗：%s", e)

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
    except Exception as e:
        log.warning("TPEx 上櫃股票清單抓取失敗：%s", e)

    if not stocks:
        return 0

    with get_session() as session:
        existing = {r.symbol: r for r in session.execute(select(StockName)).scalars().all()}
        new_records = [
            {"symbol": s["symbol"], "name": s["name"], "market": s["market"]}
            for s in stocks if s["symbol"] not in existing
        ]
        # 更新已存在的名稱
        for s in stocks:
            rec = existing.get(s["symbol"])
            if rec and rec.name != s["name"]:
                rec.name = s["name"]
        # INSERT OR IGNORE 避免並發衝突
        if new_records:
            session.execute(
                insert(StockName).prefix_with("OR IGNORE"),
                new_records,
            )
        session.commit()

    return len(stocks)


def fetch_stock_industry() -> int:
    """從 FinMind TaiwanStockInfo 抓各股產業別，寫入 stock_industry（供類股資金流向）。回傳對應檔數。"""
    try:
        with _client(30) as client:
            resp = client.get(FINMIND_BASE, params={"dataset": "TaiwanStockInfo"})
            resp.raise_for_status()
            rows = resp.json().get("data", [])
    except Exception as e:
        log.warning("FinMind TaiwanStockInfo（產業別）抓取失敗：%s", e)
        return 0

    mapping: dict[str, str] = {}
    for r in rows:
        sym = str(r.get("stock_id", "")).strip()
        ind = str(r.get("industry_category", "")).strip()
        if sym and ind and sym not in mapping:
            mapping[sym] = ind
    if not mapping:
        return 0

    with get_session() as session:
        existing = {s.symbol for s in session.execute(select(StockIndustry)).scalars().all()}
        session.add_all([
            StockIndustry(symbol=s, industry=i) for s, i in mapping.items() if s not in existing
        ])
        session.commit()
    return len(mapping)


def get_industry_map() -> dict:
    """回傳 {symbol: industry}；尚未建立則先抓一次（lazy）。"""
    with get_session() as session:
        rows = session.execute(select(StockIndustry)).scalars().all()
    if not rows:
        fetch_stock_industry()
        with get_session() as session:
            rows = session.execute(select(StockIndustry)).scalars().all()
    return {s.symbol: s.industry for s in rows}


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
