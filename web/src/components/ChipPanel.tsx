function ChipRow({ label, today, cum5d, trend }: any) {
  const sign = today >= 0 ? 'text-red-400' : 'text-green-400'
  return (
    <div className="border border-slate-700 rounded-lg p-3 space-y-1">
      <div className="flex justify-between items-center">
        <span className="text-slate-400 text-sm">{label}</span>
        <span className={`font-mono font-bold ${sign}`}>
          {today >= 0 ? '+' : ''}{today?.toLocaleString()} 張
        </span>
      </div>
      <div className="flex gap-3 text-xs text-slate-500">
        {trend && <span>{trend}</span>}
        {cum5d !== undefined && <span>5日累計 {cum5d >= 0 ? '+' : ''}{cum5d?.toLocaleString()}</span>}
      </div>
    </div>
  )
}

export default function ChipPanel({ data }) {
  if (!data) return null
  const { foreign, trust, dealer, total_today, summary, date } = data

  return (
    <div className="space-y-3">
      <div className="flex justify-between items-center">
        <p className="text-slate-300 text-sm">{summary}</p>
        <span className="text-xs text-slate-500">{date}</span>
      </div>
      <ChipRow label="外資" today={foreign?.today} cum5d={foreign?.cum_5d} trend={foreign?.trend} />
      <ChipRow label="投信" today={trust?.today} cum5d={trust?.cum_5d} trend={trust?.trend} />
      <ChipRow label="自營商" today={dealer?.today} trend={dealer?.trend} />
      <div className="flex justify-between text-sm border-t border-slate-700 pt-2">
        <span className="text-slate-400">三大合計</span>
        <span className={`font-mono font-bold ${total_today >= 0 ? 'text-red-400' : 'text-green-400'}`}>
          {total_today >= 0 ? '+' : ''}{total_today?.toLocaleString()} 張
        </span>
      </div>
    </div>
  )
}
