# 台股分析 Skill

用自然語言查台股，整合技術面、籌碼面、10 年回測、新聞基本面，並產出 TradingView Pine Script。提供 CLI 與 React Web App 兩種介面，共用 FastAPI 後端；行情與籌碼來自 TWSE / TPEx 官方開放資料，基本面用 FinMind、新聞用 Google News，皆無需付費 API。

## 架構（30 秒理解）

```
免費資料來源                  ── 後端 ──                   ── 前端 ──
─────────────────             ──────────                    ─────────
FinMind         10yr 日K  ┐
TWSE / TPEx     法人/指數  ┼──→  FastAPI (Python 3.14)   ──→  React 19 + Vite
Fugle           盤中即時   ┤      + SQLite cache             + lightweight-charts v5
Google News     新聞/地緣  ┘        (stocks.db)              (TradingView 開源圖表)
                                  + 22 routes               + RSI / KDJ 副圖
                                  + daemon thread 補資料     + 金叉/死叉 markers
                                                            + ErrorBoundary 三層
                       共用 SQLite cache：
              避開 FinMind 日額度 + TWSE 1.2s/req 速率限制
```

這是「免費 API + 個人工具」的典型 pattern，等價於 *Polygon/Yahoo/Binance → Go API → TradingView Charts*；我們用 **Python + lightweight-charts**（TradingView 自家的開源圖表）取代，多了一層 **SQLite cache** 避開額度限制。

## 安裝

```bash
cd ~/.claude/skills/taiwan-stock
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 前端相依
cd web && npm install && cd ..
```

### 選用 API key（皆免費，沒設也能跑大部分功能）

```bash
cp .env.example .env   # 編輯填入下方 keys
```

| Key | 用途 | 沒設會怎樣 | 申請 |
|---|---|---|---|
| `FUGLE_API_KEY` | 盤中即時 K + 「🔥 大單敲進」逐筆偵測 | 大單面板隱藏；K 線當日改用日線收盤 | [developer.fugle.tw](https://developer.fugle.tw/) |
| `FRED_API_KEY` | 總經頁的 CPI / GDP / NFP / Fed Funds / 失業率 | 顯示「需設定」link | [fred.stlouisfed.org/docs/api/api_key](https://fred.stlouisfed.org/docs/api/api_key.html) |

## 啟動

### 一鍵啟動（推薦）

**macOS / Linux**

```bash
./start.sh
```

首次執行自動建立 Python 虛擬環境、安裝前後端相依，接著同時啟動後端（`:8000`）與前端（`:5173`），macOS 會自動開啟瀏覽器；按 `Ctrl+C` 一併關閉。

**Windows（PowerShell）**

```powershell
.\start.ps1
```

首次執行自動建立 Python 虛擬環境、安裝前後端相依，接著各開一個 PowerShell 視窗分別跑後端與前端，並自動開啟瀏覽器（`http://localhost:5173`）；關閉各視窗即可停止對應服務。

要分開手動啟動見下方。

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
| K 線圖 | 7 種時間框架（當日/日K/3日/5日/週K/3週/月K）+ MA 疊圖 + **RSI/KDJ 副圖** + **金叉/死叉 marker**；當日採 Apple Stocks 風格（昨收為基準上紅下綠）|
| 技術面 | 日K / 週K 均線（MA5~240）、RSI、MACD、KD、布林通道，自動偵測形態 |
| 籌碼面 | 外資 / 投信 / 自營商買賣超，連買天數，5/10/20 日累計 |
| 回測 | **11 種訊號**的 10 年勝率統計，後續 5/10/20/60 天報酬率 |
| Pine Script | 回測結果自動生成 TradingView v5 策略程式碼，UI 一鍵下載 |
| 新聞 | Google News 依公司名稱彙整近 30 天，標注重大訊息 |
| 基本面 | EPS、本益比、殖利率、營收月增 / 年增（FinMind） |

### 大盤 / 市場

| 功能 | 說明 |
|------|------|
| 加權指數 | 即時走勢（盤中**每秒更新** + isTradingHours gate）+ 時間區間 當日/3日/1月/3月/6月/1年/5年 + 近 5 / 20 日漲跌 |
| 法人資金動向 | 外資 / 投信 / 自營商當日淨買賣超 + 外資・投信買超／賣超排行（盤後） |
| 類股資金流向 | 依產業別彙總三大法人淨買賣超，看資金流入 / 流出哪些類股（盤後） |
| 盤後大盤統計 | 成交金額、漲跌家數（盤後） |
| 大單敲進 | 盤中逐筆偵測法人買超股的單筆大額成交（需 Fugle key，每 60 秒輪詢） |
| 籌碼掃描 | 外資 / 投信連買 N 天以上的股票清單 |
| **全球面板** | 亞 / 歐 / 美 三大市場 + 地緣政治關鍵字新聞（Google News，後端 30 分鐘快取） |

### 期貨 / 國際商品

| 功能 | 說明 |
|------|------|
| 台股期貨 | 台指期 TX / 小台 MTX / 電子期 TE / 金融期 TF（FinMind，自動取同日最大成交量合約 = 近月連續價） |
| 國際商品 | 黃金 GC / 黃金現貨 XAUUSD / 白銀 SI / 銅 HG / 原油 WTI CL（Yahoo Finance，免 API key） |
| 績效摘要 | 1d / 5d / 1m / 6m / YTD / 1y / 5y / 10y 累積報酬（仿 TradingView XAUUSD perf 表） |
| 期貨三大法人留倉 | TX/MTX/TE/TF 外資 / 投信 / 自營商淨多空口數（FinMind TaiwanFuturesInstitutionalInvestors） |

### 總體經濟（Macro）

5 層分析框架，整合 Yahoo Finance 全球指標：

| 層 | 內容 |
|---|---|
| **🌍 1. 總體經濟** | 美 10Y/5Y 公債（^TNX / ^FVX）、DXY 美元指數、VIX 恐慌指數 + 升降息/通膨/衰退的市場反應對照 |
| **💵 2. 資金流** | 利率 ↔ 資金流向解釋（高利率 → 錢回債券；低利率 → 錢流風險資產） |
| **📊 3. 市場價格** | SPX / NDX / DJI / 黃金 / 原油 / 白銀 / DXY / BTC / ETH + 交叉關係表 |
| **📈 4. 籌碼情緒** | VIX 自動分級（> 30 恐慌、> 20 警戒、≤ 20 平靜） |
| **🌐 5. 地緣政治** | 戰爭 / 美國選舉 / 制裁 / 石油供應鏈（deep-link 到「全球」頁） |

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
| `best_four_buy` | 四大買點（量價/均線 + 負乖離反彈，twstock）|
| `best_four_sell` | 四大賣點（量價/均線 + 正乖離反轉，twstock）|

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
| 台股期貨日 K + 法人留倉 | FinMind TaiwanFuturesDaily / InstitutionalInvestors | 免費 |
| 國際商品 / 全球指數 / 加密貨幣 | Yahoo Finance v8 Chart API | 免費 |
| 美國經濟（CPI / GDP / NFP / Fed Funds / 失業率 / PCE） | FRED API（St. Louis Fed） | 免費（需 API key，選用） |

## 注意事項

- 回測結果不含交易成本（手續費 0.1425%、證交稅 0.3%）
- 歷史勝率不代表未來績效
- 觸發次數 < 10 次時會標示低樣本警告
- 資料僅供個人研究用途
