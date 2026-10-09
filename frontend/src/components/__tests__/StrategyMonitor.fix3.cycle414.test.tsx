/**
 * cycle414 보완 3차 Red — 2차 재검증 verdict(verdict2.md) 신규 MEDIUM N-A·N-b + LOW N-B.
 *
 * | 결함 | 이 파일의 단언 |
 * |---|---|
 * | N-A | 보유 사다리(Ladder) — 30px 안에서 합친 그룹도 라벨마다 값을 따로 보여준다(첫 점 값만 대표 금지).
 *        렌더된 글자(`<title>` 제외)는 점(circle, 중심 H/2) 범위 밖에 둔다 |
 * | N-b | 돈키언 「참고」 문구는 「돌파선 위」를 주장하지 않는다(엔진 `donchian_swing.check_buy_signal` 은
 *        갭·추격상한·시장유닛·랏만 보고 현재가≥돌파선을 보지 않는다). 거리 막대도 `belowLineOk`(초록
 *        구간이 0% 아래에도 걸친다) |
 * | N-B | 14일 최종 후보 추이 — 날짜·값 줄이 막대와 같은 폭 분배(`flex-1`)로 줄 서서, 어느 막대의
 *        값인지 인덱스로 맞출 수 있다(`flex-wrap`로 좌측에 몰리지 않는다) |
 */
import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'

import StrategyMonitor from '../StrategyMonitor'
import type { StrategyInfo, TickerPrice } from '../../types/trading'
import {
  DC_CAND, DC_HELD, KST_0912,
  clone, makeExitLines, makeMonitor, makeStatus, makeStatusStrategies,
} from '../../test/fixtures/strategyMonitor.fixture'

type Dict = Record<string, any> // eslint-disable-line @typescript-eslint/no-explicit-any

interface Opts {
  now?: Date
  strategies?: (s: Dict) => void
  monitor?: ((m: Dict) => void) | null
  prices?: (p: Record<string, TickerPrice>) => void
  trend?: Array<{ date: string; count: number }> | null
}

function renderPanel(sid: string, o: Opts = {}) {
  const strategies = clone(makeStatusStrategies()) as Dict
  o.strategies?.(strategies)
  const status = makeStatus(strategies) as Dict
  const prices = clone(status.scan.ticker_prices) as Record<string, TickerPrice>
  o.prices?.(prices)
  let monitor: Dict | null = clone(makeMonitor()) as Dict
  if (o.monitor === null) monitor = null
  else o.monitor?.(monitor.strategies)
  return render(
    <StrategyMonitor
      strategyId={sid}
      strategies={strategies as unknown as Record<string, StrategyInfo>}
      monitor={monitor as never}
      exitLines={(makeExitLines() as Dict).items as never}
      tickerPrices={prices}
      tickerNames={status.scan.ticker_names}
      subscribedTickers={status.scan.subscribed_tickers}
      funnelTrend={o.trend ?? null}
      now={o.now ?? KST_0912}
    />,
  )
}

const statusOf = (sid: string, t: string) => screen.getByTestId(`${sid}-monitor-status-${t}`).textContent ?? ''
const unpause = (sid: string) => (s: Dict) => { s[sid].params.buy_paused = false }

function svgOf(el: Element): SVGSVGElement {
  return (el.tagName.toLowerCase() === 'svg' ? el : el.querySelector('svg')) as SVGSVGElement
}

