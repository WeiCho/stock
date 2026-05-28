# Taiwan Stock Skill — CLAUDE.md

## 專案概述

本地台股 + 國際商品 + 期貨 + 總體經濟分析工具，提供 CLI（Claude Code skill）與 React Web App 兩種介面，共用 FastAPI 後端。涵蓋：

- **個股**：技術面（含 RSI / KDJ 副圖、MA/MACD/KDJ 金叉死叉 markers）、籌碼面（三大法人）、10 年回測（11 種訊號含 twstock 四大買賣點）、Pine Script 一鍵下載、新聞、基本面、綜合研判
- **大盤**：即時加權指數（每秒輪詢 + 交易時段 gate）、法人資金動向、類股流向、🔥 大單敲進（Fugle 逐筆）
- **期貨**：台股期貨（TX/MTX/TE/TF）+ 國際商品（黃金/白銀/銅/原油）+ 三大法人留倉
- **總經 Macro**：5 層分析框架（總體 → 資金流 → 市場價格 → 籌碼情緒 → 地緣政治），含 DXY / VIX / 公債利率 / SPX / NASDAQ / BTC / ETH
- **全球新聞**：亞 / 歐 / 美 + 地緣政治關鍵字（Google News，後端 30 min 快取）

## 目錄結構

```
taiwan-stock/
├── CLAUDE.md / README.md / SKILL.md
├── main.py                # CLI 入口（自然語言意圖解析）
├── start.sh               # 一鍵啟動（PID 追蹤 + 乾淨 shutdown）
├── .env                   # FUGLE_API_KEY（gitignored）/ .env.example 模板
├── requirements.txt       # 正式 runtime deps
├── requirements-dev.txt   # 測試 deps（pytest）
├── stocks.db              # SQLite（自動建立，勿 commit）
├── pine_output/           # 生成的 .pine 檔（勿 commit）
├── server/                # FastAPI 後端
│   ├── main.py            # 27 routes，top-level imports（無 inline）
│   ├── db.py              # SQLAlchemy + SQLite init
│   ├── data_fetcher.py    # 三層下載策略（FinMind 主力 + TWSE/TPEx 備援）
│   ├── indicators.py      # 自寫純 pandas SMA/RSI/MACD/KD/BBands
│   ├── technical.py       # 形態偵測
│   ├── chip.py            # 三大法人 + 類股資金流向
│   ├── backtest.py        # 11 種訊號回測（含 twstock 四大買賣點）
│   ├── outlook.py         # 綜合研判（多空權重）
│   ├── news_fundamental.py# 個股新聞 + 全球新聞 + 基本面
│   ├── fugle.py           # 盤中即時 + 大單偵測（需 FUGLE_API_KEY）
│   ├── commodities.py     # 期貨 + 國際商品 + 總經市場面（FinMind + Yahoo Finance）
│   ├── fred.py            # 美國經濟指標（CPI/GDP/NFP/失業率/Fed Funds，需 FRED_API_KEY）
│   ├── pine_exporter.py   # 11 個訊號的 Pine v5 模板
│   └── tests/             # pytest 26 個（backtest masks / resample / fugle filter）
└── web/                   # React 19 + Vite + TS strict + Tailwind + lightweight-charts v5
    ├── src/
    │   ├── App.tsx        # 5 views: market / global / futures / macro / stock
    │   ├── api.ts         # generic get<T>() + 21 endpoint wrappers
    │   ├── types.ts       # 10+ response types
    │   ├── indicators.ts  # JS 端 RSI / KDJ / MACD（給副圖用）
    │   ├── indicators.test.ts  # vitest 10 個
    │   ├── lib/charts.ts  # toTime / isTradingHours / SESSION_MINUTES
    │   ├── hooks/useAsync.ts
    │   └── components/    # PriceChart（3 副圖 + 3 種 markers）/ MarketOverview /
    │                      # GlobalPanel / FuturesPanel / MacroPanel /
    │                      # OutlookPanel / TechnicalPanel / ChipPanel /
    │                      # BacktestPanel（+下載 Pine）/ FundamentalsPanel /
    │                      # NewsPanel / ErrorBoundary（三層包覆）
    └── tsconfig.json      # strict: true, noImplicitAny: false（漸進收緊）
```

## 啟動方式

### 一鍵啟動（推薦）

```bash
./start.sh
```

PID 追蹤 + 乾淨 shutdown。首次自動建立 venv 與 npm install。

### 後端（手動）

```bash
source .venv/bin/activate
PYTHONPATH=server uvicorn server.main:app --host 0.0.0.0 --port 8000
```

啟動時 daemon thread 跑 `daily_update()` 與股票清單/產業/TAIEX 5 年歷史補漏。

### 前端

```bash
cd web && npm run dev   # → http://localhost:5173
```

## API 路由總覽（24 個）

