/**
 * 사이클 166 — hts_avls 시가총액 억원 단위 표시 정합 회귀 가드 (Q-C).
 *
 * 결함: formatMarketCap / detail 모달 hts_avls 렌더가 백만원 단위로 가정 → 100배 표시 어긋남.
 * 정정: raw.hts_avls = KIS FHKST01010100 "HTS 시가총액" = 억원 단위.
 *   - 운영 DB 실측 (2026-06-19): 실제시총(원) / hts_avls ≈ 10^8 → 1단위 = 1억원.
 *   - 10,000억 = 1조원 표시.
 */
import { describe, expect, it } from 'vitest'
import { http, HttpResponse } from 'msw'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import type { ReactNode } from 'react'

import StockMaster from '../StockMaster'
import { wrap } from '../../test/factories'
import { server } from '../../test/server'

function withProviders(children: ReactNode) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0, staleTime: 0 } },
  })
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  )
}

const LIST_166 = [
  {
    ticker: '005930',
    name: '삼성전자',
    excg_dvsn_cd: '01',
    nxt_tradable: true,
    krx_halted: false,
    admin_item: false,
    refreshed_at: '2026-06-19T09:00:00+09:00',
    // hts_avls = 15000 억원 = 1.5조원 (리스트 표시)
    raw: { bfdy_clpr: 70000, acml_vol: 1000000, hts_avls: 15000, acml_tr_pbmn: 70000000000 },
  },
]

function setup166Handlers() {
  server.use(
    http.get('/api/stock-master/stats', () =>
      HttpResponse.json(
        wrap({
          count_all: 1,
          bfdy_clpr_present: 1,
          nxt_tradable_count: 1,
          with_hts_avls: 1,
          with_acml_tr_pbmn: 1,
          total_daily_rows: 0,
          last_daily_load_at: null,
          top_10_recent: [],
        }),
      ),
    ),
    http.get('/api/stock-master/list', () => HttpResponse.json(wrap(LIST_166))),
    http.get('/api/stock-master/scan-pool/summary', () =>
      HttpResponse.json(wrap({ eager_refresh_today: 0 })),
    ),
    http.get('/api/stock-master/:ticker/daily', () => HttpResponse.json(wrap([]))),
    http.get('/api/stock-master/005930', () =>
      HttpResponse.json(
        wrap({
          ...LIST_166[0],
          // detail: hts_avls = 500000 억원 = 50.0조원
          raw: { ...LIST_166[0].raw, hts_avls: 500000 },
        }),
      ),
    ),
    http.get('/api/stock-master/005930/history', () => HttpResponse.json(wrap([]))),
  )
}

describe('사이클 166 (Q-C) — hts_avls 억원 단위 표시 정합', () => {
  it('G-166-FE-1: 리스트 시총 hts_avls=15000(억원) → "1.5조원" 표시 (백만원 가정 아님)', async () => {
    setup166Handlers()
    render(withProviders(<StockMaster />))

    await waitFor(() => {
      expect(screen.getByText('005930')).toBeDefined()
    })

    // hts_avls=15000 억원 = 1.5조원. 백만원 가정 시 15000/1000000=0.015조 (잘못된 표시) 차단.
    await waitFor(() => {
      expect(
        screen.getByText('1.5조원'),
        'hts_avls=15000(억원)은 1.5조원으로 표시돼야 함 (사이클 166 억원 정합)',
      ).toBeDefined()
    })
    // 백만원 가정 잔재 차단
    expect(screen.queryByText(/백만원/)).toBeNull()
  })

  it('G-166-FE-2: detail 모달 hts_avls=500000(억원) → "50.0조원" 표시', async () => {
    setup166Handlers()
    render(withProviders(<StockMaster />))

    await waitFor(() => expect(screen.getByText('005930')).toBeDefined())
    fireEvent.click(screen.getByText('005930'))

    await waitFor(() => {
      expect(screen.getByTestId('stock-master-detail-modal')).toBeDefined()
    })

    // hts_avls=500000 억원 = 50.0조원
    await waitFor(() => {
      expect(
        screen.getByText('50.0조원'),
        'detail hts_avls=500000(억원)은 50.0조원으로 표시돼야 함 (사이클 166)',
      ).toBeDefined()
    })
  })

  it('G-166-FE-3: FIELD_LABELS hts_avls 라벨이 "시가총액 (억원)"', async () => {
    setup166Handlers()
    render(withProviders(<StockMaster />))

    await waitFor(() => expect(screen.getByText('005930')).toBeDefined())
    fireEvent.click(screen.getByText('005930'))

    await waitFor(() => {
      expect(screen.getByTestId('stock-master-detail-modal')).toBeDefined()
    })

    // "시가총액 (억원)" 라벨 의무 (백만원 라벨 차단)
    await waitFor(() => {
      expect(
        screen.getByText('시가총액 (억원)'),
        'hts_avls FIELD_LABELS 가 "시가총액 (억원)"이어야 함 (사이클 166)',
      ).toBeDefined()
    })
    expect(screen.queryByText('시가총액 (백만원)')).toBeNull()
  })
})
