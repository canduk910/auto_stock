/**
 * cycle461 — 비식별 보유(unknown)는 비중 슬라이더·저장 payload 에서 빠진다(서버가 >0 을 422 로 거부).
 * 아래 헬퍼는 Settings.weightUnits.test.tsx 의 것을 그대로 옮겼다.
 *
 * 원 설명: 전략 비중 단위 계약 확정 (2026-08-18) — Settings 프론트 RED.
 *
 * 결함: 백엔드 `routes/strategies.py::update_weights` 가 `v / 100 if v > 1` 로
 * **값 크기에서 단위를 추측**해 1%(=정수 1)를 비율 1.0(=100%)으로 저장했고,
 * 프론트는 `Settings.tsx:83` 의 `totalW <= 1.01 ? Math.round(s.weight * 100) : Math.round(s.weight)`
 * 휴리스틱이 그 오염(Σ=2.98)을 "3개 전략 33% 균등분배" 화면으로 **위장**했다.
 *
 * 확정 계약:
 * - `GET /api/strategies` 의 weight = **비율(0~1)**. 프론트는 분기 없이 `weight * 100` 으로 표시.
 * - `PUT /api/strategies/weights` 바디 = **비율(0.0~1.0)**, Σ ≤ 1.0. 퍼센트 송신 금지.
 * - 로드한 합계가 100% 가 아니면 `weight-sum-warning` 배너로 오염을 **가시화**한다
 *   (휴리스틱 제거만 하면 사용자가 오염 상태를 그대로 저장해 조용한 재정규화를 일으킨다).
 *
 * ⚠️ 슬라이더 내부 상태는 계속 **퍼센트 정수**(min 0 / max 100) — 송신 시점에만 비율로 환산한다.
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { render, screen, within, fireEvent, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'

import Settings from '../Settings'
import { TestProviders } from '../../test/providers'
import { TradingStatusProvider } from '../../contexts/TradingStatusContext'
import { wrap } from '../../test/factories'
import { server } from '../../test/server'

// ---------------------------------------------------------------------------
// 픽스처 — 2026-08-18 운영 비중 (kojiro 집중 + VB/LTV 극소 1%)
// ---------------------------------------------------------------------------

type StrategyRow = { name: string; enabled: boolean; weight: number }

const NAMES: Record<string, string> = {
  kojiro: '고지로 대순환',
  donchian_swing: '돈치안 스윙',
  volatility_breakout: '변동성 돌파',
  long_tail_volatility: '롱테일 변동성 돌파',
  bull_flag_breakout: '눌림목 돌파',
  vcp_breakout: 'VCP 변동성 수축',
  unknown: '비식별 보유',
}

/** 정상 — 비율 규약 준수 (Σ = 1.0) */
const HEALTHY_RATIOS: Record<string, number> = {
  kojiro: 0.6,
  donchian_swing: 0.18,
  volatility_breakout: 0.01,
  long_tail_volatility: 0.01,
  bull_flag_breakout: 0.1,
  vcp_breakout: 0.1,
}

function strategiesPayload(ratios: Record<string, number>): Record<string, StrategyRow> {
  const out: Record<string, StrategyRow> = {}
  for (const [key, weight] of Object.entries(ratios)) {
    out[key] = { name: NAMES[key], enabled: true, weight }
  }
  return out
}

/** PUT /strategies/weights 요청 바디 캡처 (기본 handlers 는 body 무검증) */
let capturedWeights: Record<string, number> | null = null

function mountSettings(ratios: Record<string, number>) {
  server.use(
    http.get('/api/strategies', () => HttpResponse.json(wrap(strategiesPayload(ratios)))),
    http.put('/api/strategies/weights', async ({ request }) => {
      const body = (await request.json()) as { weights: Record<string, number> }
      capturedWeights = body.weights
      return HttpResponse.json(wrap({ updated: true }))
    }),
  )
  return render(
    <TestProviders>
      <TradingStatusProvider>
        <Settings />
      </TradingStatusProvider>
    </TestProviders>,
  )
}

