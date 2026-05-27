"""
綜合研判：結合技術面、籌碼面與 10 年歷史回測，給出方向偏向（偏多/中性/偏空）、
加權依據清單，以及以歷史統計為基礎的「預期區間」。

刻意採透明的規則加權（非黑箱預測）：每個依據都列出來、可解釋；
預期區間直接取自回測的歷史平均報酬與最大獲利/虧損，並標注樣本與免責。
此為研究參考，非投資建議；歷史統計不代表未來。
"""

import technical
import chip as chip_module
import backtest as bt

# 技術面偵測到的形態名稱 → 對應回測訊號代碼（用來取歷史勝率/報酬作為預期依據）
_SIGNAL_TO_BACKTEST = [
    ("黃金交叉", "ma_cross"),
    ("死亡交叉", "ma_death"),
    ("KD 低檔", "kd_low_cross"),
    ("KD 高檔", "kd_high_cross"),
    ("MACD 柱狀圖轉正", "macd_turn_pos"),
    ("MACD 柱狀圖轉負", "macd_turn_neg"),
    ("RSI 超賣", "rsi_oversold"),
    ("RSI 超買", "rsi_overbought"),
]


def _match_backtest_signal(signal_names: list[str]) -> str | None:
    for name in signal_names:
        for key, code in _SIGNAL_TO_BACKTEST:
            if key in name:
                return code
    return None


def analyze(symbol: str) -> dict:
    """回傳綜合研判結果。"""
    tech = technical.analyze(symbol, "daily")
    if "error" in tech:
        return tech

    chip_data = chip_module.analyze(symbol)
    close = tech.get("close")

    factors: list[dict] = []

    def add(label: str, weight: int):
        factors.append({"label": label, "weight": weight})

    # ── 趨勢（均線排列）──
    trend = tech.get("trend")
    if trend == "多頭排列":
        add("日K 均線多頭排列", 2)
    elif trend == "空頭排列":
        add("日K 均線空頭排列", -2)

    # ── 技術形態訊號 ──
    signal_names = [s["name"] for s in tech.get("signals", [])]
    for s in tech.get("signals", []):
        add(s["name"], 1 if s["type"] == "bullish" else -1)

    # ── RSI 過熱/過冷 ──
    rsi = tech.get("rsi")
    if rsi is not None:
        if rsi >= 80:
            add(f"RSI {rsi} 過熱（追高風險）", -1)
        elif rsi <= 20:
            add(f"RSI {rsi} 過冷（超跌）", 1)

    # ── MACD 柱狀圖方向 ──
    hist = (tech.get("macd") or {}).get("hist")
    if hist is not None:
        add("MACD 柱狀圖為正" if hist > 0 else "MACD 柱狀圖為負", 1 if hist > 0 else -1)

    # ── 籌碼：外資 / 投信連買賣 ──
    if "error" not in chip_data:
        fc = chip_data.get("foreign", {}).get("consecutive_days", 0)
        if fc >= 3:
            add(f"外資連買 {fc} 日", 2)
        elif fc <= -3:
            add(f"外資連賣 {abs(fc)} 日", -2)
        tc = chip_data.get("trust", {}).get("consecutive_days", 0)
        if tc >= 3:
            add(f"投信連買 {tc} 日", 1)
        elif tc <= -3:
            add(f"投信連賣 {abs(tc)} 日", -1)

    # ── 歷史回測：取目前最強的有效形態，引用其 20 日勝率/報酬作為預期 ──
    expected = None
    bt_code = _match_backtest_signal(signal_names)
    if bt_code:
        r = bt.run(symbol, bt_code)
        stat20 = next((s for s in r.get("stats", []) if s["hold_days"] == 20), None)
        if stat20 and close:
            wr, avg = stat20["win_rate"], stat20["avg_return"]
            if wr >= 55 and avg > 0:
                add(f"{r['signal_name']}：歷史20日勝率 {wr}%", 2)
            elif wr <= 45 or avg < 0:
                add(f"{r['signal_name']}：歷史20日勝率 {wr}%", -1)
            expected = {
                "basis": r["signal_name"],
                "horizon_days": 20,
                "win_rate": wr,
                "avg_return": avg,
                "sample_count": stat20.get("sample_count"),
                "low_sample": r.get("low_sample_warning", False),
                "target": round(close * (1 + avg / 100), 2),
                "range_low": round(close * (1 + stat20["max_loss"] / 100), 2),
                "range_high": round(close * (1 + stat20["max_gain"] / 100), 2),
            }

    score = sum(f["weight"] for f in factors)
    bias = "偏多" if score >= 2 else "偏空" if score <= -2 else "中性"
    # 正規化到 -100~100 供前端做強弱條
    score_norm = max(-100, min(100, score * 15))

    # 依正負分組、強度排序，方便前端呈現
    factors.sort(key=lambda f: -abs(f["weight"]))

    return {
        "symbol": symbol,
        "close": close,
        "bias": bias,
        "score": score_norm,
        "trend": trend,
        "support": tech.get("support"),
        "resistance": tech.get("resistance"),
        "factors": factors,
        "expected": expected,
        "disclaimer": "本研判綜合技術面、籌碼面與歷史回測統計，僅供研究參考，"
                      "非投資建議；歷史統計不代表未來績效，且未計入交易成本。",
    }
