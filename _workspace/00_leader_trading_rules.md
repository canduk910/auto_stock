# 매매 규칙 명세 — 팀장 작성

## 1. 시스템 개요
KIS OpenAPI 기반 국내주식 자동매매시스템. 다중 전략 아키텍처로 전략별 독립 자금 운용.
모의투자(VTS) 환경에서 1차 검증 후 실전 전환. **2026-05-08판 KIS API 명세에서 NXT(넥스트레이드 ATS) 주문/시세 정식 지원** → 매매 시간대를 KRX 단독에서 KRX+NXT 통합(08:00~20:00)으로 확장.

## 2. 전략 구성

### 전략 A: 상한가 모멘텀 (strategy_id: momentum)
전일종가 대비 급등 종목을 추적하여 +29% 돌파 시 매수, 다음 영업일 NXT 프리 시가에서 청산. **KRX 보드 한정**(상한가 +29%는 KRX 기준).

### 전략 B: 변동성 돌파 (strategy_id: volatility_breakout)
노이즈 비율 기반 동적 K값으로 보드별 시가 + 전일Range × K로 매수 목표가 설정, 돌파 시 매수. **NXT 프리 / KRX 메인 / NXT 애프터 모두 활성**(보드별 K값 분리 운용).

### 전략 C: 롱테일 변동성 돌파 (strategy_id: long_tail_volatility)
변동성 돌파 방식으로 조기 진입 + 당일 +29% 도달 시 익일 청산 모드 전환(롱테일 추구). **매수는 PRE_NXT / MAIN 한정** (2026-05-15 결함 D). 상한가 미도달 종목은 15:20 일괄 청산, 상한가 도달 종목은 익일 NXT 프리 청산 + POST_NXT 시간대 손절 모니터링.

### 전략 D: 20일 신고가 스윙 (strategy_id: donchian_swing)
일봉 종가가 20일 신고가 돌파 + 60일 EMA 우상향 + 거래대금 1.5배 → 다음 영업일 09:05 시장가 매수. ATR(14)×2 트레일링 청산 / 하드 -7% / 시간 청산 없음 / 평균 5~15 영업일 보유. **KRX 메인만 활성**(추세추종은 일중 변동성 필요).

### 전략 E: 눌림목 돌파 (strategy_id: bull_flag_breakout)
강한 상승(폴) 후 짧은 횡보·완만한 조정(플래그) 종목을 추적, 플래그 상단 재돌파 시 매수. **KRX 메인 09:05~13:00 한정**(`tradable_boards=("main",)`). "측정된 이동(measured move)" 익절 — 폴 폭만큼 가면 절반 청산, 잔여 ATR×2 트레일링. 손절 -5% 또는 플래그 하단 이탈. 모멘텀(+29% 폭발) 후속 진입로.

### 전략 F: 변동성 수축 돌파 (strategy_id: vcp_breakout)
미네르비니식 VCP(Volatility Contraction Pattern) — 추세 + Stage 2 확인 + 2~4회 pullback 점진 수축 + 거래량 수축 후 베이스 상단 돌파 시 매수. **KRX 메인 09:05~14:30 한정**. ATR(14)×2 트레일링 + 50일 EMA 이탈 청산. 손절 -7% 또는 베이스 하단 이탈. 시간 청산 없음(멀티데이). donchian_swing 정공법 보강(신고가 직진 추격 → VCP 는 베이스 + 변동성 수축 확인).

### 전략별 자금 비중
- 프론트엔드 Settings 페이지에서 비중 조절 (예: momentum 25 / VB 35 / LTV 25 / donchian 15 / bull_flag 0 / vcp 0)
- 총 자산을 비중에 따라 분배, 각 전략은 할당된 자금 내에서만 매매
- 전략 간 동일 종목 중복 매수 방지 (보유 OR 주문중 OR 당일매도 통합 가드)
- **신규 2종(bull_flag_breakout / vcp_breakout) 디폴트 weight=0 + enabled=false**: 기존 4개 합계 1.0 유지, 운영자가 Settings 에서 수동 활성화 + 비중 재조정(`donchian_swing` 011 마이그레이션과 동일 패턴)
- **매수 수량 1주 fallback (전략 잔여 자금 기준, 2026-05-11 P1 격상)**: `position_ratio × total_investment // current_price = 0`이라도 **전략 잔여 자금**이 1주 살 수 있으면 1주 매수. **6개 전략 동일 규칙**.
  - **잔여 자금 = `state.total_investment` − (해당 전략 보유 포지션 `buy_price×qty` 합계 + 해당 전략 `pending_buys` 매수 예정 금액 합계)**
  - 보유/주문중은 `strategy_id`로 격리 — 다른 전략 포지션은 자기 전략 사용액에 포함하지 않음
  - 결함 차단: 기존 로직은 `state.total_investment >= current_price`(고정 총액)와 비교 → 동일 전략이 이미 다른 종목에 자금 90% 점유해도 1주 추가 매수 → **전략 한도 초과**. 2026-05-11 운영 사고로 노출
  - 구현: `StrategyBase._fallback_one_share(current_price)` 공통 헬퍼로 통합 — 6개 전략(`momentum`/`volatility_breakout`/`long_tail_volatility`/`donchian_swing`/`bull_flag_breakout`/`vcp_breakout`) 모두 동일 메서드 호출
  - race 가드: `pending_buys`는 `place_order` 응답 직후 동기 영역에서 즉시 등록 — 기존 매핑 등록 규약과 동일하게 합산 일관성 보장

### WebSocket 구독 가시성 (2026-05-12 G, 운영자 슬롯 추적)
- KIS REST/WS 어디에도 슬롯 사용현황 조회 API 미존재 → 우리 측 도구 강화로 갈음
- **G1 SUBSCRIBE ACK 추적**: `KisWebSocket._subscriptions_acked` set 신규. 정상 응답(`rt_cd=="0"` + `msg1` 에 "SUBSCRIBE SUCCESS" 포함) 수신 시 add, `subscribe/unsubscribe/_is_rejection_response/connect 재연결` 시점에 discard/clear. `get_acked_tickers()` 헬퍼는 TICK_TR_ID 필터링한 set 반환
- **G2 진단 endpoint**: `GET /api/realtime/subscriptions` — `{ total, acked, fresh_60s, stale_60s, limit, tickers:{subscribed/acked/fresh/stale (모두 sorted)}, reconnect_count, ws_connected }`. KST 기준, ws_connected=False 도 200 응답. 인증 가드 없음
- **G3 status 확장**: `scanner.get_scan_status()` 에 `tick_coverage_total/acked/fresh/stale` 4개 키 추가. 기존 `subscribed_count` 보존. ScanMonitor 는 stale 카운트에 따라 색상 배지(0=기본 / 1~5=yellow / 6+=red). 한도 근접도 진행바(total/41, 80%+ amber) 노출

### WebSocket 시세 구독 우선순위 (2026-05-12 E1, donchian 조기 손절 사건 대응)
- **`MAX_SUBSCRIPTIONS = 41` (KIS 공식 한도)** — 기존 200은 과대 설정으로 한도 초과 자체를 차단하지 못해 41 초과분이 KIS 측에서 silently 거절될 수 있었음. 어제·오늘 donchian_swing 보유 종목 시세 무수신으로 ATR 트레일링이 작동 안 한 정황.
- **우선순위(HIGH → LOW)**:
  1. **보유 포지션** — `registry.all()` 순회 `state.positions.keys()` 합집합. **한도 무시 절대 보장** (`bypass_limit=True`). 손절·트레일링 감시는 KIS 한도보다 우선
  2. **익일청산 보류 대상** — `scheduler._pending_next_day_clear` set 의 ticker. **한도 무시 절대 보장**. 09:00 KRX 시장가 청산을 놓치면 위험
  3. **모멘텀 스캔** — `scan_stocks()` 결과
  4. **VB/LTV 후보** — `_collect_breakout_tickers()`
  - **donchian_swing 은 WS 구독 대상에서 제외** (G안 2026-05-12) — Pull 폴링(`_swing_buy_poll_loop`)으로 매수 평가하므로 매수 시점 시세는 매분 1회 `fetch_stock_detail` REST 로 수집. 매수 *성공* 시(`pending_buys` 또는 `positions` 등록 확인) `bypass_limit=True` 로 즉시 TICK 구독 추가. swing 후보 사전 구독은 슬롯 낭비라 제거됨
- **drop 정책**: 잔여 슬롯(`MAX_SUBSCRIPTIONS - len(_subscriptions)`) 부족 시 후순위(**breakout → momentum**, G안 2026-05-12)만 잘림. drop된 개수는 다음 형식의 INFO 로그(+ WARNING system_logs 영구 저장) 1행으로 노출: `[priority_drop] breakout=X momentum=Y swing=Z total_subscribed=N max=41 high_count=H low_remaining=R` — `low_remaining` 은 후순위 처리 후 남은 슬롯(0 으로 clamp). swing=0 고정(WS 구독 대상에서 제외). 변동성 돌파(VB/LTV) 후보를 우선 보장해 일중 매매 기회 확보.
- **중복 제거**: 같은 종목이 여러 그룹에 있으면 HIGH 순위로 1회만 subscribe. 후순위 그룹에서는 이미 구독된 종목 skip.
- **HIGH 단독 41 초과 시(이상 케이스)**: ERROR 로그 + `system_logs` 기록. 보유는 무조건 add (`bypass_limit=True`), 후순위는 0개. 운영자가 전략 비중을 줄여야 함.
- **구현 통합 지점**:
  - `src/realtime/websocket.py`: `MAX_SUBSCRIPTIONS = 41`. `subscribe(tr_id, tr_key, *, bypass_limit: bool = False)` 키워드 추가
  - `src/engine/scanner.py::subscribe_filtered_stocks(..., *, priority_groups: dict[str, list[str]] | None = None)` 키워드 추가 — 키: `positions / next_day_clear / swing / momentum / breakout`. `priority_groups=None` 이면 기존 평탄 처리(외부 호환)
  - `src/engine/scheduler.py`: `_build_priority_groups()` 헬퍼 신설, 4개 호출부(라인 254-258 / 285-291 / 307-310 / 1316-1338)가 dict 구성해 전달. 기존 `_collect_presubscribe_tickers` / `_build_subscription_source_counts` 보존
- **불변식**: HIGH 순위(보유 + 익일청산) 어떤 경우에도 drop 금지. 후순위 drop 발생 시 ERROR가 아닌 INFO (정상 운영 흐름)

### WebSocket 구독 거절 감지 (2026-05-12 E2 — 운영 가시성 + `_subscriptions` 정합성)
어제·오늘 운영 의심: KIS 한도 초과 등으로 일부 종목 구독이 거절되었으나 코드는 `msg1`의 `"ERROR"` 단일 키워드만 매칭 → 거절 사실 자체를 모른 채 `_subscriptions` set에 잔류했을 가능성. 거절 감지를 다층으로 강화해 정합성 회복 + 영구 로그로 다음 사례 추적성 확보.

- **위치**: `src/realtime/websocket.py::_handle_raw()` JSON 응답 분기 (현재 line 196-203)
- **거절 판정 조건 (하나라도 매칭)**:
  1. **rt_cd != "0"** (1순위 — KIS REST와 동일 규약). `body.get("rt_cd")` 가 None 이면 skip (Heartbeat 등 응답에는 rt_cd 없음)
  2. **msg1 키워드 (대소문자 무시, 기존 `"ERROR"` 확장)**: `ERROR / FAIL / REJECT / NOT ALLOWED / LIMIT / EXCEED / DUPLICATE / 한도 / 초과 / 이미 / 중복 / 허용되지 / 권한`
  3. msg_cd 화이트리스트는 이번 단계에서는 적용 안 함 — 거절 시 msg_cd 영구 로깅 누적되면 다음 단계에서 추가
