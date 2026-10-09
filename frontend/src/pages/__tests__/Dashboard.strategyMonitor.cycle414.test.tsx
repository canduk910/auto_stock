/**
 * cycle414 Red — 대시보드 배선(MSW): 「전체」 탭 = 요약표, 전략 탭 = 상세 패널.
 *
 * 명세 = `_workspace/red/cycle414/monitor_spec.md` §2.1(배치) · §2.10(폴링) · §5 · §9(MSW 실제 키).
 * 사용자 선택(10-09) = 「대시보드에 요약 + 전략 화면에 상세」.
 *
 * 배치(전폭 위 / ScanMonitor 안)는 팀장 판단이라 이 파일은 **위치를 고정하지 않는다** — 대신 각 패널이
 * 페이지에 **정확히 한 번** 그려지는지만 본다(전폭 패널을 새로 두면서 ScanMonitor 안 KojiroMonitor 를 남겨
 * 두 번 그리는 결함을 막는다).
 *
 * 데이터 출처:
 *  - `GET /api/strategies/monitor` — 깔때기 단계 이름·수(라우트 값이 보이면 호출된 것)
 *  - `GET /api/balance/exit-lines` — 실효 손절선 정본(라우트 `effective_stop` 과 다른 값을 줘서 어느 쪽을 쓰는지 가른다)
 *  - `GET /api/strategy-funnel/recent?strategy_id=<sid>&days=14` — 14일 추이
 */
import { describe, expect, it } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'

import Dashboard from '../Dashboard'
import { TestProviders } from '../../test/providers'
import { TradingStatusProvider } from '../../contexts/TradingStatusContext'
import { wrap } from '../../test/factories'
import { server } from '../../test/server'
import {
  ETF_HELD, makeExitLines, makeFunnelRecent, makeMonitor, makeStatus,
} from '../../test/fixtures/strategyMonitor.fixture'

type Dict = Record<string, any> // eslint-disable-line @typescript-eslint/no-explicit-any

function setup(opts: { monitorFails?: boolean } = {}) {
  const recentCalls: string[] = []
  const exitLines = makeExitLines() as Dict
  exitLines.items[0].stop_price = 10_250 // 라우트 effective_stop(10,240)과 다르게 — 화면은 exit-lines 를 정본으로 쓴다
  server.use(
    http.get('/api/trading/status', () => HttpResponse.json(wrap(makeStatus()))),
    http.get('/api/strategies/monitor', () =>
      opts.monitorFails
        ? HttpResponse.json({ success: false, data: null, message: '모니터 조회 실패' })
        : HttpResponse.json(wrap(makeMonitor()))),
    http.get('/api/balance/exit-lines', () => HttpResponse.json(wrap(exitLines))),
    http.get('/api/strategy-funnel/recent', ({ request }) => {
      const u = new URL(request.url)
      recentCalls.push(`${u.searchParams.get('strategy_id')}|${u.searchParams.get('days')}`)
      return HttpResponse.json(wrap(makeFunnelRecent(u.searchParams.get('strategy_id') ?? '')))
    }),
  )
  render(
    <TestProviders>
      <TradingStatusProvider>
        <Dashboard />
      </TradingStatusProvider>
    </TestProviders>,
  )
  return { recentCalls }
}

/** 전략 탭 버튼(「ETF 추세(1)」) — 요약표에도 같은 이름이 있을 수 있어 DOM 첫 번째(탭 줄)를 누른다. */
async function openTab(label: RegExp) {
  const [btn] = await screen.findAllByRole('button', { name: label })
  fireEvent.click(btn)
}

describe('Dashboard — 전략 진행상황(cycle414)', () => {
  it('「전체」 탭(기본) → 전략 요약표 한 장', async () => {
    setup()
    const table = await screen.findByTestId('strategy-summary-table')
    expect(await within(table).findByTestId('strategy-summary-row-etf_trend')).toBeTruthy()
    expect(screen.getAllByTestId('strategy-summary-table')).toHaveLength(1)
  })

  it('ETF 추세 탭 → 상세 패널 1개 · 라우트 깔때기 · exit-lines 실효선 · 14일 추이 조회', async () => {
    const { recentCalls } = setup()
    await openTab(/ETF 추세/)
    const panel = await screen.findByTestId('etf_trend-monitor')
    expect(screen.getAllByTestId('etf_trend-monitor')).toHaveLength(1)
    expect((await within(panel).findByTestId('etf_trend-monitor-funnel-row-4')).textContent).toMatch(/20일 신고가 돌파/)
    expect((await within(panel).findByTestId(`etf_trend-monitor-stop-${ETF_HELD}`)).textContent).toMatch(/10,250/)
    await waitFor(() => expect(panel.textContent).toMatch(/0 연속 2일/))
    expect(recentCalls).toContain('etf_trend|14')
  })

  it('요약표 행을 누르면 그 전략 탭으로 간다', async () => {
    setup()
    fireEvent.click(await screen.findByTestId('strategy-summary-row-donchian_swing'))
    expect(await screen.findByTestId('donchian_swing-monitor')).toBeTruthy()
    expect(screen.queryByTestId('strategy-summary-table')).toBeNull()
  })

  it('고지로 탭 → KojiroMonitor 가 페이지에 한 번만', async () => {
    setup()
    await openTab(/고지로 대순환/)
    await screen.findByTestId('kojiro-monitor')
    expect(screen.getAllByTestId('kojiro-monitor')).toHaveLength(1)
  })

  it('모니터 라우트가 실패해도(success=false) 패널은 status 데이터로 그린다', async () => {
    setup({ monitorFails: true })
    await openTab(/ETF 추세/)
    const panel = await screen.findByTestId('etf_trend-monitor')
    expect((await within(panel).findByTestId('etf_trend-monitor-badge')).textContent).toMatch(/멈춤/)
    // 폴백 깔때기 = scan_stats(universe 41 · candidates 2) — 라우트 단계(4·20일 신고가)는 없다
    expect((await within(panel).findByTestId('etf_trend-monitor-funnel-row-1')).textContent).toMatch(/41/)
    expect(within(panel).queryByTestId('etf_trend-monitor-funnel-row-4')).toBeNull()
  })
})
