/**
 * cycle416 — `GET /api/market/breadth` API client (매크로 6번째 섹션, 시장 등락 통계).
 *
 * 전 종목 스캔이라 백엔드가 느릴 수 있다(재시도 + 동시성 제한 포함, 시한 45초) — 우리
 * `apiClient` 기본 timeout(10초)으로는 재시작 뒤 첫 조회가 잘리므로 60초로 올려 호출한다.
 * 응답은 우리 `ApiResponse<T>` 래퍼를 쓴다(`macro.ts` 의 5섹션과 다르다 — 그쪽은 독립
 * macro 컨테이너 원본 계약).
 */
import apiClient from './client'
import type { ApiResponse } from '../types/common'
import type { MarketBreadthData } from '../types/market-breadth'

export const MARKET_BREADTH_TIMEOUT_MS = 60_000

const GENERIC_ERROR = '시장 등락 통계를 불러오지 못했습니다'

export async function getMarketBreadth(days = 20): Promise<MarketBreadthData> {
  let resp
  try {
    resp = await apiClient.get<ApiResponse<MarketBreadthData>>('/market/breadth', {
      params: { days },
      timeout: MARKET_BREADTH_TIMEOUT_MS,
    })
  } catch {
    // HTTP 오류(4xx/5xx)·네트워크 오류 — 서버 문장이 없거나 믿을 수 없는 경우라 한 문장으로 통일.
    throw new Error(GENERIC_ERROR)
  }

  const body = resp.data
  if (!body.success) {
    // success=false 는 HTTP 200 으로 오고 서버가 이유를 문장으로 담아 보낸다 — 그대로 보여준다.
    throw new Error(body.message)
  }
  return body.data
}
