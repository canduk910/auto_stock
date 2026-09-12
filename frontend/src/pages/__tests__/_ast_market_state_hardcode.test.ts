/**
 * cycle282 Red — 장운영상태 화면 **하드코딩 0건** 정적 가드 (명세 M7 · §5.4 · FE19~FE21).
 *
 * ## 왜 이 가드가 이 사이클의 핵심인가
 *
 * 이 화면이 보여주는 것은 **거래소의 장 운영 표**다. 그 표는 2026-09-14 에 실제로 바뀐다
 * (K6 애프터마켓 신설 · K7 시간외 단일가 폐지 · 27~29 GTP 시행). 화면이 행 id·시각·주문유형
 * 코드를 자기 안에 한 줄이라도 적어 두면, 백엔드 표가 바뀌어도 화면은 **옛 표를 계속 그린다** —
 * 그리고 그 거짓말은 "사용자가 지금 어떤 호가유형을 쓸 수 있나" 라는 질문에 직접 답하는 자리에서
 * 일어난다. cycle278 이 파라미터 키에 대해 잠근 것과 같은 계약을, 여기서는 **표 전체**에 건다.
 *
 * ## 금지 (명세 §5.4)
 *
 * ① 모든 `row_id` ② 모든 주문유형 `code` ③ 모든 행 `name_ko` · 코드 `name_ko`/`group_ko`
 * ④ 모든 `phase` 값 ⑤ `KRX`·`NXT`·`SOR` ⑥ 문자열 리터럴 안의 `\d{1,2}:\d{2}`
 * ⑦ 하드코딩 hex(`#rrggbb`) — 디자인시스템 v2 토큰(`var(--color-*)`)만.
 *
 * **금지어 목록은 손으로 적지 않는다** — `marketState.fixture.ts` 의 `MARKET_STATE_FORBIDDEN`
 * 에서 읽는다. 그 픽스처는 `market_state.py` 의 표에서 기계 생성되므로, 표에 행이 늘면
 * 금지어도 저절로 는다(cycle278 `_ast_param_key_hardcode.test.ts` 와 같은 구조).
 *
 * ## 두 겹으로 본다
 *
 * - **1겹 (따옴표 리터럴)** — 모든 범주. cycle278 방식(`'K3'` · `"01"` · `` `정규장` ``).
 * - **2겹 (맨몸 토큰)** — ASCII 토큰(`row_id` · `phase` · 거래소명)만. JSX 본문에 따옴표 없이
 *   적힌 `KRX(한국거래소)` 같은 하드코딩을 잡는다. 한글 이름은 2겹에서 뺀다 — 한국어에는
 *   낱말 경계가 없어 `'휴장'` 이 화면의 정당한 `'휴장일'` 배지를 오탐하기 때문이다.
 *
 * ## 커서를 클라이언트 시각으로 계산하지 않는다 (FE20)
 *
 * 브라우저 로컬 시각으로 "지금 몇 번째 행인가" 를 재면 KST 강제 규약이 그 자리에서 깨진다
 * (컨테이너 TZ 가 UTC 인 CI 에서만 틀리는, 가장 늦게 발견되는 종류의 결함이다).
 * 그래서 로컬타임 getter 와 `toLocale*` 을 0 으로 막고, `new Date(` 는 **경과 시간 계산
 * 한 곳**만 허용한다. 표시용 KST 서식은 `utils/kst.ts` 단일 진실원을 쓴다.
 *
 * 이 가드는 **프론트 파일을 읽는 프론트 가드**다. 백엔드 쪽 짝은
 * `tests/unit/ast/test_cycle282_guards.py`(H4·H6·H8)가 라우트·leaf 에 같은 계약을 건다.
 */
import { describe, it, expect } from 'vitest'
import { existsSync, readdirSync, readFileSync, statSync } from 'fs'
import path from 'path'

import { MARKET_STATE_FORBIDDEN, MARKET_STATE_AT_1305 } from '../../test/fixtures/marketState.fixture'

const SRC = path.join(__dirname, '..', '..')
const PAGE = path.join(SRC, 'pages', 'MarketState.tsx')

/**
 * 검사 대상 = 페이지 + 이 사이클이 만든 하위 컴포넌트 전부.
 *
 * 하위 컴포넌트 목록을 손으로 적으면 다음 사람이 파일을 하나 더 만들고 그 안에 `'K3'` 를
 * 적는 순간 가드가 조용히 비켜난다. 그래서 **이름 규약으로 수집**한다 —
 * `components/MarketState*.tsx` 또는 `components/market-state/*.tsx`.
 */
