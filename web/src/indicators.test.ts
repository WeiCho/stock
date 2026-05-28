import { describe, it, expect } from 'vitest'
import { rsi, kdj } from './indicators'
import type { Bar } from './types'

// 工具：用收盤價序列造 Bar；high/low/open 給合理預設
function makeBars(closes: number[], highs?: number[], lows?: number[]): Bar[] {
  return closes.map((c, i) => ({
    date: `2024-01-${String(i + 1).padStart(2, '0')}`,
    open: c,
    high: highs?.[i] ?? c + 1,
    low: lows?.[i] ?? c - 1,
    close: c,
    volume: 1000,
  }))
}

describe('rsi', () => {
  it('returns empty array when bars < period+1', () => {
    expect(rsi(makeBars([1, 2, 3]), 14)).toEqual([])
  })

  it('all-rising series → RSI 接近 100（漲多跌少極端）', () => {
    const bars = makeBars(Array.from({ length: 20 }, (_, i) => 10 + i))
    const out = rsi(bars, 14)
    expect(out.length).toBeGreaterThan(0)
    // 一路漲：avgLoss = 0 → RSI = 100
    expect(out[out.length - 1].value).toBe(100)
  })

  it('all-falling series → RSI 為 0', () => {
    const bars = makeBars(Array.from({ length: 20 }, (_, i) => 100 - i))
    const out = rsi(bars, 14)
    expect(out[out.length - 1].value).toBe(0)
  })

  it('flat series → divisions handle zero loss', () => {
    const bars = makeBars(Array.from({ length: 20 }, () => 50))
    const out = rsi(bars, 14)
    // 完全沒漲跌：gains/losses 都是 0，要回 100（loss == 0 的特例）
    expect(out[0].value).toBe(100)
  })

  it('time field aligned with input bars', () => {
    const bars = makeBars(Array.from({ length: 20 }, (_, i) => 10 + (i % 3)))
    const out = rsi(bars, 14)
    // 第一個 RSI 點對應 bars[14]
    expect(out[0].time).toBe(bars[14].date)
  })
})

describe('kdj', () => {
  it('returns empty when bars < n', () => {
    expect(kdj(makeBars([1, 2, 3]), 9).k).toEqual([])
  })

  it('K/D/J 序列長度一致', () => {
    const bars = makeBars(Array.from({ length: 20 }, (_, i) => 10 + i * 0.5))
    const { k, d, j } = kdj(bars, 9)
    expect(k.length).toBe(d.length)
    expect(d.length).toBe(j.length)
    expect(k.length).toBe(bars.length - 8)
  })

  it('all-rising series → K 與 D 接近 100（多頭極端）', () => {
    const bars = makeBars(Array.from({ length: 30 }, (_, i) => 10 + i))
    const { k, d } = kdj(bars, 9)
    expect(k[k.length - 1].value).toBeGreaterThan(80)
    expect(d[d.length - 1].value).toBeGreaterThan(70)
  })

  it('J = 3K - 2D 公式恆等成立', () => {
    const bars = makeBars(Array.from({ length: 20 }, (_, i) => 50 + Math.sin(i) * 10))
    const { k, d, j } = kdj(bars, 9)
    for (let i = 0; i < k.length; i++) {
      const expected = 3 * k[i].value - 2 * d[i].value
      // 容忍 0.01 因為各別 round2
      expect(Math.abs(j[i].value - expected)).toBeLessThanOrEqual(0.05)
    }
  })

  it('flat high == low → RSV 退化為 50 不發散', () => {
    // 同一個價格 → high == low → rng == 0 → RSV = 50
    const bars = makeBars(Array.from({ length: 20 }, () => 100),
                          Array.from({ length: 20 }, () => 100),
                          Array.from({ length: 20 }, () => 100))
    const { k } = kdj(bars, 9)
    expect(k[k.length - 1].value).toBeCloseTo(50, 0)
  })
})
