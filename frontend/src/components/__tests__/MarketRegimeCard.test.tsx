/**
 * 사이클 2 (2026-05-17): MarketRegimeCard 테스트.
 * 사이클 I (2026-08-03): 표시 정직화(buy_blocked 항상 false → 배너는 block_reason 기반
 * 관찰 라벨) + 지수ETF 레짐(관찰) 소섹션 추가.
 *
 * 요구 행위:
 * - B7-A: regime=defensive → red 배지 + 레짐 경보(관찰) amber 배너
 * - B7-B: regime=aggressive → blue 배지 + 배너 없음
 * - B7-C: auto_regime_adjust 토글 클릭 → ConfirmModal → 확인 시 API 호출
 * - B7-D: VIX/Fear&Greed/Buffett/cycle 메트릭 grid 표시
 * - B7-E: API 에러 시 graceful fallback 메시지
 * - B7-F: enabled=false 시 비활성 배지
 * - B7-G: 지수ETF 레짐(관찰) 소섹션 — stage/방어 여부 표시 + 비활성 라벨
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
  // 사이클 I — buy_blocked 는 이제 항상 false (레짐 매수 게이트 제거). block_reason 만
  // 관찰용 "레짐 경보 사유" 로 유지.
  buy_blocked: false,
  block_reason: 'regime=defensive (방어 (공포 현금))',
  auto_regime_adjust: true,
  cash_usage_ratio: 0.25,
  enabled: true,
  etf_kospi_stage: 4,
  etf_kosdaq_stage: 3,
  etf_defensive: true,
  etf_enabled: true,
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
  etf_kospi_stage: 1,
  etf_kosdaq_stage: 2,
  etf_defensive: false,
  etf_enabled: true,
}

describe('MarketRegimeCard', () => {
  it('B7-A: regime=defensive 시 red 배지 + 레짐 경보(관찰) amber 배너', async () => {
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
    // 레짐 경보(관찰) amber 배너 — "매수 차단" 문구 없이 관찰 사유만 (사이클 I 표시 정직화)
    const banner = screen.getByTestId('market-regime-block-banner')
    expect(banner.textContent).toContain('레짐 경보')
    expect(banner.textContent).not.toContain('매수 차단')
    expect(banner.textContent).toContain('defensive')
  })

  it('B7-A2: 자동 조정 OFF(라이브 상태) → 관찰 전용 배너 + 경보에 (권고·관찰) 표기', async () => {
    // 2026-08-07 라이브 = auto_regime_adjust=false, defensive 권고, cash 100% 수동.
    // 대시보드가 "방어/경보/현금75% 권고"와 "실제 cash 100%"를 화해시켜야 한다.
    server.use(
      http.get('/api/market-regime/current', () =>
        HttpResponse.json(wrap({ ...defensivePayload, auto_regime_adjust: false, cash_usage_ratio: 1.0 }))),
    )
    render(
      <TestProviders>
        <MarketRegimeCard />
      </TestProviders>,
    )

    const note = await screen.findByTestId('market-regime-observation-note')
    expect(note.textContent).toContain('관찰 전용')
    expect(note.textContent).toContain('100%')   // 실제 cash 수동
    const banner = screen.getByTestId('market-regime-block-banner')
    expect(banner.textContent).toContain('권고·관찰')
  })

  it('B7-A3: 자동 조정 ON 이면 관찰 전용 배너 미표시', async () => {
    server.use(
      http.get('/api/market-regime/current', () => HttpResponse.json(wrap(defensivePayload))),
    )
    render(
      <TestProviders>
        <MarketRegimeCard />
      </TestProviders>,
    )
    await screen.findByTestId('market-regime-badge')
    expect(screen.queryByTestId('market-regime-observation-note')).toBeNull()
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
      etf_kospi_stage: null,
      etf_kosdaq_stage: null,
      etf_defensive: null,
      etf_enabled: false,
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
    // 지수ETF 레짐 관찰 비활성 라벨 + null stage "-" 표시
    const etfDisabledLabel = await screen.findByTestId('etf-regime-disabled-label')
    expect(etfDisabledLabel.textContent).toContain('관찰 비활성')
    expect(screen.getByTestId('metric-etf-kospi-stage').textContent).toContain('-')
    expect(screen.getByTestId('metric-etf-kosdaq-stage').textContent).toContain('-')
    expect(screen.getByTestId('metric-etf-defensive').textContent).toContain('-')
  })

  it('B7-G: 지수ETF 레짐(관찰) 소섹션 — 코스피200/코스닥150 stage + 방어 여부 표시', async () => {
    server.use(
      http.get('/api/market-regime/current', () => HttpResponse.json(wrap(defensivePayload))),
    )
    render(
      <TestProviders>
        <MarketRegimeCard />
      </TestProviders>,
    )

    await waitFor(() => {
      expect(screen.getByTestId('metric-etf-kospi-stage').textContent).toContain('4')
      expect(screen.getByTestId('metric-etf-kosdaq-stage').textContent).toContain('3')
      expect(screen.getByTestId('metric-etf-defensive').textContent).toContain('방어')
    })
    // etf_enabled=true 이므로 "관찰 비활성" 라벨 미노출
    expect(screen.queryByTestId('etf-regime-disabled-label')).toBeNull()
  })
})
