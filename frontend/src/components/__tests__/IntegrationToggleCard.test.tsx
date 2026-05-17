/**
 * 사이클 5 (2026-05-17) Red — IntegrationToggleCard.
 *
 * 외부 통합 3 토글 통합 카드:
 * - dkstock-regime: 매크로 레짐 fetch (활성화 시 백그라운드 fetch trigger)
 * - kis-mcp: 외부 백테스트 서버
 * - auto-regime-adjust: 매크로 레짐 → cash_usage_ratio 자동 갱신
 *
 * 요구 행위:
 * - I5-A: 3 토글 노출 (라벨 + 현재 상태 + source 배지)
 * - I5-B: 토글 클릭 → ConfirmModal 노출 (이중 확인)
 * - I5-C: ConfirmModal 확인 → PUT API 호출 + 응답 후 invalidate
 * - I5-D: dkstock-regime 활성화 시 fetch 폴링 진행 표시
 * - I5-E: 비활성 시 진행 표시 없음
 * - I5-F: API 에러 시 graceful fallback 메시지
 */

import { describe, expect, it } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { http, HttpResponse } from 'msw'

import IntegrationToggleCard from '../IntegrationToggleCard'
import { TestProviders } from '../../test/providers'
import { wrap } from '../../test/factories'
import { server } from '../../test/server'

const dkstockDbTrue = {
  enabled: true,
  source: 'db' as const,
  env_value: false,
  db_value: true,
}

const dkstockEnvFalse = {
  enabled: false,
  source: 'env' as const,
  env_value: false,
  db_value: null,
}

const mcpEnvFalse = {
  enabled: false,
  source: 'env' as const,
  env_value: false,
  db_value: null,
}

const autoRegimeOn = {
  enabled: true,
  source: 'db' as const,
  env_value: true,
  db_value: true,
}

