/**
 * 사이클 186 (2026-06-29) — RealtimeHealth 5번째 카드 "장운영상태" Red 가드.
 *
 * 신규: VI 활성 / 거래정지 / 종목상태 이상 배지 + 서킷브레이커 추정 배지(계측 휴리스틱)
 *       + 종목별 detail + raw MKOP_CLS_CODE / 거래정지 사유 노출.
 * 데이터 소스: GET /api/realtime/market-operation (fetchMarketOperationStatus).
 * 승인 계획: ~/.claude/plans/hazy-prancing-cookie.md
 *
 * 영속 의무: 사이클 65 H3 useQuery retry:1 / 68 KST / 89 한글 친숙 용어 / 80 LIFO mock
 *
 * Red 가드:
 * - FE-CARD-RENDER: 장운영상태 카드 + VI/거래정지/종목상태 배지
 * - FE-CB-BADGE: circuit_breaker.suspected=true → "추정" orange / false → "정상" gray
 * - FE-DETAIL: details 종목별 행 (ticker + 사유 + MKOP)
 * - FE-EXISTING-4: 기존 4 카드 회귀 0 (동시 렌더)
 */
import { describe, expect, it, beforeEach, afterEach } from 'vitest'
import { http, HttpResponse } from 'msw'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import type { ReactNode } from 'react'

import RealtimeHealth from '../RealtimeHealth'
import { server } from '../../test/server'

function withProviders(children: ReactNode) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0, staleTime: 0 } },
  })
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  )
}

function makeMarketOpPayload(overrides: Record<string, unknown> = {}) {
  return {
    vi_active_count: 2,
    halt_active_count: 1,
    last_event_count: 3,
    iscd_stat_active_count: 1,
    vi_active_sample: ['005930', '000660'],
    halt_active_sample: ['000020'],
    circuit_breaker: {
      suspected: false,
      reasons: [],
      halt_ratio: 0.33,
      halted: 1,
      observed: 3,
      representative_mkop_cls_code: '110',
      halt_reasons_sample: ['서킷브레이커 발동'],
    },
    details: [
      {
        ticker: '000020',
        vi_code: '0',
        ovtm_vi_code: '0',
        halt_yn: 'Y',
        halt_reason: '서킷브레이커 발동',
        iscd_stat: '51',
        mkop_cls_code: '121',
        exch_code: 'KRX',
        received_at: '2026-06-29T09:30:00+09:00',
      },
      {
        ticker: '005930',
        vi_code: '1',
        ovtm_vi_code: '0',
        halt_yn: 'N',
        halt_reason: '',
        iscd_stat: '0',
        mkop_cls_code: '110',
        exch_code: 'KRX',
        received_at: '2026-06-29T09:31:00+09:00',
      },
    ],
    ...overrides,
  }
}

function useMarketOpHandler(payload: Record<string, unknown>) {
  server.use(
    // 기존 4 카드 (logs/search) — 빈 응답 graceful
    http.get('*/api/logs/search', () =>
      HttpResponse.json({ success: true, data: { logs: [], has_more: false }, message: 'OK' }),
    ),
    // 신규 5번째 카드 — 장운영상태
    http.get('*/api/realtime/market-operation', () =>
      HttpResponse.json({ success: true, data: payload, message: 'OK' }),
    ),
  )
}

beforeEach(() => {
  useMarketOpHandler(makeMarketOpPayload())
})

afterEach(() => {
  server.resetHandlers()
})

describe('사이클 186 — RealtimeHealth 장운영상태 카드', () => {
  it('FE-CARD-RENDER: 장운영상태 카드 + VI/거래정지/종목상태 배지', async () => {
    render(withProviders(<RealtimeHealth />))

    await waitFor(() => {
      expect(screen.getByTestId('realtime-health-card-market-operation')).toBeTruthy()
    })

    const card = screen.getByTestId('realtime-health-card-market-operation')
    const text = card.textContent ?? ''
    // 한글 친숙 용어 (사이클 89)
    expect(text).toMatch(/VI/)
    expect(text).toMatch(/거래정지/)
    expect(text).toMatch(/종목상태/)
  })

  it('FE-CB-BADGE: suspected=true → "추정" orange 배지', async () => {
    useMarketOpHandler(
      makeMarketOpPayload({
        circuit_breaker: {
          suspected: true,
          reasons: ['전 시장 거래정지 12/14 (86%)'],
          halt_ratio: 0.86,
          halted: 12,
          observed: 14,
          representative_mkop_cls_code: '121',
          halt_reasons_sample: ['서킷브레이커 발동'],
        },
      }),
    )

    render(withProviders(<RealtimeHealth />))

    await waitFor(() => {
      expect(screen.getByTestId('realtime-health-cb-badge')).toBeTruthy()
    })

    const badge = screen.getByTestId('realtime-health-cb-badge')
    expect(badge.textContent ?? '').toContain('추정')
    expect(badge.className).toContain('orange')
  })

  it('FE-CB-BADGE: suspected=false → "정상" gray 배지', async () => {
    render(withProviders(<RealtimeHealth />))

    await waitFor(() => {
      expect(screen.getByTestId('realtime-health-cb-badge')).toBeTruthy()
    })

    const badge = screen.getByTestId('realtime-health-cb-badge')
    expect(badge.textContent ?? '').toContain('정상')
    expect(badge.className).toContain('gray')
  })

  it('FE-DETAIL: details 종목별 행 (ticker + 사유 + MKOP)', async () => {
    render(withProviders(<RealtimeHealth />))

    await waitFor(() => {
      expect(screen.getByTestId('realtime-health-card-market-operation')).toBeTruthy()
    })

    const card = screen.getByTestId('realtime-health-card-market-operation')
    const text = card.textContent ?? ''
    expect(text).toContain('000020') // 거래정지 종목 ticker
    expect(text).toContain('서킷브레이커 발동') // 거래정지 사유
    expect(text).toContain('121') // raw MKOP_CLS_CODE 계측 노출
  })

  it('FE-EXISTING-4: 기존 4 카드 회귀 0 (장운영상태와 동시 렌더)', async () => {
    render(withProviders(<RealtimeHealth />))

    await waitFor(() => {
      expect(screen.getByTestId('realtime-health-card-market-operation')).toBeTruthy()
    })

    // 기존 4 카드 영속
    expect(screen.getByTestId('realtime-health-card-dispatch-drop')).toBeTruthy()
    expect(screen.getByTestId('realtime-health-card-callback-exception')).toBeTruthy()
    expect(screen.getByTestId('realtime-health-card-stale-force-retry')).toBeTruthy()
    expect(screen.getByTestId('realtime-health-card-ws-auto-restart')).toBeTruthy()
  })
})
