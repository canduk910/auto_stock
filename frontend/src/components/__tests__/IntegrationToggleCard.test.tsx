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

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, render, screen, waitFor, fireEvent } from '@testing-library/react'
import { http, HttpResponse } from 'msw'

import IntegrationToggleCard from '../IntegrationToggleCard'
import { TestProviders, createTestQueryClient } from '../../test/providers'
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

  // -------------------------------------------------------------------------
  // cycle315 (2026-09-19) — 매크로 레짐 출처 전환(외부 dkstock.cloud → 우리 macro 컨테이너).
  // 🔴 key `dkstock-regime` 과 env `DKSTOCK_REGIME_ENABLED` 는 **유지**한다(사용자 결정).
  //    바뀌는 것은 운영자가 읽는 문장뿐이다.
  // -------------------------------------------------------------------------
  it('FE-T1: dkstock-regime 행 — 라벨에 외부 서비스 이름 없음 + 설명에 매수 가드 없음', async () => {
    setupToggleStubs()
    render(
      <TestProviders>
        <IntegrationToggleCard />
      </TestProviders>,
    )

    const row = await screen.findByTestId('toggle-row-dkstock-regime')
    const label = screen.getByTestId('toggle-label-dkstock-regime')
    const desc = screen.getByTestId('toggle-desc-dkstock-regime')

    // 철거된 외부 서비스 이름을 라벨에 남기지 않는다 (2026-08-18 terraform destroy)
    expect(label.textContent).not.toContain('dkstock.cloud')
    expect(label.textContent).toMatch(/macro/i)
    // 레짐은 관찰 지표다 — 매수를 차단·축소하지 않는다
    expect(desc.textContent).not.toContain('매수 가드')
    expect(desc.textContent).not.toContain('외부')
    // 토글 자체(key·testid)는 그대로 살아 있다
    expect(row.textContent).toBeTruthy()
    expect(screen.getByTestId('toggle-dkstock-regime')).toBeTruthy()
  })

  it('FE-T2: dkstock-regime 확인 모달도 매수 가드 문구를 쓰지 않는다', async () => {
    setupToggleStubs()
    render(
      <TestProviders>
        <IntegrationToggleCard />
      </TestProviders>,
    )

    const toggle = await screen.findByTestId('toggle-dkstock-regime')
    fireEvent.click(toggle)
    const modal = (await screen.findByRole('heading', { name: /매크로 레짐.* 활성화$/ })).parentElement!
    expect(modal.textContent).not.toContain('매수 가드')
    expect(modal.textContent).not.toContain('dkstock.cloud')
  })

  it('FE-T3: env fallback 표시는 DKSTOCK_REGIME_ENABLED 이름을 유지한다', async () => {
    setupToggleStubs()
    render(
      <TestProviders>
        <IntegrationToggleCard />
      </TestProviders>,
    )

    // dkstockEnvFalse = source:'env' → env 변수 이름 노출 경로
    const row = await screen.findByTestId('toggle-row-dkstock-regime')
    expect(row.textContent).toContain('DKSTOCK_REGIME_ENABLED')
  })

  it('FE-T4: 활성화 직후 진행 안내가 콜드 수집 소요(최대 2분)와 재시도를 말한다', async () => {
    setupToggleStubs()
    server.use(
      http.put('/api/integrations/dkstock-regime', () =>
        HttpResponse.json(
          wrap({ enabled: true, source: 'db' as const, env_value: false, db_value: true }),
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
    fireEvent.click(await screen.findByText('확인'))

    const progress = await screen.findByTestId('fetch-progress-dkstock-regime')
    expect(progress.textContent).toContain('2분')
    expect(progress.textContent).toMatch(/다시 조회|재시도/)
    // 3초 단발 갱신이라는 옛 약속은 더 이상 쓰지 않는다
    expect(progress.textContent).not.toContain('3초')
  })

  it('FE-T5: auto-regime-adjust 설명의 자금 사다리가 실재 4단이다', async () => {
    setupToggleStubs()
    render(
      <TestProviders>
        <IntegrationToggleCard />
      </TestProviders>,
    )

    const desc = await screen.findByTestId('toggle-desc-auto-regime-adjust')
    for (const label of ['적극 매수', '선별 매수', '신중', '방어']) {
      expect(desc.textContent).toContain(label)
    }
    expect(desc.textContent).not.toContain('neutral')
    expect(desc.textContent).not.toContain('aggressive')
  })

  // -------------------------------------------------------------------------
  // cycle315 후속(적대 검토) — FE-T4 는 진행 배지의 *문구* 만 본다. 뮤테이션으로 확증된
  // 공허함: `MACRO_REFETCH_DELAYS_MS` 를 옛 단발 `[3_000]` 으로 되돌려도 FE-T4 를 포함한
  // 전체 스위트가 그대로 초록이다 — 값이 들어올 때까지 "자동으로 다시 조회한다" 는 약속을
  // 지키는 유일한 장치(5단 지연 배열)가 사라져도 아무것도 붉어지지 않는다는 뜻이다.
  //
  // 여기서는 fake timer 로 5단 지연(3s/15s/30s/60s/120s)을 실제로 밟아
  // invalidateQueries(['marketRegime']) 누적 호출과 진행 배지 노출 구간을 직접 잰다.
  // `setupToggleStubs` 를 같이 쓰기 위해 바깥 describe **안**에 중첩한다.
  // -------------------------------------------------------------------------
  describe('cycle315 후속: 5단 재조회 타이머 실측', () => {
    beforeEach(() => {
      // shouldAdvanceTime — MSW 응답이 쓰는 실제 I/O 까지 얼려버리면 fetch 가 영원히 안 끝난다
      // (`pages/__tests__/MarketState.test.tsx` FE14~16 선례와 같은 설정).
      vi.useFakeTimers({ shouldAdvanceTime: true })
    })

    afterEach(() => {
      vi.useRealTimers()
    })

    function marketRegimeInvalidateCount(spy: { mock: { calls: unknown[][] } }): number {
      return spy.mock.calls.filter(([arg]) => {
        const queryKey = (arg as { queryKey?: unknown } | undefined)?.queryKey
        return JSON.stringify(queryKey) === JSON.stringify(['marketRegime'])
      }).length
    }

    async function activateDkstockRegimeAndConfirm() {
      setupToggleStubs()
      server.use(
        http.put('/api/integrations/dkstock-regime', () =>
          HttpResponse.json(
            wrap({ enabled: true, source: 'db' as const, env_value: false, db_value: true }),
          ),
        ),
      )
      const queryClient = createTestQueryClient()
      const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries')
      const renderResult = render(
        <TestProviders queryClient={queryClient}>
          <IntegrationToggleCard />
        </TestProviders>,
      )

      const toggle = await screen.findByTestId('toggle-dkstock-regime')
      fireEvent.click(toggle)
      fireEvent.click(await screen.findByText('확인'))
      await screen.findByTestId('fetch-progress-dkstock-regime')

      return { ...renderResult, invalidateSpy }
    }

    it('FE-T6: 3s/15s/30s/60s/120s 를 밟을 때마다 marketRegime invalidate 가 1→2→3→4→5 로 늘어난다', async () => {
      const { invalidateSpy } = await activateDkstockRegimeAndConfirm()

      // 확인 직후 — 아직 어느 타이머도 발화하지 않았다
      expect(marketRegimeInvalidateCount(invalidateSpy)).toBe(0)

      await act(async () => {
        await vi.advanceTimersByTimeAsync(3_000)
      })
      expect(marketRegimeInvalidateCount(invalidateSpy)).toBe(1)
      // 3초 시점 — 아직 진행 배지가 남아 있다 (마지막 타이머에서만 내려간다)
      expect(screen.getByTestId('fetch-progress-dkstock-regime')).toBeTruthy()

      await act(async () => {
        await vi.advanceTimersByTimeAsync(12_000) // 누적 15s
      })
      expect(marketRegimeInvalidateCount(invalidateSpy)).toBe(2)

      await act(async () => {
        await vi.advanceTimersByTimeAsync(15_000) // 누적 30s
      })
      expect(marketRegimeInvalidateCount(invalidateSpy)).toBe(3)

      await act(async () => {
        await vi.advanceTimersByTimeAsync(30_000) // 누적 60s
      })
      expect(marketRegimeInvalidateCount(invalidateSpy)).toBe(4)

      await act(async () => {
        await vi.advanceTimersByTimeAsync(60_000) // 누적 120s
      })
      expect(marketRegimeInvalidateCount(invalidateSpy)).toBe(5)
      // 120초 시점 — 마지막 타이머가 진행 배지를 내린다
      expect(screen.queryByTestId('fetch-progress-dkstock-regime')).toBeNull()
    })

    it('FE-T7: 언마운트 후에는 남은 타이머를 전부 밟아도 invalidate 가 더 늘지 않는다 (cleanup)', async () => {
      const { unmount, invalidateSpy } = await activateDkstockRegimeAndConfirm()

      unmount()

      await act(async () => {
        await vi.advanceTimersByTimeAsync(120_000)
      })
      // 언마운트 시점에 아직 발화 전이던 5개 타이머가 전부 clearTimeout 됐어야 한다
      expect(marketRegimeInvalidateCount(invalidateSpy)).toBe(0)
    })
  })
})
