/**
 * 사이클 171 (2026-06-22) — StrategyFunnel.tsx 잠정(provisional) 배지 + 타입 영속 가드.
 *
 * 배경 (자문 cycle171 의제 4 우선순위 2 + 의제 9 반례 3):
 * - 16:20 저녁 잠정 funnel 캡처 (is_provisional=true) → 운영자 밤 후보 확인.
 * - "저녁에 본 후보" 와 "아침 확정 후보" 가 다를 수 있어 UI 에 "잠정/확정" 명시 필요.
 *
 * 회귀 가드 (사이클 132 정적 source 검증 패턴 답습):
 * - G-FE-171-A: FunnelSnapshot interface is_provisional 필드 영속
 * - G-FE-171-B: StrategyFunnel.tsx 잠정 배지 testid + is_provisional 분기 영속
 * - G-FE-171-C: 잠정 배지 amber 톤 + 한글 "잠정" 라벨 영속 (사이클 89 답습)
 */
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'

const __dirname = dirname(fileURLToPath(import.meta.url))
const STRATEGY_FUNNEL_SRC_PATH = resolve(__dirname, '..', 'StrategyFunnel.tsx')
const FUNNEL_API_SRC_PATH = resolve(__dirname, '..', '..', 'api', 'strategy-funnel.ts')

describe('사이클 171 — StrategyFunnel 잠정 배지', () => {
  const src = readFileSync(STRATEGY_FUNNEL_SRC_PATH, 'utf-8')
  const apiSrc = readFileSync(FUNNEL_API_SRC_PATH, 'utf-8')

  it('G-FE-171-A: FunnelSnapshot interface is_provisional 필드 영속', () => {
    expect(apiSrc.includes('is_provisional')).toBe(true)
  })

  it('G-FE-171-B: 잠정 배지 testid + is_provisional 분기 영속', () => {
    expect(src.includes('funnel-provisional-badge')).toBe(true)
    expect(src.includes('is_provisional')).toBe(true)
  })

  it('G-FE-171-C: 잠정 배지 amber 톤 + 한글 "잠정" 라벨 영속', () => {
    expect(src.includes('잠정')).toBe(true)
    // amber 톤 클래스 (사이클 132 휴장일 배너 답습)
    expect(src.includes('amber')).toBe(true)
  })
})
