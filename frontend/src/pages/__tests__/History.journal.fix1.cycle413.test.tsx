/**
 * cycle413 보완 1차 Red — 거래일지 탭 화면 결함 회귀(판정 원문 = scratchpad `c413/fix/verdict1.md` #2·#3·#4·#6·#7·#12).
 *
 * 명세 = `_workspace/red/cycle413/journal_view_spec.md` 5절(빈칸 표시)·8절(화면) · 계약 = `journal_view_contract.md` 4절.
 * 응답 = `src/test/fixtures/journal.fixture.ts` 를 테스트마다 복제해 고친 것(키는 그대로 — shape.json).
 *
 * | # | 결함 → 계약 |
 * |---|---|
 * | M1 (#2) | 메모 — **상태형 MSW**(PUT 이 다음 GET 에 반영)로: 바뀐 것 없으면 저장 버튼 꺼짐 · 저장 → 다른 탭 → 돌아와도 저장한 값 · 빈 body PUT 0(서버 메모가 안 지워진다) · 저장 성공이 일지 캐시를 다시 읽게 하되 편집 중인 다른 카드 입력은 덮지 않는다. QueryClient 는 운영과 같은 캐시(`gcTime` 5분·`staleTime` 3초) — 테스트 기본(`gcTime 0`)은 탭을 오갈 때마다 새로 받아 결함을 가린다 |
 * | M2 (#3) | 페이지 넘김 — `journal-page-info`(「n/m」) · `journal-page-prev`/`journal-page-next` · 요청 `page` · 필터를 바꾸면 1쪽으로 |
 * | M3 (#4) | `line_role=null`(사유 코드 없음) 청산 줄은 「손절 미발동」 을 단정하지 않고 빈칸 배지만 |
 * | M4 (#6) | 보유 중 분할 매도 — 제목 「분할 매도」(「청산」 아님) · 머리 아래 「분할 실현 세후 +x」 |
 * | M5 (#7) | 출처 칩 — 발동선 `fired_src`(스냅샷·계산) · 판단가 `judge.src`(역산·복원(AI평가)) |
 * | M6 (#12) | 표시 묶음 — 빈칸 배지 툴팁(「모름 — …」) · 문장과 출처 칩 사이 띄움 · 제목(익절 목표·일별 종가·메모) · 익절 청산 줄 목표가(발동선 = 목표) · 당일 거래 「당일」 · 보유 중 「낸 비용」 · 400px 「필터」 버튼이 접고 편다 · 경로 꼬리 한 번만 |
 */
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { QueryClient } from '@tanstack/react-query'

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

let requests: URL[] = []
let puts: Array<{ id: string; body: string }> = []
let notes: Record<string, string> = {}

/** 운영과 같은 캐시 수명 — 탭을 오가도 캐시가 살아 있다(frontend/CLAUDE.md QueryClient 기본값). */
function prodLikeClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, staleTime: 3000, gcTime: 5 * 60 * 1000 },
      mutations: { retry: false },
    },
  })
}

/**
 * 상태형 MSW — PUT 한 메모가 다음 GET 의 카드 `note` 에 그대로 실린다(실 라우트와 같다: 공백만 = 삭제 → data null).
 * `pages` 를 주면 요청 `page` 에 맞는 응답을 돌려준다.
 */
