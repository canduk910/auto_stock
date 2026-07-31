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

  // -------------------------------------------------------------------------
  // 사이클 8 (2026-05-18) — 매수 가드 4 모드 + 4 임계값
  // -------------------------------------------------------------------------
  const buyBlockHardDefault = {
    mode: 'HARD' as const,
    thresholds: {
      vix_threshold: 25.0,
      fg_high_threshold: 85.0,
      fg_low_threshold: 15.0,
      defensive_enabled: true,
    },
    blocked: false,
    reasons: [] as string[],
    soft_multiplier: 1.0,
    // 사이클 D-FE — 타입 정합 보강(값 무변경 의도, data_available=true 정상 데이터 유입 가정)
    data_available: true,
    guard_inert: false,
  }

  const buyBlockHardBlocked = {
    ...buyBlockHardDefault,
    blocked: true,
    reasons: ['regime=defensive (방어 (공포 현금))'],
  }

  // 사이클 5 토글 3종 mock 헬퍼 — 사이클 8 테스트가 함께 GET 들을 받아야 함
  // 사이클 75 Q4: retry:1 추가로 인해 auto-apply 핸들러 없으면 waitFor timeout 초과 위험
  //   → setupToggleStubs 에 auto-apply 핸들러 추가 (기존 3 + 신규 1 = 4 토글 완전 커버)
  const setupToggleStubs = () => {
    server.use(
      http.get('/api/integrations/dkstock-regime', () =>
        HttpResponse.json(wrap(dkstockEnvFalse)),
      ),
      http.get('/api/integrations/kis-mcp', () =>
        HttpResponse.json(wrap(mcpEnvFalse)),
      ),
      http.get('/api/integrations/auto-regime-adjust', () =>
        HttpResponse.json(wrap(autoRegimeOn)),
      ),
      // 사이클 23 P3-3 auto-apply 4번째 토글 — retry:1 도입 후 미등록 시 waitFor timeout
      http.get('/api/integrations/auto-apply', () =>
        HttpResponse.json(wrap({ enabled: false, source: 'db' as const })),
      ),
    )
  }

  it('I8-A: 매수 가드 모드 select + 4 임계값 슬라이더 노출', async () => {
    setupToggleStubs()
    server.use(
      http.get('/api/integrations/buy-block', () =>
        HttpResponse.json(wrap(buyBlockHardDefault)),
      ),
    )

    render(
      <TestProviders>
        <IntegrationToggleCard />
      </TestProviders>,
    )

    // 모드 select
    const modeSelect = await screen.findByTestId('buy-block-mode-select')
    expect((modeSelect as HTMLSelectElement).value).toBe('HARD')

    // 4 임계 슬라이더
    expect(screen.getByTestId('buy-block-vix-slider')).toBeTruthy()
    expect(screen.getByTestId('buy-block-fg-high-slider')).toBeTruthy()
    expect(screen.getByTestId('buy-block-fg-low-slider')).toBeTruthy()
    // defensive_enabled 체크박스
    expect(screen.getByTestId('buy-block-defensive-toggle')).toBeTruthy()
  })

  it('I8-B: 발동 사유 표시 (defensive 발동 시 reasons 리스트)', async () => {
    setupToggleStubs()
    server.use(
      http.get('/api/integrations/buy-block', () =>
        HttpResponse.json(wrap(buyBlockHardBlocked)),
      ),
    )

    render(
      <TestProviders>
        <IntegrationToggleCard />
      </TestProviders>,
    )

    const reasonsArea = await screen.findByTestId('buy-block-reasons')
    expect(reasonsArea.textContent).toMatch(/defensive/)
  })

  it('I8-C: 모드 변경 → ConfirmModal → PUT 호출', async () => {
    setupToggleStubs()
    let putBody: any = {}
    let putCount = 0
    server.use(
      http.get('/api/integrations/buy-block', () =>
        HttpResponse.json(wrap(buyBlockHardDefault)),
      ),
      http.put('/api/integrations/buy-block', async ({ request }) => {
        putCount += 1
        putBody = await request.json()
        return HttpResponse.json(
          wrap({
            ...buyBlockHardDefault,
            mode: 'SOFT' as const,
            soft_multiplier: 1.0,
          }),
        )
      }),
    )

    render(
      <TestProviders>
        <IntegrationToggleCard />
      </TestProviders>,
    )

    const modeSelect = (await screen.findByTestId(
      'buy-block-mode-select',
    )) as HTMLSelectElement

    fireEvent.change(modeSelect, { target: { value: 'SOFT' } })

    // ConfirmModal heading 노출 — 다수 h3 가능성 회피, 텍스트 검색
    await waitFor(() => {
      expect(screen.getByText(/매수 가드 모드 변경/)).toBeTruthy()
    })

    const confirmBtn = await screen.findByText('확인')
    fireEvent.click(confirmBtn)

    await waitFor(() => {
      expect(putCount).toBe(1)
      expect(putBody.mode).toBe('SOFT')
    })
  })

  it('I8-D: 임계값 슬라이더 변경 → PUT 호출 (ConfirmModal 없이 즉시)', async () => {
    setupToggleStubs()
    let putBody: any = {}
    server.use(
      http.get('/api/integrations/buy-block', () =>
        HttpResponse.json(wrap(buyBlockHardDefault)),
      ),
      http.put('/api/integrations/buy-block', async ({ request }) => {
        putBody = await request.json()
        return HttpResponse.json(
          wrap({
            ...buyBlockHardDefault,
            thresholds: {
              ...buyBlockHardDefault.thresholds,
              vix_threshold: 30.0,
            },
          }),
        )
      }),
    )

    render(
      <TestProviders>
        <IntegrationToggleCard />
      </TestProviders>,
    )

    const vixSlider = (await screen.findByTestId(
      'buy-block-vix-slider',
    )) as HTMLInputElement

    fireEvent.change(vixSlider, { target: { value: '30' } })
    // 저장 버튼 클릭 (슬라이더 commit)
    const saveBtn = await screen.findByTestId('buy-block-thresholds-save')
    fireEvent.click(saveBtn)

    await waitFor(() => {
      expect(putBody.vix_threshold).toBe(30)
    })
  })

  it('I8-E: defensive_enabled 체크박스 토글 → PUT 호출', async () => {
    setupToggleStubs()
    let putBody: any = {}
    server.use(
      http.get('/api/integrations/buy-block', () =>
        HttpResponse.json(wrap(buyBlockHardDefault)),
      ),
      http.put('/api/integrations/buy-block', async ({ request }) => {
        putBody = await request.json()
        return HttpResponse.json(
          wrap({
            ...buyBlockHardDefault,
            thresholds: {
              ...buyBlockHardDefault.thresholds,
              defensive_enabled: false,
            },
          }),
        )
      }),
    )

    render(
      <TestProviders>
        <IntegrationToggleCard />
      </TestProviders>,
    )

    const checkbox = (await screen.findByTestId(
      'buy-block-defensive-toggle',
    )) as HTMLInputElement

    fireEvent.click(checkbox) // ON → OFF
    const saveBtn = await screen.findByTestId('buy-block-thresholds-save')
    fireEvent.click(saveBtn)

    await waitFor(() => {
      expect(putBody.defensive_enabled).toBe(false)
    })
  })

  it('I8-F: SOFT 모드 — multiplier 표시', async () => {
    setupToggleStubs()
    server.use(
      http.get('/api/integrations/buy-block', () =>
        HttpResponse.json(
          wrap({
            ...buyBlockHardDefault,
            mode: 'SOFT' as const,
            soft_multiplier: 0.5,
            reasons: ['regime=defensive (방어)'],
          }),
        ),
      ),
    )

    render(
      <TestProviders>
        <IntegrationToggleCard />
      </TestProviders>,
    )

    const indicator = await screen.findByTestId('buy-block-soft-multiplier')
    expect(indicator.textContent).toMatch(/0\.5|50%|비중 절반/)
  })

  it('I8-G: GET 에러 시 graceful fallback', async () => {
    setupToggleStubs()
    server.use(
      http.get('/api/integrations/buy-block', () =>
        new HttpResponse(null, { status: 500 }),
      ),
    )

    render(
      <TestProviders>
        <IntegrationToggleCard />
      </TestProviders>,
    )

    // 사이클 75 Q4: retry:1 추가로 인해 BuyBlockSection 이 500 에러 수신 후 1회 재시도 →
    //   에러 상태 전환까지 시간 증가 → waitFor timeout 3000ms 로 상향 (재시도 대기 포함)
    await waitFor(() => {
      expect(screen.getByTestId('buy-block-error')).toBeTruthy()
    }, { timeout: 3000 })
  })

  // -------------------------------------------------------------------------
  // 사이클 D-FE (2026-07-31) — 레짐 가드 silent inert 가시화 (백엔드 사이클 D
  // guard_inert 필드 프론트 표시, tester DEF-1 봉합)
  // -------------------------------------------------------------------------
  it('D-FE-1: guard_inert=true → 매수 가드 무력 배너 렌더', async () => {
    setupToggleStubs()
    server.use(
      http.get('/api/integrations/buy-block', () =>
        HttpResponse.json(
          wrap({
            ...buyBlockHardDefault,
            data_available: false,
            guard_inert: true,
          }),
        ),
      ),
    )

    render(
      <TestProviders>
        <IntegrationToggleCard />
      </TestProviders>,
    )

    const banner = await screen.findByTestId('buy-block-guard-inert')
    expect(banner.textContent).toMatch(/매수 가드 무력/)
  })

  it('D-FE-2: guard_inert=false → 매수 가드 무력 배너 미렌더', async () => {
    setupToggleStubs()
    server.use(
      http.get('/api/integrations/buy-block', () =>
        HttpResponse.json(wrap(buyBlockHardDefault)),
      ),
    )

    render(
      <TestProviders>
        <IntegrationToggleCard />
      </TestProviders>,
    )

    await screen.findByTestId('buy-block-mode-select')
    expect(screen.queryByTestId('buy-block-guard-inert')).toBeNull()
  })
})
