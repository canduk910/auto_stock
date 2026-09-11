/**
 * cycle282 Red — 장운영상태 화면 (`/market-state`) 행위 테스트 (명세 §7.2 FE1~FE18 · FE22).
 *
 * 명세 정본 = `_workspace/red/cycle282_market_state_spec.md`.
 * 이 파일이 작성된 시점에 `pages/MarketState.tsx` 는 **없다**. import 가 실패하는 것이
 * 이 사이클의 Red 다 — Green(frontend-dev)이 그 파일을 만들면 여기 단언들이 계약이 된다.
 *
 * ## 이 화면이 지켜야 하는 세 가지 (브리프 원칙)
 *
 * 1. **표와 커서는 한 응답에서 나온다.** 그래서 이 테스트는 `/api/market-state` 를
 *    **한 번만** 목한다. 표를 따로, 커서를 따로 부르는 구현은 이 목 아래에서 살 수 없다.
 * 2. **프론트는 행·시각·코드를 하드코딩하지 않는다.** 그래서 여기 기대값은 전부
 *    픽스처(`marketState.fixture.ts`)에서 **읽어** 만든다 — 이 파일 어디에도
 *    `'K3'`·`'01'`·`'09:00'` 같은 값을 직접 적지 않는다(정적 가드는
 *    `_ast_market_state_hardcode.test.ts` 가 따로 잠근다).
 * 3. **커서는 서버가 판정한다.** 화면은 `rel`·`row_id`·`seconds_to_next` 를 받아 그릴 뿐이다.
 *    FE9 는 `data-rel` 이 **서버 값 그대로**인지 보고, FE14 는 카운트다운이 0 에 닿았을 때
 *    다음 행을 스스로 계산하지 않고 **재조회 1회**만 하는지 본다.
 *
 * ## frontend-dev 와의 인터페이스 합의 (testid 는 명세 §5.3, 아래 둘은 이 파일이 추가)
 *
 * - `market-state-card-countdown-${market}` 에 **`data-seconds`**(남은 초, 정수 문자열).
 *   텍스트 서식은 화면 자유지만 남은 초는 기계가 읽을 수 있어야 FE14 가 감소를 잰다.
 * - `market-state-row-${rowId}` 에 `data-rel` · `data-market` · `data-confidence`(명세 §5.3).
 *   `data-confidence` 가 `"confirmed"` 가 아닌 행에는 **"확인 필요"** 문구가 그 행 안에 보인다.
 *
 * ## 목 변종
 *
 * 픽스처는 네 변종을 준다 — `AT_0835`(K1 ⊃ K2 동시 중첩) · `AT_1305`(평범한 정규장,
 * MSW 기본) · `AT_2030`(장 종료) · `PREVIEW`(09-14 미리보기). 하나로는 이 화면의 계약을
 * 못 잰다: 중첩·합집합은 08:35 에만, `seconds_to_next=null` 은 20:30 에만,
 * `markets=null`·`rel="unknown"` 은 미리보기에만 있다.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { http, HttpResponse, delay } from 'msw'
import type { ReactNode } from 'react'

import MarketState from '../MarketState'
import App from '../../App'
import { server } from '../../test/server'
import { wrap } from '../../test/factories'
import {
  MARKET_STATE_AT_0835,
  MARKET_STATE_AT_1305,
  MARKET_STATE_AT_2030,
  MARKET_STATE_PREVIEW,
} from '../../test/fixtures/marketState.fixture'
import type {
  MarketStateCursor,
  MarketStateData,
  OrderDivisionRow,
} from '../../test/fixtures/marketState.fixture'

const ENDPOINT = '*/api/market-state'
const LONG = { timeout: 10_000 }

/**
 * 컴포넌트가 선언한 `retry:` 는 그대로 살리되(그 값이 계약이다) 재시도 **지연만** 0 으로
 * 줄인다. 기본 지연(1s→2s)을 그대로 두면 에러 경로 테스트가 매번 3초를 앉아서 기다린다.
 */
function createClient() {
  return new QueryClient({
    defaultOptions: { queries: { retryDelay: 0, gcTime: 0, staleTime: 0 } },
  })
}

function withProviders(children: ReactNode, client: QueryClient) {
  return (
    <QueryClientProvider client={client}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  )
}

/** 한 변종을 응답으로 고정하고 화면을 띄운다. 호출 횟수를 세어 돌려준다. */
function mount(data: MarketStateData) {
  const calls = { n: 0 }
  server.use(
    http.get(ENDPOINT, () => {
      calls.n += 1
      return HttpResponse.json(wrap(data))
    }),
  )
  const client = createClient()
  const utils = render(withProviders(<MarketState />, client))
  return { ...utils, calls, client }
}

/** 첫 렌더가 끝날 때까지 기다린다(로딩 → 본문). */
async function mountAndSettle(data: MarketStateData) {
  const r = mount(data)
  await screen.findByTestId('market-state-page', {}, LONG)
  return r
}

function cursorOf(data: MarketStateData, market: string): MarketStateCursor {
  const markets = data.markets
  if (!markets) throw new Error(`markets 가 null 인 변종에는 커서가 없다: ${data.on_date}`)
  return markets[market]
}

