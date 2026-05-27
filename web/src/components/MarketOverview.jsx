import { useEffect, useRef, useState } from 'react'
import { createChart, AreaSeries } from 'lightweight-charts'
import { api } from '../api'

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
    const line = chart.addSeries(AreaSeries, { lineColor: '#38bdf8', topColor: 'rgba(56,189,248,0.2)', bottomColor: 'transparent', lineWidth: 2 })
    line.setData(data.map(r => ({ time: r.date, value: r.close })))
    chart.timeScale().fitContent()
    const obs = new ResizeObserver(() => chart.applyOptions({ width: ref.current.clientWidth }))
    obs.observe(ref.current)
    return () => { obs.disconnect(); chart.remove() }
  }, [data])
  return <div ref={ref} className="w-full rounded-lg overflow-hidden" />
}

// 台股慣例：紅漲（正）、綠跌（負）
const sign = (n) => (n >= 0 ? 'text-red-400' : 'text-green-400')
const fmtLots = (n) => (n >= 0 ? '+' : '') + Math.round(n).toLocaleString()
const fmtPct = (v) => (v == null ? '—' : `${v >= 0 ? '+' : ''}${v.toFixed(2)}%`)
const fmtIdx = (v) => (v == null ? '—' : v.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }))
const fmtDate = (d) => (d && d.length === 8 ? `${d.slice(0, 4)}-${d.slice(4, 6)}-${d.slice(6, 8)}` : d)
const fmtTurnover = (n) => (n == null ? '—' : n >= 1e12 ? `${(n / 1e12).toFixed(2)} 兆` : `${Math.round(n / 1e8).toLocaleString()} 億`)

function FlowTile({ label, value }) {
  return (
    <div className="bg-slate-800 rounded-lg p-3 text-center">
      <p className="text-xs text-slate-500 mb-1">{label}</p>
      <p className={`text-base sm:text-lg font-bold font-mono ${sign(value)}`}>{fmtLots(value)}</p>
      <p className="text-[10px] text-slate-600">張</p>
    </div>
  )
}

