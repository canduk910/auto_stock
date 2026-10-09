/**
 * cycle416 Red — 시장 등락 통계 프론트 텍스트 가드 (FG1~FG5).
 *
 *  FG1 날짜·시각은 `utils/kst.ts` 로만 — 섹션·차트 계산 파일에 `new Date(`·`new Intl.DateTimeFormat`·
 *      `getHours(`·`'Asia/Seoul'` 0건, 섹션은 `utils/kst` 를 import 한다(asof 표시).
 *  FG2 색은 CSS 변수 — 섹션 소스에 hex 리터럴 0건, 상승 `var(--color-red-500)` · 하락 `var(--color-blue-500)`.
 *  FG3 `useMacro.ts`(원본 이식 파일)는 손대지 않는다 — 시장 등락 훅은 `hooks/useMarketBreadth.ts` 따로.
 *  FG4 API 경로는 `/market/breadth` — `/macro/` 밑이 아니다(그 접두사는 nginx·vite 가 macro 컨테이너로 보낸다).
 *  FG5 e2e `api-mocks.ts` 에 `**\/api/market/breadth` 라우트 등록 — `/macro` 마운트 시 ECONNREFUSED 방지
 *      (`_ast_api_mocks_coverage.test.ts` G-AST12 와 같은 이유).
 *
 * RED: 새 파일 부재 → 읽기 실패.
 */
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'fs'
import path from 'path'

const FRONTEND = path.join(__dirname, '..', '..', '..')
const REPO = path.join(FRONTEND, '..')
const SECTION = path.join(FRONTEND, 'src', 'macro', 'components', 'MarketBreadthSection.tsx')
const CHART = path.join(FRONTEND, 'src', 'macro', 'marketBreadthChart.ts')
const HOOK = path.join(FRONTEND, 'src', 'macro', 'hooks', 'useMarketBreadth.ts')
const USE_MACRO = path.join(FRONTEND, 'src', 'macro', 'hooks', 'useMacro.ts')
const API = path.join(FRONTEND, 'src', 'api', 'market-breadth.ts')
const PAGE = path.join(FRONTEND, 'src', 'macro', 'MacroPage.tsx')
const E2E_MOCKS = path.join(REPO, 'e2e', 'fixtures', 'api-mocks.ts')

const read = (p: string) => readFileSync(p, 'utf-8')
/** 주석 제거(블록·줄) — 주석 속 설명 문장이 가드에 걸리지 않게. */
const code = (p: string) => read(p).replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:])\/\/.*$/gm, '$1')

describe('cycle416 시장 등락 통계 — 프론트 텍스트 가드', () => {
  it.each([SECTION, CHART])('FG1 %s — 날짜를 직접 만들지 않는다', (file) => {
    const src = code(file)
    for (const banned of ['new Date(', 'new Intl.DateTimeFormat', 'getHours(', 'Asia/Seoul']) {
      expect(src.includes(banned), `${path.basename(file)}: \`${banned}\` 금지 — utils/kst.ts 위임`).toBe(false)
    }
  })

  it('FG1b 섹션은 utils/kst 의 formatKstDateTime 으로 기준 시각을 쓴다', () => {
    const src = code(SECTION)
    expect(src).toMatch(/from ['"]\.\.\/\.\.\/utils\/kst['"]/)
    expect(src).toContain('formatKstDateTime')
  })

  it('FG2 색 = CSS 변수, hex 리터럴 0건', () => {
    const src = code(SECTION)
    expect(src).toContain('var(--color-red-500)')
    expect(src).toContain('var(--color-blue-500)')
    expect(src.match(/#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3}\b/g) ?? []).toEqual([])
  })

  it('FG3 useMacro.ts 는 그대로 — 시장 등락 훅은 따로', () => {
    expect(read(USE_MACRO)).not.toMatch(/breadth|Breadth/)
    const hook = code(HOOK)
    expect(hook).toContain('useAsyncState')
    expect(hook).toContain('getMarketBreadth')
    const page = code(PAGE)
    expect(page).toContain('MarketBreadthSection')
    expect(page).toContain('useMarketBreadth')
  })

  it('FG4 API 경로 — /market/breadth, /macro/ 아님, timeout 명시', () => {
    const src = code(API)
    expect(src).toMatch(/['"`]\/market\/breadth['"`]/)
    expect(src).not.toMatch(/['"`]\/macro\//)
    expect(src).toMatch(/timeout:\s*MARKET_BREADTH_TIMEOUT_MS/)
  })

  it('FG5 e2e api-mocks 에 /api/market/breadth 라우트 등록', () => {
    const src = read(E2E_MOCKS)
    expect(src).toMatch(/page\.route\(\s*["'`][^"'`]*\/api\/market\/breadth[^"'`]*["'`]/)
  })
})
