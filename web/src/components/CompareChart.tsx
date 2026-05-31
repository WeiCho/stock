import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { createChart, LineSeries, IChartApi, LineData, Time } from 'lightweight-charts'
import { api } from '../api'
import type { Bar } from '../types'
import { toTime } from '../lib/charts'

/**
 * 多支股票疊圖工具：所有 series normalize 到 100（起點），看相對強弱。
 * 例如比 2330 vs 2454 vs 0050 近 1 年表現。
 */

const COLORS = ['#38bdf8', '#fb7185', '#facc15', '#22c55e', '#a78bfa', '#fb923c']

const RANGES: { labelKey: string; days: number }[] = [
  { labelKey: 'compare.range.1m', days: 30 },
  { labelKey: 'compare.range.3m', days: 90 },
  { labelKey: 'compare.range.6m', days: 180 },
  { labelKey: 'compare.range.1y', days: 365 },
  { labelKey: 'compare.range.3y', days: 1095 },
  { labelKey: 'compare.range.5y', days: 1825 },
]

interface SymbolBars { symbol: string; name?: string; bars: Bar[]; error?: string }

async function fetchOne(symbol: string, days: number): Promise<SymbolBars> {
  try {
    // 先試 stock price（台股），失敗試 commodity（國際商品/期貨）
    try {
      const r = await api.price(symbol, days, '1d')
      return { symbol, bars: r.data ?? [] }
    } catch {
      const r = await api.commodity(symbol, days, '1d')
      return { symbol, name: r.label, bars: r.data ?? [] }
    }
  } catch (e) {
    return { symbol, bars: [], error: (e as Error).message }
  }
}

// 把 close 序列 normalize 到 100（以第一筆為基準）
function normalize(bars: Bar[]): { time: string; value: number }[] {
  if (bars.length === 0) return []
  const base = bars[0].close
  if (!base) return []
  return bars.map(b => ({ time: b.date, value: (b.close / base) * 100 }))
}

