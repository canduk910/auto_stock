/**
 * 사이클 132 (2026-06-15) — StrategyFunnel.tsx 휴장일 UI 안내 + 전략별 funnel 정책 안내 영역 격리 가드.
 *
 * 배경 (사용자 결정 영속):
 * - Q2=C momentum funnel 영구 제외 + UI 안내 동행
 * - Q3=A 휴장일 UI 안내 추가
 * - Q4=A TDD 사이클 (Red → Green → verify)
 *
 * 회귀 가드 5 케이스 (사이클 129 정적 source 영역 검증 패턴 답습):
 * - G-FE-132-A: 휴장일 amber 배너 testid 영속
 * - G-FE-132-B: holiday_note testid 영속
 * - G-FE-132-C: 전략별 funnel 정책 안내 영역 영속 (momentum / VB / LTV)
 * - G-FE-132-D: FunnelResponse interface 영구 영속 확장 (is_business_day + holiday_note)
 * - G-FE-132-E: 안내 메시지 한글 친숙 용어 영속 (사이클 89 답습)
 */
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'

const __dirname = dirname(fileURLToPath(import.meta.url))
const STRATEGY_FUNNEL_SRC_PATH = resolve(__dirname, '..', 'StrategyFunnel.tsx')
const FUNNEL_API_SRC_PATH = resolve(__dirname, '..', '..', 'api', 'strategy-funnel.ts')
const STRATEGY_META_SRC_PATH = resolve(__dirname, '..', '..', 'utils', 'strategyMeta.ts')

describe('사이클 132 — StrategyFunnel 휴장일 안내 + 정책 안내 영역', () => {
  const src = readFileSync(STRATEGY_FUNNEL_SRC_PATH, 'utf-8')
  const apiSrc = readFileSync(FUNNEL_API_SRC_PATH, 'utf-8')

  it('G-FE-132-A: 휴장일 amber 배너 testid + 분기 영속 (Q3=A)', () => {
    // strategy-funnel-holiday-banner testid 영구 영속 의무
    expect(src.includes('strategy-funnel-holiday-banner')).toBe(true)
    // is_business_day === false 분기 영속 의무
    expect(src.includes('is_business_day === false')).toBe(true)
    // amber 톤 클래스 영속 의무 (사이클 64 답습)
    expect(src.includes('bg-amber-50')).toBe(true)
    expect(src.includes('border-amber-200')).toBe(true)
  })

  it('G-FE-132-B: holiday_note testid 영속 + data 영역 참조', () => {
    // strategy-funnel-holiday-note testid 영구 영속 의무
    expect(src.includes('strategy-funnel-holiday-note')).toBe(true)
    // data.holiday_note 영역 참조 영속 의무
    expect(src.includes('data.holiday_note')).toBe(true)
  })

  it('G-FE-132-C: 전략별 funnel 정책 안내 영역 영속 (momentum 영속 / 사이클 143 VB-LTV 정상 활성화 후 영구 제거)', () => {
    // 사이클 143 (2026-06-15) 의미 전환 (사이클 66 K-2 패턴 답습):
    // VB/LTV 안내 메시지 "단계별 funnel 후속 사이클 영역 (사이클 133 인계)" 영역 영구 제거
    // = VB 5단계 + LTV 6단계 funnel hook 정상 활성화 영구 영속.
    // momentum 안내 영속 (Q2=C 영속, 사이클 132 영역 영구 영속 = 실시간 본질 영역 영구 영속).

    // strategy-funnel-policy-notice 카드 영속 의무
    expect(src.includes('strategy-funnel-policy-notice')).toBe(true)
    // momentum 안내 영속 의무 (Q2=C 영속, 사이클 132 영역 영구 영속)
    expect(src.includes('strategy-funnel-notice-momentum')).toBe(true)
    expect(src.includes('실시간 돌파 기반')).toBe(true)
    expect(src.includes('funnel 적재 미적용')).toBe(true)
    // 사이클 143 의미 전환 — VB/LTV 안내 영역 영구 제거 영속 의무
    expect(src.includes('strategy-funnel-notice-vb-ltv')).toBe(false)
    expect(src.includes('사이클 133 인계')).toBe(false)
  })

  it('G-FE-132-D: FunnelResponse interface 영구 영속 확장 (is_business_day + holiday_note)', () => {
    // api/strategy-funnel.ts FunnelResponse interface 영구 영속 확장 의무
    expect(apiSrc.includes('is_business_day?: boolean')).toBe(true)
    expect(apiSrc.includes('holiday_note?: string | null')).toBe(true)
    // 사이클 132 docstring 영속 의무
    expect(apiSrc.includes('사이클 132')).toBe(true)
  })

  it('G-FE-132-E: 안내 메시지 한글 친숙 용어 영속 (사이클 89 답습)', () => {
    // "휴장일 안내" 영구 영속 의무 (사이클 89 한글 친숙 용어 영속)
    expect(src.includes('휴장일 안내')).toBe(true)
    // 전략 안내 문구 ("모멘텀" 은 사이클 132 정책 안내 문구에 직접 박혀 있다 — 유지)
    expect(src.includes('모멘텀')).toBe(true)
    // cycle395 — 전략 선택지 한글 표시명은 utils/strategyMeta.ts 중앙 정본(strategyLabel)을
    // 거치므로 StrategyFunnel.tsx 소스에는 더 이상 각 라벨 리터럴이 박혀 있지 않다.
    // 정본 파일 쪽에 그 값이 있는지로 검증한다.
    expect(src.includes("from '../utils/strategyMeta'")).toBe(true)
    const metaSrc = readFileSync(STRATEGY_META_SRC_PATH, 'utf-8')
    expect(metaSrc.includes('변동성 돌파')).toBe(true)
    expect(metaSrc.includes('롱테일 변동성')).toBe(true)
  })
})
