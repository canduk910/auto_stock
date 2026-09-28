/**
 * cycle388 Red — 종목 차트 보조지표 배치 (`components/StockChartModal.tsx`).
 *
 * 사용자 요청(2026-09-28 23시): 「차트 확인해보았는데 EMA가 아래 거래량쪽에 표시되네. 상단 가격캔들차트에
 * 표시되는게 좋겠어. 아래는 rsi와 macd를 추가로 표시하는게 어때.」
 * — 화면에서 「EMA」로 보인 선은 KLineChart `VOL` 지표가 기본으로 그리는 거래량 이동평균(MA5·10·20)이다.
 *
 * ## 봉인하는 계약
 * - 가격(캔들) 패널 `candle_pane` 에 EMA(5·20·60·120)를 겹친다 — `isStack=true`(캔들 패널의 다른 것을 지우지 않는다).
 * - 이동평균 계열(EMA·MA·SMA·BOLL)은 캔들 패널에만 있다.
 * - 거래량 패널은 막대만 — `VOL` 의 `calcParams` 를 비워 거래량 이동평균선을 그리지 않는다.
 * - 아래 패널은 위에서부터 거래량 · RSI(14) · MACD(12·26·9) 세 개, 서로 다른 패널 id.
 * - 아래 패널 셋은 `setPaneOptions({id, height})` 로 높이를 정한다(라이브러리 기본 100px 이면 캔들이 눌린다).
 *
 * jsdom 에는 canvas 가 없어 `klinecharts` 는 `test/fakeKlinecharts.ts` 로 대체한다(호출 기록만 한다).
 */
