/**
 * cycle278 Red — 프론트 파라미터 키 하드코딩 0건 영구 가드 (명세 C35 · C36 · C41 · §7.2 F37).
 *
 * 왜 이 가드가 이 사이클의 핵심인가 —
 * 화면이 파라미터 키를 자기 안에 적어 두면 백엔드가 키를 늘려도 화면은 모른다. 실제로
 * base(34ba9e6) 의 `Settings.tsx` 는 `utils/paramLabels.ts` 의 **24키 화이트리스트 ∩
 * `typeof === 'number'`** 로 이중 게이팅하고 있어 99키 중 73키가 구조적으로 편집 불가였고,
 * `bool`/`str`/`enum`/`list_str` 키는 **영원히** 화면에 올 수 없었다. 카탈로그로 바꿔도
 * 다음 사이클에 누가 키 하나를 다시 적어 넣으면 같은 드리프트가 시작된다. 그래서 잠근다.
 *
 * 규칙
 * - 대상 3파일의 **코드**(전체 줄 주석 제외)에 99키 중 어떤 키 이름의 **문자열 리터럴**도 없다.
 * - 예외는 둘뿐이다:
 *   ① `pages/Strategies.tsx` — 읽기 전용 요약 4키(`THRESHOLD_KEYS`). 편집 폼이 아니라
 *      "한눈에 보는 임계" 그리드이고 e2e H-ST2 가 그 라벨을 직접 단언한다.
 *   ② `pages/Settings.tsx` — `ExchangeBoardRow` 의 `exchange` · `tradable_boards`
 *      (라디오/체크박스 특화 UI).
 * - 99키 목록은 손으로 적지 않는다 — `param_catalog.py` 에서 생성한 골든 픽스처에서 읽는다.
 *
 * 이 가드는 **프론트 파일을 읽는 프론트 가드**다. 백엔드 AST 가드
 * `tests/unit/ast/test_cycle278_ast_catalog_guards.py`(B72·B73)가 같은 계약을 이중으로 잠근다.
 */
import { describe, it, expect } from 'vitest'
import { readFileSync, existsSync } from 'fs'
import path from 'path'

import { PARAM_SCHEMA_FIXTURE } from '../../test/fixtures/paramSchema.fixture'

const SRC = path.join(__dirname, '..', '..')

const ALL_KEYS: string[] = PARAM_SCHEMA_FIXTURE.params.map((p) => p.key)

/** 파일별 허용 키 (그 외 리터럴은 전부 위반). */
const TARGETS: { file: string; allowed: string[]; why: string }[] = [
  {
    file: path.join(SRC, 'components', 'StrategyParamsEditor.tsx'),
    allowed: [],
    why: '편집기는 스키마 응답만으로 렌더한다 — 키를 한 개라도 적으면 그 순간 카탈로그가 둘이 된다',
  },
  {
    file: path.join(SRC, 'pages', 'Strategies.tsx'),
    allowed: [
      'stop_loss_rate',
      'daily_loss_limit',
      'trailing_stop_rate',
      'position_ratio',
    ],
    why: '읽기 전용 요약 4키 그리드(THRESHOLD_KEYS) — 편집 폼으로 확장 금지',
  },
  {
    file: path.join(SRC, 'pages', 'Settings.tsx'),
    allowed: ['exchange', 'tradable_boards'],
    why: 'ExchangeBoardRow 의 라디오/체크박스 특화 UI 2키',
  },
]

/** 전체 줄 주석(`//`·`*`·`/*`)만 제거 — 문자열 안의 `//`(URL 등)를 건드리지 않는다. */
function stripFullLineComments(source: string): { line: number; text: string }[] {
  return source
    .split('\n')
    .map((text, idx) => ({ line: idx + 1, text }))
    .filter(({ text }) => {
      const t = text.trim()
      return !(t.startsWith('//') || t.startsWith('*') || t.startsWith('/*'))
    })
}

