/**
 * cycle414 Red — 전략 진행상황 판정 순수 함수(`src/utils/strategyMonitor.ts`).
 *
 * 명세 = `_workspace/red/cycle414/monitor_spec.md` §2.2(상태 배지) · §2.3(진입창) · §2.4(시장 유닛) ·
 * §2.5(병목) · §2.8(진입 기록 기준선 정규화) · §8.1 F1·F3(시장 유닛 부분)·F6·F7·F9.
 *
 * 계약(Green 이 만들 export):
 *
 * ```ts
 * strategyStatus(sid: string, info: StrategyInfo, marketUnit?: MonitorMarketUnit | null): {
 *   primary: 'off' | 'paused' | 'shadow' | 'live'
 *   label: string                       // 주 배지 문구
 *   chips: Array<{ kind: 'off_with_holdings' | 'paused_shadow' | 'paused_config_invalid' | 'shadow_config_invalid'
 *                       | 'zero_budget' | 'buy_disabled' | 'max_positions' | 'market_unit'
 *                  label: string; tone: 'red' | 'orange' | 'gray' | 'violet' }>
 * }
 * marketUnitEffect(sid: string, mu: MonitorMarketUnit | null | undefined): { blocks: boolean; label: string } | null
 * funnelBottleneck(steps: Array<{ step_no: number; survived_count: number }>): number | null   // 처음 0 인 step_no
 * entryWindow(sid: string, params: Record<string, unknown> | undefined, now: Date):
 *   { state: 'before' | 'open' | 'after'; start: string; end: string; fixed: boolean } | null
 * signalBaseline(sid: string, sig: Record<string, unknown>): { baseline: number | null; changeRate: number | null }
 * ```
 *
 * `MonitorMarketUnit`(라우트 `market_unit`, `src/types/` 에 둔다) = `{ mode: string; ok: boolean; m?: number;
 * state?: string; bar_date?: string | null; reason?: string }` — `ok=false` 이면 `m`·`state` 가 없다.
 *
 * 🔴 엔진과 같게 **`=== true` 일 때만** 켜짐(`strategy_base.py` `_buy_paused_blocked`·`shadow_mode_on` 의 `is True`).
 * `"true"`·`1` 은 「멈춤」·「섀도」가 **아니라** 설정 모양 오류다 — 엔진은 그 값을 꺼짐으로 읽는다.
 */
import { afterAll, beforeAll, describe, expect, it } from 'vitest'

import type { StrategyInfo } from '../../types/trading'

// 프로세스 TZ 를 UTC 로 고정한 **뒤** 동적 import — 모듈 레벨 포맷터·로컬타임 getter 구현이
// 개발 머신(KST)에서만 초록이 되는 구멍을 막는다(가드 설계 금기 · cycle256 F2).
const ORIG_TZ = process.env.TZ
let sm: typeof import('../strategyMonitor')
beforeAll(async () => {
  process.env.TZ = 'UTC'
  sm = await import('../strategyMonitor')
})
afterAll(() => {
  if (ORIG_TZ === undefined) delete process.env.TZ
  else process.env.TZ = ORIG_TZ
})

function info(over: Partial<StrategyInfo> & { params?: Record<string, unknown> } = {}): StrategyInfo {
  return {
    name: 'x', enabled: true, weight: 0.2, positions: 0, pending_buys: 0, position_tickers: [],
    total_investment: 1_000_000, daily_realized_pnl: 0, buy_disabled: false, buy_signals: [],
    positions_detail: {}, pending_buy_tickers: [], params: { max_positions: 4 }, ...over,
  } as StrategyInfo
}

const kinds = (s: { chips: Array<{ kind: string }> }) => s.chips.map((c) => c.kind).sort()
const chip = (s: { chips: Array<{ kind: string; label: string; tone: string }> }, k: string) =>
  s.chips.find((c) => c.kind === k)

