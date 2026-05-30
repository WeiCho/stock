# Taiwan Stock Skill — CLAUDE.md

## 專案概述

台股 + 國際商品 + 期貨 + 總體經濟分析工具，提供 React Web App 與 CLI 兩種介面，共用 FastAPI 後端。

- **個股**：技術面（MA/MACD/KDJ 金叉死叉 markers + 量能副圖）、籌碼面（三大法人）、10 年回測（11 種訊號）、型態掃描（三線交纏帶量突破）、Pine Script 一鍵下載、新聞、基本面、綜合研判
- **大盤**：即時加權指數（每秒輪詢 + 交易時段 gate）、法人資金動向、類股流向、大單敲進（Fugle 逐筆）
- **期貨**：台股期貨（TX/MTX/TE/TF）+ 國際商品（黃金/白銀/銅/原油）+ 三大法人留倉
- **總經 Macro**：5 層分析框架，含 DXY / VIX / 公債利率 / SPX / NASDAQ / BTC / ETH
- **全球新聞**：亞 / 歐 / 美 + 地緣政治關鍵字（Google News，後端 30 min 快取）

## 目錄結構

```
e:\stock\
├── CLAUDE.md / README.md
├── start.ps1              # 一鍵啟動（Windows，背景執行，關閉視窗自動 kill）
├── .env                   # FUGLE_API_KEY / FRED_API_KEY（gitignored）
├── requirements.txt
├── requirements-dev.txt   # pytest
├── stocks.db              # SQLite（自動建立，勿 commit）
├── pine_output/           # 生成的 .pine 檔（勿 commit）
├── server/
│   ├── main.py            # FastAPI routes
│   ├── db.py              # SQLAlchemy + SQLite init
│   ├── data_fetcher.py    # 三層下載策略（FinMind 主力 + TWSE/TPEx 備援）
│   ├── indicators.py      # 自寫純 pandas SMA/RSI/MACD/KD/BBands
│   ├── technical.py       # 指標計算 + 形態偵測
│   ├── chip.py            # 三大法人 + 類股資金流向
│   ├── backtest.py        # 11 種訊號回測 + 型態掃描 mask
│   ├── outlook.py         # 綜合研判（多空權重）
│   ├── news_fundamental.py
│   ├── fugle.py           # 盤中即時 + 大單偵測（需 FUGLE_API_KEY）
│   ├── commodities.py     # 期貨 + 國際商品 + 總經市場面
│   ├── fred.py            # 美國經濟指標（需 FRED_API_KEY）
│   ├── pine_exporter.py   # 11 個訊號的 Pine v5 模板
│   └── tests/             # pytest 26 個
└── web/
    ├── src/
    │   ├── App.tsx         # 5 views: market / global / futures / macro / stock
    │   ├── api.ts          # get<T>() + endpoint wrappers
    │   ├── types.ts        # response types
    │   ├── indicators.ts   # JS 端 RSI / KDJ / MACD
    │   ├── lib/charts.ts   # toTime / isTradingHours / SESSION_MINUTES
    │   ├── hooks/useAsync.ts
    │   └── components/     # PriceChart / MarketOverview / GlobalPanel /
    │                       # FuturesPanel / MacroPanel / PatternPanel /
    │                       # OutlookPanel / TechnicalPanel / ChipPanel /
    │                       # BacktestPanel / FundamentalsPanel / NewsPanel /
    │                       # ErrorBoundary
    └── tsconfig.json       # strict: true
```

## 啟動方式

```powershell
.\start.ps1
```

前後端在同一個 PowerShell 視窗背景執行。關閉視窗或 Ctrl+C 自動 kill 前後端。首次自動建立 venv 與 npm install。

```powershell
# 手動後端
.\.venv\Scripts\python.exe -m uvicorn server.main:app --host 0.0.0.0 --port 8000

# 手動前端
cd web; npm run dev   # → http://localhost:5173
```

## API 路由

