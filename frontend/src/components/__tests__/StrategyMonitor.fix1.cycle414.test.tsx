/**
 * cycle414 보완 1차 Red — 전략별 진행상황 상세 패널(`src/components/StrategyMonitor.tsx`).
 *
 * 판정 원문 = 1차 검수 verdict(H1~H3 · M1~M13 · L1~L15). 명세 = `_workspace/red/cycle414/monitor_spec.md`.
 * 화면 원칙(이번 보완의 기준):
 *  - 「모름」 을 「없음」·「차단」·「경보」 로 그리지 않는다 — 데이터 결손·라우트 실패·엔진 정지·정산 뒤·휴일은
 *    회색 「모름 / 장 마감 / 엔진 정지」 계열로.
 *  - 엔진 판정과 다른 판정을 화면이 만들지 않는다 — 엔진 코드와 같은 조건만 「진입 가능」, 아니면 「참고」.
 *  - 추정값은 「추정」 으로.
 *
 * | 결함 | 이 파일의 단언 |
 * |---|---|
 * | H1 | 돈키언 시간청산 `due` 를 모르면(라우트 실패·`days_held`/`time_exit_bars` null) 「모름」 — 「오늘 15:20 시간청산 대상」 0 |
 * | H2 | VCP·BFB 「진입 가능」 = 오늘 무장한 래치가 있을 때만(엔진 = `vcp_breakout.py` `if not (prev < base_high <= current_price): return NONE` · 래치 경로 `_latch_entry` → `_evaluate_vol_gate`, BFB `bull_flag_breakout.py` 같은 꼴). 래치 없이 돌파선 위 = 「참고: 돌파선 위」 |
 * | H3 | 라우트 `running=false`(21:30 `_reset_daily_state` 뒤 · 부팅 전 · 휴일) → 회색 「장 마감/엔진 정지」 · 「사지 않음」·「1주도 안 됨」·「예산 0원」·「보유 종목 없음」 0 |
 * | M1 | 터틀 4전략 enforce + 오늘 스냅샷 없음 → 엔진 `m=1.0`(`strategy_base.py` `_market_unit_view` `snap is None` → `m=1.0`) — 차단 아님 |
 * | M2 | ETF 「오늘 시도함/갭 스킵」 은 갭 사유(`gap_up`·`gap_over_line`)일 때만 — 엔진은 갭 때만 `_bought_today` 에 넣는다(`etf_trend.py` `if gap_reason is not None: self._bought_today.add`) |
 * | M3 | ETF 15:20 판정 — 돌파선이 없으면 「돌파선 모름」(엔진 `check_force_clear` 의 `missing_line` → 판정 안 함) |
 * | M5 | 라우트 실패 = 「모름」(「시세 없음」·「시세 낡음」·「거래량 미관측」 경보 0) · 판정 순서 = 자격(봉수)·시각 먼저, 시세 신선도 나중 |
 * | M6 | 손절 근접 = 색 클래스(빨강 `rose` · 주황 `amber` — KojiroMonitor 와 같은 팔레트) · 돈키언 보유표 「손절까지 %」 칸 |
 * | M7 | 최종 단계 = 전략별 최종 `step_no`(donchian·VCP·BFB·kojiro = 9 · etf = 99 · VB = 9 · LTV = 7) |
 * | M8 | BFB 후보표 「래치」 칸 |
 * | M9 | VB·모멘텀·LTV — 라우트 깔때기가 비어도 `scan_stats` 가 있으면 그것으로 · 준비 완료인데 「아직 스캔 전」 0 |
 * | M11 | 시각 요소 — §2.6 거리 막대 · §2.9 보유 사다리 · §4.3 거래량 게이지 · 14일 막대 제목·날짜·값 · ETF 구성 선이 보임 |
 * | M12 | 표 최소 폭(400px 에서 한 글자씩 세로로 눌리지 않게) |
 * | M13 | 돈키언 설계 수량 = 「n주(추정)」(「n랏」 금지) · ETF 「최대 n주(추정)」 |
 * | L1 | (정적 — `_ast_cycle414_fix1_static.test.ts` 가 ESLint rules-of-hooks 로 본다. React 는 0↔N 훅 변화를 런타임에 못 잡는다) |
 * | L6 | 후보 0 → 머리글만 있는 빈 표 대신 「후보 없음」 |
 * | L7 | 7칸 제목(heading) |
 *
 * 시각 요소 계약(Green 이 만들 것) — 차트는 recharts 또는 SVG(새 의존성 0). jsdom 은 `ResponsiveContainer` 폭이 0 이라
 * 실제 `<svg>` 가 나와야 하므로 고정 크기 recharts 또는 직접 SVG 로 그린다:
 *  - 거리 막대 `<sid>-monitor-distbar-<t>`(svg 포함) + 행에 「매수선 대비 %」 글자
 *  - 보유 사다리 `<sid>-monitor-ladder-<t>`(svg 포함) — 손절·매수·현재 + (donchian 무장 · BFB 목표) 라벨과 값
 *  - 거래량 게이지 `<sid>-monitor-volgauge-<t>` 안에 svg 또는 role=meter/progressbar
 *  - 14일 추이 `<sid>-monitor-trend` — 제목(「14일」)·날짜(MM-DD)·값이 글자로 보인다
 * 라벨·값 판정은 글자(textContent) + `aria-label`·`title` 속성을 합쳐 본다(SVG `<title>`·`<text>` 어느 쪽이든 된다).
 */
