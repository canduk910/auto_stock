/**
 * cycle414 보완 1차 Red — 대시보드 배선(MSW): M10 중복·모순 · M11 요약표 14일 선 · H3 엔진 정지 배선.
 *
 * | 결함 | 이 파일의 단언 |
 * |---|---|
 * | M10 | 전략 탭에서 상세 패널과 옛 `ScanMonitor` 가 깔때기·후보·매수 신호를 **두 번** 그리지 않는다(명세 §2.1 — ScanMonitor 는 활성 보드·구독 요약·모멘텀 목록·VB/LTV 보드별 목표가표 같은 공용 칸만). 같은 탭에 모순 문구 0 — 폐기 라벨 「50/150/200 EMA」 · 멈춤 중 「진입 대기」 · VCP 탭의 NXT 매매 시간 · 전일 대비 「+0%」 |
 * | M11 | 「전체」 탭 요약표 14일 칸 = 전략마다 `/api/strategy-funnel/recent?strategy_id=<sid>&days=14` 로 그린 선(svg) |
 * | H3 | 모니터 라우트가 실패해도(`success=false`) `/api/trading/status` 의 `running=false` 면 패널은 「장 마감/엔진 정지」 — 「사지 않음」·「보유 종목 없음」 단정 0 |
 *
 * 무엇을 걷고 무엇을 남길지(표)는 Green 이 정한다 — 이 파일은 「한 번만」·「모순 0」 결과만 본다. `ScanMonitor` 단독 렌더
 * 테스트(`ScanMonitor.*.test.tsx`)는 그대로 두어야 하므로 걷는 방식은 Dashboard 쪽 배선(prop 등)이어야 한다.
 */
import { describe, expect, it } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'

import Dashboard from '../Dashboard'
import { TestProviders } from '../../test/providers'
import { TradingStatusProvider } from '../../contexts/TradingStatusContext'
import { wrap } from '../../test/factories'
import { server } from '../../test/server'
import {
  DC_CAND, ETF_A, clone, makeExitLines, makeFunnelRecent, makeMonitor, makeStatus, makeStatusStrategies,
} from '../../test/fixtures/strategyMonitor.fixture'

type Dict = Record<string, any> // eslint-disable-line @typescript-eslint/no-explicit-any

interface SetupOpts {
  strategies?: (s: Dict) => void
  status?: (st: Dict) => void
  monitor?: ((root: Dict) => void) | 'fail'
}

