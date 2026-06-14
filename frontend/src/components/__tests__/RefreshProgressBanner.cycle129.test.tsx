/**
 * 사이클 129 — RefreshProgressBanner TaskKey "master" 자동 흡수 Red 회귀 가드.
 *
 * 배경:
 * - 사이클 127 RefreshProgressBanner 동적 폴링 패턴 답습
 * - TaskKey 4 확장 (universe / basics / daily / master) 자동 흡수
 *
 * 회귀 가드 2 케이스:
 * - G-FE-RPB-M1: TASK_ORDER 영역 'master' 포함 영속 (소스 정적 검증)
 * - G-FE-RPB-M2: TASK_LABELS 영역 'master' 한글 라벨 영속
 */
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'

const __dirname = dirname(fileURLToPath(import.meta.url))
const BANNER_SRC_PATH = resolve(
  __dirname,
  '..',
  'RefreshProgressBanner.tsx'
)

describe('사이클 129 — RefreshProgressBanner TaskKey master 영역 (Red)', () => {
  const src = readFileSync(BANNER_SRC_PATH, 'utf-8')

  it("G-FE-RPB-M1: TASK_ORDER 영역 'master' 포함 영속", () => {
    // TASK_ORDER 영역 = ['universe', 'basics', 'daily', 'master'] 의무
    expect(src.includes('TASK_ORDER')).toBe(true)
    // master 키 포함 영속 의무
    const taskOrderMatch = src.match(/TASK_ORDER[^=]*=\s*\[([^\]]+)\]/m)
    expect(taskOrderMatch).not.toBeNull()
    if (taskOrderMatch) {
      expect(taskOrderMatch[1]).toContain('master')
    }
  })

  it("G-FE-RPB-M2: TASK_LABELS 영역 'master' 한글 라벨 영속", () => {
    // TASK_LABELS 영역 매핑 = master: '마스터 ...' 의무 (사이클 89 한글 친숙 용어)
    expect(src.includes('TASK_LABELS')).toBe(true)
    // master 키 매핑 존재 영속 의무
    expect(src.includes('master:')).toBe(true)
  })
})
