/**
 * cycle414 Red — 정적 가드: KST 규약(F8) · 낡은 도움말 문구 · 탭 설명 문턱 숫자.
 *
 * 명세 = `_workspace/red/cycle414/monitor_spec.md` §2.10(프론트 규약) · §4.1 끝 · §4.2 · §4.5 · §6 C1·C2.
 *
 * | # | 계약 |
 * |---|---|
 * | S1 | 이번 사이클이 고치는·만드는 6파일에 **날짜용** `new Intl.DateTimeFormat`·`toLocale*(…timeZone/hour12)`·로컬타임 getter(`getHours()` 등)·`'Asia/Seoul'`·`'en-CA'`/`'en-GB'` 리터럴 0 |
 * | S2 | 시각을 쓰는 4파일은 `utils/kst` 를 import 한다(단일 진실원 위임) |
 * | S3 | 돈키언 화면 도움말에 cycle405 이전 청산 문구(ATR×2 트레일 · −7% 하드 손절 · 시간 청산 없음) 0 |
 * | S4 | 탭 설명(`STRATEGY_INFO`) — etf_trend 항목 존재 · 숫자 문턱 없음 / 돈키언은 깡토식 청산으로 / 고지로는 숫자·「관찰 모드」 없음 |
 *
 * `toLocaleString()` 전면 금지는 쓸 수 없다 — 숫자 천단위 서식에 같은 메서드를 쓴다(`kst.test.ts` K4 와 같은 판정).
 * 주석은 걷어내고 코드만 본다.
 */
import { describe, expect, it } from 'vitest'
import { existsSync, readFileSync } from 'fs'
import path from 'path'

const SRC = path.join(__dirname, '..', '..')

/** 이번 사이클이 고치는 기존 3파일 + 새로 만드는 3파일. */
const FILES = [
  'components/KojiroMonitor.tsx',
  'components/ScanMonitor.tsx',
  'components/BreakoutCandidateMonitor.tsx',
  'components/StrategyMonitor.tsx',
  'components/StrategySummaryTable.tsx',
  'utils/strategyMonitor.ts',
] as const

/** 시각을 표시·판정하는 파일 — `utils/kst` 위임 필수. */
const MUST_IMPORT_KST = [
  'components/KojiroMonitor.tsx',
  'components/ScanMonitor.tsx',
  'components/BreakoutCandidateMonitor.tsx',
  'utils/strategyMonitor.ts',
] as const

function stripComments(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:])\/\/.*$/gm, '$1')
}

function read(rel: string): string {
  const p = path.join(SRC, rel)
  expect(existsSync(p), `${rel} 가 없다`).toBe(true)
  return readFileSync(p, 'utf-8')
}

function dateLocaleHits(code: string): string[] {
  const lines = code.split('\n')
  const hits: string[] = []
  lines.forEach((line, i) => {
    if (!/toLocale(String|DateString|TimeString)\(/.test(line)) return
    if (/timeZone|hour12|Asia\/Seoul/.test(lines.slice(i, i + 6).join('\n'))) hits.push(`L${i + 1}: ${line.trim()}`)
  })
  return hits
}

describe('S1·S2 — KST 규약(F8): 자체 시각 포맷 금지 · utils/kst 위임', () => {
  it.each(FILES)('%s — 날짜용 Intl/toLocale/로컬 getter/tz 리터럴 0', (rel) => {
    const code = stripComments(read(rel))
    expect(code.match(/new\s+Intl\.DateTimeFormat/g) ?? [], 'new Intl.DateTimeFormat').toEqual([])
    expect(dateLocaleHits(code), '날짜용 toLocale*').toEqual([])
    expect(code.match(/\.get(Hours|Minutes|Seconds|Date|Day|Month|FullYear)\(\)/g) ?? [], '로컬타임 getter').toEqual([])
    expect(code.match(/['"]Asia\/Seoul['"]/g) ?? [], "'Asia/Seoul' 리터럴").toEqual([])
    expect(code.match(/['"]en-(CA|GB)['"]/g) ?? [], "날짜 서식용 'en-CA'/'en-GB'").toEqual([])
  })

  it.each(MUST_IMPORT_KST)('%s — utils/kst 를 import 한다', (rel) => {
    const code = stripComments(read(rel))
    expect(code).toMatch(/from\s+['"](\.\.\/utils\/kst|\.\/kst)['"]/)
  })

  it('ScanMonitor 활성 보드 판정은 kstMinutesOfDay(자체 Intl 포맷터 없음)', () => {
    const code = stripComments(read('components/ScanMonitor.tsx'))
    expect(code).toMatch(/kstMinutesOfDay/)
  })
})

describe('S3 — 돈키언 도움말: cycle405 이전 청산 설명 금지(명세 §4.2 · C2)', () => {
  const STALE = [
    /ATR\(14\)\s*×\s*2\s*트레일링/,
    /하드 손절\s*\(?\s*-7%/,
    /시간 청산 없음/,
    /두 가지 중 하나만 맞으면 매도/,
  ]
  it.each(['components/ScanMonitor.tsx', 'components/StrategyMonitor.tsx'])('%s', (rel) => {
    const code = stripComments(read(rel))
    for (const re of STALE) expect(code, String(re)).not.toMatch(re)
  })
})

describe('S4 — 탭 설명 STRATEGY_INFO(명세 §4.1 끝 · §4.5)', () => {
  it('etf_trend 항목 — ETF·신고가 설명, 숫자 문턱 없음(「숫자는 패널 상단의 현재 설정」)', async () => {
    const { STRATEGY_INFO } = await import('../../utils/strategyInfo')
    const e = STRATEGY_INFO.etf_trend
    expect(e, 'etf_trend 탭 설명이 없다').toBeTruthy()
    const text = `${e.tagline}\n${e.description}`
    expect(text).toMatch(/ETF/)
    expect(text).toMatch(/신고가/)
    expect(text).toMatch(/현재 설정/)
    expect(text.match(/\d+(\.\d+)?\s*%/g) ?? [], '퍼센트 문턱 리터럴').toEqual([])
  })

  it('donchian_swing 항목 — 깡토식 청산(1R·무장), 낡은 「ATR×2 트레일·-7%·시간 손절 없음」 없음', async () => {
    const { STRATEGY_INFO } = await import('../../utils/strategyInfo')
    const text = `${STRATEGY_INFO.donchian_swing.tagline}\n${STRATEGY_INFO.donchian_swing.description}`
    expect(text).toMatch(/1R/)
    expect(text).toMatch(/무장/)
    expect(text).not.toMatch(/ATR\(14\)\s*×\s*2|-7%|시간 손절·강제청산 없음/)
  })
})
