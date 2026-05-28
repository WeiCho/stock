import { useMemo, useState } from 'react'
import PriceChart from './PriceChart'
import { useAsync } from '../hooks/useAsync'
import { api } from '../api'
import type { Bar } from '../types'

// 期貨/商品符號清單 — 與 server/commodities.py 的 SUPPORTED 對齊
const SYMBOLS: { symbol: string; label: string; group: '台股期貨' | '國際商品' }[] = [
  { symbol: 'TX',     label: '台指期',   group: '台股期貨' },
  { symbol: 'MTX',    label: '小台',     group: '台股期貨' },
  { symbol: 'TE',     label: '電子期',   group: '台股期貨' },
  { symbol: 'TF',     label: '金融期',   group: '台股期貨' },
  { symbol: 'GC',     label: '黃金',     group: '國際商品' },
  { symbol: 'XAUUSD', label: '黃金現貨', group: '國際商品' },
  { symbol: 'CL',     label: '原油 WTI', group: '國際商品' },
  { symbol: 'SI',     label: '白銀',     group: '國際商品' },
  { symbol: 'HG',     label: '銅',       group: '國際商品' },
]

// K 線時間框架 — 短週期跟個股頁對齊；長週期保留 perf 摘要用
// tf='intraday' → Yahoo 5min 盤中 K（FinMind 期貨無 intraday）
// 其他短週期（3d/5d/1w/2w/3w）→ 後端從日線 resample
const RANGES: { label: string; tf: string; days: number }[] = [
  { label: '當日', tf: 'intraday', days: 1 },
  { label: '3日',  tf: '3d',  days: 60 },
  { label: '5日',  tf: '5d',  days: 90 },
  { label: '1週',  tf: '1w',  days: 180 },
  { label: '2週',  tf: '2w',  days: 365 },
  { label: '3週',  tf: '3w',  days: 540 },
  { label: '1月',  tf: '1mo', days: 365 },
  { label: '3月',  tf: '1d',  days: 90 },
  { label: '6月',  tf: '1d',  days: 180 },
  { label: 'YTD',  tf: '1d',  days: 365 },
  { label: '1年',  tf: '1d',  days: 365 },
  { label: '5年',  tf: '1d',  days: 1825 },
  { label: '10年', tf: '1d',  days: 3650 },
]

interface CommodityResponse {
  symbol: string
  label: string
  data: Bar[]
  previousClose?: number
  currency?: string
  regularMarketPrice?: number
  perf?: Record<string, number>
}

interface InstResponse {
  symbol: string
  label: string
  data: { date: string; foreign_net?: number; trust_net?: number; dealer_net?: number }[]
}

function PerfChip({ label, value }: { label: string; value?: number }) {
  if (value == null) return null
  const color = value >= 0 ? 'text-red-400' : 'text-green-400'
  return (
    <div className="bg-slate-800/60 rounded-lg px-3 py-1.5 text-center min-w-[78px]">
      <p className="text-[10px] text-slate-500 uppercase">{label}</p>
      <p className={`text-sm font-mono font-bold ${color}`}>
        {value >= 0 ? '+' : ''}{value.toFixed(2)}%
      </p>
    </div>
  )
}

