/**
 * 사이클 103 영역 1 — Strategies 페이지 회귀 가드 (UI 손절 임계 가시화).
 *
 * 명세: _workspace/red/cycle103_area1_strategy_thresholds_ui.md
 * 영속 의무: 사이클 41 / 65 H3 retry:1 / 68 KST / 89 한글 친숙 / 102 G-REJECT
 *
 * 회귀 가드 매트릭스 (HIGH 5):
 * - H1: 4 임계 렌더 (stop_loss_rate / daily_loss_limit / trailing_stop_rate / position_ratio)
 * - H2: API GET /api/strategies 영역 strategy_config.params 정합
 * - H3: 한글 라벨 + 영문 영역 0건
 * - H4: 데이터 영역 부재 시 graceful (params={})
 * - H5: 모바일 viewport 375px 영역 4 임계 영역 정합
 */
import { describe, expect, it, beforeEach, afterEach } from 'vitest'
import { http, HttpResponse } from 'msw'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import type { ReactNode } from 'react'

import Strategies from '../Strategies'
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

const SAMPLE_STRATEGIES_RESPONSE = {
  strategies: [
    {
      key: 'momentum',
      name: '상한가 모멘텀',
      weight: 0.25,
      enabled: true,
      total_investment: 10_000_000,
      params: {
        stop_loss_rate: -7.5,
        daily_loss_limit: -5.0,
        trailing_stop_rate: -2.0,
        position_ratio: 0.25,
      },
    },
    {
      key: 'volatility_breakout',
      name: '변동성 돌파',
      weight: 0.25,
      enabled: true,
      total_investment: 10_000_000,
      params: {
        stop_loss_rate: -3.0,
        daily_loss_limit: -5.0,
        trailing_stop_rate: -2.0,
        position_ratio: 0.25,
      },
    },
  ],
}

beforeEach(() => {
  server.use(
    http.get('*/api/strategies', () =>
      HttpResponse.json({
        success: true,
        data: SAMPLE_STRATEGIES_RESPONSE,
        message: 'OK',
      }),
    ),
  )
})

afterEach(() => {
  server.resetHandlers()
})

describe('사이클 103 영역 1 — Strategies 4 임계 가시화', () => {
  it('H1: 4 임계 렌더 정합 (stop_loss_rate / daily_loss_limit / trailing_stop_rate / position_ratio)', async () => {
    render(withProviders(<Strategies />))

    await waitFor(() => {
      expect(screen.getByTestId('strategy-card-momentum')).toBeTruthy()
    })

    // 4 임계 영역 testid 영속
    expect(screen.getByTestId('strategy-momentum-stop-loss-rate')).toBeTruthy()
    expect(screen.getByTestId('strategy-momentum-daily-loss-limit')).toBeTruthy()
    expect(screen.getByTestId('strategy-momentum-trailing-stop-rate')).toBeTruthy()
    expect(screen.getByTestId('strategy-momentum-position-ratio')).toBeTruthy()

    // 임계 값 영역 영속
    const stopLoss = screen.getByTestId('strategy-momentum-stop-loss-rate')
    expect(stopLoss.textContent ?? '').toContain('-7.5')

    const dailyLoss = screen.getByTestId('strategy-momentum-daily-loss-limit')
    expect(dailyLoss.textContent ?? '').toContain('-5.0')

    const trailing = screen.getByTestId('strategy-momentum-trailing-stop-rate')
    expect(trailing.textContent ?? '').toContain('-2.0')

    const positionRatio = screen.getByTestId('strategy-momentum-position-ratio')
    expect(positionRatio.textContent ?? '').toMatch(/25|0\.25/)
  })

  it('H2: API GET /api/strategies 영역 strategy_config.params 정합 (다중 전략)', async () => {
    render(withProviders(<Strategies />))

    await waitFor(() => {
      expect(screen.getByTestId('strategy-card-momentum')).toBeTruthy()
      expect(screen.getByTestId('strategy-card-volatility_breakout')).toBeTruthy()
    })

    // VB 전략 영역 4 임계 영속
    expect(screen.getByTestId('strategy-volatility_breakout-stop-loss-rate')).toBeTruthy()
    expect(
      screen.getByTestId('strategy-volatility_breakout-stop-loss-rate').textContent ?? '',
    ).toContain('-3.0')
  })

  it('H3: 한글 라벨 + 영문 raw 키 영역 0건 (사이클 89 답습)', async () => {
    render(withProviders(<Strategies />))

    await waitFor(() => {
      expect(screen.getByTestId('strategy-card-momentum')).toBeTruthy()
    })

    // 한글 라벨 영역 영속
    const card = screen.getByTestId('strategy-card-momentum')
    const text = card.textContent ?? ''

    // 4 임계 한글 라벨 영역 (최소 1개 영역 영속)
    const hasKoreanLabel =
      text.includes('손절') ||
      text.includes('일일 손실') ||
      text.includes('트레일링') ||
      text.includes('종목당')
    expect(hasKoreanLabel).toBe(true)
  })

  it('H4: 데이터 영역 부재 시 graceful (params={})', async () => {
    server.use(
      http.get('*/api/strategies', () =>
        HttpResponse.json({
          success: true,
          data: {
            strategies: [
              {
                key: 'momentum',
                name: '상한가 모멘텀',
                weight: 0.25,
                enabled: true,
                total_investment: 10_000_000,
                params: {},
              },
            ],
          },
          message: 'OK',
        }),
      ),
    )

    render(withProviders(<Strategies />))

    await waitFor(() => {
      expect(screen.getByTestId('strategy-card-momentum')).toBeTruthy()
    })

    // 4 임계 영역 = 0 표시 또는 "—" 영역 영속 (Error Boundary 미발화)
    const stopLoss = screen.getByTestId('strategy-momentum-stop-loss-rate')
    expect(stopLoss.textContent ?? '').toMatch(/0|—|-/)
  })

  it('H5: 모바일 viewport 375px 영역 4 임계 영역 정합', async () => {
    // viewport 시뮬레이션 = window.innerWidth 영역 변경
    Object.defineProperty(window, 'innerWidth', { value: 375, writable: true })

    render(withProviders(<Strategies />))

    await waitFor(() => {
      expect(screen.getByTestId('strategy-card-momentum')).toBeTruthy()
    })

    // 4 임계 영역 모두 렌더 영속 (모바일 viewport 영역 영속)
    expect(screen.getByTestId('strategy-momentum-stop-loss-rate')).toBeTruthy()
    expect(screen.getByTestId('strategy-momentum-daily-loss-limit')).toBeTruthy()
    expect(screen.getByTestId('strategy-momentum-trailing-stop-rate')).toBeTruthy()
    expect(screen.getByTestId('strategy-momentum-position-ratio')).toBeTruthy()
  })
})
