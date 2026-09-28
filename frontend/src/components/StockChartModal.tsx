/**
 * 종목 차트(KLineChart, 최근 5년 일·주·월봉) 모달 — cycle387.
 *
 * 사용자 요청(2026-09-28): 「잔고내역과 거래내역(주문체결내역, 매매손익)에서 종목을 더블클릭하면
 * KLineChart 를 사용한 주식차트조회를 최근 5년치에 대해 일봉/주봉/월봉으로 제공」.
 * 정본: `_workspace/red/cycle387_stock_chart_spec.md` §2.3 · §2.4 · §2.6.
 *
 * ## 이 화면이 지키는 계약
 * - 셸은 `LlmEvaluationModal.tsx` 관용구를 따른다 — 루트(오버레이) testid `stock-chart-modal`,
 *   패널은 `role="dialog" aria-modal aria-labelledby`, ESC·바깥 클릭 닫기, 닫힌 뒤 포커스 복귀.
 * - `klinecharts@10.0.3` v10 API — `init`/`dispose`/`registerLocale` 셋만 이 라이브러리에서 가져온다.
 *   기간(일/주/월) 전환은 `chart.setPeriod()`, 데이터는 `chart.setDataLoader().getBars` 로 흐른다.
 * - 지표 배치(cycle388) — 캔들 패널에 EMA(5·20·60·120), 아래 패널은 위에서부터 거래량(막대만) ·
 *   RSI(14) · MACD(12·26·9). 이동평균 계열은 캔들 패널에만 둔다.
 * - KST 는 전부 `utils/kst.ts` 위임 — 이 파일에 `Intl.DateTimeFormat`/`'Asia/Seoul'` 리터럴을
 *   두지 않는다(K4 가드). 차트 라이브러리에 넘길 tz 는 `KST_TIME_ZONE` 하나뿐이다.
 * - 상태(로딩/오류/빈/부분/잠정/지원안함)를 전부 구분해 보여 준다 — 값을 고치거나 숨기지 않는다.
 */

import { useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import axios from 'axios'
import { dispose, init, registerLocale } from 'klinecharts'
import type { Chart } from 'klinecharts'

import { getStockChart } from '../api/stock-chart'
import type { ChartPeriod } from '../types/stock-chart'
import { isChartableTicker, PERIOD_LABEL, PERIOD_TO_KLINE, toKLineData } from '../utils/stockChart'
import type { KLineBar } from '../utils/stockChart'
import { formatKstDateFromEpochMs, formatKstYearMonthFromEpochMs, KST_TIME_ZONE } from '../utils/kst'
import { LOSS_HEX, NEUTRAL_HEX, PROFIT_HEX } from '../utils/pnlColor'

const TITLE_ID = 'stock-chart-modal-title'
const PERIODS: ChartPeriod[] = ['D', 'W', 'M']

/** 가격(캔들) 패널 id — 라이브러리 `PaneIdConstants.CANDLE` 과 같은 값. */
const CANDLE_PANE_ID = 'candle_pane'
/** 아래 보조 패널 — 위에서부터 거래량 · RSI · MACD. 높이(px)를 정하지 않으면 셋 다 기본 100px 라 캔들이 눌린다. */
const VOL_PANE = { id: 'stock_chart_vol', height: 64 }
const RSI_PANE = { id: 'stock_chart_rsi', height: 80 }
const MACD_PANE = { id: 'stock_chart_macd', height: 90 }

// 모듈 최상위 1회 — KLineChart 기본 로케일(영문)을 한글로 덮는다.
registerLocale('ko-KR', {
  time: '날짜',
  open: '시가',
  high: '고가',
  low: '저가',
  close: '종가',
  volume: '거래량',
  turnover: '거래대금',
  change: '등락',
  second: '초',
  minute: '분',
  hour: '시',
  day: '일',
  week: '주',
  month: '월',
  year: '년',
})

interface Props {
  ticker: string
  name?: string
  onClose: () => void
}

/** axios 오류(422 검증 실패 등)에서 사람이 읽을 메시지를 뽑는다. */
function extractErrorMessage(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const detail = (error.response?.data as { detail?: unknown } | undefined)?.detail
    if (typeof detail === 'string' && detail.trim() !== '') return detail
    if (Array.isArray(detail) && detail.length > 0) {
      return detail
        .map((d) =>
          d && typeof d === 'object' && typeof (d as { msg?: unknown }).msg === 'string'
            ? (d as { msg: string }).msg
            : JSON.stringify(d),
        )
        .join(', ')
    }
    return error.message
  }
  if (error instanceof Error) return error.message
  return '차트 조회 실패'
}

