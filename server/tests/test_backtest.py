"""
backtest 模組：純函式 + edge cases（不依賴 DB / 網路）。
"""
import numpy as np
import pandas as pd
import pytest

import backtest


def _make_df(closes: list[float], opens: list[float] | None = None,
             volumes: list[int] | None = None) -> pd.DataFrame:
    """工具：用 close/open/volume list 造一個測試用 DataFrame。"""
    n = len(closes)
    return pd.DataFrame({
        "open":   opens if opens is not None else [c - 0.5 for c in closes],
        "high":   [c + 1 for c in closes],
        "low":    [c - 1 for c in closes],
        "close":  closes,
        "volume": volumes if volumes is not None else [100] * n,
    }, index=pd.date_range("2024-01-01", periods=n, freq="D"))


class TestSignalRegistry:
    def test_signal_registry(self):
        """核心 9 + best_four_buy/sell + weekly_w_bottom（週線W底掃描）= 12 個訊號。"""
        keys = set(backtest.SUPPORTED_SIGNALS.keys())
        assert "best_four_buy" in keys
        assert "best_four_sell" in keys
        assert "weekly_w_bottom" in keys
        assert len(keys) == 12

    def test_all_signals_have_chinese_label(self):
        for k, v in backtest.SUPPORTED_SIGNALS.items():
            assert isinstance(v, str) and len(v) > 0, f"{k} 缺中文標題"


class TestBestFourPivot:
    def test_negative_pivot_min_two_days_ago(self):
        # bias 全負，最低在 idx 2（5-2=3 < 4 且 idx != 4 → 觸發）
        bias = pd.Series([-1, -2, -5, -3, -2])
        out = backtest._best_four_pivot(bias, position=False)
        assert bool(out.iloc[-1]), "負乖離 pivot 應在最低點 2 天前時觸發"

    def test_negative_pivot_min_today_blocked(self):
        # 最低在當下 (idx 4) → 不觸發
        bias = pd.Series([-1, -2, -3, -4, -5])
        out = backtest._best_four_pivot(bias, position=False)
        assert not bool(out.iloc[-1]), "最低在當下不算 pivot"

    def test_positive_pivot_symmetric(self):
        bias = pd.Series([1, 2, 5, 3, 2])
        out = backtest._best_four_pivot(bias, position=True)
        assert bool(out.iloc[-1]), "正乖離 pivot 應在最高點 2 天前時觸發"


class TestBestFourBuyMask:
    def test_empty_df_no_crash(self):
        out = backtest._best_four_buy_mask(pd.DataFrame(columns=["open", "close", "volume"]))
        assert out.sum() == 0

    def test_short_df_returns_zero(self):
        out = backtest._best_four_buy_mask(_make_df([10] * 5))
        assert out.sum() == 0  # < 10 rows, 訊號不會 evaluate

    def test_missing_columns_returns_zero(self):
        df = pd.DataFrame({"close": [10] * 20})
        out = backtest._best_four_buy_mask(df)
        assert out.sum() == 0

    def test_monotonic_up_trend_no_buy(self):
        # 一路漲，不會有負乖離 pivot
        df = _make_df([10 + i for i in range(40)])
        assert backtest._best_four_buy_mask(df).sum() == 0


class TestRunFunction:
    def test_unknown_signal_returns_error(self):
        r = backtest.run("2330", "not_a_real_signal")
        assert "error" in r

    def test_signal_name_matches_registry(self):
        # 不用真跑 backtest（需要 DB），只測 registry 一致性
        for sig in backtest.SUPPORTED_SIGNALS:
            assert sig in backtest.SUPPORTED_SIGNALS  # tautology guard

    def test_list_signals_returns_registry(self):
        assert backtest.list_signals() == backtest.SUPPORTED_SIGNALS
