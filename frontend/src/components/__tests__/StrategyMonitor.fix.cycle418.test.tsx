/**
 * cycle418-M Red — monitor_verdict1~4.md 「남은 LOW 목록」 중 StrategyMonitor.tsx 분량.
 *
 * | 결함 | 단언 |
 * |---|---|
 * | L8 | 「풀리면: ○○」 힌트가 ETF 전용이다 — donchian·VCP·BFB 후보표에도 멈춤 중이면 힌트를 보인다 |
 * | L9 | BFB 「유지 대기」 보조 라벨이 그 종목이 실제 retention 대기 중(`target.breakout_seen_at`)일 때만 |
 * | L10 | VB·모멘텀·LTV 는 "설정을 확인하라"고 하지 않는다(확인할 설정이 없다 — 보드 시간표를 따른다) |
 * | L12 | 섀도 기록·LTV 손절선 안내가 종목코드만이 아니라 이름도 보인다 |
 * | L13 | 보유 방어선에 `stop_source`(근사·모드별 등)가 드러난다 |
 * | L15 | 돈키언 — `+1R` 넘었어도 `daysHeld ≥ maxHoldBars−1` 이면 「시간청산 면제」가 아니라 대상 |
 * | N-c | ETF 거리 막대 — 상한(`gap_over_line_pct`)은 시가 기준 1회성 판정이라 현재가 축에 캡을 긋지 않는다 |
 * | N-d | BFB 거래량 임계 0 + 미관측 → 「게이트 비활성」이 아니라 「거래량 미관측」(엔진은 여전히 막는다) |
 * | N-D | BFB 「유지 대기」는 래치·현재가 확인 뒤에만 뜬다(이미 래치됐으면 유지 대기가 아니다) |
 * | N-E | momentum 「상한가 제외」 단계 — 제외 수를 통과 수처럼 늘어놓지 않는다(늘었다 줄었다 금지) |
 * | 모름 ≠ 0 | 엔진 정지 + 후보 없음 → 후보표 「모름」 · 멈춤인데 라우트 실패 → 「건너뛴 종목 모름」 |
 * | 추정 | donchian 설계 랏 0 → 「사지 않음(추정)」(positive 케이스와 동일하게 "(추정)" 명시) |
 * | 어투 | ETF 15:20 판정 — 돌파 실패가 확정 어투가 아니라 예상 어투 |
 */
import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'

import StrategyMonitor from '../StrategyMonitor'
import type { ExitLineItem, StrategyInfo, TickerPrice } from '../../types/trading'
import {
  BFB_A, DC_CAND, DC_HELD, ETF_A, ETF_HELD, KST_0912, VCP_A,
  clone, makeExitLines, makeMonitor, makeStatus, makeStatusStrategies,
} from '../../test/fixtures/strategyMonitor.fixture'

type Dict = Record<string, any> // eslint-disable-line @typescript-eslint/no-explicit-any

interface Opts {
  now?: Date
  strategies?: (s: Dict) => void
  monitor?: ((m: Dict) => void) | null
  monitorRoot?: (root: Dict) => void
  prices?: (p: Record<string, TickerPrice>) => void
  exitLines?: (items: ExitLineItem[]) => ExitLineItem[]
  running?: boolean | null
  phase?: string | null
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
  else {
    o.monitor?.(monitor.strategies)
    o.monitorRoot?.(monitor)
  }
  let exitLines = clone(makeExitLines()).items as unknown as ExitLineItem[]
  if (o.exitLines) exitLines = o.exitLines(exitLines)
  return render(
    <StrategyMonitor
      strategyId={sid}
      strategies={strategies as unknown as Record<string, StrategyInfo>}
      monitor={monitor as never}
      exitLines={exitLines as never}
      tickerPrices={prices}
      tickerNames={status.scan.ticker_names}
      subscribedTickers={status.scan.subscribed_tickers}
      funnelTrend={o.trend ?? null}
      now={o.now ?? KST_0912}
      running={o.running}
    />,
  )
}

const statusOf = (sid: string, t: string) => screen.getByTestId(`${sid}-monitor-status-${t}`).textContent ?? ''
const unpause = (sid: string) => (s: Dict) => { s[sid].params.buy_paused = false }

// ─────────────────────────────────────────────────────────────────────────────
describe('L8 — 「풀리면」 힌트는 donchian·VCP·BFB 멈춤 중에도 보인다', () => {
  it('donchian — 멈춤 중이면 풀리면 힌트가 보인다', () => {
    renderPanel('donchian_swing')
    expect(statusOf('donchian_swing', DC_CAND)).toBe('멈춤')
    expect(screen.getByTestId(`donchian_swing-monitor-unpaused-${DC_CAND}`)).toBeTruthy()
  })

  it('BFB — 멈춤 중이 아니면(unpause) 힌트가 없다', () => {
    renderPanel('bull_flag_breakout', { strategies: unpause('bull_flag_breakout') })
    expect(screen.queryByTestId(`bull_flag_breakout-monitor-unpaused-${BFB_A}`)).toBeNull()
  })
})

