import { useTranslation } from 'react-i18next'
import type { TFunction } from 'i18next'
import type { WeeklyWBottomScanResponse, WeeklyWBottomItem } from '../types'

const interp = { interpolation: { prefix: '{', suffix: '}' } }

interface Props {
  data: WeeklyWBottomScanResponse | null
  loading: boolean
  error: string | null
  scannedAt: string | null
  onRescan: () => void
  onSelectStock: (symbol: string) => void
}

function ItemRow({ item, onSelect, t }: { item: WeeklyWBottomItem; onSelect: (s: string) => void; t: TFunction }) {
  const isUp = item.ma20w_direction === 'up'
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
      <td className="py-2 px-3 text-right text-sm text-slate-300">{item.ma20w}</td>
      <td className="py-2 px-3 text-right">
        <span className={`text-xs font-medium ${item.ma20w_gap_pct < 1 ? 'text-green-400' : item.ma20w_gap_pct < 3 ? 'text-yellow-400' : 'text-slate-400'}`}>
          {item.ma20w_gap_pct}%
        </span>
      </td>
      <td className="py-2 px-3 text-center">
        <span className={`text-xs px-1.5 py-0.5 rounded-full ${isUp ? 'bg-green-900/60 text-green-300' : 'bg-slate-700 text-slate-400'}`}>
          {isUp ? t('wbottom_panel.dir_up') : t('wbottom_panel.dir_down')}
        </span>
      </td>
      <td className="py-2 px-3 text-right text-xs text-slate-500">
        {item.week_vol.toLocaleString()}
        {item.vol_threshold != null && (
          <span className="text-slate-600"> / {item.vol_threshold.toLocaleString()}</span>
        )}
      </td>
      <td className="py-2 px-3 text-right text-xs text-slate-500">{item.total_triggers}</td>
      <td className="py-2 px-3 text-right text-xs text-slate-500">{item.last_trigger ?? '—'}</td>
    </tr>
  )
}

export default function WeeklyWBottomScanPanel({ data, loading, error, scannedAt, onRescan, onSelectStock }: Props) {
  const { t } = useTranslation()
  return (
    <div className="space-y-4">
      {/* 控制列 */}
      <div className="flex flex-wrap items-center gap-3">
        <button
          onClick={onRescan}
          disabled={loading}
          className="text-xs px-3 py-1.5 rounded-lg bg-slate-700 hover:bg-slate-600 disabled:opacity-40 disabled:cursor-not-allowed text-slate-300 transition-colors"
        >
          {loading ? t('wbottom_panel.scanning') : t('wbottom_panel.rescan')}
        </button>
        <span className="text-xs text-slate-500">
          {loading && t('wbottom_panel.scanning_first_hint')}
          {!loading && data && t('wbottom_panel.scan_summary', { scanned: data.scanned, asOf: data.as_of ?? '—', updatedAt: scannedAt ?? '—', ...interp })}
        </span>
      </div>

      {/* 說明：首次掃描前顯示 */}
      {!data && !loading && !error && (
        <div className="bg-slate-800/60 rounded-lg p-4 text-xs text-slate-400 leading-relaxed space-y-1.5">
          <div className="text-slate-300 font-medium mb-1">{t('wbottom_panel.intro_title')}</div>
          <div>・<span className="text-green-400 font-medium">{t('wbottom_panel.cond_label', { n: 1, ...interp })}</span>：{t('wbottom_panel.cond1_desc')}</div>
          <div>・<span className="text-green-400 font-medium">{t('wbottom_panel.cond_label', { n: 2, ...interp })}</span>：{t('wbottom_panel.cond2_desc')}</div>
          <div>・<span className="text-green-400 font-medium">{t('wbottom_panel.cond_label', { n: 3, ...interp })}</span>：{t('wbottom_panel.cond3_desc')}</div>
          <div>・<span className="text-green-400 font-medium">{t('wbottom_panel.cond_label', { n: 4, ...interp })}</span>：{t('wbottom_panel.cond4_desc')}</div>
          <div className="text-slate-500 mt-2">{t('wbottom_panel.intro_footer')}</div>
        </div>
      )}

      {loading && (
        <div className="flex flex-col items-center py-10 gap-3">
          <div className="w-7 h-7 border-2 border-green-500 border-t-transparent rounded-full animate-spin" />
          <p className="text-sm text-slate-400">{t('wbottom_panel.scanning_full_market')}</p>
        </div>
      )}

      {error && <p className="text-red-400 text-sm">{error}</p>}

      {data && !loading && (
        <div className="space-y-4">
          <div className="bg-slate-900/60 border border-green-500/20 rounded-xl p-4">
            <div className="flex items-center gap-2 mb-3">
              <span className="text-sm font-semibold text-slate-300">{t('wbottom_panel.results_title')}</span>
              {data.triggered.length > 0
                ? <span className="text-xs px-2 py-0.5 rounded-full bg-slate-700 text-slate-300">{t('wbottom_panel.count_suffix', { count: data.triggered.length, ...interp })}</span>
                : null}
              <span className="text-xs text-slate-500">{t('wbottom_panel.four_conditions_met')}</span>
            </div>

            {data.triggered.length === 0 ? (
              <p className="text-xs text-slate-500 py-3 text-center">{t('wbottom_panel.no_matches')}</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-xs min-w-[600px]">
                  <thead>
                    <tr className="text-slate-500 text-left">
                      <th className="py-1.5 px-3 font-medium">{t('wbottom_panel.col_symbol_name')}</th>
                      <th className="py-1.5 px-3 text-right font-medium">{t('wbottom_panel.col_close')}</th>
                      <th className="py-1.5 px-3 text-right font-medium">{t('wbottom_panel.col_ma20w')}</th>
                      <th className="py-1.5 px-3 text-right font-medium">{t('wbottom_panel.col_gap_to_ma20')}</th>
                      <th className="py-1.5 px-3 text-center font-medium">{t('wbottom_panel.col_ma20_direction')}</th>
                      <th className="py-1.5 px-3 text-right font-medium">{t('wbottom_panel.col_week_vol_threshold')}</th>
                      <th className="py-1.5 px-3 text-right font-medium">{t('wbottom_panel.col_hist_count')}</th>
                      <th className="py-1.5 px-3 text-right font-medium">{t('wbottom_panel.col_last_trigger')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.triggered.map(item => (
                      <ItemRow key={item.symbol} item={item} onSelect={onSelectStock} t={t} />
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
          <p className="text-xs text-slate-600">{t('wbottom_panel.disclaimer')}</p>
        </div>
      )}
    </div>
  )
}
