/**
 * MSW 기본 핸들러 — 19개 엔드포인트 기본 응답.
 *
 * 각 테스트는 `server.use(http.get('/api/...', ...))`로 시나리오별 오버라이드.
 */

import { http, HttpResponse } from "msw";
import { wrap, makePosition, makeStrategy, makeTrade } from "./factories";

const base = "/api";

export const handlers = [
  // trading
  http.get(`${base}/trading/status`, () =>
    HttpResponse.json(
      wrap({
        is_running: false,
        env: "vts",
        board: "main",
        strategies: {},
      })
    )
  ),
  http.post(`${base}/trading/start`, () => HttpResponse.json(wrap({ started: true }))),
  http.post(`${base}/trading/stop`, () => HttpResponse.json(wrap({ stopped: true }))),
  http.post(`${base}/trading/restart`, () => HttpResponse.json(wrap({ restarted: true }))),
  http.post(`${base}/trading/manual-sell`, () =>
    HttpResponse.json(wrap({ ordered: true, order_no: "0000111111" }))
  ),

  // strategies
  http.get(`${base}/strategies`, () =>
    HttpResponse.json(
      wrap({
        strategies: [makeStrategy()],
        total_weight: 0.5,
      })
    )
  ),
  http.put(`${base}/strategies/:id/params`, () => HttpResponse.json(wrap({ updated: true }))),
  http.put(`${base}/strategies/weights`, () => HttpResponse.json(wrap({ updated: true }))),

  // balance
  http.get(`${base}/balance`, () =>
    HttpResponse.json(
      wrap({
        positions: [makePosition()],
        total_eval: 720000,
        deposit: 10000000,
        total_asset: 10720000,
      })
    )
  ),

  // performance
  http.get(`${base}/performance/summary`, () =>
    HttpResponse.json(
      wrap({
        total_asset: 10720000,
        daily_profit_rate: 0.02,
        cumulative_return_rate: 0.05,
        deposit: 10000000,
      })
    )
  ),
  http.get(`${base}/performance/daily`, () =>
    HttpResponse.json(wrap({ items: [], total: 0 }))
  ),

  // history
  http.get(`${base}/history`, () =>
    HttpResponse.json(wrap({ items: [makeTrade()], total: 1, page: 1, size: 50 }))
  ),
  http.get(`${base}/history/pnl`, () => HttpResponse.json(wrap({ items: [], total: 0 }))),

  // recommendations
  http.get(`${base}/recommendations`, () =>
    HttpResponse.json(wrap({ items: [], total: 0 }))
  ),
  http.post(`${base}/recommendations/:id/apply`, () =>
    HttpResponse.json(wrap({ applied: true }))
  ),
  http.post(`${base}/recommendations/:id/reject`, () =>
    HttpResponse.json(wrap({ rejected: true }))
  ),

  // log reports
  http.get(`${base}/log-reports`, () =>
    HttpResponse.json(wrap({ items: [], total: 0 }))
  ),
  http.get(`${base}/log-reports/:targetDate`, ({ params }) =>
    HttpResponse.json(
      wrap({
        target_date: params.targetDate,
        summary: "",
        findings: [],
        metrics: {},
      })
    )
  ),
  http.post(`${base}/log-reports/run`, () =>
    HttpResponse.json(wrap({ scheduled: true }))
  ),

  // 사이클 6 — system logs (페이징 + 기간 필터). 기본은 빈 응답, 각 테스트에서 server.use 로 오버라이드.
  http.get(`${base}/logs`, () =>
    HttpResponse.json(wrap({ items: [], total: 0, total_pages: 0 }))
  ),

  // 사이클 103 영역 0 — 실시간 건강 모니터링 logs/search 핸들러.
  // 기본은 빈 응답. 각 테스트에서 q 파라미터 분기로 오버라이드.
  http.get(`${base}/logs/search`, ({ request }) => {
    const url = new URL(request.url)
    const q = url.searchParams.get('q') ?? ''
    if (q.includes('[dispatch_drop_summary]')) {
      return HttpResponse.json(wrap({ logs: [], total: 0, has_more: false }))
    }
    if (q.includes('[callback_exception]')) {
      return HttpResponse.json(wrap({ logs: [], total: 0, has_more: false }))
    }
    if (q.includes('[stale_force_retry]')) {
      return HttpResponse.json(wrap({ logs: [], total: 0, has_more: false }))
    }
    if (q.includes('[ws_auto_restart]')) {
      return HttpResponse.json(wrap({ logs: [], total: 0, has_more: false }))
    }
    return HttpResponse.json(wrap({ logs: [], total: 0, has_more: false }))
  }),

  // 사이클 64 — 가격 필터. 기본은 비활성, 각 테스트에서 server.use 로 오버라이드.
  http.get(`${base}/system/price-filter`, () =>
    HttpResponse.json(wrap({ min_price: 0, max_price: 0 }))
  ),
  http.put(`${base}/system/price-filter`, async ({ request }) => {
    const body = await request.json() as Record<string, unknown>
    return HttpResponse.json(wrap({ min_price: body.min_price ?? 0, max_price: body.max_price ?? 0 }))
  }),

  // 사이클 65 — 거래대금 필터. 기본은 비활성, 각 테스트에서 server.use 로 오버라이드.
  http.get(`${base}/system/trade-amount-filter`, () =>
    HttpResponse.json(wrap({ min_amount: 0 }))
  ),
  http.put(`${base}/system/trade-amount-filter`, async ({ request }) => {
    const body = await request.json() as Record<string, unknown>
    return HttpResponse.json(wrap({ min_amount: body.min_amount ?? 0 }))
  }),

  // 사이클 85 — stock_master (READ-ONLY 5 GET 라우트).
  // 사이클 124 Q3=A — stats 4 → 8 키 (with_hts_avls / with_acml_tr_pbmn / total_daily_rows / last_daily_load_at).
  http.get(`${base}/stock-master/stats`, () =>
    HttpResponse.json(
      wrap({
        count_all: 29,
        bfdy_clpr_present: 27,
        nxt_tradable_count: 12,
        top_10_recent: [
          { ticker: '005930', name: '삼성전자', refreshed_at: '2026-06-09T09:00:00+09:00' },
        ],
        with_hts_avls: 2800,
        with_acml_tr_pbmn: 2700,
        total_daily_rows: 84000,
        last_daily_load_at: '2026-06-13T20:00:00+09:00',
      })
    )
  ),
  http.get(`${base}/stock-master/list`, () =>
    HttpResponse.json(
      wrap([
        {
          ticker: '005930',
          name: '삼성전자',
          excg_dvsn_cd: '01',
          nxt_tradable: true,
          krx_halted: false,
          admin_item: false,
          refreshed_at: '2026-06-09T09:00:00+09:00',
          raw: { bfdy_clpr: 75000 },
        },
      ])
    )
  ),
  http.get(`${base}/stock-master/scan-pool/summary`, () =>
    HttpResponse.json(wrap({ eager_refresh_today: 5 }))
  ),
  // 사이클 124 Q1=A — 일봉 데이터 핸들러 (history 보다 먼저 등록해야 LIFO 우선 매칭 정합).
  http.get(`${base}/stock-master/:ticker/daily`, () =>
    HttpResponse.json(
      wrap(
        Array.from({ length: 5 }, (_, i) => ({
          bas_dd: `202606${(13 - i).toString().padStart(2, '0')}`,
          open_price: 74000 + i * 100,
          high_price: 75500 + i * 100,
          low_price: 73500 + i * 100,
          close_price: 75000 + i * 100,
          volume: 1000000 + i * 50000,
          trade_value: 75000000000,
          change_rate: parseFloat((1.2 - i * 0.3).toFixed(2)),
        }))
      )
    )
  ),
  http.get(`${base}/stock-master/:ticker/history`, () =>
    HttpResponse.json(
      wrap([
        {
          id: 1,
          ticker: '005930',
          change_type: 'INSERT',
          before_raw: null,
          after_raw: { bfdy_clpr: 75000 },
          changed_at: '2026-06-09T09:00:00+09:00',
        },
      ])
    )
  ),
  // 사이클 90 — POST refresh-universe MSW mock (Q24=B 수동 trigger).
  // Q25=A asyncio.Lock + 409 Conflict 가드는 백엔드 영역.
  // Q27=A [stock_master_bulk_refresh] emit 영속 (백엔드 영역).
  http.post(`${base}/stock-master/refresh-universe`, () =>
    HttpResponse.json(
      wrap({ universe: 500, elapsed_ms: 25000 }),
    )
  ),
  // 사이클 126 — POST basics/refresh MSW mock (KIS CTPF1002R 매스 보강)
  http.post(`${base}/stock-master/basics/refresh`, () =>
    HttpResponse.json(
      wrap({ total: 2697, updated: 2697, skipped: 0, failed: 0, elapsed_ms: 270000 }),
    )
  ),
  // 사이클 126 — POST daily/refresh MSW mock (사이클 122 일봉 task 즉시 trigger)
  http.post(`${base}/stock-master/daily/refresh`, () =>
    HttpResponse.json(
      wrap({
        total: 2697,
        fetched: 2697,
        upserted_rows: 270000,
        skipped_fresh: 0,
        failed: 0,
        db_write_failures: 0,
        elapsed_ms: 270000,
        mode: 'incremental',
      }),
    )
  ),

  http.get(`${base}/stock-master/:ticker`, ({ params }) =>
    HttpResponse.json(
      wrap({
        ticker: params.ticker,
        name: '삼성전자',
        excg_dvsn_cd: '01',
        nxt_tradable: true,
        krx_halted: false,
        admin_item: false,
        refreshed_at: '2026-06-09T09:00:00+09:00',
        raw: { bfdy_clpr: 75000, acml_vol: 1000000, nxt_tradable: true, krx_halted: false, admin_item: false },
      })
    )
  ),

  // 사이클 112 (2026-06-12) — KRX 정식 OPEN API 키 관리 (인프라 사전 구성)
  http.get(`${base}/integrations/krx-open-api`, () =>
    HttpResponse.json(
      wrap({
        enabled: false,
        base_url: 'https://data-dbg.krx.co.kr/svc/apis',
        key_masked: '****',
      })
    )
  ),
  http.put(`${base}/integrations/krx-open-api`, () =>
    HttpResponse.json(
      wrap({
        enabled: true,
        base_url: 'https://data-dbg.krx.co.kr/svc/apis',
        key_masked: '****1234',
      })
    )
  ),
];
