import { useState, useEffect, useMemo, useRef, ReactNode, lazy, Suspense } from 'react'
import { useTranslation } from 'react-i18next'
import { api } from './api'
import { toggleLang } from './i18n'
import type { Bar, MaPoint } from './types'
import type { PatternScanMode } from './components/MarketPatternScanPanel'
import type { MarketPatternScanResponse, WeeklyWBottomScanResponse } from './types'
import { useAsync } from './hooks/useAsync'
import { toTime as normalizeTime } from './lib/charts'

// Shell 必要 — eager
import ErrorBoundary from './components/ErrorBoundary'

// MarketOverview + PriceChart 都用 lightweight-charts (~150KB)；
// 全部 lazy 化讓 Vite 自動抽出 shared chunk，初次載入只下載 ~200KB main bundle
const MarketOverview = lazy(() => import('./components/MarketOverview'))
const PriceChart = lazy(() => import('./components/PriceChart'))
const LiveQuote = lazy(() => import('./components/LiveQuote'))
const TechnicalPanel = lazy(() => import('./components/TechnicalPanel'))
const ChipPanel = lazy(() => import('./components/ChipPanel'))
const BacktestPanel = lazy(() => import('./components/BacktestPanel'))
const PatternPanel = lazy(() => import('./components/PatternPanel'))
const FundamentalsPanel = lazy(() => import('./components/FundamentalsPanel'))
const NewsPanel = lazy(() => import('./components/NewsPanel'))
const OutlookPanel = lazy(() => import('./components/OutlookPanel'))
const GlobalPanel = lazy(() => import('./components/GlobalPanel'))
const FuturesPanel = lazy(() => import('./components/FuturesPanel'))
const MacroPanel = lazy(() => import('./components/MacroPanel'))
const CompareChart = lazy(() => import('./components/CompareChart'))
const WatchlistPanel = lazy(() => import('./components/WatchlistPanel'))
const MarketPatternScanPanel = lazy(() => import('./components/MarketPatternScanPanel'))
const WeeklyWBottomScanPanel = lazy(() => import('./components/WeeklyWBottomScanPanel'))

// Tab key（中英文 label 透過 i18n 查表）
const TAB_KEYS = ['outlook', 'technical', 'chip', 'backtest', 'pattern', 'fundamentals', 'news'] as const
type TabKey = typeof TAB_KEYS[number]

type ViewType = 'market' | 'stock' | 'global' | 'futures' | 'macro' | 'scan' | 'compare' | 'watchlist'

// 穩定的空物件 reference — 避免每次 render 都產生新 `{}` 害 PriceChart effect 重跑
const EMPTY_MAS: Record<string, MaPoint[]> = {}

// K 線圖時間框架：tf = 對應後端參數 + i18n key，days = 抓取的日線天數
const CHART_TFS: { tf: string; days: number }[] = [
  { tf: 'intraday', days: 0 },
  { tf: '1d', days: 120 },
  { tf: '3d', days: 240 },
  { tf: '5d', days: 240 },
  { tf: '1w', days: 365 },
  { tf: '3w', days: 730 },
  { tf: '1mo', days: 1825 },
]

function Spinner() {
  return <div className="flex justify-center py-8"><div className="w-6 h-6 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" /></div>
}

