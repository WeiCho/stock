import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { TFunction } from 'i18next'
import { api } from '../api'
import type { PatternScanResponse, PatternResult, PatternBacktestStat } from '../types'

const interp = { interpolation: { prefix: '{', suffix: '}' } }

interface Props { symbol: string }

function CheckRow({ ok, text, bonus = false }: { ok: boolean; text: string; bonus?: boolean }) {
  const icon  = bonus ? (ok ? '★' : '☆') : (ok ? '✓' : '✗')
  const color = bonus
    ? (ok ? 'text-orange-400' : 'text-slate-600')
    : (ok ? 'text-green-400'  : 'text-slate-600')
  return (
    <div className="flex items-start gap-2 py-0.5">
      <span className={`text-sm flex-shrink-0 mt-0.5 ${color}`}>{icon}</span>
      <span className={`text-xs leading-relaxed ${ok ? 'text-slate-300' : 'text-slate-500'}`}>{text}</span>
    </div>
  )
}

function buildReasons(p: PatternResult, t: TFunction) {
  const d = p.diagnostics
  const spread    = d.ma_spread ?? null
  const threshold = d.close != null ? +(d.close * 0.03).toFixed(2) : null
  const ma60Up    = p.current.ma60_direction === 'up'
  const ma60Slope = d.ma60_slope

  // 第一層：蓄勢條件（三線交纏 + 站上三線 + 接近 MA60）
  const setup = [
    {
      ok: d.cond_tangle ?? false,
      text: spread != null && threshold != null
        ? t('pattern_panel.reason.tangle', { spread, threshold, ...interp })
        : t('pattern_panel.reason.tangle_insufficient'),
    },
    {
      ok: d.cond_above_three ?? false,
      text: d.close != null
        ? t('pattern_panel.reason.above_three', { close: d.close, ...interp })
        : t('pattern_panel.reason.above_three_pending'),
    },
    {
      ok: d.cond_near_ma60 ?? false,
      text: d.ma60_gap != null && d.ma60 != null && d.ma60_gap_pct != null
        ? t('pattern_panel.reason.near_ma60', { ma60: d.ma60, gap: d.ma60_gap, gapPct: d.ma60_gap_pct, ...interp })
        : t('pattern_panel.reason.near_ma60_pending'),
    },
  ]

  // 第二層：突破確認條件（帶量 + 站穩 2 日）
  const breakout = [
    {
      ok: d.cond_support ?? false,
      text: d.prev_vol != null && d.vol_threshold != null
        ? t('pattern_panel.reason.support', { prevVol: d.prev_vol.toLocaleString(), threshold: d.vol_threshold.toLocaleString(), ...interp })
        : t('pattern_panel.reason.support_pending'),
    },
    {
      ok: d.cond_above_ma20 ?? false,
      text: d.close != null && d.ma60 != null
        ? t('pattern_panel.reason.above_ma20', { ma60: d.ma60, close: d.close, ...interp })
        : t('pattern_panel.reason.above_ma20_pending'),
    },
    {
      ok: d.cond_first_break ?? false,
      text: d.prev_close != null && d.prev_ma60 != null
        ? t('pattern_panel.reason.first_break', { prevClose: d.prev_close, prevMa60: d.prev_ma60, ...interp })
        : t('pattern_panel.reason.first_break_pending'),
    },
  ]

  return {
    setup,
    breakout,
    bonus: [
      {
        ok: ma60Up,
        text: ma60Up
          ? t('pattern_panel.reason.ma60_up', { slope: ma60Slope, ...interp })
          : ma60Slope != null && ma60Slope < 0
            ? t('pattern_panel.reason.ma60_down', { slope: ma60Slope, ...interp })
            : t('pattern_panel.reason.ma60_flat'),
      },
    ],
  }
}

