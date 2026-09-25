/**
 * DailyReportTab — cycle366 (P6): `metrics.report_accuracy` 휴장일 배지.
 *
 * 배경: 리포트·지표 정확도 관측 묶음(§5 P6) — 휴장일에는 로그·거래가 0건이거나
 * 적은 것이 정상인데, 화면이 그것을 결함처럼 보이게 하지 않아야 한다.
 * `report.metrics.report_accuracy.market_closed === true` 일 때만
 * `data-testid="report-holiday-badge"` 배지가 총평 카드 헤더에 뜬다.
 *
 * 요구 행위:
 * - holiday-A: `market_closed: true` — 배지 렌더
 * - holiday-B: `market_closed: false` — 배지 미렌더
 * - holiday-C: `report_accuracy` 자체가 없는(구버전) 리포트 — 배지 미렌더(크래시 없음)
 * - holiday-D: `trading_day: null`("모름") 이면서 `market_closed: false` — 배지 미렌더
 *   (판정 불가를 휴장으로 오인하지 않는다)
 */
import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'

import DailyReportTab from '../DailyReportTab'
import { TestProviders } from '../../test/providers'
import { wrap } from '../../test/factories'
import { server } from '../../test/server'
import type { LogReportItem } from '../../types/log_reports'

function baseReport(overrides: Partial<LogReportItem>): LogReportItem {
  return {
    id: 'r1',
    target_date: '2026-09-26',
    summary: '휴장일 — 특이사항 없음.',
    findings: [],
    metrics: null,
    model: 'gpt-4o',
    created_at: '2026-09-26T21:30:00+09:00',
    ...overrides,
  }
}

function mockList(items: LogReportItem[]) {
  server.use(http.get('/api/log-reports', () => HttpResponse.json(wrap(items))))
}

describe('DailyReportTab — 휴장일 배지 (cycle366 P6)', () => {
  it('holiday-A: market_closed=true — 배지 렌더', async () => {
    const report = baseReport({
      metrics: {
        target_date: '2026-09-26',
        logs: { level_counts: {}, top_patterns: {}, samples: {}, total_logs: 0 },
        trades: { trades_total: 0, buy_count: 0, sell_count: 0, realized_pnl: 0, by_strategy: {}, by_status: {} },
        report_accuracy: {
          trading_day: false,
          market_closed: true,
          by_ticker_pnl_total_tickers: 0,
          by_ticker_pnl_truncated: false,
          after_market_blind_secs_total: 0,
          pre_market_blind_secs_total: 0,
        },
      },
    })
    mockList([report])
    render(
      <TestProviders>
        <DailyReportTab />
      </TestProviders>,
    )

    await screen.findByText('2026-09-26 총평')
    expect(screen.getByTestId('report-holiday-badge')).toBeInTheDocument()
    expect(screen.getByTestId('report-holiday-badge').textContent).toContain('휴장일')
  })

  it('holiday-B: market_closed=false — 배지 미렌더', async () => {
    const report = baseReport({
      metrics: {
        target_date: '2026-09-26',
        logs: { level_counts: {}, top_patterns: {}, samples: {}, total_logs: 10 },
        trades: { trades_total: 3, buy_count: 2, sell_count: 1, realized_pnl: 1000, by_strategy: {}, by_status: {} },
        report_accuracy: {
          trading_day: true,
          market_closed: false,
          by_ticker_pnl_total_tickers: 1,
          by_ticker_pnl_truncated: false,
          after_market_blind_secs_total: 0,
          pre_market_blind_secs_total: 0,
        },
      },
    })
    mockList([report])
    render(
      <TestProviders>
        <DailyReportTab />
      </TestProviders>,
    )

    await screen.findByText('2026-09-26 총평')
    expect(screen.queryByTestId('report-holiday-badge')).toBeNull()
  })

  it('holiday-C: report_accuracy 없는 구버전 행 — 배지 미렌더 + 크래시 없음', async () => {
    const report = baseReport({
      metrics: {
        target_date: '2026-09-26',
        logs: { level_counts: {}, top_patterns: {}, samples: {}, total_logs: 0 },
        trades: { trades_total: 0, buy_count: 0, sell_count: 0, realized_pnl: 0, by_strategy: {}, by_status: {} },
      },
    })
    mockList([report])
    render(
      <TestProviders>
        <DailyReportTab />
      </TestProviders>,
    )

    await screen.findByText('2026-09-26 총평')
    expect(screen.queryByTestId('report-holiday-badge')).toBeNull()
  })

  it('holiday-D: trading_day=null("모름") — 휴장으로 단정하지 않는다', async () => {
    const report = baseReport({
      metrics: {
        target_date: '2026-09-26',
        logs: { level_counts: {}, top_patterns: {}, samples: {}, total_logs: 0 },
        trades: { trades_total: 0, buy_count: 0, sell_count: 0, realized_pnl: 0, by_strategy: {}, by_status: {} },
        report_accuracy: {
          trading_day: null,
          market_closed: false,
          by_ticker_pnl_total_tickers: 0,
          by_ticker_pnl_truncated: false,
          after_market_blind_secs_total: 0,
          pre_market_blind_secs_total: 0,
        },
      },
    })
    mockList([report])
    render(
      <TestProviders>
        <DailyReportTab />
      </TestProviders>,
    )

    await screen.findByText('2026-09-26 총평')
    expect(screen.queryByTestId('report-holiday-badge')).toBeNull()
  })
})
