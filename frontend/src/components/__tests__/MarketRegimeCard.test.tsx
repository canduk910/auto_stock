/**
 * 사이클 2 (2026-05-17): MarketRegimeCard 테스트.
 * 사이클 I (2026-08-03): 표시 정직화(buy_blocked 항상 false → 배너는 block_reason 기반
 * 관찰 라벨) + 지수ETF 레짐(관찰) 소섹션 추가.
 * cycle315 (2026-09-19): 레짐 출처를 외부 dkstock.cloud 에서 **우리 macro 컨테이너**로
 * 옮기면서 화면이 들고 있던 값이 실재와 어긋나 있던 것을 시정한다.
 *
 * 실측 픽스처 출처 = 우리 macro 컨테이너 `GET /api/macro/macro-cycle` 응답
 * (2026-09-19 07:30 KST): regime=defensive · cash_min=75 · vix=14.81 ·
 * buffett_ratio=2.626 · fear_greed_score=69.0 · cycle.phase=expansion.
 *
 * 요구 행위:
 * - B7-A: regime=defensive → red 배지 + 레짐 경보(관찰) amber 배너
 * - B7-C: auto_regime_adjust 토글 클릭 → ConfirmModal → 확인 시 API 호출
 * - B7-D: VIX/Fear&Greed/Buffett/cycle 메트릭 grid 표시
 * - B7-E: API 에러 시 graceful fallback 메시지
 * - B7-F: enabled=false 시 비활성 배지
 * - B7-G: 지수ETF 레짐(관찰) 소섹션 — stage/방어 여부 표시 + 비활성 라벨
 * - FE-R1: 실재 레짐 4종(accumulation/selective/cautious/defensive) 고유 라벨 + 폴백 미사용
 * - FE-R2: REGIME_STYLE 키 = 실재 4종뿐(죽은 키 neutral/aggressive 부재) + 배경색 4종 유니크
 * - FE-R3: cycle 4국면(recovery/expansion/overheating/contraction) 한글 라벨
 * - FE-R4: buffett_ratio 는 비율 계약 — 2.626 → '263%'
 * - FE-R5: 자동 조정 모달이 실재하지 않는 레짐 이름 대신 현재 cash_min 으로 계산한 값을 말한다
 * - FE-R6: 카드가 "부팅 시점 스냅샷" 성격과 기준 시각을 명시하고 /macro 라이브 화면을 가리킨다
 */

import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { describe, expect, it } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { http, HttpResponse } from 'msw'

import MarketRegimeCard from '../MarketRegimeCard'
import { CYCLE_LABEL, REGIME_STYLE } from '../../utils/marketRegime'
import { TestProviders } from '../../test/providers'
import { wrap } from '../../test/factories'
import { server } from '../../test/server'

const SELF = fileURLToPath(import.meta.url.split('?')[0])
const INDEX_CSS = path.resolve(path.dirname(SELF), '..', '..', 'index.css')

/** 2026-09-19 07:30 KST 우리 macro 컨테이너 실측값. */
const defensivePayload = {
  regime: 'defensive',
  regime_desc: '방어 (공포 현금)',
  cycle_phase: 'expansion',
  vix: 14.81,
  fear_greed_score: 69.0,
  buffett_ratio: 2.626,
  cash_min: 75,
  // 사이클 I — buy_blocked 는 이제 항상 false (레짐 매수 게이트 제거). block_reason 만
  // 관찰용 "레짐 경보 사유" 로 유지.
  buy_blocked: false,
  block_reason: 'regime=defensive (방어 (공포 현금))',
  auto_regime_adjust: true,
  cash_usage_ratio: 0.25,
  enabled: true,
  etf_kospi_stage: 4,
  etf_kosdaq_stage: 3,
  etf_defensive: true,
  etf_enabled: true,
}

