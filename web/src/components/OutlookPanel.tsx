import { useTranslation } from 'react-i18next'
import type { OutlookResponse, OutlookFactor } from '../types'

const BIAS_STYLE: Record<string, string> = {
  偏多: 'text-red-400 bg-red-900/40',
  偏空: 'text-green-400 bg-green-900/40',
  中性: 'text-yellow-400 bg-yellow-900/40',
}

const BIAS_KEY: Record<string, string> = {
  偏多: 'outlook.bias.bullish',
  偏空: 'outlook.bias.bearish',
  中性: 'outlook.bias.neutral',
}

const TREND_KEY: Record<string, string> = {
  '多頭排列': 'technical.trend.bullish',
  '空頭排列': 'technical.trend.bearish',
  '整理中': 'technical.trend.consolidating',
  '資料不足': 'technical.trend.insufficient',
}

export default function OutlookPanel({ data }: { data: OutlookResponse | null }) {
  const { t } = useTranslation()
  if (!data) return null
  const { bias, score = 0, trend, factors = [], expected, support, resistance, close } = data

  const trendLabel = trend != null && TREND_KEY[trend] ? t(TREND_KEY[trend]) : trend
  // f.label 是中文 fallback；有 labelKey 走 i18n（tf → 日/週·Daily/Weekly、code → 回測訊號名）
  const factorLabel = (f: OutlookFactor) => {
    if (!f.labelKey) return f.label
    const p: Record<string, string | number> = { ...(f.params || {}) }
    if (typeof p.tf === 'string') p.tf = t('technical.tf.' + p.tf)
    if (typeof p.code === 'string') p.signal = t('backtest.signal.' + p.code)
    return t(f.labelKey, p)
  }

  return (
    <div className="space-y-4">
      {/* 方向偏向 + 強弱條 */}
      <div className="flex items-center gap-3 flex-wrap">
        <span className={`text-xl font-bold px-3 py-1 rounded-lg ${(bias && BIAS_STYLE[bias]) || 'text-slate-300'}`}>{bias && BIAS_KEY[bias] ? t(BIAS_KEY[bias]) : bias}</span>
        <span className="text-slate-400 text-sm">{t('outlook.summary_line', { close, trend: trendLabel })}</span>
        <div className="flex-1 min-w-[140px] h-2 bg-slate-800 rounded-full relative">
          <div className="absolute top-0 bottom-0 left-1/2 w-px bg-slate-600" />
          <div
            className={`absolute top-0 bottom-0 rounded-full ${score >= 0 ? 'bg-red-500 left-1/2' : 'bg-green-500 right-1/2'}`}
            style={{ width: `${Math.min(Math.abs(score) / 2, 50)}%` }}
          />
        </div>
      </div>

      {/* 預期區間（依歷史回測） */}
      {expected ? (
        <div className="bg-slate-800 rounded-lg p-4 space-y-1">
          <p className="text-xs text-slate-500 uppercase">{t('outlook.expected_heading', { horizon_days: expected.horizon_days })}</p>
          <p className="text-sm text-slate-300">
            {t('outlook.based_on')} <b className="text-slate-100">{expected.basis_code ? t('backtest.signal.' + expected.basis_code) : expected.basis}</b>：{t('outlook.win_rate_label')}{' '}
            <b className={expected.win_rate >= 50 ? 'text-red-400' : 'text-green-400'}>{expected.win_rate}%</b>，{t('outlook.avg_return_label')}{' '}
            <b className={expected.avg_return >= 0 ? 'text-red-400' : 'text-green-400'}>
              {expected.avg_return >= 0 ? '+' : ''}{expected.avg_return}%
            </b>
          </p>
          <p className="text-sm text-slate-300">
            {t('outlook.target_label')}<b className="font-mono text-slate-100">{expected.target}</b>
            <span className="text-slate-500 mx-2">|</span>
            {t('outlook.range_label')} <span className="font-mono text-green-400">{expected.range_low}</span>
            <span className="text-slate-500"> ~ </span>
            <span className="font-mono text-red-400">{expected.range_high}</span>
          </p>
          {expected.low_sample && (
            <p className="text-xs text-yellow-400">{t('outlook.low_sample_warning', { sample_count: expected.sample_count })}</p>
          )}
        </div>
      ) : (
        <div className="bg-slate-800 rounded-lg p-4 text-sm text-slate-400">
          {t('outlook.no_expected_fallback', { support, resistance })}
        </div>
      )}

      {/* 研判依據 */}
      <div>
        <p className="text-xs text-slate-500 uppercase mb-2">{t('outlook.rationale_heading')}</p>
        <div className="flex flex-wrap gap-2">
          {factors.length ? factors.map((f, i) => (
            <span key={i} className={`text-xs px-2 py-1 rounded-full ${f.weight > 0 ? 'bg-red-900/50 text-red-300' : 'bg-green-900/50 text-green-300'}`}>
              {f.weight > 0 ? '＋' : '－'} {factorLabel(f)}
            </span>
          )) : <span className="text-slate-500 text-sm">{t('outlook.no_signals')}</span>}
        </div>
      </div>

      <p className="text-xs text-slate-600 leading-relaxed">{t('outlook.disclaimer')}</p>
    </div>
  )
}
