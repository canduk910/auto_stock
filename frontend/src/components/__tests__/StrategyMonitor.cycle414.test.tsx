/**
 * cycle414 Red — 전략별 진행상황 상세 패널(`src/components/StrategyMonitor.tsx`).
 *
 * 명세 = `_workspace/red/cycle414/monitor_spec.md` §2(공통 7칸) · §4(전략별) · §8.1 F2~F7·F9.
 *
 * 계약(Green 이 만들 것):
 *
 * ```tsx
 * <StrategyMonitor
 *   strategyId="etf_trend"
 *   strategies={status.strategies}            // /api/trading/status
 *   monitor={monitorData | null}               // /api/strategies/monitor 의 data(실패 = null → 폴백)
 *   exitLines={exitLines.items | null}         // /api/balance/exit-lines 의 items
 *   tickerPrices={scan.ticker_prices} tickerNames={scan.ticker_names}
 *   subscribedTickers={scan.subscribed_tickers}
 *   funnelTrend={[{date, count}] | null}       // /api/strategy-funnel/recent 최종 단계(14일)
 *   now={Date}                                 // 시각 seam — 테스트는 KST 시각을 고정해 넘긴다
 * />
 * ```
 *
 * 테스트 id = `<sid>-monitor-*`(명세 §2.10) — 칸: `-status`(①, 주 배지 `-badge` · 칩 `-chip-<kind>`) ·
 * `-timeline`(②) · `-funnel`(③, 행 `-funnel-row-<step_no>`) · `-asof`(기준일 머리말) · `-candidates`(④, 행
 * `-candidate-<t>` · 상태 `-status-<t>` · 멈춤 중 추정 `-unpaused-<t>`) · `-skips`(⑤) · `-entries`(⑥) ·
 * `-holdings`(⑦, 행 `-holding-<t>` · 실효선 `-stop-<t>` · 거리 `-stopdist-<t>`(`data-tone`) · 카운트다운
 * `-countdown-<t>` · 구성 선 `-line-<t>-<hard|breakeven|trail|channel>`(`data-active`)).
 * 고지로는 기존 `KojiroMonitor`(`kojiro-*` id 보존)로 그린다.
 */
import { describe, expect, it } from 'vitest'
import { render, screen, within } from '@testing-library/react'

import StrategyMonitor from '../StrategyMonitor'
import type { StrategyInfo, TickerPrice } from '../../types/trading'
import {
  BFB_A, DC_CAND, DC_HELD, ETF_A, ETF_B, ETF_HELD, KST_0912, VB_A, VCP_A,
  clone, makeExitLines, makeMonitor, makeMonitorEntries, makeStatus, makeStatusStrategies,
} from '../../test/fixtures/strategyMonitor.fixture'

type Dict = Record<string, any> // eslint-disable-line @typescript-eslint/no-explicit-any

interface Opts {
  now?: Date
  strategies?: (s: Dict) => void
  monitor?: ((m: Dict) => void) | null
  prices?: (p: Record<string, TickerPrice>) => void
  subscribed?: string[]
  exitLines?: ((items: Dict[]) => void) | null
  trend?: Array<{ date: string; count: number }> | null
}

function renderPanel(sid: string, o: Opts = {}) {
  const strategies = clone(makeStatusStrategies()) as Dict
  o.strategies?.(strategies)
  const status = makeStatus(strategies) as Dict
  const prices = clone(status.scan.ticker_prices) as Record<string, TickerPrice>
  o.prices?.(prices)
  let monitor: Dict | null = clone(makeMonitor()) as Dict
  if (o.now) freshTicks(monitor, o.now) // 시각을 옮기면 틱도 함께 옮긴다(아니면 전부 「시세 없음」)
  if (o.monitor === null) monitor = null
  else o.monitor?.(monitor.strategies)
  let items: Dict[] | null = clone((makeExitLines() as Dict).items) as Dict[]
  if (o.exitLines === null) items = null
  else o.exitLines?.(items)
  return render(
    <StrategyMonitor
      strategyId={sid}
      strategies={strategies as unknown as Record<string, StrategyInfo>}
      monitor={monitor as never}
      exitLines={items as never}
      tickerPrices={prices}
      tickerNames={status.scan.ticker_names}
      subscribedTickers={o.subscribed ?? status.scan.subscribed_tickers}
      funnelTrend={o.trend ?? null}
      now={o.now ?? KST_0912}
    />,
  )
}

/** 모든 후보·보유 틱을 `now` 5초 전으로 — 진입창 시각 테스트가 「시세 없음」 에 먹히지 않게. */
function freshTicks(monitor: Dict, now: Date) {
  const iso = new Date(now.getTime() - 5_000).toISOString()
  for (const e of Object.values(monitor.strategies as Record<string, Dict>)) {
    for (const t of Object.values((e.ticks ?? {}) as Record<string, Dict>)) t.last_tick_at = iso
  }
}

