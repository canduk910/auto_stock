/**
 * 거래일지 차트 응답 타입 — cycle457.
 *
 * 백엔드 `src/routes/journal_chart.py` `GET /api/journal-chart` 의 `data`. 일봉 칸은 종목 차트
 * (`StockChartData`)와 같고, 전략 지표(`indicators`)는 그 전략 객체의 `chart_indicators` 가 낸 값이다 —
 * 화면은 계산하지 않고 그리기만 한다.
 */

import type { StockChartData } from './stock-chart'

/** 선이 그려질 칸 — 캔들 위 · 아래 ATR 칸 · 아래 MACD 칸. */
export type IndicatorPane = 'price' | 'atr' | 'macd'

/** 선 색 이름 — 화면이 `index.css` 토큰으로 바꾼다. */
export type IndicatorTone = 'navy' | 'sky' | 'brown' | 'beige' | 'gray' | 'red' | 'blue'

export interface IndicatorLine {
  key: string
  title: string
  pane: IndicatorPane
  tone: IndicatorTone | string
  dashed: boolean
}

export interface JournalChartIndicators {
  lines: IndicatorLine[]
  /** 선 key → 봉마다 값(`bars` 와 같은 길이·순서). 그 봉에서 계산할 수 없으면 null. */
  series: Record<string, (number | null)[]>
  notes: string[]
}

export interface JournalChartData extends StockChartData {
  strategy: string
  indicators: JournalChartIndicators
  /** `engine` = 엔진 전략 객체로 계산 · `unavailable` = 엔진에 전략 없음 · `error` = 계산 실패. */
  indicator_source: 'engine' | 'unavailable' | 'error'
  /** 이 봉 번호 앞은 계산하지 않았다(null). */
  indicator_start_index: number
}