- **거절 처리**:
  - `self._subscriptions.discard((tr_id, tr_key))` — 멱등 (이미 빠진 상태에서도 안전)
  - ERROR 로그: `"WebSocket 구독 거절: tr_id=%s, tr_key=%s, rt_cd=%s, msg_cd=%s, msg=%s"`
  - `write_log("ERROR", f"[ws_subscribe_reject] tr_id={tr_id} tr_key={tr_key} rt_cd={rt_cd} msg_cd={msg_cd} msg1={msg1}")` — Phase A1 `[kis_rejection]` 패턴 차용. fire-and-forget (비차단)
- **호출자 시그널 전달 없음** — `subscribe()` 동기 시그니처 유지. 거절은 비동기 응답으로 처리되며 다음 5분 `_scan_loop` 사이클에서 E1 우선순위 큐로 자연 재시도. **재시도 큐 구현 금지(E2 범위 밖)**
- **정상 응답 흐름(`SUBSCRIBE SUCCESS` AES iv/key 저장) 불변** — 거절 분기에서 조기 return 만 한다
- **불변식**:
  - rt_cd 누락 응답 (Heartbeat PINGPONG / 비-JSON 캐럿 구분 실시간 데이터) → 거절 처리 안 함, `_subscriptions` 영향 없음
  - 같은 `(tr_id, tr_key)` 에 대해 거절 응답 2회 → discard 멱등 안전
  - E1 우선순위 큐 / `MAX_SUBSCRIPTIONS=41` / `bypass_limit` 분기 — 영향 없음

### 외부 백테스트 서버 통합 (2026-05-15 ~ 2026-05-16 Phase 0~5)
20:00 AI 자문 단계에 OpenAI 제안값을 외부 백테스트 서버로 검증하는 사이클. Phase 0(시간 이동) → 1(클라이언트) → 2(엔진+YAML+마이그 019) → 3(자문 합류+마이그 020) → 4(UI 카드) → 5(회귀 가드+모니터링 가이드) 완료. 운영 모니터링 진단 절차는 [`docs/backtest-monitoring.md`](../docs/backtest-monitoring.md).

#### Phase 1 (2026-05-15) — MCP 클라이언트 + 헬스체크

- **외부 서버**: `http://43.202.187.5:3846/mcp` (AWS EC2 ap-northeast-2, stock-manager 운영). 프로토콜 JSON-RPC 2.0 over Streamable HTTP/SSE (MCP 2025-03-26). 인증 없음 — IP 화이트리스트만 (auto_stock 운영 EC2 IP 이미 허용)
- **운영 토글**: `KIS_MCP_ENABLED=false` (기본) 면 모든 외부 호출 차단. 운영 EC2 `.env` 에서 `true` 로 켤 때만 백테스트 발화. **자동매매 핵심 흐름(scheduler/order_engine/risk) 격리** — 본 모듈 다운/네트워크 단절 시 graceful degrade, 운영 영향 0
- **graceful degrade 규약**:
  - `KIS_MCP_ENABLED=false` 면 `MCPClient.call_tool()` 은 `ConfigError` raise — 자문 단계는 OpenAI 결과만 INSERT, `backtest_summary=null` 로 자연 처리
  - `health_check()` 은 어떤 경우에도 예외 raise 안 함 — `False` 반환 (서버 다운/타임아웃/HTTP 5xx/네트워크 단절 통합 처리)
  - `GET /api/backtest/mcp/health` 는 HTTP 200 으로 `{enabled, reachable, tools_count, error}` 반환. 5xx 절대 안 냄
- **세션 관리**: stock-manager 패턴 async 이식. 모듈 레벨 싱글톤 `_client_instance` + 세션 ID 재사용. 421 (세션 만료) → 1회 자동 재초기화 후 재시도. 동시 호출 race 대비 `asyncio.Lock` 으로 initialize 중복 방지
- **타임아웃**: connect=5s / read=`BACKTEST_TIMEOUT_SECS` (기본 300s) / write=10s / pool=10s. 외부 서버 backtest 단일 호출 90일 × 6전략 시 60~90s 소요 가능 — 300s 헤드룸
- **에러 분류**: `ConfigError` (설정) vs `ExternalAPIError` (네트워크/타임아웃/HTTP/JSON-RPC error). 호출자는 `try/except ExternalAPIError` 로 자문 INSERT 보존 + summary null
- **회귀 가드**:
  - `tests/unit/services/test_mcp_client.py` 16 케이스 (A1~A12 + 싱글톤) — respx 모킹
  - `tests/contract/test_routes_backtest.py` 3 케이스 — `/api/backtest/mcp/health` enabled/reachable/error 분기
  - `tests/contract/test_backtest_mcp_health.py` 2 케이스 — 실제 외부 서버 호출 (CI skip, 로컬 `KIS_MCP_ENABLED=true pytest` 로 수동 검증)
- **검증 결과**: 2026-05-15 로컬 헬스체크 통과 — 실제 서버에 `tools/list` 응답 정상, 백테스트 도구 노출 확인. Phase 2 진입 게이트 통과
- **사후 보호 의무 (Phase 2+ 에 인계)**:
  - 백테스트 결과를 자동매매 파라미터에 **자동 반영 절대 금지** — 운영자가 Settings 에서 명시 적용(`apply_weight` J4 패턴 차용) 만 허용
  - 백테스트 task 가 settlement 20:10 와 race 가능 — fire-and-forget 별도 task + 자체 폴링. settlement 의 `_reset_daily_state()` 에서 task cancel 의무

#### Phase 2 (2026-05-15) — BacktestEngine + 6 전략 YAML DSL + 마이그 019
- **`BacktestEngine`** (`src/engine/backtest_engine.py`): submit(`run_for_strategy`) → poll(`poll(job_id)` / `wait_for_result`) 분리. 응답 unwrap 헬퍼로 `{success, data}` 또는 직접 dict 모두 지원. 모듈 레벨 싱글톤 `get_backtest_engine()`
- **6 전략 분류** (`src/engine/backtest_yaml.py::build_yaml`):
  - **(a) 외부 YAML DSL 표현 가능 3종** — `momentum`(ROC1 > 임계) / `volatility_breakout`(ATR(k) + close cross_above prev_high) / `donchian_swing`(maximum(high,20) + EMA(60) + ATR 트레일링)
  - **(b) 표현 불가 3종 — `BacktestNotSupportedError` raise** — `long_tail_volatility`(상한가 모드 전환 미표현) / `bull_flag_breakout`(폴/플래그 자동 검출) / `vcp_breakout`(베이스 + 변동성 수축 + swing high/low). Phase 4-bis 로컬 어댑터 위임
- **DB 영속화** — `supabase/migrations/019_backtest_runs.sql`: `(target_date, strategy_id, params_kind=current|recommended)` UNIQUE. `params_snapshot JSONB`, `metrics JSONB`, `status` ∈ {queued, running, completed, failed, skipped}, `mcp_job_id`, `error_message`. `src/db/backtest_runs.py` CRUD (`insert_run / update_status / list_by_date`)
- **디폴트 universe** — 코스피200 대표 5 종목 (`005930` 삼성전자 / `000660` SK하이닉스 / `035420` NAVER / `005380` 현대차 / `051910` LG화학) — 외부 서버 캐시 적중률 + 다양성 확보
- **백테스트 기간 90일** — 통계 충분 + 외부 서버 부하 균형
- **회귀 가드**: `tests/unit/engine/test_backtest_engine.py` + `test_backtest_yaml.py` + `tests/unit/db/test_backtest_runs.py`

#### Phase 3 (2026-05-15) — 20:00 자문 ↔ 백테스트 통합 + 마이그 020
- **흐름** (`src/engine/recommendation_engine.py::generate_recommendations`):
  1. 자문 INSERT 6 row (기존 OpenAI 결과)
  2. `_enqueue_backtest_jobs(target_date, inserted)` 동기 await — 12 backtest_runs INSERT (6 전략 × 2 kind)
  3. (a) 전략은 `engine.run_for_strategy` 호출 → `mcp_job_id` 받아 `running` 전이
  4. (b) 전략은 즉시 `skipped` + 사유 "YAML DSL 미지원 (Phase 4-bis 로컬 어댑터 대기)"
  5. `KIS_MCP_ENABLED=false` 면 (a) 도 즉시 `skipped` + 사유 "MCP 비활성"
  6. submit_success ≥ 1 시 `_spawn_backtest_poll_task(target_date)` fire-and-forget 발화
- **폴 루프** (`_backtest_poll_loop`):
  - 60s 주기로 `running` row 의 `engine.poll(job_id)` 호출 → completed → metrics 저장. `ExternalAPIError`/`ConfigError`/unexpected → `failed` + error_message
  - 종료 조건: 모든 row 가 terminal 상태({completed, failed, skipped}) + summary 동봉 완료 → exit
  - **24h timeout**: 미완료 running/queued row 를 `failed` + "Timeout (>24h)" 으로 마킹 후 exit
  - 중복 task 가드: `_backtest_poll_loop_running` set 멤버십 체크
- **summary 동봉** (`_emit_pending_summaries`): 완료된 (a) 전략 6 row 가 모이면 `parameter_recommendations.backtest_summary` JSONB 에 `{compared_strategies, current, recommended, diff}` 형태로 UPDATE. (b) 전략은 키만 존재 + value=null 로 UI 가 폴백 분기로 인식
- **DB 영속화** — `supabase/migrations/020_parameter_recommendations_backtest.sql`: `parameter_recommendations.backtest_summary JSONB` nullable
- **race 안전성**:
  - 자문 INSERT 와 backtest enqueue 는 `try/except` 분리 — enqueue 예외 시 자문 INSERT 보존
  - settlement 20:10 시점에 폴 task 미완료여도 자문 row 영속 (자문은 20:00 동기 완료)
  - settlement `_reset_daily_state()` 의 task cancel 책임 (현재 구현 확인 필요 — Phase 5b 모니터링)
- **회귀 가드**:
  - `tests/integration/test_recommendation_backtest_flow.py` 2 케이스 — full flow / settlement race
  - `tests/unit/engine/test_recommendation_backtest_hook.py` + `test_backtest_poll_loop.py`
  - `tests/unit/db/test_parameter_recommendations_backtest.py`

#### Phase 4 (2026-05-15) — Recommendations UI 백테스트 카드
- **`BacktestComparisonCard`** (`frontend/src/components/recommendations/BacktestComparisonCard.tsx`): 자산 배정 카드 *위* 에 `backtest_summary != null` 일 때만 조건부 노출
- **(a) 전략 분기**: 8 메트릭(`total_return_pct / annual_return / sharpe_ratio / sortino_ratio / max_drawdown / win_rate / profit_factor / total_trades`) 좌(현재) / 우(추천) 비교 + 차이값 컬러 칩(이익색 빨강 / 손실색 파랑 컨벤션)
- **(b) 전략 분기**: `compared_strategies[id] === null` 면 "외부 백테스트 서버 미지원 (Phase 4-bis 대기)" 안내 라벨
- **로딩 분기**: `status=running` 시 스피너 표시
- **`max_drawdown` 부호 컨벤션 future-proof**: `metricDefinitions[i].signInverted: boolean` 옵션 매개변수화. 실측 음수면 false 그대로 / 양수면 true 로 토글 — Phase 5b 검증 후 확정
- **회귀 가드**: `frontend/src/components/__tests__/BacktestComparisonCard.test.tsx` RTL 케이스

#### Phase 5 (2026-05-16) — 회귀 가드 + 운영 모니터링 가이드
- **graceful 통합 가드** (`tests/integration/test_backtest_disabled_and_graceful.py` 3 케이스):
  - `KIS_MCP_ENABLED=false` 재시작 → 자문 6 INSERT 보존 + backtest_runs 12 row 모두 skipped + 폴 task 발화 0회
  - 외부 서버 다운(`ExternalAPIError`) → (a) 6 row failed + 자문 INSERT 보존
  - 24h timeout → 미완료 running row failed + 자문 INSERT 보존
