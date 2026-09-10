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

// tradable_boards (string[]) / 거래소(string) / K값(number) / bool 토글 등 혼합 허용.
// cycle278 — `boolean` 을 추가했다. 카탈로그 99키에는 bool 타입이 실재하고, 종전 유니언은
// 그 키들을 프론트 타입 단계에서 이미 배제하고 있었다.
export type StrategyParamValue = number | string | string[] | boolean | null

/** 422 본문 `detail[]` 한 원소. `key === null` 은 불변식처럼 특정 칸에 못 붙는 오류다. */
export interface ParamErrorDetail {
  key: string | null
  /** `unknown_key|not_editable|type_mismatch|not_in_choices|pattern_mismatch|out_of_range|budget_invariant` */
  code: string
  /** 한글. pydantic 접두사 없음. */
  msg: string
  strategy_id?: string
  given?: unknown
  expected?: Record<string, unknown>
}

/** 200 응답에 실리는 경고(저장은 됐다). */
export interface ParamWarningDetail {
  key: string | null
  code: string
  msg: string
  strategy_id?: string
}

/**
 * 파라미터 검증 실패(422) 전용 오류. `details` 를 그대로 실어 화면이 **칸별로** 붙일 수 있게 한다.
 * 요약 문자열 하나만 던지면 "어느 칸이 왜 틀렸는지" 가 사라져 운영자가 전 항목을 왕복하게 된다.
 */
export class ParamValidationError extends Error {
  readonly details: ParamErrorDetail[]

  constructor(message: string, details: ParamErrorDetail[]) {
    super(message)
    this.name = 'ParamValidationError'
    this.details = details
    // ES5 타겟 트랜스파일에서 instanceof 가 깨지는 것을 막는다.
    Object.setPrototypeOf(this, ParamValidationError.prototype)
  }
}

export interface ParamsUpdateResult {
  success: boolean
  message: string
  /** 서버가 실제로 저장한 키·값. 무엇이 저장됐는지 화면이 확인하지 못하면 조용한 소실이 보이지 않는다. */
  applied?: Record<string, StrategyParamValue>
  warnings?: ParamWarningDetail[]
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

/**
 * 전략 파라미터 저장 (`PUT /api/strategies/{id}/params`).
 *
 * cycle278 이전에는 `data.success` 검사도 422 분기도 없어서
 *   - 범위 밖 값은 `Request failed with status code 422` 라는 opaque 문자열만 남기고
 *   - `success:false`(알 수 없는 전략 id)는 **저장 성공으로 보였다**.
 * `updateStrategyWeights` 와 동형으로 맞춘다.
 *
 * ⚠️ `!data.success` 가 던진 일반 Error 는 재포장 금지 — 그대로 전파한다.
 */
export const updateStrategyParams = async (
  strategyId: string,
  params: Record<string, StrategyParamValue>,
): Promise<ParamsUpdateResult> => {
  try {
    const { data } = await apiClient.put<
      ApiResponse<{
        applied?: Record<string, StrategyParamValue>
        warnings?: ParamWarningDetail[]
      } | null>
    >(`/strategies/${strategyId}/params`, { params })
    if (!data.success) {
      throw new Error(data.message || '파라미터 변경 실패')
    }
    const payload = data.data ?? {}
    return {
      success: data.success,
      message: data.message,
      applied: payload.applied,
      warnings: payload.warnings ?? [],
    }
  } catch (err) {
    // 422 는 axios 가 던지므로 2xx 본문 해석 경로가 못 잡는다.
    if (axios.isAxiosError(err) && err.response?.status === 422) {
      const detail = (err.response.data as { detail?: unknown } | undefined)?.detail
      const details: ParamErrorDetail[] = Array.isArray(detail)
        ? (detail as ParamErrorDetail[])
        : []
      throw new ParamValidationError(
        extractValidationMessage(detail) ??
          '파라미터 형식이 올바르지 않습니다 — 값을 확인한 뒤 다시 시도하세요',
        details,
      )
    }
    throw err
  }
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