describe('strategyStatus — 주 배지(처음 맞는 하나: 꺼짐 → 멈춤 → 섀도 → 실매매) · F1', () => {
  type Row = [boolean, unknown, unknown, 'off' | 'paused' | 'shadow' | 'live']
  const ABSENT = Symbol('absent')
  const rows: Row[] = [
    // enabled, buy_paused, shadow_mode → primary
    [false, true, true, 'off'],
    [false, ABSENT, ABSENT, 'off'],
    [true, true, false, 'paused'],
    [true, true, true, 'paused'],
    [true, false, true, 'shadow'],
    [true, ABSENT, true, 'shadow'],
    [true, 'true', true, 'shadow'],   // 문자열 "true" 는 멈춤이 아니다
    [true, 'true', false, 'live'],
    [true, false, 1, 'live'],         // 숫자 1 은 섀도가 아니다
    [true, ABSENT, ABSENT, 'live'],
    [true, false, false, 'live'],
  ]
  it.each(rows)('enabled=%s buy_paused=%s shadow_mode=%s → %s', (enabled, bp, sh, want) => {
    const params: Record<string, unknown> = { max_positions: 4 }
    if (bp !== ABSENT) params.buy_paused = bp
    if (sh !== ABSENT) params.shadow_mode = sh
    expect(sm.strategyStatus('donchian_swing', info({ enabled, params })).primary).toBe(want)
  })

  it('주 배지 문구', () => {
    expect(sm.strategyStatus('x', info({ enabled: false })).label).toBe('꺼짐')
    expect(sm.strategyStatus('x', info({ params: { buy_paused: true } })).label).toMatch(/신규 매수 멈춤/)
    expect(sm.strategyStatus('x', info({ params: { buy_paused: true } })).label).toMatch(/청산은 작동/)
    expect(sm.strategyStatus('x', info({ weight: 0, params: { shadow_mode: true } })).label).toMatch(/섀도.*주문 없이 기록만/)
    expect(sm.strategyStatus('x', info()).label).toBe('실매매')
  })
})

