/**
 * cycle456 — 시장 유닛 결정 과정 카드(읽기 전용).
 *
 * - V1: 코스피 탭 기본 — 오늘 배수 · 3단계(위치·기울기·4칸 표) · 현재 칸 강조
 * - V2: 코스닥 탭으로 바꾸면 그 시장 값으로 다시 그린다
 * - V3: 엔진 미계산(`not_computed`) = 「엔진이 아직 계산하지 않았습니다」, 다른 시장 대체·둘 다 결측 문구
 * - V4: 판정 불가 스냅샷 = 사유 + 「배수를 줄이지 않습니다」
 * - V5: 봉 0개 = 「지수 일봉이 아직 적재되지 않았습니다」 · success=false = 서버 사유 그대로
 * - V6: 전략별 모드 칩(적용/기록만/모름)
 */
import { describe, expect, it } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'

import MarketUnitChartCard from '../MarketUnitChartCard'
import { MARKET_UNIT_CHART_FIXTURE } from '../../test/fixtures/marketUnitChart.fixture'
import type { MarketUnitChartData } from '../../types/market-unit-chart'
import { TestProviders } from '../../test/providers'
import { wrap, failed } from '../../test/factories'
import { server } from '../../test/server'

function renderCard() {
  return render(
    <TestProviders>
      <MarketUnitChartCard />
    </TestProviders>,
  )
}

function useData(d: MarketUnitChartData) {
  server.use(http.get('*/api/market-unit/chart', () => HttpResponse.json(wrap(d))))
}

const clone = (): MarketUnitChartData => JSON.parse(JSON.stringify(MARKET_UNIT_CHART_FIXTURE))

describe('MarketUnitChartCard', () => {
  it('V1 — 코스피 기본: 배수 · 3단계 · 현재 칸 강조', async () => {
    renderCard()
    const kospi = MARKET_UNIT_CHART_FIXTURE.markets.kospi
    expect(await screen.findByTestId('mu-chart-today-m')).toHaveTextContent(`×${kospi.effective.m}`)
    expect(screen.getByTestId('mu-chart-tab-kospi')).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByTestId('mu-chart-step-position')).toHaveTextContent(
      kospi.decision!.above ? '60일선 위' : '60일선 아래',
    )
    expect(screen.getByTestId('mu-chart-step-slope')).toHaveTextContent(kospi.decision!.rising ? '상승' : '하락')
    expect(screen.getByTestId(`mu-chart-state-${kospi.decision!.state}`)).toHaveAttribute('data-active', 'true')
    expect(screen.getByTestId('mu-chart-source')).toHaveTextContent('엔진 메모리 값')
    expect(screen.getByTestId('mu-chart-price')).toHaveAttribute('data-bars', String(kospi.bars.length))
  })

  it('V2 — 코스닥 탭', async () => {
    renderCard()
    fireEvent.click(await screen.findByTestId('mu-chart-tab-kosdaq'))
    const q = MARKET_UNIT_CHART_FIXTURE.markets.kosdaq
    expect(screen.getByTestId('mu-chart-tab-kosdaq')).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByTestId('mu-chart-today-m')).toHaveTextContent(`×${q.effective.m}`)
    expect(screen.getByTestId(`mu-chart-state-${q.decision!.state}`)).toHaveAttribute('data-active', 'true')
  })

  it('V3 — 엔진 미계산 · 다른 시장 대체 · 둘 다 결측', async () => {
    const d = clone()
    d.markets.kospi.engine = null
    d.markets.kospi.effective = { m: null, fallback: 'not_computed', from_market: null }
    d.markets.kosdaq.effective = { m: 1, fallback: 'other_market', from_market: 'kospi' }
    useData(d)
    renderCard()
    expect(await screen.findByTestId('mu-chart-source')).toHaveTextContent('엔진이 아직 계산하지 않았습니다')
    expect(screen.getByTestId('mu-chart-today-m')).toHaveTextContent(`×${d.markets.kospi.decision!.m}`)
    fireEvent.click(screen.getByTestId('mu-chart-tab-kosdaq'))
    expect(screen.getByTestId('mu-chart-source')).toHaveTextContent('코스피 배수를 대신 씁니다')
  })

  it('V3b — 두 시장 모두 판정 불가 문구', async () => {
    const d = clone()
    d.markets.kospi.effective = { m: 1, fallback: 'none', from_market: null }
    useData(d)
    renderCard()
    expect(await screen.findByTestId('mu-chart-source')).toHaveTextContent('두 시장 모두 판정 불가')
  })

  it('V4 — 판정 불가 스냅샷은 사유와 ×1 안내', async () => {
    const d = clone()
    d.markets.kospi.decision = { ...d.markets.kospi.decision!, ok: false, state: 'unavailable', m: 1, reason: 'stale_head' }
    useData(d)
    renderCard()
    const el = await screen.findByTestId('mu-chart-steps-unavailable')
    expect(el).toHaveTextContent('직전 영업일 봉 없음')
    expect(el).toHaveTextContent('배수를 줄이지 않습니다')
  })

  it('V5 — 봉 0개 · success=false', async () => {
    const d = clone()
    d.markets.kospi.bars = []
    useData(d)
    const { unmount } = renderCard()
    expect(await screen.findByTestId('mu-chart-empty')).toHaveTextContent('지수 일봉이 아직 적재되지 않았습니다')
    unmount()
    server.use(http.get('*/api/market-unit/chart', () => HttpResponse.json(failed('지수 조회 실패'))))
    renderCard()
    expect(await screen.findByText('지수 조회 실패')).toBeInTheDocument()
  })

  it('V6 — 전략별 모드 칩', async () => {
    const d = clone()
    d.modes = { kojiro: 'enforce', donchian_swing: 'shadow', vcp_breakout: null }
    useData(d)
    renderCard()
    expect(await screen.findByTestId('mu-chart-mode-kojiro')).toHaveTextContent('적용')
    expect(screen.getByTestId('mu-chart-mode-donchian_swing')).toHaveTextContent('기록만')
    expect(screen.getByTestId('mu-chart-mode-vcp_breakout')).toHaveTextContent('모름')
  })
})