const at = (hhmm: string) => new Date(`2026-10-12T${hhmm}:00+09:00`)
const statusOf = (sid: string, t: string) => screen.getByTestId(`${sid}-monitor-status-${t}`).textContent ?? ''
const unpause = (sid: string) => (s: Dict) => { s[sid].params.buy_paused = false }

// ─────────────────────────────────────────────────────────────────────────────
describe('공통 틀 — 상태 배지 · 기준일 · 빈 데이터', () => {
  it('ETF(멈춤) → ① 주 배지 「신규 매수 멈춤」 + 시장 유닛 칩(관찰만)', () => {
    renderPanel('etf_trend')
    const root = screen.getByTestId('etf_trend-monitor')
    const st = within(root).getByTestId('etf_trend-monitor-status')
    expect(within(st).getByTestId('etf_trend-monitor-badge').textContent).toMatch(/신규 매수 멈춤/)
    expect(within(st).getByTestId('etf_trend-monitor-chip-market_unit').textContent).toMatch(/0\.75.*관찰만|관찰만.*0\.75/)
    expect(st.textContent).toMatch(/12%/) // 비중 = Math.round(weight*100)%
  })

  it('LTV 꺼짐 + 보유 2 → 빨강 「손절 정지」 칩 (F2)', () => {
    renderPanel('long_tail_volatility', {
      strategies: (s) => {
        s.long_tail_volatility.positions = 2
        s.long_tail_volatility.positions_detail = {
          '457370': { name: 'A', buy_price: 1000, quantity: 1, high_since_buy: 1000, buy_date: '2026-10-06', is_next_day: true },
          '457380': { name: 'B', buy_price: 1000, quantity: 1, high_since_buy: 1000, buy_date: '2026-10-06', is_next_day: true },
        }
      },
    })
    expect(screen.getByTestId('long_tail_volatility-monitor-badge').textContent).toBe('꺼짐')
    const c = screen.getByTestId('long_tail_volatility-monitor-chip-off_with_holdings')
    expect(c.textContent).toMatch(/보유 2.*손절 정지/)
  })

  it('VB 섀도 → 주 배지 「섀도」 + 비중 0 이 정상이라는 표기', () => {
    renderPanel('volatility_breakout')
    expect(screen.getByTestId('volatility_breakout-monitor-badge').textContent).toMatch(/섀도/)
    expect(screen.getByTestId('volatility_breakout-monitor-status').textContent).toMatch(/비중 0.*정상|정상.*비중 0/)
  })

  it('모멘텀은 데이터로만 판정한다 — 켜짐·비중 0.03·멈춤 키 없음 → 「실매매」 (명세 C4)', () => {
    renderPanel('momentum')
    expect(screen.getByTestId('momentum-monitor-badge').textContent).toBe('실매매')
  })

  it('기준일 머리말 — 아침 준비 / 저녁 미리보기(잠정) / 준비 중 / 준비 실패', () => {
    const { unmount } = renderPanel('etf_trend')
    const h = screen.getByTestId('etf_trend-monitor-asof').textContent ?? ''
    expect(h).toMatch(/10-12/)
    expect(h).toMatch(/07:46/)
    expect(h).not.toMatch(/잠정/)
    unmount()

    const r2 = renderPanel('etf_trend', {
      now: at('21:05'),
      monitor: (m) => {
        m.etf_trend.prepare = { as_of: '2026-10-13', phase: 'evening', started_at: '2026-10-12T21:00:01+09:00',
          finished_at: '2026-10-12T21:02:00+09:00', ok: true }
      },
    })
    const h2 = screen.getByTestId('etf_trend-monitor-asof').textContent ?? ''
    expect(h2).toMatch(/10-13/)
    expect(h2).toMatch(/잠정/)
    expect(h2).toMatch(/21:02/)
    r2.unmount()

    const r3 = renderPanel('etf_trend', { monitor: (m) => { m.etf_trend.prepare.ok = null; m.etf_trend.prepare.finished_at = null } })
    expect(screen.getByTestId('etf_trend-monitor-asof').textContent).toMatch(/준비 중/)
    r3.unmount()

    renderPanel('etf_trend', { monitor: (m) => { m.etf_trend.prepare.ok = false } })
    expect(screen.getByTestId('etf_trend-monitor-asof').textContent).toMatch(/준비 실패.*07:46/)
  })

  it('전략 데이터가 없으면 빈 패널(`<sid>-monitor-empty`)', () => {
    renderPanel('etf_trend', { strategies: (s) => { delete s.etf_trend } })
    expect(screen.getByTestId('etf_trend-monitor-empty')).toBeTruthy()
  })

  it('400px — 머리줄은 flex-wrap, 배지는 whitespace-nowrap, 후보표는 가로 스크롤 래퍼 안', () => {
    renderPanel('etf_trend')
    const badge = screen.getByTestId('etf_trend-monitor-badge')
    expect(badge.className).toContain('whitespace-nowrap')
    expect((badge.parentElement as HTMLElement).className).toContain('flex-wrap')
    const table = within(screen.getByTestId('etf_trend-monitor-candidates')).getByRole('table')
    let el: HTMLElement | null = table.parentElement
    let scrolls = false
    while (el && !scrolls) {
      scrolls = /overflow-x-auto|overflow-auto/.test(el.className) || el.style.overflowX === 'auto' || el.style.overflow === 'auto'
      el = el.parentElement
    }
    expect(scrolls, '좁은 화면에서 표는 가로 스크롤 래퍼(ScrollPane 등) 안에 둔다').toBe(true)
  })
})

