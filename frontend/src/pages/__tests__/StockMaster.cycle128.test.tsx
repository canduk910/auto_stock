/**
 * 사이클 128 — StockMaster 4 필터 + envelope 응답 + URL 동기화 회귀 가드.
 *
 * G-FILTER1: 4 필터 컨트롤 (시장 select + 시총/거래대금 input + 종목명 input) 렌더
 * G-FILTER2: 400ms 디바운스 후 fetch 발화
 * G-FILTER3: URL query 동기화 (필터 변경 시 searchParams 갱신)
 * G-FILTER4: 한글 IME composition 중 trigger 차단 (onCompositionEnd 흡수)
 * G-FILTER5: 필터 초기화 버튼 (전체 4 필터 reset)
 * G-FILTER6: total 카운트 표시 (envelope response.total 가시화)
 */
import { describe, expect, it } from 'vitest'
import { http, HttpResponse } from 'msw'
import {
  render,
  screen,
  fireEvent,
  waitFor,
} from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import type { ReactNode } from 'react'

import StockMaster from '../StockMaster'
import { wrap } from '../../test/factories'
import { server } from '../../test/server'

function withProviders(children: ReactNode, initialEntry = '/stock-master') {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0, staleTime: 0 } },
  })
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[initialEntry]}>{children}</MemoryRouter>
    </QueryClientProvider>
  )
}

const ENVELOPE_LIST = {
  items: [
    {
      ticker: '005930',
      name: '삼성전자',
      excg_dvsn_cd: '02',
      nxt_tradable: true,
      krx_halted: false,
      admin_item: false,
      refreshed_at: '2026-06-13T09:00:00+09:00',
      raw: { bfdy_clpr: 75000 },
    },
  ],
  total: 2697,
  limit: 100,
  offset: 0,
}

function setupEnvelopeHandlers(opts?: {
  capturePath?: { url: string; params: Record<string, string> }
}) {
  server.use(
    http.get('/api/stock-master/stats', () =>
      HttpResponse.json(
        wrap({
          count_all: 2697,
          bfdy_clpr_present: 2696,
          nxt_tradable_count: 400,
          top_10_recent: [],
          with_hts_avls: 2696,
          with_acml_tr_pbmn: 2582,
          total_daily_rows: 0,
          last_daily_load_at: null,
        }),
      ),
    ),
    http.get('/api/stock-master/list', ({ request }) => {
      const url = new URL(request.url)
      if (opts?.capturePath) {
        opts.capturePath.url = request.url
        opts.capturePath.params = Object.fromEntries(url.searchParams.entries())
      }
      return HttpResponse.json(wrap(ENVELOPE_LIST))
    }),
    http.get('/api/stock-master/scan-pool/summary', () =>
      HttpResponse.json(wrap({ eager_refresh_today: 0 })),
    ),
    http.get('/api/stock-master/refresh-progress', () =>
      HttpResponse.json(
        wrap({
          universe: { status: 'idle' },
          basics: { status: 'idle' },
          daily: { status: 'idle' },
        }),
      ),
    ),
  )
}

