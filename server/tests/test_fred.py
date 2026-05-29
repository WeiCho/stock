"""
fred 模組：純函式（_change_pct）+ key resolution + series schema。
不打 FRED API（已有 key 的話，summary() 會打網路 — 不在這驗）。
"""
import pytest

import fred


class TestSeriesRegistry:
    def test_eight_series_registered(self):
        # 加入 DGS2 + DGS10（殖利率曲線用）後總共 8 個
        assert set(fred.SERIES.keys()) == {
            "CPIAUCSL", "PCE", "GDP", "PAYEMS", "UNRATE", "DFF",
            "DGS2", "DGS10",
        }

    def test_each_has_label_unit_freq(self):
        for sid, meta in fred.SERIES.items():
            assert "label" in meta and "unit" in meta and "freq" in meta


class TestYieldCurve:
    def test_yield_curve_no_key_returns_unavailable(self, monkeypatch):
        monkeypatch.setattr(fred, "_api_key", lambda: None)
        out = fred.yield_curve(1)
        assert out["latest"] is None
        assert out["status"] == "unavailable"
        assert "data" in out


class TestChangePct:
    def test_normal_change(self):
        assert fred._change_pct(110, 100) == 10.0

    def test_negative_change(self):
        assert fred._change_pct(90, 100) == -10.0

    def test_zero_base_returns_none(self):
        assert fred._change_pct(100, 0) is None

    def test_no_change(self):
        assert fred._change_pct(100, 100) == 0.0


class TestApiKeyResolution:
    def test_available_returns_bool(self):
        # 不直接斷言 True/False（依當下 .env 有沒有 key 而定），但必須是 bool
        assert isinstance(fred.available(), bool)

    def test_no_key_summary_returns_unavailable(self, monkeypatch):
        monkeypatch.setattr(fred, "_api_key", lambda: None)
        out = fred.summary()
        assert out == {"available": False, "indicators": []}

    def test_no_key_get_series_returns_empty_data(self, monkeypatch):
        monkeypatch.setattr(fred, "_api_key", lambda: None)
        r = fred.get_series("CPIAUCSL", years=1)
        # 沒 key → fetch 回空 list，但 metadata 仍正確
        assert r["series_id"] == "CPIAUCSL"
        assert r["data"] == []

    def test_unknown_series_returns_error(self):
        r = fred.get_series("NOT_A_REAL_SERIES")
        assert "error" in r
