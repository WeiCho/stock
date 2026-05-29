import type {
  PriceResponse, BacktestResponse, TechnicalResponse, OutlookResponse,
  FundamentalsResponse, NewsItem, PineResponse, PatternScanResponse,
} from './types'

const BASE = '/api'

async function get<T = unknown>(path: string, params: Record<string, unknown> = {}): Promise<T> {
  const url = new URL(BASE + path, location.origin)
  Object.entries(params).forEach(([k, v]) => v !== undefined && url.searchParams.set(k, String(v)))
  const res = await fetch(url)
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`)
  return res.json() as Promise<T>
}

export const api = {
  health: () => get<{ status: string }>('/health'),
  stock: (sym: string, company = '') => get(`/stock/${sym}`, { company_name: company }),
  technical: (sym: string, tf = 'daily') => get<TechnicalResponse>(`/stock/${sym}/technical`, { timeframe: tf }),
  outlook: (sym: string) => get<OutlookResponse>(`/stock/${sym}/outlook`),
  chip: (sym: string) => get<import('./types').ChipResponse>(`/stock/${sym}/chip`),
  backtest: (sym: string, signal = 'ma_cross') => get<BacktestResponse>(`/stock/${sym}/backtest`, { signal }),
  pine: (sym: string, signal = 'ma_cross') => get<PineResponse>(`/stock/${sym}/pine`, { signal }),
  news: (sym: string, name = '') => get<{ news: NewsItem[] }>(`/stock/${sym}/news`, { company_name: name, limit: 10 }),
  fundamentals: (sym: string) => get<FundamentalsResponse>(`/stock/${sym}/fundamentals`),
  price: (sym: string, days = 120, tf = '1d') => get<PriceResponse>(`/stock/${sym}/price`, { days, tf }),
  stockIntraday: (sym: string, timeframe = '5') => get<PriceResponse>(`/stock/${sym}/intraday`, { timeframe }),
  stockQuote: (sym: string) => get<{
    symbol: string; last?: number; previousClose?: number; open?: number; high?: number; low?: number; avg?: number
    change?: number; change_pct?: number; volume?: number
    bids?: { price: number; size: number }[]; asks?: { price: number; size: number }[]; time?: string
  }>(`/stock/${sym}/quote`),
  marketIndex: (days = 60) => get<PriceResponse>('/market/index', { days }),
  indexLive: () => get<{ index?: number; change?: number; change_pct?: number; date?: string; time?: string }>('/market/index/live'),
  indexIntraday: (timeframe = '5') => get<PriceResponse>('/market/index/intraday', { timeframe }),
  moneyFlow: (topN = 10) => get<import('./types').MoneyFlowResponse>('/market/money-flow', { top_n: topN }),
  bigOrders: (minAmount = 30000000, topN = 8) => get<{ available?: boolean; orders?: import('./types').BigOrder[] }>('/market/big-orders', { min_amount: minAmount, top_n: topN }),
  patternScan: (sym: string) => get<PatternScanResponse>(`/stock/${sym}/pattern-scan`),
  marketPatternScan: (mode = 'both') => get<import('./types').MarketPatternScanResponse>('/market/pattern-scan', { mode }),
  weeklyWBottomScan: () => get<import('./types').WeeklyWBottomScanResponse>('/market/weekly-w-bottom-scan'),
  signals: () => get<Record<string, string>>('/backtest/signals'),
  searchStock: (q: string, limit = 10) => get<{ results: { symbol: string; name: string; market: string }[] }>('/stock/search', { q, limit }),
  globalNews: (category = 'all', perCat = 8) => get('/market/global', { category, per_cat: perCat }),
  // 期貨 / 商品 / 總經
  commodity: (sym: string, days = 365, tf = '1d') => get<import('./types').PriceResponse & { label: string; perf?: Record<string, number>; regularMarketPrice?: number }>(`/market/commodity/${sym}/price`, { days, tf }),
  commodities: () => get<{ items: { symbol: string; label: string; source: string; currency: string }[] }>('/market/commodities'),
  futuresInstitutional: (sym = 'TX', days = 30) =>
    get<{ symbol: string; label: string; data: { date: string; foreign_net?: number; trust_net?: number; dealer_net?: number }[] }>('/market/futures/institutional', { symbol: sym, days }),
  macroEconomic: () =>
    get<{ available: boolean; indicators: { series_id: string; label: string; unit: string; note?: string; latest_date: string; latest_value: number; mom_change_pct?: number | null; yoy_change_pct?: number | null }[] }>('/market/macro/economic'),
  macroSeries: (id: string, years = 3) =>
    get<{ series_id: string; label: string; unit: string; freq: string; note?: string; data: { date: string; value: number }[] }>(`/market/macro/series/${id}`, { years }),
  // 台股進階基本面 + 籌碼
  monthlyRevenue: (sym: string, months = 24) =>
    get<{
      symbol: string
      data: { year: number; month: number; date: string; revenue: number; revenue_億: number; mom_pct: number | null; yoy_pct: number | null }[]
      latest?: { year: number; month: number; revenue_億: number; mom_pct: number | null; yoy_pct: number | null; note: string }
    }>(`/stock/${sym}/monthly-revenue`, { months }),
  foreignHolding: (sym: string, weeks = 26) =>
    get<{
      symbol: string
      data: { date: string; foreign_ratio: number | null; foreign_remain_ratio: number | null }[]
      latest?: { date: string; foreign_ratio: number | null; change_4w_pp?: number; note?: string }
    }>(`/stock/${sym}/foreign-holding`, { weeks }),
  marginShort: (sym: string, days = 30) =>
    get<{
      symbol: string
      data: { date: string; margin_balance: number; margin_change: number; short_balance: number; short_change: number }[]
      latest?: { date: string; margin_balance: number; margin_change: number; short_balance: number; short_change: number }
    }>(`/stock/${sym}/margin-short`, { days }),
  securitiesLending: (sym: string, days = 30) =>
    get<{
      symbol: string
      data: { date: string; volume: number; avg_fee_rate: number }[]
      latest?: { date: string; volume: number; avg_fee_rate: number }
    }>(`/stock/${sym}/securities-lending`, { days }),
  yieldCurve: (years = 5) =>
    get<{ data: { date: string; value: number }[]; latest: number | null; status: 'normal' | 'flat' | 'inverted' | 'unavailable'; note: string }>('/market/macro/yield-curve', { years }),
  // 加密 + 匯率
  cryptoTop: (limit = 10) =>
    get<{
      available: boolean
      items?: { symbol: string; name: string; price: number; market_cap: number; market_cap_rank: number; volume_24h: number; change_24h_pct: number; change_7d_pct?: number; change_30d_pct?: number; image?: string }[]
    }>('/market/crypto/top', { limit }),
  cryptoGlobal: () =>
    get<{ available: boolean; total_market_cap_usd?: number; btc_dominance?: number; eth_dominance?: number; market_cap_change_pct_24h?: number; active_cryptocurrencies?: number }>('/market/crypto/global'),
  fx: (base = 'USD') =>
    get<{ available: boolean; base: string; date?: string; rates: Record<string, number> }>('/market/fx', { base }),
  movers: (top = 10) =>
    get<{
      available: boolean
      date?: string
      total_stocks?: number
      breadth?: { up: number; down: number; flat: number; limit_up: number; limit_down: number }
      by_value?: { symbol: string; name: string; close: number; change_pct: number; trade_value: number }[]
      gainers?: { symbol: string; name: string; close: number; change_pct: number }[]
      losers?: { symbol: string; name: string; close: number; change_pct: number }[]
      by_volume?: { symbol: string; name: string; close: number; change_pct: number; volume: number }[]
    }>('/market/movers', { top }),
  // TWSE OpenAPI 官方估值（免 key / 免額度）
  valuation: (top = 10) =>
    get<{
      available: boolean
      date?: string
      low_per?: { symbol: string; name: string; per: number; pbr?: number | null; dividend_yield?: number | null }[]
      high_yield?: { symbol: string; name: string; dividend_yield: number; per?: number | null; pbr?: number | null }[]
    }>('/market/valuation', { top }),
  stockValuation: (sym: string) =>
    get<{ available: boolean; symbol: string; date?: string; name?: string; per?: number | null; pbr?: number | null; dividend_yield?: number | null }>(`/stock/${sym}/valuation`),
  // SEC EDGAR Form 4
  insider: (sym: string, limit = 20) =>
    get<{
      ticker: string; cik?: string; company_name?: string
      transactions?: { date: string; form: string; accession: string; url: string; filing_url: string }[]
      count?: number; error?: string
    }>(`/stock/${sym}/insider`, { limit }),
  futuresPcr: (days = 30) =>
    get<{
      data: { date: string; pcr_volume: number | null; pcr_oi: number | null; call_volume: number; put_volume: number }[]
      latest: { date: string; pcr_volume: number | null; pcr_oi: number | null; volume_category?: string; note?: string } | null
      error?: string
    }>('/market/futures/pcr', { days }),
  // Finnhub — 經濟事件 / 個股財報 / 分析師評等
  macroCalendar: (daysAhead = 30, minImpact = 'high') =>
    get<{
      available: boolean
      events?: { date: string; time: string; country: string; event: string; impact: string; prev?: number | null; estimate?: number | null; actual?: number | null; unit?: string }[]
      count?: number
      note?: string
    }>('/market/macro/calendar', { days_ahead: daysAhead, min_impact: minImpact }),
  stockEarnings: (sym: string) =>
    get<{ available: boolean; symbol?: string; earnings?: { date: string; epsActual?: number; epsEstimate?: number; revenueActual?: number; revenueEstimate?: number }[] }>(`/stock/${sym}/earnings`),
  stockRecommendations: (sym: string) =>
    get<{ available: boolean; symbol?: string; recommendations?: { period: string; buy: number; hold: number; sell: number; strongBuy: number; strongSell: number }[] }>(`/stock/${sym}/recommendations`),
}
