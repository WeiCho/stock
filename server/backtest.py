"""
回測引擎：訊號勝率統計
對 10 年歷史資料掃描形態觸發點，統計後續 N 天報酬率。
"""

from datetime import date
import numpy as np
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
    # twstock BestFourPoint 四大買賣點（負/正乖離率 pivot + 任一量價/均線條件）
    "best_four_buy":   "四大買點（量價/均線 + 負乖離反彈，twstock）",
    "best_four_sell":  "四大賣點（量價/均線 + 正乖離反轉，twstock）",
    # 均線收斂突破：四線糾結 + MA5/10上翹 + 昨在MA60下 + 今突破MA20
    "ma_tangle_breakout": "均線收斂突破（四線糾結＋短線上翹＋首根突破MA60）",
}


# ──────────────────────────────────────────────
# twstock BestFourPoint 形態（vectorised）
# ──────────────────────────────────────────────

def _best_four_pivot(bias: pd.Series, position: bool) -> pd.Series:
    """對 ma_bias_ratio(3,6) 序列，每一根 K 看最近 5 根（含當下）：
    - position=False（負乖離）：5 根全為負，且最小值出現在 sample 第 2 或第 3 位（即 2–3 天前）→ 觸發
    - position=True（正乖離）：對稱，最大值在 2–3 天前
    對應 twstock.analytics.ma_bias_ratio_pivot 的 sample_size=5 條件。"""
    arr = bias.values
    n = len(arr)
    out = np.zeros(n, dtype=bool)
    for t in range(4, n):
        s = arr[t-4:t+1]
        if np.any(pd.isna(s)):
            continue
        if position:
            idx = int(np.argmax(s))
            ok = s.max() > 0
        else:
            idx = int(np.argmin(s))
            ok = s.max() < 0
        # twstock: sample_size - idx < 4 且 idx != sample_size - 1
        if ok and (5 - idx < 4) and (idx != 4):
            out[t] = True
    return pd.Series(out, index=bias.index)


def _best_four_buy_mask(df: pd.DataFrame) -> pd.Series:
    """四大買點：負乖離 pivot AND (任一條件)。"""
    if not {"close", "open", "volume"}.issubset(df.columns) or len(df) < 10:
        return pd.Series(False, index=df.index)
    close, opn, vol = df["close"], df["open"], df["volume"]
    ma3 = close.rolling(3).mean()
    ma6 = close.rolling(6).mean()
    # 條件 1：量增收紅
    c1 = (vol > vol.shift(1)) & (close > opn)
    # 條件 2：量縮且收盤 > 昨開（量縮價不跌）
    c2 = (vol < vol.shift(1)) & (close > opn.shift(1))
    # 條件 3：3日均價剛由跌轉漲（continuous(MA3) == 1）
    c3 = (ma3 > ma3.shift(1)) & (ma3.shift(1) <= ma3.shift(2))
    # 條件 4：3 日均價 > 6 日均價
    c4 = ma3 > ma6
    pivot = _best_four_pivot(ma3 - ma6, position=False)
    return pivot & (c1 | c2 | c3 | c4)


def _best_four_sell_mask(df: pd.DataFrame) -> pd.Series:
    """四大賣點：正乖離 pivot AND (任一條件)。"""
    if not {"close", "open", "volume"}.issubset(df.columns) or len(df) < 10:
        return pd.Series(False, index=df.index)
    close, opn, vol = df["close"], df["open"], df["volume"]
    ma3 = close.rolling(3).mean()
    ma6 = close.rolling(6).mean()
    c1 = (vol > vol.shift(1)) & (close < opn)
    c2 = (vol < vol.shift(1)) & (close < opn.shift(1))
    c3 = (ma3 < ma3.shift(1)) & (ma3.shift(1) >= ma3.shift(2))
    c4 = ma3 < ma6
    pivot = _best_four_pivot(ma3 - ma6, position=True)
    return pivot & (c1 | c2 | c3 | c4)


def _ma_tangle_breakout_mask(df: pd.DataFrame) -> pd.Series:
    """均線收斂突破形態（整合壓縮彈弓 + 均線糾結噴出）：
    1. MA5/10/20/60 四線差距 < 收盤 5%（緊密收斂）
    2. MA5、MA10 斜率 > 0（短線上翹，動能翻正）
    3. 近10根底部有支撐（低點平台未被跌破）
    4. 今日收盤站上 MA20（突破中期壓力）
    5. 昨收在 MA60 以下（今日才是第一根穿越長線均線）

    加分條件（不影響觸發）：
    - MA60 上斜 → 長線無壓，力道最強
    - MA60 下斜 → 均線未轉，股價領先，爆發型訊號
    """
    if not {"close", "low"}.issubset(df.columns) or len(df) < 65:
        return pd.Series(False, index=df.index)

    slope_n = 3
    ma5  = df["close"].rolling(5).mean()
    ma10 = df["close"].rolling(10).mean()
    ma20 = df["close"].rolling(20).mean()
    ma60 = df["close"].rolling(60).mean()

    ma_max = pd.concat([ma5, ma10, ma20, ma60], axis=1).max(axis=1)
    ma_min = pd.concat([ma5, ma10, ma20, ma60], axis=1).min(axis=1)

    cond_tangle      = (ma_max - ma_min) < (df["close"] * 0.05)
    cond_short_up    = ((ma5 - ma5.shift(slope_n)) > 0) & ((ma10 - ma10.shift(slope_n)) > 0)
    cond_support     = df["low"] >= df["low"].rolling(10).min().shift(1) * 0.99
    cond_above_ma20  = df["close"] > ma20
    cond_prev_below_ma60 = df["close"].shift(1) <= ma60.shift(1)

    return cond_tangle & cond_short_up & cond_support & cond_above_ma20 & cond_prev_below_ma60


# 向下相容：pattern-scan API 仍用此名稱
_slingshot_mask = _ma_tangle_breakout_mask


def _ma60_bonus(df: pd.DataFrame) -> pd.Series:
    """觸發日的 MA60 方向：上斜=True（長線無壓），下斜=False（領先突破）。"""
    if len(df) < 65:
        return pd.Series(False, index=df.index)
    ma60 = df["close"].rolling(60).mean()
    return (ma60 - ma60.shift(3)) >= 0


# 向下相容
_slingshot_ma60_bonus = _ma60_bonus


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

    if signal == "best_four_buy":
        return _best_four_buy_mask(df)

    if signal == "best_four_sell":
        return _best_four_sell_mask(df)

    if signal == "ma_tangle_breakout":
        return _ma_tangle_breakout_mask(df)

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
