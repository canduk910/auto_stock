/**
 * cycle278 Red — 전략 현황 페이지의 파라미터 편집 진입점 계약.
 *
 * 명세: `_workspace/red/cycle278_param_catalog_ui_spec.md` §6.1 · §7.2(F21~F26)
 *
 * 이 파일 작성 시점에 `Strategies.tsx` 에는 "파라미터" 버튼이 **없고**
 * `components/StrategyParamsEditor.tsx` 도 **없다** — 전건 RED 로 시작한다.
 *
 * 계약 요약
 * - 전략 카드마다 `strategy-params-open-{sid}` 버튼이 있고, 누르면 `strategy-params-editor` 가 열린다.
 * - 읽기 전용 요약 4키 그리드(`strategy-{sid}-{key}`)는 **그대로 남는다** — 편집기가 생겼다고
 *   한눈에 보던 임계 4개를 없애면 대시보드 성격이 사라진다(e2e H-ST2 가 라벨 문자열을 직접 단언한다).
 * - 저장이 성공하면 `['strategies']` 를 무효화해 요약 그리드가 **새 값으로 갱신**된다
 *   (저장했는데 화면이 옛 값을 계속 보여 주면 운영자가 두 번 저장한다).
 * - 편집기의 스키마 useQuery 는 `retry` 를 **명시**한다(사이클 65 H3 / 80 hotfix 영속 —
 *   e2e ECONNREFUSED 시 기본 retry 누적으로 페이지가 timeout 된다).
 */
import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { readFileSync } from 'fs'
import path from 'path'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { http, HttpResponse } from 'msw'

import Strategies from '../Strategies'
import { server } from '../../test/server'
import { PARAM_SCHEMA_FIXTURE } from '../../test/fixtures/paramSchema.fixture'

const STRATEGY_IDS = [
  'momentum',
  'volatility_breakout',
  'long_tail_volatility',
  'donchian_swing',
  'bull_flag_breakout',
  'vcp_breakout',
  'kojiro',
] as const

/** GET /api/strategies 응답 — 픽스처의 7 전략 현재값을 그대로 쓴다(같은 코드에서 나온 값). */
function strategiesPayload(overrides: Record<string, Record<string, unknown>> = {}) {
  const strategies: Record<string, unknown> = {}
  for (const s of PARAM_SCHEMA_FIXTURE.strategies) {
    strategies[s.strategy_id] = {
      key: s.strategy_id,
      name: s.name,
      enabled: s.enabled,
      weight: 1 / 7,
      total_investment: 10_000_000,
      params: { ...s.params, ...(overrides[s.strategy_id] ?? {}) },
    }
  }
  return { strategies }
}

function renderPage() {
  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0, staleTime: 0 },
      mutations: { retry: false },
    },
  })
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <Strategies />
      </MemoryRouter>
    </QueryClientProvider>,
  )
  return { user: userEvent.setup() }
}

beforeEach(() => {
  server.use(
    http.get('/api/strategies', () =>
      HttpResponse.json({ success: true, data: strategiesPayload(), message: '' }),
    ),
  )
})

afterEach(() => server.resetHandlers())

