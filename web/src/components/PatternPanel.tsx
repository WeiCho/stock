import { useEffect, useState } from 'react'
import { api } from '../api'
import type { PatternScanResponse, PatternResult } from '../types'

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

function buildReasons(p: PatternResult) {
  const d = p.diagnostics
  const spread    = d.ma_spread ?? null
  const threshold = d.close != null ? +(d.close * 0.05).toFixed(2) : null
  const ma60Up    = p.current.ma60_direction === 'up'
  const ma60Slope = d.ma60_slope

  return {
    required: [
      {
        ok: d.cond_tangle ?? false,
        text: spread != null && threshold != null
          ? `四條均線緊密收斂（差距 ${spread}，門檻 ${threshold}），蓄勢中`
          : '四條均線差距資料不足',
      },
      {
        ok: d.cond_short_up ?? false,
        text: `MA5、MA10 都已上翹，短線動能翻正`,
      },
      {
        ok: d.cond_above_ma20 ?? false,
        text: d.close != null && d.ma20 != null
          ? `今日收盤 ${d.close} 已突破 MA20（${d.ma20}）`
          : '今日收盤已突破 MA20',
      },
      {
        ok: d.cond_first_break ?? false,
        text: d.prev_close != null && d.prev_ma60 != null
          ? `昨收 ${d.prev_close} 還在 MA60（${d.prev_ma60}）以下，今天才是第一根穿越`
          : '昨天還在 MA60 以下，今天才剛穿越',
      },
      {
        ok: d.cond_support ?? true,
        text: '近期底部有支撐，低點平台沒有被破壞',
      },
    ],
    bonus: [
      {
        ok: ma60Up,
        text: ma60Up
          ? `MA60 上斜（斜率 +${ma60Slope}），長線無壓，力道最強`
          : ma60Slope != null && ma60Slope < 0
            ? `MA60 仍在下斜（斜率 ${ma60Slope}），均線還沒轉，股價領先突破，爆發型訊號`
            : 'MA60 走平，上方壓力輕微',
      },
    ],
  }
}

function PatternCard({ p }: { p: PatternResult }) {
  const triggered = p.current.triggered
  const ma60Up    = p.current.ma60_direction === 'up'
  const { required, bonus } = buildReasons(p)
  const failedRequired = required.filter(r => !r.ok)

  const borderColor = triggered
    ? (ma60Up ? 'border-orange-500/40' : 'border-yellow-600/40')
    : 'border-slate-700'
  const dotColor = triggered
    ? (ma60Up ? 'bg-orange-500' : 'bg-yellow-500')
    : 'bg-slate-600'

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
          {!triggered && failedRequired.length > 0 && (
            <div className="text-xs text-slate-500 mt-1 leading-relaxed">
              尚缺：{failedRequired.map(r => r.text.split('（')[0]).join('、')}
            </div>
          )}
        </div>
        {triggered && (
          <span className={`flex-shrink-0 text-xs px-2 py-0.5 rounded-full ${
            ma60Up
              ? 'bg-orange-900/60 text-orange-300'
              : 'bg-yellow-900/60 text-yellow-300'
          }`}>
            {ma60Up ? 'MA60 順勢' : 'MA60 領先'}
          </span>
        )}
      </div>

      {/* 條件進度 */}
      <div className="bg-slate-800/60 rounded-lg p-3 space-y-0.5">
        <div className="text-xs text-slate-500 mb-2 font-medium">條件進度</div>
        {required.map((r, i) => <CheckRow key={i} ok={r.ok} text={r.text} />)}
        <div className="border-t border-slate-700/60 mt-2 pt-2">
          {bonus.map((r, i) => <CheckRow key={i} ok={r.ok} text={r.text} bonus />)}
        </div>
      </div>

      {/* 歷史觸發 */}
      <div className="bg-slate-800/60 rounded-lg p-3">
        <div className="text-xs text-slate-500 mb-2 font-medium uppercase tracking-wide">歷史觸發（近10年）</div>
        <div className="text-2xl font-bold text-slate-100">
          {p.total_triggers} <span className="text-sm font-normal text-slate-400">次</span>
        </div>
        {p.trigger_dates.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1">
            {p.trigger_dates.slice(-8).map(d => (
              <span key={d} className="text-xs bg-slate-700 text-slate-300 px-1.5 py-0.5 rounded font-mono">{d}</span>
            ))}
          </div>
        )}
        {p.total_triggers < 10 && (
          <div className="mt-2 text-xs bg-yellow-900/40 text-yellow-300 px-2 py-1 rounded">樣本不足，統計意義有限</div>
        )}
      </div>
    </div>
  )
}

export default function PatternPanel({ symbol }: Props) {
  const [data, setData] = useState<PatternScanResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setLoading(true)
    setError(null)
    api.patternScan(symbol)
      .then(setData)
      .catch(e => setError(e.message ?? '載入失敗'))
      .finally(() => setLoading(false))
  }, [symbol])

  if (loading) return <div className="text-slate-500 text-sm py-4 text-center">載入中…</div>
  if (error)   return <div className="text-red-400 text-sm py-2">{error}</div>
  if (!data)   return null

  const pattern = (data.patterns ?? [])[0]
  if (!pattern) return null

  return (
    <div className="space-y-4">
      <PatternCard p={pattern} />
      <p className="text-xs text-slate-600">歷史型態不代表未來績效，僅供參考。</p>
    </div>
  )
}
