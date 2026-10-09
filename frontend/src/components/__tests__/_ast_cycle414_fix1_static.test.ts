// @vitest-environment node
/**
 * cycle414 보완 1차 Red — 정적 가드 L1(hooks 순서) · L2(지연 로딩).
 *
 * | # | 계약 | 왜 정적인가 |
 * |---|---|---|
 * | L1 | `StrategyMonitor.tsx`·`StrategySummaryTable.tsx` 에 ESLint `react-hooks/rules-of-hooks` 위반 0 — 인라인 `eslint-disable` 로 덮은 것도 센다(`allowInlineConfig: false`) | React 는 훅 0개 → N개(조기 return 뒤 훅)를 「처음 마운트」 로, N개 → 0개를 「훅 호출 0」 으로 봐서 런타임에 터지지 않는다. 1차 검수가 잡은 것도 lint 오류 2건(+ disable 로 덮은 1건)이다 |
 * | L2 | `pages/StrategyFunnel` 을 정적 import 하는 비테스트 모듈 0 — `App.tsx` 의 `lazy(() => import(...))` 만 남는다 | Dashboard·StrategyMonitor 가 정적으로 끌어오면 지연 로딩 청크가 메인 번들에 합쳐진다(vite 경고 — main 에 없던 것). 공유 함수(`extractDailyFinalCounts`·`computeZeroStreak`)는 `utils/` 로 옮긴다 |
 *
 * 주석 안의 import 문은 세지 않는다(주석을 걷어낸 뒤 본다).
 */
import { describe, expect, it } from 'vitest'
import { readFileSync, readdirSync, statSync } from 'fs'
import path from 'path'

const FRONTEND = path.join(__dirname, '..', '..', '..')
const SRC = path.join(FRONTEND, 'src')

function stripComments(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:])\/\/.*$/gm, '$1')
}

function walk(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    const p = path.join(dir, name)
    if (statSync(p).isDirectory()) {
      if (name === '__tests__' || name === 'node_modules') continue
      walk(p, out)
    } else if (/\.(ts|tsx)$/.test(name) && !/\.(test|spec)\.(ts|tsx)$/.test(name) && !name.endsWith('.d.ts')) {
      out.push(p)
    }
  }
  return out
}

describe('L1 — rules-of-hooks(조기 return 뒤 훅 금지)', () => {
  it('StrategyMonitor·StrategySummaryTable 에 rules-of-hooks 위반 0(eslint-disable 로 덮은 것 포함)', async () => {
    const { ESLint } = await import('eslint')
    const eslint = new ESLint({ cwd: FRONTEND, allowInlineConfig: false })
    const results = await eslint.lintFiles([
      'src/components/StrategyMonitor.tsx',
      'src/components/StrategySummaryTable.tsx',
    ])
    const hits = results.flatMap((r) => r.messages
      .filter((m) => m.ruleId === 'react-hooks/rules-of-hooks')
      .map((m) => `${path.basename(r.filePath)}:${m.line} ${m.message.slice(0, 60)}`))
    expect(hits, hits.join('\n')).toEqual([])
  }, 30_000)

  it('rules-of-hooks 를 끄는 인라인 주석 0', () => {
    for (const rel of ['components/StrategyMonitor.tsx', 'components/StrategySummaryTable.tsx']) {
      const src = readFileSync(path.join(SRC, rel), 'utf-8')
      expect(src, rel).not.toMatch(/eslint-disable[^\n]*rules-of-hooks/)
    }
  })
})

describe('L2 — pages/StrategyFunnel 정적 import 0(지연 로딩 보존)', () => {
  it('비테스트 모듈 어디에서도 pages/StrategyFunnel 을 정적으로 import 하지 않는다', () => {
    const target = path.join(SRC, 'pages', 'StrategyFunnel')
    const hits: string[] = []
    for (const file of walk(SRC)) {
      if (path.join(path.dirname(file), path.basename(file).replace(/\.(ts|tsx)$/, '')) === target) continue
      const code = stripComments(readFileSync(file, 'utf-8'))
      const re = /^\s*(?:import|export)\s[^;]*?\bfrom\s*['"]([^'"]+)['"]/gm
      for (let m = re.exec(code); m; m = re.exec(code)) {
        const spec = m[1]
        if (!spec.startsWith('.')) continue
        const resolved = path.join(path.dirname(file), spec).replace(/\.(ts|tsx)$/, '')
        if (resolved === target) hits.push(`${path.relative(SRC, file)} ← ${spec}`)
      }
    }
    expect(hits, hits.join('\n')).toEqual([])
  })
})
