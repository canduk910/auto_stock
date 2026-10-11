/**
 * DailyReportTab — cycle445: OpenAI 요약 생성 제거 뒤의 총평 카드 표시.
 *
 * 배경: `generate_daily_log_report` 가 더는 OpenAI 를 호출하지 않아 `summary` 는
 * 정상 경로에서도 항상 빈 값이다(사용자 결정 2026-10-11, 워크리스트 참조). 사람이
 * 읽는 운영 요약은 20:20 KST 클라우드 루틴이 `ext_*` 컬럼에 쓴다.
 *
 * 요구 행위:
 * - c445-A: `summary=""` + ext 분석 있음 — 총평 카드(legacy-summary-card) 자체가
 *   렌더되지 않는다(Claude 분석 카드만 보인다, 중복 빈 카드 없음).
 * - c445-B: `summary=""` + ext 분석 없음 — 총평 카드는 뜨되 "요약이 없습니다" 가
 *   아니라 대기 안내(summary-pending-notice)를 보인다.
 * - c445-C: `summary` 가 채워진 과거 행(cycle445 이전 OpenAI 행) — 기존 렌더 그대로
 *   (총평 카드가 그 값을 그린다, 대기 안내 없음).
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
    target_date: '2026-10-11',
    summary: '',
    findings: [],
    metrics: null,
    model: null,
    created_at: '2026-10-11T21:30:00+09:00',
    ...overrides,
  }
}

function mockList(items: LogReportItem[]) {
  server.use(http.get('/api/log-reports', () => HttpResponse.json(wrap(items))))
}

describe('DailyReportTab — cycle445 (OpenAI 요약 제거)', () => {
  it('c445-A: summary 빈 값 + ext 분석 있음 — 총평 카드를 그리지 않는다', async () => {
    mockList([
      baseReport({
        ext_summary: 'Claude 가 쓴 오늘 운영 요약입니다.',
        ext_created_at: '2026-10-11T20:20:00+09:00',
      }),
    ])
    render(
      <TestProviders>
        <DailyReportTab />
      </TestProviders>,
    )

    await screen.findByTestId('ext-analysis-card')
    expect(screen.queryByTestId('legacy-summary-card')).toBeNull()
    expect(screen.queryByTestId('summary-pending-notice')).toBeNull()
  })

  it('c445-B: summary 빈 값 + ext 분석 없음 — 대기 안내를 보인다', async () => {
    mockList([baseReport({})])
    render(
      <TestProviders>
        <DailyReportTab />
      </TestProviders>,
    )

    await screen.findByTestId('legacy-summary-card')
    expect(screen.getByTestId('summary-pending-notice')).toBeInTheDocument()
    expect(screen.queryByText('요약이 없습니다.')).toBeNull()
  })

  it('c445-C: 과거 OpenAI 행(summary 채워짐) — 기존처럼 그 값을 그린다', async () => {
    mockList([baseReport({ summary: '오늘은 특이사항이 없었습니다.', model: 'gpt-5.6-luna' })])
    render(
      <TestProviders>
        <DailyReportTab />
      </TestProviders>,
    )

    await screen.findByTestId('legacy-summary-card')
    expect(screen.getByText('오늘은 특이사항이 없었습니다.')).toBeInTheDocument()
    expect(screen.queryByTestId('summary-pending-notice')).toBeNull()
  })
})
