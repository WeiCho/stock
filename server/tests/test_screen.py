"""screen.score_candidate 純函式測試（多因子加分 / 超買偵測 / reasons 去重）。"""

import screen


def test_bullish_setup_score_and_reasons():
    score, ob, reasons = screen.score_candidate(
        trend="多頭排列",
        signals=[{"type": "bullish", "code": "macd_hist_pos", "name": "MACD 柱狀圖轉正"}],
        rsi=55, foreign_days=5, trust_days=3, in_momentum=True)
    # 多頭+2、bullish 訊號+1、外資連買>=5 +3、投信連買>=3 +1、動能入榜+1 = 8
    assert score == 8
    assert ob is False
    assert "均線多頭排列" in reasons
    assert "外資連買5日" in reasons and "投信連買3日" in reasons
    assert "放量/漲幅入榜" in reasons


def test_overbought_via_signal_code():
    _, ob, _ = screen.score_candidate(
        trend="多頭排列",
        signals=[{"type": "bearish", "code": "rsi_overbought", "name": "RSI 超買（75）"}],
        rsi=75)
    assert ob is True


def test_overbought_via_rsi_threshold():
    _, ob, _ = screen.score_candidate(trend=None, signals=[], rsi=72)
    assert ob is True
    _, ob2, _ = screen.score_candidate(trend=None, signals=[], rsi=65)
    assert ob2 is False


def test_bearish_trend_is_negative():
    score, ob, _ = screen.score_candidate(
        trend="空頭排列",
        signals=[{"type": "bearish", "code": "ma_death", "name": "死亡交叉"}], rsi=40)
    assert score == -3  # 空頭 -2、bearish 訊號 -1
    assert ob is False


def test_reasons_dedup_preserves_order():
    _, _, reasons = screen.score_candidate(
        trend="多頭排列",
        signals=[{"type": "bullish", "name": "突破"}, {"type": "bullish", "name": "突破"}],
        rsi=50)
    assert reasons.count("突破") == 1
    assert reasons[0] == "均線多頭排列"
