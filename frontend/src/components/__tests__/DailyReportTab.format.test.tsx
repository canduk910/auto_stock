/**
 * cycle256-F Red — `DailyReportTab.formatDateTime` 를 `utils/kst.ts` 로 위임.
 *
 * 명세: `_workspace/specs/cycle256F_dailyreport_kst_delegation.md` (§행위 · §테스트).
 *
 * ## 왜 지금
 * cycle256 은 `PortfolioRiskCard` 만 위임하고 `DailyReportTab` 은 **사용자 가시 서식
 * 변경**이라 결정을 미뤘다(`utils/__tests__/kst.test.ts` 헤더 "범위 정정"). 09-05
 * 보고서 2부 카드 ② 의 사용자 답이 "바꾸자" 라서 이제 위임한다.
 *
 * ## 요구 행위 (HEAD → 목표)
 * HEAD 의 `new Date(iso).toLocaleString('ko-KR', { timeZone:'Asia/Seoul', hour12:false })`
 * 는 **ICU 버전에 따라 출력이 다르다** — 브라우저 `2026. 9. 7. 09:05:00` /
 * Node ICU 77 `2026. 9. 7. 9시 5분 0초`. 즉 화면 서식이 실행 환경에 좌우된다.
 * - F1 유효 입력(UTC · `+09:00`) → `formatKstDateTime` 의 `yyyy-MM-dd HH:mm:ss`
 *   (`2026-09-07 09:05:00`) — 환경 무관 고정폭
 * - F2 `null`/`undefined`/빈 문자열 → **현행 `'-'` 유지**(빈 값 표기는 이번 결정 범위
 *   밖이고 기존 회귀 `pages/__tests__/LogReports.formatDateTime.test.ts` 가 못박고 있다)
 * - F3 파싱 불가 문자열 → `'—'`(em dash). HEAD 는 `Invalid Date` 문자열 또는 원문을
 *   그대로 화면에 흘렸다 — 원문 노출보다 대시 표기가 표시 사고에 안전하다
 * - F4 렌더 — ext 카드 헤더가 `생성 2026-09-02 20:20:00 · anthropic · claude-sonnet-5`
 *
 * ## TZ 고정 방식 (cycle256 F2 교훈)
 * `utils/kst.ts` 의 포맷터 3 개는 **모듈 레벨 상수**라 `Intl.DateTimeFormat` 생성 시점에
 * timeZone 이 고정된다. 정적 `import … from '../DailyReportTab'` 로 두면 전이 import 로
 * `utils/kst` 가 `beforeAll(process.env.TZ = 'UTC')` **이전**(= 개발 머신 Asia/Seoul)에
 * 로드돼, `timeZone: 'Asia/Seoul'` 을 지운 뮤턴트가 로컬에서만 살아남는다(cycle256 실측).
 * 그래서 컴포넌트 모듈은 `beforeAll` 안에서 TZ 설정 **후** 동적 import 하고, F0 이 그
 * 규율을 이 파일 자신의 소스로 봉인한다.
 *
 * ## RED 상태 (구현 전 = HEAD)
 * F1/F3/F4 FAIL(HEAD 는 ICU 서식 / 원문·`Invalid Date` 반환), F2 PASS(현행 유지 계약).
 * 동반 = `utils/__tests__/kst.test.ts` 의 `DELEGATING_COMPONENTS` 에 `DailyReportTab.tsx`
 * 추가 → K4-b/c/e RED.
 */
import { afterAll, beforeAll, describe, expect, it } from 'vitest'
import { readFileSync } from 'fs'
import path from 'path'
import { render, screen } from '@testing-library/react'
import { http, HttpResponse } from 'msw'

import { TestProviders } from '../../test/providers'
import { wrap } from '../../test/factories'
import { server } from '../../test/server'
import type { LogReportItem } from '../../types/log_reports'

type DailyReportTabModule = typeof import('../DailyReportTab')

const THIS_TEST_PATH = path.join(__dirname, 'DailyReportTab.format.test.tsx')

// ⚠️ TZ 고정 뒤 동적 import — 위 "TZ 고정 방식" 참조.
const ORIG_TZ = process.env.TZ
let mod: DailyReportTabModule
let formatDateTime: DailyReportTabModule['formatDateTime']
let DailyReportTab: DailyReportTabModule['default']

beforeAll(async () => {
  process.env.TZ = 'UTC'
  mod = await import('../DailyReportTab')
  formatDateTime = mod.formatDateTime
  DailyReportTab = mod.default
})
afterAll(() => {
  process.env.TZ = ORIG_TZ
})

/** 주석 제거 — F0 은 *코드* 를 검사한다(설명 주석의 import 문구는 회귀가 아니다). */
function stripComments(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:])\/\/.*$/gm, '$1')
}

// cycle249 W2 픽스처 재사용 — `DailyReportTab.ext.test.tsx` 의 extReport 와 동일한
// ext_created_at 을 쓴다(두 파일이 같은 값을 보게 해 서식 변경을 한쪽만 놓치지 않는다).
const extReport: LogReportItem = {
  id: 'r2',
  target_date: '2026-09-02',
  summary: 'OpenAI 총평입니다.',
  findings: [],
  metrics: null,
  model: 'gpt-4o',
  created_at: '2026-09-02T20:15:00+09:00',
  ext_provider: 'anthropic',
  ext_model: 'claude-sonnet-5',
  ext_summary: 'Claude 총평입니다.',
  ext_findings: [],
  ext_report_md: null,
  ext_created_at: '2026-09-02T20:20:00+09:00',
}