describe('strategyStatus — 보조 칩 · F1·F2', () => {
  it('꺼짐 + 보유 2 → 빨강 「꺼짐 + 보유 2 — 손절 정지」 (F2)', () => {
    const s = sm.strategyStatus('long_tail_volatility', info({ enabled: false, weight: 0, positions: 2 }))
    const c = chip(s, 'off_with_holdings')
    expect(c, '꺼진 전략의 보유분은 손절·트레일링·15:20 청산이 전부 멈춘다').toBeTruthy()
    expect(c!.tone).toBe('red')
    expect(c!.label).toMatch(/보유 2/)
    expect(c!.label).toMatch(/손절 정지/)
  })

  it('꺼짐 + 보유 0 → 손절 정지 칩 없음', () => {
    expect(chip(sm.strategyStatus('x', info({ enabled: false, positions: 0 })), 'off_with_holdings')).toBeUndefined()
  })

  it('멈춤 + 섀도 → 회색 「섀도 기록도 멈춤」', () => {
    const c = chip(sm.strategyStatus('x', info({ params: { buy_paused: true, shadow_mode: true } })), 'paused_shadow')
    expect(c?.tone).toBe('gray')
    expect(c?.label).toMatch(/섀도 기록도 멈춤/)
  })

  it('buy_paused="true"(문자열) → 빨강 모양 오류 칩 · 엔진은 「멈추지 않음」 으로 읽음', () => {
    const s = sm.strategyStatus('x', info({ params: { buy_paused: 'true' } }))
    const c = chip(s, 'paused_config_invalid')
    expect(c?.tone).toBe('red')
    expect(c?.label).toMatch(/멈춤 설정 모양 오류/)
    expect(c?.label).toMatch(/멈추지 않음/)
  })

  it('buy_paused=1 도 모양 오류 · 부재와 false 는 오류 아님', () => {
    expect(chip(sm.strategyStatus('x', info({ params: { buy_paused: 1 } })), 'paused_config_invalid')).toBeTruthy()
    expect(chip(sm.strategyStatus('x', info({ params: {} })), 'paused_config_invalid')).toBeUndefined()
    expect(chip(sm.strategyStatus('x', info({ params: { buy_paused: false } })), 'paused_config_invalid')).toBeUndefined()
  })

  it('shadow_mode=1 → 빨강 모양 오류 칩 · 엔진은 「실매매」 로 읽음', () => {
    const c = chip(sm.strategyStatus('x', info({ params: { shadow_mode: 1 } })), 'shadow_config_invalid')
    expect(c?.tone).toBe('red')
    expect(c?.label).toMatch(/섀도 설정 모양 오류/)
    expect(c?.label).toMatch(/실매매/)
  })

  it('켜짐 + 비중 0 + 섀도 아님 → 주황 「예산 0」 · 섀도면 없음(섀도는 비중 0 이 정상)', () => {
    const live = chip(sm.strategyStatus('x', info({ weight: 0 })), 'zero_budget')
    expect(live?.tone).toBe('orange')
    expect(live?.label).toMatch(/예산 0/)
    expect(live?.label).toMatch(/투자금 부족/)
    expect(chip(sm.strategyStatus('x', info({ weight: 0, params: { shadow_mode: true } })), 'zero_budget')).toBeUndefined()
    expect(chip(sm.strategyStatus('x', info({ enabled: false, weight: 0 })), 'zero_budget')).toBeUndefined()
  })

  it('buy_disabled → 주황 「매수 중단」', () => {
    const c = chip(sm.strategyStatus('x', info({ buy_disabled: true })), 'buy_disabled')
    expect(c?.tone).toBe('orange')
    expect(c?.label).toMatch(/매수 중단/)
  })

  it('보유 수 ≥ max_positions → 회색 「보유 한도 4/4」', () => {
    const c = chip(sm.strategyStatus('x', info({ positions: 4, params: { max_positions: 4 } })), 'max_positions')
    expect(c?.tone).toBe('gray')
    expect(c?.label).toMatch(/보유 한도 4\s*\/\s*4/)
    expect(chip(sm.strategyStatus('x', info({ positions: 3, params: { max_positions: 4 } })), 'max_positions')).toBeUndefined()
  })

  it('운영 기본 상태(켜짐·멈춤 아님·섀도 아님·비중>0·보유 0) → 칩 0', () => {
    expect(kinds(sm.strategyStatus('x', info()))).toEqual([])
  })

  it('시장 유닛 칩 — 터틀 전략 shadow m=0.75 → 보라 「관찰만」', () => {
    const s = sm.strategyStatus('donchian_swing', info(), { mode: 'shadow', ok: true, m: 0.75, state: 'up_falling' })
    const c = chip(s, 'market_unit')
    expect(c?.tone).toBe('violet')
    expect(c?.label).toMatch(/0\.75/)
    expect(c?.label).toMatch(/관찰만/)
  })
})

