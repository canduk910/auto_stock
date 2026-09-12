/**
 * cycle285 (2026-09-13) — 장운영상태 화면 신규 섹션 2개 행위 테스트.
 *
 * 섹션 A "지금 시장은"(`GET /api/realtime/market-operation` 재사용, 백엔드 신규 0)과
 * 섹션 B "오늘 야간작업"(`GET /api/market-ops` 신규)이 각자 독립적으로 조회·실패·표시된다는
 * 계약을 잰다. 기존 (1)~(4) 섹션(cycle282)은 `MarketState.test.tsx` 가 이미 지키므로
 * 여기서는 건드리지 않는다 — 표는 항상 기본 픽스처(MSW `handlers.ts` 기본 핸들러)로 둔다.
 */
import { afterEach, describe, expect, it } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { http, HttpResponse } from 'msw'
import type { ReactNode } from 'react'

import MarketState from '../MarketState'
import { server } from '../../test/server'

const LONG = { timeout: 10_000 }
// cycle285 검증(honest 렌즈 MEDIUM #6) — vitest 기본 per-test 타임아웃(5,000ms)이
// `LONG`(10,000ms) 보다 짧아 병렬 부하 아래서 flaky 하게 죽었다(실측 89/90 파일
// 통과·해당 파일 12/12 단독 실행은 통과). `StockMaster.dailyTab.cycle266.test.tsx`
// 의 `ERROR_TEST_TIMEOUT` 선례를 그대로 답습 — 실패 메시지가 "타임아웃" 이 아니라
// "해당 testid 없음" 으로 읽혀야 CI 에서 원인 진단이 된다.
const TEST_TIMEOUT = 20_000

function createClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false, retryDelay: 0, gcTime: 0, staleTime: 0 } },
  })
}

function withProviders(children: ReactNode, client: QueryClient) {
  return (
    <QueryClientProvider client={client}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  )
}

function mount() {
  const client = createClient()
  return render(withProviders(<MarketState />, client))
}

function baseOpsTask(overrides: Record<string, unknown> = {}) {
  return {
    id: 'stock_master_basics_refresh',
    label_ko: '종목마스터 기본정보 보강',
    scheduled_at: '16:10',
    status: 'done',
    last_success_at: '2026-09-13T16:12:03+09:00',
    evidence: { total: 2700, updated: 2700 },
    note: null,
    ...overrides,
  }
}

function baseOpsPayload(overrides: Record<string, unknown> = {}) {
  return {
    as_of_kst: '2026-09-13T20:35:00+09:00',
    is_trading_day: true,
    trading_day_source: 'kis',
    engine: { running: true, phase: 'closing', heartbeat_at: '2026-09-13T20:34:40+09:00' },
    tasks: [baseOpsTask()],
    evidence_errors: [],
    ...overrides,
  }
}

function useOps(payload: Record<string, unknown>) {
  server.use(http.get('*/api/market-ops', () => HttpResponse.json({ success: true, data: payload, message: '' })))
}

function useMarketOp(payload: Record<string, unknown>) {
  server.use(
    http.get('*/api/realtime/market-operation', () =>
      HttpResponse.json({ success: true, data: payload, message: '' }),
    ),
  )
}

const MARKET_OP_ZERO = {
  vi_active_count: 0,
  halt_active_count: 0,
  last_event_count: 11,
  iscd_stat_active_count: 0,
  vi_active_sample: [],
  halt_active_sample: [],
  circuit_breaker: {
    suspected: false,
    reasons: [],
    halt_ratio: 0,
    halted: 0,
    observed: 11,
    representative_mkop_cls_code: '00',
    halt_reasons_sample: [],
  },
  details: [],
}

afterEach(() => {
  server.resetHandlers()
})

