import type { WeeklyWBottomScanResponse, WeeklyWBottomItem } from '../types'

interface Props {
  data: WeeklyWBottomScanResponse | null
  loading: boolean
  error: string | null
  scannedAt: string | null
  onRescan: () => void
  onSelectStock: (symbol: string) => void
}

function ItemRow({ item, onSelect }: { item: WeeklyWBottomItem; onSelect: (s: string) => void }) {
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
          {isUp ? '↗ 上斜' : '↘ 下斜'}
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
  return (
    <div className="space-y-4">
      {/* 控制列 */}
      <div className="flex flex-wrap items-center gap-3">
        <button
          onClick={onRescan}
          disabled={loading}
          className="text-xs px-3 py-1.5 rounded-lg bg-slate-700 hover:bg-slate-600 disabled:opacity-40 disabled:cursor-not-allowed text-slate-300 transition-colors"
        >
          {loading ? '掃描中…' : '重新掃描'}
        </button>
        <span className="text-xs text-slate-500">
          {loading && '掃描中，首次約需 30–90 秒…'}
          {!loading && data && `掃描 ${data.scanned} 檔 · 資料日 ${data.as_of ?? '—'} · ${scannedAt ? `${scannedAt} 更新` : ''}`}
        </span>
      </div>

      {/* 說明：首次掃描前顯示 */}
      {!data && !loading && !error && (
        <div className="bg-slate-800/60 rounded-lg p-4 text-xs text-slate-400 leading-relaxed space-y-1.5">
          <div className="text-slate-300 font-medium mb-1">週線W底突破 — 全市場掃描</div>
          <div>・<span className="text-green-400 font-medium">條件1</span>：本週收盤剛站上週MA20（上週仍在以下）</div>
          <div>・<span className="text-green-400 font-medium">條件2</span>：週MA20 上斜（本週 &gt; 3週前，均線轉多）</div>
          <div>・<span className="text-green-400 font-medium">條件3</span>：近40週內 W底成形（底底高 + 中間有峰值）</div>
          <div>・<span className="text-green-400 font-medium">條件4</span>：本週爆量（&gt; 近10週均量 1.5×）</div>
          <div className="text-slate-500 mt-2">點擊「重新掃描」開始。第一次視 DB 資料量約需 30–90 秒，後續快取直接回傳。</div>
        </div>
      )}

      {loading && (
        <div className="flex flex-col items-center py-10 gap-3">
          <div className="w-7 h-7 border-2 border-green-500 border-t-transparent rounded-full animate-spin" />
          <p className="text-sm text-slate-400">正在掃描全台股週線型態，請稍候…</p>
        </div>
      )}

      {error && <p className="text-red-400 text-sm">{error}</p>}

      {data && !loading && (
        <div className="space-y-4">
          <div className="bg-slate-900/60 border border-green-500/20 rounded-xl p-4">
            <div className="flex items-center gap-2 mb-3">
              <span className="text-sm font-semibold text-slate-300">W底突破完成</span>
              {data.triggered.length > 0
                ? <span className="text-xs px-2 py-0.5 rounded-full bg-slate-700 text-slate-300">{data.triggered.length} 檔</span>
                : null}
              <span className="text-xs text-slate-500">四條件同時成立（週K）</span>
            </div>

            {data.triggered.length === 0 ? (
              <p className="text-xs text-slate-500 py-3 text-center">今日無符合週線W底突破的個股</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-xs min-w-[600px]">
                  <thead>
                    <tr className="text-slate-500 text-left">
                      <th className="py-1.5 px-3 font-medium">代碼 / 名稱</th>
                      <th className="py-1.5 px-3 text-right font-medium">收盤</th>
                      <th className="py-1.5 px-3 text-right font-medium">週MA20</th>
                      <th className="py-1.5 px-3 text-right font-medium">距MA20</th>
                      <th className="py-1.5 px-3 text-center font-medium">MA20 方向</th>
                      <th className="py-1.5 px-3 text-right font-medium">週量 / 門檻</th>
                      <th className="py-1.5 px-3 text-right font-medium">歷史次數</th>
                      <th className="py-1.5 px-3 text-right font-medium">上次觸發</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.triggered.map(item => (
                      <ItemRow key={item.symbol} item={item} onSelect={onSelectStock} />
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
          <p className="text-xs text-slate-600">歷史型態不代表未來績效，僅供研究參考。</p>
        </div>
      )}
    </div>
  )
}
