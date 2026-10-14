/**
 * 거래일지 차트 모달 — cycle457.
 *
 * 사용자 요청(2026-10-15): 「매매일지에 캔들차트와 함께 전략들에서 사용하는 기술적 지표들을 표시하고
 * 진입청산위치를 캔들차트위에 표시하고 싶어」.
 *
 * ## 이 화면이 그리는 것
 * - 일봉 캔들(상승 빨강 · 하락 파랑) — 종목 차트(`StockChartModal`)와 같은 원천(서버 캐시 공유).
 * - 캔들 위 — 그 전략이 판정에 쓰는 선(이평선·돌파선·청산 채널·목표가). 🔴 **화면은 계산하지 않는다** —
 *   백엔드 `GET /api/journal-chart` 가 그 전략 객체의 `chart_indicators`(매수·청산 판정과 같은 함수)로 낸
 *   봉별 값을 받아 그리기만 한다(사용자 지시 2026-10-15 「소스 중복」).
 * - 캔들 위 — 매수 체결 ▲(빨강) · 매도 체결 ▼(파랑) 표시와 그 가격·수량, 손절선 계단(파랑 점선) ·
 *   익절 목표(빨강 점선)를 보유 구간에만.
 * - 아래 칸 — 거래량 막대 · 응답에 있으면 ATR 칸 · MACD 칸(kojiro 대순환 MACD).
 *
 * ## 지키는 계약
 * - 셸·ESC·바깥 클릭·포커스 복귀는 `StockChartModal` 관용구 그대로.
 * - 차트 라이브러리 지표는 이 파일이 등록한 사용자 지표 셋(`JOURNAL_LINES`·`JOURNAL_ATR`·`JOURNAL_MACD`)
 *   과 내장 `VOL` 뿐이다 — 사용자 지표의 `calc` 는 응답 값을 봉 날짜로 찾아 돌려줄 뿐 계산하지 않는다.
 * - 색은 `index.css` 토큰을 실행 중에 읽어 쓴다(캔버스는 CSS 변수를 못 읽는다). 상승·하락·매수·매도 색은
 *   `utils/pnlColor.ts` 단일 출처.
 * - KST 는 전부 `utils/kst.ts` 위임 — 이 파일에 날짜 포맷터를 만들지 않는다.
 * - 이 화면은 **읽기만** 한다 — 매매·설정을 바꾸는 호출이 없다.
 */