describe('cycle285 섹션 A — 지금 시장은', () => {
  it('VI·거래정지·서킷브레이커 배지와 관측 커버리지 문구를 보여준다', async () => {
    useMarketOp(MARKET_OP_ZERO)
    mount()
    await waitFor(() => expect(screen.getByTestId('market-state-now-section')).toBeInTheDocument(), LONG)
    expect(screen.getByTestId('market-state-now-vi')).toHaveTextContent('VI 0건')
    expect(screen.getByTestId('market-state-now-halt')).toHaveTextContent('거래정지 0건')
    expect(screen.getByTestId('market-state-now-cb')).toHaveTextContent('정상')
    const coverage = screen.getByTestId('market-state-now-coverage-note')
    expect(coverage.textContent).toContain('11종목')
    // §4-2 — "0건" 을 "없음" 이 아니라 "관측 대상 안에 없음" 으로 읽게 하는 문구가 실재해야 한다
    expect(coverage.textContent).toContain('관측 대상')
    // §4-3 — 평시(정상)에도 "추정" 표기와 근거 박스가 존재해야 한다(발동 시에만
    // 보이면 "0/11 이 얼마나 먼지" 를 알 수 없다). cycle285 검증 test 렌즈 MEDIUM #5
    // 가 이 두 단언 부재로 뮤테이션 2건이 무방비였다고 지적했다.
    expect(screen.getByTestId('market-state-now-cb').textContent).toContain('추정')
    expect(screen.getByTestId('market-state-now-cb-basis')).toBeInTheDocument()
  }, TEST_TIMEOUT)

  it('서킷브레이커 의심 시 "추정" 표기와 halted/observed 근거를 보여준다', async () => {
    useMarketOp({
      ...MARKET_OP_ZERO,
      halt_active_count: 6,
      circuit_breaker: {
        ...MARKET_OP_ZERO.circuit_breaker,
        suspected: true,
        halted: 6,
        observed: 7,
        halt_ratio: 0.857,
        halt_reasons_sample: ['서킷브레이커 발동'],
        representative_mkop_cls_code: '20',
      },
    })
    mount()
    await waitFor(() => expect(screen.getByTestId('market-state-now-cb')).toHaveTextContent('의심'), LONG)
    // 발동 시에도 "추정" 문구는 지워지지 않는다 — 확정처럼 보이면 안 된다.
    expect(screen.getByTestId('market-state-now-cb').textContent).toContain('추정')
    const basis = screen.getByTestId('market-state-now-cb-basis')
    expect(basis.textContent).toContain('6/관측 7종목')
    expect(basis.textContent).toContain('서킷브레이커 발동')
  }, TEST_TIMEOUT)

  it('20:00~21:30 구간(phase=closing)에는 "장 종료 — 마지막 관측값" 배지를 보인다', async () => {
    useOps(baseOpsPayload({ engine: { running: true, phase: 'closing', heartbeat_at: null } }))
    useMarketOp(MARKET_OP_ZERO)
    mount()
    await waitFor(
      () => expect(screen.getByTestId('market-state-now-session-badge')).toHaveAttribute('data-state', 'frozen'),
      LONG,
    )
  }, TEST_TIMEOUT)

  it('엔진이 idle 이면 "세션 종료 — 집계 없음" 을 보이고 0 건을 이상 없음으로 위장하지 않는다', async () => {
    useOps(baseOpsPayload({ engine: { running: false, phase: 'idle', heartbeat_at: null } }))
    useMarketOp(MARKET_OP_ZERO)
    mount()
    const badge = await screen.findByTestId('market-state-now-session-badge', {}, LONG)
    expect(badge).toHaveAttribute('data-state', 'ended')
    expect(badge.textContent).toContain('세션 종료')
  }, TEST_TIMEOUT)

  it('실시간 장운영 조회 실패는 이 섹션만 비운다 — 다른 섹션은 정상', async () => {
    server.use(http.get('*/api/realtime/market-operation', () => HttpResponse.json({}, { status: 500 })))
    mount()
    await waitFor(() => expect(screen.getByTestId('market-state-now-error')).toBeInTheDocument(), LONG)
    // 표(기존 cycle282 섹션)는 여전히 정상 — 섹션 격리 확인
    expect(await screen.findByTestId('market-state-table', {}, LONG)).toBeInTheDocument()
    expect(await screen.findByTestId('market-state-ops-section', {}, LONG)).toBeInTheDocument()
  }, TEST_TIMEOUT)
})

