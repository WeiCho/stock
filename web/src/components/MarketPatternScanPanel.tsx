import { useTranslation } from 'react-i18next'
import type { MarketPatternScanResponse, MarketPatternItem } from '../types'

const interp = { interpolation: { prefix: '{', suffix: '}' } }

type Mode = 'both' | 'triggered' | 'setup'

export type { Mode as PatternScanMode }

interface Props {
  mode: Mode
  onModeChange: (m: Mode) => void
  data: MarketPatternScanResponse | null
  loading: boolean
  error: string | null
  scannedAt: string | null
  onRescan: () => void
  onSelectStock: (symbol: string) => void
}

function ItemRow({ item, onSelect }: { item: MarketPatternItem; onSelect: (s: string) => void }) {
  const { t } = useTranslation()
  const isUp = item.ma60_direction === 'up'
  return (
    <tr
      className="border-t border-slate-700/50 hover:bg-slate-800/60 cursor-pointer transition-colors"
      onClick={() => onSelect(item.symbol)}
    >
      <td className="py-2 px-3">
        <div className="font-medium text-blue-400 text-sm">{item.symbol}</div>
        <div className="text-xs text-slate-400 truncate max-w-[6rem]">{item.name}</div>
      </td>
      <td className="py-2 px-3 text-right text-sm text-slate-200">{item.close}</td>
      <td className="py-2 px-3 text-right text-sm text-slate-300">{item.ma60}</td>
      <td className="py-2 px-3 text-right">
        <span className={`text-xs font-medium ${item.ma60_gap_pct < 1 ? 'text-green-400' : item.ma60_gap_pct < 2 ? 'text-yellow-400' : 'text-slate-400'}`}>
          {item.ma60_gap_pct}%
        </span>
      </td>
      <td className="py-2 px-3 text-center">
        <span className={`text-xs px-1.5 py-0.5 rounded-full ${isUp ? 'bg-green-900/60 text-green-300' : 'bg-slate-700 text-slate-400'}`}>
          {isUp ? t('scan_panel.direction_up') : t('scan_panel.direction_down')}
        </span>
      </td>
      <td className="py-2 px-3 text-right text-xs text-slate-500">
        {item.prev_vol != null ? item.prev_vol.toLocaleString() : '—'}
        {item.vol_threshold != null && (
          <span className="text-slate-600"> / {item.vol_threshold.toLocaleString()}</span>
        )}
      </td>
      <td className="py-2 px-3 text-right text-xs text-slate-500">{item.last_trigger ?? '—'}</td>
    </tr>
  )
}

