/**
 * cycle413 Red — 거래일지 MSW 기본 목·타입이 **백엔드 실제 응답 키**와 같다 (handlers.honesty cycle276·411 원칙).
 *
 * 키 정본 = `tests/fixtures/cycle413_journal_shape.json` — 백엔드 `tests/unit/routes/test_cycle413_journal_routes.py::
 * test_r10_*` 가 같은 파일로 라우트 응답을 비교한다. 두 쪽이 한 파일을 보므로 목과 라우트가 갈라질 수 없다.
 *
 * 계약
 *  - JH1: 기본 핸들러 `GET /api/history/journal` 응답이 shape 와 객체마다 키가 정확히 같다(setup 의
 *         `onUnhandledRequest: "error"` — 기본 목이 없으면 일지 탭을 그리는 테스트가 전부 붉어진다).
 *  - JH2: 그 응답에 빈칸 이유 5종(na)이 모두 한 번 이상 나온다(화면 테스트가 5종을 다 그려 보게).
 *  - JH3: 기본 핸들러 `PUT /api/history/journal/notes/:id` = `{anchor_trade_id, body, created_at, updated_at}`.
 *  - JH4: `src/types/journal.ts` 가 interface 들과 shape 의 키를 전부 선언한다.
 *  - JH5: 이름에 journal 이 든 프론트 파일(테스트 제외)에 `dangerouslySetInnerHTML`·새 `Intl.DateTimeFormat` 0
 *         — 메모는 글자 그대로, 시각은 `src/utils/kst.ts` 위임(frontend/CLAUDE.md 「시각적 컨벤션」).
 */
import { describe, expect, it } from 'vitest'
import { readFileSync, readdirSync, statSync } from 'fs'
import path from 'path'

const REPO_ROOT = path.join(__dirname, '..', '..', '..', '..')
const SHAPE: Record<string, string[]> = JSON.parse(
  readFileSync(path.join(REPO_ROOT, 'tests', 'fixtures', 'cycle413_journal_shape.json'), 'utf-8'),
)
const BASE = 'http://localhost:3000/api'

type Obj = Record<string, unknown>

function keysDiff(obj: Obj | null | undefined, kind: string, where: string, bad: string[]) {
  if (obj === null || obj === undefined) return
  const got = Object.keys(obj).sort()
  const want = [...SHAPE[kind]].sort()
  if (JSON.stringify(got) !== JSON.stringify(want)) {
    bad.push(`${where}(${kind}): +[${got.filter((k) => !want.includes(k))}] -[${want.filter((k) => !got.includes(k))}]`)
  }
}

function checkShape(data: Obj): string[] {
  const bad: string[] = []
  keysDiff(data, 'response', 'data', bad)
  for (const k of ['record_start', 'filters', 'counts']) keysDiff(data[k] as Obj, k, k, bad)
  const cards = data.cards as Obj[]
  cards.forEach((c, i) => {
    const p = `cards[${i}]`
    keysDiff(c, 'card', p, bad)
    keysDiff(c.pnl as Obj, 'pnl', `${p}.pnl`, bad)
    const e = c.entry as Obj
    keysDiff(e, 'entry', `${p}.entry`, bad)
    ;(e.orders as Obj[]).forEach((ln, j) => {
      keysDiff(ln, 'order_line', `${p}.entry.orders[${j}]`, bad)
      keysDiff(ln.judge as Obj, 'judge', `${p}.entry.orders[${j}].judge`, bad)
      keysDiff(ln.slip_order as Obj, 'slip', `${p}.entry.orders[${j}].slip_order`, bad)
      keysDiff(ln.slip_judge as Obj, 'slip', `${p}.entry.orders[${j}].slip_judge`, bad)
    })
    keysDiff(e.reason as Obj, 'reason', `${p}.entry.reason`, bad)
    keysDiff(e.initial_stop as Obj, 'stop_point', `${p}.entry.initial_stop`, bad)
    keysDiff((e.initial_stop as Obj).first_seen as Obj, 'first_seen', `${p}.entry.initial_stop.first_seen`, bad)
    keysDiff(e.target as Obj, 'target', `${p}.entry.target`, bad)
    ;(c.exits as Obj[]).forEach((x, j) => {
      keysDiff(x, 'exit_line', `${p}.exits[${j}]`, bad)
      keysDiff(x.judge as Obj, 'judge', `${p}.exits[${j}].judge`, bad)
      keysDiff(x.slip_order as Obj, 'slip', `${p}.exits[${j}].slip_order`, bad)
      keysDiff(x.slip_judge as Obj, 'slip', `${p}.exits[${j}].slip_judge`, bad)
      keysDiff(x.reason as Obj, 'reason', `${p}.exits[${j}].reason`, bad)
    })
    const st = c.stop_track as Obj
    keysDiff(st, 'stop_track', `${p}.stop_track`, bad)
    ;(st.rows as Obj[]).forEach((r, j) => keysDiff(r, 'stop_row', `${p}.stop_track.rows[${j}]`, bad))
    const co = c.costs as Obj
    keysDiff(co, 'costs', `${p}.costs`, bad)
    ;(co.exits as Obj[]).forEach((x, j) => keysDiff(x, 'cost_exit', `${p}.costs.exits[${j}]`, bad))
    const ex = c.excursion as Obj
    keysDiff(ex, 'excursion', `${p}.excursion`, bad)
    keysDiff(ex.mfe as Obj, 'ex_point', `${p}.excursion.mfe`, bad)
    keysDiff(ex.mae as Obj, 'ex_point', `${p}.excursion.mae`, bad)
    keysDiff(c.note as Obj, 'note', `${p}.note`, bad)
  })
  return bad
}

