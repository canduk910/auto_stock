/**
 * cycle411 3차 검증 후 LOW 결함 — OrderMonitor 머리줄 gap · 오류 span nowrap.
 *
 * 계약 정본 = `_workspace/red/cycle411/cost_overlay.md`.
 *
 * 3차 검증(화면 실측, 400px)에서 머리줄(제목 + 배지 그룹)이 공간 부족 시 줄바꿈 없이
 * 압착되며 그 안의 짧은 문구까지 글자 단위로 꺾였다(「조회 실패」 → 「조/회 실패」).
 *
 *  - OD1: 머리줄 컨테이너(제목의 부모)가 `flex-wrap` + `gap-2` 를 가진다 — 공간이
 *         부족하면 배지 그룹이 줄바꿈으로 내려가고 그 사이에 여백이 생긴다(압착 금지).
 *  - OD2: 오류 표시(`order-monitor-net-pnl-error`)는 `whitespace-nowrap` — 가장 좁은
 *         폭에서도 문구가 글자 단위로 꺾이지 않는다.
 *
 * jsdom 은 실제 줄바꿈을 재현하지 못하므로 className 단언으로 고정한다.
 */

import { describe, expect, it } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'

import OrderMonitor from '../OrderMonitor'
import { TestProviders } from '../../test/providers'
import { TradingStatusProvider } from '../../contexts/TradingStatusContext'
import { wrap } from '../../test/factories'
import { server } from '../../test/server'

function strat(daily: number) {
  return {
    name: 'x',
    enabled: true,
    weight: 1,
    total_investment: 5_000_000,
    positions: 0,
    pending_buys: 0,
    position_tickers: [],
    pending_buy_tickers: [],
    positions_detail: {},
    buy_disabled: false,
    daily_realized_pnl: daily,
  }
}

function setup() {
  server.use(
    http.get('/api/trading/status', () =>
      HttpResponse.json(
        wrap({ is_running: true, env: 'vts', board: 'main', strategies: { momentum: strat(500) } }),
      ),
    ),
    http.get('/api/costs/today', () => new HttpResponse(null, { status: 500 }) as unknown as Response),
  )
  return render(
    <TestProviders>
      <TradingStatusProvider>
        <OrderMonitor selectedStrategy="all" />
      </TradingStatusProvider>
    </TestProviders>,
  )
}

describe('cycle411d — OrderMonitor 머리줄 gap · 오류 span nowrap', () => {
  it('OD1: 머리줄 컨테이너(제목의 부모) = flex-wrap + gap-2', async () => {
    setup()
    const title = await screen.findByText('주문처리 현황')
    const header = title.parentElement as HTMLElement
    expect(header.className).toContain('flex-wrap')
    expect(header.className).toContain('gap-2')
  })

  it('OD2: 오류 span = whitespace-nowrap(「조회 실패」 글자 단위 꺾임 금지)', async () => {
    setup()
    const err = await screen.findByTestId('order-monitor-net-pnl-error')
    expect(err.className).toContain('whitespace-nowrap')
    await waitFor(() => expect(err.textContent).toContain('조회 실패'))
  })
})
