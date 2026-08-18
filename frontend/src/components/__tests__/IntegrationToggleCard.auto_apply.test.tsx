/**
 * 사이클 23 (2026-05-20) Red — IntegrationToggleCard auto-apply 4번째 토글.
 *
 * 요구 행위:
 * - AC23-A: 4번째 토글 `data-testid="toggle-auto-apply"` 렌더 (라벨 포함)
 * - AC23-B: ConfirmModal 이중 확인 후 PUT /api/integrations/auto-apply 발사
 */

import { describe, expect, it } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { http, HttpResponse } from 'msw'

import IntegrationToggleCard from '../IntegrationToggleCard'
import { TestProviders } from '../../test/providers'
import { wrap } from '../../test/factories'
import { server } from '../../test/server'

const autoApplyOff = { enabled: false }
const autoApplyOn = { enabled: true }

const defaultHandlers = [
  http.get('/api/integrations/dkstock-regime', () =>
    HttpResponse.json(
      wrap({ enabled: false, source: 'env', env_value: false, db_value: null }),
    ),
  ),
  http.get('/api/integrations/kis-mcp', () =>
    HttpResponse.json(
      wrap({ enabled: false, source: 'env', env_value: false, db_value: null }),
    ),
  ),
  http.get('/api/integrations/auto-regime-adjust', () =>
    HttpResponse.json(
      wrap({ enabled: false, source: 'env', env_value: false, db_value: null }),
    ),
  ),
  http.get('/api/integrations/auto-apply', () =>
    HttpResponse.json(wrap(autoApplyOff)),
  ),
  http.get('/api/integrations/buy-block', () =>
    HttpResponse.json(
      wrap({
        mode: 'HARD',
        thresholds: {
          vix_threshold: 25,
          fg_high_threshold: 85,
          fg_low_threshold: 15,
          defensive_enabled: true,
        },
        blocked: false,
        reasons: [],
        soft_multiplier: 1.0,
      }),
    ),
  ),
]

describe('IntegrationToggleCard — auto-apply 4번째 토글', () => {
  it('AC23-A: data-testid="toggle-auto-apply" 렌더 + "AI 자문 자동 적용" 라벨 포함', async () => {
    server.use(...defaultHandlers)

    render(
      <TestProviders>
        <IntegrationToggleCard />
      </TestProviders>,
    )

    // 4번째 토글이 DOM 에 존재
    const toggle = await screen.findByTestId('toggle-auto-apply')
    expect(toggle).toBeTruthy()

    // "AI 자문 자동 적용" 라벨 텍스트 포함 (일부 매칭)
    expect(screen.getByText(/AI 자문 자동 적용/)).toBeTruthy()
  })

  it('AC23-B: ConfirmModal 이중 확인 후 PUT /api/integrations/auto-apply 발사', async () => {
    let putCalled = false
    let putBody: unknown = null

    server.use(
      ...defaultHandlers,
      http.put('/api/integrations/auto-apply', async ({ request }) => {
        putCalled = true
        putBody = await request.json()
        return HttpResponse.json(wrap(autoApplyOn))
      }),
    )

    render(
      <TestProviders>
        <IntegrationToggleCard />
      </TestProviders>,
    )

    const toggle = await screen.findByTestId('toggle-auto-apply')

    // 토글 클릭 → ConfirmModal 노출
    fireEvent.click(toggle)
    // ConfirmModal 확인 버튼
    const confirmBtn = await screen.findByRole('button', { name: /확인/ })
    fireEvent.click(confirmBtn)

    await waitFor(() => expect(putCalled).toBe(true))
    expect((putBody as { enabled: boolean }).enabled).toBe(true)
  })
})

/**
 * 2026-08-19 정리 사이클 ③ — `AUTO_APPLY_META` 문구 ↔ 코드 사실 정합.
 *
 * 코드 사실 (`src/engine/recommendation_engine.py`):
 * - `_CONSERVATIVE_KEYS: frozenset[str] = frozenset()` (사이클 210, 2026-07-14 — param
 *   단조 조임(ratchet)이 전략을 교살해 7키 전량 제거).
 * - `auto_apply_recommendations` 의 파라미터 루프는 `if k not in _CONSERVATIVE_KEYS: continue`
 *   → **모든 키가 continue = 루프 전체 no-op**. `save_params` 미호출, `[auto_params_apply]` 미발화.
 * → 실제 자동 적용은 **weight 감액뿐**인데 UI 는 "보수적 파라미터 (stop_loss/position_ratio/
 *   daily_loss_limit) 를 자동 적용합니다" 라고 안내 = 운영자 오도(가장 위험한 종류 — 손절/비중이
 *   자동으로 관리된다고 믿게 만든다).
 *
 * 요구 행위 (문구를 코드에 맞춘다 — 코드는 건드리지 않는다):
 * - G-AA-1: description/confirmOnMessage 에 "보수적 파라미터"/"stop_loss"/"position_ratio"/
 *   "daily_loss_limit" 문자열 0건.
 * - G-AA-2: description 이 weight(비중) 감액만 자동 적용됨을 명시.
 * - G-AA-3: description 이 파라미터는 자동 적용되지 않고 운영자 명시 적용임을 명시.
 * - G-AA-4: 코드 상수명(`_CONSERVATIVE_KEYS` 등)을 운영자 문구에 노출 금지.
 * - G-AA-5: 렌더된 auto-apply 토글 행에 위 문구가 실제로 표시된다.
 */
