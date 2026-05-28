import { useState, useEffect, useMemo, useRef, ReactNode } from 'react'
import { api } from './api'
import type { Bar, MaPoint } from './types'
import { useAsync } from './hooks/useAsync'
import { toTime as normalizeTime } from './lib/charts'
import PriceChart from './components/PriceChart'
import TechnicalPanel from './components/TechnicalPanel'
import ChipPanel from './components/ChipPanel'
import BacktestPanel from './components/BacktestPanel'
import FundamentalsPanel from './components/FundamentalsPanel'
import NewsPanel from './components/NewsPanel'
import MarketOverview from './components/MarketOverview'
import OutlookPanel from './components/OutlookPanel'
import GlobalPanel from './components/GlobalPanel'
import FuturesPanel from './components/FuturesPanel'
import MacroPanel from './components/MacroPanel'
import ErrorBoundary from './components/ErrorBoundary'

const TABS = ['綜合研判', '技術面', '籌碼面', '回測', '基本面', '新聞']

// 穩定的空物件 reference — 避免每次 render 都產生新 `{}` 害 PriceChart effect 重跑
const EMPTY_MAS: Record<string, MaPoint[]> = {}

// K 線圖時間框架：當日（Fugle 盤中 5 分鐘）+ 由日 K 重採樣的 6 種；days = 抓取的日線天數
const CHART_TFS: { tf: string; label: string; days: number }[] = [
  { tf: 'intraday', label: '當日', days: 0 },
  { tf: '1d', label: '日K', days: 120 },
  { tf: '3d', label: '3日', days: 240 },
  { tf: '5d', label: '5日', days: 240 },
  { tf: '1w', label: '週K', days: 365 },
  { tf: '3w', label: '3週', days: 730 },
  { tf: '1mo', label: '月K', days: 1825 },
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
  const [symbol, setSymbol] = useState('')
  const [input, setInput] = useState('')
  const [activeTab, setActiveTab] = useState('綜合研判')
  const [btSignal, setBtSignal] = useState('ma_cross')
  const [chartTf, setChartTf] = useState('1d')
  const [view, setView] = useState<'market' | 'stock' | 'global' | 'futures' | 'macro'>('market')
  const [suggestions, setSuggestions] = useState<any[]>([])
  const [showSuggestions, setShowSuggestions] = useState(false)
  const searchRef = useRef<HTMLFormElement>(null)

  // 大盤資料：法人資金動向 + 盤後統計（指數走勢由 MarketOverview 自行依時間區間抓取）
  const market = useAsync(() => api.moneyFlow(8), [])

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
    () => (symbol && activeTab === '基本面') ? api.fundamentals(symbol) : Promise.resolve(null),
    [symbol, activeTab],
  )
  const news = useAsync(
    () => (symbol && activeTab === '新聞') ? api.news(symbol) : Promise.resolve(null),
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
    setActiveTab('綜合研判')
  }

  // 從大盤排行等處點股票代碼 → 直接分析該股
  const goStock = (sym: string) => {
    setInput(sym)
    setShowSuggestions(false)
    setSymbol(sym)
    setView('stock')
    setActiveTab('綜合研判')
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
    setActiveTab('綜合研判')
  }

  return (
    <div className="min-h-screen bg-slate-950 text-slate-200">
      {/* Header */}
      <header className="border-b border-slate-800 bg-slate-900/80 backdrop-blur sticky top-0 z-10">
        <div className="max-w-6xl mx-auto px-4 py-3 flex items-center gap-4">
          <button onClick={() => setView('market')} className="text-lg font-bold text-blue-400 hover:text-blue-300 shrink-0">
            台股分析
          </button>
          <form onSubmit={handleSearch} className="flex gap-2 flex-1 max-w-sm relative" ref={searchRef}>
            <div className="flex-1 relative">
              <input
                value={input}
                onChange={e => { setInput(e.target.value); setShowSuggestions(true) }}
                onFocus={() => setShowSuggestions(true)}
                placeholder="代碼或中文名稱，如 2330 / 台積電"
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
                      <span className="text-slate-500 text-xs ml-auto">{s.market === 'twse' ? '上市' : '上櫃'}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
            <button type="submit" className="bg-blue-600 hover:bg-blue-500 px-4 py-1.5 rounded-lg text-sm font-medium shrink-0">
              查詢
            </button>
          </form>
          <nav className="flex items-center gap-3 text-sm shrink-0 ml-auto">
            <button onClick={() => setView('market')}
              className={view === 'market' ? 'text-blue-400 font-medium' : 'text-slate-400 hover:text-slate-200'}>
              大盤
            </button>
            <button onClick={() => setView('global')}
              className={view === 'global' ? 'text-blue-400 font-medium' : 'text-slate-400 hover:text-slate-200'}>
              全球
            </button>
            <button onClick={() => setView('futures')}
              className={view === 'futures' ? 'text-blue-400 font-medium' : 'text-slate-400 hover:text-slate-200'}>
              期貨
            </button>
            <button onClick={() => setView('macro')}
              className={view === 'macro' ? 'text-blue-400 font-medium' : 'text-slate-400 hover:text-slate-200'}>
              總經
            </button>
            {symbol && (
              <button onClick={() => setView('stock')}
                className={view === 'stock' ? 'text-blue-400 font-medium' : 'text-slate-400 hover:text-slate-200'}>
                {symbol}
              </button>
            )}
          </nav>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-4 py-6 space-y-6">
        {view === 'market' && (
          <Card title="大盤總覽">
            {market.error && <p className="text-red-400 text-sm">{market.error}</p>}
            <ErrorBoundary label="大盤總覽">
              <MarketOverview moneyFlow={market.data} onSelectStock={goStock} />
            </ErrorBoundary>
          </Card>
        )}

        {view === 'global' && (
          <ErrorBoundary label="全球盤勢">
            <GlobalPanel />
          </ErrorBoundary>
        )}

        {view === 'futures' && (
          <Card title="期貨 / 國際商品">
            <ErrorBoundary label="期貨">
              <FuturesPanel />
            </ErrorBoundary>
          </Card>
        )}

        {view === 'macro' && (
          <Card>
            <ErrorBoundary label="總體經濟">
              <MacroPanel onJumpGlobal={() => setView('global')} />
            </ErrorBoundary>
          </Card>
        )}

        {view === 'stock' && symbol && (
          <>
            {/* K 線圖 */}
            <Card title={`${symbol} · K 線圖`}>
              <div className="flex flex-wrap gap-1 mb-3">
                {CHART_TFS.map(o => (
                  <button key={o.tf} onClick={() => setChartTf(o.tf)}
                    className={`text-xs px-3 py-1 rounded-full ${chartTf === o.tf ? 'bg-blue-600 text-white' : 'bg-slate-800 text-slate-400 hover:bg-slate-700'}`}>
                    {o.label}
                  </button>
                ))}
              </div>
              {price.loading && <Spinner />}
              {price.data && (
                // key 強制在切時間框架時整個重建，避免 lightweight-charts 內部殘留狀態
                <ErrorBoundary label="K 線圖" onReset={() => setChartTf(chartTf)}>
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
                {TABS.map(t => (
                  <button key={t} onClick={() => setActiveTab(t)}
                    className={`px-4 py-2 text-sm -mb-px border-b-2 transition-colors ${activeTab === t ? 'border-blue-500 text-blue-400' : 'border-transparent text-slate-500 hover:text-slate-300'}`}>
                    {t}
                  </button>
                ))}
              </div>

              <Card>
                <ErrorBoundary label={activeTab}>
                  {activeTab === '綜合研判' && (
                    outlook.loading ? <Spinner /> : <OutlookPanel data={outlook.data} />
                  )}
                  {activeTab === '技術面' && (
                    technical.loading ? <Spinner /> : <TechnicalPanel data={technical.data} />
                  )}
                  {activeTab === '籌碼面' && (
                    chip.loading ? <Spinner /> : <ChipPanel data={chip.data} />
                  )}
                  {activeTab === '回測' && (
                    backtest.loading
                      ? <Spinner />
                      : <BacktestPanel data={backtest.data} signal={btSignal} onSignalChange={setBtSignal} />
                  )}
                  {activeTab === '基本面' && (
                    fundamentals.loading ? <Spinner /> : <FundamentalsPanel data={fundamentals.data} />
                  )}
                  {activeTab === '新聞' && (
                    news.loading ? <Spinner /> : <NewsPanel news={news.data?.news} />
                  )}
                </ErrorBoundary>
              </Card>
            </div>
          </>
        )}

        {view === 'stock' && !symbol && (
          <p className="text-slate-500 text-center py-12">輸入股票代碼開始分析</p>
        )}
      </main>
    </div>
  )
}
