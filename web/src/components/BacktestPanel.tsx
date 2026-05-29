import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { api } from '../api'
import type { BacktestResponse, PineResponse } from '../types'

interface Props {
  data: BacktestResponse | null
  signal: string
  onSignalChange: (s: string) => void
}

export default function BacktestPanel({ data, signal, onSignalChange }: Props) {
  const { t } = useTranslation()
  // 後備清單：API 拿不到時用（離線開發 / 後端臨時掛掉）。
  // 正常情況會被 /backtest/signals 動態覆蓋，包含後端新增的訊號（如 best_four_buy/sell）。
  const FALLBACK_SIGNALS: Record<string, string> = {
    ma_cross: t('backtest.fallback_signal.ma_cross'),
    ma_death: t('backtest.fallback_signal.ma_death'),
  }
  const [signals, setSignals] = useState<Record<string, string>>(FALLBACK_SIGNALS)
  useEffect(() => {
    api.signals().then(setSignals).catch(() => {})  // 失敗就維持 fallback
  }, [])

  const handleDownloadPine = async () => {
    try {
      const sym = data?.symbol
      if (!sym) return
      const res = await api.pine(sym, signal) as PineResponse
      const blob = new Blob([res.pine_code], { type: 'text/plain' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${sym}_${signal}.pine`
      a.click()
      URL.revokeObjectURL(url)
    } catch (e) {
      console.error('Pine 下載失敗', e)
    }
  }

  if (!data) return (
    <div className="space-y-3">
      <select
        value={signal}
        onChange={e => onSignalChange(e.target.value)}
        className="w-full bg-slate-800 border border-slate-600 rounded px-3 py-2 text-sm text-slate-200"
      >
        {Object.entries(signals).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
      </select>
    </div>
  )

  const { total_triggers, low_sample_warning, stats, trigger_dates, disclaimer } = data

  return (
    <div className="space-y-3">
      <div className="flex gap-2 flex-wrap items-center">
        <select
          value={signal}
          onChange={e => onSignalChange(e.target.value)}
          className="bg-slate-800 border border-slate-600 rounded px-3 py-2 text-sm text-slate-200"
        >
          {Object.entries(signals).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
        <span className="text-sm text-slate-400">{t('backtest.triggered_prefix')} <b className="text-slate-200">{total_triggers}</b> {t('backtest.triggered_suffix')}</span>
        {low_sample_warning && <span className="text-xs bg-yellow-900 text-yellow-300 px-2 py-0.5 rounded-full">{t('backtest.low_sample_warning')}</span>}
        <button onClick={handleDownloadPine}
          className="ml-auto text-xs px-3 py-1 rounded bg-slate-700 hover:bg-slate-600 text-slate-200">
          {t('backtest.download_pine')}
        </button>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-slate-500 text-xs border-b border-slate-700">
              <th className="text-left py-1 pr-3">{t('backtest.col_hold')}</th>
              <th className="text-right pr-3">{t('backtest.col_win_rate')}</th>
              <th className="text-right pr-3">{t('backtest.col_avg_return')}</th>
              <th className="text-right pr-3">{t('backtest.col_max_gain')}</th>
              <th className="text-right">{t('backtest.col_max_loss')}</th>
            </tr>
          </thead>
          <tbody>
            {stats?.map(s => (
              <tr key={s.hold_days} className="border-b border-slate-800">
                <td className="py-1.5 pr-3 text-slate-400">{s.hold_days}{t('backtest.hold_days_unit')}</td>
                <td className={`text-right pr-3 font-mono ${s.win_rate >= 55 ? 'text-red-400' : s.win_rate >= 45 ? 'text-slate-300' : 'text-green-400'}`}>
                  {s.win_rate}%
                </td>
                <td className={`text-right pr-3 font-mono ${s.avg_return >= 0 ? 'text-red-400' : 'text-green-400'}`}>
                  {s.avg_return >= 0 ? '+' : ''}{s.avg_return}%
                </td>
                <td className="text-right pr-3 font-mono text-red-400">+{s.max_gain}%</td>
                <td className="text-right font-mono text-green-400">{s.max_loss}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {trigger_dates && trigger_dates.length > 0 && (
        <div className="text-xs text-slate-500">
          {t('backtest.recent_triggers')}{trigger_dates.join(t('backtest.date_separator'))}
        </div>
      )}
      {disclaimer && <p className="text-xs text-slate-600">{disclaimer}</p>}
    </div>
  )
}