### 個股
| Method | Path | 說明 |
|--------|------|------|
| GET | `/stock/{symbol}` | 完整個股分析 |
| GET | `/stock/{symbol}/price` | 日 K（?days=120&tf=1d\|3d\|5d\|1w\|3w\|1mo）|
| GET | `/stock/{symbol}/intraday` | Fugle 盤中分鐘 K（?timeframe=5）|
| GET | `/stock/{symbol}/technical` | 技術面（?timeframe=daily\|weekly）|
| GET | `/stock/{symbol}/outlook` | 綜合研判 |
| GET | `/stock/{symbol}/chip` | 籌碼面 |
| GET | `/stock/{symbol}/backtest` | 回測（?signal=ma_cross 等 11 種）|
| GET | `/stock/{symbol}/pine` | 輸出 Pine v5（含 best_four_buy/sell 完整模板）|
| GET | `/stock/{symbol}/news` | 新聞列表 |
| GET | `/stock/{symbol}/fundamentals` | 基本面指標 |
| GET | `/stock/search` | 代碼或中文名稱模糊搜尋 |

### 大盤
| Method | Path | 說明 |
|--------|------|------|
| GET | `/market/institutional` | 三大法人全市場排行 |
| GET | `/market/chip-scan` | 全市場連買掃描 |
| GET | `/market/index` | 加權指數走勢 |
| GET | `/market/index/live` | 即時加權指數（TWSE MIS）|
| GET | `/market/index/intraday` | TAIEX 盤中分鐘 K（Fugle IX0001）|
| GET | `/market/money-flow` | 法人資金 + 盤後統計 + 類股流向 |
| GET | `/market/big-orders` | 🔥 大單敲進（Fugle 逐筆）|
| GET | `/market/global` | 全球盤勢新聞（亞/歐/美 + 地緣，30 min 快取）|

### 期貨 / 商品 / 總經
| Method | Path | 說明 |
|--------|------|------|
| GET | `/market/commodities` | 支援符號清單 |
| GET | `/market/commodity/{symbol}/price` | 統一 K 線 + perf 摘要（TX/MTX/TE/TF/GC/CL/SI/HG/DXY/SPX/NDX/DJI/VIX/TNX/FVX/BTC/ETH）|
| GET | `/market/futures/institutional` | 期貨三大法人留倉 |
| GET | `/market/macro/economic` | 美國 6 大經濟指標（CPI/PCE/GDP/NFP/UNRATE/Fed Funds，含 MoM/YoY），需 FRED_API_KEY |
| GET | `/market/macro/series/{series_id}` | 單一 FRED series 完整時間序列 |

### 其他
| Method | Path | 說明 |
|--------|------|------|
| GET | `/backtest/signals` | 11 種訊號清單 |
| POST | `/admin/init-all` | 全台股歷史下載（背景，1-2 小時）|
| GET | `/health` | 健康檢查 |

## CLI Skill 用法

```bash
source .venv/bin/activate
python main.py "分析台積電"
python main.py "2330 回測黃金交叉"
python main.py "幫我出台積電的 Pine Script"
python main.py "今天外資買超前五名"
python main.py "找外資連買 3 天以上的股票"
python main.py "今天加權指數"
```

## 11 種回測訊號

```
ma_cross         MA20 × MA60 黃金交叉（日K）
ma_death         MA20 × MA60 死亡交叉（日K）
weekly_ma_cross  週MA20 × 週MA52 黃金交叉
kd_low_cross     KD 低檔黃金交叉（K<30）
kd_high_cross    KD 高檔死亡交叉（K>70）
macd_turn_pos    MACD 柱狀圖由負轉正
macd_turn_neg    MACD 柱狀圖由正轉負
rsi_oversold     RSI 超賣（<30）
rsi_overbought   RSI 超買（>70）
best_four_buy    四大買點（量價/均線 + 負乖離反彈，twstock）
best_four_sell   四大賣點（量價/均線 + 正乖離反轉，twstock）
```

每個訊號都有對應的 Pine v5 模板（`pine_exporter.TEMPLATES`），前端「下載 Pine」按鈕一鍵存檔。

## 資料架構

### 資料來源分工

| 資料 | 來源 | 費用 |
|---------|------|:--------------:|
| 個股歷史日 K（10 年）| FinMind（首選，單一請求）／TWSE STOCK_DAY·TPEx tradingStock（備援）| 免費 |
| 三大法人每日 bulk | TWSE T86 endpoint | 免費 |
| 加權指數歷史 | FinMind（5 年）／TWSE MI_5MINS_HIST（備援，按月）| 免費 |
| 股票清單 | TWSE STOCK_DAY_ALL／TPEx OpenAPI | 免費 |
| 產業別 | FinMind TaiwanStockInfo | 免費 |
| 基本面（EPS/PER/ROE）| FinMind 免費 API | 免費（有額度）|
| 新聞 | Google News RSS（依公司名稱 / 全球關鍵字）| 免費 |
| 盤中分鐘 K + 大單 | Fugle Market Data | 免費額度（需 API key，選用）|
| 台股期貨日 K + 法人留倉 | FinMind TaiwanFuturesDaily / InstitutionalInvestors | 免費 |
| 國際商品 / 總經市場指標 | Yahoo Finance v8 Chart API（GC=F/^GSPC/DX-Y.NYB/^TNX 等）| 免費 |
| 美國經濟（CPI/GDP/NFP/Fed Funds/失業率/PCE）| FRED API（St. Louis Fed）| 免費（需個人 API key，5 分鐘申請）|