function setup(opts: { fixture?: Json; pages?: Record<string, Json>; client?: QueryClient } = {}) {
  requests = []
  puts = []
  const base = opts.fixture ?? clone()
  notes = {}
  for (const c of base.cards) if (c.note) notes[c.anchor_trade_id] = c.note.body
  server.use(
    http.get('/api/history/journal', ({ request }) => {
      const url = new URL(request.url)
      requests.push(url)
      const src: Json = opts.pages ? opts.pages[url.searchParams.get('page') ?? '1'] ?? base : base
      const body: Json = JSON.parse(JSON.stringify(src))
      for (const c of body.cards) {
        c.note = c.anchor_trade_id in notes
          ? { body: notes[c.anchor_trade_id], updated_at: '2026-10-09T10:00:01+09:00' }
          : null
      }
      return HttpResponse.json(wrap(body))
    }),
    http.put('/api/history/journal/notes/:id', async ({ request, params }) => {
      const id = String(params.id)
      const { body } = (await request.json()) as { body: string }
      puts.push({ id, body })
      const trimmed = body.trim()
      if (trimmed === '') {
        delete notes[id]
        return HttpResponse.json(wrap(null))
      }
      notes[id] = trimmed
      return HttpResponse.json(
        wrap({ anchor_trade_id: id, body: trimmed, created_at: '2026-10-09T10:00:00+09:00',
               updated_at: '2026-10-09T10:00:01+09:00' }),
      )
    }),
  )
  return render(
    <TestProviders queryClient={opts.client}>
      <History />
    </TestProviders>,
  )
}

async function openJournal(anchor: string = BFB): Promise<void> {
  await userEvent.click(screen.getByTestId('history-tab-journal'))
  await screen.findByTestId(`journal-card-${anchor}`)
}

async function roundTrip(anchor: string = BFB): Promise<void> {
  await userEvent.click(screen.getByRole('button', { name: '주문체결내역' }))
  await waitFor(() => expect(screen.queryByTestId(`journal-card-${anchor}`)).toBeNull())
  await openJournal(anchor)
}

const card = (anchor: string) => screen.getByTestId(`journal-card-${anchor}`)
const noteInput = (anchor: string) => within(card(anchor)).getByTestId('journal-note-input') as HTMLTextAreaElement
const saveBtn = (anchor: string) => within(card(anchor)).getByTestId('journal-note-save')
const lastReq = (): URL => requests[requests.length - 1]

function setViewport(width: number) {
  Object.defineProperty(window, 'innerWidth', { configurable: true, writable: true, value: width })
  Object.defineProperty(window, 'matchMedia', {
    configurable: true,
    writable: true,
    value: (query: string) => {
      const min = /min-width:\s*(\d+)px/.exec(query)
      const max = /max-width:\s*(\d+)px/.exec(query)
      const matches = (!min || width >= Number(min[1])) && (!max || width <= Number(max[1]))
      return {
        matches, media: query, onchange: null,
        addListener: () => {}, removeListener: () => {},
        addEventListener: () => {}, removeEventListener: () => {}, dispatchEvent: () => false,
      }
    },
  })
  window.dispatchEvent(new Event('resize'))
}

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
  setViewport(1280)
})
afterEach(() => {
  setViewport(1280)
})

