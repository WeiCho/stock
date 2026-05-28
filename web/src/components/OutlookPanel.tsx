import type { OutlookResponse } from '../types'

const BIAS_STYLE: Record<string, string> = {
  偏多: 'text-red-400 bg-red-900/40',
  偏空: 'text-green-400 bg-green-900/40',
  中性: 'text-yellow-400 bg-yellow-900/40',
}

export default function OutlookPanel({ data }: { data: OutlookResponse | null }) {
  if (!data) return null
  const { bias, score = 0, trend, factors = [], expected, support, resistance, close, disclaimer } = data

  return (
    <div className="space-y-4">
      {/* 方向偏向 + 強弱條 */}
      <div className="flex items-center gap-3 flex-wrap">
        <span className={`text-xl font-bold px-3 py-1 rounded-lg ${(bias && BIAS_STYLE[bias]) || 'text-slate-300'}`}>{bias}</span>
        <span className="text-slate-400 text-sm">綜合研判 · 收盤 {close} · {trend}</span>
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
          <p className="text-xs text-slate-500 uppercase">預期（{expected.horizon_days} 個交易日，依歷史回測推估）</p>
          <p className="text-sm text-slate-300">
            基於 <b className="text-slate-100">{expected.basis}</b>：歷史勝率{' '}
            <b className={expected.win_rate >= 50 ? 'text-red-400' : 'text-green-400'}>{expected.win_rate}%</b>，平均報酬{' '}
            <b className={expected.avg_return >= 0 ? 'text-red-400' : 'text-green-400'}>
              {expected.avg_return >= 0 ? '+' : ''}{expected.avg_return}%
            </b>
          </p>
          <p className="text-sm text-slate-300">
            目標 ~<b className="font-mono text-slate-100">{expected.target}</b>
            <span className="text-slate-500 mx-2">|</span>
            歷史區間 <span className="font-mono text-green-400">{expected.range_low}</span>
            <span className="text-slate-500"> ~ </span>
            <span className="font-mono text-red-400">{expected.range_high}</span>
          </p>
          {expected.low_sample && (
            <p className="text-xs text-yellow-400">⚠ 樣本數較少（{expected.sample_count} 次），參考性較低</p>
          )}
        </div>
      ) : (
        <div className="bg-slate-800 rounded-lg p-4 text-sm text-slate-400">
          目前無明顯回測訊號可推估預期；可參考 支撐{' '}
          <b className="font-mono text-slate-200">{support}</b>、壓力{' '}
          <b className="font-mono text-slate-200">{resistance}</b>。
        </div>
      )}

      {/* 研判依據 */}
      <div>
        <p className="text-xs text-slate-500 uppercase mb-2">研判依據</p>
        <div className="flex flex-wrap gap-2">
          {factors.length ? factors.map((f, i) => (
            <span key={i} className={`text-xs px-2 py-1 rounded-full ${f.weight > 0 ? 'bg-red-900/50 text-red-300' : 'bg-green-900/50 text-green-300'}`}>
              {f.weight > 0 ? '＋' : '－'} {f.label}
            </span>
          )) : <span className="text-slate-500 text-sm">無明顯訊號</span>}
        </div>
      </div>

      <p className="text-xs text-slate-600 leading-relaxed">{disclaimer}</p>
    </div>
  )
}