// ─────────────────────────────────────────────────────────────────────────────
describe('L9 — BFB 「유지 대기」는 그 종목이 실제로 대기 중일 때만', () => {
  it('breakout_seen_at 없음(대기 아님) → 유지 대기 라벨 없음(retention_minutes>0 이어도)', () => {
    renderPanel('bull_flag_breakout', {
      strategies: (s) => {
        s.bull_flag_breakout.params.breakout_retention_minutes = 3
        s.bull_flag_breakout.params.buy_paused = false
        s.bull_flag_breakout.targets[BFB_A].breakout_seen_at = null
      },
    })
    expect(screen.queryByTestId(`bull_flag_breakout-monitor-retention-${BFB_A}`)).toBeNull()
  })

  it('breakout_seen_at 있음(대기 중) → 유지 대기 라벨 보임', () => {
    renderPanel('bull_flag_breakout', {
      strategies: (s) => {
        s.bull_flag_breakout.params.breakout_retention_minutes = 3
        s.bull_flag_breakout.params.buy_paused = false
        s.bull_flag_breakout.targets[BFB_A].breakout_seen_at = '2026-10-12T09:08:00+09:00'
      },
    })
    expect(screen.getByTestId(`bull_flag_breakout-monitor-retention-${BFB_A}`)).toBeTruthy()
  })
})

// ─────────────────────────────────────────────────────────────────────────────
describe('L10 — 시간표 정보 없음 안내: 확인할 설정이 없는 전략은 다르게 말한다', () => {
  it('VB(진입창 개념 자체가 없는 전략) — "설정을 확인하세요" 라고 하지 않는다', () => {
    renderPanel('volatility_breakout')
    const timeline = screen.getByTestId('volatility_breakout-monitor-timeline').textContent ?? ''
    expect(timeline).not.toMatch(/설정을 확인/)
  })
})

// ─────────────────────────────────────────────────────────────────────────────
describe('L12 — 섀도 기록·LTV 손절선 안내는 종목명도 함께 보인다', () => {
  it('섀도 기록 — 코드만이 아니라 종목명이 보인다', () => {
    renderPanel('volatility_breakout', {
      monitor: (m) => { m.volatility_breakout.shadow_buys = ['010170'] },
    })
    const entries = screen.getByTestId('volatility_breakout-monitor-entries').textContent ?? ''
    expect(entries).toMatch(/대한광통신/)
  })
})

// ─────────────────────────────────────────────────────────────────────────────
describe('L13 — 보유 방어선에 stop_source 가 드러난다', () => {
  it('stop_source="hard_pct"(근사) → 근사 표시', () => {
    renderPanel('donchian_swing', {
      exitLines: (items) => items.map((it) => (it.ticker === DC_HELD ? { ...it, stop_source: 'hard_pct' } : it)),
    })
    const holding = screen.getByTestId(`donchian_swing-monitor-holding-${DC_HELD}`)
    expect(holding.textContent).toMatch(/근사/)
  })

  it('stop_source="effective"(엔진 값) → 근사 표시 없음', () => {
    renderPanel('donchian_swing')
    const holding = screen.getByTestId(`donchian_swing-monitor-holding-${DC_HELD}`)
    expect(holding.textContent).not.toMatch(/근사/)
  })
})

// ─────────────────────────────────────────────────────────────────────────────
describe('L15 — 돈키언 max_hold_bars 도달은 +1R 면제보다 우선한다', () => {
  it('reached_1r=true ∧ days_held ≥ max_hold_bars−1 → 시간청산 면제가 아니라 대상', () => {
    renderPanel('donchian_swing', {
      monitor: (m) => {
        Object.assign(m.donchian_swing.holdings[DC_HELD], {
          reached_1r: true, days_held: 249, max_hold_bars: 250, time_exit_bars: 20,
        })
      },
    })
    const countdown = screen.getByTestId(`donchian_swing-monitor-countdown-${DC_HELD}`).textContent ?? ''
    expect(countdown).not.toMatch(/면제/)
    expect(countdown).toMatch(/최대 보유|시간청산 대상/)
  })

  it('reached_1r=true ∧ max_hold 미도달 → 그대로 면제', () => {
    renderPanel('donchian_swing', {
      monitor: (m) => {
        Object.assign(m.donchian_swing.holdings[DC_HELD], {
          reached_1r: true, days_held: 10, max_hold_bars: 250, time_exit_bars: 20,
        })
      },
    })
    const countdown = screen.getByTestId(`donchian_swing-monitor-countdown-${DC_HELD}`).textContent ?? ''
    expect(countdown).toMatch(/면제/)
  })
})

