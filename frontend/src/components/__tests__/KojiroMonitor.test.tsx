/**
 * 고지로(kojiro) 대순환 전용 모니터링 패널 회귀 가드.
 *
 * 6 패널: 상태 배너 / 대순환 사이클+분포 / 유니버스 깔때기 / 후보 그리드 /
 * 진입 이벤트 / 보유 방어선.
 *
 * cycle414(명세 `_workspace/red/cycle414/monitor_spec.md` §4.5 정정 목록) — 테스트 id 는 그대로 두고 내용만 바꾼다:
 *  - 배너 = 공통 상태 배지(꺼짐·멈춤·섀도·실매매, `=== true` 만 켜짐) — 「관찰(다크런치)/활성」 둘뿐이던 것 시정
 *  - 실효 손절선 = exit-lines `stop_price`(엔진 `_position_stop_price`) — 후보 ATR 로 화면이 계산하던 것 폐기.
 *    구성 선은 exit-lines `entry_atr` 로 그린다(보유가 후보에서 빠져도 비지 않는다)
 *  - 문턱 숫자는 `params` 에서(밴드 4.5%·신선도 3일·갭 ≥5%/≤-4% 리터럴 금지)
 */
import { describe, it, expect } from 'vitest'
import { render, screen, within } from '@testing-library/react'

import KojiroMonitor from '../KojiroMonitor'
import type { StrategyInfo } from '../../types/trading'

function makeKojiro(over: Partial<StrategyInfo> = {}): Record<string, StrategyInfo> {
  const base: StrategyInfo = {
    name: '고지로 대순환',
    enabled: false,
    weight: 0,
    positions: 0,
    pending_buys: 0,
    position_tickers: [],
    total_investment: 0,
    daily_realized_pnl: 0,
    buy_disabled: false,
    buy_signals: [],
    positions_detail: {},
    pending_buy_tickers: [],
    scanned_count: 0,
    scanned_tickers: [],
    targets: {},
    scan_stats: {
      universe_union: 348, universe_candidates: 95, universe_filtered: 90,
      candle_fetch_ok: 88, band_pass: 40, stage_valid_pass: 38,
      stage1_uptrend_pass: 6, strict_entry_pass: 3, final_prepared: 3,
      last_run_at: '2026-07-17T21:00:00+09:00',
    },
    params: {
      stop_atr: 2.0, trail_atr: 2.5, hard_stop_pct: -8.0,
      atr_ratio_min: 0.01, atr_ratio_max: 0.045, position_ratio: 0.2,
    },
    ...over,
  }
  return { kojiro: base }
}