// ════════════════════════════════════════════════════════════════════════════
// M1 (#2) 메모 — 저장 → 탭 왕복 → 값 유지 · 변경 없으면 저장 꺼짐 · 빈 body PUT 0
// ════════════════════════════════════════════════════════════════════════════
describe('cycle413 보완 1차 M1 — 메모가 지워지지 않는다', () => {
  it('M1a: 바뀐 것이 없으면 저장 버튼이 꺼져 있다(열자마자 · 저장 직후)', async () => {
    setup({ client: prodLikeClient() })
    await openJournal()
    expect(noteInput(BFB).value).toBe('목표 도달 — 계획대로')
    expect(saveBtn(BFB)).toBeDisabled()
    expect(saveBtn(OPEN)).toBeDisabled()   // 메모 없음 + 입력 없음
    fireEvent.change(noteInput(BFB), { target: { value: '새 메모' } })
    expect(saveBtn(BFB)).toBeEnabled()
    fireEvent.change(noteInput(BFB), { target: { value: '목표 도달 — 계획대로' } })   // 되돌리면 다시 꺼진다
    expect(saveBtn(BFB)).toBeDisabled()
  })

  it('M1b: 저장 → 다른 탭 → 돌아와도 저장한 값이 보이고 저장 버튼은 꺼져 있다', async () => {
    setup({ client: prodLikeClient() })
    await openJournal()
    fireEvent.change(noteInput(BFB), { target: { value: '새 메모' } })
    await userEvent.click(saveBtn(BFB))
    await waitFor(() => expect(card(BFB)).toHaveTextContent('저장됨'))
    expect(saveBtn(BFB)).toBeDisabled()
    expect(notes[BFB]).toBe('새 메모')

    await roundTrip()
    await waitFor(() => expect(noteInput(BFB).value).toBe('새 메모'))
    expect(saveBtn(BFB)).toBeDisabled()
  })

  it('M1c: 메모 없던 카드에 저장 → 탭 왕복 → 그대로 저장 눌러도 빈 body PUT 0 · 서버 메모 유지', async () => {
    setup({ client: prodLikeClient() })
    await openJournal()
    fireEvent.change(noteInput(OPEN), { target: { value: '처음 메모' } })
    await userEvent.click(saveBtn(OPEN))
    await waitFor(() => expect(puts).toHaveLength(1))
    await waitFor(() => expect(card(OPEN)).toHaveTextContent('저장됨'))

    await roundTrip(OPEN)
    await waitFor(() => expect(noteInput(OPEN).value).toBe('처음 메모'))
    await userEvent.click(saveBtn(OPEN))
    await new Promise((r) => setTimeout(r, 100))
    expect(puts.filter((p) => p.body.trim() === '')).toEqual([])
    expect(notes[OPEN]).toBe('처음 메모')
  })

  it('M1d: 저장 성공이 일지를 다시 읽게 하되, 편집 중인 다른 카드 입력은 덮지 않는다', async () => {
    setup({ client: prodLikeClient() })
    await openJournal()
    fireEvent.change(noteInput(BFB), { target: { value: 'BFB 편집 중' } })
    const before = requests.length
    fireEvent.change(noteInput(OPEN), { target: { value: '보유 메모' } })
    await userEvent.click(saveBtn(OPEN))
    await waitFor(() => expect(requests.length).toBeGreaterThan(before))
    await waitFor(() => expect(noteInput(OPEN).value).toBe('보유 메모'))
    expect(noteInput(BFB).value).toBe('BFB 편집 중')
    expect(card(BFB)).toHaveTextContent('저장 안 됨')
    expect(saveBtn(BFB)).toBeEnabled()
  })
})

// ════════════════════════════════════════════════════════════════════════════
// M2 (#3) 페이지 넘김
// ════════════════════════════════════════════════════════════════════════════
function twoPages(): Record<string, Json> {
  const p1 = clone()
  Object.assign(p1, { page: 1, total: 21, total_pages: 2, counts: { total: 21, open: 1, closed: 20 } })
  p1.cards = [p1.cards[0], p1.cards[1]]
  const p2 = clone()
  Object.assign(p2, { page: 2, total: 21, total_pages: 2, counts: { total: 21, open: 1, closed: 20 } })
  p2.cards = [p2.cards[2]]
  return { '1': p1, '2': p2 }
}