- **운영 모니터링 가이드** — `docs/backtest-monitoring.md` 신규:
  - Section 1: 운영 활성화 절차 (Case A `KIS_MCP_ENABLED=true` 토글 / Case B Phase 4-bis 진입 placeholder)
  - Section 2: Phase 5b 사용자 검증 절차 (20:00 직후 system_logs/backtest_runs/parameter_recommendations SQL 진단)
  - Section 3: 트러블슈팅 체크리스트 (헬스체크 / 좀비 task / UI 카드 미표시 분기)
  - Section 4: `max_drawdown` 부호 컨벤션 확정 절차
  - Section 5: 응답 키 검증 체크리스트 (`max_drawdown` 부호 / `profit_loss_ratio` 매핑 / `total_orders` 단위 / `annual_return` vs `cagr`)
  - Section 6: 자동매매 격리 안전 규칙 + 회귀 가드 매트릭스
  - Section 7: 후속 작업 (MDD 확정 / 응답 키 매핑 검증 / Phase 4-bis / historical 누적 페이지)
- **Phase 5b 사용자 책임** — 2026-05-18(월) 20:00 첫 실 발화 후 운영자가 직접:
  1. `[backtest_enqueue]` / `[backtest_poll]` 로그 확인
  2. backtest_runs 12 row INSERT + summary 동봉 전이 확인
  3. UI 카드 (a)/(b) 분기 검증
  4. `max_drawdown` 부호 SQL 확인 후 `BacktestComparisonCard` `signInverted` 결정
  5. 응답 키 매핑 결함 발견 시 별도 사이클 발의

#### Phase 6 (2026-05-16) — 보강 (사후 검증으로 발견된 결함 3건 fix)
- **결함 A (Critical) — MCP content 2겹 래핑 unwrap**: `MCPClient.call_tool()` 마지막에 `_extract_mcp_content()` 호출 추가. 외부 응답이 `{"content":[{"type":"text","text":"<JSON>"}]}` 인 stock-manager 컨벤션이면 안쪽 JSON 의 `data` 평탄화 반환. `success:false` 시 `ExternalAPIError(error_msg)` raise. 일반 응답(`{"result":{...}}`) 은 그대로 통과 — Phase 1 16 케이스 회귀 보존. 회귀 가드 `tests/unit/services/test_mcp_client_unwrap.py` 9 케이스
- **결함 D' (Critical, 사후 발견) — metrics 중첩 평탄화**: 실측 외부 응답이 `data.result.metrics.{basic,risk,trading}` 3단 중첩. `_extract_metrics()` 가 `data.metrics` 와 `data.result.metrics` 두 경로 모두 검사 후 `_normalize_metrics()` 로 8 키 평탄화. 키 매핑: `basic.total_return → total_return_pct` / `basic.annual_return → cagr` / `basic.max_drawdown → max_drawdown (양수 = 절대값)` / `risk.sharpe_ratio/sortino_ratio` 그대로 / `trading.win_rate` 그대로 / `trading.profit_loss_ratio → profit_factor` (외부 명명 차이) / `trading.total_orders → total_trades`. 평탄 키(향후 외부 서버가 평탄화 했을 때 대비) 우선. 회귀 가드 `tests/unit/engine/test_backtest_engine_nested_metrics.py` 4 케이스 — verify_mcp_response_schema.py 실측 응답 그대로 fixture
- **결함 B (확인) — donchian_swing YAML 외부 호환**: 외부 preset 10 개에 donchian 미포함 → YAML 커스텀 경로(`run_backtest_tool`) 가 정상 동작 확인. `validate_yaml_tool` 응답 `{"valid":true,"errors":[],"warnings":[]}` — **(a) 분류 유지**. 회귀 가드 `tests/unit/engine/test_backtest_yaml_donchian_compat.py` 6 케이스 (정적 YAML 구조 검증, 외부 호출 안 함). `_FALLBACK_STRATEGIES` 변경 없음
- **결함 C (Low) — initialize session-id 누락 로그 다운그레이드**: stateless 외부 서버는 `mcp-session-id` 헤더 미반환이 정상. 매 호출 WARNING 노이즈 → DEBUG 다운그레이드 + "stateless 모드" 명시. 회귀 가드 `tests/unit/services/test_mcp_client_session_log.py` 2 케이스 (caplog 로 WARNING 없음 검증)
- **응답 키 확정**:
  - **`max_drawdown` 부호**: 양수 (실측 `16.1`) — 절대값 컨벤션. `BacktestComparisonCard` `signInverted: true` 토글 권장
  - **`profit_loss_ratio` → `profit_factor`**: 외부 서버 명명 차이. `_NESTED_METRIC_MAP` 매핑 처리
  - **`total_orders` → `total_trades`**: 거래 횟수 단위 동일
  - **`annual_return` → `cagr`**: 둘 다 percent 단위
- **실측 검증 도구** — `scripts/verify_mcp_response_schema.py` Phase 6 보강:
  - Section [6] `_extract_metrics + BacktestMetrics 평탄화 결과` — 실시간 외부 응답에 Phase 6 평탄화 적용해 8/8 키 채집 확인
  - Section [7] `donchian_swing YAML → validate_yaml_tool` — 외부 서버 호환성 사후 확인
  - 다음 실서버 변경 시 재실행으로 즉시 검증 가능
- **운영 영향 0 검증**: `KIS_MCP_ENABLED=false` 그대로 유지 → Phase 6 패치가 EC2 배포돼도 백테스트 호출 0건. Phase 5b 토글 시점에 자동으로 결함 fix 적용된 상태로 첫 발화. 백엔드 888 passed (Phase 5 862 → +26) / 프론트엔드 85 passed 회귀 0
- **Phase 5b 진입 게이트 통과** — 2026-05-18(월) 20:00 토글 안전

### 거래소 라우팅 (전략별 `exchange` 파라미터)
| 값 | 의미 | 비고 |
|---|---|---|
| `KRX` | 한국거래소 단일 | 기본값. 모의(VTS) 지원 |
| `NXT` | 넥스트레이드 ATS 단일 | 실전 한정 |
| `SOR` | Smart Order Routing | KIS가 KRX/NXT 자동 분배. 실전 한정 |

`place_order`/`cancel_order` body에 `EXCG_ID_DVSN_CD`로 전송. 모의는 SOR/NXT 시도 시 KIS가 거절하므로 KRX만 사용.

### 보드(매매 시간대) 화이트리스트
각 전략 `tradable_boards` 파라미터로 매매 가능 보드를 결정:

| Board | 시간 | 전략 매핑 (기본값) |
|---|---|---|
| `pre_nxt` | NXT 프리 08:00~09:00 | VB / LTV |
| `krx_open` | KRX 동시호가 08:30~09:00 | momentum |
| `main` | KRX+NXT 메인 09:00~15:20 | momentum / VB / LTV / donchian_swing / bull_flag_breakout / vcp_breakout |
| `krx_after` | KRX 시간외 단일가 15:30~18:00 | (현재 미사용) |
| `post_nxt` | NXT 애프터 15:30~20:00 | VB / LTV |

**RiskManager 보드 가드**: `on_tick` 매수 신호 평가 전 `session_tracker.is_tradable(strategy_id, params)`로 활성 보드 ∩ tradable_boards 체크 — 비활성 보드에서는 신호 평가 자체 skip.

---

## 3. 전략 A: 상한가 모멘텀 상세

### 종목 선정
- 09:30 이후 등락률 순위 API로 5분 주기 필터링
- 1차 필터: 전일종가 대비 등락률 +15% 이상 상승 종목
- 2차 필터: 시가총액 1,000억 원 이상 AND 당일 거래대금 200억 원 이상
- ETF/ETN 제외 (KODEX, TIGER, 인버스, 레버리지 등 + RISE/KoAct/PLUS/TIMEFOLIO/WOORI/FOCUS 키워드)
- 최대 40개 종목으로 제한

### 매수 규칙
- **진입 조건**: 전일종가 대비 현재가가 +29.0% 이상 도달 (29% 미만 → 29% 이상 돌파 순간만)
- **제외**: 이미 상한가(+30%)에 도달한 종목은 매수 대상에서 제외
- **주문 방식**: 시장가 매수
- **투자 비중**: 할당 자금의 25% (1종목당) — 자금 부족 시 1주 fallback 동작
- **중복 방지**: 동일 종목이 이미 보유 중이거나 미체결 매수 주문이 있으면 매수 금지
- **매매 보드**: KRX_OPEN + MAIN만 (NXT 보드 비활성 — 상한가 기준이 KRX이므로 NXT 단독 +29% 의미 약함)
- **거래소 라우팅**: 기본 KRX (SOR로 변경 시 KIS가 NXT/KRX 자동 분배)

### 당일 손절
- **조건**: 매수 체결가 대비 현재가가 -7.5% 이하 도달
- **주문**: 즉시 시장가 전량 매도
- **주의**: 기준은 반드시 "매수 체결가"이지 시가가 아님

### 익일 청산 (다음 영업일 NXT 프리 08:00 → NXT 거래가능 여부로 분기)
다음 영업일 보유 종목에 대해 **NXT 거래가능 여부**로 청산 시점을 분기한다 (2026-05-11 P1(B) → 2026-05-11 P1(C) 격상).

#### 분기 기준 — KIS CTPF1002R 사전 조회 (Primary) + 시가 수신 (Fallback)
KIS MCP 4질의 결과(2026-05-11) **CTPF1002R(주식기본조회) 응답의 두 필드로 종목별 NXT 등록 여부를 사전 조회 가능**함이 확정됨:
- `cptt_trad_tr_psbl_yn` — NXT 거래종목여부 (Y/N)
- `nxt_tr_stop_yn` — NXT 거래정지여부 (Y/N)
- **파생값**: `nxt_tradable = (cptt_trad_tr_psbl_yn == "Y") AND (nxt_tr_stop_yn == "N")`

**Primary 판별**: `stock_master` 테이블(24h TTL 캐시) → `inquire_stock_basics(ticker)` (CTPF1002R)
- Lazy: 매수 진입/익일 청산 직전 조회 → miss/stale 시 KIS 호출 후 upsert
- Eager(향후): 07:50 _boot()에서 후보 일괄 갱신 (1차에서는 Lazy만)

**Fallback**: stock_master 조회 실패 또는 미보강 종목 → 기존 WebSocket 시가 수신 휴리스틱 유지
- `ticker_prices[ticker]["open_price"] > 0` (또는 `_resolve_open_price` 폴링) → NXT 거래 가능 추정
- 시가 미수신 → NXT 거래 불가 추정

#### (a) NXT 거래 가능 (`nxt_tradable=True` + 시가 수신) — 08:00 NXT 프리 지정가 청산
- 매수 체결가 대비 +10% 이상 갭상승 → 고점 -2% 트레일링 스탑 (기존 동작 유지)
- 갭상승 미달 → **지정가 매도** (직전가 -1호가, KRX 호가단위 적용)
  - `ORD_DVSN = "00"`(지정가), `EXCG_ID_DVSN_CD = "NXT"`
  - 호가단위: `src/engine/util/tick_size.py::step_down(current, steps=1)` — KRX 표준 7구간 (1/5/10/50/100/500/1000원)
  - **시장가 미사용 사유**: NXT 프리 시간대 시장가는 KIS 에서 거부될 수 있음

