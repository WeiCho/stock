# 台股分析 Skill

用自然語言查台股，整合技術面、籌碼面、10 年回測、新聞基本面，並產出 TradingView Pine Script。提供 CLI 與 React Web App 兩種介面，共用 FastAPI 後端，所有資料來自 TWSE / TPEx 官方開放資料，無需付費 API。

## 安裝

```bash
cd ~/.claude/skills/taiwan-stock
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 前端相依
cd web && npm install && cd ..
```

## 啟動

### 後端（必要）

```bash
cd ~/.claude/skills/taiwan-stock
source .venv/bin/activate
PYTHONPATH=server uvicorn server.main:app --host 0.0.0.0 --port 8000
```

啟動後自動下載今日三大法人資料與近 6 個月加權指數。
**第一次查詢某支股票**會自動下載該股 10 年歷史（約 5–15 秒）。

### 前端 Web App

```bash
cd ~/.claude/skills/taiwan-stock/web
npm run dev
# → 開啟 http://localhost:5173
```

### CLI（透過 Claude Code skill）

後端啟動後直接對 Claude 說：

```
分析台積電
2330 回測黃金交叉
幫我出台積電的 Pine Script
今天外資買超前五名
找外資連買超過 3 天的股票
今天加權指數怎麼樣
```

或直接執行：

```bash
source .venv/bin/activate
python main.py "分析台積電"
```

## 功能

### 個股分析

| 功能 | 說明 |
|------|------|
| 技術面 | 日K / 週K 均線（MA5~240）、RSI、MACD、KD、布林通道，自動偵測形態 |
| 籌碼面 | 外資 / 投信 / 自營商買賣超，連買天數，5/10/20 日累計 |
| 回測 | 9 種訊號的 10 年勝率統計，後續 5/10/20/60 天報酬率 |
| Pine Script | 回測結果自動生成 TradingView v5 策略程式碼 |
| 新聞 | RSS 彙整（鉅亨網 / Yahoo Finance），標注重大訊息 |
| 基本面 | EPS、本益比、殖利率、營收月增 / 年增（FinMind） |

### 大盤 / 市場

| 功能 | 說明 |
|------|------|
| 加權指數 | 近期走勢（預設 90 天） |
| 三大法人排行 | 全市場最新交易日買超 / 賣超排行 |
| 籌碼掃描 | 外資 / 投信連買 N 天以上的股票清單 |

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

## TradingView 整合

1. 執行回測：`GET /stock/2330/backtest?signal=ma_cross`
2. 產生 Pine Script：`GET /stock/2330/pine?signal=ma_cross`
3. 將 `pine_output/2330_ma_cross.pine` 內容貼到 TradingView Pine Script 編輯器
4. 在 TradingView 回測驗證，確認訊號一致

## 全市場歷史資料初始化（選用）

預設只有查詢過的個股才有 10 年歷史。若要使用全市場技術面選股，需先執行：

```bash
curl -X POST "http://localhost:8000/admin/init-all"
```

背景執行約 1–2 小時（全台 ~2,500 支股票）。三大法人籌碼掃描**不需要**此步驟，開箱即用。

## 資料來源

| 資料 | 來源 | 費用 |
|------|------|------|
| 個股歷史日K | TWSE / TPEx 官方開放資料 | 免費 |
| 三大法人每日 | TWSE T86 endpoint | 免費 |
| 加權指數歷史 | TWSE MI_5MINS_HIST（按月抓取） | 免費 |
| 基本面（EPS / PER） | FinMind 免費 API | 免費（有額度限制） |
| 新聞 | 鉅亨網 RSS / Yahoo Finance TW RSS | 免費 |
| 盤中即時報價 | Fugle Market Data API | 免費額度 |

## 注意事項

- 回測結果不含交易成本（手續費 0.1425%、證交稅 0.3%）
- 歷史勝率不代表未來績效
- 觸發次數 < 10 次時會標示低樣本警告
- 資料僅供個人研究用途
