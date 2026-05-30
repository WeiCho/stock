# Taiwan Stock — CLAUDE.md

## 專案概述

台股 + 國際商品 + 期貨 + 總體經濟分析工具，React Web App + FastAPI 後端。

- **個股**：技術面（MA/MACD/KDJ markers + 量能副圖）、籌碼面、11 種訊號回測、型態掃描、Pine Script 匯出、新聞、基本面、綜合研判
- **大盤**：即時加權指數（1 秒輪詢）、法人資金動向、類股流向、大單敲進
- **掃描**：三線交纏帶量突破 + 週線W底突破 — 全市場掃描（當日快取）
- **期貨**：TX/MTX/TE/TF + 黃金/白銀/銅/原油 + 三大法人留倉
- **總經**：DXY / VIX / 公債 / SPX / NASDAQ / BTC / ETH
- **全球新聞**：亞/歐/美 + 地緣政治（Google News，30 min 快取）
本地台股 + 美股 + 國際商品 + 期貨 + 總體經濟分析工具，提供 CLI（Claude Code skill）與 React Web App 兩種介面，共用 FastAPI 後端。前端全面 i18n（zh-TW / en）。涵蓋：

- **個股（台股 + 美股）**：技術面（含 RSI / KDJ 副圖、MA/MACD/KDJ 金叉死叉 markers）、籌碼面（三大法人）、10 年回測（11 種訊號含 twstock 四大買賣點）、Pine Script 一鍵下載、新聞、基本面（含月營收 MoM/YoY、外資持股、融資融券、借券）、綜合研判。美股以 Yahoo v8 寫進共用 `daily_price` schema，技術/回測/綜合研判自動相容
- **大盤**：即時加權指數（每秒輪詢 + 交易時段 gate）、法人資金動向、類股流向、🔥 大單敲進（Fugle 逐筆）、全市場漲跌幅/成交值排行（market movers）
- **期貨**：台股期貨（TX/MTX/TE/TF）+ 國際商品（黃金/白銀/銅/原油）+ 三大法人留倉 + TXO Put/Call Ratio
- **總經 Macro**：5 層分析框架（總體 → 資金流 → 市場價格 → 籌碼情緒 → 地緣政治），含 DXY / VIX / 公債利率 / 殖利率曲線 / SPX / NASDAQ / BTC / ETH、加密前 10 大、外匯匯率、經濟事件日曆
- **觀察清單**：自選股 + 警示條件 CRUD + 當前狀態評估
- **全球新聞**：亞 / 歐 / 美 + 地緣政治關鍵字（Google News，後端 30 min 快取）

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
taiwan-stock/
├── CLAUDE.md / README.md / SKILL.md
├── main.py                # CLI 入口（自然語言意圖解析）
├── start.sh               # 一鍵啟動（PID 追蹤 + 乾淨 shutdown）
├── .env                   # FUGLE/FRED/FINNHUB_API_KEY + SEC_CONTACT_EMAIL（gitignored）/ .env.example 模板
├── requirements.txt       # 正式 runtime deps（含 python-dotenv）
├── requirements-dev.txt   # 測試 deps（pytest）
├── stocks.db              # SQLite（自動建立，勿 commit）
├── pine_output/           # 生成的 .pine 檔（勿 commit）
├── server/                # FastAPI 後端（25 個模組）
│   ├── main.py            # 52 routes，top-level imports（無 inline）+ 啟動 load_dotenv()
│   ├── db.py              # SQLAlchemy + SQLite init（10 張表）
│   ├── data_fetcher.py    # 三層下載策略（FinMind 主力 + TWSE/TPEx 備援；台股 + 美股分流）
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
│   ├── news_fundamental.py# 個股新聞 + 全球新聞 + 基本面
│   ├── fundamentals_extra.py # 進階台股基本面（月營收 MoM/YoY、外資持股、融資融券、借券；FinMind）
│   ├── fugle.py           # 盤中即時 + 大單偵測 + 即時報價快照（需 FUGLE_API_KEY）
│   ├── fugle_ws.py        # 多檔即時報價 WS hub（單一上游 Fugle 連線 + aggregates，廣播給瀏覽器）
│   ├── commodities.py     # 期貨 + 國際商品 + 總經市場面（FinMind + Yahoo Finance）
│   ├── fred.py            # 美國經濟指標（CPI/GDP/NFP/失業率/Fed Funds，需 FRED_API_KEY）
│   ├── crypto.py          # CoinGecko 前 10 大 + 全球統計（BTC/ETH dominance），無需 key
│   ├── fx.py              # USD 對 TWD/JPY/CNY/EUR/GBP/HKD/SGD 即時匯率（exchangerate-api），無需 key
│   ├── market_movers.py   # 全市場 T+0 漲跌幅/成交值排行 + 漲跌家數（TWSE STOCK_DAY_ALL）
│   ├── sec.py             # SEC EDGAR Form 4 內部人交易 + ticker→CIK（需 SEC_CONTACT_EMAIL 帶 UA）
│   ├── finnhub.py         # 經濟事件日曆 / 美股財報日 / 分析師評等 / 內線 / IPO（需 FINNHUB_API_KEY）
│   ├── taifex.py          # TXO Put/Call Ratio（成交量 + OI，FinMind TaiwanOptionDaily）
│   ├── us_stocks.py       # 美股支援：ticker 偵測 + Yahoo v8 → 寫進共用 daily_price + Finnhub /search
│   ├── screen.py          # 偏多候選多因子掃描（動能 + 籌碼連買 + 技術 + 估值；可排除 RSI 超買）
│   ├── twse_openapi.py    # TWSE 官方 OpenAPI：全市場估值(PER/PBR/殖利率) + 融資融券（免 key/額度）
│   ├── watchlist.py       # 觀察清單 + 警示條件 CRUD + evaluate_all() 當前狀態評估
│   ├── pine_exporter.py   # 11 個訊號的 Pine v5 模板
│   └── tests/             # pytest 76 個（backtest / resample / fugle / fugle_ws / twse_openapi / screen / commodities / fred）
└── web/                   # React 19 + Vite + TS strict + Tailwind + lightweight-charts v5 + react-i18next
    ├── src/
    │   ├── App.tsx        # 7 views: market / global / futures / macro / compare / watchlist / stock
    │   ├── api.ts         # 單一 api 物件，generic get<T>() + ~30 endpoint wrappers
    │   ├── types.ts       # 10+ response types
    │   ├── i18n/          # index.ts（react-i18next init + toggleLang）+ zh.json / en.json（各 375 keys）
    │   ├── indicators.ts  # JS 端 RSI / KDJ / MACD（給副圖用）
    │   ├── indicators.test.ts  # vitest 10 個
    │   ├── lib/charts.ts  # toTime / isTradingHours / SESSION_MINUTES
    │   ├── hooks/useAsync.ts
    │   └── components/    # PriceChart（3 副圖 + 3 種 markers）/ MarketOverview /
    │                      # GlobalPanel / FuturesPanel / MacroPanel /
    │                      # CompareChart / WatchlistPanel /
    │                      # OutlookPanel / TechnicalPanel / ChipPanel /
    │                      # BacktestPanel（+下載 Pine）/ FundamentalsPanel /
    │                      # NewsPanel / ErrorBoundary（三層包覆，withTranslation HOC）
    └── tsconfig.json      # strict: true, noImplicitAny: false（漸進收緊）
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
| Path                           | 說明                                    |
| ------------------------------ | --------------------------------------- |
| `/stock/{symbol}/price`        | K線（?days&tf=1d\|3d\|5d\|1w\|3w\|1mo） |
| `/stock/{symbol}/intraday`     | Fugle 盤中分鐘K                         |
| `/stock/{symbol}/technical`    | 技術面（?timeframe=daily\|weekly）      |
| `/stock/{symbol}/outlook`      | 綜合研判                                |
| `/stock/{symbol}/chip`         | 籌碼面                                  |
| `/stock/{symbol}/backtest`     | 回測（?signal=...）                     |
| `/stock/{symbol}/pattern-scan` | 三線交纏型態掃描                        |
| `/stock/{symbol}/pine`         | Pine v5 匯出                            |
| `/stock/{symbol}/news`         | 新聞                                    |
| `/stock/{symbol}/fundamentals` | 基本面                                  |
| `/stock/search`                | 模糊搜尋                                |