### 個股
| Path | 說明 |
|------|------|
| `/stock/{symbol}` | 完整個股分析 |
| `/stock/{symbol}/price` | 日K（?days=120&tf=1d\|3d\|5d\|1w\|3w\|1mo）|
| `/stock/{symbol}/intraday` | Fugle 盤中分鐘K（?timeframe=5）|
| `/stock/{symbol}/technical` | 技術面（?timeframe=daily\|weekly）|
| `/stock/{symbol}/outlook` | 綜合研判 |
| `/stock/{symbol}/chip` | 籌碼面 |
| `/stock/{symbol}/backtest` | 回測（?signal=ma_cross 等 11 種）|
| `/stock/{symbol}/pattern-scan` | 三線交纏帶量突破型態掃描 |
| `/stock/{symbol}/pine` | 輸出 Pine v5 |
| `/stock/{symbol}/news` | 新聞列表 |
| `/stock/{symbol}/fundamentals` | 基本面指標 |
| `/stock/search` | 代碼或中文名稱模糊搜尋 |

### 大盤
| Path | 說明 |
|------|------|
| `/market/institutional` | 三大法人全市場排行 |
| `/market/chip-scan` | 全市場連買掃描 |
| `/market/index` | 加權指數走勢 |
| `/market/index/live` | 即時加權指數（TWSE MIS）|
| `/market/index/intraday` | TAIEX 盤中分鐘K（Fugle IX0001）|
| `/market/money-flow` | 法人資金 + 盤後統計 + 類股流向 |
| `/market/big-orders` | 大單敲進（Fugle 逐筆）|
| `/market/global` | 全球盤勢新聞（亞/歐/美 + 地緣，30 min 快取）|

### 期貨 / 商品 / 總經
| Path | 說明 |
|------|------|
| `/market/commodities` | 支援符號清單 |
| `/market/commodity/{symbol}/price` | K 線 + perf 摘要（TX/MTX/TE/TF/GC/CL/SI/HG/DXY/SPX/NDX/DJI/VIX/TNX/FVX/BTC/ETH）|
| `/market/futures/institutional` | 期貨三大法人留倉 |
| `/market/macro/economic` | 美國 6 大經濟指標（需 FRED_API_KEY）|
| `/market/macro/series/{series_id}` | 單一 FRED series |
| `/backtest/signals` | 11 種訊號清單 |
| `/admin/init-all` | 全台股歷史下載（背景，1-2 小時）|
| `/health` | 健康檢查 |

## 分析模組

### backtest.py — 型態掃描邏輯

`_ma_tangle_breakout_mask(df)` 實作「三線交纏帶量突破 MA60」的觸發條件：
1. MA5/MA10/MA20 三線差距 < 收盤 3%（交纏）
2. 昨日量 > 20 日均量 × 1.5（帶量突破）
3. 連續 2 日收盤站上 MA60（昨突破、今確認）
4. 前天仍在 MA60 以下（突破剛發生）

`/stock/{symbol}/pattern-scan` route 在後端計算兩層：
- **蓄勢判定**：三線交纏 + 距 MA60 < 3% → `setup_triggered: true`，提示可準備進場
- **突破判定**：四條件全符合 → `triggered: true`，觸發完整回測統計

回測以**冷卻期去重**確保樣本獨立：每次觸發後，間隔持有天數內的重複觸發不計入（避免連續觸發重複計算同一段行情）。

### technical.py
- `daily` / `weekly` 兩種時間框架，週K 由日K resample（W-FRI）
- 指標：MA(5/10/20/60/120/240)、RSI(14)、MACD(12/26/9)、KD(9/3/3)、布林(20,2σ)

### chip.py
- `analyze(symbol)`、`scan_bulk(min_foreign_days=3)`、`market_money_flow()`、`sector_money_flow()`

### commodities.py
- FinMind 台股期貨：自動取同日最大成交量合約（近月連續價）
- Yahoo Finance 國際商品 + 總經市場指標
- 5 min in-memory cache（key = symbol:days）

### fred.py
- 指標：CPIAUCSL / PCE / GDP / PAYEMS / UNRATE / DFF
- 未設 `FRED_API_KEY` → 前端顯示申請提示
- 1 小時 in-memory cache

