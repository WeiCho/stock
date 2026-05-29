import { useEffect, useState } from 'react'
import { api } from '../api'
import type { ChipResponse } from '../types'

function ChipRow({ label, today, cum5d, trend }:
  { label: string; today?: number; cum5d?: number; trend?: string }) {
  const sign = (today ?? 0) >= 0 ? 'text-red-400' : 'text-green-400'
  return (
    <div className="border border-slate-700 rounded-lg p-3 space-y-1">
      <div className="flex justify-between items-center">
        <span className="text-slate-400 text-sm">{label}</span>
        <span className={`font-mono font-bold ${sign}`}>
          {today != null && (today >= 0 ? '+' : '')}{today?.toLocaleString() ?? '—'} 張
        </span>
      </div>
      <div className="flex gap-3 text-xs text-slate-500">
        {trend && <span>{trend}</span>}
        {cum5d !== undefined && <span>5日累計 {cum5d >= 0 ? '+' : ''}{cum5d.toLocaleString()}</span>}
      </div>
    </div>
  )
}

interface ForeignHold { date: string; foreign_ratio: number | null; change_4w_pp?: number; note?: string }
interface MarginShort { date: string; margin_balance: number; margin_change: number; short_balance: number; short_change: number }
interface SecLend { date: string; volume: number; avg_fee_rate: number }

function ForeignHoldingSection({ symbol }: { symbol: string }) {
  const [data, setData] = useState<ForeignHold | null>(null)
  useEffect(() => {
    let cancelled = false
    api.foreignHolding(symbol, 26).then(r => {
      if (!cancelled) setData(r.latest ?? null)
    }).catch(() => {})
    return () => { cancelled = true }
  }, [symbol])

  if (!data || data.foreign_ratio == null) return null
  const ch = data.change_4w_pp ?? 0
  const chColor = ch > 0.5 ? 'text-red-400' : ch < -0.5 ? 'text-green-400' : 'text-slate-400'
  return (
    <div className="border border-slate-700 rounded-lg p-3">
      <p className="text-xs text-slate-500 uppercase mb-1">🌏 外資持股比率（集保）</p>
      <div className="flex items-baseline gap-3">
        <span className="text-xl font-bold text-slate-100 font-mono">{data.foreign_ratio.toFixed(2)}%</span>
        {data.change_4w_pp != null && (
          <span className={`text-xs font-mono ${chColor}`}>
            近 4 週 {ch >= 0 ? '+' : ''}{ch} pp
          </span>
        )}
      </div>
      {data.note && <p className="text-xs text-slate-500 mt-1">{data.note}</p>}
    </div>
  )
}

function MarginShortSection({ symbol }: { symbol: string }) {
  const [data, setData] = useState<MarginShort | null>(null)
  useEffect(() => {
    let cancelled = false
    api.marginShort(symbol, 10).then(r => {
      if (!cancelled) setData(r.latest ?? null)
    }).catch(() => {})
    return () => { cancelled = true }
  }, [symbol])

  if (!data) return null
  return (
    <div className="border border-slate-700 rounded-lg p-3">
      <p className="text-xs text-slate-500 uppercase mb-2">💳 融資融券餘額（{data.date}）</p>
      <div className="grid grid-cols-2 gap-3 text-sm">
        <div>
          <p className="text-xs text-slate-500">融資（散戶買進）</p>
          <p className="font-mono font-bold text-slate-100">{data.margin_balance.toLocaleString()} 張</p>
          <p className={`text-xs font-mono ${data.margin_change >= 0 ? 'text-red-400' : 'text-green-400'}`}>
            日變化 {data.margin_change >= 0 ? '+' : ''}{data.margin_change.toLocaleString()}
          </p>
        </div>
        <div>
          <p className="text-xs text-slate-500">融券（散戶放空）</p>
          <p className="font-mono font-bold text-slate-100">{data.short_balance.toLocaleString()} 張</p>
          <p className={`text-xs font-mono ${data.short_change >= 0 ? 'text-green-400' : 'text-red-400'}`}>
            日變化 {data.short_change >= 0 ? '+' : ''}{data.short_change.toLocaleString()}
          </p>
        </div>
      </div>
    </div>
  )
}

function SecLendSection({ symbol }: { symbol: string }) {
  const [data, setData] = useState<SecLend | null>(null)
  useEffect(() => {
    let cancelled = false
    api.securitiesLending(symbol, 10).then(r => {
      if (!cancelled) setData(r.latest ?? null)
    }).catch(() => {})
    return () => { cancelled = true }
  }, [symbol])

  if (!data) return null
  return (
    <div className="border border-slate-700 rounded-lg p-3">
      <p className="text-xs text-slate-500 uppercase mb-1">📉 借券賣出（外資放空，{data.date}）</p>
      <div className="flex items-baseline gap-3">
        <span className="text-lg font-bold text-slate-100 font-mono">{data.volume.toLocaleString()} 張</span>
        <span className="text-xs text-slate-500">手續費率 {data.avg_fee_rate}%</span>
      </div>
      <p className="text-[10px] text-slate-600 mt-1">借券量 ↑ 通常代表機構建立空單；費率 ↑ 代表借不到（軋空風險高）</p>
    </div>
  )
}

export default function ChipPanel({ data, symbol }: { data: ChipResponse | null; symbol?: string }) {
  if (!data && !symbol) return null
  const { foreign, trust, dealer, total_today, summary, date } = data ?? {}
  const total = total_today ?? 0

  return (
    <div className="space-y-3">
      {data && (
        <>
          <div className="flex justify-between items-center">
            <p className="text-slate-300 text-sm">{summary}</p>
            <span className="text-xs text-slate-500">{date}</span>
          </div>
          <ChipRow label="外資" today={foreign?.today} cum5d={foreign?.cum_5d} trend={foreign?.trend} />
          <ChipRow label="投信" today={trust?.today} cum5d={trust?.cum_5d} trend={trust?.trend} />
          <ChipRow label="自營商" today={dealer?.today} trend={dealer?.trend} />
          <div className="flex justify-between text-sm border-t border-slate-700 pt-2">
            <span className="text-slate-400">三大合計</span>
            <span className={`font-mono font-bold ${total >= 0 ? 'text-red-400' : 'text-green-400'}`}>
              {total >= 0 ? '+' : ''}{total.toLocaleString()} 張
            </span>
          </div>
        </>
      )}

      {/* 進階籌碼（只對台股數字代碼有資料）*/}
      {symbol && /^\d+$/.test(symbol) && (
        <>
          <ForeignHoldingSection symbol={symbol} />
          <MarginShortSection symbol={symbol} />
          <SecLendSection symbol={symbol} />
        </>
      )}
    </div>
  )
}
