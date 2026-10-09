/**
 * cycle414 보완 1차 Red — M1: 시장 유닛 판정 순수 함수(`src/utils/strategyMonitor.ts`).
 *
 * 엔진 정본(`src/engine/strategy_base.py::_market_unit_view`):
 *   - mode off(또는 모양 오류) → `m=1.0`
 *   - 오늘 스냅샷 없음(`snap is None`) → `MarketUnitView(mode, m=1.0, state="unavailable", reason="not_computed")`
 *   - 스냅샷 `ok=False` → `m=1.0, state="unavailable"`
 * 터틀 4전략은 이 view 의 `m` 으로 `_market_unit_blocks_entry` 를 판정하므로 **enforce + 결손 = m=1 = 차단 아님**.
 * etf_trend 만 `check_buy_signal` 이 `view.state == "unavailable"` 를 직접 보고 거른다(`etf_trend.py`
 * `if view.mode != "off": if view.state == "unavailable": … market_unit_unavailable`) — shadow·enforce 둘 다 차단.
 *
 * 1차 결함 = `marketUnitEffect(turtle, {mode:'enforce', ok:false})` 가 `{blocks:true, '…미계산 — 차단'}` 이었다.
 */
import { describe, expect, it } from 'vitest'

import { marketUnitBlockLabel, marketUnitEffect } from '../strategyMonitor'

const TURTLE = ['kojiro', 'donchian_swing', 'vcp_breakout', 'bull_flag_breakout'] as const
const NOT_COMPUTED = { mode: 'enforce', ok: false, reason: 'not_computed' }
const SNAP_NOT_OK = { mode: 'enforce', ok: false, reason: 'stale_head' }

describe('M1 — 터틀 4전략 enforce + 스냅샷 결손 = 엔진 m=1(차단 아님)', () => {
  it.each(TURTLE)('%s enforce·스냅샷 없음 → blocks=false · 문구에 「m=1」 또는 「차단 아님」', (sid) => {
    const eff = marketUnitEffect(sid, NOT_COMPUTED)
    expect(eff?.blocks).toBe(false)
    expect(eff?.label).toMatch(/미계산/)
    expect(eff?.label).toMatch(/m=1|차단 아님/)
  })

  it.each(TURTLE)('%s enforce·스냅샷 ok=false → blocks=false', (sid) => {
    expect(marketUnitEffect(sid, SNAP_NOT_OK)?.blocks).toBe(false)
  })

  it.each(TURTLE)('%s enforce·결손 → marketUnitBlockLabel = null(후보 상태·요약표 「왜 안 사나」 로 번지지 않는다)', (sid) => {
    expect(marketUnitBlockLabel(sid, NOT_COMPUTED)).toBeNull()
  })

  it('etf_trend 는 enforce·결손이면 그대로 차단(엔진이 state=unavailable 을 직접 거른다)', () => {
    expect(marketUnitEffect('etf_trend', NOT_COMPUTED)?.blocks).toBe(true)
    expect(marketUnitBlockLabel('etf_trend', NOT_COMPUTED)).toMatch(/시장 유닛 미계산/)
  })
})