import { describe, expect, it } from 'vitest'
import { render, screen, within } from '@testing-library/react'

import StrategyMonitor from '../StrategyMonitor'
import type { StrategyInfo, TickerPrice } from '../../types/trading'
import {
  BFB_A, DC_CAND, DC_HELD, ETF_A, ETF_B, ETF_HELD, KST_0912, VB_A, VCP_A,
  clone, makeExitLines, makeMonitor, makeStatus, makeStatusStrategies,
} from '../../test/fixtures/strategyMonitor.fixture'

type Dict = Record<string, any> // eslint-disable-line @typescript-eslint/no-explicit-any

interface Opts {
  now?: Date
  strategies?: (s: Dict) => void
  monitor?: ((m: Dict) => void) | null
  monitorRoot?: (root: Dict) => void
  prices?: (p: Record<string, TickerPrice>) => void
  subscribed?: string[]
  exitLines?: ((items: Dict[]) => void) | null
  trend?: Array<{ date: string; count: number }> | null
}

function buildProps(sid: string, o: Opts = {}) {
  const strategies = clone(makeStatusStrategies()) as Dict
  o.strategies?.(strategies)
  const status = makeStatus(strategies) as Dict
  const prices = clone(status.scan.ticker_prices) as Record<string, TickerPrice>
  o.prices?.(prices)
  let monitor: Dict | null = clone(makeMonitor()) as Dict
  if (o.now) freshTicks(monitor, o.now)
  if (o.monitor === null) monitor = null
  else {
    o.monitor?.(monitor.strategies)
    o.monitorRoot?.(monitor)
  }
  let items: Dict[] | null = clone((makeExitLines() as Dict).items) as Dict[]
  if (o.exitLines === null) items = null
  else o.exitLines?.(items)
  return {
    strategyId: sid,
    strategies: strategies as unknown as Record<string, StrategyInfo>,
    monitor: monitor as never,
    exitLines: items as never,
    tickerPrices: prices,
    tickerNames: status.scan.ticker_names as Record<string, string>,
    subscribedTickers: (o.subscribed ?? status.scan.subscribed_tickers) as string[],
    funnelTrend: o.trend ?? null,
    now: o.now ?? KST_0912,
  }
}

function renderPanel(sid: string, o: Opts = {}) {
  return render(<StrategyMonitor {...buildProps(sid, o)} />)
}

function freshTicks(monitor: Dict, now: Date) {
  const iso = new Date(now.getTime() - 5_000).toISOString()
  for (const e of Object.values(monitor.strategies as Record<string, Dict>)) {
    for (const t of Object.values((e.ticks ?? {}) as Record<string, Dict>)) t.last_tick_at = iso
  }
}

const at = (hhmm: string) => new Date(`2026-10-12T${hhmm}:00+09:00`)
const statusOf = (sid: string, t: string) => screen.getByTestId(`${sid}-monitor-status-${t}`).textContent ?? ''
const unpause = (sid: string) => (s: Dict) => { s[sid].params.buy_paused = false }
const panelText = (sid: string) => screen.getByTestId(`${sid}-monitor`).textContent ?? ''

/** 글자 + aria-label + title 을 합친 「보이거나 읽히는」 문자열 — SVG `<text>`·`<title>` 어느 쪽으로 그려도 된다. */
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

/** 조상 어디든 `hidden`·`sr-only`·`invisible` 클래스 토큰 또는 display:none 이면 사람 눈에 안 보인다. */
function isVisuallyHidden(el: Element | null): boolean {
  for (let n: Element | null = el; n; n = n.parentElement) {
    const tokens = (n.getAttribute('class') ?? '').split(/\s+/)
    if (tokens.includes('hidden') || tokens.includes('sr-only') || tokens.includes('invisible')) return true
    if ((n as HTMLElement).style?.display === 'none') return true
    if (n.hasAttribute('hidden')) return true
  }
  return false
}

function hasSvg(el: Element): boolean {
  return el.tagName.toLowerCase() === 'svg' || el.querySelector('svg') !== null
}

/** 21:30 정산 `_reset_daily_state`(scheduler.py) 뒤의 메모리 — 보유·예산·주문중 0, 라우트 running=false. */
function afterSettlement(s: Dict) {
  for (const sid of Object.keys(s)) {
    Object.assign(s[sid], {
      positions: 0, pending_buys: 0, position_tickers: [], positions_detail: {}, pending_buy_tickers: [],
      total_investment: 0, invested_amount: 0, daily_realized_pnl: 0, buy_disabled: false, buy_signals: [],
    })
  }
}
function afterSettlementMonitor(m: Dict) {
  for (const sid of Object.keys(m)) {
    m[sid].holdings = {}
    m[sid].shadow_buys = []
    m[sid].paused_skips = []
  }
  m.etf_trend.candidates[ETF_A].design_qty = 0
  m.etf_trend.candidates[ETF_B].design_qty = 0
  m.donchian_swing.candidates[DC_CAND].design_lot = 0
}

