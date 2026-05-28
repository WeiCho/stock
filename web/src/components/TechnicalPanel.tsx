function Badge({ type, name }) {
  const color = type === 'bullish' ? 'bg-green-900 text-green-300' : 'bg-red-900 text-red-300'
  return <span className={`text-xs px-2 py-0.5 rounded-full ${color}`}>{name}</span>
}

function Row({ label, value, sub }: any) {
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

export default function TechnicalPanel({ data }) {
  if (!data) return null
  const { ma, rsi, macd, kd, bollinger, trend, signals, close, support, resistance } = data

  const trendColor = trend === '多頭排列' ? 'text-red-400' : trend === '空頭排列' ? 'text-green-400' : 'text-yellow-400'

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3 flex-wrap">
        <span className="text-2xl font-bold text-slate-100">{close}</span>
        <span className={`text-sm font-medium ${trendColor}`}>{trend}</span>
        {signals?.map((s, i) => <Badge key={i} {...s} />)}
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div>
          <p className="text-xs text-slate-500 uppercase mb-1">均線</p>
          {Object.entries(ma ?? {}).map(([k, v]) => (
            <Row key={k} label={k.toUpperCase()} value={v} />
          ))}
        </div>
        <div>
          <p className="text-xs text-slate-500 uppercase mb-1">指標</p>
          <Row label="RSI(14)" value={rsi} />
          <Row label="MACD" value={macd?.macd} sub={`訊號${macd?.signal}`} />
          <Row label="KD" value={kd?.k != null ? `K ${kd.k}` : null} sub={kd?.d != null ? `D ${kd.d}` : ''} />
          <Row label="布林上" value={bollinger?.upper} />
          <Row label="布林下" value={bollinger?.lower} />
          <Row label="支撐" value={support} />
          <Row label="壓力" value={resistance} />
        </div>
      </div>
    </div>
  )
}