// ─────────────────────────────────────────────────────────────────────────────
describe('③ 깔때기 — 라우트 단계 이름 · 병목 · 폴백 (F6)', () => {
  it('라우트 funnel 의 step_name·step_conditions 를 그대로 쓰고 수를 막대로', () => {
    renderPanel('etf_trend')
    const f = screen.getByTestId('etf_trend-monitor-funnel')
    for (const n of [1, 2, 3, 4, 5, 6, 99]) expect(within(f).getByTestId(`etf_trend-monitor-funnel-row-${n}`)).toBeTruthy()
    expect(within(f).getByTestId('etf_trend-monitor-funnel-row-4').textContent).toMatch(/20일 신고가 돌파/)
    expect(within(f).getByTestId('etf_trend-monitor-funnel-row-4').textContent).toMatch(/조건-4/)
    expect(within(f).getByTestId('etf_trend-monitor-funnel-row-1').textContent).toMatch(/41/)
  })

  it('처음 0 이 되는 단계에 「여기서 0」 + 최종 0 이면 「○단계(이름)에서 전부 걸렸습니다」', () => {
    renderPanel('etf_trend', {
      monitor: (m) => {
        for (const r of m.etf_trend.funnel) if (r.step_no >= 5) r.survived_count = 0
      },
    })
    const f = screen.getByTestId('etf_trend-monitor-funnel')
    expect(within(f).getByTestId('etf_trend-monitor-funnel-row-5').textContent).toMatch(/여기서 0/)
    expect(within(f).getByTestId('etf_trend-monitor-funnel-row-6').textContent).not.toMatch(/여기서 0/)
    expect(f.textContent).toMatch(/최종 후보 0/)
    expect(f.textContent).toMatch(/EMA60 우상향 통과/)
  })

  it('14일 추이 — 마지막 0 연속 일수 표기', () => {
    renderPanel('etf_trend', {
      trend: [{ date: '2026-10-08', count: 2 }, { date: '2026-10-11', count: 0 }, { date: '2026-10-12', count: 0 }],
    })
    expect(screen.getByTestId('etf_trend-monitor-funnel').textContent).toMatch(/0 연속 2일/)
  })

  it('라우트 실패(monitor=null) — ETF 는 scan_stats 로 1행·최종만', () => {
    renderPanel('etf_trend', { monitor: null })
    const f = screen.getByTestId('etf_trend-monitor-funnel')
    expect(within(f).getByTestId('etf_trend-monitor-funnel-row-1').textContent).toMatch(/41/)
    expect(within(f).getByTestId('etf_trend-monitor-funnel-row-99').textContent).toMatch(/2/)
    expect(within(f).queryByTestId('etf_trend-monitor-funnel-row-4')).toBeNull()
  })

  it('라우트 실패 폴백 상수 라벨에도 낡은 리터럴이 없다 — VCP 「50/150/200」', () => {
    renderPanel('vcp_breakout', { monitor: null })
    const f = screen.getByTestId('vcp_breakout-monitor-funnel')
    expect(f.textContent).toMatch(/2000/)
    expect(f.textContent).not.toMatch(/50\/150\/200/)
  })
})

