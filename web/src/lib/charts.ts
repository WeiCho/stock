/**
 * 跟 lightweight-charts 互動的共用 helper —— 由 PriceChart / MarketOverview / App 共用。
 * 集中在一個檔案，避免「同一份 toTime 邏輯散落多處 + race condition 時格式不一致」的歷史問題。
 */
import { UTCTimestamp, Time } from 'lightweight-charts'

/**
 * 'YYYY-MM-DD' 字串原樣回傳（v5 內建解析）；
 * ISO datetime（含 'T' 的字串）→ epoch 秒（給盤中分鐘 K 用）。
 */
export const toTime = (s: string): Time =>
  (typeof s === 'string' && s.includes('T'))
    ? (Math.floor(new Date(s).getTime() / 1000) as UTCTimestamp)
    : (s as Time)

/** 台股盤中總分鐘數（09:00 → 13:30）。算 rightOffset / X 軸範圍時用。 */
export const SESSION_MINUTES = 270

/** 台股盤中（週一到週五 09:00–13:30，台北時間）。用於 gate 即時 polling。 */
export function isTradingHours(): boolean {
  const tw = new Date(new Date().toLocaleString('en-US', { timeZone: 'Asia/Taipei' }))
  const day = tw.getDay()  // 0=Sun, 6=Sat
  if (day === 0 || day === 6) return false
  const hm = tw.getHours() * 100 + tw.getMinutes()
  return hm >= 900 && hm <= 1330
}
