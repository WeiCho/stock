/**
 * 共用型別：跟後端 API 對齊的最小 schema，
 * 用來收緊原本散在各處的 `any` annotation。
 */

// ─── K 線 / 指標 ─────────────────────────────────────────

// 後端 /stock/{symbol}/price (或 /intraday) 的單根 K 結構
export interface Bar {
  date: string  // 'YYYY-MM-DD' 或 ISO datetime（盤中分鐘 K）
  open: number
  high: number
  low: number
  close: number
  volume: number
  average?: number  // 僅盤中 K 有（Fugle 提供的均價）
}

// MA 序列：lightweight-charts 接受 time 為字串（'YYYY-MM-DD'）或 epoch 秒（number）
export interface MaPoint {
  time: string | number
  value: number
}

// useAsync 的泛型 state
export interface AsyncState<T> {
  data: T | null
  loading: boolean
  error: string | null
}

// ─── API 回應 ────────────────────────────────────────────

export interface PriceResponse {
  symbol: string
  name?: string
  tf?: string
  data: Bar[]
  // 盤中時 fugle.intraday_candles 會附加：
  previousClose?: number
  openPrice?: number
  closePrice?: number
}

export interface BacktestStat {
  hold_days: number
  sample_count: number
  win_rate: number
  avg_return: number
  max_gain: number
  max_loss: number
}

export interface BacktestResponse {
  symbol: string
  signal: string
  signal_name: string
  total_triggers: number
  low_sample_warning?: boolean
  trigger_dates?: string[]
  stats: BacktestStat[]
  disclaimer?: string
  note?: string
}

export interface TechnicalSignal {
  type: 'bullish' | 'bearish'
  name: string
  code?: string  // i18n key suffix → technical.signal.{code}
  params?: Record<string, string | number>
}

export interface TechnicalResponse {
  ma?: Record<string, number>
  rsi?: number
  macd?: { macd?: number; signal?: number; hist?: number }
  kd?: { k?: number; d?: number }
  bollinger?: { upper?: number; middle?: number; lower?: number }
  trend?: string
  signals?: TechnicalSignal[]
  close?: number
  support?: number
  resistance?: number
}

export interface OutlookFactor {
  label: string  // 中文 fallback
  weight: number
  labelKey?: string | null  // i18n key（technical.signal.* 或 outlook.factor.*）
  params?: Record<string, string | number>
}

export interface OutlookExpected {
  horizon_days: number
  basis: string
  basis_code?: string  // i18n key → backtest.signal.{basis_code}
  win_rate: number
  avg_return: number
  target: number
  range_low: number
  range_high: number
  low_sample?: boolean
  sample_count?: number
}

export interface OutlookResponse {
  bias?: '偏多' | '偏空' | '中性' | string
  score?: number
  trend?: string
  factors?: OutlookFactor[]
  expected?: OutlookExpected | null
  support?: number
  resistance?: number
  close?: number
  disclaimer?: string
}

export interface FundamentalsResponse {
  eps_latest?: number | null
  pe?: number | null
  revenue_mom?: number | null
  revenue_yoy?: number | null
  yield_rate?: number | null
  note?: string
}

export interface NewsItem {
  title: string
  url: string
  published_at?: string
  is_major?: boolean
  summary?: string | null
  sentiment?: string | null
}

export interface PineResponse {
  symbol: string
  signal: string
  file: string
  win_rate_20d: number | string
  avg_return_20d: number | string
  pine_code: string
}

// 籌碼面（/stock/{symbol}/chip）— 跟 server/chip.py 對齊 snake_case
export interface ChipFlow { today?: number; cum_5d?: number; trend?: string }
export interface ChipResponse {
  foreign?: ChipFlow
  trust?: ChipFlow
  dealer?: ChipFlow
  total_today?: number
  summary?: string
  date?: string
}

// 大單敲進（Fugle 逐筆）
export interface BigOrder {
  symbol: string
  name?: string
  max_size: number
  max_amount: number
  price: number
  count?: number
  trades?: { price: number; size: number; amount: number; time?: number }[]
}

// 型態掃描（/stock/{symbol}/pattern-scan）
export interface PatternDiagnostics {
  ma5_slope:  number | null
  ma10_slope: number | null
  ma20_slope: number | null
  ma60_slope: number | null
  close:      number | null
  ma20:       number | null
  ma60?:      number | null
  ma_spread?: number | null
  prev_close?:       number | null
  prev_ma60?:        number | null
  prev_vol?:         number | null
  vol_ma20?:         number | null
  vol_threshold?:    number | null
  ma60_gap?:         number | null
  ma60_gap_pct?:     number | null
  cond_tangle?:       boolean
  cond_above_three?:  boolean
  cond_near_ma60?:    boolean
  cond_short_up?:    boolean
  cond_above_ma20?:  boolean
  cond_first_break?: boolean
  cond_support?:     boolean
}

export interface PatternBacktestStat {
  hold_days: number
  sample_count: number
  win_rate: number
  avg_return: number
  max_gain: number
  max_loss: number
}

export interface PatternResult {
  pattern: string
  pattern_name: string
  description: string
  total_triggers: number
  trigger_dates: string[]
  backtest_stats?: PatternBacktestStat[]
  current: {
    triggered: boolean
    setup_triggered?: boolean
    ma60_bonus: boolean
    ma60_direction?: 'up' | 'down'
    label: string
  }
  diagnostics: PatternDiagnostics
}

export interface PatternScanResponse {
  symbol: string
  // 舊版單一型態欄位（向下相容）
  pattern: string
  pattern_name: string
  total_triggers: number
  trigger_dates: string[]
  current: { triggered: boolean; ma60_bonus: boolean; label: string }
  diagnostics: PatternDiagnostics
  // 新版多型態陣列
  patterns: PatternResult[]
}

// 全市場型態掃描（/market/pattern-scan）
export interface MarketPatternItem {
  symbol: string
  name: string
  close: number
  ma60: number
  ma60_gap_pct: number
  ma60_direction: 'up' | 'down'
  ma_spread: number
  ma_threshold: number
  prev_vol: number | null
  vol_threshold: number | null
  last_trigger: string | null
  total_triggers: number
}

export interface MarketPatternScanResponse {
  scanned: number
  triggered: MarketPatternItem[]
  setup: MarketPatternItem[]
  as_of: string | null
}

// 全市場週線W底掃描（/market/weekly-w-bottom-scan）
export interface WeeklyWBottomItem {
  symbol: string
  name: string
  close: number
  ma20w: number
  ma20w_gap_pct: number
  ma20w_direction: 'up' | 'down'
  week_vol: number
  vol_threshold: number | null
  last_trigger: string | null
  total_triggers: number
}

export interface WeeklyWBottomScanResponse {
  scanned: number
  triggered: WeeklyWBottomItem[]
  as_of: string | null
}

// 大盤資金動向（/market/money-flow）
export interface RankRow { symbol: string; name?: string; foreign?: number; trust?: number; dealer?: number }
export interface SectorRow { industry: string; count: number; total: number }
export interface MoneyFlowResponse {
  date?: string
  summary?: { foreign: number; trust: number; dealer: number; total: number }
  market_stats?: { turnover?: number | null; up?: number; down?: number; unchanged?: number }
  sector_flow?: { inflow?: SectorRow[]; outflow?: SectorRow[] }
  foreign_buy?: RankRow[]; foreign_sell?: RankRow[]
  trust_buy?: RankRow[]; trust_sell?: RankRow[]
}
