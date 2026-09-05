/**
 * cycle261 후속(적대 검토) — 별칭 재정의 후 배경색 구분이 거의 사라진 배지 쌍.
 *
 * `index.css` 별칭(amber/yellow→beige) 이후 다음 두 쌍은 배경색이 거의 같아지고
 * 구분이 글자색 채도 차이 하나에만 의존하게 됐다(실측 대비는 충분하지만 종전보다
 * 훨씬 약함):
 *   - `PortfolioRiskCard` 계좌 게이트 배지: "경고"(amber→beige-100) vs "정상"(gray-100)
 *   - `TradeHistoryGrid` 거래상태 배지: "대기"(yellow→beige-100) vs "부분체결"(orange→brown-100)
 *
 * sRGB 유클리드 거리(간이 지표, 완전한 ΔE2000 은 아니다)로 "거의 같은 배경"을 계측한다
 * — 완벽한 지각 색차 공식을 재현하는 대신, 종전(결함) 값보다는 명확히 높고 실제
 * 시각적으로 분리되는 지점을 임계로 못박는다.
 */
import { describe, expect, it } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const SELF = fileURLToPath(import.meta.url.split('?')[0])
const COMPONENT_DIR = path.resolve(path.dirname(SELF), '..')
const INDEX_CSS = path.join(COMPONENT_DIR, '..', 'index.css')
const PORTFOLIO_RISK_CARD = path.join(COMPONENT_DIR, 'PortfolioRiskCard.tsx')
const TRADE_HISTORY_GRID = path.join(COMPONENT_DIR, 'TradeHistoryGrid.tsx')

// 배경 구분이 "거의 사라졌다" 고 판단하는 sRGB 유클리드 거리 하한. 종전(결함) 값들은
// 전부 이 아래(정상/경고 ≈10.5, 대기/부분체결 ≈12.0)였고, 시정 후 값은 전부 이 위(≥35)다.
const MIN_BG_DISTANCE = 25

function read(file: string): string {
  return fs.readFileSync(file, 'utf8')
}

function themeVar(css: string, name: string): string | null {
  const m = css.match(new RegExp(`--${name}\\s*:\\s*([^;]+);`))
  return m ? m[1].trim().toLowerCase() : null
}

function resolvedBgHex(css: string, cls: string): string {
  const m = cls.match(/\bbg-([a-z]+)-(\d{2,3})\b/)
  if (!m) throw new Error(`bg 클래스에서 색 토큰을 찾지 못했다: ${cls}`)
  const hex = themeVar(css, `color-${m[1]}-${m[2]}`)
  if (!hex) throw new Error(`@theme 에 --color-${m[1]}-${m[2]} 미정의 (cls=${cls})`)
  return hex
}

function hexToRgb(hex: string): [number, number, number] {
  const h = hex.replace('#', '')
  return [parseInt(h.slice(0, 2), 16), parseInt(h.slice(2, 4), 16), parseInt(h.slice(4, 6), 16)]
}

function rgbDistance(hexA: string, hexB: string): number {
  const [r1, g1, b1] = hexToRgb(hexA)
  const [r2, g2, b2] = hexToRgb(hexB)
  return Math.sqrt((r1 - r2) ** 2 + (g1 - g2) ** 2 + (b1 - b2) ** 2)
}

function extractLiteral(src: string, pattern: RegExp, what: string): string {
  const m = src.match(pattern)
  expect(m, `[${what}] 패턴을 찾지 못했다(컴포넌트 구조 변경?)`).not.toBeNull()
  return m![1]
}

describe('cycle261 후속 — PortfolioRiskCard 계좌 게이트 배지 배경 구분', () => {
  it('"경고" 배경이 "정상" 배경과 충분히 구분된다', () => {
    const src = read(PORTFOLIO_RISK_CARD)
    const css = read(INDEX_CSS)

    const normalCls = extractLiteral(src, /let badgeClass = '([^']+)'/, '정상 badgeClass 기본값')
    const warnCls = extractLiteral(
      src,
      /badgeText = '경고'[\s\S]*?badgeClass = '([^']+)'/,
      '경고 badgeClass',
    )

    const normalHex = resolvedBgHex(css, normalCls)
    const warnHex = resolvedBgHex(css, warnCls)
    const distance = rgbDistance(normalHex, warnHex)

    expect(
      distance,
      `[PortfolioRiskCard] "정상"(${normalCls}=${normalHex}) ↔ "경고"(${warnCls}=${warnHex}) ` +
        `배경 거리 ${distance.toFixed(1)} < ${MIN_BG_DISTANCE} — 별칭 재정의 후 구분이 거의 사라졌다`,
    ).toBeGreaterThanOrEqual(MIN_BG_DISTANCE)
  })
})

describe('cycle261 후속 — TradeHistoryGrid 거래상태 배지 배경 구분', () => {
  it('"대기"(PENDING) 배경이 "부분체결"(PARTIAL) 배경과 충분히 구분된다', () => {
    const src = read(TRADE_HISTORY_GRID)
    const css = read(INDEX_CSS)

    const pendingCls = extractLiteral(src, /PENDING:\s*\{[^}]*cls:\s*'([^']+)'/, 'PENDING cls')
    const partialCls = extractLiteral(src, /PARTIAL:\s*\{[^}]*cls:\s*'([^']+)'/, 'PARTIAL cls')

    const pendingHex = resolvedBgHex(css, pendingCls)
    const partialHex = resolvedBgHex(css, partialCls)
    const distance = rgbDistance(pendingHex, partialHex)

    expect(
      distance,
      `[TradeHistoryGrid] "대기"(${pendingCls}=${pendingHex}) ↔ "부분체결"(${partialCls}=${partialHex}) ` +
        `배경 거리 ${distance.toFixed(1)} < ${MIN_BG_DISTANCE} — 별칭 재정의 후 구분이 거의 사라졌다`,
    ).toBeGreaterThanOrEqual(MIN_BG_DISTANCE)
  })
})