#### (b) NXT 거래 불가 (`nxt_tradable=False` OR 시가 미수신) — 09:00 KRX 메인 시가 확정 후 시장가 청산
- 08:00 시점에는 **청산 보류** (`_pending_next_day_clear` set 에 등록)
- **NXT 등록 사전 판별이 False면 30s 안정화도 거치지 않고 즉시 보류** (불필요한 NXT 주문 시도 0)
- 09:00 KRX 메인 시가 확정(`_confirm_breakout_open_prices(board="main")`) 직후
  `_drain_pending_next_day_clear()` 가 시장가로 일괄 정리
- 정규장 시간대이므로 시장가 OK

#### 거래소 라우팅 사전 다운그레이드
- `OrderEngine._strategy_exchange(strategy_id, ticker=...)` — ticker 인자 추가
- 전략 `exchange`가 NXT/SOR 이지만 `stock_master.get(ticker).nxt_tradable=False`이면 **KRX 강제 다운그레이드**
- `system_logs`에 `[nxt_downgrade]` prefix 1행 (strategy/ticker/원래 exchange/적용 exchange)

#### 사후 보강
- 매도 거부 시(KIS `APBK0918` + "장운영시간이 아닙니다" 등) `is_market_closed_rejection()` 가드로
  **메모리 `state.positions` 및 DB `positions` 보존** (재시도하지 않고 다음 거래 가능 시각에 자연 재트리거)
- 거부 발생 직후 `stock_master.upsert_one(ticker, nxt_tradable=False)` 사후 보강 → 같은 종목 재 NXT 호출 방지
- **시가 미수신 시 `high_since_buy` 폴백 + 갭률 0% 즉시 청산 경로는 제거** (전일 고가 혼입으로 좀비 포지션 위험)
- **시장가 호가 불가 거부(`is_market_order_disallowed`, APBK1943 "시장가호가불가" 등) Phase C, 2026-05-11**: 시장가 매도 경로(`limit_price=0`)에서 `step_down(현재가, 5)` 지정가 1회 폴백. 폴백 실패 시 메모리/DB positions 보존, cooldown 등록 안 함(청산 의무) → 다음 사이클 재트리거. 2026-05-11 계양전기(012200) 09:00:21 매도 ×3 + 수동 매도 ×2 실패 사고 대응

### 트레일링 스탑 상세
- NXT 프리 시가 이후 고점을 실시간 추적
- 현재가가 고점 대비 -2% 이하로 떨어지면 시장가 매도 트리거
- 수식: `(고점 - 현재가) / 고점 * 100 >= 2.0` 이면 매도

### 리스크 관리
- 종목당 최대 투자: 할당 자금의 25%
- 일일 최대 손실 한도: 할당 자금의 5% → 도달 시 당일 매매 중단
- 동시 보유 종목 수: 최대 4종목

---

## 4. 전략 B: 변동성 돌파 상세

### 핵심 개념
- **노이즈 비율** = 1 - |Close - Open| / (High - Low)
- **동적 K값** = 최근 20일 평균 노이즈 비율
- **보드별 매수 목표가** = 보드 시가 + (전일 Range × K값 × 보드별 K 곱)

### 보드별 시가/타겟 분리 (Phase 5 Q1=C)
보드마다 시가가 다르므로 별도로 추적:
- `_targets[ticker]["boards"]["main"]` ← KRX 09:00 시가 + (전일Range × K × `k_value_krx_main`)
- `_targets[ticker]["boards"]["pre_nxt"]` ← NXT 프리 첫 거래 시가 + (전일Range × K × `k_value_nxt_pre`)
- `_targets[ticker]["boards"]["post_nxt"]` ← NXT 애프터 첫 거래 시가 + (전일Range × K × `k_value_nxt_post`)
- 보드별 K 곱 기본값 1.0. NXT는 거래대금이 KRX의 ~10%로 변동성 큼 → 1.2~1.5로 보수 운용 권장

### 종목군
- 코스피 + 코스닥 전체에서 거래대금/시총 조건 필터
- 조건: 시가총액 1,000억 원 이상 AND **전일** 거래대금 200억 원 이상 (Settings에서 변경 가능)
  - 거래대금은 거래량순위 API 응답의 `prdy_vol × (stck_prpr - prdy_vrss)`로 산출 → 시간 의존 제거
- ETF/ETN 제외
- 최대 100종목

### 데이터 준비 (07:50 부트 시점)
- 각 종목의 최근 22일 일봉 데이터(시/고/저/종) 조회 (KIS FHKST03010100, 100일 응답)
- candles[0]이 오늘이면 candles[1]을 "전일"로 사용 (장 시작 전 빈/부분봉 방어)
- 종목별 K값 계산 + 전일 Range로 `target_offset_base` 산출
- `prev_range == 0` 또는 `target_offset_base == 0` 종목은 skip
- 전일 종가를 `scanner.ticker_prev_close`에 사전 등록

### 시가 확정 + 매수 규칙
- 보드 진입 시점에 `_confirm_breakout_open_prices(board=...)` 호출 → 보드별 시가 확정 + Target 계산
- **진입 조건**: 현재가 >= 활성 보드의 Target_Price 돌파 순간 (이전 틱 < target AND 현재 틱 >= target). 보드별 `_prev_price[ticker][board]` 분리
- **주문 방식**: 시장가 매수
- **투자 비중**: 할당 자금의 10% (1종목당) — 자금 부족 시 1주 fallback
- **동시 보유**: 최대 10종목
- **매매 보드**: PRE_NXT + MAIN (08:00~15:20). **POST_NXT 비활성** (2026-05-15 결함 D — 당일 15:20 일괄매도 정책으로 환원)
- **거래소 라우팅**: 기본 KRX. SOR 권장(NXT/KRX 자동 분배)

### 보드별 시가 확정 호출 — `board` 인자 명시 의무 (2026-05-15, 결함 A 대응)
- `_confirm_breakout_open_prices()` 자동 결정 분기는 `SessionTracker.active`를 main → post_nxt → pre_nxt 우선순위로 검색해 보드를 추론한다. SessionTracker의 `_session_loop`는 **30초 주기**라 보드 경계(08:00 / 09:00 / 15:30) 정각 호출과 race가 발생할 수 있다.
- **2026-05-14 사고**: 09:00:05 `TIME_KRX_OPEN_CONFIRM` 시점에 SessionTracker가 아직 main 진입을 반영 못 한 상태에서 `_confirm_breakout_open_prices()`가 호출됨 → pre_nxt만 active → `board="pre_nxt"` 폴백 → `_targets[ticker]["boards"]["main"]` 키가 영영 안 채워져 **5/14, 5/15 KRX 메인 시간대 VB/LTV 매수 신호 0건**.
- **불변식**: 보드 경계 정각 호출은 반드시 `board="..."`를 **명시 인자로** 전달한다. 자동 결정에 의존하지 않는다.
  - `TIME_PRE_NXT_OPEN` (08:00) → `board="pre_nxt"` 명시
  - `TIME_KRX_OPEN_CONFIRM` (09:00:05) → `board="main"` 명시
  - `TIME_KRX_MAIN_CLOSE` (15:30) → `board="post_nxt"` 명시 (이미 적용됨, 2026-05-12 M)
- **자동 결정 허용 호출** (시점이 가변이라 명시가 부적절):
  - 중간 부팅(09:00:05 이전 다른 시각 시작) 호출
  - `now > TIME_KRX_OPEN_CONFIRM` 조건의 스캔 시작 직전 재확정
- **Red 테스트 의무**: pytest+freezegun으로 09:00:05 시각 고정 + SessionTracker `_active`를 의도적으로 `{PRE_NXT}`만 활성 → `_confirm_breakout_open_prices()` 호출 후 `strategy._targets[t]["boards"]`에 `"main"` 키가 반드시 존재해야 함을 assert. 결함 상태에선 `"pre_nxt"`만 존재하므로 Red 성립 → `board="main"` 명시로 Green.

### 손절
- **조건**: 매수 체결가 대비 -3%
- **주문**: 즉시 시장가 전량 매도

### 강제 청산 — 보드별 분리
- **15:20 KRX 메인 매수 중단 + 강제 청산**: `tradable_boards`에 POST_NXT가 **없는** 전략의 종목만 청산. POST_NXT 활성 전략은 19:50까지 보유 유지
- **VB·LTV는 15:20 일괄 청산 (2026-05-15 결함 D)**: VB/LTV 둘 다 `DEFAULT_TRADABLE_BOARDS = ("pre_nxt", "main")` — POST_NXT 매수 비활성. `_force_clear_main_only` 의 keeps_post_nxt 분기에서 False → 15:20 청산 호출. VB는 모든 보유 청산, LTV 는 `_limit_up_reached` 제외(상한가 모드만 익일 보유). LTV 상한가 모드의 POST_NXT 손절 모니터링은 `risk.on_tick` 청산 평가가 보드 가드 무관하게 작동.
- **VB 익일 청산 안전망 (2026-05-15 결함 D 잔여 fix)**: VB `_execute_next_day_clear` 대상 포함. 당일 15:20 청산이 어떤 비상 상황으로 누락되면 다음 영업일 NXT 프리 시가에서 자동 청산. `check_exit_signal` 익일 청산 분기 추가(STOP_LOSS 우선 → pending 가드 → NEXT_DAY_CLEAR). 5/15 LG전자 사고 회복용.
- **19:50 NXT 애프터 매수 중단**: 모든 활성 전략 `buy_disabled = True`. POST_NXT 매수가 VB/LTV 에서 비활성이라 19:50 강제 청산 코드 부재 결함은 실질 영향 없음 (LTV 상한가 모드 종목은 정책상 익일 청산 의도).
- **20:00 NXT 애프터 종료**: VB 는 정상 경로상 OVERNIGHT 보유 없음 (15:20 청산). LTV 상한가 모드 종목 + 안전망 발동 VB 종목만 다음 영업일 NXT 프리 청산 대기.

### 리스크 관리
- 종목당 최대 투자: 할당 자금의 10%
- 일일 최대 손실 한도: 할당 자금의 5%

---

## 5. 전략 C: 롱테일 변동성 돌파 상세

VB와 진입 로직 동일 + 상한가 도달 시 익일 청산 모드로 전환해 긴 꼬리(롱테일) 추구.

### VB 대비 차이
- 추가 진입 필터: 전일대비 ≥ `min_prdy_rate`(기본 5%)
- 연속상한가 종목 제외 (`exclude_consecutive_limit`, 기본 2일 — 전일 기준 N일 연속 +25%↑면 후보 제외)
- 상한가 도달(+29%) 시 → 익일 청산 모드 전환(`_limit_up_reached` set)
- **2단계 청산**:
  - 당일 모드(상한가 미도달): 손절 -3%, 15:20 강제 청산 보류 가능(POST_NXT 활성 시 19:50까지)
  - 상한가 모드: 손절 -5%, 다음 영업일 NXT 프리 시가에서 갭상승 +10% → 트레일링 -2% / 그 외 즉시 매도
- 보드별 K값 분리는 VB와 동일

### 매매 보드 / 거래소 라우팅
VB와 동일.

---

## 6. 전략 D: 20일 신고가 스윙 (donchian_swing) 상세

### 개념
멀티데이 추세추종(터틀 스타일). 한 번 추세 잡힌 종목은 끝까지 따라간다는 클래식 추세 전략.

### 종목군
- **코스피200 + 코스닥150 고정 유니버스** (`scanner.KOSPI_200_TICKERS` + `KOSDAQ_150_TICKERS` 합집합) — 거래량순위 API 미사용(추세추종 부적합)
- 시가총액 컷만 사후 적용 (`min_market_cap`, 기본 3,000억)
- 거래대금 컷은 prepare()의 `volume_multiplier`(기본 1.5×)에서 일원화

### 진입 조건 (07:50 prepare)
1. 어제 종가가 최근 20일 신고가 돌파 (`donchian_period`)
2. 어제 종가가 60일 EMA 위 + EMA 우상향 (`long_ma_period`)
3. 어제 거래대금 ≥ 20일 평균 × `volume_multiplier`(1.5)
4. ATR(14) 산출

