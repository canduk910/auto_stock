/**
 * MSW 기본 핸들러 — 46개 라우트 기본 응답(2026-09-11 실측).
 *
 * 각 테스트는 `server.use(http.get('/api/...', ...))`로 시나리오별 오버라이드.
 *
 * ⚠️ **목은 실제 응답을 담는다** — "의도한 계약"만 담은 목은 결함을 3개월간 초록으로
 * 덮는다(cycle266 §C-3: `change_rate` 를 목이 전부 number 로 만들어 실제 문자열
 * 응답의 흰 화면을 아무도 못 봤다). cycle276 에서 `/api/history` 의 `items` 를
 * 실제 응답 키인 `trades` + `total_pages` 로 정직화했다 — 그 전에는 그리드가 빈 표를
 * 렌더해도 목 덕분에 아무 테스트도 깨지지 않았다.
 */

import { http, HttpResponse } from "msw";
import {
  wrap,
  makePosition,
  makeStrategy,
  makeTrade,
  makeTradePair,
  makeLlmEvaluation,
} from "./factories";
// cycle278 — 전략 파라미터 카탈로그 스키마 골든 픽스처(param_catalog.py 에서 기계 생성).
import { PARAM_SCHEMA_FIXTURE } from "./fixtures/paramSchema.fixture";
// cycle282 — 장운영상태(표 + 커서) 골든 픽스처(market_state.py 에서 기계 생성).
import { MARKET_STATE_FIXTURE } from "./fixtures/marketState.fixture";

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
  // cycle278 — 실응답과 **같은 형태**를 돌려준다: `{ applied, warnings, strategies }`.
  // 종전 `{ updated: true }` 는 서버가 한 번도 낸 적 없는 모양이었다 — 목이 *의도한 계약*만
  // 담고 *실제 응답*을 안 담아 3개월 넘게 초록이던 cycle266(종목마스터 일봉 탭)의 재발이다.
  // `applied` 는 서버처럼 요청 바디를 되울린다(화면이 "무엇이 저장됐나" 를 읽는 필드).
  // 형태 대조 가드 = `tests/unit/routes/test_cycle278_params_validation.py`
  // ::test_msw_default_put_handler_matches_live_response_shape
  http.put(`${base}/strategies/:id/params`, async ({ request }) => {
    const body = (await request.json().catch(() => ({}))) as {
      params?: Record<string, unknown>
    }
    return HttpResponse.json(
      wrap(
        { applied: body.params ?? {}, warnings: [], strategies: {} },
        "파라미터 업데이트 완료"
      )
    )
  }),
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
  // ⚠️ 응답 키는 `trades` + `total_pages` 다(백엔드 `src/routes/history.py`,
  //    프론트 타입 `TradeHistoryData`). 구 목의 `items` 는 부정직 — cycle276 시정.
  http.get(`${base}/history`, () =>
    HttpResponse.json(
      wrap({ trades: [makeTrade()], page: 1, size: 20, total: 1, total_pages: 1 })
    )
  ),
  http.get(`${base}/history/pnl`, () =>
    HttpResponse.json(
      wrap({
        // cycle276 — 페어에 `buy_order_nos`/`sell_order_nos`/`pair_key` 가 실린다.
        pairs: [makeTradePair()],
        page: 1,
        size: 30,
        total: 1,
        total_pages: 1,
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

  // cycle276 — AI 매수평가(LLM) 기록.
  // MSW 는 **first-match** 이므로 구체 경로(단건)를 먼저, 배치를 뒤에 둔다.
  http.get(`${base}/llm-evaluations/:orderNo`, ({ params }) =>
    HttpResponse.json(
      wrap(makeLlmEvaluation({ order_no: String(params.orderNo) }))
    )
  ),
  // 배치 요약 기본값 = **빈 맵**(기록 없음). 기록이 있는 상황은 각 테스트가 override 한다 —
  // 기본값을 "전부 있음" 으로 두면 버튼 비활성 분기가 어느 테스트에서도 안 밟힌다.
  http.get(`${base}/llm-evaluations`, () => HttpResponse.json(wrap({}))),

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

  // cycle278 (2026-09-11) — 전략 파라미터 카탈로그 스키마.
  // 편집기(StrategyParamsEditor)는 **이 한 응답**으로 렌더한다(키 하드코딩 0건의 전제).
  // 미등록이면 setup.ts 의 onUnhandledRequest:"error" 로 vitest 가 즉시 붕괴한다.
  // 목 본문은 손으로 쓴 요약이 아니라 param_catalog.py 에서 생성한 골든 픽스처다 —
  // 목이 *의도한 계약*만 담고 *실제 응답*을 안 담아 3개월 초록이던 cycle266 재발 차단.
  http.get(`${base}/strategies/params-schema`, () =>
    HttpResponse.json(wrap(PARAM_SCHEMA_FIXTURE))
  ),

  // cycle282 (2026-09-11) — 장운영상태(거래소 실제 장 운영 상태) 표 + 커서.
  // **표와 커서가 한 응답에서 나온다** — 둘을 따로 부르면 자정·경계 순간에 갈라져
  // 화면이 거짓말을 한다(M9). 그래서 목도 한 응답으로 둔다.
  //
  // 기본 변종은 평범한 정규장(13:05:22). 동시 중첩(08:35)·장 종료(20:30)·미리보기가
  // 필요한 시나리오는 각 테스트가 `server.use(...)` 로 다른 변종을 덮어쓴다.
  // 목 본문은 손으로 쓴 요약이 아니라 `market_state.py` 에서 생성한 골든 픽스처다 —
  // 목이 *의도한 계약*만 담고 *실제 응답*을 안 담아 3개월 초록이던 cycle266 재발 차단.
  http.get(`${base}/market-state`, () => HttpResponse.json(wrap(MARKET_STATE_FIXTURE))),

  // cycle285 (2026-09-13) — 야간작업 현황. `/api/market-state`(위) 와 별도 엔드포인트라
  // 목도 별도다 — 표 조회가 실패해도 이쪽은 독립적으로 정상일 수 있다는 계약을 목에서도
  // 반영한다. 기본 변종 = 평일 저녁, 대부분 완료·일부 확인불가/건너뜀 섞은 대표 상태.
  // 시나리오별 다른 상태가 필요하면 각 테스트가 `server.use(...)` 로 덮어쓴다.
  http.get(`${base}/market-ops`, () =>
    HttpResponse.json(
      wrap({
        as_of_kst: "2026-09-13T20:35:00+09:00",
        is_trading_day: true,
        trading_day_source: "kis",
        engine: {
          running: true,
          phase: "closing",
          heartbeat_at: "2026-09-13T20:34:40+09:00",
        },
        tasks: [
          {
            id: "stock_master_basics_refresh",
            label_ko: "종목마스터 기본정보 보강",
            scheduled_at: "16:10",
            status: "done",
            last_success_at: "2026-09-13T16:12:03+09:00",
            evidence: { total: 2700, processed: 2700, updated: 2700, skipped: 0, failed: 0 },
            note: null,
          },
          {
            id: "stock_master_daily_purge",
            label_ko: "일봉 보관기간 정리",
            scheduled_at: "16:15",
            status: "unknown",
            last_success_at: null,
            evidence: { retention_tail: "2026-02-04" },
            note: "이 작업은 성공 마커를 남기지 않는다 — 보관 경계값만으로는 오늘 실행 여부를 알 수 없다",
          },
          {
            id: "evening_funnel_capture",
            label_ko: "저녁 잠정 퍼널 캡처",
            scheduled_at: "16:20",
            status: "done",
            last_success_at: "2026-09-13T16:20:11+09:00",
            evidence: { snapshot_rows_today: 61 },
            note: null,
          },
          {
            id: "stock_master_master_load",
            label_ko: "종목마스터 파일(.mst) 적재",
            scheduled_at: "16:30",
            status: "done",
            last_success_at: "2026-09-13T16:30:15+09:00",
            evidence: { total: 3583, processed: 3583, updated: 3583, skipped: 0, failed: 0 },
            note: null,
          },
          {
            id: "stock_master_financial_load",
            label_ko: "재무 데이터 적재(주 1회)",
            scheduled_at: "16:40",
            status: "skipped_weekly",
            last_success_at: "2026-09-11T16:40:01+09:00",
            evidence: {},
            note: "주 1회 게이트 — 오늘 미실행이 정상일 수 있다",
          },
          {
            id: "quote_token_refresh",
            label_ko: "보조 시세계정 토큰 강제 재발급",
            scheduled_at: "19:00",
            status: "unknown",
            last_success_at: null,
            evidence: {},
            note: "이 작업은 성공 마커를 남기지 않는다 — 서버 로그(system_logs) 로만 확인 가능",
          },
          {
            id: "nxt_post_buy_stop",
            label_ko: "NXT 애프터 신규 매수 중단",
            scheduled_at: "19:50",
            status: "done",
            last_success_at: null,
            evidence: {},
            note: "시각 기준 컷오프 — 별도 산출물 없음(코드가 그 시각부터 매수를 막는다는 사실만 보장)",
          },
          {
            id: "recommendation",
            label_ko: "AI 매매자문",
            scheduled_at: "20:00",
            status: "done",
            last_success_at: "2026-09-13T20:00:42+09:00",
            evidence: { recommendation_rows_today: 7 },
            note: null,
          },
          {
            id: "full_universe_load",
            label_ko: "전체 유니버스 적재",
            scheduled_at: "20:00:05",
            status: "done",
            last_success_at: null,
            evidence: { total: 3577, processed: 3577, updated: 120, skipped: 3457, failed: 0 },
            note: null,
          },
          {
            id: "metrics_snapshot",
            label_ko: "매매지표 1차 스냅샷",
            scheduled_at: "20:05",
            status: "overwritten",
            last_success_at: null,
            evidence: {},
            note: "정산(21:30) 의 최종 분석이 이 값을 덮어쓴다 — 정산 이후 'overwritten' 은 결함이 아니다",
          },
          {
            id: "cloud_report_routine",
            label_ko: "클라우드 로그 분석 루틴(외부)",
            scheduled_at: null,
            status: "unknown",
            last_success_at: null,
            evidence: { ext_provider: null, ext_model: null },
            note: "이 코드베이스에 예정 시각 상수가 없다 — 외부 크론이 부른다",
          },
          {
            id: "stock_master_daily_load",
            label_ko: "일봉(KIS) 적재",
            scheduled_at: "20:30",
            status: "scheduled",
            last_success_at: "2026-09-11T18:10:13+09:00",
            evidence: { daily_head: "2026-09-11", daily_rows_today: 0 },
            note: "daily_head 가 오늘이 아니면 다음 영업일 아침 재기동 전까지 그대로다",
          },
          {
            id: "settlement",
            label_ko: "정산(전략별 실적 집계)",
            scheduled_at: "21:30",
            status: "scheduled",
            last_success_at: null,
            evidence: { daily_performance_rows_today: 0 },
            note: null,
          },
          {
            id: "log_analysis",
            label_ko: "일일 로그 분석(AI)",
            scheduled_at: "21:30",
            status: "scheduled",
            last_success_at: null,
            evidence: { model: null, has_api_metrics: false },
            note: null,
          },
        ],
        evidence_errors: [],
      })
    )
  ),

  // ── cycle303 (2026-09-18) — macro_lite 이식 1단계 5 엔드포인트 ──────────────
  // 🔴 이 5개는 wrap() 을 쓰지 않는다 — macro 서비스는 독립 FastAPI 프로세스라
  // 원본 계약(`{ <section>, updated_at, errors }`)을 그대로 반환한다(우리 ApiResponse
  // 래퍼 밖). 실측 근거 = `packaging/macro_lite/backend/macro_lite/{fetcher,cycle,regime}.py`
  // 반환문 + `packaging/macro_lite/backend/tests/test_service_router.py` 의 mock 기본값
  // (`_default_yield_curve`/`_default_credit_spread`/`_mock_fetchers` 의 currencies/
  // commodities, 2026-09-18 읽음). macro-cycle 의 scores/regime 필드는 `cycle.py::
  // determine_cycle_phase` L238-264 + `regime.py::determine_regime` L215-227 반환 shape.
  http.get(`${base}/macro/yield-curve`, () =>
    HttpResponse.json({
      yield_curve: {
        current: { "3m": 5.0, "5y": 4.0, "10y": 4.2, "30y": 4.5 },
        spread_10y_3m: -0.8,
        history: [
          { date: "2020-01-01", y3m: 1.5, y10y: 1.8, spread: 0.3 },
          { date: "2020-06-01", y3m: 1.4, y10y: 1.6, spread: 0.2 },
        ],
        inverted: true,
        events: { recessions: [], bear_markets: [] },
      },
      updated_at: "2026-09-18T09:00:00+09:00",
      errors: [],
    })
  ),
  http.get(`${base}/macro/credit-spread`, () =>
    HttpResponse.json({
      credit_spread: {
        oas_current: 3.5,
        oas_history_10y: [{ date: "2020-01-01", oas: 3.5 }],
        oas_history_5y: [{ date: "2020-01-01", oas: 3.5 }],
        oas_history: [{ date: "2020-01-01", oas: 3.5 }],
        oas_stats: { p10: 2.5, p25: 3.0, p75: 5.0, p90: 6.5, mean: 4.0, max: 10.0, max_date: "2020-03-23" },
        oas_percentile: 40.0,
        oas_zscore: -0.2,
        oas_sentiment: "normal",
        ig_current: 1.2,
        hy_ig_spread: 2.3,
        partial_failure: [],
        events: { recessions: [], bear_markets: [] },
      },
      updated_at: "2026-09-18T09:00:00+09:00",
      errors: [],
    })
  ),
  http.get(`${base}/macro/currencies`, () =>
    HttpResponse.json({
      currencies: [
        {
          symbol: "USDKRW=X",
          name: "USD/KRW",
          price: 1300.0,
          prev_close: 1290.0,
          change: 10.0,
          change_pct: 0.7,
          sparkline: [],
        },
      ],
      updated_at: "2026-09-18T09:00:00+09:00",
      errors: [],
    })
  ),
  http.get(`${base}/macro/commodities`, () =>
    HttpResponse.json({
      commodities: [
        {
          symbol: "GC=F",
          name: "금",
          price: 2000.0,
          prev_close: 1990.0,
          change: 10.0,
          change_pct: 0.5,
          sparkline: [],
        },
      ],
      updated_at: "2026-09-18T09:00:00+09:00",
      errors: [],
    })
  ),
  http.get(`${base}/macro/macro-cycle`, () =>
    HttpResponse.json({
      cycle: {
        phase: "expansion",
        phase_label: "확장기",
        phase_desc: "양의 수익률곡선, 낮은 VIX, 좁은 스프레드",
        confidence: 62,
        scores: {
          yield_curve: { score: 0.15, weight: 0.3, signal: "스프레드 +1.00%" },
          credit_spread: { score: 0.06, weight: 0.2, signal: "안정" },
          vix: { score: 0.06, weight: 0.2, signal: "18.0 (보통)" },
          sector_rotation: { score: 0.0375, weight: 0.15, signal: "혼합" },
          dollar: { score: 0.0375, weight: 0.15, signal: "보합" },
        },
        leader_sectors: ["XLK", "XLY"],
        // cycle308/310 — 원 패키지가 2026-09-19 에 반환에 얹은 4국면 총점.
        // 불변식: phase == argmax(final_scores) · confidence == round((1위−2위)×200).
        // 여기 62 = round((0.345 − 0.035) × 200) = 62 로 실제 계약과 맞춘 값이다.
        final_scores: { recovery: 0.06, expansion: 0.345, overheating: 0.035, contraction: 0.21 },
      },
      regime: {
        regime: "cautious",
        regime_desc: "신중 (방어 선별)",
        params: {},
        vix: 18.0,
        buffett_ratio: 1.5,
        fear_greed_score: 50,
        buffett_level: "high",
        fg_level: "neutral",
        credit_adjustment: null,
        credit_override: null,
      },
      updated_at: "2026-09-18T09:00:00+09:00",
      errors: [],
    })
  ),

  // cycle310 — S&P500 주간 종가. `macro_lite/` vendor 가 아니라 우리 `macro/sp500.py` 가
  // 돌려준다. 실측 모양(2026-09-18 로컬 `get_sp500()` 호출): 주간 5,151포인트,
  // 1927-12-26 ~ 2026-09-14. 여기서는 금리차·하이일드 목의 날짜 범위에 맞춰 잘라 넣는다.
  http.get(`${base}/macro/sp500`, () =>
    HttpResponse.json({
      sp500: {
        history: [
          { date: "2026-08-24", close: 7521.3 },
          { date: "2026-08-31", close: 7588.4 },
          { date: "2026-09-07", close: 7656.98 },
          { date: "2026-09-14", close: 7637.76 },
        ],
        symbol: "^GSPC",
        interval: "1wk",
        first: "2026-08-24",
        last: "2026-09-14",
        count: 4,
      },
      updated_at: "2026-09-18T09:00:00+09:00",
      errors: [],
    })
  ),

  // ── cycle315 (2026-09-19) — 시장 레짐 (MarketRegimeCard) ────────────────────
  // 종전에는 MSW 기본 핸들러가 아예 없어서 Dashboard 를 렌더하는 테스트마다 카드가
  // unhandled request → 에러 폴백으로 떨어졌다. 값은 **실측**이다 — 우리 macro 컨테이너
  // `GET /api/macro/macro-cycle` (2026-09-19 07:30 KST) 의 `regime` 블록 + `cycle.phase`
  // 를 백엔드 `/api/market-regime/current` 가 그대로 실어 보낸다.
  // ⚠️ buffett_ratio 는 **비율**(2.626 = 262.6%) 이다. 퍼센트 스케일 숫자를 넣지 마라 —
  //    화면이 ×100 해서 그리므로 목이 스케일을 틀리면 26,260% 가 초록으로 통과한다.
  http.get(`${base}/market-regime/current`, () =>
    HttpResponse.json(
      wrap({
        regime: "defensive",
        regime_desc: "방어 (공포 현금)",
        cycle_phase: "expansion",
        vix: 14.81,
        fear_greed_score: 69.0,
        buffett_ratio: 2.626,
        cash_min: 75,
        // 레짐은 매수에 개입하지 않는다 — buy_blocked 는 항상 false
        buy_blocked: false,
        block_reason: "regime=defensive (방어 (공포 현금))",
        auto_regime_adjust: false,
        cash_usage_ratio: 1.0,
        enabled: true,
        etf_kospi_stage: null,
        etf_kosdaq_stage: null,
        etf_defensive: null,
        etf_enabled: false,
      })
    )
  ),
  http.get(`${base}/market-regime/history`, () => HttpResponse.json(wrap([]))),
  http.put(`${base}/market-regime/auto-adjust`, () =>
    HttpResponse.json(wrap({ auto_regime_adjust: false }, "수동 모드"))
  ),
];