import { readFileSync } from 'fs'
import path from 'path'

const FORBIDDEN = ['보수적 파라미터', 'stop_loss', 'position_ratio', 'daily_loss_limit']

function autoApplyMetaBlock(): string {
  const source = readFileSync(
    path.join(__dirname, '..', 'IntegrationToggleCard.tsx'),
    'utf-8',
  )
  const m = source.match(/const AUTO_APPLY_META[^=]*=\s*\{([\s\S]*?)\n\}/)
  if (!m) throw new Error('AUTO_APPLY_META 선언을 찾지 못함')
  return m[1]
}

function fieldOf(block: string, key: 'description' | 'confirmOnMessage'): string {
  const m = block.match(new RegExp(`${key}:\\s*([\\s\\S]*?)\\n\\s{2}\\w+:`))
  if (!m) throw new Error(`AUTO_APPLY_META.${key} 를 찾지 못함`)
  return m[1]
}

describe('AUTO_APPLY_META 문구 ↔ 코드 사실 정합 (사이클 210 param ratchet 차단 반영)', () => {
  it('G-AA-1: description/confirmOnMessage 에 자동 적용되지 않는 파라미터 문구 0건', () => {
    const block = autoApplyMetaBlock()
    const description = fieldOf(block, 'description')
    const confirmOn = fieldOf(block, 'confirmOnMessage')

    const violations: string[] = []
    for (const bad of FORBIDDEN) {
      if (description.includes(bad)) violations.push(`description 에 "${bad}" 잔존`)
      if (confirmOn.includes(bad)) violations.push(`confirmOnMessage 에 "${bad}" 잔존`)
    }

    expect(
      violations,
      '_CONSERVATIVE_KEYS 가 빈 frozenset 이라 파라미터는 자동 적용되지 않는다 — ' +
        '운영자 오도 문구 금지',
    ).toEqual([])
  })

  it('G-AA-2: description 이 weight(비중) 감액 자동 적용을 명시', () => {
    const description = fieldOf(autoApplyMetaBlock(), 'description')

    expect(
      /(weight|비중)[^\n]{0,20}감액/.test(description),
      `description 에 "weight/비중 감액" 명시 의무 (실제 자동 적용되는 유일한 대상):\n${description}`,
    ).toBe(true)
  })

  it('G-AA-3: description 이 파라미터 미자동적용 + 운영자 명시 적용을 명시', () => {
    const description = fieldOf(autoApplyMetaBlock(), 'description')

    expect(
      description.includes('파라미터'),
      `description 에 파라미터 언급 의무:\n${description}`,
    ).toBe(true)
    expect(
      /자동 적용되지 않|자동 적용 안|자동 적용하지 않/.test(description),
      `description 에 "파라미터는 자동 적용되지 않는다" 명시 의무:\n${description}`,
    ).toBe(true)
    expect(
      /(운영자|수동|직접)/.test(description),
      `description 에 운영자 명시 적용 안내 의무:\n${description}`,
    ).toBe(true)
  })

  it('G-AA-4: 운영자 문구에 코드 상수명 노출 금지', () => {
    const block = autoApplyMetaBlock()

    expect(
      /_CONSERVATIVE_KEYS|_STOP_LOSS_KEYS|frozenset/.test(block),
      'UI 문구는 운영자가 읽는다 — 코드 상수명 노출 금지',
    ).toBe(false)
  })

  it('G-AA-5: 렌더된 auto-apply 토글 행에 정합 문구가 실제 표시', async () => {
    server.use(...defaultHandlers)

    render(
      <TestProviders>
        <IntegrationToggleCard />
      </TestProviders>,
    )

    const badge = await screen.findByTestId('source-badge-auto-apply')
    const row = badge.closest('.border-gray-200')
    expect(row, 'auto-apply 토글 행을 찾지 못함').toBeTruthy()

    const text = row!.textContent ?? ''
    for (const bad of FORBIDDEN) {
      expect(text.includes(bad), `화면 문구에 "${bad}" 노출 금지`).toBe(false)
    }
    expect(/(weight|비중)[^\n]{0,20}감액/.test(text)).toBe(true)
    expect(text.includes('파라미터')).toBe(true)
    expect(/자동 적용되지 않|자동 적용 안|자동 적용하지 않/.test(text)).toBe(true)
  })
})
