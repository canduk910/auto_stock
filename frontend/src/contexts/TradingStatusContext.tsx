import { createContext, useContext, type ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getTradingStatus } from '../api/trading'
import type { TradingStatusData } from '../types/trading'

interface TradingStatusValue {
  data: TradingStatusData | undefined
  isLoading: boolean
  isError: boolean
}

const TradingStatusContext = createContext<TradingStatusValue | undefined>(undefined)

/**
 * `/api/trading/status`를 5초 폴링하는 단일 owner.
 *
 * 이전엔 App/Dashboard/BalanceTable/OrderMonitor/ScanMonitor 5개 컴포넌트가
 * 각각 useQuery(['tradingStatus'])로 호출 → 같은 응답을 5번씩 받던 낭비.
 * Provider가 한 번만 구독하고 자식은 `useTradingStatus()` hook으로 공유.
 */
export function TradingStatusProvider({ children }: { children: ReactNode }) {
  const query = useQuery({
    queryKey: ['tradingStatus'],
    queryFn: getTradingStatus,
    refetchInterval: 5000,
    retry: false,
  })

  return (
    <TradingStatusContext.Provider
      value={{ data: query.data, isLoading: query.isLoading, isError: query.isError }}
    >
      {children}
    </TradingStatusContext.Provider>
  )
}

export function useTradingStatus(): TradingStatusValue {
  const ctx = useContext(TradingStatusContext)
  if (!ctx) {
    throw new Error('useTradingStatus must be used within <TradingStatusProvider>')
  }
  return ctx
}