### 大盤 / 掃描
| Path                           | 說明                           |
| ------------------------------ | ------------------------------ |
| `/market/index/live`           | 即時加權指數                   |
| `/market/index/intraday`       | TAIEX 盤中分鐘K                |
| `/market/money-flow`           | 法人資金 + 類股流向            |
| `/market/big-orders`           | 大單敲進                       |
| `/market/global`               | 全球新聞                       |
| `/market/pattern-scan`         | 三線交纏全市場掃描（當日快取） |
| `/market/weekly-w-bottom-scan` | 週線W底全市場掃描（當日快取）  |
| `/market/chip-scan`            | 三大法人連買掃描               |

### 期貨 / 總經
| Path                               | 說明                                 |
| ---------------------------------- | ------------------------------------ |
| `/market/commodity/{symbol}/price` | K線 + perf（TX/GC/CL/DXY/SPX/BTC…）  |
| `/market/futures/institutional`    | 期貨三大法人留倉                     |
| `/market/macro/economic`           | 美國 6 大經濟指標（需 FRED_API_KEY） |
| `/backtest/signals`                | 11 種訊號清單                        |
| `/admin/init-all`                  | 全台股歷史下載（背景）               |
| `/health`                          | 健康檢查                             |
啟動時 `main.py` 先 `load_dotenv()` 讀 repo-root `.env`（FUGLE / FRED / FINNHUB_API_KEY / SEC_CONTACT_EMAIL 自動載入），接著 daemon thread 跑 `daily_update()` 與股票清單/產業/TAIEX 5 年歷史補漏。

