/**
 * cycle370 (장운영 상태 화면 정리) — RealtimeHealth 「장운영상태」 카드의 종목별 행 배지 Red 가드.
 *
 * 배경: 백엔드 cycle368 이 H0UNMKO0 칸 밀림을 바로잡은 뒤, 화면의 종목별 행이 백엔드 판정과 어긋났다.
 *   (1) VI 배지가 vi_code ∉ {'0',''} 이면 무조건 떠서 해제된 VI('N')가 「VI:N」 으로 보였다.
 *       → 백엔드 비활성 집합 `src/api/market_operation.py::_INACTIVE_VALUES`
 *         = {'', '0', 'N', 'n', '(null)'} 과 같은 집합으로만 판정한다.
 *   (2) 거래정지 배지가 halt_yn === 'Y' 만 봐서 종목상태 58(거래정지 지정)로 정지된 종목에 배지가 없었다.
 *       → halt_yn === 'Y' 또는 iscd_stat === '58' (백엔드 `ISCD_STAT_BLOCKING` = {'58'}).
 *   (3) iscd_stat 가 화면에 전혀 안 나왔다.
 *       → 표시 집합(백엔드 `_ISCD_STAT_DISPLAY_CODES`) 51 관리종목 · 52 투자위험 · 53 투자경고 ·
 *         54 투자주의 · 58 거래정지 · 59 단기과열 만 보이고 55/57/00/'' 는 아무것도 안 보인다.
 *         58 은 거래정지 배지 **하나로만** 그린다(종목상태 배지를 따로 그리지 않는다 = 중복 금지).
 *   (4) 정지 사유가 KIS null 토큰 "(null)" 이면 그 글자를 그리지 않는다(백엔드가 이미 "" 로 정규화하지만
 *       방어 가드). 정규화는 **정확일치만** — 백엔드 N4 와 같다(부분 치환이면 실제 사유 문장이 깎인다).
 *
 * 데이터 소스: GET /api/realtime/market-operation → details[] (shape = src/routes/realtime.py
 *   get_market_operation: ticker / vi_code / ovtm_vi_code / halt_yn / halt_reason / iscd_stat /
 *   mkop_cls_code / exch_code / received_at). 타입 = frontend/src/types/market-operation.ts::MarketOpDetail.
 *
 * testid 계약 (Green 이 구현):
 *   - 행:          realtime-health-op-row-<ticker>
 *   - VI 배지:     realtime-health-op-vi-badge     (행 안)
 *   - 거래정지 배지: realtime-health-op-halt-badge   (행 안, 행당 최대 1개)
 *   - 종목상태 배지: realtime-health-op-stat-badge   (행 안, 51·52·53·54·59 만)
 */
import { describe, expect, it, beforeEach, afterEach } from 'vitest'
import { http, HttpResponse } from 'msw'
import { render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import type { ReactNode } from 'react'

import RealtimeHealth from '../RealtimeHealth'
import { server } from '../../test/server'
import type { MarketOpDetail } from '../../types/market-operation'

function withProviders(children: ReactNode) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0, staleTime: 0 } },
  })
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  )
}

// 행 기본값 — VI·정지·종목상태 모두 비활성. received_at=null 로 두어 행 글자에 시각 숫자가 섞이지 않게 한다
// (55/57/00 「아무것도 안 보인다」 단언이 코드 숫자의 부재까지 보기 때문).
function row(ticker: string, overrides: Partial<MarketOpDetail> = {}): MarketOpDetail {
  return {
    ticker,
    vi_code: '0',
    ovtm_vi_code: '0',
    halt_yn: 'N',
    halt_reason: '',
    iscd_stat: '',
    mkop_cls_code: '110',
    exch_code: 'KRX',
    received_at: null,
    ...overrides,
  }
}

// ── 케이스 표 ────────────────────────────────────────────────────────────────
// 티커는 검사 대상 코드 문자열(55·57·00 등)을 포함하지 않게 골랐다.

const VI_INACTIVE: Array<[string, string]> = [
  ['N', '100001'],
  ['0', '100002'],
  ['', '100003'],
  ['(null)', '100004'],
  ['n', '100006'],
]
const VI_ACTIVE: Array<[string, string]> = [
  ['Y', '100010'],
  ['1', '100011'],
]

