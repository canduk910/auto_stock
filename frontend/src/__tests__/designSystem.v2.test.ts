/**
 * cycle261 — DK Stock 디자인시스템 v2 (가을 팔레트 + Gmarket Sans) 텍스트 계약 가드.
 *
 * 명세: `_workspace/specs/cycle261_dk_stock_design_v2.md` §테스트 (a)~(e)
 * 정본 입력: `dk-stock-design/handoff/frontend/src/{index.css, utils/pnlColor.ts.txt,
 *            types/strategy.ts.txt, App.tsx.patch.md}`
 *
 * 왜 텍스트 계약인가 —
 *   Tailwind v4 `@theme` 는 빌드 타임에 CSS 변수로 컴파일되므로 jsdom 렌더로는
 *   "팔레트가 실제로 새 값인지" 를 잴 수 없다. 그래서 이 가드는 정본 소스 파일을
 *   **fs 로 직접 읽어** 두 정본(index.css @theme ↔ pnlColor.ts / strategy.ts) 사이의
 *   드리프트와 하드코딩 hex 잔존을 텍스트 수준에서 봉인한다.
 *
 * 설계 금기 준수 —
 *   - 소스 sha 리터럴 핀 없음(내용이 바뀌면 계약만 다시 읽는다).
 *   - `git grep`/`git ls-files` 를 쓰지 않는다 — 미추적 신규 파일을 놓치므로 `fs` 재귀로 센다.
 *   - TZ/ICU/시계에 의존하지 않는다.
 *   - (c) 전수 스캔은 **이 파일 자신을 제외**한다(검색 패턴 리터럴을 보유하므로).
 */
import { describe, expect, it } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { PROFIT_HEX, LOSS_HEX, NEUTRAL_HEX } from '../utils/pnlColor'
import { STRATEGY_COLORS, getStrategyColor } from '../types/strategy'

// ── 경로 (cwd 비의존) ────────────────────────────────────────────────────────
const SELF = fileURLToPath(import.meta.url.split('?')[0])
const SRC_ROOT = path.resolve(path.dirname(SELF), '..')
const FRONTEND_ROOT = path.resolve(SRC_ROOT, '..')
const INDEX_CSS = path.join(SRC_ROOT, 'index.css')
const APP_TSX = path.join(SRC_ROOT, 'App.tsx')
const FONT_DIR = path.join(FRONTEND_ROOT, 'public', 'fonts')

const FONT_WEIGHTS = ['Light', 'Medium', 'Bold'] as const

function read(file: string): string {
  return fs.readFileSync(file, 'utf8')
}

function rel(file: string): string {
  return path.relative(FRONTEND_ROOT, file)
}

/** `src/**` 재귀 수집 — .ts/.tsx 전수, 이 파일 자신은 제외. */
function collectSourceFiles(dir: string, out: string[] = []): string[] {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name)
    if (entry.isDirectory()) {
      collectSourceFiles(full, out)
      continue
    }
    if (!entry.isFile()) continue
    if (!/\.tsx?$/.test(entry.name)) continue
    if (path.resolve(full) === SELF) continue // 자기 파일 = 검색 패턴 보유
    out.push(full)
  }
  return out
}

/** `@theme` 에 선언된 CSS 변수 값(소문자, 세미콜론 앞까지). 없으면 null. */
function themeVar(css: string, name: string): string | null {
  const m = css.match(new RegExp(`--${name}\\s*:\\s*([^;]+);`))
  return m ? m[1].trim().toLowerCase() : null
}

function countOf(text: string, needle: string): number {
  return text.split(needle).length - 1
}

