/**
 * cycle413 Red — 거래 내역 세 번째 탭 「거래일지」 (명세 `_workspace/red/cycle413/journal_view_spec.md` 8절·5절).
 *
 * 계약 = `_workspace/red/cycle413/journal_view_contract.md` 4절. 응답 = `src/test/fixtures/journal.fixture.ts`
 * (키 = `tests/fixtures/cycle413_journal_shape.json`, 백엔드 라우트 테스트와 같은 파일).
 *
 * | # | 계약 |
 * |---|---|
 * | J1 | 탭 `history-tab-journal`(「거래일지」) — 기본 탭은 그대로 주문체결내역, 누르기 전엔 일지 API 0 |
 * | J2 | 기록 시작일 한 줄 `journal-record-start` — 값 없으면 「실시간 기록 대기」 |
 * | J3 | 카드 = 응답 순서 · 머리 손익은 토글 기준이 먼저(크게), 다른 기준이 뒤 · 세후/세전 토글은 `useCostBasis` 공유(서버로 basis 전달) |
 * | J4 | 빈칸 5종 `journal-na-{na}` 서로 다른 문구 · 모름을 0/0원으로 그리지 않는다 |
 * | J5 | 손절 정지 경고·기록 전 안내·진입 이유·최초 손절(근사 배지)·익절 목표·체결오차·시각(MM-DD HH:mm:ss) |
 * | J6 | 청산 블록 `journal-exit-{order_no}` — 사유 배지 + 서버 문장 + 선(목표/참고 손절선 n초 전) + 판단가 체결오차 |
 * | J7 | 비용 합계·정산/추정 · MFE/MAE(잠정·락·종가 k/n·손실 구간 없음·해당 없음·조회 실패) |
 * | J8 | 손절선 변화 — 접힘 기본(행을 그리지 않는다) · ↑n ↓n(↓ 빨강) · 펼치면 행 · 내림 빨강 · 재시작 노랑 · 정지 빨강 · 숨김 n건 |
 * | J9 | 메모 — 저장 버튼으로만 PUT · 자동 저장 0 · 4,000 초과 비활성 · 실패면 입력 유지 · 글자 그대로 |
 * | J10 | 필터 — 기간 7일 · 보유/청산 · 이익/손실 · 정렬이 쿼리로 간다 · 건수 줄 |
 * | J11 | 400px — 카드 안 표 0 · 손절선 변화는 표 행이 아니다 · 400px 넘는 고정 폭 0 · 「필터」 버튼 |
 */
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
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
  JOURNAL_FIXTURE_NO_RECORDS,
} from '../../test/fixtures/journal.fixture'
import { kstTodayISO } from '../../utils/kst'
import History from '../History'

const COST_BASIS_KEY = 'autostock.costBasis'

let requests: URL[] = []
let puts: Array<{ id: string; body: unknown }> = []

function setup(fixture: unknown = JOURNAL_FIXTURE, opts: { putStatus?: number } = {}) {
  requests = []
  puts = []
  server.use(
    http.get('/api/history/journal', ({ request }) => {
      requests.push(new URL(request.url))
      return HttpResponse.json(wrap(fixture))
    }),
    http.put('/api/history/journal/notes/:id', async ({ request, params }) => {
      const body = (await request.json()) as { body: string }
      puts.push({ id: String(params.id), body })
      if (opts.putStatus && opts.putStatus !== 200) {
        return HttpResponse.json({ success: false, data: null, message: '실패' }, { status: opts.putStatus })
      }
      return HttpResponse.json(
        wrap({ anchor_trade_id: params.id, body: body.body.trim(), created_at: '2026-10-09T10:00:00+09:00',
               updated_at: '2026-10-09T10:00:01+09:00' }),
      )
    }),
  )
  return render(
    <TestProviders>
      <History />
    </TestProviders>,
  )
}

async function openJournal(): Promise<void> {
  await userEvent.click(screen.getByTestId('history-tab-journal'))
  await screen.findByTestId(`journal-card-${BFB}`)
}

const card = (anchor: string) => screen.getByTestId(`journal-card-${anchor}`)
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

/**
 * 결정론적 in-memory localStorage — Node 25 실험 localStorage 글로벌이 jsdom Storage 를 가려
 * `setItem` 이 없는 환경 대응(`PerformanceCard.cost.cycle411.test.tsx` 와 같은 방식).
 */
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

