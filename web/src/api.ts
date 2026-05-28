const BASE = '/api'

async function get(path: string, params: Record<string, unknown> = {}) {
  const url = new URL(BASE + path, location.origin)
  Object.entries(params).forEach(([k, v]) => v !== undefined && url.searchParams.set(k, String(v)))
  const res = await fetch(url)
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`)
  return res.json()
}

export const api = {
  health: () => get('/health'),
  stock: (sym, company = '') => get(`/stock/${sym}`, { company_name: company }),
  technical: (sym, tf = 'daily') => get(`/stock/${sym}/technical`, { timeframe: tf }),
  outlook: (sym) => get(`/stock/${sym}/outlook`),
  chip: (sym) => get(`/stock/${sym}/chip`),
  backtest: (sym, signal = 'ma_cross') => get(`/stock/${sym}/backtest`, { signal }),
  pine: (sym, signal = 'ma_cross') => get(`/stock/${sym}/pine`, { signal }),
  news: (sym, name = '') => get(`/stock/${sym}/news`, { company_name: name, limit: 10 }),
  fundamentals: (sym) => get(`/stock/${sym}/fundamentals`),
  price: (sym, days = 120, tf = '1d') => get(`/stock/${sym}/price`, { days, tf }),
  stockIntraday: (sym, timeframe = '5') => get(`/stock/${sym}/intraday`, { timeframe }),
  marketIndex: (days = 60) => get('/market/index', { days }),
  indexLive: () => get('/market/index/live'),
  indexIntraday: (timeframe = '5') => get('/market/index/intraday', { timeframe }),
  marketInstitutional: (top = 20) => get('/market/institutional', { top }),
  moneyFlow: (topN = 10) => get('/market/money-flow', { top_n: topN }),
  bigOrders: (minAmount = 30000000, topN = 8) => get('/market/big-orders', { min_amount: minAmount, top_n: topN }),
  chipScan: (foreignDays = 3, trustDays = 0, topN = 20) =>
    get('/market/chip-scan', { min_foreign_days: foreignDays, min_trust_days: trustDays, top_n: topN }),
  signals: () => get('/backtest/signals'),
  searchStock: (q, limit = 10) => get('/stock/search', { q, limit }),
}
