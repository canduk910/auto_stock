/**
 * cycle256 Red — 프론트 KST 포맷 유틸 단일화(리팩토링 카드 #9) +
 * `AccountGate.level` 유니온 정정(카드 #10).
 *
 * 명세: `spec_cycle256_frontend_kst_gatelevel.md` §1(범위) · §2(Red K1~K5).
 *
 * ## 왜
 * `Intl.DateTimeFormat(…, timeZone:'Asia/Seoul')` 를 각자 만드는 파일이 15 개다
 * (08-09 리뷰 13 + cycle251 `PortfolioRiskCard` + cycle249 `DailyReportTab` 의
 * `toLocaleString` 변종). 컨벤션이 코드가 아니라 문서에만 있으니 새 사이트마다
 * 12시제·로컬타임 회귀가 재발할 여지가 그대로 남는다. 이번 사이클은 **신규 사이트만**
 * `utils/kst.ts` 로 위임한다(기존 13 은 사이트별 출력 동등성 확인이 선행 — 후속).
 *
 * ## 범위 정정 2 (cycle256-F, 2026-09-05 오후) — DailyReportTab 도 위임한다
 * 아래 "범위 정정" 이 미룬 결정에 사용자가 "바꾸자" 로 답했다(09-05 보고서 2부 카드 ②).
 * 그래서 `DELEGATING_COMPONENTS` 에 `DailyReportTab.tsx` 를 넣고 K4-e 를 뒤집었다 —
 * 이제 이 파일은 "byte 동일" 이 아니라 **위임 여부**를 잰다. 서식 계약(`yyyy-MM-dd
 * HH:mm:ss`, 빈 값 `'-'` 유지, 파싱 불가 `'—'`)은
 * `components/__tests__/DailyReportTab.format.test.tsx` 가 소유한다.
 *
 * ## 범위 정정 (Verify F1, 2026-09-05) — ⚠️ 위 "범위 정정 2" 가 이 절을 대체했다(맥락 보존)
 * 명세 §1 은 `DailyReportTab.formatDateTime` 도 위임 대상으로 적었지만, HEAD 의
 * `toLocaleString('ko-KR', { timeZone, hour12: false })` 출력(브라우저 `2026. 9. 7.
 * 09:05:00` · Node ICU 77 `2026. 9. 7. 9시 5분 0초`)과 유틸의 `yyyy-MM-dd HH:mm:ss`
 * (`2026-09-07 09:05:00`)는 구조적으로 byte 동일일 수 없다 — 명세 §0 "화면 출력
 * 문자열 byte 동일" 계약과 §1 서식 지정이 서로 모순이고, §4 가 "변경 2사이트 렌더
 * 문자열을 HEAD 와 대조" 를 요구한 것으로 보아 명세 작성 의도는 byte 동일 쪽이다.
 * 따라서 이번 사이클은 **PortfolioRiskCard 1 사이트만** 위임하고(5 입력 전부 HEAD 와
 * byte 동일 실측), DailyReportTab 은 서식 변경 승인(team-leader) 후 후속 사이클에서
 * 위임한다. 그때 주의할 점 = `formatDateTime(null)` 은 기존 회귀
 * `src/pages/__tests__/LogReports.formatDateTime.test.ts` 가 `'-'`(하이픈)을 못박고
 * 있으므로 `if (!iso) return '-'` 를 호출부에 남긴 채 유효 입력만 넘겨야 한다(유틸
 * 폴백은 `'—'` em dash). K4 가드의 `DELEGATING_COMPONENTS` 는 그때 확장한다.
 *
 * ## 요구 행위
 * - K1 `formatKstHHMM(iso)` — KST `HH:mm` 24시제. UTC 입력도 KST 환산. 잘못된 입력 → `'—'`
 * - K2 `formatKstDateTime(iso)` — KST `yyyy-MM-dd HH:mm:ss` 24시제. 같은 경계 케이스
 * - K3 `kstTodayISO(now?)` — KST 기준 `YYYY-MM-DD`. `now` 주입이 테스트 seam
 * - K4 텍스트 가드 — 위임 컴포넌트에 **날짜용** `Intl.DateTimeFormat`/`toLocaleString` 0건,
 *   `utils/kst.ts` 에 `hour12: false` ≥1 + `getHours()/getMinutes()` 0건(cycle251 g251_3 관례)
 * - K5 타입 — `AccountGate['level']` 이 `GateLevel` 유니온(임의 문자열 대입은 컴파일 오류) +
 *   `isKnownLevel` 런타임 가드
 *
 * ## TZ 고정 방식 (Verify F2, 2026-09-05) — 정적 import 금지, `beforeAll` 뒤 동적 import
 * `Intl.DateTimeFormat` 은 **생성 시점**에 timeZone 이 고정된다. `utils/kst.ts` 의
 * 포맷터 3 개는 모듈 레벨 상수라 정적 `import { … } from '../kst'` 로 두면
 * `beforeAll(process.env.TZ = 'UTC')` **이전**에 머신 TZ(개발 머신 = Asia/Seoul)로
 * 생성되고, 그 상태에서는 `timeZone: 'Asia/Seoul'` 을 지운 뮤턴트도 34/34 PASS 로
 * 살아남는다(실측 — CI ubuntu(UTC)에서만 검출되던 구멍). 그래서 `../kst` 와 그것을
 * 전이 import 하는 `../../components/PortfolioRiskCard` 는 **둘 다** `beforeAll` 안에서
 * TZ 설정 **후** 동적 import 한다(선례: `LogReports.formatDateTime.test.ts`). vitest 는
 * 테스트 파일마다 모듈 그래프를 격리하므로 이 파일 안에서 정적 경로로 먼저 로드되지만
 * 않으면 포맷터는 UTC 기본값으로 생성된다 — K0 이 그 규율을 텍스트로 봉인한다.
 *
 * ## RED 상태 (구현 전)
 * `frontend/src/utils/kst.ts` 부재 → 동적 import 실패로 K1~K3·K5 RED, K4-f/g 존재 검사 RED.
 * K5 의 `@ts-expect-error` 는 `tsc -b`(= `npm run build`) 가 판정한다 — 루트
 * `tsconfig.json` 이 `files: []` 솔루션 형식이라 `tsc --noEmit` 은 파일을 0 개 검사한다
 * (Verify F3 실측 `--listFiles | wc -l` → 0). `level: … | string` 이면 TS2578("사용되지
 * 않은 @ts-expect-error 지시문")로 RED, 유니온 정정 후 GREEN.
 */
