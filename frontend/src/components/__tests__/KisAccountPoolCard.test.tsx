/**
 * 사이클 7-D (2026-05-18) Red — KisAccountPoolCard (Dashboard).
 *
 * WebsocketPool 세션 상태 + 슬롯 사용률 + REST 시세 풀 분배 모니터링.
 *
 * 요구 행위:
 * - 7D-PA: 보조 0개 → 메인 1행만 + "보조 세션 없음 (메인 only)" 안내
 * - 7D-PB: 메인 + 보조 2 → 3행 표 (label/connected/subscribed/limit)
 * - 7D-PC: 세션 disconnect → red 배지
 * - 7D-PD: 슬롯 가득 → 진행바 100% (사용률 색 변경)
 * - 7D-PE: API 에러 → graceful 안내 메시지
 * - 7D-PF: 새로고침 버튼 클릭 → 즉시 재조회
 */
import { describe, it, expect } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { http, HttpResponse } from 'msw'

import KisAccountPoolCard from '../KisAccountPoolCard'
import { TestProviders } from '../../test/providers'
import { wrap } from '../../test/factories'
import { server } from '../../test/server'

const subsMainOnly = {
  total: 12,
  acked: 12,
  fresh_60s: 10,
  stale_60s: 2,
  limit: 41,
  reconnect_count: 0,
  ws_connected: true,
  sessions: [
    {
      label: 'main',
      subscribed: 12,
      acked: 12,
      fresh: 10,
      stale: 2,
      limit: 41,
      ws_connected: true,
      reconnect_count: 0,
      tickers: { subscribed: [], acked: [] },
    },
  ],
}

const subsMainPlus2 = {
  total: 80,
  acked: 80,
  fresh_60s: 75,
  stale_60s: 5,
  limit: 123, // 41 * 3
  reconnect_count: 1,
  ws_connected: true,
  sessions: [
    {
      label: 'main',
      subscribed: 41,
      acked: 41,
      fresh: 38,
      stale: 3,
      limit: 41,
      ws_connected: true,
      reconnect_count: 1,
      tickers: { subscribed: [], acked: [] },
    },
    {
      label: 'quote-1',
      subscribed: 25,
      acked: 25,
      fresh: 24,
      stale: 1,
      limit: 41,
      ws_connected: true,
      reconnect_count: 0,
      tickers: { subscribed: [], acked: [] },
    },
    {
      label: 'quote-2',
      subscribed: 14,
      acked: 14,
      fresh: 13,
      stale: 1,
      limit: 41,
      ws_connected: false,
      reconnect_count: 2,
      tickers: { subscribed: [], acked: [] },
    },
  ],
}

const subsSlotFull = {
  total: 41,
  acked: 41,
  fresh_60s: 40,
  stale_60s: 1,
  limit: 41,
  reconnect_count: 0,
  ws_connected: true,
  sessions: [
    {
      label: 'main',
      subscribed: 41,
      acked: 41,
      fresh: 40,
      stale: 1,
      limit: 41,
      ws_connected: true,
      reconnect_count: 0,
      tickers: { subscribed: [], acked: [] },
    },
  ],
}

describe('KisAccountPoolCard', () => {
  it('7D-PA: 보조 0개 → 메인 1행만 + 안내', async () => {
    server.use(
      http.get('/api/realtime/subscriptions', () =>
        HttpResponse.json(wrap(subsMainOnly)),
      ),
    )
    render(
      <TestProviders>
        <KisAccountPoolCard />
      </TestProviders>,
    )

    await screen.findByTestId('kis-account-pool-card')
    const mainRow = await screen.findByTestId('pool-session-row-main')
    expect(mainRow.textContent).toContain('main')

    // 보조 0개 안내
    await waitFor(() => {
      const note = screen.getByTestId('pool-no-secondary-note')
      expect(note.textContent).toMatch(/보조 세션 없음|메인 only|메인만/)
    })
  })

  it('7D-PB: 메인 + 보조 2 → 3행 표', async () => {
    server.use(
      http.get('/api/realtime/subscriptions', () =>
        HttpResponse.json(wrap(subsMainPlus2)),
      ),
    )
    render(
      <TestProviders>
        <KisAccountPoolCard />
      </TestProviders>,
    )

    await screen.findByTestId('pool-session-row-main')
    await screen.findByTestId('pool-session-row-quote-1')
    await screen.findByTestId('pool-session-row-quote-2')

    // 총 슬롯 표시 (41 × 3 = 123)
    const totalSlots = await screen.findByTestId('pool-total-slots')
    expect(totalSlots.textContent).toContain('123')
  })

  it('7D-PC: 세션 disconnect → red 배지', async () => {
    server.use(
      http.get('/api/realtime/subscriptions', () =>
        HttpResponse.json(wrap(subsMainPlus2)),
      ),
    )
    render(
      <TestProviders>
        <KisAccountPoolCard />
      </TestProviders>,
    )

    const disconnectedBadge = await screen.findByTestId('pool-session-status-quote-2')
    // disconnect = red 컬러 클래스 보유 또는 텍스트
    expect(disconnectedBadge.className).toMatch(/red/)
  })

  it('7D-PD: 슬롯 가득 → 진행바 100% / 색 변경', async () => {
    server.use(
      http.get('/api/realtime/subscriptions', () =>
        HttpResponse.json(wrap(subsSlotFull)),
      ),
    )
    render(
      <TestProviders>
        <KisAccountPoolCard />
      </TestProviders>,
    )

    const progressBar = await screen.findByTestId('pool-usage-progress')
    // width: 100% style 또는 progressed 표시
    expect(progressBar.getAttribute('style') ?? '').toMatch(/100/)
  })

  it('7D-PE: API 에러 → graceful 안내', async () => {
    server.use(
      http.get('/api/realtime/subscriptions', () =>
        new HttpResponse(null, { status: 500 }),
      ),
    )
    render(
      <TestProviders>
        <KisAccountPoolCard />
      </TestProviders>,
    )

    await waitFor(() => {
      const err = screen.getByTestId('pool-error-message')
      expect(err.textContent).toMatch(/불러오지 못했|오류|재시도/)
    })
  })

  it('7D-PF: 새로고침 버튼 클릭 → 즉시 재조회', async () => {
    let callCount = 0
    server.use(
      http.get('/api/realtime/subscriptions', () => {
        callCount += 1
        return HttpResponse.json(wrap(subsMainOnly))
      }),
    )
    render(
      <TestProviders>
        <KisAccountPoolCard />
      </TestProviders>,
    )

    await screen.findByTestId('pool-session-row-main')
    const initialCount = callCount

    fireEvent.click(screen.getByTestId('pool-refresh-button'))

    await waitFor(() => {
      expect(callCount).toBeGreaterThan(initialCount)
    })
  })
})