import { useEffect, useMemo, useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import { dispose, init, registerIndicator, registerLocale, registerOverlay } from 'klinecharts'
import type { Chart, KLineData } from 'klinecharts'

import { getJournalChart } from '../api/journal-chart'
import type { JournalCard } from '../types/journal'
import type { IndicatorLine, IndicatorPane, JournalChartData } from '../types/journal-chart'
import { strategyLabel } from '../utils/strategyMeta'
import { isChartableTicker, KLINE_LOCALE_KO, toKLineData } from '../utils/stockChart'
import type { KLineBar } from '../utils/stockChart'
import { formatKstDateFromEpochMs, kstDateToEpochMs, KST_TIME_ZONE } from '../utils/kst'
import { LOSS_HEX, NEUTRAL_HEX, PROFIT_HEX } from '../utils/pnlColor'
import { holdRange, stopSteps, targetSteps, tradeMarks } from '../utils/journalChart'
import type { TradeMark } from '../utils/journalChart'

const TITLE_ID = 'journal-chart-modal-title'
const CANDLE_PANE_ID = 'candle_pane'
const VOL_PANE = { id: 'journal_chart_vol', height: 60 }
const ATR_PANE = { id: 'journal_chart_atr', height: 70 }
const MACD_PANE = { id: 'journal_chart_macd', height: 90 }
const MARK_OVERLAY = 'journalTradeMark'
const MARK_GROUP = 'journal_trade_marks'
/** 매매 구간 오른쪽에 남길 봉 수 — 청산 뒤 흐름이 조금 보이게. */
const FOCUS_TAIL_BARS = 15

type LineTone = 'navy' | 'sky' | 'brown' | 'beige' | 'gray' | 'red' | 'blue'

/** 선 색 이름 → `index.css` 토큰 변수. 모르는 이름은 회색. */
const TONE_VAR: Record<LineTone, string> = {
  navy: '--color-navy-600',
  sky: '--color-sky-500',
  brown: '--color-brown-500',
  beige: '--color-beige-500',
  gray: '--color-gray-500',
  red: '--color-red-500',
  blue: '--color-blue-500',
}

function toneOf(tone: string): LineTone {
  return (tone in TONE_VAR ? tone : 'gray') as LineTone
}

/** 토큰 색을 실행 중에 읽는다. 못 읽으면(테스트 환경 등) 보합 색. */
function toneColor(tone: LineTone): string {
  if (tone === 'red') return PROFIT_HEX
  if (tone === 'blue') return LOSS_HEX
  try {
    const v = getComputedStyle(document.documentElement).getPropertyValue(TONE_VAR[tone]).trim()
    return v || NEUTRAL_HEX
  } catch {
    return NEUTRAL_HEX
  }
}

// 종목 차트 모달과 같은 한글 로케일 — 이 모달만 먼저 열려도 툴팁이 한글이다.
registerLocale('ko-KR', KLINE_LOCALE_KO)

type CalcFn = (dataList: KLineData[]) => Record<string, number | null>[]

// 모듈 최상위 1회 — 각 지표의 `extendData.calc` 가 응답 값을 봉 날짜로 찾아 돌려준다(계산 없음).
for (const name of ['JOURNAL_LINES', 'JOURNAL_ATR', 'JOURNAL_MACD']) {
  registerIndicator<Record<string, number | null>, number, { calc: CalcFn }>({
    name,
    shortName: name,
    figures: [],
    calc: (dataList, indicator) => {
      const fn = indicator.extendData?.calc
      return typeof fn === 'function' ? fn(dataList) : dataList.map(() => ({}))
    },
  })
}

// 매수 ▲ · 매도 ▼ 표시 — 체결가 위치에 꼭짓점, 그 아래(매수)·위(매도)에 「매수 12,300×10」.
registerOverlay<{ side: 'BUY' | 'SELL'; label: string; color: string }>({
  name: MARK_OVERLAY,
  totalStep: 2,
  needDefaultPointFigure: false,
  needDefaultXAxisFigure: false,
  needDefaultYAxisFigure: false,
  createPointFigures: ({ overlay, coordinates }) => {
    const c = coordinates[0]
    const d = overlay.extendData
    if (!c || !d) return []
    const dir = d.side === 'BUY' ? 1 : -1
    const tip = c.y + dir * 2
    const base = c.y + dir * 12
    return [
      {
        type: 'polygon',
        attrs: { coordinates: [{ x: c.x, y: tip }, { x: c.x - 6, y: base }, { x: c.x + 6, y: base }] },
        styles: { style: 'fill', color: d.color },
        ignoreEvent: true,
      },
      {
        type: 'text',
        attrs: { x: c.x, y: base + dir * 2, text: d.label, align: 'center', baseline: d.side === 'BUY' ? 'top' : 'bottom' },
        styles: { color: 'white', backgroundColor: d.color, size: 11, paddingLeft: 3, paddingRight: 3, paddingTop: 2, paddingBottom: 2, borderRadius: 2 },
        ignoreEvent: true,
      },
    ]
  },
})

interface Props {
  card: JournalCard
  onClose: () => void
}

interface DrawLine {
  key: string
  title: string
  tone: LineTone
  dashed: boolean
  emphasis?: boolean
}

function toDrawLine(l: IndicatorLine): DrawLine {
  return { key: l.key, title: l.title, tone: toneOf(l.tone), dashed: l.dashed }
}

function lineStyles(lines: DrawLine[]) {
  return lines.map((l) => ({
    color: toneColor(l.tone),
    size: l.emphasis ? 1.5 : 1,
    style: l.dashed ? ('dashed' as const) : ('solid' as const),
    dashedValue: [4, 3],
    smooth: false,
  }))
}

const PANE_INDICATOR: Record<Exclude<IndicatorPane, 'price'>, { name: string; pane: { id: string; height: number } }> = {
  atr: { name: 'JOURNAL_ATR', pane: ATR_PANE },
  macd: { name: 'JOURNAL_MACD', pane: MACD_PANE },
}

/** 응답의 봉 날짜 → 봉 번호. 차트 라이브러리가 넘긴 봉을 날짜로 찾아 응답 값을 꺼낸다. */
function indexByDate(data: JournalChartData): Map<string, number> {
  const m = new Map<string, number>()
  data.bars.forEach((b, i) => m.set(b.date, i))
  return m
}

export default function JournalChartModal({ card, onClose }: Props) {
  const ticker = card.ticker
  const chartable = isChartableTicker(ticker)
  const hostRef = useRef<HTMLDivElement | null>(null)
  const chartRef = useRef<Chart | null>(null)
  const barsRef = useRef<KLineBar[]>([])
  const openerRef = useRef<Element | null>(null)

  useEffect(() => {
    const onEsc = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onEsc)
    return () => document.removeEventListener('keydown', onEsc)
  }, [onClose])

  useEffect(() => {
    openerRef.current = document.activeElement
    return () => {
      const el = openerRef.current
      if (el instanceof HTMLElement && document.contains(el)) el.focus()
    }
  }, [])

  const { from: holdFrom } = holdRange(card)
  // 일봉 + 그 전략의 지표 값(백엔드가 전략 함수로 계산) — 화면은 그리기만 한다.
  const chartQuery = useQuery({
    queryKey: ['journalChart', ticker, card.strategy, holdFrom],
    queryFn: () => getJournalChart(ticker, card.strategy, holdFrom),
    enabled: chartable,
    retry: 1,
    staleTime: (q) => (q.state.data?.complete === false ? 60_000 : 10 * 60_000),
    gcTime: 30 * 60_000,
  })
  const marks = useMemo(() => tradeMarks(card), [card])

  // 차트 마운트 — 종목이 바뀔 때만 다시 만든다.
  useEffect(() => {
    if (!chartable) return
    const host = hostRef.current
    if (!host) return
    const chart = init(host, {
      locale: 'ko-KR',
      timezone: KST_TIME_ZONE,
      formatter: { formatDate: ({ timestamp }) => formatKstDateFromEpochMs(timestamp) },
      styles: {
        candle: {
          bar: {
            upColor: PROFIT_HEX, upBorderColor: PROFIT_HEX, upWickColor: PROFIT_HEX,
            downColor: LOSS_HEX, downBorderColor: LOSS_HEX, downWickColor: LOSS_HEX,
            noChangeColor: NEUTRAL_HEX, noChangeBorderColor: NEUTRAL_HEX, noChangeWickColor: NEUTRAL_HEX,
          },
        },
        indicator: { bars: [{ upColor: PROFIT_HEX, downColor: LOSS_HEX, noChangeColor: NEUTRAL_HEX }] },
      },
    })
    chartRef.current = chart
    if (chart) {
      chart.setSymbol({ ticker, pricePrecision: 0, volumePrecision: 0 })
      chart.createIndicator({ name: 'VOL', paneId: VOL_PANE.id, calcParams: [] })
      chart.setPaneOptions(VOL_PANE)
      chart.setDataLoader({
        getBars: ({ type, callback }) => {
          callback(type === 'init' ? barsRef.current : [], false)
        },
      })
    }
    let observer: ResizeObserver | undefined
    if (chart && typeof ResizeObserver !== 'undefined') {
      observer = new ResizeObserver(() => chart.resize())
      observer.observe(host)
    }
    return () => {
      observer?.disconnect()
      dispose(host)
      chartRef.current = null
    }
  }, [chartable, ticker])

  // 봉 + 지표 + 표시 — 응답이 오면 그린다.
  useEffect(() => {
    const chart = chartRef.current
    const data = chartQuery.data
    if (!chart || !data) return
    barsRef.current = toKLineData(data.bars)

    for (const name of ['JOURNAL_LINES', 'JOURNAL_ATR', 'JOURNAL_MACD']) chart.removeIndicator({ name })
    chart.removeOverlay({ groupId: MARK_GROUP })

    const idx = indexByDate(data)
    const series = data.indicators.series
    const lookup = (lines: DrawLine[]): CalcFn => (dataList) =>
      dataList.map((d) => {
        const i = idx.get(formatKstDateFromEpochMs(d.timestamp))
        const row: Record<string, number | null> = {}
        for (const l of lines) row[l.key] = i === undefined ? null : (series[l.key]?.[i] ?? null)
        return row
      })

    const strategyPrice = data.indicators.lines.filter((l) => l.pane === 'price').map(toDrawLine)
    const cardLines: DrawLine[] = [
      { key: 'stop', title: '손절선', tone: 'blue', dashed: true, emphasis: true },
      { key: 'target', title: '익절 목표', tone: 'red', dashed: true, emphasis: true },
    ]
    const priceLines = [...strategyPrice, ...cardLines]
    const priceCalc: CalcFn = (dataList) => {
      const dates = dataList.map((d) => formatKstDateFromEpochMs(d.timestamp))
      const stop = stopSteps(dates, card)
      const target = targetSteps(dates, card)
      return lookup(strategyPrice)(dataList).map((r, i) => ({ ...r, stop: stop[i], target: target[i] }))
    }
    chart.createIndicator(
      {
        name: 'JOURNAL_LINES',
        shortName: strategyLabel(card.strategy),
        paneId: CANDLE_PANE_ID,
        precision: 0,
        figures: priceLines.map((l) => ({ key: l.key, title: `${l.title}: `, type: 'line' })),
        styles: { lines: lineStyles(priceLines) },
        extendData: { calc: priceCalc },
      },
      true,
    )
    for (const pane of ['atr', 'macd'] as const) {
      const lines = data.indicators.lines.filter((l) => l.pane === pane).map(toDrawLine)
      if (lines.length === 0) continue
      const { name, pane: paneOpt } = PANE_INDICATOR[pane]
      chart.createIndicator({
        name,
        shortName: pane === 'macd' ? 'MACD' : lines[0].title,
        paneId: paneOpt.id,
        precision: 0,
        figures: lines.map((l) => ({ key: l.key, title: `${l.title}: `, type: 'line' })),
        styles: { lines: lineStyles(lines) },
        extendData: { calc: lookup(lines) },
      })
      chart.setPaneOptions(paneOpt)
    }

    chart.setPeriod({ type: 'day', span: 1 })

    for (const m of marks) {
      const ts = kstDateToEpochMs(m.date)
      if (ts === null) continue
      chart.createOverlay({
        name: MARK_OVERLAY,
        groupId: MARK_GROUP,
        paneId: CANDLE_PANE_ID,
        lock: true,
        points: [{ timestamp: ts, value: m.price }],
        extendData: { side: m.side, label: m.label, color: m.side === 'BUY' ? PROFIT_HEX : LOSS_HEX },
      })
    }

    const focus = focusTimestamp(barsRef.current, card)
    if (focus !== null) chart.scrollToTimestamp(focus)
  }, [chartQuery.data, card, marks])

  const data = chartQuery.data
  const firstBarDate = data && data.bars.length > 0 ? data.bars[0].date : null
  const from = holdFrom
  const beforeData = !!(from && firstBarDate && from < firstBarDate)
  const titleText = `${card.ticker_name || ticker} (${ticker}) — ${strategyLabel(card.strategy)} 매매 차트`

  return (
    <div
      data-testid="journal-chart-modal"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-2"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={TITLE_ID}
        className="bg-white rounded-lg shadow-xl w-[calc(100vw-16px)] sm:w-full sm:max-w-5xl mx-2 sm:mx-4 max-h-[92vh] overflow-hidden flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-4 py-3 border-b border-gray-200 shrink-0">
          <h2 id={TITLE_ID} data-testid="journal-chart-title" className="text-base font-semibold text-gray-900 truncate">
            {titleText}
          </h2>
          <button
            type="button"
            data-testid="journal-chart-close"
            onClick={onClose}
            aria-label="닫기"
            className="text-gray-500 hover:text-gray-700 text-xl font-bold shrink-0 ml-2"
          >
            ×
          </button>
        </div>

        {!chartable ? (
          <div className="px-4 py-6 text-sm text-gray-500" data-testid="journal-chart-unsupported">
            6자리 숫자 종목코드만 차트를 볼 수 있습니다 (받은 값: {ticker || '(없음)'})
          </div>
        ) : (
          <div className="px-4 py-3 overflow-y-auto flex-1 flex flex-col gap-2">
            <Legend data={data ?? null} marks={marks} card={card} />

            {chartQuery.isLoading && (
              <div data-testid="journal-chart-loading" className="text-sm text-gray-500 py-2">
                차트 불러오는 중… (5년 일봉은 수 초 걸립니다)
              </div>
            )}
            {chartQuery.isError && (
              <div
                data-testid="journal-chart-error"
                className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 flex items-center justify-between gap-2"
              >
                <span className="break-words">
                  {chartQuery.error instanceof Error ? chartQuery.error.message : '차트 조회 실패'}
                </span>
                <button
                  type="button"
                  data-testid="journal-chart-retry"
                  onClick={() => chartQuery.refetch()}
                  className="shrink-0 px-2 py-1 text-xs border border-red-300 rounded hover:bg-red-100"
                >
                  다시 시도
                </button>
              </div>
            )}
            {data && data.bars.length === 0 && (
              <div data-testid="journal-chart-empty" className="text-sm text-gray-500 py-2">
                표시할 봉이 없습니다
              </div>
            )}
            {beforeData && (
              <div data-testid="journal-chart-before-data" className="text-xs text-amber-700">
                매수일({from})이 받은 일봉 첫날({firstBarDate})보다 앞이라 일부 표시가 차트 밖에 있습니다
              </div>
            )}
            {data && data.last_bar_provisional && (
              <div data-testid="journal-chart-provisional" className="text-[11px] text-gray-400">
                마지막 봉({data.bars[data.bars.length - 1]?.date ?? '—'})은 잠정값입니다 — 다음 날 아침 확정됩니다
              </div>
            )}

            <div ref={hostRef} data-testid="journal-chart-canvas-host" className="h-[66vh] min-h-[440px] w-full" />
          </div>
        )}
      </div>
    </div>
  )
}

