"""
新聞面 + 基本面模組
新聞：RSS 爬蟲（鉅亨網 / Yahoo Finance TW / MOPS）
基本面：FinMind 免費 API + TWSE 財報
"""

import re
from datetime import datetime, timedelta, timezone
from typing import Optional
import httpx
import feedparser
from sqlalchemy import select
from db import NewsCache, get_session

FINMIND_BASE = "https://api.finmindtrade.com/api/v4/data"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; TaiwanStockBot/1.0)"}

RSS_SOURCES = [
    "https://www.cnyes.com/rss/cat/tw_stock",
    "https://tw.stock.yahoo.com/rss",
]


# ──────────────────────────────────────────────
# 新聞
# ──────────────────────────────────────────────

def fetch_news(symbol: str, company_name: str = "", limit: int = 10) -> list[dict]:
    """爬取 RSS 新聞，依 symbol 或 company_name 過濾，寫入快取後回傳。"""
    keywords = [symbol]
    if company_name:
        keywords.append(company_name)

    fresh_news = []
    for rss_url in RSS_SOURCES:
        try:
            feed = feedparser.parse(rss_url)
            for entry in feed.entries:
                title = entry.get("title", "")
                if not any(kw in title for kw in keywords):
                    continue

                pub = entry.get("published_parsed")
                if pub:
                    pub_dt = datetime(*pub[:6], tzinfo=timezone.utc)
                else:
                    pub_dt = datetime.now(timezone.utc)

                # 只取近 30 天
                if pub_dt < datetime.now(timezone.utc) - timedelta(days=30):
                    continue

                is_major = any(w in title for w in [
                    "法說", "財報", "EPS", "配息", "董事會", "重大", "停牌", "下市"
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
            continue

    # 寫入快取（去重）
    with get_session() as session:
        for item in fresh_news:
            existing = session.execute(
                select(NewsCache).where(
                    NewsCache.symbol == symbol,
                    NewsCache.title == item["title"],
                )
            ).scalar_one_or_none()
            if existing is None:
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
