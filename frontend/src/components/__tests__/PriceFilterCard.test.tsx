/**
 * 사이클 62 (2026-06-05) Red — F-FE 카테고리: PriceFilterCard (5 케이스).
 *
 * 선행 명세: _workspace/red/cycle62_price_filter.md (§F-FE)
 * 설계 카드: §4.1 PriceFilterCard 신규 컴포넌트
 *
 * 요구 행위 (Red 단계 모두 import 실패 / element 미존재):
 * - F-1: fetch 후 렌더 (mode + min + max 표시)
 * - F-2: 슬라이더 변경 → state 갱신
 * - F-3: 저장 버튼 → PUT 호출 + toast (즉시 반영)
 * - F-4: 범위 가드 (음수 / max<min UI 검증)
 * - F-5: mode 토글 (HARD / WARN / OFF) — 3 모드 (Q4 자문 확정)
 */
import { describe, it, expect } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { http, HttpResponse } from 'msw'

// Red 단계: 컴포넌트 미존재 → import error 정답
import PriceFilterCard from '../PriceFilterCard'
import { TestProviders } from '../../test/providers'
import { wrap } from '../../test/factories'
import { server } from '../../test/server'

const defaultFilter = {
  min_price: 0,
  max_price: 0,
  mode: 'OFF' as const,
}

const activeHardFilter = {
  min_price: 5000,
  max_price: 1_000_000,
  mode: 'HARD' as const,
}

describe('PriceFilterCard', () => {
  it('F-1: fetch 후 렌더 (mode + min + max 표시)', async () => {
    server.use(
      http.get('/api/system/price-filter', () =>
        HttpResponse.json(wrap(activeHardFilter)),
      ),
    )
    render(
      <TestProviders>
        <PriceFilterCard />
      </TestProviders>,
    )

    // 카드 렌더 검증
    await screen.findByTestId('price-filter-card')

    // 3 필드 표시 (mode + min + max)
    await waitFor(() => {
      const modeEl = screen.getByTestId('price-filter-mode-select')
      expect((modeEl as HTMLSelectElement).value).toBe('HARD')
    })

    const minSlider = await screen.findByTestId('price-filter-min-slider')
    expect((minSlider as HTMLInputElement).value).toBe('5000')

    const maxSlider = await screen.findByTestId('price-filter-max-slider')
    expect((maxSlider as HTMLInputElement).value).toBe('1000000')
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

  it('F-3: 저장 버튼 → PUT 호출 + toast (즉시 반영)', async () => {
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

    // 모드 변경 (OFF → HARD)
    const modeSelect = await screen.findByTestId('price-filter-mode-select')
    fireEvent.change(modeSelect, { target: { value: 'HARD' } })

    // 저장 버튼 클릭
    const saveBtn = await screen.findByTestId('price-filter-save-button')
    fireEvent.click(saveBtn)

    // PUT 호출 검증
    await waitFor(() => {
      expect(putBody).not.toBeNull()
    })
    expect((putBody as Record<string, unknown>).min_price).toBe(5000)
    expect((putBody as Record<string, unknown>).mode).toBe('HARD')

    // toast / 안내 표시 ("즉시 반영" 문구)
    await waitFor(() => {
      const toast = screen.getByTestId('price-filter-save-toast')
      expect(toast.textContent).toMatch(/즉시 반영|반영되었습니다/)
    })
  })

  it('F-4: 범위 가드 (음수 / max<min UI 검증)', async () => {
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

  it('F-5: mode 토글 (HARD / WARN / OFF 3 모드)', async () => {
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

    const modeSelect = await screen.findByTestId('price-filter-mode-select')

    // 3 모드 옵션 모두 존재
    const options = Array.from(
      (modeSelect as HTMLSelectElement).options,
    ).map((o) => o.value)
    expect(options).toEqual(expect.arrayContaining(['HARD', 'WARN', 'OFF']))
    expect(options.length).toBe(3) // Q4 자문 — SOFT 모드 없음

    // 토글 전환 검증
    for (const mode of ['HARD', 'WARN', 'OFF']) {
      fireEvent.change(modeSelect, { target: { value: mode } })
      await waitFor(() => {
        expect((modeSelect as HTMLSelectElement).value).toBe(mode)
      })
    }
  })
})
