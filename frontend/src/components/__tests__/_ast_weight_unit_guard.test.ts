/**
 * 전략 비중 단위 추론 휴리스틱 영구 차단 (2026-08-18) — 정적 소스 AST 가드.
 *
 * > **선례**: `_ast_useQuery_retry_required.test.ts` 정적 소스 파싱 관례 답습.
 * > **결함 배경**: `Settings.tsx` 의 로드 휴리스틱
 * >   `totalW <= 1.01 ? Math.round(s.weight * 100) : Math.round(s.weight)` 가
 * >   **합계 크기로 단위를 추측**했다. 백엔드가 1%를 비율 1.0 으로 잘못 저장해 Σ=2.98 이 되면
 * >   이 분기가 깨어나 유효숫자를 파괴(0.60→1, 0.18→0)하고 상대 정규화가 그것을
 * >   "3개 전략 33% 균등분배" 화면으로 **위장**한다 — 운영자가 오염을 볼 수 없었다.
 * >   백엔드 계약이 비율(0~1) 단일 단위로 확정되었으므로 추론 분기는 영구 금지.
 *
 * 요구 행위:
 * - `Settings.tsx` 소스에 `1.01` 리터럴 0건 (합계 기반 단위 추론 임계).
 * - `Settings.tsx` 소스에 `Math.round(s.weight)` (뒤에 `* 100` 없는 형태) 0건.
 *
 * 위험 등급 HIGH — 오염 위장 화면 재발 = 운영자가 잘못된 비중을 그대로 저장.
 */
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'fs'
import path from 'path'

const SETTINGS_PATH = path.join(__dirname, '..', '..', 'pages', 'Settings.tsx')

describe('전략 비중 단위 추론 휴리스틱 영구 차단 (2026-08-18)', () => {
  it('Settings.tsx 에 합계 기반 단위 추론 임계 `1.01` 리터럴 0건', () => {
    const source = readFileSync(SETTINGS_PATH, 'utf-8')
    const hits = [...source.matchAll(/1\.01/g)]
    expect(
      hits.length,
      'Settings.tsx 에 `1.01` 잔존 — 합계 크기로 단위를 추측하는 휴리스틱 부활 의심. ' +
        '백엔드 계약은 비율(0~1) 단일 단위이므로 분기 없이 `weight * 100` 으로 표시해야 한다.',
    ).toBe(0)
  })

  it('Settings.tsx 에 `Math.round(s.weight)` (× 100 없는 형태) 0건', () => {
    const source = readFileSync(SETTINGS_PATH, 'utf-8')
    // `Math.round(s.weight * 100)` 은 정상 — 인자가 s.weight 단독인 형태만 위반.
    const hits = [...source.matchAll(/Math\.round\(\s*s\.weight\s*\)/g)]
    expect(
      hits.length,
      'Settings.tsx 에 `Math.round(s.weight)` 잔존 — 비율(0~1)을 퍼센트로 오인해 ' +
        '0.60→1 / 0.18→0 으로 유효숫자를 파괴하는 오염 위장 경로. ' +
        '`Math.round(s.weight * 100)` 만 허용.',
    ).toBe(0)
  })
})
