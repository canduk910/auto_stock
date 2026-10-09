/**
 * cycle414 보완 2차 Red — 재검증 N1(suites)·N4(screens)·N4(trader) 요약표 잔여.
 *
 * H3 는 상세 패널(`StrategyMonitor`)에서는 패널에 들어온 `running` prop 으로 해결됐지만, 요약표
 * (`StrategySummaryTable`)에는 그 prop 이 오지 않아 두 조합에서 여전히 「모름」이 「0」으로 보였다:
 *  1) 엔진 정지(running=false, 모니터 라우트는 성공) — 「왜 안 사나」는 「장 마감/엔진 정지」인데
 *     보유·청산 예정·오늘 신호는 그대로 숫자(흔히 0)로 확정되어 보였다.
 *  2) 모니터 라우트만 실패(monitor=null) + 엔진은 실제로 돈다(running=true) — `engineStopped` 이
 *     `monitor?.running===false` 만 보던 시절에는 반영도 안 됐고, exitDue/섀도 신호처럼 routeEntry
 *     가 있어야 계산되는 값이 조용히 0 으로 나왔다.
 */
import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'

import StrategySummaryTable from '../StrategySummaryTable'
import type { StrategyInfo, TickerPrice } from '../../types/trading'
import {
  KST_0912, clone, makeExitLines, makeMonitor, makeStatus, makeStatusStrategies,
} from '../../test/fixtures/strategyMonitor.fixture'

type Dict = Record<string, any> // eslint-disable-line @typescript-eslint/no-explicit-any

interface Opts {
  running?: boolean | null
  monitor?: Dict | null | undefined
  strategies?: (s: Dict) => void
}

function renderTable(o: Opts = {}) {
  const strategies = clone(makeStatusStrategies()) as Dict
  o.strategies?.(strategies)
  const status = makeStatus(strategies) as Dict
  const prices = clone(status.scan.ticker_prices) as Record<string, TickerPrice>
  const monitor = o.monitor === undefined ? (clone(makeMonitor()) as Dict) : o.monitor
  return render(
    <StrategySummaryTable
      strategies={strategies as unknown as Record<string, StrategyInfo>}
      monitor={monitor as never}
      exitLines={(makeExitLines() as Dict).items as never}
      tickerPrices={prices}
      now={KST_0912}
      running={o.running}
      onSelect={() => {}}
    />,
  )
}

const why = (sid: string) => screen.getByTestId(`strategy-summary-why-${sid}`).textContent ?? ''
const holdings = (sid: string) => screen.getByTestId(`strategy-summary-holdings-${sid}`).textContent ?? ''
const exitdue = (sid: string) => screen.getByTestId(`strategy-summary-exitdue-${sid}`).textContent ?? ''
const signals = (sid: string) => screen.getByTestId(`strategy-summary-signals-${sid}`).textContent ?? ''

describe('N4 — running=false(모니터 라우트는 성공) → 보유·청산 예정·신호도 「모름」', () => {
  it('돈키언 — 「왜 안 사나」 장 마감/엔진 정지 + 보유·청산예정·신호 모름', () => {
    renderTable({ running: false })
    expect(why('donchian_swing')).toMatch(/엔진 정지|장 마감/)
    expect(holdings('donchian_swing')).toMatch(/모름/)
    expect(exitdue('donchian_swing')).toMatch(/모름/)
    expect(signals('donchian_swing')).toMatch(/모름/)
  })
})

describe('N1(suites)·N4(trader) — 모니터 라우트만 실패(monitor=null) + running=true', () => {
  it('etf_trend — 「왜 안 사나」가 평소 판정으로 되돌아가지 않는다(엔진 정지 아님을 알아야 정상 흐름)', () => {
    renderTable({ running: true, monitor: null })
    // 엔진은 돌고 있다(running=true) → 「장 마감/엔진 정지」로 오판하지 않는다.
    expect(why('etf_trend')).not.toMatch(/엔진 정지|장 마감/)
  })

  it('donchian_swing — 청산 예정은 routeEntry 가 없어 0 이 아니라 「모름」', () => {
    renderTable({ running: true, monitor: null })
    expect(exitdue('donchian_swing')).toMatch(/모름/)
  })

  it('VB(섀도) — 「왜 안 사나」·신호 칸 둘 다 「섀도 기록 0」 단정이 아니라 「모름」', () => {
    renderTable({ running: true, monitor: null })
    expect(why('volatility_breakout')).not.toMatch(/섀도 기록 0\b/)
    expect(why('volatility_breakout')).toMatch(/모름/)
    expect(signals('volatility_breakout')).toMatch(/모름/)
  })

  it('모멘텀(실매매, 섀도 아님) — 신호 칸은 `info.buy_signals`(모니터 무관) 그대로 보인다', () => {
    renderTable({ running: true, monitor: null, strategies: (s) => { s.momentum.buy_signals = [{ ticker: '000001', name: '', price: 1, time: '09:10', change_rate: 0 }] } })
    expect(signals('momentum')).not.toMatch(/모름/)
    expect(signals('momentum')).toBe('1')
  })
})