export default function CompareChart() {
  const { t } = useTranslation()
  const [symbols, setSymbols] = useState<string[]>(['2330', '2454'])
  const [input, setInput] = useState('')
  const [rangeIdx, setRangeIdx] = useState(3)  // 預設 1 年
  const [series, setSeries] = useState<SymbolBars[]>([])
  const [loading, setLoading] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const range = RANGES[rangeIdx]

  // 抓資料
  useEffect(() => {
    let cancelled = false
    setLoading(true)
    Promise.all(symbols.map(s => fetchOne(s, range.days))).then(results => {
      if (cancelled) return
      setSeries(results)
      setLoading(false)
    })
    return () => { cancelled = true }
  }, [symbols, range.days])

  // 畫圖
  useEffect(() => {
    const el = containerRef.current
    if (!el || series.length === 0) return

    const chart = createChart(el, {
      layout: { background: { color: '#1a1d2e' }, textColor: '#94a3b8' },
      grid: { vertLines: { color: '#1e2235' }, horzLines: { color: '#1e2235' } },
      rightPriceScale: { borderColor: '#2e3347' },
      timeScale: { borderColor: '#2e3347', timeVisible: false },
      width: el.clientWidth,
      height: 400,
    })
    chartRef.current = chart

    // 100 基準線（dashed）
    series.forEach((s, i) => {
      const data = normalize(s.bars)
      if (data.length === 0) return
      const line = chart.addSeries(LineSeries, {
        color: COLORS[i % COLORS.length],
        lineWidth: 2,
        title: s.name ? `${s.symbol} (${s.name})` : s.symbol,
        lastValueVisible: true,
      })
      line.setData(data.map(d => ({ time: toTime(d.time), value: d.value })) as unknown as LineData<Time>[])
      if (i === 0) {
        // 第一條加 100 baseline price line
        line.createPriceLine({ price: 100, color: '#64748b', lineWidth: 1, lineStyle: 2, axisLabelVisible: true, title: t('compare.baseline') })
      }
    })

    chart.timeScale().fitContent()
    const obs = new ResizeObserver(() => chart.applyOptions({ width: el.clientWidth }))
    obs.observe(el)
    return () => { obs.disconnect(); chart.remove(); chartRef.current = null }
  }, [series, t])

  const addSymbol = (e: React.FormEvent) => {
    e.preventDefault()
    const s = input.trim().toUpperCase()
    if (!s || symbols.includes(s)) return
    if (symbols.length >= 6) return  // 最多 6 條，避免太亂
    setSymbols([...symbols, s])
    setInput('')
  }

  const removeSymbol = (s: string) => {
    if (symbols.length <= 1) return  // 至少留 1 條
    setSymbols(symbols.filter(x => x !== s))
  }

  // 顯示每條最終漲跌％
  const summary = series.map(s => {
    if (s.bars.length === 0) return { symbol: s.symbol, change: null, error: s.error }
    const last = s.bars[s.bars.length - 1].close
    const base = s.bars[0].close
    const change = base > 0 ? ((last - base) / base) * 100 : null
    return { symbol: s.symbol, name: s.name, change }
  })

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-lg font-bold text-slate-100">{t('compare.title')}</h2>
        <p className="text-xs text-slate-500 mt-1">
          {t('compare.subtitle')}
        </p>
      </div>

      {/* 新增符號 */}
      <form onSubmit={addSymbol} className="flex gap-2">
        <input value={input} onChange={e => setInput(e.target.value)}
          placeholder={t('compare.input_placeholder')}
          className="flex-1 bg-slate-800 border border-slate-600 rounded px-3 py-1.5 text-sm focus:outline-none focus:border-blue-500" />
        <button type="submit"
          className="bg-blue-600 hover:bg-blue-500 px-4 py-1.5 rounded text-sm font-medium disabled:opacity-50"
          disabled={symbols.length >= 6}>
          {t('common.add')}
        </button>
      </form>

      {/* 已加入的符號 chips + 漲跌 */}
      <div className="flex flex-wrap gap-2">
        {summary.map((s, i) => (
          <div key={s.symbol} className="flex items-center gap-1.5 bg-slate-800 rounded px-2.5 py-1 text-xs">
            <span className="w-2 h-2 rounded-full" style={{ background: COLORS[i % COLORS.length] }} />
            <span className="text-slate-200 font-mono">{s.symbol}</span>
            {s.name && <span className="text-slate-500">{s.name}</span>}
            {s.change != null && (
              <span className={`font-mono ${s.change >= 0 ? 'text-red-400' : 'text-green-400'}`}>
                {s.change >= 0 ? '+' : ''}{s.change.toFixed(2)}%
              </span>
            )}
            {s.error && <span className="text-amber-400 text-[10px]">⚠ {s.error}</span>}
            {symbols.length > 1 && (
              <button onClick={() => removeSymbol(s.symbol)}
                className="text-slate-500 hover:text-red-400 ml-1">×</button>
            )}
          </div>
        ))}
      </div>

      {/* 時間區間 */}
      <div className="flex flex-wrap gap-1">
        {RANGES.map((r, i) => (
          <button key={r.labelKey} onClick={() => setRangeIdx(i)}
            className={`text-xs px-3 py-1 rounded ${rangeIdx === i ? 'bg-blue-600 text-white' : 'bg-slate-800 text-slate-400 hover:bg-slate-700'}`}>
            {t(r.labelKey)}
          </button>
        ))}
      </div>

      {/* 圖 */}
      {loading && <p className="text-slate-500 text-sm">{t('common.loading')}</p>}
      <div ref={containerRef} className="w-full rounded-lg overflow-hidden" />

      <p className="text-[10px] text-slate-600">
        {t('compare.footnote')}
      </p>
    </div>
  )
}
