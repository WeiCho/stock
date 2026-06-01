import { useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import PriceChart from './PriceChart'
import { useAsync } from '../hooks/useAsync'
import { api } from '../api'
import type { Bar } from '../types'

// 期貨/商品符號清單 — 與 server/commodities.py 的 SUPPORTED 對齊
// group 為後端分類邏輯值（用於 currency fallback 判斷），groupKey 為 i18n 顯示 key
// labelKey 為 i18n 顯示 key（symbol 代碼本身不翻譯）
const SYMBOLS: { symbol: string; labelKey: string; group: '台股期貨' | '國際商品'; groupKey: string }[] = [
  { symbol: 'TX',     labelKey: 'futures.symbol.TX',  group: '台股期貨', groupKey: 'futures.group.tw_futures' },
  { symbol: 'MTX',    labelKey: 'futures.symbol.MTX', group: '台股期貨', groupKey: 'futures.group.tw_futures' },
  { symbol: 'TE',     labelKey: 'futures.symbol.TE',  group: '台股期貨', groupKey: 'futures.group.tw_futures' },
  { symbol: 'TF',     labelKey: 'futures.symbol.TF',  group: '台股期貨', groupKey: 'futures.group.tw_futures' },
  { symbol: 'GC',     labelKey: 'futures.symbol.GC',  group: '國際商品', groupKey: 'futures.group.commodities' },
  { symbol: 'CL',     labelKey: 'futures.symbol.CL',  group: '國際商品', groupKey: 'futures.group.commodities' },
  { symbol: 'SI',     labelKey: 'futures.symbol.SI',  group: '國際商品', groupKey: 'futures.group.commodities' },
  { symbol: 'HG',     labelKey: 'futures.symbol.HG',  group: '國際商品', groupKey: 'futures.group.commodities' },
]

// K 線時間框架 — 短週期跟個股頁對齊；長週期保留 perf 摘要用
// tf='intraday' → Yahoo 5min 盤中 K（FinMind 期貨無 intraday）
// 其他短週期（3d/5d/1w/2w/3w）→ 後端從日線 resample
// id 為穩定 React key；labelKey 為 i18n 顯示 key
const RANGES: { id: string; labelKey: string; tf: string; days: number }[] = [
  { id: 'intraday', labelKey: 'futures.range.intraday', tf: 'intraday', days: 1 },
  { id: '3d',  labelKey: 'futures.range.3d',  tf: '3d',  days: 60 },
  { id: '5d',  labelKey: 'futures.range.5d',  tf: '5d',  days: 90 },
  { id: '1w',  labelKey: 'futures.range.1w',  tf: '1w',  days: 180 },
  { id: '2w',  labelKey: 'futures.range.2w',  tf: '2w',  days: 365 },
  { id: '3w',  labelKey: 'futures.range.3w',  tf: '3w',  days: 540 },
  { id: '1mo', labelKey: 'futures.range.1mo', tf: '1mo', days: 365 },
  { id: '3mo', labelKey: 'futures.range.3mo', tf: '1d',  days: 90 },
  { id: '6mo', labelKey: 'futures.range.6mo', tf: '1d',  days: 180 },
  { id: 'ytd', labelKey: 'futures.range.ytd', tf: '1d',  days: 365 },
  { id: '1y',  labelKey: 'futures.range.1y',  tf: '1d',  days: 365 },
  { id: '5y',  labelKey: 'futures.range.5y',  tf: '1d',  days: 1825 },
  { id: '10y', labelKey: 'futures.range.10y', tf: '1d',  days: 3650 },
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
  const { t } = useTranslation()
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
  // 用對應符號的「該來源預設幣別」當 fallback（503 時不再硬寫 TWD 誤導國際商品）
  const symbolMeta = SYMBOLS.find(s => s.symbol === symbol)
  const fallbackCcy = symbolMeta?.group === '台股期貨' ? 'TWD' : 'USD'
  const currency = price.data?.currency ?? fallbackCcy

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
            <span className="text-xs text-slate-500 w-16 shrink-0">{t(items[0].groupKey)}</span>
            {items.map(s => (
              <button key={s.symbol} onClick={() => setSymbol(s.symbol)}
                className={`text-xs px-3 py-1 rounded-full ${symbol === s.symbol
                  ? 'bg-blue-600 text-white'
                  : 'bg-slate-800 text-slate-400 hover:bg-slate-700'}`}>
                {t(s.labelKey)} <span className="text-[10px] opacity-60">{s.symbol}</span>
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
            {price.data?.label} ({symbol}) · {t('futures.last_updated')} {price.data?.data?.at(-1)?.date ?? '—'}
          </span>
        </div>

        {/* 走勢區間：當日 / 3日 / 5日 / 週系列 / 月 / 長線 */}
        <div className="flex flex-wrap gap-1 mt-2">
          {RANGES.map((r, i) => (
            <button key={r.id} onClick={() => setRangeIdx(i)}
              className={`text-xs px-2.5 py-0.5 rounded ${rangeIdx === i
                ? 'bg-blue-600 text-white'
                : 'bg-slate-800 text-slate-400 hover:bg-slate-700'}`}>
              {t(r.labelKey)}
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
      {price.loading && <p className="text-slate-500 text-sm">{t('common.loading')}</p>}
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
          <h3 className="text-sm font-semibold text-slate-300 mb-2">{t('futures.inst.title')}</h3>
          <table className="w-full text-xs">
            <thead>
              <tr className="text-slate-500 border-b border-slate-700">
                <th className="text-left py-1.5 pr-3">{t('futures.inst.col_date')}</th>
                <th className="text-right pr-3">{t('futures.inst.col_foreign')}</th>
                <th className="text-right pr-3">{t('futures.inst.col_trust')}</th>
                <th className="text-right">{t('futures.inst.col_dealer')}</th>
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
            {t('futures.inst.note')}
          </p>
        </div>
      )}
    </div>
  )
}