/** "전략 비중" 카드 스코프 — 다른 카드(가용금액·가격필터·거래대금)의 range 와 섞이지 않게 */
async function weightSection(): Promise<HTMLElement> {
  const heading = await screen.findByRole('heading', { name: '전략 비중' })
  return heading.closest('div') as HTMLElement
}

/** 전략 비중 슬라이더 (응답 키 순서 = 렌더 순서) */
async function weightSliders(): Promise<HTMLInputElement[]> {
  const section = await weightSection()
  return within(section).getAllByRole('slider') as HTMLInputElement[]
}

const ORDER = Object.keys(HEALTHY_RATIOS)
const idxOf = (key: string) => ORDER.indexOf(key)

/** 값을 바꿨다가 되돌려 dirty 만 세운다 (합계가 100 이하로만 움직여 재분배 미발화) */
function wiggle(slider: HTMLInputElement) {
  const original = slider.value
  fireEvent.change(slider, { target: { value: '0' } })
  fireEvent.change(slider, { target: { value: original } })
}

async function saveWeights() {
  fireEvent.click(screen.getByRole('button', { name: '비중 저장' }))
  const confirm = await screen.findByRole('button', { name: '확인' })
  fireEvent.click(confirm)
  await waitFor(() => expect(capturedWeights).not.toBeNull())
}

beforeEach(() => {
  capturedWeights = null
  // Settings 가 마운트하는 하위 카드들의 endpoint 보충 (setup.ts onUnhandledRequest='error')
  server.use(
    http.get('/api/strategies/system/auto-start', () => HttpResponse.json(wrap({ auto_start: false }))),
    http.put('/api/strategies/system/auto-start', () => HttpResponse.json(wrap({ auto_start: false }))),
    http.get('/api/strategies/system/cash-usage-ratio', () => HttpResponse.json(wrap({ ratio: 1.0 }))),
    http.get('/api/integrations/dkstock-regime', () =>
      HttpResponse.json(wrap({ enabled: false, source: 'db', env_value: false, db_value: false })),
    ),
    http.get('/api/integrations/kis-mcp', () =>
      HttpResponse.json(wrap({ enabled: false, source: 'db', env_value: false, db_value: false })),
    ),
    http.get('/api/integrations/auto-regime-adjust', () =>
      HttpResponse.json(wrap({ enabled: false, source: 'db', env_value: false, db_value: false })),
    ),
    http.get('/api/integrations/auto-apply', () => HttpResponse.json(wrap({ enabled: false }))),
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
          soft_multiplier: 0.5,
          data_available: true,
          guard_inert: false,
        }),
      ),
    ),
    http.get('/api/integrations/quote-accounts', () => HttpResponse.json(wrap([]))),
  )
})

// ---------------------------------------------------------------------------

describe('Settings — 비식별 보유(unknown) 비중 제외 (cycle461)', () => {
  const WITH_UNKNOWN = { ...HEALTHY_RATIOS, unknown: 0 }

  it('unknown 은 비중 슬라이더에 없다', async () => {
    mountSettings(WITH_UNKNOWN)
    const sliders = await weightSliders()
    expect(sliders).toHaveLength(ORDER.length)
    const section = await weightSection()
    expect(section.textContent).not.toMatch(/비식별 보유/)
  })

  it('저장 payload 에 unknown 이 없다', async () => {
    mountSettings(WITH_UNKNOWN)
    const sliders = await weightSliders()
    wiggle(sliders[idxOf('volatility_breakout')])
    await saveWeights()
    expect(capturedWeights).not.toHaveProperty('unknown')
    const sum = Object.values(capturedWeights!).reduce((a, b) => a + b, 0)
    expect(sum).toBeCloseTo(1.0, 3)
  })
})
