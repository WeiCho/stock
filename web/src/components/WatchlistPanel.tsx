import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

// JSON 字典用單大括號 {var} 內插，覆寫 i18next 預設的 {{var}}
const interp = { interpolation: { prefix: '{', suffix: '}' } }

interface WatchItem { id: number; symbol: string; name?: string; note?: string; added_at: string }
interface Condition {
  id: number; symbol: string; indicator: string; op: string;
  threshold: number; enabled: boolean
  current_value?: number | null; triggered?: boolean; as_of?: string
}

// label 為純技術代號者不需翻譯；MACD 柱狀 / 收盤價 透過 i18nKey 顯示
const INDICATORS: { v: string; label?: string; i18nKey?: string }[] = [
  { v: 'rsi', label: 'RSI(14)' },
  { v: 'kd_k', label: 'KD K' },
  { v: 'kd_d', label: 'KD D' },
  { v: 'macd_hist', i18nKey: 'watchlist.indicator.macd_hist' },
  { v: 'close', i18nKey: 'watchlist.indicator.close' },
]
const OPS = [
  { v: 'lt', label: '<' },
  { v: 'gt', label: '>' },
]

async function jsonFetch<T>(url: string, opts: RequestInit = {}): Promise<T> {
  const res = await fetch(url, {
    ...opts,
    headers: { 'Content-Type': 'application/json', ...(opts.headers || {}) },
  })
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`)
  return res.json() as Promise<T>
}

export default function WatchlistPanel({ onSelectStock }: { onSelectStock?: (s: string) => void }) {
  const { t } = useTranslation()
  const [items, setItems] = useState<WatchItem[]>([])
  const [conditions, setConditions] = useState<Condition[]>([])
  const [newSym, setNewSym] = useState('')
  const [newCondSym, setNewCondSym] = useState('')
  const [newCondInd, setNewCondInd] = useState('rsi')
  const [newCondOp, setNewCondOp] = useState('lt')
  const [newCondThr, setNewCondThr] = useState('30')
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const reload = async () => {
    setLoading(true)
    try {
      const [w, s] = await Promise.all([
        jsonFetch<{ items: WatchItem[] }>('/api/watchlist'),
        jsonFetch<{ conditions: Condition[] }>('/api/watchlist/status'),
      ])
      setItems(w.items)
      setConditions(s.conditions)
      setError(null)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }
  useEffect(() => { reload() }, [])

  const addSymbol = async (e: React.FormEvent) => {
    e.preventDefault()
    const s = newSym.trim().toUpperCase()
    if (!s) return
    await jsonFetch('/api/watchlist', { method: 'POST', body: JSON.stringify({ symbol: s }) })
    setNewSym('')
    reload()
  }

  const removeSymbol = async (s: string) => {
    if (!confirm(t('watchlist.remove_confirm', { symbol: s, ...interp }))) return
    await jsonFetch(`/api/watchlist/${s}`, { method: 'DELETE' })
    reload()
  }

  const addCondition = async (e: React.FormEvent) => {
    e.preventDefault()
    const s = newCondSym.trim().toUpperCase()
    const thr = parseFloat(newCondThr)
    if (!s || isNaN(thr)) return
    await jsonFetch('/api/watchlist/conditions', {
      method: 'POST',
      body: JSON.stringify({ symbol: s, indicator: newCondInd, op: newCondOp, threshold: thr }),
    })
    setNewCondSym('')
    reload()
  }

  const removeCondition = async (cid: number) => {
    await jsonFetch(`/api/watchlist/conditions/${cid}`, { method: 'DELETE' })
    reload()
  }

  // 條件依 symbol 分組
  const condBySym: Record<string, Condition[]> = {}
  for (const c of conditions) (condBySym[c.symbol] ||= []).push(c)

  const triggeredCount = conditions.filter(c => c.triggered).length

  return (
    <div className="space-y-5">
      <header className="flex items-baseline justify-between">
        <div>
          <h2 className="text-lg font-bold text-slate-100">{t('watchlist.title')}</h2>
          <p className="text-xs text-slate-500 mt-1">
            {t('watchlist.description')}
          </p>
        </div>
        <button onClick={reload} disabled={loading}
          className="text-xs px-3 py-1 rounded bg-slate-700 hover:bg-slate-600 disabled:opacity-50 text-slate-200">
          {loading ? t('common.updating') : t('watchlist.reevaluate')}
        </button>
      </header>

      {error && <p className="text-red-400 text-sm">{error}</p>}

      {triggeredCount > 0 && (
        <div className="bg-amber-950/40 border border-amber-800/50 rounded-lg p-3 text-sm">
          🔥 <b className="text-amber-300">{triggeredCount}</b> {t('watchlist.triggered_banner_suffix')}
        </div>
      )}

      {/* 加入股票 */}
      <section>
        <p className="text-xs text-slate-500 uppercase mb-2">{t('watchlist.add_section_title')}</p>
        <form onSubmit={addSymbol} className="flex gap-2">
          <input value={newSym} onChange={e => setNewSym(e.target.value)}
            placeholder={t('watchlist.symbol_placeholder')}
            className="flex-1 bg-slate-800 border border-slate-600 rounded px-3 py-1.5 text-sm focus:outline-none focus:border-blue-500" />
          <button type="submit"
            className="bg-blue-600 hover:bg-blue-500 px-4 py-1.5 rounded text-sm font-medium">
            {t('common.add')}
          </button>
        </form>
      </section>

      {/* 已關注清單 */}
      {items.length > 0 && (
        <section>
          <p className="text-xs text-slate-500 uppercase mb-2">{t('watchlist.watching_count', { count: items.length, ...interp })}</p>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
            {items.map(it => {
              const conds = condBySym[it.symbol] || []
              return (
                <div key={it.id} className="bg-slate-800/50 border border-slate-700 rounded-lg p-3">
                  <div className="flex items-center justify-between">
                    <button onClick={() => onSelectStock?.(it.symbol)}
                      className="text-left hover:text-blue-400">
                      <span className="font-mono text-blue-300 text-base">{it.symbol}</span>
                      {it.name && <span className="text-slate-400 ml-2">{it.name}</span>}
                    </button>
                    <button onClick={() => removeSymbol(it.symbol)}
                      className="text-xs text-slate-500 hover:text-red-400">{t('common.remove')}</button>
                  </div>
                  {conds.length === 0 ? (
                    <p className="text-[10px] text-slate-600 mt-2">{t('watchlist.no_conditions')}</p>
                  ) : (
                    <ul className="mt-2 space-y-1 text-xs">
                      {conds.map(c => {
                        const ind = INDICATORS.find(i => i.v === c.indicator)
                        const indLabel = ind?.i18nKey ? t(ind.i18nKey) : (ind?.label ?? c.indicator)
                        const opLabel = c.op === 'lt' ? '<' : '>'
                        return (
                          <li key={c.id} className={`flex items-center justify-between p-1.5 rounded ${
                            c.triggered ? 'bg-amber-950/60 border border-amber-800/40' : 'bg-slate-900/40'
                          }`}>
                            <span className="font-mono">
                              {c.triggered && '🔥 '}
                              {indLabel} {opLabel} {c.threshold}
                              <span className="text-slate-500 ml-2">
                                {t('watchlist.current_value_label')} {c.current_value != null ? c.current_value.toFixed(2) : '—'}
                              </span>
                            </span>
                            <button onClick={() => removeCondition(c.id)}
                              className="text-slate-600 hover:text-red-400 text-[10px] ml-2">×</button>
                          </li>
                        )
                      })}
                    </ul>
                  )}
                </div>
              )
            })}
          </div>
        </section>
      )}

      {/* 加條件 */}
      <section>
        <p className="text-xs text-slate-500 uppercase mb-2">{t('watchlist.add_condition_section_title')}</p>
        <form onSubmit={addCondition} className="flex flex-wrap gap-2 items-center">
          <input value={newCondSym} onChange={e => setNewCondSym(e.target.value)}
            placeholder={t('watchlist.code_placeholder')}
            className="bg-slate-800 border border-slate-600 rounded px-3 py-1.5 text-sm w-24 focus:outline-none focus:border-blue-500" />
          <select value={newCondInd} onChange={e => setNewCondInd(e.target.value)}
            className="bg-slate-800 border border-slate-600 rounded px-2 py-1.5 text-sm">
            {INDICATORS.map(i => <option key={i.v} value={i.v}>{i.i18nKey ? t(i.i18nKey) : i.label}</option>)}
          </select>
          <select value={newCondOp} onChange={e => setNewCondOp(e.target.value)}
            className="bg-slate-800 border border-slate-600 rounded px-2 py-1.5 text-sm">
            {OPS.map(o => <option key={o.v} value={o.v}>{o.label}</option>)}
          </select>
          <input value={newCondThr} onChange={e => setNewCondThr(e.target.value)}
            type="number" step="0.01" placeholder="threshold"
            className="bg-slate-800 border border-slate-600 rounded px-3 py-1.5 text-sm w-28 focus:outline-none focus:border-blue-500" />
          <button type="submit"
            className="bg-blue-600 hover:bg-blue-500 px-4 py-1.5 rounded text-sm font-medium">
            {t('watchlist.add_condition_button')}
          </button>
        </form>
        <p className="text-[10px] text-slate-600 mt-2">
          {t('watchlist.condition_examples')}
        </p>
      </section>

      {items.length === 0 && conditions.length === 0 && (
        <p className="text-center text-slate-500 py-12 text-sm">
          {t('watchlist.empty_state')}
        </p>
      )}
    </div>
  )
}