import { afterAll, beforeAll, describe, expect, it } from 'vitest'
import { existsSync, readFileSync } from 'fs'
import path from 'path'

import type { AccountGate, GateLevel } from '../../types/portfolio'

type KstModule = typeof import('../kst')
type IsKnownLevel = (typeof import('../../components/PortfolioRiskCard'))['isKnownLevel']

// 프로세스 TZ 를 UTC 로 고정 — 로컬타임 추출 구현(`getHours()` 등)과 timeZone 누락
// 포맷터가 통과하지 못하게 한다. ⚠️ 포맷터가 모듈 레벨 상수라 **동적 import 가 이
// 대입 뒤**에 와야 효과가 있다(위 "TZ 고정 방식" 참조).
const ORIG_TZ = process.env.TZ
let kst: KstModule
let isKnownLevel: IsKnownLevel
beforeAll(async () => {
  process.env.TZ = 'UTC'
  kst = await import('../kst')
  ;({ isKnownLevel } = await import('../../components/PortfolioRiskCard'))
})
afterAll(() => {
  process.env.TZ = ORIG_TZ
})

const UTILS_DIR = path.join(__dirname, '..')
const COMPONENTS_DIR = path.join(__dirname, '..', '..', 'components')
const KST_UTIL_PATH = path.join(UTILS_DIR, 'kst.ts')
const THIS_TEST_PATH = path.join(__dirname, 'kst.test.ts')

// 위임 사이트. cycle256 = PortfolioRiskCard(출력 byte 동일) · cycle256-F =
// DailyReportTab(09-05 사용자 결정 "바꾸자" — 서식이 `2026-09-07 09:05:00` 으로 바뀐다,
// 헤더 "범위 정정 2" 참조).
const DELEGATING_COMPONENTS = ['PortfolioRiskCard.tsx', 'DailyReportTab.tsx'] as const

function readComponent(filename: string): string {
  return readFileSync(path.join(COMPONENTS_DIR, filename), 'utf-8')
}

/**
 * 주석을 제거한 소스 — K4 는 *코드* 를 검사한다. 주석에 남은 설명 문구
 * (`timeZone: 'Asia/Seoul' 로만 표기한다` 같은)까지 금지하면 가드가 문서를
 * 검열하게 되고, 정작 회귀(실제 포맷터 재생성)와는 무관하다.
 */
