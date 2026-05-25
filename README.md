# 台股分析 Skill

用自然語言問台股，整合技術面、籌碼面、回測、新聞基本面分析，並產出 TradingView Pine Script。

## 功能

- **技術面分析** — 日K / 週K 均線（MA）、RSI、MACD、KD、布林通道，自動偵測黃金交叉等形態
- **籌碼面分析** — 三大法人（外資、投信、自營商）買賣超，連買天數統計，全市場掃描
- **10 年回測** — 指定訊號的歷史勝率統計，後續 5/10/20/60 天報酬率
- **Pine Script 輸出** — 回測結果自動生成 TradingView v5 策略程式碼
- **新聞 + 基本面** — RSS 新聞彙整（鉅亨網 / Yahoo Finance）、EPS / PER / ROE / 殖利率
- **大盤總覽** — 加權指數 + 三大法人大盤買賣超排行

## 安裝

```bash
cd ~/.claude/skills/taiwan-stock
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 啟動 Server

```bash
PYTHONPATH=server uvicorn server.main:app --host 0.0.0.0 --port 8000
```

Server 啟動後自動下載今日三大法人資料與加權指數。第一次查詢某支股票時會自動下載該股 10 年歷史（約 5-10 秒）。

## 使用方式

### CLI（透過 Claude Code skill）

```
分析台積電
2330 回測黃金交叉
幫我出台積電的 Pine Script
今天外資買超前五名
找三大法人連買超過 5 天的股票
今天加權指數怎麼樣
```

### 直接呼叫 API

```bash
# 個股完整分析
curl "http://localhost:8000/stock/2330"

# 技術面（週K）
curl "http://localhost:8000/stock/2330/technical?timeframe=weekly"

# 籌碼面
curl "http://localhost:8000/stock/2330/chip"

# 回測：KD 低檔交叉，持有 5/10/20/60 天
curl "http://localhost:8000/stock/2330/backtest?signal=kd_low_cross"

# 輸出 Pine Script
curl "http://localhost:8000/stock/2330/pine?signal=ma_cross"

# 全市場：三大法人今日買超前 20
curl "http://localhost:8000/market/institutional?top=20"

# 全市場：外資連買 3 天以上的股票
curl "http://localhost:8000/market/chip-scan?min_foreign_days=3"
```

## 支援的回測訊號

| 訊號代碼 | 說明 |
|---------|------|
| `ma_cross` | MA20 × MA60 黃金交叉（日K） |
| `ma_death` | MA20 × MA60 死亡交叉（日K） |
| `weekly_ma_cross` | 週MA20 × 週MA52 黃金交叉 |
| `kd_low_cross` | KD 低檔黃金交叉（K<30） |
| `kd_high_cross` | KD 高檔死亡交叉（K>70） |
| `macd_turn_pos` | MACD 柱狀圖由負轉正 |
| `macd_turn_neg` | MACD 柱狀圖由正轉負 |
| `rsi_oversold` | RSI 超賣（<30）回升 |
| `rsi_overbought` | RSI 超買（>70）回落 |

完整清單：`GET /backtest/signals`

## TradingView 整合

1. 執行回測取得勝率統計：`GET /stock/2330/backtest?signal=ma_cross`
2. 產生 Pine Script：`GET /stock/2330/pine?signal=ma_cross`
3. 將 `pine_output/2330_ma_cross.pine` 的內容貼到 TradingView Pine Script 編輯器
4. 在 TradingView 上回測驗證，確認訊號與本地結果一致

## 全市場歷史資料初始化（選用）

預設只有查詢過的個股才有 10 年歷史資料。若要使用**低基期技術面選股**等全市場掃描功能，需先執行初始化：

```bash
curl -X POST "http://localhost:8000/admin/init-all"
```

背景執行約 1-2 小時（全台 ~2,500 支股票，爬蟲速率 1 req/秒）。三大法人掃描**不需要**此步驟，開箱即用。

## 資料來源

| 資料 | 來源 | 費用 |
|------|------|------|
| 個股歷史日K | TWSE / TPEx 官方開放資料 | 免費 |
| 三大法人每日 | TWSE T86 endpoint | 免費 |
| 加權 / 櫃買指數 | TWSE / TPEx | 免費 |
| 基本面（EPS / PER / ROE） | FinMind 免費 API | 免費（有額度限制） |
| 新聞 | 鉅亨網 RSS / Yahoo Finance TW RSS | 免費 |
| 盤中即時報價 | Fugle Market Data API | 免費額度 |

## 注意事項

- 回測結果不含交易成本（手續費 0.1425%、證交稅 0.3%）
- 歷史勝率不代表未來績效
- 觸發次數 < 10 次時會標示低樣本警告
- 資料僅供個人研究用途
