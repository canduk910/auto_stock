/**
 * cycle387 Red — 종목 차트 모달 (`components/StockChartModal.tsx`) M1~M13.
 *
 * 명세: `_workspace/red/cycle387_stock_chart_spec.md` §2.3 · §2.4 · §2.6 · §3.2(M1~M13)
 * 사용자 요청(2026-09-28): 잔고·주문체결내역·매매손익에서 종목을 더블클릭하면 KLineChart 로
 * 최근 5년 일봉/주봉/월봉 차트를 본다.
 *
 * ## 봉인하는 계약
 * - 기본 export `StockChartModal({ ticker, name?, onClose })` — 루트(오버레이) testid
 *   `stock-chart-modal`, 패널 `role="dialog" aria-modal="true" aria-labelledby`, 제목 `stock-chart-title`
 * - 토글 `stock-chart-period-D|W|M`(`aria-pressed`, 기본 일봉) · 메타 `stock-chart-meta` ·
 *   상태 `stock-chart-{unsupported|loading|error|empty|partial|provisional}` · `stock-chart-retry` ·
 *   닫기 `stock-chart-close`(aria-label 닫기) · 차트 자리 `stock-chart-canvas-host`
 * - `klinecharts@10.0.3` v10 API — `init(host, {locale:'ko-KR', timezone:'Asia/Seoul', formatter, styles})`
 *   · `setSymbol` · `createIndicator('VOL')` · `setDataLoader` · `setPeriod({type, span:1})` · `dispose(host)`.
 *   모달이 import 하는 값은 `init`·`dispose`·`registerLocale` 셋뿐이다(가짜 모듈이 그 셋만 준다).
 * - 조회 = `getStockChart(ticker, period, 5)` → `GET /api/stock-chart/candles?ticker&period&years=5`,
 *   `useQuery` `retry: 1` · `staleTime` = 완전 결과 10분 · 부분 결과(`complete=false`) 1분 — 서버 캐시와 같은
 *   값이고, 부분 안내 문구 「1분 뒤 다시 열면 다시 받습니다」 가 참이 되는 조건이다.
 *
 * jsdom 에는 canvas 가 없어 `klinecharts` 는 `test/fakeKlinecharts.ts` 로 대체한다.
 * 목 응답은 `test/fixtures/stockChart.fixture.ts`(참조 라우트를 실제로 태운 JSON 리터럴).
 *
 * TZ 고정 — 모달이 `utils/kst.ts`(모듈 레벨 `Intl`)를 쓰므로 `beforeAll` 에서 TZ=UTC 를 먼저 두고
 * 모달을 **동적 import** 한다(정적 import 는 고정 이전에 포맷터를 만든다 — cycle256 F2).
 *
 * RED: `components/StockChartModal.tsx`·`klinecharts` 부재 → 동적 import 실패로 전 케이스 FAIL.
 */
