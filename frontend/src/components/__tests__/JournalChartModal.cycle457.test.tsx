/**
 * cycle457 — 거래일지 카드 「차트」 버튼 → `JournalChartModal`.
 *
 * - JC1: 카드 버튼이 모달을 열고 `GET /api/journal-chart?ticker&strategy&from` 한 번으로 일봉·지표를 받아 그린다
 * - JC2: kojiro — 응답의 선을 칸별로(캔들 위 EMA + 손절선·익절 목표 · 아래 ATR · 아래 MACD) 그린다
 * - JC3: 매수 ▲(빨강)·매도 ▼(파랑) 표시가 체결 날짜·가격에 하나씩
 * - JC4: 지표 `calc` 는 응답 값을 봉 날짜로 찾아 돌려줄 뿐이다(계산 없음) + 손절선 계단은 보유 구간 안만
 * - JC5: 조회 실패 = 오류 문장 + 다시 시도
 * - JC6: 닫기
 *
 * jsdom 에는 canvas 가 없어 `klinecharts` 는 `test/fakeKlinecharts.ts` 로 대체한다(호출 기록만 한다).
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'

import JournalCard from '../JournalCard'
import { server } from '../../test/server'
import { TestProviders } from '../../test/providers'
import { failed, wrap } from '../../test/factories'
import { JOURNAL_CHART_FIXTURE } from '../../test/fixtures/journalChart.fixture'
import { JOURNAL_FIXTURE } from '../../test/fixtures/journal.fixture'
import { lastChart, resetFakeKline } from '../../test/fakeKlinecharts'
import type { JournalCard as JournalCardType } from '../../types/journal'
import { LOSS_HEX, PROFIT_HEX } from '../../utils/pnlColor'

vi.mock('klinecharts', async () => (await import('../../test/fakeKlinecharts')).klinechartsModule)

const [CARD_OPEN, CARD_BFB] = JOURNAL_FIXTURE.cards as unknown as JournalCardType[]

interface IndicatorArg {
  name: string
  paneId?: string
  figures?: { key: string }[]
  extendData?: { calc: (d: unknown[]) => Record<string, number | null>[] }
}

let chartCalls: string[] = []
beforeEach(() => {
  resetFakeKline()
  chartCalls = []
  server.use(
    http.get('*/api/journal-chart', ({ request }) => {
      const u = new URL(request.url)
      const sid = u.searchParams.get('strategy') ?? ''
      chartCalls.push(`${u.searchParams.get('ticker')}/${sid}/${u.searchParams.get('from')}`)
      return HttpResponse.json(wrap(JOURNAL_CHART_FIXTURE[sid] ?? JOURNAL_CHART_FIXTURE.kojiro))
    }),
  )
})

async function openFor(card: JournalCardType) {
  render(
    <TestProviders>
      <JournalCard card={card} basis="net" stopsRecordStart="2026-10-07" />
    </TestProviders>,
  )
  fireEvent.click(screen.getByTestId('journal-chart-open'))
  await waitFor(() => expect(lastChart().fn('setPeriod').mock.calls.length).toBeGreaterThan(0), { timeout: 5000 })
  return lastChart()
}

function indicators(): IndicatorArg[] {
  return lastChart().fn('createIndicator').mock.calls.map((c) => c[0] as IndicatorArg)
}

