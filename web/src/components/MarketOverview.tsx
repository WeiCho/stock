import { useEffect, useRef, useState } from 'react'
import { createChart, AreaSeries, BaselineSeries, LineSeries } from 'lightweight-charts'
import { api } from '../api'
import type { Bar, BigOrder, MoneyFlowResponse, RankRow, SectorRow } from '../types'
import { toTime, isTradingHours, SESSION_MINUTES } from '../lib/charts'

function IndexChart({ data, intraday, previousClose }: { data?: Bar[]; intraday?: boolean; previousClose?: number | null }) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const el = ref.current
    if (!el || !data?.length) return
    const chart = createChart(el, {
      layout: { background: { color: '#1a1d2e' }, textColor: '#94a3b8' },
      grid: { vertLines: { color: '#1e2235' }, horzLines: { color: '#1e2235' } },
      rightPriceScale: { borderColor: '#2e3347' },
      timeScale: {
        borderColor: '#2e3347',
        timeVisible: !!intraday,
        secondsVisible: false,
        // 盤中只標小時（09 10 11 12 13）；其他模式維持預設日期格式
        tickMarkFormatter: intraday
          ? (t: number) => {
              const d = new Date((t as number) * 1000)
              const hh = d.toLocaleString('en-US', { timeZone: 'Asia/Taipei', hour: '2-digit', hour12: false })
              const mm = d.toLocaleString('en-US', { timeZone: 'Asia/Taipei', minute: '2-digit' })
              return mm === '00' ? hh : `${hh}:${mm.padStart(2, '0')}`
            }
          : undefined,
      },
      width: el.clientWidth,
      height: 200,
    })

    // 盤中且有昨收 → 用 BaselineSeries（昨收之上紅+紅填、之下綠+綠填，台股慣例）
    // 否則退回單色 Area（歷史日線多空都正常）
    const line = (intraday && previousClose != null)
      ? chart.addSeries(BaselineSeries, {
          baseValue: { type: 'price', price: previousClose },
          topLineColor: '#ef4444',
          topFillColor1: 'rgba(239,68,68,0.28)',
          topFillColor2: 'rgba(239,68,68,0.04)',
          bottomLineColor: '#22c55e',
          bottomFillColor1: 'rgba(34,197,94,0.04)',
          bottomFillColor2: 'rgba(34,197,94,0.28)',
          lineWidth: 2,
          priceLineVisible: false,
        })
      : chart.addSeries(AreaSeries, {
          lineColor: '#38bdf8',
          topColor: 'rgba(56,189,248,0.2)',
          bottomColor: 'transparent',
          lineWidth: 2,
          priceLineVisible: false,
        })
    line.setData(data.map(r => ({ time: toTime(r.date), value: r.close })))

    // 盤中均價線（Fugle 已提供 r.average）
    if (intraday && data.some(r => r.average != null)) {
      const avg = chart.addSeries(LineSeries, {
        color: '#fbbf24', lineWidth: 1, priceLineVisible: false, lastValueVisible: false,
      })
      avg.setData(data.filter(r => r.average != null).map(r => ({ time: toTime(r.date), value: r.average })))
    }

    // 前收參考線（盤中）
    if (intraday && previousClose != null) {
      line.createPriceLine({
        price: previousClose,
        color: '#64748b',
        lineWidth: 1,
        lineStyle: 2, // Dashed
        axisLabelVisible: true,
        title: '昨收',
      })
    }

    // 盤中：在實際資料後補上空 bar slot 直到收盤（09:00–13:30 共 270 分鐘）。
    // v5 的 setVisibleRange 會 clamp 到有資料的時間點，無法直接延伸；改用 rightOffset
    // 補空 slot，X 軸的 tickMarkFormatter 會自動 render 11:00 / 12:00 / 13:00 等時間標記。
    if (intraday && data.length >= 2) {
      const dt = (new Date(data[1].date).getTime() - new Date(data[0].date).getTime()) / 60000
      if (dt > 0) {
        const expected = Math.round(SESSION_MINUTES / dt)  // 09:00–13:30
        chart.timeScale().applyOptions({ rightOffset: Math.max(0, expected - data.length) })
      }
    }
    chart.timeScale().fitContent()

    const obs = new ResizeObserver(() => chart.applyOptions({ width: el.clientWidth }))
    obs.observe(el)
    return () => { obs.disconnect(); chart.remove() }
  }, [data, intraday, previousClose])
  return <div ref={ref} className="w-full rounded-lg overflow-hidden" />
}

