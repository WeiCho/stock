import type { MarketPatternScanResponse, MarketPatternItem } from '../types'

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
          {isUp ? '↗ 上斜' : '↘ 下斜'}
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
        <span className="text-xs px-2 py-0.5 rounded-full bg-slate-700 text-slate-300">{items.length} 檔</span>
        <span className="text-xs text-slate-500">{badge}</span>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-xs min-w-[560px]">
          <thead>
            <tr className="text-slate-500 text-left">
              <th className="py-1.5 px-3 font-medium">代碼 / 名稱</th>
              <th className="py-1.5 px-3 text-right font-medium">收盤</th>
              <th className="py-1.5 px-3 text-right font-medium">MA60</th>
              <th className="py-1.5 px-3 text-right font-medium">距MA60</th>
              <th className="py-1.5 px-3 text-center font-medium">MA60 方向</th>
              <th className="py-1.5 px-3 text-right font-medium">昨量 / 門檻</th>
              <th className="py-1.5 px-3 text-right font-medium">上次觸發</th>
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

const MODES: { value: Mode; label: string }[] = [
  { value: 'both',      label: '全部（突破 + 蓄勢）' },
  { value: 'triggered', label: '突破完成' },
  { value: 'setup',     label: '蓄勢中' },
]

export default function MarketPatternScanPanel({
  mode, onModeChange, data, loading, error, scannedAt, onRescan, onSelectStock,
}: Props) {
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
              {m.label}
            </button>
          ))}
        </div>
        <button
          onClick={onRescan}
          disabled={loading}
          className="text-xs px-3 py-1.5 rounded-lg bg-slate-700 hover:bg-slate-600 disabled:opacity-40 disabled:cursor-not-allowed text-slate-300 transition-colors"
        >
          {loading ? '掃描中…' : '重新掃描'}
        </button>
        <span className="text-xs text-slate-500">
          {loading && '掃描中，首次約需 30–60 秒…'}
          {!loading && data && `掃描 ${data.scanned} 檔 · 資料日 ${data.as_of ?? '—'} · ${scannedAt ? `${scannedAt} 更新` : ''}`}
        </span>
      </div>

      {/* 說明：首次掃描前顯示 */}
      {!data && !loading && !error && (
        <div className="bg-slate-800/60 rounded-lg p-4 text-xs text-slate-400 leading-relaxed space-y-1.5">
          <div className="text-slate-300 font-medium mb-1">三線交纏帶量突破 MA60 — 全市場掃描</div>
          <div>・<span className="text-orange-400 font-medium">突破完成</span>：MA5/10/20 三線交纏（差距 &lt; 3%）+ 昨日帶量（&gt; 均量 1.5×）+ 連 2 日站上 MA60 + 前天仍在 MA60 下</div>
          <div>・<span className="text-blue-400 font-medium">蓄勢中</span>：三線交纏 + 收盤站上 MA5/MA10/MA20 + 距 MA60 &lt; 3%（等待帶量突破）</div>
          <div className="text-slate-500 mt-2">點擊「重新掃描」開始。第一次視 DB 資料量約需 10–60 秒，後續快取直接回傳。</div>
        </div>
      )}

      {loading && (
        <div className="flex flex-col items-center py-10 gap-3">
          <div className="w-7 h-7 border-2 border-orange-500 border-t-transparent rounded-full animate-spin" />
          <p className="text-sm text-slate-400">正在掃描全台股型態，請稍候…</p>
        </div>
      )}

      {error && <p className="text-red-400 text-sm">{error}</p>}

      {data && !loading && (
        <div className="space-y-6">
          {(mode === 'triggered' || mode === 'both') && (
            <div className="bg-slate-900/60 border border-orange-500/20 rounded-xl p-4">
              <ResultTable
                title="突破完成"
                badge="帶量突破 MA60，連 2 日確認站穩"
                badgeClass="bg-orange-900/60 text-orange-300"
                items={data.triggered}
                emptyText="今日無突破完成個股"
                onSelect={onSelectStock}
              />
            </div>
          )}

          {(mode === 'setup' || mode === 'both') && (
            <div className="bg-slate-900/60 border border-blue-500/20 rounded-xl p-4">
              <ResultTable
                title="蓄勢中"
                badge="三線交纏 + 距 MA60 &lt; 3%，等待突破確認"
                badgeClass="bg-blue-900/60 text-blue-300"
                items={data.setup}
                emptyText="今日無蓄勢中個股"
                onSelect={onSelectStock}
              />
            </div>
          )}

          <p className="text-xs text-slate-600">歷史型態不代表未來績效，僅供研究參考。</p>
        </div>
      )}
    </div>
  )
}