// ─────────────────────────────────────────────────────────────────────────────
describe('H1 — 돈키언 시간청산 due 를 모르면 「모름」(거짓 15:20 경보 0)', () => {
  it('라우트 실패(monitor=null, 첫 로딩 포함) → 카운트다운 「모름」 · 「오늘 15:20 시간청산 대상」 없음', () => {
    renderPanel('donchian_swing', { monitor: null })
    const c = screen.getByTestId(`donchian_swing-monitor-countdown-${DC_HELD}`).textContent ?? ''
    expect(c).toMatch(/모름/)
    expect(c).not.toMatch(/오늘 15:20/)
    expect(panelText('donchian_swing')).not.toMatch(/오늘 15:20 시간청산 대상/)
  })

  it.each([
    ['days_held=null', { days_held: null }],
    ['time_exit_bars=null', { time_exit_bars: null }],
  ])('%s → 「모름」 · 거짓 「오늘 15:20」 0', (_n, patch) => {
    renderPanel('donchian_swing', { monitor: (m) => { Object.assign(m.donchian_swing.holdings[DC_HELD], patch) } })
    const c = screen.getByTestId(`donchian_swing-monitor-countdown-${DC_HELD}`).textContent ?? ''
    expect(c).toMatch(/모름/)
    expect(c).not.toMatch(/오늘 15:20/)
  })
})

// ─────────────────────────────────────────────────────────────────────────────
describe('H2 — VCP·BFB 「진입 가능」 은 엔진 조건(아래→위 교차 틱 또는 오늘 래치)일 때만', () => {
  // VCP_A: 현재가 10,200 ≥ 돌파선 10,000 · 거래량 150% · 확장 2% ≤ 7.5% · 10:00(진입창 09:05~14:30 안) · 멈춤 아님.
  it('VCP 래치 없음 + 돌파선 위 + 거래량 충족 → 「진입 가능」 이 아니라 「참고: 돌파선 위」', () => {
    renderPanel('vcp_breakout', { now: at('10:00') })
    const s = statusOf('vcp_breakout', VCP_A)
    expect(s).not.toMatch(/진입 가능/)
    expect(s).toMatch(/참고.*돌파선 위/)
  })

  it('VCP 오늘 무장한 래치 + 돌파선 위 + 거래량 충족 → 「진입 가능」', () => {
    renderPanel('vcp_breakout', {
      now: at('10:00'),
      monitor: (m) => { m.vcp_breakout.candidates[VCP_A].latch_armed_at = '2026-10-12T00:10:00Z' },
    })
    expect(statusOf('vcp_breakout', VCP_A)).toMatch(/진입 가능/)
  })

  it('BFB 래치 없음 + 깃발 고점 위 + 거래량 충족 → 「참고: 돌파선 위」', () => {
    renderPanel('bull_flag_breakout', {
      now: at('10:00'),
      prices: (p) => { p[BFB_A] = { ...p[BFB_A], current_price: 10_300 } }, // flag_high 10,200 · 확장 0.98%
    })
    const s = statusOf('bull_flag_breakout', BFB_A)
    expect(s).not.toMatch(/진입 가능/)
    expect(s).toMatch(/참고.*돌파선 위/)
  })

  it('BFB 오늘 무장한 래치 + 깃발 고점 위 + 거래량 충족 → 「진입 가능」', () => {
    renderPanel('bull_flag_breakout', {
      now: at('10:00'),
      prices: (p) => { p[BFB_A] = { ...p[BFB_A], current_price: 10_300 } },
      monitor: (m) => { m.bull_flag_breakout.candidates[BFB_A].latch_armed_at = '2026-10-12T00:20:00Z' },
    })
    expect(statusOf('bull_flag_breakout', BFB_A)).toMatch(/진입 가능/)
  })
})

// ─────────────────────────────────────────────────────────────────────────────
describe('H3 — 엔진 정지(running=false: 정산 뒤 · 부팅 전 · 휴일)는 회색 「장 마감/엔진 정지」', () => {
  const stopped = (sid: string, extra: (s: Dict) => void = () => {}) => renderPanel(sid, {
    now: at('21:40'),
    strategies: (s) => { afterSettlement(s); extra(s) },
    monitor: afterSettlementMonitor,
    monitorRoot: (root) => { root.running = false },
  })

  it('ETF(멈춤 해제) — 「장 마감/엔진 정지」 표시 · 「사지 않음」·「1주도 안 됨」·「예산 0원」·「보유 종목 없음」 단정 0', () => {
    stopped('etf_trend', unpause('etf_trend'))
    const t = panelText('etf_trend')
    expect(t).toMatch(/엔진 정지|장 마감/)
    expect(t).not.toMatch(/사지 않음/)
    expect(t).not.toMatch(/1주도 안 됨/)
    expect(t).not.toMatch(/예산 0원/)
    expect(t).not.toMatch(/보유 종목 없음/)
  })

  it('ETF 후보 상태 — 「1주도 안 됨」·「예산 0」·「진입 가능」 이 아니라 「장 마감/엔진 정지/모름」', () => {
    stopped('etf_trend', unpause('etf_trend'))
    const s = statusOf('etf_trend', ETF_A)
    expect(s).not.toMatch(/1주도 안 됨|예산 0|진입 가능/)
    expect(s).toMatch(/엔진 정지|장 마감|모름/)
  })

  it('돈키언 — 「사지 않음」(설계 랏 0)·「보유 종목 없음」 단정 0', () => {
    stopped('donchian_swing', unpause('donchian_swing'))
    const t = panelText('donchian_swing')
    expect(t).toMatch(/엔진 정지|장 마감/)
    expect(t).not.toMatch(/사지 않음/)
    expect(t).not.toMatch(/보유 종목 없음/)
  })

  it('「장 마감/엔진 정지」 표시는 회색 계열(빨강·주황 경보색 아님)', () => {
    stopped('etf_trend', unpause('etf_trend'))
    const root = screen.getByTestId('etf_trend-monitor')
    const nodes = within(root).getAllByText(/엔진 정지|장 마감/)
    expect(nodes.length).toBeGreaterThan(0)
    for (const n of nodes) {
      expect(n.getAttribute('class') ?? '', n.textContent ?? '').not.toMatch(/\bbg-(rose|red|amber|orange)-\d/)
      for (let a: Element | null = n; a && a !== root.parentElement; a = a.parentElement) {
        expect(a.getAttribute('class') ?? '', n.textContent ?? '').not.toMatch(/\btext-(rose|red|amber|orange)-\d/)
      }
    }
  })
})

