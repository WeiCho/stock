"""
技術面分析模組：日K + 週K
計算 MA / RSI / MACD / KD / 布林通道，偵測形態訊號。
"""

from datetime import date
import pandas as pd
import indicators as ind
from data_fetcher import get_price_df, ensure_stock_data


# ──────────────────────────────────────────────
# 週K 聚合
# ──────────────────────────────────────────────

def to_weekly(df: pd.DataFrame) -> pd.DataFrame:
    """將日K DataFrame 重採樣為週K（每週五收盤）。"""
    df = df.copy()
    df.index = pd.to_datetime(df.index)
    weekly = df.resample("W-FRI").agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    }).dropna()
    return weekly


# ──────────────────────────────────────────────
# 指標計算
# ──────────────────────────────────────────────

def calc_indicators(df: pd.DataFrame, timeframe: str = "daily") -> pd.DataFrame:
    """在 df 上就地計算所有技術指標，回傳帶指標欄位的 DataFrame。"""
    if timeframe == "weekly":
        ma_periods = [5, 10, 20, 52, 104]
    else:
        ma_periods = [5, 10, 20, 60, 120, 240]

    for p in ma_periods:
        if len(df) >= p:
            df[f"ma{p}"] = ind.sma(df["close"], p)

    if len(df) >= 14:
        df["rsi"] = ind.rsi(df["close"], 14)

    if len(df) >= 26:
        macd = ind.macd(df["close"], fast=12, slow=26, signal=9)
        df["macd"] = macd["macd"]
        df["macd_signal"] = macd["signal"]
        df["macd_hist"] = macd["hist"]

    if len(df) >= 9:
        stoch = ind.stoch(df["high"], df["low"], df["close"], k=9, d=3, smooth_k=3)
        df["kd_k"] = stoch["k"]
        df["kd_d"] = stoch["d"]

    if len(df) >= 20:
        bb = ind.bbands(df["close"], length=20, std=2)
        df["bb_upper"] = bb["upper"]
        df["bb_mid"] = bb["mid"]
        df["bb_lower"] = bb["lower"]
        df["bb_width"] = (df["bb_upper"] - df["bb_lower"]) / df["bb_mid"]

    if len(df) >= 5:
        df["vol_ma5"] = df["volume"].rolling(5).mean()
        df["vol_ratio"] = df["volume"] / df["vol_ma5"]

    return df


# ──────────────────────────────────────────────
# 形態偵測
# ──────────────────────────────────────────────

def detect_signals(df: pd.DataFrame, timeframe: str = "daily") -> list[dict]:
    """在最新一根 K 棒上偵測形態訊號，回傳觸發清單。"""
    signals = []
    if len(df) < 3:
        return signals

    last = df.iloc[-1]
    prev = df.iloc[-2]

    ma_short = "ma20"
    ma_long = "ma60" if timeframe == "daily" else "ma52"

    # 黃金交叉（MA20 穿越 MA60 / MA52）
    if all(c in df.columns for c in [ma_short, ma_long]):
        crossed_up = (prev[ma_short] <= prev[ma_long]) and (last[ma_short] > last[ma_long])
        crossed_dn = (prev[ma_short] >= prev[ma_long]) and (last[ma_short] < last[ma_long])
        if crossed_up:
            signals.append({"name": f"{'日' if timeframe=='daily' else '週'}K 黃金交叉", "type": "bullish", "triggered": True, "code": "ma_golden", "params": {"tf": timeframe}})
        if crossed_dn:
            signals.append({"name": f"{'日' if timeframe=='daily' else '週'}K 死亡交叉", "type": "bearish", "triggered": True, "code": "ma_death", "params": {"tf": timeframe}})

    # KD 低檔交叉（K < 20 且 K 由下穿 D）
    if "kd_k" in df.columns and "kd_d" in df.columns:
        kd_cross_up = (prev["kd_k"] <= prev["kd_d"]) and (last["kd_k"] > last["kd_d"])
        kd_cross_dn = (prev["kd_k"] >= prev["kd_d"]) and (last["kd_k"] < last["kd_d"])
        if kd_cross_up and last["kd_k"] < 30:
            signals.append({"name": "KD 低檔黃金交叉（K<30）", "type": "bullish", "triggered": True, "code": "kd_golden_low", "params": {}})
        if kd_cross_dn and last["kd_k"] > 70:
            signals.append({"name": "KD 高檔死亡交叉（K>70）", "type": "bearish", "triggered": True, "code": "kd_death_high", "params": {}})

    # MACD 柱狀圖由負轉正
    if "macd_hist" in df.columns:
        if prev["macd_hist"] < 0 and last["macd_hist"] >= 0:
            signals.append({"name": "MACD 柱狀圖轉正", "type": "bullish", "triggered": True, "code": "macd_hist_pos", "params": {}})
        if prev["macd_hist"] > 0 and last["macd_hist"] <= 0:
            signals.append({"name": "MACD 柱狀圖轉負", "type": "bearish", "triggered": True, "code": "macd_hist_neg", "params": {}})

    # RSI 超買超賣
    if "rsi" in df.columns:
        if last["rsi"] > 70:
            signals.append({"name": f"RSI 超買（{last['rsi']:.1f}）", "type": "bearish", "triggered": True, "code": "rsi_overbought", "params": {"val": round(float(last['rsi']), 1)}})
        elif last["rsi"] < 30:
            signals.append({"name": f"RSI 超賣（{last['rsi']:.1f}）", "type": "bullish", "triggered": True, "code": "rsi_oversold", "params": {"val": round(float(last['rsi']), 1)}})

    # RSI 背離（價格創新高但 RSI 未創新高，取近20根）
    if "rsi" in df.columns and len(df) >= 20:
        recent = df.tail(20)
        price_new_high = last["close"] >= recent["close"].max()
        rsi_not_new_high = last["rsi"] < recent["rsi"].max() - 5
        if price_new_high and rsi_not_new_high:
            signals.append({"name": "RSI 頂背離（價格新高但RSI未創高）", "type": "bearish", "triggered": True, "code": "rsi_bear_div", "params": {}})

    # 布林通道收縮後突破
    if "bb_width" in df.columns and len(df) >= 20:
        recent_width = df["bb_width"].tail(20)
        is_squeeze = last["bb_width"] <= recent_width.quantile(0.2)
        if not is_squeeze:
            squeeze_before = recent_width.iloc[-5:-1].min() <= recent_width.quantile(0.2)
            if squeeze_before:
                direction = "bullish" if last["close"] > last["bb_mid"] else "bearish"
                signals.append({"name": "布林通道收縮後突破", "type": direction, "triggered": True, "code": "bb_squeeze_break", "params": {}})

    # 均線糾結噴出：MA5/10/20/60 四線緊密交錯，底部平台撐著，今日收盤突破站上全線
    ma_cols_tangle = ["ma5", "ma10", "ma20", "ma60"] if timeframe == "daily" else ["ma5", "ma10", "ma20", "ma52"]
    if all(c in df.columns for c in ma_cols_tangle) and len(df) >= 65:
        ma_vals = [last[c] for c in ma_cols_tangle]
        ma_vals_prev = [prev[c] for c in ma_cols_tangle]
        if all(pd.notna(v) for v in ma_vals + ma_vals_prev):
            ma_spread = max(ma_vals) - min(ma_vals)
            # 四線緊密糾結（最大差距 < 收盤 5%）
            tangle = ma_spread < last["close"] * 0.05
            # 今日收盤站上全部均線
            above_all = all(last["close"] > v for v in ma_vals)
            # 昨日收盤仍在 MA60 以下（糾結期尚未突破，今日才是第一根穿越）
            ma60_col = "ma60" if timeframe == "daily" else "ma52"
            prev_not_above = prev["close"] <= prev[ma60_col]
            # 近10根底部未被今日低點跌破（有平台支撐）
            if len(df) >= 12:
                recent_low = df["low"].iloc[-11:-1].min()
                support_ok = last["low"] >= recent_low * 0.99
            else:
                support_ok = True
            if tangle and above_all and prev_not_above and support_ok:
                signals.append({"name": "均線糾結噴出（四線交錯＋底部撐＋突破站上）", "type": "bullish", "triggered": True})

    return signals