/** 매매 구간이 화면 오른쪽 끝에서 `FOCUS_TAIL_BARS` 봉 안쪽에 오도록 스크롤할 봉 시각. */
function focusTimestamp(bars: KLineBar[], card: JournalCard): number | null {
  if (bars.length === 0) return null
  const { from, to } = holdRange(card)
  const endDate = to ?? from
  if (!endDate) return null
  const endTs = kstDateToEpochMs(endDate)
  if (endTs === null) return null
  let idx = bars.findIndex((b) => b.timestamp >= endTs)
  if (idx < 0) idx = bars.length - 1
  return bars[Math.min(bars.length - 1, idx + FOCUS_TAIL_BARS)].timestamp
}

function Swatch({ tone, dashed }: { tone: LineTone; dashed?: boolean }) {
  return (
    <span
      aria-hidden="true"
      className="inline-block w-4 align-middle"
      style={{ borderTop: `2px ${dashed ? 'dashed' : 'solid'} var(${TONE_VAR[tone]})` }}
    />
  )
}

function Legend({ data, marks, card }: { data: JournalChartData | null; marks: TradeMark[]; card: JournalCard }) {
  const buys = marks.filter((m) => m.side === 'BUY').length
  const sells = marks.filter((m) => m.side === 'SELL').length
  const stopKnown = card.stop_track.rows.some((r) => r.price !== null) || card.entry.initial_stop.price !== null
  const lines = data?.indicators.lines ?? []
  const paneLabel: Record<string, string> = { price: '', atr: '아래 칸 ', macd: '아래 칸 ' }
  return (
    <div data-testid="journal-chart-legend" className="text-xs text-gray-600 space-y-1">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <span data-testid="journal-chart-marks" data-buys={buys} data-sells={sells}>
          <span className="text-pnl-profit">▲ 매수 {buys}건</span>
          {' · '}
          <span className="text-pnl-loss">▼ 매도 {sells}건</span>
        </span>
        <span data-testid="journal-chart-stop-legend">
          <Swatch tone="blue" dashed /> 손절선{stopKnown ? '' : '(기록 없음)'}
        </span>
        {card.entry.target.price !== null && (
          <span data-testid="journal-chart-target-legend">
            <Swatch tone="red" dashed /> 익절 목표
          </span>
        )}
      </div>
      {data && (
        <>
          {lines.length > 0 && (
            <div data-testid="journal-chart-lines" className="flex flex-wrap items-center gap-x-3 gap-y-1">
              <span className="text-gray-500">전략 지표(전략 판정과 같은 계산):</span>
              {lines.map((l) => (
                <span key={l.key} data-testid={`journal-chart-line-${l.key}`} data-pane={l.pane}>
                  <Swatch tone={toneOf(l.tone)} dashed={l.dashed} /> {paneLabel[l.pane] ?? ''}{l.title}
                </span>
              ))}
            </div>
          )}
          {data.indicators.notes.map((n) => (
            <div key={n} data-testid="journal-chart-note" className="text-gray-400">
              {n}
            </div>
          ))}
        </>
      )}
    </div>
  )
}
