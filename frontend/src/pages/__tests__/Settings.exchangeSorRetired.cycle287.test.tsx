/**
 * cycle287 (2026-09-12) — Settings.tsx 거래소 선택 UI에서 SOR 제거 + 폐기 배지.
 *
 * 사용자 결정(cycle287 명세 상단, 여러 차례 확정): "SOR 내용들 UI에서 일단 걷어내자" ·
 * "정규장에서는 NXT 필요없어, SOR이 최적호가라는 보장도 없고" · "프리장은 NXT, 나머지는 전부
 * KRX로." 백엔드 `order_engine.py`(cycle287, Green 완료)가 09:00~15:30·16:00~20:00 구간의
 * 실제 주문 거래소를 시각으로 강제하므로, `ExchangeBoardRow` 의 SOR 라디오는 더 이상 새로
 * 저장할 이유가 없는 선택지다.
 *
 * ⚠️ 백엔드는 이번 사이클에서 **무접촉**이다 — `param_catalog.py`(`_EXCHANGE_CHOICES`)와
 * 운영 DB(`strategy_config.params.exchange`)는 여전히 SOR 을 담을 수 있다(cycle287b 대상).
 * 그래서 이미 SOR 로 저장된 전략의 값을 화면이 **지우지 않는다** — 리포 관례(param_catalog.py
 * 절 "deprecated 파라미터는 회색 배지로 보여준다, 숨기지 않는다")를 그대로 따른다. 값 자체는
 * 실제 응답에서 그대로 읽어 보여주므로(하드코딩 아님), 다음에 백엔드가 다른 값을 반환해도
 * 이 화면은 거짓말하지 않는다.
 *
 * ⚠️ 이 사이클은 `StrategyParamsEditor.tsx`(카탈로그 편집기)와 `MarketState.tsx` 는 건드리지
 * 않는다 — 각각 별도의 영구 AST 가드(`_ast_param_key_hardcode.test.ts` "편집기는 파라미터
 * 키 리터럴 0건" / `_ast_market_state_hardcode.test.ts` "KRX·NXT·SOR 리터럴 0건")가 이 두
 * 파일을 스키마 전용 렌더로 강제하고 있어, 그 안에서 'SOR' 값 하나만 특별취급하려면 금지된
 * 키 리터럴(`exchange`) 또는 금지된 거래소명 리터럴(`SOR`)을 새로 심어야 한다. 두 파일은
 * 여전히 백엔드(`param_catalog.py`/`market_state.py`, 이번 사이클 diff 0)가 돌려주는 SOR 을
 * 있는 그대로 보여주는 것이 맞다 — cycle287b 가 백엔드에서 그 값을 deprecated 로 표시하면
 * 이 두 파일은 코드 변경 없이 이미 있는 일반 로직(`choice.deprecated`)으로 따라간다.
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { readFileSync } from 'fs'
import path from 'path'
import { render, screen, fireEvent, within } from '@testing-library/react'
import { http, HttpResponse } from 'msw'

import Settings from '../Settings'
import { TestProviders } from '../../test/providers'
import { TradingStatusProvider } from '../../contexts/TradingStatusContext'
import { wrap } from '../../test/factories'
import { server } from '../../test/server'

type StrategyRow = {
  name: string
  enabled: boolean
  weight: number
  params?: Record<string, unknown>
}

function mountSettings(rows: Record<string, StrategyRow>) {
  server.use(http.get('/api/strategies', () => HttpResponse.json(wrap(rows))))
  return render(
    <TestProviders>
      <TradingStatusProvider>
        <Settings />
      </TradingStatusProvider>
    </TestProviders>,
  )
}

/** "전략별 거래소·매매 보드" 카드로 스코프 — 같은 전략명이 비중/파라미터 카드에도
 *  반복 렌더되므로 페이지 전체에서 텍스트를 찾으면 "multiple elements" 로 깨진다. */
async function exchangeSection(): Promise<HTMLElement> {
  const heading = await screen.findByRole('heading', { name: '전략별 거래소·매매 보드' })
  return heading.closest('div') as HTMLElement
}

