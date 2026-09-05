/**
 * 전략 성과 표시 정직화 — PerformanceCard 테스트.
 *
 * 배경: 대시보드가 전략별 성과를 `daily_performance.total_asset`(전략 row =
 * 배분예산(비중×순자산) + 당일 실현손익 합성값, `scheduler._settle` 산출)로 노출해
 * 체결 0건 전략(VCP/BFB)에도 자산이 잡히고 weight=0 비활성 전략(momentum)에 누적수익률이
 * 남는 오염된 신호를 줬다. `strategy='total'` row(전체 탭)는 KIS 잔고 실측 net_asset 이라
 * 합성이 아니다 — 라벨 분기는 전체/전략 탭에 따라 달라야 한다.
 *
 * 시정: 전략 탭에서만 "(합성)" 라벨 + 경고 배너를 붙이고, `/api/strategies/te`
 * (완결 매매 기준 실현손익 · 승률 · sample_tier)를 병기해 운영자가 오염된 합성값이
 * 아니라 실현손익을 보게 한다.
 *
 * 요구 행위:
 * - PC-A: 로딩 상태
 * - PC-B: 에러 상태
 * - PC-C: 전체(all) 탭 — 라벨 불변(최근 자산/누적 수익률/일평균 수익률), 합성 배너 없음
 * - PC-D: 특정 전략 탭 — "(합성)" 라벨 + 합성 경고 배너
 * - PC-E: 전략 탭 실현 성과 — 손실(파랑) + 활성/비중 배지
 * - PC-F: sample_tier='insufficient' — 회색 뮤트 배지, pnl/승률 미노출
 * - PC-G: 전체 탭 — 전 전략 실현 성과 행 다건 표시
 * - PC-H: 실현 성과 API 에러 — graceful (합성 카드는 정상 렌더)
 * - PC-I: 실현 성과 빈 데이터 — 안내 문구
 */

import { describe, expect, it } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'

import PerformanceCard from '../PerformanceCard'
import { TestProviders } from '../../test/providers'
import { TradingStatusProvider } from '../../contexts/TradingStatusContext'
import { wrap } from '../../test/factories'
import { server } from '../../test/server'
import type { TeRrMetrics } from '../../types/strategy'

const summaryPayload = {
  total_days: 42,
  total_profit_rate: 3.21,
  avg_daily_profit_rate: 0.08,
  latest_asset: 10_720_000,
}

function makeTe(overrides: Partial<TeRrMetrics> = {}): TeRrMetrics {
  return {
    strategy_id: 'kojiro',
    n: 4,
    win: 0,
    loss: 4,
    even: 0,
    win_rate: 0,
    avg_win_pct: null,
    avg_loss_pct: -3.2,
    te_pct: -3.2,
    te_krw_avg: -12_000,
    realized_sum_krw: -48_000,
    rr: null,
    required_rr: null,
    rr_margin: null,
    rr_available: false,
    sample_tier: 'insufficient',
    verdict: 'undecided',
    structure_tag: null,
    single_trade_dominant: false,
    ...overrides,
  }
}

function mockTradingStatus(strategies: Record<string, Partial<Record<string, unknown>>>) {
  server.use(
    http.get('/api/trading/status', () =>
      HttpResponse.json(
        wrap({
          running: true,
          env: 'vts',
          positions: 0,
          pending_buys: 0,
          position_tickers: [],
          phase: 'main_trading',
          scan: {},
          positions_detail: {},
          orders: {},
          strategy: {},
          strategies,
        }),
      ),
    ),
  )
}

function renderCard(selectedStrategy: string) {
  return render(
    <TestProviders>
      <TradingStatusProvider>
        <PerformanceCard selectedStrategy={selectedStrategy} />
      </TradingStatusProvider>
    </TestProviders>,
  )
}