describe('cycle413 보완 1차 M2 — 페이지 넘김', () => {
  it('M2a: 「총 21」 이면 다음 쪽으로 넘겨 나머지 카드를 볼 수 있다', async () => {
    setup({ pages: twoPages() })
    await openJournal()
    expect(lastReq().searchParams.get('page')).toBe('1')
    expect(screen.getByTestId('journal-page-info').textContent).toMatch(/1\s*\/\s*2/)
    expect(screen.getByTestId('journal-page-prev')).toBeDisabled()
    expect(screen.getByTestId('journal-page-next')).toBeEnabled()
    expect(screen.queryByTestId(`journal-card-${VB}`)).toBeNull()

    await userEvent.click(screen.getByTestId('journal-page-next'))
    await screen.findByTestId(`journal-card-${VB}`)
    expect(lastReq().searchParams.get('page')).toBe('2')
    expect(lastReq().searchParams.get('size')).toBe('20')
    expect(screen.queryByTestId(`journal-card-${BFB}`)).toBeNull()
    expect(screen.getByTestId('journal-page-info').textContent).toMatch(/2\s*\/\s*2/)
    expect(screen.getByTestId('journal-page-next')).toBeDisabled()

    await userEvent.click(screen.getByTestId('journal-page-prev'))
    await screen.findByTestId(`journal-card-${BFB}`)
    expect(lastReq().searchParams.get('page')).toBe('1')
  })

  it('M2b: 필터를 바꾸면 1쪽부터 다시 본다', async () => {
    setup({ pages: twoPages() })
    await openJournal()
    await userEvent.click(screen.getByTestId('journal-page-next'))
    await screen.findByTestId(`journal-card-${VB}`)
    await userEvent.selectOptions(screen.getByTestId('journal-filter-status'), 'closed')
    await waitFor(() => expect(lastReq().searchParams.get('status')).toBe('closed'))
    expect(lastReq().searchParams.get('page')).toBe('1')
  })

  it('M2c: 한 쪽뿐이면 다음 쪽 버튼이 꺼져 있다', async () => {
    setup()
    await openJournal()
    const next = screen.queryByTestId('journal-page-next')
    if (next) expect(next).toBeDisabled()
  })
})

// ════════════════════════════════════════════════════════════════════════════
// M3 (#4) 사유 없는 청산 줄
// ════════════════════════════════════════════════════════════════════════════
describe('cycle413 보완 1차 M3 — 사유를 모르는 청산은 「손절 미발동」 을 단정하지 않는다', () => {
  it('M3: line_role=null · line_na=before_record → 빈칸 배지만', async () => {
    const fx = clone()
    const x = fx.cards[2].exits[0]
    Object.assign(x, {
      source: null, source_na: 'before_record', line_role: null, line_na: 'before_record', effective_line: null,
      snapshot_age_s: null,
      reason: { code: null, sub: null, phrase: null, renamed_from: null, text: null, src: null, signal_src: null,
                na: 'before_record' },
    })
    setup({ fixture: fx })
    await openJournal()
    const line = within(within(card(VB)).getByTestId('journal-exit-V2')).getByTestId('journal-exit-line')
    expect(line.textContent).not.toContain('손절 미발동')
    expect(within(line).getByTestId('journal-na-before_record')).toBeInTheDocument()
  })
})

// ════════════════════════════════════════════════════════════════════════════
// M4 (#6) 보유 중 분할 매도
// ════════════════════════════════════════════════════════════════════════════
describe('cycle413 보완 1차 M4 — 보유 중 분할 매도', () => {
  it('M4: 제목 「분할 매도」 · 머리 아래 「분할 실현 세후 +5,940」', async () => {
    const fx = clone()
    const open = fx.cards[0]
    const vbExit = fx.cards[2].exits[0]
    open.exits = [{
      ...JSON.parse(JSON.stringify(vbExit)),
      order_no: 'K9', trade_ids: ['aaaaaaaa-0000-4000-8000-000000000009'], at: '2026-10-07T16:02:10.000000+09:00',
      price: 51200, qty: 5, division: '41', path: 'manual', realized_gross_krw: 6000,
      reason: { code: 'MANUAL', sub: null, phrase: null, renamed_from: null, text: '수동 매도(화면)', src: 'live',
                signal_src: null, na: null },
      effective_line: 47800, snapshot_age_s: 12, line_role: 'reference', line_na: null,
    }]
    open.pnl.partial_gross_krw = 6000
    open.pnl.partial_net_krw = 5940
    open.costs.exits = [{ order_no: 'K9', at: '2026-10-07T16:02:10.000000+09:00', fee: 36, tax: 24,
                          status: 'estimated', allocated: false }]
    open.costs.paid_total = 770
    setup({ fixture: fx })
    await openJournal()
    const c = card(OPEN)
    expect(c).toHaveTextContent('분할 매도')
    expect(within(c).queryAllByText('청산', { exact: true })).toHaveLength(0)
    expect(c.textContent).toMatch(/분할 실현 세후\s*\+5,940/)
    expect(within(c).getByTestId('journal-exit-K9')).toHaveTextContent('수동 매도(화면)')
  })
})

