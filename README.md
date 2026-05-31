# 台股分析工具

台股 + 國際商品 + 期貨 + 總體經濟分析，React Web App + FastAPI 後端。

## 啟動

```powershell
.\start.ps1
```

首次執行自動建立 venv 與安裝前後端相依，啟動後端（`:8000`）與前端（`:5173`）。關閉視窗或 Ctrl+C 自動停止。

手動分開啟動：

```powershell
.\.venv\Scripts\python.exe -m uvicorn server.main:app --host 0.0.0.0 --port 8000
cd web; npm run dev
```

### API Key（選用）

```
FUGLE_API_KEY   盤中即時K + 大單敲進逐筆偵測
FRED_API_KEY    總經頁 CPI / GDP / NFP / Fed Funds / 失業率
```

申請：[Fugle](https://developer.fugle.tw/) / [FRED](https://fred.stlouisfed.org/docs/api/api_key.html)（皆免費）

## 功能

### 個股（7 個 Tab）

| Tab | 說明 |
|------|------|
| 綜合研判 | 技術面 + 籌碼面 + 回測綜合方向研判 |
| 技術面 | 日K/週K，MA/RSI/MACD/KD/布林，自動偵測形態訊號 |
| 籌碼面 | 外資/投信/自營商買賣超，連買天數，5/10/20 日累計 |
| 回測 | 11 種訊號，10 年勝率統計（5/10/20/60 日報酬）|
| 型態 | 三線交纏帶量突破 MA60 掃描（見下方）|
| 基本面 | EPS、本益比、殖利率、營收月增/年增 |
| 新聞 | Google News 近 30 天 |

K 線支援 7 種時間框架（當日/日K/3日/5日/週K/3週/月K）+ MA 金叉死叉與 MACD marker + 量能副圖。

### 掃描（全市場，當日快取）

**三線交纏帶量突破 MA60**

- 蓄勢中：MA5/MA10/MA20 三線交纏（差距 < 3%）+ 收盤站上三線 + 距 MA60 < 3%
- 突破完成：帶量（昨量 > 均量 1.5×）+ 連 2 日站上 MA60 + 前天仍在 MA60 以下

**週線W底突破**

四條件同時成立：本週收盤剛站上週MA20 / 週MA20 上斜 / 近40週W底底底高 / 本週爆量（> 近10週均量 1.5×）

### 大盤

| 功能 | 說明 |
|------|------|
| 加權指數 | 盤中每秒更新 + 多時間區間走勢 |
| 法人資金 | 外資/投信/自營商買賣超排行 + 類股流向 |
| 大單敲進 | 盤中大額成交逐筆偵測（需 Fugle key）|
| 全球新聞 | 亞/歐/美 + 地緣政治（30 分鐘快取）|

### 期貨 / 國際商品

TX / MTX / TE / TF + 黃金 / 白銀 / 銅 / 原油，多時間框架 K 線 + 績效摘要 + 三大法人留倉。

### 總經（Macro）

美 10Y/5Y 公債、DXY、VIX、SPX/NDX/DJI、黃金/原油/BTC/ETH，VIX 自動分級（> 30 恐慌 / > 20 警戒）。

## 回測訊號（11 種）

| 訊號 | 說明 |
|------|------|
| `ma_cross` / `ma_death` | MA20 × MA60 黃金/死亡交叉（日K）|
| `weekly_ma_cross` | 週MA20 × 週MA52 黃金交叉 |
| `kd_low_cross` / `kd_high_cross` | KD 低檔金叉（K<30）/ 高檔死叉（K>70）|
| `macd_turn_pos` / `macd_turn_neg` | MACD 柱狀由負轉正 / 由正轉負 |
| `rsi_oversold` / `rsi_overbought` | RSI 超賣（<30）/ 超買（>70）|
| `best_four_buy` / `best_four_sell` | 四大買點 / 賣點（乖離率 pivot + 量價條件）|
| `weekly_w_bottom` | 週線W底突破（站上週MA20 + 上斜 + W底 + 爆量）|

每個訊號有對應 Pine v5 模板，前端「下載 Pine」一鍵存檔。

## 資料來源

| 資料 | 來源 |
|------|------|
| 個股歷史日K（10年）| FinMind（首選）/ TWSE·TPEx 爬蟲（備援）|
| 三大法人 | TWSE T86 |
| 即時指數 | TWSE MIS |
| 基本面 | FinMind |
| 新聞 | Google News RSS |
| 盤中逐筆 / 大單 | Fugle Market Data（選用）|
| 期貨 | FinMind TaiwanFuturesDaily |
| 國際商品 / 全球指數 | Yahoo Finance v8 |
| 美國經濟指標 | FRED API（選用）|

## 全市場歷史初始化

預設只有查詢過的個股有 10 年歷史。要啟用全市場掃描，先執行：

```powershell
Invoke-RestMethod -Method Post "http://localhost:8000/admin/init-all"
```

背景執行約 1–2 小時（全台 ~2,500 支股票）。

## 注意事項

- 回測不含交易成本（手續費 0.1425% + 證交稅 0.3%）
- 歷史勝率不代表未來績效，觸發次數 < 10 次標示低樣本警告
- 資料僅供個人研究用途