import { afterAll, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import type { ComponentType } from 'react'
import { useState } from 'react'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'

import { server } from '../../test/server'
import { TestProviders } from '../../test/providers'
import { LOSS_HEX, NEUTRAL_HEX, PROFIT_HEX } from '../../utils/pnlColor'
import {
  STOCK_CHART_RESPONSES,
  type StockChartEnvelopeFixture,
  type StockChartPeriodKey,
} from '../../test/fixtures/stockChart.fixture'
import { collectBars, fakeKline, lastChart, resetFakeKline } from '../../test/fakeKlinecharts'

vi.mock('klinecharts', async () => (await import('../../test/fakeKlinecharts')).klinechartsModule)

interface ModalProps {
  ticker: string
  name?: string
  onClose: () => void
}

const ORIG_TZ = process.env.TZ
let StockChartModal: ComponentType<ModalProps>
let registerLocaleCalls: unknown[][] = []
beforeAll(async () => {
  process.env.TZ = 'UTC'
  StockChartModal = (await import('../StockChartModal')).default as ComponentType<ModalProps>
  registerLocaleCalls = [...fakeKline.registerLocale.mock.calls]
})
afterAll(() => {
  process.env.TZ = ORIG_TZ
})
beforeEach(() => {
  resetFakeKline()
})

const URL_PATH = '/api/stock-chart/candles'

/** 요청을 기록하며 기간별 응답을 돌려준다. `respond` 로 시나리오별 응답을 갈아낀다. */
function installChart(
  respond: (period: StockChartPeriodKey, url: URL) => Response | StockChartEnvelopeFixture = (p) =>
    STOCK_CHART_RESPONSES[p],
) {
  const requests: URL[] = []
  const state = { respond }
  server.use(
    http.get(URL_PATH, ({ request }) => {
      const url = new URL(request.url)
      requests.push(url)
      const period = (url.searchParams.get('period') ?? 'D') as StockChartPeriodKey
      const out = state.respond(period, url)
      return out instanceof Response ? out : HttpResponse.json(out)
    }),
  )
  return { requests, state }
}

function withData(
  period: StockChartPeriodKey,
  patch: Partial<NonNullable<StockChartEnvelopeFixture['data']>>,
  message?: string,
): StockChartEnvelopeFixture {
  const base = STOCK_CHART_RESPONSES[period]
  return {
    ...base,
    message: message ?? base.message,
    data: { ...(base.data as NonNullable<StockChartEnvelopeFixture['data']>), ...patch },
  }
}

function renderModal(props: Partial<ModalProps> = {}) {
  const onClose = vi.fn()
  const utils = render(
    <TestProviders>
      <StockChartModal ticker="005930" name="삼성전자" onClose={onClose} {...props} />
    </TestProviders>,
  )
  return { onClose, ...utils }
}

/** 픽스처 봉 → 기대 KLineData (KST 자정 epoch). */
function expectedKline(period: StockChartPeriodKey) {
  return (STOCK_CHART_RESPONSES[period].data?.bars ?? []).map((b) => ({
    timestamp: Date.parse(`${b.date}T00:00:00+09:00`),
    open: b.open,
    high: b.high,
    low: b.low,
    close: b.close,
    volume: b.volume,
    turnover: b.amount,
  }))
}

async function waitPeriod(type: 'day' | 'week' | 'month') {
  await waitFor(
    () => {
      const calls = lastChart().fn('setPeriod').mock.calls
      expect(calls.length).toBeGreaterThan(0)
      expect(calls[calls.length - 1][0]).toEqual(expect.objectContaining({ type, span: 1 }))
    },
    { timeout: 5000 },
  )
}

// ═════════════════════════════════════════════════════════════════════════════
// M1 — 열림 → 로딩 → 차트 초기화 → 일봉
// ═════════════════════════════════════════════════════════════════════════════
describe('M1: 열면 일봉을 받아 KLineChart v10 으로 그린다', () => {
  it('M1-a: 로딩 → init(host, 옵션) · setSymbol · VOL 패널 · setPeriod(day) · 로더가 오름차순 봉을 준다', async () => {
    const { requests } = installChart()
    renderModal()

    expect(screen.getByTestId('stock-chart-modal')).toBeInTheDocument()
    expect(screen.getByTestId('stock-chart-loading')).toBeInTheDocument()
    expect(screen.getByTestId('stock-chart-title').textContent).toContain('삼성전자')
    expect(screen.getByTestId('stock-chart-title').textContent).toContain('005930')

    await waitPeriod('day')
    expect(fakeKline.init).toHaveBeenCalledTimes(1)
    const rec = lastChart()
    const host = screen.getByTestId('stock-chart-canvas-host')
    expect(rec.el === host || host.contains(rec.el as Node)).toBe(true)
    expect(rec.options).toEqual(
      expect.objectContaining({ locale: 'ko-KR', timezone: 'Asia/Seoul' }),
    )
    expect(typeof rec.options?.formatter?.formatDate).toBe('function')
    expect(rec.fn('setSymbol')).toHaveBeenCalledWith(
      expect.objectContaining({ ticker: '005930', pricePrecision: 0, volumePrecision: 0 }),
    )
    const indicatorNames = rec.fn('createIndicator').mock.calls.map((c) => {
      const v = c[0] as unknown
      return typeof v === 'string' ? v : (v as { name?: string } | null)?.name
    })
    expect(indicatorNames).toContain('VOL')

    const init = await collectBars(rec, 'init')
    expect(init.data).toEqual(expectedKline('D'))
    expect((await collectBars(rec, 'forward')).data).toEqual([])
    expect((await collectBars(rec, 'backward')).data).toEqual([])

    await waitFor(() => expect(screen.queryByTestId('stock-chart-loading')).toBeNull())
    expect(requests).toHaveLength(1)
    const q = requests[0].searchParams
    expect([q.get('ticker'), q.get('period'), q.get('years')]).toEqual(['005930', 'D', '5'])
  })

  it('M1-b: 기본 기간은 일봉 — aria-pressed', async () => {
    installChart()
    renderModal()
    expect(screen.getByTestId('stock-chart-period-D')).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByTestId('stock-chart-period-W')).toHaveAttribute('aria-pressed', 'false')
    expect(screen.getByTestId('stock-chart-period-M')).toHaveAttribute('aria-pressed', 'false')
    expect(screen.getByTestId('stock-chart-period-D').textContent).toContain('일봉')
    expect(screen.getByTestId('stock-chart-period-W').textContent).toContain('주봉')
    expect(screen.getByTestId('stock-chart-period-M').textContent).toContain('월봉')
    await waitPeriod('day')
  })

  it('M1-c: 행 이름이 비면 제목은 응답 name 을 쓴다', async () => {
    installChart()
    renderModal({ name: '' })
    await waitFor(() =>
      expect(screen.getByTestId('stock-chart-title').textContent).toContain('삼성전자'),
    )
    expect(screen.getByTestId('stock-chart-title').textContent).toContain('005930')
  })

  it('M1-d: 모듈 최상위에서 ko-KR 로케일을 한 번 등록한다', () => {
    expect(registerLocaleCalls.length).toBeGreaterThanOrEqual(1)
    expect(registerLocaleCalls[0][0]).toBe('ko-KR')
    expect(registerLocaleCalls[0][1]).toEqual(
      expect.objectContaining({ open: '시가', high: '고가', low: '저가', close: '종가', volume: '거래량' }),
    )
  })
})