describe('PerformanceCard', () => {
  it('PC-A: 로딩 상태', () => {
    server.use(http.get('/api/performance/summary', () => new Promise(() => {})))
    renderCard('all')
    expect(screen.getByText('실적 로딩 중...')).toBeTruthy()
  })

  it('PC-B: 에러 상태', async () => {
    server.use(http.get('/api/performance/summary', () => new HttpResponse(null, { status: 500 })))
    renderCard('all')
    // retry:1 이라 에러 확정까지 재시도 지연(~1s) 발생 — 타임아웃 여유.
    await screen.findByText('실적 데이터를 불러올 수 없습니다.', {}, { timeout: 3000 })
  })

  it('PC-C: 전체 탭 — 라벨 불변 + 합성 배너 없음', async () => {
    server.use(http.get('/api/performance/summary', () => HttpResponse.json(wrap(summaryPayload))))
    server.use(http.get('/api/strategies/te', () => HttpResponse.json(wrap([]))))
    mockTradingStatus({})
    renderCard('all')

    await waitFor(() => {
      expect(screen.getByTestId('performance-metric-latest-asset').textContent).toContain('10,720,000')
    })
    expect(screen.getByText('최근 자산')).toBeTruthy()
    expect(screen.getByText('누적 수익률')).toBeTruthy()
    expect(screen.getByText('일평균 수익률')).toBeTruthy()
    expect(screen.queryByText(/배분 예산\(합성\)/)).toBeNull()
    expect(screen.queryByTestId('performance-synthetic-banner')).toBeNull()
  })

  it('PC-D: 특정 전략 탭 — "(합성)" 라벨 + 경고 배너', async () => {
    server.use(http.get('/api/performance/summary', () => HttpResponse.json(wrap(summaryPayload))))
    server.use(http.get('/api/strategies/te', () => HttpResponse.json(wrap([]))))
    mockTradingStatus({})
    renderCard('kojiro')

    await waitFor(() => {
      expect(screen.getByText('배분 예산(합성)')).toBeTruthy()
    })
    expect(screen.getByText('누적 수익률(합성)')).toBeTruthy()
    expect(screen.getByText('일평균 수익률(합성)')).toBeTruthy()
    expect(screen.queryByText('최근 자산')).toBeNull()
    const banner = screen.getByTestId('performance-synthetic-banner')
    expect(banner.textContent).toContain('합성값')
    expect(banner.textContent).toContain('실현 성과')
  })

  it('PC-E: 전략 탭 실현 성과 — 손실(파랑) + 활성/비중 배지', async () => {
    server.use(http.get('/api/performance/summary', () => HttpResponse.json(wrap(summaryPayload))))
    server.use(
      http.get('/api/strategies/te', () =>
        HttpResponse.json(
          wrap([
            makeTe({
              strategy_id: 'kojiro',
              n: 30,
              win: 10,
              loss: 20,
              win_rate: 0.33,
              realized_sum_krw: -120_000,
              sample_tier: 'normal',
            }),
          ]),
        ),
      ),
    )
    mockTradingStatus({
      kojiro: { name: '고지로 대순환', enabled: true, weight: 0.6 },
    })
    renderCard('kojiro')

    const pnl = await screen.findByTestId('realized-pnl-kojiro')
    expect(pnl.textContent).toContain('120,000')
    expect(pnl.className).toContain('pnl-loss') // 손실 = 파랑 (cycle261 — text-pnl-loss 시맨틱 클래스)
    expect(screen.getByTestId('realized-winrate-kojiro').textContent).toContain('33%')
    const badge = screen.getByTestId('strategy-status-badge-kojiro')
    expect(badge.textContent).toContain('활성')
    expect(badge.textContent).toContain('60%')
  })

  it('PC-F: sample_tier=insufficient — 회색 뮤트 배지, pnl/승률 미노출', async () => {
    server.use(http.get('/api/performance/summary', () => HttpResponse.json(wrap(summaryPayload))))
    server.use(
      http.get('/api/strategies/te', () =>
        HttpResponse.json(wrap([makeTe({ strategy_id: 'vcp_breakout', n: 0, win: 0, loss: 0 })])),
      ),
    )
    mockTradingStatus({
      vcp_breakout: { name: 'VCP 변동성 수축', enabled: true, weight: 0.1 },
    })
    renderCard('vcp_breakout')

    const badge = await screen.findByTestId('realized-insufficient-badge-vcp_breakout')
    expect(badge.textContent).toContain('체결 0건')
    expect(badge.textContent).toContain('미확정')
    expect(screen.queryByTestId('realized-pnl-vcp_breakout')).toBeNull()
    expect(screen.queryByTestId('realized-winrate-vcp_breakout')).toBeNull()
  })

  it('PC-G: 전체 탭 — 전 전략 실현 성과 행 다건 표시', async () => {
    server.use(http.get('/api/performance/summary', () => HttpResponse.json(wrap(summaryPayload))))
    server.use(
      http.get('/api/strategies/te', () =>
        HttpResponse.json(
          wrap([
            makeTe({ strategy_id: 'momentum', n: 0, win: 0, loss: 0 }),
            makeTe({
              strategy_id: 'kojiro',
              n: 30,
              win: 10,
              loss: 20,
              win_rate: 0.33,
              realized_sum_krw: -120_000,
              sample_tier: 'normal',
            }),
          ]),
        ),
      ),
    )
    mockTradingStatus({
      momentum: { name: '상한가 모멘텀', enabled: false, weight: 0 },
      kojiro: { name: '고지로 대순환', enabled: true, weight: 0.6 },
    })
    renderCard('all')

    await screen.findByTestId('realized-row-momentum')
    expect(screen.getByTestId('realized-row-kojiro')).toBeTruthy()
    const momentumBadge = screen.getByTestId('strategy-status-badge-momentum')
    expect(momentumBadge.textContent).toContain('비활성')
    expect(momentumBadge.textContent).toContain('0%')
  })

  it('PC-H: 실현 성과 API 에러 — graceful (합성 카드는 정상 렌더)', async () => {
    server.use(http.get('/api/performance/summary', () => HttpResponse.json(wrap(summaryPayload))))
    server.use(http.get('/api/strategies/te', () => new HttpResponse(null, { status: 500 })))
    mockTradingStatus({})
    renderCard('kojiro')

    await waitFor(() => {
      expect(screen.getByTestId('performance-metric-latest-asset')).toBeTruthy()
    })
    // strategy-te 쿼리는 retry:1 이라 에러 확정까지 재시도 지연(~1s) 발생 — 타임아웃 여유.
    await screen.findByTestId('realized-performance-error', {}, { timeout: 3000 })
  })

  it('PC-I: 실현 성과 빈 데이터 — 안내 문구', async () => {
    server.use(http.get('/api/performance/summary', () => HttpResponse.json(wrap(summaryPayload))))
    server.use(http.get('/api/strategies/te', () => HttpResponse.json(wrap([]))))
    mockTradingStatus({})
    renderCard('kojiro')

    await screen.findByTestId('realized-performance-empty')
  })
})