// ─────────────────────────────────────────────────────────────────────────────
describe('M1 — 터틀 enforce + 오늘 스냅샷 없음 = 엔진 m=1(차단 아님)', () => {
  it('돈키언(멈춤 해제) enforce·스냅샷 결손 → 후보 상태가 「시장 유닛 …」 차단이 아니다', () => {
    renderPanel('donchian_swing', {
      strategies: (s) => { s.donchian_swing.params.buy_paused = false; s.donchian_swing.params.market_unit_mode = 'enforce' },
      monitor: (m) => { m.donchian_swing.market_unit = { mode: 'enforce', ok: false, reason: 'not_computed' } },
    })
    expect(statusOf('donchian_swing', DC_CAND)).not.toMatch(/시장 유닛/)
    const chip = screen.getByTestId('donchian_swing-monitor-chip-market_unit').textContent ?? ''
    expect(chip).toMatch(/차단 아님|m=1/)
    expect(chip).not.toMatch(/—\s*차단$/)
  })

  it('VCP enforce·스냅샷 결손 → 「시장 유닛」 차단 아님(래치 무장 + 조건 충족이면 진입 가능)', () => {
    renderPanel('vcp_breakout', {
      now: at('10:00'),
      strategies: (s) => { s.vcp_breakout.params.market_unit_mode = 'enforce' },
      monitor: (m) => {
        m.vcp_breakout.market_unit = { mode: 'enforce', ok: false, reason: 'not_computed' }
        m.vcp_breakout.candidates[VCP_A].latch_armed_at = '2026-10-12T00:10:00Z'
      },
    })
    const st = statusOf('vcp_breakout', VCP_A)
    expect(st).not.toMatch(/시장 유닛/)
    expect(st).toMatch(/진입 가능/)
  })
})

// ─────────────────────────────────────────────────────────────────────────────
describe('M2 — ETF 「오늘 시도함/갭 스킵」 은 갭 사유일 때만(엔진은 갭 때만 그날 평가를 닫는다)', () => {
  it.each([['collapse'], ['cluster_held'], ['no_budget'], ['rounds_to_zero'], ['open_unknown']])(
    '오늘 사유 %s 만 있음 → 「오늘 시도함」 아님(엔진은 다음 틱에 다시 평가)',
    (reason) => {
      renderPanel('etf_trend', {
        strategies: unpause('etf_trend'),
        monitor: (m) => {
          m.etf_trend.skips = { known: true, day: '2026-10-12', counts: { [reason]: 1 }, by_ticker: { [ETF_A]: [reason] } }
        },
      })
      expect(statusOf('etf_trend', ETF_A)).not.toMatch(/오늘 시도함|갭 스킵/)
    },
  )

  it('오늘 사유 gap_over_line → 「오늘 갭 스킵」', () => {
    renderPanel('etf_trend', {
      strategies: unpause('etf_trend'),
      monitor: (m) => {
        m.etf_trend.skips = { known: true, day: '2026-10-12', counts: { gap_over_line: 1 }, by_ticker: { [ETF_A]: ['gap_over_line'] } }
      },
    })
    expect(statusOf('etf_trend', ETF_A)).toMatch(/오늘 갭 스킵/)
  })
})

// ─────────────────────────────────────────────────────────────────────────────
describe('M3 — ETF 15:20 판정: 돌파선이 없으면 판정 대상이 아니다(엔진 missing_line)', () => {
  it('breakout_fail.active=true · line=null → 「15:20 판정 대상」·「15:20 정리」 아님, 「돌파선 모름」', () => {
    renderPanel('etf_trend', { monitor: (m) => { m.etf_trend.holdings[ETF_HELD].breakout_fail.line = null } })
    const c = screen.getByTestId(`etf_trend-monitor-countdown-${ETF_HELD}`).textContent ?? ''
    expect(c).not.toMatch(/15:20 판정 대상|15:20 정리/)
    expect(c).toMatch(/돌파선.*모름|모름/)
  })
})

