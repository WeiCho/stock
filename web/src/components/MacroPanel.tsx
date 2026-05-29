import { useEffect, useState } from 'react'
import { api } from '../api'
import type { Bar } from '../types'

interface YieldCurve { latest: number | null; status: 'normal' | 'flat' | 'inverted' | 'unavailable'; note: string }
interface Pcr { latest: { date: string; pcr_volume: number | null; pcr_oi: number | null; note?: string; volume_category?: string } | null; error?: string }
interface CalEvent { date: string; time: string; country: string; event: string; impact: string; prev?: number | null; estimate?: number | null; actual?: number | null; unit?: string }
interface CalResp { available: boolean; events?: CalEvent[]; count?: number }

/**
 * 總體經濟（Macro）面板：5 層分析框架
 *   1. 總體經濟（Macro）  — 利率、DXY、通膨、GDP、就業
 *   2. 資金流（Liquidity） — 10Y 公債、ETF 流向、央行買金
 *   3. 市場價格（Price Action）— SPX / DXY / XAU / CL / BTC mini-charts
 *   4. 籌碼 / 情緒        — VIX 等
 *   5. 地緣政治（Geopolitics）— 引導至 /global 頁
 *
 * 資料來自 Yahoo Finance（透過後端 /market/commodity/{symbol}/price）；
 * 通膨/GDP/就業需要 FRED API key，未設定先顯示「請設 FRED_API_KEY」。
 */

interface CommodityResp {
  symbol: string
  label: string
  data: Bar[]
  previousClose?: number
  currency?: string
  regularMarketPrice?: number
  perf?: Record<string, number>
}

interface FredIndicator {
  series_id: string
  label: string
  unit: string
  note?: string
  latest_date: string
  latest_value: number
  mom_change_pct?: number | null
  yoy_change_pct?: number | null
}
interface FredSummary { available: boolean; indicators: FredIndicator[] }

async function fetchFredSummary(): Promise<FredSummary> {
  try {
    return await api.macroEconomic()
  } catch {
    return { available: false, indicators: [] }
  }
}

// CPI / PCE 漲算「壞」（紅）；GDP / 就業漲算「好」（綠）；失業率 / Fed Rate 漲算「壞」
// 為了單一規則：「對市場/景氣是利空 → 紅；利多 → 綠」
function fredSign(seriesId: string, pct?: number | null): string {
  if (pct == null) return 'text-slate-400'
  // 通膨/利率/失業率：升高 → 紅（不利股市/黃金壓力）
  const inverted = ['CPIAUCSL', 'PCE', 'UNRATE', 'DFF'].includes(seriesId)
  if (inverted) return pct >= 0 ? 'text-red-400' : 'text-green-400'
  // GDP / 就業：升高 → 綠
  return pct >= 0 ? 'text-green-400' : 'text-red-400'
}

const sign = (n?: number) => (n == null ? 'text-slate-400' : n >= 0 ? 'text-red-400' : 'text-green-400')

// 取得 commodities 端點（容錯版：失敗回 null 而非 throw）
async function fetchSym(sym: string, days = 365): Promise<CommodityResp | null> {
  try {
    return await api.commodity(sym, days) as CommodityResp
  } catch {
    return null
  }
}

function MetricCard({ label, sub, value, change, changePct, currency }:
  { label: string; sub?: string; value?: number; change?: number; changePct?: number; currency?: string }) {
  return (
    <div className="bg-slate-800/50 rounded-lg p-3 border border-slate-700">
      <div className="flex items-baseline justify-between">
        <span className="text-xs text-slate-400">{label}</span>
        {sub && <span className="text-[10px] text-slate-600">{sub}</span>}
      </div>
      <div className="flex items-baseline gap-2 mt-1">
        <span className="text-lg font-bold text-slate-100 font-mono">
          {value != null ? value.toLocaleString(undefined, { maximumFractionDigits: 2 }) : '—'}
        </span>
        {currency && currency !== 'INDEX' && <span className="text-[10px] text-slate-600">{currency}</span>}
      </div>
      {changePct != null && (
        <div className={`text-xs font-mono mt-0.5 ${sign(changePct)}`}>
          {changePct >= 0 ? '▲' : '▼'} {Math.abs(change ?? 0).toFixed(2)} ({Math.abs(changePct).toFixed(2)}%)
        </div>
      )}
    </div>
  )
}

