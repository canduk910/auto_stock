import apiClient from './client'
import type { BalanceData } from '../types/balance'
import type { ApiResponse } from '../types/common'
import type { ExitLinesResponse } from '../types/trading'

export const getBalance = async (): Promise<BalanceData> => {
  const { data } = await apiClient.get<ApiResponse<BalanceData>>('/balance')
  // cycle406 L2 — 백엔드가 get_balance() 소진 예외를 200 + success=false 로 흡수한다
  // (src/routes/balance.py). 여기서 그대로 null 을 돌려주면 BalanceTable 의
  // `if (!data) return null` 이 설명 없이 빈 화면을 그린다 — 던져서 기존 isError
  // 경로("잔고를 불러올 수 없습니다.")를 타게 한다.
  if (!data.success) {
    throw new Error(data.message || '잔고 조회 실패')
  }
  return data.data
}

/**
 * cycle412 G1 — 보유 청산선 스냅샷(실효 손절선 정본). cycle414 전략 패널·요약표가 함께 쓴다.
 *
 * 실패해도 HTTP 200 + `success=false`(exit-lines 설계) — 조회 실패는 빈 목록으로 흡수해
 * 화면이 「보유 청산선을 모른다」 보다 나쁘게(틀린 값) 보이지 않게 한다.
 */
export const getExitLines = async (): Promise<ExitLinesResponse> => {
  try {
    const { data } = await apiClient.get<ApiResponse<ExitLinesResponse | null>>('/balance/exit-lines')
    if (!data.success || !data.data) return { running: false, as_of: '', items: [] }
    return data.data
  } catch {
    return { running: false, as_of: '', items: [] }
  }
}
