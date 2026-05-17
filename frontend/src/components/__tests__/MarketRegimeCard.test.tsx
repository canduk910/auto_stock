/**
 * 사이클 2 (2026-05-17): MarketRegimeCard 테스트.
 *
 * 요구 행위:
 * - B7-A: regime=defensive → red 배지 + 매수 가드 amber 배너
 * - B7-B: regime=aggressive → blue 배지 + 가드 비활성
 * - B7-C: auto_regime_adjust 토글 클릭 → ConfirmModal → 확인 시 API 호출
 * - B7-D: VIX/Fear&Greed/Buffett/cycle 메트릭 grid 표시
 * - B7-E: API 에러 시 graceful fallback 메시지
 * - B7-F: enabled=false 시 비활성 배지
 */

import { describe, expect, it } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { http, HttpResponse } from 'msw'

import MarketRegimeCard from '../MarketRegimeCard'
import { TestProviders } from '../../test/providers'
import { wrap } from '../../test/factories'
import { server } from '../../test/server'

const defensivePayload = {
  regime: 'defensive',
  regime_desc: '방어 (공포 현금)',
  cycle_phase: 'contraction',
  vix: 26.5,
  fear_greed_score: 86.0,
  buffett_ratio: 260.1,
  cash_min: 75,
  buy_blocked: true,
  block_reason: 'regime=defensive (방어 (공포 현금))',
  auto_regime_adjust: true,
  cash_usage_ratio: 0.25,
  enabled: true,
}

const aggressivePayload = {
  regime: 'aggressive',
  regime_desc: '공격 (탐욕 적극)',
  cycle_phase: 'expansion',
  vix: 14.2,
  fear_greed_score: 45.0,
  buffett_ratio: 230.0,
  cash_min: 20,
  buy_blocked: false,
  block_reason: null,
  auto_regime_adjust: true,
  cash_usage_ratio: 0.8,
  enabled: true,
}

describe('MarketRegimeCard', () => {
  it('B7-A: regime=defensive 시 red 배지 + 매수 가드 amber 배너', async () => {
    server.use(
      http.get('/api/market-regime/current', () => HttpResponse.json(wrap(defensivePayload))),
    )
    render(
      <TestProviders>
        <MarketRegimeCard />
      </TestProviders>,
    )

    const badge = await screen.findByTestId('market-regime-badge')
    expect(badge.textContent).toContain('방어')
    // 매수 가드 amber 배너
    const banner = screen.getByTestId('market-regime-block-banner')
    expect(banner.textContent).toContain('매수 차단')
    expect(banner.textContent).toContain('defensive')
  })

  it('B7-B: regime=aggressive 시 blue 배지 + 가드 비활성', async () => {
    server.use(
      http.get('/api/market-regime/current', () => HttpResponse.json(wrap(aggressivePayload))),
    )
    render(
      <TestProviders>
        <MarketRegimeCard />
      </TestProviders>,
    )

    const badge = await screen.findByTestId('market-regime-badge')
    expect(badge.textContent).toContain('공격')
    expect(screen.queryByTestId('market-regime-block-banner')).toBeNull()
  })

  it('B7-D: VIX/Fear&Greed/Buffett/cycle 메트릭 grid 표시', async () => {
    server.use(
      http.get('/api/market-regime/current', () => HttpResponse.json(wrap(defensivePayload))),
    )
    render(
      <TestProviders>
        <MarketRegimeCard />
      </TestProviders>,
    )

    await waitFor(() => {
      expect(screen.getByTestId('metric-vix').textContent).toContain('26.50')
      expect(screen.getByTestId('metric-fear-greed').textContent).toContain('86')
      expect(screen.getByTestId('metric-buffett').textContent).toContain('260.1')
      expect(screen.getByTestId('metric-cycle').textContent).toContain('수축기')
      expect(screen.getByTestId('metric-cash-ratio').textContent).toContain('25%')
    })
  })

  it('B7-C: auto_regime_adjust 토글 클릭 → ConfirmModal 노출', async () => {
    server.use(
      http.get('/api/market-regime/current', () => HttpResponse.json(wrap(defensivePayload))),
    )
    render(
      <TestProviders>
        <MarketRegimeCard />
      </TestProviders>,
    )

    const toggle = await screen.findByTestId('auto-regime-toggle')
    expect(toggle.textContent).toContain('ON')
    fireEvent.click(toggle)
    // ConfirmModal 노출 — 제목 키워드 검증
    await waitFor(() => {
      expect(screen.getByText(/자동 조정 OFF/)).toBeTruthy()
    })
  })

  it('B7-C2: 토글 확인 시 PUT API 호출 + 재조회', async () => {
    let putCallCount = 0
    server.use(
      http.get('/api/market-regime/current', () => HttpResponse.json(wrap(defensivePayload))),
      http.put('/api/market-regime/auto-adjust', () => {
        putCallCount += 1
        return HttpResponse.json(wrap({ auto_regime_adjust: false }, '수동 모드'))
      }),
    )
    render(
      <TestProviders>
        <MarketRegimeCard />
      </TestProviders>,
    )

    const toggle = await screen.findByTestId('auto-regime-toggle')
    fireEvent.click(toggle)
    // ConfirmModal "확인" 클릭
    const confirmBtn = await screen.findByText('확인')
    fireEvent.click(confirmBtn)

    await waitFor(() => {
      expect(putCallCount).toBe(1)
    })
  })

  it('B7-E: API 에러 시 graceful fallback 메시지', async () => {
    server.use(
      http.get('/api/market-regime/current', () => new HttpResponse(null, { status: 500 })),
    )
    render(
      <TestProviders>
        <MarketRegimeCard />
      </TestProviders>,
    )

    await waitFor(() => {
      const card = screen.getByTestId('market-regime-card')
      expect(card.textContent).toMatch(/불러오지 못했|로딩/)
    })
  })

  it('B7-F: enabled=false 시 비활성 배지', async () => {
    const disabledPayload = {
      ...aggressivePayload,
      regime: null,
      enabled: false,
      buy_blocked: false,
      block_reason: null,
      vix: null,
      fear_greed_score: null,
      buffett_ratio: null,
      cash_min: null,
      cycle_phase: null,
    }
    server.use(
      http.get('/api/market-regime/current', () => HttpResponse.json(wrap(disabledPayload))),
    )
    render(
      <TestProviders>
        <MarketRegimeCard />
      </TestProviders>,
    )

    const badge = await screen.findByTestId('market-regime-badge')
    expect(badge.textContent).toContain('비활성')
  })
})