function PerfChip({ label, value }: { label: string; value?: number }) {
  if (value == null) return null
  return (
    <div className="bg-slate-800/40 rounded px-2.5 py-1 text-center min-w-[60px]">
      <p className="text-[10px] text-slate-500">{label}</p>
      <p className={`text-xs font-mono font-bold ${sign(value)}`}>
        {value >= 0 ? '+' : ''}{value.toFixed(1)}%
      </p>
    </div>
  )
}

export default function MacroPanel({ onJumpGlobal }: { onJumpGlobal?: () => void }) {
  const [loading, setLoading] = useState(true)
  const [items, setItems] = useState<Record<string, CommodityResp>>({})
  const [fred, setFred] = useState<FredSummary>({ available: false, indicators: [] })
  const [yc, setYc] = useState<YieldCurve | null>(null)
  const [pcr, setPcr] = useState<Pcr | null>(null)
  const [cal, setCal] = useState<CalResp | null>(null)

  // 一次抓全部需要的標的，並行（Yahoo 商品 + FRED + 殖利率 + PCR + Finnhub 經濟事件）
  useEffect(() => {
    let cancelled = false
    setLoading(true)
    const symbols = ['DXY', 'TNX', 'FVX', 'SPX', 'NDX', 'DJI', 'VIX', 'GC', 'CL', 'SI', 'BTC', 'ETH']
    Promise.all([
      Promise.all(symbols.map(s => fetchSym(s, 365).then(r => [s, r] as const))),
      fetchFredSummary(),
      api.yieldCurve(5).catch(() => null),
      api.futuresPcr(30).catch(() => null),
      api.macroCalendar(30, 'high').catch(() => null),
    ]).then(([yahoo, fredResp, ycResp, pcrResp, calResp]) => {
      if (cancelled) return
      const out: Record<string, CommodityResp> = {}
      for (const [s, r] of yahoo) if (r) out[s] = r
      setItems(out)
      setFred(fredResp)
      setYc(ycResp)
      setPcr(pcrResp)
      setCal(calResp)
      setLoading(false)
    })
    return () => { cancelled = true }
  }, [])

  const get = (sym: string) => {
    const r = items[sym]
    if (!r) return undefined
    const last = r.regularMarketPrice ?? r.data?.at(-1)?.close
    const prev = r.previousClose
    const change = (last != null && prev != null) ? last - prev : undefined
    const changePct = (change != null && prev) ? (change / prev) * 100 : undefined
    return { ...r, last, change, changePct }
  }

  return (
    <div className="space-y-6">
      <header>
        <h2 className="text-xl font-bold text-slate-100">總體經濟 · Macro</h2>
        <p className="text-xs text-slate-500 mt-1">
          5 層分析框架：總體 → 資金流 → 市場價格 → 籌碼情緒 → 地緣政治。
          資料來自 Yahoo Finance{fred.available ? ' + FRED（美國經濟基本面）' : '；通膨/GDP/就業需 FRED API'}。
        </p>
      </header>

      {loading && <p className="text-slate-500 text-sm">載入 12 個指標…</p>}

      {/* ───── 1. 總體經濟 ───── */}
      <section>
        <h3 className="text-sm font-semibold text-amber-300 mb-2">🌍 1. 總體經濟 · 決定大方向</h3>

        {/* 市場面（Yahoo Finance）：利率 / DXY / VIX */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mb-2">
          {([
            { label: '美10Y公債', sub: '^TNX', sym: 'TNX', currency: '%' },
            { label: '美5Y公債', sub: '^FVX', sym: 'FVX', currency: '%' },
            { label: '美元指數', sub: 'DXY', sym: 'DXY', currency: 'INDEX' },
            { label: 'VIX 恐慌', sub: '^VIX', sym: 'VIX', currency: 'INDEX' },
          ] as const).map(c => {
            const r = get(c.sym)
            return <MetricCard key={c.sym} label={c.label} sub={c.sub}
              value={r?.last} change={r?.change} changePct={r?.changePct} currency={c.currency} />
          })}
        </div>

        {/* 經濟基本面（FRED）：CPI / GDP / NFP / 失業率 / Fed Funds */}
        {fred.available ? (
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2">
            {fred.indicators.map(ind => (
              <div key={ind.series_id} className="bg-slate-800/50 rounded-lg p-3 border border-slate-700">
                <div className="flex items-baseline justify-between">
                  <span className="text-xs text-slate-400">{ind.label}</span>
                  <span className="text-[10px] text-slate-600">{ind.series_id}</span>
                </div>
                <p className="text-lg font-bold text-slate-100 font-mono mt-1">
                  {ind.latest_value.toLocaleString(undefined, { maximumFractionDigits: 2 })}
                  <span className="text-[10px] text-slate-600 ml-1">{ind.unit}</span>
                </p>
                <div className="flex gap-2 text-[10px] mt-0.5">
                  <span className="text-slate-500">MoM
                    <b className={`ml-1 font-mono ${fredSign(ind.series_id, ind.mom_change_pct)}`}>
                      {ind.mom_change_pct != null
                        ? `${ind.mom_change_pct >= 0 ? '+' : ''}${ind.mom_change_pct}%`
                        : '—'}
                    </b>
                  </span>
                  <span className="text-slate-500">YoY
                    <b className={`ml-1 font-mono ${fredSign(ind.series_id, ind.yoy_change_pct)}`}>
                      {ind.yoy_change_pct != null
                        ? `${ind.yoy_change_pct >= 0 ? '+' : ''}${ind.yoy_change_pct}%`
                        : '—'}
                    </b>
                  </span>
                </div>
                <p className="text-[10px] text-slate-600 mt-0.5">{ind.latest_date}</p>
              </div>
            ))}
          </div>
        ) : (
          <div className="bg-slate-800/30 border border-dashed border-slate-700 rounded-lg p-3 text-center">
            <p className="text-xs text-slate-500">CPI / GDP / NFP / Fed Funds / 失業率</p>
            <p className="text-[10px] text-slate-600 mt-1">
              需設定 <code className="text-amber-400">FRED_API_KEY</code>（.env，
              <a href="https://fred.stlouisfed.org/docs/api/api_key.html" target="_blank" rel="noreferrer"
                className="text-blue-400 underline ml-1">免費申請</a>）
            </p>
          </div>
        )}

        <div className="mt-3 bg-slate-800/40 rounded-lg p-3 text-xs space-y-1">
          <p className="text-slate-400 font-medium">📌 判斷邏輯</p>
          <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-slate-500">
            <span>升息</span><span className="text-red-300">→ 股市壓力 / 黃金偏弱</span>
            <span>降息</span><span className="text-green-300">→ 股市上漲 / 黃金上漲</span>
            <span>通膨上升</span><span className="text-amber-300">→ 黃金上漲</span>
            <span>經濟衰退</span><span className="text-blue-300">→ 防禦資產上漲</span>
          </div>
        </div>
      </section>

      {/* ───── 2. 資金流 ───── */}
      <section>
        <h3 className="text-sm font-semibold text-amber-300 mb-2">💵 2. 資金流 · 錢往哪裡跑</h3>
        <div className="bg-slate-800/40 rounded-lg p-3 text-xs space-y-2">
          <p className="text-slate-400">
            利率 = 資金成本。10Y 公債殖利率
            <b className="text-slate-100 font-mono mx-1">{get('TNX')?.last?.toFixed(2) ?? '—'}%</b>
            （近 1 年 <b className={sign(get('TNX')?.perf?.['1y'])}>
              {get('TNX')?.perf?.['1y'] != null ? `${get('TNX')!.perf!['1y'] >= 0 ? '+' : ''}${get('TNX')!.perf!['1y']}%` : '—'}
            </b>）
          </p>
          <ul className="text-slate-500 space-y-0.5 ml-4 list-disc">
            <li>利率高 → 錢回債券 → 股市 / 黃金壓力</li>
            <li>利率低 → 錢流向股市 / 風險資產</li>
            <li>DXY 強 → 資金回流美國 → 新興市場 / 黃金壓力</li>
          </ul>
        </div>
      </section>

      {/* ───── 3. 市場價格 ───── */}
      <section>
        <h3 className="text-sm font-semibold text-amber-300 mb-2">📊 3. 市場價格 · Price Action</h3>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2">
          {(['SPX', 'NDX', 'DJI', 'GC', 'CL', 'SI', 'DXY', 'BTC', 'ETH'] as const).map(sym => {
            const r = get(sym)
            return <MetricCard key={sym} label={r?.label ?? sym} sub={sym}
              value={r?.last} change={r?.change} changePct={r?.changePct} currency={r?.currency} />
          })}
        </div>

        {/* 績效摘要：黃金的長期 perf */}
        {get('GC')?.perf && (
          <div className="mt-3">
            <p className="text-xs text-slate-500 mb-1">黃金 GC（USD/oz）長期績效</p>
            <div className="flex flex-wrap gap-1">
              {(['1mo', '6mo', 'ytd', '1y', '5y', '10y'] as const).map(k =>
                <PerfChip key={k} label={k.toUpperCase()} value={get('GC')?.perf?.[k]} />)}
            </div>
          </div>
        )}

        <div className="mt-3 bg-slate-800/40 rounded-lg p-3 text-xs">
          <p className="text-slate-400 font-medium mb-1">🔗 交叉關係（很重要）</p>
          <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-slate-500">
            <span>DXY ↑</span><span>→ 黃金 ↓</span>
            <span>利率 ↑</span><span>→ 科技股 ↓</span>
            <span>避險情緒 ↑</span><span>→ 黃金 ↑ BTC ↑</span>
            <span>經濟強</span><span>→ 股市 ↑</span>
          </div>
        </div>
      </section>

      {/* ───── 4. 籌碼 / 情緒 ───── */}
      <section>
        <h3 className="text-sm font-semibold text-amber-300 mb-2">📈 4. 籌碼 / 情緒</h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
          {/* VIX */}
          <div className="bg-slate-800/50 rounded-lg p-3 border border-slate-700">
            <p className="text-xs text-slate-500 mb-1">VIX 恐慌指數</p>
            <p className="text-lg font-bold font-mono text-slate-100">{get('VIX')?.last?.toFixed(2) ?? '—'}</p>
            <p className="text-[10px] text-slate-500 mt-0.5">
              {(get('VIX')?.last ?? 0) > 30 && '🔴 高度恐慌 → 防禦'}
              {(get('VIX')?.last ?? 0) > 20 && (get('VIX')?.last ?? 0) <= 30 && '🟡 警戒'}
              {(get('VIX')?.last ?? 0) <= 20 && (get('VIX')?.last ?? 0) > 0 && '🟢 平靜（風險偏好）'}
            </p>
          </div>

          {/* 殖利率曲線 10Y-2Y */}
          <div className="bg-slate-800/50 rounded-lg p-3 border border-slate-700">
            <p className="text-xs text-slate-500 mb-1">10Y - 2Y 殖利率利差</p>
            <p className={`text-lg font-bold font-mono ${
              yc?.status === 'inverted' ? 'text-red-400'
              : yc?.status === 'flat' ? 'text-amber-400'
              : yc?.status === 'normal' ? 'text-green-400'
              : 'text-slate-500'
            }`}>
              {yc?.latest != null ? `${yc.latest >= 0 ? '+' : ''}${yc.latest.toFixed(2)}%` : '—'}
            </p>
            <p className="text-[10px] text-slate-500 mt-0.5">{yc?.note ?? '需 FRED API'}</p>
          </div>

          {/* 台指選擇權 PCR */}
          <div className="bg-slate-800/50 rounded-lg p-3 border border-slate-700">
            <p className="text-xs text-slate-500 mb-1">台指期選擇權 PCR</p>
            <p className={`text-lg font-bold font-mono ${
              pcr?.latest?.volume_category?.includes('bearish') ? 'text-green-400'
              : pcr?.latest?.volume_category?.includes('bullish') ? 'text-red-400'
              : 'text-slate-100'
            }`}>
              {pcr?.latest?.pcr_volume?.toFixed(2) ?? '—'}
              <span className="text-[10px] text-slate-600 ml-1">vol</span>
              {pcr?.latest?.pcr_oi != null && (
                <span className="text-sm text-slate-400 font-mono ml-2">
                  {pcr.latest.pcr_oi.toFixed(2)}<span className="text-[10px] text-slate-600 ml-1">oi</span>
                </span>
              )}
            </p>
            <p className="text-[10px] text-slate-500 mt-0.5">{pcr?.latest?.note ?? '— TXO PCR'}</p>
          </div>
        </div>
        <p className="text-[10px] text-slate-600 mt-2">
          PCR &gt; 1.2 通常代表「過度恐慌」（反向買入訊號）；&lt; 0.7「過度樂觀」（反向警戒）。
          殖利率倒掛在歷史上 6-18 個月內常出現衰退。
        </p>
      </section>

      {/* ───── 5. 地緣政治 ───── */}
      <section>
        <h3 className="text-sm font-semibold text-amber-300 mb-2">🌐 5. 地緣政治 · 黑天鵝來源</h3>
        <div className="bg-slate-800/40 rounded-lg p-3 text-xs space-y-2">
          <p className="text-slate-400">監測重點：戰爭（俄烏、中東）/ 美國選舉 / 制裁 / 石油供應鏈</p>
          <button onClick={onJumpGlobal}
            className="text-xs px-3 py-1.5 rounded bg-blue-700/50 hover:bg-blue-700/70 text-blue-200">
            前往「全球」頁查最新新聞 →
          </button>
        </div>
      </section>

      {/* ───── 6. 經濟事件日曆 ───── */}
      <section>
        <h3 className="text-sm font-semibold text-amber-300 mb-2">
          📅 6. 未來 30 天經濟事件 · Calendar
          {cal?.count != null && <span className="text-xs text-slate-500 font-normal ml-2">{cal.count} 筆</span>}
        </h3>
        {!cal?.available && (
          <div className="bg-slate-800/30 border border-dashed border-slate-700 rounded-lg p-3 text-xs text-center">
            <p className="text-slate-500">需設定 <code className="text-amber-400">FINNHUB_API_KEY</code></p>
            <a href="https://finnhub.io/dashboard" target="_blank" rel="noreferrer"
              className="text-[10px] text-blue-400 underline">免費申請 →</a>
          </div>
        )}
        {cal?.available && cal.events && cal.events.length > 0 && (
          <div className="bg-slate-900 border border-slate-800 rounded-lg overflow-hidden">
            <table className="w-full text-xs">
              <thead className="bg-slate-800/60">
                <tr className="text-slate-500 text-[10px] uppercase">
                  <th className="text-left py-1.5 px-2">日期 / 時間</th>
                  <th className="text-left px-2">國家</th>
                  <th className="text-left px-2">事件</th>
                  <th className="text-right px-2">前值</th>
                  <th className="text-right px-2">預期</th>
                  <th className="text-right px-2">公布</th>
                  <th className="text-center px-2">影響</th>
                </tr>
              </thead>
              <tbody>
                {cal.events.slice(0, 30).map((e, i) => {
                  const impactEmoji = e.impact === 'high' ? '🔴' : e.impact === 'medium' ? '🟡' : '⚪'
                  const fmtNum = (v?: number | null) => v == null ? '—' : v.toLocaleString(undefined, { maximumFractionDigits: 2 })
                  return (
                    <tr key={i} className="border-b border-slate-800/50 hover:bg-slate-800/30">
                      <td className="py-1 px-2 text-slate-400 whitespace-nowrap">
                        {e.date}<span className="text-slate-600 ml-1">{e.time}</span>
                      </td>
                      <td className="px-2 font-mono text-blue-300">{e.country}</td>
                      <td className="px-2 text-slate-300">{e.event}</td>
                      <td className="px-2 text-right font-mono text-slate-500">{fmtNum(e.prev)}</td>
                      <td className="px-2 text-right font-mono text-amber-300">{fmtNum(e.estimate)}</td>
                      <td className={`px-2 text-right font-mono ${e.actual != null ? 'text-slate-100 font-bold' : 'text-slate-700'}`}>
                        {fmtNum(e.actual)}
                      </td>
                      <td className="px-2 text-center">{impactEmoji}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
            {cal.events.length > 30 && (
              <p className="text-[10px] text-slate-600 text-center py-2">
                顯示前 30 筆，共 {cal.events.length} 筆
              </p>
            )}
          </div>
        )}
        <p className="text-[10px] text-slate-600 mt-2">
          🔴 high / 🟡 medium / ⚪ low · 資料源 Finnhub · 已過濾掉德國各州、Prel 中間版本、節日噪音
        </p>
      </section>
    </div>
  )
}