describe('cycle413 — 거래일지 탭', () => {
  it('J1: 세 번째 탭 「거래일지」 — 기본 탭은 주문체결내역, 누르기 전엔 일지 API 를 부르지 않는다', async () => {
    setup()
    const tab = screen.getByTestId('history-tab-journal')
    expect(tab).toHaveTextContent('거래일지')
    expect(screen.getAllByText('주문체결내역').length).toBeGreaterThan(0)
    expect(screen.getAllByText('매매손익').length).toBeGreaterThan(0)
    await new Promise((r) => setTimeout(r, 50))
    expect(requests).toHaveLength(0)
    await openJournal()
    expect(requests.length).toBeGreaterThan(0)
  })

  it('J2: 기록 시작일 한 줄', async () => {
    setup()
    await openJournal()
    const line = screen.getByTestId('journal-record-start')
    expect(line).toHaveTextContent('2026-09-17')
    expect(line).toHaveTextContent('2026-10-07')
    expect(line.textContent).toContain('손절선 기록')
  })

  it('J2: 기록 시작일이 없으면 「실시간 기록 대기」', async () => {
    setup(JOURNAL_FIXTURE_NO_RECORDS)
    await openJournal()
    expect(screen.getByTestId('journal-record-start')).toHaveTextContent('실시간 기록 대기')
  })

  it('J3: 카드는 응답 순서 · 머리 손익은 세후가 먼저(기본)', async () => {
    setup()
    await openJournal()
    const ids = screen.getAllByTestId(/^journal-card-/).map((el) => el.getAttribute('data-testid'))
    expect(ids).toEqual([`journal-card-${OPEN}`, `journal-card-${BFB}`, `journal-card-${VB}`])
    const head = within(card(BFB)).getByTestId('journal-head-pnl').textContent ?? ''
    expect(head).toContain('+41,464')
    expect(head).toContain('+44,000')
    expect(head.indexOf('+41,464')).toBeLessThan(head.indexOf('+44,000'))
    expect(head).toContain('+8.39%')
    expect(card(BFB)).toHaveTextContent('에코프로비엠')
    expect(card(BFB)).toHaveTextContent('247540')
  })

  it('J3: 세전으로 바꾸면 머리 순서가 바뀌고 · 공유 저장소에 남고 · 서버에 basis=gross 를 보낸다', async () => {
    setup()
    await openJournal()
    await userEvent.click(within(screen.getByTestId('cost-basis-toggle')).getByText('세전'))
    await waitFor(() => {
      const head = within(card(BFB)).getByTestId('journal-head-pnl').textContent ?? ''
      expect(head.indexOf('+44,000')).toBeLessThan(head.indexOf('+41,464'))
    })
    expect(window.localStorage.getItem(COST_BASIS_KEY)).toBe('gross')
    await waitFor(() => expect(lastReq().searchParams.get('basis')).toBe('gross'))
  })

  it('J3: 다른 화면에서 고른 세전이 일지 첫 요청에 그대로 실린다', async () => {
    window.localStorage.setItem(COST_BASIS_KEY, 'gross')
    setup()
    await openJournal()
    expect(requests[0].searchParams.get('basis')).toBe('gross')
    const head = within(card(BFB)).getByTestId('journal-head-pnl').textContent ?? ''
    expect(head.indexOf('+44,000')).toBeLessThan(head.indexOf('+41,464'))
  })

  it('J4: 빈칸 5종이 서로 다른 문구로 보이고 0 으로 채우지 않는다', async () => {
    setup()
    await openJournal()
    const want: Record<string, string> = {
      before_record: '기록 전', unknown: '—', not_applicable: '해당 없음', pending: '대기', lookup_failed: '조회 실패',
    }
    const seen = new Set<string>()
    for (const [na, text] of Object.entries(want)) {
      const els = screen.getAllByTestId(`journal-na-${na}`)
      expect(els.length, na).toBeGreaterThan(0)
      expect(els[0].textContent, na).toContain(text)
      seen.add(els[0].textContent ?? '')
    }
    expect(seen.size).toBe(5)
    const openHead = within(card(OPEN)).getByTestId('journal-head-pnl')
    expect(within(openHead).getAllByTestId('journal-na-pending').length).toBeGreaterThan(0)
    const t = openHead.textContent ?? ''
    expect(t).not.toMatch(/(^|[^\d,])0원/)
    expect(t).not.toMatch(/[+-]0(\.0+)?%/)
    expect(t).not.toMatch(/(^|[^\d,.])0($|[^\d,.%])/)
  })

  it('J5: 손절 정지 경고 · 기록 전 안내는 그 카드에만', async () => {
    setup()
    await openJournal()
    expect(within(card(OPEN)).getByTestId('journal-paused-warning')).toHaveTextContent('손절 평가 정지')
    expect(within(card(BFB)).queryByTestId('journal-paused-warning')).toBeNull()
    const notice = within(card(OPEN)).getByTestId('journal-record-notice')
    expect(notice).toHaveTextContent('손절선 기록 시작')
    expect(notice).toHaveTextContent('2026-10-07')
    expect(within(card(BFB)).queryByTestId('journal-record-notice')).toBeNull()
  })

  it('J5: 진입 — 시각·가격·주문구분·이유(출처 배지)·체결오차·최초 손절·익절 목표', async () => {
    setup()
    await openJournal()
    const c = card(BFB)
    expect(c).toHaveTextContent('10-05 09:12:03')
    expect(c).toHaveTextContent('12,350')
    expect(c).toHaveTextContent('시장가')
    const reason = within(c).getByTestId('journal-entry-reason')
    expect(reason).toHaveTextContent('깃발 상단 12,300 돌파 · 측정 목표 13,450 · ATR 410')
    expect(reason).toHaveTextContent('기록')
    expect(c).toHaveTextContent('8.1bp')
    const stop = within(c).getByTestId('journal-initial-stop')
    expect(stop).toHaveTextContent('11,530')
    expect(stop.textContent).toMatch(/[−-]6\.64%/)
    const target = within(c).getByTestId('journal-target')
    expect(target).toHaveTextContent('13,450')
    expect(target).toHaveTextContent('도달')
    // 고정% 손절선(근사) · 기록 전 진입의 첫 관측 참고값
    expect(within(card(VB)).getByTestId('journal-initial-stop')).toHaveTextContent('근사')
    const openStop = within(card(OPEN)).getByTestId('journal-initial-stop')
    expect(within(openStop).getByTestId('journal-na-before_record')).toBeInTheDocument()
    expect(openStop).toHaveTextContent('첫 관측')
    expect(openStop).toHaveTextContent('47,800')
    expect(within(card(OPEN)).getByTestId('journal-target')).toHaveTextContent('해당 없음')
  })

  it('J6: 청산 블록 — 사유 배지·서버 문장·선·판단가 체결오차', async () => {
    setup()
    await openJournal()
    const ex = within(card(BFB)).getByTestId('journal-exit-S1')
    expect(within(ex).getByText('익절')).toBeInTheDocument() // 사유 배지(문장 속 「전량 익절」과 별개)
    expect(within(ex).getByTestId('journal-exit-reason')).toHaveTextContent(
      '측정 목표 13,450 도달 — 전량 익절 (현재가 13,460)')
    const line = within(ex).getByTestId('journal-exit-line')
    expect(line).toHaveTextContent('목표 13,450')
    expect(line).toHaveTextContent('참고 손절선 12,350')
    expect(line).toHaveTextContent('8초 전')
    expect(ex).toHaveTextContent('0.0bp')
    expect(ex).toHaveTextContent('13,460')
    expect(ex).toHaveTextContent('7.4bp')
    expect(ex).toHaveTextContent('10-08 14:31:20')
    const vb = within(card(VB)).getByTestId('journal-exit-V2')
    expect(within(vb).getByText('15:20 청산')).toBeInTheDocument()
    expect(within(vb).getByTestId('journal-exit-reason')).toHaveTextContent('15:20 강제청산')
    const vbLine = within(vb).getByTestId('journal-exit-line')
    expect(vbLine).toHaveTextContent('손절 미발동')
    expect(vbLine).toHaveTextContent('참고 손절선 97,000')
    expect(vbLine).toHaveTextContent('5초 전')
    expect(within(card(OPEN)).queryAllByTestId(/^journal-exit-(?!reason|line)/)).toHaveLength(0)
  })

  it('J7: 비용 합계·정산 / 보유 중 낸 비용·예상 청산비용 대기', async () => {
    setup()
    await openJournal()
    const c = card(BFB)
    expect(c).toHaveTextContent('701')
    expect(c).toHaveTextContent('764')
    expect(c).toHaveTextContent('1,071')
    const total = within(c).getByTestId('journal-cost-total')
    expect(total).toHaveTextContent('2,536')
    expect(total).toHaveTextContent('정산')
    const openTotal = within(card(OPEN)).getByTestId('journal-cost-total')
    expect(openTotal).toHaveTextContent('710')
    expect(within(openTotal).getAllByTestId('journal-na-pending').length).toBeGreaterThan(0)
  })

  it('J7: MFE/MAE — 잠정·락·종가 k/n·손실 구간 없음 · 해당 없음 · 조회 실패', async () => {
    setup()
    await openJournal()
    const c = card(BFB)
    const mfe = within(c).getByTestId('journal-mfe')
    expect(mfe).toHaveTextContent('+6.23%')
    expect(mfe).toHaveTextContent('30,800')
    expect(mfe).toHaveTextContent('잠정')
    const mae = within(c).getByTestId('journal-mae')
    expect(mae).toHaveTextContent('손실 구간 없음')
    expect(mae).toHaveTextContent('0.81%')
    expect(c).toHaveTextContent('3/3')
    expect(c).toHaveTextContent('락')
    expect(within(card(VB)).getByTestId('journal-mfe')).toHaveTextContent('해당 없음')
    expect(within(card(OPEN)).getByTestId('journal-mfe')).toHaveTextContent('조회 실패')
  })

  it('J8: 손절선 변화 — 접힘 기본 · 요약(↑2 ↓1) · 펼치면 행·색', async () => {
    setup()
    await openJournal()
    const c = card(BFB)
    const toggle = within(c).getByTestId('journal-stop-toggle')
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    expect(toggle).toHaveTextContent('11,530')
    expect(toggle).toHaveTextContent('12,350')
    expect(toggle.textContent).toMatch(/↑\s*2/)
    expect(toggle.textContent).toMatch(/↓\s*1/)
    const down = within(toggle).getByText(/↓\s*1/)
    expect(down.className + (down.parentElement?.className ?? '')).toMatch(/red/)
    expect(within(c).queryAllByTestId('journal-stop-row')).toHaveLength(0)

    await userEvent.click(toggle)
    expect(toggle).toHaveAttribute('aria-expanded', 'true')
    const rows = within(c).getAllByTestId('journal-stop-row')
    expect(rows.map((r) => r.getAttribute('data-event'))).toEqual(['first', 'eod', 'boot', 'change', 'exit'])
    expect(rows.map((r) => r.getAttribute('data-direction') ?? '')).toEqual(['', 'up', 'down', 'up', 'flat'])
    expect(rows[1]).toHaveTextContent('고점 갱신')
    expect(rows[2]).toHaveTextContent('재시작 재계산')
    expect(rows[2].outerHTML).toMatch(/red/)
    expect(rows[2].outerHTML).toMatch(/yellow|amber/)
    expect(c).toHaveTextContent('2건 숨김')

    const o = card(OPEN)
    await userEvent.click(within(o).getByTestId('journal-stop-toggle'))
    const paused = within(o).getAllByTestId('journal-stop-row').find((r) => r.getAttribute('data-event') === 'paused')
    expect(paused).toBeDefined()
    expect(paused!.outerHTML).toMatch(/red/)
    expect(paused!).toHaveTextContent('전략 꺼짐')
  })

  it('J9: 메모 — 저장 버튼으로만 PUT · 자동 저장 0 · 저장됨', async () => {
    setup()
    await openJournal()
    const c = card(BFB)
    const input = within(c).getByTestId('journal-note-input') as HTMLTextAreaElement
    expect(input.value).toBe('목표 도달 — 계획대로')
    expect(c).toHaveTextContent('/ 4,000')
    await userEvent.type(input, ' 추가')
    expect(c).toHaveTextContent('저장 안 됨')
    await new Promise((r) => setTimeout(r, 400))
    expect(puts).toHaveLength(0)
    await userEvent.click(within(c).getByTestId('journal-note-save'))
    await waitFor(() => expect(puts).toHaveLength(1))
    expect(puts[0]).toEqual({ id: BFB, body: { body: '목표 도달 — 계획대로 추가' } })
    await waitFor(() => expect(c).toHaveTextContent('저장됨'))
  })

  it('J9: 4,000자를 넘으면 저장 비활성 · 카운터 빨강', async () => {
    setup()
    await openJournal()
    const c = card(BFB)
    fireEvent.change(within(c).getByTestId('journal-note-input'), { target: { value: 'a'.repeat(4001) } })
    expect(within(c).getByTestId('journal-note-save')).toBeDisabled()
    const counter = within(c).getByText(/4,001/)
    expect(counter.className + (counter.parentElement?.className ?? '')).toMatch(/red/)
  })

  it('J9: 저장 실패면 입력을 그대로 두고 「저장 실패」', async () => {
    setup(JOURNAL_FIXTURE, { putStatus: 500 })
    await openJournal()
    const c = card(BFB)
    const input = within(c).getByTestId('journal-note-input') as HTMLTextAreaElement
    fireEvent.change(input, { target: { value: '다시 써 둔 메모' } })
    await userEvent.click(within(c).getByTestId('journal-note-save'))
    await waitFor(() => expect(c).toHaveTextContent('저장 실패'))
    expect(input.value).toBe('다시 써 둔 메모')
  })

  it('J9: 메모는 글자 그대로(HTML 해석 없음)', async () => {
    const fx = JSON.parse(JSON.stringify(JOURNAL_FIXTURE))
    fx.cards[1].note = { body: '<b>굵게</b>\n둘째 줄', updated_at: '2026-10-08T15:05:00+09:00' }
    setup(fx)
    await openJournal()
    const c = card(BFB)
    expect((within(c).getByTestId('journal-note-input') as HTMLTextAreaElement).value).toBe('<b>굵게</b>\n둘째 줄')
    expect(c.querySelector('b')).toBeNull()
  })

  it('J10: 필터가 쿼리로 간다 · 건수 줄', async () => {
    setup()
    await openJournal()
    expect(screen.getByTestId('journal-counts')).toHaveTextContent('총 3')
    expect(screen.getByTestId('journal-counts')).toHaveTextContent('보유 1')
    expect(screen.getByTestId('journal-counts')).toHaveTextContent('청산 2')

    await userEvent.click(screen.getByTestId('journal-filter-period-7'))
    const today = kstTodayISO()
    const d = new Date(`${today}T00:00:00Z`)
    d.setUTCDate(d.getUTCDate() - 7)
    const from7 = d.toISOString().slice(0, 10)
    await waitFor(() => {
      const last = lastReq()
      expect(last.searchParams.get('from')).toBe(from7)
      expect(last.searchParams.get('to')).toBe(today)
    })

    await userEvent.selectOptions(screen.getByTestId('journal-filter-status'), 'open')
    await waitFor(() => expect(lastReq().searchParams.get('status')).toBe('open'))
    await userEvent.selectOptions(screen.getByTestId('journal-filter-outcome'), 'loss')
    await waitFor(() => expect(lastReq().searchParams.get('outcome')).toBe('loss'))
    await userEvent.selectOptions(screen.getByTestId('journal-filter-sort'), 'pnl_asc')
    await waitFor(() => expect(lastReq().searchParams.get('sort')).toBe('pnl_asc'))
    const last = lastReq()
    expect(last.searchParams.get('status')).toBe('open')
    expect(last.searchParams.get('outcome')).toBe('loss')
  })

  it('J11: 400px — 카드 안 표 0 · 손절선 변화는 표 행이 아니다 · 400px 넘는 고정 폭 0 · 「필터」 버튼', async () => {
    setViewport(400)
    setup()
    await openJournal()
    await userEvent.click(within(card(BFB)).getByTestId('journal-stop-toggle'))
    const rows = within(card(BFB)).getAllByTestId('journal-stop-row')
    expect(rows.length).toBe(5)
    for (const r of rows) {
      expect(r.tagName).not.toBe('TR')
      expect(r.closest('table')).toBeNull()
    }
    for (const el of screen.getAllByTestId(/^journal-card-/)) {
      expect(el.querySelector('table')).toBeNull()
      const all = [el, ...Array.from(el.querySelectorAll<HTMLElement>('*'))]
      for (const node of all) {
        const cls = typeof node.className === 'string' ? node.className : ''
        for (const m of cls.matchAll(/(?:min-w|w)-\[(\d+)px\]/g)) {
          expect(Number(m[1]), cls).toBeLessThanOrEqual(400)
        }
        for (const w of [node.style.width, node.style.minWidth]) {
          const px = /^(\d+(?:\.\d+)?)px$/.exec(w)
          if (px) expect(Number(px[1]), `${cls} style=${w}`).toBeLessThanOrEqual(400)
        }
      }
    }
    expect(screen.getByTestId('journal-filter-toggle')).toHaveTextContent('필터')
  })
})