### 매수 규칙
- **시점**: 다음 영업일 09:05 ~ 09:30 사이 시장가 (1종목당 1회만)
- **갭 스킵**: 시가 갭상승 +3% 이상이면 진입 스킵 (`gap_skip_threshold`, 추격 매수 회피)
- **투자 비중**: 할당 자금의 20% (1종목당)
- **동시 보유**: 최대 5종목
- **매매 보드**: MAIN만 (KRX 메인 한정)
- **거래소 라우팅**: 기본 KRX
- **매수 평가 채널 (G안, 2026-05-12)**: WebSocket on_tick 매수 평가 **제거**. `scheduler._swing_buy_poll_loop()` 가 09:05~09:30 KST **1분 주기**로 `fetch_stock_detail`(KIS REST) 폴링하여 매수 평가. 일봉 전략이라 실시간 tick 평가가 구조적 낭비였던 결함 차단 — 후보 50~150개의 WebSocket 슬롯을 변동성 돌파(VB/LTV) 후보에 양보.
  - **보유 종목은 그대로 WebSocket(positions HIGH 그룹) 구독** → 청산(ATR 트레일링/-7% 하드)은 `risk.on_tick` 의 `check_exit_signal` 그대로 평가
  - `risk.on_tick` 매수 평가 직전에 `if strategy_id == "donchian_swing": continue` 가드 (이중 안전망)
  - `donchian_swing.check_buy_signal` 의 09:05~09:30 시간 가드 + `_bought_today` set 그대로 유지 (Pull 폴링도 중복 진입 방지)
  - `[swing_poll] candidates=N filtered=M bought=K elapsed=T.Ts` INFO 로그 1행 / 사이클

### 청산
- **하드 손절**: 매수가 대비 -7%
- **ATR×2 Chandelier 트레일링**: `high_since_buy − ATR(14) × 2` 이하로 떨어지면 매도
- **시간 청산 없음**: 15:20 강제 청산 제외 (`check_force_clear()` 빈 리스트)
- 평균 5~15 영업일 보유 → DB `positions` 영속화로 일자 넘어 유지

#### high_since_buy 일봉 폴백 (E3, 2026-05-12)
- **`recompute_held_atr()` 직후 또는 함께 `high_since_buy` 일봉 보정** — 매수일 다음 영업일~전영업일까지의 KIS 일봉 high max로 복구. 시세 미수신 누적으로 chandelier 트레일링 손절선이 매수가 부근에 동결되는 결함 차단 (2026-05-12 이마트 사례)
- 대상: **donchian_swing 보유 포지션만** (chandelier 트레일링 사용 전략). 헬퍼는 일반화하되 호출은 donchian만 — 다른 전략 확장은 별도 단계
- 보정 조건: `pos.buy_date < today_kst` 인 보유 포지션만. 매수일 당일/미래일은 skip (당일은 `buy_price`가 진실, 미래일은 비정상 → WARNING)
- 보정값: `max(pos.high_since_buy, max(eligible_daily_highs))` — 일봉 응답 후 매수일 < bsop_date < today 범위 필터 → 일별 `stck_hgpr` max
- DB 영속화: 보정값이 기존 high_since_buy 초과 시 `update_high(ticker, new_high)` (또는 `save_position`)로 UPDATE + `system_logs` `[high_since_buy_recover]` prefix 1행
- 안전 가드: 종목별 sequential await (Rate Limit), 일봉 fetch 예외/빈 응답 → 해당 종목 skip + 다른 종목 영향 없음
- `risk.py:72` 실시간 시세 기반 `high_since_buy` 갱신은 그대로 유지 — 이건 boot 시점 1회 복구만

#### 일중 시세 REST 폴링 보강 (2026-05-15, 결함 B 대응)
- **배경**: donchian_swing은 멀티데이 보유 + ATR×2 Chandelier 트레일링 + 하드 -7% 손절 전략이라 일중 시세에 100% 의존. 2026-05-15 운영 중 `[tick_coverage] fresh 4~16 / stale 22~32 / ratio 11~45%`가 종일 지속, `[stale_watcher]`도 KIS silent inactive로 6회 retry 초과 후 skip → **보유·후보 시세 둘 다 누락 → 손절 평가 불가** 운영 위험. UI(ScanMonitor 최종 후보)에서도 종목명/현재가 빈칸 다수.
- **해결 접근**: WebSocket을 보강하는 **REST 폴링 레이어** 추가. WS 정상이면 그대로, stale이면 REST가 메꿈. KIS Rate Limit(20req/s) 대비 1req/s 수준이라 안전 마진 충분.
- **위치**: `src/engine/scheduler.py` — `_swing_rest_poll_loop()` 신설 (기존 `_swing_buy_poll_loop`와 별개의 시세 보강 loop. 기존 G안의 `_swing_buy_poll_loop`는 09:05~09:30 매수 평가 전용으로 보존).
- **운영 시간**: 09:30 ~ 15:20 KRX 메인 시간대 (매수 진입 종료 후에도 보유 평가는 계속). `scan_task`처럼 `asyncio.create_task`로 발화하고 종료 시 cancel.
- **주기**: **60초**. 1차 구현은 단일 주기로 단순화. 향후 보유 30s / 후보 60s 분리는 운영 데이터 보고 결정.
- **대상 ticker 수집** (사이클 시작 시 합집합 산출, 6자리 영숫자 필터 + dedupe):
  1. `donchian._scanned_tickers` — donchian 최종 후보(매수 평가 대상)
  2. `donchian.state.positions.keys()` — donchian 보유 포지션 (손절·트레일링 평가 대상)
  3. `donchian.state.pending_buys` — 매수 주문 진행 중인 ticker (체결가 추정)
- **동작 (종목별 sequential await)**:
  1. KIS `inquire_stock_basics` 또는 `fetch_stock_detail` 단건 호출 (택1, backend-dev 판단 — 응답에 `current_price/open_price/change_rate/prdy_ctrt`가 포함되는 쪽)
  2. Rate Limit 보호: 종목 사이 `await asyncio.sleep(0.05)` (50ms)
  3. 응답으로 `scanner.ticker_prices[ticker]` dict 갱신 (`current_price` / `open_price` / `change_rate` / `prdy_ctrt`)
  4. `scanner.ticker_last_tick[ticker] = datetime.now(KST_TZ)` touch — stale_watcher가 자연스럽게 fresh 인식
  5. `ticker_names[ticker]` 비어있으면 응답 종목명 또는 `STATIC_TICKER_NAMES`에서 보강 (UI "최종 후보" 종목명 표시 복구)
  6. **보유 종목 한정**: REST 응답 직후 `RiskManager.on_tick(ticker, price)` 직접 호출 — 기존 트레일링/하드 손절 코드 재사용 (별도 청산 경로 신설 금지)
- **예외 격리**: KIS 5xx/timeout/`KisApiError`는 종목 단위 try/except로 흡수 (다음 종목 진행). loop 본체 예외는 `ERROR` 로그 + 다음 사이클 자연 회복. `_swing_rest_poll_task` 같은 보일러플레이트는 backend-dev 재량.
- **구조화 로그** (사이클당 1행, INFO + `system_logs`):
  ```
  [swing_rest_poll] candidates=N held=M pending=P updated=U failed=F elapsed_ms=X
  ```
  - `candidates` = `_scanned_tickers` 개수
  - `held` = donchian positions 개수
  - `pending` = donchian pending_buys 개수
  - `updated` = 이번 사이클에서 ticker_prices 갱신 성공 종목 수
  - `failed` = KIS 호출 실패 종목 수
  - `elapsed_ms` = 사이클 전체 소요 시간
- **WebSocket과 협업**: 같은 ticker가 WS로도 들어오면 `ticker_last_tick`을 양쪽이 갱신해도 무해 (멱등 갱신). stale_watcher(60s 신선도)가 두 경로 통합 인식. **`RiskManager.on_tick` 중복 호출도 무해** — 멱등 설계됨 (가격 같으면 신호 변화 없음).
- **불변식**:
  - 매수 평가는 폴링이 **트리거하지 않는다** — donchian 매수는 `_swing_buy_poll_loop`(09:05~09:30 1분 주기) 전용. 이 신설 loop는 **시세 갱신 + 보유 평가만** 책임.
  - `risk.py`의 donchian_swing 매수 스킵 가드(`if strategy_id == "donchian_swing": continue`) 그대로 보존.
  - WS 우선순위 큐(E1)와 무관 — 이 폴링은 WS 슬롯 사용 안 함.
- **Red 테스트 의무**: pytest+respx+freezegun으로 09:30 시각 고정 + donchian `_scanned_tickers`에 3종목 + `state.positions`에 1종목 등록. KIS `inquire-price` 응답을 respx mock. 폴링 loop 1사이클 후:
  1. `scanner.ticker_prices`에 4종목 모두 `current_price` 갱신 assert
  2. `ticker_last_tick`에 4종목 모두 timestamp 갱신 assert
  3. 보유 종목 1개에 대해 `RiskManager.on_tick` 호출 흔적 assert
  4. 보유 종목 응답을 매수가 -7% 미만 가격으로 mock한 별도 케이스에서 `OrderEngine.execute_sell(STOP_LOSS)` 호출 흔적 assert (손절 트리거 회로 검증)
  - 결함 상태(폴링 미구현)에선 `ticker_prices`가 비어 있으니 Red 성립.

### 리스크 관리
- 종목당 최대 투자: 할당 자금의 20%
- 일일 최대 손실 한도: 할당 자금의 8%

---

## 6-E. 전략 E: 눌림목 돌파 (bull_flag_breakout) 상세

### 개념
강한 상승(폴, flag pole) 직후 짧은 횡보·완만한 조정(플래그) 후 플래그 상단을 재돌파하는 클래식 셋업.
모멘텀 전략이 +29% 폭발 순간을 잡는다면, 본 전략은 그 후속 정리(소형 조정) 후 2차 상승 진입로를 담당한다.

### 종목군
- KOSPI + KOSDAQ 전체에서 사후 필터 (모멘텀과 동일한 등락률/거래량 순위 API 또는 일봉 사후 필터, backend-dev 판단)
- **시가총액 ≥ 500억** (`min_market_cap`, 기본 50_000_000_000)
- **20일 평균 거래대금 ≥ 20억** (`min_trade_amount`, 기본 2_000_000_000)
- ETF/ETN 제외 (기존 키워드 컨벤션 재사용 — KODEX/TIGER/RISE/KoAct/PLUS/TIMEFOLIO/WOORI/FOCUS/인버스/레버리지)
- 최대 100종목 (`max_scan_stocks`)

### 데이터 준비 (07:50 prepare)
- 종목별 일봉 30일치(폴 10일 + 플래그 10일 + 여유 10일) — `fetch_daily_candles(ticker, days=30)`
- `candles[0]==오늘`이면 `candles[1]`을 전일로 사용 (부분봉 가드, VB/LTV/donchian 컨벤션 재사용)

### 셋업 검증 (단계별 필터, prepare 시 통과 종목만 `_candidates`에 등록)
**폴(Pole) 조건 — `pole_lookback_days=3~10`**:
1. 직전 N영업일(3~10) 사이에 **누적 상승률 ≥ +20%** (`pole_min_return`, 기본 20.0)
2. 같은 구간 **음봉 비율 ≤ 30%** (`pole_max_red_ratio`, 기본 0.30) — `close < open`인 일수 / 구간 길이
3. 폴 구간 내 최고가 = `pole_high`, 폴 시작가 = `pole_start`, **폴 폭 = `pole_high - pole_start`**