// ─────────────────────────────────────────────────────────────────────────────
describe('ETF 추세 — 후보 상태(엔진 거름 순서) · F3·F7', () => {
  it('멈춤 중 → 주 배지 「멈춤」 + 회색 「풀리면: …」(화면 추정)', () => {
    renderPanel('etf_trend')
    expect(statusOf('etf_trend', ETF_A)).toMatch(/멈춤/)
    expect(screen.getByTestId(`etf_trend-monitor-unpaused-${ETF_A}`).textContent).toMatch(/풀리면.*진입 가능/)
    expect(screen.getByTestId(`etf_trend-monitor-unpaused-${ETF_B}`).textContent).toMatch(/풀리면.*묶음/)
  })

  it('시세 없음이 최우선 — 미구독이면 멈춤보다 먼저', () => {
    renderPanel('etf_trend', { subscribed: [ETF_B, ETF_HELD] })
    expect(statusOf('etf_trend', ETF_A)).toMatch(/시세 없음/)
  })

  it.each([
    ['시가=전일종가×1.03 → 갭 초과(≥)', 10_300, 10_350, /갭 초과/],
    ['시가=전일종가×1.0299 → 통과', 10_299, 10_350, /진입 가능/],
    ['현재가=시가−1 → 장중 붕괴', 10_299, 10_298, /붕괴/],
  ])('%s', (_name, open, cur, want) => {
    renderPanel('etf_trend', {
      strategies: unpause('etf_trend'),
      prices: (p) => { p[ETF_A] = { ...p[ETF_A], open_price: open, current_price: cur } },
    })
    expect(statusOf('etf_trend', ETF_A)).toMatch(want)
  })

  it.each([
    ['시가=돌파선×1.04 → 통과(엔진은 >)', 10_192, /진입 가능/],
    ['시가=돌파선×1.0401 → 돌파선 위 과다', 10_193, /돌파선 위 과다/],
  ])('%s', (_name, open, want) => {
    renderPanel('etf_trend', {
      strategies: (s) => { s.etf_trend.params.buy_paused = false; s.etf_trend.targets[ETF_A].target_price = 9_800 },
      monitor: (m) => { m.etf_trend.candidates[ETF_A].line = 9_800 },
      prices: (p) => { p[ETF_A] = { ...p[ETF_A], open_price: open, current_price: open + 50 } },
    })
    expect(statusOf('etf_trend', ETF_A)).toMatch(want)
  })

  it('멈춤 켜짐 + 갭 초과 → 주 배지 멈춤 + 「풀리면: 갭 초과」', () => {
    renderPanel('etf_trend', { prices: (p) => { p[ETF_A] = { ...p[ETF_A], open_price: 10_300 } } })
    expect(statusOf('etf_trend', ETF_A)).toMatch(/멈춤/)
    expect(statusOf('etf_trend', ETF_A)).not.toMatch(/갭 초과/)
    expect(screen.getByTestId(`etf_trend-monitor-unpaused-${ETF_A}`).textContent).toMatch(/풀리면.*갭 초과/)
  })

  it('시장 유닛 shadow·m=0 → ETF 는 차단(「시장 유닛 0배」)', () => {
    renderPanel('etf_trend', {
      strategies: unpause('etf_trend'),
      monitor: (m) => { m.etf_trend.market_unit = { mode: 'shadow', ok: true, m: 0, state: 'down_falling', bar_date: '2026-10-08' } },
    })
    expect(statusOf('etf_trend', ETF_A)).toMatch(/시장 유닛 0배/)
  })

  it('시장 유닛 스냅샷 결손(shadow) → ETF 는 「시장 유닛 미계산」 차단', () => {
    renderPanel('etf_trend', {
      strategies: unpause('etf_trend'),
      monitor: (m) => { m.etf_trend.market_unit = { mode: 'shadow', ok: false, reason: 'not_computed' } },
    })
    expect(statusOf('etf_trend', ETF_A)).toMatch(/시장 유닛 미계산/)
  })

  it('예상 수량 0 → 빨강 「1주도 안 됨 — 사지 않음」 · 양수는 「최대 n주」', () => {
    renderPanel('etf_trend', {
      strategies: unpause('etf_trend'),
      monitor: (m) => { m.etf_trend.candidates[ETF_A].design_qty = 0 },
    })
    expect(screen.getByTestId(`etf_trend-monitor-qty-${ETF_A}`).textContent).toMatch(/1주도 안 됨/)
    expect(statusOf('etf_trend', ETF_A)).toMatch(/1주도 안 됨/)
  })

  it('예상 수량 양수 → 「최대 250주」', () => {
    renderPanel('etf_trend')
    expect(screen.getByTestId(`etf_trend-monitor-qty-${ETF_A}`).textContent).toMatch(/최대 250주/)
  })

  it.each([
    ['09:04', /09:05 부터/],
    ['09:05', /진입 가능/],
    ['09:30', /진입 가능/],
    ['09:31', /진입창 지남|다음 거래일/],
  ])('진입창 %s → %s (F7, 시각 주입)', (hhmm, want) => {
    renderPanel('etf_trend', { strategies: unpause('etf_trend'), now: at(hhmm) })
    expect(statusOf('etf_trend', ETF_A)).toMatch(want)
  })

  it('오늘 갭 스킵 기록이 있으면 「오늘 갭 스킵」 으로 구체화(엔진이 _bought_today 에 넣는 경로)', () => {
    renderPanel('etf_trend', {
      strategies: unpause('etf_trend'),
      monitor: (m) => {
        m.etf_trend.skips = { known: true, day: '2026-10-12', counts: { gap_up: 1 }, by_ticker: { [ETF_A]: ['gap_up'] } }
      },
    })
    expect(statusOf('etf_trend', ETF_A)).toMatch(/오늘 갭 스킵/)
  })
})