function divisionOf(data: MarketStateData, code: string): OrderDivisionRow {
  const row = data.order_divisions.find((d) => d.code === code)
  if (!row) throw new Error(`카탈로그에 없는 코드: ${code}`)
  return row
}

/** `seconds_to_next` 만 바꾼 사본 — 카운트다운 계약을 짧은 시간 안에 재기 위한 seam. */
function withSecondsToNext(data: MarketStateData, seconds: number): MarketStateData {
  const markets = data.markets
  if (!markets) throw new Error('preview 변종에는 커서가 없다')
  const next: Record<string, MarketStateCursor> = {}
  for (const [market, cursor] of Object.entries(markets)) {
    next[market] = { ...cursor, seconds_to_next: seconds }
  }
  return { ...data, markets: next }
}

/** 사유 문구가 본문 텍스트든 툴팁 속성이든 화면에서 읽을 수 있는가. */
function noteIsReachable(note: string): boolean {
  if ((document.body.textContent ?? '').includes(note)) return true
  return Array.from(document.querySelectorAll('[title],[aria-label]')).some(
    (el) =>
      (el.getAttribute('title') ?? '').includes(note) ||
      (el.getAttribute('aria-label') ?? '').includes(note),
  )
}

afterEach(() => {
  vi.useRealTimers()
})

// ───────────────────────────────────────────────────────────────────────────
// FE1 · FE2 — 로딩 / 에러 / 재시도
// ───────────────────────────────────────────────────────────────────────────

describe('cycle282 FE1·FE2 — 로딩과 오류 분기', () => {
  it('FE1: 응답 전에는 로딩 표시가 보인다', async () => {
    server.use(
      http.get(ENDPOINT, async () => {
        await delay(50)
        return HttpResponse.json(wrap(MARKET_STATE_AT_1305))
      }),
    )
    render(withProviders(<MarketState />, createClient()))

    expect(await screen.findByTestId('market-state-loading')).toBeInTheDocument()
    await screen.findByTestId('market-state-page', {}, LONG)
    expect(screen.queryByTestId('market-state-loading')).not.toBeInTheDocument()
  })

  it('FE2: 500 이면 오류를 보이고, 재시도 버튼이 실제로 다시 부른다', async () => {
    let calls = 0
    let failing = true
    server.use(
      http.get(ENDPOINT, () => {
        calls += 1
        if (failing) return new HttpResponse(null, { status: 500 })
        return HttpResponse.json(wrap(MARKET_STATE_AT_1305))
      }),
    )
    render(withProviders(<MarketState />, createClient()))

    const error = await screen.findByTestId('market-state-error', {}, LONG)
    expect(error).toBeInTheDocument()
    // 서버 장애를 200 빈 화면으로 흡수하지 않는다(cycle266 fail-silent 재발 차단).
    expect(screen.queryByTestId('market-state-table')).not.toBeInTheDocument()

    const before = calls
    failing = false
    fireEvent.click(await screen.findByTestId('market-state-retry'))

    await screen.findByTestId('market-state-page', {}, LONG)
    expect(calls).toBeGreaterThan(before)
  })
})

// ───────────────────────────────────────────────────────────────────────────
// FE3 ~ FE8 — 현재 상태 카드
// ───────────────────────────────────────────────────────────────────────────

