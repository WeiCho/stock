#!/usr/bin/env python3
"""
Taiwan Stock CLI — 自然語言入口。
用法：python main.py "分析台積電"
     python main.py "外資買超前五名"
     python main.py "2330 回測黃金交叉"
輸出 JSON，由 Claude 解讀後以中文回應使用者。
"""

import sys
import re
import json
import httpx

SERVER = "http://localhost:8000"
TIMEOUT = 120  # 首次查詢需要下載 10 年歷史資料

# ──────────────────────────────────────────────
# 對照表
# ──────────────────────────────────────────────

COMPANY_TO_SYMBOL = {
    "台積電": "2330", "tsmc": "2330",
    "鴻海": "2317", "富士康": "2317",
    "聯發科": "2454", "mediatek": "2454",
    "台達電": "2308",
    "大立光": "3008",
    "富邦金": "2881",
    "國泰金": "2882",
    "中信金": "2891",
    "兆豐金": "2886",
    "玉山金": "2884",
    "第一金": "2892",
    "台塑": "1301",
    "南亞": "1303",
    "台化": "1326",
    "聯電": "2303", "umc": "2303",
    "日月光": "3711", "ase": "3711",
    "廣達": "2382",
    "緯創": "3231",
    "仁寶": "2324",
    "華碩": "2357", "asus": "2357",
    "宏碁": "2353", "acer": "2353",
    "友達": "2409",
    "群創": "3481",
    "台灣大": "3045",
    "中華電": "2412",
    "遠傳": "4904",
    "台泥": "1101",
    "亞泥": "1102",
    "統一": "1216",
    "台糖": "1110",
    "長榮": "2603",
    "陽明": "2609",
    "萬海": "2615",
    "長榮航": "2618",
    "中鋼": "2002",
    "台塑石化": "6505",
    "元大台灣50": "0050",
    "台灣50": "0050",
    "元大高股息": "0056",
    "高股息": "0056",
}

SIGNAL_MAP = {
    "黃金交叉": "ma_cross",
    "ma黃金": "ma_cross",
    "死亡交叉": "ma_death",
    "ma死亡": "ma_death",
    "週黃金": "weekly_ma_cross",
    "週均線黃金": "weekly_ma_cross",
    "weekly": "weekly_ma_cross",
    "kd低檔": "kd_low_cross",
    "kd低": "kd_low_cross",
    "kd黃金": "kd_low_cross",
    "kd高檔": "kd_high_cross",
    "kd高": "kd_high_cross",
    "kd死亡": "kd_high_cross",
    "macd轉正": "macd_turn_pos",
    "macd正": "macd_turn_pos",
    "macd轉負": "macd_turn_neg",
    "macd負": "macd_turn_neg",
    "rsi超賣": "rsi_oversold",
    "rsi低": "rsi_oversold",
    "rsi超買": "rsi_overbought",
    "rsi高": "rsi_overbought",
}


# ──────────────────────────────────────────────
# 意圖解析
# ──────────────────────────────────────────────

def extract_symbol(query: str) -> tuple[str, str]:
    """從 query 提取股票代碼，回傳 (symbol, company_name)。"""
    q = query.lower()

    # 直接出現 4–6 碼數字（股票代碼）；中文環境不依賴 \b，改用前後非數字的斷言
    m = re.search(r'(?<!\d)(\d{4,6})(?!\d)', query)
    if m:
        return m.group(1), ""

    # 公司名稱對照
    for name, symbol in COMPANY_TO_SYMBOL.items():
        if name.lower() in q:
            return symbol, name

    return "", ""


def extract_signal(query: str) -> str:
    """從 query 提取回測訊號代碼，未找到回傳 'ma_cross'。"""
    q = query.lower().replace(" ", "")
    for keyword, code in SIGNAL_MAP.items():
        if keyword.lower() in q:
            return code
    return "ma_cross"