function collectTargets(): string[] {
  const found: string[] = [PAGE]
  const components = path.join(SRC, 'components')
  if (existsSync(components)) {
    for (const name of readdirSync(components)) {
      const full = path.join(components, name)
      if (statSync(full).isDirectory()) {
        if (name === 'market-state' || name === 'marketState') {
          for (const child of readdirSync(full)) {
            if (child.endsWith('.tsx') || child.endsWith('.ts')) found.push(path.join(full, child))
          }
        }
        continue
      }
      if (/^MarketState.*\.(tsx|ts)$/.test(name)) found.push(full)
    }
  }
  return found
}

/**
 * 주석을 지우고 **코드만** 남긴다.
 *
 * 전체 줄 주석(`//`·`*`·`/*`)은 통째로 버리고, 줄 끝 주석은 **따옴표 상태를 추적하며**
 * 잘라낸다 — 문자열 안의 `//`(URL 등)를 건드리지 않기 위해서다. 줄 끝 주석을 남기면
 * `// KRX 는 …` 같은 설명 한 줄이 하드코딩으로 오탐된다(가드가 욕먹는 가장 흔한 이유).
 */
function stripComments(input: string): string {
  let text = input
  let quote: string | null = null
  for (let i = 0; i < text.length; i += 1) {
    const c = text[i]
    if (quote) {
      if (c === '\\') {
        i += 1
        continue
      }
      if (c === quote) quote = null
      continue
    }
    if (c === "'" || c === '"' || c === '`') {
      quote = c
      continue
    }
    if (c === '/' && text[i + 1] === '/') return text.slice(0, i)
    if (c === '/' && text[i + 1] === '*') {
      const end = text.indexOf('*/', i + 2)
      if (end === -1) return text.slice(0, i)
      text = `${text.slice(0, i)} ${text.slice(end + 2)}`
      i -= 1
    }
  }
  return text
}

function codeLines(source: string): { line: number; text: string }[] {
  return source
    .split('\n')
    .map((text, idx) => ({ line: idx + 1, text }))
    .filter(({ text }) => {
      const t = text.trim()
      return !(t.startsWith('//') || t.startsWith('*') || t.startsWith('/*'))
    })
    .map(({ line, text }) => ({ line, text: stripComments(text) }))
}

function readCode(file: string): { line: number; text: string }[] {
  expect(
    existsSync(file),
    `${file} 없음 — Green(frontend-dev)이 만들어야 하는 파일이다`,
  ).toBe(true)
  return codeLines(readFileSync(file, 'utf-8'))
}

const STRING_LITERAL = /'(?:[^'\\\n]|\\.)*'|"(?:[^"\\\n]|\\.)*"|`(?:[^`\\]|\\.)*`/g

const F = MARKET_STATE_FORBIDDEN

// ───────────────────────────────────────────────────────────────────────────
// 방어 — 목록이 비면 이 파일은 아무것도 막지 않는다
// ───────────────────────────────────────────────────────────────────────────

describe('cycle282 M7 방어 — 금지어 목록이 실재한다', () => {
  it('픽스처가 13행·28코드·10 phase·3 거래소를 준다', () => {
    expect(F.rowIds.length).toBe(13)
    expect(F.divisionCodes.length).toBe(28)
    expect(F.phases.length).toBe(10)
    expect(F.markets).toEqual(MARKET_STATE_AT_1305.exchange_order)
    expect(F.rowNames.length).toBeGreaterThan(5)
    expect(F.divisionNames.length).toBeGreaterThan(15)
  })

  it('표현 어휘(tone·rel·support·confidence)는 금지어가 아니다 — 스타일 매핑 키로 허용', () => {
    const vocab = MARKET_STATE_AT_1305.vocab
    const allForbidden = new Set([
      ...F.rowIds,
      ...F.divisionCodes,
      ...F.rowNames,
      ...F.divisionNames,
      ...F.phases,
      ...F.markets,
    ])
    for (const word of [
      ...vocab.tones,
      ...vocab.rels,
      ...vocab.support_levels,
      ...vocab.confidences,
      ...vocab.division_confidences,
    ]) {
      expect(allForbidden.has(word), `표현 어휘가 금지어와 충돌한다: ${word}`).toBe(false)
    }
  })
})

// ───────────────────────────────────────────────────────────────────────────
// FE19 — 행 id · 코드 · 이름 · phase · 시장명 하드코딩 0건
// ───────────────────────────────────────────────────────────────────────────