describe('cycle278 F21~F22 — 전략 카드에서 편집기로', () => {
  it('F21 전략 카드마다 "파라미터" 버튼이 있고 누르면 편집기가 열린다', async () => {
    const { user } = renderPage()

    const button = await screen.findByTestId('strategy-params-open-momentum')
    expect(button).toHaveTextContent('파라미터')

    await user.click(button)
    const editor = await screen.findByTestId('strategy-params-editor')
    expect(within(editor).getByTestId('strategy-params-title')).toHaveTextContent(
      '상한가 모멘텀',
    )
    expect(screen.getByTestId('strategy-params-version')).toHaveTextContent(
      PARAM_SCHEMA_FIXTURE.catalog_version,
    )
  })

  it('F22 읽기 전용 요약 4키 그리드는 그대로 남는다 (회귀)', async () => {
    renderPage()

    await screen.findByTestId('strategy-card-momentum')
    expect(screen.getByTestId('strategy-momentum-stop-loss-rate')).toHaveTextContent('-7.5%')
    expect(screen.getByTestId('strategy-momentum-daily-loss-limit')).toBeInTheDocument()
    expect(screen.getByTestId('strategy-momentum-trailing-stop-rate')).toBeInTheDocument()
    expect(screen.getByTestId('strategy-momentum-position-ratio')).toHaveTextContent('25%')
  })

  it('F26 7 전략 전수에 카드와 파라미터 버튼이 렌더된다', async () => {
    renderPage()

    await screen.findByTestId('strategy-card-momentum')
    for (const sid of STRATEGY_IDS) {
      expect(
        screen.getByTestId(`strategy-card-${sid}`),
        `${sid} 카드가 사라졌다 — 편집 수단을 붙이며 전략을 잃으면 안 된다`,
      ).toBeInTheDocument()
      expect(screen.getByTestId(`strategy-params-open-${sid}`)).toBeInTheDocument()
    }
  })
})

describe('cycle278 — 저장 성공 후 요약 값이 갱신된다', () => {
  it('편집기에서 손절률을 고쳐 저장하면 카드 요약이 새 값으로 바뀐다', async () => {
    let saved = false
    server.use(
      http.get('/api/strategies', () =>
        HttpResponse.json({
          success: true,
          data: strategiesPayload(
            saved ? { momentum: { stop_loss_rate: -8.0 } } : {},
          ),
          message: '',
        }),
      ),
      http.put('/api/strategies/:id/params', async () => {
        saved = true
        return HttpResponse.json({
          success: true,
          data: { applied: { stop_loss_rate: -8.0 }, warnings: [] },
          message: '파라미터 저장 완료',
        })
      }),
    )

    const { user } = renderPage()
    await screen.findByTestId('strategy-card-momentum')
    expect(screen.getByTestId('strategy-momentum-stop-loss-rate')).toHaveTextContent('-7.5%')

    await user.click(screen.getByTestId('strategy-params-open-momentum'))
    await screen.findByTestId('strategy-params-editor')

    // 청산 그룹을 열고 손절률을 -8.0 으로
    const header = await screen.findByTestId('strategy-params-group-exit')
    if (!screen.queryByTestId('strategy-params-group-body-exit')) {
      await user.click(header)
    }
    const input = await screen.findByTestId('strategy-params-input-stop-loss-rate')
    await user.clear(input)
    await user.type(input, '-8')

    await user.click(screen.getByTestId('strategy-params-save'))
    await user.click(await screen.findByRole('button', { name: '확인' }))

    await waitFor(() =>
      expect(screen.getByTestId('strategy-momentum-stop-loss-rate')).toHaveTextContent(
        '-8.0%',
      ),
    )
  })
})

describe('cycle278 F25 — 편집기 스키마 쿼리는 retry 를 명시한다', () => {
  it('StrategyParamsEditor.tsx 의 모든 useQuery 에 retry 옵션이 있다', () => {
    const source = readFileSync(
      path.join(__dirname, '..', '..', 'components', 'StrategyParamsEditor.tsx'),
      'utf-8',
    )
    const matches = [...source.matchAll(/useQuery(?:<[^>]+>)?\(\s*\{([\s\S]*?)\}\s*\)/g)]
    expect(matches.length, 'useQuery 호출 0건 — 스키마 fetch 누락 의심').toBeGreaterThanOrEqual(1)
    for (const m of matches) {
      expect(
        /\bretry\s*:\s*(false|0|1|2|3)\b/.test(m[1]),
        'retry 미명시 — e2e ECONNREFUSED 시 기본 retry 누적으로 페이지가 timeout 된다',
      ).toBe(true)
    }
    expect(
      source.includes("'strategy-params-schema'") ||
        source.includes('"strategy-params-schema"'),
      "queryKey 는 ['strategy-params-schema'] 로 고정한다(저장 후 무효화 대상)",
    ).toBe(true)
  })
})
