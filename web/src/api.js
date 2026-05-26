const BASE = '/api'

async function get(path, params = {}) {
  const url = new URL(BASE + path, location.origin)
  Object.entries(params).forEach(([k, v]) => v !== undefined && url.searchParams.set(k, v))
  const res = await fetch(url)
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`)
  return res.json()
}

export const api = {
  health: () => get('/health'),
  stock: (sym, company = '') => get(`/stock/${sym}`, { company_name: company }),
  technical: (sym, tf = 'daily') => get(`/stock/${sym}/technical`, { timeframe: tf }),
  chip: (sym) => get(`/stock/${sym}/chip`),
  backtest: (sym, signal = 'ma_cross') => get(`/stock/${sym}/backtest`, { signal }),
  pine: (sym, signal = 'ma_cross') => get(`/stock/${sym}/pine`, { signal }),
  news: (sym, name = '') => get(`/stock/${sym}/news`, { company_name: name, limit: 10 }),
  fundamentals: (sym) => get(`/stock/${sym}/fundamentals`),
  price: (sym, days = 120) => get(`/stock/${sym}/price`, { days }),
  marketIndex: (days = 60) => get('/market/index', { days }),
  marketInstitutional: (top = 20) => get('/market/institutional', { top }),
  chipScan: (foreignDays = 3, trustDays = 0, topN = 20) =>
    get('/market/chip-scan', { min_foreign_days: foreignDays, min_trust_days: trustDays, top_n: topN }),
  signals: () => get('/backtest/signals'),
  searchStock: (q, limit = 10) => get('/stock/search', { q, limit }),
}