function ResultTable({
  title, badge, items, emptyText, onSelect,
}: {
  title: string
  badge: string
  badgeClass: string
  items: MarketPatternItem[]
  emptyText: string
  onSelect: (s: string) => void
}) {
  const { t } = useTranslation()
  if (items.length === 0) {
    return (
      <div className="space-y-2">
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold text-slate-300">{title}</span>
          <span className="text-xs text-slate-500">{badge}</span>
        </div>
        <p className="text-xs text-slate-500 py-3 text-center">{emptyText}</p>
      </div>
    )
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2">
        <span className="text-sm font-semibold text-slate-300">{title}</span>
        <span className="text-xs px-2 py-0.5 rounded-full bg-slate-700 text-slate-300">{items.length} {t('market.unit_stocks')}</span>
        <span className="text-xs text-slate-500">{badge}</span>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-xs min-w-[560px]">
          <thead>
            <tr className="text-slate-500 text-left">
              <th className="py-1.5 px-3 font-medium">{t('scan_panel.col_symbol_name')}</th>
              <th className="py-1.5 px-3 text-right font-medium">{t('scan_panel.col_close')}</th>
              <th className="py-1.5 px-3 text-right font-medium">{t('scan_panel.col_ma60')}</th>
              <th className="py-1.5 px-3 text-right font-medium">{t('scan_panel.col_ma60_gap')}</th>
              <th className="py-1.5 px-3 text-center font-medium">{t('scan_panel.col_ma60_direction')}</th>
              <th className="py-1.5 px-3 text-right font-medium">{t('scan_panel.col_prev_vol_threshold')}</th>
              <th className="py-1.5 px-3 text-right font-medium">{t('scan_panel.col_last_trigger')}</th>
            </tr>
          </thead>
          <tbody>
            {items.map(item => (
              <ItemRow key={item.symbol} item={item} onSelect={onSelect} />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

const MODES: { value: Mode; labelKey: string }[] = [
  { value: 'both',      labelKey: 'scan_panel.mode_both' },
  { value: 'triggered', labelKey: 'scan_panel.mode_triggered' },
  { value: 'setup',     labelKey: 'scan_panel.mode_setup' },
]

export default function MarketPatternScanPanel({
  mode, onModeChange, data, loading, error, scannedAt, onRescan, onSelectStock,
}: Props) {
  const { t } = useTranslation()
  return (
    <div className="space-y-4">
      {/* 控制列 */}
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex gap-1.5">
          {MODES.map(m => (
            <button
              key={m.value}
              onClick={() => onModeChange(m.value)}
              className={`text-xs px-3 py-1.5 rounded-full transition-colors ${
                mode === m.value ? 'bg-blue-600 text-white' : 'bg-slate-800 text-slate-400 hover:bg-slate-700'
              }`}
            >
              {t(m.labelKey)}
            </button>
          ))}
        </div>
        <button
          onClick={onRescan}
          disabled={loading}
          className="text-xs px-3 py-1.5 rounded-lg bg-slate-700 hover:bg-slate-600 disabled:opacity-40 disabled:cursor-not-allowed text-slate-300 transition-colors"
        >
          {loading ? t('scan_panel.scanning') : t('scan_panel.rescan')}
        </button>
        <span className="text-xs text-slate-500">
          {loading && t('scan_panel.scanning_first_time')}
          {!loading && data && t('scan_panel.scan_summary', {
            scanned: data.scanned,
            asOf: data.as_of ?? '—',
            updatedAt: scannedAt ?? '—',
            ...interp,
          })}
        </span>
      </div>

      {/* 說明：首次掃描前顯示 */}
      {!data && !loading && !error && (
        <div className="bg-slate-800/60 rounded-lg p-4 text-xs text-slate-400 leading-relaxed space-y-1.5">
          <div className="text-slate-300 font-medium mb-1">{t('scan_panel.intro_title')}</div>
          <div>・<span className="text-orange-400 font-medium">{t('scan_panel.intro_triggered_label')}</span>{t('scan_panel.intro_triggered_desc')}</div>
          <div>・<span className="text-blue-400 font-medium">{t('scan_panel.intro_setup_label')}</span>{t('scan_panel.intro_setup_desc')}</div>
          <div className="text-slate-500 mt-2">{t('scan_panel.intro_hint')}</div>
        </div>
      )}

      {loading && (
        <div className="flex flex-col items-center py-10 gap-3">
          <div className="w-7 h-7 border-2 border-orange-500 border-t-transparent rounded-full animate-spin" />
          <p className="text-sm text-slate-400">{t('scan_panel.loading_text')}</p>
        </div>
      )}

      {error && <p className="text-red-400 text-sm">{error}</p>}

      {data && !loading && (
        <div className="space-y-6">
          {(mode === 'triggered' || mode === 'both') && (
            <div className="bg-slate-900/60 border border-orange-500/20 rounded-xl p-4">
              <ResultTable
                title={t('scan_panel.triggered_title')}
                badge={t('scan_panel.triggered_badge')}
                badgeClass="bg-orange-900/60 text-orange-300"
                items={data.triggered}
                emptyText={t('scan_panel.triggered_empty')}
                onSelect={onSelectStock}
              />
            </div>
          )}

          {(mode === 'setup' || mode === 'both') && (
            <div className="bg-slate-900/60 border border-blue-500/20 rounded-xl p-4">
              <ResultTable
                title={t('scan_panel.setup_title')}
                badge={t('scan_panel.setup_badge')}
                badgeClass="bg-blue-900/60 text-blue-300"
                items={data.setup}
                emptyText={t('scan_panel.setup_empty')}
                onSelect={onSelectStock}
              />
            </div>
          )}

          <p className="text-xs text-slate-600">{t('scan_panel.disclaimer')}</p>
        </div>
      )}
    </div>
  )
}
