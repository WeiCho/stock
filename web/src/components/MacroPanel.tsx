import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { api } from '../api'
import type { Bar } from '../types'

interface YieldCurve { latest: number | null; status: 'normal' | 'flat' | 'inverted' | 'unavailable'; note: string }
interface Pcr { latest: { date: string; pcr_volume: number | null; pcr_oi: number | null; note?: string; volume_category?: string } | null; error?: string }
interface CalEvent { date: string; time: string; country: string; event: string; impact: string; prev?: number | null; estimate?: number | null; actual?: number | null; unit?: string }
interface CalResp { available: boolean; events?: CalEvent[]; count?: number }
interface CryptoCoin { symbol: string; name: string; price: number; market_cap: number; market_cap_rank: number; change_24h_pct: number; change_7d_pct?: number; change_30d_pct?: number; image?: string }
interface CryptoTop { available: boolean; items?: CryptoCoin[] }
interface CryptoGlobal { available: boolean; total_market_cap_usd?: number; btc_dominance?: number; eth_dominance?: number; market_cap_change_pct_24h?: number; active_cryptocurrencies?: number }
interface FxResp { available: boolean; base: string; date?: string; rates: Record<string, number> }

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
  const { t } = useTranslation()
  const [loading, setLoading] = useState(true)
  const [items, setItems] = useState<Record<string, CommodityResp>>({})
  const [fred, setFred] = useState<FredSummary>({ available: false, indicators: [] })
  const [yc, setYc] = useState<YieldCurve | null>(null)
  const [pcr, setPcr] = useState<Pcr | null>(null)
  const [cal, setCal] = useState<CalResp | null>(null)
  const [cryptoTop, setCryptoTop] = useState<CryptoTop | null>(null)
  const [cryptoG, setCryptoG] = useState<CryptoGlobal | null>(null)
  const [fxRates, setFxRates] = useState<FxResp | null>(null)

  // 一次抓全部需要的標的，並行（Yahoo 商品 + FRED + 殖利率 + PCR + Finnhub 經濟事件）
  useEffect(() => {
    let cancelled = false
    setLoading(true)
    const symbols = ['DXY', 'TNX', 'FVX', 'SPX', 'NDX', 'DJI', 'VIX', 'GC', 'CL', 'SI', 'BTC', 'ETH']
    // GC 黃金額外抓 10 年（供 perf 1Y/5Y/10Y 表用，其他用 1y 夠了）
    Promise.all([
      Promise.all(symbols.map(s => fetchSym(s, s === 'GC' ? 3650 : 365).then(r => [s, r] as const))),
      fetchFredSummary(),
      api.yieldCurve(5).catch(() => null),
      api.futuresPcr(30).catch(() => null),
      api.macroCalendar(30, 'high').catch(() => null),
      api.cryptoTop(10).catch(() => null),
      api.cryptoGlobal().catch(() => null),
      api.fx('USD').catch(() => null),
    ]).then(([yahoo, fredResp, ycResp, pcrResp, calResp, ctResp, cgResp, fxResp]) => {
      if (cancelled) return
      const out: Record<string, CommodityResp> = {}
      for (const [s, r] of yahoo) if (r) out[s] = r
      setItems(out)
      setFred(fredResp)
      setYc(ycResp)
      setPcr(pcrResp)
      setCal(calResp)
      setCryptoTop(ctResp)
      setCryptoG(cgResp)
      setFxRates(fxResp)
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
        <h2 className="text-xl font-bold text-slate-100">{t('macro.title')}</h2>
        <p className="text-xs text-slate-500 mt-1">
          {t('macro.subtitle')}{fred.available ? t('macro.subtitle_fred_on') : t('macro.subtitle_fred_off')}。
        </p>
      </header>

      {loading && <p className="text-slate-500 text-sm">{t('macro.loading_indicators')}</p>}

      {/* ───── 1. 總體經濟 ───── */}
      <section>
        <h3 className="text-sm font-semibold text-amber-300 mb-2">{t('macro.section1_title')}</h3>

        {/* 市場面（Yahoo Finance）：利率 / DXY / VIX */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mb-2">
          {([
            { label: t('macro.metric.us10y'), sub: '^TNX', sym: 'TNX', currency: '%' },
            { label: t('macro.metric.us5y'), sub: '^FVX', sym: 'FVX', currency: '%' },
            { label: t('macro.metric.dxy'), sub: 'DXY', sym: 'DXY', currency: 'INDEX' },
            { label: t('macro.metric.vix'), sub: '^VIX', sym: 'VIX', currency: 'INDEX' },
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
            <p className="text-xs text-slate-500">{t('macro.fred_unavailable_list')}</p>
            <p className="text-[10px] text-slate-600 mt-1">
              {t('macro.requires_prefix')}<code className="text-amber-400">FRED_API_KEY</code>{t('macro.requires_env_mid')}
              <a href="https://fred.stlouisfed.org/docs/api/api_key.html" target="_blank" rel="noreferrer"
                className="text-blue-400 underline ml-1">{t('macro.free_signup')}</a>{t('macro.paren_close')}
            </p>
          </div>
        )}

        <div className="mt-3 bg-slate-800/40 rounded-lg p-3 text-xs space-y-1">
          <p className="text-slate-400 font-medium">{t('macro.logic_title')}</p>
          <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-slate-500">
            <span>{t('macro.logic.rate_hike')}</span><span className="text-red-300">{t('macro.logic.rate_hike_effect')}</span>
            <span>{t('macro.logic.rate_cut')}</span><span className="text-green-300">{t('macro.logic.rate_cut_effect')}</span>
            <span>{t('macro.logic.inflation_up')}</span><span className="text-amber-300">{t('macro.logic.inflation_up_effect')}</span>
            <span>{t('macro.logic.recession')}</span><span className="text-blue-300">{t('macro.logic.recession_effect')}</span>
          </div>
        </div>
      </section>

      {/* ───── 2. 資金流 ───── */}
      <section>
        <h3 className="text-sm font-semibold text-amber-300 mb-2">{t('macro.section2_title')}</h3>
        <div className="bg-slate-800/40 rounded-lg p-3 text-xs space-y-2">
          <p className="text-slate-400">
            {t('macro.liquidity.rate_intro')}
            <b className="text-slate-100 font-mono mx-1">{get('TNX')?.last?.toFixed(2) ?? '—'}%</b>
            {t('macro.liquidity.last_1y_prefix')}<b className={sign(get('TNX')?.perf?.['1y'])}>
              {get('TNX')?.perf?.['1y'] != null ? `${get('TNX')!.perf!['1y'] >= 0 ? '+' : ''}${get('TNX')!.perf!['1y']}%` : '—'}
            </b>{t('macro.liquidity.last_1y_suffix')}
          </p>
          <ul className="text-slate-500 space-y-0.5 ml-4 list-disc">
            <li>{t('macro.liquidity.bullet_high_rate')}</li>
            <li>{t('macro.liquidity.bullet_low_rate')}</li>
            <li>{t('macro.liquidity.bullet_strong_dxy')}</li>
          </ul>
        </div>

        {/* 匯率（exchangerate-api 免費，US 對主要幣別）*/}
        {fxRates?.available && fxRates.rates && Object.keys(fxRates.rates).length > 0 && (
          <div className="mt-3">
            <p className="text-xs text-slate-500 uppercase mb-2">{t('macro.fx.title_prefix')}{fxRates.date}{t('macro.fx.title_suffix')}</p>
            <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-2">
              {Object.entries(fxRates.rates).map(([ccy, rate]) => (
                <div key={ccy} className="bg-slate-800/50 rounded-lg p-2 text-center border border-slate-700">
                  <p className="text-[10px] text-slate-500">USD/{ccy}</p>
                  <p className="text-sm font-mono font-bold text-slate-100">{rate?.toFixed(ccy === 'JPY' ? 2 : 3)}</p>
                </div>
              ))}
            </div>
            <p className="text-[10px] text-slate-600 mt-1">{t('macro.fx.note')}</p>
          </div>
        )}
      </section>

      {/* ───── 3. 市場價格 ───── */}
      <section>
        <h3 className="text-sm font-semibold text-amber-300 mb-2">{t('macro.section3_title')}</h3>
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
            <p className="text-xs text-slate-500 mb-1">{t('macro.gold_perf_title')}</p>
            <div className="flex flex-wrap gap-1">
              {(['1mo', '6mo', 'ytd', '1y', '5y', '10y'] as const).map(k =>
                <PerfChip key={k} label={k.toUpperCase()} value={get('GC')?.perf?.[k]} />)}
            </div>
          </div>
        )}

        <div className="mt-3 bg-slate-800/40 rounded-lg p-3 text-xs">
          <p className="text-slate-400 font-medium mb-1">{t('macro.cross.title')}</p>
          <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-slate-500">
            <span>{t('macro.cross.dxy_up')}</span><span>{t('macro.cross.dxy_up_effect')}</span>
            <span>{t('macro.cross.rate_up')}</span><span>{t('macro.cross.rate_up_effect')}</span>
            <span>{t('macro.cross.risk_off_up')}</span><span>{t('macro.cross.risk_off_up_effect')}</span>
            <span>{t('macro.cross.strong_econ')}</span><span>{t('macro.cross.strong_econ_effect')}</span>
          </div>
        </div>
      </section>

      {/* ───── 3.5 加密貨幣（CoinGecko）───── */}
      {cryptoTop?.available && cryptoTop.items && cryptoTop.items.length > 0 && (
        <section>
          <h3 className="text-sm font-semibold text-amber-300 mb-2">{t('macro.crypto.title')}</h3>
          {cryptoG?.available && (
            <div className="bg-slate-800/40 rounded-lg p-3 mb-2 text-xs flex flex-wrap gap-x-6 gap-y-1">
              <span className="text-slate-400">{t('macro.crypto.total_cap')}<b className="text-slate-100 font-mono">
                {cryptoG.total_market_cap_usd != null ? `$${(cryptoG.total_market_cap_usd / 1e12).toFixed(2)}T` : '—'}
              </b></span>
              {cryptoG.market_cap_change_pct_24h != null && (
                <span className={`font-mono ${cryptoG.market_cap_change_pct_24h >= 0 ? 'text-red-400' : 'text-green-400'}`}>
                  24h {cryptoG.market_cap_change_pct_24h >= 0 ? '+' : ''}{cryptoG.market_cap_change_pct_24h.toFixed(2)}%
                </span>
              )}
              <span className="text-slate-400">{t('macro.crypto.btc_dominance')}<b className="text-amber-300 font-mono">
                {cryptoG.btc_dominance?.toFixed(1) ?? '—'}%
              </b></span>
              <span className="text-slate-400">{t('macro.crypto.eth_dominance')}<b className="text-blue-300 font-mono">
                {cryptoG.eth_dominance?.toFixed(1) ?? '—'}%
              </b></span>
              <span className="text-slate-500">{cryptoG.active_cryptocurrencies?.toLocaleString()}{t('macro.crypto.coins_suffix')}</span>
            </div>
          )}
          <div className="grid grid-cols-2 sm:grid-cols-5 gap-2">
            {cryptoTop.items.map(c => (
              <div key={c.symbol} className="bg-slate-800/50 rounded-lg p-2 border border-slate-700">
                <div className="flex items-baseline justify-between">
                  <span className="text-xs font-mono text-blue-300">#{c.market_cap_rank} {c.symbol}</span>
                  <span className={`text-[10px] font-mono ${c.change_24h_pct >= 0 ? 'text-red-400' : 'text-green-400'}`}>
                    {c.change_24h_pct >= 0 ? '+' : ''}{c.change_24h_pct?.toFixed(2)}%
                  </span>
                </div>
                <p className="text-sm font-mono text-slate-100 mt-0.5">
                  ${c.price >= 1 ? c.price.toLocaleString(undefined, { maximumFractionDigits: 2 }) : c.price.toFixed(4)}
                </p>
                <p className="text-[10px] text-slate-500">cap ${(c.market_cap / 1e9).toFixed(1)}B</p>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* ───── 4. 籌碼 / 情緒 ───── */}
      <section>
        <h3 className="text-sm font-semibold text-amber-300 mb-2">{t('macro.section4_title')}</h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
          {/* VIX */}
          <div className="bg-slate-800/50 rounded-lg p-3 border border-slate-700">
            <p className="text-xs text-slate-500 mb-1">{t('macro.vix.label')}</p>
            <p className="text-lg font-bold font-mono text-slate-100">{get('VIX')?.last?.toFixed(2) ?? '—'}</p>
            <p className="text-[10px] text-slate-500 mt-0.5">
              {(get('VIX')?.last ?? 0) > 30 && t('macro.vix.extreme_fear')}
              {(get('VIX')?.last ?? 0) > 20 && (get('VIX')?.last ?? 0) <= 30 && t('macro.vix.caution')}
              {(get('VIX')?.last ?? 0) <= 20 && (get('VIX')?.last ?? 0) > 0 && t('macro.vix.calm')}
            </p>
          </div>

          {/* 殖利率曲線 10Y-2Y */}
          <div className="bg-slate-800/50 rounded-lg p-3 border border-slate-700">
            <p className="text-xs text-slate-500 mb-1">{t('macro.yield_curve.label')}</p>
            <p className={`text-lg font-bold font-mono ${
              yc?.status === 'inverted' ? 'text-red-400'
              : yc?.status === 'flat' ? 'text-amber-400'
              : yc?.status === 'normal' ? 'text-green-400'
              : 'text-slate-500'
            }`}>
              {yc?.latest != null ? `${yc.latest >= 0 ? '+' : ''}${yc.latest.toFixed(2)}%` : '—'}
            </p>
            <p className="text-[10px] text-slate-500 mt-0.5">{yc?.note ?? t('macro.yield_curve.fallback_note')}</p>
          </div>

          {/* 台指選擇權 PCR */}
          <div className="bg-slate-800/50 rounded-lg p-3 border border-slate-700">
            <p className="text-xs text-slate-500 mb-1">{t('macro.pcr.label')}</p>
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
            <p className="text-[10px] text-slate-500 mt-0.5">{pcr?.latest?.note ?? t('macro.pcr.fallback_note')}</p>
          </div>
        </div>
        <p className="text-[10px] text-slate-600 mt-2">
          {t('macro.sentiment.footnote')}
        </p>
      </section>

      {/* ───── 5. 地緣政治 ───── */}
      <section>
        <h3 className="text-sm font-semibold text-amber-300 mb-2">{t('macro.section5_title')}</h3>
        <div className="bg-slate-800/40 rounded-lg p-3 text-xs space-y-2">
          <p className="text-slate-400">{t('macro.geopolitics.watch')}</p>
          <button onClick={onJumpGlobal}
            className="text-xs px-3 py-1.5 rounded bg-blue-700/50 hover:bg-blue-700/70 text-blue-200">
            {t('macro.geopolitics.jump_button')}
          </button>
        </div>
      </section>

      {/* ───── 6. 經濟事件日曆 ───── */}
      <section>
        <h3 className="text-sm font-semibold text-amber-300 mb-2">
          {t('macro.section6_title')}
          {cal?.count != null && <span className="text-xs text-slate-500 font-normal ml-2">{cal.count}{t('macro.calendar.count_suffix')}</span>}
        </h3>
        {!cal?.available && (
          <div className="bg-slate-800/30 border border-dashed border-slate-700 rounded-lg p-3 text-xs text-center">
            <p className="text-slate-500">{t('macro.requires_prefix')}<code className="text-amber-400">FINNHUB_API_KEY</code></p>
            <a href="https://finnhub.io/dashboard" target="_blank" rel="noreferrer"
              className="text-[10px] text-blue-400 underline">{t('macro.calendar.free_signup')}</a>
          </div>
        )}
        {cal?.available && cal.events && cal.events.length > 0 && (
          <div className="bg-slate-900 border border-slate-800 rounded-lg overflow-hidden">
            <table className="w-full text-xs">
              <thead className="bg-slate-800/60">
                <tr className="text-slate-500 text-[10px] uppercase">
                  <th className="text-left py-1.5 px-2">{t('macro.calendar.col_datetime')}</th>
                  <th className="text-left px-2">{t('macro.calendar.col_country')}</th>
                  <th className="text-left px-2">{t('macro.calendar.col_event')}</th>
                  <th className="text-right px-2">{t('macro.calendar.col_prev')}</th>
                  <th className="text-right px-2">{t('macro.calendar.col_estimate')}</th>
                  <th className="text-right px-2">{t('macro.calendar.col_actual')}</th>
                  <th className="text-center px-2">{t('macro.calendar.col_impact')}</th>
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
                {t('macro.calendar.showing_prefix')}{cal.events.length}{t('macro.calendar.count_suffix')}
              </p>
            )}
          </div>
        )}
        <p className="text-[10px] text-slate-600 mt-2">
          {t('macro.calendar.footnote')}
        </p>
      </section>
    </div>
  )
}
