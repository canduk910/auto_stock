/**
 * cycle261 후속(적대 검토) — IntegrationToggleCard 배지 색 별칭 충돌.
 *
 * `index.css` 별칭(emerald≡blue) 때문에 토글 ON 상태 배지(`stateBadgeClass`,
 * emerald)와 소스 배지(`sourceBadgeClass`, source==='db' 일 때 blue)가 같은 카드
 * 안에서 실제로 같은 hex 로 렌더된다 — "활성" 뜻의 배지와 "DB 값 사용 중" 뜻의 배지가
 * 구별 불가능해진다.
 *
 * 텍스트 계약 — Tailwind @theme 은 빌드 타임 CSS 변수라 jsdom 렌더로 실제 색을 잴 수
 * 없다. 컴포넌트 소스에서 세 배지 클래스 리터럴을 파싱해 `index.css` 의 실제
 * `--color-*-*` 값으로 해석한 뒤 비교한다.
 */
import { describe, expect, it } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const SELF = fileURLToPath(import.meta.url.split('?')[0])
const COMPONENT_DIR = path.resolve(path.dirname(SELF), '..')
const COMPONENT_FILE = path.join(COMPONENT_DIR, 'IntegrationToggleCard.tsx')
const INDEX_CSS = path.join(COMPONENT_DIR, '..', 'index.css')

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

function extractLiteral(src: string, pattern: RegExp, what: string): string {
  const m = src.match(pattern)
  expect(m, `[${what}] 패턴을 찾지 못했다(IntegrationToggleCard.tsx 구조 변경?)`).not.toBeNull()
  return m![1]
}

describe('cycle261 후속 — IntegrationToggleCard 배지, "활성" 상태가 다른 의미 배지와 겹치지 않는다', () => {
  it('toggle ON 배지(stateBadgeClass) 배경이 source=db 배지·SOFT 모드 배지와 다른 hex다', () => {
    const src = read(COMPONENT_FILE)
    const css = read(INDEX_CSS)

    const stateOnCls = extractLiteral(
      src,
      /const stateBadgeClass = data\.enabled\s*\n?\s*\?\s*'([^']+)'/,
      'stateBadgeClass(ON)',
    )
    const sourceDbCls = extractLiteral(
      src,
      /const sourceBadgeClass =\s*\n?\s*data\.source === 'db'\s*\n?\s*\?\s*'([^']+)'/,
      'sourceBadgeClass(db)',
    )
    const modeBadgeBlock = extractLiteral(
      src,
      /(const modeBadgeClass: Record<BuyBlockMode, string> = \{[\s\S]*?\n {2}\})/,
      'modeBadgeClass 블록',
    )
    const modeSoftCls = extractLiteral(modeBadgeBlock, /SOFT:\s*'([^']+)'/, 'modeBadgeClass(SOFT)')

    const stateHex = resolvedBgHex(css, stateOnCls)
    const sourceHex = resolvedBgHex(css, sourceDbCls)
    const modeHex = resolvedBgHex(css, modeSoftCls)

    expect(
      stateHex,
      `[IntegrationToggleCard] 토글 ON 배지("${stateOnCls}"=${stateHex})가 ` +
        `source=db 배지("${sourceDbCls}"=${sourceHex})와 같은 색 — 별칭 충돌(cycle261 후속)`,
    ).not.toBe(sourceHex)
    expect(
      stateHex,
      `[IntegrationToggleCard] 토글 ON 배지("${stateOnCls}"=${stateHex})가 ` +
        `SOFT 모드 배지("${modeSoftCls}"=${modeHex})와 같은 색 — 별칭 충돌(cycle261 후속)`,
    ).not.toBe(modeHex)
  })
})