describe('cycle282 FE3~FE8 — 현재 상태 카드는 응답이 그린다', () => {
  it('FE3: 카드는 응답 `market_order` 개수·순서 그대로 렌더된다', async () => {
    const data = MARKET_STATE_AT_1305
    await mountAndSettle(data)

    const cards = data.market_order.map((m) => screen.getByTestId(`market-state-card-${m}`))
    expect(cards).toHaveLength(data.market_order.length)
    for (let i = 1; i < cards.length; i += 1) {
      const rel = cards[i - 1].compareDocumentPosition(cards[i])
      expect(
        rel & Node.DOCUMENT_POSITION_FOLLOWING,
        `${data.market_order[i - 1]} 카드가 ${data.market_order[i]} 보다 앞에 와야 한다`,
      ).toBeTruthy()
    }
  })

  it('FE4: 카드의 상태명·창·다음 행이 응답 값과 문자열 단위로 같다', async () => {
    const data = MARKET_STATE_AT_1305
    await mountAndSettle(data)

    for (const market of data.market_order) {
      const cursor = cursorOf(data, market)
      expect(screen.getByTestId(`market-state-card-name-${market}`).textContent).toContain(
        cursor.name_ko,
      )

      const card = screen.getByTestId(`market-state-card-${market}`)
      expect(card.getAttribute('data-phase')).toBe(cursor.phase)
      expect(card.getAttribute('data-tone')).toBe(cursor.tone)

      const window = screen.getByTestId(`market-state-card-window-${market}`).textContent ?? ''
      expect(window).toContain(cursor.window?.start ?? '')
      expect(window).toContain(cursor.window?.end ?? '')

      const nextText = screen.getByTestId(`market-state-card-next-${market}`).textContent ?? ''
      const nextRow = data.table.find((r) => r.row_id === cursor.next_row_id)
      expect(nextRow, '다음 행은 반드시 같은 표 안에 있다(M9)').toBeTruthy()
      expect(nextText).toContain(nextRow!.name_ko)
    }
  })

  it('FE5: 시장가 가능 배지는 `market_order_ok` 그대로 — NXT 는 항상 불가', async () => {
    const data = MARKET_STATE_AT_1305
    await mountAndSettle(data)

    for (const market of data.market_order) {
      const cursor = cursorOf(data, market)
      const badge = screen.getByTestId(`market-state-card-market-order-${market}`)
      expect(
        badge.getAttribute('data-ok'),
        `${market} 시장가 배지가 응답 market_order_ok 와 다르다`,
      ).toBe(String(cursor.market_order_ok))

      const canOrder = screen.getByTestId(`market-state-card-can-order-${market}`)
      expect(canOrder.getAttribute('data-ok')).toBe(String(cursor.can_order))
    }

    // 두 시장이 서로 다른 값이어야 이 단언이 의미를 가진다 — 표에서 그렇게 나온다.
    const values = data.market_order.map((m) => cursorOf(data, m).market_order_ok)
    expect(new Set(values).size, '픽스처가 시장가 가능/불가를 둘 다 담아야 한다').toBe(2)
  })

  it('FE6: 주문유형 칩은 `order_divisions` × 카탈로그 조인과 1:1', async () => {
    const data = MARKET_STATE_AT_1305
    await mountAndSettle(data)

    for (const market of data.market_order) {
      const cursor = cursorOf(data, market)
      const card = screen.getByTestId(`market-state-card-${market}`)

      const chips = within(card).getAllByTestId(
        (id) => id.startsWith(`market-state-card-division-${market}-`),
      )
      expect(chips).toHaveLength(cursor.order_divisions.length)

      for (const code of cursor.order_divisions) {
        const chip = screen.getByTestId(`market-state-card-division-${market}-${code}`)
        const text = chip.textContent ?? ''
        expect(text, `칩에 코드가 없다: ${code}`).toContain(code)
        expect(text, `칩에 이름이 없다: ${code}`).toContain(divisionOf(data, code).name_ko)
      }
    }
  })

  it('FE7: 08:35 동시 중첩 — 커서는 K1, 동시 창에 K2, 칩은 두 행의 합집합', async () => {
    const data = MARKET_STATE_AT_0835
    await mountAndSettle(data)

    const market = data.market_order[0]
    const cursor = cursorOf(data, market)

    // 픽스처가 실제로 중첩 변종인지 먼저 확인 — 아니면 이 테스트는 아무것도 안 막는다.
    expect(cursor.concurrent_row_ids.length, 'AT_0835 는 동시 중첩 변종이어야 한다').toBe(1)

    for (const rowId of cursor.concurrent_row_ids) {
      const chip = screen.getByTestId(`market-state-card-concurrent-${market}-${rowId}`)
      const row = data.table.find((r) => r.row_id === rowId)!
      expect(chip.textContent).toContain(row.name_ko)
    }

    // 합집합 — 커서 행 단독이 아니라 동시 행의 코드까지 전부 칩으로 보인다.
    const cursorRow = data.table.find((r) => r.row_id === cursor.row_id)!
    const onlyFromConcurrent = cursor.order_divisions.filter(
      (c) => !cursorRow.order_divisions.includes(c),
    )
    expect(
      onlyFromConcurrent.length,
      '동시 행에서만 오는 코드가 있어야 합집합 계약이 검증된다',
    ).toBeGreaterThan(0)
    for (const code of onlyFromConcurrent) {
      expect(screen.getByTestId(`market-state-card-division-${market}-${code}`)).toBeInTheDocument()
    }
  })

  it('FE8: 확인 필요 배지는 `confidence !== "confirmed"` 인 카드·행에만 붙는다', async () => {
    const data = MARKET_STATE_AT_1305
    await mountAndSettle(data)

    for (const market of data.market_order) {
      const cursor = cursorOf(data, market)
      const badge = screen.queryByTestId(`market-state-card-confidence-${market}`)
      if (cursor.confidence === 'confirmed') {
        expect(badge, `${market}: 확신 있는 커서에 확인 필요 배지가 붙었다`).toBeNull()
      } else {
        expect(badge, `${market}: 미확인 커서에 확인 필요 배지가 없다`).not.toBeNull()
        expect(badge!.getAttribute('data-level')).toBe(cursor.confidence)
      }
    }

    // 표 — 미확인 행에만 "확인 필요" 문구. 숨기지 않는다(브리프).
    const unconfirmed = data.table.filter((r) => r.confidence !== 'confirmed')
    expect(unconfirmed.length, '픽스처에 미확인 행이 있어야 이 단언이 산다').toBeGreaterThan(0)
    for (const row of data.table) {
      const el = screen.getByTestId(`market-state-row-${row.row_id}`)
      expect(el.getAttribute('data-confidence')).toBe(row.confidence)
      const marks = within(el).queryAllByText(/확인 필요/)
      if (row.confidence === 'confirmed') {
        expect(marks, `${row.row_id}: 확정 행에 확인 필요 배지가 붙었다`).toHaveLength(0)
      } else {
        expect(marks.length, `${row.row_id}: 미확인 행에 확인 필요 배지가 없다`).toBeGreaterThan(0)
      }
    }

    // 카드 확신이 떨어졌으면 그 사유(note)도 화면에 있다 — 배지만 띄우고 이유를 숨기지 않는다.
    // 본문 텍스트든 툴팁(title/aria-label)이든 어디든 좋다. 사라지는 것만 안 된다.
    for (const market of data.market_order) {
      const cursor = cursorOf(data, market)
      expect(cursor.confidence_notes.length).toBe(cursor.confidence === 'confirmed' ? 0 : 1)
      for (const note of cursor.confidence_notes) {
        expect(noteIsReachable(note), `${market}: 미확인 사유가 화면 어디에도 없다`).toBe(true)
      }
    }
  })
})

