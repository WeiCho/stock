"""twse_openapi 測試 — 解析 / 排序純邏輯（monkeypatch _get，不打網路）。"""

import twse_openapi


def test_roc_to_ad():
    assert twse_openapi._roc_to_ad("1150528") == "2026-05-28"
    assert twse_openapi._roc_to_ad("") == ""
    assert twse_openapi._roc_to_ad("badly") == ""


def test_parse_float():
    assert twse_openapi._f("3.38") == 3.38
    assert twse_openapi._f("1,234.5") == 1234.5
    assert twse_openapi._f("") is None
    assert twse_openapi._f("--") is None
    assert twse_openapi._f(None) is None


_BWIBBU = [
    {"Date": "1150528", "Code": "2911", "Name": "麗嬰房", "PEratio": "2.16", "PBratio": "0.61", "DividendYield": ""},
    {"Date": "1150528", "Code": "2330", "Name": "台積電", "PEratio": "30.86", "PBratio": "10.1", "DividendYield": "0.96"},
    {"Date": "1150528", "Code": "1432", "Name": "大魯閣", "PEratio": "2.97", "PBratio": "1.09", "DividendYield": "12.35"},
    {"Date": "1150528", "Code": "BAD", "Name": "缺值", "PEratio": "", "PBratio": "", "DividendYield": ""},
]


def test_valuation_parses_and_dates(monkeypatch):
    monkeypatch.setattr(twse_openapi, "_get", lambda path: _BWIBBU)
    v = twse_openapi.valuation()
    assert v["available"] and v["date"] == "2026-05-28"
    assert len(v["items"]) == 4
    assert v["items"][1]["per"] == 30.86 and v["items"][1]["dividend_yield"] == 0.96


def test_valuation_screen_sorts_and_filters_invalid(monkeypatch):
    monkeypatch.setattr(twse_openapi, "_get", lambda path: _BWIBBU)
    s = twse_openapi.valuation_screen(top_n=2)
    assert [i["symbol"] for i in s["low_per"]] == ["2911", "1432"]   # 低本益比，BAD(None) 排除
    assert s["high_yield"][0]["symbol"] == "1432"                     # 高殖利率第一


def test_valuation_for_hit_and_miss(monkeypatch):
    monkeypatch.setattr(twse_openapi, "_get", lambda path: _BWIBBU)
    assert twse_openapi.valuation_for("2330")["per"] == 30.86
    assert twse_openapi.valuation_for("9999")["available"] is False


def test_margin_for_computes_change(monkeypatch):
    monkeypatch.setattr(twse_openapi, "_get", lambda path: [
        {"股票代號": "2330", "股票名稱": "台積電", "融資今日餘額": "16621", "融資前日餘額": "15673",
         "融券今日餘額": "33", "融券前日餘額": "66"},
    ])
    m = twse_openapi.margin_for("2330")
    assert m["margin_balance"] == 16621 and m["margin_change"] == 948
    assert m["short_balance"] == 33 and m["short_change"] == -33
    assert twse_openapi.margin_for("9999") is None