describe('F0: 이 테스트 파일의 TZ 고정 규율 — DailyReportTab 정적 import 금지', () => {
  it('F0-a: `../DailyReportTab` 을 값(value) 정적 import 하지 않는다', () => {
    // 정적 import 하나면 전이 import 된 `utils/kst` 포맷터가 beforeAll 이전(머신 TZ)에
    // 생성돼 timeZone 누락 뮤턴트가 Asia/Seoul 머신에서 통과한다(cycle256 F2 실측).
    const code = stripComments(readFileSync(THIS_TEST_PATH, 'utf-8'))
    const staticValueImports = code
      .split('\n')
      .filter((line) => /^\s*import\s+(?!type\b)[\s\S]*?from\s+['"]/.test(line))
      .filter((line) => /['"]\.\.\/DailyReportTab['"]/.test(line))
    expect(staticValueImports, 'TZ 고정 이전에 포맷터를 생성하는 정적 import 발견').toEqual([])
  })

  it('F0-b: 동적 import 가 `beforeAll` 안, TZ 대입 뒤에 있다', () => {
    const code = stripComments(readFileSync(THIS_TEST_PATH, 'utf-8'))
    const start = code.indexOf('beforeAll(async () => {')
    expect(start, 'beforeAll(async …) 부재').toBeGreaterThanOrEqual(0)
    const body = code.slice(start, code.indexOf('\n})', start))
    expect(body).toContain("process.env.TZ = 'UTC'")
    expect(body).toContain("await import('../DailyReportTab')")
    expect(body.indexOf("process.env.TZ = 'UTC'")).toBeLessThan(
      body.indexOf("await import('../DailyReportTab')"),
    )
  })
})

describe('F1: formatDateTime — 유효 ISO 는 KST `yyyy-MM-dd HH:mm:ss`', () => {
  it('F1-a: UTC 입력 "2026-09-07T00:05:00Z" → "2026-09-07 09:05:00"', () => {
    expect(formatDateTime('2026-09-07T00:05:00Z')).toBe('2026-09-07 09:05:00')
  })

  it('F1-b: 동일 시각의 `+09:00` 입력도 같은 문자열', () => {
    expect(formatDateTime('2026-09-07T09:05:00+09:00')).toBe('2026-09-07 09:05:00')
    expect(formatDateTime('2026-09-07T09:05:00+09:00')).toBe(
      formatDateTime('2026-09-07T00:05:00Z'),
    )
  })

  it('F1-c: 서식은 환경 무관 고정폭 — ICU 로케일 서식(`2026. 9. 7.` / `9시 5분 0초`) 0건', () => {
    const out = formatDateTime('2026-09-07T00:05:00Z')
    expect(out).toMatch(/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/)
    expect(out).not.toContain('. ') // "2026. 9. 7." ICU 서식
    expect(out).not.toContain('시')
    expect(out).not.toContain('오전')
    expect(out).not.toContain('오후')
  })

  it('F1-d: UTC 날짜 경계 — "2026-09-06T23:30:00Z" 는 KST 익일 "2026-09-07 08:30:00"', () => {
    expect(formatDateTime('2026-09-06T23:30:00Z')).toBe('2026-09-07 08:30:00')
  })

  it('F1-e: 자정 직후는 24시제 "00:05:00" (12시제 회귀 차단)', () => {
    expect(formatDateTime('2026-09-07T00:05:00+09:00')).toBe('2026-09-07 00:05:00')
  })
})

describe('F2: 빈 값 표기는 현행 `-` 유지 (이번 결정 범위 밖)', () => {
  it.each([
    ['null', null],
    ['undefined', undefined],
    ['빈 문자열', ''],
  ])('F2-a: %s → "-" (하이픈, em dash 아님)', (_label, value) => {
    const out = formatDateTime(value as string | null | undefined)
    expect(out).toBe('-')
    expect(out).not.toBe('—')
  })
})

describe('F3: 파싱 불가 문자열 → `—` (원문 노출 금지)', () => {
  it('F3-a: "garbage" → "—"', () => {
    const out = formatDateTime('garbage')
    expect(out).toBe('—')
    expect(out).not.toContain('garbage')
    expect(out).not.toContain('Invalid')
  })

  it('F3-b: 날짜처럼 보이지만 파싱 불가한 값도 "—"', () => {
    expect(formatDateTime('2026-13-45T99:99:99Z')).toBe('—')
  })
})

describe('F4: 렌더 — ext 카드 헤더가 새 서식으로 보인다', () => {
  it('F4-a: "생성 2026-09-02 20:20:00 · anthropic · claude-sonnet-5"', async () => {
    server.use(http.get('/api/log-reports', () => HttpResponse.json(wrap([extReport]))))
    render(
      <TestProviders>
        <DailyReportTab />
      </TestProviders>,
    )

    const card = await screen.findByTestId('ext-analysis-card')
    expect(card.textContent).toContain('생성 2026-09-02 20:20:00 · anthropic · claude-sonnet-5')
    // HEAD 의 ICU 서식이 남아 있으면 잡는다.
    expect(card.textContent).not.toContain('2026. 9. 2.')
    expect(card.textContent).not.toContain('20시 20분')
  })
})