describe('marketUnitEffect — 전략마다 뜻이 다르다 · 명세 §2.4 · F3 마지막 줄', () => {
  it('etf_trend: shadow 에서도 m≤0 · 결손이면 사지 않는다(etf_trend.py:184-190)', () => {
    expect(sm.marketUnitEffect('etf_trend', { mode: 'shadow', ok: true, m: 0, state: 'down_falling' })?.blocks).toBe(true)
    const miss = sm.marketUnitEffect('etf_trend', { mode: 'shadow', ok: false, reason: 'not_computed' })
    expect(miss?.blocks).toBe(true)
    expect(miss?.label).toMatch(/미계산/)
    const watch = sm.marketUnitEffect('etf_trend', { mode: 'shadow', ok: true, m: 0.75, state: 'up_falling' })
    expect(watch?.blocks).toBe(false)
    expect(watch?.label).toMatch(/관찰만/)
  })

  it('etf_trend: enforce m<1 → 랏 ×m · m=0 → 차단', () => {
    const half = sm.marketUnitEffect('etf_trend', { mode: 'enforce', ok: true, m: 0.5, state: 'down_rising' })
    expect(half?.blocks).toBe(false)
    expect(half?.label).toMatch(/×\s*0\.5/)
    expect(sm.marketUnitEffect('etf_trend', { mode: 'enforce', ok: true, m: 0, state: 'down_falling' })?.blocks).toBe(true)
  })

  it('같은 입력의 donchian(터틀 4전략) — shadow m=0 은 차단 아님(관찰만)', () => {
    const e = sm.marketUnitEffect('donchian_swing', { mode: 'shadow', ok: true, m: 0, state: 'down_falling' })
    expect(e?.blocks).toBe(false)
    expect(e?.label).toMatch(/관찰만/)
    expect(sm.marketUnitEffect('donchian_swing', { mode: 'shadow', ok: false, reason: 'not_computed' })?.blocks).toBe(false)
  })

  it('터틀 4전략 enforce — m=0 → 「신규 진입 0배」 차단 · m=0.75 → 「랏 ×0.75」', () => {
    for (const sid of ['kojiro', 'donchian_swing', 'vcp_breakout', 'bull_flag_breakout']) {
      const zero = sm.marketUnitEffect(sid, { mode: 'enforce', ok: true, m: 0, state: 'down_falling' })
      expect(zero?.blocks, sid).toBe(true)
      expect(zero?.label, sid).toMatch(/0배/)
      const part = sm.marketUnitEffect(sid, { mode: 'enforce', ok: true, m: 0.75, state: 'up_falling' })
      expect(part?.blocks, sid).toBe(false)
      expect(part?.label, sid).toMatch(/×\s*0\.75/)
    }
  })

  it('off · 값 없음 → null(표시 안 함)', () => {
    expect(sm.marketUnitEffect('etf_trend', { mode: 'off', ok: true, m: 1, state: 'up_rising' })).toBeNull()
    expect(sm.marketUnitEffect('momentum', null)).toBeNull()
  })

  // cycle423 카드 #5 — 대상 판정은 하드코딩 목록이 아니라 응답(`mu` 존재)이다. 실제 라우트는
  // volatility_breakout 에 market_unit 을 절대 보내지 않지만(명부 밖), 응답이 주어지면 그 자체가
  // "적용 대상" 신호라 터틀형으로 판정한다 — `TURTLE_SIDS` 재검증 삭제의 의도된 결과.
  it('카드 #5 — 응답이 주어지면 터틀 4 + etf_trend 밖 sid 도 터틀형으로 판정', () => {
    const eff = sm.marketUnitEffect('volatility_breakout', { mode: 'shadow', ok: true, m: 0, state: 'x' })
    expect(eff?.blocks).toBe(false)
    expect(eff?.label).toMatch(/관찰만/)
  })
})

describe('funnelBottleneck — 위에서 처음 0 이 되는 단계 · F6', () => {
  it('처음 0 인 단계의 step_no(정렬은 step_no 오름차순)', () => {
    expect(sm.funnelBottleneck([
      { step_no: 99, survived_count: 0 }, { step_no: 1, survived_count: 348 }, { step_no: 5, survived_count: 40 },
      { step_no: 8, survived_count: 0 },
    ])).toBe(8)
  })
  it('0 이 없으면 null · 빈 목록 null · 1단계부터 0 이면 1', () => {
    expect(sm.funnelBottleneck([{ step_no: 1, survived_count: 3 }, { step_no: 99, survived_count: 2 }])).toBeNull()
    expect(sm.funnelBottleneck([])).toBeNull()
    expect(sm.funnelBottleneck([{ step_no: 1, survived_count: 0 }, { step_no: 99, survived_count: 0 }])).toBe(1)
  })
})