export default function FuturesPanel() {
  const [symbol, setSymbol] = useState('TX')
  const [rangeIdx, setRangeIdx] = useState(10)  // 預設 1年（index 10）
  const range = RANGES[rangeIdx]

  const price = useAsync<CommodityResponse>(
    () => api.commodity(symbol, range.days, range.tf) as Promise<CommodityResponse>,
    [symbol, range.tf, range.days],
  )

  // 台股期貨才抓三大法人留倉
  const isTwFutures = ['TX', 'MTX', 'TE', 'TF'].includes(symbol)
  const inst = useAsync<InstResponse>(
    () => isTwFutures
      ? api.futuresInstitutional(symbol, 30) as Promise<InstResponse>
      : Promise.resolve({ symbol, label: '', data: [] }),
    [symbol],
  )

  const latestPrice = price.data?.regularMarketPrice ?? price.data?.data?.at(-1)?.close
  const prevClose = price.data?.previousClose
  const change = (latestPrice != null && prevClose != null) ? latestPrice - prevClose : null
  const changePct = (change != null && prevClose) ? (change / prevClose) * 100 : null
  const currency = price.data?.currency ?? 'TWD'

  // 依分類分組 symbol 選單
  const groups = useMemo(() => {
    const acc: Record<string, typeof SYMBOLS> = {}
    SYMBOLS.forEach(s => { (acc[s.group] ||= []).push(s) })
    return acc
  }, [])

  const sign = (n?: number) => (n == null ? 'text-slate-400' : n >= 0 ? 'text-red-400' : 'text-green-400')

  return (
    <div className="space-y-5">
      {/* 符號選單（依台股期貨 / 國際商品分組） */}
      <div className="space-y-2">
        {Object.entries(groups).map(([group, items]) => (
          <div key={group} className="flex flex-wrap items-center gap-2">
            <span className="text-xs text-slate-500 w-16 shrink-0">{group}</span>
            {items.map(s => (
              <button key={s.symbol} onClick={() => setSymbol(s.symbol)}
                className={`text-xs px-3 py-1 rounded-full ${symbol === s.symbol
                  ? 'bg-blue-600 text-white'
                  : 'bg-slate-800 text-slate-400 hover:bg-slate-700'}`}>
                {s.label} <span className="text-[10px] opacity-60">{s.symbol}</span>
              </button>
            ))}
          </div>
        ))}
      </div>

      {/* 現價 + 漲跌 */}
      <div>
        <div className="flex items-baseline gap-3 flex-wrap">
          <span className="text-3xl font-bold text-slate-100 font-mono">
            {latestPrice != null ? latestPrice.toLocaleString(undefined, { maximumFractionDigits: 2 }) : '—'}
          </span>
          <span className="text-xs text-slate-500">{currency}</span>
          {change != null && changePct != null && (
            <span className={`text-sm font-medium ${sign(change)}`}>
              {change >= 0 ? '▲' : '▼'} {Math.abs(change).toFixed(2)} ({Math.abs(changePct).toFixed(2)}%)
            </span>
          )}
          <span className="text-xs text-slate-500 ml-2">
            {price.data?.label} ({symbol}) · 最後更新 {price.data?.data?.at(-1)?.date ?? '—'}
          </span>
        </div>

        {/* 走勢區間：當日 / 3日 / 5日 / 週系列 / 月 / 長線 */}
        <div className="flex flex-wrap gap-1 mt-2">
          {RANGES.map((r, i) => (
            <button key={r.label} onClick={() => setRangeIdx(i)}
              className={`text-xs px-2.5 py-0.5 rounded ${rangeIdx === i
                ? 'bg-blue-600 text-white'
                : 'bg-slate-800 text-slate-400 hover:bg-slate-700'}`}>
              {r.label}
            </button>
          ))}
        </div>
      </div>

      {/* 績效摘要（仿 TradingView XAUUSD perf 表） */}
      {price.data?.perf && (
        <div className="flex flex-wrap gap-2">
          {(['1d', '5d', '1mo', '6mo', 'ytd', '1y', '5y', '10y'] as const).map(k => (
            <PerfChip key={k} label={k.toUpperCase()} value={price.data?.perf?.[k]} />
          ))}
        </div>
      )}

      {/* K 線圖（重用 PriceChart；非盤中模式自動帶 RSI/KDJ 副圖 + MACD/KDJ markers） */}
      {price.error && <p className="text-red-400 text-sm">{price.error}</p>}
      {price.loading && <p className="text-slate-500 text-sm">載入中…</p>}
      {price.data?.data && price.data.data.length > 0 && (
        <PriceChart
          key={`${symbol}-${range.tf}-${range.days}`}
          data={price.data.data}
          intraday={range.tf === 'intraday'}
          previousClose={range.tf === 'intraday' ? (price.data.previousClose ?? null) : null}
        />
      )}

      {/* 期貨三大法人留倉淨口數 */}
      {isTwFutures && inst.data?.data && inst.data.data.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-slate-300 mb-2">三大法人留倉（淨口數，近 30 天）</h3>
          <table className="w-full text-xs">
            <thead>
              <tr className="text-slate-500 border-b border-slate-700">
                <th className="text-left py-1.5 pr-3">日期</th>
                <th className="text-right pr-3">外資</th>
                <th className="text-right pr-3">投信</th>
                <th className="text-right">自營商</th>
              </tr>
            </thead>
            <tbody>
              {inst.data.data.slice(-15).reverse().map(r => (
                <tr key={r.date} className="border-b border-slate-800">
                  <td className="py-1 pr-3 text-slate-400">{r.date}</td>
                  <td className={`text-right pr-3 font-mono ${sign(r.foreign_net)}`}>
                    {r.foreign_net != null ? (r.foreign_net >= 0 ? '+' : '') + r.foreign_net.toLocaleString() : '—'}
                  </td>
                  <td className={`text-right pr-3 font-mono ${sign(r.trust_net)}`}>
                    {r.trust_net != null ? (r.trust_net >= 0 ? '+' : '') + r.trust_net.toLocaleString() : '—'}
                  </td>
                  <td className={`text-right font-mono ${sign(r.dealer_net)}`}>
                    {r.dealer_net != null ? (r.dealer_net >= 0 ? '+' : '') + r.dealer_net.toLocaleString() : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="text-xs text-slate-600 mt-2">
            淨口數 = 未平倉多單 − 空單口數；正值偏多、負值偏空。資料來源 FinMind。
          </p>
        </div>
      )}
    </div>
  )
}
