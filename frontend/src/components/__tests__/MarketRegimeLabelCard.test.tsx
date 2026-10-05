/**
 * cycle410 — 6장세 라벨 카드(관찰 전용). 사용자 결정 10-05 「UI에도 표시해줘」 — 장세 라벨만.
 *
 * - C1: 오늘 장세 한글(6종) + 근거 두 값(60일선 20일 기울기 · 20일 변동성) + 시작일 + 기준 봉
 * - C2: 최근 60거래일 색 띠 — 칸마다 날짜·장세 툴팁
 * - C3: 「관찰용 — 매매에 쓰지 않습니다」 주석
 * - C4: since_truncated 면 시작일을 하한(「이전부터」)으로 표기
 * - C5: success=false 면 서버 사유를 그대로 보인다 · 네트워크 오류는 폴백 문구
 * - C6: 한글 이름 6종이 서로 다르고 백엔드 라벨 키 6종을 전부 덮는다
 * - U1: 시장 유닛 — 오늘 배수(×0.75) + 근거(종가 60일선 위/아래 · 60일선 상승/하락) + 기준 봉
 * - U2: 두 칸을 문구로 구분 — 장세 「관찰용」 / 시장 유닛 「실제 매수 수량에 쓰임 — enforce 인 전략만」
 * - U3: 전략별 모드(적용/기록만/꺼짐/모름) — enforce 0개면 「지금 적용 중인 전략 없음」
 * - U4: 띠 두 줄 — 장세 색 띠 + m 값 띠(칸 title = 날짜 + ×m, m=null 이면 —)
 */
import { describe, expect, it } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'

import MarketRegimeLabelCard from '../MarketRegimeLabelCard'
import { REGIME_LABEL_KO, formatUnitM } from '../../utils/marketRegimeLabel'
import { MARKET_REGIME_LABEL_FIXTURE } from '../../test/fixtures/marketRegimeLabel.fixture'
import { TestProviders } from '../../test/providers'
import { wrap, failed } from '../../test/factories'
import { server } from '../../test/server'

function renderCard() {
  return render(
    <TestProviders>
      <MarketRegimeLabelCard />
    </TestProviders>,
  )
}