describe('ETF 추세 — ⑤ 사유 · ⑦ 보유 방어선', () => {
  it('⑤ 멈춤 중 → 「멈춤 중 — 엔진 기록 없음」 + 오늘 멈춤으로 건너뛴 종목 수', () => {
    renderPanel('etf_trend')
    const sk = screen.getByTestId('etf_trend-monitor-skips').textContent ?? ''
    expect(sk).toMatch(/멈춤 중/)
    expect(sk).toMatch(/건너뛴 종목 1/)
  })

  it('⑤ 멈춤 아님 → 사유별 종목 수(엔진 reason 을 화면 문구로)', () => {
    renderPanel('etf_trend', {
      strategies: unpause('etf_trend'),
      monitor: (m) => {
        m.etf_trend.skips = { known: true, day: '2026-10-12', counts: { gap_up: 2, cluster_held: 1, rounds_to_zero: 1 },
          by_ticker: {} }
      },
    })
    const sk = screen.getByTestId('etf_trend-monitor-skips').textContent ?? ''
    expect(sk).toMatch(/전일 대비 갭 과다/)
    expect(sk).toMatch(/같은 묶음 ETF 보유 중/)
    expect(sk).toMatch(/1주도 안 됨/)
  })

  it('⑦ 실효 손절선 = 엔진 값(exit-lines) · 같은 값의 구성 선만 「작동 중」', () => {
    renderPanel('etf_trend')
    const row = screen.getByTestId(`etf_trend-monitor-holding-${ETF_HELD}`)
    expect(within(row).getByTestId(`etf_trend-monitor-stop-${ETF_HELD}`).textContent).toMatch(/10,240/)
    expect(within(row).getByTestId(`etf_trend-monitor-line-${ETF_HELD}-trail`).getAttribute('data-active')).toBe('true')
    for (const k of ['hard', 'breakeven', 'channel']) {
      expect(within(row).getByTestId(`etf_trend-monitor-line-${ETF_HELD}-${k}`).getAttribute('data-active'), k).toBe('false')
    }
  })

  it('⑦ 엔진 실효선과 같은 구성 선이 없으면 아무것도 강조하지 않는다', () => {
    renderPanel('etf_trend', {
      exitLines: (items) => { items[0].stop_price = 10_500 },
      monitor: (m) => { m.etf_trend.holdings[ETF_HELD].effective_stop = 10_500 },
    })
    const row = screen.getByTestId(`etf_trend-monitor-holding-${ETF_HELD}`)
    for (const k of ['hard', 'breakeven', 'trail', 'channel']) {
      expect(within(row).getByTestId(`etf_trend-monitor-line-${ETF_HELD}-${k}`).getAttribute('data-active'), k).toBe('false')
    }
  })

  it('⑦ 엔진 실효선을 모르면 「—」(화면이 산식을 흉내 내 채우지 않는다)', () => {
    renderPanel('etf_trend', {
      exitLines: (items) => { items[0].stop_price = null },
      monitor: (m) => { m.etf_trend.holdings[ETF_HELD].effective_stop = null },
    })
    expect(screen.getByTestId(`etf_trend-monitor-stop-${ETF_HELD}`).textContent).toMatch(/—/)
  })

  it.each([
    [10_700, 'normal'],   // (10700−10240)/10700 = 4.3%
    [10_500, 'orange'],   // 2.48%
    [10_300, 'red'],      // 0.58%
  ])('⑦ 손절까지 거리 — 현재가 %s → %s', (cur, tone) => {
    renderPanel('etf_trend', { prices: (p) => { p[ETF_HELD] = { ...p[ETF_HELD], current_price: cur } } })
    expect(screen.getByTestId(`etf_trend-monitor-stopdist-${ETF_HELD}`).getAttribute('data-tone')).toBe(tone)
  })

  it('⑦ 15:20 돌파 실패 카운트다운 — 판정 대상 · 돌파선 아래 · 아직 아님', () => {
    const r1 = renderPanel('etf_trend')
    expect(screen.getByTestId(`etf_trend-monitor-countdown-${ETF_HELD}`).textContent).toMatch(/15:20 판정 대상/)
    r1.unmount()

    const r2 = renderPanel('etf_trend', { prices: (p) => { p[ETF_HELD] = { ...p[ETF_HELD], current_price: 9_850 } } })
    expect(screen.getByTestId(`etf_trend-monitor-countdown-${ETF_HELD}`).textContent).toMatch(/15:20 정리/)
    r2.unmount()

    renderPanel('etf_trend', {
      monitor: (m) => { m.etf_trend.holdings[ETF_HELD].breakout_fail.active = false; m.etf_trend.holdings[ETF_HELD].bars_since_buy = 1 },
    })
    expect(screen.getByTestId(`etf_trend-monitor-countdown-${ETF_HELD}`).textContent).toMatch(/2봉째부터/)
  })

  it('⑦ 보유 ETF 틱이 breakout_fail_price_max_age_secs(180초)보다 낡으면 「시세 낡음」(15:20 직전)', () => {
    // 보완 1차(M5) — 시각이 먼저다: 15:20 판정 직전(15:15)의 4분 낡은 틱만 「15:20 판정 건너뜀 위험」.
    renderPanel('etf_trend', {
      now: at('15:15'),
      monitor: (m) => { m.etf_trend.ticks[ETF_HELD].last_tick_at = '2026-10-12T15:11:00+09:00' }, // 4분 전
    })
    expect(screen.getByTestId(`etf_trend-monitor-countdown-${ETF_HELD}`).textContent).toMatch(/시세 낡음/)
  })
})