**플래그(Flag) 조건 — `flag_lookback_days=3~10`** (폴 종료 직후 N영업일):
1. 플래그 구간 최고가 = `flag_high`, 최저가 = `flag_low`
2. **조정 폭 ≤ 폴 폭의 38.2%** (`flag_retracement_max=0.382`, 피보 retracement) — `(pole_high - flag_low) <= (pole_high - pole_start) × 0.382`
3. **플래그 평균 거래량 < 폴 평균 거래량 × 60%** (`flag_volume_ratio=0.60`) — 거래량 수축 확인
4. 플래그 종가 추세는 강한 우하향이 아니어야 함 (마지막 종가가 flag_low 보다 0.5×ATR 이상 멀지 않을 것 — 일종의 sanity check, 정밀한 회귀선 검사는 1차에서 생략)

검증 통과 시 `_candidates[ticker] = {pole_high, pole_low, pole_start, flag_high, flag_low, flag_avg_volume, atr14, prev_close}` 등록.

### 매수 규칙
- **진입 조건**: 현재가가 `flag_high`(플래그 상단) 돌파 순간 + 당일 거래량 ≥ `flag_avg_volume × 2.0` (`breakout_volume_mult=2.0`)
  - 돌파 순간: `이전 틱 < flag_high AND 현재 틱 ≥ flag_high` (VB 컨벤션 — `_prev_price[ticker]` 추적)
  - 거래량 컷: WebSocket tick 의 `acml_vol` 또는 분당 누적치 사용 — `scanner.ticker_prices[ticker]` 의 누적 거래량 필드 활용
- **진입 시간대**: **09:05 ~ 13:00 KRX 메인** (`entry_start=09:05` / `entry_end=13:00`, 시간 가드)
  - `tradable_boards=("main",)` — KRX 메인만, NXT 비활성(눌림목 패턴이 NXT 거래대금 부족으로 신뢰성 낮음)
- **거래소 라우팅**: 기본 `KRX` (모의 호환). 실전에서 SOR 권장은 backend-dev 판단
- **주문 방식**: 시장가
- **투자 비중**: 할당 자금의 25% (`position_ratio=0.25`) — 1주 폴백 `_fallback_one_share()` 호출
- **동시 보유**: 최대 4종목 (`max_positions=4`)
- **종목당 1회만**: `_bought_today` set (donchian 컨벤션 재사용) — 진입 시도 즉시 add (체결 여부 무관)
- **쿨다운**: 청산 후 **3영업일** (`reentry_cooldown_days=3`). DB `positions` 또는 `trade_history` 마지막 매도일 + 3 < today 면 재진입 허용. 1차 구현은 메모리 `_cooldown_until[ticker] = date` 로 단순화 가능 — 영속화는 backend-dev 판단

### 청산 (3단계 — `check_exit_signal`)
1. **하드 손절**: 매수가 -5% (`stop_loss_rate=-5.0`) → 즉시 시장가 매도 (Signal.STOP_LOSS)
2. **플래그 하단 이탈 손절**: `current_price < flag_low` → Signal.STOP_LOSS
3. **측정된 이동(measured move) — 절반 익절**:
   - **타겟가** = `flag_high + (pole_high - pole_start)` (플래그 상단에서 폴 폭만큼 상승)
   - 현재가 ≥ 타겟가 도달 순간 → **보유 수량의 50% 시장가 매도** (Signal.TRAILING_STOP 으로 보고 + 별도 부분 매도 라우팅)
   - **부분 매도 미지원 시 1차 구현 단순화**: 전량 매도로 처리 후 향후 부분 매도 헬퍼 도입. backend-dev 판단 — `Position.quantity` 분할 매도 로직은 `order_engine.execute_sell(ticker, quantity=N)` 호출 시 `state.positions[ticker].quantity` 차감이 일관성 있게 처리되는지 검증 필요. **본 단계 디폴트는 전량 매도** (한 종목 = 한 청산)
   - 절반 익절 처리 시 `_partial_exit[ticker]=True` 로 마킹 → 잔여 ATR 트레일링
4. **잔여 ATR×2 트레일링**: `_partial_exit[ticker]==True` 분기에서 `current_price <= high_since_buy - ATR×2` → Signal.TRAILING_STOP (donchian 컨벤션 재사용)
5. **시간 청산**: 진입 후 **5영업일 경과** 시 잔량 시장가 (`max_hold_days=5`) — `pos.buy_date + 5영업일 ≤ today` 판정 (KIS chk-holiday 활용 또는 단순 캘린더일 ±2 보정. 1차 구현은 단순 캘린더일 + 7 보정 가능, backend-dev 판단)

### 매수 회전
- 종목당 진입 1회 (`_bought_today` set)
- 청산 후 **3영업일 쿨다운**
- 신규 매수 차단 조건: `is_max_positions()` / `is_daily_loss_exceeded()` / `state.buy_disabled` / `registry.is_ticker_blocked_for_buy()`

### 리스크 관리
- 종목당 최대 투자: 할당 자금의 25%
- 일일 최대 손실 한도: 할당 자금의 6% (`daily_loss_limit=-6.0`)
- 동시 보유 종목 수: 최대 4종목

### 기본 파라미터 (`DEFAULT_PARAMS`)
```python
DEFAULT_PARAMS = {
    "tradable_boards": ["main"],
    "exchange": "KRX",
    # 폴
    "pole_lookback_min": 3,
    "pole_lookback_max": 10,
    "pole_min_return": 20.0,
    "pole_max_red_ratio": 0.30,
    # 플래그
    "flag_lookback_min": 3,
    "flag_lookback_max": 10,
    "flag_retracement_max": 0.382,
    "flag_volume_ratio": 0.60,
    # 매수
    "breakout_volume_mult": 2.0,
    "entry_start": "09:05",
    "entry_end": "13:00",
    "position_ratio": 0.25,
    "max_positions": 4,
    # 청산
    "stop_loss_rate": -5.0,
    "atr_period": 14,
    "atr_trail_mult": 2.0,
    "max_hold_days": 5,
    "reentry_cooldown_days": 3,
    # 유니버스
    "min_market_cap": 50_000_000_000,
    "min_trade_amount": 2_000_000_000,
    "max_scan_stocks": 100,
    # 일반
    "daily_loss_limit": -6.0,
}
```

### 운영 노트
- VTS(모의) 검증 가능 — KRX 메인 한정이므로 SOR/NXT 의존성 없음
- 셋업이 빈번하지 않은 패턴 — prepare 결과 0종목이 정상일 수도 있음. 0종목 ERROR 로그는 조건 완화 검토 신호로 사용
- `_workspace/00_leader_trading_rules.md` 변경 시 `src/engine/CLAUDE.md`·`CLAUDE.md` 다중 전략 표 동기화

---

## 6-F. 전략 F: 변동성 수축 돌파 (vcp_breakout) 상세

### 개념
미네르비니식 VCP(Volatility Contraction Pattern). 상승 후 변동성이 단계적으로 축소되는 베이스(2~4회 pullback, 점진 수축) → 거래량 폭증 베이스 상단 돌파 시 매수.
donchian_swing 의 정공법(신고가 직진 추격)을 보강하는 추세추종 보조 전략. VCP 는 베이스 + 변동성 수축 확인으로 후핵폐기를 줄인다.

### 종목군
- **코스피200 + 코스닥150 고정 유니버스 권장** (donchian 컨벤션 재사용 — `scanner.KOSPI_200_TICKERS + KOSDAQ_150_TICKERS`)
- **시가총액 ≥ 1,000억** (`min_market_cap`, 기본 100_000_000_000)
- **60일 평균 거래대금 ≥ 30억** (`min_trade_amount`, 기본 3_000_000_000)
- ETF/ETN 제외
- 최대 200종목 (`max_scan_stocks`)

### 데이터 준비 (07:50 prepare)
- 종목별 일봉 **220일** 가져오기 (200일 EMA + 여유 20일) — `fetch_daily_candles(ticker, days=220)`
- `candles[0]==오늘`이면 `candles[1]`을 전일로 사용 (부분봉 가드)

### 추세 필터 (Stage 2 confirmation, prepare 시 단계별 검사)
1. **종가 > 50일 EMA > 150일 EMA > 200일 EMA** (`ema_short=50`, `ema_mid=150`, `ema_long=200`)
2. **200일 EMA 우상향 1개월 이상** — 현재 200일 EMA > 1개월 전(20영업일 전) 200일 EMA (`long_ema_uptrend_days=20`)
3. 통과 종목만 다음 단계 검사

### 베이스 정의 (`base_lookback_weeks=5~15` → 일봉 25~75영업일)
1. 베이스 시작·종료 자동 검출: 최근 N영업일(75일) 내에서 `(highest_close - lowest_close) / lowest_close ≤ 0.25` 인 최장 연속 구간을 베이스로 인식 (`base_depth_max=0.25`)
2. **베이스 깊이** = `(base_high - base_low) / base_high ≤ 30%` (`base_depth_pct=0.30`)
3. 베이스 길이 = 25~75영업일 (`base_min_days=25`, `base_max_days=75`)

### 조정 시퀀스 (Pullback Sequence, 점진 수축)
1. 베이스 구간 내 pullback 자동 검출: 직전 swing high → swing low 까지의 하락 폭 → 다음 swing high 까지의 상승. `pullback_count_min=2`, `pullback_count_max=4`
2. 각 pullback 폭 = `(swing_high - swing_low) / swing_high` (%)
3. **각 pullback 폭이 직전 pullback 보다 작아야 함** (점진 수축, 변동성 contraction)
4. **마지막 pullback ≤ 8%** (`last_pullback_max=0.08`)

### 거래량 수축
- 베이스 형성 중 **마지막 5일 평균 거래량 < 베이스 직전 20일 평균 거래량 × 70%** (`volume_contraction_ratio=0.70`)
- 베이스 직전 20일 = 베이스 시작 직전 영업일들

검증 통과 시 `_candidates[ticker] = {base_high, base_low, last_pullback_pct, atr14, ema50, ema150, ema200, prev_close}` 등록.

### 매수 규칙
- **진입 조건**: 현재가가 `base_high`(베이스 상단, `pivot_high`) 돌파 순간 + 당일 거래량 ≥ 20일 평균 × 1.5 (`breakout_volume_mult=1.5`)
  - 돌파 순간: `이전 틱 < base_high AND 현재 틱 ≥ base_high` (VB 컨벤션)
- **진입 시간대**: **09:05 ~ 14:30 KRX 메인** (`entry_start=09:05` / `entry_end=14:30`)
  - `tradable_boards=("main",)`
- **거래소 라우팅**: 기본 `KRX`
- **주문 방식**: 시장가
- **투자 비중**: 할당 자금의 20% (`position_ratio=0.20`) — 1주 폴백 `_fallback_one_share()`
- **동시 보유**: 최대 5종목 (`max_positions=5`) — donchian 과 동일 수준
- **종목당 1회만**: `_bought_today` set
- **쿨다운**: 청산 후 **7영업일** (`reentry_cooldown_days=7`)

### 청산 (멀티데이, 시간 청산 없음)
1. **하드 손절**: 매수가 -7% (`stop_loss_rate=-7.0`) → Signal.STOP_LOSS
2. **베이스 하단 이탈**: `current_price < base_low` → Signal.STOP_LOSS
3. **ATR×2 트레일링 (Chandelier)**: `current_price <= high_since_buy - ATR×2` → Signal.TRAILING_STOP (donchian 컨벤션 재사용 — `_atr()` 헬퍼)
4. **50일 EMA 이탈**: `current_price < ema50` (일봉 기준으로 매일 재계산되지만 1차 구현은 prepare 시점 `ema50` 그대로 사용 + 향후 매일 갱신 검토. backend-dev 판단) → Signal.TRAILING_STOP
5. **시간 청산 없음 + 15:20 강제 청산 없음** — `check_force_clear() = []` (donchian 컨벤션, 멀티데이 보유)

