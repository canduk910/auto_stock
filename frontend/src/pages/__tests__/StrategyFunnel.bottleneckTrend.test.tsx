/**
 * team-leader 3d (2026-08-06) — 깔때기 병목 강조 + 최근 N영업일 추이.
 *
 * 배경: VCP 전략(vcp_breakout) enabled=True·weight=0.10 이나 도입 이래 체결 0건.
 * 실측 깔때기(코스피200+코스닥150 348 → EMA 정렬 7 → Pullback 0) 원인이 이미
 * `strategy_funnel_snapshots` DB 에 매일 적재되고 화면에도 나오지만, 화면이
 * (1) 단계별 급감 지점을 시각 강조하지 않고 (2) getRecentFunnel 로 시계열 추세를
 * 보여주지 않아 "3주째 전멸 중"인지 "오늘만 그런지" 구분이 불가능했다.
 *
 * 검증:
 * - G-BTN-1~4: computeBottleneck 순수 함수 (절대 감소 수 최대 단계 판정)
 * - G-DAILY-1~2: extractDailyFinalCounts 순수 함수 (최종 단계 추출 + 날짜 정렬)
 * - G-STREAK-1~2: computeZeroStreak 순수 함수
 * - G-RENDER-1~5: 배너 톤 분기 + 단계 1개 미렌더 + 추이 섹션 + graceful 실패
 */
import { describe, expect, it } from 'vitest'
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'

import StrategyFunnel, {
  computeBottleneck,
  computeZeroStreak,
  extractDailyFinalCounts,
  type DailyFinalCount,
} from '../StrategyFunnel'
import type { FunnelSnapshot } from '../../api/strategy-funnel'
import { TestProviders } from '../../test/providers'
import { wrap } from '../../test/factories'
import { server } from '../../test/server'

function makeSnapshot(overrides: Partial<FunnelSnapshot> = {}): FunnelSnapshot {
  return {
    id: `${overrides.strategy_id ?? 'vcp_breakout'}-${overrides.step_no ?? 1}`,
    target_date: '2026-08-06',
    snapshot_at: '2026-08-06T09:30:00+09:00',
    strategy_id: 'vcp_breakout',
    step_no: 1,
    step_name: '단계',
    step_conditions: null,
    survived_count: 0,
    excluded_count: 0,
    survived_tickers: [],
    excluded_sample: [],
    is_provisional: false,
    ...overrides,
  }
}

// 팀장이 실측한 VCP 깔때기 패턴 (코스피200+코스닥150 합집합 → EMA 정렬 → Pullback 전멸).
function vcpFunnelRows(): FunnelSnapshot[] {
  return [
    makeSnapshot({ step_no: 1, step_name: '코스피200+코스닥150 합집합', survived_count: 348 }),
    makeSnapshot({ step_no: 2, step_name: '시총 ≥ 1,000억', survived_count: 348 }),
    makeSnapshot({ step_no: 4, step_name: '일봉 fetch + 추세필터', survived_count: 329 }),
    makeSnapshot({ step_no: 5, step_name: '단기/중기/장기 EMA 정렬', survived_count: 7 }),
    makeSnapshot({ step_no: 6, step_name: '베이스 자동 검출', survived_count: 7 }),
    makeSnapshot({ step_no: 7, step_name: 'Pullback 점진 수축', survived_count: 0 }),
    makeSnapshot({ step_no: 9, step_name: '최종 prepared', survived_count: 0 }),
  ]
}

function mockFunnel(snapshots: FunnelSnapshot[]) {
  server.use(
    http.get('/api/strategy-funnel', () =>
      HttpResponse.json(
        wrap({
          target_date: '2026-08-06',
          strategy_id: null,
          snapshots,
          is_business_day: true,
          holiday_note: null,
        }),
      ),
    ),
  )
}

function mockRecent(snapshots: FunnelSnapshot[]) {
  server.use(
    http.get('/api/strategy-funnel/recent', () =>
      HttpResponse.json(wrap({ strategy_id: 'vcp_breakout', days: 14, snapshots })),
    ),
  )
}