// ───────────────────────────────────────────────────────────────────────────
// FE9 ~ FE11 — 커서 표
// ───────────────────────────────────────────────────────────────────────────

describe('cycle282 FE9~FE11 — 표는 서버 판정(rel)으로만 그린다', () => {
  it('FE10: 행 수와 순서가 응답 `table` 과 같다', async () => {
    const data = MARKET_STATE_AT_1305
    await mountAndSettle(data)

    const table = screen.getByTestId('market-state-table')
    const rows = within(table).getAllByTestId((id) => /^market-state-row-[^-]+$/.test(id))
    expect(rows).toHaveLength(data.table.length)
    expect(rows.map((el) => el.getAttribute('data-testid'))).toEqual(
      data.table.map((r) => `market-state-row-${r.row_id}`),
    )
    for (const row of data.table) {
      expect(screen.getByTestId(`market-state-row-${row.row_id}`).getAttribute('data-market')).toBe(
        row.market,
      )
    }
  })

  it('FE9: `data-rel` 이 서버 값 그대로이고, past/current 가 시각적으로 구분된다', async () => {
    const data = MARKET_STATE_AT_1305
    await mountAndSettle(data)

    for (const row of data.table) {
      expect(
        screen.getByTestId(`market-state-row-${row.row_id}`).getAttribute('data-rel'),
        `${row.row_id}: rel 이 서버 값과 다르다 — 프론트가 시각으로 다시 계산했을 가능성`,
      ).toBe(row.rel)
    }

    const pick = (rel: string) => {
      const row = data.table.find((r) => r.rel === rel)
      expect(row, `픽스처에 rel=${rel} 행이 있어야 한다`).toBeTruthy()
      return screen.getByTestId(`market-state-row-${row!.row_id}`)
    }
    const past = pick('past')
    const current = pick('current')
    const upcoming = pick('upcoming')

    const cls = (el: HTMLElement) => new Set((el.className || '').split(/\s+/).filter(Boolean))
    const upcomingCls = cls(upcoming)

    const pastOnly = [...cls(past)].filter((c) => !upcomingCls.has(c))
    const currentOnly = [...cls(current)].filter((c) => !upcomingCls.has(c))
    expect(pastOnly.length, '지난 행이 다음 행과 똑같이 보인다 — 흐림 처리가 없다').toBeGreaterThan(0)
    expect(
      pastOnly.some((c) => c.includes('opacity')),
      `지난 행은 흐리게(opacity) 표시한다 — 실제 클래스: ${[...cls(past)].join(' ')}`,
    ).toBe(true)
    expect(currentOnly.length, '현재 행에 커서 강조가 없다').toBeGreaterThan(0)
  })

  it('FE11: 아직 시행 전인 코드는 지우지 않고 `pending` 배지로 보인다', async () => {
    const data = MARKET_STATE_AT_1305
    await mountAndSettle(data)

    const withPending = data.table.filter((r) => r.order_divisions_pending.length > 0)
    expect(
      withPending.length,
      '픽스처(09-11)에는 시행 전 코드가 있는 행이 있어야 한다 — 없으면 날짜 차원이 안 잡힌다',
    ).toBeGreaterThan(0)

    for (const row of data.table) {
      for (const code of row.order_divisions_pending) {
        expect(
          screen.getByTestId(`market-state-row-pending-${row.row_id}-${code}`),
        ).toBeInTheDocument()
      }
      for (const code of row.order_divisions) {
        expect(
          screen.getByTestId(`market-state-row-division-${row.row_id}-${code}`),
        ).toBeInTheDocument()
        expect(
          screen.queryByTestId(`market-state-row-pending-${row.row_id}-${code}`),
          `${row.row_id}: 유효한 코드가 시행 전으로 표시됐다`,
        ).toBeNull()
      }
    }
  })
})

// ───────────────────────────────────────────────────────────────────────────
// FE12 · FE13 — 주문유형 카탈로그 + 발견 문구
// ───────────────────────────────────────────────────────────────────────────