### 멀티데이 보유 영속화
- `Position._MULTIDAY_STRATEGIES` frozenset 에 `vcp_breakout` 추가 — `is_next_day` 항상 False 반환 (OrderMonitor "청산" 배지 미표시, donchian I2 컨벤션)
- DB `positions` 영속화로 일자 넘어 유지
- `recompute_held_atr()` + `recompute_high_since_buy()` 동등 메커니즘 적용 (boot 시 일봉 fetch 로 ATR 재계산 + high_since_buy 폴백) — backend-dev 가 donchian 헬퍼 재사용 또는 vcp 별도 메서드 판단

### 매수 회전
- 종목당 진입 1회 (`_bought_today` set)
- 청산 후 **7영업일 쿨다운**
- 신규 매수 차단 조건: `is_max_positions()` / `is_daily_loss_exceeded()` / `state.buy_disabled` / `registry.is_ticker_blocked_for_buy()`

### 리스크 관리
- 종목당 최대 투자: 할당 자금의 20%
- 일일 최대 손실 한도: 할당 자금의 8% (`daily_loss_limit=-8.0`)
- 동시 보유 종목 수: 최대 5종목

### 기본 파라미터 (`DEFAULT_PARAMS`)
```python
DEFAULT_PARAMS = {
    "tradable_boards": ["main"],
    "exchange": "KRX",
    # 추세 필터
    "ema_short": 50,
    "ema_mid": 150,
    "ema_long": 200,
    "long_ema_uptrend_days": 20,
    # 베이스
    "base_min_days": 25,
    "base_max_days": 75,
    "base_depth_pct": 0.30,
    # 조정 시퀀스
    "pullback_count_min": 2,
    "pullback_count_max": 4,
    "last_pullback_max": 0.08,
    # 거래량 수축
    "volume_contraction_ratio": 0.70,
    # 매수
    "breakout_volume_mult": 1.5,
    "entry_start": "09:05",
    "entry_end": "14:30",
    "position_ratio": 0.20,
    "max_positions": 5,
    # 청산
    "stop_loss_rate": -7.0,
    "atr_period": 14,
    "atr_trail_mult": 2.0,
    "reentry_cooldown_days": 7,
    # 유니버스
    "min_market_cap": 100_000_000_000,
    "min_trade_amount": 3_000_000_000,
    "max_scan_stocks": 200,
    # 일반
    "daily_loss_limit": -8.0,
}
```

### 운영 노트
- 미네르비니식 셋업은 빈번하지 않음 — 정상 운영에서도 일일 후보 0~5 종목이 정상
- 멀티데이 보유 — donchian_swing 과 동일 부류, `_MULTIDAY_STRATEGIES` 멤버 등록 필수
- VTS(모의) 검증 가능 — KRX 메인 한정
- 추후 200일 EMA 갱신 빈도, base 자동 검출 알고리즘 정밀도는 운영 데이터 기반으로 튜닝

---

## 7. 공통 규칙

### 부분 체결 처리
- 시장가 주문도 호가 잔량 부족 시 부분 체결 가능
- 부분 체결 시: trade_history에 PARTIAL 상태로 기록, 체결된 수량만 반영
- 미체결 잔량: 30초 대기 후 미체결이면 잔여 주문 취소
- 손절 시 부분 체결: 체결된 부분은 손절 완료로 처리, 잔여는 재주문

### 체결 기반 포지션 관리
- **체결통보 WebSocket 구독 필수**: 시세(H0UNCNT0 KRX+NXT 통합) 외에 체결통보(실전: H0STCNI0, 모의: H0STCNI9)를 반드시 구독해야 함
- 통합 시세 `H0UNCNT0`로 KRX/NXT 거래가 같은 콜백으로 흘러옴 — 거래소 식별은 체결통보 `ODER_KIND` 필드에서
- **장운영정보 H0UNMKO0 구독** (실전 한정): 대표 종목(`005930`) 1개로 보드 전환 코드(`MKOP_CLS_CODE`) 실시간 수신
- 주문 접수 시 pending_buys에 등록 (중복 주문 차단)
- **체결통보 수신 시** 포지션 등록/제거 (주문 직후가 아님 — 체결 확인 전 포지션 등록하면 안 됨)
- 주문번호 매핑(`_order_qty`/`_order_strategy`/`_order_ticker`) 등록은 `place_order` 응답 직후 동기 영역에서. `await insert_trade` 진입 전 (시장가 즉시체결 race 방지)
- 체결통보 선행 race 가드: `_completed_orders` set + UPDATE 0건 보정 INSERT
- 기동 시: KIS 주문체결내역 API + DB trade_history.strategy로 포지션/미체결 복구
- 매수일자(buy_date) 기반 익일 청산 판정 (시간 기준이 아님)

### 매수 안전장치
- **종목코드 형식 비대칭**: 진입은 6자리 숫자만(`isdigit`) — ETF·신주인수권 차단. 사후처리(체결통보·잔고 sync)는 6자리 영숫자(`isalnum`) 허용
- **매수가능 캐시**: 60초 TTL — KIS `get_buyable()` 호출을 매 틱 → 분당 1회로 축소
- **잔고부족 매수 락**: 900초 — `is_insufficient_cash` 응답 또는 `max_buy_quantity≤0` 시 다음 잔고 sync까지 매수 차단
- **per-ticker low_funds cooldown**: 900초 — `calc_buy_quantity()<=0`인 종목 매 틱 반복 호출 차단
- **매도 잔고부족 즉시 break**: `is_insufficient_quantity` 응답 시 3회 재시도 생략 + 메모리·DB positions 정리

### 스케줄 — KRX/NXT 통합 운영 (08:00~20:00)

| 시각 | 동작 |
|------|------|
| 07:45 | 자동 매매 시작 (`AUTO_START` + DB 재확인. 주말+공휴일 KIS chk-holiday로 자동 건너뜀) |
| 07:50 | 프로세스 기동, OAuth 토큰 갱신, DB 포지션/설정 복구, 전략별 자금 분배, 전략 prepare(일봉/K값/전일종가/도치안 단계별 통계) |
| 07:55 | WebSocket 연결, **체결통보(H0STCNI0/9) 구독** + **통합 장운영정보(H0UNMKO0/005930) 구독** + 사전 구독(돌파+스윙+보유 합집합) |
| 08:00 | NXT 프리 진입 — 익일 청산 백그라운드(30초 안정화 후 NXT 시가 청산) + 돌파 시가 확정(`board="pre_nxt"`) + VB/LTV PRE_NXT 매매 시작 |
| 09:00:05 | KRX 메인 시가 확정 — VB/LTV `board="main"` 별도 시가 + KRX 09:00 시가 + (전일Range × `k_value_krx_main`) Target_Price 계산 → MAIN 매매 진입 |
| 09:05~09:30 | donchian_swing 진입창 — 시장가 1주문/종목, 갭 +3%↑ 스킵 |
| 09:30 | 모멘텀 종목 스캔 시작. 5분 주기 `_scan_loop` 시작(돌파+스윙+보유 합집합 재구독) |
| 15:20 | KRX 메인 신규 매수 중단 + KRX 메인 강제 청산(`_force_clear_main_only`) — POST_NXT 활성 전략 종목은 보유 유지 |
| 15:30 | KRX 메인 마감 → NXT 애프터 전환. VB/LTV는 POST_NXT에서 매매 계속 |
| 19:50 | NXT 애프터 신규 매수 중단 (`buy_disabled = True`. 자문은 20:00 으로 이동, Phase 0/2026-05-15) |
| 20:00 | NXT 애프터 종료(WebSocket 구독 해제) + 전략수정 AI자문 생성(OpenAI → `parameter_recommendations`). 동기 순차 실행 — 자문 ~3분, settlement 20:10 까지 7분 여유 |
| 20:10 | 전략별 + 합산 일일 정산, daily_performance 기록, 일일 로그 분석 리포트 생성(OpenAI → `daily_log_reports`), 프로세스 Sleep |

### 야간 매매(POST_NXT 15:30~20:00) 운용 원칙 — Q3=A 활성
- 사용자 부재 시간대 사고 위험 인지 — Settings 상단 amber 경고 배너 노출
- 손절·트레일링은 실시간 작동
- NXT 거래대금 KRX 대비 ~10%로 변동성 큼 → 보드별 K 곱(`k_value_nxt_post`) 1.2~1.5 보수 운용 권장
- 비활성화 원하면 Settings 페이지에서 해당 전략의 `tradable_boards`에서 POST_NXT 해제

### API Rate Limit 대응
- 초당 20건 제한 준수
- 일괄 매도(손절 동시 발생) 시 asyncio.Semaphore로 큐잉
- 주문이 지연되더라도 순차 실행 보장

### 환경 설정
- .env의 `KIS_ENV`로 실전/모의 전환 (인증 정보 자동 매핑)
- 모든 TR_ID는 `settings.get_tr_id()`로 환경별 자동 변환
- **모의(VTS)는 KRX만 지원** — SOR/NXT는 실전 한정. 모의에서 NXT/SOR 시도 시 KIS가 거절
- 실전 전환 시 반드시 팀장 승인 필요

### 전략별 잔고/실적 관리
- trade_history: strategy 컬럼으로 전략별 거래내역 분리
- daily_performance: (date, strategy) 복합PK로 전략별 + 합산 실적 기록
- 정산 시각 변경 영향: total_asset 계산 시점이 16:10 → 20:10로 이동, 종가가 NXT 20:00 마지막 체결가가 됨

### 시간 상수 (`src/engine/scheduler.py`)
| 상수 | 값 | 의미 |
|---|---|---|
| `TIME_AUTO_START` | 07:45 | 자동 매매 시작 |
| `TIME_BOOT` | 07:50 | 프로세스 부트 |
| `TIME_PRESUBSCRIBE` | 07:55 | 사전 구독 |
| `TIME_PRE_NXT_OPEN` | 08:00 | NXT 프리 진입 (익일 청산 + VB/LTV PRE_NXT) |
| `TIME_KRX_OPEN_CONFIRM` | 09:00:05 | KRX 메인 시가 확정 |
| `TIME_SCAN_START` | 09:30 | 모멘텀 스캔 |
| `TIME_KRX_MAIN_BUY_STOP` | 15:20 | KRX 메인 매수 중단 + 강제 청산 |
| `TIME_KRX_MAIN_CLOSE` | 15:30 | KRX 메인 마감 → NXT 애프터 전환 |
| `TIME_NXT_POST_BUY_STOP` | 19:50 | NXT 애프터 매수 중단 (안전 마감, 변경 금지) |
| `TIME_NXT_POST_CLOSE` | 20:00 | NXT 애프터 종료, unsubscribe |
| `TIME_RECOMMENDATION` | 20:00 | AI자문 생성 (Phase 0, 2026-05-15: 19:50 → 20:00 이동, 백테스트 검증 정합성) |
| `TIME_SETTLEMENT` | 20:10 | 정산 + 일일 로그 분석 |
| `NEXT_DAY_STABILIZE_SECS` | 30 | 익일 청산 NXT 프리 시가 안정화 |
| `SESSION_TICK_INTERVAL` | 30 | SessionTracker 보드 전환 감시 주기 |

### 위험 요약 (실전 전환 전 검토)
1. **VTS 검증 불가** — SOR/NXT는 실전 한정. 카나리 운영 어려움
2. **NXT 거래대금 ~10%** — 시가 흔들림이 매매 신호 노이즈로 작용 가능
3. **야간 매매 모니터링 부재** — 사용자 부재 시간대 사고 위험. POST_NXT는 명시 토글로만 활성
4. **정산 시각 이동 영향** — daily_performance 'date' 의미, EC2 자동 재시작 정책, 익일 부팅 시각 모두 영향
5. **종목 적격성** — NXT 거래 가능 종목이 KRX 전 종목인지 일부인지 명세 미기재. 운영 데이터로 검증 필요

