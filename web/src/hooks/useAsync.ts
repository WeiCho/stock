import { useEffect, useState } from 'react'
import type { AsyncState } from '../types'

/**
 * 把一個 promise-returning 函式包進 React state：
 * - 切換 deps 時自動取消舊 promise（透過 cancelled flag）
 * - 載入中保留上一輪的 data（少一個 flicker）
 * - error 統一拍成 string
 *
 * deps 由呼叫端自行決定（依參考相等性觸發 refetch）。
 */
export function useAsync<T>(fn: () => Promise<T>, deps: unknown[]) {
  const [state, setState] = useState<AsyncState<T>>({ data: null, loading: false, error: null })
  useEffect(() => {
    let cancelled = false
    setState(s => ({ ...s, loading: true, error: null }))
    fn().then(data => {
      if (!cancelled) setState({ data, loading: false, error: null })
    }).catch(err => {
      if (!cancelled) setState({ data: null, loading: false, error: err?.message ?? String(err) })
    })
    return () => { cancelled = true }
    // deps 由呼叫端控制
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)
  return state
}
