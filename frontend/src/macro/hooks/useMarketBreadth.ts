import { useCallback } from "react"
import { useAsyncState } from "./useAsyncState"
import { getMarketBreadth } from "../../api/market-breadth"
import type { MarketBreadthData } from "../../types/market-breadth"

/**
 * cycle416 — 시장 등락 통계(매크로 6번째 섹션) 전용 훅.
 *
 * `useMacro.ts`(원본 macro_lite 이식 파일)는 손대지 않는다 — 이 엔드포인트는 그 5섹션과
 * 달리 우리 backend(`/api/market/breadth`)가 직접 낸다(FG3).
 */
export function useMarketBreadth(days = 20) {
  const { data, loading, error, run } = useAsyncState<MarketBreadthData>()
  const load = useCallback(() => run(() => getMarketBreadth(days)).catch(() => {}), [run, days])
  return { data, loading, error, load }
}