describe('MarketRegimeLabelCard', () => {
  it('C1 — 오늘 장세·근거 두 값·시작일·기준 봉', async () => {
    renderCard()
    const badge = await screen.findByTestId('regime-label-badge')
    expect(badge).toHaveTextContent('변동하락')
    expect(screen.getByText('60일선 20일 기울기 -7.5%')).toBeInTheDocument()
    expect(screen.getByText('20일 변동성 32%')).toBeInTheDocument()
    expect(screen.getByTestId('regime-label-since')).toHaveTextContent('2026-08-24부터')
    expect(screen.getByTestId('regime-label-basis')).toHaveTextContent('2026-10-02')
  })

  it('C1 — 양의 기울기는 + 부호를 붙인다', async () => {
    server.use(
      http.get('/api/market-regime-label', () =>
        HttpResponse.json(
          wrap({
            ...MARKET_REGIME_LABEL_FIXTURE,
            today: { ...MARKET_REGIME_LABEL_FIXTURE.today, label: 'stable_up', direction: 'up', volatility: 'stable', slope_pct: 3.24, vol_pct: 15.6 },
          }),
        ),
      ),
    )
    renderCard()
    expect(await screen.findByTestId('regime-label-badge')).toHaveTextContent('안정상승')
    expect(screen.getByText('60일선 20일 기울기 +3.2%')).toBeInTheDocument()
    expect(screen.getByText('20일 변동성 16%')).toBeInTheDocument()
  })

  it('C2 — 최근 60거래일 색 띠, 칸마다 날짜·장세', async () => {
    renderCard()
    const band = await screen.findByTestId('regime-label-band')
    const cells = within(band).getAllByTestId('regime-label-band-cell')
    expect(cells).toHaveLength(60)
    expect(cells[0]).toHaveAttribute('title', '2026-07-08 변동상승')
    expect(cells[59]).toHaveAttribute('title', '2026-10-05 변동하락')
  })

  it('C3 — 관찰용 주석', async () => {
    renderCard()
    expect(await screen.findByText('관찰용 — 매매에 쓰지 않습니다')).toBeInTheDocument()
  })

  it('C4 — since_truncated 면 「이전부터」', async () => {
    server.use(
      http.get('/api/market-regime-label', () =>
        HttpResponse.json(wrap({ ...MARKET_REGIME_LABEL_FIXTURE, since: '2025-06-10', since_truncated: true })),
      ),
    )
    renderCard()
    expect(await screen.findByTestId('regime-label-since')).toHaveTextContent('2025-06-10 이전부터')
  })

  it('C5 — success=false 는 서버 사유를 보인다', async () => {
    server.use(
      http.get('/api/market-regime-label', () =>
        HttpResponse.json(failed('069500 일봉이 12행뿐이라 장세를 매길 수 없다(필요 80행)')),
      ),
    )
    renderCard()
    expect(
      await screen.findByText('069500 일봉이 12행뿐이라 장세를 매길 수 없다(필요 80행)'),
    ).toBeInTheDocument()
    expect(screen.queryByTestId('regime-label-badge')).not.toBeInTheDocument()
  })

  it('C5 — 네트워크 오류는 폴백 문구', async () => {
    server.use(http.get('/api/market-regime-label', () => HttpResponse.error()))
    renderCard()
    expect(await screen.findByText('장세 라벨을 불러오지 못했습니다.')).toBeInTheDocument()
  })

  it('C6 — 한글 이름 6종', () => {
    expect(REGIME_LABEL_KO).toEqual({
      stable_up: '안정상승',
      volatile_up: '변동상승',
      stable_flat: '안정횡보',
      volatile_flat: '변동횡보',
      stable_down: '안정하락',
      volatile_down: '변동하락',
    })
  })

  it('U1 — 시장 유닛 배수와 근거', async () => {
    renderCard()
    expect(await screen.findByTestId('regime-unit-m')).toHaveTextContent('×0.75')
    expect(screen.getByText('종가 60일선 위')).toBeInTheDocument()
    expect(screen.getByText('60일선 하락')).toBeInTheDocument()
    expect(screen.getByTestId('regime-unit-basis')).toHaveTextContent('2026-10-02')
    // 엔진 메모리 값이 아니라 운영 DB 종가로 다시 계산한 값임을 밝힌다
    expect(screen.getByTestId('regime-unit-source')).toHaveTextContent('운영 DB 종가로 다시 계산')
  })

  it('U1 — 아래·상승 근거 문구', async () => {
    server.use(
      http.get('/api/market-regime-label', () =>
        HttpResponse.json(
          wrap({
            ...MARKET_REGIME_LABEL_FIXTURE,
            market_unit: { ...MARKET_REGIME_LABEL_FIXTURE.market_unit, m: 0.5, state: 'down_rising', above_sma60: false, sma60_rising: true },
          }),
        ),
      ),
    )
    renderCard()
    expect(await screen.findByTestId('regime-unit-m')).toHaveTextContent('×0.5')
    expect(screen.getByText('종가 60일선 아래')).toBeInTheDocument()
    expect(screen.getByText('60일선 상승')).toBeInTheDocument()
  })

  it('U2 — 두 칸을 문구로 구분', async () => {
    renderCard()
    expect(await screen.findByText('관찰용 — 매매에 쓰지 않습니다')).toBeInTheDocument()
    expect(screen.getByText('실제 매수 수량에 쓰임 — enforce 인 전략만')).toBeInTheDocument()
  })

  it('U3 — 전략별 모드, 적용 0개 안내', async () => {
    renderCard()
    const modes = await screen.findByTestId('regime-unit-modes')
    expect(within(modes).getByTestId('regime-unit-mode-kojiro')).toHaveTextContent('고지로 대순환 기록만')
    expect(screen.getByText('지금 적용 중인 전략 없음')).toBeInTheDocument()
  })

  it('U3 — enforce·off·모름 표기', async () => {
    server.use(
      http.get('/api/market-regime-label', () =>
        HttpResponse.json(
          wrap({
            ...MARKET_REGIME_LABEL_FIXTURE,
            market_unit: {
              ...MARKET_REGIME_LABEL_FIXTURE.market_unit,
              modes: { kojiro: 'enforce', donchian_swing: 'off', vcp_breakout: null },
            },
          }),
        ),
      ),
    )
    renderCard()
    expect(await screen.findByTestId('regime-unit-mode-kojiro')).toHaveTextContent('고지로 대순환 적용')
    expect(screen.getByTestId('regime-unit-mode-donchian_swing')).toHaveTextContent('꺼짐')
    expect(screen.getByTestId('regime-unit-mode-vcp_breakout')).toHaveTextContent('모름')
    expect(screen.queryByText('지금 적용 중인 전략 없음')).not.toBeInTheDocument()
  })

  it('U4 — m 값 띠', async () => {
    const hist = MARKET_REGIME_LABEL_FIXTURE.history.map((h, i) => (i === 0 ? { ...h, m: null } : h))
    server.use(
      http.get('/api/market-regime-label', () =>
        HttpResponse.json(wrap({ ...MARKET_REGIME_LABEL_FIXTURE, history: hist })),
      ),
    )
    renderCard()
    const band = await screen.findByTestId('regime-unit-band')
    const cells = within(band).getAllByTestId('regime-unit-band-cell')
    expect(cells).toHaveLength(60)
    expect(cells[0]).toHaveAttribute('title', '2026-07-08 —')
    expect(cells[59]).toHaveAttribute('title', '2026-10-05 ×0.75')
  })

  it('U4 — 배수 표기', () => {
    expect([1, 0.75, 0.5, 0, null].map(formatUnitM)).toEqual(['×1', '×0.75', '×0.5', '×0', '—'])
  })
})
