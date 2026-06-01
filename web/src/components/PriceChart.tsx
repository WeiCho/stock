import { useEffect, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import {
  createChart, createSeriesMarkers,
  CandlestickSeries, BaselineSeries, LineSeries, HistogramSeries,
  IChartApi, LineData, SeriesMarker, Time,
} from 'lightweight-charts'
import type { Bar, MaPoint } from '../types'
import { rsi as calcRsi, kdj as calcKdj, macd as calcMacd } from '../indicators'
import { toTime, SESSION_MINUTES } from '../lib/charts'

function detectCrosses(a: { value: number }[], b: { value: number }[]) {
  const out: { i: number; type: 'golden' | 'death' }[] = []
  for (let i = 1; i < Math.min(a.length, b.length); i++) {
    const prev = a[i - 1].value - b[i - 1].value
    const curr = a[i].value - b[i].value
    if (prev <= 0 && curr > 0) out.push({ i, type: 'golden' })
    else if (prev >= 0 && curr < 0) out.push({ i, type: 'death' })
  }
  return out
}

const MA_COLORS: Record<string, string> = {
  ma5: '#f59e0b', ma10: '#a78bfa', ma20: '#38bdf8',
  ma60: '#fb7185', ma120: '#4ade80', ma240: '#f97316',
}

export default function PriceChart({ data, mas = {}, intraday = false, previousClose = null }:
  { data?: Bar[]; mas?: Record<string, MaPoint[]>; intraday?: boolean; previousClose?: number | null }) {
  const { t: tr } = useTranslation()
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)

  useEffect(() => {
    const el = containerRef.current
    if (!el || !data?.length) return

    const chart = createChart(el, {
      layout: { background: { color: '#1a1d2e' }, textColor: '#94a3b8' },
      grid: { vertLines: { color: '#1e2235' }, horzLines: { color: '#1e2235' } },
      crosshair: { mode: 1 },
      rightPriceScale: { borderColor: '#2e3347', visible: true },
      timeScale: {
        borderColor: '#2e3347',
        timeVisible: true,
        secondsVisible: false,
        fixLeftEdge: true,
        fixRightEdge: true,
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
      height: intraday ? 320 : 520,
    })
    chartRef.current = chart

    // ── 主圖：盤中用 Baseline，其他用 Candlestick
    let candle: any = null
    if (intraday && previousClose != null) {
      const base = chart.addSeries(BaselineSeries, {
        baseValue: { type: 'price', price: previousClose },
        topLineColor: '#ef4444', topFillColor1: 'rgba(239,68,68,0.30)', topFillColor2: 'rgba(239,68,68,0.02)',
        bottomLineColor: '#22c55e', bottomFillColor1: 'rgba(34,197,94,0.02)', bottomFillColor2: 'rgba(34,197,94,0.30)',
        lineWidth: 2, priceLineVisible: false,
      })
      base.setData(data.map(r => ({ time: toTime(r.date), value: r.close })))
      base.createPriceLine({
        price: previousClose,
        color: '#64748b', lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: tr('chart.prev_close'),
      })
    } else {
      candle = chart.addSeries(CandlestickSeries, {
        upColor: '#ef4444', downColor: '#22c55e',
        borderUpColor: '#ef4444', borderDownColor: '#22c55e',
        wickUpColor: '#ef4444', wickDownColor: '#22c55e',
        priceLineVisible: false, lastValueVisible: false,
      })
      candle.setData(data.map(r => ({ time: toTime(r.date), open: r.open, high: r.high, low: r.low, close: r.close })))
    }

    // ── 盤中均價線
    if (intraday && data.some(r => r.average != null)) {
      const avg = chart.addSeries(LineSeries, { color: '#fbbf24', lineWidth: 1, priceLineVisible: false, lastValueVisible: false })
      avg.setData(data.filter(r => r.average != null).map(r => ({ time: toTime(r.date), value: r.average })))
    }

    if (!intraday) {
      // ── 均線（主圖 pane 0）
      Object.entries(mas).forEach(([key, values]) => {
        if (!values?.length) return
        chart.addSeries(LineSeries, {
          color: MA_COLORS[key] ?? '#888', lineWidth: 1,
          priceLineVisible: false, lastValueVisible: false,
        }).setData(values as unknown as LineData<Time>[])
      })

      // ── Markers
      const allMarkers: SeriesMarker<Time>[] = []

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
              allMarkers.push({ time: t, position: 'belowBar', color: '#ef4444', shape: 'arrowUp', text: tr('chart.marker.ma_golden') })
            } else if (prevDiff >= 0 && diff < 0) {
              allMarkers.push({ time: t, position: 'aboveBar', color: '#22c55e', shape: 'arrowDown', text: tr('chart.marker.ma_death') })
            }
          }
          prevDiff = diff
        }
      }

      // ── MACD markers（保留圓點，移除曲線圖）
      const macdData = calcMacd(data, 12, 26, 9)
      if (macdData.macd.length > 0) {
        detectCrosses(macdData.macd, macdData.signal).forEach(c => {
          allMarkers.push({
            time: toTime(data[c.i].date),
            position: c.type === 'golden' ? 'belowBar' : 'aboveBar',
            color: c.type === 'golden' ? '#fb923c' : '#94a3b8',
            shape: 'circle',
            text: c.type === 'golden' ? tr('chart.marker.macd_golden') : tr('chart.marker.macd_death'),
          })
        })
      }

      // ── 量能副圖（pane 1）
      const volSeries = chart.addSeries(HistogramSeries, {
        priceFormat: { type: 'volume' }, priceLineVisible: false, lastValueVisible: false,
      }, 1)
      volSeries.priceScale().applyOptions({ scaleMargins: { top: 0.1, bottom: 0 }, borderVisible: false })
      volSeries.setData(data.map(r => ({
        time: toTime(r.date), value: r.volume,
        color: r.close >= r.open ? '#ef444488' : '#22c55e88',
      })))

      // ───── RSI 副圖（pane 2）── 0-100 帶 30/70 超買超賣參考線
      const rsiData = calcRsi(data, 14)
      if (rsiData.length > 0) {
        const rsiSeries = chart.addSeries(LineSeries, {
          color: '#a78bfa', lineWidth: 1, priceLineVisible: false,
          priceFormat: { type: 'price', precision: 2, minMove: 0.01 },
        }, 2)
        rsiSeries.setData(rsiData as unknown as LineData<Time>[])
        rsiSeries.createPriceLine({ price: 70, color: '#64748b', lineStyle: 2, lineWidth: 1, axisLabelVisible: true, title: tr('chart.rsi_overbought') })
        rsiSeries.createPriceLine({ price: 30, color: '#64748b', lineStyle: 2, lineWidth: 1, axisLabelVisible: true, title: tr('chart.rsi_oversold') })
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
              text: c.type === 'golden' ? tr('chart.marker.kdj_low') : tr('chart.marker.kdj_high'),
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

      // ── pane 相對高度（主圖 4：量能 1）
      setTimeout(() => {
        try {
          const panes = chart.panes()
          if (panes[0]) panes[0].setStretchFactor(4)
          if (panes[1]) panes[1].setStretchFactor(1)
        } catch (_) { /* ignore */ }
      }, 0)
    }

    // ── ResizeObserver：確認 chart 未被 remove 才更新
    const obs = new ResizeObserver(() => {
      if (!chartRef.current) return
      try { chart.applyOptions({ width: el.clientWidth }) } catch (_) { /* ignore */ }
    })
    obs.observe(el)

    let rightOffset = 0
    if (intraday && data.length >= 2) {
      const dt = (new Date(data[1].date).getTime() - new Date(data[0].date).getTime()) / 60000
      if (dt > 0) rightOffset = Math.max(0, Math.round(SESSION_MINUTES / dt) - data.length)
    }
    chart.timeScale().applyOptions({ rightOffset })
    chart.timeScale().fitContent()
    // After fitContent, scroll last bar to right edge (rightOffset = 0 means no trailing space)
    if (!intraday) chart.timeScale().scrollToRealTime()

    return () => {
      chartRef.current = null
      obs.disconnect()
      chart.remove()
    }
  }, [data, mas, intraday, previousClose, tr])

  return <div ref={containerRef} className="w-full rounded-lg" style={{ height: intraday ? 320 : 520 }} />
}