function BacktestStatsTable({ stats }: { stats: PatternBacktestStat[] }) {
  const { t } = useTranslation()
  return (
    <div className="bg-slate-800/60 rounded-lg p-3">
      <div className="text-xs text-slate-500 mb-3 font-medium uppercase tracking-wide">{t('pattern_panel.backtest_stats_title')}</div>
      <table className="w-full text-xs">
        <thead>
          <tr className="text-slate-500">
            <th className="text-left pb-2 font-medium">{t('pattern_panel.col_hold_days')}</th>
            <th className="text-right pb-2 font-medium">{t('pattern_panel.col_sample')}</th>
            <th className="text-right pb-2 font-medium">{t('pattern_panel.col_win_rate')}</th>
            <th className="text-right pb-2 font-medium">{t('pattern_panel.col_avg_return')}</th>
            <th className="text-right pb-2 font-medium">{t('pattern_panel.col_max_gain')}</th>
            <th className="text-right pb-2 font-medium">{t('pattern_panel.col_max_loss')}</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-700/50">
          {stats.map(s => {
            const winColor = s.win_rate >= 60 ? 'text-green-400' : s.win_rate >= 50 ? 'text-yellow-400' : 'text-red-400'
            const retColor = s.avg_return > 0 ? 'text-green-400' : 'text-red-400'
            return (
              <tr key={s.hold_days} className="text-slate-300">
                <td className="py-1.5 text-slate-400">{t('pattern_panel.hold_days_value', { days: s.hold_days, ...interp })}</td>
                <td className="text-right py-1.5 text-slate-500">{s.sample_count}</td>
                <td className={`text-right py-1.5 font-semibold ${winColor}`}>{s.win_rate}%</td>
                <td className={`text-right py-1.5 font-semibold ${retColor}`}>{s.avg_return > 0 ? '+' : ''}{s.avg_return}%</td>
                <td className="text-right py-1.5 text-green-500">+{s.max_gain}%</td>
                <td className="text-right py-1.5 text-red-500">{s.max_loss}%</td>
              </tr>
            )
          })}
        </tbody>
      </table>
      <p className="text-xs text-slate-600 mt-2">{t('pattern_panel.backtest_disclaimer')}</p>
    </div>
  )
}

