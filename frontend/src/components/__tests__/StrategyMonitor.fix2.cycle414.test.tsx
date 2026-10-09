/**
 * cycle414 보완 2차 Red — 재검증(suites·screens·trader 세 렌즈) N1~N10 중 MEDIUM 전부 + 적용한 LOW.
 *
 * | 결함(렌즈) | 이 파일의 단언 |
 * |---|---|
 * | N1(screens·trader) | 보유 사다리 — 값이 가까우면(겹침) 합쳐 그리고, 라벨·값은 `aria-label`/`title` 로도 읽힌다(잘림·겹침 0) |
 * | N2(trader) | 돈키언 추격 상한이 설정돼 있으면 「진입 가능」 대신 「참고」(당일 고가·오늘매도 미반영 — 엔진은 더 엄격할 수 있다) |
 * | N3(trader) | ETF 거리 막대 — 초록 구간이 0% 아래(가격<돌파선)에도 걸친다(엔진 조건은 시가 기준, 현재가 하한 없음) |
 * | N3(screens) | ETF·돈키언 구분 — 돈키언 거리 막대는 초록 구간이 0% 위부터만(현재가가 돌파선 아래가 아니어야 한다는 전제 유지) |
 * | N3(suites)·N3(screens)·N7(trader) | VB·모멘텀·LTV 라우트 funnel 폴백이 `scan_stats` 영문 키 대신 한글 라벨 |
 * | N4(suites)·N8(trader) | 폴백 단계 값 결측은 「모름」(0 둔갑 금지) |
 * | N6(screens) | 엔진 정지(running=false)면 ⑥ 매수 신호·돈키언 오늘 신규 진입 게이지도 「모름」(0 확정 금지) |
 * | N10(trader) | VCP·BFB 거래량 임계가 0(게이트 비활성)이면 관측 없이도 「거래량 미관측」 경보를 내지 않는다 |
 */
import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'

import StrategyMonitor from '../StrategyMonitor'
import type { StrategyInfo, TickerPrice } from '../../types/trading'
import {
  DC_CAND, DC_HELD, ETF_A, KST_0912, VCP_A,
  clone, makeExitLines, makeMonitor, makeStatus, makeStatusStrategies,
} from '../../test/fixtures/strategyMonitor.fixture'

type Dict = Record<string, any> // eslint-disable-line @typescript-eslint/no-explicit-any

interface Opts {
  now?: Date
  strategies?: (s: Dict) => void
  monitor?: ((m: Dict) => void) | null
  monitorRoot?: (root: Dict) => void
  prices?: (p: Record<string, TickerPrice>) => void
  running?: boolean | null
}

function renderPanel(sid: string, o: Opts = {}) {
  const strategies = clone(makeStatusStrategies()) as Dict
  o.strategies?.(strategies)
  const status = makeStatus(strategies) as Dict
  const prices = clone(status.scan.ticker_prices) as Record<string, TickerPrice>
  o.prices?.(prices)
  let monitor: Dict | null = clone(makeMonitor()) as Dict
  if (o.monitor === null) monitor = null
  else {
    o.monitor?.(monitor.strategies)
    o.monitorRoot?.(monitor)
  }
  return render(
    <StrategyMonitor
      strategyId={sid}
      strategies={strategies as unknown as Record<string, StrategyInfo>}
      monitor={monitor as never}
      exitLines={(makeExitLines() as Dict).items as never}
      tickerPrices={prices}
      tickerNames={status.scan.ticker_names}
      subscribedTickers={status.scan.subscribed_tickers}
      funnelTrend={null}
      now={o.now ?? KST_0912}
      running={o.running}
    />,
  )
}

const statusOf = (sid: string, t: string) => screen.getByTestId(`${sid}-monitor-status-${t}`).textContent ?? ''
const unpause = (sid: string) => (s: Dict) => { s[sid].params.buy_paused = false }

function labelled(el: Element): string {
  const parts: string[] = [el.textContent ?? '']
  for (const n of [el, ...Array.from(el.querySelectorAll('*'))]) {
    for (const a of ['aria-label', 'title']) {
      const v = n.getAttribute(a)
      if (v) parts.push(v)
    }
  }
  return parts.join(' ')
}

// ─────────────────────────────────────────────────────────────────────────────
describe('N1 — 보유 사다리: 값이 가까우면 합쳐 그린다(겹침·잘림 대신)', () => {
  it('돈키언 무장(무장값=매수가) → 매수·무장 두 점이 하나로 합쳐진다(원 1개)', () => {
    renderPanel('donchian_swing', {
      monitor: (m) => { Object.assign(m.donchian_swing.holdings[DC_HELD], { armed: true, arm_price: null }) },
    })
    const ladder = screen.getByTestId(`donchian_swing-monitor-ladder-${DC_HELD}`)
    const l = labelled(ladder)
    for (const k of ['손절', '매수', '무장']) expect(l, k).toContain(k)
    // 매수가(100,000) = 무장가 → 원 중복 없이 1개로 합쳐진다(점 4개가 아니라 3개).
    expect(ladder.querySelectorAll('circle').length).toBeLessThan(4)
  })

  it('사다리는 svg 폭이 넓어 끝 눈금 값이 잘리지 않는다(최소 폭 확보)', () => {
    renderPanel('donchian_swing')
    const ladder = screen.getByTestId(`donchian_swing-monitor-ladder-${DC_HELD}`)
    const svg = ladder.tagName.toLowerCase() === 'svg' ? ladder : ladder.querySelector('svg')
    expect(svg).not.toBeNull()
    expect(Number(svg!.getAttribute('width'))).toBeGreaterThanOrEqual(200)
  })
})