describe('computeBottleneck — 병목 단계 판정', () => {
  it('G-BTN-1: 절대 감소 수가 가장 큰 단계를 병목으로 판정 (%로는 후행 단계가 더 높아도 무시)', () => {
    // step5(329→7)=322건 감소 vs step7(7→0)=7건 감소, 100%지만 절대량은 미미.
    const bottleneck = computeBottleneck(vcpFunnelRows())
    expect(bottleneck).not.toBeNull()
    expect(bottleneck?.stepNo).toBe(5)
    expect(bottleneck?.prevCount).toBe(329)
    expect(bottleneck?.curCount).toBe(7)
    expect(bottleneck?.dropRatePct).toBeCloseTo(97.87, 1)
  })

  it('G-BTN-2: 단계가 1개면 비교 대상이 없어 null', () => {
    expect(computeBottleneck([makeSnapshot({ step_no: 1, survived_count: 10 })])).toBeNull()
  })

  it('G-BTN-3: 데이터 없음(빈 배열) 시 null', () => {
    expect(computeBottleneck([])).toBeNull()
  })

  it('G-BTN-4: 감소가 없는(단조 비감소) 구간에서도 크래시 없이 최댓값(0) 판정', () => {
    const rows = [
      makeSnapshot({ step_no: 1, survived_count: 10 }),
      makeSnapshot({ step_no: 2, survived_count: 10 }),
    ]
    const bottleneck = computeBottleneck(rows)
    expect(bottleneck?.dropRatePct).toBe(0)
  })
})

describe('extractDailyFinalCounts — 날짜별 최종 단계 추출', () => {
  it('G-DAILY-1: step_no=99 최종 단계 우선 추출 + 날짜 오름차순 정렬', () => {
    const snapshots: FunnelSnapshot[] = [
      makeSnapshot({ target_date: '2026-08-05', step_no: 5, survived_count: 3 }),
      makeSnapshot({ target_date: '2026-08-05', step_no: 99, survived_count: 0 }),
      makeSnapshot({ target_date: '2026-08-04', step_no: 99, survived_count: 2 }),
      makeSnapshot({ target_date: '2026-08-04', step_no: 5, survived_count: 9 }),
    ]
    const daily = extractDailyFinalCounts(snapshots)
    expect(daily).toEqual<DailyFinalCount[]>([
      { date: '2026-08-04', count: 2 },
      { date: '2026-08-05', count: 0 },
    ])
  })

  it('G-DAILY-2: step_no=99 부재 시 최대 step_no 를 최종 단계로 폴백', () => {
    const snapshots: FunnelSnapshot[] = [
      makeSnapshot({ target_date: '2026-08-06', step_no: 1, survived_count: 100 }),
      makeSnapshot({ target_date: '2026-08-06', step_no: 7, survived_count: 0 }),
    ]
    expect(extractDailyFinalCounts(snapshots)).toEqual([{ date: '2026-08-06', count: 0 }])
  })
})

describe('computeZeroStreak — 연속 0 스트릭', () => {
  it('G-STREAK-1: 최근일부터 역순으로 연속된 0 개수를 센다', () => {
    const daily: DailyFinalCount[] = [
      { date: '2026-08-01', count: 5 },
      { date: '2026-08-02', count: 0 },
      { date: '2026-08-03', count: 0 },
      { date: '2026-08-04', count: 0 },
    ]
    expect(computeZeroStreak(daily)).toBe(3)
  })

  it('G-STREAK-2: 최근일이 0이 아니면 스트릭 0', () => {
    const daily: DailyFinalCount[] = [
      { date: '2026-08-01', count: 0 },
      { date: '2026-08-02', count: 5 },
    ]
    expect(computeZeroStreak(daily)).toBe(0)
  })
})

