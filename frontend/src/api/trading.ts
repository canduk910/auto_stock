import axios from 'axios'

import apiClient from './client'
import type { TradingStatusData, ActionResult, StrategiesResponse } from '../types/trading'
import type { ApiResponse } from '../types/common'

export const getTradingStatus = async (): Promise<TradingStatusData> => {
  const { data } = await apiClient.get<ApiResponse<TradingStatusData>>('/trading/status')
  return data.data
}

export const startTrading = async (): Promise<ActionResult> => {
  const { data } = await apiClient.post<ApiResponse<null>>('/trading/start')
  return { success: data.success, message: data.message }
}

export const stopTrading = async (): Promise<ActionResult> => {
  const { data } = await apiClient.post<ApiResponse<null>>('/trading/stop')
  return { success: data.success, message: data.message }
}

export const restartTrading = async (): Promise<ActionResult> => {
  const { data } = await apiClient.post<ApiResponse<null>>('/trading/restart')
  return { success: data.success, message: data.message }
}

export const getStrategies = async (): Promise<StrategiesResponse> => {
  const { data } = await apiClient.get<ApiResponse<Record<string, unknown>>>('/strategies')
  const raw = data.data ?? {}
  // API는 { momentum: {...}, volatility_breakout: {...} } 객체를 반환
  // 프론트용 배열로 변환
  const strategies = Object.entries(raw).map(([key, val]) => {
    const v = val as { name: string; enabled: boolean; weight: number; params?: Record<string, unknown>; total_investment?: number; invested_amount?: number; min_weight?: number }
    return { key, name: v.name, enabled: v.enabled, weight: v.weight, params: v.params, total_investment: v.total_investment, invested_amount: v.invested_amount, min_weight: v.min_weight }
  })
  return { strategies }
}

// tradable_boards (string[]) / exchange (string) / k_value_* (number) / 기타 number 등 혼합 허용
export type StrategyParamValue = number | string | string[] | null
export const updateStrategyParams = async (
  strategyId: string,
  params: Record<string, StrategyParamValue>,
): Promise<ActionResult> => {
  const { data } = await apiClient.put<ApiResponse<null>>(
    `/strategies/${strategyId}/params`,
    { params },
  )
  return { success: data.success, message: data.message }
}

/**
 * pydantic v2 가 검증 예외 앞에 붙이는 영문 접두사 — validator 본문(한글)만 남긴다.
 * ⚠️ `^[A-Za-z ]+, ` 같은 일반 패턴 금지 — 한글 메시지에 영문 구절이 섞이면 본문을
 * 잘라먹는다. 알려진 접두사만 명시적으로 열거한다 (ValueError / AssertionError).
 */
const PYDANTIC_MSG_PREFIX_RE = /^(?:Value error|Assertion failed), /

const stripPydanticPrefix = (msg: string): string => {
  const stripped = msg.replace(PYDANTIC_MSG_PREFIX_RE, '').trim()
  return stripped || msg
}

/** 422(pydantic validator) 본문에서 사람이 읽을 메시지를 추출. 실패 시 null. */
const extractValidationMessage = (detail: unknown): string | null => {
  if (typeof detail === 'string' && detail.trim()) return stripPydanticPrefix(detail)
  if (Array.isArray(detail) && detail.length > 0) {
    const msg = (detail[0] as { msg?: unknown })?.msg
    if (typeof msg === 'string' && msg.trim()) return stripPydanticPrefix(msg)
  }
  return null
}

export const updateStrategyWeights = async (
  weights: Record<string, number>,
): Promise<ActionResult> => {
  try {
    const { data } = await apiClient.put<ApiResponse<null>>('/strategies/weights', { weights })
    if (!data.success) {
      throw new Error(data.message || '비중 변경 실패')
    }
    return { success: data.success, message: data.message }
  } catch (err) {
    // 422 는 axios 가 던지므로 2xx 본문 해석 경로가 못 잡는다 — validator 의 한글 안내를
    // 운영자에게 그대로 노출한다 (미처리 시 "Request failed with status code 422" opaque).
    // ⚠️ `!data.success` 가 던진 일반 Error 는 재포장 금지 — 그대로 전파.
    if (axios.isAxiosError(err) && err.response?.status === 422) {
      const detail = (err.response.data as { detail?: unknown } | undefined)?.detail
      throw new Error(
        extractValidationMessage(detail) ??
          '비중 형식이 올바르지 않습니다 — 페이지를 새로고침한 뒤 다시 시도하세요',
      )
    }
    throw err
  }
}

export const manualSell = async (
  ticker: string,
  quantity: number,
): Promise<ActionResult> => {
  const { data } = await apiClient.post<ApiResponse<null>>('/trading/manual-sell', { ticker, quantity })
  return { success: data.success, message: data.message }
}

// J3 (2026-05-12) — 매매 가용 자금 비율
// system_config.cash_usage_ratio. 범위 [0.5, 1.0], 5% 단위. 기본 1.0.
// 변경 즉시 적용 안 됨 — 다음 영업일 _boot() 부터 반영.
export const getCashUsageRatio = async (): Promise<number> => {
  const { data } = await apiClient.get<ApiResponse<{ ratio: number }>>(
    '/strategies/system/cash-usage-ratio',
  )
  return data.data?.ratio ?? 1.0
}

export const updateCashUsageRatio = async (ratio: number): Promise<number> => {
  const { data } = await apiClient.put<ApiResponse<{ ratio: number }>>(
    '/strategies/system/cash-usage-ratio',
    { ratio },
  )
  if (!data.success) {
    throw new Error(data.message || '가용 자금 비율 저장 실패')
  }
  // 백엔드가 5% 단위로 보정한 값을 반환 (예: 0.83 → 0.85)
  return data.data?.ratio ?? ratio
}