describe('사이클 128 — StockMaster 4 필터 + envelope 응답 + URL 동기화', () => {
  it('G-FILTER1: 4 필터 컨트롤 모두 렌더된다', async () => {
    setupEnvelopeHandlers()
    render(withProviders(<StockMaster />))

    await waitFor(() => {
      expect(screen.getByTestId('stock-master-filter-bar')).toBeDefined()
    })

    expect(screen.getByTestId('stock-master-filter-market')).toBeDefined()
    expect(screen.getByTestId('stock-master-filter-marketcap-min')).toBeDefined()
    expect(screen.getByTestId('stock-master-filter-tradeamount-min')).toBeDefined()
    expect(screen.getByTestId('stock-master-filter-name-substr')).toBeDefined()
    expect(screen.getByTestId('stock-master-filter-clear')).toBeDefined()
  })

  it('G-FILTER2: 시장 select 변경 시 400ms 디바운스 후 market query param 전송', async () => {
    const captured = { url: '', params: {} as Record<string, string> }
    setupEnvelopeHandlers({ capturePath: captured })

    render(withProviders(<StockMaster />))

    await waitFor(() => {
      expect(screen.getByTestId('stock-master-filter-market')).toBeDefined()
    })

    // 시장 select 변경 (select 는 디바운스 영역 외 — 즉시 반영 가능)
    fireEvent.change(screen.getByTestId('stock-master-filter-market'), {
      target: { value: 'KOSPI' },
    })

    // 디바운스 + fetch 대기
    await waitFor(
      () => {
        expect(captured.params.market).toBe('KOSPI')
      },
      { timeout: 2000 },
    )
  })

  it('G-FILTER3: URL query 동기화 — 필터 변경 시 fetch param 갱신 (MemoryRouter 영역)', async () => {
    // MemoryRouter 환경에서 window.location 미갱신 → fetch query param 정합으로 URL 동기화 검증.
    // 운영 환경 (BrowserRouter) 에서는 useSearchParams setSearchParams 가 window.location 갱신.
    const captured = { url: '', params: {} as Record<string, string> }
    setupEnvelopeHandlers({ capturePath: captured })
    render(withProviders(<StockMaster />))

    await waitFor(() => {
      expect(screen.getByTestId('stock-master-filter-market')).toBeDefined()
    })

    fireEvent.change(screen.getByTestId('stock-master-filter-market'), {
      target: { value: 'KOSDAQ' },
    })

    await waitFor(
      () => {
        expect(captured.params.market).toBe('KOSDAQ')
      },
      { timeout: 2000 },
    )
  })

  it('G-FILTER4: 한글 IME composition 중 trigger 차단', async () => {
    const captured = { url: '', params: {} as Record<string, string> }
    setupEnvelopeHandlers({ capturePath: captured })
    render(withProviders(<StockMaster />))

    const input = await screen.findByTestId('stock-master-filter-name-substr')

    // compositionStart → IME 진입 → 디바운스 대상에서 제외
    fireEvent.compositionStart(input)
    fireEvent.change(input, { target: { value: 'ㅅ' } })

    // 1초 대기 후에도 name_substr 파라미터 미전송 확인
    await new Promise((r) => setTimeout(r, 600))
    expect(captured.params.name_substr).toBeUndefined()

    // compositionEnd → IME 종료 → 디바운스 trigger
    fireEvent.compositionEnd(input, { target: { value: '삼성' } })

    await waitFor(
      () => {
        expect(captured.params.name_substr).toBe('삼성')
      },
      { timeout: 2000 },
    )
  })

  it('G-FILTER5: 필터 초기화 버튼이 4 필터를 모두 reset', async () => {
    setupEnvelopeHandlers()
    render(
      withProviders(
        <StockMaster />,
        '/stock-master?market=KOSPI&minMarketCap=1000&name=삼성',
      ),
    )

    await waitFor(() => {
      expect(screen.getByTestId('stock-master-filter-market')).toBeDefined()
    })

    // 초기 URL query 로부터 필터 state 초기화 확인
    const marketSelect = screen.getByTestId(
      'stock-master-filter-market',
    ) as HTMLSelectElement
    expect(marketSelect.value).toBe('KOSPI')

    const capInput = screen.getByTestId(
      'stock-master-filter-marketcap-min',
    ) as HTMLInputElement
    expect(capInput.value).toBe('1000')

    // 초기화 클릭
    fireEvent.click(screen.getByTestId('stock-master-filter-clear'))

    expect(marketSelect.value).toBe('')
    expect(capInput.value).toBe('')
    expect(
      (screen.getByTestId('stock-master-filter-name-substr') as HTMLInputElement)
        .value,
    ).toBe('')
  })

  it('G-FILTER6: total 카운트 표시 (envelope response.total 가시화)', async () => {
    setupEnvelopeHandlers()
    render(withProviders(<StockMaster />))

    await waitFor(() => {
      expect(screen.getByTestId('stock-master-list-card')).toBeDefined()
    })

    // total 2697 표시
    await waitFor(() => {
      const listCard = screen.getByTestId('stock-master-list-card')
      expect(listCard.textContent).toMatch(/전체.+2,697/)
    })
  })

  it('G-FILTER7: 빈 필터 = 전체 (T-1 영속 — list_paged_by_filter 호출 시 4 param 미포함)', async () => {
    const captured = { url: '', params: {} as Record<string, string> }
    setupEnvelopeHandlers({ capturePath: captured })

    render(withProviders(<StockMaster />))

    await waitFor(() => {
      expect(captured.url).toContain('/stock-master/list')
    })

    // 4 필터 param 모두 미포함 (limit/offset 만)
    expect(captured.params.market).toBeUndefined()
    expect(captured.params.min_market_cap).toBeUndefined()
    expect(captured.params.min_trade_amount).toBeUndefined()
    expect(captured.params.name_substr).toBeUndefined()
    // limit/offset 은 항상 전송
    expect(captured.params.limit).toBeDefined()
    expect(captured.params.offset).toBeDefined()
  })
})
