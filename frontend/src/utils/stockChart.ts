/**
 * 종목 차트(KLineChart) 순수 함수 — cycle387.
 *
 * 정본: `_workspace/red/cycle387_stock_chart_spec.md` §2.1 · §2.2 · §2.4.
 *
 * K4 가드(`utils/__tests__/kst.test.ts`) 의 위임 대상이다 — 이 파일은 `Intl.DateTimeFormat` 을
 * 직접 만들지 않고 `utils/kst.ts::kstDateToEpochMs` 를 통해서만 KST 날짜를 다룬다.
 */

import { kstDateToEpochMs } from './kst'
import type { ChartPeriod, StockChartBar } from '../types/stock-chart'

const TICKER_RE = /^\d{6}$/

/** KRX 6자리 **숫자** 종목코드만 차트 조회 대상이다(백엔드 422 규칙과 동일). */
export function isChartableTicker(v: unknown): boolean {
  return typeof v === 'string' && TICKER_RE.test(v)
}

const INTERACTIVE_SELECTOR = 'button, a, input, select, textarea, label'

/**
 * 더블클릭 대상에서 뺄 요소 — 버튼·링크·입력·라벨 및 그 자손.
 *
 * 행 더블클릭이 「매도」·「AI 자문」 두 번 누름을 차트 열기로 오인하지 않게 한다.
 */
export function isInteractiveTarget(t: EventTarget | null): boolean {
  if (!(t instanceof Element)) return false
  return t.closest(INTERACTIVE_SELECTOR) !== null
}

function toSafeNumber(v: unknown): number | null {
  if (typeof v === 'number') return Number.isFinite(v) ? v : null
  if (typeof v === 'string' && v.trim() !== '') {
    const n = Number(v)
    return Number.isFinite(n) ? n : null
  }
  return null
}

export interface KLineBar {
  timestamp: number
  open: number
  high: number
  low: number
  close: number
  volume: number
  turnover: number
  // klinecharts `KLineData` 의 인덱스 시그니처와 구조적으로 맞추기 위함(런타임 영향 없음).
  [key: string]: unknown
}

/**
 * 백엔드 봉 배열 → KLineChart `KLineData[]`.
 *
 * `timestamp` = KST 자정 epoch ms(`kstDateToEpochMs`), `turnover` = `amount`. 숫자는 방어
 * 변환(문자열 숫자도 받는다), 날짜·OHLC·거래량·거래대금 중 하나라도 변환 실패인 봉은 버리고,
 * 결과는 항상 오름차순(오래된 것 먼저)으로 정렬해 돌려준다.
 */
export function toKLineData(bars: StockChartBar[] | null | undefined): KLineBar[] {
  if (!Array.isArray(bars)) return []
  const out: KLineBar[] = []
  for (const b of bars) {
    if (!b || typeof b !== 'object') continue
    const timestamp = kstDateToEpochMs(typeof b.date === 'string' ? b.date : null)
    const open = toSafeNumber(b.open)
    const high = toSafeNumber(b.high)
    const low = toSafeNumber(b.low)
    const close = toSafeNumber(b.close)
    const volume = toSafeNumber(b.volume)
    const turnover = toSafeNumber(b.amount)
    if (
      timestamp === null ||
      open === null ||
      high === null ||
      low === null ||
      close === null ||
      volume === null ||
      turnover === null
    ) {
      continue
    }
    out.push({ timestamp, open, high, low, close, volume, turnover })
  }
  out.sort((a, b) => a.timestamp - b.timestamp)
  return out
}

/** klinecharts v10 `PeriodType` 매핑. */
export const PERIOD_TO_KLINE: Record<ChartPeriod, 'day' | 'week' | 'month'> = {
  D: 'day',
  W: 'week',
  M: 'month',
}

/** 화면 표시 라벨. */
export const PERIOD_LABEL: Record<ChartPeriod, string> = {
  D: '일봉',
  W: '주봉',
  M: '월봉',
}
