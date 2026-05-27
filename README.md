# 台股分析 Skill

用自然語言查台股，整合技術面、籌碼面、10 年回測、新聞基本面，並產出 TradingView Pine Script。提供 CLI 與 React Web App 兩種介面，共用 FastAPI 後端；行情與籌碼來自 TWSE / TPEx 官方開放資料，基本面用 FinMind、新聞用 Google News，皆無需付費 API。

## 安裝

```bash
cd ~/.claude/skills/taiwan-stock
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 前端相依
cd web && npm install && cd ..
```

### 盤中即時報價 / 大單敲進（選用）

複製 `.env.example` 為 `.env`，填入 [Fugle Market Data](https://developer.fugle.tw/) 的 API key：

```bash
cp .env.example .env   # 編輯 .env，填入 FUGLE_API_KEY
```

沒有 key 也能用其餘所有功能（行情、法人、回測、綜合研判…皆免費）；有 key 才會啟用首頁的「🔥 大單敲進」盤中逐筆偵測。

## 啟動

### 一鍵啟動（推薦）

```bash
./start.sh
```

首次執行自動建立 Python 虛擬環境、安裝前後端相依，接著同時啟動後端（`:8000`）與前端（`:5173`），macOS 會自動開啟瀏覽器；按 `Ctrl+C` 一併關閉。要分開手動啟動見下方。

### 後端（必要）

```bash
source .venv/bin/activate
PYTHONPATH=server uvicorn server.main:app --host 0.0.0.0 --port 8000
```

啟動後自動下載今日三大法人資料與近 6 個月加權指數。
**第一次查詢某支股票**會自動下載該股 10 年歷史（透過 FinMind 一次抓取，約 1–2 秒；FinMind 不可用時改用 TWSE/TPEx 逐月爬取，較慢）。

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
| 綜合研判 | 結合技術面、籌碼面、10 年回測的方向研判（偏多/中性/偏空）與預期區間 |
| 技術面 | 日K / 週K 均線（MA5~240）、RSI、MACD、KD、布林通道，自動偵測形態 |
| 籌碼面 | 外資 / 投信 / 自營商買賣超，連買天數，5/10/20 日累計 |
| 回測 | 9 種訊號的 10 年勝率統計，後續 5/10/20/60 天報酬率 |
| Pine Script | 回測結果自動生成 TradingView v5 策略程式碼 |
| 新聞 | Google News 依公司名稱彙整近 30 天，標注重大訊息 |
| 基本面 | EPS、本益比、殖利率、營收月增 / 年增（FinMind） |

### 大盤 / 市場

| 功能 | 說明 |
|------|------|
| 加權指數 | 即時走勢（盤中每 20 秒更新）+ 時間區間 3日/1月/3月/6月/1年/5年 + 近 5 / 20 日漲跌 |
| 法人資金動向 | 外資 / 投信 / 自營商當日淨買賣超 + 外資・投信買超／賣超排行（盤後） |
| 類股資金流向 | 依產業別彙總三大法人淨買賣超，看資金流入 / 流出哪些類股（盤後） |
| 盤後大盤統計 | 成交金額、漲跌家數（盤後） |
| 大單敲進 | 盤中逐筆偵測法人買超股的單筆大額成交（需 Fugle key，見下方設定） |
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
| 個股歷史日K（10年） | FinMind（首選，一次抓取）／ TWSE·TPEx 爬蟲（備援） | 免費 |
| 三大法人每日 | TWSE T86 endpoint | 免費 |
| 加權指數歷史（5年） | FinMind（首選）／ TWSE MI_5MINS_HIST（備援，按月） | 免費 |
| 即時加權指數 | TWSE MIS（盤中即時） | 免費 |
| 股票清單（含市場別） | TWSE STOCK_DAY_ALL / TPEx OpenAPI | 免費 |
| 產業別（類股分類） | FinMind TaiwanStockInfo | 免費 |
| 基本面（EPS / PER） | FinMind 免費 API | 免費（有額度限制） |
| 新聞 | Google News RSS（依公司名稱查詢） | 免費 |
| 盤中逐筆 / 大單敲進 | Fugle Market Data API | 免費額度（需 API key，選用） |

## 注意事項

- 回測結果不含交易成本（手續費 0.1425%、證交稅 0.3%）
- 歷史勝率不代表未來績效
- 觸發次數 < 10 次時會標示低樣本警告
- 資料僅供個人研究用途