/** 잠정 봉 안내 문구 — D 는 날짜, W·M 은 「이번 주」/「이번 달」. */
function provisionalMessage(period: ChartPeriod, lastDate: string | undefined): string {
  if (period === 'W') {
    return '이번 주 봉은 진행 중입니다 — 장중이거나 애프터마켓(16:00~20:00) 가격이 섞여 있을 수 있습니다.'
  }
  if (period === 'M') {
    return '이번 달 봉은 진행 중입니다 — 장중이거나 애프터마켓(16:00~20:00) 가격이 섞여 있을 수 있습니다.'
  }
  return (
    `마지막 봉(${lastDate ?? '—'})은 잠정값입니다 — 장중이거나 애프터마켓(16:00~20:00) 가격이 ` +
    '종가·고저에 섞여 있을 수 있습니다(다음 날 06:00 무렵 확정).'
  )
}

export default function StockChartModal({ ticker, name, onClose }: Props) {
  const chartable = isChartableTicker(ticker)
  const [period, setPeriod] = useState<ChartPeriod>('D')

  const hostRef = useRef<HTMLDivElement | null>(null)
  const chartRef = useRef<Chart | null>(null)
  const barsRef = useRef<KLineBar[]>([])
  const periodRef = useRef<ChartPeriod>('D')
  const openerRef = useRef<Element | null>(null)

  useEffect(() => {
    periodRef.current = period
  }, [period])

  // ESC 닫기 — `LlmEvaluationModal.tsx` 관용구 그대로.
  useEffect(() => {
    const onEsc = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onEsc)
    return () => document.removeEventListener('keydown', onEsc)
  }, [onClose])

  // 닫을 때 트리거 요소로 포커스 복귀.
  useEffect(() => {
    openerRef.current = document.activeElement
    return () => {
      const el = openerRef.current
      if (el instanceof HTMLElement && document.contains(el)) el.focus()
    }
  }, [])

  const query = useQuery({
    queryKey: ['stockChart', ticker, period, 5],
    queryFn: () => getStockChart(ticker, period, 5),
    enabled: chartable,
    retry: 1,
    // 서버 캐시와 같은 값 — 완전 결과 10분 · 부분 결과 1분. 부분 안내 문구
    // 「1분 뒤 다시 열면 다시 받습니다」 가 참이려면 부분 결과는 1분 뒤 낡은 것이어야 한다.
    staleTime: (q) => (q.state.data?.complete === false ? 60_000 : 10 * 60_000),
    gcTime: 30 * 60_000,
  })

  // 차트 마운트 — 종목이 바뀔 때만 다시 만든다(기간 전환은 setPeriod 로 처리).
  useEffect(() => {
    if (!chartable) return
    const host = hostRef.current
    if (!host) return
    const chart = init(host, {
      locale: 'ko-KR',
      timezone: KST_TIME_ZONE,
      formatter: {
        formatDate: ({ timestamp, type }) =>
          type === 'xAxis' && periodRef.current === 'M'
            ? formatKstYearMonthFromEpochMs(timestamp)
            : formatKstDateFromEpochMs(timestamp),
      },
      styles: {
        candle: {
          bar: {
            upColor: PROFIT_HEX,
            upBorderColor: PROFIT_HEX,
            upWickColor: PROFIT_HEX,
            downColor: LOSS_HEX,
            downBorderColor: LOSS_HEX,
            downWickColor: LOSS_HEX,
            noChangeColor: NEUTRAL_HEX,
            noChangeBorderColor: NEUTRAL_HEX,
            noChangeWickColor: NEUTRAL_HEX,
          },
        },
        indicator: {
          bars: [{ upColor: PROFIT_HEX, downColor: LOSS_HEX, noChangeColor: NEUTRAL_HEX }],
        },
      },
    })
    chartRef.current = chart

    if (chart) {
      chart.setSymbol({ ticker, pricePrecision: 0, volumePrecision: 0 })
      // 이동평균은 가격 축에 겹쳐야 읽힌다 — 캔들 패널에 EMA(5·20·60·120).
      chart.createIndicator({ name: 'EMA', paneId: CANDLE_PANE_ID, calcParams: [5, 20, 60, 120] }, true)
      // 거래량은 막대만 — VOL 기본값은 거래량 이동평균선(MA5·10·20)을 같이 그려 EMA 처럼 보인다.
      chart.createIndicator({ name: 'VOL', paneId: VOL_PANE.id, calcParams: [] })
      // precision 을 주지 않으면 라이브러리가 소수 넷째 자리까지 찍는다.
      chart.createIndicator({
        name: 'RSI',
        paneId: RSI_PANE.id,
        calcParams: [14],
        precision: 2,
        figures: [{ key: 'rsi1', title: 'RSI14: ', type: 'line' }],
      })
      chart.createIndicator({ name: 'MACD', paneId: MACD_PANE.id, calcParams: [12, 26, 9], precision: 2 })
      for (const pane of [VOL_PANE, RSI_PANE, MACD_PANE]) chart.setPaneOptions(pane)
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

  // 데이터 교체 — 이 기간 데이터가 준비되면 반영, 아직이면 이전 기간 봉을 비운다.
  useEffect(() => {
    const chart = chartRef.current
    if (!chart) return
    if (query.data) {
      barsRef.current = toKLineData(query.data.bars)
      chart.setPeriod({ type: PERIOD_TO_KLINE[period], span: 1 })
    } else {
      barsRef.current = []
      chart.resetData()
    }
  }, [period, query.data])

  const data = query.data
  const effectiveName = (name && name.trim()) || data?.name || ''
  const titleText = effectiveName
    ? `${effectiveName} (${ticker}) — 종목 차트`
    : `${ticker || '—'} — 종목 차트`
  const lastBarDate = data && data.bars.length > 0 ? data.bars[data.bars.length - 1].date : undefined
  const isEmpty = !query.isLoading && !query.isError && !!data && data.bars.length === 0

  return (
    <div
      data-testid="stock-chart-modal"
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
          <h2
            id={TITLE_ID}
            data-testid="stock-chart-title"
            className="text-base font-semibold text-gray-900 truncate"
          >
            {titleText}
          </h2>
          <button
            type="button"
            data-testid="stock-chart-close"
            onClick={onClose}
            aria-label="닫기"
            className="text-gray-500 hover:text-gray-700 text-xl font-bold shrink-0 ml-2"
          >
            ×
          </button>
        </div>

        {!chartable ? (
          <div className="px-4 py-6 text-sm text-gray-500" data-testid="stock-chart-unsupported">
            6자리 숫자 종목코드만 차트를 볼 수 있습니다 (받은 값: {ticker || '(없음)'})
          </div>
        ) : (
          <div className="px-4 py-3 overflow-y-auto flex-1 flex flex-col gap-2">
            <div className="flex flex-wrap items-center gap-2">
              {PERIODS.map((p) => (
                <button
                  key={p}
                  type="button"
                  data-testid={`stock-chart-period-${p}`}
                  aria-pressed={period === p}
                  onClick={() => setPeriod(p)}
                  className={`px-3 py-1 text-sm rounded border font-medium ${
                    period === p
                      ? 'border-blue-500 bg-blue-50 text-blue-700'
                      : 'border-gray-300 text-gray-600 hover:bg-gray-50'
                  }`}
                >
                  {PERIOD_LABEL[p]}
                </button>
              ))}
              {data && (
                <span
                  data-testid="stock-chart-meta"
                  className="text-xs text-gray-500 flex flex-wrap gap-x-1"
                >
                  <span>
                    {data.start_date} ~ {data.end_date}
                  </span>
                  <span>· {data.bars.length.toLocaleString('ko-KR')}봉</span>
                  <span>· 수정주가</span>
                  <span>· KRX</span>
                </span>
              )}
            </div>

            {query.isLoading && (
              <div data-testid="stock-chart-loading" className="text-sm text-gray-500 py-2">
                차트 불러오는 중… (5년 일봉은 수 초 걸립니다)
              </div>
            )}

            {query.isError && (
              <div
                data-testid="stock-chart-error"
                className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 flex items-center justify-between gap-2"
              >
                <span className="break-words">{extractErrorMessage(query.error)}</span>
                <button
                  type="button"
                  data-testid="stock-chart-retry"
                  onClick={() => query.refetch()}
                  className="shrink-0 px-2 py-1 text-xs border border-red-300 rounded hover:bg-red-100"
                >
                  다시 시도
                </button>
              </div>
            )}

            {isEmpty && (
              <div data-testid="stock-chart-empty" className="text-sm text-gray-500 py-2">
                표시할 봉이 없습니다
              </div>
            )}

            {data && !data.complete && (
              <div
                data-testid="stock-chart-partial"
                className="rounded border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800"
              >
                일부 구간만 받았습니다({data.bars[0]?.date ?? '—'}부터) — {data.incomplete_reason ?? '사유 미상'}.
                1분 뒤 다시 열면 다시 받습니다
              </div>
            )}

            {data && data.last_bar_provisional && (
              <div data-testid="stock-chart-provisional" className="text-[11px] text-gray-400">
                {provisionalMessage(period, lastBarDate)}
              </div>
            )}

            <div
              ref={hostRef}
              data-testid="stock-chart-canvas-host"
              className="h-[72vh] min-h-[460px] w-full"
            />
          </div>
        )}
      </div>
    </div>
  )
}