describe('StrategyFunnel 렌더링 — 병목 배너 + 최근 추이', () => {
  it('G-RENDER-1: 최종 후보 0 — 병목 배너 red 톤 렌더', async () => {
    mockFunnel(vcpFunnelRows())
    render(
      <TestProviders>
        <StrategyFunnel />
      </TestProviders>,
    )
    const banner = await screen.findByTestId('funnel-bottleneck-banner')
    expect(banner.textContent).toContain('5단계')
    expect(banner.textContent).toContain('329')
    expect(banner.textContent).toContain('7')
    expect(banner.textContent).toMatch(/97\.9/)
    expect(banner.className).toMatch(/bg-red-100/)
  })

  it('G-RENDER-2: 최종 후보 > 0 — 병목 배너 amber 톤 렌더', async () => {
    const rows = [
      makeSnapshot({ step_no: 1, step_name: '유니버스', survived_count: 200 }),
      makeSnapshot({ step_no: 2, step_name: '필터', survived_count: 20 }),
      makeSnapshot({ step_no: 3, step_name: '최종', survived_count: 15 }),
    ]
    mockFunnel(rows)
    render(
      <TestProviders>
        <StrategyFunnel />
      </TestProviders>,
    )
    const banner = await screen.findByTestId('funnel-bottleneck-banner')
    expect(banner.className).toMatch(/bg-amber-50/)
    expect(banner.className).not.toMatch(/bg-red-100/)
  })

  it('G-RENDER-3: 단계가 1개뿐이면 병목 배너 미렌더', async () => {
    mockFunnel([makeSnapshot({ step_no: 1, step_name: '단일단계', survived_count: 5 })])
    render(
      <TestProviders>
        <StrategyFunnel />
      </TestProviders>,
    )
    await waitFor(() => {
      expect(screen.getByTestId('funnel-strategy-block-vcp_breakout')).toBeInTheDocument()
    })
    expect(screen.queryByTestId('funnel-bottleneck-banner')).not.toBeInTheDocument()
  })

  it('G-RENDER-4: 특정 전략 선택 시 최근 추이 섹션 렌더 + 연속 0 배지', async () => {
    mockFunnel(vcpFunnelRows())
    const recentDaily = [
      makeSnapshot({ target_date: '2026-08-03', step_no: 99, survived_count: 0 }),
      makeSnapshot({ target_date: '2026-08-04', step_no: 99, survived_count: 0 }),
      makeSnapshot({ target_date: '2026-08-05', step_no: 99, survived_count: 0 }),
    ]
    mockRecent(recentDaily)

    render(
      <TestProviders>
        <StrategyFunnel />
      </TestProviders>,
    )
    // 기본값 '전체' 에서는 추이 섹션이 없어야 함
    expect(screen.queryByTestId('funnel-recent-trend')).not.toBeInTheDocument()

    fireEvent.change(screen.getByTestId('funnel-strategy-select'), {
      target: { value: 'vcp_breakout' },
    })

    const trend = await screen.findByTestId('funnel-recent-trend')
    await waitFor(() => {
      expect(within(trend).getByTestId('funnel-recent-trend-zero-streak-badge')).toBeInTheDocument()
    })
    expect(within(trend).getByTestId('funnel-recent-trend-zero-streak-badge').textContent).toContain(
      '3일 연속 후보 0',
    )
  })

  it('G-RENDER-5: getRecentFunnel 실패해도 나머지 페이지(단계별 테이블)는 정상 렌더 (graceful)', async () => {
    mockFunnel(vcpFunnelRows())
    server.use(
      http.get('/api/strategy-funnel/recent', () =>
        HttpResponse.json({ success: false, data: null, message: 'boom' }, { status: 500 }),
      ),
    )

    render(
      <TestProviders>
        <StrategyFunnel />
      </TestProviders>,
    )

    fireEvent.change(screen.getByTestId('funnel-strategy-select'), {
      target: { value: 'vcp_breakout' },
    })

    // 메인 단계별 테이블은 최근 추이 실패와 무관하게 정상 렌더
    await waitFor(() => {
      expect(screen.getByTestId('funnel-strategy-block-vcp_breakout')).toBeInTheDocument()
      expect(screen.getByTestId('funnel-bottleneck-banner')).toBeInTheDocument()
    })
    // 추이 섹션 자체는 에러 상태를 graceful 하게 표시 (페이지 크래시 없음)
    const trend = await screen.findByTestId('funnel-recent-trend')
    expect(trend.textContent).toMatch(/실패/)
  })
})
