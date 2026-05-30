# 台股分析工具

台股 + 國際商品 + 期貨 + 總體經濟分析工具，提供 React Web App 與 CLI 兩種介面，共用 FastAPI 後端。行情與籌碼來自 TWSE / TPEx 官方開放資料，基本面用 FinMind、新聞用 Google News，皆無需付費 API。

## 啟動

```powershell
.\start.ps1
```

首次執行自動建立 Python 虛擬環境、安裝前後端相依，接著同時啟動後端（`:8000`）與前端（`:5173`）並開啟瀏覽器。關閉視窗或 Ctrl+C 自動停止前後端。

手動分開啟動：

```powershell
# 後端
.\.venv\Scripts\python.exe -m uvicorn server.main:app --host 0.0.0.0 --port 8000

# 前端
cd web; npm run dev
```

### 選用 API Key（沒設也能跑大部分功能）

```powershell
cp .env.example .env   # 編輯填入
```

| Key | 用途 | 沒設會怎樣 |
|---|---|---|
| `FUGLE_API_KEY` | 盤中即時 K + 大單敲進逐筆偵測 | 大單面板隱藏；當日 K 線改用日線收盤 |
| `FRED_API_KEY` | 總經頁的 CPI / GDP / NFP / Fed Funds / 失業率 | 顯示「需設定」提示 |

申請連結：[Fugle](https://developer.fugle.tw/) / [FRED](https://fred.stlouisfed.org/docs/api/api_key.html)（皆免費）

## 功能

### 個股分析（7 個 Tab）

| Tab | 說明 |
|------|------|
| 綜合研判 | 結合技術面、籌碼面、回測的方向研判（偏多/中性/偏空）與預期區間 |
| 技術面 | 日K / 週K 均線（MA5~240）、RSI、MACD、KD、布林通道，自動偵測形態 |
| 籌碼面 | 外資 / 投信 / 自營商買賣超，連買天數，5/10/20 日累計 |
| 回測 | 11 種訊號的 10 年勝率統計，後續 5/10/20/60 天報酬率 |
| 型態 | 三線交纏帶量突破 MA60 型態掃描（見下方說明）|
| 基本面 | EPS、本益比、殖利率、營收月增 / 年增（FinMind）|
| 新聞 | Google News 依公司名稱彙整近 30 天 |

K 線圖支援 7 種時間框架（當日/日K/3日/5日/週K/3週/月K）+ MA 疊圖 + MA 金叉/死叉與 MACD 訊號 marker + 量能副圖。

### 型態：三線交纏帶量突破

兩層判斷邏輯分開：

**① 蓄勢條件（符合即提示可準備進場）**
- MA5/MA10/MA20 三線差距 < 收盤 3%（三線交纏）
- 收盤距 MA60 < 3%（蓄勢待突破）

**② 突破確認條件（回測勝率以此計算）**
- 帶量突破 MA60：昨日量 > 20 日均量 × 1.5
- 連續 2 日收盤站上 MA60（昨突破、今確認）
- 前天仍在 MA60 以下（突破剛發生）

觸發後回測統計（10 年歷史，冷卻期去重確保樣本獨立）：持有 5 / 10 / 20 日的勝率、平均報酬、最大獲利/虧損。

### 大盤 / 市場

| 功能 | 說明 |
|------|------|
| 加權指數 | 即時走勢（盤中每秒更新）+ 時間區間 當日/3日/1月/3月/6月/1年/5年 |
| 法人資金動向 | 外資 / 投信 / 自營商當日淨買賣超 + 買超/賣超排行 |
| 類股資金流向 | 依產業別彙總三大法人淨買賣超 |
| 大單敲進 | 盤中逐筆偵測法人買超股的大額成交（需 Fugle key，每 60 秒輪詢）|
| 籌碼掃描 | 外資 / 投信連買 N 天以上的股票清單 |
| 全球新聞 | 亞 / 歐 / 美 + 地緣政治關鍵字（Google News，後端 30 分鐘快取）|

### 期貨 / 國際商品

台指期 TX / 小台 MTX / 電子期 TE / 金融期 TF + 黃金 / 白銀 / 銅 / 原油，提供多時間框架 K 線與績效摘要（1d / 5d / 1m / 6m / YTD / 1y / 5y / 10y），以及期貨三大法人留倉口數。

### 總體經濟（Macro）

5 層分析框架：

| 層 | 內容 |
|---|---|
| 總體經濟 | 美 10Y/5Y 公債、DXY 美元指數、VIX 恐慌指數 |
| 資金流 | 利率 ↔ 資金流向解釋 |
| 市場價格 | SPX / NDX / DJI / 黃金 / 原油 / BTC / ETH |
| 籌碼情緒 | VIX 自動分級（> 30 恐慌、> 20 警戒、≤ 20 平靜）|
| 地緣政治 | 戰爭 / 制裁 / 石油供應鏈新聞 |

## 回測訊號（11 種）

| 訊號代碼 | 說明 |
|---------|------|
| `ma_cross` | MA20 × MA60 黃金交叉（日K）|
| `ma_death` | MA20 × MA60 死亡交叉（日K）|
| `weekly_ma_cross` | 週MA20 × 週MA52 黃金交叉 |
| `kd_low_cross` | KD 低檔黃金交叉（K<30）|
| `kd_high_cross` | KD 高檔死亡交叉（K>70）|
| `macd_turn_pos` | MACD 柱狀圖由負轉正 |
| `macd_turn_neg` | MACD 柱狀圖由正轉負 |
| `rsi_oversold` | RSI 超賣（<30）|
| `rsi_overbought` | RSI 超買（>70）|
| `best_four_buy` | 四大買點（量價/均線 + 負乖離反彈）|
| `best_four_sell` | 四大賣點（量價/均線 + 正乖離反轉）|

每個訊號有對應 Pine v5 模板，前端「下載 Pine」按鈕一鍵存檔到 TradingView。

## 資料來源

| 資料 | 來源 |
|------|------|
| 個股歷史日K（10年）| FinMind（首選）／ TWSE·TPEx 爬蟲（備援）|
| 三大法人每日 | TWSE T86 endpoint |
| 加權指數歷史 | FinMind（5年）／ TWSE MI_5MINS_HIST（備援）|
| 即時加權指數 | TWSE MIS |
| 股票清單 / 產業別 | TWSE STOCK_DAY_ALL / FinMind TaiwanStockInfo |
| 基本面 | FinMind 免費 API（有額度限制）|
| 新聞 | Google News RSS |
| 盤中逐筆 / 大單 | Fugle Market Data（選用）|
| 台股期貨 | FinMind TaiwanFuturesDaily / InstitutionalInvestors |
| 國際商品 / 全球指數 | Yahoo Finance v8 Chart API |
| 美國經濟指標 | FRED API（選用）|

## 全市場歷史初始化（選用）

預設只有查詢過的個股才有 10 年歷史。要使用全市場技術面選股，先執行：

```bash
curl -X POST "http://localhost:8000/admin/init-all"
```

背景執行約 1–2 小時（全台 ~2,500 支股票）。三大法人籌碼掃描不需要此步驟。

## 注意事項

- 回測結果不含交易成本（手續費 0.1425%、證交稅 0.3%）
- 歷史勝率不代表未來績效
- 觸發次數 < 10 次時標示低樣本警告
- 資料僅供個人研究用途