describe('cycle282 FE12·FE13 — 카탈로그와 발견 문구', () => {
  it('FE12: 카탈로그 행·셀이 응답 그대로이고 3상태가 모두 등장한다', async () => {
    const data = MARKET_STATE_AT_1305
    await mountAndSettle(data)

    const catalog = screen.getByTestId('market-state-catalog')
    const rows = within(catalog).getAllByTestId((id) => id.startsWith('market-state-catalog-row-'))
    expect(rows).toHaveLength(data.order_divisions.length)

    const seen = new Set<string>()
    for (const division of data.order_divisions) {
      const row = screen.getByTestId(`market-state-catalog-row-${division.code}`)
      expect(row.textContent).toContain(division.code)
      expect(row.textContent).toContain(division.name_ko)
      for (const exchange of data.exchange_order) {
        const cell = screen.getByTestId(
          `market-state-catalog-cell-${division.code}-${exchange}`,
        )
        const support = division.exchange_support[exchange]
        expect(
          cell.getAttribute('data-support'),
          `${division.code}/${exchange}: 미지원과 미확인은 다른 값이다`,
        ).toBe(support)
        seen.add(support)
      }
    }
    // `?`(미확인)를 빈칸(미지원)으로 접으면 브리프가 "숨기지 않는다" 고 못박은 항목이 사라진다.
    expect([...seen].sort()).toEqual([...data.vocab.support_levels].sort())
  })

  it('FE13: 발견 2건·보드 주석·미확인 주석이 응답에서 온다', async () => {
    const data = MARKET_STATE_AT_1305
    await mountAndSettle(data)

    data.findings.forEach((finding, i) => {
      expect(screen.getByTestId(`market-state-finding-${i}`).textContent).toContain(finding)
    })
    expect(screen.queryByTestId(`market-state-finding-${data.findings.length}`)).toBeNull()

    expect(screen.getByTestId('market-state-board-note').textContent).toContain(data.board_note)
    expect(screen.getByTestId('market-state-unconfirmed-note').textContent).toContain(
      data.unconfirmed_note,
    )
  })
})

// ───────────────────────────────────────────────────────────────────────────
// FE14 ~ FE16 — 카운트다운과 폴링 (원칙 3: 커서는 서버가 판정한다)
// ───────────────────────────────────────────────────────────────────────────

describe('cycle282 FE14~FE16 — 카운트다운은 스톱워치이지 시계가 아니다', () => {
  beforeEach(() => {
    // `shouldAdvanceTime` — MSW/fetch 가 쓰는 타이머까지 얼려 버리면 응답이 영원히 안 온다.
    vi.useFakeTimers({ shouldAdvanceTime: true })
  })

  it('FE14a: 1초가 지나면 남은 초가 줄어든다', async () => {
    const data = withSecondsToNext(MARKET_STATE_AT_1305, 120)
    const market = data.market_order[0]
    server.use(http.get(ENDPOINT, () => HttpResponse.json(wrap(data))))
    render(withProviders(<MarketState />, createClient()))
    await screen.findByTestId('market-state-page', {}, LONG)

    const read = () =>
      Number(
        screen.getByTestId(`market-state-card-countdown-${market}`).getAttribute('data-seconds'),
      )
    const first = read()
    // 렌더까지 흐른 수 ms 때문에 119 가 나올 수 있다(floor/ceil 은 구현 자유).
    expect(Number.isFinite(first), 'data-seconds 가 숫자가 아니다').toBe(true)
    expect(first).toBeGreaterThan(115)
    expect(first).toBeLessThanOrEqual(120)

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2_000)
    })
    await waitFor(() => expect(read()).toBeLessThan(first))
  })

  it('FE14b: 0 에 닿으면 다음 행을 스스로 계산하지 않고 재조회를 **1회만** 한다', async () => {
    // 첫 응답만 2초, 이후는 원래 값 — 재조회가 다시 0 으로 떨어져 폭주하는 것을 막는다.
    const short = withSecondsToNext(MARKET_STATE_AT_1305, 2)
    let calls = 0
    server.use(
      http.get(ENDPOINT, () => {
        calls += 1
        return HttpResponse.json(wrap(calls === 1 ? short : MARKET_STATE_AT_1305))
      }),
    )
    render(withProviders(<MarketState />, createClient()))
    await screen.findByTestId('market-state-page', {}, LONG)
    expect(calls).toBe(1)

    await act(async () => {
      await vi.advanceTimersByTimeAsync(6_000)
    })

    await waitFor(() => expect(calls).toBe(2))
    // 6초 동안 틱마다 refetch 했다면 여기서 2 를 크게 넘는다.
    expect(calls, '카운트다운 0 에서 재조회가 폭주한다').toBe(2)
  })

  it('FE15: `seconds_to_next === null` 이면 카운트다운 대신 "오늘 장 종료"', async () => {
    const data = MARKET_STATE_AT_2030
    server.use(http.get(ENDPOINT, () => HttpResponse.json(wrap(data))))
    render(withProviders(<MarketState />, createClient()))
    await screen.findByTestId('market-state-page', {}, LONG)

    for (const market of data.market_order) {
      const cursor = cursorOf(data, market)
      expect(cursor.seconds_to_next, 'AT_2030 은 장 종료 변종이어야 한다').toBeNull()
      expect(screen.queryByTestId(`market-state-card-countdown-${market}`)).toBeNull()
      const card = screen.getByTestId(`market-state-card-${market}`)
      expect(within(card).getAllByText(/오늘 장 종료/).length).toBeGreaterThan(0)
      // 내일로 굴리지 않는다 — 순수 함수는 내일이 거래일인지 모른다.
      expect(card.getAttribute('data-tone')).toBe(cursor.tone)
    }
  })

  it('FE16: 30초 폴링 — 30초를 지나면 요청이 한 번 더 나간다', async () => {
    let calls = 0
    server.use(
      http.get(ENDPOINT, () => {
        calls += 1
        return HttpResponse.json(wrap(MARKET_STATE_AT_1305))
      }),
    )
    render(withProviders(<MarketState />, createClient()))
    await screen.findByTestId('market-state-page', {}, LONG)
    expect(calls).toBe(1)

    await act(async () => {
      await vi.advanceTimersByTimeAsync(31_000)
    })
    await waitFor(() => expect(calls).toBeGreaterThanOrEqual(2))
  })
})