// ═════════════════════════════════════════════════════════════════════════════
// M2 — 기간 토글
// ═════════════════════════════════════════════════════════════════════════════
describe('M2: 주봉·월봉 토글', () => {
  it('M2-a: 주봉 → period=W 요청 · setPeriod(week) · 로더가 주봉 · 일봉으로 되돌리면 재요청 0', async () => {
    const user = userEvent.setup()
    const { requests } = installChart()
    renderModal()
    await waitPeriod('day')

    await user.click(screen.getByTestId('stock-chart-period-W'))
    await waitPeriod('week')
    expect(requests.map((u) => u.searchParams.get('period'))).toEqual(['D', 'W'])
    expect(screen.getByTestId('stock-chart-period-W')).toHaveAttribute('aria-pressed', 'true')
    expect((await collectBars(lastChart(), 'init', { type: 'week', span: 1 })).data).toEqual(
      expectedKline('W'),
    )

    await user.click(screen.getByTestId('stock-chart-period-D'))
    await waitPeriod('day')
    expect((await collectBars(lastChart(), 'init')).data).toEqual(expectedKline('D'))
    expect(requests).toHaveLength(2)
    expect(fakeKline.init).toHaveBeenCalledTimes(1)
  })

  it('M2-b: 월봉 → period=M 요청 · setPeriod(month)', async () => {
    const user = userEvent.setup()
    const { requests } = installChart()
    renderModal()
    await waitPeriod('day')
    await user.click(screen.getByTestId('stock-chart-period-M'))
    await waitPeriod('month')
    expect(requests[requests.length - 1].searchParams.get('period')).toBe('M')
    expect((await collectBars(lastChart(), 'init', { type: 'month', span: 1 })).data).toEqual(
      expectedKline('M'),
    )
  })
})

// ═════════════════════════════════════════════════════════════════════════════
// M3·M13 — 오류 · 다시 시도
// ═════════════════════════════════════════════════════════════════════════════
describe('M3: success=false → 오류 + 다시 시도', () => {
  it('M3-a: 백엔드 message 를 보여 주고 「다시 시도」 는 요청 1건을 더 보낸다', async () => {
    const user = userEvent.setup()
    const failed = {
      success: false,
      data: null,
      message: 'KIS 조회 실패 [EGW00201] 초당 거래건수를 초과하였습니다.',
    }
    const { requests, state } = installChart(() => failed)
    renderModal()

    const err = await screen.findByTestId('stock-chart-error', {}, { timeout: 10000 })
    expect(err.textContent).toContain('KIS 조회 실패 [EGW00201] 초당 거래건수를 초과하였습니다.')
    const before = requests.length

    state.respond = (p) => STOCK_CHART_RESPONSES[p]
    await user.click(screen.getByTestId('stock-chart-retry'))
    await waitPeriod('day')
    await waitFor(() => expect(screen.queryByTestId('stock-chart-error')).toBeNull())
    expect(requests.length - before).toBe(1)
  }, 20000)
})