// ── (a) src/index.css — 서체 + @theme 팔레트 ─────────────────────────────────
describe('cycle261 (a) src/index.css — Gmarket Sans @font-face + @theme 팔레트', () => {
  it('@font-face 3개 + public/fonts TTF 경로 3개를 선언한다', () => {
    const css = read(INDEX_CSS)
    expect(
      countOf(css, '@font-face'),
      '[cycle261 (a)] index.css 에 @font-face 3개(Light/Medium/Bold)가 있어야 한다.',
    ).toBe(3)
    for (const w of FONT_WEIGHTS) {
      expect(
        css,
        `[cycle261 (a)] @font-face src 가 url('/fonts/GmarketSans${w}.ttf') 를 가리켜야 한다.`,
      ).toContain(`url('/fonts/GmarketSans${w}.ttf')`)
    }
    expect(css, '[cycle261 (a)] font-display: swap 누락').toContain('font-display')
  })

  it('@theme 의 --font-sans 첫 패밀리가 Gmarket Sans, --font-brand 도 정의된다', () => {
    const css = read(INDEX_CSS)
    expect(css, '[cycle261 (a)] @theme 블록 부재').toMatch(/@theme\s*\{/)

    const fontSans = themeVar(css, 'font-sans')
    expect(fontSans, '[cycle261 (a)] --font-sans 미정의').not.toBeNull()
    const firstFamily = (fontSans ?? '').split(',')[0].trim().replace(/^['"]|['"]$/g, '')
    expect(
      firstFamily,
      '[cycle261 (a)] --font-sans 의 첫 패밀리가 Gmarket Sans 여야 한다(본문 서체 정본).',
    ).toBe('gmarket sans')

    const fontBrand = themeVar(css, 'font-brand')
    expect(fontBrand, '[cycle261 (a)] --font-brand 미정의 (로고타입 font-brand 사용)').not.toBeNull()
    expect(fontBrand ?? '').toContain('gmarket sans')
  })

  it('--color-pnl-{profit,loss,flat} 이 pnlColor.ts 의 3상수와 동일 값이다 (두 정본 드리프트 방지)', () => {
    const css = read(INDEX_CSS)
    const pairs: Array<[string, string, string]> = [
      ['color-pnl-profit', PROFIT_HEX, 'PROFIT_HEX'],
      ['color-pnl-loss', LOSS_HEX, 'LOSS_HEX'],
      ['color-pnl-flat', NEUTRAL_HEX, 'NEUTRAL_HEX'],
    ]
    for (const [varName, hex, constName] of pairs) {
      expect(
        themeVar(css, varName),
        `[cycle261 (a)] index.css --${varName} 가 pnlColor.ts ${constName}(${hex}) 와 달라지면 ` +
          'pnlColorClass 가 반환하는 시맨틱 클래스와 style hex 가 화면에서 갈라진다.',
      ).toBe(hex.toLowerCase())
    }
  })
})

// ── (b) public/fonts — TTF 3개 실재 ──────────────────────────────────────────
describe('cycle261 (b) public/fonts — Gmarket Sans TTF 3개', () => {
  it.each(FONT_WEIGHTS)('GmarketSans%s.ttf 가 존재하고 1MB 초과다', (w) => {
    const file = path.join(FONT_DIR, `GmarketSans${w}.ttf`)
    expect(fs.existsSync(file), `[cycle261 (b)] ${rel(file)} 부재 — @font-face 가 404 를 문다.`).toBe(
      true,
    )
    expect(
      fs.statSync(file).size,
      `[cycle261 (b)] ${rel(file)} 크기가 1MB 이하 — LFS 포인터/빈 파일 의심.`,
    ).toBeGreaterThan(1_000_000)
  })
})

// ── (c) 구 하드코딩 hex 전수 소탕 ────────────────────────────────────────────
describe('cycle261 (c) src/**/*.{ts,tsx} — 구 팔레트 hex 4종 0건', () => {
  // 대소문자 무관. 테스트 파일도 포함한다 — 기대값이 구 hex 로 남아 있으면
  // "테스트는 초록인데 화면은 새 팔레트" 라는 위장 초록이 만들어진다.
  const LEGACY_HEX = ['#FF3333', '#3366FF', '#333333', '#2563eb']

  it('구 hex 리터럴이 소스·테스트 어디에도 남지 않는다', () => {
    const hits: string[] = []
    for (const file of collectSourceFiles(SRC_ROOT)) {
      const lines = read(file).split('\n')
      lines.forEach((line, idx) => {
        const lower = line.toLowerCase()
        for (const hex of LEGACY_HEX) {
          if (lower.includes(hex.toLowerCase())) {
            hits.push(`${rel(file)}:${idx + 1}  ${hex}  |  ${line.trim().slice(0, 120)}`)
          }
        }
      })
    }
    expect(
      hits,
      `[cycle261 (c)] 구 팔레트 hex 잔존 ${hits.length}건:\n${hits.join('\n')}`,
    ).toEqual([])
  })
})

// ── (d) types/strategy.ts — 전략 7색 + @theme 변수 실재 ──────────────────────
describe('cycle261 (d) STRATEGY_COLORS — 명세 hex 7키 + 클래스↔@theme 정합', () => {
  const EXPECTED_HEX: Record<string, string> = {
    momentum: '#3d73b7',
    volatility_breakout: '#364c6d',
    long_tail_volatility: '#b39364',
    donchian_swing: '#488eb4',
    bull_flag_breakout: '#c34a36',
    vcp_breakout: '#9d6644',
    kojiro: '#141c2b',
  }
  const EXPECTED_DEFAULT_HEX = '#74716a'

  it('7 전략 키 전수 + hex 가 명세 값과 일치한다', () => {
    expect(Object.keys(STRATEGY_COLORS).sort()).toEqual(Object.keys(EXPECTED_HEX).sort())
    for (const [key, hex] of Object.entries(EXPECTED_HEX)) {
      expect(
        STRATEGY_COLORS[key].hex.toLowerCase(),
        `[cycle261 (d)] ${key} hex 불일치 — Recharts/배지 색의 단일 진실원.`,
      ).toBe(hex)
    }
  })

  it('미지 전략 폴백 hex 가 gray-500(#74716a) 이다', () => {
    expect(getStrategyColor('__unknown_strategy__').hex.toLowerCase()).toBe(EXPECTED_DEFAULT_HEX)
  })

  it('bg/text/badge 의 모든 색 이름이 index.css @theme 에 --color-<name>-<shade> 로 정의돼 있다', () => {
    const css = read(INDEX_CSS)
    const TOKEN = /\b(?:bg|text|border)-([a-z]+)-(\d{2,3})\b/g

    const entries: Array<[string, { bg: string; text: string; badge: string }]> = [
      ...Object.entries(STRATEGY_COLORS).map(
        ([k, v]) => [k, v] as [string, { bg: string; text: string; badge: string }],
      ),
      ['__default__', getStrategyColor('__unknown_strategy__')],
    ]

    const missing: string[] = []
    for (const [key, color] of entries) {
      for (const cls of [color.bg, color.text, color.badge]) {
        for (const m of cls.matchAll(TOKEN)) {
          const varName = `--color-${m[1]}-${m[2]}`
          if (!css.includes(`${varName}:`)) missing.push(`${key}: "${cls}" → ${varName}`)
        }
      }
    }
    expect(
      missing,
      `[cycle261 (d)] @theme 미정의 색 토큰 ${missing.length}건 (별칭 정의도 인정):\n${missing.join('\n')}`,
    ).toEqual([])
  })
})

// ── (e) App.tsx — 브랜드/배경/배너 + accentColor 5곳 ────────────────────────
describe('cycle261 (e) App.tsx — DK Stock 브랜드 · beige 배경 · sky 배너', () => {
  it('로고타입이 DK Stock 2곳(font-brand)이고 AutoStock 은 0건이다', () => {
    const app = read(APP_TSX)
    expect(countOf(app, 'AutoStock'), '[cycle261 (e)] 구 브랜드명 AutoStock 잔존').toBe(0)
    expect(countOf(app, 'DK Stock'), '[cycle261 (e)] 로고타입 DK Stock 은 PC/모바일 2곳').toBe(2)
    expect(
      countOf(app, 'font-brand'),
      '[cycle261 (e)] 로고타입 2곳에 font-brand 적용(--font-brand 사용)',
    ).toBeGreaterThanOrEqual(2)
  })

  it('AppShell 루트 배경이 bg-beige-100(--surface-page) 이다', () => {
    const app = read(APP_TSX)
    expect(countOf(app, 'bg-beige-100'), '[cycle261 (e)] 루트 배경 bg-beige-100 1곳').toBe(1)
    expect(
      countOf(app, 'min-h-screen bg-gray-100'),
      '[cycle261 (e)] 루트의 구 배경 bg-gray-100 잔존 (다른 bg-gray-100 은 무접촉)',
    ).toBe(0)
  })

  it('EnvBanner 모의투자 배지가 bg-sky-600 이다', () => {
    const app = read(APP_TSX)
    expect(countOf(app, 'bg-sky-600'), '[cycle261 (e)] EnvBanner vts 배지 bg-sky-600').toBe(1)
    expect(countOf(app, 'bg-green-600'), '[cycle261 (e)] 구 bg-green-600 잔존').toBe(0)
  })
})

describe('cycle261 (e2) 슬라이더 accentColor — 5곳 모두 var(--color-navy-600)', () => {
  // 명세 §행위 5: App.tsx 1 + TradeAmountFilterCard 1 + CashUsageRatioCard 1 + PriceFilterCard 2.
  // hex 리터럴 대신 CSS 변수를 쓰는 이유 = @theme 이 단일 진실원이고, 팔레트를 다시
  // 조정할 때 5곳을 각각 고치면 반드시 하나가 뒤처진다.
  const EXPECTED = 'var(--color-navy-600)'

  it('literal accentColor 는 정확히 5곳이고 값이 전부 동일하다', () => {
    const ACCENT = /accentColor:\s*(['"])([^'"]*)\1/g
    const sites: Array<{ file: string; value: string }> = []
    for (const file of collectSourceFiles(SRC_ROOT)) {
      for (const m of read(file).matchAll(ACCENT)) {
        sites.push({ file: rel(file), value: m[2] })
      }
    }

    expect(
      sites.length,
      `[cycle261 (e2)] literal accentColor 사이트 수 불일치 — 발견:\n${sites
        .map((s) => `${s.file} = ${s.value}`)
        .join('\n')}`,
    ).toBe(5)

    const wrong = sites.filter((s) => s.value !== EXPECTED)
    expect(
      wrong,
      `[cycle261 (e2)] accentColor 값이 ${EXPECTED} 가 아닌 곳 ${wrong.length}건:\n${wrong
        .map((s) => `${s.file} = ${s.value}`)
        .join('\n')}`,
    ).toEqual([])
  })
})
