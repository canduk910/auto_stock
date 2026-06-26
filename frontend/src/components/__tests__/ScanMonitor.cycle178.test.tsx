/**
 * 사이클 178 — VB/LTV ScanMonitor 죽은 단계 제거 + universe_candidates 정확 라벨.
 *
 * 사용자 보고 "변동성돌파/롱테일변동성돌파 조건검색 현황이 이상 — 원천 유니버스가
 * 적고, 2/3/4단계가 0인데 5에서 살아남는다." 진단:
 * - price_filtered/mcap_pass/trade_amount_pass = 백엔드 `_empty_scan_stats` 에만 존재,
 *   어디서도 세팅 안 됨(사이클 108 list_by_filter 단일 호출 전환으로 죽은 키) → 항상 0.
 * - universe_candidates = list_by_filter 결과 = 시총+거래대금 컷 *후* (VB/LTV 는 full
 *   universe 라 union(fetch buffer) 무의미) → 사이클 175 'stock_master 원천' 은 오라벨.
 * 시정: VB/LTV STAGES 에서 죽은 단계 제거 + step1 라벨 "시총+거래대금 컷 통과".
 */
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'

const __dirname = dirname(fileURLToPath(import.meta.url))
const src = readFileSync(resolve(__dirname, '../ScanMonitor.tsx'), 'utf-8')

const vbBlock = src.slice(src.indexOf('const VB_STAGES'), src.indexOf('const LTV_STAGES'))
const ltvBlock = src.slice(src.indexOf('const LTV_STAGES'), src.indexOf('const MOMENTUM_STAGES'))

describe('사이클 178 — VB/LTV ScanMonitor 죽은 단계 제거 + 정확 라벨', () => {
  // 주석의 키 언급(제거 설명)은 무관 — 실제 STAGES 항목(key: '...')만 검사
  it('VB_STAGES 에 죽은 단계 항목(key: price_filtered/mcap_pass/trade_amount_pass) 0건', () => {
    expect(vbBlock).not.toMatch(/key:\s*'price_filtered'/)
    expect(vbBlock).not.toMatch(/key:\s*'mcap_pass'/)
    expect(vbBlock).not.toMatch(/key:\s*'trade_amount_pass'/)
  })

  it('LTV_STAGES 에 죽은 단계 항목 0건', () => {
    expect(ltvBlock).not.toMatch(/key:\s*'price_filtered'/)
    expect(ltvBlock).not.toMatch(/key:\s*'mcap_pass'/)
    expect(ltvBlock).not.toMatch(/key:\s*'trade_amount_pass'/)
  })

  it('VB/LTV step1 universe_candidates = "시총+거래대금 컷 통과" 정확 라벨', () => {
    expect(vbBlock).toContain("{ key: 'universe_candidates', label: '시총+거래대금 컷 통과' }")
    expect(ltvBlock).toContain("{ key: 'universe_candidates', label: '시총+거래대금 컷 통과' }")
  })

  it('VB/LTV 단계 수 축소 (8/9 → 5/6, 죽은 단계 제거 반영)', () => {
    const vbKeys = (vbBlock.match(/key:\s*'/g) || []).length
    const ltvKeys = (ltvBlock.match(/key:\s*'/g) || []).length
    expect(vbKeys).toBe(5)   // candidates/filtered/candle/k_value/final
    expect(ltvKeys).toBe(6)  // + consecutive_limit_pass
  })
})