// 台股慣例：紅漲（正）、綠跌（負）
const sign = (n: number) => (n >= 0 ? 'text-red-400' : 'text-green-400')
const fmtLots = (n: number) => (n >= 0 ? '+' : '') + Math.round(n).toLocaleString()
const fmtPct = (v: number | null | undefined) => (v == null ? '—' : `${v >= 0 ? '+' : ''}${v.toFixed(2)}%`)
const fmtIdx = (v: number | null | undefined) => (v == null ? '—' : v.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }))
const fmtDate = (d: string | null | undefined) => (d && d.length === 8 ? `${d.slice(0, 4)}-${d.slice(4, 6)}-${d.slice(6, 8)}` : d)
const fmtTurnover = (n: number | null | undefined) => (n == null ? '—' : n >= 1e12 ? `${(n / 1e12).toFixed(2)} 兆` : `${Math.round(n / 1e8).toLocaleString()} 億`)

function FlowTile({ label, value }: { label: string; value: number }) {
  return (
    <div className="bg-slate-800 rounded-lg p-3 text-center">
      <p className="text-xs text-slate-500 mb-1">{label}</p>
      <p className={`text-base sm:text-lg font-bold font-mono ${sign(value)}`}>{fmtLots(value)}</p>
      <p className="text-[10px] text-slate-600">張</p>
    </div>
  )
}

function RankTable({ title, rows, field, onSelect }:
  { title: string; rows?: RankRow[]; field: 'foreign' | 'trust' | 'dealer'; onSelect?: (sym: string) => void }) {
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
              <td className={`py-1 text-right font-mono ${sign(r[field] ?? 0)}`}>{fmtLots(r[field] ?? 0)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function SectorList({ title, rows }: { title: string; rows?: SectorRow[] }) {
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

// 0 = 當日（Fugle 盤中 5 分鐘）；其餘為日線歷史的回溯天數
const RANGES: [string, number][] = [['當日', 0], ['3日', 3], ['1月', 30], ['3月', 90], ['6月', 180], ['1年', 365], ['5年', 1825]]

export default function MarketOverview({ moneyFlow, onSelectStock }:
  { moneyFlow?: MoneyFlowResponse | null; onSelectStock?: (sym: string) => void }) {
  // 指數走勢：依選擇的時間區間抓取；當日 = Fugle IX0001 盤中分鐘 K
  const [days, setDays] = useState(180)
  const [index, setIndex] = useState<any>(null)
  useEffect(() => {
    let active = true
    setIndex(null)
    const p = days === 0 ? api.indexIntraday('5') : api.marketIndex(days)
    p.then(d => { if (active) setIndex(d) }).catch(() => {})
    return () => { active = false }
  }, [days])

  const data = index?.data || []
  const latest = data.at(-1)
  const prev = data.at(-2)
  const chgN = (n: number): number | null => {
    if (data.length <= n || !latest) return null
    const base = data.at(-1 - n)
    if (!base?.close) return null
    return ((latest.close - base.close) / base.close) * 100
  }
  const chg5 = chgN(5)
  const chg20 = chgN(20)

  // 即時加權指數：盤中每秒輪詢；非交易時段（週末、09:00-13:30 以外）保留最後狀態、不再打 API
  const [live, setLive] = useState<any>(null)
  useEffect(() => {
    let active = true
    const tick = () => api.indexLive().then(d => { if (active) setLive(d) }).catch(() => {})
    tick()  // 初次必抓一次，讓非交易時段也能顯示上一盤
    const id = setInterval(() => { if (isTradingHours()) tick() }, 1000)
    return () => { active = false; clearInterval(id) }
  }, [])

  // 今日大單敲進（Fugle 逐筆）：盤中每 60 秒更新（受 Fugle 流量限制，不每秒打）
  const [bigOrders, setBigOrders] = useState<any>(null)
  useEffect(() => {
    let active = true
    const tick = () => api.bigOrders().then(d => { if (active) setBigOrders(d) }).catch(() => {})
    tick()
    const id = setInterval(() => { if (isTradingHours()) tick() }, 60000)
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
            {bigOrders.orders.map((o: BigOrder) => (
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
          {days !== 0 && (
            <span className="text-xs text-slate-500 ml-auto">
              近5日 <b className={sign(chg5 ?? 0)}>{fmtPct(chg5)}</b>
              <span className="mx-1">·</span>
              近20日 <b className={sign(chg20 ?? 0)}>{fmtPct(chg20)}</b>
            </span>
          )}
        </div>
        <div className="flex flex-wrap gap-1 mt-2">
          {RANGES.map(([label, d]) => (
            <button key={d} onClick={() => setDays(d)}
              className={`text-xs px-2 py-0.5 rounded ${days === d ? 'bg-blue-600 text-white' : 'bg-slate-800 text-slate-400 hover:bg-slate-700'}`}>
              {label}
            </button>
          ))}
        </div>
        <div className="mt-2"><IndexChart data={data} intraday={days === 0} previousClose={index?.previousClose ?? null} /></div>
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

          {moneyFlow.sector_flow?.inflow && moneyFlow.sector_flow.inflow.length > 0 && (
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
