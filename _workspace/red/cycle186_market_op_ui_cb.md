# 사이클 186 Red — 장운영상태 UI + 서킷브레이커 휴리스틱 (관찰성 전용)

승인 계획: `~/.claude/plans/hazy-prancing-cookie.md`
TDD: tdd-engineer Red → backend-dev + frontend-dev Green → tester. domain-expert 불요 (매수 가드 X).

## 배경 (왜)
사이클 149 가 H0UNMKO0 로 VI/거래정지/종목상태를 백엔드 추적 (`market_operation_monitor.py`) 하나
목적이 stale 회피뿐 → getter 소비처 0건 → 운영자가 볼 화면 0. 서킷브레이커(전 시장 매매거래중단)도 미인지.
사이클 186 = 표시-전용 (CB 중엔 KRX 가 주문 자연 거부 → risk/order 변경 0). CB 는 계측-우선 + best-effort 휴리스틱.

## Green 계약 (테스트가 가정하는 정확한 형태)

### 백엔드 1: `src/engine/market_operation_monitor.py` (신규 *추가만*, 기존 추적/`is_ticker_stale_excluded` 불변)
- 상수: `_CB_REASON_KEYWORDS = ("서킷", "매매거래중단", "circuit")` / `_CB_HALT_RATIO = 0.8` / `_CB_MIN_HALTED = 5`.
- `get_circuit_breaker_state() -> dict`:
  - `halted = len(_halt_active_tickers)` / `observed = len(_market_op_last_event)` / `halt_ratio = halted / max(1, observed)`.
  - **suspected = (R) OR (W)**:
    - (R) 키워드: 어느 halted 종목의 `_market_op_last_event[t].tr_susp_reas_cntt` 에 `_CB_REASON_KEYWORDS` 부분문자열 매칭.
    - (W) 비율: `halted >= 5 AND halt_ratio >= 0.8`.
  - `representative_mkop_cls_code` = `_market_op_last_event["005930"].mkop_cls_code` if 존재 else `""`.
  - `halt_reasons_sample` = halted 종목 distinct 비어있지 않은 `tr_susp_reas_cntt` 최대 5.
  - `reasons` = 근거 list[str] (키워드 매칭 시 키워드 포함 문자열 "...서킷..."; 비율 시 "%"/"12/14" 포함 문자열).
- `get_market_op_state_summary()` 확장: 기존 5키 보존 + `circuit_breaker`(위 dict) + `iscd_stat_active_count`(= `_market_op_last_event` 중 `_is_code_active(event.iscd_stat_cls_code)` 종목 수).
- 계측 로그: `record_market_op_event` 에서 CB 휴리스틱 첫 발화 시 `[market_op_cb_suspected] ...` INFO 1회/일 cap (DailyEmitCap, logger=`src.engine.market_operation_monitor`). 기존 VI/halt set 갱신 로직은 불변 — 로그만 추가.
- **`reset_market_op_state()` 가 CB 계측 cap 도 함께 reset** (테스트 autouse fixture 가 의존 — _reset_daily_state 동행 clear).
- 불변 (SAFETY): `is_ticker_stale_excluded`(arg `ticker`) / `record_market_op_event`(arg `event`) 시그너처 + `_vi_active_tickers.add/discard` + `_halt_active_tickers.add/discard` 라인 = 변경 0.

### 백엔드 2: `src/routes/realtime.py` 신규 `get_market_operation` (`GET /api/realtime/market-operation`)
- 함수명 **`get_market_operation`** (라우트 테스트 직접 import + await). subscriptions ApiResponse 빌드 패턴 답습.
- ApiResponse data = `get_market_op_state_summary()` 전체 + `circuit_breaker`(=`get_circuit_breaker_state()`) + `details`(cap 200).
- `details` = VI∪halt 종목 sorted, 각 `get_last_event(ticker)` → `{ticker, vi_code, ovtm_vi_code, halt_yn, halt_reason, iscd_stat, mkop_cls_code, exch_code, received_at}`.
  - 필드 매핑: vi_code=`vi_cls_code` / ovtm_vi_code=`ovtm_vi_cls_code` / halt_yn=`trht_yn` / halt_reason=`tr_susp_reas_cntt` / iscd_stat=`iscd_stat_cls_code` / mkop_cls_code=`mkop_cls_code` / exch_code=`exch_cls_code` / received_at=ISO or None.