### 前端

```bash
cd web && npm run dev   # → http://localhost:5173
```

## API 路由總覽（52 個 HTTP + 1 WebSocket）

> 即時報價 WebSocket：`WS /ws/quotes` — 瀏覽器送 `{action:'subscribe', symbols:[≤5]}`，後端維護單一上游 Fugle 連線（aggregates channel）廣播多檔即時報價（自選清單 / movers 各列用；Fugle 免費上限 1 連線 / 5 訂閱）。

### 個股（台股 + 美股）
| Method | Path                                 | 說明                                                    |
| ------ | ------------------------------------ | ------------------------------------------------------- |
| GET    | `/stock/{symbol}`                    | 完整個股分析                                            |
| GET    | `/stock/{symbol}/price`              | 日 K（?days=120&tf=1d\|3d\|5d\|1w\|3w\|1mo）            |
| GET    | `/stock/{symbol}/intraday`           | Fugle 盤中分鐘 K（?timeframe=5）                        |
| GET    | `/stock/{symbol}/quote`              | 個股/ETF 即時報價快照（Fugle，含五檔；前端每 3 秒輪詢） |
| GET    | `/stock/{symbol}/technical`          | 技術面（?timeframe=daily\|weekly）                      |
| GET    | `/stock/{symbol}/outlook`            | 綜合研判                                                |
| GET    | `/stock/{symbol}/chip`               | 籌碼面                                                  |
| GET    | `/stock/{symbol}/backtest`           | 回測（?signal=ma_cross 等 11 種）                       |
| GET    | `/stock/{symbol}/pine`               | 輸出 Pine v5（含 best_four_buy/sell 完整模板）          |
| GET    | `/stock/{symbol}/news`               | 新聞列表                                                |
| GET    | `/stock/{symbol}/fundamentals`       | 基本面指標                                              |
| GET    | `/stock/{symbol}/monthly-revenue`    | 月營收 MoM/YoY（台股，FinMind）                         |
| GET    | `/stock/{symbol}/foreign-holding`    | 外資持股比率（台股，FinMind）                           |
| GET    | `/stock/{symbol}/margin-short`       | 融資融券餘額（台股，FinMind）                           |
| GET    | `/stock/{symbol}/securities-lending` | 借券餘額（台股，FinMind）                               |
| GET    | `/stock/{symbol}/earnings`           | 美股財報日曆（Finnhub）                                 |
| GET    | `/stock/{symbol}/recommendations`    | 美股分析師評等（Finnhub）                               |
| GET    | `/stock/{symbol}/insider`            | 美股內部人 Form 4（SEC EDGAR）                          |
| GET    | `/stock/search`                      | 代碼/中文名稱（台股）+ Finnhub /search（美股）模糊搜尋  |

### 大盤
| Method | Path                     | 說明                                           |
| ------ | ------------------------ | ---------------------------------------------- |
| GET    | `/market/institutional`  | 三大法人全市場排行                             |
| GET    | `/market/chip-scan`      | 全市場連買掃描                                 |
| GET    | `/market/index`          | 加權指數走勢                                   |
| GET    | `/market/index/live`     | 即時加權指數（TWSE MIS）                       |
| GET    | `/market/index/intraday` | TAIEX 盤中分鐘 K（Fugle IX0001）               |
| GET    | `/market/money-flow`     | 法人資金 + 盤後統計 + 類股流向                 |
| GET    | `/market/big-orders`     | 🔥 大單敲進（Fugle 逐筆）                       |
| GET    | `/market/movers`         | 全市場漲跌幅/成交值排行 + 漲跌家數（T+0 盤後） |
| GET    | `/market/global`         | 全球盤勢新聞（亞/歐/美 + 地緣，30 min 快取）   |

