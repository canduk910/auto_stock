/**
 * cycle395 — 전략 표시명 중앙 정본(utils/strategyMeta.ts) 단위 가드.
 *
 * 배경: 사용자 요청(10-02) "모든 전략명을 한글로 보여지도록 통일해줘" — 화면마다 전략명이
 * 제각각이던 것(백엔드 API name 그대로 노출 / 컴포넌트별 로컬 STRATEGY_NAMES 사본 간 표기
 * 불일치 / 일부 화면은 id 원문 노출)을 `strategyLabel()` 한 함수로 통일한다.
 *
 * 표시명 정본(사용자 09-27 확정 3개 + 기존 4개, 10-02 전수 통일):
 *   momentum=모멘텀 · volatility_breakout=변동성 돌파 · long_tail_volatility=롱테일 변동성 ·
 *   donchian_swing=돈키언 추세 스윙 · bull_flag_breakout=추세 눌림목 돌파 ·
 *   vcp_breakout=VCP 변동성 수축 · kojiro=고지로 대순환
 */
import { describe, expect, it } from 'vitest'
import { STRATEGY_DISPLAY_NAMES, strategyLabel } from '../strategyMeta'

describe('strategyMeta — STRATEGY_DISPLAY_NAMES 정본 7종', () => {
  it('7 전략 표시명이 정본 표와 정확히 일치한다', () => {
    expect(STRATEGY_DISPLAY_NAMES).toEqual({
      momentum: '모멘텀',
      volatility_breakout: '변동성 돌파',
      long_tail_volatility: '롱테일 변동성',
      donchian_swing: '돈키언 추세 스윙',
      bull_flag_breakout: '추세 눌림목 돌파',
      vcp_breakout: 'VCP 변동성 수축',
      kojiro: '고지로 대순환',
    })
  })
})

describe('strategyMeta — strategyLabel()', () => {
  it('7 전략 id → 정본 한글 표시명', () => {
    expect(strategyLabel('momentum')).toBe('모멘텀')
    expect(strategyLabel('volatility_breakout')).toBe('변동성 돌파')
    expect(strategyLabel('long_tail_volatility')).toBe('롱테일 변동성')
    expect(strategyLabel('donchian_swing')).toBe('돈키언 추세 스윙')
    expect(strategyLabel('bull_flag_breakout')).toBe('추세 눌림목 돌파')
    expect(strategyLabel('vcp_breakout')).toBe('VCP 변동성 수축')
    expect(strategyLabel('kojiro')).toBe('고지로 대순환')
  })

  it('7 전략은 API 가 다른 이름을 줘도 정본이 우선한다 (백엔드 name 무시)', () => {
    expect(strategyLabel('momentum', '상한가 모멘텀')).toBe('모멘텀')
    expect(strategyLabel('donchian_swing', '20일 신고가 스윙')).toBe('돈키언 추세 스윙')
    expect(strategyLabel('bull_flag_breakout', '눌림목 돌파')).toBe('추세 눌림목 돌파')
    expect(strategyLabel('vcp_breakout', 'VCP 돌파')).toBe('VCP 변동성 수축')
  })

  it('정본에 없는(신규) 전략 id 는 API 가 준 이름을 그대로 쓴다', () => {
    expect(strategyLabel('new_strategy_x', '신규 전략 X')).toBe('신규 전략 X')
  })

  it('정본에 없는 id + API 이름도 없으면 id 원문을 그대로 돌려준다', () => {
    expect(strategyLabel('new_strategy_x')).toBe('new_strategy_x')
    expect(strategyLabel('new_strategy_x', null)).toBe('new_strategy_x')
  })
})
