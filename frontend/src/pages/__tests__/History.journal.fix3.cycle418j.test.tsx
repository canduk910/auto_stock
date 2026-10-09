/**
 * cycle418-J Red — 거래일지 화면 사소한 결함 회귀(프론트 몫).
 *
 * 원문 = 메인 세션 scratchpad `c418/journal_verdict.md` 「새 결함 (모두 하)」 A·B·C +
 * 「워크리스트 후속」 1(#5 남은 몫)·7(보유 카드 net_rate_pct). 백엔드 몫(#5 `stop_kind`
 * 적재·exits_na·8 BFB 문구·D 회귀)은 `tests/unit/engine/test_cycle418j_journal_view_fixes.py`.
 *
 * | # | 결함 → 계약 |
 * |---|---|
 * | A | 체결 조회 실패 등으로 `costs.paid_total=null` 인데 `costs.na=null` 이면 상태·배분 칩이 그대로
 * |   | 보여 "모르지만 확정됨" 처럼 모순됐다 — paid_total 을 알 때만 칩을 보이고 모르면 `lookup_failed` |
 * | B | 체결 조회 실패로 `exits=[]` 가 되면 「청산이 없다」(정상)와 구분 없이 아무 표시도 없었다 —
 * |   | `exits_na` 가 서면 배지를 보인다 |
 * | C | 「발동선 4,827계산」·「손절 미발동—」·「종가 5/5일락」 처럼 문장·숫자와 칩·배지가 띄어쓰기
 * |   | 없이 붙었다 + 락 칩에 툴팁이 없었다 |
 * | #5 남은 몫 | 유효선이 `stop_kind="hard_pct"`(고정% 근사)면 [근사] 표시가 붙는다 |
 * | 7 | 보유 카드의 net 조회가 실패해도(순손익은 모름 배지, 비율은 아무 것도 안 보임) NaN·깨진
 * |   | 표시가 없다 |
 */
import { beforeEach, describe, expect, it } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'

import { server } from '../../test/server'
import { wrap } from '../../test/factories'
import { TestProviders } from '../../test/providers'
import {
  JOURNAL_ANCHOR_BFB as BFB,
  JOURNAL_ANCHOR_OPEN as OPEN,
  JOURNAL_ANCHOR_VB as VB,
  JOURNAL_FIXTURE,
} from '../../test/fixtures/journal.fixture'
import History from '../History'

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Json = any

const clone = (): Json => JSON.parse(JSON.stringify(JOURNAL_FIXTURE))

/** 결정론적 in-memory localStorage(`History.journal.cycle413.test.tsx` 와 같은 방식). */
function installStorage(): void {
  let store: Record<string, string> = {}
  const mock = {
    getItem: (k: string) => (k in store ? store[k] : null),
    setItem: (k: string, v: string) => void (store[k] = String(v)),
    removeItem: (k: string) => void delete store[k],
    clear: () => void (store = {}),
    key: (i: number) => Object.keys(store)[i] ?? null,
    get length() {
      return Object.keys(store).length
    },
  } as unknown as Storage
  Object.defineProperty(window, 'localStorage', { value: mock, configurable: true, writable: true })
  Object.defineProperty(globalThis, 'localStorage', { value: mock, configurable: true, writable: true })
}

beforeEach(() => {
  installStorage()
})

function setup(fixture: Json = clone()) {
  server.use(
    http.get('/api/history/journal', () => HttpResponse.json(wrap(fixture))),
    http.put('/api/history/journal/notes/:id', async () => HttpResponse.json(wrap(null))),
  )
  return render(
    <TestProviders>
      <History />
    </TestProviders>,
  )
}

async function openJournal(anchor: string): Promise<void> {
  await userEvent.click(screen.getByTestId('history-tab-journal'))
  await screen.findByTestId(`journal-card-${anchor}`)
}

const card = (anchor: string) => screen.getByTestId(`journal-card-${anchor}`)

function cardWith(fixture: Json, anchor: string): Json {
  return fixture.cards.find((c: Json) => c.anchor_trade_id === anchor)
}

// ════════════════════════════════════════════════════════════════════════════
// A — paid_total=null 이면 상태·배분 칩을 감추고 조회 실패 배지를 보인다
// ════════════════════════════════════════════════════════════════════════════
describe('cycle418-J A — 비용 합계를 모르면 상태 칩을 보이지 않는다', () => {
  it('A1: paid_total 이 null 이면 「조회 실패」 배지가 뜨고 확정/배분 칩이 없다', async () => {
    const fixture = clone()
    const bfb = cardWith(fixture, BFB)
    bfb.costs.paid_total = null
    bfb.costs.allocated = true
    setup(fixture)
    await openJournal(BFB)
    const costs = within(card(BFB)).getByTestId('journal-cost-total')
    expect(costs.textContent).toContain('조회 실패')
    expect(within(costs).getByTestId('journal-na-lookup_failed')).toBeInTheDocument()
    expect(costs.textContent).not.toContain('정산')
    expect(costs.textContent).not.toContain('배분')
  })

  it('A2 (가드): paid_total 을 알면 지금처럼 숫자와 상태 칩이 함께 보인다', async () => {
    setup()
    await openJournal(BFB)
    const costs = within(card(BFB)).getByTestId('journal-cost-total')
    expect(costs.textContent).toContain('2,536')
    expect(costs.textContent).toContain('정산')
  })
})