### SQLite 表格

- `daily_price` — 個股 OHLCV，10 年
- `institutional` — 三大法人，10 年
- `index_data` — 加權／櫃買指數
- `fundamentals` — 財報，季頻
- `news_cache` — 30 天
- `sync_log` — 各股最後同步時間
- `stock_names` / `stock_industry` — 清單 + 產業
- 期貨 / 商品**不寫 DB**（commodities 用 5 min in-memory cache）

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
- Yahoo Finance 國際商品 + 總經市場面指標
- 5 min in-memory cache（key = symbol:days）
- `perf_summary()` 算 1d/5d/1m/6m/YTD/1y/5y/10y 累積報酬

### fred.py（新）
- 美國經濟基本面指標：CPIAUCSL（CPI）/ PCE / GDP / PAYEMS（非農）/ UNRATE（失業）/ DFF（Fed Funds）
- 沒設 `FRED_API_KEY` 時所有函式回空 → 前端顯示「需設定」link 到申請頁
- `summary()` 一次回 6 個指標的「最新值 + MoM + YoY」，給 MacroPanel 一次抓
- 1 小時 in-memory cache（FRED 月頻資料一天才更新一次）

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

### fugle.py
- `intraday_candles()` — 並行抓 candles + quote（return_exceptions=True），quote 失敗仍回 candles
- `scan_big_orders()` — async parallel 大單偵測，排除 serial 99999999 + hm in (900, 1325)
- 所有失敗 path 都 `log.warning(...)` 含 HTTP 狀態碼 + body

## 前端架構

### View 切換（5 個）
1. **大盤**（預設）— MarketOverview：即時指數 + 法人 + 類股 + 大單
2. **全球** — GlobalPanel：亞/歐/美 + 地緣政治 4 分類新聞
3. **期貨** — FuturesPanel：9 個符號選單 + perf 表 + 法人留倉
4. **總經** — MacroPanel：5 層 macro 框架
5. **個股**（symbol 設定後）— 7 時間框架 K 線 + 6 個 tab（綜合研判/技術/籌碼/回測/基本面/新聞）

### PriceChart（K 線元件）
- 7 種時間框架：當日 / 日K / 3日 / 5日 / 週K / 3週 / 月K
- **盤中**：BaselineSeries（昨收為基準上紅下綠雙色漸層 + 均價線 + 09:00-13:30 rightOffset 補滿）
- **非盤中**：CandlestickSeries + MA 疊圖 + **3 個副圖**（MACD 偏多偏空 + RSI 超買賣 + KDJ 進場時機）
- **3 種 markers**：MA20/MA60 紅藍箭頭、MACD 橙色圓點、KDJ 黃色方塊（K<30 或 K>70 才標記）
- ErrorBoundary 三層包覆（大盤 / K線 / Tab），單一錯誤不會白屏

### 即時策略（盤中 09:00–13:30 台北時間）

| 來源 | 頻率 | gate |
|---|---|---|
| TWSE MIS 即時指數 | **1 秒** | `isTradingHours()` |
| Fugle 大單敲進 | 60 秒 | 同上 |
| Fugle 盤中分鐘 K | 用戶切「當日」時 fetch | — |
| 法人 / 漲跌家數 | 盤後 | — |

## 注意事項

- `stocks.db` 和 `pine_output/` 已加入 `.gitignore`，勿手動 commit
- `.env` 收 `FUGLE_API_KEY`（gitignored），只 commit `.env.example`
- TWSE/TPEx 爬蟲 1.2 秒/req（`REQUEST_DELAY`）
- FinMind 免費 API 有日額度
- 技術指標自寫 `indicators.py`（避開 pandas-ta + numpy 2 + Python 3.14 不相容問題）
- TPEx 憑證鏈缺 SKI → 放寬 OpenSSL3 `VERIFY_X509_STRICT`（仍完整驗證）
- DB / pine_output 路徑可用 `TAIWAN_STOCK_DB` / `TAIWAN_STOCK_PINE_DIR` 覆寫
- lightweight-charts v5：`addSeries(SeriesClass, opts, paneIndex)`、`createSeriesMarkers(series, markers)`
- 資料僅供個人研究，不得用於自動下單

## 測試

```bash
./.venv/bin/pip install -r requirements-dev.txt
./.venv/bin/python -m pytest server/tests -v   # 26 tests
cd web && npm test                              # vitest 10 tests
```

`pytest`：backtest masks/pivot、resample 各 tf、fugle 大單過濾
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