describe('entryWindow — 진입창(시각 고정, 창 안·밖 두 시각) · F7', () => {
  const at = (hhmm: string) => new Date(`2026-10-12T${hhmm}:00+09:00`)
  it.each([
    ['etf_trend'], ['donchian_swing'], ['kojiro'],
  ])('%s — 09:05~09:30 코드 고정(params 아님)', (sid) => {
    expect(sm.entryWindow(sid, {}, at('09:04'))?.state).toBe('before')
    expect(sm.entryWindow(sid, {}, at('09:05'))?.state).toBe('open')
    expect(sm.entryWindow(sid, {}, at('09:30'))?.state).toBe('open')
    expect(sm.entryWindow(sid, {}, at('09:31'))?.state).toBe('after')
    const w = sm.entryWindow(sid, { entry_start: '10:00', entry_end: '11:00' }, at('09:10'))
    expect(w).toMatchObject({ state: 'open', start: '09:05', end: '09:30', fixed: true })
  })

  it('VCP·BFB — params.entry_start~entry_end', () => {
    const p = { entry_start: '09:05', entry_end: '13:00' }
    expect(sm.entryWindow('bull_flag_breakout', p, at('09:04'))?.state).toBe('before')
    expect(sm.entryWindow('bull_flag_breakout', p, at('13:00'))?.state).toBe('open')
    expect(sm.entryWindow('bull_flag_breakout', p, at('13:01'))?.state).toBe('after')
    expect(sm.entryWindow('vcp_breakout', { entry_start: '09:05', entry_end: '14:30' }, at('14:30'))).toMatchObject({
      state: 'open', start: '09:05', end: '14:30', fixed: false,
    })
  })

  it('VCP·BFB 에 params 가 없으면 null(추측하지 않는다)', () => {
    expect(sm.entryWindow('vcp_breakout', {}, at('10:00'))).toBeNull()
  })

  it('UTC 로 넘겨도 KST 로 판정한다(브라우저 로컬타임 금지)', () => {
    expect(sm.entryWindow('etf_trend', {}, new Date('2026-10-12T00:10:00Z'))?.state).toBe('open') // = KST 09:10
  })
})

describe('signalBaseline — 진입 기록 기준선 정규화 · F9', () => {
  it('전략마다 다른 키를 「기준선」 하나로', () => {
    expect(sm.signalBaseline('etf_trend', { line: 9_950, change_rate: 0 }).baseline).toBe(9_950)
    expect(sm.signalBaseline('donchian_swing', { donchian_high: 49_500, change_rate: 0 }).baseline).toBe(49_500)
    expect(sm.signalBaseline('vcp_breakout', { base_high: 10_000, change_rate: 0 }).baseline).toBe(10_000)
    expect(sm.signalBaseline('bull_flag_breakout', { flag_high: 10_200, target_price: 11_600, change_rate: 0 }).baseline)
      .toBe(10_200)
    expect(sm.signalBaseline('volatility_breakout', { target_price: 10_500, change_rate: 4.2 }).baseline).toBe(10_500)
    expect(sm.signalBaseline('kojiro', { stage: 1, change_rate: 0 }).baseline).toBeNull()
  })

  it('change_rate 를 0 으로 채우는 전략(etf·donchian·VCP·BFB·kojiro)은 전일 대비를 모른다 → null(「+0%」 거짓 표기 금지)', () => {
    for (const sid of ['etf_trend', 'donchian_swing', 'vcp_breakout', 'bull_flag_breakout', 'kojiro']) {
      expect(sm.signalBaseline(sid, { change_rate: 0 }).changeRate, sid).toBeNull()
    }
    expect(sm.signalBaseline('volatility_breakout', { target_price: 1, change_rate: 4.2 }).changeRate).toBe(4.2)
  })
})