// ─────────────────────────────────────────────────────────────────────────────
describe('N-c — ETF 거리 막대는 상한 캡을 현재가 축에 긋지 않는다(시가 1회성 판정)', () => {
  it('상한(주황) 구간이 ETF 거리 막대에 그려지지 않는다', () => {
    renderPanel('etf_trend', { prices: (p) => { p[ETF_A] = { ...p[ETF_A], current_price: 11_000 } } })
    const bar = screen.getByTestId(`etf_trend-monitor-distbar-${ETF_A}`)
    expect(bar.querySelector('rect[fill="#fed7aa"]')).toBeNull()
  })
})

// ─────────────────────────────────────────────────────────────────────────────
describe('N-d — BFB 거래량 임계 0(설정 없음) + 미관측 → 「거래량 미관측」(「게이트 비활성」 아님)', () => {
  it('BFB: volume_threshold=0 ∧ acml_vol 없음 → 거래량 미관측(엔진은 no_data 로 막는다)', () => {
    renderPanel('bull_flag_breakout', {
      strategies: (s) => {
        s.bull_flag_breakout.targets[BFB_A].volume_threshold = 0
        s.bull_flag_breakout.params.buy_paused = false
      },
      monitor: (m) => { m.bull_flag_breakout.ticks = {} },
    })
    const row = screen.getByTestId(`bull_flag_breakout-monitor-candidate-${BFB_A}`)
    expect(row.textContent).toMatch(/거래량 미관측/)
  })

  it('VCP: volume_threshold=0(진짜 비활성) ∧ 관측 없음 → 그대로 게이트 비활성', () => {
    renderPanel('vcp_breakout', {
      strategies: (s) => { s.vcp_breakout.targets[VCP_A].volume_threshold = 0 },
      monitor: (m) => { m.vcp_breakout.ticks = {} },
    })
    const row = screen.getByTestId(`vcp_breakout-monitor-candidate-${VCP_A}`)
    expect(row.textContent).toMatch(/게이트 비활성/)
  })
})

// ─────────────────────────────────────────────────────────────────────────────
describe('N-D — BFB 「유지 대기」는 래치·현재가 확인 뒤에만 판정한다', () => {
  it('이미 래치된 종목은 유지 대기가 아니라 다른 상태(돌파선 아래 등)로 읽힌다', () => {
    renderPanel('bull_flag_breakout', {
      strategies: (s) => {
        s.bull_flag_breakout.params.breakout_retention_minutes = 3
        s.bull_flag_breakout.params.buy_paused = false
        s.bull_flag_breakout.targets[BFB_A].breakout_seen_at = '2026-10-12T09:08:00+09:00'
      },
      monitor: (m) => {
        m.bull_flag_breakout.candidates[BFB_A] = { latch_armed_at: '2026-10-12T09:09:00+09:00' }
      },
    })
    const s = statusOf('bull_flag_breakout', BFB_A)
    expect(s).not.toBe('유지 대기')
  })
})

// ─────────────────────────────────────────────────────────────────────────────
describe('N-E — momentum 「상한가 제외」는 제외 수를 통과 수처럼 늘어놓지 않는다', () => {
  it('직전 단계 50 · 제외 3 → 통과 47(제외 3건과 함께)', () => {
    renderPanel('momentum', {
      strategies: (s) => {
        s.momentum.scan_stats = {
          universe_candidates: 100, rate_pass: 80, mcap_pass: 60, trade_amount_pass: 50,
          limit_up_excluded: 3, final_prepared: 47,
        }
      },
      monitor: (m) => { m.momentum.funnel = [] },
    })
    const funnel = screen.getByTestId('momentum-monitor-funnel').textContent ?? ''
    expect(funnel).toMatch(/47/)
    expect(funnel).toMatch(/제외 3건/)
  })
})

// ─────────────────────────────────────────────────────────────────────────────
describe('모름 ≠ 0 — 엔진 정지 중 후보표·멈춤 중 라우트 실패', () => {
  it('엔진 정지 + 후보 없음 → 후보표 「모름」(「후보 없음」이 아니다)', () => {
    renderPanel('donchian_swing', {
      running: false,
      strategies: (s) => { s.donchian_swing.targets = {} },
    })
    const cands = screen.getByTestId('donchian_swing-monitor-candidates').textContent ?? ''
    expect(cands).toMatch(/모름/)
    expect(cands).not.toMatch(/^.*후보 없음.*$/)
  })

  it('멈춤 중 + 라우트 실패(monitor=null) → 건너뛴 종목 수가 「0」 이 아니라 「모름」', () => {
    renderPanel('donchian_swing', { monitor: null })
    const skips = screen.getByTestId('donchian_swing-monitor-skips').textContent ?? ''
    expect(skips).toMatch(/모름/)
  })
})

