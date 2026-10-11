/**
 * cycle446 D-6 — 거래일지 카드 「AI 청산 의견」(`exit_ai`) 요지.
 *
 * 백엔드 = `src/db/exit_ai.py` + `src/routes/history.py::_attach_exit_ai`(읽기만). 5가지
 * 상태(`not_applicable`·`no_evaluation`·`lookup_failed`·`hold_all`·`exit_signaled`)를 전부
 * 「없음」 으로 접지 않고 각자 다른 문구로 보인다.
 */
import { beforeEach, describe, expect, it } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'

import { server } from '../../test/server'
import { wrap } from '../../test/factories'
import { TestProviders } from '../../test/providers'
import { JOURNAL_FIXTURE } from '../../test/fixtures/journal.fixture'
import History from '../History'

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Json = any

const clone = (): Json => JSON.parse(JSON.stringify(JOURNAL_FIXTURE))

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
  server.use(http.get('/api/history/journal', () => HttpResponse.json(wrap(fixture))))
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

describe('cycle446 — 거래일지 카드 AI 청산 의견', () => {
  it('고정 픽스처 3장이 각자 다른 상태를 보인다(없음/모름/청산신호)', async () => {
    const fixture = clone()
    const open = fixture.cards.find((c: Json) => c.strategy === 'kojiro')
    const bfb = fixture.cards.find((c: Json) => c.strategy === 'bull_flag_breakout')
    const vb = fixture.cards.find((c: Json) => c.strategy === 'volatility_breakout')
    setup(fixture)
    await openJournal(open.anchor_trade_id)

    const openBlock = within(card(open.anchor_trade_id)).getByTestId('journal-ai-opinion')
    expect(openBlock).toHaveTextContent('아직 평가 없음')

    const bfbBlock = within(card(bfb.anchor_trade_id)).getByTestId('journal-ai-opinion')
    expect(bfbBlock).toHaveTextContent('2026-10-07')
    expect(bfbBlock).toHaveTextContent('72')
    expect(bfbBlock).toHaveTextContent('EMA20 이탈')

    const vbBlock = within(card(vb.anchor_trade_id)).getByTestId('journal-ai-opinion')
    expect(vbBlock).toHaveTextContent('대상 전략 아님')
  })

  it('조회 실패(lookup_failed)는 경고색 문구로 보인다', async () => {
    const fixture = clone()
    fixture.cards[0].exit_ai = { status: 'lookup_failed' }
    setup(fixture)
    await openJournal(fixture.cards[0].anchor_trade_id)
    expect(within(card(fixture.cards[0].anchor_trade_id)).getByTestId('journal-ai-opinion'))
      .toHaveTextContent('조회 실패')
  })

  it('전부 hold 였던 청산 포지션은 「보유 판단 유지」를 보인다', async () => {
    const fixture = clone()
    fixture.cards[0].exit_ai = { status: 'hold_all', note: '보유 판단 유지' }
    setup(fixture)
    await openJournal(fixture.cards[0].anchor_trade_id)
    expect(within(card(fixture.cards[0].anchor_trade_id)).getByTestId('journal-ai-opinion'))
      .toHaveTextContent('보유 판단 유지')
  })
})
