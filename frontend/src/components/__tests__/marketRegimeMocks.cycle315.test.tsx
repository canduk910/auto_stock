/**
 * cycle315 (2026-09-19) — 시장 레짐 목 정합 가드.
 *
 * 레짐 출처가 우리 macro 컨테이너로 바뀌면서 카드에서 죽은 키(neutral/aggressive)를
 * 지웠다. 목이 그 죽은 값을 계속 먹이면 카드는 "비활성" 폴백 배지로 떨어지고, 아무 테스트도
 * 붉어지지 않은 채 e2e 만 조용히 다른 화면을 본다 — 「테스트 규약 5」(목은 의도한 계약이
 * 아니라 실제 응답을 담는다)가 막으려던 바로 그 형태다.
 *
 * 실측 출처 = 우리 macro 컨테이너 `GET /api/macro/macro-cycle` (2026-09-19 07:30 KST):
 *   regime=defensive · cash_min=75 · vix=14.81 · buffett_ratio=2.626 · fear_greed_score=69.0
 *   · cycle.phase=expansion
 */
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'

import MarketRegimeCard from '../MarketRegimeCard'
import { TestProviders } from '../../test/providers'

const SELF = fileURLToPath(import.meta.url.split('?')[0])
const FRONTEND_SRC = path.resolve(path.dirname(SELF), '..', '..')
const REPO_ROOT = path.resolve(FRONTEND_SRC, '..', '..')
const API_MOCKS = path.join(REPO_ROOT, 'e2e', 'fixtures', 'api-mocks.ts')
const MSW_HANDLERS = path.join(FRONTEND_SRC, 'test', 'handlers.ts')

function read(file: string): string {
  return fs.readFileSync(file, 'utf8')
}

/** 소스에서 `**<endpoint>` 혹은 `${base}<path>` 라우트 뒤 블록을 대략 잘라 온다. */
function sliceAfter(source: string, marker: string, length = 900): string {
  const i = source.indexOf(marker)
  expect(i, `목 소스에서 ${marker} 를 찾지 못했다`).toBeGreaterThan(-1)
  return source.slice(i, i + length)
}

/** `//` 줄 주석을 제거한다 — 주석 속 예시 코드(`regime:"neutral"` 처럼 옛 값을 설명하는
 *  인용)까지 부정 단언에 걸리면 실제 목이 아니라 그 목을 설명하는 글에서 거짓 실패가 난다. */
function stripLineComments(source: string): string {
  return source
    .split('\n')
    .map((line) => {
      const idx = line.indexOf('//')
      return idx === -1 ? line : line.slice(0, idx)
    })
    .join('\n')
}

/**
 * 죽은 레짐 값 — **`regime` 키(정확히 이 이름)에 물린 값만** 본다. 단순 부분 문자열
 * `"neutral"` 검사는 `regime.fg_level`(Fear & Greed 수준, 실재하는 별개 필드) 같은
 * 무관한 키에서도 걸려 거짓 실패를 낸다(실측: `handlers.ts` 의 `macro-cycle` 픽스처가
 * `fg_level: "neutral"` 을 정당하게 담고 있다). `regime_desc` 처럼 밑줄로 이어지는
 * 키도 `regime:` 리터럴이 아니라서 매칭되지 않는다.
 */
const DEAD_REGIME_VALUE_RE = /\bregime:\s*"(neutral|aggressive)"/

describe('cycle315: 시장 레짐 목 정합', () => {
  it('FE-M1: e2e api-mocks 의 /api/market-regime/current 가 실측값을 담는다', () => {
    const block = sliceAfter(read(API_MOCKS), '"**/api/market-regime/current"')
    expect(block).toContain('regime: "defensive"')
    expect(block).toContain('cash_min: 75')
    expect(block).toContain('enabled: true')
    expect(block).toContain('buffett_ratio: 2.626')
    expect(block).toContain('vix: 14.81')
  })

  it('FE-M2: MSW handlers 에 /market-regime/* 핸들러가 있고 같은 실측값을 담는다', () => {
    const source = read(MSW_HANDLERS)
    expect(source).toContain('`${base}/market-regime/current`')
    expect(source).toContain('`${base}/market-regime/history`')
    expect(source).toContain('`${base}/market-regime/auto-adjust`')

    const block = sliceAfter(source, '`${base}/market-regime/current`')
    expect(block).toContain('regime: "defensive"')
    expect(block).toContain('cash_min: 75')
    expect(block).toContain('buffett_ratio: 2.626')
  })

  // cycle315 후속(적대 검토) — sliceAfter 의 고정 900자 창은 긍정 단언에는 안전하지만
  // (창이 짧아지면 시끄럽게 실패), 부정 단언(neutral/aggressive 부재)에는 위험하다.
  // 죽은 값이 창 밖으로 밀려나면 아무 신호 없이 통과해 버린다 — 그래서 부정 단언은
  // 창을 쓰지 않고 파일 전체에 건다.
  it('FE-M4: 죽은 레짐 값(regime: neutral/aggressive)이 api-mocks.ts 파일 어디에도 없다', () => {
    const source = stripLineComments(read(API_MOCKS))
    expect(DEAD_REGIME_VALUE_RE.test(source)).toBe(false)
  })

  it('FE-M5: 죽은 레짐 값(regime: neutral/aggressive)이 MSW handlers.ts 파일 어디에도 없다', () => {
    const source = stripLineComments(read(MSW_HANDLERS))
    expect(DEAD_REGIME_VALUE_RE.test(source)).toBe(false)
  })

  it('FE-M3: 기본 MSW 핸들러만으로 카드가 폴백이 아닌 실제 레짐을 그린다', async () => {
    render(
      <TestProviders>
        <MarketRegimeCard />
      </TestProviders>,
    )
    const badge = await screen.findByTestId('market-regime-badge')
    expect(badge.textContent).toContain('방어')
    expect(badge.textContent).not.toContain('비활성')
  })
})