beforeEach(() => {
  // Settings 가 마운트하는 하위 카드들의 endpoint 보충 (setup.ts onUnhandledRequest='error').
  // Settings.weightUnits.test.tsx 의 관례를 그대로 답습한다.
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

const SETTINGS_SOURCE = readFileSync(path.join(__dirname, '..', 'Settings.tsx'), 'utf-8')

describe('cycle287 — Settings.tsx 소스에서 SOR 은 선택지가 아니다', () => {
  it('EXCHANGE_OPTIONS 에 값 리터럴 SOR 이 없다 (KRX·NXT 2개만)', () => {
    expect(SETTINGS_SOURCE).not.toMatch(/value:\s*['"]SOR['"]/)
    expect(SETTINGS_SOURCE).toMatch(/value:\s*['"]KRX['"]/)
    expect(SETTINGS_SOURCE).toMatch(/value:\s*['"]NXT['"]/)
  })

  it('주석을 뺀 코드 라인에 따옴표로 감싼 SOR 리터럴이 없다 (값·의미 있는 코드에서 0건)', () => {
    const violations = SETTINGS_SOURCE.split('\n')
      .map((text, idx) => ({ line: idx + 1, text }))
      .filter(({ text }) => !text.trim().startsWith('//') && !text.trim().startsWith('*'))
      .filter(({ text }) => /(['"])SOR\1/.test(text))
    expect(
      violations,
      `Settings.tsx 코드에 따옴표 SOR 리터럴 잔존 — SOR 은 이제 데이터(응답값)로만 등장해야 한다:\n${violations
        .map((v) => `${v.line}: ${v.text.trim()}`)
        .join('\n')}`,
    ).toEqual([])
  })
})

describe('cycle287 — ExchangeBoardRow 렌더 (SOR 저장값 폐기 배지)', () => {
  it('exchange=SOR 로 저장된 전략은 접힌 상태에서도 폐기 배지를 보여준다', async () => {
    mountSettings({
      kojiro: {
        name: '고지로 대순환',
        enabled: true,
        weight: 1.0,
        params: { exchange: 'SOR', tradable_boards: ['main'] },
      },
    })
    const section = await exchangeSection()
    const badge = await within(section).findByTestId('exchange-retired-badge-kojiro')
    expect(badge.textContent).toMatch(/폐기/)
    // 값 자체(SOR)는 지우지 않는다 — 배지 옆에 실제 저장값을 그대로 보여준다.
    expect(within(section).getByText('SOR')).toBeInTheDocument()
  })

  it('exchange=KRX 로 저장된 전략은 폐기 배지가 없다', async () => {
    mountSettings({
      kojiro: {
        name: '고지로 대순환',
        enabled: true,
        weight: 1.0,
        params: { exchange: 'KRX', tradable_boards: ['main'] },
      },
    })
    const section = await exchangeSection()
    await within(section).findByText('고지로 대순환')
    expect(within(section).queryByTestId('exchange-retired-badge-kojiro')).toBeNull()
  })

  it('편집을 열면 라디오는 KRX·NXT 2개뿐이고 SOR 라벨이 없다', async () => {
    mountSettings({
      kojiro: {
        name: '고지로 대순환',
        enabled: true,
        weight: 1.0,
        params: { exchange: 'SOR', tradable_boards: ['main'] },
      },
    })
    const section = await exchangeSection()
    fireEvent.click(within(section).getByRole('button', { name: '편집' }))

    const radios = within(section).getAllByRole('radio')
    expect(radios).toHaveLength(2)
    for (const radio of radios) {
      expect((radio as HTMLInputElement).value).not.toBe('SOR')
    }
    expect(within(section).queryByText(/^SOR$/)).toBeNull()

    // 저장된 값이 선택지에 없으니 "폐기된 값입니다" 안내가 뜬다.
    expect(await within(section).findByText(/폐기된 값입니다/)).toBeInTheDocument()
  })

  it('편집 중 KRX 를 선택하면 저장 시 exchange 만 바뀐 필드로 전송된다 (tradable_boards 미변경분은 안 보낸다)', async () => {
    let captured: { params: Record<string, unknown> } | null = null
    mountSettings({
      kojiro: {
        name: '고지로 대순환',
        enabled: true,
        weight: 1.0,
        params: { exchange: 'SOR', tradable_boards: ['main'] },
      },
    })
    server.use(
      http.put('/api/strategies/:id/params', async ({ request }) => {
        captured = (await request.json()) as { params: Record<string, unknown> }
        return HttpResponse.json(wrap({ applied: captured.params, warnings: [], strategies: {} }))
      }),
    )

    const section = await exchangeSection()
    fireEvent.click(within(section).getByRole('button', { name: '편집' }))
    const row = within(section).getByText('KRX').closest('label') as HTMLElement
    fireEvent.click(within(row).getByRole('radio'))
    fireEvent.click(within(section).getByRole('button', { name: '저장' }))
    fireEvent.click(await screen.findByRole('button', { name: '확인' }))

    await within(section).findByRole('button', { name: '편집' }) // 저장 성공 → 편집모드 종료
    expect(captured).not.toBeNull()
    expect(captured!.params).toEqual({ exchange: 'KRX' })
  })
})