# ──────────────────────────────────────────────
# 均線多空排列
# ──────────────────────────────────────────────

def detect_trend(df: pd.DataFrame, timeframe: str = "daily") -> str:
    last = df.iloc[-1]
    if timeframe == "daily":
        cols = ["ma5", "ma10", "ma20", "ma60"]
    else:
        cols = ["ma5", "ma10", "ma20", "ma52"]

    cols = [c for c in cols if c in df.columns and pd.notna(last[c])]
    if len(cols) < 3:
        return "資料不足"

    values = [last[c] for c in cols]
    if all(values[i] > values[i + 1] for i in range(len(values) - 1)):
        return "多頭排列"
    if all(values[i] < values[i + 1] for i in range(len(values) - 1)):
        return "空頭排列"
    return "整理中"


# ──────────────────────────────────────────────
# 支撐 / 壓力
# ──────────────────────────────────────────────

def find_support_resistance(df: pd.DataFrame, window: int = 60) -> dict:
    recent = df.tail(window)
    support = round(recent["low"].min(), 2)
    resistance = round(recent["high"].max(), 2)
    return {"support": support, "resistance": resistance}


# ──────────────────────────────────────────────
# 主分析函式
# ──────────────────────────────────────────────

def analyze(symbol: str, timeframe: str = "daily") -> dict:
    """
    完整技術面分析。
    timeframe: "daily" | "weekly"
    """
    ensure_stock_data(symbol)
    df = get_price_df(symbol)

    if df.empty:
        return {"error": f"找不到 {symbol} 的價格資料"}

    if timeframe == "weekly":
        df = to_weekly(df)

    df = calc_indicators(df, timeframe)
    last = df.iloc[-1]

    # 最新指標值
    def safe(col):
        v = last.get(col)
        return round(float(v), 2) if v is not None and pd.notna(v) else None

    ma_cols = (
        ["ma5", "ma10", "ma20", "ma52", "ma104"]
        if timeframe == "weekly"
        else ["ma5", "ma10", "ma20", "ma60", "ma120", "ma240"]
    )

    result = {
        "symbol": symbol,
        "timeframe": timeframe,
        "date": str(df.index[-1].date() if hasattr(df.index[-1], "date") else df.index[-1]),
        "close": safe("close"),
        "trend": detect_trend(df, timeframe),
        "ma": {col: safe(col) for col in ma_cols},
        "rsi": safe("rsi"),
        "macd": {
            "macd": safe("macd"),
            "signal": safe("macd_signal"),
            "hist": safe("macd_hist"),
        },
        "kd": {"k": safe("kd_k"), "d": safe("kd_d")},
        "bollinger": {
            "upper": safe("bb_upper"),
            "mid": safe("bb_mid"),
            "lower": safe("bb_lower"),
        },
        "vol_ratio": safe("vol_ratio"),
        "signals": detect_signals(df, timeframe),
        **find_support_resistance(df),
    }

    return result
