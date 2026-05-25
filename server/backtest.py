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


def _detect_trigger(df: pd.DataFrame, signal: str) -> pd.Series:
    """回傳布林 Series，True 表示該日觸發訊號。"""
    df = df.copy()

    if signal == "ma_cross":
        df = calc_indicators(df, "daily")
        if "ma20" not in df.columns or "ma60" not in df.columns:
            return pd.Series(False, index=df.index)
        return (df["ma20"].shift(1) <= df["ma60"].shift(1)) & (df["ma20"] > df["ma60"])

    if signal == "ma_death":
        df = calc_indicators(df, "daily")
        if "ma20" not in df.columns or "ma60" not in df.columns:
            return pd.Series(False, index=df.index)
        return (df["ma20"].shift(1) >= df["ma60"].shift(1)) & (df["ma20"] < df["ma60"])

    if signal == "weekly_ma_cross":
        df = to_weekly(df)
        df = calc_indicators(df, "weekly")
        if "ma20" not in df.columns or "ma52" not in df.columns:
            return pd.Series(False, index=df.index)
        return (df["ma20"].shift(1) <= df["ma52"].shift(1)) & (df["ma20"] > df["ma52"])

    if signal == "kd_low_cross":
        df = calc_indicators(df, "daily")
        if "kd_k" not in df.columns or "kd_d" not in df.columns:
            return pd.Series(False, index=df.index)
        cross = (df["kd_k"].shift(1) <= df["kd_d"].shift(1)) & (df["kd_k"] > df["kd_d"])
        return cross & (df["kd_k"] < 30)

    if signal == "kd_high_cross":
        df = calc_indicators(df, "daily")
        if "kd_k" not in df.columns or "kd_d" not in df.columns:
            return pd.Series(False, index=df.index)
        cross = (df["kd_k"].shift(1) >= df["kd_d"].shift(1)) & (df["kd_k"] < df["kd_d"])
        return cross & (df["kd_k"] > 70)

    if signal == "macd_turn_pos":
        df = calc_indicators(df, "daily")
        if "macd_hist" not in df.columns:
            return pd.Series(False, index=df.index)
        return (df["macd_hist"].shift(1) < 0) & (df["macd_hist"] >= 0)

    if signal == "macd_turn_neg":
        df = calc_indicators(df, "daily")
        if "macd_hist" not in df.columns:
            return pd.Series(False, index=df.index)
        return (df["macd_hist"].shift(1) > 0) & (df["macd_hist"] <= 0)

    if signal == "rsi_oversold":
        df = calc_indicators(df, "daily")
        if "rsi" not in df.columns:
            return pd.Series(False, index=df.index)
        return (df["rsi"].shift(1) >= 30) & (df["rsi"] < 30)

    if signal == "rsi_overbought":
        df = calc_indicators(df, "daily")
        if "rsi" not in df.columns:
            return pd.Series(False, index=df.index)
        return (df["rsi"].shift(1) <= 70) & (df["rsi"] > 70)

    return pd.Series(False, index=df.index)


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
    df = get_price_df(symbol)

    if df.empty:
        return {"error": f"找不到 {symbol} 的資料"}

    trigger_mask = _detect_trigger(df, signal)
    trigger_dates = df.index[trigger_mask].tolist()

    if not trigger_dates:
        return {
            "symbol": symbol,
            "signal": signal,
            "signal_name": SUPPORTED_SIGNALS[signal],
            "total_triggers": 0,
            "stats": [],
            "note": "近10年歷史資料中未發現此訊號觸發",
        }

    stats = []
    for n in hold_days:
        returns = []
        for trigger_date in trigger_dates:
            try:
                entry_price = df.loc[trigger_date, "close"]
                # 找觸發日之後第 n 個交易日
                future_dates = df.index[df.index > trigger_date]
                if len(future_dates) < n:
                    continue
                exit_date = future_dates[n - 1]
                exit_price = df.loc[exit_date, "close"]
                ret = (exit_price - entry_price) / entry_price * 100
                returns.append(ret)
            except (KeyError, IndexError):
                continue

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
        "trigger_dates": [str(d) for d in trigger_dates[-5:]],  # 最近5次
        "stats": stats,
        "disclaimer": "歷史勝率不代表未來績效。未含手續費(0.1425%)及證交稅(0.3%)",
    }


def list_signals() -> dict:
    return SUPPORTED_SIGNALS