describe('JournalChartModal', () => {
  it('JC1 — 버튼이 모달을 열고 일봉·지표를 한 번에 받아 일봉 주기로 그린다', async () => {
    const chart = await openFor(CARD_OPEN)
    expect(screen.getByTestId('journal-chart-modal')).toBeInTheDocument()
    expect(screen.getByTestId('journal-chart-title')).toHaveTextContent('카카오 (035720)')
    expect(chartCalls).toEqual(['035720/kojiro/2026-10-05'])
    expect(chart.fn('setPeriod').mock.calls.at(-1)?.[0]).toEqual({ type: 'day', span: 1 })
    expect(chart.fn('scrollToTimestamp').mock.calls.length).toBeGreaterThan(0)
  })

  it('JC2 — kojiro: 응답의 선을 칸별로 그린다', async () => {
    await openFor(CARD_OPEN)
    const ind = indicators()
    const lines = ind.find((i) => i.name === 'JOURNAL_LINES')!
    expect(lines.paneId).toBe('candle_pane')
    expect(lines.figures!.map((f) => f.key)).toEqual(['ema_s', 'ema_m', 'ema_l', 'stop', 'target'])
    expect(ind.find((i) => i.name === 'JOURNAL_ATR')?.figures!.map((f) => f.key)).toEqual(['atr'])
    expect(ind.find((i) => i.name === 'JOURNAL_MACD')?.figures!.map((f) => f.key)).toEqual(['macd1', 'macd2', 'macd3'])
    expect(ind.find((i) => i.name === 'VOL')?.paneId).toBe('journal_chart_vol')
    expect(screen.getByTestId('journal-chart-lines')).toHaveTextContent('전략 판정과 같은 계산')
    expect(screen.getByTestId('journal-chart-line-macd1')).toHaveAttribute('data-pane', 'macd')
  })

  it('JC3 — 매수 빨강 ▲ · 매도 파랑 ▼ 표시', async () => {
    const chart = await openFor(CARD_BFB)
    const ov = chart.fn('createOverlay').mock.calls.map((c) => c[0] as {
      name: string; points: { timestamp: number; value: number }[]; extendData: { side: string; color: string; label: string }
    })
    expect(ov.map((o) => [o.extendData.side, o.points[0].value, o.extendData.color])).toEqual([
      ['BUY', 12350, PROFIT_HEX],
      ['SELL', 13450, LOSS_HEX],
    ])
    expect(ov[0].points[0].timestamp).toBe(Date.parse('2026-10-05T00:00:00+09:00'))
    expect(screen.getByTestId('journal-chart-marks')).toHaveAttribute('data-buys', '1')
    expect(screen.getByTestId('journal-chart-marks')).toHaveAttribute('data-sells', '1')
    expect(screen.getByTestId('journal-chart-target-legend')).toBeInTheDocument()
    // BFB 는 패턴 전략 — 캔들 위 전략 선 없이 아래 ATR 칸 + 안내
    expect(screen.getByTestId('journal-chart-line-atr')).toHaveAttribute('data-pane', 'atr')
    expect(screen.getAllByTestId('journal-chart-note').map((n) => n.textContent).join()).toContain('깃대')
  })

  it('JC4 — calc 는 응답 값을 봉 날짜로 찾아 돌려준다 + 손절선 계단', async () => {
    await openFor(CARD_OPEN)
    const lines = indicators().find((i) => i.name === 'JOURNAL_LINES')!
    const fx = JOURNAL_CHART_FIXTURE.kojiro
    const i = fx.indicators.series.ema_s.findIndex((v) => v !== null)
    const ts = (d: string) => Date.parse(`${d}T00:00:00+09:00`)
    const day = (d: string) => ({ timestamp: ts(d), open: 1, high: 1, low: 1, close: 1 })
    const rows = lines.extendData!.calc([day(fx.bars[i].date), day('2026-10-02'), day('2026-10-07'), day('2026-10-08')])
    expect(rows[0].ema_s).toBe(fx.indicators.series.ema_s[i])
    expect(rows.map((r) => r.stop)).toEqual([null, null, 47800, 47500])
    expect(rows.every((r) => r.target === null)).toBe(true)
    // 응답에 없는 날짜 = null(지어내지 않는다)
    expect(lines.extendData!.calc([day('2030-01-02')])[0].ema_s).toBeNull()
  })

  it('JC5 — 조회 실패 = 오류 문장 + 다시 시도', async () => {
    server.use(http.get('*/api/journal-chart', () => HttpResponse.json(failed('KIS 조회 실패 [X] 실패'))))
    render(
      <TestProviders>
        <JournalCard card={CARD_OPEN} basis="net" stopsRecordStart="2026-10-07" />
      </TestProviders>,
    )
    fireEvent.click(screen.getByTestId('journal-chart-open'))
    expect(await screen.findByTestId('journal-chart-error', {}, { timeout: 5000 })).toHaveTextContent('KIS 조회 실패')
    expect(screen.getByTestId('journal-chart-retry')).toBeInTheDocument()
  })

  it('JC6 — 닫기', async () => {
    await openFor(CARD_OPEN)
    fireEvent.click(screen.getByTestId('journal-chart-close'))
    await waitFor(() => expect(screen.queryByTestId('journal-chart-modal')).not.toBeInTheDocument())
  })
})
