import { useTranslation } from 'react-i18next'
import type { NewsItem } from '../types'

export default function NewsPanel({ news }: { news?: NewsItem[] }) {
  const { t } = useTranslation()
  if (!news?.length) return <p className="text-slate-500 text-sm">{t('news.empty')}</p>

  return (
    <ul className="space-y-2">
      {news.map((n, i) => (
        <li key={i} className="border-b border-slate-800 pb-2">
          <div className="flex items-start gap-2">
            {n.is_major && <span className="shrink-0 text-xs bg-red-900 text-red-300 px-1.5 py-0.5 rounded mt-0.5">{t('news.major_badge')}</span>}
            <a href={n.url} target="_blank" rel="noreferrer"
              className="text-sm text-slate-300 hover:text-blue-400 leading-snug">
              {n.title}
            </a>
          </div>
          <p className="text-xs text-slate-600 mt-0.5">{n.published_at?.slice(0, 10)}</p>
        </li>
      ))}
    </ul>
  )
}