### 期貨 / 商品 / 總經
| Method | Path                               | 說明                                                                                  |
| ------ | ---------------------------------- | ------------------------------------------------------------------------------------- |
| GET    | `/market/commodities`              | 支援符號清單                                                                          |
| GET    | `/market/commodity/{symbol}/price` | 統一 K 線 + perf 摘要（TX/MTX/TE/TF/GC/CL/SI/HG/DXY/SPX/NDX/DJI/VIX/TNX/FVX/BTC/ETH） |
| GET    | `/market/futures/institutional`    | 期貨三大法人留倉                                                                      |
| GET    | `/market/futures/pcr`              | TXO Put/Call Ratio（成交量 + OI，FinMind）                                            |
| GET    | `/market/macro/economic`           | 美國 6 大經濟指標（CPI/PCE/GDP/NFP/UNRATE/Fed Funds，含 MoM/YoY），需 FRED_API_KEY    |
| GET    | `/market/macro/series/{series_id}` | 單一 FRED series 完整時間序列                                                         |
| GET    | `/market/macro/yield-curve`        | 美債殖利率曲線（FRED 多 series）                                                      |
| GET    | `/market/macro/calendar`           | 經濟事件日曆（Finnhub）                                                               |
| GET    | `/market/crypto/top`               | 加密前 10 大（CoinGecko）                                                             |
| GET    | `/market/crypto/global`            | 加密全球統計（總市值 + BTC/ETH dominance）                                            |
| GET    | `/market/fx`                       | USD 對 TWD/JPY/CNY/EUR/GBP/HKD/SGD 匯率                                               |

### 觀察清單
| Method | Path                          | 說明                        |
| ------ | ----------------------------- | --------------------------- |
| GET    | `/watchlist`                  | 取得自選股清單              |
| POST   | `/watchlist`                  | 新增自選股                  |
| DELETE | `/watchlist/{symbol}`         | 移除自選股                  |
| GET    | `/watchlist/conditions`       | 取得警示條件                |
| POST   | `/watchlist/conditions`       | 新增警示條件                |
| DELETE | `/watchlist/conditions/{cid}` | 移除警示條件                |
| GET    | `/watchlist/status`           | evaluate_all() 當前狀態評估 |

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
### 資料來源分工