// ─────────────────────────────────────────────────────────────────────────────
describe('N-A — 사다리: 합친 그룹도 라벨별 값 + 글자는 점 범위 밖', () => {
  it('매수(100,000)·현재(101,500)가 30px 안으로 합쳐져도 둘 다 화면 글자(제목 제외)로 보인다', () => {
    renderPanel('donchian_swing', {
      // 무장 ≠ 매수 로 두어(armed:false) 매수·현재만 가깐게 합치는 조합을 만든다.
      monitor: (m) => { Object.assign(m.donchian_swing.holdings[DC_HELD], { armed: false, arm_price: 124_000 }) },
      prices: (p) => { p[DC_HELD] = { ...p[DC_HELD], current_price: 101_500 } },
    })
    const ladder = screen.getByTestId(`donchian_swing-monitor-ladder-${DC_HELD}`)
    const svg = svgOf(ladder)
    // <title> 은 제외하고 렌더된 <text> 만 본다 — 제목은 이미 라벨별 값을 올바로 담고 있어 이 결함을 가린다.
    const texts = Array.from(svg.querySelectorAll('text'))
    const rendered = texts.map((t) => t.textContent ?? '').join(' ')
    expect(rendered).toMatch(/100,000/)
    expect(rendered).toMatch(/101,500/)
  })

  it('렌더된 글자(title 제외)의 y 는 점(circle) 중심에서 충분히 떨어져 있다(겹침 금지)', () => {
    renderPanel('donchian_swing', {
      monitor: (m) => { Object.assign(m.donchian_swing.holdings[DC_HELD], { armed: false, arm_price: 124_000 }) },
      prices: (p) => { p[DC_HELD] = { ...p[DC_HELD], current_price: 101_500 } },
    })
    const ladder = screen.getByTestId(`donchian_swing-monitor-ladder-${DC_HELD}`)
    const svg = svgOf(ladder)
    const h = Number(svg.getAttribute('height'))
    const cy = h / 2
    const texts = Array.from(svg.querySelectorAll('text'))
    expect(texts.length).toBeGreaterThan(0)
    for (const t of texts) {
      const y = Number(t.getAttribute('y'))
      expect(Math.abs(y - cy), `y=${y} cy=${cy}`).toBeGreaterThanOrEqual(5)
    }
  })
})

// ─────────────────────────────────────────────────────────────────────────────
describe('N-b — 돈키언 「참고」 문구·거리 막대는 엔진 조건과 같은 것만 주장한다', () => {
  it('추격 상한 설정 상태 — 「참고: 돌파선 위」가 아니다(엔진은 현재가≥돌파선을 보지 않는다)', () => {
    renderPanel('donchian_swing', { strategies: unpause('donchian_swing') })
    const s = statusOf('donchian_swing', DC_CAND)
    expect(s).toMatch(/참고/)
    expect(s).not.toMatch(/돌파선 위/)
  })

  it('거리 막대 — 초록 구간이 0% 아래에도 걸친다(belowLineOk, ETF 와 같은 처리)', () => {
    renderPanel('donchian_swing', { strategies: unpause('donchian_swing') })
    const bar = screen.getByTestId(`donchian_swing-monitor-distbar-${DC_CAND}`)
    const green = bar.querySelector('rect[fill="#bbf7d0"]')
    expect(green).not.toBeNull()
    expect(Number(green!.getAttribute('x'))).toBeLessThanOrEqual(2)
  })
})

// ─────────────────────────────────────────────────────────────────────────────
describe('N-B — 14일 추이: 날짜·값 줄이 막대와 같은 폭 분배로 정렬된다', () => {
  it('날짜·값 칩 수 = 막대 수, 각 칩이 막대처럼 flex-1(flex-wrap 없이)', () => {
    renderPanel('donchian_swing', {
      trend: [
        { date: '2026-09-29', count: 3 }, { date: '2026-09-30', count: 0 }, { date: '2026-10-01', count: 5 },
      ],
    })
    const trendBox = screen.getByTestId('donchian_swing-monitor-trend')
    const barRow = trendBox.querySelector('.flex.items-end') as HTMLElement
    expect(barRow).not.toBeNull()
    const bars = Array.from(barRow.children)
    expect(bars.length).toBe(3)

    // 날짜·값 줄 — 막대 바로 아래, bar row 와 형제인 두 번째 flex 컨테이너.
    const labelRow = Array.from(trendBox.children).find(
      (el) => el !== barRow && el.querySelector('span'),
    ) as HTMLElement
    expect(labelRow).not.toBeNull()
    expect(labelRow.className).not.toMatch(/flex-wrap/)
    const chips = Array.from(labelRow.children)
    expect(chips.length).toBe(3)
    for (const c of chips) expect((c as HTMLElement).className).toMatch(/flex-1/)
    // N3-2(보완 4차) — 「날짜:값」한 줄은 칸이 좁아지면 통째로 잘려 값이 안 보여, 날짜·값을
    // 두 줄(span 2개)로 나눴다. 순서는 막대와 같은 날짜 순서여야 인덱스로 맞출 수 있다.
    expect(chips.map((c) => Array.from(c.querySelectorAll('span')).map((s) => s.textContent))).toEqual([
      ['09-29', '3'], ['09-30', '0'], ['10-01', '5'],
    ])
  })
})
