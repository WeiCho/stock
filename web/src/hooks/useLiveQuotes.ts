import { useEffect, useState } from 'react'

export interface LiveQuote {
  symbol: string
  last?: number
  previousClose?: number
  open?: number
  high?: number
  low?: number
  avg?: number
  change?: number
  change_pct?: number
  volume?: number
  bids?: { price: number; size: number }[]
  asks?: { price: number; size: number }[]
  time?: string
}

/**
 * 訂閱 ≤5 檔即時報價（透過後端 /ws/quotes hub → 單一上游 Fugle 連線，aggregates channel）。
 * Fugle 免費方案上限為 1 連線 / 5 訂閱，故只取前 5 檔；其餘列維持靜態值。
 * 後端在訂閱當下會用 REST 補一筆最後一盤，所以盤後/週末也會先有一個快照。
 * 連不上（沒設 key 等）時靜默回空物件，呼叫端 fallback 到靜態資料。
 */
export function useLiveQuotes(symbols: string[]): Record<string, LiveQuote> {
  const [quotes, setQuotes] = useState<Record<string, LiveQuote>>({})
  const capped = symbols.slice(0, 5)
  const key = capped.join(',')

  useEffect(() => {
    if (!capped.length) {
      setQuotes({})
      return
    }
    // 切換訂閱清單時，只留下仍訂閱的 symbol（避免 record 無限長大 / 殘留舊列的報價）
    setQuotes(prev => {
      const next: Record<string, LiveQuote> = {}
      for (const s of capped) if (prev[s]) next[s] = prev[s]
      return next
    })

    let ws: WebSocket | null = null
    let closed = false
    let backoff = 1000
    let timer: ReturnType<typeof setTimeout> | undefined

    const connect = () => {
      if (closed) return
      const proto = location.protocol === 'https:' ? 'wss' : 'ws'
      ws = new WebSocket(`${proto}://${location.host}/api/ws/quotes`)
      ws.onopen = () => ws?.send(JSON.stringify({ action: 'subscribe', symbols: capped }))
      ws.onmessage = (e) => {
        backoff = 1000 // 有收到資料 = 連線健康，重置退避
        try {
          const msg = JSON.parse(e.data)
          if (msg.event === 'quote' && msg.quote?.symbol) {
            setQuotes(prev => ({ ...prev, [msg.quote.symbol]: msg.quote }))
          }
        } catch { /* ignore malformed frame */ }
      }
      ws.onerror = () => { try { ws?.close() } catch { /* noop */ } }
      ws.onclose = () => {
        if (closed) return
        // 斷線（睡眠/網路抖動/伺服器重啟）自動重連：指數退避 1s→15s，重連後 onopen 會重送 subscribe
        timer = setTimeout(connect, backoff)
        backoff = Math.min(backoff * 2, 15000)
      }
    }
    connect()

    return () => {
      closed = true
      if (timer) clearTimeout(timer)
      try { ws?.close() } catch { /* noop */ }
    }
    // 只在訂閱清單（key）改變時重建連線
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key])

  return quotes
}
