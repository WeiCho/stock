"""
Fugle helper：純函式邏輯（_big_from_trades 過濾）— 不打網路 / 不需要 API key。
"""
import pytest

import fugle


class TestBigOrderFilter:
    """_big_from_trades 應該排除：
    1. serial == 99999999（集合競價）
    2. hm <= 900（開盤前）
    3. hm >= 1325（收盤集合競價）
    4. amount < min_amount
    """

    def _trade(self, serial: int, hour: int, minute: int, size: int, price: float):
        # epoch_us 用 fixed 日期 2026-05-28 + (hour:minute):00 台北時間
        # 2026-05-28 09:30:00 +08 = 1779937800 unix → microseconds
        import datetime as dt
        ts = dt.datetime(2026, 5, 28, hour, minute, tzinfo=dt.timezone(dt.timedelta(hours=8)))
        return {"serial": serial, "time": int(ts.timestamp() * 1_000_000), "size": size, "price": price}

    def test_keeps_continuous_trade_above_threshold(self):
        data = {"data": [self._trade(1, 10, 30, 1000, 100)]}  # 1000 張 × 100 元 × 1000 股 = 1 億
        bigs = fugle._big_from_trades(data, min_amount=50_000_000)
        assert len(bigs) == 1
        assert bigs[0]["amount"] == 100_000_000

    def test_excludes_auction_serial(self):
        data = {"data": [self._trade(fugle._AUCTION_SERIAL, 9, 0, 5000, 100)]}
        bigs = fugle._big_from_trades(data, min_amount=10_000_000)
        assert bigs == []

    def test_excludes_pre_open(self):
        data = {"data": [self._trade(1, 8, 59, 1000, 100)]}
        bigs = fugle._big_from_trades(data, min_amount=10_000_000)
        assert bigs == []

    def test_excludes_closing_auction(self):
        # 13:25 之後屬於收盤集合競價區間
        data = {"data": [self._trade(1, 13, 25, 1000, 100)]}
        bigs = fugle._big_from_trades(data, min_amount=10_000_000)
        assert bigs == []

    def test_excludes_below_threshold(self):
        data = {"data": [self._trade(1, 10, 30, 100, 100)]}  # 100 張 × 100 × 1000 = 1000 萬
        bigs = fugle._big_from_trades(data, min_amount=50_000_000)
        assert bigs == []


class TestApiKeyResolution:
    def test_available_false_when_no_key(self, monkeypatch):
        monkeypatch.delenv("FUGLE_API_KEY", raising=False)
        # patch _api_key 直接回 None，避開 .env 讀取
        monkeypatch.setattr(fugle, "_api_key", lambda: None)
        assert fugle.available() is False