// ─────────────────────────────────────────────────────────────────────────────
describe('돈키언 — 깡토식 청산 · 1R · 시간청산 카운트다운 · F4', () => {
  const dcHold = (patch: Dict) => (m: Dict) => { Object.assign(m.donchian_swing.holdings[DC_HELD], patch) }

  it.each([
    [{ days_held: 18, reached_1r: false }, /1영업일 뒤 15:20/],
    [{ days_held: 19, reached_1r: false }, /오늘 15:20/],
    [{ days_held: 19, reached_1r: true }, /면제/],
  ])('카운트다운 %o → %s', (patch, want) => {
    renderPanel('donchian_swing', { monitor: dcHold(patch) })
    const c = screen.getByTestId(`donchian_swing-monitor-countdown-${DC_HELD}`).textContent ?? ''
    expect(c).toMatch(want)
  })

  it('보유 (days_held+1)봉째 · 거래일 캐시 부족이면 「보유일 근사」', () => {
    renderPanel('donchian_swing', { monitor: dcHold({ days_held: 18, days_fallback: true }) })
    const c = screen.getByTestId(`donchian_swing-monitor-countdown-${DC_HELD}`).textContent ?? ''
    expect(c).toMatch(/19봉째/)
    expect(c).toMatch(/보유일 근사/)
  })

  it('무장 전 사다리에 무장가 · 무장 뒤 「손절선 본전 · 10일 채널」', () => {
    const r1 = renderPanel('donchian_swing')
    expect(screen.getByTestId(`donchian_swing-monitor-holding-${DC_HELD}`).textContent).toMatch(/124,000/)
    r1.unmount()
    renderPanel('donchian_swing', { monitor: dcHold({ armed: true, arm_price: null, stop: 100_000, channel: 101_000 }) })
    const t = screen.getByTestId(`donchian_swing-monitor-holding-${DC_HELD}`).textContent ?? ''
    expect(t).toMatch(/무장/)
    expect(t).toMatch(/101,000/)
  })

  it('오늘 신규 진입 n / max_daily_entries 게이지', () => {
    renderPanel('donchian_swing')
    expect(screen.getByTestId('donchian_swing-monitor-daily-entries').textContent).toMatch(/0\s*\/\s*3/)
  })

  it('후보 1R·R% · 설계 랏 0 이면 빨강 「사지 않음」', () => {
    const r1 = renderPanel('donchian_swing')
    const row = screen.getByTestId(`donchian_swing-monitor-candidate-${DC_CAND}`).textContent ?? ''
    expect(row).toMatch(/4,000/)
    expect(row).toMatch(/8\.0%/)
    r1.unmount()
    renderPanel('donchian_swing', {
      strategies: unpause('donchian_swing'),
      monitor: (m) => { m.donchian_swing.candidates[DC_CAND].design_lot = 0 },
    })
    expect(screen.getByTestId(`donchian_swing-monitor-candidate-${DC_CAND}`).textContent).toMatch(/사지 않음/)
    expect(statusOf('donchian_swing', DC_CAND)).toMatch(/설계 랏 0/)
  })

  it('상태 순서 — 갭 초과 → 추격 상한 초과 → 하루 신규 상한', () => {
    const r1 = renderPanel('donchian_swing', {
      strategies: unpause('donchian_swing'),
      prices: (p) => { p[DC_CAND] = { ...p[DC_CAND], open_price: 51_500, current_price: 51_600 } }, // 갭 3%
    })
    expect(statusOf('donchian_swing', DC_CAND)).toMatch(/갭/)
    r1.unmount()
    const r2 = renderPanel('donchian_swing', {
      strategies: unpause('donchian_swing'),
      prices: (p) => { p[DC_CAND] = { ...p[DC_CAND], open_price: 50_800, current_price: 51_100 } }, // (51100−49500)/49500 = 3.23%
    })
    expect(statusOf('donchian_swing', DC_CAND)).toMatch(/추격 상한 초과/)
    r2.unmount()
    renderPanel('donchian_swing', {
      strategies: unpause('donchian_swing'),
      monitor: (m) => { m.donchian_swing.extra.daily_entries = { count: 3, cap: 3 } },
    })
    expect(statusOf('donchian_swing', DC_CAND)).toMatch(/하루 신규 상한/)
  })

  it('청산 규칙 설명은 cycle405 깡토식 — 숫자는 params 에서(낡은 「ATR×2 트레일·−7%·시간청산 없음」 금지)', () => {
    renderPanel('donchian_swing', {
      strategies: (s) => {
        Object.assign(s.donchian_swing.params, { kk_breakeven_r: 2.5, kk_time_exit_bars: 15, max_daily_entries: 2 })
      },
    })
    const rules = screen.getByTestId('donchian_swing-monitor-exit-rules').textContent ?? ''
    expect(rules).toMatch(/1R/)
    expect(rules).toMatch(/2\.5R/)
    expect(rules).toMatch(/15봉/)
    expect(rules).toMatch(/무장/)
    expect(rules).toMatch(/2종목/)
    expect(rules).not.toMatch(/ATR\s*\(?14\)?\s*×\s*2|-7%|−7%|시간 청산 없음/)
  })
})

