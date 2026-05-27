"""
回測引擎：訊號勝率統計
對 10 年歷史資料掃描形態觸發點，統計後續 N 天報酬率。
"""

from datetime import date
import pandas as pd
from data_fetcher import get_price_df, ensure_stock_data
from technical import calc_indicators, to_weekly

MIN_SAMPLE_WARNING = 10

# ──────────────────────────────────────────────
# 支援的訊號清單
# ──────────────────────────────────────────────

SUPPORTED_SIGNALS = {
    "ma_cross":        "MA20 × MA60 黃金交叉（日K）",
    "ma_death":        "MA20 × MA60 死亡交叉（日K）",
    "weekly_ma_cross": "週MA20 × 週MA52 黃金交叉",
    "kd_low_cross":    "KD 低檔黃金交叉（K<30）",
    "kd_high_cross":   "KD 高檔死亡交叉（K>70）",
    "macd_turn_pos":   "MACD 柱狀圖由負轉正",
    "macd_turn_neg":   "MACD 柱狀圖由正轉負",
    "rsi_oversold":    "RSI 超賣（<30）",
    "rsi_overbought":  "RSI 超買（>70）",
}


WEEKLY_SIGNALS = {"weekly_ma_cross"}


def _signal_frame(daily: pd.DataFrame, signal: str) -> pd.DataFrame:
    """回傳該訊號對應時間框架的價格 DataFrame（週訊號回傳週K，其餘為日K）。"""
    return to_weekly(daily) if signal in WEEKLY_SIGNALS else daily


def _detect_trigger(df: pd.DataFrame, signal: str) -> pd.Series:
    """在「已是對應時間框架」的 df 上計算指標，回傳布林 Series（True=觸發）。"""
    timeframe = "weekly" if signal in WEEKLY_SIGNALS else "daily"
    df = calc_indicators(df.copy(), timeframe)
    false = pd.Series(False, index=df.index)

    if signal in ("ma_cross", "weekly_ma_cross"):
        long_ma = "ma52" if signal == "weekly_ma_cross" else "ma60"
        if "ma20" not in df or long_ma not in df:
            return false
        return (df["ma20"].shift(1) <= df[long_ma].shift(1)) & (df["ma20"] > df[long_ma])

    if signal == "ma_death":
        if "ma20" not in df or "ma60" not in df:
            return false
        return (df["ma20"].shift(1) >= df["ma60"].shift(1)) & (df["ma20"] < df["ma60"])

    if signal == "kd_low_cross":
        if "kd_k" not in df or "kd_d" not in df:
            return false
        cross = (df["kd_k"].shift(1) <= df["kd_d"].shift(1)) & (df["kd_k"] > df["kd_d"])
        return cross & (df["kd_k"] < 30)

    if signal == "kd_high_cross":
        if "kd_k" not in df or "kd_d" not in df:
            return false
        cross = (df["kd_k"].shift(1) >= df["kd_d"].shift(1)) & (df["kd_k"] < df["kd_d"])
        return cross & (df["kd_k"] > 70)

    if signal == "macd_turn_pos":
        if "macd_hist" not in df:
            return false
        return (df["macd_hist"].shift(1) < 0) & (df["macd_hist"] >= 0)

    if signal == "macd_turn_neg":
        if "macd_hist" not in df:
            return false
        return (df["macd_hist"].shift(1) > 0) & (df["macd_hist"] <= 0)

    if signal == "rsi_oversold":
        if "rsi" not in df:
            return false
        return (df["rsi"].shift(1) >= 30) & (df["rsi"] < 30)

    if signal == "rsi_overbought":
        if "rsi" not in df:
            return false
        return (df["rsi"].shift(1) <= 70) & (df["rsi"] > 70)

    return false


# ──────────────────────────────────────────────
# 主回測函式
# ──────────────────────────────────────────────

def run(
    symbol: str,
    signal: str,
    hold_days: list[int] = None,
) -> dict:
    """
    對指定股票跑訊號勝率統計。

    回傳：
    {
      signal_name, total_triggers, low_sample_warning,
      stats: [ { hold_days, win_rate, avg_return, max_gain, max_loss, triggers } ]
    }
    """
    if hold_days is None:
        hold_days = [5, 10, 20, 60]

    if signal not in SUPPORTED_SIGNALS:
        return {
            "error": f"不支援的訊號 '{signal}'，可用訊號：{list(SUPPORTED_SIGNALS.keys())}"
        }

    ensure_stock_data(symbol)
    daily = get_price_df(symbol)

    if daily.empty:
        return {"error": f"找不到 {symbol} 的資料"}

    # 統一以 DatetimeIndex 處理，讓週訊號的觸發日也能對應回日線交易日
    daily.index = pd.to_datetime(daily.index)
    frame = _signal_frame(daily, signal)
    trigger_mask = _detect_trigger(frame, signal).fillna(False).astype(bool)
    trigger_dates = frame.index[trigger_mask].tolist()

    if not trigger_dates:
        return {
            "symbol": symbol,
            "signal": signal,
            "signal_name": SUPPORTED_SIGNALS[signal],
            "total_triggers": 0,
            "stats": [],
            "note": "近10年歷史資料中未發現此訊號觸發",
        }

    # 進出場一律以日線、以「交易日」為單位計算報酬，確保各訊號 hold_days 語意一致；
    # 週訊號的觸發日（週五標籤）會對應到當週最後一個實際交易日進場。
    daily_index = daily.index
    stats = []
    for n in hold_days:
        returns = []
        for trigger_date in trigger_dates:
            prior = daily_index[daily_index <= trigger_date]
            if len(prior) == 0:
                continue
            entry_date = prior[-1]
            future_dates = daily_index[daily_index > entry_date]
            if len(future_dates) < n:
                continue
            entry_price = daily.loc[entry_date, "close"]
            exit_price = daily.loc[future_dates[n - 1], "close"]
            returns.append((exit_price - entry_price) / entry_price * 100)

        if not returns:
            continue

        wins = sum(1 for r in returns if r > 0)
        stats.append({
            "hold_days": n,
            "sample_count": len(returns),
            "win_rate": round(wins / len(returns) * 100, 1),
            "avg_return": round(sum(returns) / len(returns), 2),
            "max_gain": round(max(returns), 2),
            "max_loss": round(min(returns), 2),
        })

    total = len(trigger_dates)
    return {
        "symbol": symbol,
        "signal": signal,
        "signal_name": SUPPORTED_SIGNALS[signal],
        "total_triggers": total,
        "low_sample_warning": total < MIN_SAMPLE_WARNING,
        "trigger_dates": [pd.Timestamp(d).strftime("%Y-%m-%d") for d in trigger_dates[-5:]],
        "stats": stats,
        "disclaimer": "歷史勝率不代表未來績效。未含手續費(0.1425%)及證交稅(0.3%)",
    }


def list_signals() -> dict:
    return SUPPORTED_SIGNALS