// ════════════════════════════════════════════════════════════════════════════
// B — exits=[] 가 체결 조회 실패일 때만 「조회 실패」 배지를 보인다
// ════════════════════════════════════════════════════════════════════════════
describe('cycle418-J B — 체결 조회 실패로 exits 가 비면 표시 없이 사라지지 않는다', () => {
  it('B1: exits_na="lookup_failed" 면 청산 영역에 조회 실패 배지가 선다', async () => {
    const fixture = clone()
    const bfb = cardWith(fixture, BFB)
    bfb.exits = []
    bfb.exits_na = 'lookup_failed'
    setup(fixture)
    await openJournal(BFB)
    expect(within(card(BFB)).getByTestId('journal-exits-na')).toHaveTextContent('조회 실패')
  })

  it('B2 (가드): 정상 보유 카드는(exits_na=null) 조회 실패 배지가 없다', async () => {
    setup()
    await openJournal(OPEN)
    expect(within(card(OPEN)).queryByTestId('journal-exits-na')).toBeNull()
  })
})

// ════════════════════════════════════════════════════════════════════════════
// C — 띄어쓰기 3곳 + 락 칩 툴팁
// ════════════════════════════════════════════════════════════════════════════
describe('cycle418-J C — 문장·숫자와 칩·배지 사이 띄어쓰기, 락 칩 툴팁', () => {
  it('C1: 「손절 미발동」 뒤 모름 배지 사이에 공백이 있다', async () => {
    const fixture = clone()
    const vb = cardWith(fixture, VB)
    vb.exits[0].effective_line = null
    vb.exits[0].line_na = 'unknown'
    setup(fixture)
    await openJournal(VB)
    const exitLine = within(card(VB)).getByTestId('journal-exit-line')
    expect(exitLine.textContent).toContain('손절 미발동 —')
    expect(exitLine.textContent).not.toContain('미발동—')
  })

  it('C2: 발동선 숫자 뒤 출처 칩 사이에 공백이 있다', async () => {
    const fixture = clone()
    const vb = cardWith(fixture, VB)
    vb.exits[0].line_role = 'fired'
    vb.exits[0].fired_line = 97000
    vb.exits[0].fired_src = 'derived'
    setup(fixture)
    await openJournal(VB)
    const exitLine = within(card(VB)).getByTestId('journal-exit-line')
    expect(exitLine.textContent).toContain('97,000 계산')
    expect(exitLine.textContent).not.toContain('000계산')
  })

  it('C3: 「종가 n/n일」 뒤 락 칩 사이에 공백이 있고 칩에 툴팁이 있다', async () => {
    setup()
    await openJournal(BFB)
    const closesLine = within(card(BFB)).getByTestId('journal-excursion-closes')
    expect(closesLine.textContent).toBe('종가 3/3일 락')
    const lockChip = within(closesLine).getByText('락')
    expect(lockChip).toHaveAttribute('title', '락 — 수정주가 미보정')
  })
})

// ════════════════════════════════════════════════════════════════════════════
// #5 남은 몫 — hard_pct 유효선에 [근사] 표시
// ════════════════════════════════════════════════════════════════════════════
describe('cycle418-J #5 — 유효선이 고정% 근사면 [근사] 가 붙는다', () => {
  it('5-1: stop_kind=hard_pct 면 [근사] 가 보인다', async () => {
    const fixture = clone()
    const vb = cardWith(fixture, VB)
    vb.exits[0].line_role = 'fired'
    vb.exits[0].fired_line = null
    vb.exits[0].effective_line = 97000
    vb.exits[0].stop_kind = 'hard_pct'
    setup(fixture)
    await openJournal(VB)
    const exitLine = within(card(VB)).getByTestId('journal-exit-line')
    expect(exitLine.textContent).toContain('유효선 97,000')
    expect(exitLine.textContent).toContain('[근사]')
  })

  it('5-2 (가드): stop_kind=effective 면 [근사] 가 없다', async () => {
    const fixture = clone()
    const vb = cardWith(fixture, VB)
    vb.exits[0].line_role = 'fired'
    vb.exits[0].fired_line = null
    vb.exits[0].effective_line = 97000
    vb.exits[0].stop_kind = 'effective'
    setup(fixture)
    await openJournal(VB)
    const exitLine = within(card(VB)).getByTestId('journal-exit-line')
    expect(exitLine.textContent).toContain('유효선 97,000')
    expect(exitLine.textContent).not.toContain('[근사]')
  })
})

// ════════════════════════════════════════════════════════════════════════════
// 7 — 보유 카드 net 조회 실패 — NaN 없음, 모름 배지만
// ════════════════════════════════════════════════════════════════════════════
describe('cycle418-J 7 — 보유 카드 net 조회 실패 시 표시', () => {
  it('7: net_krw/net_rate_pct 가 null 이어도 NaN 없이 모름 배지 + 세전 값만 보인다', async () => {
    const fixture = clone()
    const open = cardWith(fixture, OPEN)
    open.pnl.gross_krw = 12000
    open.pnl.gross_rate_pct = 2.4
    open.pnl.net_krw = null
    open.pnl.net_rate_pct = null
    open.pnl.net_na = 'lookup_failed'
    setup(fixture)
    await openJournal(OPEN)
    const head = within(card(OPEN)).getByTestId('journal-head-pnl')
    expect(head.textContent).not.toMatch(/NaN/)
    expect(within(head).getByTestId('journal-na-lookup_failed')).toBeInTheDocument()
    expect(head.textContent).toContain('+12,000원')
  })
})