def parse_intent(query: str) -> dict:
    """解析查詢意圖，回傳 {action, symbol, company_name, signal, params}。"""
    q = query.lower()

    # ── 大盤相關 ──
    if any(kw in q for kw in ["大盤", "加權指數", "taiex", "指數漲跌", "今日指數"]):
        return {"action": "market_index"}

    if any(kw in q for kw in ["外資買超排行", "投信買超排行", "法人排行", "三大法人排行",
                               "買超前", "賣超前", "法人今日"]):
        top = int(m.group(1)) if (m := re.search(r'前\s*(\d+)', q)) else 10
        order = "asc" if "賣超" in q else "desc"
        return {"action": "market_institutional", "params": {"top": top, "order": order}}

    if any(kw in q for kw in ["連買", "連續買", "籌碼掃描", "外資連", "投信連", "chip scan"]):
        foreign_days = int(m.group(1)) if (m := re.search(r'外資連[買超]*\s*(\d+)', q)) else 0
        trust_days = int(m.group(1)) if (m := re.search(r'投信連[買超]*\s*(\d+)', q)) else 0
        # 無明確指定時給合理預設
        if foreign_days == 0 and trust_days == 0:
            foreign_days = 3
        return {
            "action": "chip_scan",
            "params": {"min_foreign_days": foreign_days, "min_trust_days": trust_days, "top_n": 20},
        }

    # ── 個股相關 ──
    symbol, company_name = extract_symbol(query)

    if any(kw in q for kw in ["pine", "pine script", "tradingview", "腳本"]):
        signal = extract_signal(query)
        return {"action": "pine", "symbol": symbol, "company_name": company_name, "signal": signal}

    if any(kw in q for kw in ["回測", "勝率", "歷史勝率", "backtest"]):
        signal = extract_signal(query)
        return {"action": "backtest", "symbol": symbol, "company_name": company_name, "signal": signal}

    if any(kw in q for kw in ["技術", "均線", "rsi", "macd", "kd", "布林", "日k", "週k",
                               "k線", "technical"]):
        timeframe = "weekly" if any(kw in q for kw in ["週k", "週線", "weekly"]) else "daily"
        return {"action": "technical", "symbol": symbol, "company_name": company_name,
                "params": {"timeframe": timeframe}}

    if any(kw in q for kw in ["籌碼", "三大法人", "外資", "投信", "自營", "chip"]):
        return {"action": "chip", "symbol": symbol, "company_name": company_name}

    if any(kw in q for kw in ["新聞", "消息", "最新", "news"]):
        return {"action": "news", "symbol": symbol, "company_name": company_name}

    if any(kw in q for kw in ["基本面", "eps", "pe", "本益比", "殖利率", "roe", "營收",
                               "fundamental"]):
        return {"action": "fundamentals", "symbol": symbol, "company_name": company_name}

    # 預設：完整分析
    return {"action": "full", "symbol": symbol, "company_name": company_name}


# ──────────────────────────────────────────────
# API 呼叫
# ──────────────────────────────────────────────

def call(path: str, params: dict = None) -> dict:
    try:
        with httpx.Client(timeout=TIMEOUT) as c:
            resp = c.get(f"{SERVER}{path}", params=params or {})
            resp.raise_for_status()
            return resp.json()
    except httpx.ConnectError:
        return {
            "error": "無法連線到 Taiwan Stock server（localhost:8000）",
            "hint": "請先啟動後端：在專案根目錄執行 source .venv/bin/activate && PYTHONPATH=server uvicorn server.main:app --host 0.0.0.0 --port 8000",
        }
    except httpx.HTTPStatusError as e:
        return {"error": f"API 錯誤 {e.response.status_code}", "detail": e.response.text}
    except Exception as e:
        return {"error": str(e)}


def dispatch(intent: dict) -> dict:
    action = intent["action"]
    symbol = intent.get("symbol", "")
    company_name = intent.get("company_name", "")
    signal = intent.get("signal", "ma_cross")
    params = intent.get("params", {})

    if action == "market_index":
        return call("/market/index", {"days": 30})

    if action == "market_institutional":
        return call("/market/institutional", params)

    if action == "chip_scan":
        return call("/market/chip-scan", params)

    if not symbol:
        return {"error": "找不到股票代碼，請指定代碼（如 2330）或公司名稱（如台積電）"}

    if action == "full":
        return call(f"/stock/{symbol}", {"company_name": company_name})

    if action == "technical":
        return call(f"/stock/{symbol}/technical", {"timeframe": params.get("timeframe", "daily")})

    if action == "chip":
        return call(f"/stock/{symbol}/chip")

    if action == "backtest":
        return call(f"/stock/{symbol}/backtest", {"signal": signal})

    if action == "pine":
        return call(f"/stock/{symbol}/pine", {"signal": signal})

    if action == "news":
        return call(f"/stock/{symbol}/news", {"company_name": company_name, "limit": 10})

    if action == "fundamentals":
        return call(f"/stock/{symbol}/fundamentals")

    return {"error": f"未知 action: {action}"}


# ──────────────────────────────────────────────
# 主程式
# ──────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "請提供查詢字串", "usage": 'python main.py "分析台積電"'},
                         ensure_ascii=False, indent=2))
        sys.exit(1)

    query = " ".join(sys.argv[1:])
    intent = parse_intent(query)
    result = dispatch(intent)

    # 在結果中加入 intent 供除錯
    result["_intent"] = intent

    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
