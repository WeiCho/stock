"""
data_fetcher.resample_ohlc：日K → 其他時間框架的純函式測試。
"""
import pandas as pd
import pytest

import data_fetcher as dfm


def _daily(n: int) -> pd.DataFrame:
    """造 n 個交易日的日K（每天遞增）。"""
    return pd.DataFrame({
        "open":   [10 + i for i in range(n)],
        "high":   [12 + i for i in range(n)],
        "low":    [8 + i for i in range(n)],
        "close":  [11 + i for i in range(n)],
        "volume": [100 + i for i in range(n)],
    }, index=pd.date_range("2024-01-01", periods=n, freq="B"))  # B = 工作日


class TestResampleOhlc:
    def test_passthrough_for_1d(self):
        df = _daily(20)
        out = dfm.resample_ohlc(df, "1d")
        assert len(out) == 20

    def test_empty_df_returns_empty(self):
        out = dfm.resample_ohlc(pd.DataFrame(), "1w")
        assert out.empty

    def test_1w_aggregates_to_weekly(self):
        df = _daily(20)  # 4 個完整週
        out = dfm.resample_ohlc(df, "1w")
        assert 3 <= len(out) <= 5  # 4 週 ± 邊界

    def test_1mo_aggregates_to_monthly(self):
        df = _daily(60)  # ~3 月
        out = dfm.resample_ohlc(df, "1mo")
        assert 2 <= len(out) <= 4

    def test_3d_buckets(self):
        df = _daily(30)
        out = dfm.resample_ohlc(df, "3d")
        assert len(out) == 10  # 30 / 3

    def test_5d_buckets(self):
        df = _daily(30)
        out = dfm.resample_ohlc(df, "5d")
        assert len(out) == 6

    def test_2w_buckets_from_weekly(self):
        """新增 tf='2w'：從週 K 兩兩分桶。8 個工作日 ≈ 約 2 週 → 1 個 2w bar。"""
        df = _daily(20)  # ~4 週
        out = dfm.resample_ohlc(df, "2w")
        assert 1 <= len(out) <= 3  # 4 週 / 2 = 2，±邊界

    def test_3w_buckets_from_weekly(self):
        df = _daily(30)  # ~6 週
        out = dfm.resample_ohlc(df, "3w")
        assert 1 <= len(out) <= 3

    def test_2w_smaller_than_1w_count(self):
        """sanity：2w 的 bar 數一定 ≤ 1w 的 bar 數。"""
        df = _daily(50)
        w = dfm.resample_ohlc(df, "1w")
        w2 = dfm.resample_ohlc(df, "2w")
        assert len(w2) <= len(w)
        # 2 週合併大約是週數的一半
        assert abs(len(w2) - len(w) // 2) <= 1

    def test_unknown_tf_returns_original(self):
        df = _daily(20)
        out = dfm.resample_ohlc(df, "weird_tf")
        # 未知 tf → 回原樣
        assert len(out) == 20

    def test_ohlc_aggregation_correctness_1w(self):
        # 用 freq='B' 7 個營業日會跨兩週（pandas 的 B 是 Mon–Fri），
        # 所以拿單一週（前 5 個 = 週一到週五）做驗證
        df = _daily(7).iloc[:5]
        out = dfm.resample_ohlc(df, "1w")
        assert len(out) == 1
        first = out.iloc[0]
        # open=第一天的 open；high/low=全週極值；close=最後一天 close；volume=總和
        assert first["open"] == df["open"].iloc[0]
        assert first["high"] == df["high"].max()
        assert first["low"] == df["low"].min()
        assert first["close"] == df["close"].iloc[-1]
        assert first["volume"] == df["volume"].sum()