import { afterAll, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import type { ComponentType } from 'react'
import { render, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'

import { server } from '../../test/server'
import { TestProviders } from '../../test/providers'
import { STOCK_CHART_RESPONSES, type StockChartPeriodKey } from '../../test/fixtures/stockChart.fixture'
import { lastChart, resetFakeKline } from '../../test/fakeKlinecharts'

vi.mock('klinecharts', async () => (await import('../../test/fakeKlinecharts')).klinechartsModule)

interface ModalProps {
  ticker: string
  name?: string
  onClose: () => void
}

interface IndicatorCall {
  name: string | undefined
  paneId: string | undefined
  calcParams: unknown
  figures: unknown
  isStack: unknown
}

const ORIG_TZ = process.env.TZ
let StockChartModal: ComponentType<ModalProps>
beforeAll(async () => {
  process.env.TZ = 'UTC'
  StockChartModal = (await import('../StockChartModal')).default as ComponentType<ModalProps>
})
afterAll(() => {
  process.env.TZ = ORIG_TZ
})
beforeEach(() => {
  resetFakeKline()
  server.use(
    http.get('/api/stock-chart/candles', ({ request }) => {
      const period = (new URL(request.url).searchParams.get('period') ?? 'D') as StockChartPeriodKey
      return HttpResponse.json(STOCK_CHART_RESPONSES[period])
    }),
  )
})

async function openChart() {
  render(
    <TestProviders>
      <StockChartModal ticker="005930" name="삼성전자" onClose={vi.fn()} />
    </TestProviders>,
  )
  await waitFor(
    () => {
      const calls = lastChart().fn('setPeriod').mock.calls
      expect(calls.length).toBeGreaterThan(0)
    },
    { timeout: 5000 },
  )
  return lastChart()
}

function indicatorCalls(): IndicatorCall[] {
  return lastChart()
    .fn('createIndicator')
    .mock.calls.map((c) => {
      const v = c[0] as unknown
      const o = typeof v === 'string' ? { name: v } : ((v ?? {}) as Record<string, unknown>)
      return {
        name: o.name as string | undefined,
        paneId: o.paneId as string | undefined,
        calcParams: o.calcParams,
        figures: o.figures,
        isStack: c[1],
      }
    })
}

function one(name: string): IndicatorCall {
  const found = indicatorCalls().filter((c) => c.name === name)
  expect(found, `${name} 지표 생성 호출 수`).toHaveLength(1)
  return found[0]
}

describe('C388-1: 이동평균은 가격 캔들 패널에', () => {
  it('C388-1a: EMA(5·20·60·120)를 candle_pane 에 겹친다(isStack=true)', async () => {
    await openChart()
    const ema = one('EMA')
    expect(ema.paneId).toBe('candle_pane')
    expect(ema.calcParams).toEqual([5, 20, 60, 120])
    expect(ema.isStack).toBe(true)
  })

  it('C388-1b: 이동평균 계열은 캔들 패널 밖에 없다', async () => {
    await openChart()
    const averages = indicatorCalls().filter((c) => ['EMA', 'MA', 'SMA', 'BOLL'].includes(c.name ?? ''))
    expect(averages.length).toBeGreaterThan(0)
    for (const c of averages) expect(c.paneId, `${c.name}`).toBe('candle_pane')
  })

  it('C388-1c: 거래량 패널은 막대만 — VOL calcParams 가 비어 있다(거래량 이동평균선 없음)', async () => {
    await openChart()
    const vol = one('VOL')
    expect(vol.calcParams).toEqual([])
    expect(vol.paneId).toBeTruthy()
    expect(vol.paneId).not.toBe('candle_pane')
  })
})

describe('C388-2: 아래 패널 = 거래량 · RSI · MACD', () => {
  it('C388-2a: RSI(14) · MACD(12·26·9) 를 각자 패널에 만든다', async () => {
    await openChart()
    const rsi = one('RSI')
    const macd = one('MACD')
    expect(rsi.calcParams).toEqual([14])
    expect(macd.calcParams).toEqual([12, 26, 9])
    const ids = [one('VOL').paneId, rsi.paneId, macd.paneId]
    for (const id of ids) {
      expect(id).toBeTruthy()
      expect(id).not.toBe('candle_pane')
    }
    expect(new Set(ids).size).toBe(3)
  })

  it('C388-2e: RSI · MACD 는 소수 둘째 자리까지(라이브러리 기본 넷째 자리)', async () => {
    await openChart()
    for (const name of ['RSI', 'MACD']) {
      const call = lastChart()
        .fn('createIndicator')
        .mock.calls.map((c) => c[0] as Record<string, unknown>)
        .find((o) => typeof o === 'object' && o?.name === name)
      expect(call?.precision, name).toBe(2)
    }
  })

  it('C388-2b: RSI 툴팁 제목이 기간을 밝힌다(RSI14)', async () => {
    await openChart()
    const figures = one('RSI').figures as Array<{ key?: string; title?: string }>
    expect(Array.isArray(figures)).toBe(true)
    expect(figures).toHaveLength(1)
    expect(figures[0].key).toBe('rsi1')
    expect(figures[0].title).toContain('RSI14')
  })

  it('C388-2c: 생성 순서 = 거래량 → RSI → MACD (위에서 아래)', async () => {
    await openChart()
    const lower = indicatorCalls()
      .filter((c) => c.paneId !== 'candle_pane')
      .map((c) => c.name)
    expect(lower).toEqual(['VOL', 'RSI', 'MACD'])
  })

  it('C388-2d: 아래 패널 셋은 높이를 명시한다 — 합이 캔들을 누르지 않게 280px 이하', async () => {
    const rec = await openChart()
    const ids = [one('VOL').paneId, one('RSI').paneId, one('MACD').paneId]
    const opts = rec.fn('setPaneOptions').mock.calls.map((c) => c[0] as { id?: string; height?: number })
    let total = 0
    for (const id of ids) {
      const o = opts.find((x) => x.id === id)
      expect(o, `${id} setPaneOptions`).toBeTruthy()
      expect(typeof o?.height).toBe('number')
      expect(o!.height!).toBeGreaterThanOrEqual(40)
      total += o!.height!
    }
    expect(total).toBeLessThanOrEqual(280)
    // 캔들 패널 높이는 건드리지 않는다(남는 높이를 캔들이 가져간다).
    expect(opts.find((x) => x.id === 'candle_pane')).toBeUndefined()
  })
})
