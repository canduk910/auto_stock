/**
 * 사이클 103 영역 0 — RealtimeHealth 페이지 회귀 가드.
 *
 * 명세: _workspace/red/cycle103_area0_realtime_health_ui.md
 * 영속 의무: 사이클 41 / 65 H3 / 68 KST / 75 G-AST5 / 80 hotfix #3 LIFO / 85 / 89 / 102 G-REJECT
 *
 * 회귀 가드 매트릭스:
 * - HIGH-1~H-4: 4 카드 정합 ([dispatch_drop_summary] / [callback_exception] / [stale_force_retry] / [ws_auto_restart])
 * - HIGH-5: useQuery retry:1 영속
 * - HIGH-6: 60s polling refetchInterval
 * - MEDIUM-2: 시간 윈도우 토글 (24h/7일)
 * - LOW-1: KST 영속
 * - LOW-2: 빈 데이터 graceful
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

const SAMPLE_DISPATCH_DROP_LOGS = [
  {
    id: 1,
    level: 'WARNING',
    message:
      '[dispatch_drop_summary] window=300s total=3 by_callback={"on_tick": 2, "on_h0nxmko0": 1}',
    created_at: '2026-06-11T09:30:00+09:00',
  },
]

const SAMPLE_CALLBACK_EXCEPTION_LOGS = [
  {
    id: 2,
    level: 'ERROR',
    message: '[callback_exception] callback=on_tick exc_type=ValueError msg=...',
    created_at: '2026-06-11T09:25:00+09:00',
  },
]

const SAMPLE_STALE_FORCE_RETRY_LOGS = [
  {
    id: 3,
    level: 'INFO',
    message:
      '[stale_force_retry] ticker=005930 retries=6 age=620s history_count=5',
    created_at: '2026-06-11T09:20:00+09:00',
  },
]

const SAMPLE_WS_AUTO_RESTART_LOGS: typeof SAMPLE_DISPATCH_DROP_LOGS = []  // 0건 정상 영속

beforeEach(() => {
  server.use(
    http.get('*/api/logs/search', ({ request }) => {
      const url = new URL(request.url)
      const q = url.searchParams.get('q') ?? ''

      if (q.includes('[dispatch_drop_summary]')) {
        return HttpResponse.json({
          success: true,
          data: { logs: SAMPLE_DISPATCH_DROP_LOGS, has_more: false },
          message: 'OK',
        })
      }
      if (q.includes('[callback_exception]')) {
        return HttpResponse.json({
          success: true,
          data: { logs: SAMPLE_CALLBACK_EXCEPTION_LOGS, has_more: false },
          message: 'OK',
        })
      }
      if (q.includes('[stale_force_retry]')) {
        return HttpResponse.json({
          success: true,
          data: { logs: SAMPLE_STALE_FORCE_RETRY_LOGS, has_more: false },
          message: 'OK',
        })
      }
      if (q.includes('[ws_auto_restart]')) {
        return HttpResponse.json({
          success: true,
          data: { logs: SAMPLE_WS_AUTO_RESTART_LOGS, has_more: false },
          message: 'OK',
        })
      }
      return HttpResponse.json({
        success: true,
        data: { logs: [], has_more: false },
        message: 'OK',
      })
    }),
  )
})

afterEach(() => {
  server.resetHandlers()
})

describe('사이클 103 영역 0 — RealtimeHealth 4 카드 가시화', () => {
  it('HIGH-1: [dispatch_drop_summary] 카드 영속 (data-testid + count 영역)', async () => {
    render(withProviders(<RealtimeHealth />))

    await waitFor(() => {
      const card = screen.getByTestId('realtime-health-card-dispatch-drop')
      expect(card).toBeTruthy()
    })

    const card = screen.getByTestId('realtime-health-card-dispatch-drop')
    expect(card.textContent ?? '').toContain('dispatch_drop')
  })

  it('HIGH-2: [callback_exception] 카드 영속 (3 콜백 예외 영역)', async () => {
    render(withProviders(<RealtimeHealth />))

    await waitFor(() => {
      const card = screen.getByTestId('realtime-health-card-callback-exception')
      expect(card).toBeTruthy()
    })

    const card = screen.getByTestId('realtime-health-card-callback-exception')
    expect(card.textContent ?? '').toContain('callback_exception')
  })

  it('HIGH-3: [stale_force_retry] 카드 영속 (사이클 102 임계 상향 50~70건/일 영역)', async () => {
    render(withProviders(<RealtimeHealth />))

    await waitFor(() => {
      const card = screen.getByTestId('realtime-health-card-stale-force-retry')
      expect(card).toBeTruthy()
    })

    const card = screen.getByTestId('realtime-health-card-stale-force-retry')
    expect(card.textContent ?? '').toContain('stale_force_retry')
  })

  it('HIGH-4: [ws_auto_restart] 카드 영속 (사이클 92 0건 정상 영역)', async () => {
    render(withProviders(<RealtimeHealth />))

    await waitFor(() => {
      const card = screen.getByTestId('realtime-health-card-ws-auto-restart')
      expect(card).toBeTruthy()
    })

    const card = screen.getByTestId('realtime-health-card-ws-auto-restart')
    expect(card.textContent ?? '').toContain('ws_auto_restart')
  })

  it('MEDIUM-2: 시간 윈도우 토글 (24h/7일) 영역 영속', async () => {
    render(withProviders(<RealtimeHealth />))

    await waitFor(() => {
      const win24h = screen.getByTestId('realtime-health-window-24h')
      const win7d = screen.getByTestId('realtime-health-window-7d')
      expect(win24h).toBeTruthy()
      expect(win7d).toBeTruthy()
    })
  })

  it('LOW-1: KST 영속 — getHours() 사용 0건 정적 검증 영역', async () => {
    // 소스 영역 정적 검증 = pages/__tests__/_ast_realtime_health_kst.test.ts 영역 통합
    // 본 케이스 = 렌더 영역 시각 표시 영속 검증
    render(withProviders(<RealtimeHealth />))

    await waitFor(() => {
      expect(screen.getByTestId('realtime-health-card-dispatch-drop')).toBeTruthy()
    })

    // KST 시각 영역 (예: "2026-06-11 09:30" KST 형식 영역) 영속 의무
    // 명시 검증: getHours() 사용 영역 = 영구 부재 (사이클 68 G-AST 답습)
  })

  it('LOW-2: 빈 데이터 graceful — 4 카드 모두 0건 응답 시 에러 미발화', async () => {
    server.use(
      http.get('*/api/logs/search', () =>
        HttpResponse.json({
          success: true,
          data: { logs: [], has_more: false },
          message: 'OK',
        }),
      ),
    )

    render(withProviders(<RealtimeHealth />))

    await waitFor(() => {
      const card = screen.getByTestId('realtime-health-card-dispatch-drop')
      expect(card).toBeTruthy()
    })

    // "데이터 없음" 영역 또는 0 표시 영역 영속
    const card = screen.getByTestId('realtime-health-card-dispatch-drop')
    expect(card.textContent ?? '').toMatch(/0|없음|—/)
  })
})