// ─────────────────────────────────────────────────────────────────────────────
describe('VCP·BFB — 거래량 게이지 · 추격 상한 · 래치 · F5', () => {
  it('VCP 거래량 게이지 = acml_vol / volume_threshold · 미관측이면 「엔진은 사지 않음」', () => {
    const r1 = renderPanel('vcp_breakout')
    expect(screen.getByTestId(`vcp_breakout-monitor-volgauge-${VCP_A}`).textContent).toMatch(/150%/)
    r1.unmount()
    renderPanel('vcp_breakout', { monitor: (m) => { m.vcp_breakout.ticks[VCP_A].acml_vol = null } })
    const g = screen.getByTestId(`vcp_breakout-monitor-volgauge-${VCP_A}`).textContent ?? ''
    expect(g).toMatch(/거래량 미관측/)
    expect(statusOf('vcp_breakout', VCP_A)).toMatch(/거래량 미관측/)
  })

  it.each([
    [10_750, false], // 정확히 7.5% → 허용(엔진은 > 만 거부)
    [10_751, true],  // 7.51% → 추격 상한 초과
  ])('VCP 추격 상한 — 현재가 %s → 초과=%s', (cur, over) => {
    // 보완 1차(H2) — 「진입 가능」 은 오늘 무장한 래치(또는 아래→위 교차 틱)가 있을 때만이라 래치를 둔다.
    renderPanel('vcp_breakout', {
      now: at('10:00'),
      prices: (p) => { p[VCP_A] = { ...p[VCP_A], current_price: cur } },
      monitor: (m) => { m.vcp_breakout.candidates[VCP_A].latch_armed_at = '2026-10-12T00:10:00Z' },
    })
    const s = statusOf('vcp_breakout', VCP_A)
    if (over) expect(s).toMatch(/추격 상한 초과/)
    else {
      expect(s).not.toMatch(/추격 상한 초과/)
      expect(s).toMatch(/진입 가능/)
    }
  })

  it('VCP 래치 무장 시각(KST hh:mm) 표시', () => {
    renderPanel('vcp_breakout', {
      monitor: (m) => { m.vcp_breakout.candidates[VCP_A].latch_armed_at = '2026-10-12T00:10:00Z' },
    })
    expect(screen.getByTestId(`vcp_breakout-monitor-latch-${VCP_A}`).textContent).toMatch(/09:10/)
  })

  it('VCP 돌파선 아래 → 「돌파선 아래」 + 거리 %', () => {
    renderPanel('vcp_breakout', { now: at('10:00'), prices: (p) => { p[VCP_A] = { ...p[VCP_A], current_price: 9_900 } } })
    expect(statusOf('vcp_breakout', VCP_A)).toMatch(/돌파선 아래/)
  })

  it('BFB breakout_retention_minutes=0 → 유지 대기 칸 없음 · >0 이면 있음', () => {
    const r1 = renderPanel('bull_flag_breakout')
    expect(screen.queryByTestId(`bull_flag_breakout-monitor-retention-${BFB_A}`)).toBeNull()
    expect(screen.getByTestId('bull_flag_breakout-monitor-candidates').textContent).not.toMatch(/유지 대기/)
    r1.unmount()
    renderPanel('bull_flag_breakout', {
      strategies: (s) => {
        s.bull_flag_breakout.params.breakout_retention_minutes = 5
        s.bull_flag_breakout.targets[BFB_A].retention_minutes = 5
        s.bull_flag_breakout.targets[BFB_A].breakout_seen_at = '2026-10-12T09:10:00+09:00'
      },
    })
    expect(screen.getByTestId(`bull_flag_breakout-monitor-retention-${BFB_A}`)).toBeTruthy()
  })

  it('BFB 구조 막대에 측정목표(11,600)', () => {
    renderPanel('bull_flag_breakout')
    expect(screen.getByTestId(`bull_flag_breakout-monitor-candidate-${BFB_A}`).textContent).toMatch(/11,600/)
  })
})