| 資料                                            | 來源                                                                |                    費用                    |
| ----------------------------------------------- | ------------------------------------------------------------------- | :----------------------------------------: |
| 個股歷史日 K（10 年）                           | FinMind（首選，單一請求）／TWSE STOCK_DAY·TPEx tradingStock（備援） |                    免費                    |
| 三大法人每日 bulk                               | TWSE T86 endpoint                                                   |                    免費                    |
| 加權指數歷史                                    | FinMind（5 年）／TWSE MI_5MINS_HIST（備援，按月）                   |                    免費                    |
| 股票清單                                        | TWSE STOCK_DAY_ALL／TPEx OpenAPI                                    |                    免費                    |
| 產業別                                          | FinMind TaiwanStockInfo                                             |                    免費                    |
| 基本面（EPS/PER/ROE）                           | FinMind 免費 API                                                    |               免費（有額度）               |
| 新聞                                            | Google News RSS（依公司名稱 / 全球關鍵字）                          |                    免費                    |
| 盤中分鐘 K + 大單                               | Fugle Market Data                                                   |        免費額度（需 API key，選用）        |
| 台股期貨日 K + 法人留倉                         | FinMind TaiwanFuturesDaily / InstitutionalInvestors                 |                    免費                    |
| TXO Put/Call Ratio                              | FinMind TaiwanOptionDaily                                           |                    免費                    |
| 進階台股基本面（月營收/外資持股/融資融券/借券） | FinMind 免費 dataset                                                |               免費（有額度）               |
| 國際商品 / 總經市場指標                         | Yahoo Finance v8 Chart API（GC=F/^GSPC/DX-Y.NYB/^TNX 等）           |                    免費                    |
| 美股日 K（10 年）                               | Yahoo Finance v8 Chart API → 寫進共用 daily_price                   |                    免費                    |
| 美股搜尋 / 財報日 / 分析師評等 / 經濟日曆       | Finnhub                                                             |    免費（需個人 API key，60 calls/min）    |
| 美股內部人交易（Form 4）                        | SEC EDGAR                                                           | 免費（需 SEC_CONTACT_EMAIL 帶 User-Agent） |
| 加密前 10 大 + 全球統計                         | CoinGecko public API                                                |       免費（無需 key，30 calls/min）       |
| 外匯匯率（USD 對 TWD/JPY/…）                    | exchangerate-api.com                                                |              免費（無需 key）              |
| 全市場漲跌幅/成交值排行                         | TWSE STOCK_DAY_ALL OpenAPI（T+0 盤後）                              |                    免費                    |
| 美國經濟（CPI/GDP/NFP/Fed Funds/失業率/PCE）    | FRED API（St. Louis Fed）                                           |     免費（需個人 API key，5 分鐘申請）     |
| 資料                                            | 來源                                                                |                    費用                    |
| ---------                                       | ------                                                              |              :--------------:              |
| 個股歷史日 K（10 年）                           | FinMind（首選，單一請求）／TWSE STOCK_DAY·TPEx tradingStock（備援） |                    免費                    |
| 三大法人每日 bulk                               | TWSE T86 endpoint                                                   |                    免費                    |
| 加權指數歷史                                    | FinMind（5 年）／TWSE MI_5MINS_HIST（備援，按月）                   |                    免費                    |
| 股票清單                                        | TWSE STOCK_DAY_ALL／TPEx OpenAPI                                    |                    免費                    |
| 產業別                                          | FinMind TaiwanStockInfo                                             |                    免費                    |
| 基本面（EPS/PER/ROE）                           | FinMind 免費 API                                                    |               免費（有額度）               |
| 新聞                                            | Google News RSS（依公司名稱 / 全球關鍵字）                          |                    免費                    |
| 盤中分鐘 K + 大單                               | Fugle Market Data                                                   |        免費額度（需 API key，選用）        |
| 台股期貨日 K + 法人留倉                         | FinMind TaiwanFuturesDaily / InstitutionalInvestors                 |                    免費                    |
| TXO Put/Call Ratio                              | FinMind TaiwanOptionDaily                                           |                    免費                    |
| 進階台股基本面（月營收/外資持股/融資融券/借券） | FinMind 免費 dataset                                                |               免費（有額度）               |
| 全市場估值（PER/PBR/殖利率）+ 融資融券最新      | **TWSE OpenAPI**（官方，免 key、**免額度**；僅上市、EOD 快照）      |                    免費                    |
| 國際商品 / 總經市場指標                         | Yahoo Finance v8 Chart API（GC=F/^GSPC/DX-Y.NYB/^TNX 等）           |                    免費                    |
| 美股日 K（10 年）                               | Yahoo Finance v8 Chart API → 寫進共用 daily_price                   |                    免費                    |
| 美股搜尋 / 財報日 / 分析師評等 / 經濟日曆       | Finnhub                                                             |    免費（需個人 API key，60 calls/min）    |
| 美股內部人交易（Form 4）                        | SEC EDGAR                                                           | 免費（需 SEC_CONTACT_EMAIL 帶 User-Agent） |
| 加密前 10 大 + 全球統計                         | CoinGecko public API                                                |       免費（無需 key，30 calls/min）       |
| 外匯匯率（USD 對 TWD/JPY/…）                    | exchangerate-api.com                                                |              免費（無需 key）              |
| 全市場漲跌幅/成交值排行                         | TWSE STOCK_DAY_ALL OpenAPI（T+0 盤後）                              |                    免費                    |
| 美國經濟（CPI/GDP/NFP/Fed Funds/失業率/PCE）    | FRED API（St. Louis Fed）                                           |     免費（需個人 API key，5 分鐘申請）     |

### SQLite 表格

- `daily_price` — 個股 OHLCV，10 年（**台股 + 美股共用**，us_stocks.py 把 Yahoo 資料寫進同一張表）
- `institutional` — 三大法人，10 年
- `index_data` — 加權／櫃買指數
- `fundamentals` — 財報，季頻
- `news_cache` — 30 天
- `sync_log` — 各股最後同步時間
- `stock_names` / `stock_industry` — 清單 + 產業
- `watchlist` — 觀察清單自選股（watchlist.py）
- `alert_conditions` — 警示條件（watchlist.py）
- 期貨 / 商品 / 加密 / 匯率 / movers / SEC / Finnhub / 進階基本面**不寫 DB**（各模組用 in-memory cache）

### 資料下載策略（三層）

1. **每日 bulk（自動）** — server 啟動時 daemon thread 跑 daily_update（三大法人 + 指數近 6 個月補漏）
2. **on-demand（個股）** — 第一次查詢觸發 10 年歷史下載；首選 FinMind 單一請求（1-2 秒）
3. **`/admin/init-all`（選用）** — 全台股 ~2500 支歷史下載，低基期選股用

## 分析模組

### technical.py
- `daily` / `weekly` 兩種時間框架，週 K 由日 K resample（W-FRI）
- 指標：MA(5/10/20/60/120/240)、RSI(14)、MACD(12/26/9)、KD(9/3/3)、布林(20,2σ)
- 形態：黃金/死亡交叉、KD 低/高檔、MACD 轉正/負、RSI 超買賣、布林收縮突破

### chip.py
- `analyze(symbol)`、`scan_bulk(min_foreign_days=3)`、`market_money_flow()`、`sector_money_flow()`

