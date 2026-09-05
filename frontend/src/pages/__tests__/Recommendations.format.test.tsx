/**
 * cycle256-G Red — `pages/Recommendations.tsx` 의 `formatDateTime` 를 `utils/kst.ts` 로 위임.
 *
 * 명세: `_workspace/specs/cycle256G_recommendations_kst_delegation.md` (§행위 · §테스트).
 *
 * ## 왜 지금
 * cycle261 적대 검토가 발견 — `Recommendations.tsx:44~52` 의 `formatDateTime` 은
 * `new Date(iso).toLocaleString('ko-KR', { hour12: false })` 로 **`timeZone` 자체가 없다**.
 * cycle256-F 가 고친 `DailyReportTab` 은 최소한 `timeZone: 'Asia/Seoul'` 은 있었고 서식만
 * ICU 에 좌우됐지만, 이쪽은 **표시 시각이 브라우저/컨테이너 로컬타임**이라
 * `frontend/CLAUDE.md` 의 "모든 시각 데이터 KST 강제" 를 정면으로 어긴다(사용자 브라우저가
 * KST 라 우연히 맞아 보였을 뿐 — UTC 컨테이너·해외 접속에서는 9시간 어긋난다).
 * 09-05 3부 보고서 카드 ③ 의 사용자 답이 "바꿔" 라서 이제 위임한다.
 *
 * ## 요구 행위 (HEAD → 목표)
 * - G1 유효 입력(UTC · `+09:00` · 날짜 경계) → `formatKstDateTime` 의 `yyyy-MM-dd HH:mm:ss`
 *   (`2026-09-07 09:05:00`) — 환경 무관 고정폭, ICU 로케일 토큰(`'. '`·`오전`·`오후`·`시`) 0건
 * - G2 `null`/`undefined`/빈 문자열 → **현행 `'-'` 유지**(빈 값 표기는 이번 결정 범위 밖 —
 *   cycle256-F 와 같은 계약)
 * - G3 파싱 불가 문자열 → `'—'`(em dash). HEAD 는 `catch` 로 원문을 흘리거나
 *   `Invalid Date` 를 화면에 그대로 노출했다(`new Date('garbage')` 는 throw 하지 않으므로
 *   HEAD 의 try/catch 는 실제로는 발화하지 않는 죽은 분기다)
 * - G4 렌더 — 카드 헤더 `생성 2026-09-07 09:05:00` · 하단 `적용 시각: …` / `거절 시각: …`
 * - G5 무접촉 — 같은 파일의 **숫자** 서식(`value.toLocaleString()`, 41행)은 그대로 둔다
 *
 * ## TZ 고정 방식 (cycle256 F2 · cycle256-F F0 교훈)
 * `utils/kst.ts` 의 포맷터 3 개는 **모듈 레벨 상수**라 `Intl.DateTimeFormat` 생성 시점에
 * timeZone 이 고정된다. 정적 `import Recommendations from '../Recommendations'` 로 두면
 * 전이 import 로 `utils/kst` 가 `beforeAll(process.env.TZ = 'UTC')` **이전**(= 개발 머신
 * Asia/Seoul)에 로드돼, `timeZone: 'Asia/Seoul'` 을 지운 뮤턴트가 로컬에서만 살아남는다.
 * 그래서 페이지 모듈은 `beforeAll` 안에서 TZ 설정 **후** 동적 import 하고, G0 이 그 규율을
 * 이 파일 자신의 소스로 봉인한다. TZ=UTC 고정은 동시에 HEAD 의 로컬타임 결함을
 * **테스트가 실제로 잴 수 있게** 만든다(개발 머신 KST 에서는 HEAD 도 우연히 맞는다).
 *
 * ## RED 상태 (구현 전 = HEAD)
 * - G1/G3/G4 FAIL — HEAD 는 `formatDateTime` 을 export 하지 않는다(→ `TypeError`) +
 *   export 하더라도 ICU 로컬타임 서식을 낸다. **export 추가는 Green 의 몫**이다.
 * - G2/G5 는 HEAD 에서 export 부재로 호출 불가(TypeError) — Green 이 export 를 추가하면 계약대로 PASS — 현행 유지 계약(빈 값 `'-'` · 숫자 서식 무접촉)
 * - 동반 = `utils/__tests__/kst.test.ts` 의 위임 목록에 `pages/Recommendations.tsx` 추가 →
 *   K4-b(48행 `toLocaleString('ko-KR', { hour12: false })`) · K4-h(위임 확인) RED
 */
