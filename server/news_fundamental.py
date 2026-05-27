"""
新聞面 + 基本面模組
新聞：Google News RSS（依公司名稱查詢近 30 天；原 cnyes/Yahoo 一般版 RSS 已失效）
基本面：FinMind 免費 API
"""

import ssl
from datetime import datetime, timedelta, timezone
import httpx
import feedparser
from sqlalchemy import select
from db import NewsCache, StockName, get_session

FINMIND_BASE = "https://api.finmindtrade.com/api/v4/data"
GOOGLE_NEWS_URL = "https://news.google.com/rss/search"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; TaiwanStockBot/1.0)"}
# Google News 會擋非瀏覽器 UA，另備一個瀏覽器 UA
BROWSER_UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"}

# OpenSSL3（Python 3.13+）放寬 X509 嚴格檢查（與 data_fetcher 一致），仍完整驗證憑證
try:
    import certifi
    _SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except Exception:
    _SSL_CTX = ssl.create_default_context()
_SSL_CTX.verify_flags &= ~ssl.VERIFY_X509_STRICT


# ──────────────────────────────────────────────
# 新聞
# ──────────────────────────────────────────────

def _resolve_company_name(symbol: str, company_name: str = "") -> str:
    """補上公司名稱：未提供時從 stock_names 反查，查無則退回代碼。"""
    if company_name:
        return company_name
    with get_session() as session:
        rec = session.execute(
            select(StockName).where(StockName.symbol == symbol)
        ).scalar_one_or_none()
    return rec.name if rec else symbol


def fetch_news(symbol: str, company_name: str = "", limit: int = 10) -> list[dict]:
    """以 Google News RSS 依公司名稱搜尋近 30 天新聞，寫入快取後回傳。"""
    query = _resolve_company_name(symbol, company_name)

    fresh_news = []
    try:
        params = {"q": f"{query} when:30d", "hl": "zh-TW", "gl": "TW", "ceid": "TW:zh-Hant"}
        # retries=2 讓連線層失敗（ConnectTimeout 等）自動重試，提高 Google News 取得率
        transport = httpx.HTTPTransport(retries=2, verify=_SSL_CTX)
        with httpx.Client(headers=BROWSER_UA, timeout=20,
                          follow_redirects=True, transport=transport) as client:
            resp = client.get(GOOGLE_NEWS_URL, params=params)
            resp.raise_for_status()
        feed = feedparser.parse(resp.content)
        for entry in feed.entries:
            title = entry.get("title", "").strip()
            if not title:
                continue

            pub = entry.get("published_parsed")
            pub_dt = datetime(*pub[:6], tzinfo=timezone.utc) if pub else datetime.now(timezone.utc)
            if pub_dt < datetime.now(timezone.utc) - timedelta(days=30):
                continue

            is_major = any(w in title for w in [
                "法說", "財報", "EPS", "配息", "董事會", "重大", "停牌", "下市", "減資", "增資"
            ])

            fresh_news.append({
                "symbol": symbol,
                "title": title,
                "url": entry.get("link", ""),
                "published_at": pub_dt.replace(tzinfo=None),
                "sentiment": None,
                "is_major": is_major,
                "summary": None,
            })
    except Exception:
        pass

    # 寫入快取（一次查出已存在標題，批次去重）
    with get_session() as session:
        existing_titles = set(session.execute(
            select(NewsCache.title).where(NewsCache.symbol == symbol)
        ).scalars().all())
        for item in fresh_news:
            if item["title"] in existing_titles:
                continue
            existing_titles.add(item["title"])
            session.add(NewsCache(**item))
        session.commit()

        # 讀快取回傳
        cutoff = datetime.now() - timedelta(days=30)
        rows = session.execute(
            select(NewsCache)
            .where(NewsCache.symbol == symbol, NewsCache.published_at >= cutoff)
            .order_by(NewsCache.published_at.desc())
            .limit(limit)
        ).scalars().all()

    return [
        {
            "title": r.title,
            "url": r.url,
            "published_at": str(r.published_at),
            "sentiment": r.sentiment,
            "is_major": r.is_major,
            "summary": r.summary,
        }
        for r in rows
    ]


