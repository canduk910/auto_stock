import { useCallback } from "react"
import { useAsyncState } from "./useAsyncState"
import {
  fetchCommodities,
  fetchCreditSpread,
  fetchCurrencies,
  fetchMacroCycle,
  fetchSp500,
  fetchYieldCurve,
} from "../../api/macro"
import type {
  CommoditiesResponse,
  CreditSpreadResponse,
  CurrenciesResponse,
  MacroCycleResponse,
  Sp500Response,
  YieldCurveResponse,
} from "../../types/macro"

// 원본 `macro_lite/hooks/useMacro.js` 이식 — 5개 섹션마다 독립 loading/error/data.
// `MacroPage.tsx` 가 mount 시 `load()` 를 한 번씩 호출한다.

export function useMacroCycle() {
  const { data, loading, error, run } = useAsyncState<MacroCycleResponse>()
  const load = useCallback(() => run(() => fetchMacroCycle()).catch(() => {}), [run])
  return { data, loading, error, load }
}

export function useYieldCurve() {
  const { data, loading, error, run } = useAsyncState<YieldCurveResponse>()
  const load = useCallback(() => run(() => fetchYieldCurve()).catch(() => {}), [run])
  return { data, loading, error, load }
}

export function useCreditSpread() {
  const { data, loading, error, run } = useAsyncState<CreditSpreadResponse>()
  const load = useCallback(() => run(() => fetchCreditSpread()).catch(() => {}), [run])
  return { data, loading, error, load }
}

export function useCurrencies() {
  const { data, loading, error, run } = useAsyncState<CurrenciesResponse>()
  const load = useCallback(() => run(() => fetchCurrencies()).catch(() => {}), [run])
  return { data, loading, error, load }
}

export function useCommodities() {
  const { data, loading, error, run } = useAsyncState<CommoditiesResponse>()
  const load = useCallback(() => run(() => fetchCommodities()).catch(() => {}), [run])
  return { data, loading, error, load }
}

/** S&P500 주간 종가 (cycle310). 실패해도 화면 본선은 살아 있어야 하므로 조용히 삼킨다. */
export function useSp500() {
  const { data, loading, error, run } = useAsyncState<Sp500Response>()
  const load = useCallback(() => run(() => fetchSp500()).catch(() => {}), [run])
  return { data, loading, error, load }
}
