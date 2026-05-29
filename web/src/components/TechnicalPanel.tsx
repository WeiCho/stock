import { useTranslation } from 'react-i18next'
import type { TechnicalResponse, TechnicalSignal } from '../types'

const TREND_KEY: Record<string, string> = {
  '多頭排列': 'technical.trend.bullish',
  '空頭排列': 'technical.trend.bearish',
  '整理中': 'technical.trend.consolidating',
  '資料不足': 'technical.trend.insufficient',
}

function Badge({ type, label }: { type: string; label: string }) {
  const color = type === 'bullish' ? 'bg-green-900 text-green-300' : 'bg-red-900 text-red-300'
  return <span className={`text-xs px-2 py-0.5 rounded-full ${color}`}>{label}</span>
}

function Row({ label, value, sub }:
  { label: string; value?: number | string | null; sub?: string }) {
  return (
    <div className="flex justify-between py-1 border-b border-slate-800 text-sm">
      <span className="text-slate-400">{label}</span>
      <span className="text-slate-200 font-mono">
        {value ?? '—'}
        {sub && <span className="text-slate-500 ml-1 text-xs">{sub}</span>}
      </span>
    </div>
  )
}

export default function TechnicalPanel({ data }: { data: TechnicalResponse | null }) {
  const { t } = useTranslation()
  if (!data) return null
  const { ma, rsi, macd, kd, bollinger, trend, signals, close, support, resistance } = data

  const trendColor = trend === '多頭排列' ? 'text-red-400' : trend === '空頭排列' ? 'text-green-400' : 'text-yellow-400'
  const trendLabel = trend != null && TREND_KEY[trend] ? t(TREND_KEY[trend]) : trend

  // signal.name 是後端中文 fallback；有 code 時走 i18n（tf 參數先翻成 日/週·Daily/Weekly）
  const signalLabel = (s: TechnicalSignal) => {
    if (!s.code) return s.name
    const p: Record<string, string | number> = { ...(s.params || {}) }
    if (typeof p.tf === 'string') p.tf = t('technical.tf.' + p.tf)
    return t('technical.signal.' + s.code, p)
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3 flex-wrap">
        <span className="text-2xl font-bold text-slate-100">{close}</span>
        <span className={`text-sm font-medium ${trendColor}`}>{trendLabel}</span>
        {signals?.map((s, i) => <Badge key={i} type={s.type} label={signalLabel(s)} />)}
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div>
          <p className="text-xs text-slate-500 uppercase mb-1">{t('technical.section.ma')}</p>
          {Object.entries(ma ?? {}).map(([k, v]) => (
            <Row key={k} label={k.toUpperCase()} value={v as number | string | null} />
          ))}
        </div>
        <div>
          <p className="text-xs text-slate-500 uppercase mb-1">{t('technical.section.indicators')}</p>
          <Row label={t('technical.label.rsi')} value={rsi} />
          <Row label={t('technical.label.macd')} value={macd?.macd} sub={`${t('technical.label.macd_signal')}${macd?.signal}`} />
          <Row label={t('technical.label.kd')} value={kd?.k != null ? `${t('technical.label.kd_k')} ${kd.k}` : null} sub={kd?.d != null ? `${t('technical.label.kd_d')} ${kd.d}` : ''} />
          <Row label={t('technical.label.bb_upper')} value={bollinger?.upper} />
          <Row label={t('technical.label.bb_lower')} value={bollinger?.lower} />
          <Row label={t('technical.label.support')} value={support} />
          <Row label={t('technical.label.resistance')} value={resistance} />
        </div>
      </div>
    </div>
  )
}
