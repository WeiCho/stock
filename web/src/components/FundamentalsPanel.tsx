import type { FundamentalsResponse } from '../types'

function Metric({ label, value, unit = '' }: { label: string; value?: number | null; unit?: string }) {
  return (
    <div className="bg-slate-800 rounded-lg p-3 text-center">
      <p className="text-xs text-slate-500 mb-1">{label}</p>
      <p className="text-lg font-bold text-slate-100 font-mono">
        {value != null ? `${value}${unit}` : '—'}
      </p>
    </div>
  )
}

export default function FundamentalsPanel({ data }: { data: FundamentalsResponse | null }) {
  if (!data) return null
  const { eps_latest, pe, revenue_mom, revenue_yoy, yield_rate, note } = data

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
        <Metric label="最新 EPS" value={eps_latest} unit=" 元" />
        <Metric label="本益比 PE" value={pe} unit="x" />
        <Metric label="殖利率" value={yield_rate} unit="%" />
        <Metric label="營收月增" value={revenue_mom} unit="%" />
        <Metric label="營收年增" value={revenue_yoy} unit="%" />
      </div>
      <p className="text-xs text-slate-600">{note}</p>
    </div>
  )
}
