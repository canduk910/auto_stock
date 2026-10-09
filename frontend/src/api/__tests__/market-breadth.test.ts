/**
 * cycle416 Red — 시장 등락 통계 API 클라이언트 `src/api/market-breadth.ts` (A1~A5).
 *
 * 봉인하는 계약
 *  - `getMarketBreadth(days = 20): Promise<MarketBreadthData>` —
 *    `apiClient.get('/market/breadth', { params: { days }, timeout: MARKET_BREADTH_TIMEOUT_MS })`.
 *  - `MARKET_BREADTH_TIMEOUT_MS = 60_000` — 🔴 빼면 `apiClient` 기본 10초에 재시작 뒤 첫 조회(10~45초)가 잘린다.
 *  - `success=false` → `Error(서버 message)` 그대로.
 *  - HTTP 오류(422·500)·네트워크 오류 → `Error('시장 등락 통계를 불러오지 못했습니다')`.
 *
 * RED: 모듈 부재 → import 실패.
 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import { http, HttpResponse } from 'msw'

import apiClient from '../client'
import { getMarketBreadth, MARKET_BREADTH_TIMEOUT_MS } from '../market-breadth'
import { failed, wrap } from '../../test/factories'
import { server } from '../../test/server'
import { MARKET_BREADTH_FIXTURE } from '../../test/fixtures/marketBreadth.fixture'

const URL = '/api/market/breadth'
const GENERIC = '시장 등락 통계를 불러오지 못했습니다'

afterEach(() => {
  vi.restoreAllMocks()
})

describe('getMarketBreadth (cycle416)', () => {
  it('A1 요청 = GET /market/breadth · params.days · timeout 60초', async () => {
    const spy = vi.spyOn(apiClient, 'get').mockResolvedValue({ data: wrap(MARKET_BREADTH_FIXTURE) } as never)
    await getMarketBreadth()
    expect(MARKET_BREADTH_TIMEOUT_MS).toBe(60_000)
    expect(spy).toHaveBeenCalledTimes(1)
    const [path, config] = spy.mock.calls[0]
    expect(path).toBe('/market/breadth')
    expect(config).toMatchObject({ params: { days: 20 }, timeout: 60_000 })

    await getMarketBreadth(60)
    expect(spy.mock.calls[1][1]).toMatchObject({ params: { days: 60 }, timeout: 60_000 })
  })

  it('A2 실제 경로(MSW) — 성공이면 data 를 돌려주고 쿼리에 days=20', async () => {
    const seen: string[] = []
    server.use(
      http.get(URL, ({ request }) => {
        seen.push(new globalThis.URL(request.url).searchParams.get('days') ?? '')
        return HttpResponse.json(wrap(MARKET_BREADTH_FIXTURE))
      }),
    )
    const data = await getMarketBreadth()
    expect(seen).toEqual(['20'])
    expect(data.window.n_days).toBe(3)
    expect(data.days[0].total.up).toBe(870)
  })

  it('A3 success=false 는 서버 문장 그대로 Error', async () => {
    const msg = '오늘 이 화면의 KRX 조회 한도를 다 썼습니다 — 내일 다시 볼 수 있습니다'
    server.use(http.get(URL, () => HttpResponse.json(failed(msg))))
    await expect(getMarketBreadth()).rejects.toThrow(msg)
  })

  it.each([
    ['500', () => HttpResponse.json({ detail: 'internal' }, { status: 500 })],
    ['422', () => HttpResponse.json({ detail: [{ loc: ['query', 'days'], msg: 'bad' }] }, { status: 422 })],
    ['네트워크', () => HttpResponse.error()],
  ])('A4 %s 오류는 정해진 한 문장으로', async (_label, resolver) => {
    server.use(http.get(URL, resolver))
    await expect(getMarketBreadth()).rejects.toThrow(GENERIC)
  })
})
