# Taiwan Stock — CLAUDE.md

## 專案概述

台股 + 國際商品 + 期貨 + 總體經濟分析工具，React Web App + FastAPI 後端。

- **個股**：技術面（MA/MACD/KDJ markers + 量能副圖）、籌碼面、11 種訊號回測、型態掃描、Pine Script 匯出、新聞、基本面、綜合研判
- **大盤**：即時加權指數（1 秒輪詢）、法人資金動向、類股流向、大單敲進
- **掃描**：三線交纏帶量突破 + 週線W底突破 — 全市場掃描（當日快取）
- **期貨**：TX/MTX/TE/TF + 黃金/白銀/銅/原油 + 三大法人留倉
- **總經**：DXY / VIX / 公債 / SPX / NASDAQ / BTC / ETH
- **全球新聞**：亞/歐/美 + 地緣政治（Google News，30 min 快取）

## 目錄結構

```
e:\stock\
├── start.ps1              # 一鍵啟動（Windows）
├── .env                   # FUGLE_API_KEY / FRED_API_KEY（gitignored）
├── stocks.db              # SQLite（自動建立，勿 commit）
├── pine_output/           # 生成的 .pine 檔（勿 commit）
├── server/
│   ├── main.py            # FastAPI routes
│   ├── db.py              # SQLAlchemy + SQLite init
│   ├── data_fetcher.py    # FinMind 主力 + TWSE/TPEx 備援
│   ├── indicators.py      # 自寫純 pandas SMA/RSI/MACD/KD/BBands
│   ├── technical.py       # 指標計算 + 形態偵測
│   ├── chip.py            # 三大法人 + 類股資金流向
│   ├── backtest.py        # 11 種訊號回測 + 三線交纏/週W底 mask + 全市場掃描
│   ├── outlook.py         # 綜合研判（多空權重）
│   ├── news_fundamental.py
│   ├── fugle.py           # 盤中即時 + 大單偵測（需 FUGLE_API_KEY）
│   ├── commodities.py     # 期貨 + 國際商品 + 總經市場面
│   ├── fred.py            # 美國經濟指標（需 FRED_API_KEY）
│   ├── pine_exporter.py   # 11 個訊號的 Pine v5 模板
│   └── tests/
└── web/src/
    ├── App.tsx             # 6 views: market / global / futures / macro / scan / stock
    ├── api.ts
    ├── types.ts
    └── components/         # PriceChart / MarketOverview / GlobalPanel / FuturesPanel /
                            # MacroPanel / MarketPatternScanPanel / WeeklyWBottomScanPanel /
                            # PatternPanel / OutlookPanel / TechnicalPanel / ChipPanel /
                            # BacktestPanel / FundamentalsPanel / NewsPanel / ErrorBoundary
```

## 啟動

```powershell
.\start.ps1
# 後端 :8000 / 前端 :5173
```

手動：
```powershell
.\.venv\Scripts\python.exe -m uvicorn server.main:app --host 0.0.0.0 --port 8000
cd web; npm run dev
```

## API 路由

### 個股
| Path | 說明 |
|------|------|
| `/stock/{symbol}/price` | K線（?days&tf=1d\|3d\|5d\|1w\|3w\|1mo）|
| `/stock/{symbol}/intraday` | Fugle 盤中分鐘K |
| `/stock/{symbol}/technical` | 技術面（?timeframe=daily\|weekly）|
| `/stock/{symbol}/outlook` | 綜合研判 |
| `/stock/{symbol}/chip` | 籌碼面 |
| `/stock/{symbol}/backtest` | 回測（?signal=...）|
| `/stock/{symbol}/pattern-scan` | 三線交纏型態掃描 |
| `/stock/{symbol}/pine` | Pine v5 匯出 |
| `/stock/{symbol}/news` | 新聞 |
| `/stock/{symbol}/fundamentals` | 基本面 |
| `/stock/search` | 模糊搜尋 |

### 大盤 / 掃描
| Path | 說明 |
|------|------|
| `/market/index/live` | 即時加權指數 |
| `/market/index/intraday` | TAIEX 盤中分鐘K |
| `/market/money-flow` | 法人資金 + 類股流向 |
| `/market/big-orders` | 大單敲進 |
| `/market/global` | 全球新聞 |
| `/market/pattern-scan` | 三線交纏全市場掃描（當日快取）|
| `/market/weekly-w-bottom-scan` | 週線W底全市場掃描（當日快取）|
| `/market/chip-scan` | 三大法人連買掃描 |

