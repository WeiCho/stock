"""fugle._shape_quote 純函式測試（不打網路）。"""

import fugle


def test_shape_quote_maps_core_fields():
    raw = {
        "lastPrice": 1085.0,
        "previousClose": 1070.0,
        "openPrice": 1075.0,
        "highPrice": 1090.0,
        "lowPrice": 1072.0,
        "avgPrice": 1083.5,
        "change": 15.0,
        "changePercent": 1.40,
        "total": {"tradeVolume": 23456, "tradeValue": 9999},
        "bids": [{"price": 1084, "size": 120}, {"price": 1083, "size": 80}],
        "asks": [{"price": 1085, "size": 60}, {"price": 1086, "size": 45}],
        "lastUpdated": 1_700_000_000_000_000,
    }
    q = fugle._shape_quote("2330", raw)
    assert q["symbol"] == "2330"
    assert q["last"] == 1085.0
    assert q["previousClose"] == 1070.0
    assert q["change"] == 15.0
    assert q["change_pct"] == 1.40
    assert q["volume"] == 23456
    assert q["bids"][0] == {"price": 1084, "size": 120}
    assert q["asks"][1] == {"price": 1086, "size": 45}
    assert len(q["bids"]) == 2 and len(q["asks"]) == 2


def test_shape_quote_falls_back_to_close_and_handles_missing():
    # lastPrice 缺 → 用 closePrice；bids/asks/total 缺 → 安全空值
    raw = {"closePrice": 50.5, "previousClose": 50.0}
    q = fugle._shape_quote("0050", raw)
    assert q["last"] == 50.5          # fallback to closePrice
    assert q["bids"] == [] and q["asks"] == []
    assert q["volume"] is None
    assert q["change"] is None


def test_shape_quote_etf_symbol_no_special_handling():
    # ETF（含主動式 00403A）走相同路徑，純粹當作 symbol
    raw = {"lastPrice": 12.34, "bids": [{"price": 12.33, "size": 500}], "asks": []}
    q = fugle._shape_quote("00403A", raw)
    assert q["symbol"] == "00403A"
    assert q["last"] == 12.34
    assert q["bids"][0]["size"] == 500