// ─────────────────────────────────────────────────────────────────────────────
describe('M5 — 라우트 실패는 「모름」 · 자격·시각을 시세 신선도보다 먼저', () => {
  it('라우트 실패 → ETF 후보 「시세 없음」 0(멈춤·멈춤 해제 둘 다)', () => {
    const r1 = renderPanel('etf_trend', { monitor: null })
    for (const t of [ETF_A, ETF_B]) expect(statusOf('etf_trend', t), t).not.toMatch(/시세 없음/)
    r1.unmount()
    renderPanel('etf_trend', { monitor: null, strategies: unpause('etf_trend') })
    for (const t of [ETF_A, ETF_B]) expect(statusOf('etf_trend', t), t).not.toMatch(/시세 없음/)
  })

  it('라우트 실패 → ETF 보유 15:20 칸 「모름」(「시세 낡음 — 15:20 판정 건너뜀 위험」 경보 0)', () => {
    renderPanel('etf_trend', { monitor: null })
    const c = screen.getByTestId(`etf_trend-monitor-countdown-${ETF_HELD}`).textContent ?? ''
    expect(c).toMatch(/모름/)
    expect(c).not.toMatch(/시세 낡음|건너뜀/)
  })

  it('라우트 실패 → 돈키언·VCP 후보 「시세 없음」 0 · VCP 「거래량 미관측(엔진은 사지 않음)」 단정 0', () => {
    const r1 = renderPanel('donchian_swing', { monitor: null, strategies: unpause('donchian_swing') })
    expect(statusOf('donchian_swing', DC_CAND)).not.toMatch(/시세 없음/)
    r1.unmount()
    renderPanel('vcp_breakout', { monitor: null, now: at('10:00') })
    expect(statusOf('vcp_breakout', VCP_A)).not.toMatch(/시세 없음|거래량 미관측/)
    const g = screen.getByTestId(`vcp_breakout-monitor-volgauge-${VCP_A}`).textContent ?? ''
    expect(g).not.toMatch(/미관측/)
    expect(g).toMatch(/모름/)
  })

  it('진입창 전(08:30)·틱 없음 → 「09:05 부터」(시각이 먼저 — 「시세 없음」 아님)', () => {
    renderPanel('etf_trend', {
      now: at('08:30'),
      strategies: unpause('etf_trend'),
      monitor: (m) => { for (const t of Object.values(m.etf_trend.ticks as Record<string, Dict>)) t.last_tick_at = '2026-10-11T15:30:00+09:00' },
    })
    const s = statusOf('etf_trend', ETF_A)
    expect(s).not.toMatch(/시세 없음/)
    expect(s).toMatch(/09:05 부터/)
  })

  it('진입창 지남(10:00)·틱 낡음 → 「진입창 지남」(「시세 없음」 아님)', () => {
    renderPanel('etf_trend', {
      now: at('10:00'),
      strategies: unpause('etf_trend'),
      monitor: (m) => { for (const t of Object.values(m.etf_trend.ticks as Record<string, Dict>)) t.last_tick_at = '2026-10-12T09:40:00+09:00' },
    })
    const s = statusOf('etf_trend', ETF_A)
    expect(s).not.toMatch(/시세 없음/)
    expect(s).toMatch(/진입창 지남|다음 거래일/)
  })

  it('보유 봉수 미달(자격 없음) + 15:15·틱 4분 낡음 → 「n봉째부터」(「시세 낡음」 경보 아님)', () => {
    renderPanel('etf_trend', {
      now: at('15:15'),
      monitor: (m) => {
        Object.assign(m.etf_trend.holdings[ETF_HELD], { bars_since_buy: 1 })
        m.etf_trend.holdings[ETF_HELD].breakout_fail.active = false
        m.etf_trend.ticks[ETF_HELD].last_tick_at = '2026-10-12T15:11:00+09:00'
      },
    })
    const c = screen.getByTestId(`etf_trend-monitor-countdown-${ETF_HELD}`).textContent ?? ''
    expect(c).toMatch(/2봉째부터/)
    expect(c).not.toMatch(/시세 낡음|건너뜀/)
  })

  it('판정 대상이라도 09:12 의 4분 낡은 틱은 15:20 경보가 아니다(시각 먼저)', () => {
    renderPanel('etf_trend', {
      monitor: (m) => { m.etf_trend.ticks[ETF_HELD].last_tick_at = '2026-10-12T09:08:00+09:00' },
    })
    const c = screen.getByTestId(`etf_trend-monitor-countdown-${ETF_HELD}`).textContent ?? ''
    expect(c).not.toMatch(/시세 낡음|건너뜀/)
    expect(c).toMatch(/15:20 판정 대상/)
  })
})