describe('IntegrationToggleCard', () => {
  it('I5-A: 3 토글 노출 + 현재 상태 + source 배지', async () => {
    server.use(
      http.get('/api/integrations/dkstock-regime', () =>
        HttpResponse.json(wrap(dkstockEnvFalse)),
      ),
      http.get('/api/integrations/kis-mcp', () => HttpResponse.json(wrap(mcpEnvFalse))),
      http.get('/api/integrations/auto-regime-adjust', () =>
        HttpResponse.json(wrap(autoRegimeOn)),
      ),
    )
    render(
      <TestProviders>
        <IntegrationToggleCard />
      </TestProviders>,
    )

    await screen.findByTestId('integration-toggle-card')
    // 3 토글 모두 노출 (async fetch 완료 대기)
    const dkstockToggle = await screen.findByTestId('toggle-dkstock-regime')
    const mcpToggle = await screen.findByTestId('toggle-kis-mcp')
    const autoToggle = await screen.findByTestId('toggle-auto-regime-adjust')
    // dkstock-regime 은 OFF 상태
    expect(dkstockToggle.textContent).toContain('OFF')
    expect(mcpToggle.textContent).toContain('OFF')
    // auto-regime-adjust 는 ON 상태
    expect(autoToggle.textContent).toContain('ON')
  })

  it('I5-A-source: DB 값 사용 중인 토글에 source=db 배지', async () => {
    server.use(
      http.get('/api/integrations/dkstock-regime', () =>
        HttpResponse.json(wrap(dkstockDbTrue)),
      ),
      http.get('/api/integrations/kis-mcp', () => HttpResponse.json(wrap(mcpEnvFalse))),
      http.get('/api/integrations/auto-regime-adjust', () =>
        HttpResponse.json(wrap(autoRegimeOn)),
      ),
    )
    render(
      <TestProviders>
        <IntegrationToggleCard />
      </TestProviders>,
    )

    await waitFor(() => {
      const dkstock = screen.getByTestId('source-badge-dkstock-regime')
      expect(dkstock.textContent).toMatch(/DB/)
    })
  })

  it('I5-B: 토글 클릭 → ConfirmModal 노출 (이중 확인)', async () => {
    server.use(
      http.get('/api/integrations/dkstock-regime', () =>
        HttpResponse.json(wrap(dkstockEnvFalse)),
      ),
      http.get('/api/integrations/kis-mcp', () => HttpResponse.json(wrap(mcpEnvFalse))),
      http.get('/api/integrations/auto-regime-adjust', () =>
        HttpResponse.json(wrap(autoRegimeOn)),
      ),
    )
    render(
      <TestProviders>
        <IntegrationToggleCard />
      </TestProviders>,
    )

    const toggle = await screen.findByTestId('toggle-dkstock-regime')
    fireEvent.click(toggle)

    // ConfirmModal 노출 - heading 으로 정확 검증 (모달 내부 h3 만 매칭)
    await waitFor(() => {
      const heading = screen.getByRole('heading', { level: 3 })
      expect(heading.textContent).toContain('활성화')
    })
  })

  it('I5-C: ConfirmModal 확인 → PUT API 호출', async () => {
    let putCallCount = 0
    let putBody: { enabled?: boolean } = {}
    server.use(
      http.get('/api/integrations/dkstock-regime', () =>
        HttpResponse.json(wrap(dkstockEnvFalse)),
      ),
      http.get('/api/integrations/kis-mcp', () => HttpResponse.json(wrap(mcpEnvFalse))),
      http.get('/api/integrations/auto-regime-adjust', () =>
        HttpResponse.json(wrap(autoRegimeOn)),
      ),
      http.put('/api/integrations/dkstock-regime', async ({ request }) => {
        putCallCount += 1
        putBody = (await request.json()) as { enabled?: boolean }
        return HttpResponse.json(
          wrap({
            enabled: true,
            source: 'db' as const,
            env_value: false,
            db_value: true,
          }),
        )
      }),
    )
    render(
      <TestProviders>
        <IntegrationToggleCard />
      </TestProviders>,
    )

    const toggle = await screen.findByTestId('toggle-dkstock-regime')
    fireEvent.click(toggle)

    // ConfirmModal "확인" 클릭
    const confirmBtn = await screen.findByText('확인')
    fireEvent.click(confirmBtn)

    await waitFor(() => {
      expect(putCallCount).toBe(1)
      expect(putBody).toEqual({ enabled: true })
    })
  })

  it('I5-E: API 에러 시 graceful fallback', async () => {
    server.use(
      http.get('/api/integrations/dkstock-regime', () => new HttpResponse(null, { status: 500 })),
      http.get('/api/integrations/kis-mcp', () => HttpResponse.json(wrap(mcpEnvFalse))),
      http.get('/api/integrations/auto-regime-adjust', () =>
        HttpResponse.json(wrap(autoRegimeOn)),
      ),
    )
    render(
      <TestProviders>
        <IntegrationToggleCard />
      </TestProviders>,
    )

    await waitFor(() => {
      const card = screen.getByTestId('integration-toggle-card')
      expect(card.textContent).toMatch(/불러오지 못했|로딩|오류/)
    })
  })

  it('I5-G: dkstock-regime 활성화 후 백그라운드 fetch 진행 안내', async () => {
    server.use(
      http.get('/api/integrations/dkstock-regime', () =>
        HttpResponse.json(wrap(dkstockEnvFalse)),
      ),
      http.get('/api/integrations/kis-mcp', () => HttpResponse.json(wrap(mcpEnvFalse))),
      http.get('/api/integrations/auto-regime-adjust', () =>
        HttpResponse.json(wrap(autoRegimeOn)),
      ),
      http.put('/api/integrations/dkstock-regime', () =>
        HttpResponse.json(
          wrap({
            enabled: true,
            source: 'db' as const,
            env_value: false,
            db_value: true,
          }),
        ),
      ),
    )
    render(
      <TestProviders>
        <IntegrationToggleCard />
      </TestProviders>,
    )

    const toggle = await screen.findByTestId('toggle-dkstock-regime')
    fireEvent.click(toggle)
    const confirmBtn = await screen.findByText('확인')
    fireEvent.click(confirmBtn)

    // 활성화 후 안내 메시지 — fetch 진행 키워드
    await waitFor(() => {
      expect(screen.getByTestId('fetch-progress-dkstock-regime')).toBeTruthy()
    })
  })
})
