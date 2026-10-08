/**
 * cycle411 Red — 로그 일일리포트의 실현손익은 저장 스냅샷이라 숫자 그대로 두고 「세전」 라벨만
 * (사용자 결정 10-08 Q3).
 *
 * 계약
 *  - DR1: 「원본 메트릭 → 거래 통계」 의 실현손익 칸 이름에 `세전` 이 붙는다.
 *  - DR2: 숫자는 `metrics.trades.realized_pnl` 그대로(비용을 빼지 않는다).
 */

import { describe, expect, it } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'

import DailyReportTab from '../DailyReportTab'
import { TestProviders } from '../../test/providers'
import { wrap } from '../../test/factories'
import { server } from '../../test/server'

const REPORT = {
  id: 'r1',
  target_date: '2026-10-07',
  summary: '총평',
  findings: [],
  metrics: {
    target_date: '2026-10-07',
    logs: { level_counts: { INFO: 1, WARNING: 0, ERROR: 0, CRITICAL: 0 } },
    trades: {
      trades_total: 4,
      buy_count: 2,
      sell_count: 2,
      realized_pnl: 30000,
      by_strategy: {},
      by_status: {},
    },
  },
  model: 'gpt-4o',
  created_at: '2026-10-07T21:30:00+09:00',
}

describe('cycle411 — DailyReportTab 실현손익 「세전」 라벨', () => {
  it('DR1·DR2', async () => {
    server.use(http.get('/api/log-reports', () => HttpResponse.json(wrap([REPORT]))))
    render(
      <TestProviders>
        <DailyReportTab />
      </TestProviders>,
    )
    await userEvent.click(await screen.findByText('원본 메트릭'))
    await waitFor(() => expect(screen.getByText(/실현손익/)).toBeInTheDocument())
    const label = screen.getByText(/실현손익/)
    expect(label.textContent).toContain('세전')
    const cell = label.parentElement as HTMLElement
    expect(cell.textContent).toContain('30,000')
  })
})
