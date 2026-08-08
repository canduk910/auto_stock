/**
 * 사이클 175 — 대시보드 조건검색 현황(ScanMonitor) ↔ 조건검색 추적(DB funnel) 정합 회귀 가드.
 *
 * 정적 source 검증 (사이클 132 패턴):
 * - donchian/VCP "코스피200+코스닥150 합집합" 단계 = universe_union 키 (필터 전 원천 합집합)
 * - 폐기된 'blng 0/1/3'(거래량순위 API, 사이클 108 폐기) 라벨 0건
 * - VB/LTV/BFB step1 = 'stock_master 원천 유니버스 후보'
 */
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'

const __dirname = dirname(fileURLToPath(import.meta.url))
const src = readFileSync(resolve(__dirname, '../ScanMonitor.tsx'), 'utf-8')

describe('사이클 175 — ScanMonitor scan_stats funnel DB funnel 정합', () => {
  it('donchian 합집합 단계가 universe_union 키 사용 (필터 후 universe_candidates 아님)', () => {
    // [의미 전환 2026-08-08 확대] "코스피200+코스닥150 합집합" 라벨은 이제 SWING(donchian)
    // 만 사용 (donchian 은 지수 전용 유지). VCP 는 확대로 '전체 상장 유니버스 (필터 전)' 전환.
    const matches = src.match(/key:\s*'universe_union',\s*label:\s*'코스피200\+코스닥150 합집합'/g) || []
    expect(matches.length).toBe(1)
  })

  it('폐기된 blng 0/1/3 라벨 0건 (사이클 108 거래량순위 API 폐기)', () => {
    expect(src).not.toContain('blng 0/1/3')
  })

  it('사이클 178 의미 전환 — VB/LTV/BFB 의 "stock_master 원천 유니버스 후보" 오라벨 제거됨', () => {
    // 사이클 175 는 VB/LTV/BFB step1 을 "stock_master 원천 유니버스 후보" 로 라벨했으나,
    // VB/LTV/BFB 는 full universe 라 universe_candidates = list_by_filter 결과(시총+거래대금
    // 컷 *후*) → '원천' 은 오라벨. 사이클 178 에서 "시총+거래대금 컷 통과" 로 시정.
    expect(src).not.toContain('원천 유니버스 후보')
  })

  it('donchian 시총 단계 라벨이 시총+거래대금 컷 통과로 정합', () => {
    expect(src).toContain('시총+거래대금 컷 통과')
  })
})