describe('M13: 422(axios 오류) → detail 을 보여 준다', () => {
  it('M13-a: FastAPI 검증 detail 의 msg 가 오류 칸에 선다', async () => {
    installChart(
      () =>
        HttpResponse.json(
          {
            detail: [
              {
                type: 'less_than_equal',
                loc: ['query', 'years'],
                msg: 'Input should be less than or equal to 5',
                input: '9',
              },
            ],
          },
          { status: 422 },
        ) as unknown as Response,
    )
    renderModal()
    const err = await screen.findByTestId('stock-chart-error', {}, { timeout: 10000 })
    expect(err.textContent).toContain('Input should be less than or equal to 5')
    expect(screen.getByTestId('stock-chart-retry')).toBeInTheDocument()
  }, 20000)
})

// ═════════════════════════════════════════════════════════════════════════════
// M4~M7 — 빈 · 부분 · 잠정 · 지원 안 됨
// ═════════════════════════════════════════════════════════════════════════════
describe('M4: 빈 결과', () => {
  it('M4-a: bars=[] → stock-chart-empty, 로더는 빈 목록', async () => {
    installChart((p) =>
      withData(p, { bars: [], last_bar_provisional: false }, '표시할 봉이 없습니다'),
    )
    renderModal()
    const empty = await screen.findByTestId('stock-chart-empty', {}, { timeout: 5000 })
    expect(empty.textContent).toContain('표시할 봉이 없습니다')
    if (fakeKline.charts.length > 0 && lastChart().fn('setDataLoader').mock.calls.length > 0) {
      expect((await collectBars(lastChart(), 'init')).data).toEqual([])
    }
    expect(screen.queryByTestId('stock-chart-provisional')).toBeNull()
  })
})

describe('M5: 부분 결과', () => {
  it('M5-a: complete=false → stock-chart-partial 에 첫 봉 날짜·사유, 차트는 그린다', async () => {
    installChart((p) => withData(p, { complete: false, incomplete_reason: 'window_error' }))
    renderModal()
    const partial = await screen.findByTestId('stock-chart-partial', {}, { timeout: 5000 })
    expect(partial.textContent).toContain('일부 구간만')
    expect(partial.textContent).toContain('2026-09-18')
    expect(partial.textContent).toContain('window_error')
    await waitPeriod('day')
    expect((await collectBars(lastChart(), 'init')).data).toEqual(expectedKline('D'))
  })

  it('M5-b: complete=true 면 부분 안내가 없다', async () => {
    installChart()
    renderModal()
    await waitPeriod('day')
    expect(screen.queryByTestId('stock-chart-partial')).toBeNull()
  })

  /** 61초 뒤로 시계를 민 채(`Date.now` 오프셋) 주봉 → 일봉으로 되돌려 일봉 재요청 여부를 본다. */
  async function periodsAfterRevisitAt61s(requests: URL[]) {
    const user = userEvent.setup()
    await waitPeriod('day')
    const realNow = Date.now.bind(Date)
    const spy = vi.spyOn(Date, 'now').mockImplementation(() => realNow() + 61_000)
    try {
      await user.click(screen.getByTestId('stock-chart-period-W'))
      await waitPeriod('week')
      await user.click(screen.getByTestId('stock-chart-period-D'))
      await waitPeriod('day')
      await new Promise((r) => setTimeout(r, 80))
    } finally {
      spy.mockRestore()
    }
    return requests.map((u) => u.searchParams.get('period'))
  }

  it('M5-c: 부분 결과는 1분이 지나면 낡은 것으로 본다 — 다시 보면 다시 받는다(안내 문구와 같은 값)', async () => {
    const { requests } = installChart((p) =>
      withData(p, { complete: false, incomplete_reason: 'window_error' }),
    )
    renderModal()
    await screen.findByTestId('stock-chart-partial', {}, { timeout: 5000 })
    expect(await periodsAfterRevisitAt61s(requests)).toEqual(['D', 'W', 'D'])
  })

  it('M5-d: 완전 결과는 61초 뒤에도 그대로 쓴다(10분) — 일봉 재요청 0', async () => {
    const { requests } = installChart()
    renderModal()
    expect(await periodsAfterRevisitAt61s(requests)).toEqual(['D', 'W'])
  })
})