### backtest.py
- 掃 10 年歷史，統計後續 5/10/20/60 天勝率與平均報酬
- 11 種訊號（見上），不含交易成本
- 樣本 < 10 → `low_sample_warning: true`

### outlook.py
- 加權技術+籌碼+回測 → 偏多/中性/偏空 + 預期區間

### commodities.py（新）
- FinMind 台股期貨：自動取「同日最大成交量合約 = 近月連續價」
- Yahoo Finance 國際商品 + 總經市場面指標；日 K previousClose 取 `meta.previousClose`（非 `chartPreviousClose`）
- 已移除失效的 XAUUSD spot forex symbol（Yahoo 2025/26 起 404，GC=F 已涵蓋黃金）→ 期貨選單 8 個符號（TX/MTX/TE/TF/GC/CL/SI/HG）
- 5 min in-memory cache（key = symbol:days）
- `perf_summary()` 算 1d/5d/1m/6m/YTD/1y/5y/10y 累積報酬

### fred.py
- 美國經濟基本面指標：CPIAUCSL（CPI）/ PCE / GDP / PAYEMS（非農）/ UNRATE（失業）/ DFF（Fed Funds）
- 沒設 `FRED_API_KEY` 時所有函式回空 → 前端顯示「需設定」link 到申請頁
- `summary()` 一次回 6 個指標的「最新值 + MoM + YoY」，給 MacroPanel 一次抓
- 殖利率曲線（多 series 組合）
- 1 小時 in-memory cache（FRED 月頻資料一天才更新一次）

### crypto.py（新）
- CoinGecko public API（免費，30 calls/min，無需 key）
- `top_markets(limit=10)` 前 10 大幣（市值排序 + 24h 漲跌）、`global_stats()` 全球統計（總市值、BTC/ETH dominance、活躍幣種數）
- 5 min in-memory cache

### fx.py（新）
- exchangerate-api.com（免費，無需 key）
- `latest_rates(base="USD")` → USD 對 TWD/JPY/CNY/EUR/GBP/HKD/SGD；台股最看 USD/TWD（出口股 EPS 敏感）
- 1 小時 in-memory cache

### market_movers.py（新）
- 全市場漲跌幅/成交值排行 + 漲跌家數，直接抓 TWSE STOCK_DAY_ALL OpenAPI（+ TPEx）原始 endpoint
- 資料是 **T+0（盤後 ~16:00 才有）**，盤中查到的是「昨日資料」
- 5 min in-memory cache

### sec.py（新）
- SEC EDGAR 整合，免費**無需 API key**，但需在 User-Agent 帶真實聯絡 email（讀 `SEC_CONTACT_EMAIL`，否則 data.sec.gov 可能限流 / 403）
- `insider_transactions(ticker)` 回 Form 4（內部人交易）**filing metadata + SEC 連結**（非解析後的股數/價格），`get_cik()` ticker→CIK 對照表（lazy 載入一次，~10000 entries）
- 12 小時 in-memory cache

### finnhub.py（新）
- 經濟事件日曆 / 美股財報日 / 分析師評等 / 內線 / IPO，需 `FINNHUB_API_KEY`（免費 60 calls/min）
- 沒設 key → `available()` 回 False，前端顯示「需設定」
- 1 小時 in-memory cache

### taifex.py（新）
- TXO Put/Call Ratio：PCR(volume) = put/call 成交量、PCR(OI) = put/call 未平倉，附情緒區間判讀（> 1.2 過度恐慌反向看多、< 0.7 過度樂觀）
- 資料源 FinMind TaiwanOptionDaily，30 min in-memory cache

### us_stocks.py（新）
- 美股支援：`is_us_stock()` ticker 偵測（純字母 1-5 字）、`_fetch_yahoo_us()` 抓 Yahoo v8 Chart API → 寫進**共用 `daily_price` schema**、`search_us()` 走 Finnhub /search
- 寫進 daily_price 後，現有 `technical.analyze` / `backtest` / `outlook` 全部「自動相容」美股
- 由 data_fetcher 在 on-demand / search 路徑 inline import（避免循環 import）

### fundamentals_extra.py（新）
- 進階台股基本面（全走 FinMind 免費 dataset）：`monthly_revenue()` 月營收 MoM/YoY（含營收訊號）、`foreign_shareholding()` 外資持股比率、`margin_short()` 融資融券餘額、`securities_lending()` 借券餘額
- 1 小時 in-memory cache

### watchlist.py（新）
- 觀察清單 CRUD（`list_watchlist` / `add_watchlist` / `remove_watchlist`）+ 警示條件 CRUD
- `evaluate_all()` 跑當前所有條件，回 `[triggered, current_value, threshold]`
- 後端兩張新表 `watchlist` / `alert_conditions`

