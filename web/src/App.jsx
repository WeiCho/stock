import { useState, useEffect, useCallback } from 'react'
import { api } from './api'
import PriceChart from './components/PriceChart'
import TechnicalPanel from './components/TechnicalPanel'
import ChipPanel from './components/ChipPanel'
import BacktestPanel from './components/BacktestPanel'
import FundamentalsPanel from './components/FundamentalsPanel'
import NewsPanel from './components/NewsPanel'
import MarketOverview from './components/MarketOverview'

const TABS = ['技術面', '籌碼面', '回測', '基本面', '新聞']

function useAsync(fn, deps) {
  const [state, setState] = useState({ data: null, loading: false, error: null })
  useEffect(() => {
    let cancelled = false
    setState(s => ({ ...s, loading: true, error: null }))
    fn().then(data => {
      if (!cancelled) setState({ data, loading: false, error: null })
    }).catch(err => {
      if (!cancelled) setState({ data: null, loading: false, error: err.message })
    })
    return () => { cancelled = true }
  }, deps)
  return state
}

function Spinner() {
  return <div className="flex justify-center py-8"><div className="w-6 h-6 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" /></div>
}

function Card({ title, children, className = '' }) {
  return (
    <div className={`bg-slate-900 border border-slate-700 rounded-xl p-4 ${className}`}>
      {title && <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-3">{title}</h3>}
      {children}
    </div>
  )
}

// 把日K 資料切成 MA 序列
function buildMas(priceData, technicalData) {
  if (!priceData?.data?.length || !technicalData?.ma) return {}
  const maKeys = Object.keys(technicalData.ma)
  // 只取 close 序列，搭配 pandas-ta 已計算好的最終值
  // 在前端重新計算 MA，不需多一次 API
  const closes = priceData.data.map(r => ({ date: r.date, close: r.close }))
  const result = {}
  for (const key of maKeys) {
    const period = parseInt(key.replace('ma', ''))
    const series = []
    for (let i = period - 1; i < closes.length; i++) {
      const avg = closes.slice(i - period + 1, i + 1).reduce((s, r) => s + r.close, 0) / period
      series.push({ time: closes[i].date, value: parseFloat(avg.toFixed(2)) })
    }
    result[key] = series
  }
  return result
}

export default function App() {
  const [symbol, setSymbol] = useState('')
  const [input, setInput] = useState('')
  const [activeTab, setActiveTab] = useState('技術面')
  const [btSignal, setBtSignal] = useState('ma_cross')
  const [timeframe, setTimeframe] = useState('daily')
  const [view, setView] = useState('market') // 'market' | 'stock'

  // 大盤資料
  const market = useAsync(() => Promise.all([
    api.marketIndex(60),
    api.marketInstitutional(20),
  ]).then(([index, inst]) => ({ index, institutional: inst })), [])

  // 個股資料（當 symbol 改變時觸發）
  const price = useAsync(() => symbol ? api.price(symbol, 120) : Promise.resolve(null), [symbol])
  const technical = useAsync(() => symbol ? api.technical(symbol, timeframe) : Promise.resolve(null), [symbol, timeframe])
  const chip = useAsync(() => symbol ? api.chip(symbol) : Promise.resolve(null), [symbol])
  const backtest = useAsync(() => symbol ? api.backtest(symbol, btSignal) : Promise.resolve(null), [symbol, btSignal])
  const fundamentals = useAsync(() => symbol ? api.fundamentals(symbol) : Promise.resolve(null), [symbol])
  const news = useAsync(() => symbol ? api.news(symbol) : Promise.resolve(null), [symbol])

  const mas = buildMas(price.data, technical.data)

  const handleSearch = (e) => {
    e.preventDefault()
    const v = input.trim()
    if (!v) return
    setSymbol(v)
    setView('stock')
    setActiveTab('技術面')
  }

  return (
    <div className="min-h-screen bg-slate-950 text-slate-200">
      {/* Header */}
      <header className="border-b border-slate-800 bg-slate-900/80 backdrop-blur sticky top-0 z-10">
        <div className="max-w-6xl mx-auto px-4 py-3 flex items-center gap-4">
          <button onClick={() => setView('market')} className="text-lg font-bold text-blue-400 hover:text-blue-300 shrink-0">
            台股分析
          </button>
          <form onSubmit={handleSearch} className="flex gap-2 flex-1 max-w-sm">
            <input
              value={input}
              onChange={e => setInput(e.target.value)}
              placeholder="輸入股票代碼，如 2330"
              className="flex-1 bg-slate-800 border border-slate-600 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:border-blue-500"
            />
            <button type="submit" className="bg-blue-600 hover:bg-blue-500 px-4 py-1.5 rounded-lg text-sm font-medium">
              查詢
            </button>
          </form>
          {symbol && view === 'stock' && (
            <span className="text-slate-400 text-sm hidden sm:block">
              {symbol}
            </span>
          )}
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-4 py-6 space-y-6">
        {view === 'market' && (
          <Card title="大盤總覽">
            {market.loading && <Spinner />}
            {market.error && <p className="text-red-400 text-sm">{market.error}</p>}
            {market.data && <MarketOverview index={market.data.index} institutional={market.data.institutional} />}
          </Card>
        )}

        {view === 'stock' && symbol && (
          <>
            {/* K 線圖 */}
            <Card title={`${symbol} · K 線圖`}>
              <div className="flex gap-2 mb-3">
                {['daily', 'weekly'].map(tf => (
                  <button key={tf} onClick={() => setTimeframe(tf)}
                    className={`text-xs px-3 py-1 rounded-full ${timeframe === tf ? 'bg-blue-600 text-white' : 'bg-slate-800 text-slate-400 hover:bg-slate-700'}`}>
                    {tf === 'daily' ? '日K' : '週K'}
                  </button>
                ))}
              </div>
              {price.loading && <Spinner />}
              {price.data && <PriceChart data={price.data.data} mas={timeframe === 'daily' ? mas : {}} />}
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