### data_fetcher.py
- `fetch_finmind_price_history()` — 一次抓完整 10 年
- `fetch_daily_institutional_bulk()` — TWSE T86，`foreign = row[4]+row[7]`、`dealer = row[11]`
- `resample_ohlc(df, tf)` — 1d/3d/5d/1w/3w/1mo
- `fetch_live_index()` — async TWSE MIS

### fugle.py
- `intraday_candles()` — 並行抓 candles + quote（quote 失敗仍回 candles）
- `scan_big_orders()` — async parallel，排除 serial 99999999 + hm in (900, 1325)

## 前端架構

### View 切換（5 個）
1. **大盤**（預設）— MarketOverview：即時指數 + 法人 + 類股 + 大單
2. **全球** — GlobalPanel：亞/歐/美 + 地緣政治新聞
3. **期貨** — FuturesPanel：符號選單 + perf 表 + 法人留倉
4. **總經** — MacroPanel：5 層 macro 框架
5. **個股** — 7 時間框架 K 線 + 7 個 tab（綜合研判/技術/籌碼/回測/型態/基本面/新聞）

### PriceChart（K 線元件）
- **盤中**：BaselineSeries（昨收為基準上紅下綠 + 均價線 + rightOffset 補滿交易時段）
- **非盤中**：CandlestickSeries + MA 疊圖（5/10/20/60）+ 量能副圖（pane 1）
- **markers**：MA20/MA60 金叉/死叉箭頭 + MACD 訊號圓點（主圖上，無 MACD 曲線副圖）
- `lastValueVisible: false`：均線與K棒收盤價均不顯示右側 TAG
- `fixLeftEdge: true` + `fixRightEdge: true`：防止拖曳超出資料左右邊界（v5 副圖不受影響）
- `scrollToRealTime()` after `fitContent()`：收斂 fitContent 的留白，確保最後一根K棒貼右邊界
- 副圖刻度隱藏：用 `series.priceScale().applyOptions({ borderVisible: false })`，**不要用 `visible: false`**（會把主圖 right scale 寬度壓成 0）
- 容器需給明確高度（`style={{ height: 520 }}`），否則 lightweight-charts 抓到 clientHeight=0 導致渲染失敗
- ResizeObserver callback 先 guard `chartRef.current` 存在，避免 chart remove 後觸發 null 錯誤

### PatternPanel（型態掃描面板）
- **蓄勢條件**（`setup_triggered`）：三線交纏 + 距 MA60 < 3% → 藍色「蓄勢中」badge
- **突破確認**（`triggered`）：帶量突破 + 站穩 2 日 → 橘/黃色「突破完成」badge
- 條件進度分兩區塊：① 蓄勢條件 ② 突破確認條件（含加分項 MA60 方向）
- 觸發後回測統計表（5/10/20 日）：勝率顏色 ≥60% 綠 / ≥50% 黃 / <50% 紅

### URL Hash 狀態持久化
- `view` / `symbol` / `tab` / `tf` 同步寫入 `location.hash`（`history.replaceState`）
- 重整頁面自動從 hash 還原

### 即時策略（盤中 09:00–13:30 台北時間）

| 來源 | 頻率 |
|---|---|
| TWSE MIS 即時指數 | 1 秒 |
| Fugle 大單敲進 | 60 秒 |
| Fugle 盤中分鐘K | 用戶切「當日」時 fetch |

## 注意事項

- `stocks.db` / `pine_output/` 已加入 `.gitignore`，勿手動 commit
- TWSE/TPEx 爬蟲 1.2 秒/req（`REQUEST_DELAY`）
- FinMind 免費 API 有日額度
- 技術指標自寫 `indicators.py`（避開 pandas-ta + numpy 2 不相容問題）
- TPEx 憑證鏈缺 SKI → 放寬 OpenSSL3 `VERIFY_X509_STRICT`（仍完整驗證）
- lightweight-charts v5 API：`addSeries(SeriesClass, opts, paneIndex)`、`createSeriesMarkers(series, markers)`
- 資料僅供個人研究，不得用於自動下單

## 測試

```powershell
.\.venv\Scripts\python.exe -m pytest server/tests -v   # 26 tests
cd web; npm test                                        # vitest 10 tests
```
