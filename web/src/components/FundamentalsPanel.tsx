import { useEffect, useState } from 'react'
import { api } from '../api'
import type { FundamentalsResponse } from '../types'

interface MonthRev { year: number; month: number; revenue_億: number; mom_pct: number | null; yoy_pct: number | null }

function MonthlyRevenueSection({ symbol }: { symbol: string }) {
  const [data, setData] = useState<MonthRev[] | null>(null)
  const [note, setNote] = useState<string>('')
  useEffect(() => {
    let cancelled = false
    api.monthlyRevenue(symbol, 12)
      .then(r => { if (!cancelled) { setData(r.data); setNote(r.latest?.note ?? '') } })
      .catch(() => { if (!cancelled) setData([]) })
    return () => { cancelled = true }
  }, [symbol])

  if (!data || data.length === 0) return null
  return (
    <div>
      <p className="text-xs text-slate-500 uppercase mb-2">📊 月營收（MOPS · 近 12 月）</p>
      {note && <p className="text-xs text-amber-300 mb-2">{note}</p>}
      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-slate-600 text-[10px] uppercase border-b border-slate-800">
              <th className="text-left py-1">月份</th>
              <th className="text-right pr-3">營收（億）</th>
              <th className="text-right pr-3">MoM</th>
              <th className="text-right">YoY</th>
            </tr>
          </thead>
          <tbody>
            {data.slice().reverse().map(r => {
              const momColor = r.mom_pct == null ? 'text-slate-500' : r.mom_pct >= 0 ? 'text-red-400' : 'text-green-400'
              const yoyColor = r.yoy_pct == null ? 'text-slate-500' : r.yoy_pct >= 0 ? 'text-red-400' : 'text-green-400'
              return (
                <tr key={`${r.year}-${r.month}`} className="border-b border-slate-800/50">
                  <td className="py-1 text-slate-400">{r.year}/{String(r.month).padStart(2, '0')}</td>
                  <td className="text-right pr-3 font-mono text-slate-300">{r.revenue_億.toFixed(0)}</td>
                  <td className={`text-right pr-3 font-mono ${momColor}`}>
                    {r.mom_pct != null ? `${r.mom_pct >= 0 ? '+' : ''}${r.mom_pct}%` : '—'}
                  </td>
                  <td className={`text-right font-mono ${yoyColor}`}>
                    {r.yoy_pct != null ? `${r.yoy_pct >= 0 ? '+' : ''}${r.yoy_pct}%` : '—'}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

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

// 美股財報日（過 + 未來）
interface EarningsRow { date: string; epsActual?: number; epsEstimate?: number; revenueActual?: number; revenueEstimate?: number }
// 分析師評等近 4 季變化
interface RecRow { period: string; buy: number; hold: number; sell: number; strongBuy: number; strongSell: number }

function EarningsSection({ symbol }: { symbol: string }) {
  const [rows, setRows] = useState<EarningsRow[] | null>(null)
  useEffect(() => {
    let cancelled = false
    api.stockEarnings(symbol)
      .then(r => { if (!cancelled) setRows(r.earnings ?? []) })
      .catch(() => { if (!cancelled) setRows([]) })
    return () => { cancelled = true }
  }, [symbol])

  if (!rows || rows.length === 0) return null
  const today = new Date().toISOString().slice(0, 10)
  return (
    <div>
      <p className="text-xs text-slate-500 uppercase mb-2">📅 財報日（美股，Finnhub）</p>
      <table className="w-full text-xs">
        <thead className="text-slate-600 text-[10px] uppercase border-b border-slate-800">
          <tr>
            <th className="text-left py-1">日期</th>
            <th className="text-right">EPS 預期</th>
            <th className="text-right">EPS 實際</th>
            <th className="text-right">營收 預期</th>
            <th className="text-right">營收 實際</th>
          </tr>
        </thead>
        <tbody>
          {rows.slice(0, 8).map((r, i) => {
            const beats = r.epsActual != null && r.epsEstimate != null && r.epsActual > r.epsEstimate
            const future = r.date > today
            return (
              <tr key={i} className="border-b border-slate-800/50">
                <td className={`py-1 ${future ? 'text-amber-300 font-bold' : 'text-slate-400'}`}>
                  {future && '⏰ '}{r.date}
                </td>
                <td className="text-right font-mono text-slate-500">{r.epsEstimate?.toFixed(2) ?? '—'}</td>
                <td className={`text-right font-mono ${beats ? 'text-red-400 font-bold' : 'text-slate-300'}`}>
                  {r.epsActual?.toFixed(2) ?? (future ? '—' : '—')}
                </td>
                <td className="text-right font-mono text-slate-500">
                  {r.revenueEstimate ? (r.revenueEstimate / 1e9).toFixed(2) + 'B' : '—'}
                </td>
                <td className="text-right font-mono text-slate-300">
                  {r.revenueActual ? (r.revenueActual / 1e9).toFixed(2) + 'B' : '—'}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function RecommendationsSection({ symbol }: { symbol: string }) {
  const [rows, setRows] = useState<RecRow[] | null>(null)
  useEffect(() => {
    let cancelled = false
    api.stockRecommendations(symbol)
      .then(r => { if (!cancelled) setRows(r.recommendations ?? []) })
      .catch(() => { if (!cancelled) setRows([]) })
    return () => { cancelled = true }
  }, [symbol])

  if (!rows || rows.length === 0) return null
  // Finnhub 回 4 季從新到舊，反過來時間正向比較易讀
  const sorted = [...rows].reverse()
  return (
    <div>
      <p className="text-xs text-slate-500 uppercase mb-2">👥 分析師評等（美股，Finnhub 近 4 季）</p>
      <div className="space-y-1.5">
        {sorted.map((r, i) => {
          const total = r.buy + r.hold + r.sell + r.strongBuy + r.strongSell
          if (total === 0) return null
          const sbPct = (r.strongBuy / total) * 100
          const bPct = (r.buy / total) * 100
          const hPct = (r.hold / total) * 100
          const sPct = (r.sell / total) * 100
          const ssPct = (r.strongSell / total) * 100
          return (
            <div key={i} className="text-xs">
              <div className="flex justify-between text-[10px] text-slate-500 mb-0.5">
                <span>{r.period}</span>
                <span>
                  強買 {r.strongBuy} · 買 {r.buy} · 持有 {r.hold} · 賣 {r.sell} · 強賣 {r.strongSell}（共 {total}）
                </span>
              </div>
              <div className="flex h-3 rounded overflow-hidden">
                {sbPct > 0 && <div style={{ width: `${sbPct}%` }} className="bg-red-700" title={`強買 ${r.strongBuy}`} />}
                {bPct > 0 && <div style={{ width: `${bPct}%` }} className="bg-red-500" title={`買進 ${r.buy}`} />}
                {hPct > 0 && <div style={{ width: `${hPct}%` }} className="bg-slate-500" title={`持有 ${r.hold}`} />}
                {sPct > 0 && <div style={{ width: `${sPct}%` }} className="bg-green-500" title={`賣出 ${r.sell}`} />}
                {ssPct > 0 && <div style={{ width: `${ssPct}%` }} className="bg-green-700" title={`強賣 ${r.strongSell}`} />}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

export default function FundamentalsPanel({ data, symbol }: { data: FundamentalsResponse | null; symbol?: string }) {
  if (!data && !symbol) return null
  const { eps_latest, pe, revenue_mom, revenue_yoy, yield_rate, note } = data ?? {}

  return (
    <div className="space-y-4">
      {data && (
        <>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
            <Metric label="最新 EPS" value={eps_latest} unit=" 元" />
            <Metric label="本益比 PE" value={pe} unit="x" />
            <Metric label="殖利率" value={yield_rate} unit="%" />
            <Metric label="營收月增" value={revenue_mom} unit="%" />
            <Metric label="營收年增" value={revenue_yoy} unit="%" />
          </div>
          {note && <p className="text-xs text-slate-600">{note}</p>}
        </>
      )}

      {/* 台股月營收（MOPS）—— 純數字符號自動顯示，美股自動隱藏 */}
      {symbol && /^\d+$/.test(symbol) && <MonthlyRevenueSection symbol={symbol} />}

      {/* 美股財報日 + 分析師評等（如果 Finnhub 有資料才顯示，台股自動隱藏）*/}
      {symbol && (
        <>
          <EarningsSection symbol={symbol} />
          <RecommendationsSection symbol={symbol} />
        </>
      )}
    </div>
  )
}
