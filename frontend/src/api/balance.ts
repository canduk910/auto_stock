import apiClient from './client'
import type { BalanceData } from '../types/balance'
import type { ApiResponse } from '../types/common'

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