function Card({ title, children, className = '' }: { title?: ReactNode; children?: ReactNode; className?: string }) {
  return (
    <div className={`bg-slate-900 border border-slate-700 rounded-xl p-4 ${className}`}>
      {title && <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-3">{title}</h3>}
      {children}
    </div>
  )
}

// 把日K 資料切成 MA 序列
type PriceResponse = { data?: Bar[]; previousClose?: number | null }
type TechnicalResponse = { ma?: Record<string, number> }
function buildMas(priceData: PriceResponse | null, technicalData: TechnicalResponse | null): Record<string, MaPoint[]> {
  if (!priceData?.data?.length || !technicalData?.ma) return {}
  const maKeys = Object.keys(technicalData.ma)
  // 只取 close 序列；前端重新計算 MA，不需多一次 API
  const closes = priceData.data.map(r => ({ date: r.date, close: r.close }))
  const result: Record<string, MaPoint[]> = {}
  for (const key of maKeys) {
    const period = parseInt(key.replace('ma', ''))
    const series: MaPoint[] = []
    for (let i = period - 1; i < closes.length; i++) {
      const avg = closes.slice(i - period + 1, i + 1).reduce((s, r) => s + r.close, 0) / period
      series.push({ time: normalizeTime(closes[i].date) as string | number, value: parseFloat(avg.toFixed(2)) })
    }
    result[key] = series
  }
  return result
}

export default function App() {
  const { t, i18n } = useTranslation()
  const [symbol, setSymbol] = useState('')
  const [input, setInput] = useState('')
  const [activeTab, setActiveTab] = useState<TabKey>('outlook')
  const [btSignal, setBtSignal] = useState('ma_cross')
  const [chartTf, setChartTf] = useState('1d')
  const [view, setView] = useState<ViewType>('market')
  const [suggestions, setSuggestions] = useState<any[]>([])
  const [showSuggestions, setShowSuggestions] = useState(false)
  const searchRef = useRef<HTMLFormElement>(null)

  // 大盤資料：法人資金動向 + 盤後統計（指數走勢由 MarketOverview 自行依時間區間抓取）
  const market = useAsync(() => api.moneyFlow(8), [])

  // 全市場型態掃描（三線交纏 / 週W底）— state 住 App，切頁不重跑；掃描較重，由面板按鈕手動觸發
  const [scanMode, setScanMode] = useState<PatternScanMode>('both')
  const [scanData, setScanData] = useState<MarketPatternScanResponse | null>(null)
  const [scanLoading, setScanLoading] = useState(false)
  const [scanError, setScanError] = useState<string | null>(null)
  const [scanAt, setScanAt] = useState<string | null>(null)
  const _runScan = (m: PatternScanMode) => {
    if (scanLoading) return
    setScanLoading(true); setScanError(null)
    api.marketPatternScan(m)
      .then(r => { setScanData(r); setScanAt(new Date().toLocaleTimeString('zh-TW', { hour: '2-digit', minute: '2-digit' })) })
      .catch(e => setScanError(e.message ?? '掃描失敗'))
      .finally(() => setScanLoading(false))
  }
  const runScan = () => _runScan(scanMode)
  const handleScanModeChange = (m: PatternScanMode) => { setScanMode(m); _runScan(m) }

  const [wScanData, setWScanData] = useState<WeeklyWBottomScanResponse | null>(null)
  const [wScanLoading, setWScanLoading] = useState(false)
  const [wScanError, setWScanError] = useState<string | null>(null)
  const [wScanAt, setWScanAt] = useState<string | null>(null)
  const runWScan = () => {
    if (wScanLoading) return
    setWScanLoading(true); setWScanError(null)
    api.weeklyWBottomScan()
      .then(r => { setWScanData(r); setWScanAt(new Date().toLocaleTimeString('zh-TW', { hour: '2-digit', minute: '2-digit' })) })
      .catch(e => setWScanError(e.message ?? '掃描失敗'))
      .finally(() => setWScanLoading(false))
  }

  // 個股資料（當 symbol 改變時觸發）
  const price = useAsync(() => {
    if (!symbol) return Promise.resolve(null)
    if (chartTf === 'intraday') return api.stockIntraday(symbol, '5')
    const opt = CHART_TFS.find(o => o.tf === chartTf) ?? CHART_TFS[1]
    return api.price(symbol, opt.days, chartTf)
  }, [symbol, chartTf])
  const technical = useAsync(() => symbol ? api.technical(symbol, 'daily') : Promise.resolve(null), [symbol])
  const outlook = useAsync(() => symbol ? api.outlook(symbol) : Promise.resolve(null), [symbol])
  const chip = useAsync(() => symbol ? api.chip(symbol) : Promise.resolve(null), [symbol])
  const backtest = useAsync(() => symbol ? api.backtest(symbol, btSignal) : Promise.resolve(null), [symbol, btSignal])
  // 只在切到該 tab 時才 fetch — 省 FinMind 配額 / 減少初次 render 等待時間
  const fundamentals = useAsync(
    () => (symbol && activeTab === 'fundamentals') ? api.fundamentals(symbol) : Promise.resolve(null),
    [symbol, activeTab],
  )
  const news = useAsync(
    () => (symbol && activeTab === 'news') ? api.news(symbol) : Promise.resolve(null),
    [symbol, activeTab],
  )

  // memoise — buildMas 每次 render 都會回新物件，會讓 PriceChart 的 useEffect 反覆 fire 拆掉重建 chart
  const mas = useMemo(() => buildMas(price.data, technical.data), [price.data, technical.data])

  // 搜尋建議：輸入時查詢
  useEffect(() => {
    const q = input.trim()
    if (!q) { setSuggestions([]); return }
    const timer = setTimeout(() => {
      api.searchStock(q, 8).then(r => setSuggestions(r.results || [])).catch(() => setSuggestions([]))
    }, 200)
    return () => clearTimeout(timer)
  }, [input])

  // 點擊外部關閉建議列表
  useEffect(() => {
    const handler = (e: MouseEvent) => { if (searchRef.current && !searchRef.current.contains(e.target as Node)) setShowSuggestions(false) }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const selectSuggestion = (s: { symbol: string; name?: string; market?: string }) => {
    setInput(s.symbol)
    setSuggestions([])
    setShowSuggestions(false)
    setSymbol(s.symbol)
    setView('stock')
    setActiveTab('outlook')
  }

  // 從大盤排行等處點股票代碼 → 直接分析該股
  const goStock = (sym: string) => {
    setInput(sym)
    setShowSuggestions(false)
    setSymbol(sym)
    setView('stock')
    setActiveTab('outlook')
  }

  const handleSearch = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    const v = input.trim()
    if (!v) return
    setShowSuggestions(false)
    // 若輸入的是中文且有建議，直接用第一筆
    const resolved = (!v.match(/^\d/) && suggestions.length > 0) ? suggestions[0].symbol : v
    setSymbol(resolved)
    setView('stock')
    setActiveTab('outlook')
  }

  return (
    <div className="min-h-screen bg-slate-950 text-slate-200">
      {/* Header */}
      <header className="border-b border-slate-800 bg-slate-900/80 backdrop-blur sticky top-0 z-10">
        <div className="max-w-6xl mx-auto px-4 py-3 flex items-center gap-4">
          <button onClick={() => setView('market')} className="text-lg font-bold text-blue-400 hover:text-blue-300 shrink-0">
            {t('nav.title')}
          </button>
          <form onSubmit={handleSearch} className="flex gap-2 flex-1 max-w-sm relative" ref={searchRef}>
            <div className="flex-1 relative">
              <input
                value={input}
                onChange={e => { setInput(e.target.value); setShowSuggestions(true) }}
                onFocus={() => setShowSuggestions(true)}
                placeholder={t('nav.search_placeholder')}
                className="w-full bg-slate-800 border border-slate-600 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:border-blue-500"
              />
              {showSuggestions && suggestions.length > 0 && (
                <ul className="absolute top-full mt-1 left-0 w-full bg-slate-800 border border-slate-600 rounded-lg shadow-lg z-50 overflow-hidden">
                  {suggestions.map(s => (
                    <li
                      key={s.symbol}
                      onMouseDown={() => selectSuggestion(s)}
                      className="flex items-center justify-between px-3 py-2 text-sm cursor-pointer hover:bg-slate-700"
                    >
                      <span className="font-medium text-blue-300">{s.symbol}</span>
                      <span className="text-slate-300 ml-2">{s.name}</span>
                      <span className="text-slate-500 text-xs ml-auto">
                        {s.market === 'twse' ? t('market_label.twse')
                          : s.market === 'tpex' ? t('market_label.tpex')
                          : s.market === 'us' ? t('market_label.us')
                          : s.market}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
            <button type="submit" className="bg-blue-600 hover:bg-blue-500 px-4 py-1.5 rounded-lg text-sm font-medium shrink-0">
              {t('nav.search_button')}
            </button>
          </form>
          <nav className="flex items-center gap-3 text-sm shrink-0 ml-auto">
            {([
              ['market', 'nav.market'],
              ['global', 'nav.global'],
              ['futures', 'nav.futures'],
              ['macro', 'nav.macro'],
              ['scan', 'nav.scan'],
              ['compare', 'nav.compare'],
              ['watchlist', 'nav.watchlist'],
            ] as const).map(([v, key]) => (
              <button key={v} onClick={() => setView(v)}
                className={view === v ? 'text-blue-400 font-medium' : 'text-slate-400 hover:text-slate-200'}>
                {t(key)}
              </button>
            ))}
            {symbol && (
              <button onClick={() => setView('stock')}
                className={view === 'stock' ? 'text-blue-400 font-medium' : 'text-slate-400 hover:text-slate-200'}>
                {symbol}
              </button>
            )}
            {/* 語言切換 */}
            <button onClick={() => { toggleLang(); /* 觸發 re-render */ }}
              className="text-xs px-2 py-0.5 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 ml-2"
              title={`current: ${i18n.language}`}>
              {t('common.lang_switch')}
            </button>
          </nav>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-4 py-6 space-y-6">
        <Suspense fallback={<Spinner />}>
        {view === 'market' && (
          <Card title={t('card.market_overview')}>
            {market.error && <p className="text-red-400 text-sm">{market.error}</p>}
            <ErrorBoundary label={t('card.market_overview')}>
              <MarketOverview moneyFlow={market.data} onSelectStock={goStock} />
            </ErrorBoundary>
          </Card>
        )}

        {view === 'global' && (
          <ErrorBoundary label={t('nav.global')}>
            <GlobalPanel />
          </ErrorBoundary>
        )}

        {view === 'futures' && (
          <Card title={t('card.futures_commodities')}>
            <ErrorBoundary label={t('nav.futures')}>
              <FuturesPanel />
            </ErrorBoundary>
          </Card>
        )}

        {view === 'macro' && (
          <Card>
            <ErrorBoundary label={t('nav.macro')}>
              <MacroPanel onJumpGlobal={() => setView('global')} />
            </ErrorBoundary>
          </Card>
        )}

        {/* 全市場型態掃描（三線交纏帶量突破 + 週線W底突破）。面板內文目前為中文（尚未 i18n） */}
        {view === 'scan' && (
          <>
            <Card title="三線交纏帶量突破 — 全市場掃描">
              <ErrorBoundary label="三線交纏掃描">
                <MarketPatternScanPanel
                  mode={scanMode}
                  onModeChange={handleScanModeChange}
                  data={scanData}
                  loading={scanLoading}
                  error={scanError}
                  scannedAt={scanAt}
                  onRescan={runScan}
                  onSelectStock={goStock}
                />
              </ErrorBoundary>
            </Card>
            <Card title="週線W底突破 — 全市場掃描">
              <ErrorBoundary label="週線W底掃描">
                <WeeklyWBottomScanPanel
                  data={wScanData}
                  loading={wScanLoading}
                  error={wScanError}
                  scannedAt={wScanAt}
                  onRescan={runWScan}
                  onSelectStock={goStock}
                />
              </ErrorBoundary>
            </Card>
          </>
        )}

        {view === 'compare' && (
          <Card>
            <ErrorBoundary label={t('nav.compare')}>
              <CompareChart />
            </ErrorBoundary>
          </Card>
        )}

        {view === 'watchlist' && (
          <Card>
            <ErrorBoundary label={t('nav.watchlist')}>
              <WatchlistPanel onSelectStock={goStock} />
            </ErrorBoundary>
          </Card>
        )}

        {view === 'stock' && symbol && (
          <>
            {/* 即時報價（Fugle，含五檔）— 台股/ETF 盤中每 3 秒更新 */}
            <ErrorBoundary label={t('quote.live')}>
              <LiveQuote symbol={symbol} />
            </ErrorBoundary>

            {/* K 線圖 */}
            <Card title={`${symbol} · ${t('card.kline')}`}>
              <div className="flex flex-wrap gap-1 mb-3">
                {CHART_TFS.map(o => (
                  <button key={o.tf} onClick={() => setChartTf(o.tf)}
                    className={`text-xs px-3 py-1 rounded-full ${chartTf === o.tf ? 'bg-blue-600 text-white' : 'bg-slate-800 text-slate-400 hover:bg-slate-700'}`}>
                    {t(`kline_tf.${o.tf}`)}
                  </button>
                ))}
              </div>
              {price.loading && <Spinner />}
              {price.data && (
                // key 強制在切時間框架時整個重建，避免 lightweight-charts 內部殘留狀態
                <ErrorBoundary label={t('card.kline')} onReset={() => setChartTf(chartTf)}>
                  <PriceChart
                    key={`${symbol}-${chartTf}`}
                    data={price.data.data}
                    mas={chartTf === '1d' ? mas : EMPTY_MAS}
                    intraday={chartTf === 'intraday'}
                    previousClose={chartTf === 'intraday' ? (price.data.previousClose ?? null) : null}
                  />
                </ErrorBoundary>
              )}
            </Card>

            {/* Tab 切換 */}
            <div>
              <div className="flex gap-1 border-b border-slate-800 mb-4">
                {TAB_KEYS.map(key => (
                  <button key={key} onClick={() => setActiveTab(key)}
                    className={`px-4 py-2 text-sm -mb-px border-b-2 transition-colors ${activeTab === key ? 'border-blue-500 text-blue-400' : 'border-transparent text-slate-500 hover:text-slate-300'}`}>
                    {t(`tabs.${key}`)}
                  </button>
                ))}
              </div>

              <Card>
                <ErrorBoundary label={t(`tabs.${activeTab}`)}>
                  {activeTab === 'outlook' && (
                    outlook.loading ? <Spinner /> : <OutlookPanel data={outlook.data} />
                  )}
                  {activeTab === 'technical' && (
                    technical.loading ? <Spinner /> : <TechnicalPanel data={technical.data} />
                  )}
                  {activeTab === 'chip' && (
                    chip.loading ? <Spinner /> : <ChipPanel data={chip.data} symbol={symbol} />
                  )}
                  {activeTab === 'backtest' && (
                    backtest.loading
                      ? <Spinner />
                      : <BacktestPanel data={backtest.data} signal={btSignal} onSignalChange={setBtSignal} />
                  )}
                  {activeTab === 'pattern' && symbol && (
                    <PatternPanel symbol={symbol} />
                  )}
                  {activeTab === 'fundamentals' && (
                    fundamentals.loading ? <Spinner /> : <FundamentalsPanel data={fundamentals.data} symbol={symbol} />
                  )}
                  {activeTab === 'news' && (
                    news.loading ? <Spinner /> : <NewsPanel news={news.data?.news} />
                  )}
                </ErrorBoundary>
              </Card>
            </div>
          </>
        )}

        {view === 'stock' && !symbol && (
          <p className="text-slate-500 text-center py-12">{t('common.stock_view_hint')}</p>
        )}
        </Suspense>
      </main>
    </div>
  )
}