function RankTable({ title, rows, field, onSelect }) {
  if (!rows?.length) return null
  return (
    <div>
      <p className="text-xs text-slate-500 uppercase mb-2">{title}</p>
      <table className="w-full text-xs">
        <tbody>
          {rows.map(r => (
            <tr key={r.symbol} onClick={() => onSelect?.(r.symbol)}
              className="border-b border-slate-800 cursor-pointer hover:bg-slate-800/60">
              <td className="py-1 text-blue-300 font-mono">{r.symbol}</td>
              <td className="py-1 text-slate-400 truncate max-w-[8rem]">{r.name}</td>
              <td className={`py-1 text-right font-mono ${sign(r[field])}`}>{fmtLots(r[field])}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function SectorList({ title, rows }) {
  if (!rows?.length) return null
  return (
    <div>
      <p className="text-xs text-slate-500 mb-1">{title}</p>
      <table className="w-full text-xs">
        <tbody>
          {rows.map(s => (
            <tr key={s.industry} className="border-b border-slate-800">
              <td className="py-1 text-slate-300">{s.industry}</td>
              <td className="py-1 text-slate-600 text-right pr-2">{s.count}檔</td>
              <td className={`py-1 text-right font-mono ${sign(s.total)}`}>{fmtLots(s.total)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

const RANGES = [['3日', 3], ['1月', 30], ['3月', 90], ['6月', 180], ['1年', 365], ['5年', 1825]]

export default function MarketOverview({ moneyFlow, onSelectStock }) {
  // 指數走勢：依選擇的時間區間抓取（指數歷史已用 FinMind 補滿約 5 年）
  const [days, setDays] = useState(180)
  const [index, setIndex] = useState(null)
  useEffect(() => {
    let active = true
    setIndex(null)
    api.marketIndex(days).then(d => { if (active) setIndex(d) }).catch(() => {})
    return () => { active = false }
  }, [days])

  const data = index?.data || []
  const latest = data.at(-1)
  const prev = data.at(-2)
  const chgN = (n) => (data.length > n ? ((latest.close - data.at(-1 - n).close) / data.at(-1 - n).close * 100) : null)
  const chg5 = chgN(5)
  const chg20 = chgN(20)

  // 即時加權指數：每 20 秒輪詢（盤中跳動，非交易時段為最後狀態）
  const [live, setLive] = useState(null)
  useEffect(() => {
    let active = true
    const tick = () => api.indexLive().then(d => { if (active) setLive(d) }).catch(() => {})
    tick()
    const id = setInterval(tick, 20000)
    return () => { active = false; clearInterval(id) }
  }, [])

  // 今日大單敲進（Fugle 逐筆，盤中每 60 秒更新）
  const [bigOrders, setBigOrders] = useState(null)
  useEffect(() => {
    let active = true
    const tick = () => api.bigOrders().then(d => { if (active) setBigOrders(d) }).catch(() => {})
    tick()
    const id = setInterval(tick, 60000)
    return () => { active = false; clearInterval(id) }
  }, [])

  // 即時優先，取不到則退回日線收盤
  const idxVal = live?.index ?? latest?.close
  const chgPts = live?.change ?? (latest && prev ? latest.close - prev.close : null)
  const chgPct = live?.change_pct ?? (latest && prev ? (latest.close - prev.close) / prev.close * 100 : null)

  return (
    <div className="space-y-5">
      {/* 今日大單敲進（Fugle 逐筆，盤中即時） */}
      {bigOrders?.available && bigOrders.orders?.length > 0 && (
        <div className="bg-amber-950/40 border border-amber-800/50 rounded-lg p-3">
          <p className="text-xs text-amber-400 uppercase mb-2">🔥 今日大單敲進（單筆大額成交，盤中即時）</p>
          <div className="flex flex-wrap gap-2">
            {bigOrders.orders.map(o => (
              <button key={o.symbol} onClick={() => onSelectStock?.(o.symbol)}
                className="text-xs px-2 py-1 rounded bg-slate-800 hover:bg-slate-700">
                <span className="text-amber-300 font-medium">{o.name}</span>
                <span className="text-slate-500 ml-1 font-mono">{o.symbol}</span>
                <span className="text-slate-300 ml-1 font-mono">{o.max_size}張@{o.price}</span>
                <span className="text-amber-400 ml-1 font-mono">{(o.max_amount / 1e8).toFixed(2)}億</span>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* 大盤走勢（即時） */}
      <div>
        <div className="flex items-baseline gap-3 flex-wrap">
          <span className="text-2xl font-bold text-slate-100 font-mono">{fmtIdx(idxVal)}</span>
          {chgPct != null && (
            <span className={`text-sm font-medium ${sign(chgPct)}`}>
              {chgPct >= 0 ? '▲' : '▼'} {Math.abs(chgPts ?? 0).toFixed(2)} ({Math.abs(chgPct).toFixed(2)}%)
            </span>
          )}
          {live?.time ? (
            <span className="text-xs text-emerald-400 flex items-center gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
              加權指數 {fmtDate(live.date)} {live.time}
            </span>
          ) : (
            <span className="text-xs text-slate-500">加權指數 {latest?.date}</span>
          )}
          <span className="text-xs text-slate-500 ml-auto">
            近5日 <b className={sign(chg5 ?? 0)}>{fmtPct(chg5)}</b>
            <span className="mx-1">·</span>
            近20日 <b className={sign(chg20 ?? 0)}>{fmtPct(chg20)}</b>
          </span>
        </div>
        <div className="flex flex-wrap gap-1 mt-2">
          {RANGES.map(([label, d]) => (
            <button key={d} onClick={() => setDays(d)}
              className={`text-xs px-2 py-0.5 rounded ${days === d ? 'bg-blue-600 text-white' : 'bg-slate-800 text-slate-400 hover:bg-slate-700'}`}>
              {label}
            </button>
          ))}
        </div>
        <div className="mt-2"><IndexChart data={data} /></div>
      </div>

      {/* 盤後市場概況（成交金額、漲跌家數、三大法人；皆為收盤後資料，無官方即時版） */}
      {moneyFlow?.summary && (
        <div className="space-y-3">
          <p className="text-xs text-slate-500 uppercase">
            盤後市場概況 · {moneyFlow.date}（收盤後資料）
          </p>

          {moneyFlow.market_stats && (moneyFlow.market_stats.turnover != null || moneyFlow.market_stats.up != null) && (
            <div className="flex flex-wrap items-center gap-x-6 gap-y-1 text-sm bg-slate-800/50 rounded-lg px-3 py-2">
              {moneyFlow.market_stats.turnover != null && (
                <span className="text-slate-400">成交金額 <b className="text-slate-100 font-mono">{fmtTurnover(moneyFlow.market_stats.turnover)}</b></span>
              )}
              {moneyFlow.market_stats.up != null && (
                <span className="text-slate-400">
                  漲跌家數
                  <b className="text-red-400 font-mono ml-1">▲{moneyFlow.market_stats.up}</b>
                  <b className="text-green-400 font-mono ml-1">▼{moneyFlow.market_stats.down}</b>
                  <span className="text-slate-500 font-mono ml-1">→{moneyFlow.market_stats.unchanged}</span>
                </span>
              )}
            </div>
          )}

          <p className="text-xs text-slate-500">三大法人買賣超（張，資料來源 TWSE 上市）</p>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
            <FlowTile label="外資" value={moneyFlow.summary.foreign} />
            <FlowTile label="投信" value={moneyFlow.summary.trust} />
            <FlowTile label="自營商" value={moneyFlow.summary.dealer} />
            <FlowTile label="三大法人合計" value={moneyFlow.summary.total} />
          </div>

          {moneyFlow.sector_flow?.inflow?.length > 0 && (
            <div>
              <p className="text-xs text-slate-500 uppercase mb-2 mt-1">類股資金流向（三大法人淨買賣超，張）</p>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <SectorList title="資金流入類股" rows={moneyFlow.sector_flow.inflow} />
                <SectorList title="資金流出類股" rows={moneyFlow.sector_flow.outflow} />
              </div>
            </div>
          )}

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <RankTable title="外資買超" rows={moneyFlow.foreign_buy} field="foreign" onSelect={onSelectStock} />
            <RankTable title="外資賣超" rows={moneyFlow.foreign_sell} field="foreign" onSelect={onSelectStock} />
            <RankTable title="投信買超" rows={moneyFlow.trust_buy} field="trust" onSelect={onSelectStock} />
            <RankTable title="投信賣超" rows={moneyFlow.trust_sell} field="trust" onSelect={onSelectStock} />
          </div>
        </div>
      )}
    </div>
  )
}