function collectNa(v: unknown, out: Set<string>) {
  if (Array.isArray(v)) v.forEach((x) => collectNa(x, out))
  else if (v && typeof v === 'object') {
    for (const [k, x] of Object.entries(v as Obj)) {
      if ((k === 'na' || k.endsWith('_na')) && typeof x === 'string') out.add(x)
      collectNa(x, out)
    }
  }
}

function walk(dir: string, out: string[] = []): string[] {
  for (const name of readdirSync(dir)) {
    const full = path.join(dir, name)
    if (statSync(full).isDirectory()) {
      if (name === '__tests__' || name === 'node_modules') continue
      walk(full, out)
    } else if (/\.(ts|tsx)$/.test(name)) out.push(full)
  }
  return out
}

describe('cycle413 — 거래일지 MSW 기본 목·타입 정직화', () => {
  it('JH1·JH2: 기본 GET 목 = shape 키 · 빈칸 이유 5종', async () => {
    const res = await fetch(`${BASE}/history/journal`)
    const body = (await res.json()) as { success: boolean; data: Obj }
    expect(body.success).toBe(true)
    expect(checkShape(body.data)).toEqual([])
    expect((body.data.cards as Obj[]).length).toBeGreaterThan(0)
    const na = new Set<string>()
    collectNa(body.data, na)
    for (const k of SHAPE.na_kinds) expect([...na]).toContain(k)
  })

  it('JH3: 기본 PUT 목 = note_put 키', async () => {
    const res = await fetch(`${BASE}/history/journal/notes/aaaaaaaa-0000-4000-8000-000000000001`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ body: '메모' }),
    })
    const body = (await res.json()) as { success: boolean; data: Obj }
    expect(body.success).toBe(true)
    expect(Object.keys(body.data).sort()).toEqual([...SHAPE.note_put].sort())
  })

  it('JH4: src/types/journal.ts 가 interface 와 shape 키를 선언한다', () => {
    const src = readFileSync(path.join(REPO_ROOT, 'frontend', 'src', 'types', 'journal.ts'), 'utf-8')
    for (const t of ['NaKind', 'ValSrc', 'CostStatus']) expect(src).toMatch(new RegExp(`export type ${t}\\b`))
    for (const i of ['JournalResponse', 'JournalCard', 'OrderLine', 'ExitLine', 'Slip', 'Reason', 'StopPoint',
      'Target', 'StopTrack', 'StopRow', 'Costs', 'Excursion', 'ExPoint']) {
      expect(src).toMatch(new RegExp(`export interface ${i}\\b`))
    }
    for (const [kind, keys] of Object.entries(SHAPE)) {
      if (kind.startsWith('_') || kind === 'na_kinds') continue
      for (const k of keys) expect(src, `${kind}.${k}`).toMatch(new RegExp(`\\b${k}\\??:`))
    }
  })

  it('JH5: journal 파일에 dangerouslySetInnerHTML · 새 Intl.DateTimeFormat 금지', () => {
    const files = walk(path.join(REPO_ROOT, 'frontend', 'src')).filter((f) => /journal/i.test(path.basename(f)))
    // 표기표·타입·픽스처 + 화면 컴포넌트 — 0 개면 이 가드가 공허하다.
    expect(files.length).toBeGreaterThanOrEqual(3)
    for (const f of files) {
      const src = readFileSync(f, 'utf-8')
      expect(src, f).not.toMatch(/dangerouslySetInnerHTML/)
      expect(src, f).not.toMatch(/new\s+Intl\.DateTimeFormat/)
    }
  })
})
