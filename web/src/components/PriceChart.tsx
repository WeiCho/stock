import { useEffect, useRef } from 'react'
import { createChart, CandlestickSeries, BaselineSeries, LineSeries, UTCTimestamp, Time } from 'lightweight-charts'

const toTime = (s: string): Time => (typeof s === 'string' && s.includes('T')
  ? (Math.floor(new Date(s).getTime() / 1000) as UTCTimestamp)
  : s as Time)

export default function PriceChart({ data, mas = {}, intraday = false, previousClose = null }:
  { data?: any[]; mas?: Record<string, any>; intraday?: boolean; previousClose?: number | null }) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<any>(null)

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
      height: 320,
    })
    chartRef.current = chart

    // 盤中+有昨收：用 Apple Stocks 風格 BaselineSeries（昨收為基準上紅/下綠雙色漸層填）
    // 其他模式（日K/週K/月K）：用標準蠟燭圖
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
      const candle = chart.addSeries(CandlestickSeries, {
        upColor: '#ef4444', downColor: '#22c55e',
        borderUpColor: '#ef4444', borderDownColor: '#22c55e',
        wickUpColor: '#ef4444', wickDownColor: '#22c55e',
      })
      candle.setData(data.map(r => ({
        time: toTime(r.date), open: r.open, high: r.high, low: r.low, close: r.close,
      })))
      // 盤中但無昨收 → 用收盤線當作 baseline 仍標一條昨收線（這分支不會有 previousClose，跳過）
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
      const MA_COLORS = { ma5: '#f59e0b', ma10: '#a78bfa', ma20: '#38bdf8', ma60: '#fb7185', ma120: '#4ade80', ma240: '#f97316' }
      Object.entries(mas).forEach(([key, values]) => {
        if (!values?.length) return
        const s = chart.addSeries(LineSeries, { color: MA_COLORS[key] ?? '#888', lineWidth: 1, priceLineVisible: false })
        s.setData(values)
      })
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
        rightOffset = Math.max(0, Math.round(270 / dt) - data.length)
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
