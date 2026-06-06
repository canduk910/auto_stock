/**
 * 사이클 64 (2026-06-06) Red — F-FE 카테고리: PriceFilterCard 단순화 (4 케이스).
 *
 * 선행 명세: _workspace/red/cycle64_price_filter_scanner.md (§F-FE)
 * 설계 카드: _workspace/cycle64_price_filter_scanner_design_card.md §4
 *
 * 사이클 62 → 사이클 64 변화:
 * - mode select 폐기 (사이클 62 F-5 테스트 케이스 폐기)
 * - 안내 배너 갱신 — "WebSocket 구독 대상 필터" + "보유/익일청산 종목 절대 제외 안 됨"
 * - PUT body 에 mode 미포함
 * - PriceFilterMode 타입 폐기
 *
 * 요구 행위 (Red 단계 — 컴포넌트 갱신 전 일부 케이스 FAIL):
 * - F-1: fetch 후 렌더 (min + max 표시) — mode 검증 폐기
 * - F-2: 슬라이더 변경 → state 갱신 (변경 0)
 * - F-3: 저장 버튼 → PUT 호출 + toast (mode 미포함 검증)
 * - F-4: 범위 가드 (max<min UI 검증) (변경 0)
 * - (F-5 mode 토글 폐기 — 사이클 64 mode 단순화)
 */
import { describe, it, expect } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { http, HttpResponse } from 'msw'

// Red 단계: 컴포넌트가 사이클 62 mode select 보존 시 일부 케이스 FAIL
import PriceFilterCard from '../PriceFilterCard'
import { TestProviders } from '../../test/providers'
import { wrap } from '../../test/factories'
import { server } from '../../test/server'

const defaultFilter = {
  min_price: 0,
  max_price: 0,
}

const activeFilter = {
  min_price: 5000,
  max_price: 1_000_000,
}

describe('PriceFilterCard (사이클 64 단순화)', () => {
  it('F-1: fetch 후 렌더 (min + max 표시) — mode select 폐기', async () => {
    server.use(
      http.get('/api/system/price-filter', () =>
        HttpResponse.json(wrap(activeFilter)),
      ),
    )
    render(
      <TestProviders>
        <PriceFilterCard />
      </TestProviders>,
    )

    // 카드 렌더 검증
    await screen.findByTestId('price-filter-card')

    // 2 슬라이더 표시 (min + max) — mode select 폐기
    const minSlider = await screen.findByTestId('price-filter-min-slider')
    expect((minSlider as HTMLInputElement).value).toBe('5000')

    const maxSlider = await screen.findByTestId('price-filter-max-slider')
    expect((maxSlider as HTMLInputElement).value).toBe('1000000')

    // 사이클 64 — mode select 폐기 검증
    const modeSelect = screen.queryByTestId('price-filter-mode-select')
    expect(modeSelect).toBeNull()
  })

  it('F-2: 슬라이더 변경 → state 갱신', async () => {
    server.use(
      http.get('/api/system/price-filter', () =>
        HttpResponse.json(wrap(defaultFilter)),
      ),
    )
    render(
      <TestProviders>
        <PriceFilterCard />
      </TestProviders>,
    )

    const minSlider = await screen.findByTestId('price-filter-min-slider')
    fireEvent.change(minSlider, { target: { value: '10000' } })

    await waitFor(() => {
      expect((minSlider as HTMLInputElement).value).toBe('10000')
    })

    const maxSlider = await screen.findByTestId('price-filter-max-slider')
    fireEvent.change(maxSlider, { target: { value: '500000' } })

    await waitFor(() => {
      expect((maxSlider as HTMLInputElement).value).toBe('500000')
    })
  })

  it('F-3: 저장 버튼 → PUT 호출 (mode 미포함) + toast (즉시 반영)', async () => {
    let putBody: unknown = null
    server.use(
      http.get('/api/system/price-filter', () =>
        HttpResponse.json(wrap(defaultFilter)),
      ),
      http.put('/api/system/price-filter', async ({ request }) => {
        putBody = await request.json()
        return HttpResponse.json(
          wrap({ ...defaultFilter, ...(putBody as object) }),
        )
      }),
    )
    render(
      <TestProviders>
        <PriceFilterCard />
      </TestProviders>,
    )

    // 슬라이더 변경
    const minSlider = await screen.findByTestId('price-filter-min-slider')
    fireEvent.change(minSlider, { target: { value: '5000' } })

    // 저장 버튼 클릭
    const saveBtn = await screen.findByTestId('price-filter-save-button')
    fireEvent.click(saveBtn)

    // PUT 호출 검증
    await waitFor(() => {
      expect(putBody).not.toBeNull()
    })
    const body = putBody as Record<string, unknown>
    expect(body.min_price).toBe(5000)
    // 사이클 64 — PUT body 에 mode 미포함 검증
    expect(body.mode).toBeUndefined()
    expect('mode' in body).toBe(false)

    // toast / 안내 표시 ("즉시 반영" 문구)
    await waitFor(() => {
      const toast = screen.getByTestId('price-filter-save-toast')
      expect(toast.textContent).toMatch(/즉시 반영|반영되었습니다/)
    })
  })

  it('F-4: 범위 가드 (max<min UI 검증)', async () => {
    server.use(
      http.get('/api/system/price-filter', () =>
        HttpResponse.json(wrap(defaultFilter)),
      ),
    )
    render(
      <TestProviders>
        <PriceFilterCard />
      </TestProviders>,
    )

    const minSlider = await screen.findByTestId('price-filter-min-slider')
    const maxSlider = await screen.findByTestId('price-filter-max-slider')

    // max < min 입력 시도 (min=20_000 > max=10_000)
    fireEvent.change(maxSlider, { target: { value: '10000' } })
    fireEvent.change(minSlider, { target: { value: '20000' } })

    // 저장 시도 → 에러 메시지
    const saveBtn = await screen.findByTestId('price-filter-save-button')
    fireEvent.click(saveBtn)

    await waitFor(() => {
      const err = screen.getByTestId('price-filter-validation-error')
      expect(err.textContent).toMatch(/min.*max|범위|작아야|커야/i)
    })
  })

  // F-5 mode 토글 — 사이클 64 폐기 (mode 필드 자체 폐기)
})