const STAT_LABELS: Array<[string, string, string]> = [
  ['51', '관리종목', '300001'],
  ['52', '투자위험', '300002'],
  ['53', '투자경고', '300003'],
  ['54', '투자주의', '300004'],
  ['59', '단기과열', '300009'],
]
const ALL_STAT_LABELS = ['관리종목', '투자위험', '투자경고', '투자주의', '단기과열']

const STAT_HIDDEN: Array<[string, string]> = [
  ['55', '312341'],
  ['57', '312342'],
  ['00', '312343'],
  ['', '312344'],
]

const DETAILS: MarketOpDetail[] = [
  ...VI_INACTIVE.map(([code, t]) => row(t, { vi_code: code })),
  ...VI_ACTIVE.map(([code, t]) => row(t, { vi_code: code })),
  // 거래정지
  row('200001', { halt_yn: 'Y', iscd_stat: '' }), // halt_yn 만
  row('200002', { halt_yn: 'N', iscd_stat: '58' }), // 종목상태 58 만
  row('200003', { halt_yn: 'Y', iscd_stat: '58' }), // 둘 다
  // 종목상태 표시 집합 (정지 아님)
  ...STAT_LABELS.map(([code, , t]) => row(t, { iscd_stat: code })),
  row('300201', { halt_yn: 'Y', iscd_stat: '51', halt_reason: '관리종목 지정' }), // 정지 + 관리
  // 종목상태 비표시 집합
  ...STAT_HIDDEN.map(([code, t]) => row(t, { iscd_stat: code })),
  // 정지 사유 null 토큰
  row('400001', { halt_yn: 'Y', halt_reason: '(null)' }),
  row('400002', { halt_yn: 'Y', halt_reason: '공시 (null) 확인 필요' }),
]

function makePayload(details: MarketOpDetail[]) {
  return {
    vi_active_count: 2,
    halt_active_count: 3,
    last_event_count: details.length,
    iscd_stat_active_count: 6,
    vi_active_sample: ['100010', '100011'],
    halt_active_sample: ['200001', '200002', '200003'],
    circuit_breaker: {
      suspected: false,
      reasons: [],
      halt_ratio: 0,
      halted: 0,
      observed: details.length,
      representative_mkop_cls_code: '110',
      halt_reasons_sample: [],
    },
    details,
  }
}

beforeEach(() => {
  server.use(
    http.get('*/api/logs/search', () =>
      HttpResponse.json({ success: true, data: { logs: [], has_more: false }, message: 'OK' }),
    ),
    http.get('*/api/realtime/market-operation', () =>
      HttpResponse.json({ success: true, data: makePayload(DETAILS), message: 'OK' }),
    ),
  )
})

afterEach(() => {
  server.resetHandlers()
})

async function renderAndGetRow(ticker: string): Promise<HTMLElement> {
  render(withProviders(<RealtimeHealth />))
  await waitFor(() => {
    expect(screen.getByTestId('realtime-health-card-market-operation')).toBeTruthy()
  })
  const card = screen.getByTestId('realtime-health-card-market-operation')
  return await within(card).findByTestId(`realtime-health-op-row-${ticker}`)
}

function countOccurrences(haystack: string, needle: string): number {
  return haystack.split(needle).length - 1
}

// ── (1) VI 배지 ─────────────────────────────────────────────────────────────

describe('cycle370 (1) — VI 배지는 활성 코드일 때만 (백엔드 _INACTIVE_VALUES 와 같은 집합)', () => {
  it.each(VI_INACTIVE)(
    'vi_code_when_%j_then_no_vi_badge_and_no_VI_text',
    async (_code, ticker) => {
      const r = await renderAndGetRow(ticker)
      expect(within(r).queryByTestId('realtime-health-op-vi-badge')).toBeNull()
      // 테스트 id 없이 그려진 「VI:N」 같은 글자도 없어야 한다
      expect(r.textContent ?? '').not.toMatch(/VI/)
      // null 토큰은 어떤 칸에서든 글자 그대로 새지 않는다
      expect(r.textContent ?? '').not.toContain('(null)')
    },
  )

  it.each(VI_ACTIVE)(
    'vi_code_when_%j_then_one_amber_vi_badge',
    async (_code, ticker) => {
      const r = await renderAndGetRow(ticker)
      const badges = within(r).getAllByTestId('realtime-health-op-vi-badge')
      expect(badges).toHaveLength(1)
      expect(badges[0].textContent ?? '').toContain('VI')
      expect(badges[0].className).toContain('amber')
      // VI 만 걸린 행에는 거래정지 배지가 없다
      expect(within(r).queryByTestId('realtime-health-op-halt-badge')).toBeNull()
    },
  )
})

