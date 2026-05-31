import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { api } from '../api'
import { isTradingHours } from '../lib/charts'

type Level = { price: number; size: number }
type Quote = {
  symbol: string
  last?: number
  previousClose?: number
  open?: number
  high?: number
  low?: number
  avg?: number
  change?: number
  change_pct?: number
  volume?: number
  bids?: Level[]
  asks?: Level[]
  time?: string
}

const fmt = (n?: number | null, d = 2) => (n === undefined || n === null ? '—' : n.toFixed(d))

// 個股 / ETF 即時報價（Fugle）。每 3 秒輪詢（交易時段才打，避開 Fugle 免費 60 次/分鐘上限），
// 非交易時段顯示最後一盤。ETF 與一般個股同一組 endpoint，無需特殊處理。
// 美股（非台股）Fugle 無資料 → quote 回失敗 → 本元件自動隱藏。
export default function LiveQuote({ symbol }: { symbol: string }) {
  const { t } = useTranslation()
  const [q, setQ] = useState<Quote | null>(null)

  useEffect(() => {
    let active = true
    setQ(null)
    const tick = () =>
      api.stockQuote(symbol).then(d => { if (active) setQ(d) }).catch(() => {})
    tick()
    const id = setInterval(() => { if (isTradingHours()) tick() }, 3000)
    return () => { active = false; clearInterval(id) }
  }, [symbol])

  if (!q || q.last === undefined || q.last === null) return null

  const up = (q.change ?? 0) >= 0
  const color = up ? 'text-red-400' : 'text-green-400'
  const sign = up ? '+' : ''
  const bids = (q.bids ?? []).slice(0, 5)
  const asks = (q.asks ?? []).slice(0, 5)
  const maxSize = Math.max(1, ...bids.map(l => l.size || 0), ...asks.map(l => l.size || 0))

  return (
    <div className="bg-slate-900 border border-slate-700 rounded-xl p-4">
      <div className="flex items-end flex-wrap gap-x-8 gap-y-3">
        {/* 成交價 + 漲跌 */}
        <div>
          <div className="flex items-baseline gap-2">
            <span className={`text-3xl font-bold ${color}`}>{fmt(q.last)}</span>
            <span className={`text-sm font-medium ${color}`}>
              {sign}{fmt(q.change)} ({sign}{fmt(q.change_pct)}%)
            </span>
          </div>
          <div className="text-xs text-slate-500 mt-1 flex items-center gap-1.5">
            <span className="inline-block w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
            {t('quote.live')}
            {q.time && <span className="text-slate-600">· {q.time}</span>}
          </div>
        </div>
        {/* OHLC + 量 */}
        <div className="grid grid-cols-3 gap-x-5 gap-y-1 text-xs text-slate-400">
          <span>{t('quote.open')} <b className="text-slate-200">{fmt(q.open)}</b></span>
          <span>{t('quote.high')} <b className="text-red-300">{fmt(q.high)}</b></span>
          <span>{t('quote.low')} <b className="text-green-300">{fmt(q.low)}</b></span>
          <span>{t('quote.prev_close')} <b className="text-slate-200">{fmt(q.previousClose)}</b></span>
          <span>{t('quote.avg')} <b className="text-slate-200">{fmt(q.avg)}</b></span>
          <span>{t('quote.volume')} <b className="text-slate-200">{q.volume ?? '—'}</b></span>
        </div>
      </div>

      {/* 五檔 */}
      {(bids.length > 0 || asks.length > 0) && (
        <div className="mt-3 pt-3 border-t border-slate-800">
          <div className="text-[10px] uppercase tracking-wide text-slate-500 mb-1">{t('quote.five_levels')}</div>
          <div className="grid grid-cols-2 gap-x-4 text-xs">
            {/* 買 */}
            <div className="space-y-0.5">
              {bids.map((l, i) => (
                <div key={i} className="relative flex justify-between px-1.5 py-0.5 rounded overflow-hidden">
                  <div className="absolute inset-y-0 right-0 bg-red-500/10" style={{ width: `${((l.size || 0) / maxSize) * 100}%` }} />
                  <span className="relative text-slate-500">{t('quote.bid')}</span>
                  <span className="relative text-red-300">{fmt(l.price)}</span>
                  <span className="relative text-slate-400">{l.size ?? '—'}</span>
                </div>
              ))}
            </div>
            {/* 賣 */}
            <div className="space-y-0.5">
              {asks.map((l, i) => (
                <div key={i} className="relative flex justify-between px-1.5 py-0.5 rounded overflow-hidden">
                  <div className="absolute inset-y-0 right-0 bg-green-500/10" style={{ width: `${((l.size || 0) / maxSize) * 100}%` }} />
                  <span className="relative text-slate-500">{t('quote.ask')}</span>
                  <span className="relative text-green-300">{fmt(l.price)}</span>
                  <span className="relative text-slate-400">{l.size ?? '—'}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