### AI자문 고도화 (Phase J4, 2026-05-12)

기존 AI자문(Phase 0 이후 20:00 발화)은 `recommended_params` 화이트리스트 키만 권고했으나, **전략별 자산배정(weight)** 과 **로직/파라미터 추가·삭제** 같은 구조적 변경은 권고 채널이 없었다. J4 에서 두 채널을 신설하되 **자동 적용은 절대 없음** — 모두 운영자 수동 검토 후 명시적 apply.

**DB 스키마 확장 (`parameter_recommendations`)**:
- `recommended_weight NUMERIC` — AI 추천 전략 weight (0.0~1.0). null = 변경 권고 없음
- `code_review_notes TEXT` — 로직/파라미터 추가·삭제 자유 텍스트 자문. 최대 2000자. 자동 적용 없음
- `applied_weight NUMERIC` — 사용자가 apply 시점에 실제 적용한 weight (트래킹용)

**recommendation_engine 컨텍스트 확장**:
- `current_weight` (자기 전략 weight) + `peer_weights` (다른 enabled 전략 weight dict) + `peer_metrics` (다른 전략 최근 성과 dict) 를 user_payload 에 추가
- 프롬프트에 명시: ① 다른 전략 weight + 성과 종합해 자기 비중 변경 권고 (0.0~1.0). 합계 1.0 근접은 **운영자가 apply 시점에 책임** ② 화이트리스트 외 신규 파라미터 도입 또는 폐기 제안을 자유 텍스트로 (최대 2000자, 코드 자동 변경 없음)

**검증 헬퍼 (`_validate_recommendations` 확장)**:
- `recommended_weight`: float 캐스트 + `0.0 <= x <= 1.0` 범위 검증. 범위 외면 None 으로 무시 + WARNING 로그
- `code_review_notes`: str 캐스트 + `len(text) > 2000` 이면 2000자로 잘라냄. 비-str 이면 None

**apply 흐름 (`POST /api/recommendations/{id}/apply`)**:
- body 신규 옵션: `apply_weight: bool = False`
  - True 일 때 `recommended_weight == None` 이면 400 (`"적용할 weight 가 없습니다"`)
  - True + 유효한 weight 면 `strategy_config.weight` 갱신 (`save_weights({strategy_id: recommended_weight})`) + `registry.update_weights()` 메모리 반영 + DB `parameter_recommendations.applied_weight` 갱신
  - **`allocate_funds()` 즉시 재호출 금지** — 다음 `_boot()` (다음 영업일 07:50) 에서 자연 반영
- 기존 `apply_keys` 와 `apply_weight` 동시 가능 — 둘 다 처리
- 응답 데이터에 `applied_weight: float | null` 포함

**프론트엔드 (`Recommendations.tsx`)**:
- **자산 배정 카드** (recommended_weight 가 null 아닐 때만): 현재 weight → 추천 weight + 변경량(%p) + "weight 적용" 체크박스. 체크 시 apply body 에 `apply_weight: true` 포함. 적용 후 `applied_weight` 표시 + amber 안내 "다음 영업일부터 반영"
- **로직/파라미터 자문 카드** (code_review_notes 가 null 아닐 때만): 자유 텍스트 (whitespace-pre-wrap, max-height + overflow-y-auto). "검토 완료" 토글은 클라이언트 상태(localStorage 선택)
- 기존 params 적용 카드는 그대로 유지 — 변경 없음

**안전 불변식**:
- weights 자동 적용 절대 금지 — `apply_weight=true` 명시 시에만
- code_review_notes 텍스트 기반 코드 자동 변경 절대 금지 — 정보 표시만
- `allocate_funds()` 시그니처 그대로, 즉시 재호출 안 함 (다음 _boot 반영)
- 기존 `apply_keys` 흐름 + J1~J3 + I1~I3 + 다른 Phase 영향 없음

---

## (2026-05-13) 작업 1 — 활성 보드만 노출 (VB/LTV `get_targets_status`)

### 결함
KST 09:09 (PRE_NXT 비활성, MAIN 활성) 시점에도 `get_targets_status()` 가 `_targets[ticker].boards` 의 **모든 보드** target 을 노출 → 프론트엔드가 "프리" 라벨로 표시 → 사용자 혼란. VB(`src/engine/strategies/volatility_breakout.py:278~305`) 및 LTV(`src/engine/strategies/long_tail_volatility.py:309~331`) 동일 결함.

### 백엔드 명세
- `get_targets_status()` 내부에서 `from src.engine.session import session_tracker` (지연 import — 모듈 순환/테스트 격리)
- `active_boards = session_tracker.active` (frozenset[MarketBoard])
- `tradable = parse_tradable_boards(self.config.params.get("tradable_boards"))` 또는 `DEFAULT_TRADABLE_BOARDS` fallback
- **노출 보드 집합** `visible = {b.value for b in (active_boards & tradable)}`
- ticker 별 처리:
  - `visible == set()`: `boards={}`, top-level `target_price/open_price/target_offset=0`, `open_confirmed={}`
  - `visible != set()`: 기존 `info.get("boards", {})` 중 `b in visible` 만 dict 에 포함. top-level 은 노출 보드 중 우선순위(main → post_nxt → pre_nxt) 첫 `confirmed=True` 보드 기준 → 없으면 우선순위 첫 보드의 값(미확정이면 0). `open_confirmed` 도 노출 보드만 `{board: bool}` 로 필터
- LTV 동일 변경 (`limit_up_reached` 키는 보존)

### 안전 fallback
`session_tracker` import/`session_tracker.active` 접근 예외 시 → **기존 모든 보드 노출** (외부 호환 + 장애 시 운영자 시야 보존). `try/except Exception` 으로 흡수.

### 프론트엔드 명세 (`frontend/src/components/ScanMonitor.tsx:769~860`)
- `usedBoards` 계산: `t.boards` 키 합집합 (변경 없음 — 백엔드가 이미 활성 보드만 보내므로 자연 정리)
- `boardRows` 빌더:
  - `t.boards` 가 비어있고 `activeBoardCode` 없음(장 외) → `return null` 후 `filter(Boolean)` 으로 종목 row 자체 제외
  - `t.boards` 가 비어있고 `activeBoardCode` 있음 → 기존 backwards-compat 단일 row (top-level 사용)
  - `t.boards` 가 비지 않음 → 기존 로직 그대로 (백엔드 필터링 자연 적용)

### 테스트
**백엔드 (VB)**: `tests/unit/engine/strategies/test_volatility_breakout.py` 추가 4건
- `test_get_targets_status_returns_only_active_boards`: session_tracker.active={MAIN} 시 `boards` 키 `["main"]` 만
- `test_get_targets_status_returns_empty_when_no_active_board_intersection`: active={KRX_AFTER} 시 boards={} + top-level=0
- `test_get_targets_status_top_level_uses_first_active_confirmed_board`: active={MAIN, POST_NXT} 중 MAIN confirmed=True 면 top-level=main 값
- `test_get_targets_status_when_session_module_unavailable_falls_back_to_all_boards`: monkeypatch 로 session import 실패 시뮬 → 모든 보드 노출

**백엔드 (LTV)**: `tests/unit/engine/strategies/test_long_tail_volatility.py` 추가 동일 구조 4건 (+ `limit_up_reached` 키 보존 검증)

**프론트엔드**: `frontend/src/components/__tests__/ScanMonitor.boards.test.tsx` 신규 3건
- `boards 빈 dict + activeBoardCode 없음 → 종목 row 미렌더`
- `boards={main:...} + activeBoardCode=main → 단일 row 렌더`
- `boards 빈 dict + activeBoardCode=main(backwards-compat) → top-level 기반 row 렌더`

### 응답 호환성 불변
- 스키마(필드명/타입) 보존 — boards dict 가 빈 dict 일 뿐, 키 자체 제거 안 함
- top-level `target_price`/`open_price`/`target_offset`/`open_confirmed` 보존 (필드 누락 없음)
- OrderMonitor 보유 행은 매수가 중심이라 영향 0

---

## (2026-05-13) 작업 2 — breakout 후순위 cap 25 (momentum 보호)

### 결함
2026-05-13 08:57:39 로그:
`사전 구독: total=33 (vb=30, ltv=30, swing=2, momentum=0, positions=3)`

BLNG 다중 호출로 VB/LTV 각 30종목 → dedup 후 28 breakout 슬롯 점유. 09:30 momentum 발화 시 ~10~30 추가 → 41 초과 → momentum drop 위험. 모멘텀 전략은 09:30 신호 발생 직전에 갓 구독해야 돌파 순간 감지 가능 → drop 시 매수 기회 통째로 상실.

### 명세
- 상수: `BREAKOUT_LOW_CAP = 25` (`src/engine/scanner.py` 모듈 레벨, `MAX_SUBSCRIPTIONS` import 옆)
- 구현 위치: `subscribe_filtered_stocks` 의 `priority_groups` 분기, **breakout 큐 처리 직전**:
  ```
  if len(breakout) > BREAKOUT_LOW_CAP:
      drop_counts["breakout"] += (len(breakout) - BREAKOUT_LOW_CAP)
      breakout = breakout[:BREAKOUT_LOW_CAP]
  ```
- 이후 기존 `for label, candidates in (("breakout", breakout), ("momentum", momentum), ("swing", swing)):` 루프 그대로 (잔여 슬롯 부족 시 추가 drop 카운트 합산)
- HIGH 무영향: positions/next_day_clear `bypass_limit=True` 절대 보장 (Phase E1 불변식)
- 우선순위 순서 유지: breakout(cap 25) → momentum → swing
- 로그 형식 유지: `[priority_drop] breakout=X momentum=Y swing=Z total_subscribed=N max=41 high_count=H low_remaining=R` — cap 초과 drop 도 `breakout` 카운트에 합산

### slot 분배 시뮬레이션
- HIGH: positions 3 + next_day_clear 1 = 4 (bypass)
- LOW 잔여: 41-4 = 37
- breakout 30 → cap 25 → 25 add + 5 drop
- momentum 10 → 잔여 12 → 10 add (drop 0)
- swing 0 (Pull 폴링이므로 WS 미사용 — G안 2026-05-12)
- total_subscribed = 4+25+10 = 39 (≤ 41), low_remaining = 2

### 테스트
`tests/unit/engine/test_scanner_priority_cap.py` 신규 4건 (또는 기존 `test_scanner_priority_order.py` 에 추가):
- `test_breakout_cap_25_applied_when_breakout_exceeds`: breakout 30, cap 25 → 25 add + 5 drop
- `test_breakout_cap_preserves_momentum_slot`: HIGH 4, breakout 30, momentum 10 → breakout 25 / momentum 10, drop=(breakout=5, momentum=0, swing=0)
- `test_breakout_cap_no_effect_when_under_cap`: breakout 20 → 20 add + 0 drop
- `test_breakout_cap_constant_value_is_25`: `assert scanner.BREAKOUT_LOW_CAP == 25`

### 안전 불변식
- HIGH(positions + next_day_clear) bypass_limit=True 절대 보장
- `MAX_SUBSCRIPTIONS=41` 초과 절대 금지
- 매핑 동기 등록 규약(`_order_qty/_order_strategy/_order_ticker/_pending_buy_orders`) 영향 0 — WS 구독 흐름 한정

---

## 커밋 5분할 (squash 금지)
1. `feat(strategies): VB/LTV get_targets_status returns active boards only`
2. `feat(scanner): cap breakout to 25 slots in priority queue (protect momentum)`
3. `feat(frontend): hide non-active board rows in ScanMonitor`
4. `test(strategies/scanner/frontend): cover active board filter and breakout cap`
5. `docs(engine/frontend): document active-board filter and breakout cap`

PR #2 (브랜치 `claude/diagram-stock-filtering-IaJ4G`) 위에 push → 자동 갱신.
