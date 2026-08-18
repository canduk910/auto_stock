/**
 * 2026-08-19 정리 사이클 (①②) — 운영자 노출 부팅 시각 문구 영구 가드 (정적 소스 파싱).
 *
 * > **선례**: `_ast_useQuery_retry_required.test.ts` / `_ast_weight_unit_guard.test.ts`
 * >   (사이클 65 H3 · 사이클 80 hotfix) 의 AST 정적 소스 파싱 패턴 답습.
 *
 * 결함 배경:
 * - `src/engine/scheduler.py:56 TIME_BOOT = time(7, 55)` (사이클 92, 2026-06-10 — KIS 07:50
 *   강제 중단 후 5분 마진). 그러나 프론트 3파일이 **07:50** 을 그대로 안내 중 →
 *   운영자가 보조 계좌 등록/활성화 반영 시각을 5분 이르게 오인.
 * - 시각 문구는 렌더 경로가 조건부(ConfirmModal / 보조 세션 0개 안내)라 렌더 테스트로는
 *   전수 커버가 어렵다 → **정적 소스 가드**가 적합.
 *
 * 요구 행위:
 * - G-BOOT-1: 3 파일 소스에 `07:50` 리터럴 0건.
 * - G-BOOT-2: 3 파일 소스에 `_boot(07:55)` 또는 `부트 07:55` 표기 존재.
 * - G-BOOT-3: `Settings.tsx` 의 일과 시각 안내 줄이 `scheduler.py` 의 `TIME_*` 상수와 전수 정합.
 *
 * ⚠️ 대상 제외: `ScanMonitor.formatRunAt.test.ts` 의 "07:50" 은 테스트 주석의 예시 시각이라
 *    본 가드와 무관 (검사 대상 아님).
 */
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'fs'
import path from 'path'

const COMPONENT_FILES = ['KisAccountPoolCard.tsx', 'KisQuoteAccountsCard.tsx']
const PAGE_FILES = ['Settings.tsx']

function readComponent(filename: string): string {
  return readFileSync(path.join(__dirname, '..', filename), 'utf-8')
}

function readPage(filename: string): string {
  return readFileSync(path.join(__dirname, '..', '..', 'pages', filename), 'utf-8')
}

function readSource(filename: string): string {
  return PAGE_FILES.includes(filename) ? readPage(filename) : readComponent(filename)
}

const TARGETS = [...COMPONENT_FILES, ...PAGE_FILES]

describe('부팅 시각 문구 영구 가드 — 07:50 폐기 / 07:55 정합 (scheduler.TIME_BOOT)', () => {
  it.each(TARGETS)('G-BOOT-1: %s 소스에 `07:50` 리터럴 0건', (filename) => {
    const source = readSource(filename)
    const hits = source
      .split('\n')
      .map((line, idx) => ({ line, no: idx + 1 }))
      .filter(({ line }) => line.includes('07:50'))

    expect(
      hits.map(({ no, line }) => `L${no}: ${line.trim()}`),
      `${filename}: 스테일 부팅 시각 07:50 잔존 — scheduler.py TIME_BOOT = time(7, 55) 정합 위반`,
    ).toEqual([])
  })

  it.each(TARGETS)(
    'G-BOOT-2: %s 소스에 `_boot(07:55)` 또는 `부트 07:55` 표기 존재',
    (filename) => {
      const source = readSource(filename)
      const ok = source.includes('_boot(07:55)') || source.includes('부트 07:55')

      expect(
        ok,
        `${filename}: 부팅 시각 안내 문구 부재 — 운영자에게 반영 시각(07:55)을 알리는 표기 의무`,
      ).toBe(true)
    },
  )

  it('G-BOOT-3: Settings.tsx 일과 시각 안내 줄이 scheduler.py TIME_* 상수와 전수 정합', () => {
    const settings = readPage('Settings.tsx')
    const schedulerSrc = readFileSync(
      path.join(__dirname, '..', '..', '..', '..', 'src', 'engine', 'scheduler.py'),
      'utf-8',
    )

    // scheduler.py 의 `TIME_X = time(h, m[, s])` 파싱 → "HH:MM"
    const pickTime = (name: string): string => {
      const m = schedulerSrc.match(
        new RegExp(`^${name}\\s*=\\s*time\\((\\d+),\\s*(\\d+)`, 'm'),
      )
      expect(m, `scheduler.py 에서 ${name} 상수를 찾지 못함`).toBeTruthy()
      const hh = String(Number(m![1])).padStart(2, '0')
      const mm = String(Number(m![2])).padStart(2, '0')
      return `${hh}:${mm}`
    }

    // Settings.tsx 의 일과 시각 안내 줄 (자동 시작 … 정산)
    const line = settings
      .split('\n')
      .find((l) => l.includes('자동 시작') && l.includes('정산'))
    expect(line, 'Settings.tsx 에서 일과 시각 안내 줄을 찾지 못함').toBeTruthy()

    const expected: Array<[string, string]> = [
      ['자동 시작', pickTime('TIME_AUTO_START')],
      ['부트', pickTime('TIME_BOOT')],
      ['NXT 프리', pickTime('TIME_PRE_NXT_OPEN')],
      ['KRX 메인', pickTime('TIME_KRX_OPEN_CONFIRM')],
      ['KRX 마감', pickTime('TIME_KRX_MAIN_CLOSE')],
      ['NXT 애프터 종료', pickTime('TIME_NXT_POST_CLOSE')],
      ['정산', pickTime('TIME_SETTLEMENT')],
    ]

    const violations = expected
      .filter(([label, hhmm]) => !line!.includes(`${label} ${hhmm}`))
      .map(([label, hhmm]) => `${label} → scheduler 정본 ${hhmm} 표기 부재`)

    expect(
      violations,
      `Settings.tsx 일과 시각 안내가 scheduler.py TIME_* 와 불일치:\n${line!.trim()}`,
    ).toEqual([])
  })
})