import { afterAll, beforeAll, describe, expect, it } from 'vitest'
import { readFileSync } from 'fs'
import path from 'path'
import { render, screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'

import { TestProviders } from '../../test/providers'
import { wrap } from '../../test/factories'
import { server } from '../../test/server'
import type { RecommendationItem } from '../../types/recommendations'

type RecommendationsModule = typeof import('../Recommendations')

const THIS_TEST_PATH = path.join(__dirname, 'Recommendations.format.test.tsx')
const PAGE_PATH = path.join(__dirname, '..', 'Recommendations.tsx')

// ⚠️ TZ 고정 뒤 동적 import — 위 "TZ 고정 방식" 참조.
const ORIG_TZ = process.env.TZ
let mod: RecommendationsModule
let formatDateTime: RecommendationsModule['formatDateTime']
let Recommendations: RecommendationsModule['default']

beforeAll(async () => {
  process.env.TZ = 'UTC'
  mod = await import('../Recommendations')
  formatDateTime = mod.formatDateTime
  Recommendations = mod.default
})
afterAll(() => {
  process.env.TZ = ORIG_TZ
})

/** 주석 제거 — G0/G5 는 *코드* 를 검사한다(설명 주석의 import 문구는 회귀가 아니다). */
function stripComments(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:])\/\/.*$/gm, '$1')
}

function makeRec(overrides: Partial<RecommendationItem> = {}): RecommendationItem {
  return {
    id: 'R1',
    created_at: '2026-09-07T00:05:00Z', // = KST 2026-09-07 09:05:00
    target_date: '2026-09-07',
    strategy_id: 'momentum',
    status: 'pending',
    current_params: { position_ratio: 0.25 },
    recommended_params: { position_ratio: 0.3 },
    applied_params: null,
    reasoning: '비중을 올리는 것을 추천',
    metrics: null,
    applied_at: null,
    rejected_at: null,
    recommended_weight: null,
    code_review_notes: null,
    applied_weight: null,
    ...overrides,
  }
}

function setupStrategies() {
  server.use(
    http.get('/api/strategies', () =>
      HttpResponse.json(
        wrap({
          momentum: {
            name: '모멘텀',
            enabled: true,
            weight: 0.25,
            params: {},
            invested_amount: 0,
            min_weight: 0,
            total_investment: 5_000_000,
          },
        }),
      ),
    ),
  )
}