// ─────────────────────────────────────────────────────────────────────────────
describe('⑥ 진입 기록 · 가벼운 패널(VB·모멘텀·LTV) · 고지로', () => {
  it('VB 섀도 기록 = shadow_buys 수 · 「매수 신호 0」 이 「섀도가 안 돈다」 가 아님을 밝힌다', () => {
    renderPanel('volatility_breakout')
    const entries = screen.getByTestId('volatility_breakout-monitor-entries')
    const e = entries.textContent ?? ''
    expect(e).toMatch(/섀도 기록 2|실전이었으면 샀을 종목 2/)
    expect(e).toMatch(/매수 신호/)
    expect(e).toContain(VB_A)
  })

  it('가벼운 패널은 ①②③⑥만 — 후보표(④)·사유(⑤) 없음', () => {
    for (const sid of ['volatility_breakout', 'momentum', 'long_tail_volatility']) {
      const { unmount } = renderPanel(sid)
      for (const part of ['status', 'timeline', 'funnel', 'entries']) {
        expect(screen.getByTestId(`${sid}-monitor-${part}`), `${sid} ${part}`).toBeTruthy()
      }
      expect(screen.queryByTestId(`${sid}-monitor-candidates`), sid).toBeNull()
      expect(screen.queryByTestId(`${sid}-monitor-skips`), sid).toBeNull()
      unmount()
    }
  })

  it('⑥ 기준선 정규화 — donchian `donchian_high` 를 기준선 칸에, change_rate=0 은 「+0%」 대신 「—」 (F9)', () => {
    renderPanel('donchian_swing', {
      strategies: (s) => {
        s.donchian_swing.buy_signals = [{ ticker: DC_CAND, name: '', price: 50_100, donchian_high: 49_500, atr: 1_500,
          change_rate: 0, time: '09:06:12' }]
      },
    })
    const e = screen.getByTestId('donchian_swing-monitor-entries').textContent ?? ''
    expect(e).toMatch(/49,500/)
    expect(e).toMatch(/09:06:12/)
    expect(e).not.toMatch(/\+0%/)
  })

  it('LTV 보유 손절선은 상한가 모드에 따라 달라 화면이 하나로 고르지 않는다', () => {
    renderPanel('long_tail_volatility', {
      strategies: (s) => {
        s.long_tail_volatility.positions = 1
        s.long_tail_volatility.positions_detail = {
          '457370': { name: 'A', buy_price: 1000, quantity: 1, high_since_buy: 1000, buy_date: '2026-10-06', is_next_day: true },
        }
      },
      exitLines: (items) => {
        items.push({ strategy_id: 'long_tail_volatility', ticker: '457370', stop_price: null, stop_source: 'mode_dependent',
          target_price: null, target_source: null, buy_price: 1000, quantity: 1, high_since_buy: 1000,
          buy_date: '2026-10-06', order_no: 'O', entry_atr: null, kk_armed: null, kk_arm_price: null })
      },
    })
    expect(screen.getByTestId('long_tail_volatility-monitor').textContent).toMatch(/상한가 모드에 따라/)
  })

  it('고지로 → 기존 KojiroMonitor(id 보존) + 배너는 §2.2 배지(멈춤)', () => {
    renderPanel('kojiro')
    expect(screen.getByTestId('kojiro-monitor')).toBeTruthy()
    expect(screen.getByTestId('kojiro-darklaunch-banner').textContent).toMatch(/신규 매수 멈춤/)
  })

  it('고지로 → 라우트 깔때기 이름을 쓴다(화면 리터럴 「4.5%」 없음)', () => {
    renderPanel('kojiro')
    const root = screen.getByTestId('kojiro-monitor').textContent ?? ''
    expect(root).toMatch(/6→1 전환 인접/)
    expect(root).not.toMatch(/4\.5%/)
  })
})

// 펼침 버튼이 있어도 핵심 칸은 기본으로 보여야 한다(현행 돈키언 후보표는 「펼치기」 를 눌러야 보였다).
describe('기본 펼침', () => {
  it('후보표·보유 방어선은 클릭 없이 보인다', () => {
    const r1 = renderPanel('etf_trend')
    expect(screen.getByTestId(`etf_trend-monitor-candidate-${ETF_A}`)).toBeTruthy()
    expect(screen.getByTestId(`etf_trend-monitor-holding-${ETF_HELD}`)).toBeTruthy()
    r1.unmount()
    renderPanel('donchian_swing')
    expect(screen.getByTestId(`donchian_swing-monitor-candidate-${DC_CAND}`)).toBeTruthy()
    expect(screen.getByTestId(`donchian_swing-monitor-holding-${DC_HELD}`)).toBeTruthy()
  })
})

// 고정 데이터 회귀 — 키 이름이 백엔드와 같다(명세 §9). 고정 데이터 자체가 틀리면 위 테스트가 공허해진다.
describe('고정 데이터 실제 키', () => {
  it('status/monitor/exit-lines 모양', () => {
    const s = makeStatusStrategies() as Dict
    expect(Object.keys(s.etf_trend.targets[ETF_A]).sort()).toEqual(['prev_close', 'target_price'])
    expect(s.vcp_breakout.targets[VCP_A]).toHaveProperty('volume_threshold')
    const m = makeMonitorEntries() as Dict
    for (const sid of Object.keys(m)) {
      expect(Object.keys(m[sid]).sort()).toEqual(
        // cycle423 카드 #6(N-e) — bought_today·sold_today 추가.
        ['bought_today', 'candidates', 'extra', 'funnel', 'holdings', 'market_unit', 'paused_skips',
          'prepare', 'shadow_buys', 'skips', 'sold_today', 'ticks'],
      )
    }
    expect(Object.keys((makeExitLines() as Dict).items[0]).length).toBe(14)
    expect(ETF_B).toBe('229200')
  })
})