// ─────────────────────────────────────────────────────────────────────────────
describe('M6 — 손절 근접은 색 클래스로(데이터 속성만으로는 안 보인다) · 돈키언 「손절까지 %」 칸', () => {
  const RED = /\btext-(rose|red)-[5-9]00\b/
  const ORANGE = /\btext-(amber|orange)-[5-9]00\b/

  it.each([
    [10_700, 'normal'],
    [10_500, 'orange'],
    [10_300, 'red'],
  ])('ETF 현재가 %s → %s 색', (cur, tone) => {
    renderPanel('etf_trend', { prices: (p) => { p[ETF_HELD] = { ...p[ETF_HELD], current_price: cur } } })
    const el = screen.getByTestId(`etf_trend-monitor-stopdist-${ETF_HELD}`)
    if (tone === 'red') expect(el.className).toMatch(RED)
    else if (tone === 'orange') expect(el.className).toMatch(ORANGE)
    else {
      expect(el.className).not.toMatch(RED)
      expect(el.className).not.toMatch(ORANGE)
    }
  })

  it('돈키언 보유표에 「손절까지 %」 칸 — (103,000−92,000)/103,000 = 10.7%', () => {
    renderPanel('donchian_swing')
    const el = screen.getByTestId(`donchian_swing-monitor-stopdist-${DC_HELD}`)
    expect(el.textContent).toMatch(/10\.7%/)
    expect(el.getAttribute('data-tone')).toBe('normal')
  })

  it('돈키언 손절 근접(현재가 92,500 → 0.5%) → 빨강 색 클래스', () => {
    renderPanel('donchian_swing', { prices: (p) => { p[DC_HELD] = { ...p[DC_HELD], current_price: 92_500 } } })
    const el = screen.getByTestId(`donchian_swing-monitor-stopdist-${DC_HELD}`)
    expect(el.getAttribute('data-tone')).toBe('red')
    expect(el.className).toMatch(RED)
  })
})

// ─────────────────────────────────────────────────────────────────────────────
describe('M7 — 최종 단계 = 전략별 최종 step_no(엔진 FUNNEL_STAGES)', () => {
  const dcFunnel = (zeroFrom: number) => (m: Dict) => {
    m.donchian_swing.funnel = [
      [1, '코스피200+코스닥150 합집합', 400], [2, '시총+거래대금 컷 통과', 380], [3, '1단계 진입 차단 13건 통과', 300],
      [4, '일봉 fetch + 전일종가>0', 290], [5, '신고가 돌파', 12], [6, 'EMA 우상향 + 종가>EMA', 6],
      [7, '거래대금 평균 대비 통과', 3], [8, 'ATR(14) > 0', 3], [9, '최종 후보', 3],
    ].map(([step_no, step_name, n]) => ({
      step_no, step_name, step_conditions: null, survived_count: (step_no as number) >= zeroFrom ? 0 : n, excluded_count: 0,
    }))
  }

  it('돈키언 최종(9) 0 → 「최종 후보 0 — 5단계(신고가 돌파)에서 전부 걸렸습니다」', () => {
    renderPanel('donchian_swing', { monitor: dcFunnel(5) })
    const f = screen.getByTestId('donchian_swing-monitor-funnel').textContent ?? ''
    expect(f).toMatch(/최종 후보 0/)
    expect(f).toMatch(/5단계.*신고가 돌파/)
  })
})

// ─────────────────────────────────────────────────────────────────────────────
describe('M8 — BFB 후보표 래치 칸', () => {
  it('BFB latch_armed_at(오늘) → 래치 칸에 KST hh:mm', () => {
    renderPanel('bull_flag_breakout', {
      monitor: (m) => { m.bull_flag_breakout.candidates[BFB_A].latch_armed_at = '2026-10-12T00:10:00Z' },
    })
    expect(screen.getByTestId(`bull_flag_breakout-monitor-latch-${BFB_A}`).textContent).toMatch(/09:10/)
  })
})

// ─────────────────────────────────────────────────────────────────────────────
describe('M9 — 가벼운 패널 깔때기: 스캔 결과가 있으면 「아직 스캔 전」 0', () => {
  it('VB — 라우트 깔때기 비어도 scan_stats(최종 31)로 그린다', () => {
    renderPanel('volatility_breakout', { monitor: (m) => { m.volatility_breakout.funnel = [] } })
    const f = screen.getByTestId('volatility_breakout-monitor-funnel').textContent ?? ''
    expect(f).not.toMatch(/아직 스캔 전/)
    expect(f).toMatch(/31/)
  })

  it('모멘텀 — scan_stats(scanner 필터 통계, 최종 3)로 그린다', () => {
    renderPanel('momentum', {
      strategies: (s) => {
        s.momentum.scan_stats = { universe_candidates: 50, rate_pass: 10, mcap_pass: 6, trade_amount_pass: 4,
          limit_up_excluded: 1, final_prepared: 3, last_run_at: '2026-10-12T09:30:05+09:00' }
      },
    })
    const f = screen.getByTestId('momentum-monitor-funnel').textContent ?? ''
    expect(f).not.toMatch(/아직 스캔 전/)
    expect(f).toMatch(/50/)
  })

  it('LTV — scan_stats(최종 5)로 그린다', () => {
    renderPanel('long_tail_volatility', {
      strategies: (s) => {
        s.long_tail_volatility.scan_stats = { universe_candidates: 40, universe_filtered: 30, price_filtered: 0, mcap_pass: 0,
          trade_amount_pass: 0, candle_fetch_ok: 28, consecutive_limit_pass: 20, k_value_computed: 6, final_prepared: 5,
          last_run_at: '2026-10-12T07:48:00+09:00' }
      },
    })
    const f = screen.getByTestId('long_tail_volatility-monitor-funnel').textContent ?? ''
    expect(f).not.toMatch(/아직 스캔 전/)
    expect(f).toMatch(/40/)
  })

  it('준비 완료(prepare.ok=true)인데 단계 기록이 없으면 「아직 스캔 전」 이라고 하지 않는다(머리말과 모순 금지)', () => {
    renderPanel('volatility_breakout', {
      strategies: (s) => { s.volatility_breakout.scan_stats = null },
      monitor: (m) => { m.volatility_breakout.funnel = [] },
    })
    expect(screen.getByTestId('volatility_breakout-monitor-asof').textContent).toMatch(/완료/)
    expect(screen.getByTestId('volatility_breakout-monitor-funnel').textContent).not.toMatch(/아직 스캔 전/)
  })
})