describe('cycle282 FE19 (M7) — 표의 값이 화면 소스에 없다', () => {
  it('1겹: 따옴표 리터럴로 적힌 금지어 0건', () => {
    const violations: string[] = []
    for (const file of collectTargets()) {
      const lines = readCode(file)
      const buckets: [string, string[]][] = [
        ['row_id', F.rowIds],
        ['주문유형 code', F.divisionCodes],
        ['행 이름', F.rowNames],
        ['주문유형 이름', F.divisionNames],
        ['phase', F.phases],
        ['거래소명', F.markets],
      ]
      for (const [label, words] of buckets) {
        for (const word of words) {
          const re = new RegExp(`(['"\`])${word.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\1`)
          for (const { line, text } of lines) {
            if (re.test(text)) {
              violations.push(
                `${path.basename(file)}:${line} [${label}] ${word} — ${text.trim().slice(0, 110)}`,
              )
            }
          }
        }
      }
    }
    expect(
      violations,
      `표의 값을 화면이 들고 있으면 2026-09-14 표 개편 때 화면만 옛 표를 그린다 ` +
        `(${violations.length}건):\n` +
        violations.join('\n'),
    ).toEqual([])
  })

  it('2겹: 따옴표 없이 적힌 ASCII 토큰(row_id·phase·거래소명) 0건', () => {
    const tokens = [...F.rowIds, ...F.phases, ...F.markets]
    const violations: string[] = []
    for (const file of collectTargets()) {
      for (const { line, text } of readCode(file)) {
        for (const token of tokens) {
          if (new RegExp(`\\b${token}\\b`).test(text)) {
            violations.push(
              `${path.basename(file)}:${line} ${token} — ${text.trim().slice(0, 110)}`,
            )
          }
        }
      }
    }
    expect(
      violations,
      `JSX 본문에 맨몸으로 적힌 표의 값 ${violations.length}건 — 따옴표만 피한 하드코딩이다:\n` +
        violations.join('\n'),
    ).toEqual([])
  })

  it('⑥ 문자열 리터럴 안에 시각(`H:MM`)이 없다', () => {
    const violations: string[] = []
    for (const file of collectTargets()) {
      for (const { line, text } of readCode(file)) {
        for (const literal of text.match(STRING_LITERAL) ?? []) {
          if (/\d{1,2}:\d{2}/.test(literal)) {
            violations.push(`${path.basename(file)}:${line} ${literal.slice(0, 80)}`)
          }
        }
      }
    }
    expect(
      violations,
      '시각은 전부 응답(window·start·end·next_boundary)에서 온다 ' +
        `(${violations.length}건):\n` +
        violations.join('\n'),
    ).toEqual([])
  })
})

// ───────────────────────────────────────────────────────────────────────────
// FE20 — 커서를 클라이언트 시각으로 계산하지 않는다
// ───────────────────────────────────────────────────────────────────────────

