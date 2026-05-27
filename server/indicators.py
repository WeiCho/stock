"""
技術指標計算（純 pandas 實作）。

取代已停止維護的 pandas-ta：後者在 numpy>=2 會因 `from numpy import NaN`
匯入失敗，且無 Python 3.13/3.14 wheel。這裡只實作本專案會用到的
五個指標，公式對齊常見定義，方便日後在 TradingView 對照驗證：

- SMA：簡單移動平均
- RSI：Wilder 平滑（RMA，alpha = 1/length）
- MACD：EMA 差離（adjust=False），柱狀圖 = MACD − Signal
- KD（Stochastic）：%K 取 k 期高低區間，再以 SMA 平滑 smooth_k 期，%D 為 %K 的 d 期 SMA
- 布林通道：length 期均線 ± std 倍母體標準差（ddof=0）
"""

import pandas as pd


def sma(series: pd.Series, length: int) -> pd.Series:
    """簡單移動平均。"""
    return series.rolling(length).mean()


def ema(series: pd.Series, length: int) -> pd.Series:
    """指數移動平均（adjust=False，與多數看盤軟體一致）。"""
    return series.ewm(span=length, adjust=False).mean()


def rsi(close: pd.Series, length: int = 14) -> pd.Series:
    """相對強弱指標（Wilder 平滑）。"""
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / length, min_periods=length, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / length, min_periods=length, adjust=False).mean()
    rs = avg_gain / avg_loss
    return 100 - 100 / (1 + rs)


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    """MACD，回傳欄位 macd / signal / hist。"""
    macd_line = ema(close, fast) - ema(close, slow)
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    hist = macd_line - signal_line
    return pd.DataFrame({"macd": macd_line, "signal": signal_line, "hist": hist})


def stoch(
    high: pd.Series, low: pd.Series, close: pd.Series,
    k: int = 9, d: int = 3, smooth_k: int = 3,
) -> pd.DataFrame:
    """KD 隨機指標，回傳欄位 k / d。"""
    lowest = low.rolling(k).min()
    highest = high.rolling(k).max()
    rng = highest - lowest
    # 區間為 0（k 期內價格全平）時避免除以零，該日 %K 以 NaN 表示
    raw_k = 100 * (close - lowest) / rng.where(rng != 0)
    k_line = raw_k.rolling(smooth_k).mean()
    d_line = k_line.rolling(d).mean()
    return pd.DataFrame({"k": k_line, "d": d_line})


def bbands(close: pd.Series, length: int = 20, std: float = 2.0) -> pd.DataFrame:
    """布林通道，回傳欄位 upper / mid / lower。"""
    mid = close.rolling(length).mean()
    sd = close.rolling(length).std(ddof=0)
    return pd.DataFrame({
        "upper": mid + std * sd,
        "mid": mid,
        "lower": mid - std * sd,
    })
