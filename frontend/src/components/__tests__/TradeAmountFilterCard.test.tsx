/**
 * 사이클 65 (2026-06-06) Red — F-FE 카테고리: TradeAmountFilterCard (4 케이스).
 *
 * 선행 명세: _workspace/red/cycle65_trade_amount_filter.md (§File 12)
 * 설계 카드 v2: _workspace/cycle65_trade_amount_filter_design_card.md §4
 * 자문 응답: Q1 디폴트 0 + 0~100억 step 1억 + 권장값 마커 1억/5억/10억 + Q6-1 안내 배너
 *
 * testid 매트릭스 (Red 명세 §4.2 기준):
 *   trade-amount-filter-card           — 카드 컨테이너
 *   trade-amount-filter-min-slider     — 최소거래대금 슬라이더 (0~100억, step 1억)
 *   trade-amount-filter-save-button    — 저장 버튼
 *   trade-amount-filter-save-toast     — 저장 성공 안내
 *
 * 요구 행위 (Red 단계 — 컴포넌트 미존재 시 ImportError):
 * - F-FE-1: fetch 후 슬라이더 디폴트 0 렌더
 * - F-FE-2: 슬라이더 조작 + 저장 → PUT body 검증 (min_amount=100억)
 * - F-FE-3: 권장값 마커 (1억/5억/10억) 버튼 클릭 → 슬라이더 값 갱신
 * - F-FE-4: 안내 배너 — 보유/익일청산 보호 + Q6-1 09:00 graceful 명시
 *
 * 패턴 답습: PriceFilterCard.test.tsx (사이클 64) — 동일 fixture/MSW 구조.
 */
import { describe, it, expect } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { http, HttpResponse } from 'msw'

// Red 단계: TradeAmountFilterCard 컴포넌트 미존재 → ImportError 정답
import TradeAmountFilterCard from '../TradeAmountFilterCard'
import { TestProviders } from '../../test/providers'
import { wrap } from '../../test/factories'
import { server } from '../../test/server'

const defaultFilter = {
  min_amount: 0,
}

const activeFilter = {
  min_amount: 500_000_000, // 5억 (Q1 권장 중간값)
}
void activeFilter // Red 명세 예약 — F-FE-2 슬라이더 preset 시나리오용

describe('TradeAmountFilterCard (사이클 65 거래대금 필터)', () => {
  // ---------------------------------------------------------------------------
  // F-FE-1: 초기 fetch + 슬라이더 디폴트 0 렌더
  // ---------------------------------------------------------------------------
  it('F-FE-1: 초기 fetch + 슬라이더 디폴트 0 렌더', async () => {
    server.use(
      http.get('/api/system/trade-amount-filter', () =>
        HttpResponse.json(wrap(defaultFilter)),
      ),
    )

    render(
      <TestProviders>
        <TradeAmountFilterCard />
      </TestProviders>,
    )

    // 카드 렌더 검증
    await screen.findByTestId('trade-amount-filter-card')

    // 슬라이더 표시 + 디폴트 0 (Q1 자문 확정 — 비활성)
    const slider = await screen.findByTestId('trade-amount-filter-min-slider')
    expect((slider as HTMLInputElement).value).toBe('0')
  })

  // ---------------------------------------------------------------------------
  // F-FE-2: 슬라이더 조작 + 저장 → PUT body 검증 (100억)
  // ---------------------------------------------------------------------------
  it('F-FE-2: 슬라이더 조작 + 저장 → PUT body min_amount 검증', async () => {
    let putBody: unknown = null
    server.use(
      http.get('/api/system/trade-amount-filter', () =>
        HttpResponse.json(wrap(defaultFilter)),
      ),
      http.put('/api/system/trade-amount-filter', async ({ request }) => {
        putBody = await request.json()
        return HttpResponse.json(
          wrap({ ...defaultFilter, ...(putBody as object) }),
        )
      }),
    )

    render(
      <TestProviders>
        <TradeAmountFilterCard />
      </TestProviders>,
    )

    // 슬라이더 100억 (10_000_000_000) — Q1 최대값
    const slider = await screen.findByTestId('trade-amount-filter-min-slider')
    fireEvent.change(slider, { target: { value: '10000000000' } })

    await waitFor(() => {
      expect((slider as HTMLInputElement).value).toBe('10000000000')
    })

    // 저장 버튼 클릭
    const saveBtn = await screen.findByTestId('trade-amount-filter-save-button')
    fireEvent.click(saveBtn)

    // PUT 호출 + body 검증
    await waitFor(() => {
      expect(putBody).not.toBeNull()
    })
    const body = putBody as Record<string, unknown>
    expect(body.min_amount).toBe(10_000_000_000)
  })

  // ---------------------------------------------------------------------------
  // F-FE-3: 권장값 마커 (1억/5억/10억) 빠른 선택 버튼
  // ---------------------------------------------------------------------------
  it('F-FE-3: 권장값 마커 (1억/5억/10억) 버튼 클릭 시 슬라이더 값 갱신', async () => {
    server.use(
      http.get('/api/system/trade-amount-filter', () =>
        HttpResponse.json(wrap(defaultFilter)),
      ),
    )

    render(
      <TestProviders>
        <TradeAmountFilterCard />
      </TestProviders>,
    )

    // 5억 권장 버튼 (Q1 자문 권장 중간값)
    const btn5 = await screen.findByRole('button', { name: /5억/ })
    fireEvent.click(btn5)

    const slider = screen.getByTestId(
      'trade-amount-filter-min-slider',
    ) as HTMLInputElement
    await waitFor(() => {
      expect(slider.value).toBe('500000000')
    })

    // 10억 권장 버튼 (Q1 자문 권장 최대값)
    const btn10 = await screen.findByRole('button', { name: /10억/ })
    fireEvent.click(btn10)
    await waitFor(() => {
      expect(slider.value).toBe('1000000000')
    })
  })

  // ---------------------------------------------------------------------------
  // F-FE-4: 안내 배너 — 보유/익일청산 보호 + Q6-1 09:00 graceful 명시
  // ---------------------------------------------------------------------------
  it('F-FE-4: 안내 배너 — 보유/익일청산 보호 + 09:00 graceful 명시', async () => {
    server.use(
      http.get('/api/system/trade-amount-filter', () =>
        HttpResponse.json(wrap(defaultFilter)),
      ),
    )

    render(
      <TestProviders>
        <TradeAmountFilterCard />
      </TestProviders>,
    )

    // 카드 렌더 후 안내 배너 검증 (자문 Q6-1 + 보유 보호 명시)
    await screen.findByTestId('trade-amount-filter-card')

    // 보유 / 익일청산 절대 제외 안 됨 명시
    const protectedNote = await screen.findByText(/보유.*익일청산.*절대 제외 안 됨/)
    expect(protectedNote).toBeInTheDocument()

    // Q6-1 09:00 graceful 명시 — "09:00" + "graceful" 키워드 포함
    const raceNote = screen.getByText(/09:00.*graceful/)
    expect(raceNote).toBeInTheDocument()
  })
})