// ─────────────────────────────────────────────────────────────────────────────
describe('M11 — 시각 요소(사용자 요청 핵심): 거리 막대 · 보유 사다리 · 거래량 게이지 · 14일 막대 · ETF 구성 선', () => {
  it.each([
    ['etf_trend', ETF_A, /\+4\.0%/],            // (10,350−9,950)/9,950
    ['donchian_swing', DC_CAND, /\+2\.0%/],      // (50,500−49,500)/49,500
    ['vcp_breakout', VCP_A, /\+2\.0%/],          // (10,200−10,000)/10,000
    ['bull_flag_breakout', BFB_A, /[-−]1\.0%/],  // (10,100−10,200)/10,200
  ])('§2.6 %s 후보 %s — 거리 막대(svg) + 매수선 대비 %% 글자', (sid, t, pct) => {
    renderPanel(sid)
    const bar = screen.getByTestId(`${sid}-monitor-distbar-${t}`)
    expect(hasSvg(bar), `${sid} 거리 막대는 svg`).toBe(true)
    const row = screen.getByTestId(`${sid}-monitor-candidate-${t}`)
    expect(row.textContent).toMatch(pct)
  })

  it('§2.9 ETF 보유 사다리 — 손절·매수·현재 라벨과 값(10,240 · 10,000 · 10,700)', () => {
    renderPanel('etf_trend')
    const ladder = screen.getByTestId(`etf_trend-monitor-ladder-${ETF_HELD}`)
    expect(hasSvg(ladder)).toBe(true)
    const l = labelled(ladder)
    for (const k of ['손절', '매수', '현재']) expect(l, k).toContain(k)
    for (const v of ['10,240', '10,000', '10,700']) expect(l, v).toContain(v)
  })

  it('§2.9 돈키언 보유 사다리 — 손절(92,000)·매수(100,000)·현재(103,000)·무장(124,000)', () => {
    renderPanel('donchian_swing')
    const ladder = screen.getByTestId(`donchian_swing-monitor-ladder-${DC_HELD}`)
    expect(hasSvg(ladder)).toBe(true)
    const l = labelled(ladder)
    for (const k of ['손절', '매수', '현재', '무장']) expect(l, k).toContain(k)
    for (const v of ['92,000', '100,000', '103,000', '124,000']) expect(l, v).toContain(v)
  })

  it('§2.9 BFB 보유 사다리 — 측정목표(exit-lines target_price 11,600) 라벨', () => {
    renderPanel('bull_flag_breakout', {
      strategies: (s) => {
        s.bull_flag_breakout.positions = 1
        s.bull_flag_breakout.position_tickers = [BFB_A]
        s.bull_flag_breakout.positions_detail = {
          [BFB_A]: { name: 'CJ씨푸드', buy_price: 10_250, quantity: 10, high_since_buy: 10_400, buy_date: '2026-10-08', is_next_day: false },
        }
      },
      exitLines: (items) => {
        items.push({ strategy_id: 'bull_flag_breakout', ticker: BFB_A, stop_price: 9_400, stop_source: 'effective',
          target_price: 11_600, target_source: 'measured', buy_price: 10_250, quantity: 10, high_since_buy: 10_400,
          buy_date: '2026-10-08', order_no: 'O-B', entry_atr: 300, kk_armed: null, kk_arm_price: null })
      },
    })
    const ladder = screen.getByTestId(`bull_flag_breakout-monitor-ladder-${BFB_A}`)
    expect(hasSvg(ladder)).toBe(true)
    const l = labelled(ladder)
    for (const k of ['손절', '매수', '현재', '목표']) expect(l, k).toContain(k)
    for (const v of ['9,400', '10,250', '11,600']) expect(l, v).toContain(v)
  })

  it('§4.3 VCP 거래량 게이지 — svg 또는 meter/progressbar + 150% 글자', () => {
    renderPanel('vcp_breakout')
    const g = screen.getByTestId(`vcp_breakout-monitor-volgauge-${VCP_A}`)
    const meter = g.querySelector('[role="meter"],[role="progressbar"]') ?? (/^(meter|progressbar)$/.test(g.getAttribute('role') ?? '') ? g : null)
    expect(hasSvg(g) || meter !== null, '거래량 게이지는 그림(svg) 또는 meter').toBe(true)
    expect(g.textContent).toMatch(/150%/)
  })

  it('14일 막대 — 제목(14일)·날짜(MM-DD)·값이 글자로 보인다', () => {
    renderPanel('etf_trend', {
      trend: [{ date: '2026-09-29', count: 7 }, { date: '2026-10-08', count: 5 }, { date: '2026-10-12', count: 0 }],
    })
    const trend = screen.getByTestId('etf_trend-monitor-trend')
    const t = trend.textContent ?? ''
    expect(t).toMatch(/14일/)
    expect(t).toMatch(/09-29/)
    expect(t).toMatch(/10-12/)
    expect(t).toMatch(/7/)
    expect(t).toMatch(/5/)
  })

  it('ETF 구성 선(하드·본전·트레일·채널)이 숨김 칸이 아니라 보인다 · 라벨 동반', () => {
    renderPanel('etf_trend')
    const row = screen.getByTestId(`etf_trend-monitor-holding-${ETF_HELD}`)
    for (const k of ['hard', 'breakeven', 'trail', 'channel']) {
      const el = within(row.closest('[data-testid="etf_trend-monitor-holdings"]') as HTMLElement)
        .getByTestId(`etf_trend-monitor-line-${ETF_HELD}-${k}`)
      expect(isVisuallyHidden(el), `${k} 선이 hidden 안에 있다`).toBe(false)
    }
    const holdings = labelled(screen.getByTestId('etf_trend-monitor-holdings'))
    for (const k of ['하드', '본전', '트레일', '채널']) expect(holdings, k).toContain(k)
  })
})

