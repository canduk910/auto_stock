/**
 * cycle413 보완 2차 Red — 재검증 렌즈(suites·screens·trader)가 새로 찾은 결함 회귀.
 *
 * 원문 = scratchpad `c413/fix/{suites2,screens,trader}` 재검증 결과. 명세 = 각 렌즈의 수정 방향.
 *
 * | # | 결함 → 계약 |
 * |---|---|
 * | N1 (프론트 — 중) | 메모 저장 중 레이스 — `onSuccess` 가 전송 시점의 값(`draft`)이 아니라 응답이 온 시점의 현재
 * |     | `draft` 를 저장값으로 삼는다. 저장 전송 뒤 입력칸을 더 고치면 그 글자가 사라지고, `dirty` 가 거짓이 되어
 * |     | 다시 저장할 길이 막힌다. 수정 = `onSuccess(_data, body)` 의 `body`(전송값)로 `lastSaved` 를 맞춘다 |
 * | N3 (프론트 — 하) | 세후/세전 토글이 `page` 를 1로 되돌리지 않아 2쪽을 보던 중 토글하면 「데이터가 없습니다」 가 뜬다.
 * |     | `total_pages=0` 이면 「1 / 0」 이 찍힌다 — `/pnl` 과 같은 규약이라 화면이 `max(1, total_pages)` 로 가린다 |
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
let putDelayMs = 0

function prodLikeClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, staleTime: 3000, gcTime: 5 * 60 * 1000 },
      mutations: { retry: false },
    },
  })
}

function setup(opts: { fixture?: Json; pages?: Record<string, Json>; client?: QueryClient } = {}) {
  requests = []
  puts = []
  putDelayMs = 0
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
      if (putDelayMs > 0) await new Promise((r) => setTimeout(r, putDelayMs))
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

const card = (anchor: string) => screen.getByTestId(`journal-card-${anchor}`)
const noteInput = (anchor: string) => within(card(anchor)).getByTestId('journal-note-input') as HTMLTextAreaElement
const saveBtn = (anchor: string) => within(card(anchor)).getByTestId('journal-note-save')
const lastReq = (): URL => requests[requests.length - 1]

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
afterEach(() => {
  putDelayMs = 0
})

// ════════════════════════════════════════════════════════════════════════════
// N1 — 메모 저장 레이스: onSuccess 는 전송값으로 lastSaved 를 맞춘다
// ════════════════════════════════════════════════════════════════════════════
describe('cycle413 보완 2차 N1 — 메모 저장 중 더 고친 글자가 사라지지 않는다', () => {
  it('N1: 저장 응답이 늦게 오는 동안 더 입력하면, 응답 뒤 그 글자가 남고 다시 저장할 수 있다', async () => {
    putDelayMs = 50
    setup({ client: prodLikeClient() })
    await openJournal()

    fireEvent.change(noteInput(BFB), { target: { value: 'abc' } })
    fireEvent.click(saveBtn(BFB))
    // 응답이 오기 전에 더 입력한다 — 서버로는 'abc' 가 나갔다(userEvent.click 은 내부 지연이 있어
    // 응답이 먼저 끝날 수 있으므로 동기 fireEvent.click 으로 레이스 창을 보장한다).
    fireEvent.change(noteInput(BFB), { target: { value: 'abcXYZ' } })

    await waitFor(() => expect(puts).toHaveLength(1))
    expect(puts[0].body).toBe('abc')

    // 응답이 돌아온 뒤 — 입력칸의 'XYZ' 가 사라지면 안 되고, 서버에 안 나간 글자이므로 다시 저장할 수 있어야 한다.
    await waitFor(() => expect(noteInput(BFB).value).toBe('abcXYZ'))
    expect(saveBtn(BFB)).toBeEnabled()
    expect(card(BFB)).toHaveTextContent('저장 안 됨')
  })
})

// ════════════════════════════════════════════════════════════════════════════
// N3 — 세후/세전 토글이 페이지를 되돌린다 · total_pages=0 표시
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

describe('cycle413 보완 2차 N3 — 세후/세전 토글·빈 결과 페이지 표시', () => {
  it('N3a: 2쪽을 보던 중 세후/세전을 바꾸면 1쪽으로 돌아간다', async () => {
    setup({ pages: twoPages() })
    await openJournal()
    await userEvent.click(screen.getByTestId('journal-page-next'))
    await screen.findByTestId(`journal-card-${VB}`)
    expect(lastReq().searchParams.get('page')).toBe('2')

    await userEvent.click(within(screen.getByTestId('cost-basis-toggle')).getByText('세전'))
    await waitFor(() => expect(lastReq().searchParams.get('basis')).toBe('gross'))
    expect(lastReq().searchParams.get('page')).toBe('1')
    expect(screen.getByTestId('journal-page-info').textContent).toMatch(/1\s*\/\s*2/)
  })

  it('N3b: 결과가 0건이면 「1 / 0」 대신 「1 / 1」 로 보인다', async () => {
    const empty = clone()
    Object.assign(empty, { total: 0, total_pages: 0, counts: { total: 0, open: 0, closed: 0 }, cards: [] })
    setup({ fixture: empty })
    await userEvent.click(screen.getByTestId('history-tab-journal'))
    await screen.findByText('거래일지 데이터가 없습니다.')
    expect(screen.getByTestId('journal-page-info').textContent).toMatch(/1\s*\/\s*1/)
    expect(screen.getByTestId('journal-page-info').textContent).not.toMatch(/\/\s*0/)
  })
})

// ════════════════════════════════════════════════════════════════════════════
// N3 잔여(#12) — 문장/숫자 뒤 칩이 띄어쓰기 없이 붙는다
// ════════════════════════════════════════════════════════════════════════════
describe('cycle413 보완 2차 N3 잔여(#12) — 칩이 문장·숫자에 바로 붙지 않는다', () => {
  it('N3c: 익절 목표 문장과 na 배지(둘 다 서는 경우) 사이에 공백이 있다', async () => {
    setup({ client: prodLikeClient() })
    await openJournal(OPEN)
    const target = within(card(OPEN)).getByTestId('journal-target')
    expect(target.textContent).toContain('샹들리에 트레일·스테이지3 청산 해당 없음')
  })

  it('N3d: 판단가 숫자와 출처 칩 사이에 공백이 있다', async () => {
    setup({ client: prodLikeClient() })
    await openJournal(OPEN)
    const row = within(card(OPEN)).getAllByText(/판단가/)[0].closest('span')!
    expect(row.textContent).toContain('49,950 신호 틱 가격')
  })

  it('N3e: 비용 합계 숫자와 상태 칩 사이에 공백이 있다', async () => {
    setup({ client: prodLikeClient() })
    await openJournal(OPEN)
    const costs = within(card(OPEN)).getByTestId('journal-cost-total')
    expect(costs.textContent).toContain('710 추정')
  })

  it('N3f: 보유 중 「지금 손절선」 숫자와 종류 칩 사이에 공백이 있다', async () => {
    const fixture = clone()
    const openCard = fixture.cards.find((c: Json) => c.anchor_trade_id === OPEN)
    openCard.entry.initial_stop.kind = 'effective'
    setup({ fixture, client: prodLikeClient() })
    await openJournal(OPEN)
    expect(card(OPEN).textContent).toMatch(/지금 손절선 47,500\s+\S/)
  })
})
