/**
 * cycle423 리팩토링 카드 #5 — Red (프론트 쪽).
 *
 * 정본 = `_workspace/refactor/2026-10-09_review.md` 「카드 #5」. 백엔드 `GET /api/strategies/monitor`
 * 는 이제 `strategy_manifest.MARKET_UNIT_SCALE_IDS`(명부의 `market_unit_policy=="scale"` 파생)로
 * `market_unit` 을 채운다 — 그 집합 밖 전략은 항상 `market_unit: null` 이다(라우트가 유일한 출처).
 *
 * `utils/strategyMonitor.ts::marketUnitEffect` 는 **같은 사실을 `TURTLE_SIDS` 하드코딩 Set 으로
 * 다시 들고 있었다** — 명부에 6번째 "scale" 전략(터틀도 etf_trend 도 아닌)이 들어오면, 라우트는
 * 이미 그 전략의 `market_unit` 을 채워 보내는데도 프론트 목록이 못 따라가 화면에서 조용히
 * 사라진다. 이 테스트는 그 드리프트를 재현한다.
 */
import { describe, expect, it } from 'vitest'

import { marketUnitEffect } from '../strategyMonitor'

describe('카드 #5 — marketUnitEffect 는 하드코딩 목록이 아니라 라우트 응답으로 판정한다', () => {
  it('터틀 4전략·etf_trend 가 아닌 미래 scale 전략도 라우트가 market_unit 을 주면 표시한다', () => {
    // 라우트는 이미 명부 기준으로 이 전략에 market_unit 을 채워 보냈다(= 응답이 그 자체로
    // "적용 대상" 신호다). 프론트가 하드코딩 Set 으로 다시 거르면 이 값이 null 로 떨어진다.
    const effect = marketUnitEffect('mean_reversion_breakout', {
      mode: 'enforce', ok: true, m: 0.5, state: 'up_falling',
    })
    expect(effect).not.toBeNull()
    expect(effect?.blocks).toBe(false)
    expect(effect?.label).toMatch(/×\s*0\.5/)
  })

  it('m=0 ∧ enforce 면 그 신규 전략도 터틀과 같게 차단한다(etf_trend 전용 분기가 아니다)', () => {
    const effect = marketUnitEffect('mean_reversion_breakout', {
      mode: 'enforce', ok: true, m: 0, state: 'down_falling',
    })
    expect(effect?.blocks).toBe(true)
    expect(effect?.label).toMatch(/0배/)
  })
})
