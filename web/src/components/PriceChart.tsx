import { useEffect, useRef } from 'react'
import { createChart, createSeriesMarkers, CandlestickSeries, BaselineSeries, LineSeries, IChartApi, ISeriesApi, LineData, SeriesMarker, Time } from 'lightweight-charts'
import type { Bar, MaPoint } from '../types'
import { rsi as calcRsi, kdj as calcKdj, macd as calcMacd } from '../indicators'
import { toTime, SESSION_MINUTES } from '../lib/charts'

// 偵測兩條序列的「金叉/死叉」：a 由下而上穿越 b = 金叉；由上而下 = 死叉
// 回傳 [{index, type: 'golden'|'death'}]
function detectCrosses(a: { value: number }[], b: { value: number }[]):
  { i: number; type: 'golden' | 'death' }[] {
  const out: { i: number; type: 'golden' | 'death' }[] = []
  for (let i = 1; i < Math.min(a.length, b.length); i++) {
    const prev = a[i - 1].value - b[i - 1].value
    const curr = a[i].value - b[i].value
    if (prev <= 0 && curr > 0) out.push({ i, type: 'golden' })
    else if (prev >= 0 && curr < 0) out.push({ i, type: 'death' })
  }
  return out
}

export default function PriceChart({ data, mas = {}, intraday = false, previousClose = null }:
  { data?: Bar[]; mas?: Record<string, MaPoint[]>; intraday?: boolean; previousClose?: number | null }) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)

  useEffect(() => {
    const el = containerRef.current
    if (!el || !data?.length) return

    const chart = createChart(el, {
      layout: { background: { color: '#1a1d2e' }, textColor: '#94a3b8' },
      grid: { vertLines: { color: '#1e2235' }, horzLines: { color: '#1e2235' } },
      crosshair: { mode: 1 },
      rightPriceScale: { borderColor: '#2e3347' },
      timeScale: {
        borderColor: '#2e3347',
        timeVisible: true,
        secondsVisible: false,
        // 盤中分鐘 K：刻度顯示 HH 或 HH:MM；其他時間框架沿用 v5 預設
        tickMarkFormatter: intraday
          ? (t: number) => {
              const d = new Date((t as number) * 1000)
              const hh = d.toLocaleString('en-US', { timeZone: 'Asia/Taipei', hour: '2-digit', hour12: false })
              const mm = d.toLocaleString('en-US', { timeZone: 'Asia/Taipei', minute: '2-digit' })
              return mm === '00' ? hh : `${hh}:${mm.padStart(2, '0')}`
            }
          : undefined,
      },
      width: el.clientWidth,
      // 非盤中加 MACD + RSI + KDJ 三個副圖 → 主圖 320 + 三個 80 = 560
      height: intraday ? 320 : 600,
    })
    chartRef.current = chart

    // 盤中+有昨收：用 Apple Stocks 風格 BaselineSeries（昨收為基準上紅/下綠雙色漸層填）
    // 其他模式（日K/週K/月K）：用標準蠟燭圖
    let candle: ISeriesApi<'Candlestick'> | null = null
    if (intraday && previousClose != null) {
      const base = chart.addSeries(BaselineSeries, {
        baseValue: { type: 'price', price: previousClose },
        topLineColor: '#ef4444',
        topFillColor1: 'rgba(239,68,68,0.30)',
        topFillColor2: 'rgba(239,68,68,0.02)',
        bottomLineColor: '#22c55e',
        bottomFillColor1: 'rgba(34,197,94,0.02)',
        bottomFillColor2: 'rgba(34,197,94,0.30)',
        lineWidth: 2,
        priceLineVisible: false,
      })
      base.setData(data.map(r => ({ time: toTime(r.date), value: r.close })))
      base.createPriceLine({
        price: previousClose,
        color: '#64748b', lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: '昨收',
      })
    } else {
      candle = chart.addSeries(CandlestickSeries, {
        upColor: '#ef4444', downColor: '#22c55e',
        borderUpColor: '#ef4444', borderDownColor: '#22c55e',
        wickUpColor: '#ef4444', wickDownColor: '#22c55e',
      })
      candle.setData(data.map(r => ({
        time: toTime(r.date), open: r.open, high: r.high, low: r.low, close: r.close,
      })))
    }

    // 盤中均價線（Fugle 已回 r.average）— 在所有盤中模式都疊加
    if (intraday && data.some(r => r.average != null)) {
      const avg = chart.addSeries(LineSeries, {
        color: '#fbbf24', lineWidth: 1, priceLineVisible: false, lastValueVisible: false,
      })
      avg.setData(data.filter(r => r.average != null).map(r => ({ time: toTime(r.date), value: r.average })))
    }

    // 日 K 模式才疊均線；盤中模式不顯示日線級的 MA
    if (!intraday) {
      const MA_COLORS: Record<string, string> = { ma5: '#f59e0b', ma10: '#a78bfa', ma20: '#38bdf8', ma60: '#fb7185', ma120: '#4ade80', ma240: '#f97316' }
      Object.entries(mas).forEach(([key, values]) => {
        if (!values?.length) return
        const s = chart.addSeries(LineSeries, { color: MA_COLORS[key] ?? '#888', lineWidth: 1, priceLineVisible: false })
        // MaPoint.time 是 string | number；lightweight-charts 接受兩者，型別差只是 branded
        s.setData(values as unknown as LineData<Time>[])
      })

      // ───── 計算所有 markers（最後一次 createSeriesMarkers 才會生效，所以全部收集起來一次設）
      const allMarkers: SeriesMarker<Time>[] = []

      // MA20 × MA60 金叉/死叉（大趨勢轉折）— 紅藍箭頭
      if (mas.ma20?.length && mas.ma60?.length) {
        const ma20Map = new Map(mas.ma20.map(p => [p.time, p.value]))
        const ma60Map = new Map(mas.ma60.map(p => [p.time, p.value]))
        let prevDiff: number | null = null
        for (const bar of data) {
          const t = toTime(bar.date)
          const m20 = ma20Map.get(t as string | number)
          const m60 = ma60Map.get(t as string | number)
          if (m20 == null || m60 == null) continue
          const diff = m20 - m60
          if (prevDiff !== null) {
            if (prevDiff <= 0 && diff > 0) {
              allMarkers.push({ time: t, position: 'belowBar', color: '#ef4444', shape: 'arrowUp', text: 'MA金叉' })
            } else if (prevDiff >= 0 && diff < 0) {
              allMarkers.push({ time: t, position: 'aboveBar', color: '#22c55e', shape: 'arrowDown', text: 'MA死叉' })
            }
          }
          prevDiff = diff
        }
      }

      // ───── MACD 副圖（pane 1）── 大方向判斷（金叉=偏多、死叉=偏空）
      const macdData = calcMacd(data, 12, 26, 9)
      if (macdData.macd.length > 0) {
        const macdSeries = chart.addSeries(LineSeries, { color: '#60a5fa', lineWidth: 1, priceLineVisible: false }, 1)
        const sigSeries = chart.addSeries(LineSeries, { color: '#f59e0b', lineWidth: 1, priceLineVisible: false }, 1)
        macdSeries.setData(macdData.macd as unknown as LineData<Time>[])
        sigSeries.setData(macdData.signal as unknown as LineData<Time>[])
        // MACD 金叉/死叉 marker：橙色圓點 = 大方向訊號
        detectCrosses(macdData.macd, macdData.signal).forEach(c => {
          allMarkers.push({
            time: toTime(data[c.i].date),
            position: c.type === 'golden' ? 'belowBar' : 'aboveBar',
            color: c.type === 'golden' ? '#fb923c' : '#94a3b8',
            shape: 'circle',
            text: c.type === 'golden' ? 'MACD↑' : 'MACD↓',
          })
        })
      }

      // ───── RSI 副圖（pane 2）── 0-100 帶 30/70 超買超賣參考線
      const rsiData = calcRsi(data, 14)
      if (rsiData.length > 0) {
        const rsiSeries = chart.addSeries(LineSeries, {
          color: '#a78bfa', lineWidth: 1, priceLineVisible: false,
          priceFormat: { type: 'price', precision: 2, minMove: 0.01 },
        }, 2)
        rsiSeries.setData(rsiData as unknown as LineData<Time>[])
        rsiSeries.createPriceLine({ price: 70, color: '#64748b', lineStyle: 2, lineWidth: 1, axisLabelVisible: true, title: '超買' })
        rsiSeries.createPriceLine({ price: 30, color: '#64748b', lineStyle: 2, lineWidth: 1, axisLabelVisible: true, title: '超賣' })
      }

      // ───── KDJ 副圖（pane 3）── 進場時機（K/D 交叉，K<30 / K>70 才標記）
      const kdjData = calcKdj(data, 9)
      if (kdjData.k.length > 0) {
        const kSeries = chart.addSeries(LineSeries, { color: '#facc15', lineWidth: 1, priceLineVisible: false }, 3)
        const dSeries = chart.addSeries(LineSeries, { color: '#60a5fa', lineWidth: 1, priceLineVisible: false }, 3)
        const jSeries = chart.addSeries(LineSeries, { color: '#f472b6', lineWidth: 1, priceLineVisible: false }, 3)
        kSeries.setData(kdjData.k as unknown as LineData<Time>[])
        dSeries.setData(kdjData.d as unknown as LineData<Time>[])
        jSeries.setData(kdjData.j as unknown as LineData<Time>[])
        const offset = data.length - kdjData.k.length  // kdj 從 bars[n-1] 起算
        detectCrosses(kdjData.k, kdjData.d).forEach(c => {
          const kVal = kdjData.k[c.i].value
          // 只標記 K<30 黃金交叉（低檔進場）或 K>70 死亡交叉（高檔出場）— 過濾雜訊
          if ((c.type === 'golden' && kVal < 30) || (c.type === 'death' && kVal > 70)) {
            allMarkers.push({
              time: toTime(data[c.i + offset].date),
              position: c.type === 'golden' ? 'belowBar' : 'aboveBar',
              color: c.type === 'golden' ? '#facc15' : '#a3a3a3',
              shape: 'square',
              text: c.type === 'golden' ? 'KDJ低' : 'KDJ高',
            })
          }
        })
      }

      // 一次套用所有 markers：MA / MACD / KDJ 三層訊號疊在 K 線上
      // 「Top-Down」分析：MACD 看大方向（橙圓），KDJ 找進場（黃方），MA 看趨勢轉折（紅藍箭）
      if (candle && allMarkers.length > 0) {
        allMarkers.sort((a, b) => (a.time as number) - (b.time as number))
        createSeriesMarkers(candle, allMarkers)
      }

      // 設定 panes 高度：主圖大、三個副圖各 80
      const panes = chart.panes()
      panes.forEach((p, idx) => { if (idx > 0) p.setHeight(80) })
    }

    const obs = new ResizeObserver(() => {
      chart.applyOptions({ width: el.clientWidth })
    })
    obs.observe(el)

    // 盤中：在實際資料後補空 bar slot 直到 13:30（v5 的 setVisibleRange 無法延伸至無資料時段，
    // 改用 rightOffset 撐開 X 軸；tickMarkFormatter 會自動標記 11:00 / 12:00 / 13:00 / 13:30）。
    // 非盤中時明確設 0，避免之前的 chart 狀態（理論上不會殘留但防禦性處理）。
    let rightOffset = 0
    if (intraday && data.length >= 2) {
      const dt = (new Date(data[1].date).getTime() - new Date(data[0].date).getTime()) / 60000
      if (dt > 0) {
        rightOffset = Math.max(0, Math.round(SESSION_MINUTES / dt) - data.length)
      }
    }
    chart.timeScale().applyOptions({ rightOffset })
    chart.timeScale().fitContent()

    return () => {
      obs.disconnect()
      chart.remove()
      chartRef.current = null
    }
  }, [data, mas, intraday, previousClose])

  return <div ref={containerRef} className="w-full rounded-lg overflow-hidden" />
}