// ───────────────────────────────────────────────────────────────────────────
// FE17 · FE18 — 미리보기 / 휴장일 3상태
// ───────────────────────────────────────────────────────────────────────────

describe('cycle282 FE17·FE18 — 미리보기와 휴장일 "모른다"', () => {
  it('FE17: `markets: null` 이면 카드 대신 미리보기 배너 ∧ 모든 rel 이 unknown', async () => {
    const data = MARKET_STATE_PREVIEW
    expect(data.preview, 'PREVIEW 변종은 preview=true 여야 한다').toBe(true)
    expect(data.markets).toBeNull()
    await mountAndSettle(data)

    expect(screen.getByTestId('market-state-preview-banner')).toBeInTheDocument()
    for (const market of data.market_order) {
      expect(
        screen.queryByTestId(`market-state-card-${market}`),
        '다른 날짜를 보는 중에 "지금" 커서 카드를 그리면 화면이 거짓말을 한다',
      ).toBeNull()
    }
    for (const row of data.table) {
      const el = screen.getByTestId(`market-state-row-${row.row_id}`)
      expect(el.getAttribute('data-rel')).toBe('unknown')
    }
    // 표는 그 날짜 것이다 — 09-14 에만 있는 행이 보이고, 폐지된 행은 없다.
    const today = MARKET_STATE_AT_1305.table.map((r) => r.row_id)
    const preview = data.table.map((r) => r.row_id)
    expect(preview.filter((id) => !today.includes(id)).length).toBeGreaterThan(0)
    expect(today.filter((id) => !preview.includes(id)).length).toBeGreaterThan(0)
  })

  it('FE18: `is_trading_day` 3상태 — true/false/null 이 각각 다른 배지가 된다', async () => {
    const base = MARKET_STATE_AT_1305

    const cases: { value: boolean | null; source: string; expected: string }[] = [
      { value: true, source: 'kis', expected: 'true' },
      { value: false, source: 'kis', expected: 'false' },
      { value: null, source: 'unknown', expected: 'unknown' },
    ]

    for (const c of cases) {
      const data: MarketStateData = {
        ...base,
        is_trading_day: c.value,
        trading_day_source: c.source,
      }
      const { unmount } = await mountAndSettle(data)
      const badge = screen.getByTestId('market-state-trading-day-badge')
      expect(
        badge.getAttribute('data-value'),
        'null(모른다)을 개장/휴장으로 접으면 M10 위반이다',
      ).toBe(c.expected)
      if (c.value === null) {
        expect(badge.textContent).toContain('확인 불가')
      }
      unmount()
    }
  })

  it('as_of 는 KST 로 표시된다 (브라우저 로컬타임 금지)', async () => {
    const data = MARKET_STATE_AT_1305
    await mountAndSettle(data)
    const text = screen.getByTestId('market-state-asof').textContent ?? ''
    // 픽스처의 as_of 는 `2026-09-11T13:05:22+09:00`. 로컬타임으로 찍으면 TZ 가 KST 가 아닌
    // 환경(CI=UTC)에서 다른 시각이 나온다.
    expect(text).toContain(data.as_of_kst.slice(0, 10))
    expect(text).toContain(data.as_of_kst.slice(11, 19))
  })
})

// ───────────────────────────────────────────────────────────────────────────
// FE22 — 메뉴와 경로
// ───────────────────────────────────────────────────────────────────────────

