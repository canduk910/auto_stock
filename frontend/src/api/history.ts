import apiClient from './client'
import type { TradeHistoryData, TradePnLData } from '../types/trading'
import type { ApiResponse } from '../types/common'
import type { JournalNotePut, JournalQuery, JournalResponse } from '../types/journal'

export interface HistoryParams {
  page?: number
  size?: number
  ticker?: string
  strategy?: string
}

export const getTradeHistory = async (
  params: HistoryParams = {},
): Promise<TradeHistoryData> => {
  const { data } = await apiClient.get<ApiResponse<TradeHistoryData>>('/history', { params })
  return data.data
}

export const getTradePnL = async (
  params: HistoryParams = {},
): Promise<TradePnLData> => {
  const { data } = await apiClient.get<ApiResponse<TradePnLData>>('/history/pnl', { params })
  return data.data
}

// cycle413 — 거래일지 화면(1b). 명세 `_workspace/red/cycle413/journal_view_spec.md` 1-1·1-3.
export const getJournal = async (params: JournalQuery): Promise<JournalResponse> => {
  const { data } = await apiClient.get<ApiResponse<JournalResponse>>('/history/journal', { params })
  return data.data
}

export const putJournalNote = async (
  anchorTradeId: string,
  body: string,
): Promise<JournalNotePut | null> => {
  const { data } = await apiClient.put<ApiResponse<JournalNotePut | null>>(
    `/history/journal/notes/${anchorTradeId}`,
    { body },
  )
  return data.data
}
