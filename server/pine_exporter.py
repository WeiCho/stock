"""
Pine Script 產生器：依回測結果生成 TradingView Pine Script v5 模板。
"""

import os
from pathlib import Path

# 輸出至專案根目錄的 pine_output/，可用 TAIWAN_STOCK_PINE_DIR 覆寫。
REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = os.environ.get("TAIWAN_STOCK_PINE_DIR", str(REPO_ROOT / "pine_output"))
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Pine Script 模板，依訊號類型
TEMPLATES = {
    "ma_cross": """\
//@version=5
// 由 Taiwan Stock Skill 自動生成
// 訊號：MA20 × MA60 黃金交叉  勝率（20天）：{win_rate_20}%  平均報酬：{avg_return_20}%
strategy("MA20xMA60 黃金交叉 [{symbol}]", overlay=true, default_qty_type=strategy.percent_of_equity, default_qty_value=100)

ma20 = ta.sma(close, 20)
ma60 = ta.sma(close, 60)

plot(ma20, color=color.orange, title="MA20")
plot(ma60, color=color.blue, title="MA60")

crossover_signal = ta.crossover(ma20, ma60)
crossunder_signal = ta.crossunder(ma20, ma60)

if crossover_signal
    strategy.entry("Buy", strategy.long)
if crossunder_signal
    strategy.close("Buy")

bgcolor(crossover_signal ? color.new(color.green, 85) : na)
""",

    "ma_death": """\
//@version=5
// 由 Taiwan Stock Skill 自動生成
// 訊號：MA20 × MA60 死亡交叉  勝率（20天）：{win_rate_20}%  平均報酬：{avg_return_20}%
strategy("MA20xMA60 死亡交叉（放空）[{symbol}]", overlay=true, default_qty_type=strategy.percent_of_equity, default_qty_value=100)

ma20 = ta.sma(close, 20)
ma60 = ta.sma(close, 60)

plot(ma20, color=color.orange, title="MA20")
plot(ma60, color=color.blue, title="MA60")

crossunder_signal = ta.crossunder(ma20, ma60)
crossover_signal = ta.crossover(ma20, ma60)

if crossunder_signal
    strategy.entry("Short", strategy.short)
if crossover_signal
    strategy.close("Short")

bgcolor(crossunder_signal ? color.new(color.red, 85) : na)
""",

    "kd_low_cross": """\
//@version=5
// 由 Taiwan Stock Skill 自動生成
// 訊號：KD 低檔黃金交叉（K<30）  勝率（20天）：{win_rate_20}%  平均報酬：{avg_return_20}%
strategy("KD 低檔黃金交叉 [{symbol}]", overlay=false, default_qty_type=strategy.percent_of_equity, default_qty_value=100)

k = ta.stoch(close, high, low, 9)
d = ta.ema(k, 3)

plot(k, color=color.blue, title="K")
plot(d, color=color.orange, title="D")
hline(30, color=color.gray, linestyle=hline.style_dashed)
hline(70, color=color.gray, linestyle=hline.style_dashed)

signal = ta.crossover(k, d) and k < 30
if signal
    strategy.entry("Buy", strategy.long)
strategy.exit("Exit", "Buy", profit=close * {profit_ratio}, loss=close * {loss_ratio})

plotshape(signal, style=shape.triangleup, location=location.bottom, color=color.green, size=size.small)
""",

    "macd_turn_pos": """\
//@version=5
// 由 Taiwan Stock Skill 自動生成
// 訊號：MACD 柱狀圖由負轉正  勝率（20天）：{win_rate_20}%  平均報酬：{avg_return_20}%
strategy("MACD 柱狀圖轉正 [{symbol}]", overlay=false, default_qty_type=strategy.percent_of_equity, default_qty_value=100)

[macd_line, signal_line, hist] = ta.macd(close, 12, 26, 9)

plot(hist, style=plot.style_histogram, color=hist >= 0 ? color.green : color.red, title="Histogram")
plot(macd_line, color=color.blue, title="MACD")
plot(signal_line, color=color.orange, title="Signal")

turn_pos = hist[1] < 0 and hist >= 0
if turn_pos
    strategy.entry("Buy", strategy.long)
strategy.exit("Exit", "Buy", profit=close * {profit_ratio}, loss=close * {loss_ratio})

plotshape(turn_pos, style=shape.triangleup, location=location.bottom, color=color.green, size=size.small)
""",

    "rsi_oversold": """\
//@version=5
// 由 Taiwan Stock Skill 自動生成
// 訊號：RSI 超賣（<30）  勝率（20天）：{win_rate_20}%  平均報酬：{avg_return_20}%
strategy("RSI 超賣反彈 [{symbol}]", overlay=false, default_qty_type=strategy.percent_of_equity, default_qty_value=100)

rsi_val = ta.rsi(close, 14)
plot(rsi_val, color=color.purple, title="RSI")
hline(30, color=color.green, linestyle=hline.style_dashed)
hline(70, color=color.red, linestyle=hline.style_dashed)

signal = rsi_val[1] >= 30 and rsi_val < 30
if signal
    strategy.entry("Buy", strategy.long)
strategy.exit("Exit", "Buy", profit=close * {profit_ratio}, loss=close * {loss_ratio})
""",

    "best_four_buy": """\
//@version=5
// 由 Taiwan Stock Skill 自動生成
// 訊號：四大買點（twstock BestFourPoint）  勝率（20天）：{win_rate_20}%  平均報酬：{avg_return_20}%
// 條件：負乖離 pivot AND 任一{{量增收紅 / 量縮價不跌 / 3日均剛轉漲 / 3日均>6日均}}
strategy("四大買點 [{symbol}]", overlay=true, default_qty_type=strategy.percent_of_equity, default_qty_value=100)

ma3 = ta.sma(close, 3)
ma6 = ta.sma(close, 6)
plot(ma3, color=color.orange, title="MA3")
plot(ma6, color=color.blue, title="MA6")

c1 = volume > volume[1] and close > open
c2 = volume < volume[1] and close > open[1]
c3 = ma3 > ma3[1] and ma3[1] <= ma3[2]
c4 = ma3 > ma6

bias = ma3 - ma6
all_negative = ta.highest(bias, 5) < 0
bars_since_low = ta.barssince(bias == ta.lowest(bias, 5))
pivot = all_negative and (bars_since_low == 2 or bars_since_low == 3)

signal = pivot and (c1 or c2 or c3 or c4)
if signal
    strategy.entry("Buy", strategy.long)
strategy.exit("Exit", "Buy", profit=close * {profit_ratio}, loss=close * {loss_ratio})

bgcolor(signal ? color.new(color.green, 80) : na)
""",

    "best_four_sell": """\
//@version=5
// 由 Taiwan Stock Skill 自動生成
// 訊號：四大賣點（twstock BestFourPoint）  勝率（20天）：{win_rate_20}%  平均報酬：{avg_return_20}%
// 條件：正乖離 pivot AND 任一{{量增收黑 / 量縮價跌 / 3日均剛轉跌 / 3日均<6日均}}
strategy("四大賣點 [{symbol}]", overlay=true, default_qty_type=strategy.percent_of_equity, default_qty_value=100)

ma3 = ta.sma(close, 3)
ma6 = ta.sma(close, 6)
plot(ma3, color=color.orange, title="MA3")
plot(ma6, color=color.blue, title="MA6")

c1 = volume > volume[1] and close < open
c2 = volume < volume[1] and close < open[1]
c3 = ma3 < ma3[1] and ma3[1] >= ma3[2]
c4 = ma3 < ma6

bias = ma3 - ma6
all_positive = ta.lowest(bias, 5) > 0
bars_since_high = ta.barssince(bias == ta.highest(bias, 5))
pivot = all_positive and (bars_since_high == 2 or bars_since_high == 3)

signal = pivot and (c1 or c2 or c3 or c4)
if signal
    strategy.entry("Sell", strategy.short)
strategy.exit("Exit", "Sell", profit=close * {profit_ratio}, loss=close * {loss_ratio})

bgcolor(signal ? color.new(color.red, 80) : na)
""",
}