// ── (2) 거래정지 배지 ───────────────────────────────────────────────────────

describe('cycle370 (2) — 거래정지 배지 = halt_yn Y 또는 종목상태 58, 행당 정확히 1개', () => {
  it.each([
    ['halt_yn_Y_only', '200001'],
    ['iscd_stat_58_with_halt_yn_N', '200002'],
    ['halt_yn_Y_and_iscd_stat_58', '200003'],
  ])('halt_when_%s_then_exactly_one_red_halt_badge', async (_label, ticker) => {
    const r = await renderAndGetRow(ticker)
    const badges = within(r).getAllByTestId('realtime-health-op-halt-badge')
    expect(badges).toHaveLength(1)
    expect(badges[0].textContent ?? '').toContain('거래정지')
    expect(badges[0].className).toContain('red')
    // 58 을 종목상태 배지로 한 번 더 그리지 않는다 — 「거래정지」 글자는 행에 한 번뿐
    expect(countOccurrences(r.textContent ?? '', '거래정지')).toBe(1)
    expect(within(r).queryByTestId('realtime-health-op-stat-badge')).toBeNull()
  })
})

// ── (3) 종목상태 배지 ───────────────────────────────────────────────────────

describe('cycle370 (3) — 종목상태 배지는 표시 집합 51·52·53·54·59 만 (58 은 거래정지 배지가 담당)', () => {
  it.each(STAT_LABELS)(
    'iscd_stat_when_%s_then_status_badge_%s',
    async (_code, label, ticker) => {
      const r = await renderAndGetRow(ticker)
      const badges = within(r).getAllByTestId('realtime-health-op-stat-badge')
      expect(badges).toHaveLength(1)
      expect(badges[0].textContent ?? '').toContain(label)
      // 정지가 아니므로 거래정지 배지는 없다 (51·59 를 정지로 넓게 읽지 않는다 — cycle368 사용자 결정)
      expect(within(r).queryByTestId('realtime-health-op-halt-badge')).toBeNull()
      expect(r.textContent ?? '').not.toContain('거래정지')
      // 다른 라벨이 섞이지 않는다 (코드↔라벨 오매핑 차단)
      for (const other of ALL_STAT_LABELS.filter((l) => l !== label)) {
        expect(r.textContent ?? '').not.toContain(other)
      }
    },
  )

  it.each(STAT_HIDDEN)(
    'iscd_stat_when_%j_then_nothing_rendered_for_status',
    async (code, ticker) => {
      const r = await renderAndGetRow(ticker)
      expect(within(r).queryByTestId('realtime-health-op-stat-badge')).toBeNull()
      const text = r.textContent ?? ''
      for (const l of ALL_STAT_LABELS) expect(text).not.toContain(l)
      expect(text).not.toContain('거래정지')
      // 원시 코드도 그리지 않는다 ('' 는 검사 불가라 건너뜀)
      if (code !== '') expect(text).not.toContain(code)
    },
  )

  it('iscd_stat_51_with_halt_yn_Y_then_one_halt_badge_and_one_관리종목_badge', async () => {
    const r = await renderAndGetRow('300201')
    expect(within(r).getAllByTestId('realtime-health-op-halt-badge')).toHaveLength(1)
    const stat = within(r).getAllByTestId('realtime-health-op-stat-badge')
    expect(stat).toHaveLength(1)
    expect(stat[0].textContent ?? '').toContain('관리종목')
  })
})

// ── (4) 정지 사유 null 토큰 ────────────────────────────────────────────────

describe('cycle370 (4) — 정지 사유 "(null)" 은 그리지 않는다 (정확일치만)', () => {
  it('halt_reason_when_exact_null_token_then_not_rendered_but_halt_badge_kept', async () => {
    const r = await renderAndGetRow('400001')
    expect(r.textContent ?? '').not.toContain('(null)')
    expect(within(r).getAllByTestId('realtime-health-op-halt-badge')).toHaveLength(1)
  })

  it('halt_reason_when_sentence_contains_null_token_then_rendered_verbatim', async () => {
    // 백엔드 N4 와 같은 규약 — 부분 치환은 실제 사유 문장을 깎는다
    const r = await renderAndGetRow('400002')
    expect(r.textContent ?? '').toContain('공시 (null) 확인 필요')
  })
})
