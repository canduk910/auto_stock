/**
 * cycle261 후속(적대 검토) — ScanMonitor 보드 배지 색 별칭 충돌.
 *
 * `src/index.css` 의 하위호환 별칭(green≡teal≡cyan≡sky, purple≡violet≡indigo≡navy)
 * 때문에 `BOARD_META`(pre_nxt=teal, krx_open=sky)와 `activeBoards`(같은 조합)가
 * 서로 다른 보드인데도 같은 hex 로 렌더된다. 두 쌍이 실제로 겹치는 시간창에서 함께
 * 노출된다 — `activeBoards`: pre_nxt(08:00~09:00) ∩ krx_open(08:30~09:00),
 * post_nxt(15:30~20:00) ∩ krx_after(15:30~18:00). 배지가 유일한 구분 단서인 화면에서
 * ΔE=0 는 "구별 불가" 결함이다(디자인 취향이 아니다).
 *
 * 텍스트 계약인 이유 — Tailwind v4 `@theme` 는 빌드 타임 CSS 변수라 jsdom 렌더로는
 * 실제 색을 잴 수 없다. `index.css` 를 fs 로 읽어 각 배지 클래스가 가리키는
 * `--color-<name>-<shade>` 실제 hex 를 비교한다(`designSystem.v2.test.ts` 패턴 답습).
 */
import { describe, expect, it } from 'vitest'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const SELF = fileURLToPath(import.meta.url.split('?')[0])
const COMPONENT_DIR = path.resolve(path.dirname(SELF), '..')
const SCAN_MONITOR = path.join(COMPONENT_DIR, 'ScanMonitor.tsx')
const INDEX_CSS = path.join(COMPONENT_DIR, '..', 'index.css')

function read(file: string): string {
  return fs.readFileSync(file, 'utf8')
}

function themeVar(css: string, name: string): string | null {
  const m = css.match(new RegExp(`--${name}\\s*:\\s*([^;]+);`))
  return m ? m[1].trim().toLowerCase() : null
}

/** `bg-<name>-<shade>` 또는 `text-<name>-<shade>` 토큰이 가리키는 @theme 실제 hex. */
function resolvedHex(css: string, cls: string, prefix: 'bg' | 'text'): string {
  const m = cls.match(new RegExp(`\\b${prefix}-([a-z]+)-(\\d{2,3})\\b`))
  if (!m) throw new Error(`[${prefix}] 클래스에서 색 토큰을 찾지 못했다: ${cls}`)
  const hex = themeVar(css, `color-${m[1]}-${m[2]}`)
  if (!hex) throw new Error(`@theme 에 --color-${m[1]}-${m[2]} 미정의 (cls=${cls})`)
  return hex
}

function assertAllDistinct(
  entries: Array<{ board: string; cls: string }>,
  css: string,
  prefix: 'bg' | 'text',
  label: string,
) {
  const seen = new Map<string, string>()
  const collisions: string[] = []
  for (const { board, cls } of entries) {
    const hex = resolvedHex(css, cls, prefix)
    if (seen.has(hex)) {
      collisions.push(`${board}(${cls}) ↔ ${seen.get(hex)} (둘 다 ${hex})`)
    } else {
      seen.set(hex, board)
    }
  }
  expect(
    collisions,
    `[${label}] ${prefix} 색 충돌(@theme 별칭 해석 후 동일 hex) — 서로 다른 보드가 같은 색:\n${collisions.join('\n')}`,
  ).toEqual([])
}

describe('cycle261 후속 — ScanMonitor 보드 배지, 별칭 해석 후에도 서로 다른 색', () => {
  it('BOARD_META 5개 보드의 chipCls 가 서로 다른 hex 를 가리킨다', () => {
    const src = read(SCAN_MONITOR)
    const css = read(INDEX_CSS)
    const blockMatch = src.match(/const BOARD_META:[^=]*=\s*\{[\s\S]*?\n\}/)
    expect(blockMatch, 'BOARD_META 선언 블록을 찾지 못했다(ScanMonitor.tsx 구조 변경?)').not.toBeNull()
    const entries = [...blockMatch![0].matchAll(/(\w+):\s*\{\s*label:\s*'[^']*',\s*chipCls:\s*'([^']+)'/g)].map(
      (m) => ({ board: m[1], cls: m[2] }),
    )
    expect(entries.length, 'BOARD_META 5개 보드를 모두 파싱하지 못했다').toBe(5)
    assertAllDistinct(entries, css, 'bg', 'BOARD_META')
    assertAllDistinct(entries, css, 'text', 'BOARD_META')
  })

  it('activeBoards(헤더 시간대 배지) 5개도 서로 다른 hex — 08:30~09:00·15:30~18:00 동시 노출 구간 존재', () => {
    const src = read(SCAN_MONITOR)
    const css = read(INDEX_CSS)
    const fnMatch = src.match(/const activeBoards = \(\(\) => \{[\s\S]*?\n {2}\}\)\(\)/)
    expect(fnMatch, 'activeBoards 선언을 찾지 못했다(ScanMonitor.tsx 구조 변경?)').not.toBeNull()
    const entries = [...fnMatch![0].matchAll(/code:\s*'(\w+)'[^}]*color:\s*'([^']+)'/g)].map((m) => ({
      board: m[1],
      cls: m[2],
    }))
    expect(entries.length, 'activeBoards 5개 push 를 모두 파싱하지 못했다').toBe(5)
    assertAllDistinct(entries, css, 'bg', 'activeBoards')
    assertAllDistinct(entries, css, 'text', 'activeBoards')
  })
})
