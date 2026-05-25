# Taiwan Stock Skill — CLAUDE.md

## 專案概述

本地台股分析工具，提供 CLI（Claude Code skill）與 React Web App 兩種介面，共用 FastAPI 後端。分析台股技術面（日K/週K）、籌碼面（三大法人）、10 年回測勝率統計、新聞面與基本面，並可輸出 Pine Script 供 TradingView 驗證。

## 目錄結構

```
taiwan-stock/
├── CLAUDE.md              # 本文件
├── README.md              # 使用說明
├── SKILL.md               # Claude Code skill 觸發描述（待建）
├── main.py                # CLI 入口（待建）
├── requirements.txt       # Python 相依套件
├── stocks.db              # SQLite 資料庫（自動建立，勿 commit）
├── pine_output/           # 自動生成的 .pine 檔案
├── server/                # FastAPI 後端
│   ├── main.py            # API 路由（localhost:8000）
│   ├── db.py              # SQLAlchemy models + SQLite init
│   ├── data_fetcher.py    # TWSE/TPEx 爬蟲 + Fugle 即時
│   ├── technical.py       # 技術指標計算與形態偵測
│   ├── chip.py            # 三大法人籌碼分析
│   ├── backtest.py        # 訊號勝率回測引擎
│   ├── news_fundamental.py# 新聞 RSS + FinMind 基本面
│   └── pine_exporter.py   # Pine Script 模板生成
└── web/                   # React Web App（待建）
    └── src/
```

## 啟動方式

```bash
cd ~/.claude/skills/taiwan-stock
source .venv/bin/activate
PYTHONPATH=server uvicorn server.main:app --host 0.0.0.0 --port 8000
```

server 啟動時會自動執行每日更新（三大法人 bulk + 加權指數）。

## API 路由總覽

| Method | Path | 說明 |
|--------|------|------|
| GET | `/health` | 健康檢查 |
| GET | `/stock/{symbol}` | 完整個股分析 |
| GET | `/stock/{symbol}/technical` | 技術面（?timeframe=daily\|weekly） |
| GET | `/stock/{symbol}/chip` | 籌碼面 |
| GET | `/stock/{symbol}/backtest` | 回測（?signal=ma_cross） |
| GET | `/stock/{symbol}/pine` | 輸出 Pine Script |
| GET | `/stock/{symbol}/news` | 新聞列表 |
| GET | `/stock/{symbol}/fundamentals` | 基本面指標 |
| GET | `/market/institutional` | 三大法人全市場排行 |
| GET | `/market/chip-scan` | 全市場籌碼掃描（?min_foreign_days=3） |
| GET | `/market/index` | 加權指數走勢 |
| GET | `/backtest/signals` | 支援的回測訊號清單 |
| POST | `/admin/init-all` | 觸發全台股歷史資料下載（背景） |

## 資料架構

### 資料來源分工

| 資料類型 | 來源 | Fugle Token 消耗 |
|---------|------|:--------------:|
| 個股歷史日K（10年） | TWSE/TPEx HTTP 爬蟲 | 否 |
| 三大法人每日 bulk | TWSE T86 endpoint | 否 |
| 加權/櫃買指數歷史 | TWSE MI_INDEX endpoint | 否 |
| 基本面（EPS/PER/ROE） | FinMind 免費 API | 否 |
| 新聞 | 鉅亨網 RSS / Yahoo Finance RSS | 否 |
| 盤中即時報價 | Fugle Market Data API | **是**（保留用途） |

### SQLite 表格

- `daily_price` — 個股 OHLCV，保留 10 年
- `institutional` — 三大法人買賣超，保留 10 年
- `index_data` — 加權/櫃買指數
- `fundamentals` — 財報基本面，季頻
- `news_cache` — 新聞快取，保留 30 天
- `sync_log` — 各股最後同步時間，用於增量更新判斷

### 資料下載策略（三層）

1. **每日 bulk（自動）** — server 啟動時檢查，自動抓三大法人 + 指數
2. **on-demand（個股）** — 第一次查詢某支股票時觸發 10 年歷史下載
3. **`--init-all`（選用）** — POST `/admin/init-all` 觸發全市場歷史下載，低基期選股用

## 分析模組說明

### technical.py

- 支援 `daily`（日K）和 `weekly`（週K）兩種時間框架
- 週K 由日K 以 pandas `resample("W-FRI")` 聚合，不需額外 API
- 計算指標：MA(5/10/20/60/120/240)、RSI(14)、MACD(12/26/9)、KD(9/3/3)、布林通道(20,2σ)
- 形態偵測：黃金/死亡交叉、KD 低/高檔交叉、MACD 轉正/負、RSI 超買超賣背離、布林收縮突破

### chip.py

- `analyze(symbol)` — 個股三大法人，計算連買/賣天數、5/10/20 日累計
- `scan_bulk()` — 全市場掃描，支援 `min_foreign_days`、`min_trust_days` 條件過濾

### backtest.py

- 掃描 10 年歷史，統計後續 5/10/20/60 天勝率與平均報酬
- `SUPPORTED_SIGNALS` 字典定義所有支援的訊號（目前 9 種）
- 樣本數 < 10 次時 `low_sample_warning: true`
- 不含交易成本（手續費 0.1425% + 證交稅 0.3%）

### pine_exporter.py

- `TEMPLATES` 字典依訊號類型提供 Pine Script v5 模板
- 回測的平均報酬自動填入 `profit target`，停損設為預期獲利的 60%
- 輸出至 `pine_output/{symbol}_{signal}.pine`

## 注意事項

- `stocks.db` 和 `pine_output/` 不應 commit 到 git
- TWSE/TPEx 爬蟲每次請求間隔 1.2 秒（`REQUEST_DELAY`），避免被封鎖
- Fugle 免費額度每分鐘 30 次請求，歷史資料下載**不使用** Fugle
- FinMind 免費 API 有每日請求額度限制
- 資料僅供個人研究，不得用於自動下單

## 實作進度

- [x] Phase 1：資料層（SQLite schema + TWSE/TPEx 爬蟲 + FastAPI 骨架）
- [x] Phase 2：分析模組（technical / chip / backtest / news_fundamental / pine_exporter）
- [x] Phase 3：FastAPI 路由完整驗收
- [ ] Phase 4：CLI Skill（SKILL.md + main.py 意圖解析）
- [ ] Phase 5：React Web App（TradingView 圖表 + 各分析面板）
