import { useEffect, useState } from 'react'
import { api } from '../api'
import type { PatternScanResponse, PatternResult, PatternBacktestStat } from '../types'

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
  const threshold = d.close != null ? +(d.close * 0.03).toFixed(2) : null
  const ma60Up    = p.current.ma60_direction === 'up'
  const ma60Slope = d.ma60_slope

  // 第一層：蓄勢條件（三線交纏 + 站上三線 + 接近 MA60）
  const setup = [
    {
      ok: d.cond_tangle ?? false,
      text: spread != null && threshold != null
        ? `MA5/MA10/MA20 三線交纏（差距 ${spread}，門檻 ${threshold}）`
        : 'MA5/MA10/MA20 三線差距資料不足',
    },
    {
      ok: d.cond_above_three ?? false,
      text: d.close != null
        ? `收盤 ${d.close} 站上 MA5/MA10/MA20 三線`
        : '收盤須站上 MA5/MA10/MA20 三線',
    },
    {
      ok: d.cond_near_ma60 ?? false,
      text: d.ma60_gap != null && d.ma60 != null && d.ma60_gap_pct != null
        ? `收盤距 MA60（${d.ma60}）僅差 ${d.ma60_gap}（${d.ma60_gap_pct}%），等待突破`
        : '收盤距 MA60 < 3%，等待帶量突破',
    },
  ]

  // 第二層：突破確認條件（帶量 + 站穩 2 日）
  const breakout = [
    {
      ok: d.cond_support ?? false,
      text: d.prev_vol != null && d.vol_threshold != null
        ? `昨日帶量 ${d.prev_vol.toLocaleString()} 張 > 門檻 ${d.vol_threshold.toLocaleString()} 張（均量 × 1.5）`
        : '昨日成交量需 > 20 日均量 × 1.5（帶量突破）',
    },
    {
      ok: d.cond_above_ma20 ?? false,
      text: d.close != null && d.ma60 != null
        ? `連續 2 日收盤站上 MA60（${d.ma60}），今日 ${d.close} 確認站穩`
        : '今日與昨日收盤均站上 MA60（連續 2 日站穩）',
    },
    {
      ok: d.cond_first_break ?? false,
      text: d.prev_close != null && d.prev_ma60 != null
        ? `前天收 ${d.prev_close} 仍在 MA60（${d.prev_ma60}）以下，突破剛發生`
        : '前天還在 MA60 以下，突破剛發生',
    },
  ]

  return {
    setup,
    breakout,
    bonus: [
      {
        ok: ma60Up,
        text: ma60Up
          ? `MA60 上斜（斜率 +${ma60Slope}），長線無壓，力道最強`
          : ma60Slope != null && ma60Slope < 0
            ? `MA60 仍在下斜（斜率 ${ma60Slope}），均線還沒轉，爆發型訊號`
            : 'MA60 走平，上方壓力輕微',
      },
    ],
  }
}

function BacktestStatsTable({ stats }: { stats: PatternBacktestStat[] }) {
  return (
    <div className="bg-slate-800/60 rounded-lg p-3">
      <div className="text-xs text-slate-500 mb-3 font-medium uppercase tracking-wide">觸發後獲利統計</div>
      <table className="w-full text-xs">
        <thead>
          <tr className="text-slate-500">
            <th className="text-left pb-2 font-medium">持有天數</th>
            <th className="text-right pb-2 font-medium">樣本</th>
            <th className="text-right pb-2 font-medium">勝率</th>
            <th className="text-right pb-2 font-medium">平均報酬</th>
            <th className="text-right pb-2 font-medium">最大獲利</th>
            <th className="text-right pb-2 font-medium">最大虧損</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-700/50">
          {stats.map(s => {
            const winColor = s.win_rate >= 60 ? 'text-green-400' : s.win_rate >= 50 ? 'text-yellow-400' : 'text-red-400'
            const retColor = s.avg_return > 0 ? 'text-green-400' : 'text-red-400'
            return (
              <tr key={s.hold_days} className="text-slate-300">
                <td className="py-1.5 text-slate-400">{s.hold_days} 日</td>
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
      <p className="text-xs text-slate-600 mt-2">未含手續費及證交稅，歷史績效不代表未來。</p>
    </div>
  )
}

function PatternCard({ p }: { p: PatternResult }) {
  const triggered      = p.current.triggered
  const setupTriggered = p.current.setup_triggered ?? false
  const ma60Up         = p.current.ma60_direction === 'up'
  const { setup, breakout, bonus } = buildReasons(p)

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
              等待：{failedBreakout.map(r => r.text.split('（')[0]).join('、')}
            </div>
          )}
          {!triggered && !setupTriggered && (
            <div className="text-xs text-slate-500 mt-1 leading-relaxed">
              尚缺：{setup.filter(r => !r.ok).map(r => r.text.split('（')[0]).join('、')}
            </div>
          )}
        </div>
        {triggered && (
          <span className={`flex-shrink-0 text-xs px-2 py-0.5 rounded-full ${
            ma60Up ? 'bg-orange-900/60 text-orange-300' : 'bg-yellow-900/60 text-yellow-300'
          }`}>
            {ma60Up ? 'MA60 順勢' : 'MA60 領先'}
          </span>
        )}
        {!triggered && setupTriggered && (
          <span className="flex-shrink-0 text-xs px-2 py-0.5 rounded-full bg-blue-900/60 text-blue-300">
            蓄勢中
          </span>
        )}
      </div>

      {/* 條件進度：蓄勢條件 */}
      <div className="bg-slate-800/60 rounded-lg p-3 space-y-0.5">
        <div className="text-xs text-slate-500 mb-2 font-medium">① 蓄勢條件（符合即可準備進場）</div>
        {setup.map((r, i) => <CheckRow key={i} ok={r.ok} text={r.text} />)}
      </div>

      {/* 條件進度：突破確認條件 */}
      <div className="bg-slate-800/60 rounded-lg p-3 space-y-0.5">
        <div className="text-xs text-slate-500 mb-2 font-medium">② 突破確認條件（符合才算完整觸發，回測以此計算）</div>
        {breakout.map((r, i) => <CheckRow key={i} ok={r.ok} text={r.text} />)}
        <div className="border-t border-slate-700/60 mt-2 pt-2">
          {bonus.map((r, i) => <CheckRow key={i} ok={r.ok} text={r.text} bonus />)}
        </div>
      </div>

      {/* 歷史觸發 */}
      <div className="bg-slate-800/60 rounded-lg p-3">
        <div className="text-xs text-slate-500 mb-2 font-medium uppercase tracking-wide">歷史觸發（近10年，共 {p.total_triggers} 次）</div>
        {p.trigger_dates.length > 0 && (
          <div className="mt-1 flex flex-wrap gap-1">
            {p.trigger_dates.map(d => (
              <span key={d} className="text-xs bg-slate-700 text-slate-300 px-1.5 py-0.5 rounded font-mono">{d}</span>
            ))}
          </div>
        )}
        {p.total_triggers < 10 && (
          <div className="mt-2 text-xs bg-yellow-900/40 text-yellow-300 px-2 py-1 rounded">樣本不足，統計意義有限</div>
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