describe('cycle282 FE22 — 신규 메뉴 항목과 경로', () => {
  it('`/market-state` 로 진입하면 App 이 이 페이지를 렌더한다', async () => {
    server.use(http.get(ENDPOINT, () => HttpResponse.json(wrap(MARKET_STATE_AT_1305))))
    const client = createClient()
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={['/market-state']}>
          <App />
        </MemoryRouter>
      </QueryClientProvider>,
    )
    expect(await screen.findByTestId('market-state-page', {}, LONG)).toBeInTheDocument()
  }, 20_000)

  it('나브에 장운영상태 링크가 **한 개** 있고 `/market-state` 를 가리킨다', async () => {
    server.use(http.get(ENDPOINT, () => HttpResponse.json(wrap(MARKET_STATE_AT_1305))))
    render(
      <QueryClientProvider client={createClient()}>
        <MemoryRouter initialEntries={['/market-state']}>
          <App />
        </MemoryRouter>
      </QueryClientProvider>,
    )
    await screen.findByTestId('market-state-page', {}, LONG)

    const links = screen
      .getAllByRole('link')
      .filter((el) => el.getAttribute('href') === '/market-state')
    // PC 가로 메뉴 1개 — 모바일 드로어는 닫혀 있어 렌더되지 않는다.
    expect(links.length, '나브 항목이 없거나 중복 등록됐다').toBe(1)
    expect(links[0].textContent?.trim()).toBe('장운영상태')
  }, 20_000)
})

// ───────────────────────────────────────────────────────────────────────────
// FE23 — 카탈로그 3상태의 **보이는** 글리프 (적대 검증 지적 2)
//
// FE12 는 셀의 `data-support` 속성만 봤다. 그래서 `SUPPORT_GLYPH.unknown` 을 빈 문자열로
// 바꾸면 **미확인 칸과 미지원 칸이 화면상 완전히 같아지는데도** 컴포넌트 746 · e2e 42 가
// 전부 초록이었다. SOR 열의 27~29·41~47 이 바로 그 칸이다 — "우리가 모른다" 는 사실을
// 화면이 말해야 하는 자리이고, 그 말이 사라지면 사용자는 "지원하지 않는다" 로 읽는다.
//
// 글리프 문자열은 이 파일에 적지 않는다. 적는 순간 테스트가 화면이 아니라 자기 자신을
// 검사하게 되고, 화면과 함께 고치면 같이 틀린다. 대신 **성질**로 잠근다 —
// 세 상태가 서로 다르게 보이고, "지원" 과 "미확인" 은 빈칸이 아니며, 빈칸은 "미지원"
// 하나뿐이다(빈칸 = 미지원은 명세 §5.3 이 못박은 계약이다).
// ───────────────────────────────────────────────────────────────────────────

describe('cycle282 FE23 — 카탈로그 3상태는 화면에서 서로 다르게 보인다', () => {
  it('세 상태의 보이는 텍스트가 서로 다르고, "모른다" 는 빈칸이 아니다', async () => {
    const data = MARKET_STATE_AT_1305
    await mountAndSettle(data)

    // 상태 → 그 상태 셀들의 보이는 텍스트. 같은 상태가 서로 다르게 보이면 그것도 결함이다.
    const textByLevel = new Map<string, string>()
    for (const division of data.order_divisions) {
      for (const exchange of data.exchange_order) {
        const cell = screen.getByTestId(
          `market-state-catalog-cell-${division.code}-${exchange}`,
        )
        const level = cell.getAttribute('data-support') ?? ''
        const text = (cell.textContent ?? '').trim()
        const prev = textByLevel.get(level)
        expect(
          prev === undefined || prev === text,
          `같은 상태 '${level}' 인데 셀마다 다르게 보인다: ${JSON.stringify(prev)} vs ${JSON.stringify(text)}`,
        ).toBe(true)
        textByLevel.set(level, text)
      }
    }

    // 세 상태가 실제로 한 화면에 다 떠야 이 검사가 공허하지 않다.
    expect([...textByLevel.keys()].sort()).toEqual([...data.vocab.support_levels].sort())

    const texts = [...textByLevel.values()]
    expect(
      new Set(texts).size,
      `세 상태가 같은 모습으로 보인다 — ${JSON.stringify([...textByLevel])}. ` +
        '미확인을 미지원과 같은 칸으로 접으면 "모른다" 가 "안 된다" 로 전달된다',
    ).toBe(texts.length)

    const shown = textByLevel.get('yes') ?? ''
    const unknown = textByLevel.get('unknown') ?? ''
    const missing = textByLevel.get('no') ?? ''

    expect(shown.length, '"지원" 칸이 비어 있다 — 지원 여부를 화면이 말하지 못한다').toBeGreaterThan(0)
    expect(
      unknown.length,
      '"확인 필요" 칸이 비어 있다 — 미지원 칸과 구별되지 않는다(브리프가 못박은 "숨기지 않는다" 위반)',
    ).toBeGreaterThan(0)
    // 빈칸은 "미지원" 하나뿐이다(명세 §5.3). 여기에 글리프를 주면 위 distinct 검사가 잡는다.
    expect(missing, '"미지원" 은 빈칸이라는 계약이다').toBe('')
  })
})

