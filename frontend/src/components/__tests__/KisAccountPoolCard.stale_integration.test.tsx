/**
 * 사이클 21 (2026-05-20) Red — KisAccountPoolCard 끊김 종목 통합.
 *
 * ScanMonitor 의 사이클 18 끊김 영역(stale-context-label / stale-list-toggle /
 * 수동 재구독 / 종목별 last_tick) 을 KisAccountPoolCard 로 이전.
 *
 * 요구 행위:
 * - C21-PA: stale_60s > 0 시 `pool-resubscribe-button` 노출 + 클릭 시 POST /api/realtime/resubscribe
 * - C21-PB: stale_60s > 0 시 `pool-stale-list-toggle` 노출
 * - C21-PC: toggle 클릭 → `pool-stale-row-{ticker}` + 마지막 tick KST HH:MM:SS 표시
 * - C21-PD: stale > 0 시 `stale-context-label` (KRX 메인 → 빨강 / PRE_NXT → 노랑 / 그 외 → 회색)
 * - C21-PE: last_tick_map[ticker] = null → "—" 표시
 * - C21-PF: stale_60s = 0 시 끊김 영역 모두 미노출
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { http, HttpResponse } from 'msw'

import KisAccountPoolCard from '../KisAccountPoolCard'
import { TestProviders } from '../../test/providers'
import { wrap } from '../../test/factories'
import { server } from '../../test/server'
import * as staleCtx from '../../utils/stale-context'

const subsWithStale = {
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
      tickers: {
        subscribed: ['005930', '000660', '012450'],
        acked: ['005930', '000660', '012450'],
        fresh: ['005930'],
        stale: ['000660', '012450'],
      },
    },
  ],
  tickers: {
    subscribed: ['005930', '000660', '012450'],
    acked: ['005930', '000660', '012450'],
    fresh: ['005930'],
    stale: ['000660', '012450'],
  },
  last_tick_map: {
    '005930': '2026-05-20T11:30:15+09:00',
    '000660': '2026-05-20T11:25:43+09:00',
    '012450': null,
  },
}

const subsNoStale = {
  total: 5,
  acked: 5,
  fresh_60s: 5,
  stale_60s: 0,
  limit: 41,
  reconnect_count: 0,
  ws_connected: true,
  sessions: [
    {
      label: 'main',
      subscribed: 5,
      acked: 5,
      fresh: 5,
      stale: 0,
      limit: 41,
      ws_connected: true,
      reconnect_count: 0,
      tickers: { subscribed: [], acked: [], fresh: [], stale: [] },
    },
  ],
  tickers: { subscribed: [], acked: [], fresh: [], stale: [] },
  last_tick_map: {},
}

describe('KisAccountPoolCard — 사이클 21 stale 통합', () => {
  beforeEach(() => {
    // KRX 메인 시간대 (12:00 KST = 720 분) 로 고정 → main_critical
    vi.spyOn(staleCtx, 'getKstMinutes').mockReturnValue(12 * 60)
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('C21-PA: stale_60s > 0 → pool-resubscribe-button 노출 + 클릭 시 POST 호출', async () => {
    let resubCalled = false
    server.use(
      http.get('/api/realtime/subscriptions', () =>
        HttpResponse.json(wrap(subsWithStale)),
      ),
      http.post('/api/realtime/resubscribe', () => {
        resubCalled = true
        return HttpResponse.json(wrap({ resubscribed: 2, tickers: ['000660', '012450'] }))
      }),
    )

    render(
      <TestProviders>
        <KisAccountPoolCard />
      </TestProviders>,
    )

    const button = await screen.findByTestId('pool-resubscribe-button')
    expect(button).toBeTruthy()

    fireEvent.click(button)

    await waitFor(() => {
      expect(resubCalled).toBe(true)
    })
  })

  it('C21-PB: stale_60s > 0 → pool-stale-list-toggle 노출', async () => {
    server.use(
      http.get('/api/realtime/subscriptions', () =>
        HttpResponse.json(wrap(subsWithStale)),
      ),
    )

    render(
      <TestProviders>
        <KisAccountPoolCard />
      </TestProviders>,
    )

    const toggle = await screen.findByTestId('pool-stale-list-toggle')
    expect(toggle.textContent).toMatch(/끊김 종목|보기|\(2개\)/)
  })

  it('C21-PC: toggle 클릭 → pool-stale-row-{ticker} + KST HH:MM:SS', async () => {
    server.use(
      http.get('/api/realtime/subscriptions', () =>
        HttpResponse.json(wrap(subsWithStale)),
      ),
    )

    render(
      <TestProviders>
        <KisAccountPoolCard />
      </TestProviders>,
    )

    const toggle = await screen.findByTestId('pool-stale-list-toggle')
    fireEvent.click(toggle)

    const row000660 = await screen.findByTestId('pool-stale-row-000660')
    expect(row000660.textContent).toContain('000660')
    // KST 11:25:43 형식 (Intl en-GB)
    expect(row000660.textContent).toMatch(/\d{2}:\d{2}:\d{2}/)
  })

  it('C21-PD: KRX 메인 시간대 → stale-context-label 빨강 (main_critical)', async () => {
    server.use(
      http.get('/api/realtime/subscriptions', () =>
        HttpResponse.json(wrap(subsWithStale)),
      ),
    )

    render(
      <TestProviders>
        <KisAccountPoolCard />
      </TestProviders>,
    )

    const ctxLabel = await screen.findByTestId('stale-context-label')
    expect(ctxLabel.textContent).toMatch(/KRX 메인|결함 가능/)
    expect(ctxLabel.className).toMatch(/red/)
  })

  it('C21-PE: last_tick_map[ticker] = null → "—" 표시', async () => {
    server.use(
      http.get('/api/realtime/subscriptions', () =>
        HttpResponse.json(wrap(subsWithStale)),
      ),
    )

    render(
      <TestProviders>
        <KisAccountPoolCard />
      </TestProviders>,
    )

    const toggle = await screen.findByTestId('pool-stale-list-toggle')
    fireEvent.click(toggle)

    const row012450 = await screen.findByTestId('pool-stale-row-012450')
    // last_tick_map[012450] = null → "—"
    expect(row012450.textContent).toMatch(/—|--/)
  })

  it('C21-PF: stale_60s = 0 → 끊김 영역 모두 미노출', async () => {
    server.use(
      http.get('/api/realtime/subscriptions', () =>
        HttpResponse.json(wrap(subsNoStale)),
      ),
    )

    render(
      <TestProviders>
        <KisAccountPoolCard />
      </TestProviders>,
    )

    await screen.findByTestId('kis-account-pool-card')

    expect(screen.queryByTestId('pool-resubscribe-button')).toBeNull()
    expect(screen.queryByTestId('pool-stale-list-toggle')).toBeNull()
    expect(screen.queryByTestId('stale-context-label')).toBeNull()
  })
})
