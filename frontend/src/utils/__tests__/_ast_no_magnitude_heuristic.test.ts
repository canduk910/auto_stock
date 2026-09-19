/**
 * cycle316 후속 A — **값 크기로 단위를 추측하는 분기**가 화면 코드에 다시 들어오는 것을 막는다.
 *
 * 🔴 왜 금지인가 (루트 `CLAUDE.md` 「비중 단위 추론 변환 금지」)
 * 폐기된 `totalW <= 1.01 ? round(w*100) : round(w)` 는 1%(정수 1)를 100%로 저장하고
 * 그 오염을 "균등분배" 화면으로 **위장**했다. 추론 분기는 값이 오염됐을 때만 깨어나므로
 * 결함이 아니라 **결함 은폐 장치**다.
 *
 * 같은 패턴이 `macro/components/MacroCycleSection.tsx` 에 살아 있었다 —
 * `buffett_ratio > 10 ? v : v*100`. 계약을 어긴 값을 그럴듯한 퍼센트로 만들어
 * 단위가 틀어졌다는 사실을 화면에서 지웠다. cycle316 이 `formatBuffettRatio` 로 바꿨고,
 * 그 함수는 상한을 넘는 값을 변환하지 않고 `⚠단위` 로 **드러낸다**.
 *
 * 이 가드는 소스 텍스트를 본다 — 단위는 계약으로 고정하고 위반은 시끄럽게 거부한다.
 */
import { describe, expect, it } from 'vitest'
import { readFileSync, readdirSync, statSync } from 'node:fs'
import path from 'node:path'

// 기존 가드(`components/__tests__/_ast_weight_unit_guard.test.ts`)와 같은 방식.
const SRC = path.join(__dirname, '..', '..')

/**
 * 진짜 금지 패턴 = **같은 값에 크기별로 다른 배율**을 씌우는 삼항.
 *
 * - 금지: `v > 10 ? v : v * 100`            (같은 v, 한쪽만 ×100)
 * - 금지: `totalW <= 1.01 ? w * 100 : w`    (같은 w, 한쪽만 ×100) ← 폐기된 비중 오염 패턴
 * - 허용: `total > 0 ? (a / total) * 100 : 0`   (0 나누기 가드 — else 에 공통 식별자가 없다)
 * - 허용: `spec.type === 'percent' ? v * 100 : v` (**타입 선언**을 읽는다 — 추측이 아니다)
 *
 * 판정 셋을 모두 만족할 때만 잡는다.
 * ① 조건이 **숫자 크기 비교**다(`>` `<` `>=` `<=` + 숫자 리터럴). `===` 로 타입·enum 을
 *    비교하는 것은 계약을 읽는 정당한 분기다.
 * ② 두 분기에 **공통 식별자**가 있다. 조건 변수와 변환 대상이 다른 경우(폐기된 비중
 *    오염 패턴 `totalW <= 1.01 ? w * 100 : w`)까지 잡으려면 조건식이 아니라 여기를 봐야 한다.
 * ③ **정확히 한쪽에만** ×100 또는 ÷100 이 있다.
 */
const TERNARY = /([^?;\n]{0,90})\?([^:;\n]{1,160}):([^;\n]{1,160})/g
/** 조건이 숫자 크기 비교인가 — 이게 「크기로 추측한다」의 정의다. */
const SIZE_COMPARE = /[<>]=?\s*-?[\d.]+/
const SCALE = /\*\s*100|\/\s*100/
const IDENT = /[A-Za-z_$][\w$]*/g
/** 흔한 유틸 이름은 「공통 식별자」로 치지 않는다 — 그러면 아무 삼항이나 걸린다. */
const NOISE = new Set([
  'Math', 'Number', 'String', 'round', 'floor', 'ceil', 'abs', 'min', 'max',
  'toFixed', 'null', 'undefined', 'true', 'false',
])

function identsOf(s: string): Set<string> {
  return new Set((s.match(IDENT) ?? []).filter((x) => !NOISE.has(x)))
}

function isMagnitudeHeuristic(line: string): boolean {
  TERNARY.lastIndex = 0
  let m: RegExpExecArray | null
  while ((m = TERNARY.exec(line)) !== null) {
    const [, condPart, thenPart, elsePart] = m
    // ① 숫자 크기 비교가 아니면 계약을 읽는 분기다(타입·enum 비교 등).
    if (!SIZE_COMPARE.test(condPart)) continue
    // ③ 정확히 한쪽에만 배율이 있어야 한다 — 양쪽 다 있거나 없으면 단위 추론이 아니다.
    if (SCALE.test(thenPart) === SCALE.test(elsePart)) continue
    const a = identsOf(thenPart)
    const b = identsOf(elsePart)
    for (const x of a) if (b.has(x)) return true
  }
  return false
}

function walk(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    const p = path.join(dir, name)
    if (statSync(p).isDirectory()) {
      if (name === '__tests__' || name === 'test') continue
      walk(p, out)
    } else if (/\.(ts|tsx)$/.test(name)) {
      out.push(p)
    }
  }
  return out
}

describe('값 크기로 단위를 추측하는 분기 금지', () => {
  it('화면 코드 전체에 0건이다', () => {
    const hits: string[] = []
    for (const file of walk(SRC)) {
      const src = readFileSync(file, 'utf-8')
      src.split('\n').forEach((line, i) => {
        // 주석은 제외 — 이 규약을 설명하는 문장 자체가 걸리면 안 된다.
        const code = line.replace(/\/\/.*$/, '').replace(/\/\*.*?\*\//g, '')
        if (isMagnitudeHeuristic(code)) {
          hits.push(`${path.relative(SRC, file)}:${i + 1}  ${line.trim()}`)
        }
      })
    }
    expect(
      hits,
      `값 크기로 단위를 추측하는 분기가 들어왔다. 단위는 계약으로 고정하고 위반은 드러낸다 ` +
        `(예: utils/marketRegime.ts 의 formatBuffettRatio).\n${hits.join('\n')}`,
    ).toEqual([])
  })
})