// ════════════════════════════════════════════════════════════════════════════
// M5 (#7) 출처 칩 — 근사·역산 값이 정확한 값처럼 보이지 않게
// ════════════════════════════════════════════════════════════════════════════
describe('cycle413 보완 1차 M5 — 발동선·판단가 출처 칩', () => {
  function stopLossExit(fx: Json, fired_src: string, judge: Json): void {
    Object.assign(fx.cards[2].exits[0], {
      reason: { code: 'STOP_LOSS', sub: null, phrase: 'vb_stop', renamed_from: null,
                text: '고정 손절 — 매수가 대비 3.0% · 선 97,000', src: 'live', signal_src: null, na: null },
      fired_line: 97000, fired_src, effective_line: 97000, snapshot_age_s: 5, line_role: 'fired', line_na: null,
      judge,
    })
  }

  it('M5a: 발동선 출처 — 스냅샷이면 「스냅샷」 칩 · 판단가 역산이면 「역산」 칩', async () => {
    const fx = clone()
    stopLossExit(fx, 'snapshot', { price: 97050, upper: null, src: 'log_pct', na: null })
    setup({ fixture: fx })
    await openJournal()
    const ex = within(card(VB)).getByTestId('journal-exit-V2')
    const line = within(ex).getByTestId('journal-exit-line')
    expect(line).toHaveTextContent('발동선 97,000')
    expect(line).toHaveTextContent('스냅샷')
    expect(ex).toHaveTextContent('판단가 97,050')
    expect(ex).toHaveTextContent('역산')
  })

  it('M5b: 발동선 계산값이면 「계산」 · 매수 판단가가 AI평가 복원이면 「복원(AI평가)」', async () => {
    const fx = clone()
    stopLossExit(fx, 'derived', { price: null, upper: null, src: null, na: 'unknown' })
    fx.cards[2].entry.orders[0].judge = { price: 99800, upper: null, src: 'restored_ai', na: null }
    setup({ fixture: fx })
    await openJournal()
    const c = card(VB)
    expect(within(within(c).getByTestId('journal-exit-V2')).getByTestId('journal-exit-line')).toHaveTextContent('계산')
    // 진입 이유 칩은 「기록」(reason.src=live) — 「복원(AI평가)」 는 판단가 칩에서만 나올 수 있다.
    expect(within(c).getByTestId('journal-entry-reason')).not.toHaveTextContent('복원(AI평가)')
    expect(c).toHaveTextContent('복원(AI평가)')
  })
})

