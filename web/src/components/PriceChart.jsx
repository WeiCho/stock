import { useEffect, useRef } from 'react'
import { createChart, CandlestickSeries, LineSeries } from 'lightweight-charts'

export default function PriceChart({ data, mas = {} }) {
  const containerRef = useRef(null)
  const chartRef = useRef(null)

  useEffect(() => {
    if (!containerRef.current || !data?.length) return

    const chart = createChart(containerRef.current, {
      layout: { background: { color: '#1a1d2e' }, textColor: '#94a3b8' },
      grid: { vertLines: { color: '#1e2235' }, horzLines: { color: '#1e2235' } },
      crosshair: { mode: 1 },
      rightPriceScale: { borderColor: '#2e3347' },
      timeScale: { borderColor: '#2e3347', timeVisible: true },
      width: containerRef.current.clientWidth,
      height: 320,
    })
    chartRef.current = chart

    const candle = chart.addSeries(CandlestickSeries, {
      upColor: '#ef4444', downColor: '#22c55e',
      borderUpColor: '#ef4444', borderDownColor: '#22c55e',
      wickUpColor: '#ef4444', wickDownColor: '#22c55e',
    })
    candle.setData(data.map(r => ({
      time: r.date, open: r.open, high: r.high, low: r.low, close: r.close,
    })))

    const MA_COLORS = { ma5: '#f59e0b', ma10: '#a78bfa', ma20: '#38bdf8', ma60: '#fb7185', ma120: '#4ade80', ma240: '#f97316' }
    Object.entries(mas).forEach(([key, values]) => {
      if (!values?.length) return
      const s = chart.addSeries(LineSeries, { color: MA_COLORS[key] ?? '#888', lineWidth: 1, priceLineVisible: false })
      s.setData(values)
    })

    const obs = new ResizeObserver(() => {
      chart.applyOptions({ width: containerRef.current.clientWidth })
    })
    obs.observe(containerRef.current)

    chart.timeScale().fitContent()

    return () => { obs.disconnect(); chart.remove() }
  }, [data, mas])

  return <div ref={containerRef} className="w-full rounded-lg overflow-hidden" />
}
