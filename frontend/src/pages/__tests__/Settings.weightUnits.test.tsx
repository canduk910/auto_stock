/**
 * 전략 비중 단위 계약 확정 (2026-08-18) — Settings 프론트 RED.
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

/** 오염 — 1% 두 개가 `v > 1` 추론 변환을 못 타 1.0(=100%)으로 저장된 실측 상태 (Σ = 2.98) */
const POLLUTED_RATIOS: Record<string, number> = {
  ...HEALTHY_RATIOS,
  volatility_breakout: 1.0,
  long_tail_volatility: 1.0,
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

describe('Settings 전략 비중 단위 계약 (2026-08-18)', () => {
  it('1퍼센트_전략이_슬라이더에_1로_표시된다', async () => {
    mountSettings(HEALTHY_RATIOS)
    const sliders = await weightSliders()
    expect(sliders).toHaveLength(ORDER.length)
    expect(sliders[idxOf('volatility_breakout')].value).toBe('1')
    expect(sliders[idxOf('long_tail_volatility')].value).toBe('1')
    expect(sliders[idxOf('kojiro')].value).toBe('60')
  })

  it('저장시_퍼센트가_아니라_비율로_전송된다', async () => {
    mountSettings(HEALTHY_RATIOS)
    const sliders = await weightSliders()
    wiggle(sliders[idxOf('volatility_breakout')])
    await saveWeights()

    const vb = capturedWeights!.volatility_breakout
    // 비율이면 0.01 근방. 퍼센트(=1)로 보내면 백엔드 Σ 가드에 걸리고 1%가 100%로 저장된다.
    expect(vb).toBeGreaterThan(0)
    expect(vb).toBeLessThan(0.05)
  })

  it('전송_비중_합이_1이다', async () => {
    mountSettings(HEALTHY_RATIOS)
    const sliders = await weightSliders()
    wiggle(sliders[idxOf('volatility_breakout')])
    await saveWeights()

    const sum = Object.values(capturedWeights!).reduce((a, b) => a + b, 0)
    expect(sum).toBeCloseTo(1.0, 3)
  })

  it('오염_응답을_균등분배로_위장하지_않는다', async () => {
    mountSettings(POLLUTED_RATIOS)
    const sliders = await weightSliders()
    // 오염돼도 각 전략의 저장값을 있는 그대로 보여야 한다 (kojiro 60% / VB 100%)
    expect(sliders[idxOf('kojiro')].value).toBe('60')
    expect(sliders[idxOf('volatility_breakout')].value).toBe('100')
    expect(sliders[idxOf('long_tail_volatility')].value).toBe('100')
    // 상대 정규화가 만들어내던 "3개 전략 33% 균등분배" 위장 화면이 남아 있으면 안 된다
    const section = await weightSection()
    expect(section.textContent).not.toMatch(/33%/)
  })

  it('합계_이상시_경고_배너가_보인다', async () => {
    mountSettings(POLLUTED_RATIOS)
    await weightSliders()
    expect(await screen.findByTestId('weight-sum-warning')).toBeInTheDocument()
  })

  it('정상_합계에서는_경고_배너가_없다', async () => {
    mountSettings(HEALTHY_RATIOS)
    await weightSliders()
    expect(screen.queryByTestId('weight-sum-warning')).toBeNull()
  })

  it('왕복_멱등성', async () => {
    mountSettings(HEALTHY_RATIOS)
    const sliders = await weightSliders()
    wiggle(sliders[idxOf('kojiro')])
    await saveWeights()

    for (const [key, ratio] of Object.entries(HEALTHY_RATIOS)) {
      expect(capturedWeights![key], `${key} 왕복 오차`).toBeCloseTo(ratio, 2)
      expect(Math.abs(capturedWeights![key] - ratio), `${key} 왕복 오차 ±0.002`).toBeLessThanOrEqual(0.002)
    }
  })
})

// ---------------------------------------------------------------------------
// 적대적 리뷰 시정 (2026-08-18) — R-HIGH / R-MED-1 / R-MED-2
//
// 배너·저장차단 판정을 **서버 저장값(비율)** 기준으로 전환한 계약의 봉인.
//   R-HIGH  : 오염 상태에서 슬라이더 한 번이면 overflow 재분배가 오염 비율을 보존한 채
//             Σ 만 100 으로 눌러 배너를 지웠고, 그대로 저장하면 DB Σ 가 1.0 이 되어
//             `[weight_config_anomaly]` 탐지기가 영구 침묵했다 → 저장 자체를 차단한다.
//   R-MED-1 : 4dp 비율 → 정수% 반올림 누적오차(전략 n개면 최대 ±n/2 %p)가 ±1%p 임계를
//             넘겨 **DB 가 정상인데** 배너가 고정 점등되던 오탐.
//   R-MED-2 : `totalWeight` 는 편집 중 UI 상태라 슬라이더를 내리기만 해도 발화 + 문구 거짓.
// ---------------------------------------------------------------------------

/** 균등분배 왕복 픽스처 — Σ(비율) = 1.0 (정상) 인데 재로드 UI 합은 102 가 되는 조합.
 *  검산: Math.round(0.1667*100)=17, Math.round(0.1666*100)=17 → 17×6 = 102 ≠ 100.
 *  구 임계(totalWeight < 99 || > 101)였다면 정상 DB 를 오염으로 신고했다. */
const EVEN_SPLIT_RATIOS: Record<string, number> = {
  kojiro: 0.1667,
  donchian_swing: 0.1667,
  volatility_breakout: 0.1667,
  long_tail_volatility: 0.1667,
  bull_flag_breakout: 0.1666,
  vcp_breakout: 0.1666,
}

const saveButton = () => screen.getByRole('button', { name: '비중 저장' }) as HTMLButtonElement

describe('Settings 비중 오염 복구 UX (2026-08-18 적대적 리뷰 시정)', () => {
  it('오염_상태에서_슬라이더를_건드려도_배너가_사라지지_않는다', async () => {
    mountSettings(POLLUTED_RATIOS)
    const sliders = await weightSliders()
    expect(await screen.findByTestId('weight-sum-warning')).toBeInTheDocument()

    // BFB 10 → 11 : overflow 재분배가 발화해 편집 중 합(totalWeight)은 101 로 눌린다.
    fireEvent.change(sliders[idxOf('bull_flag_breakout')], { target: { value: '11' } })

    // 배너는 서버 저장값(Σ=2.98) 기준이므로 편집으로 세탁되지 않는다.
    const banner = screen.getByTestId('weight-sum-warning')
    expect(banner).toBeInTheDocument()
    expect(banner.textContent).toMatch(/100%를 초과/)
    expect(banner.textContent).toMatch(/298%/)
    expect(banner.textContent).toMatch(/운영 DB/)
  })

  it('오염_상태에서는_저장_버튼이_잠긴다', async () => {
    mountSettings(POLLUTED_RATIOS)
    const sliders = await weightSliders()
    fireEvent.change(sliders[idxOf('bull_flag_breakout')], { target: { value: '11' } })
    // dirty=true 인데도 오염(Σ>1) 이면 저장 불가 — 오염 비율의 조용한 정규화 차단
    expect(saveButton()).toBeDisabled()
  })

  it('균등분배_왕복에서_배너가_오탐하지_않는다', async () => {
    mountSettings(EVEN_SPLIT_RATIOS)
    const sliders = await weightSliders()
    // 재로드 UI 합은 102 (반올림 누적오차) — 그러나 서버 Σ 는 1.0 이므로 정상이다.
    const uiTotal = sliders.reduce((sum, el) => sum + Number(el.value), 0)
    expect(uiTotal).toBe(102)
    expect(screen.queryByTestId('weight-sum-warning')).toBeNull()
  })

  it('슬라이더를_내려_편집_중_합이_줄어도_배너가_없다', async () => {
    mountSettings(HEALTHY_RATIOS)
    const sliders = await weightSliders()
    fireEvent.change(sliders[idxOf('kojiro')], { target: { value: '10' } })
    // 편집 중 합 = 50 이지만 저장값은 멀쩡하다 — "저장된 비중 합" 문구가 거짓이 되면 안 된다.
    const uiTotal = (await weightSliders()).reduce((sum, el) => sum + Number(el.value), 0)
    expect(uiTotal).toBeLessThan(99)
    expect(screen.queryByTestId('weight-sum-warning')).toBeNull()
  })

  it('정상_상태에서는_저장_버튼이_열린다', async () => {
    mountSettings(HEALTHY_RATIOS)
    const sliders = await weightSliders()
    expect(saveButton()).toBeDisabled() // dirty 이전
    wiggle(sliders[idxOf('volatility_breakout')])
    expect(saveButton()).toBeEnabled()
  })
})