function stripComments(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:])\/\/.*$/gm, '$1')
}

/**
 * `toLocaleString`/`toLocaleDateString`/`toLocaleTimeString` 호출 중 **날짜/시각
 * 포맷 목적** 인 것만 집는다 — 같은 줄부터 6줄 창에 `timeZone`/`hour12`/`Asia/Seoul`
 * 이 있으면 KST 포맷터다.
 *
 * ⚠️ `toLocaleString(` 전면 금지는 쓸 수 없다: 컴포넌트가 **숫자 천단위 서식**
 * (`PortfolioRiskCard.formatWon` 등)에 같은 메서드를 쓰고 그것은 이번 범위 밖이다
 * (명세 §1 은 날짜 위임만 지시).
 */
function kstLocaleStringHits(source: string): string[] {
  const lines = stripComments(source).split('\n')
  const hits: string[] = []
  lines.forEach((line, idx) => {
    const calls = /toLocale(String|DateString|TimeString)\(/.test(line)
    if (!calls) return
    const windowText = lines.slice(idx, idx + 6).join('\n')
    if (/timeZone|hour12|Asia\/Seoul/.test(windowText)) {
      hits.push(`L${idx + 1}: ${line.trim()}`)
    }
  })
  return hits
}

describe('K0: 이 테스트 파일의 TZ 고정 규율 — kst/PortfolioRiskCard 정적 import 금지', () => {
  it('K0-a: `../kst` · `components/PortfolioRiskCard` 를 값(value) 정적 import 하지 않는다', () => {
    // 정적 import 가 하나라도 있으면 포맷터가 beforeAll 이전(머신 TZ)에 생성돼
    // timeZone 누락 뮤턴트가 Asia/Seoul 머신에서 살아남는다(Verify F2 실측).
    const code = stripComments(readFileSync(THIS_TEST_PATH, 'utf-8'))
    const staticValueImports = code
      .split('\n')
      .filter((line) => /^\s*import\s+(?!type\b)[\s\S]*?from\s+['"]/.test(line))
      .filter((line) => /['"](\.\.\/kst|\.\.\/\.\.\/components\/PortfolioRiskCard)['"]/.test(line))
    expect(staticValueImports, 'TZ 고정 이전에 포맷터를 생성하는 정적 import 발견').toEqual([])
  })

  it('K0-b: 동적 import 가 `beforeAll` 안에 있다', () => {
    const code = stripComments(readFileSync(THIS_TEST_PATH, 'utf-8'))
    const beforeAllStart = code.indexOf('beforeAll(async () => {')
    expect(beforeAllStart, 'beforeAll(async …) 부재').toBeGreaterThanOrEqual(0)
    const beforeAllBody = code.slice(beforeAllStart, code.indexOf('\n})', beforeAllStart))
    expect(beforeAllBody).toContain("process.env.TZ = 'UTC'")
    expect(beforeAllBody).toContain("await import('../kst')")
    expect(beforeAllBody).toContain("await import('../../components/PortfolioRiskCard')")
    // TZ 대입이 import 보다 앞이어야 한다.
    expect(beforeAllBody.indexOf("process.env.TZ = 'UTC'")).toBeLessThan(
      beforeAllBody.indexOf("await import('../kst')"),
    )
  })
})

describe('K1: formatKstHHMM — KST HH:mm (24시제)', () => {
  it('K1-a: KST 오후 입력 → "13:05"', () => {
    expect(kst.formatKstHHMM('2026-09-07T13:05:00+09:00')).toBe('13:05')
  })

  it('K1-b: UTC 입력도 KST 로 환산 — "2026-09-07T04:05:00Z" → "13:05"', () => {
    expect(kst.formatKstHHMM('2026-09-07T04:05:00Z')).toBe('13:05')
  })

  it('K1-c: 자정 직후는 "00:05" — 12시제 회귀 차단("12:05"/"오전 12:05" 금지)', () => {
    const out = kst.formatKstHHMM('2026-09-07T00:05:00+09:00')
    expect(out).toBe('00:05')
    expect(out).not.toContain('오전')
    expect(out).not.toContain('12:05')
  })

  it('K1-d: 정오는 "12:00" (오전/오후 접두 금지)', () => {
    const out = kst.formatKstHHMM('2026-09-07T12:00:00+09:00')
    expect(out).toBe('12:00')
    expect(out).not.toContain('오후')
  })

  it('K1-e: UTC 날짜 경계 — "2026-09-06T23:30:00Z" 는 KST 익일 "08:30"', () => {
    expect(kst.formatKstHHMM('2026-09-06T23:30:00Z')).toBe('08:30')
  })

  it.each([
    ['null', null],
    ['undefined', undefined],
    ['빈 문자열', ''],
    ['파싱 불가', 'garbage'],
  ])('K1-f: 잘못된 입력(%s) → "—"', (_label, value) => {
    expect(kst.formatKstHHMM(value as string | null | undefined)).toBe('—')
  })
})

describe('K2: formatKstDateTime — KST yyyy-MM-dd HH:mm:ss (24시제, 초 포함)', () => {
  it('K2-a: KST 오후 입력 → "2026-09-07 13:05:09"', () => {
    expect(kst.formatKstDateTime('2026-09-07T13:05:09+09:00')).toBe('2026-09-07 13:05:09')
  })

  it('K2-b: UTC 입력도 KST 로 환산 — "2026-09-07T04:05:09Z" → "2026-09-07 13:05:09"', () => {
    expect(kst.formatKstDateTime('2026-09-07T04:05:09Z')).toBe('2026-09-07 13:05:09')
  })

  it('K2-c: UTC 날짜 경계 — "2026-09-06T23:30:00Z" → "2026-09-07 08:30:00"', () => {
    expect(kst.formatKstDateTime('2026-09-06T23:30:00Z')).toBe('2026-09-07 08:30:00')
  })

  it('K2-d: 자정 직후는 "00:05:00" — 12시제/오전 접두 회귀 차단', () => {
    const out = kst.formatKstDateTime('2026-09-07T00:05:00+09:00')
    expect(out).toBe('2026-09-07 00:05:00')
    expect(out).not.toContain('오전')
  })

  it.each([
    ['null', null],
    ['undefined', undefined],
    ['빈 문자열', ''],
    ['파싱 불가', 'garbage'],
  ])('K2-e: 잘못된 입력(%s) → "—"', (_label, value) => {
    expect(kst.formatKstDateTime(value as string | null | undefined)).toBe('—')
  })
})

describe('K3: kstTodayISO — KST 기준 YYYY-MM-DD (now 주입 seam)', () => {
  it('K3-a: "2026-09-06T23:30:00Z" 주입 → KST 익일 "2026-09-07"', () => {
    expect(kst.kstTodayISO(new Date('2026-09-06T23:30:00Z'))).toBe('2026-09-07')
  })

  it('K3-b: KST 23:59:59 (= "2026-09-06T14:59:59Z") 는 아직 "2026-09-06"', () => {
    expect(kst.kstTodayISO(new Date('2026-09-06T14:59:59Z'))).toBe('2026-09-06')
  })

  it('K3-c: KST 00:00:00 (= "2026-09-06T15:00:00Z") 에서 날짜가 넘어간다', () => {
    expect(kst.kstTodayISO(new Date('2026-09-06T15:00:00Z'))).toBe('2026-09-07')
  })

  it('K3-d: 인자 없이 호출하면 현재 KST 날짜 — YYYY-MM-DD 형식', () => {
    expect(kst.kstTodayISO()).toMatch(/^\d{4}-\d{2}-\d{2}$/)
  })
})

describe('K4: 텍스트 가드 — KST 포맷 소유권이 utils/kst.ts 로 이동', () => {
  it.each(DELEGATING_COMPONENTS)(
    'K4-a: %s 코드에 `new Intl.DateTimeFormat` 0건 (포맷터 자체 생성 금지)',
    (filename) => {
      const code = stripComments(readComponent(filename))
      const hits = code
        .split('\n')
        .map((line, idx) => ({ line, no: idx + 1 }))
        .filter(({ line }) => line.includes('new Intl.DateTimeFormat'))

      expect(
        hits.map(({ no, line }) => `L${no}: ${line.trim()}`),
        `${filename}: KST 포맷터 자체 생성 잔존 — utils/kst.ts 위임 위반`,
      ).toEqual([])
    },
  )

  it.each(DELEGATING_COMPONENTS)(
    'K4-b: %s 코드에 날짜용 `toLocaleString(...)` 0건 (숫자 서식은 대상 아님)',
    (filename) => {
      expect(
        kstLocaleStringHits(readComponent(filename)),
        `${filename}: timeZone/hour12 를 동반한 toLocale*String 잔존 — utils/kst.ts 위임 위반`,
      ).toEqual([])
    },
  )

  it.each(DELEGATING_COMPONENTS)(
    "K4-c: %s 코드에 `'Asia/Seoul'` 리터럴 0건 (tz 리터럴 단일 진실원)",
    (filename) => {
      const code = stripComments(readComponent(filename))
      expect(code.includes('Asia/Seoul'), `${filename}: tz 리터럴 잔존`).toBe(false)
    },
  )

  it('K4-d: PortfolioRiskCard.tsx 가 `formatKstHHMM` 을 호출한다 (위임 확인)', () => {
    expect(stripComments(readComponent('PortfolioRiskCard.tsx'))).toContain('formatKstHHMM')
  })

  it('K4-e: DailyReportTab.tsx 가 `formatKstDateTime` 을 호출한다 (cycle256-F 위임 확인)', () => {
    // cycle256 에서는 이 케이스가 반대 방향(미위임 보존)이었다 — 09-05 사용자 결정
    // "바꾸자" 로 뒤집었다. 서식 계약은 components/__tests__/DailyReportTab.format.test.tsx.
    expect(stripComments(readComponent('DailyReportTab.tsx'))).toContain('formatKstDateTime')
  })

  it('K4-f: utils/kst.ts 에 `hour12: false` ≥1 (ko-KR 기본 12시제 차단)', () => {
    expect(existsSync(KST_UTIL_PATH), 'frontend/src/utils/kst.ts 부재').toBe(true)
    const source = readFileSync(KST_UTIL_PATH, 'utf-8')
    const count = (source.match(/hour12:\s*false/g) ?? []).length
    expect(count, 'hour12: false 부재 — ko-KR 기본 12시제("오후 01:05") 회귀').toBeGreaterThanOrEqual(1)
  })

  it('K4-g: utils/kst.ts 에 `Asia/Seoul` ≥1 · `getHours(`/`getMinutes(` 0건 (cycle251 g251_3 관례)', () => {
    expect(existsSync(KST_UTIL_PATH), 'frontend/src/utils/kst.ts 부재').toBe(true)
    const source = readFileSync(KST_UTIL_PATH, 'utf-8')
    expect(source.includes('Asia/Seoul'), 'timeZone 명시 부재').toBe(true)
    const code = stripComments(source)
    expect(code.includes('getHours('), '로컬타임 추출(getHours) 사용 금지').toBe(false)
    expect(code.includes('getMinutes('), '로컬타임 추출(getMinutes) 사용 금지').toBe(false)
  })
})

describe('K5: AccountGate.level 유니온 + isKnownLevel 런타임 가드', () => {
  it('K5-a: `AccountGate["level"]` 은 GateLevel 유니온 — 임의 문자열 대입은 컴파일 오류', () => {
    // 4 리터럴은 대입 가능해야 한다.
    const ok: AccountGate['level'] = 'warn'
    const levels: GateLevel[] = ['ok', 'warn', 'block', 'error']
    expect(levels).toContain(ok)

    // @ts-expect-error — `| string` 이 제거되면 임의 문자열은 대입 불가.
    //   (`| string` 이 되살아나면 오류가 사라져 `tsc -b` 가 TS2578 로 RED)
    const bad: AccountGate['level'] = 'weird'
    expect(bad).toBe('weird')
  })

  it('K5-b: isKnownLevel — 알려진 4 레벨은 true', () => {
    for (const level of ['ok', 'warn', 'block', 'error']) {
      expect(isKnownLevel(level), `${level} 는 GateLevel`).toBe(true)
    }
  })

  it('K5-c: isKnownLevel — 미지 값/비문자열은 false (현재 else 분기 = 정상 배지 유지)', () => {
    expect(isKnownLevel('weird')).toBe(false)
    expect(isKnownLevel('WARN')).toBe(false)
    expect(isKnownLevel('')).toBe(false)
    expect(isKnownLevel(null)).toBe(false)
    expect(isKnownLevel(undefined)).toBe(false)
    expect(isKnownLevel(0)).toBe(false)
    expect(isKnownLevel({ level: 'warn' })).toBe(false)
  })
})
