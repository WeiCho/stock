"""
commodities 模組：純函式 + cache 行為（不打網路）。
"""
from datetime import datetime, timedelta, timezone
import pytest

import commodities


class TestSupportedSymbols:
    def test_has_taiwan_futures(self):
        for s in ('TX', 'MTX', 'TE', 'TF'):
            assert s in commodities.SUPPORTED
            assert commodities.SUPPORTED[s]["source"] == "finmind"

    def test_has_intl_commodities(self):
        # XAUUSD 已移除（Yahoo XAUUSD=X 2026 起 404；GC=F 已涵蓋黃金）
        for s in ('GC', 'CL', 'SI', 'HG'):
            assert s in commodities.SUPPORTED
            assert commodities.SUPPORTED[s]["source"] == "yahoo"

    def test_has_macro_indicators(self):
        # 總經頁需要的指標
        for s in ('DXY', 'SPX', 'NDX', 'VIX', 'TNX', 'FVX', 'BTC', 'ETH'):
            assert s in commodities.SUPPORTED


class TestPerfSummary:
    def test_empty_returns_empty(self):
        assert commodities.perf_summary([]) == {}

    def test_single_bar_returns_empty(self):
        assert commodities.perf_summary([{"date": "2026-01-01", "close": 100.0}]) == {}

    def test_two_bars_basic_perf(self):
        bars = [
            {"date": "2025-05-28", "close": 100.0},
            {"date": "2026-05-28", "close": 130.0},
        ]
        out = commodities.perf_summary(bars)
        # 1d 是 1 天前 → 該是同一根（沒前一天）→ None；1y +30%
        assert out.get("1y") == pytest.approx(30.0)

    def test_returns_for_real_series(self):
        # 造 400 個遞增 bar，價格從 100 漲到 200（+100%）
        today = datetime.now(timezone.utc).date()
        bars = []
        for i in range(400):
            d = today - timedelta(days=399 - i)
            bars.append({"date": d.isoformat(), "close": 100 + i * 0.25})
        out = commodities.perf_summary(bars)
        assert "1d" in out
        assert "1y" in out
        # 1y 約 +90~100%（接近最末段的成長）
        assert out["1y"] > 80


class TestUnsupportedSymbol:
    def test_unknown_symbol_returns_error(self):
        r = commodities.fetch_history("FAKE_SYM", 30)
        assert "error" in r

    def test_unsupported_in_institutional(self):
        r = commodities.fetch_institutional("GC")
        # GC 是 yahoo，不是 finmind → 錯誤
        assert "error" in r


class TestCacheBehavior:
    def test_cache_set_and_get(self):
        commodities._CACHE.clear()
        commodities._cache_set("TEST:30", {"foo": "bar"})
        assert commodities._cache_get("TEST:30") == {"foo": "bar"}

    def test_cache_expires(self, monkeypatch):
        commodities._CACHE.clear()
        # 假裝 6 分鐘前寫入（超過 5 min TTL）
        past = datetime.now(timezone.utc) - timedelta(minutes=6)
        commodities._CACHE["EXPIRED:30"] = (past, {"stale": True})
        assert commodities._cache_get("EXPIRED:30") is None

    def test_cache_miss(self):
        commodities._CACHE.clear()
        assert commodities._cache_get("NEVER:30") is None
