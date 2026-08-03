/**
 * 사이클 I (2026-08-03): PortfolioRiskCard 테스트.
 *
 * `MarketRegimeCard.test.tsx` 템플릿 복제. 관찰 전용 카드 — 매수 배제 없음(Phase 1).
 *
 * 요구 행위:
 * - PR-A: 정상 렌더 — 요약 4지표 + 섹터별 리스크 막대
 * - PR-B: top_sector.risk_share_pct >= 40 → 섹터 집중 경고 배너
 * - PR-C: top_sector.risk_share_pct < 40 → 경고 배너 미노출
 * - PR-D: API 500 에러 시 graceful fallback 메시지
 * - PR-E: 빈 스냅샷 (concurrent_positions=0 / top_sector=null) — 빈 상태 안내
 */

import { describe, expect, it } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'

import PortfolioRiskCard from '../PortfolioRiskCard'
import { TestProviders } from '../../test/providers'
import { wrap } from '../../test/factories'
import { server } from '../../test/server'

const normalPayload = {
  total_notional_won: 15_000_000,
  total_open_risk_won: 450_000,
  open_risk_pct_of_net: 3.5,
  concurrent_positions: 5,
  by_strategy: {
    momentum: { positions: 3, notional_won: 9_000_000, risk_won: 270_000 },
    donchian_swing: { positions: 2, notional_won: 6_000_000, risk_won: 180_000 },
  },
  by_sector: {
    반도체: { positions: 3, notional_won: 9_000_000, risk_won: 270_000 },
    '2차전지': { positions: 2, notional_won: 6_000_000, risk_won: 180_000 },
  },
  top_sector: { sector: '반도체', risk_won: 270_000, risk_share_pct: 25.0 },
}

const concentratedPayload = {
  ...normalPayload,
  top_sector: { sector: '반도체', risk_won: 400_000, risk_share_pct: 55.5 },
}

const emptyPayload = {
  total_notional_won: 0,
  total_open_risk_won: 0,
  open_risk_pct_of_net: 0,
  concurrent_positions: 0,
  by_strategy: {},
  by_sector: {},
  top_sector: null,
}

describe('PortfolioRiskCard', () => {
  it('PR-A: 정상 렌더 — 요약 4지표 + 섹터별 리스크 막대', async () => {
    server.use(
      http.get('/api/portfolio/risk', () => HttpResponse.json(wrap(normalPayload))),
    )
    render(
      <TestProviders>
        <PortfolioRiskCard />
      </TestProviders>,
    )

    await screen.findByTestId('portfolio-risk-card')

    await waitFor(() => {
      expect(screen.getByTestId('portfolio-risk-total-notional').textContent).toContain(
        '15,000,000',
      )
      expect(screen.getByTestId('portfolio-risk-open-risk').textContent).toContain('450,000')
      expect(screen.getByTestId('portfolio-risk-open-pct').textContent).toContain('3.50%')
      expect(screen.getByTestId('portfolio-risk-concurrent-positions').textContent).toContain(
        '5',
      )
    })

    // 섹터별 리스크 막대 — risk_won DESC 정렬 (반도체 먼저)
    const sectorBars = screen.getByTestId('portfolio-risk-sector-bars')
    expect(sectorBars).toBeTruthy()
    expect(screen.getByTestId('portfolio-risk-sector-row-반도체')).toBeTruthy()
    expect(screen.getByTestId('portfolio-risk-sector-row-2차전지')).toBeTruthy()

    // 전략별 리스크 표
    expect(screen.getByTestId('portfolio-risk-strategy-row-momentum')).toBeTruthy()
    expect(screen.getByTestId('portfolio-risk-strategy-row-donchian_swing')).toBeTruthy()

    // risk_share_pct=25 (< 40) → 경고 배너 없음
    expect(screen.queryByTestId('portfolio-risk-top-sector-banner')).toBeNull()
  })

  it('PR-B: top_sector.risk_share_pct >= 40 → 섹터 집중 경고 배너', async () => {
    server.use(
      http.get('/api/portfolio/risk', () => HttpResponse.json(wrap(concentratedPayload))),
    )
    render(
      <TestProviders>
        <PortfolioRiskCard />
      </TestProviders>,
    )

    const banner = await screen.findByTestId('portfolio-risk-top-sector-banner')
    expect(banner.textContent).toContain('섹터 집중 경고')
    expect(banner.textContent).toContain('반도체')
    expect(banner.textContent).toContain('55.5')
  })

  it('PR-D: API 500 에러 시 graceful fallback 메시지', async () => {
    server.use(
      http.get('/api/portfolio/risk', () => new HttpResponse(null, { status: 500 })),
    )
    render(
      <TestProviders>
        <PortfolioRiskCard />
      </TestProviders>,
    )

    await waitFor(() => {
      const card = screen.getByTestId('portfolio-risk-card')
      expect(card.textContent).toMatch(/불러오지 못했|로딩/)
    })
  })

  it('PR-E: 빈 스냅샷 (concurrent_positions=0 / top_sector=null) — 빈 상태 안내', async () => {
    server.use(
      http.get('/api/portfolio/risk', () => HttpResponse.json(wrap(emptyPayload))),
    )
    render(
      <TestProviders>
        <PortfolioRiskCard />
      </TestProviders>,
    )

    await waitFor(() => {
      expect(screen.getByTestId('portfolio-risk-concurrent-positions').textContent).toContain(
        '0',
      )
    })
    expect(screen.getByTestId('portfolio-risk-sector-empty')).toBeTruthy()
    expect(screen.getByTestId('portfolio-risk-strategy-empty')).toBeTruthy()
    expect(screen.queryByTestId('portfolio-risk-top-sector-banner')).toBeNull()
  })
})