### pine_exporter.py
- `TEMPLATES` 字典：11 個訊號各有 Pine v5 模板
- 回測 20 天平均報酬自動填入 `profit target`，停損 = 預期獲利 × 60%
- GENERIC_TEMPLATE 是 fallback（理論上 11 個訊號都有專屬模板，跑不到）

### data_fetcher.py
- `fetch_finmind_price_history()` — 一次抓完整 10 年
- `fetch_stock_history()` — TWSE/TPEx 月度爬蟲備援
- `fetch_taiex_history(months)` — TWSE MI_5MINS_HIST 按月，`row[4]` 為收盤價
- `fetch_taiex_finmind(years=5)` — FinMind TAIEX 一次補滿
- `fetch_daily_institutional_bulk()` — TWSE T86，`foreign = row[4]+row[7]`、`dealer = row[11]`
- `fetch_market_breadth()` — MI_INDEX MS（漲跌家數/成交金額）
- `fetch_live_index()` — async TWSE MIS
- `resample_ohlc(df, tf)` — 1d/3d/5d/1w/3w/1mo
- on-demand / search 路徑判斷美股 ticker → 轉交 `us_stocks`（inline import 避免循環）

### fugle.py
- `intraday_candles()` — 並行抓 candles + quote（return_exceptions=True），quote 失敗仍回 candles
- `quote()` — 個股/ETF 即時報價快照（`/intraday/quote`，含五檔買賣價量）；`_shape_quote()` 純函式整形便於測試。ETF 與一般個股同一組 endpoint，無特殊處理
- `scan_big_orders()` — async parallel 大單偵測，排除 serial 99999999 + hm in (900, 1325)
- 所有失敗 path 都 `log.warning(...)` 含 HTTP 狀態碼 + body

### fugle_ws.py（新）
- 多檔即時報價 hub：後端維護「單一」上游 Fugle WS（aggregates channel），訂閱目前需要的 ≤5 檔（免費方案上限 1 連線 / 5 訂閱），廣播給所有瀏覽器端 `/ws/quotes` client。同一時間通常只有一個 view 在跑，union 多半 ≤5；超過 5 截斷並 log（不靜默）
- subscribe 帶 symbol、unsubscribe 認 Fugle 回的訂閱 **id**；`snapshot`（訂閱當下）與 `data`（盤中更新）兩種 event 同樣整形（重用 `fugle._shape_quote`，前後端報價結構一致）；新訂閱時用 REST 補一筆最後一盤，盤後/週末也先有畫面。美股 ticker（字母開頭）自動過濾不佔額度
- 前端 `useLiveQuotes(symbols)` hook：MarketOverview 成交額 Top 5 + WatchlistPanel 前 5 檔各列即時價＋漲跌（綠點脈動）

## 前端架構

### View 切換（7 個）
1. **大盤**（預設）— MarketOverview：即時指數 + 法人 + 類股 + 大單 + movers 排行
2. **全球** — GlobalPanel：亞/歐/美 + 地緣政治 4 分類新聞
3. **期貨** — FuturesPanel：8 個符號選單 + perf 表 + 法人留倉 + PCR
4. **總經** — MacroPanel：5 層 macro 框架 + 殖利率曲線 + 加密 + 匯率 + 經濟日曆
5. **比較** — CompareChart：多檔個股/指數疊圖比較
6. **觀察清單** — WatchlistPanel：自選股 + 警示條件 + 當前狀態
7. **個股**（symbol 設定後，台股 + 美股）— 即時報價（Fugle 五檔，每 3 秒）+ 7 時間框架 K 線 + 6 個 tab（綜合研判/技術/籌碼/回測/基本面/新聞）

### i18n（react-i18next）
- 兩本字典 `web/src/i18n/zh.json`（zh-TW，預設）+ `en.json`，各 375 keys（zh/en parity）
- localStorage 持久化語言切換（key = `lang`），`toggleLang()` 同步 `document.documentElement.lang`（zh → `zh-Hant`）
- 全部 14 個 component + App.tsx 透過 `useTranslation()` / `t()` 接線；ErrorBoundary 走 `withTranslation` HOC（class component）

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
| 來源              | 頻率  |
| ----------------- | ----- |
| TWSE MIS 即時指數 | 1 秒  |
| Fugle 大單敲進    | 60 秒 |

## 注意事項