function setup(o: SetupOpts = {}) {
  const recentCalls: string[] = []
  const strategies = clone(makeStatusStrategies()) as Dict
  o.strategies?.(strategies)
  const status = makeStatus(strategies) as Dict
  o.status?.(status)
  const monitor = clone(makeMonitor()) as Dict
  if (typeof o.monitor === 'function') o.monitor(monitor)
  server.use(
    http.get('/api/trading/status', () => HttpResponse.json(wrap(status))),
    http.get('/api/strategies/monitor', () =>
      o.monitor === 'fail'
        ? HttpResponse.json({ success: false, data: null, message: '모니터 조회 실패' })
        : HttpResponse.json(wrap(monitor))),
    http.get('/api/balance/exit-lines', () => HttpResponse.json(wrap(makeExitLines()))),
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

async function openTab(label: RegExp) {
  const [btn] = await screen.findAllByRole('button', { name: label })
  fireEvent.click(btn)
}

const countIds = (...ids: string[]) => ids.reduce((n, id) => n + screen.queryAllByTestId(id).length, 0)
const pageText = () => document.body.textContent ?? ''

// ─────────────────────────────────────────────────────────────────────────────
describe('M10 — 전략 탭에서 깔때기·후보·신호는 한 번만, 모순 문구 0', () => {
  it('VCP 탭 — 깔때기 1 · 후보 칸 1 · 폐기 라벨 「50/150/200」 0 · NXT 매매 시간 문구 0', async () => {
    setup()
    await openTab(/VCP/)
    await screen.findByTestId('vcp_breakout-monitor')
    expect(countIds('vcp-scan-funnel', 'vcp_breakout-monitor-funnel'), '깔때기').toBe(1)
    expect(countIds('breakout-candidate-monitor', 'vcp_breakout-monitor-candidates'), '후보 칸').toBe(1)
    expect(pageText()).not.toMatch(/50\/150\/200/)
    expect(pageText()).not.toMatch(/NXT 애프터 15:30/)
  })

  it('BFB 탭 — 깔때기 1 · 후보 칸 1', async () => {
    setup()
    await openTab(/추세 눌림목 돌파/)
    await screen.findByTestId('bull_flag_breakout-monitor')
    expect(countIds('bfb-scan-funnel', 'bull_flag_breakout-monitor-funnel'), '깔때기').toBe(1)
    expect(countIds('breakout-candidate-monitor', 'bull_flag_breakout-monitor-candidates'), '후보 칸').toBe(1)
  })

  it('VB·모멘텀 탭 — 깔때기 1', async () => {
    setup()
    await openTab(/변동성 돌파/)
    await screen.findByTestId('volatility_breakout-monitor')
    expect(countIds('vb-scan-funnel', 'volatility_breakout-monitor-funnel'), 'VB 깔때기').toBe(1)
    await openTab(/^모멘텀/)
    await screen.findByTestId('momentum-monitor')
    expect(countIds('momentum-scan-funnel', 'momentum-monitor-funnel'), '모멘텀 깔때기').toBe(1)
  })

  it('돈키언 탭(멈춤) — 깔때기 1(합집합 단계가 한 번) · 펼쳐도 「진입 대기」 0', async () => {
    setup()
    await openTab(/돈키언/)
    await screen.findByTestId('donchian_swing-monitor')
    await waitFor(() => expect(screen.getAllByText(/코스피200\+코스닥150 합집합/).length).toBeGreaterThan(0))
    expect(screen.getAllByText(/코스피200\+코스닥150 합집합/), '깔때기 1단계 라벨').toHaveLength(1)
    for (const b of screen.queryAllByRole('button', { name: /펼치기/ })) fireEvent.click(b)
    expect(pageText()).not.toMatch(/진입 대기/)
  })

  it('돈키언 탭 — 매수 신호는 한 번만 · change_rate 0 을 「+0%」 로 그리지 않는다', async () => {
    setup({
      strategies: (s) => {
        s.donchian_swing.buy_signals = [{ ticker: DC_CAND, name: '삼성전자', price: 50_100, donchian_high: 49_500, atr: 1_500,
          change_rate: 0, time: '09:06:12' }]
      },
    })
    await openTab(/돈키언/)
    await screen.findByTestId('donchian_swing-monitor')
    await waitFor(() => expect(screen.getAllByText(/09:06:12/).length).toBeGreaterThan(0))
    expect(screen.getAllByText(/09:06:12/), '같은 신호 두 번').toHaveLength(1)
    expect(pageText()).not.toMatch(/\+0%/)
  })

  it('ETF 탭 — change_rate 0 신호의 「+0%」 0', async () => {
    setup({
      strategies: (s) => {
        s.etf_trend.buy_signals = [{ ticker: ETF_A, name: 'KODEX 200', price: 10_300, open_price: 10_250, line: 9_950,
          atr: 150, change_rate: 0, time: '09:07:01' }]
      },
    })
    await openTab(/ETF 추세/)
    await screen.findByTestId('etf_trend-monitor')
    await waitFor(() => expect(screen.getAllByText(/09:07:01/).length).toBeGreaterThan(0))
    expect(pageText()).not.toMatch(/\+0%/)
  })
})

// ─────────────────────────────────────────────────────────────────────────────
describe('M11 — 「전체」 탭 요약표 14일 선', () => {
  it('전략마다 14일 추이를 조회해 요약표 14일 칸에 선(svg)을 그린다', async () => {
    const { recentCalls } = setup()
    await screen.findByTestId('strategy-summary-table')
    await waitFor(() => {
      expect(screen.getByTestId('strategy-summary-trend-etf_trend').querySelector('svg')).not.toBeNull()
      expect(screen.getByTestId('strategy-summary-trend-donchian_swing').querySelector('svg')).not.toBeNull()
    })
    expect(recentCalls).toContain('etf_trend|14')
    expect(recentCalls).toContain('donchian_swing|14')
  })
})

// ─────────────────────────────────────────────────────────────────────────────
describe('H3 — 모니터 라우트가 실패해도 status.running=false 면 「장 마감/엔진 정지」', () => {
  it('ETF 탭(멈춤 해제·정산 뒤) — 「엔진 정지/장 마감」 · 「사지 않음」·「보유 종목 없음」 단정 0', async () => {
    setup({
      strategies: (s) => {
        for (const sid of Object.keys(s)) {
          Object.assign(s[sid], { positions: 0, position_tickers: [], positions_detail: {}, total_investment: 0, invested_amount: 0 })
        }
        s.etf_trend.params.buy_paused = false
      },
      status: (st) => { st.running = false; st.is_running = false; st.phase = 'idle'; st.positions = 0; st.position_tickers = [] },
      monitor: 'fail',
    })
    await openTab(/ETF 추세/)
    const panel = await screen.findByTestId('etf_trend-monitor')
    await waitFor(() => expect(panel.textContent).toMatch(/엔진 정지|장 마감/))
    expect(panel.textContent).not.toMatch(/사지 않음/)
    expect(panel.textContent).not.toMatch(/보유 종목 없음/)
  })
})