// ───────────────────────────────────────────────────────────────────────────
// FE24 — 실패 네 갈래를 한 빨간 박스로 뭉개지 않는다 (적대 검증 지적 6)
//
// 라우트는 404(그 날짜에 행 0) · 422(on_date 형식·범위) · 500(오늘 표가 빈 데이터 결함) ·
// 그리고 연결 끊김을 **구분해** 보낸다. 화면이 넷을 같은 톤으로 그리면 "그 날짜엔 원래
// 행이 없다" 가 "서버가 고장났다" 로 읽히고, 반대로 진짜 장애가 안내처럼 보인다.
// cycle266(종목마스터 일봉 탭)이 404 안내와 500 오류를 같은 문구로 보여 진짜 DB 장애를
// 3개월 은폐한 것이 정확히 이 뭉갬이다.
// ───────────────────────────────────────────────────────────────────────────

/** 응답 하나를 고정하고 화면을 띄운다(로딩 완료를 기다리지 않는다 — 실패 경로 전용). */
function mountWithStatus(status: number, body: unknown = null) {
  server.use(
    http.get(ENDPOINT, () =>
      body === null
        ? new HttpResponse(null, { status })
        : HttpResponse.json(body, { status }),
    ),
  )
  return render(withProviders(<MarketState />, createClient()))
}

describe('cycle282 FE24 — 안내와 오류는 다른 톤이다', () => {
  it('404(그 날짜에 행 0)는 **안내**다 — 오류 박스가 아니라 안내 박스', async () => {
    const detail = 'no_effective_rows'
    const { unmount } = mountWithStatus(404, { detail })

    const notice = await screen.findByTestId('market-state-notice', {}, LONG)
    expect(notice).toBeInTheDocument()
    expect(screen.queryByTestId('market-state-error')).toBeNull()
    expect(notice.getAttribute('data-status')).toBe('404')
    // 서버가 붙인 사유는 지우지 않고 그대로 보인다.
    expect(screen.getByTestId('market-state-failure-detail').textContent).toContain(detail)
    // 안내든 오류든 되돌릴 길은 남는다.
    expect(screen.getByTestId('market-state-retry')).toBeInTheDocument()
    unmount()
  })

  it.each([
    ['422 (on_date 형식·범위 위반 — 우리가 보낸 값이 틀렸다)', 422],
    ['500 (오늘 표가 비었다 — 데이터 결함)', 500],
  ])('%s 는 **오류**다', async (_label, status) => {
    const { unmount } = mountWithStatus(status)

    const error = await screen.findByTestId('market-state-error', {}, LONG)
    expect(error).toBeInTheDocument()
    expect(
      screen.queryByTestId('market-state-notice'),
      '오류를 안내 톤으로 그리면 진짜 장애가 조용해진다(cycle266 재발)',
    ).toBeNull()
    expect(error.getAttribute('data-status')).toBe(String(status))
    unmount()
  })

  it('연결이 끊기면(응답 없음) **오류**다 — 상태 코드가 없어도 안내로 접지 않는다', async () => {
    server.use(http.get(ENDPOINT, () => HttpResponse.error()))
    const { unmount } = render(withProviders(<MarketState />, createClient()))

    const error = await screen.findByTestId('market-state-error', {}, LONG)
    expect(error).toBeInTheDocument()
    expect(screen.queryByTestId('market-state-notice')).toBeNull()
    expect(error.getAttribute('data-status')).toBe('')
    unmount()
  })

  it('안내 박스와 오류 박스의 스타일이 실제로 다르다', async () => {
    const first = mountWithStatus(404, { detail: 'no_effective_rows' })
    const noticeClass = (await screen.findByTestId('market-state-notice', {}, LONG)).className
    const noticeText = screen.getByTestId('market-state-notice').textContent ?? ''
    first.unmount()

    const second = mountWithStatus(500)
    const errorClass = (await screen.findByTestId('market-state-error', {}, LONG)).className
    const errorText = screen.getByTestId('market-state-error').textContent ?? ''
    second.unmount()

    expect(
      noticeClass,
      '안내와 오류가 같은 색이면 화면은 둘을 구분해 말하지 않는 것이다',
    ).not.toBe(errorClass)
    expect(noticeText).not.toBe(errorText)
  })

  it('200 인데 휴장일을 모르면 오류가 아니라 **안내 배지**다 — 표는 그대로 그린다', async () => {
    const base = MARKET_STATE_AT_1305

    const { unmount: unmountKnown } = await mountAndSettle({
      ...base,
      is_trading_day: true,
      trading_day_source: 'kis',
    })
    const knownClass = screen.getByTestId('market-state-trading-day-badge').className
    unmountKnown()

    const { unmount } = await mountAndSettle({
      ...base,
      is_trading_day: null,
      trading_day_source: 'unknown',
    })
    // 휴장일 조회 실패는 응답 200 이다 — 표는 코드 상수라 살아 있다.
    expect(screen.queryByTestId('market-state-error')).toBeNull()
    expect(screen.queryByTestId('market-state-notice')).toBeNull()
    expect(screen.getByTestId('market-state-table')).toBeInTheDocument()

    const badge = screen.getByTestId('market-state-trading-day-badge')
    expect(badge.getAttribute('data-value')).toBe('unknown')
    expect(
      badge.className,
      '"모른다" 배지가 "개장" 배지와 같은 색이면 모름이 화면에서 사라진다',
    ).not.toBe(knownClass)
    unmount()
  })
})
