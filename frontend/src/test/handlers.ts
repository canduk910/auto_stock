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
];