function PatternCard({ p }: { p: PatternResult }) {
  const { t } = useTranslation()
  const triggered      = p.current.triggered
  const setupTriggered = p.current.setup_triggered ?? false
  const ma60Up         = p.current.ma60_direction === 'up'
  const { setup, breakout, bonus } = buildReasons(p, t)

  // 狀態卡樣式
  const borderColor = triggered
    ? (ma60Up ? 'border-orange-500/40' : 'border-yellow-500/40')
    : setupTriggered
      ? 'border-blue-500/40'
      : 'border-slate-700'
  const dotColor = triggered
    ? (ma60Up ? 'bg-orange-500' : 'bg-yellow-500')
    : setupTriggered
      ? 'bg-blue-500'
      : 'bg-slate-600'

  const failedBreakout = breakout.filter(r => !r.ok)

  return (
    <div className="space-y-3">
      {/* 說明 */}
      <div className="text-xs text-slate-500 leading-relaxed border border-slate-700 rounded p-2">
        <span className="text-slate-300 font-medium">{p.pattern_name}</span>：{p.description}
      </div>

      {/* 狀態卡 */}
      <div className={`rounded-lg p-3 flex items-start gap-3 bg-slate-800 border ${borderColor}`}>
        <div className={`w-3 h-3 rounded-full flex-shrink-0 mt-0.5 ${dotColor}`} />
        <div className="flex-1 min-w-0">
          <div className="text-sm font-semibold text-slate-100">{p.current.label}</div>
          {!triggered && setupTriggered && failedBreakout.length > 0 && (
            <div className="text-xs text-slate-400 mt-1 leading-relaxed">
              {t('pattern_panel.waiting_prefix')}{failedBreakout.map(r => r.text.split('（')[0]).join('、')}
            </div>
          )}
          {!triggered && !setupTriggered && (
            <div className="text-xs text-slate-500 mt-1 leading-relaxed">
              {t('pattern_panel.missing_prefix')}{setup.filter(r => !r.ok).map(r => r.text.split('（')[0]).join('、')}
            </div>
          )}
        </div>
        {triggered && (
          <span className={`flex-shrink-0 text-xs px-2 py-0.5 rounded-full ${
            ma60Up ? 'bg-orange-900/60 text-orange-300' : 'bg-yellow-900/60 text-yellow-300'
          }`}>
            {ma60Up ? t('pattern_panel.badge.ma60_trend') : t('pattern_panel.badge.ma60_leading')}
          </span>
        )}
        {!triggered && setupTriggered && (
          <span className="flex-shrink-0 text-xs px-2 py-0.5 rounded-full bg-blue-900/60 text-blue-300">
            {t('pattern_panel.badge.building')}
          </span>
        )}
      </div>

      {/* 條件進度：蓄勢條件 */}
      <div className="bg-slate-800/60 rounded-lg p-3 space-y-0.5">
        <div className="text-xs text-slate-500 mb-2 font-medium">{t('pattern_panel.setup_section_title')}</div>
        {setup.map((r, i) => <CheckRow key={i} ok={r.ok} text={r.text} />)}
      </div>

      {/* 條件進度：突破確認條件 */}
      <div className="bg-slate-800/60 rounded-lg p-3 space-y-0.5">
        <div className="text-xs text-slate-500 mb-2 font-medium">{t('pattern_panel.breakout_section_title')}</div>
        {breakout.map((r, i) => <CheckRow key={i} ok={r.ok} text={r.text} />)}
        <div className="border-t border-slate-700/60 mt-2 pt-2">
          {bonus.map((r, i) => <CheckRow key={i} ok={r.ok} text={r.text} bonus />)}
        </div>
      </div>

      {/* 歷史觸發 */}
      <div className="bg-slate-800/60 rounded-lg p-3">
        <div className="text-xs text-slate-500 mb-2 font-medium uppercase tracking-wide">{t('pattern_panel.history_title', { count: p.total_triggers, ...interp })}</div>
        {p.trigger_dates.length > 0 && (
          <div className="mt-1 flex flex-wrap gap-1">
            {p.trigger_dates.map(d => (
              <span key={d} className="text-xs bg-slate-700 text-slate-300 px-1.5 py-0.5 rounded font-mono">{d}</span>
            ))}
          </div>
        )}
        {p.total_triggers < 10 && (
          <div className="mt-2 text-xs bg-yellow-900/40 text-yellow-300 px-2 py-1 rounded">{t('pattern_panel.low_sample_warning')}</div>
        )}
      </div>

      {/* 觸發後回測勝率 */}
      {p.backtest_stats && p.backtest_stats.length > 0 && (
        <BacktestStatsTable stats={p.backtest_stats} />
      )}
    </div>
  )
}

export default function PatternPanel({ symbol }: Props) {
  const { t } = useTranslation()
  const [data, setData] = useState<PatternScanResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setLoading(true)
    setError(null)
    api.patternScan(symbol)
      .then(setData)
      .catch(e => setError(e.message ?? t('pattern_panel.load_failed')))
      .finally(() => setLoading(false))
  }, [symbol, t])

  if (loading) return <div className="text-slate-500 text-sm py-4 text-center">{t('common.loading')}</div>
  if (error)   return <div className="text-red-400 text-sm py-2">{error}</div>
  if (!data)   return null

  const pattern = (data.patterns ?? [])[0]
  if (!pattern) return null

  return (
    <div className="space-y-4">
      <PatternCard p={pattern} />
      <p className="text-xs text-slate-600">{t('pattern_panel.footer_disclaimer')}</p>
    </div>
  )
}
