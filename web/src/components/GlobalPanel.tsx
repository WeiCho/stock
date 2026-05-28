import { useEffect, useState } from 'react'
import { api } from '../api'

interface GlobalNewsItem {
  title: string
  url: string
  source?: string
  published_at?: string
}
interface GlobalCategory {
  key: string
  label: string
  news: GlobalNewsItem[]
}
interface GlobalResponse {
  categories: GlobalCategory[]
  fetched_at?: string
}

// 把 ISO datetime → 在地時間 HH:MM
function timeAgo(iso?: string): string {
  if (!iso) return ''
  const t = new Date(iso).getTime()
  if (isNaN(t)) return ''
  const diff = (Date.now() - t) / 60000  // 分鐘
  if (diff < 60) return `${Math.max(1, Math.round(diff))} 分鐘前`
  if (diff < 60 * 24) return `${Math.round(diff / 60)} 小時前`
  return `${Math.round(diff / 60 / 24)} 天前`
}

export default function GlobalPanel() {
  const [data, setData] = useState<GlobalResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const fetch = () => {
    setLoading(true)
    setError(null)
    api.globalNews('all', 8)
      .then((d) => setData(d as GlobalResponse))
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }

  useEffect(() => { fetch() }, [])

  return (
    <div className="space-y-4">
      <div className="flex items-baseline justify-between">
        <div>
          <h2 className="text-lg font-bold text-slate-100">全球盤勢 · 地緣動態</h2>
          <p className="text-xs text-slate-500 mt-1">
            亞、歐、美三大市場 + 地緣政治關鍵字 · 來源 Google News · 後端 30 分鐘快取
            {data?.fetched_at && <span className="ml-2">· 最後抓取 {timeAgo(data.fetched_at)}</span>}
          </p>
        </div>
        <button onClick={fetch} disabled={loading}
          className="text-xs px-3 py-1 rounded bg-slate-700 hover:bg-slate-600 disabled:opacity-50 text-slate-200">
          {loading ? '更新中…' : '重新抓取'}
        </button>
      </div>

      {error && <p className="text-red-400 text-sm">{error}</p>}

      {!data && loading && <p className="text-slate-500 text-sm">載入中…</p>}

      {data?.categories && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {data.categories.map(cat => (
            <div key={cat.key} className="bg-slate-900 border border-slate-800 rounded-xl p-4">
              <h3 className="text-sm font-semibold text-slate-300 mb-2 flex items-baseline gap-2">
                <span>{cat.label}</span>
                <span className="text-xs text-slate-500">{cat.news.length} 則</span>
              </h3>
              {cat.news.length === 0 ? (
                <p className="text-xs text-slate-600">暫無近 36 小時新聞</p>
              ) : (
                <ul className="space-y-2">
                  {cat.news.map((n, i) => (
                    <li key={i} className="border-b border-slate-800 pb-2 last:border-b-0">
                      <a href={n.url} target="_blank" rel="noreferrer"
                        className="text-sm text-slate-300 hover:text-blue-400 leading-snug block">
                        {n.title}
                      </a>
                      <div className="flex items-center gap-2 mt-1 text-[10px] text-slate-600">
                        {n.source && <span>{n.source}</span>}
                        {n.published_at && <span>· {timeAgo(n.published_at)}</span>}
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