// ─────────────────────────────────────────────────────────────────────────────
describe('추정 — donchian 설계 랏 0 은 "사지 않음(추정)"', () => {
  it('design_lot<=0 → "사지 않음(추정)"', () => {
    renderPanel('donchian_swing', {
      strategies: unpause('donchian_swing'),
      monitor: (m) => { m.donchian_swing.candidates[DC_CAND].design_lot = 0 },
    })
    const row = screen.getByTestId(`donchian_swing-monitor-candidate-${DC_CAND}`)
    expect(row.textContent).toMatch(/사지 않음\(추정\)/)
  })
})

// ─────────────────────────────────────────────────────────────────────────────
describe('어투 — ETF 15:20 돌파 실패 판정은 예상 어투', () => {
  it('"15:20 정리(돌파 실패)" 대신 "정리 예상" 류 어투', () => {
    renderPanel('etf_trend', {
      prices: (p) => { p[ETF_HELD] = { ...p[ETF_HELD], current_price: 9_500 } },
      monitor: (m) => {
        Object.assign(m.etf_trend.holdings[ETF_HELD].breakout_fail, { line: 9_900, active: true })
      },
    })
    const countdown = screen.getByTestId(`etf_trend-monitor-countdown-${ETF_HELD}`).textContent ?? ''
    expect(countdown).toMatch(/정리 예상/)
  })
})

// ─────────────────────────────────────────────────────────────────────────────
describe('N4-1 — 14일 추이 칸이 많으면 날짜를 일(DD)만 쓴다', () => {
  it('14칸 추이 — 날짜 칸이 "MM-DD" 가 아니라 "DD" 만', () => {
    const days = [
      '09-29', '09-30', '10-01', '10-02', '10-03', '10-04', '10-05',
      '10-06', '10-07', '10-08', '10-09', '10-10', '10-11', '10-12',
    ]
    const trend = days.map((d) => ({ date: `2026-${d}`, count: 1 }))
    renderPanel('donchian_swing', { trend })
    const trendBlock = screen.getByTestId('donchian_swing-monitor-trend')
    expect(trendBlock.textContent).not.toMatch(/10-12/)
    expect(trendBlock.textContent).toMatch(/12/)
  })
})

// ─────────────────────────────────────────────────────────────────────────────
describe('N-f — phase="booting" 중 보유 복원 전 「보유 종목 없음」을 확정으로 쓰지 않는다', () => {
  it('running=true ∧ phase="booting" ∧ 보유 0 → 「모름」(「보유 종목 없음」 아님)', () => {
    const strategies = clone(makeStatusStrategies()) as Dict
    strategies.donchian_swing.positions_detail = {}
    strategies.donchian_swing.position_tickers = []
    const status = makeStatus(strategies) as Dict
    const monitor = clone(makeMonitor()) as Dict
    render(
      <StrategyMonitor
        strategyId="donchian_swing"
        strategies={strategies as unknown as Record<string, StrategyInfo>}
        monitor={monitor as never}
        exitLines={(clone(makeExitLines()) as Dict).items as never}
        tickerPrices={status.scan.ticker_prices}
        tickerNames={status.scan.ticker_names}
        subscribedTickers={status.scan.subscribed_tickers}
        funnelTrend={null}
        now={KST_0912}
        running={true}
        phase="booting"
      />,
    )
    const holdings = screen.getByTestId('donchian_swing-monitor-holdings').textContent ?? ''
    expect(holdings).toMatch(/모름/)
    expect(holdings).not.toMatch(/^.*보유 종목 없음.*$/)
  })

  it('phase="main_trading"(평소) + 보유 0 → 그대로 「보유 종목 없음」(회귀 없음)', () => {
    const strategies = clone(makeStatusStrategies()) as Dict
    strategies.donchian_swing.positions_detail = {}
    strategies.donchian_swing.position_tickers = []
    const status = makeStatus(strategies) as Dict
    const monitor = clone(makeMonitor()) as Dict
    render(
      <StrategyMonitor
        strategyId="donchian_swing"
        strategies={strategies as unknown as Record<string, StrategyInfo>}
        monitor={monitor as never}
        exitLines={(clone(makeExitLines()) as Dict).items as never}
        tickerPrices={status.scan.ticker_prices}
        tickerNames={status.scan.ticker_names}
        subscribedTickers={status.scan.subscribed_tickers}
        funnelTrend={null}
        now={KST_0912}
        running={true}
        phase="main_trading"
      />,
    )
    expect(screen.getByTestId('donchian_swing-monitor-holdings').textContent).toMatch(/보유 종목 없음/)
  })
})