describe('M6: 잠정 봉', () => {
  it('M6-a: 일봉 last_bar_provisional=true → 마지막 봉 날짜를 밝힌다', async () => {
    installChart()
    renderModal()
    const note = await screen.findByTestId('stock-chart-provisional', {}, { timeout: 5000 })
    expect(note.textContent).toContain('2026-09-28')
    expect(note.textContent).toContain('잠정')
  })

  it('M6-b: 주봉이면 「이번 주」', async () => {
    const user = userEvent.setup()
    installChart()
    renderModal()
    await waitPeriod('day')
    await user.click(screen.getByTestId('stock-chart-period-W'))
    await waitPeriod('week')
    await waitFor(() =>
      expect(screen.getByTestId('stock-chart-provisional').textContent).toContain('이번 주'),
    )
  })

  it('M6-c: 월봉이면 「이번 달」', async () => {
    const user = userEvent.setup()
    installChart()
    renderModal()
    await waitPeriod('day')
    await user.click(screen.getByTestId('stock-chart-period-M'))
    await waitPeriod('month')
    await waitFor(() =>
      expect(screen.getByTestId('stock-chart-provisional').textContent).toContain('이번 달'),
    )
  })

  it('M6-d: false 면 요소가 없다', async () => {
    installChart((p) => withData(p, { last_bar_provisional: false }))
    renderModal()
    await waitPeriod('day')
    expect(screen.queryByTestId('stock-chart-provisional')).toBeNull()
  })
})

describe('M7: 6자리 숫자가 아닌 코드', () => {
  it('M7-a: Q12345 → stock-chart-unsupported(받은 값 표시) · 요청 0', async () => {
    const { requests } = installChart()
    renderModal({ ticker: 'Q12345', name: '어떤종목' })
    const box = screen.getByTestId('stock-chart-unsupported')
    expect(box.textContent).toContain('Q12345')
    expect(box.textContent).toContain('6자리')
    await new Promise((r) => setTimeout(r, 50))
    expect(requests).toHaveLength(0)
    expect(screen.queryByTestId('stock-chart-loading')).toBeNull()
  })
})

// ═════════════════════════════════════════════════════════════════════════════
// M8·M9 — 닫기 · 해제
// ═════════════════════════════════════════════════════════════════════════════
describe('M8: 닫기 3경로 + 포커스 복귀', () => {
  it('M8-a: × 버튼 → onClose', async () => {
    const user = userEvent.setup()
    installChart()
    const { onClose } = renderModal()
    const close = screen.getByTestId('stock-chart-close')
    expect(close).toHaveAttribute('aria-label', '닫기')
    await user.click(close)
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('M8-b: ESC → onClose', async () => {
    const user = userEvent.setup()
    installChart()
    const { onClose } = renderModal()
    await user.keyboard('{Escape}')
    await waitFor(() => expect(onClose).toHaveBeenCalled())
  })

  it('M8-c: 패널 안 클릭은 닫지 않고 바깥(오버레이) 클릭은 닫는다 · dialog 접근성', async () => {
    const user = userEvent.setup()
    installChart()
    const { onClose } = renderModal()
    const dialog = screen.getByRole('dialog')
    expect(dialog).toHaveAttribute('aria-modal', 'true')
    const labelledBy = dialog.getAttribute('aria-labelledby')
    expect(labelledBy).toBeTruthy()
    expect(document.getElementById(labelledBy as string)).toBe(screen.getByTestId('stock-chart-title'))

    await user.click(screen.getByTestId('stock-chart-period-W'))
    await user.click(dialog)
    expect(onClose).not.toHaveBeenCalled()

    const root = screen.getByTestId('stock-chart-modal')
    const overlay = root === dialog ? (root.parentElement as HTMLElement) : root
    await user.click(overlay)
    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1))
  })

  it('M8-d: 닫힌 뒤 연 요소로 포커스가 돌아간다', async () => {
    const user = userEvent.setup()
    installChart()
    function Harness() {
      const [open, setOpen] = useState(false)
      return (
        <>
          <button type="button" onClick={() => setOpen(true)}>
            차트 열기
          </button>
          {open && <StockChartModal ticker="005930" name="삼성전자" onClose={() => setOpen(false)} />}
        </>
      )
    }
    render(
      <TestProviders>
        <Harness />
      </TestProviders>,
    )
    const opener = screen.getByRole('button', { name: '차트 열기' })
    await user.click(opener)
    expect(screen.getByTestId('stock-chart-modal')).toBeInTheDocument()
    // 모달 안 버튼으로 포커스를 옮긴 뒤 닫는다 — 그 버튼이 사라지면 복귀 없이는 포커스가 body 로 떨어진다.
    await user.click(screen.getByTestId('stock-chart-period-W'))
    expect(document.activeElement).toBe(screen.getByTestId('stock-chart-period-W'))
    await user.keyboard('{Escape}')
    await waitFor(() => expect(screen.queryByTestId('stock-chart-modal')).toBeNull())
    expect(document.activeElement).toBe(opener)
  })
})

