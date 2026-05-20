/**
 * 사이클 23 (2026-05-20) Red — IntegrationToggleCard auto-apply 4번째 토글.
 *
 * 요구 행위:
 * - AC23-A: 4번째 토글 `data-testid="toggle-auto-apply"` 렌더 (라벨 포함)
 * - AC23-B: ConfirmModal 이중 확인 후 PUT /api/integrations/auto-apply 발사
 */

import { describe, expect, it, vi } from 'vitest'
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