describe('G0: 이 테스트 파일의 TZ 고정 규율 — Recommendations 정적 import 금지', () => {
  it('G0-a: `../Recommendations` 를 값(value) 정적 import 하지 않는다', () => {
    // 정적 import 하나면 전이 import 된 `utils/kst` 포맷터가 beforeAll 이전(머신 TZ)에
    // 생성돼 timeZone 누락 뮤턴트가 Asia/Seoul 머신에서 통과한다(cycle256 F2 실측).
    const code = stripComments(readFileSync(THIS_TEST_PATH, 'utf-8'))
    const staticValueImports = code
      .split('\n')
      .filter((line) => /^\s*import\s+(?!type\b)[\s\S]*?from\s+['"]/.test(line))
      .filter((line) => /['"]\.\.\/Recommendations['"]/.test(line))
    expect(staticValueImports, 'TZ 고정 이전에 포맷터를 생성하는 정적 import 발견').toEqual([])
  })

  it('G0-b: 동적 import 가 `beforeAll` 안, TZ 대입 뒤에 있다', () => {
    const code = stripComments(readFileSync(THIS_TEST_PATH, 'utf-8'))
    const start = code.indexOf('beforeAll(async () => {')
    expect(start, 'beforeAll(async …) 부재').toBeGreaterThanOrEqual(0)
    const body = code.slice(start, code.indexOf('\n})', start))
    expect(body).toContain("process.env.TZ = 'UTC'")
    expect(body).toContain("await import('../Recommendations')")
    expect(body.indexOf("process.env.TZ = 'UTC'")).toBeLessThan(
      body.indexOf("await import('../Recommendations')"),
    )
  })
})

describe('G1: formatDateTime — 유효 ISO 는 KST `yyyy-MM-dd HH:mm:ss`', () => {
  it('G1-0: 단위 테스트 가능하도록 `formatDateTime` 이 export 돼 있다 (export 추가 = Green)', () => {
    expect(typeof formatDateTime, 'Recommendations.tsx 가 formatDateTime 을 export 하지 않는다').toBe(
      'function',
    )
  })

  it('G1-a: UTC 입력 "2026-09-07T00:05:00Z" → "2026-09-07 09:05:00"', () => {
    expect(formatDateTime('2026-09-07T00:05:00Z')).toBe('2026-09-07 09:05:00')
  })

  it('G1-b: 동일 시각의 `+09:00` 입력도 같은 문자열', () => {
    expect(formatDateTime('2026-09-07T09:05:00+09:00')).toBe('2026-09-07 09:05:00')
    expect(formatDateTime('2026-09-07T09:05:00+09:00')).toBe(formatDateTime('2026-09-07T00:05:00Z'))
  })

  it('G1-c: 서식은 환경 무관 고정폭 — ICU 로케일 토큰(`2026. 9. 7.` / `9시 5분` / 오전·오후) 0건', () => {
    const out = formatDateTime('2026-09-07T00:05:00Z')
    expect(out).toMatch(/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/)
    expect(out).not.toContain('. ') // "2026. 9. 7." ICU 서식
    expect(out).not.toContain('시')
    expect(out).not.toContain('오전')
    expect(out).not.toContain('오후')
  })

  it('G1-d: UTC 날짜 경계 — "2026-09-06T23:30:00Z" 는 KST 익일 "2026-09-07 08:30:00"', () => {
    expect(formatDateTime('2026-09-06T23:30:00Z')).toBe('2026-09-07 08:30:00')
  })

  it('G1-e: 자정 직후는 24시제 "00:05:00" (12시제 회귀 차단)', () => {
    expect(formatDateTime('2026-09-07T00:05:00+09:00')).toBe('2026-09-07 00:05:00')
  })

  it('G1-f: 정오는 "12:00:00" (오후 접두 금지)', () => {
    const out = formatDateTime('2026-09-07T12:00:00+09:00')
    expect(out).toBe('2026-09-07 12:00:00')
    expect(out).not.toContain('오후')
  })
})

describe('G2: 빈 값 표기는 현행 `-` 유지 (이번 결정 범위 밖)', () => {
  it.each([
    ['null', null],
    ['undefined', undefined],
    ['빈 문자열', ''],
  ])('G2-a: %s → "-" (하이픈, em dash 아님)', (_label, value) => {
    const out = formatDateTime(value as string | null)
    expect(out).toBe('-')
    expect(out).not.toBe('—')
  })
})

describe('G3: 파싱 불가 문자열 → `—` (원문 노출 금지)', () => {
  it('G3-a: "garbage" → "—"', () => {
    const out = formatDateTime('garbage')
    expect(out).toBe('—')
    expect(out).not.toContain('garbage')
    expect(out).not.toContain('Invalid')
  })

  it('G3-b: 날짜처럼 보이지만 파싱 불가한 값도 "—"', () => {
    expect(formatDateTime('2026-13-45T99:99:99Z')).toBe('—')
  })
})

describe('G4: 렌더 — 생성/적용/거절 시각이 새 서식으로 보인다', () => {
  it('G4-a: 카드 헤더 "생성 2026-09-07 09:05:00" + 적용/거절 시각', async () => {
    setupStrategies()
    server.use(
      http.get('/api/recommendations', () =>
        HttpResponse.json(
          wrap([
            makeRec({
              id: 'R-applied',
              status: 'applied',
              created_at: '2026-09-07T00:05:00Z', // KST 09:05:00
              applied_at: '2026-09-07T20:30:00+09:00',
            }),
            makeRec({
              id: 'R-rejected',
              status: 'rejected',
              created_at: '2026-09-06T23:30:00Z', // KST 익일 08:30:00
              rejected_at: '2026-09-07T11:00:00+09:00',
            }),
          ]),
        ),
      ),
    )

    render(
      <TestProviders>
        <Recommendations />
      </TestProviders>,
    )

    expect(await screen.findByText('생성 2026-09-07 09:05:00')).toBeInTheDocument()
    expect(screen.getByText('생성 2026-09-07 08:30:00')).toBeInTheDocument()
    expect(screen.getByText('적용 시각: 2026-09-07 20:30:00')).toBeInTheDocument()
    expect(screen.getByText('거절 시각: 2026-09-07 11:00:00')).toBeInTheDocument()

    // HEAD 의 로컬타임 ICU 서식이 남아 있으면 잡는다(TZ=UTC 고정이라 "2026. 9. 7. 0:05" 계열).
    const body = document.body.textContent ?? ''
    expect(body).not.toContain('2026. 9.')
    expect(body).not.toContain('시 5분')
  })
})

describe('G5: 무접촉 — 같은 파일의 숫자 서식은 그대로 둔다', () => {
  it('G5-a: `value.toLocaleString()`(천단위 숫자 서식) 이 남아 있다', () => {
    // 위임 대상은 *날짜* 서식 하나뿐이다. Green 이 파일 전체의 `toLocaleString` 을
    // 일괄 치환하면 `formatNumber` 가 함께 바뀌므로 여기서 봉인한다.
    const code = stripComments(readFileSync(PAGE_PATH, 'utf-8'))
    expect(code).toMatch(/value\.toLocaleString\(/)
  })

  it('G5-b: 페이지가 `formatKstDateTime` 을 utils/kst 에서 가져온다 (위임 확인)', () => {
    const code = stripComments(readFileSync(PAGE_PATH, 'utf-8'))
    expect(code, 'utils/kst 위임 미완료').toContain('formatKstDateTime')
    expect(code, "import 경로가 '../utils/kst' 가 아니다").toMatch(
      /from\s+['"]\.\.\/utils\/kst['"]/,
    )
  })
})