# Fallback：理論上目前 11 個訊號都有專屬模板，跑不到這條。
# 未來如果加新訊號（例如自訂組合）忘了補模板，就會落到這裡。
GENERIC_TEMPLATE = """\
//@version=5
// 由 Taiwan Stock Skill 自動生成（fallback 模板）
// 訊號：{signal_name}  勝率（20天）：{win_rate_20}%  平均報酬：{avg_return_20}%
// 此訊號未提供 Pine 實作；請依回測統計於 TradingView 上自行撰寫進出場條件。
indicator("{signal_name} [{symbol}]", overlay=true)
"""


def export(symbol: str, signal: str, signal_name: str, backtest_stats: list[dict]) -> dict:
    """
    依回測結果生成 Pine Script 並存成 .pine 檔。

    backtest_stats: backtest.run() 回傳的 stats 清單
    """
    # 從 stats 取 20 天的數字（若無則取最接近的）
    stat_20 = next((s for s in backtest_stats if s["hold_days"] == 20), None)
    if stat_20 is None and backtest_stats:
        stat_20 = sorted(backtest_stats, key=lambda s: abs(s["hold_days"] - 20))[0]

    win_rate_20 = stat_20["win_rate"] if stat_20 else "N/A"
    avg_return_20 = stat_20["avg_return"] if stat_20 else "N/A"

    # profit/loss ratio from avg_return (簡單估算)
    profit_ratio = round(abs(avg_return_20) / 100, 4) if isinstance(avg_return_20, (int, float)) else 0.05
    loss_ratio = round(profit_ratio * 0.6, 4)  # 預設停損在預期獲利的 60%

    template = TEMPLATES.get(signal, GENERIC_TEMPLATE)
    pine_code = template.format(
        symbol=symbol,
        signal_name=signal_name,
        win_rate_20=win_rate_20,
        avg_return_20=avg_return_20,
        profit_ratio=profit_ratio,
        loss_ratio=loss_ratio,
    )

    filename = f"{symbol}_{signal}.pine"
    filepath = os.path.join(OUTPUT_DIR, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(pine_code)

    return {
        "symbol": symbol,
        "signal": signal,
        "file": filepath,
        "win_rate_20d": win_rate_20,
        "avg_return_20d": avg_return_20,
        "pine_code": pine_code,
    }