// ════════════════════════════════════════════════════════════════════════════
// M6 (#12) 표시 묶음
// ════════════════════════════════════════════════════════════════════════════
describe('cycle413 보완 1차 M6 — 표시 묶음', () => {
  it('M6a: 빈칸 배지마다 사유 툴팁 — 「—」(모름)는 「모름 — …」', async () => {
    setup()
    await openJournal()
    const badges = screen.getAllByTestId(/^journal-na-/)
    expect(badges.length).toBeGreaterThan(0)
    for (const b of badges) {
      expect(b.getAttribute('title') ?? '', b.getAttribute('data-testid') ?? '').not.toBe('')
    }
    for (const b of screen.getAllByTestId('journal-na-unknown')) {
      expect(b.getAttribute('title') ?? '').toMatch(/^모름/)
    }
  })

  it('M6b: 서버 문장과 출처 칩이 붙어 보이지 않는다', async () => {
    setup()
    await openJournal()
    const reason = within(card(BFB)).getByTestId('journal-entry-reason')
    const chip = within(reason).getByText('기록')
    const spaced = /410\s+기록/.test(reason.textContent ?? '')
    const margin = /\bml-|\bgap-/.test(`${chip.className} ${chip.parentElement?.className ?? ''}`)
    expect(spaced || margin, `「${reason.textContent}」`).toBe(true)
  })

  it('M6c: 제목 — 익절 목표 · 보유 중 평가(일별 종가) · 메모', async () => {
    setup()
    await openJournal()
    const c = card(BFB)
    expect(within(c).getByTestId('journal-target')).toHaveTextContent('익절 목표')
    expect(c).toHaveTextContent('일별 종가')
    expect(within(c).getAllByText(/^메모$/).length).toBeGreaterThan(0)
  })

  it('M6d: 익절 청산 줄 — 진입 목표가 기록 전이어도 발동선(= 목표)으로 「목표 13,450」', async () => {
    const fx = clone()
    const bfb = fx.cards[1]
    Object.assign(bfb.entry.target, { price: null, hit: null, signal_price: null, text: '측정 목표 기록 없음',
                                      na: 'before_record' })
    Object.assign(bfb.exits[0], { fired_line: 13450, fired_src: 'live' })
    setup({ fixture: fx })
    await openJournal()
    const line = within(within(card(BFB)).getByTestId('journal-exit-S1')).getByTestId('journal-exit-line')
    expect(line).toHaveTextContent('목표 13,450')
    expect(within(line).queryAllByTestId(/^journal-na-/)).toHaveLength(0)
  })

  it('M6e: 당일 매매는 「보유 0일」 이 아니라 「당일」', async () => {
    setup()
    await openJournal()
    const c = card(VB)
    // 익절 목표 문장(「없음 — 15:20 당일 청산」)의 「당일」 은 빼고 본다.
    const head = (c.textContent ?? '').replace(within(c).getByTestId('journal-target').textContent ?? '', '')
    expect(head).toContain('당일')
    expect(head).not.toMatch(/보유\s*0일/)
    expect(card(BFB)).toHaveTextContent('3일')
  })

  it('M6f: 보유 중 비용은 「낸 비용」 — 「합계」 는 청산 카드만', async () => {
    setup()
    await openJournal()
    const openTotal = within(card(OPEN)).getByTestId('journal-cost-total')
    expect(openTotal).toHaveTextContent('낸 비용')
    expect(openTotal).toHaveTextContent('710')
    expect(openTotal.textContent).not.toContain('합계')
    expect(within(card(BFB)).getByTestId('journal-cost-total')).toHaveTextContent('합계')
  })

  it('M6g: 400px 「필터」 버튼이 필터줄을 접고 편다(aria-expanded)', async () => {
    setViewport(400)
    setup()
    await openJournal()
    const toggle = screen.getByTestId('journal-filter-toggle')
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    await userEvent.click(toggle)
    expect(toggle).toHaveAttribute('aria-expanded', 'true')
    await userEvent.click(toggle)
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
  })

  it('M6h: 경로 꼬리(5호가 폴백 · 잔여 재주문)는 서버 문장에 한 번만', async () => {
    const fx = clone()
    Object.assign(fx.cards[2].exits[0], {
      path: 'fallback',
      reason: { ...fx.cards[2].exits[0].reason, text: '15:20 강제청산 · 5호가 폴백' },
    })
    Object.assign(fx.cards[1].exits[0], {
      path: 'reorder', parent_order_no: 'S0',
      reason: { ...fx.cards[1].exits[0].reason, text: '측정 목표 13,450 도달 — 전량 익절 · 잔여 재주문(원주문 S0)' },
    })
    setup({ fixture: fx })
    await openJournal()
    const vb = within(card(VB)).getByTestId('journal-exit-V2').textContent ?? ''
    expect(vb.split('5호가 폴백').length - 1).toBe(1)
    const bfb = within(card(BFB)).getByTestId('journal-exit-S1').textContent ?? ''
    expect(bfb.split('잔여 재주문').length - 1).toBe(1)
  })
})