describe('KojiroMonitor — 6 패널', () => {
  it('1) 배너: enabled=false → 공통 배지 「꺼짐」 + last_run_at(KST)', () => {
    render(<KojiroMonitor strategies={makeKojiro()} />)
    const banner = screen.getByTestId('kojiro-darklaunch-banner')
    expect(banner.textContent).toMatch(/꺼짐/)
    expect(banner.textContent).not.toMatch(/다크런치/)
    expect(banner.textContent).toMatch(/07-17|21:00/) // KST last_run_at
  })

  it('1b) 배너: enabled=true → 「실매매」 + 비중 19%', () => {
    render(<KojiroMonitor strategies={makeKojiro({ enabled: true, weight: 0.19 })} />)
    const banner = screen.getByTestId('kojiro-darklaunch-banner')
    expect(banner.textContent).toMatch(/실매매/)
    expect(banner.textContent).toContain('19%')
  })

  it('1c) 배너: buy_paused=true → 「신규 매수 멈춤」 · 문자열 "true" 는 멈춤 아님(모양 오류)', () => {
    const { unmount } = render(<KojiroMonitor strategies={makeKojiro({ enabled: true, weight: 0.3, params: { buy_paused: true } })} />)
    expect(screen.getByTestId('kojiro-darklaunch-banner').textContent).toMatch(/신규 매수 멈춤/)
    unmount()
    render(<KojiroMonitor strategies={makeKojiro({ enabled: true, weight: 0.3, params: { buy_paused: 'true' } })} />)
    const b = screen.getByTestId('kojiro-darklaunch-banner').textContent ?? ''
    expect(b).not.toMatch(/신규 매수 멈춤/)
    expect(b).toMatch(/모양 오류/)
  })

  it('1d) 배너: shadow_mode=true → 「섀도」', () => {
    render(<KojiroMonitor strategies={makeKojiro({ enabled: true, weight: 0, params: { shadow_mode: true } })} />)
    expect(screen.getByTestId('kojiro-darklaunch-banner').textContent).toMatch(/섀도/)
  })

  it('2) 대순환 사이클: 6 스테이지 + targets 분포 히스토그램', () => {
    const targets = {
      '005930': { prev_close: 60000, atr: 1800, stage: 1, ema_s: 61000, ema_m: 60000, ema_l: 59000, atr_ratio: 0.03 },
      '000660': { prev_close: 50000, atr: 1500, stage: 1, ema_s: 51000, ema_m: 50000, ema_l: 49000, atr_ratio: 0.03 },
      '035420': { prev_close: 40000, atr: 1200, stage: 3, ema_s: 39000, ema_m: 40000, ema_l: 39500, atr_ratio: 0.03 },
    }
    render(<KojiroMonitor strategies={makeKojiro({ targets })} />)
    const cycle = screen.getByTestId('kojiro-stage-cycle')
    expect(cycle).toBeTruthy()
    // 스테이지 1 = 2종목, 스테이지 3 = 1종목
    expect(within(cycle).getByTestId('kojiro-stage-count-1').textContent).toBe('2')
    expect(within(cycle).getByTestId('kojiro-stage-count-3').textContent).toBe('1')
    expect(within(cycle).getByTestId('kojiro-stage-count-6').textContent).toBe('0')
  })

  it('3) 유니버스 깔때기: 9단계 막대 + 카운트', () => {
    render(<KojiroMonitor strategies={makeKojiro()} />)
    const funnel = screen.getByTestId('kojiro-scan-funnel')
    // 9 단계 row
    for (let i = 0; i < 9; i++) {
      expect(within(funnel).getByTestId(`kojiro-funnel-row-${i}`)).toBeTruthy()
    }
    expect(funnel.textContent).toContain('348')   // universe_union
    expect(funnel.textContent).toMatch(/변동성 밴드/)  // band_pass 라벨
    expect(funnel.textContent).toContain('3')     // final_prepared
  })

  it('3b) scan_stats=null → 아직 스캔 전 fallback', () => {
    render(<KojiroMonitor strategies={makeKojiro({ scan_stats: null })} />)
    expect(screen.getByTestId('kojiro-scan-funnel').textContent).toMatch(/아직 스캔 전/)
  })

  it('4) 후보 그리드: stage 배지 + EMA 정배열 + ATR 밴드 %', () => {
    const targets = {
      '005930': { prev_close: 60000, atr: 1800, stage: 1, ema_s: 61000, ema_m: 60000, ema_l: 59000, atr_ratio: 0.03 },
    }
    render(<KojiroMonitor strategies={makeKojiro({ targets })} />)
    const row = screen.getByTestId('kojiro-candidate-005930')
    expect(row.textContent).toContain('005930')
    expect(row.textContent).toContain('정배열')       // ema_s>ema_m>ema_l
    expect(row.textContent).toContain('3.0%')          // atr_ratio 3%
    expect(within(row).getByTestId('kojiro-band-marker-005930')).toBeTruthy()
  })

  it('4b) atr_ratio 부재 시 atr/prev_close 프론트 계산', () => {
    const targets = {
      '005930': { prev_close: 50000, atr: 1000, stage: 2, ema_s: 0, ema_m: 0, ema_l: 0 },
    }
    render(<KojiroMonitor strategies={makeKojiro({ targets })} />)
    // 1000/50000 = 2.0%
    expect(screen.getByTestId('kojiro-candidate-005930').textContent).toContain('2.0%')
  })

  it('5) 진입 이벤트: 빈 상태 + 신호 피드', () => {
    render(<KojiroMonitor strategies={makeKojiro()} />)
    expect(screen.getByTestId('kojiro-entry-feed').textContent).toMatch(/매수 신호 없음|관찰 모드/)

    const withSignal = makeKojiro({
      buy_signals: [{ ticker: '005930', name: '삼성전자', price: 61000, change_rate: 0, time: '09:07:00', stage: 1, atr: 1800 } as never],
    })
    render(<KojiroMonitor strategies={withSignal} />)
    const feeds = screen.getAllByTestId('kojiro-entry-feed')
    expect(feeds[feeds.length - 1].textContent).toContain('삼성전자')
  })

  it('6) 보유 방어선: 실효선 = exit-lines stop_price · 구성 선은 exit-lines entry_atr(후보 ATR 아님)', () => {
    const positions_detail = {
      '005930': { name: '삼성전자', buy_price: 60000, quantity: 10, high_since_buy: 65000, is_next_day: false },
    }
    // 후보 ATR(9,999)은 쓰지 않는다 — 쓰면 2ATR 하드가 40,002 가 된다
    const targets = {
      '005930': { prev_close: 60000, atr: 9999, stage: 1, ema_s: 0, ema_m: 0, ema_l: 0, atr_ratio: 0.025 },
    }
    const tickerPrices = { '005930': { current_price: 63000, open_price: 62000, change_rate: 0, prdy_ctrt: 0 } }
    const exitLines = [{
      strategy_id: 'kojiro', ticker: '005930', stop_price: 61250, stop_source: 'effective', target_price: null,
      target_source: null, buy_price: 60000, quantity: 10, high_since_buy: 65000, buy_date: '2026-10-06',
      order_no: 'O-1', entry_atr: 1500, kk_armed: null, kk_arm_price: null,
    }]
    render(
      <KojiroMonitor strategies={makeKojiro({ positions_detail, targets })} tickerPrices={tickerPrices}
        exitLines={exitLines as never} />,
    )
    const row = screen.getByTestId('kojiro-defense-005930')
    // 하드 = 60000-2*1500=57000 / 트레일 = 65000-2.5*1500=61250 / backstop = 60000*0.92=55200
    expect(row.textContent).toContain('57,000')
    expect(row.textContent).toContain('61,250')
    expect(row.textContent).toContain('55,200')
    expect(row.textContent).not.toContain('40,002')
    expect(row.textContent).toContain('63,000') // 현재가
  })

  it('6c) 보유가 후보에서 빠져도(targets 없음) exit-lines 실효선은 보인다 · 모르면 「—」', () => {
    const positions_detail = {
      '005930': { name: '삼성전자', buy_price: 60000, quantity: 10, high_since_buy: 65000, is_next_day: false },
      '000660': { name: 'SK하이닉스', buy_price: 100000, quantity: 1, high_since_buy: 100000, is_next_day: false },
    }
    const exitLines = [{
      strategy_id: 'kojiro', ticker: '005930', stop_price: 61250, stop_source: 'effective', target_price: null,
      target_source: null, buy_price: 60000, quantity: 10, high_since_buy: 65000, buy_date: '2026-10-06',
      order_no: 'O-1', entry_atr: 1500, kk_armed: null, kk_arm_price: null,
    }]
    render(<KojiroMonitor strategies={makeKojiro({ positions_detail, targets: {} })} exitLines={exitLines as never} />)
    expect(screen.getByTestId('kojiro-defense-005930').textContent).toContain('61,250')
    expect(screen.getByTestId('kojiro-defense-000660').textContent).toContain('—')
  })

  it('6d) 방어선 머리글 숫자는 params 에서(stop_atr 2.2 · trail_atr 3 · hard_stop_pct -9)', () => {
    const positions_detail = {
      '005930': { name: '삼성전자', buy_price: 60000, quantity: 10, high_since_buy: 65000, is_next_day: false },
    }
    render(<KojiroMonitor strategies={makeKojiro({
      positions_detail,
      params: { stop_atr: 2.2, trail_atr: 3, hard_stop_pct: -9, breakeven_promote_atr: 1.5, atr_ratio_min: 0.01, atr_ratio_max: 0.06 },
    })} />)
    const panel = screen.getByTestId('kojiro-defense-panel').textContent ?? ''
    expect(panel).toMatch(/2\.2\s*ATR/)
    expect(panel).toMatch(/3\s*ATR/)
    expect(panel).toMatch(/-9%|−9%/)
    expect(panel).not.toMatch(/-8%/)
  })

  it('7) 문턱 리터럴 금지 — 밴드 상한·신선도·갭 문턱은 params 값(4.5%·3영업일·≥5%/≤-4% 가 렌더에 없다)', () => {
    render(<KojiroMonitor strategies={makeKojiro({
      params: {
        stop_atr: 2.0, trail_atr: 2.5, hard_stop_pct: -8.0, atr_ratio_min: 0.01, atr_ratio_max: 0.06,
        stage1_freshness: 5, gap_up_skip_pct: 6.5, gap_down_skip_pct: -3.5,
      },
      targets: { '005930': { prev_close: 60000, atr: 1800, stage: 1, ema_s: 61000, ema_m: 60000, ema_l: 59000, atr_ratio: 0.03 } },
    })} />)
    const root = screen.getByTestId('kojiro-monitor').textContent ?? ''
    expect(root).not.toMatch(/4\.5%/)
    expect(root).toMatch(/6\.0%/)
    expect(root).toMatch(/5영업일/)
    expect(root).not.toMatch(/3영업일/)
    expect(root).toMatch(/6\.5%/)
    expect(root).toMatch(/-3\.5%|−3\.5%/)
    expect(root).not.toMatch(/≥5%/)
  })

  it('7b) params 에 밴드 키가 없으면 기본값으로 메우지 않고 「—」', () => {
    render(<KojiroMonitor strategies={makeKojiro({
      params: { stop_atr: 2.0, trail_atr: 2.5, hard_stop_pct: -8.0 },
      targets: { '005930': { prev_close: 60000, atr: 1800, stage: 1, ema_s: 61000, ema_m: 60000, ema_l: 59000, atr_ratio: 0.03 } },
    })} />)
    const grid = screen.getByTestId('kojiro-candidate-grid').textContent ?? ''
    expect(grid).toMatch(/—/)
    expect(grid).not.toMatch(/4\.5%/)
  })

  it('8) 라우트 깔때기가 있으면 엔진 단계 이름·조건을 쓴다', () => {
    const monitor = {
      as_of: '2026-10-12T09:12:03+09:00', running: true,
      strategies: { kojiro: {
        prepare: null, market_unit: null, skips: { known: false }, paused_skips: [], shadow_buys: [], ticks: {},
        candidates: {}, holdings: {}, extra: {},
        funnel: [
          { step_no: 1, step_name: '엔진 1단계 이름', step_conditions: '조건 A', survived_count: 348, excluded_count: 0 },
          { step_no: 99, step_name: '최종 후보', step_conditions: null, survived_count: 3, excluded_count: 0 },
        ],
      } },
    }
    render(<KojiroMonitor strategies={makeKojiro()} monitor={monitor as never} />)
    const funnel = screen.getByTestId('kojiro-scan-funnel').textContent ?? ''
    expect(funnel).toMatch(/엔진 1단계 이름/)
    expect(funnel).toMatch(/조건 A/)
  })

  it('6b) 보유 0건 → 빈 상태', () => {
    render(<KojiroMonitor strategies={makeKojiro()} />)
    expect(screen.getByTestId('kojiro-defense-panel').textContent).toMatch(/보유 종목 없음|관찰 모드/)
  })

  it('stage3 보유 → 청산 경고', () => {
    const positions_detail = {
      '035420': { name: '네이버', buy_price: 40000, quantity: 5, high_since_buy: 42000, is_next_day: false },
    }
    const targets = {
      '035420': { prev_close: 40000, atr: 1200, stage: 3, ema_s: 0, ema_m: 0, ema_l: 0, atr_ratio: 0.03 },
    }
    render(<KojiroMonitor strategies={makeKojiro({ positions_detail, targets })} />)
    expect(screen.getByTestId('kojiro-defense-035420').textContent).toContain('청산')
  })

  // ── 후보 그리드 종목명 (targets.name) ──
  // 현행 KojiroMonitor.tsx:235 = `const name = prices[ticker] ? ticker : ticker` (스텁, 항상 종목번호).
  // 시정 = `const name = t.name || ticker` (매수신호 289 sig.name||sig.ticker / 보유 341 pos.name||ticker 정합).

  it('F1) 후보 그리드: targets.name 있으면 종목명 렌더 (종목번호 아님)', () => {
    const targets = {
      '005930': { name: '삼성전자', prev_close: 60000, atr: 1800, stage: 1, ema_s: 61000, ema_m: 60000, ema_l: 59000, atr_ratio: 0.03 },
    }
    render(<KojiroMonitor strategies={makeKojiro({ targets })} />)
    const row = screen.getByTestId('kojiro-candidate-005930')
    // 첫 <td> = 종목명 셀 (KojiroMonitor.tsx:238). 현행 스텁은 종목번호 렌더 → Red.
    const nameCell = row.querySelector('td')
    expect(nameCell?.textContent).toBe('삼성전자')
  })

  it('F2) 후보 그리드: targets.name 없음/빈문자 → 종목번호 폴백', () => {
    const targets = {
      '000660': { prev_close: 50000, atr: 1500, stage: 2, ema_s: 0, ema_m: 0, ema_l: 0, atr_ratio: 0.03 },
      '035420': { name: '', prev_close: 40000, atr: 1200, stage: 3, ema_s: 0, ema_m: 0, ema_l: 0, atr_ratio: 0.03 },
    }
    render(<KojiroMonitor strategies={makeKojiro({ targets })} />)
    // name 미제공/빈문자 → ticker 폴백 (t.name || ticker).
    expect(screen.getByTestId('kojiro-candidate-000660').querySelector('td')?.textContent).toBe('000660')
    expect(screen.getByTestId('kojiro-candidate-035420').querySelector('td')?.textContent).toBe('035420')
  })

  it('F3) 회귀: name 노출 후에도 EMA 정배열/ATR 밴드 렌더 무회귀', () => {
    const targets = {
      '005930': { name: '삼성전자', prev_close: 60000, atr: 1800, stage: 1, ema_s: 61000, ema_m: 60000, ema_l: 59000, atr_ratio: 0.03 },
    }
    render(<KojiroMonitor strategies={makeKojiro({ targets })} />)
    const row = screen.getByTestId('kojiro-candidate-005930')
    expect(row.textContent).toContain('정배열')  // ema_s>ema_m>ema_l
    expect(row.textContent).toContain('3.0%')     // atr_ratio 3%
    expect(within(row).getByTestId('kojiro-band-marker-005930')).toBeTruthy()
  })
})