# ──────────────────────────────────────────────
# 基本面（FinMind 免費 API）
# ──────────────────────────────────────────────

def _finmind_get(dataset: str, stock_id: str, start_date: str) -> list[dict]:
    params = {
        "dataset": dataset,
        "data_id": stock_id,
        "start_date": start_date,
        "token": "",  # 免費不需 token，有額度限制
    }
    try:
        with httpx.Client(headers=HEADERS, timeout=15) as client:
            resp = client.get(FINMIND_BASE, params=params)
            resp.raise_for_status()
            data = resp.json()
        return data.get("data", [])
    except Exception:
        return []


def fetch_fundamentals(symbol: str) -> dict:
    """抓取基本面指標：EPS、PER、ROE、營收月增/年增、殖利率。"""
    from datetime import date
    start = str(date.today().replace(year=date.today().year - 3))

    # EPS（季度）
    eps_data = _finmind_get("TaiwanStockFinancialStatements", symbol, start)
    eps_latest = None
    if eps_data:
        eps_rows = [r for r in eps_data if r.get("type") == "EPS"]
        if eps_rows:
            eps_latest = eps_rows[-1].get("value")

    # 本益比（PE）
    pe_data = _finmind_get("TaiwanStockPER", symbol, start)
    pe_latest = None
    if pe_data:
        pe_latest = pe_data[-1].get("PER")

    # 月營收
    rev_data = _finmind_get("TaiwanStockMonthRevenue", symbol, start)
    rev_mom = rev_yoy = None
    if rev_data and len(rev_data) >= 2:
        last_rev = rev_data[-1]
        prev_rev = rev_data[-2]
        if prev_rev.get("revenue") and prev_rev["revenue"] != 0:
            rev_mom = round(
                (last_rev["revenue"] - prev_rev["revenue"]) / prev_rev["revenue"] * 100, 1
            )
        # 同期去年
        same_period = next(
            (r for r in rev_data
             if r.get("revenue_year") == last_rev.get("revenue_year", 0) - 1
             and r.get("revenue_month") == last_rev.get("revenue_month")),
            None
        )
        if same_period and same_period.get("revenue"):
            rev_yoy = round(
                (last_rev["revenue"] - same_period["revenue"]) / same_period["revenue"] * 100, 1
            )

    # 殖利率
    div_data = _finmind_get("TaiwanStockDividendResult", symbol, start)
    yield_rate = None
    if div_data:
        latest_div = div_data[-1]
        cash_div = latest_div.get("cash_dividend", 0) or 0
        if pe_data and pe_latest and cash_div:
            # 估算：殖利率 = 現金股利 / 最新收盤價（用 PE × EPS 近似）
            pass  # 簡化：直接從 FinMind dividend yield 取
        div_yield = latest_div.get("dividend_yield")
        if div_yield:
            yield_rate = div_yield

    return {
        "symbol": symbol,
        "eps_latest": eps_latest,
        "pe": round(float(pe_latest), 1) if pe_latest else None,
        "revenue_mom": rev_mom,
        "revenue_yoy": rev_yoy,
        "yield_rate": yield_rate,
        "note": "資料來源：FinMind 免費 API，季頻更新",
    }


# ──────────────────────────────────────────────
# 整合摘要（給 Claude 用的結構化文字）
# ──────────────────────────────────────────────

def summarize(symbol: str, company_name: str = "") -> dict:
    """回傳新聞 + 基本面的整合摘要，供 Claude 產生建議文字。"""
    news = fetch_news(symbol, company_name, limit=5)
    fundamentals = fetch_fundamentals(symbol)

    major_news = [n for n in news if n["is_major"]]
    recent_titles = [n["title"] for n in news[:3]]

    return {
        "symbol": symbol,
        "company_name": company_name,
        "fundamentals": fundamentals,
        "recent_news_titles": recent_titles,
        "major_news_count": len(major_news),
        "has_negative_major": any(
            n["sentiment"] == "negative" for n in major_news if n["sentiment"]
        ),
        "news_list": news,
    }