describe('M9: 언마운트 → dispose', () => {
  it('M9-a: dispose(host) 1회 — init 에 준 요소와 같다', async () => {
    installChart()
    const { unmount } = renderModal()
    await waitPeriod('day')
    const el = lastChart().el
    unmount()
    expect(fakeKline.dispose).toHaveBeenCalledTimes(1)
    const arg = fakeKline.dispose.mock.calls[0][0]
    expect(arg === el || arg === lastChart().chart).toBe(true)
  })
})

// ═════════════════════════════════════════════════════════════════════════════
// M10~M12 — 색 · 날짜 · 메타
// ═════════════════════════════════════════════════════════════════════════════
describe('M10: 국내 관례 색 — 상승 적색 · 하락 청색 (라이브러리 기본의 반대)', () => {
  it('M10-a: 캔들·거래량 색은 pnlColor 상수', async () => {
    installChart()
    renderModal()
    await waitPeriod('day')
    const styles = lastChart().options?.styles
    const bar = styles?.candle?.bar ?? {}
    for (const k of ['upColor', 'upBorderColor', 'upWickColor']) expect(bar[k], k).toBe(PROFIT_HEX)
    for (const k of ['downColor', 'downBorderColor', 'downWickColor']) expect(bar[k], k).toBe(LOSS_HEX)
    for (const k of ['noChangeColor', 'noChangeBorderColor', 'noChangeWickColor'])
      expect(bar[k], k).toBe(NEUTRAL_HEX)
    const vol = styles?.indicator?.bars?.[0] ?? {}
    expect(vol.upColor).toBe(PROFIT_HEX)
    expect(vol.downColor).toBe(LOSS_HEX)
  })
})

describe('M11: 축·툴팁 날짜는 KST (TZ=UTC 에서도)', () => {
  it('M11-a: 툴팁 = YYYY-MM-DD · 월봉 x축 = YYYY-MM', async () => {
    const user = userEvent.setup()
    installChart()
    renderModal()
    await waitPeriod('day')
    const formatDate = lastChart().options?.formatter?.formatDate as (p: Record<string, unknown>) => string
    const ts = Date.UTC(2026, 8, 24, 15) // 2026-09-25 00:00 KST
    const call = (type: string) =>
      formatDate({ dateTimeFormat: undefined, timestamp: ts, template: 'YYYY-MM-DD', type })
    expect(call('tooltip')).toBe('2026-09-25')
    expect(call('xAxis')).toBe('2026-09-25')

    await user.click(screen.getByTestId('stock-chart-period-M'))
    await waitPeriod('month')
    expect(call('xAxis')).toBe('2026-09')
    expect(call('tooltip')).toBe('2026-09-25')
  })
})

describe('M12: 메타 줄', () => {
  it('M12-a: 구간 · 봉 수(천 단위) · 수정주가 · KRX', async () => {
    const bars = Array.from({ length: 1231 }, (_, i) => {
      const d = new Date(Date.UTC(2021, 8, 28) + i * 86_400_000).toISOString().slice(0, 10)
      return { date: d, open: 70000, high: 70500, low: 69500, close: 70200, volume: 1000, amount: 70_200_000 }
    })
    installChart((p) => withData(p, { bars }, '일봉 1,231개'))
    renderModal()
    await waitPeriod('day')
    const meta = screen.getByTestId('stock-chart-meta')
    expect(meta.textContent).toContain('2021-09-28')
    expect(meta.textContent).toContain('2026-09-28')
    expect(meta.textContent).toContain('1,231')
    expect(meta.textContent).toContain('수정주가')
    expect(meta.textContent).toContain('KRX')
    expect(meta.textContent).not.toContain('NaN')
  })
})
