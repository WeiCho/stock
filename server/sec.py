"""
SEC EDGAR 整合 — 免費，無需 API key（但需 User-Agent 帶聯絡方式以符合 SEC 政策）。

提供：
- Form 4: 內部人交易（CEO/CFO/Director 買賣自家股票，每次 2 個工作日內申報）
- Ticker → CIK 對照表

CEO 大買通常是強烈看多訊號；連續大量 sell（非自動賣出計畫）是警訊。

12 小時 cache（SEC 資料更新慢）。
"""

import logging
import os
import ssl
from datetime import datetime, timedelta
import re
import httpx

log = logging.getLogger("uvicorn.error")

try:
    import certifi
    _SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except Exception:
    _SSL_CTX = ssl.create_default_context()
_SSL_CTX.verify_flags &= ~ssl.VERIFY_X509_STRICT

# SEC 政策：必須帶 User-Agent 含「真實聯絡 email」，否則 data.sec.gov 可能限流 / 403。
# 從環境變數讀（見 .env / .env.example），避免把個人 email 寫死在原始碼（repo 若公開會被爬）。
def _headers() -> dict:
    contact = os.environ.get("SEC_CONTACT_EMAIL", "").strip()
    if not contact:
        log.warning("未設定 SEC_CONTACT_EMAIL，SEC 可能因缺聯絡資訊而限流；請於 .env 設定。")
    ua = f"TaiwanStockSkill/1.0 ({contact})" if contact else "TaiwanStockSkill/1.0"
    return {"User-Agent": ua, "Accept": "application/json"}

DATA_BASE = "https://data.sec.gov"
WWW_BASE = "https://www.sec.gov"

_CACHE: dict[str, tuple[datetime, dict]] = {}
_CACHE_TTL = timedelta(hours=12)

# Ticker → CIK 對照表（lazy 載入一次，整個 process 共用）
_TICKER_TO_CIK: dict[str, dict] = {}


def _load_ticker_map() -> None:
    """從 SEC 抓 ticker→CIK 對照表（一次性，~10000 entries）。"""
    global _TICKER_TO_CIK
    if _TICKER_TO_CIK:
        return
    try:
        with httpx.Client(headers=_headers(), verify=_SSL_CTX, timeout=20) as client:
            resp = client.get(f"{WWW_BASE}/files/company_tickers.json")
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        log.warning("SEC ticker map 抓取失敗：%s", e)
        return
    # data shape: {"0": {cik_str, ticker, title}, "1": {...}, ...}
    for entry in data.values():
        ticker = entry.get("ticker", "").upper()
        if ticker:
            _TICKER_TO_CIK[ticker] = {
                "cik": f"{entry['cik_str']:010d}",
                "title": entry.get("title", ticker),
            }
    log.info("SEC ticker map 載入 %d 個", len(_TICKER_TO_CIK))


def get_cik(ticker: str) -> str | None:
    """ticker → 10 位 zero-padded CIK。未知回 None。"""
    if not _TICKER_TO_CIK:
        _load_ticker_map()
    entry = _TICKER_TO_CIK.get(ticker.upper())
    return entry["cik"] if entry else None


# ──────────────────────────────────────────────
# Form 4 內部人交易
# ──────────────────────────────────────────────

def insider_transactions(ticker: str, limit: int = 20) -> dict:
    """近 N 筆內部人交易（Form 4）。回 {ticker, cik, transactions: [...]}。

    SEC 的 Form 4 是 XML，含 transactionShares / transactionPricePerShare /
    isAcquiredOrDisposed (A/D)。解析複雜，這版用 submissions feed 拿 metadata，
    完整明細需 access archives 各 Form 4 XML — 此版本只回 metadata（日期、accession）+
    SEC 上的連結，讓使用者點開看詳情。
    """
    cik = get_cik(ticker)
    if not cik:
        return {"ticker": ticker.upper(), "error": "找不到 CIK（非美股或不在 SEC 註冊）"}

    cache_key = f"f4:{cik}"
    cached = _CACHE.get(cache_key)
    if cached and (datetime.now() - cached[0]) < _CACHE_TTL:
        return cached[1]

    try:
        with httpx.Client(headers=_headers(), verify=_SSL_CTX, timeout=15) as client:
            resp = client.get(f"{DATA_BASE}/submissions/CIK{cik}.json")
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        log.warning("SEC submissions CIK %s 失敗：%s", cik, e)
        return {"ticker": ticker.upper(), "cik": cik, "transactions": [], "error": str(e)}

    recent = data.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    dates = recent.get("filingDate", [])
    accessions = recent.get("accessionNumber", [])
    primary_docs = recent.get("primaryDocument", [])

    transactions = []
    for i, f in enumerate(forms):
        if f != "4":
            continue
        if len(transactions) >= limit:
            break
        acc = accessions[i] if i < len(accessions) else ""
        acc_no_dashes = acc.replace("-", "")
        doc = primary_docs[i] if i < len(primary_docs) else ""
        transactions.append({
            "date": dates[i] if i < len(dates) else "",
            "form": "4",
            "accession": acc,
            "url": f"{WWW_BASE}/Archives/edgar/data/{int(cik)}/{acc_no_dashes}/{doc}" if doc else "",
            "filing_url": f"{WWW_BASE}/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type=4&dateb=&owner=include&count=40",
        })

    result = {
        "ticker": ticker.upper(),
        "cik": cik,
        "company_name": data.get("name", _TICKER_TO_CIK.get(ticker.upper(), {}).get("title")),
        "transactions": transactions,
        "count": len(transactions),
    }
    _CACHE[cache_key] = (datetime.now(), result)
    return result


# ──────────────────────────────────────────────
# 全 13F 簡介（用於 famous 機構持股）— 預留
# ──────────────────────────────────────────────

# 預留：常見機構 CIK 對照
FAMOUS_FUNDS = {
    "berkshire": {"cik": "0001067983", "name": "Berkshire Hathaway"},
    "tiger_global": {"cik": "0001167483", "name": "Tiger Global Management"},
    "ark_innovation": {"cik": "0001697748", "name": "ARK Investment Management"},
    "renaissance": {"cik": "0001037389", "name": "Renaissance Technologies"},
    "bridgewater": {"cik": "0001350694", "name": "Bridgewater Associates"},
}
