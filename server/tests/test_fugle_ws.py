"""fugle_ws 測試 — 純函式 + QuoteHub 狀態機（用假 ws，不開真連線）。"""

import asyncio
import json

import fugle_ws


def test_union_capped_caps_at_max_subs():
    sets = [{"2330", "0050"}, {"0050", "2317", "1101", "2454", "3008", "2412"}]
    capped, total = fugle_ws._union_capped(sets, max_subs=5)
    assert total == 7              # 聯集原始大小
    assert len(capped) == 5        # 截斷到上限
    assert capped <= {"2330", "0050", "2317", "1101", "2454", "3008", "2412"}


def test_union_capped_under_limit_keeps_all():
    capped, total = fugle_ws._union_capped([{"2330"}, {"0050", "2330"}], max_subs=5)
    assert total == 2
    assert capped == {"2330", "0050"}


def test_tw_only_filters_us_tickers():
    # 台股代碼數字開頭（含主動式 00xxxA）保留；美股字母開頭過濾
    out = fugle_ws._tw_only(["2330", "0050", "00403A", "AAPL", "aapl", "", "  2317 "])
    assert out == {"2330", "0050", "00403A", "2317"}


def test_max_subs_is_five():
    assert fugle_ws.MAX_SUBS == 5


# ── QuoteHub 狀態機（用假上游 ws，不 add_client 所以不會 spawn _run / 連真 Fugle）──

class _FakeWS:
    def __init__(self):
        self.sent: list[dict] = []
        self.closed = False

    async def send(self, s):
        self.sent.append(json.loads(s))

    async def close(self):
        self.closed = True


def test_recompute_caps_desired_at_five():
    async def body():
        hub = fugle_ws.QuoteHub()
        c1, c2 = fugle_ws._Client(), fugle_ws._Client()
        c1.symbols = {"2330", "0050"}
        c2.symbols = {"2317", "2454", "2412", "3008", "1101"}  # union = 7
        hub._clients = {c1, c2}
        await hub._recompute()
        assert len(hub._desired) == 5
    asyncio.run(body())


def test_recompute_closes_upstream_when_no_clients():
    async def body():
        hub = fugle_ws.QuoteHub()
        ws = _FakeWS()
        hub._ws = ws
        hub._clients = set()  # 最後一個 client 走了
        await hub._recompute()
        assert ws.closed is True       # 主動關上游連線，釋放 Fugle 連線額度
        assert hub._desired == set()
    asyncio.run(body())


def test_set_client_symbols_filters_and_seeds_cached_latest():
    async def body():
        hub = fugle_ws.QuoteHub()
        hub._latest = {"2330": {"symbol": "2330", "last": 2355}}
        c = fugle_ws._Client()
        hub._clients = {c}
        await hub.set_client_symbols(c, ["2330", "AAPL"])  # AAPL（美股）會被過濾
        assert c.symbols == {"2330"}
        seeded = c.queue.get_nowait()  # 已快取的最新報價立即推給 client
        assert seeded["event"] == "quote" and seeded["quote"]["symbol"] == "2330"
    asyncio.run(body())


def test_subscribed_ack_unsubscribes_if_no_longer_desired():
    # 修掉「快速切換」孤兒訂閱：ack 回來時已不需要 → 立刻用 id 退訂
    async def body():
        hub = fugle_ws.QuoteHub()
        hub._ws = _FakeWS()
        hub._authed = True
        hub._desired = {"0050"}      # 2330 已不在 desired
        hub._pending = {"2330"}
        await hub._handle(json.dumps(
            {"event": "subscribed", "data": {"symbol": "2330", "id": "ABC"}}))
        assert "2330" not in hub._subscribed
        assert "2330" not in hub._pending
        assert any(f.get("event") == "unsubscribe" and f["data"].get("id") == "ABC"
                   for f in hub._ws.sent)
    asyncio.run(body())


def test_subscribed_ack_promotes_when_still_desired():
    async def body():
        hub = fugle_ws.QuoteHub()
        hub._ws = _FakeWS()
        hub._authed = True
        hub._desired = {"2330"}
        hub._pending = {"2330"}
        await hub._handle(json.dumps(
            {"event": "subscribed", "data": {"symbol": "2330", "id": "XYZ"}}))
        assert hub._subscribed == {"2330"}
        assert hub._sub_ids["2330"] == "XYZ"
        assert hub._ws.sent == []  # 仍需要 → 不退訂
    asyncio.run(body())


def test_put_drops_on_full_queue_without_raising():
    async def body():
        hub = fugle_ws.QuoteHub()
        c = fugle_ws._Client()
        for i in range(c.queue.maxsize):
            c.queue.put_nowait({"n": i})
        hub._put(c, {"n": "overflow"})  # 滿了應靜默丟棄，不丟例外
        assert c.queue.full()
    asyncio.run(body())
