/**
 * 前端用的技術指標：RSI(14) 與 KDJ(9,3,3)。
 * 跟 server/indicators.py 對齊（Wilder smoothing），讓副圖一定能畫，不需後端額外回傳序列。
 */
import type { Bar, MaPoint } from './types'

const round2 = (n: number) => Math.round(n * 100) / 100

/**
 * Wilder RSI(14)：典型 Welles Wilder 平滑（α = 1/n）。
 * 與 pandas EMA(α=1/n, adjust=false) 等價。
 */
export function rsi(bars: Bar[], period = 14): MaPoint[] {
  if (bars.length < period + 1) return []
  const closes = bars.map(b => b.close)
  const gains: number[] = []
  const losses: number[] = []
  for (let i = 1; i < closes.length; i++) {
    const diff = closes[i] - closes[i - 1]
    gains.push(diff > 0 ? diff : 0)
    losses.push(diff < 0 ? -diff : 0)
  }
  // 用前 period 個 simple average 當種子，再用 Wilder smoothing 推進
  let avgGain = gains.slice(0, period).reduce((a, b) => a + b, 0) / period
  let avgLoss = losses.slice(0, period).reduce((a, b) => a + b, 0) / period
  const out: MaPoint[] = []
  // 第 period 根 K 第一筆 RSI（對應 bars[period]）
  out.push({ time: bars[period].date, value: round2(avgLoss === 0 ? 100 : 100 - 100 / (1 + avgGain / avgLoss)) })
  for (let i = period; i < gains.length; i++) {
    avgGain = (avgGain * (period - 1) + gains[i]) / period
    avgLoss = (avgLoss * (period - 1) + losses[i]) / period
    out.push({ time: bars[i + 1].date, value: round2(avgLoss === 0 ? 100 : 100 - 100 / (1 + avgGain / avgLoss)) })
  }
  return out
}

/**
 * KDJ(9,3,3)：台股慣例
 *   RSV = (close - low9) / (high9 - low9) * 100
 *   K[t] = (2/3)*K[t-1] + (1/3)*RSV
 *   D[t] = (2/3)*D[t-1] + (1/3)*K
 *   J = 3*K - 2*D
 * 初始 K/D 用 50（與 stock 慣例一致）。
 */
/**
 * MACD(12, 26, 9)：標準 EMA 實作。
 * macdLine = EMA12 − EMA26；signal = EMA9(macdLine)；hist = macdLine − signal
 */
export function macd(bars: Bar[], fast = 12, slow = 26, sig = 9): {
  macd: MaPoint[]; signal: MaPoint[]; hist: MaPoint[];
} {
  if (bars.length < slow) return { macd: [], signal: [], hist: [] }
  const closes = bars.map(b => b.close)
  const ema = (arr: number[], n: number): number[] => {
    const k = 2 / (n + 1)
    const out: number[] = []
    let prev = arr[0]
    out.push(prev)
    for (let i = 1; i < arr.length; i++) {
      prev = arr[i] * k + prev * (1 - k)
      out.push(prev)
    }
    return out
  }
  const ef = ema(closes, fast)
  const es = ema(closes, slow)
  const macdLine = closes.map((_, i) => ef[i] - es[i])
  const signalLine = ema(macdLine, sig)
  const histArr = macdLine.map((v, i) => v - signalLine[i])
  const r2 = (n: number) => Math.round(n * 100) / 100
  return {
    macd: bars.map((b, i) => ({ time: b.date, value: r2(macdLine[i]) })),
    signal: bars.map((b, i) => ({ time: b.date, value: r2(signalLine[i]) })),
    hist: bars.map((b, i) => ({ time: b.date, value: r2(histArr[i]) })),
  }
}

export function kdj(bars: Bar[], n = 9): { k: MaPoint[]; d: MaPoint[]; j: MaPoint[] } {
  if (bars.length < n) return { k: [], d: [], j: [] }
  const k: MaPoint[] = []
  const d: MaPoint[] = []
  const j: MaPoint[] = []
  let prevK = 50
  let prevD = 50
  for (let i = n - 1; i < bars.length; i++) {
    let highN = -Infinity
    let lowN = Infinity
    for (let p = i - n + 1; p <= i; p++) {
      highN = Math.max(highN, bars[p].high)
      lowN = Math.min(lowN, bars[p].low)
    }
    const rng = highN - lowN
    const rsv = rng === 0 ? 50 : ((bars[i].close - lowN) / rng) * 100
    const curK = (2 / 3) * prevK + (1 / 3) * rsv
    const curD = (2 / 3) * prevD + (1 / 3) * curK
    const curJ = 3 * curK - 2 * curD
    k.push({ time: bars[i].date, value: round2(curK) })
    d.push({ time: bars[i].date, value: round2(curD) })
    j.push({ time: bars[i].date, value: round2(curJ) })
    prevK = curK
    prevD = curD
  }
  return { k, d, j }
}