// ─────────────────────────────────────────────────────────────────────────────
describe('N2 — 돈키언 「진입 가능」은 당일 고가·오늘 매도를 못 보는 동안 「참고」로 낮춘다', () => {
  it('추격 상한(params.max_breakout_extension_pct) 설정 + 그 밖 조건 통과 → 「진입 가능」이 아니라 「참고」', () => {
    renderPanel('donchian_swing', { strategies: unpause('donchian_swing') })
    const s = statusOf('donchian_swing', DC_CAND)
    expect(s).not.toBe('진입 가능')
    expect(s).toMatch(/참고/)
  })
})

// ─────────────────────────────────────────────────────────────────────────────
describe('N3 — 거리 막대 초록 구간: ETF 는 현재가 하한이 없고, 돈키언은 있다', () => {
  it('ETF — 현재가가 돌파선 아래(pct<0)여도 초록 구간이 0% 밑까지 걸친다', () => {
    renderPanel('etf_trend', { prices: (p) => { p[ETF_A] = { ...p[ETF_A], current_price: 9_750 } } })
    const bar = screen.getByTestId(`etf_trend-monitor-distbar-${ETF_A}`)
    const green = bar.querySelector('rect[fill="#bbf7d0"]')
    expect(green).not.toBeNull()
    expect(Number(green!.getAttribute('x'))).toBeLessThanOrEqual(2)
  })

  it('돈키언 — 초록 구간은 0% 위부터만(현재가가 20일 신고가 위라는 전제 유지)', () => {
    renderPanel('donchian_swing', { strategies: unpause('donchian_swing') })
    const bar = screen.getByTestId(`donchian_swing-monitor-distbar-${DC_CAND}`)
    const green = bar.querySelector('rect[fill="#bbf7d0"]')
    expect(green).not.toBeNull()
    expect(Number(green!.getAttribute('x'))).toBeGreaterThan(2)
  })
})

// ─────────────────────────────────────────────────────────────────────────────
describe('N3(suites)·N7(trader) — VB·모멘텀·LTV 폴백 깔때기는 한글 라벨(영문 키 그대로 금지)', () => {
  it('VB 폴백 — scan_stats 영문 키(`k_value_computed`)가 그대로 노출되지 않는다', () => {
    renderPanel('volatility_breakout', {
      strategies: (s) => { s.volatility_breakout.scan_stats = { k_value_computed: 31, final_prepared: 31 } },
      monitor: (m) => { m.volatility_breakout.funnel = [] },
    })
    const f = screen.getByTestId('volatility_breakout-monitor-funnel').textContent ?? ''
    expect(f).not.toMatch(/k_value_computed/)
    expect(f).toMatch(/K값|target/i)
  })

  it('모멘텀 폴백 — `rate_pass` 영문 키가 그대로 노출되지 않는다', () => {
    renderPanel('momentum', {
      strategies: (s) => { s.momentum.scan_stats = { universe_candidates: 50, rate_pass: 10, final_prepared: 3 } },
    })
    const f = screen.getByTestId('momentum-monitor-funnel').textContent ?? ''
    expect(f).not.toMatch(/rate_pass/)
    expect(f).toMatch(/등락률/)
  })
})

// ─────────────────────────────────────────────────────────────────────────────
describe('N4(suites)·N8(trader) — 폴백 단계 값 결측은 「모름」(0 둔갑 금지)', () => {
  it('돈키언 폴백 — scan_stats 에 없는 단계 키는 숫자 0 이 아니라 「모름」', () => {
    renderPanel('donchian_swing', {
      strategies: (s) => { s.donchian_swing.scan_stats = { universe_union: 400 } },
      monitor: (m) => { m.donchian_swing.funnel = [] },
    })
    const rows = Array.from(screen.getByTestId('donchian_swing-monitor-funnel').querySelectorAll('[data-testid^="donchian_swing-monitor-funnel-row-"]'))
    const missing = rows.find((r) => /20일 신고가 돌파/.test(r.textContent ?? ''))
    expect(missing?.textContent).toMatch(/모름/)
    expect(missing?.textContent).not.toMatch(/—\s*0\b/)
  })
})

// ─────────────────────────────────────────────────────────────────────────────
describe('N6 — 엔진 정지(running=false)면 매수 신호·오늘 신규 진입도 「모름」(0 확정 금지)', () => {
  it('돈키언 — running=false 면 ⑥ 매수 신호 0, 오늘 신규 진입 0/3 을 확정으로 보여주지 않는다', () => {
    renderPanel('donchian_swing', { running: false })
    const entries = screen.getByTestId('donchian_swing-monitor-entries').textContent ?? ''
    expect(entries).not.toMatch(/매수 신호 0(?!.*모름)/)
    expect(entries).toMatch(/모름|엔진 정지/)
    const gauge = screen.queryByTestId('donchian_swing-monitor-daily-entries')
    if (gauge) expect(gauge.textContent).toMatch(/모름|엔진 정지/)
  })
})

// ─────────────────────────────────────────────────────────────────────────────
describe('N10 — 거래량 임계가 0(게이트 비활성)이면 관측 없이도 「거래량 미관측」 경보를 내지 않는다', () => {
  it('VCP — volume_threshold=0 + acml_vol 데이터 없음 → 거래량 미관측이 아니라 다음 조건으로 진행', () => {
    renderPanel('vcp_breakout', {
      strategies: (s) => { s.vcp_breakout.targets[VCP_A].volume_threshold = 0 },
      monitor: (m) => { m.vcp_breakout.ticks = {} },
    })
    const s = statusOf('vcp_breakout', VCP_A)
    expect(s).not.toMatch(/거래량 미관측/)
  })
})