// ─────────────────────────────────────────────────────────────────────────────
describe('M12 — 400px 에서 표가 한 글자씩 세로로 눌리지 않게 최소 폭', () => {
  const hasMinWidth = (table: HTMLElement) => /\bmin-w-/.test(table.className) || table.style.minWidth !== ''

  it.each([['etf_trend'], ['donchian_swing'], ['vcp_breakout'], ['bull_flag_breakout']])('%s 후보표·보유표에 최소 폭', (sid) => {
    renderPanel(sid, {
      strategies: (s) => {
        if (sid === 'vcp_breakout' || sid === 'bull_flag_breakout') {
          s[sid].positions = 1
          s[sid].position_tickers = ['900100']
          s[sid].positions_detail = { '900100': { name: 'X', buy_price: 1000, quantity: 1, high_since_buy: 1000, buy_date: '2026-10-08', is_next_day: false } }
        }
      },
    })
    for (const part of ['candidates', 'holdings']) {
      const table = within(screen.getByTestId(`${sid}-monitor-${part}`)).getByRole('table')
      expect(hasMinWidth(table), `${sid} ${part}`).toBe(true)
    }
  })
})

// ─────────────────────────────────────────────────────────────────────────────
describe('M13 — 추정값은 「추정」 · 돈키언 설계 수량 단위는 주', () => {
  it('돈키언 설계 수량 2 → 「2주(추정)」(「2랏」 아님)', () => {
    renderPanel('donchian_swing')
    const row = screen.getByTestId(`donchian_swing-monitor-candidate-${DC_CAND}`).textContent ?? ''
    expect(row).not.toMatch(/\d+\s*랏/)
    expect(row).toMatch(/2주/)
    expect(row).toMatch(/추정/)
  })

  it('ETF 예상 수량 → 「최대 250주」 + 추정 표기', () => {
    renderPanel('etf_trend')
    const q = screen.getByTestId(`etf_trend-monitor-qty-${ETF_A}`).textContent ?? ''
    expect(q).toMatch(/최대 250주/)
    expect(q).toMatch(/추정/)
  })
})

// ─────────────────────────────────────────────────────────────────────────────
describe('L6 — 후보 0 이면 빈 표 대신 「후보 없음」', () => {
  it.each([['etf_trend'], ['donchian_swing'], ['vcp_breakout'], ['bull_flag_breakout']])('%s targets={} → 「후보 없음」 · 표 없음', (sid) => {
    renderPanel(sid, {
      strategies: (s) => { s[sid].targets = {} },
      monitor: (m) => { m[sid].candidates = {} },
    })
    const c = screen.getByTestId(`${sid}-monitor-candidates`)
    expect(c.textContent).toMatch(/후보 없음/)
    expect(within(c).queryByRole('table')).toBeNull()
  })
})

// ─────────────────────────────────────────────────────────────────────────────
describe('L7 — 칸 제목(heading)', () => {
  it('전체 패널(ETF) 7칸 제목', () => {
    renderPanel('etf_trend')
    const want: Array<[string, RegExp]> = [
      ['status', /상태/], ['timeline', /오늘의 시간표/], ['funnel', /후보 깔때기/], ['candidates', /후보 종목/],
      ['skips', /오늘 거르기 사유/], ['entries', /진입 기록/], ['holdings', /보유 방어선/],
    ]
    for (const [part, name] of want) {
      expect(within(screen.getByTestId(`etf_trend-monitor-${part}`)).getByRole('heading', { name }), part).toBeTruthy()
    }
  })

  it('가벼운 패널(VB) 4칸 제목', () => {
    renderPanel('volatility_breakout')
    const want: Array<[string, RegExp]> = [
      ['status', /상태/], ['timeline', /오늘의 시간표/], ['funnel', /후보 깔때기/], ['entries', /진입 기록/],
    ]
    for (const [part, name] of want) {
      expect(within(screen.getByTestId(`volatility_breakout-monitor-${part}`)).getByRole('heading', { name }), part).toBeTruthy()
    }
    expect(VB_A).toBe('010170')
  })
})
