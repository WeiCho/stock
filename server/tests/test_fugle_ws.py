"""fugle_ws 純函式測試（不開任何連線）。"""

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