- 0건 정상 → 빈 details + CB suspected=False.

### 프론트: `RealtimeHealth.tsx` 5번째 카드 "장운영상태"
- 신규 `frontend/src/types/market-operation.ts` (interface) + `frontend/src/api/market-operation.ts` (`fetchMarketOperationStatus` → `apiClient.get<ApiResponse<T>>('/realtime/market-operation')` + `data.data ?? fallback`, realtime-health.ts/strategy-funnel.ts 패턴 답습).
- 별도 useQuery (`retry:1` + `refetchInterval` + `staleTime`, 사이클 65 H3) — 기존 4 카드 useQuery 와 별개 쿼리.
- testid: 카드 `realtime-health-card-market-operation` / CB 배지 `realtime-health-cb-badge`.
- 카드 내용: VI 활성 N / 거래정지 N / 종목상태 이상 N 배지(0=gray, >0=amber/red) + 서킷브레이커 배지(suspected=true → orange "추정" / false → gray "정상") + 종목별 detail(ticker + 거래정지 사유 + raw MKOP_CLS_CODE) + KST 시각(`Asia/Seoul`). 한글 라벨.

## 작성한 테스트 (Red)
- 백엔드 monitor `tests/unit/engine/test_cycle186_market_op_cb_heuristic.py` (10):
  - cb_keyword (suspected+키워드근거) / cb_ratio (14·12·86%) / cb_no_false_positive (SAFETY, 2/10=False) /
    cb_representative (005930 mkop) / cb_representative_empty (005930 부재 "") / cb_halt_reasons_sample /
    summary_ext (circuit_breaker + iscd_stat_active_count + 기존 5키) / instrument_cap (로그 1행) /
    safety_stale_behavior_unchanged (PASS-guard) / safety_ast_signatures_unchanged (PASS-guard)
- 백엔드 route `tests/unit/routes/test_cycle186_market_op_route.py` (3):
  - route_schema / route_details (VI+halt 필드) / route_empty_state
- 프론트 `frontend/src/pages/__tests__/RealtimeHealth.cycle186.test.tsx` (5):
  - FE-CARD-RENDER / FE-CB-BADGE(true=추정 orange) / FE-CB-BADGE(false=정상 gray) / FE-DETAIL / FE-EXISTING-4
- MSW `frontend/src/test/handlers.ts` + e2e `e2e/fixtures/api-mocks.ts` 에 `/realtime/market-operation` 기본 핸들러 추가 (신규 엔드포인트).

## Red 실행 결과 (현 코드)
- 백엔드: monitor 8 FAIL (get_circuit_breaker_state/summary 확장/계측로그 부재) + 2 PASS(SAFETY 가드). route 3 FAIL (get_market_operation ImportError).
- 프론트: RealtimeHealth.cycle186 5 FAIL (장운영상태 카드/CB 배지 testid 부재).
  (상세 카운트는 본 사이클 응답 보고 참조)

## 매매 안전성 (8영역 diff 0 — Green 의무)
`git diff -- src/engine/risk.py src/engine/order_engine.py src/realtime/ src/auth/ src/api/order.py src/engine/session.py src/engine/scanner.py src/engine/strategy_registry.py` = 0.
market_operation_monitor 는 신규 getter/휴리스틱/계측 *추가만* → `is_ticker_stale_excluded` 불변. 사이클 149 stale 회피 + 162 call-auction 영속.

## Handoff (범위 밖)
- CB 정식 코드 감지 승격 (실CB 1회 관측 → session.py 코드표 + 정식 감지).
- 사이드카 (H0UNMKO0 미포함 → 프로그램매매 TR 별도).
- CB → 매수 가드 (현재 표시만, 필요 시 regime get_buy_block_state 패턴 + domain-expert).
