import apiClient from './client'
import type { BalanceData } from '../types/balance'
import type { ApiResponse } from '../types/common'

export const getBalance = async (): Promise<BalanceData> => {
  const { data } = await apiClient.get<ApiResponse<BalanceData>>('/balance')
  return data.data
}
