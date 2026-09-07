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
  // 사이클 F — TE(트레이딩 예지치)/RR(손익비) 성과 (관찰 전용, F-FE6)
  http.get(`${base}/strategies/te`, () => HttpResponse.json(wrap([]))),

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
  http.get(`${base}/history/pnl`, () =>
    HttpResponse.json(
      wrap({
        pairs: [],
        page: 1,
        size: 30,
        total: 0,
        total_pages: 0,
        summary: {
          realized_total_krw: 0,
          realized_rate_pct: 0,
          win_count: 0,
          loss_count: 0,
          even_count: 0,
          win_rate_pct: 0,
          closed_count: 0,
        },
      })
    )
  ),

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

  // 사이클 186 — 장운영상태 (VI/거래정지/종목상태 + 서킷브레이커 휴리스틱).
  // 기본은 0건 정상. 각 테스트에서 server.use 로 오버라이드.
  http.get(`${base}/realtime/market-operation`, () =>
    HttpResponse.json(
      wrap({
        vi_active_count: 0,
        halt_active_count: 0,
        last_event_count: 0,
        iscd_stat_active_count: 0,
        vi_active_sample: [],
        halt_active_sample: [],
        circuit_breaker: {
          suspected: false,
          reasons: [],
          halt_ratio: 0,
          halted: 0,
          observed: 0,
          representative_mkop_cls_code: '',
          halt_reasons_sample: [],
        },
        details: [],
      })
    )
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
  // 사이클 128 — list 응답 schema {items, total, limit, offset} envelope 갱신
  // + 4 query param (market / min_market_cap / min_trade_amount / name_substr) 흡수
  http.get(`${base}/stock-master/list`, ({ request }) => {
    const url = new URL(request.url)
    const limit = parseInt(url.searchParams.get('limit') || '100', 10)
    const offset = parseInt(url.searchParams.get('offset') || '0', 10)
    const nameSubstr = url.searchParams.get('name_substr') || ''
    const items = [
      {
        ticker: '005930',
        name: '삼성전자',
        excg_dvsn_cd: '02',
        nxt_tradable: true,
        krx_halted: false,
        admin_item: false,
        refreshed_at: '2026-06-09T09:00:00+09:00',
        raw: { bfdy_clpr: 75000 },
      },
    ]
    // 검색어 mismatch 시 빈 응답 (필터 동작 검증용)
    const filtered = nameSubstr && !items[0].name.includes(nameSubstr) ? [] : items
    return HttpResponse.json(
      wrap({
        items: filtered,
        total: filtered.length === 0 ? 0 : 2697,
        limit,
        offset,
      }),
    )
  }),
  http.get(`${base}/stock-master/scan-pool/summary`, () =>
    HttpResponse.json(wrap({ eager_refresh_today: 5 }))
  ),
  // 사이클 124 Q1=A — 일봉 데이터 핸들러 (history 보다 먼저 등록해야 LIFO 우선 매칭 정합).
  // cycle266 §C-3 — 종전 목은 `change_rate` 를 전부 진짜 number 로, `bas_dd` 를
  // `YYYYMMDD` 로 만들어 **의도한 계약**만 담고 **실제 응답**을 담지 않았다. 그래서
  // 일봉 탭이 프로덕션에서 3개월 넘게 흰 화면인 동안 목 셋은 계속 초록이었다.
  // 실제 응답: `change_rate`/`prtt_rate` = NUMERIC(8,4) → asyncpg Decimal →
  // pydantic v2 JSON **문자열** / `bas_dd` = DATE 컬럼 → `YYYY-MM-DD`.
  // ⇒ 문자열 행(시정 전 모양)과 숫자 행(A-1 시정 후 모양)을 **함께** 담는다.
  // 가드 = tests/unit/e2e_mocks/test_cycle266_mock_string_change_rate.py
  http.get(`${base}/stock-master/:ticker/daily`, () =>
    HttpResponse.json(
      wrap([
        {
          bas_dd: '2026-09-05',
          open_price: 74000,
          high_price: 75500,
          low_price: 73500,
          close_price: 75000,
          volume: 1000000,
          trade_value: 75000000000,
          change_rate: '1.2000',
          prtt_rate: '0.0000',
        },
        {
          bas_dd: '2026-09-04',
          open_price: 74100,
          high_price: 75600,
          low_price: 73600,
          close_price: 75100,
          volume: 1050000,
          trade_value: 75000000000,
          change_rate: 0.9,
          prtt_rate: '0.0000',
        },
        {
          bas_dd: '2026-09-03',
          open_price: 74200,
          high_price: 75700,
          low_price: 73700,
          close_price: 75200,
          volume: 1100000,
          trade_value: 75000000000,
          change_rate: '0.6000',
          prtt_rate: '0.0000',
        },
        {
          bas_dd: '2026-09-02',
          open_price: 74300,
          high_price: 75800,
          low_price: 73800,
          close_price: 75300,
          volume: 1150000,
          trade_value: 75000000000,
          change_rate: 0.3,
          prtt_rate: '0.0000',
        },
        {
          bas_dd: '2026-09-01',
          open_price: 74400,
          high_price: 75900,
          low_price: 73900,
          close_price: 75400,
          volume: 1200000,
          trade_value: 75000000000,
          change_rate: '0.0000',
          prtt_rate: '0.0000',
        },
      ])
    )
  ),
  // 사이클 169 — migration 036 (사이클 150) 신 스키마 (seq/raw).
  // seq0 최신본 / seq1 직전본 2 스냅샷.
  http.get(`${base}/stock-master/:ticker/history`, () =>
    HttpResponse.json(
      wrap([
        {
          ticker: '005930',
          seq: 0,
          change_type: 'UPDATE',
          raw: { bfdy_clpr: 75000 },
          changed_at: '2026-06-09T09:05:00+09:00',
        },
        {
          ticker: '005930',
          seq: 1,
          change_type: 'UPDATE',
          raw: { bfdy_clpr: 74000 },
          changed_at: '2026-06-09T09:05:00+09:00',
        },
      ])
    )
  ),
  // 사이클 127 — POST 3 라우트 fire-and-forget (즉시 202 Accepted + 백그라운드 task).
  // 응답 schema: RefreshStartedResponse { status: 'started', task_key }
  http.post(`${base}/stock-master/refresh-universe`, () =>
    HttpResponse.json(wrap({ status: 'started', task_key: 'universe' }), { status: 202 })
  ),
  http.post(`${base}/stock-master/basics/refresh`, () =>
    HttpResponse.json(wrap({ status: 'started', task_key: 'basics' }), { status: 202 })
  ),
  http.post(`${base}/stock-master/daily/refresh`, () =>
    HttpResponse.json(wrap({ status: 'started', task_key: 'daily' }), { status: 202 })
  ),
  // 사이클 129 — KIS 종목 마스터 파일 적재 fire-and-forget
  http.post(`${base}/stock-master/master/refresh`, () =>
    HttpResponse.json(wrap({ status: 'started', task_key: 'master' }), { status: 202 })
  ),
  // 사이클 127 — GET refresh-progress (5초 폴링 + RefreshProgressBanner).
  // 디폴트 = 3 작업 모두 idle (배너 미표시).
  http.get(`${base}/stock-master/refresh-progress`, () =>
    HttpResponse.json(
      wrap({
        universe: {
          status: 'idle',
          total: 0,
          processed: 0,
          updated: 0,
          skipped: 0,
          failed: 0,
          started_at: null,
          finished_at: null,
          elapsed_ms: 0,
          error_message: null,
        },
        basics: {
          status: 'idle',
          total: 0,
          processed: 0,
          updated: 0,
          skipped: 0,
          failed: 0,
          started_at: null,
          finished_at: null,
          elapsed_ms: 0,
          error_message: null,
        },
        daily: {
          status: 'idle',
          total: 0,
          processed: 0,
          updated: 0,
          skipped: 0,
          failed: 0,
          started_at: null,
          finished_at: null,
          elapsed_ms: 0,
          error_message: null,
        },
        // 사이클 129 — master 4번째 작업 영역 (KIS 종목 마스터 파일 16:30 KST)
        master: {
          status: 'idle',
          total: 0,
          processed: 0,
          updated: 0,
          skipped: 0,
          failed: 0,
          started_at: null,
          finished_at: null,
          elapsed_ms: 0,
          error_message: null,
        },
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

  // 사이클 I (2026-08-03) — 포트폴리오 리스크 관찰 (Phase 1, 매수 배제 없음).
  // 기본은 빈 스냅샷. 각 테스트에서 server.use 로 오버라이드.
  http.get(`${base}/portfolio/risk`, () =>
    HttpResponse.json(
      wrap({
        total_notional_won: 0,
        total_open_risk_won: 0,
        open_risk_pct_of_net: 0,
        concurrent_positions: 0,
        by_strategy: {},
        by_sector: {},
        top_sector: null,
      }),
    ),
  ),

  // 사이클 I (2026-08-03) — 지수ETF 레짐(관찰) 계산 토글. 5번째 IntegrationToggleCard
  // 토글 — 개별 테스트가 server.use 로 오버라이드하지 않는 한 이 기본값(비활성)으로 렌더되어
  // 기존 IntegrationToggleCard 테스트(4 토글 수동 stub)가 영향받지 않음.
  http.get(`${base}/integrations/etf-regime`, () =>
    HttpResponse.json(wrap({ enabled: false, source: 'db', env_value: false, db_value: false })),
  ),
  http.put(`${base}/integrations/etf-regime`, async ({ request }) => {
    const body = (await request.json()) as Record<string, unknown>
    return HttpResponse.json(
      wrap({ enabled: !!body.enabled, source: 'db', env_value: false, db_value: !!body.enabled }),
    )
  }),

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
