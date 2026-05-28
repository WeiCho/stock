import type {
  PriceResponse, BacktestResponse, TechnicalResponse, OutlookResponse,
  FundamentalsResponse, NewsItem, PineResponse,
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
  marketIndex: (days = 60) => get<PriceResponse>('/market/index', { days }),
  indexLive: () => get<{ index?: number; change?: number; change_pct?: number; date?: string; time?: string }>('/market/index/live'),
  indexIntraday: (timeframe = '5') => get<PriceResponse>('/market/index/intraday', { timeframe }),
  moneyFlow: (topN = 10) => get<import('./types').MoneyFlowResponse>('/market/money-flow', { top_n: topN }),
  bigOrders: (minAmount = 30000000, topN = 8) => get<{ available?: boolean; orders?: import('./types').BigOrder[] }>('/market/big-orders', { min_amount: minAmount, top_n: topN }),
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
}
