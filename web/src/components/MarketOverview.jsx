import { useEffect, useRef } from 'react'
import { createChart } from 'lightweight-charts'

function IndexChart({ data }) {
  const ref = useRef(null)
  useEffect(() => {
    if (!ref.current || !data?.length) return
    const chart = createChart(ref.current, {
      layout: { background: { color: '#1a1d2e' }, textColor: '#94a3b8' },
      grid: { vertLines: { color: '#1e2235' }, horzLines: { color: '#1e2235' } },
      rightPriceScale: { borderColor: '#2e3347' },
      timeScale: { borderColor: '#2e3347' },
      width: ref.current.clientWidth,
      height: 180,
    })
    const line = chart.addAreaSeries({ lineColor: '#38bdf8', topColor: 'rgba(56,189,248,0.2)', bottomColor: 'transparent', lineWidth: 2 })
    line.setData(data.map(r => ({ time: r.date, value: r.close })))
    chart.timeScale().fitContent()
    const obs = new ResizeObserver(() => chart.applyOptions({ width: ref.current.clientWidth }))
    obs.observe(ref.current)
    return () => { obs.disconnect(); chart.remove() }
  }, [data])
  return <div ref={ref} className="w-full rounded-lg overflow-hidden" />
}

export default function MarketOverview({ index, institutional }) {
  const latest = index?.data?.at(-1)
  const prev = index?.data?.at(-2)
  const change = latest && prev ? ((latest.close - prev.close) / prev.close * 100).toFixed(2) : null

  return (
    <div className="space-y-4">
      <div className="flex items-baseline gap-3">
        <span className="text-2xl font-bold text-slate-100 font-mono">
          {latest?.close?.toLocaleString()}
        </span>
        {change !== null && (
          <span className={`text-sm font-medium ${parseFloat(change) >= 0 ? 'text-red-400' : 'text-green-400'}`}>
            {parseFloat(change) >= 0 ? '▲' : '▼'} {Math.abs(change)}%
          </span>
        )}
        <span className="text-xs text-slate-500">加權指數 {latest?.date}</span>
      </div>

      <IndexChart data={index?.data} />

      {institutional?.data?.length > 0 && (
        <div>
          <p className="text-xs text-slate-500 uppercase mb-2">三大法人買超排行 ({institutional.date})</p>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-slate-600 border-b border-slate-800">
                  <th className="text-left pb-1">代碼</th>
                  <th className="text-right pb-1">外資</th>
                  <th className="text-right pb-1">投信</th>
                  <th className="text-right pb-1">合計(張)</th>
                </tr>
              </thead>
              <tbody>
                {institutional.data.slice(0, 10).map(r => (
                  <tr key={r.symbol} className="border-b border-slate-800">
                    <td className="py-1 text-slate-300 font-mono">{r.symbol}</td>
                    <td className={`text-right font-mono ${r.foreign_buy >= 0 ? 'text-red-400' : 'text-green-400'}`}>
                      {r.foreign_buy >= 0 ? '+' : ''}{Math.round(r.foreign_buy).toLocaleString()}
                    </td>
                    <td className={`text-right font-mono ${r.trust_buy >= 0 ? 'text-red-400' : 'text-green-400'}`}>
                      {r.trust_buy >= 0 ? '+' : ''}{Math.round(r.trust_buy).toLocaleString()}
                    </td>
                    <td className={`text-right font-mono font-bold ${r.total_buy >= 0 ? 'text-red-400' : 'text-green-400'}`}>
                      {r.total_buy >= 0 ? '+' : ''}{Math.round(r.total_buy).toLocaleString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