### 期貨 / 總經
| Path | 說明 |
|------|------|
| `/market/commodity/{symbol}/price` | K線 + perf（TX/GC/CL/DXY/SPX/BTC…）|
| `/market/futures/institutional` | 期貨三大法人留倉 |
| `/market/macro/economic` | 美國 6 大經濟指標（需 FRED_API_KEY）|
| `/backtest/signals` | 11 種訊號清單 |
| `/admin/init-all` | 全台股歷史下載（背景）|
| `/health` | 健康檢查 |

## 分析模組重點

### backtest.py — 型態 mask

**`_ma_tangle_breakout_mask`**（三線交纏帶量突破 MA60）：
1. MA5/MA10/MA20 差距 < 收盤 3%（交纏）
2. 連 2 日收盤 > MA60（昨突破、今確認）
3. 前天收盤 ≤ MA60（突破剛發生）
4. 昨量 > 20日均量 × 1.5（帶量）

蓄勢判定（`setup_triggered`）：三線交纏 + 收盤站上 MA5/MA10/MA20 + 距 MA60 < 3%。

**`_weekly_w_bottom_mask`**（週線W底突破）：
1. 本週收盤剛站上週MA20（上週仍在以下）
2. 週MA20 本週 > 3週前（均線上斜）
3. 近 40 週 W 底：底底高 + 兩底間峰值高出均值 3%，第二底距今 ≤ 16 週
4. 本週量 > 近10週均量 × 1.5

兩個掃描函式都有**當日 in-memory 快取**（`_scan_cache` / `_w_scan_cache`），隔天自動失效。

回測**冷卻期去重**：每次觸發後，間隔持有天數內的重複觸發不計入。

**已知地雷**：收盤價為 0 的股票（剛上市/資料缺漏）計算 `(exit-entry)/entry` 會產生 `inf`，JSON 序列化失敗。回測除法前必須 guard `if not entry_price: continue`。

### data_fetcher.py
- FinMind 一次抓 10 年；失敗自動退回 TWSE/TPEx 逐月爬（1.2 s/req）
- `fetch_twse_stock_month`：JSON 解碼與 ReadTimeout 皆 catch，月份失敗繼續下一月

### technical.py
- `daily` / `weekly` 兩框架，週K 由日K resample（W-FRI）
- 指標：MA(5/10/20/60/120/240)、RSI(14)、MACD(12/26/9)、KD(9/3/3)、布林(20,2σ)

### fugle.py
- `intraday_candles()`：並行抓 candles + quote，quote 失敗仍回 candles
- `scan_big_orders()`：排除 serial 99999999 + hm in (900, 1325)

## 前端架構

### Views（6 個）
1. **大盤** — 即時指數 + 法人 + 類股 + 大單
2. **全球** — 亞/歐/美 + 地緣政治新聞
3. **期貨** — 符號選單 + perf 表 + 法人留倉
4. **總經** — 5 層 macro 框架
5. **掃描** — 三線交纏掃描 + 週線W底掃描（state 住 App 層，切 view 不重跑）
6. **個股** — 7 時間框架 K 線 + 7 tab

### PriceChart
- 盤中：BaselineSeries（昨收基準，上紅下綠）
- 非盤中：CandlestickSeries + MA 疊圖 + 量能副圖（pane 1）
- markers：MA20/MA60 金叉死叉箭頭 + MACD 訊號圓點
- `lastValueVisible: false`（不顯示右側 TAG）
- 副圖刻度隱藏用 `priceScale().applyOptions({ borderVisible: false })`，**不用 `visible: false`**（會壓縮主圖 scale 寬度）
- 容器需給明確高度，否則 clientHeight=0 渲染失敗

### URL Hash 狀態
- `view` / `symbol` / `tab` / `tf` 同步寫入 `location.hash`，重整自動還原

### 即時輪詢（盤中）
| 來源 | 頻率 |
|---|---|
| TWSE MIS 即時指數 | 1 秒 |
| Fugle 大單敲進 | 60 秒 |

## 注意事項

- `stocks.db` / `pine_output/` 已 gitignore
- FinMind 免費 API 有日額度（超額退 402，自動切 TWSE 備援）
- lightweight-charts v5：`addSeries(SeriesClass, opts, paneIndex)`、`createSeriesMarkers(series, markers)`
- 資料僅供個人研究

## 測試

```powershell
.\.venv\Scripts\python.exe -m pytest server/tests -v
cd web; npm test
```