describe('cycle285 섹션 B — 오늘 야간작업', () => {
  it('작업 행을 시각순 그대로 보여주고 상태 배지를 붙인다', async () => {
    useOps(
      baseOpsPayload({
        tasks: [
          baseOpsTask({ id: 'a', label_ko: '작업A', scheduled_at: '16:10', status: 'done' }),
          baseOpsTask({ id: 'b', label_ko: '작업B', scheduled_at: '19:00', status: 'unknown', last_success_at: null }),
          baseOpsTask({ id: 'c', label_ko: '작업C', scheduled_at: '21:30', status: 'scheduled', last_success_at: null }),
        ],
      }),
    )
    mount()
    await waitFor(() => expect(screen.getByTestId('market-state-ops-table')).toBeInTheDocument(), LONG)
    const rows = screen.getAllByRole('row')
    // 헤더 1행 + 데이터 3행 순서 유지(응답 순서 == 렌더 순서)
    const dataRowTexts = rows.slice(1).map((r) => r.textContent ?? '')
    expect(dataRowTexts[0]).toContain('작업A')
    expect(dataRowTexts[1]).toContain('작업B')
    expect(dataRowTexts[2]).toContain('작업C')
    expect(screen.getByTestId('market-state-ops-status-a')).toHaveTextContent('완료')
    expect(screen.getByTestId('market-state-ops-status-b')).toHaveTextContent('확인 불가')
    expect(screen.getByTestId('market-state-ops-status-c')).toHaveTextContent('예정')
  }, TEST_TIMEOUT)

  it('마커가 없는 작업을 "실패" 로 위장하지 않는다(unknown 유지)', async () => {
    useOps(
      baseOpsPayload({
        tasks: [
          baseOpsTask({
            id: 'quote_token_refresh',
            label_ko: '보조 시세계정 토큰 강제 재발급',
            scheduled_at: '19:00',
            status: 'unknown',
            last_success_at: null,
            evidence: {},
            note: '이 작업은 성공 마커를 남기지 않는다',
          }),
        ],
      }),
    )
    mount()
    const status = await screen.findByTestId('market-state-ops-status-quote_token_refresh', {}, LONG)
    expect(status).not.toHaveTextContent('실패')
    expect(status).toHaveTextContent('확인 불가')
    expect(screen.getByTestId('market-state-ops-note-quote_token_refresh').textContent).toContain('마커를 남기지 않는다')
  }, TEST_TIMEOUT)

  it('20:05 스냅샷이 정산 뒤 덮어써진 것은 결함이 아니다(overwritten ≠ failed)', async () => {
    useOps(
      baseOpsPayload({
        tasks: [
          baseOpsTask({ id: 'metrics_snapshot', label_ko: '매매지표 1차 스냅샷', scheduled_at: '20:05', status: 'overwritten', last_success_at: null, evidence: {} }),
        ],
      }),
    )
    mount()
    const status = await screen.findByTestId('market-state-ops-status-metrics_snapshot', {}, LONG)
    expect(status).not.toHaveTextContent('실패')
    expect(status.textContent).toContain('완료')
  }, TEST_TIMEOUT)

  it('휴장일이면 전 행이 휴장일 상태이고 안내 배너를 보인다', async () => {
    useOps(
      baseOpsPayload({
        is_trading_day: false,
        tasks: [baseOpsTask({ id: 'x', status: 'holiday' })],
      }),
    )
    mount()
    await waitFor(() => expect(screen.getByTestId('market-state-ops-holiday-banner')).toBeInTheDocument(), LONG)
    expect(screen.getByTestId('market-state-ops-status-x')).toHaveTextContent('휴장일')
  }, TEST_TIMEOUT)

  it('일부 데이터 소스 조회 실패를 숨기지 않는다', async () => {
    useOps(baseOpsPayload({ evidence_errors: ['log_report', 'markers'] }))
    mount()
    const banner = await screen.findByTestId('market-state-ops-evidence-errors', {}, LONG)
    expect(banner.textContent).toContain('log_report')
    expect(banner.textContent).toContain('markers')
  }, TEST_TIMEOUT)

  it('요약 수치(evidence)를 키·값으로 보여준다', async () => {
    useOps(
      baseOpsPayload({
        tasks: [
          baseOpsTask({
            id: 'daily',
            label_ko: '일봉 적재',
            evidence: { daily_head: '2026-09-11', daily_rows_today: 0 },
          }),
        ],
      }),
    )
    mount()
    const row = await screen.findByTestId('market-state-ops-row-daily', {}, LONG)
    expect(within(row).getByText('2026-09-11')).toBeInTheDocument()
  }, TEST_TIMEOUT)

  it('야간작업 조회 실패는 이 섹션만 비운다 — 표·섹션A 는 정상', async () => {
    server.use(http.get('*/api/market-ops', () => HttpResponse.json({}, { status: 500 })))
    useMarketOp(MARKET_OP_ZERO)
    mount()
    await waitFor(() => expect(screen.getByTestId('market-state-ops-error')).toBeInTheDocument(), LONG)
    expect(await screen.findByTestId('market-state-table', {}, LONG)).toBeInTheDocument()
    expect(await screen.findByTestId('market-state-now-section', {}, LONG)).toBeInTheDocument()
  }, TEST_TIMEOUT)
})
