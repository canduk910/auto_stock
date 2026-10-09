/**
 * cycle418-M Red — 전략 진행상황 화면 잔여 LOW 결함 중 순수 함수 경계값 테스트.
 *
 * 대상 함수(`src/utils/strategyMonitor.ts`에 추가):
 *  - `skipReasonLabel(reason)` — L3: `latch_released:<reason>` 접두 키 번역 + 그 밖 사유는 그대로
 *  - `entryWindow` — L14: `entry_start > entry_end`(잘못 뒤집힌 설정)는 추측하지 않고 `null`
 *  - `donchianTimeExitState(...)` — L15: `max_hold_bars` 도달은 `+1R` 면제보다 우선한다
 *    (엔진 `check_force_clear`: (a) bars≥kk_time_exit_bars−1 ∧ R 미도달, 또는 (b) bars≥kk_max_hold_bars−1
 *    이면 TIME_EXIT — (b)는 R 과 무관하다)
 *  - `trendDateLabel(dateStr, totalCols)` — N4-1: 칸이 많으면(≥11) 날짜를 일(DD)만
 *  - `momentumExcludedStageText(prevSurvived, excluded)` — N-E: `limit_up_excluded` 는 "제외 수"라
 *    통과 수로 그대로 늘어놓으면 깔때기 숫자가 늘었다 줄었다 한다
 */
import { describe, expect, it } from 'vitest'

import {
  skipReasonLabel, entryWindow, donchianTimeExitState, trendDateLabel, momentumExcludedStageText,
} from '../strategyMonitor'

describe('skipReasonLabel — L3 latch_released:* 접두 키 번역', () => {
  it('정확히 일치하는 사유는 SKIP_REASON_LABELS 그대로', () => {
    expect(skipReasonLabel('no_data')).toBe('거래량 미관측')
  })

  it('latch_released:level_moved → 번역된 한글(레벨 이동)', () => {
    const label = skipReasonLabel('latch_released:level_moved')
    expect(label).not.toBe('latch_released:level_moved')
    expect(label).toMatch(/래치 해제/)
    expect(label).toMatch(/레벨|이동/)
  })

  it('latch_released:stop_line → 번역된 한글(손절선)', () => {
    const label = skipReasonLabel('latch_released:stop_line')
    expect(label).not.toBe('latch_released:stop_line')
    expect(label).toMatch(/래치 해제/)
    expect(label).toMatch(/손절선/)
  })

  it('모르는 사유는 원문을 그대로 둔다(추측 금지)', () => {
    expect(skipReasonLabel('ext_cap_warn')).toBe('ext_cap_warn')
  })
})

describe('entryWindow — L14 시작>끝 설정은 null(추측 금지)', () => {
  const now = new Date('2026-10-12T09:12:00+09:00')

  it('entry_start > entry_end(뒤집힌 설정) → null', () => {
    const win = entryWindow('vcp_breakout', { entry_start: '14:30', entry_end: '09:05' }, now)
    expect(win).toBeNull()
  })

  it('정상 설정(start < end)은 그대로 판정', () => {
    const win = entryWindow('vcp_breakout', { entry_start: '09:05', entry_end: '14:30' }, now)
    expect(win?.state).toBe('open')
  })
})

describe('donchianTimeExitState — L15 max_hold_bars 는 +1R 면제보다 우선', () => {
  it('+1R 도달 ∧ daysHeld 가 max_hold_bars−1 이상 → 면제가 아니라 시간청산 대상', () => {
    const r = donchianTimeExitState({ daysHeld: 249, timeExitBars: 20, maxHoldBars: 250, reachedR1: true })
    expect(r.kind).toBe('max_hold_due')
  })

  it('+1R 도달 ∧ max_hold 미도달 → 면제', () => {
    const r = donchianTimeExitState({ daysHeld: 10, timeExitBars: 20, maxHoldBars: 250, reachedR1: true })
    expect(r.kind).toBe('exempt')
  })

  it('+1R 미도달 ∧ daysHeld ≥ timeExitBars−1 → 오늘 시간청산 대상', () => {
    const r = donchianTimeExitState({ daysHeld: 19, timeExitBars: 20, maxHoldBars: 250, reachedR1: false })
    expect(r.kind).toBe('due_today')
  })

  it('+1R 미도달 ∧ 아직 남음 → n영업일 뒤', () => {
    const r = donchianTimeExitState({ daysHeld: 10, timeExitBars: 20, maxHoldBars: 250, reachedR1: false })
    expect(r.kind).toBe('pending')
    expect(r.dueInDays).toBe(9)
  })

  it('timeExitBars·daysHeld 모름 → 모름', () => {
    const r = donchianTimeExitState({ daysHeld: null, timeExitBars: null, maxHoldBars: 250, reachedR1: false })
    expect(r.kind).toBe('unknown')
  })

  it('maxHoldBars 모름이어도 timeExitBars 판정은 그대로 작동한다', () => {
    const r = donchianTimeExitState({ daysHeld: 19, timeExitBars: 20, maxHoldBars: null, reachedR1: false })
    expect(r.kind).toBe('due_today')
  })
})

describe('trendDateLabel — N4-1 칸이 많으면 일(DD)만', () => {
  it('10칸(경계 아래) → MM-DD 그대로', () => {
    expect(trendDateLabel('2026-10-07', 10)).toBe('10-07')
  })

  it('11칸(경계) → 일(DD)만', () => {
    expect(trendDateLabel('2026-10-07', 11)).toBe('07')
  })

  it('14칸 → 일(DD)만', () => {
    expect(trendDateLabel('2026-10-07', 14)).toBe('07')
  })

  it('빈 문자열·짧은 문자열은 원문을 그대로 둔다', () => {
    expect(trendDateLabel('', 14)).toBe('—')
  })
})

describe('momentumExcludedStageText — N-E limit_up_excluded 는 제외 수다(통과 수 아님)', () => {
  it('직전 단계 50 · 제외 3 → 통과 47 + 제외 3건 병기', () => {
    const r = momentumExcludedStageText(50, 3)
    expect(r.survived).toBe(47)
    expect(r.excluded).toBe(3)
  })

  it('직전 단계 모름 → 통과도 모름(제외 수는 그대로)', () => {
    const r = momentumExcludedStageText(null, 3)
    expect(r.survived).toBeNull()
    expect(r.excluded).toBe(3)
  })
})