describe('cycle282 FE20 (M7) — 시각 판정은 서버, 화면은 스톱워치만', () => {
  it('브라우저 로컬타임 getter 와 `toLocale*` 이 0건', () => {
    const banned = [
      /\.getHours\s*\(/,
      /\.getMinutes\s*\(/,
      /\.getSeconds\s*\(/,
      /\.getDay\s*\(/,
      /\.getDate\s*\(/,
      /\.getMonth\s*\(/,
      /\.getFullYear\s*\(/,
      /\.toLocaleTimeString\s*\(/,
      /\.toLocaleDateString\s*\(/,
      /\.toLocaleString\s*\(/,
    ]
    const violations: string[] = []
    for (const file of collectTargets()) {
      for (const { line, text } of readCode(file)) {
        for (const re of banned) {
          if (re.test(text)) {
            violations.push(`${path.basename(file)}:${line} — ${text.trim().slice(0, 110)}`)
          }
        }
      }
    }
    expect(
      violations,
      `로컬타임은 컨테이너/브라우저 TZ 를 그대로 탄다 — KST 서식은 utils/kst.ts 단일 진실원을 쓴다 ` +
        `(${violations.length}건):\n` +
        violations.join('\n'),
    ).toEqual([])
  })

  it('`new Date(` 는 경과 시간 계산 한 곳까지만 허용한다', () => {
    for (const file of collectTargets()) {
      const code = readCode(file)
        .map((l) => l.text)
        .join('\n')
      const hits = code.match(/new Date\s*\(/g) ?? []
      expect(
        hits.length,
        `${path.basename(file)}: \`new Date(\` ${hits.length}건. ` +
          `카운트다운은 두 시각의 **차이**(경과)만 쓰면 되고(Date.now() 로 충분), ` +
          `표시용 KST 서식은 utils/kst.ts 가 한다. 절대 시각을 직접 다루기 시작하면 ` +
          `커서가 서버 판정에서 브라우저 판정으로 미끄러진다.`,
      ).toBeLessThanOrEqual(1)
    }
  })

  it('KST 서식은 명시된다 — `timeZone: \'Asia/Seoul\'` 또는 utils/kst 경유', () => {
    const page = readFileSync(PAGE, 'utf-8')
    const explicit = /timeZone:\s*['"]Asia\/Seoul['"]/.test(page)
    const viaUtil = /from\s+['"][^'"]*utils\/kst['"]/.test(page)
    expect(
      explicit || viaUtil,
      'as_of 표시가 KST 라는 근거가 소스에 없다 — 규약은 문서가 아니라 코드에 있어야 한다',
    ).toBe(true)
  })

  it('조회는 `retry:` 와 30초 폴링을 명시한다 (명세 §5.2)', () => {
    const code = readCode(PAGE)
      .map((l) => l.text)
      .join('\n')
    const matches = [...code.matchAll(/useQuery(?:<[^>]+>)?\(\s*\{([\s\S]*?)\}\s*\)/g)]
    expect(matches.length, 'MarketState.tsx: useQuery 호출 0건').toBeGreaterThanOrEqual(1)
    const options = matches.map((m) => m[1]).join('\n')
    expect(
      /\bretry\s*:\s*(false|0|1|2|3)\b/.test(options),
      'retry 미명시 — e2e/백엔드 미기동 환경에서 기본 retry(3회 backoff)가 누적돼 페이지가 안 뜬다(사이클 65 H3)',
    ).toBe(true)
    expect(
      /\brefetchInterval\s*:\s*30_?000\b/.test(options),
      '30초 폴링 미명시 — 커서가 서버 판정이라면 화면은 주기적으로 다시 물어야 한다',
    ).toBe(true)
  })
})

// ───────────────────────────────────────────────────────────────────────────
// FE21 — 디자인시스템 v2 토큰만
// ───────────────────────────────────────────────────────────────────────────

describe('cycle282 FE21 — 하드코딩 hex 0건 (DK Stock 디자인시스템 v2)', () => {
  it('`#rrggbb` / `#rgb` 리터럴이 없다', () => {
    const violations: string[] = []
    for (const file of collectTargets()) {
      for (const { line, text } of readCode(file)) {
        if (/#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?\b/.test(text)) {
          violations.push(`${path.basename(file)}:${line} — ${text.trim().slice(0, 110)}`)
        }
      }
    }
    expect(
      violations,
      `색은 index.css 의 @theme 토큰(var(--color-*)) 또는 Tailwind 별칭으로만 쓴다 — ` +
        `cycle261 이 팔레트를 한 곳으로 모은 이유가 이것이다 (${violations.length}건):\n` +
        violations.join('\n'),
    ).toEqual([])
  })
})

// ───────────────────────────────────────────────────────────────────────────
// 목 등록 · 리포 관례 — 화면이 생기면 함께 있어야 하는 것들
// ───────────────────────────────────────────────────────────────────────────

describe('cycle282 — 목 3곳과 영구 가드 등재', () => {
  const REPO = path.join(SRC, '..', '..')

  it('MSW 기본 핸들러에 `/api/market-state` 가 등록돼 있다', () => {
    const handlers = readFileSync(path.join(SRC, 'test', 'handlers.ts'), 'utf-8')
    expect(
      /http\.get\(`\$\{base\}\/market-state`/.test(handlers),
      'MSW 미등록이면 setup.ts 의 onUnhandledRequest:"error" 로 컴포넌트 테스트가 즉시 붕괴한다',
    ).toBe(true)
    expect(
      /from\s+['"]\.\/fixtures\/marketState\.fixture['"]/.test(handlers),
      '목 본문은 손으로 쓴 요약이 아니라 골든 픽스처여야 한다(cycle266 재발 차단)',
    ).toBe(true)
  })

  it('Playwright 목에 `**/api/market-state*` 라우트가 등록돼 있다', () => {
    const mocks = readFileSync(path.join(REPO, 'e2e', 'fixtures', 'api-mocks.ts'), 'utf-8')
    expect(
      /page\.route\(\s*["'`][^"'`]*\/api\/market-state[^"'`]*["'`]/.test(mocks),
      '미등록이면 vite proxy → 백엔드 미기동 → ECONNREFUSED → e2e timeout (사이클 65 H3 계열)',
    ).toBe(true)
  })

  it('신규 페이지가 useQuery `retry` 영구 가드 목록에 등재된다 (리포 관례)', () => {
    const guard = readFileSync(
      path.join(SRC, 'components', '__tests__', '_ast_useQuery_retry_required.test.ts'),
      'utf-8',
    )
    expect(
      guard.includes("'MarketState.tsx'"),
      'StockMaster·RealtimeHealth·Strategies 가 그랬듯 신규 페이지는 TARGET_PAGES 에 등재한다 — ' +
        '등재하지 않으면 다음 사람이 retry 를 지워도 아무도 모른다',
    ).toBe(true)
  })
})
