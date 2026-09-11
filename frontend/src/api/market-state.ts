/**
 * cycle282 (2026-09-11) — 장운영상태 API client.
 *
 * `GET /api/market-state` **한 번**으로 (a) 시장별 현재 커서 (b) 그 날짜에 유효한 표 전체
 * (c) 주문유형 카탈로그 (d) 표현 어휘·발견 문구를 모두 받는다.
 *
 * 표와 커서를 따로 부르지 않는 것이 이 화면의 계약이다 — 두 번 부르면 자정이나 경계
 * 순간에 표는 어제 것, 커서는 오늘 것이 되어 화면이 조용히 거짓말을 한다.
 */
import apiClient from './client'
import type { ApiResponse } from '../types/common'
import type { MarketStateData } from '../types/market-state'

/**
 * @param onDate `YYYY-MM-DD` 미리보기 날짜(생략 시 오늘). 다른 날짜면 서버가 커서를 비운다
 *   (`markets: null`) — "지금" 이 아닌 날짜에 커서를 그리면 그 자체가 거짓이기 때문이다.
 */
export async function fetchMarketState(onDate?: string): Promise<MarketStateData> {
  const resp = await apiClient.get<ApiResponse<MarketStateData>>('/market-state', {
    params: onDate ? { on_date: onDate } : undefined,
  })
  return resp.data.data
}