describe('cycle278 F37 — 편집 3파일에 파라미터 키 하드코딩 0건', () => {
  it('픽스처가 101키를 준다 (방어 가드 — 목록이 비면 이 가드는 아무것도 안 막는다, cycle290 99→101)', () => {
    expect(ALL_KEYS.length).toBe(101)
    expect(new Set(ALL_KEYS).size).toBe(101)
  })

  it.each(TARGETS.map((t) => [path.basename(t.file), t] as const))(
    '%s 에 허용 키 외 파라미터 키 리터럴 0건',
    (_name, target) => {
      expect(
        existsSync(target.file),
        `${target.file} 없음 — Green 이 만들어야 하는 파일이다`,
      ).toBe(true)

      const lines = stripFullLineComments(readFileSync(target.file, 'utf-8'))
      const allowed = new Set(target.allowed)
      const violations: string[] = []

      for (const key of ALL_KEYS) {
        if (allowed.has(key)) continue
        const re = new RegExp(`(['"\`])${key}\\1`)
        for (const { line, text } of lines) {
          if (re.test(text)) violations.push(`${line}: ${key} — ${text.trim().slice(0, 100)}`)
        }
      }

      expect(
        violations,
        `${path.basename(target.file)} 파라미터 키 하드코딩 ${violations.length}건 — ` +
          `${target.why}\n` +
          violations.join('\n'),
      ).toEqual([])
    },
  )
})

describe('cycle278 C36 — paramLabels 는 자문 화면 전용으로 남는다', () => {
  it('편집 3파일 중 어느 것도 utils/paramLabels 를 import 하지 않는다', () => {
    const offenders: string[] = []
    for (const target of TARGETS) {
      if (!existsSync(target.file)) {
        offenders.push(`${path.basename(target.file)}: 파일 없음`)
        continue
      }
      const source = readFileSync(target.file, 'utf-8')
      if (/from\s+['"][^'"]*paramLabels['"]/.test(source)) {
        offenders.push(`${path.basename(target.file)}: paramLabels import 잔존`)
      }
    }
    expect(
      offenders,
      '24키 화이트리스트를 계속 import 하면 카탈로그 전환이 절반만 된 것이다',
    ).toEqual([])
  })

  it('utils/paramLabels.ts 는 삭제되지 않고 Recommendations.tsx 가 계속 쓴다', () => {
    const labels = path.join(SRC, 'utils', 'paramLabels.ts')
    expect(
      existsSync(labels),
      '삭제하면 AI 자문 추천 표가 영문 키로 퇴행한다',
    ).toBe(true)
    const rec = readFileSync(path.join(SRC, 'pages', 'Recommendations.tsx'), 'utf-8')
    expect(/from\s+['"][^'"]*paramLabels['"]/.test(rec)).toBe(true)
  })
})

describe('cycle278 C41 — 장중 판정은 KST 유틸로만 한다', () => {
  it('편집기와 전략 페이지에 로컬타임 getter 가 없고 편집기는 isKrxMainSession 을 쓴다', () => {
    const editor = path.join(SRC, 'components', 'StrategyParamsEditor.tsx')
    expect(existsSync(editor), 'Green 이 만들어야 하는 파일이다').toBe(true)

    for (const file of [editor, path.join(SRC, 'pages', 'Strategies.tsx')]) {
      const code = stripFullLineComments(readFileSync(file, 'utf-8'))
        .map((l) => l.text)
        .join('\n')
      expect(
        /\.getHours\s*\(|\.getMinutes\s*\(/.test(code),
        `${path.basename(file)}: Date 로컬타임 getter 는 브라우저/컨테이너 TZ 를 그대로 탄다`,
      ).toBe(false)
    }

    const editorSource = readFileSync(editor, 'utf-8')
    expect(
      editorSource.includes('isKrxMainSession'),
      '장중 배너는 utils/kst.ts 의 단일 판정을 쓴다',
    ).toBe(true)
  })
})
