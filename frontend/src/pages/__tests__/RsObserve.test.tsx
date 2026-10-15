/**
 * RS·재무 관찰 페이지(`pages/RsObserve.tsx`, 전략 메뉴 세 번째 세부).
 *
 * - P1: 관찰 전용 띠 · 날짜 · 전략별 구역(4전략) · 행 정렬(보유 먼저)
 * - P2: 모름(null) 칸은 — · 0 이 아니다 · 값 칸은 단위대로
 * - P3: 전략 버튼 = 그 전략 구역만 · 기록 없는 전략은 「기록이 없습니다」
 * - P4: 날짜를 바꾸면 그 날짜로 다시 묻는다
 * - P5: 기록 0 = 빈 안내 · success=false = 서버 사유 그대로 · 네트워크 오류 = 오류 문장
 */
import { describe, expect, it } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'

import RsObserve from '../RsObserve'
import { RS_OBSERVE_FIXTURE } from '../../test/fixtures/rsObserve.fixture'
import { TestProviders } from '../../test/providers'
import { failed, wrap } from '../../test/factories'
import { server } from '../../test/server'

function renderPage() {
  return render(
    <TestProviders>
      <RsObserve />
    </TestProviders>,
  )
}

const cell = (row: HTMLElement, key: string) => row.querySelector(`[data-key="${key}"]`) as HTMLElement

describe('RsObserve', () => {
  it('P1 — 띠 · 날짜 · 전략 구역 · 보유 먼저', async () => {
    renderPage()
    expect(await screen.findByTestId('rs-observe-date')).toHaveValue(RS_OBSERVE_FIXTURE.target_date)
    expect(screen.getByTestId('rs-observe-banner')).toHaveTextContent('관찰 전용 — 매매에 쓰이지 않습니다')
    expect(screen.getByTestId('rs-observe-banner')).toHaveTextContent('2027-04')
    for (const sid of RS_OBSERVE_FIXTURE.strategies) {
      expect(screen.getByTestId(`rs-observe-section-${sid}`)).toBeInTheDocument()
    }
    const rows = within(screen.getByTestId('rs-observe-table-donchian_swing')).getAllByTestId(/^rs-observe-row-/)
    expect(rows[0]).toHaveAttribute('data-testid', 'rs-observe-row-donchian_swing-005930') // 보유
    expect(rows[0]).toHaveTextContent('보유')
    expect(screen.getByTestId('rs-observe-summary-donchian_swing')).toHaveTextContent('후보 1 · 보유 1')
    expect(screen.getByTestId('rs-observe-summary-donchian_swing')).toHaveTextContent('2,390')
  })

  it('P2 — 모름은 —, 값은 단위대로', async () => {
    renderPage()
    const kakao = await screen.findByTestId('rs-observe-row-donchian_swing-035720')
    expect(cell(kakao, 'roe')).toHaveTextContent('—')
    expect(cell(kakao, 'in_sector_pct')).toHaveTextContent('—')
    expect(cell(kakao, 'op_yoy_growth')).toHaveTextContent('—')
    expect(cell(kakao, 'op_turnaround')).toHaveTextContent('예')
    expect(cell(kakao, 'rs_raw')).toHaveTextContent('-5.1%')
    expect(cell(kakao, 'debt_ratio_latest')).toHaveTextContent('88%')
    expect(cell(kakao, 'fin_quarter')).toHaveTextContent('2026년 6월')
    const etf = screen.getByTestId('rs-observe-row-etf_trend-069500')
    expect(cell(etf, 'rs_pct')).toHaveTextContent('64')
    for (const k of ['revision_breadth', 'opinion_brokers', 'fin_quarter', 'roe', 'op_turnaround']) {
      expect(cell(etf, k)).toHaveTextContent('—')
    }
    expect(screen.getByTestId('rs-observe-etf-note')).toBeInTheDocument()
  })

  it('P3 — 전략 버튼은 그 구역만, 기록 없는 전략은 안내', async () => {
    renderPage()
    fireEvent.click(await screen.findByTestId('rs-observe-strategy-kojiro'))
    expect(screen.getByTestId('rs-observe-strategy-kojiro')).toHaveAttribute('aria-pressed', 'true')
    expect(screen.queryByTestId('rs-observe-section-donchian_swing')).toBeNull()
    expect(screen.getByTestId('rs-observe-section-empty-kojiro')).toHaveTextContent('기록이 없습니다')
    fireEvent.click(screen.getByTestId('rs-observe-strategy-all'))
    expect(screen.getByTestId('rs-observe-section-donchian_swing')).toBeInTheDocument()
  })

  it('P4 — 날짜를 바꾸면 그 날짜로 다시 묻는다', async () => {
    const asked: (string | null)[] = []
    server.use(
      http.get('*/api/rs-observe', ({ request }) => {
        const d = new URL(request.url).searchParams.get('date')
        asked.push(d)
        if (d === '2026-10-14') {
          return HttpResponse.json(
            wrap({ ...RS_OBSERVE_FIXTURE, target_date: '2026-10-14', rows: RS_OBSERVE_FIXTURE.rows.slice(0, 0) }),
          )
        }
        return HttpResponse.json(wrap(RS_OBSERVE_FIXTURE))
      }),
    )
    renderPage()
    fireEvent.change(await screen.findByTestId('rs-observe-date'), { target: { value: '2026-10-14' } })
    await waitFor(() => expect(asked).toContain('2026-10-14'))
    expect(asked[0]).toBeNull()
    expect(await screen.findByTestId('rs-observe-section-empty-donchian_swing')).toBeInTheDocument()
  })

  it('P5 — 기록 0 · success=false · 네트워크 오류', async () => {
    server.use(
      http.get('*/api/rs-observe', () =>
        HttpResponse.json(wrap({ target_date: null, dates: [], strategies: RS_OBSERVE_FIXTURE.strategies, rows: [] })),
      ),
    )
    const { unmount } = renderPage()
    expect(await screen.findByTestId('rs-observe-empty')).toHaveTextContent('아직 기록이 없습니다')
    unmount()
    server.use(http.get('*/api/rs-observe', () => HttpResponse.json(failed('RS·재무 관찰 기록 조회 실패: RuntimeError'))))
    const r2 = renderPage()
    expect(await screen.findByTestId('rs-observe-failed')).toHaveTextContent('조회 실패: RuntimeError')
    r2.unmount()
    server.use(http.get('*/api/rs-observe', () => HttpResponse.error()))
    renderPage()
    expect(await screen.findByTestId('rs-observe-error', {}, { timeout: 5000 })).toBeInTheDocument()
  })
})
