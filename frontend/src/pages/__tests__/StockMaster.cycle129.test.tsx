/**
 * 사이클 129 — StockMaster.tsx 4번째 새로고침 버튼 + FIELD_LABELS 영역 Red 회귀 가드.
 *
 * 배경:
 * - 사용자 결정 Q4=A 마스터 우선 + Q6=C master_raw 별도 컬럼
 * - 사이클 124 영역 답습 (FIELD_LABELS + CATEGORY_KEYS + HIGHLIGHT_KEYS)
 * - 사이클 126 영역 답습 (3 새로고침 버튼 → 4 확장)
 *
 * 회귀 가드 3 케이스 (정적 source 영역 검증 패턴 답습):
 * - G-FE-MS1: 4번째 새로고침 버튼 "마스터 새로고침" testid + 라벨 영속
 * - G-FE-MS2: refreshMasterNow API 영역 영속
 * - G-FE-MS3: FIELD_LABELS master_raw 1단계 차단 7건 + 핵심 키 한글 라벨 영속
 */
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'

const __dirname = dirname(fileURLToPath(import.meta.url))
const STOCKMASTER_SRC_PATH = resolve(__dirname, '..', 'StockMaster.tsx')

describe('사이클 129 — StockMaster 마스터 새로고침 영역 (Red)', () => {
  const src = readFileSync(STOCKMASTER_SRC_PATH, 'utf-8')

  it('G-FE-MS1: 4번째 새로고침 버튼 "마스터 새로고침" testid 영속', () => {
    // production 코드 영역 source 영역 직접 정적 검증 의무
    expect(src.includes('stock-master-refresh-master-button')).toBe(true)
    expect(src.includes('마스터 새로고침')).toBe(true)
  })

  it('G-FE-MS2: refreshMasterNow API 영역 영속 (4번째 mutation)', async () => {
    // refreshMasterMutation 호출 시 POST /api/stock-master/master/refresh 영역 영속 의무
    const apiModule = await import('../../api/stock-master')
    expect(typeof (apiModule as Record<string, unknown>).refreshMasterNow).toBe(
      'function'
    )
  })

  it('G-FE-MS3: FIELD_LABELS master_raw 1단계 차단 7건 + 핵심 키 한글 라벨 영속', () => {
    // FIELD_LABELS 영역에 1단계 차단 7건 + prdy_avls_scal/lstn_stcn/roe 키 영속
    const expectedLabelKeys = [
      'trht_yn',
      'sltr_yn',
      'mang_issu_yn',
      'ssts_hot_yn',
      'stange_runup_yn',
      'mrkt_alrm_cls_code',
      'invt_alrm_yn',
      'prdy_avls_scal',
      'lstn_stcn',
      'roe',
    ]

    for (const key of expectedLabelKeys) {
      expect(src.includes(key)).toBe(true)
    }
  })
})