- `stocks.db` / `pine_output/` 已 gitignore
- FinMind 免費 API 有日額度（超額退 402，自動切 TWSE 備援）
- `stocks.db` 和 `pine_output/` 已加入 `.gitignore`，勿手動 commit
- `.env`（gitignored，只 commit `.env.example`）收 3 把 key + 1 個聯絡 email：`FUGLE_API_KEY` / `FRED_API_KEY` / `FINNHUB_API_KEY` / `SEC_CONTACT_EMAIL`；server 啟動 `load_dotenv()` 自動載入（依賴 `python-dotenv`，已列入 requirements.txt）。四者皆選用，沒設時對應功能 graceful degrade（前端顯示「需設定」）
- TWSE/TPEx 爬蟲 1.2 秒/req（`REQUEST_DELAY`）
- FinMind 免費 API 有日額度
- 技術指標自寫 `indicators.py`（避開 pandas-ta + numpy 2 + Python 3.14 不相容問題）
- TPEx 憑證鏈缺 SKI → 放寬 OpenSSL3 `VERIFY_X509_STRICT`（仍完整驗證）
- DB / pine_output 路徑可用 `TAIWAN_STOCK_DB` / `TAIWAN_STOCK_PINE_DIR` 覆寫
- lightweight-charts v5：`addSeries(SeriesClass, opts, paneIndex)`、`createSeriesMarkers(series, markers)`
- 資料僅供個人研究

## 測試

```powershell
.\.venv\Scripts\python.exe -m pytest server/tests -v
cd web; npm test
```
```bash
./.venv/bin/pip install -r requirements-dev.txt
./.venv/bin/python -m pytest server/tests -v   # 76 tests
cd web && npm test                              # vitest 10 tests
```

`pytest`：backtest masks/pivot、resample 各 tf、fugle 大單過濾 + quote 整形、commodities、fred
`vitest`：RSI/KDJ 數學一致性

## 實作進度

- [x] Phase 1：資料層（SQLite + TWSE/TPEx 爬蟲 + FastAPI 骨架）
- [x] Phase 2：分析模組（technical / chip / backtest / news_fundamental / pine_exporter）
- [x] Phase 3：FastAPI 路由完整驗收
- [x] Phase 4：CLI Skill（SKILL.md + main.py 意圖解析）
- [x] Phase 5：React Web App（K線 + 各分析面板）
- [x] Phase 6：大盤即時面板（live index + big orders + money flow + 類股）
- [x] Phase 7：jsx → tsx 全面遷移、TS strict 收緊、共用 hooks/lib 抽出
- [x] Phase 8：期貨 + 國際商品 + 總經 + 全球新聞 + RSI/KDJ 副圖 + 金叉死叉 markers
- [x] Phase 9：測試（pytest 26 + vitest 10）+ ErrorBoundary + 多層 cache
- [x] Phase 10：美股支援（Yahoo → 共用 daily_price）+ 6 大整合（crypto / FX / movers / SEC Form 4 / Finnhub / TXO PCR）+ 進階台股基本面 + 觀察清單（2 新表）+ 比較視圖 + 全面 i18n（zh/en 364 keys）+ .env 自動載入（python-dotenv）+ pytest 52 + 48 routes
- [x] Phase 11：Fugle 個股/ETF 即時報價（含五檔，每 3 秒輪詢 + 交易時段 gate）+ SEC User-Agent 改 env + market_movers 去重 + 後端字串 i18n（technical 訊號 / outlook 研判因子+免責，英文模式 100% 乾淨，後端發 code/key+params）+ pytest 55 + 49 routes + 364 i18n keys
- [x] Phase 12：多檔即時報價 WebSocket streamer（後端單一 Fugle 連線 hub + aggregates → `WS /ws/quotes` 廣播；自選清單 / movers 成交額 Top 5 各列即時價＋漲跌，免費上限 5 檔）+ websockets dep + pytest 59 + 365 i18n keys
- [x] Phase 13：TWSE OpenAPI 官方整合（免 key/免額度）— `twse_openapi.py` 全市場估值篩選 BWIBBU（低本益比/高殖利率 → `/market/valuation` + 大盤估值面板）+ 個股 PER/PBR/殖利率（`/stock/{symbol}/valuation`）+ margin-short 附 TWSE 官方最新；pytest 71 + 51 routes + 369 i18n keys
- [x] Phase 14：偏多候選多因子掃描 `screen.py`（動能+籌碼連買+技術+估值收斂，輕量訊號免回測）→ `GET /market/screen`（可調濾網，例如排除 RSI 超買找較早設定）+ 大盤頁「偏多候選」面板；pytest 76 + 52 routes + 375 i18n keys。研究訊號，非投資建議
- [x] Phase 15：資料新鮮度修復 — T86 三大法人改 `/rwd/zh/fund/T86`（TWSE 棄用舊 `/fund/T86`，回空）；個股 `daily_price` 加「每日節流增量 top-up」（`_topup_recent_if_stale`，修掉「下載一次後就停在當天」的 staleness，連帶 technical/outlook 同步更新）