/** 레짐만 갈아끼운 파생 픽스처 — cash_min 사다리는 macro_lite `REGIME_PARAMS` 정본값. */
const REGIME_CASES: Array<{ regime: string; regime_desc: string; cash_min: number; label: string }> = [
  { regime: 'accumulation', regime_desc: '축적 (탐욕 매수)', cash_min: 25, label: '적극 매수' },
  { regime: 'selective', regime_desc: '선별 (중립 적극)', cash_min: 35, label: '선별 매수' },
  { regime: 'cautious', regime_desc: '신중 (방어 선별)', cash_min: 50, label: '신중' },
  { regime: 'defensive', regime_desc: '방어 (공포 현금)', cash_min: 75, label: '방어' },
]

function themeHex(css: string, token: string): string | null {
  const m = css.match(new RegExp(`--${token}\\s*:\\s*([^;]+);`))
  return m ? m[1].trim().toLowerCase() : null
}

describe('MarketRegimeCard', () => {
  it('B7-A: regime=defensive 시 red 배지 + 레짐 경보(관찰) amber 배너', async () => {
    server.use(
      http.get('/api/market-regime/current', () => HttpResponse.json(wrap(defensivePayload))),
    )
    render(
      <TestProviders>
        <MarketRegimeCard />
      </TestProviders>,
    )

    const badge = await screen.findByTestId('market-regime-badge')
    expect(badge.textContent).toContain('방어')
    // 레짐 경보(관찰) amber 배너 — "매수 차단" 문구 없이 관찰 사유만 (사이클 I 표시 정직화)
    const banner = screen.getByTestId('market-regime-block-banner')
    expect(banner.textContent).toContain('레짐 경보')
    expect(banner.textContent).not.toContain('매수 차단')
    expect(banner.textContent).toContain('defensive')
  })

  it('B7-A2: 자동 조정 OFF(라이브 상태) → 관찰 전용 배너 + 경보에 (권고·관찰) 표기', async () => {
    // 2026-08-07 라이브 = auto_regime_adjust=false, defensive 권고, cash 100% 수동.
    // 대시보드가 "방어/경보/현금75% 권고"와 "실제 cash 100%"를 화해시켜야 한다.
    server.use(
      http.get('/api/market-regime/current', () =>
        HttpResponse.json(wrap({ ...defensivePayload, auto_regime_adjust: false, cash_usage_ratio: 1.0 }))),
    )
    render(
      <TestProviders>
        <MarketRegimeCard />
      </TestProviders>,
    )

    const note = await screen.findByTestId('market-regime-observation-note')
    expect(note.textContent).toContain('관찰 전용')
    expect(note.textContent).toContain('100%')   // 실제 cash 수동
    // 외부 서비스 이름(dkstock)은 더 이상 출처가 아니다 — 우리 macro 컨테이너가 출처다.
    expect(note.textContent).not.toContain('dkstock')
    const banner = screen.getByTestId('market-regime-block-banner')
    expect(banner.textContent).toContain('권고·관찰')
  })

  it('B7-A3: 자동 조정 ON 이면 관찰 전용 배너 미표시', async () => {
    server.use(
      http.get('/api/market-regime/current', () => HttpResponse.json(wrap(defensivePayload))),
    )
    render(
      <TestProviders>
        <MarketRegimeCard />
      </TestProviders>,
    )
    await screen.findByTestId('market-regime-badge')
    expect(screen.queryByTestId('market-regime-observation-note')).toBeNull()
  })

  it.each(REGIME_CASES)(
    'FE-R1: regime=$regime 는 고유 한글 라벨로 렌더되고 비활성 폴백으로 떨어지지 않는다',
    async ({ regime, regime_desc, cash_min, label }) => {
      server.use(
        http.get('/api/market-regime/current', () =>
          HttpResponse.json(wrap({ ...defensivePayload, regime, regime_desc, cash_min }))),
      )
      render(
        <TestProviders>
          <MarketRegimeCard />
        </TestProviders>,
      )

      const badge = await screen.findByTestId('market-regime-badge')
      expect(badge.textContent).toContain(label)
      expect(badge.textContent).not.toContain('비활성')
      // 폴백 배경(bg-gray-50)이 아니라 레짐 고유 색을 입는다
      expect(badge.className).not.toContain('bg-gray-50')
    },
  )

  it('FE-R2: REGIME_STYLE 은 실재 4종만 갖고 배경색이 서로 다르다 (별칭 충돌 포함)', () => {
    expect(Object.keys(REGIME_STYLE).sort()).toEqual(
      ['accumulation', 'cautious', 'defensive', 'selective'],
    )
    // macro_lite `REGIME_MATRIX` 가 낼 수 없는 값 = 죽은 키
    expect(REGIME_STYLE).not.toHaveProperty('neutral')
    expect(REGIME_STYLE).not.toHaveProperty('aggressive')

    const labels = Object.values(REGIME_STYLE).map((s) => s.label)
    expect(new Set(labels).size).toBe(labels.length)

    // Tailwind v4 `@theme` 별칭(emerald≡blue, amber≡beige …) 때문에 클래스 이름이 달라도
    // 실제 hex 가 같을 수 있다 — 토큰까지 풀어서 4종 유니크를 단언한다.
    const css = fs.readFileSync(INDEX_CSS, 'utf8')
    const hexes = Object.values(REGIME_STYLE).map((s) => {
      const m = s.bg.match(/\bbg-([a-z]+)-(\d{2,3})\b/)
      expect(m, `bg 클래스에서 색 토큰을 찾지 못했다: ${s.bg}`).not.toBeNull()
      const hex = themeHex(css, `color-${m![1]}-${m![2]}`)
      expect(hex, `@theme 에 --color-${m![1]}-${m![2]} 미정의`).not.toBeNull()
      return hex
    })
    expect(new Set(hexes).size).toBe(hexes.length)
  })

  it('FE-R3: cycle 4국면이 모두 한글로 렌더된다', async () => {
    expect(Object.keys(CYCLE_LABEL).sort()).toEqual(
      ['contraction', 'expansion', 'overheating', 'recovery'],
    )
    for (const [phase, label] of [
      ['recovery', '회복기'],
      ['overheating', '과열기'],
    ] as const) {
      server.use(
        http.get('/api/market-regime/current', () =>
          HttpResponse.json(wrap({ ...defensivePayload, cycle_phase: phase }))),
      )
      const { unmount } = render(
        <TestProviders>
          <MarketRegimeCard />
        </TestProviders>,
      )
      await waitFor(() => {
        expect(screen.getByTestId('metric-cycle').textContent).toContain(label)
      })
      // 영문 원문이 그대로 노출되면 안 된다
      expect(screen.getByTestId('metric-cycle').textContent).not.toContain(phase)
      unmount()
    }
  })

  it('FE-R4: buffett_ratio 는 비율 계약 — 2.626 → 263%', async () => {
    server.use(
      http.get('/api/market-regime/current', () => HttpResponse.json(wrap(defensivePayload))),
    )
    render(
      <TestProviders>
        <MarketRegimeCard />
      </TestProviders>,
    )
    await waitFor(() => {
      expect(screen.getByTestId('metric-buffett').textContent).toContain('263%')
    })
  })

  it('B7-D: VIX/Fear&Greed/Buffett/cycle 메트릭 grid 표시', async () => {
    server.use(
      http.get('/api/market-regime/current', () => HttpResponse.json(wrap(defensivePayload))),
    )
    render(
      <TestProviders>
        <MarketRegimeCard />
      </TestProviders>,
    )

    await waitFor(() => {
      expect(screen.getByTestId('metric-vix').textContent).toContain('14.81')
      expect(screen.getByTestId('metric-fear-greed').textContent).toContain('69')
      expect(screen.getByTestId('metric-buffett').textContent).toContain('263%')
      expect(screen.getByTestId('metric-cycle').textContent).toContain('확장기')
      expect(screen.getByTestId('metric-cash-ratio').textContent).toContain('25%')
    })
  })

  it('FE-R6: 카드가 부팅 시점 스냅샷 성격 + 기준 시각 + /macro 라이브 링크를 명시', async () => {
    server.use(
      http.get('/api/market-regime/current', () => HttpResponse.json(wrap(defensivePayload))),
    )
    render(
      <TestProviders>
        <MarketRegimeCard />
      </TestProviders>,
    )

    const note = await screen.findByTestId('market-regime-snapshot-note')
    expect(note.textContent).toContain('스냅샷')
    expect(note.textContent).toContain('07:45')       // 기준 시각 = _boot()
    expect(note.textContent).toMatch(/라이브|실시간/)
    const link = screen.getByTestId('market-regime-macro-link')
    expect(link.getAttribute('href')).toBe('/macro')
  })

  it('FE-R7: 자금 사다리 표는 실재 4단(25/35/50/75) 이다', async () => {
    server.use(
      http.get('/api/market-regime/current', () => HttpResponse.json(wrap(defensivePayload))),
    )
    render(
      <TestProviders>
        <MarketRegimeCard />
      </TestProviders>,
    )

    const ladder = await screen.findByTestId('market-regime-cash-ladder')
    for (const { regime, cash_min, label } of REGIME_CASES) {
      const row = screen.getByTestId(`market-regime-cash-ladder-${regime}`)
      expect(row.textContent).toContain(label)
      expect(row.textContent).toContain(String(cash_min))
      // 자금 사용률 = (100 - cash_min)%
      expect(row.textContent).toContain(`${100 - cash_min}%`)
    }
    // 죽은 사다리(neutral=0.5 / aggressive=0.8) 잔재 금지
    expect(ladder.textContent).not.toContain('neutral')
    expect(ladder.textContent).not.toContain('aggressive')
    // 현재 레짐 행이 표시된다
    expect(
      screen.getByTestId('market-regime-cash-ladder-defensive').getAttribute('data-active'),
    ).toBe('true')
  })

  it('B7-C: auto_regime_adjust 토글 클릭 → ConfirmModal 노출', async () => {
    server.use(
      http.get('/api/market-regime/current', () => HttpResponse.json(wrap(defensivePayload))),
    )
    render(
      <TestProviders>
        <MarketRegimeCard />
      </TestProviders>,
    )

    const toggle = await screen.findByTestId('auto-regime-toggle')
    expect(toggle.textContent).toContain('ON')
    fireEvent.click(toggle)
    // ConfirmModal 노출 — 제목 키워드 검증
    await waitFor(() => {
      expect(screen.getByText(/자동 조정 OFF/)).toBeTruthy()
    })
  })

  it('FE-R5: 자동 조정 ON 모달은 실재하지 않는 레짐 대신 현재 cash_min 계산값을 말한다', async () => {
    // auto_regime_adjust=false 상태에서 토글 → pendingValue=true → ON 안내 문구
    server.use(
      http.get('/api/market-regime/current', () =>
        HttpResponse.json(wrap({ ...defensivePayload, auto_regime_adjust: false, cash_usage_ratio: 1.0 }))),
    )
    render(
      <TestProviders>
        <MarketRegimeCard />
      </TestProviders>,
    )

    const toggle = await screen.findByTestId('auto-regime-toggle')
    fireEvent.click(toggle)

    // ConfirmModal 은 testid 를 노출하지 않는다(공용 컴포넌트) — 제목 노드의 부모가 모달 본문
    const modal = (await screen.findByText(/자동 조정 ON/)).parentElement!
    // 죽은 레짐 이름을 예시로 들지 않는다
    expect(modal.textContent).not.toContain('neutral')
    expect(modal.textContent).not.toContain('aggressive')
    // cash_min=75 → (100-75)/100 = 0.25. 현재 100% 에서 25% 로 바뀐다고 실제 값으로 말한다
    expect(modal.textContent).toContain('100%')
    expect(modal.textContent).toContain('25%')
  })

  it('B7-C2: 토글 확인 시 PUT API 호출 + 재조회', async () => {
    let putCallCount = 0
    server.use(
      http.get('/api/market-regime/current', () => HttpResponse.json(wrap(defensivePayload))),
      http.put('/api/market-regime/auto-adjust', () => {
        putCallCount += 1
        return HttpResponse.json(wrap({ auto_regime_adjust: false }, '수동 모드'))
      }),
    )
    render(
      <TestProviders>
        <MarketRegimeCard />
      </TestProviders>,
    )

    const toggle = await screen.findByTestId('auto-regime-toggle')
    fireEvent.click(toggle)
    // ConfirmModal "확인" 클릭
    const confirmBtn = await screen.findByText('확인')
    fireEvent.click(confirmBtn)

    await waitFor(() => {
      expect(putCallCount).toBe(1)
    })
  })

  it('B7-E: API 에러 시 graceful fallback 메시지', async () => {
    server.use(
      http.get('/api/market-regime/current', () => new HttpResponse(null, { status: 500 })),
    )
    render(
      <TestProviders>
        <MarketRegimeCard />
      </TestProviders>,
    )

    await waitFor(() => {
      const card = screen.getByTestId('market-regime-card')
      expect(card.textContent).toMatch(/불러오지 못했|로딩/)
    })
  })

  it('B7-F: enabled=false 시 비활성 배지', async () => {
    const disabledPayload = {
      ...defensivePayload,
      regime: null,
      regime_desc: null,
      enabled: false,
      buy_blocked: false,
      block_reason: null,
      vix: null,
      fear_greed_score: null,
      buffett_ratio: null,
      cash_min: null,
      cycle_phase: null,
      auto_regime_adjust: true,
      cash_usage_ratio: 1.0,
      etf_kospi_stage: null,
      etf_kosdaq_stage: null,
      etf_defensive: null,
      etf_enabled: false,
    }
    server.use(
      http.get('/api/market-regime/current', () => HttpResponse.json(wrap(disabledPayload))),
    )
    render(
      <TestProviders>
        <MarketRegimeCard />
      </TestProviders>,
    )

    const badge = await screen.findByTestId('market-regime-badge')
    expect(badge.textContent).toContain('비활성')
    // 배지에 env 변수 이름을 노출하지 않는다 (운영자가 읽을 문장이 아니다)
    expect(badge.textContent).not.toContain('DKSTOCK_REGIME_ENABLED')
    // 지수ETF 레짐 관찰 비활성 라벨 + null stage "-" 표시
    const etfDisabledLabel = await screen.findByTestId('etf-regime-disabled-label')
    expect(etfDisabledLabel.textContent).toContain('관찰 비활성')
    expect(screen.getByTestId('metric-etf-kospi-stage').textContent).toContain('-')
    expect(screen.getByTestId('metric-etf-kosdaq-stage').textContent).toContain('-')
    expect(screen.getByTestId('metric-etf-defensive').textContent).toContain('-')

    // cycle315 후속(적대 검토) — payload 전체가 null 인 유일한 케이스인데도 4 메트릭이
    // 실제로 '—' 로 떨어지는지는 이제껏 아무것도 안 봤다. VIX/Fear&Greed/Buffett/cycle
    // 포매터가 하나라도 결측을 다르게 다루면(예: '0' 이나 'NaN') 여기서만 잡힌다.
    expect(screen.getByTestId('metric-vix').textContent).toContain('—')
    expect(screen.getByTestId('metric-fear-greed').textContent).toContain('—')
    expect(screen.getByTestId('metric-buffett').textContent).toContain('—')
    expect(screen.getByTestId('metric-cycle').textContent).toContain('—')

    // 자금 사다리 4행 — 레짐이 null 이면 4단 중 어느 것도 "현재 레짐" 이 아니다.
    // active 오판(예: 기본값 'defensive' 로 falls back)이 있으면 여기서 true 가 섞인다.
    for (const { regime } of REGIME_CASES) {
      expect(
        screen.getByTestId(`market-regime-cash-ladder-${regime}`).getAttribute('data-active'),
      ).toBe('false')
    }
  })

  it('B7-G: 지수ETF 레짐(관찰) 소섹션 — 코스피200/코스닥150 stage + 방어 여부 표시', async () => {
    server.use(
      http.get('/api/market-regime/current', () => HttpResponse.json(wrap(defensivePayload))),
    )
    render(
      <TestProviders>
        <MarketRegimeCard />
      </TestProviders>,
    )

    await waitFor(() => {
      expect(screen.getByTestId('metric-etf-kospi-stage').textContent).toContain('4')
      expect(screen.getByTestId('metric-etf-kosdaq-stage').textContent).toContain('3')
      expect(screen.getByTestId('metric-etf-defensive').textContent).toContain('방어')
    })
    // etf_enabled=true 이므로 "관찰 비활성" 라벨 미노출
    expect(screen.queryByTestId('etf-regime-disabled-label')).toBeNull()
  })
})
