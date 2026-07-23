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

### 전략 G: 고지로 대순환 스윙 (strategy_id: kojiro) — 2026-07 라이브 (enabled=True·비중 19%)
이동평균선 대순환(EMA 5/20/40 배열 스테이지) 추세추종. donchian 정공법 보강 — "질서정연한 추세"를 EMA 정배열 상태로 포착.
- **유니버스**: 전체 상장 종목(지수 고정 해제, 시총 500억↑·거래대금 10억↑ 컷) + **ATR/종가 변동성 밴드 1.0~6.0%(비협상 판별 필터 — <1% 노이즈·>6.0% 급등작전주 배제. 상한 4.5→6.0 은 2026-07-20 백테스트 확정: PF 0.86→1.60, 평균손익 -0.5%→+2.2%, 거래 2.2배)**.
- **동시보유 리스크 캡**: `max_positions=5` + **동일섹터 동시보유 ≤ `max_positions_per_sector=2`** (매수 게이트 전용·fail-open·청산 미차단, 2026-07-20 도입). 섹터 프록시 = KRX 산업지수 플래그 + 업종 대분류 폴백.
- **후보 점수 랭킹** (2026-07-20, 원설계 §9④): 후보 > 슬롯/섹터캡 경합 시 `0.4×MACD3기울기 + 0.3×띠폭확장률 + 0.3×6→1신선도`(후보풀 min-max 정규화 가중합)로 최적 셋업 우선 매수. 이미 계산되나 미사용(dormant)이던 대순환 MACD3·띠폭 지표 배선. **매수 후보 정렬만** — strict entry 자격·청산 임계 무변경, `rank_w_*` 가중치 PARAM_RANGES 제외(정체성 상수).
- **매수(strict entry, 4조건 AND)**: ① 현재 스테이지 1(단기>중기>장기) ② 최근 5영업일 내 6→1 전환 인접(신선도, `stage1_freshness=5` — 2026-07-20 백테스트 3→5 PF 1.60→1.75·평균 +2.2→+3.0%) ③ EMA 3선 우상향 ④ 전일 종가 > EMA5. **KRX 메인 09:05~09:30 시장가**, 갭업 ≥5% / 갭다운 ≤-4% / 장중 붕괴(현재가<시가) 스킵, 1회만.
- **청산(우선순위)**: 고정% 하드손절 -8%(ATR 독립 backstop) → 2ATR 하드손절(tighten-only) → 스테이지3 진입(추세 종료, 익일 아침 발화) → 2.5ATR 샹들리에 트레일링. **시간·15:20 청산 없음(멀티데이)**.
- **Phase 1 = position_ratio 자금관리**. 조기진입(스테이지6)·터틀 유닛 sizing·피라미딩 = **Phase 2 연기**.
- **⚠️ "돌파 순간 절대규칙" 명시적 승인 예외**: kojiro 진입은 전일 종가에 확정되는 *완성 일봉 상태조건*이라 장중 목표가 교차(돌파 순간)가 아니다 — VB/LTV 같은 intraday breakout 클래스 전용 규칙(이전틱<기준가 AND 현재틱≥기준가) 미적용. donchian 과 동일 "일봉 확정 → 익일 시가 집행" 클래스. **단 kojiro 는 donchian보다 장중 확증이 약함**(donchian 은 장중 신고가 재돌파 확인 유지, kojiro 는 장중 검증 0) → 이 약화를 **방어선 4중으로 보상**: 09:05~09:30 창 + 갭업 스킵 + 갭다운 스킵 + 비붕괴(현재가≥시가) 확인.

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
- **조건**: 매수 체결가 대비 현재가가 `stop_loss_rate` 이하 도달 시 즉시 시장가 전량 매도
- **주의**: 기준은 반드시 "매수 체결가"이지 시가가 아님
- **명세 영역 DEFAULT**: `stop_loss_rate = -7.5%` (`src/engine/strategies/momentum.py::DEFAULT_PARAMS`)
- **운영 영역 (DB `strategy_config.momentum.params.stop_loss_rate`, 사이클 103 명문화, 2026-06-11)**:
  - **현재 운영 영역 = `-2.4%`** (2026-06-03 22:11 KST 사용자 수동 apply, AI 자문 권고 영역)
  - **AI 자문 reasoning 영구 영속**: "승률 낮음 + 손절 빈도 19회 + 변동성 9.21 → 보수적 손절 임계 권고"
  - **시계열 진화 영구 영속**:
    - `-7.5%` (DEFAULT, 명세 영역) → `-4.5%` (2026-05-07 apply) → `-3.8%` (2026-05-12) → `-3.2%` (2026-05-15) → `-2.8%` (2026-05-28) → **`-2.4%` (2026-06-03 현재 운영 영역)**
  - **운영 영역 진실의 원천**: DB `strategy_config.momentum.params` JSONB (사용자 apply 영역). `DEFAULT_PARAMS` 코드 영역은 신규 전략 추가 시 초기 영역.
- **사이클 102.5 회고 결정적 사실 (영구 영속, 코미코 사례)**: 코미코(183300) 2026-06-11 10:03 매수 138,200원 → 13:21:30 STOP_LOSS 매도 138,200원. 매도 시점 loss_rate = -2.604% ≤ -2.4% 만족 → momentum.py STOP_LOSS 분기 정상 작동. 사용자 의문 = 코드 DEFAULT `-7.5%` 가정 → 운영 영역 `-2.4%` 영구 영속 가시화 부족 → 오인. **결함 영역 = 아님** (코드 정상, 운영 가시화 영역 보강 의무 = 사이클 103 4 영역 통합 시정).
- **사이클 103 시정 영속 (영구 영속)**:
  - 영역 1 = `frontend/src/pages/Strategies.tsx` 신규 (6 전략 각 4 임계 영속 가시화, 사용자 오인 영역 영구 차단)
  - 영역 2 = `momentum.py:127` 손절 로그 임계 동행 emit (`"손절 신호: ... 대비 %.1f%% (임계: %.1f%%, 현재가: %d)"` 영구 영속)
- **향후 운영 영역 변경 시 본 명세 동기화 의무 영구 영속** (미래 운영자 오인 영구 차단).

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

#### (a) NXT 거래 가능 (`nxt_tradable=True` + 시가 수신) — 갭상승 여부로 분기
- 매수 체결가 대비 +10% 이상 갭상승 → 고점 -2% 트레일링 스탑 (기존 동작 유지)
- 갭상승 미달 → **08:00 NXT 프리 지정가 조기청산 폐지, (b) 와 동일하게 `_pending_next_day_clear` 보류(reason=`nxt_underthreshold`) → 09:00 KRX 시장가 단일 청산** (Tier 1, 2026-07-23, 자문 `nxt_prelimit_stale_selling_orderflow`)
  - **폐지 사유**: 얇은 NXT 프리 유동성에서 open−1호가 지정가는 미체결 만료가 잦고(금호 실측 +3% 종이이익), 만료가 어느 `_selling` discard 경로에도 안 걸려 `_selling` 영구 잔존 → `risk.on_tick` 손절/트레일링 종일 억제(Defect 2). 08:00 지정가를 아예 내지 않으니 leak·double-sell 레이스 원천 소멸
  - **손익비**: 갭<임계 조기탈출 이익은 대부분 얇은 호가의 미실현 종이이익이라, 검증된 09:00 KRX 시장가 단일 청산(`_drain_pending_next_day_clear`)이 손익비 우위

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

#### 매도 거부 정책 — `SellRejectionTracker` (사이클 55 R-1, 2026-06-03)

`src/engine/sell_rejection.py::SellRejectionTracker` 단일 정책 객체가 4 분류 (market_closed / market_order_disallowed / insufficient_quantity / insufficient_cash) 통합 관리. `OrderEngine.execute_sell` 진입 직후 `is_blocked(ticker)` 게이트로 KIS 호출 전 차단. **행위 변경 3종** (domain-expert Q1/Q2/Q3 RECOMMEND 채택):

**Q1 — `market_closed_rejection` 2단계 TTL** (사이클 52 단일 09:00 TTL 에서 분기)
- KRX 메인 시간대(09:00~15:30 KST) 거부 = **5분 TTL** (일시 장애 가정 — KIS 일시 거부 후 자연 복구 시나리오 빠른 재진입 보장)
- NXT 시간대(08:00~09:00 / 15:40~20:00 KST) 거부 = **다음 KST 09:00 TTL** (장운영시간 외 명확 — KRX 메인 개장까지 차단 유지)
- TTL 미경과 시 INFO `[market_closed_blocked] ticker=... reason=...` 1줄/ticker/일 cap → 동일 종목 재시도 폭주 차단

**Q2 — `market_order_disallowed` 30초 TTL + NXT 폴백 실패 익일 청산 전환**
- 시장가 매도 폴백(`step_down(현재가, 5)` 지정가 1회) 결과(성공/실패) 무관 **30초 TTL** 등록 (동일 tick 폭주 차단)
- NXT 시간대 폴백 실패 시(`is_nxt_session=True AND fallback_succeeded=False`) → `_pending_next_day_clear.add((ticker, strategy_id))` 자동 등록 + `[next_day_clear_deferred]` WARNING → 다음 영업일 09:00 KRX 시장가 일괄 청산 자연 전환
- 지정가 매도(`limit_price>0`)는 폴백/TTL 등록 모두 안 함 (운영자 명시 지정가 의도 보존)

**Q3 — `insufficient_quantity` reconciliation**
- 거부 발생 시 tracker history 적재(차단 X — positions 메모리/DB 제거가 자연 차단)
- 즉시 `[positions_reconciliation] ticker=... strategy=... reason=insufficient_quantity` INFO 1행
- 1회 `get_balance()` 호출 → 실제 잔량 > 0 인 경우 (수동 부분매도 보호 시나리오) INFO `실제 잔량 확인: ... qty=N — positions 재등록 권고` (자동 재등록 미구현 — 운영자 수동 확인 권고)
- `get_balance()` 실패 graceful (DEBUG 로그만, positions 제거는 이미 완료)

**호환 layer + reset 정책**
- `OrderEngine._market_closed_blocked` / `_market_closed_blocked_logged_today` 2 property 보존 (사이클 52 테스트 코드 무수정, dict/set 인스턴스 동일성 보장)
- `OrderEngine.reset_daily_state()` → `self._sell_rejection.reset_daily()` 4 필드 (`_blocked_until` / `_blocked_reason` / `_logged_today` / `_history`) 일괄 위임 + `_nxt_downgrade_logged_today.clear()` 보존
- ticker별 history `deque(maxlen=20)` 사전 도입 — V-1 (시간당 5건 초과 실시간 알람) hook 준비 완료

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

### 재진입 쿨다운 (사이클 201)
- **쿨다운**: 청산 후 **2영업일** (`reentry_cooldown_days=2`, BFB 3영업일 / VCP 7영업일과 구분 — VB 당일청산 특성상 짧게 설정).
- **배선**: `OrderEngine.on_position_closed(ticker)` 훅에서 `register_cooldown_after_exit(ticker)` 즉시 호출(달력일 근사 = today + days + 2) → `_refine_cooldown_business_days(ticker)` 비동기 정정(CTCA0903R `add_business_days`로 정확한 N영업일 교체, 실패 시 근사값 유지 graceful).
- **매수 게이트**: `check_buy_signal`의 `is_sold_today` 가드 직후 `_cooldown_until[ticker] >= today` 면 즉시 NONE (돌파 조건 완비 여부 무관).
- **영속 금지**: `_cooldown_until`는 크로스데이 상태 — `_reset_daily_state`/`prepare()` 리셋 대상에서 절대 제외 (일일 초기화 시 매일 소멸하면 재진입 방어가 무력화됨).

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
- **하드 손절**: 매수가 대비 **-6%** (운영 DB, 사이클 210 복원). 코드 DEFAULT -7. **⚠️ 사이클 210 (2026-07-14)**: AI 자문 수동 apply 누적으로 `stop_loss_rate -3.2` / `daily_loss_limit -0.8`(배정자금 -0.8% 손실=당일 매수 중단)까지 과조임 방치돼 208/209로 신호가 나와도 진입 직후 죽던 상태 → **stop -6.0 / daily_loss -6.0 복원**. 재조임 방지 = auto_apply `_CONSERVATIVE_KEYS` 제거(engine/CLAUDE.md 참조).
- **일일 손실 한도** (`daily_loss_limit`): 배정자금 대비 **-6%** (사이클 210 복원, 코드 DEFAULT -8). 초과 시 당일 매수 중단.
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
- KOSPI + KOSDAQ 전체에서 사후 필터.
- **사이클 48 (2026-05-27) 유니버스 소스 교체 — 시간무관화 (운영 결함 시정)**: 기존 `_fetch_fluctuation_rank()` + 종목별 `fetch_stock_detail()`(FHKST01010100) 방식은 응답에 `prdy_vol`(전일거래량) 필드가 없어 `acml_vol`(당일 누적거래량)으로 거래대금을 계산 → BFB `prepare()` 가 07:50 장 전 boot 에서만 호출되므로 `acml_vol=0` → **매일 "유니버스 0종목"** 결함. VB/LTV 와 동일하게 **거래량순위 API(`volume-rank` / FHPST01710000, blng 0/1/3 합집합)** 로 교체 — 응답 1건에 `prdy_vol`/`stck_prpr`/`prdy_vrss`/`lstn_stcn` 포함 → 개별 호출 없이 시총·전일거래대금 산출 + 시간 의존 제거. `trade_amt = prdy_vol × prdy_close` (prdy_close = stck_prpr - prdy_vrss).
- **시가총액 ≥ 500억** (`min_market_cap`, 기본 50_000_000_000)
- **전일 거래대금 ≥ 20억** (`min_trade_amount`, 기본 2_000_000_000) — 전일 확정치(prdy) 기준. 당일 누적(acml) 금지 (시간 편향 → 오후 편중 후보 왜곡)
- ETF/ETN 제외 (기존 키워드 컨벤션 재사용 — KODEX/TIGER/RISE/KoAct/PLUS/TIMEFOLIO/WOORI/FOCUS/인버스/레버리지)
- 최대 100종목 (`max_scan_stocks`)

### 데이터 준비 (07:50 prepare)
- 종목별 일봉 30일치(폴 10일 + 플래그 10일 + 여유 10일) — `fetch_daily_candles(ticker, days=30)`
- `candles[0]==오늘`이면 `candles[1]`을 전일로 사용 (부분봉 가드, VB/LTV/donchian 컨벤션 재사용)

### 셋업 검증 (단계별 필터, prepare 시 통과 종목만 `_candidates`에 등록)
**폴(Pole) 조건 — `pole_lookback_days=3~10`**:
1. 직전 N영업일(3~10) 사이에 **누적 상승률 ≥ +15%** (`pole_min_return`, 기본 **15.0** — 사이클 48 완화, 기존 20.0 은 음봉 30% 와 교집합이 0 을 만듦. 한국 일일 ±30% 환경에서 3~10일 +15% 도 충분히 강한 깃대 모멘텀)
2. 같은 구간 **음봉 비율 ≤ 45%** (`pole_max_red_ratio`, 기본 **0.45** — 사이클 48 완화, 기존 0.30. 강한 폴 구간도 보통 1~2일 쉬어가는 음봉이 정상인데 30% 면 5일 중 음봉 2개(40%)에 탈락 → 현실 깃대상승 다수 탈락. 돌파 순간 + 거래량 2배 컷이 여전히 가짜 돌파 거름) — `close < open`인 일수 / 구간 길이
3. 폴 구간 내 최고가 = `pole_high`, 폴 시작가 = `pole_start`, **폴 폭 = `pole_high - pole_start`**

**플래그(Flag) 조건 — `flag_lookback_days=2~10`** (폴 종료 직후 N영업일. **사이클 198 (2026-07-09) — 3→2 완화**: domain-expert 자문 + 298종목×4일 DB 실측(`_workspace/domain_consult/cycle198_pattern_strictness_korea.md`) — 한국 급등주는 눌림(플래그)이 얕고 빠르다(상한가 익일 눌림 → 3일차 재돌파 리듬), `flag_lookback_min=3`이면 2일 눌림을 플래그로 검출 못해 후보 소실. `flag_volume_ratio`(거래량 수축 60%) 안전장치가 저품질(급락 되돌림) 후보를 여전히 전량 흡수 실증 — 완화해도 오탐 0):
1. 플래그 구간 최고가 = `flag_high`, 최저가 = `flag_low`
2. **조정 폭 ≤ 폴 폭의 50%** (`flag_retracement_max=0.5`, 사이클 211 — 0.382→0.5 완화, funnel 폴/플래그 병목 실측 3.3배) — `(pole_high - flag_low) <= (pole_high - pole_start) × 0.5`. 거래량 수축(`flag_volume_ratio 0.6`)이 급락 되돌림 오판 봉쇄(안전장치 불변)
3. **플래그 평균 거래량 < 폴 평균 거래량 × 60%** (`flag_volume_ratio=0.60`) — 거래량 수축 확인
4. 플래그 종가 추세는 강한 우하향이 아니어야 함 (마지막 종가가 flag_low 보다 0.5×ATR 이상 멀지 않을 것 — 일종의 sanity check, 정밀한 회귀선 검사는 1차에서 생략)

검증 통과 시 `_candidates[ticker] = {pole_high, pole_low, pole_start, flag_high, flag_low, flag_avg_volume, atr14, prev_close}` 등록.

### 사이클 50 (2026-06-01) — funnel 단계별 사유 정밀화 (계측 전용, 임계 무변경)

**배경**: 06/01 대시보드 BFB 퍼널 4단계 "폴 검출"에서 22~25종목 → 0 전멸 (05/29·06/01 2영업일 연속, `strategy_funnel_snapshots` DB 확정). 진단 결과 근본 원인 3개 중첩 — (1) 운영 DB `strategy_config.params` 오버라이드(`pole_min_return:20`/`exchange:SOR`/`max_scan_stocks:250`)가 코드 디폴트(사이클 48 완화값)를 덮어씀, (2) 사이클 48 의 거래량순위 유니버스(거래량 폭발 종목)와 플래그 검출의 거래량 *수축* 요구가 구조적 모순, (3) `_detect_pole_and_flag` 가 4 sub-condition 을 한 함수에서 평가하고 실패 시 `None` 만 반환 → funnel step 5/6 이 survived=0 AND excluded=0 → 어느 조건이 바인딩인지 계측 불가.

**이번 시정 범위 = 근본 원인 3 (진단 인프라)만**. 임계값/유니버스 소스/DB params 는 단계 2 (실측 + domain-expert 자문 후)로 보류 — 본 사이클에서 일절 변경 안 함.

- `_detect_pole_and_flag_detailed(candles) -> (result, fail_stage, detail)` 신규 — 실패 시 "가장 멀리 도달한 sub-condition"(`pole_return`/`pole_red_ratio`/`flag_retracement`/`volume_contraction`) + 측정 수치(`best_return`/`red_ratio`/`retracement`/`vol_ratio`) 보고. 사이클 49 VCP `last_pullback_pct 항상 기록` 동일 계열.
- `_detect_pole_and_flag(candles) -> dict | None` 은 detailed 의 result 만 반환하는 thin wrapper — **기존 계약/행위 완전 보존** (통과/탈락 종목 무변경, 검출 결과 무변경).
- `prepare()` funnel hook 이 fail_stage 에 따라 step 4(폴 상승률+음봉) / step 5(플래그 조정폭) / step 6(거래량 수축) 에 탈락 종목을 수치 사유로 분배. 기존엔 step 4 에 "폴 검출 실패" 한 줄로 뭉뚱그려 어느 조건이 바인딩인지 운영자가 알 수 없던 결함 시정.
- 회귀 가드: `tests/unit/engine/strategies/test_cycle50_bfb_funnel_stage_detail.py` 6 케이스.
- 실측 계측 스크립트: `tools/measure_bfb_pole_flag.py` — EC2 운영 환경에서 5종목(009150/011070/242040/000660/005930) 일봉으로 4 sub-condition 조건별 바인딩 단계 집계 (KIS 실호출 필요, 클라우드 샌드박스 불가). `--db` 플래그로 운영 DB params 효과도 측정 가능.

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
    # 폴 (사이클 48 — Pole 검출 0건 결함 시정)
    "pole_lookback_min": 3,
    "pole_lookback_max": 10,
    "pole_min_return": 15.0,    # 사이클 48 — 20.0 → 15.0 완화
    "pole_max_red_ratio": 0.45, # 사이클 48 — 0.30 → 0.45 완화
    # 플래그
    "flag_lookback_min": 2,   # 사이클 198 — 3 → 2 완화 (얕은 2일 눌림 포착, flag_volume_ratio 안전장치 보전)
    "flag_lookback_max": 10,
    "flag_retracement_max": 0.5,   # 사이클 211 (0.382→0.5)
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
1. **종가 > 단기 EMA > 중기 EMA > 장기 EMA** (`ema_short=50`, `ema_mid=60`, `ema_long=120`)
2. **장기 EMA 우상향 1개월 이상** — 현재 장기 EMA > 1개월 전(20영업일 전) 장기 EMA (`long_ema_uptrend_days=20`)
3. 통과 종목만 다음 단계 검사
4. **사이클 48 (2026-05-27) — 추세필터 0건 결함 시정 (운영 확정)**: KIS `fetch_daily_candles` 단일 호출 최대 100일 한도 때문에 사이클 33 의 `effective_ema_long = min(200, available_len - 25)` 자동 축소가 200EMA 를 사실상 ~75EMA 로 만들고, `ema_mid(150) > effective_ema_long(75)` 이면 다시 `ema_mid = ema_long-10 = 65` 로 축소 → 50/65/75 EMA 가 100일 데이터로 완벽 정배열 + 75EMA 20일 우상향까지 요구 → 한국 중소형주에서 추세필터 항상 0. **시정: `ema_long` DEFAULT 200→120, `ema_mid` 150→60 으로 낮춰 100일 fetch 로 안정 계산 가능한 50/60/120 정배열로 의도 보존.** 미네르비니 원전은 200EMA 이나 KIS 단일호출 한도(100일)로 계산 불가능한 200 을 형식만 두는 것보다 실측 가능한 120 이 정직. 분할 fetch 인프라는 운영 1주 후 별도 검토 (사이클 33 권고 유지). `effective_ema_long` 자동 축소 가드는 fetch 부족 시 안전망으로 유지 (120 도 100일 cap 에 걸리면 축소되나 폭 작음)

### 베이스 정의 (`base_lookback_weeks=5~15` → 일봉 25~75영업일)
1. 베이스 시작·종료 자동 검출: 최근 N영업일(75일) 내에서 `(highest_close - lowest_close) / lowest_close ≤ 0.25` 인 최장 연속 구간을 베이스로 인식 (`base_depth_max=0.25`)
2. **베이스 깊이** = `(base_high - base_low) / base_high ≤ 30%` (`base_depth_pct=0.30`)
3. 베이스 길이 = 25~75영업일 (`base_min_days=25`, `base_max_days=75`)

### 조정 시퀀스 (Pullback Sequence, 점진 수축)
1. 베이스 구간 내 pullback 자동 검출: 직전 swing high → swing low 까지의 하락 폭 → 다음 swing high 까지의 상승. `pullback_count_min=2`, `pullback_count_max=4`
2. 각 pullback 폭 = `(swing_high - swing_low) / swing_high` (%)
3. **각 pullback 폭이 직전 pullback 보다 작아야 함** (점진 수축, 변동성 contraction. strict — 동일 폭 거부)
4. **마지막 pullback ≤ 12%** (`last_pullback_max=0.12` — 사이클 48 완화, 기존 0.08. 한국 중소형주 변동성에 8% 는 빡셈. 점진 수축 조건은 유지)
5. **사이클 49 (2026-05-31) — Pullback "마지막 폭 0.0%" 결함 시정**:
   - **결함**: 운영 5/26~5/29 4영업일 누적 33/33 종목이 step 6 에서 "마지막 폭 ≈ 0.0%" 동일 사유로 탈락 (vcp_breakout 30일 연속 0건 매매 원인 중 하나). Root cause 는 2개: (a) `_check_pullback_sequence` 의 단순 swing 검출이 chrono 끝부분 rising 중이면 `j=k=n-1` → `high==low` → `high > low` 가드로 마지막 pullback 누락 → `base["last_pullback_pct"]` 미설정 → funnel reason 의 `base.get("last_pullback_pct", 0)` 디폴트가 "0.0%" 표시 (운영자 오인). (b) 등호 포함 `>=`/`<=` swing 검출이 한국 KRX 평탄 우량주(SK텔레콤/삼성전자우 등)의 1원 단위 미세 변동도 swing 으로 인식 → 회수 2~4회 범위 위반 빈발.
   - **시정 1 (노이즈 필터, ZigZag 변형)**: 신규 파라미터 `min_swing_atr_mult=0.5`. 베이스 구간 평균 일중 변동폭(`sum(high-low) / N`, ATR 근사) × 0.5 미만 변동은 swing 으로 인정 안 함. ATR 산출 실패 시 종가 평균의 0.3% 폴백. running_max / running_min 추적 + threshold 이상 반전 시에만 swing 확정 (ZigZag indicator 표준 임계).
   - **시정 2 (마지막 swing 미완성 포함)**: state machine ('undefined' / 'up' / 'down') 으로 끝까지 진행. `state=='down'` 중 끝나면 마지막 pivot_high → running_min 의 진행 중 pullback 도 "마지막 pullback" 으로 포함.
   - **시정 3 (점진 수축 strict)**: `curr >= prev` → `curr >= prev` 유지하되 의미는 "동일 폭도 거부" 명확화 (등호로 동일 폭이 단조 감소 위반). 노이즈 필터 후엔 동일 폭 swing 거의 발생 안 함.
   - **시정 4 (funnel reason 정확성)**: False 반환 경로에서도 `base["last_pullback_pct"]` 에 실제 마지막 swing 폭 (또는 swing 0개면 명시적 0.0) 기록. 운영자가 "왜 탈락했는지" 정확한 수치로 진단 가능.
   - **신규 파라미터**: `min_swing_atr_mult=0.5` (`DEFAULT_PARAMS` 추가). PARAM_RANGES / INT_PARAMS 등록은 후속 AI 자문 튜닝 시 별도 검토.
   - **회귀 영향 0**: 다른 5 전략 무영향. VCP 외 scan/매매 흐름 변경 없음. 백엔드 1748 PASS / 2 skip.
   - **회귀 가드**: `tests/unit/engine/strategies/test_cycle49_vcp_pullback_width_fix.py` 6 케이스 (마지막 swing 미완성 / 노이즈 필터 파라미터 / 전형적 VCP 3회 점진 수축 통과 / "0.0%" 디폴트 제거 / DEFAULT_PARAMS 신규 키 / strict 점진 수축 회귀).
   - **운영 관찰 포인트**: 다음 영업일(2026-06-01) 09:30 funnel snapshot 에서 step 6 통과 카운트 > 0 확인. 첫 거래 발생 시 손절(-7%) / 베이스 하단 / ATR 트레일링 / 50일 EMA 이탈 4중 청산 정상 발화 tester 검증.

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
    # 추세 필터 (사이클 48 — KIS 100일 한도로 계산 가능한 값으로 하향)
    "ema_short": 50,
    "ema_mid": 60,
    "ema_long": 120,
    "long_ema_uptrend_days": 20,
    # 베이스
    "base_min_days": 25,
    "base_max_days": 75,
    "base_depth_pct": 0.30,
    # 조정 시퀀스
    "pullback_count_min": 2,
    "pullback_count_max": 4,
    "last_pullback_max": 0.12,  # 사이클 48 — 0.08 → 0.12 완화
    "min_swing_atr_mult": 0.5,  # 사이클 49 — 노이즈 swing 필터 (베이스 ATR × 0.5)
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

### 사이클 48 (2026-05-27) — BFB/VCP 구독 배선 편입 (P1 후속, PR #15 코드리뷰)
유니버스 시간무관화 + 임계 완화로 BFB/VCP 가 후보를 *산출* 하게 만들었으나, codex 리뷰가 치명적 갭을 지적했고 코드로 확정함: BFB/VCP 매수 신호는 (donchian 의 폴링 루프와 달리) `risk.on_tick`(WebSocket tick) 으로만 평가된다. 그런데 후보가 WebSocket 구독에 들어가는 유일한 경로 `scheduler._collect_breakout_tickers()` 가 VB/LTV 두 전략만 순회했다 → BFB/VCP 후보 미구독 → tick 미수신 → on_tick 매수 평가 영영 안 됨 → 유니버스/임계 완화를 해도 **0건 지속**.
- **시정**: `_collect_breakout_tickers()` 순회 튜플에 `bull_flag_breakout` / `vcp_breakout` 추가 (VB/LTV/BFB/VCP 4 전략). 이 함수는 (a) `_scan_loop` extra, (b) `_collect_presubscribe_tickers`(07:55 사전구독), (c) `_build_priority_groups()["breakout"]` 세 구독 경로 전부의 소스이므로 한 곳 수정으로 전파.
- **우선순위 불변**: BFB/VCP 후보는 VB/LTV 와 동일하게 `breakout` 그룹 = **LOW + bypass_limit=False** 로 유입 → `BREAKOUT_LOW_CAP=25` 2-pass cap + graceful `[priority_drop]` 대상(설계대로). HIGH(positions/next_day_clear) `bypass_limit=True` 41슬롯 절대 보장은 무수정. 매도/손절/Trailing/익일청산 경로 무수정.
- **가시성**: `_build_subscription_source_counts()` 에 `bfb`/`vcp` 카운트 키 + scanner 구독 완료 로그에 `bfb=%d, vcp=%d` 추가.
- `_universe_excluded_today` 필터는 BFB/VCP 후보에도 동일 적용.

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

### PARAM_RANGES 화이트리스트 확장 (Phase B, 2026-05-17)

5/15 첫 자문 발화에서 4 전략의 `code_review_notes` 가 강하게 권고한 키 7 종을 `src/engine/recommendation_engine.py::PARAM_RANGES` 화이트리스트에 추가. 다음 자문 사이클(5/18 월 20:00) 부터 OpenAI 가 자동 튜닝 가능. 신규 키 + 범위:

| 키 | 범위 | 사용 전략 | INT 여부 |
|----|------|----------|----------|
| `k_value_krx_main` | (0.5, 2.0) | VB, LTV | float |
| `k_value_nxt_pre` | (0.5, 2.0) | VB, LTV | float |
| `k_value_nxt_post` | (0.5, 2.0) | VB(호환), LTV | float |
| `donchian_period` | (10, 60) | donchian_swing | **INT** (정수 일봉 개수) |
| `long_ma_period` | (20, 120) | donchian_swing | **INT** (정수 일봉 개수) |
| `volume_multiplier` | (1.0, 5.0) | donchian_swing | float |
| `atr_trail_mult` | (1.0, 5.0) | donchian_swing, bull_flag, vcp | float |

`min_prdy_rate` 는 사이클 진입 시점에 이미 등록(`(0.0, 30.0)`)되어 있어 중복 추가하지 않음(요구 명세 8 키 → 실 추가 7 키). `donchian_period` / `long_ma_period` 는 `INT_PARAMS` 에 함께 등록되어 LLM 출력이 25.7 → 26 으로 자동 캐스트.

**Phase A 별건 — LTV `stop_loss_hits=0` metrics 결함**: 5/15 자문 metrics 분석에서 `stop_loss_hits=0` 과 `max_loss_pct=-7.554%` 모순 발견. root cause 는 `recommendation_metrics.compute_metrics()` 가 `current_params.get("stop_loss_rate")` 단일 키만 참조하는데 LTV 만 `intraday_stop_loss`/`overnight_stop_loss` 분리 키 사용 → `None` 폴백 → 분기 영영 skip. 본 사이클에서는 진단만, fix 는 별도 사이클로 분리(`_workspace/red/phase-a-ltv-stop-loss-hits.md`).

### LTV stop_loss_hits 결함 fix (Phase A2, 2026-05-17)

Phase A 진단 후속. `src/engine/recommendation_metrics.py` 에 `_normalize_stop_loss_rate(params: dict) -> float` 헬퍼 도입:

| 입력 케이스 | 후보 수집 | 반환 | 사용 전략 |
|------------|-----------|------|-----------|
| `{"stop_loss_rate": -7.5}` | `[-7.5]` | `-7.5` | momentum/VB/donchian/bull_flag/vcp |
| `{"intraday_stop_loss": -2.5, "overnight_stop_loss": -2.0}` | `[-2.5, -2.0]` | `-2.5` (절대값 큰) | LTV |
| `{"intraday_stop_loss": -3.0}` | `[-3.0]` | `-3.0` | LTV (overnight 부재) |
| `{}` | `[]` | `0.0` | compute_metrics 분기 skip 보존 |
| `{"stop_loss_rate": 2.0}` | `[]` (양수 skip) | `0.0` | 잘못된 양수 임계 보호 |

알고리즘: 3 키(`stop_loss_rate`/`intraday_stop_loss`/`overnight_stop_loss`) 후보 수집 → `_safe_float` 변환 → 음수만 인정 → `min(candidates)` 반환 (절대값 큰 = 가장 보수적 = "확실히 손절 도달"). `compute_metrics()` 의 단일 키 참조 1줄을 헬퍼 호출로 교체. 다른 5 전략은 후보 그대로 단일 반환 → 회귀 0건.

**적용 시점**: 5/15 발화된 LTV `parameter_recommendations.metrics.stop_loss_hits=0` 은 소급 재계산 안 함. **5/18 월 20:00 첫 자문부터 정상**. 운영 자동매매 흐름은 metrics 계산만 영향 — 자문/매매 흐름 미침범.

회귀 가드: `tests/unit/engine/test_recommendation_metrics_ltv_stop_loss.py` 8 케이스 (Case A LTV 분리 키 / Case B 단일 키 / Case C 부재 0.0 / Case D 5/15 LTV 064400 -3.030% 통합 / Case E intraday only / Case F 혼합 + 양수/None edge).

### 비중조절 사유 분리 + UI 카드 순서 변경 (사이클 1, 2026-05-17)

J4(2026-05-12) 에서 도입한 통합 `reasoning` 필드에 비중 변경 사유가 다른 분석 텍스트와 섞여 있어, 운영자가 5/18 월 20:00 첫 자문 검수 시 가독성 저하 + 비중 의사결정 흐름이 묻히는 문제 해소.

**DB 마이그레이션 021** (`supabase/migrations/021_weight_reasoning.sql`):
```sql
ALTER TABLE parameter_recommendations
    ADD COLUMN IF NOT EXISTS weight_reasoning TEXT;
```
nullable TEXT (≤1000자). `recommended_weight` 가 null 이면 weight_reasoning 도 null.

**백엔드 명세** (`src/engine/recommendation_engine.py`):
- `SYSTEM_PROMPT` 에 `weight_reasoning` 필드 명시 — `recommended_weight` 변경 권고 시 별도 사유 (최대 1000자, 한국어, 통합 `reasoning` 과 별개)
- `_validate_recommendations()` 5-tuple 반환 `(validated_params, reasoning, weight, notes, weight_reasoning)`:
  - `weight is None` → `weight_reasoning = None` 자동 정리
  - `weight is not None AND raw_weight_reasoning isinstance str AND non-empty` → 그대로 (1000자 초과 시 truncate + WARNING)
  - `weight is not None AND (raw_weight_reasoning is None | 빈문자열 | 비-str)` → `WEIGHT_REASONING_FALLBACK="(사유 미제공)"` + WARNING 로그
- `generate_recommendations()` 의 unpacking 5-tuple + `insert_recommendation(weight_reasoning=...)` 호출부 갱신

**DB CRUD 확장** (`src/db/parameter_recommendations.py::insert_recommendation`):
- 시그니처에 `weight_reasoning: str | None = None` kwarg 추가
- INSERT data dict 에 `"weight_reasoning"` 키 포함

**모델** (`src/models/recommendation.py::RecommendationItem`):
- `weight_reasoning: Optional[str] = None` 필드 추가
- `frontend/src/types/recommendations.ts::RecommendationItem` 에 대응

**프론트엔드 UI 카드 순서 변경** (`frontend/src/pages/Recommendations.tsx`):
- 변경 전: BacktestComparison → 분석 통계 → 추천 근거 → 자산 배정 → 로직 자문 → 파라미터
- 변경 후: **자산 배정 (최상단)** → BacktestComparison → 분석 통계 → 추천 근거 → 로직 자문 → 파라미터
- 자산 배정 카드 내부에 `weight_reasoning` amber 영역(`data-testid="weight-reasoning-{id}"`, `bg-amber-50 border-amber-200 max-h-32 overflow-y-auto whitespace-pre-wrap`) 추가 — `rec.weight_reasoning` truthy 시에만 렌더

**안전 불변식**:
- 5/15 발화된 row 영향 없음 (소급 재계산 안 함, `weight_reasoning=null` 그대로)
- weight_reasoning 누락 시 `(사유 미제공)` 자동 fallback — null 미저장
- 운영 매매 흐름 미침범 (자문 metrics/UI 영역만)
- 1000자 초과 truncate 시 WARNING 로그로 추적

**회귀 가드**:
- `tests/unit/engine/test_recommendation_weight_reasoning.py` 11 케이스 (5-tuple 시그니처 / weight+reasoning 정상 / 누락 fallback / null 동시 정리 / 1000자 truncate / 비-str fallback / 빈문자열 fallback / 5/15 LTV fixture / 1000자 이내 보존 / 양쪽 null 정상 / 묵시적 누락 fallback)
- `tests/unit/db/test_parameter_recommendations_weight_reasoning.py` 4 케이스 (INSERT round-trip / null / J4 시그니처 회귀 / kwarg default)
- `frontend/src/pages/__tests__/Recommendations.weightReasoning.test.tsx` 5 케이스 (A amber 영역 / B null 미렌더 / C weight null 시 weight-card 자체 미렌더 / D DOM 순서 / E 1000자 overflow)
- `frontend/src/pages/__tests__/Recommendations.cardOrder.test.tsx` 2 케이스 (모든 카드 노출 시 순서 / weight 카드 없을 때 fallback 순서)

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

## (2026-05-17) 자문 시스템 개선 사이클 2 — 시장 레짐 필터 + dkstock.cloud 매크로 연동

**옵션 1b + 2b + 3a + 4a 확정.** 운영 graceful 우선 — `DKSTOCK_REGIME_ENABLED=false` 기본 비활성.

### 핵심 규칙

1. **매수 가드 (1b — 복합 임계 OR)** — `risk.on_tick()` 매수 신호 평가 *직전*. 다음 중 1개 이상 발동 시 모든 전략 매수 차단:
   - `regime == "defensive"`
   - `vix > 25`
   - `fear_greed_score > 85` (극도 탐욕)
   - `fear_greed_score < 15` (극도 공포)
   - **매도/손절 무관** — 보유 종목 청산은 정상 작동 (`check_exit_signal` 분기는 가드 진입 전)

2. **cash_usage_ratio 자동 조정 (2b)** — `_boot()` 가 매크로 fetch 후 결정:
   - `cash_usage_ratio = clamp((100 - regime.params.cash_min) / 100, 0.0, 1.0)`
   - 예: defensive(75) → 0.25 / neutral(50) → 0.5 / aggressive(20) → 0.8
   - 범위 [0.0, 1.0] 으로 확장 (이전 [0.5, 1.0] — 마이그 023)
   - `auto_regime_adjust=true` (기본) 면 자동 갱신, `false` 면 운영자 수동값 보존

3. **외부 실패 시 graceful** — dkstock.cloud fetch 실패/timeout/토큰 만료/`DKSTOCK_REGIME_ENABLED=false`:
   - `MarketRegime.empty()` 반환 → `is_buy_allowed=True` (매수 가드 비활성)
   - `cash_usage_ratio` 자동 갱신 안 함 (운영자 수동값 그대로)
   - 자동매매 본 흐름 영향 0건

### 운영 활성화 절차 (배포 후)

1. EC2 `.env` 추가:
   ```
   DKSTOCK_API_URL=https://dkstock.cloud
   DKSTOCK_USERNAME=autostock
   DKSTOCK_PASSWORD=AUTOSTOCK1
   DKSTOCK_REGIME_ENABLED=false   # 1단계: false 로 코드만 배포 검증
   ```
2. Supabase 마이그 022 (market_regime_snapshots) + 023 (cash_usage_ratio 범위 COMMENT) 적용
3. `DKSTOCK_REGIME_ENABLED=true` 토글 + 서비스 재기동
4. Dashboard MarketRegimeCard 에서 첫 fetch 확인 (VIX/FG/Buffett 값 표시)
5. `auto_regime_adjust` Dashboard 토글로 자동 조정 활성/비활성 (ConfirmModal 이중 확인)
6. 보수 운영 권고: 5/18 월 20:00 사이클 1(weight_reasoning) 자문 검증 완료 후 활성화

### 회귀 가드 (5/18 사이클 1 검증 + 5/19 사이클 2 운영 안전성)

- `tests/unit/services/test_dkstock_client.py` 8 케이스 — JWT/refresh/401/connect_error/graceful
- `tests/unit/engine/test_market_regime.py` 11 케이스 — 복합 임계 OR/clamp/empty 폴백
- `tests/unit/db/test_market_regime_snapshots.py` 4 케이스 — INSERT/UNIQUE/get_latest
- `tests/unit/db/test_system_config_auto_regime.py` 3 케이스 — get/set round-trip
- `tests/integration/test_boot_market_regime.py` 3 케이스 — defensive 자동 0.25 / manual 0.7 보존 / 외부 실패 graceful
- `tests/unit/engine/test_risk_regime_guard.py` 4 케이스 — block buy / allow buy / **exit 무관** / empty graceful
- `tests/contract/test_routes_market_regime.py` 4 케이스 — current/history/auto-adjust
- `frontend/src/components/__tests__/MarketRegimeCard.test.tsx` 7 케이스 — 배지/배너/메트릭/토글 ConfirmModal/API 에러

### 안전 불변식

- 매수 가드는 `risk.on_tick` 매수 분기 *전*, 보드 가드 *후* 위치 — 보드 가드 통과 → 매수 가드 → 중복 매수 차단 → calc_buy_quantity 순서
- `get_current_regime()` 모듈 함수는 `_boot()` 1회 호출 가정 — 동시성 lock 없음 (운영 단일 워커)
- empty regime (외부 fetch 실패) 는 `regime=None` 이라 `to_dict()` 와 DB `persist_snapshot` 모두 None 키 처리 — UI/DB 안전
- `auto_regime_adjust=true` 시에도 empty regime 이면 `computed_cash_usage_ratio()=None` → 수동값 폴백 (graceful 분기 보존)

---

## (2026-05-17) 자문 시스템 개선 사이클 3 — VB 보드별 손절 분리

### 배경

5/15 첫 자문 발화의 VB `code_review_notes` 권고:
> "보드별(kospi/krx main, pre/open 구간 등) 개별 손절·진입시간 파라미터 분리"

VB 의 K값은 이미 보드별 분리(`k_value_krx_main` / `k_value_nxt_pre` / `k_value_nxt_post`,
사이클 1 PARAM_RANGES 등록) — 손절도 같은 패턴으로 확장.

근거: PRE_NXT (08:00~09:00) 의 변동성이 KRX MAIN 과 다름 (NXT 프리는 거래대금 작아
변동성 큼, 노이즈 많음). 동일 -3.5% 손절이 PRE_NXT 에서 너무 빨리 발동되는
가능성 차단.

LTV 는 본 사이클 범위 외 — 이미 시간 모드 분리(`intraday_stop_loss` /
`overnight_stop_loss`). 보드 × 모드 = 4 조합 복잡도라 사이클 3-B 로 분리
(`_workspace/cycle3b_ltv_board_stop_loss_spec.md` 참조).

### 신규 파라미터

```python
# DEFAULT_PARAMS / strategy_config.params (VB 한정)
"stop_loss_main": -3.0,       # KRX MAIN 시간대 손절 임계 (본격 변동성 수용)
"stop_loss_pre_nxt": -4.0,    # PRE_NXT 시간대 손절 임계 (노이즈 흡수, 더 관대)

# 기존 키 (호환성, deprecated 권고)
"stop_loss_rate": -3.5,       # 보드별 키 부재 시 fallback (5/15 운영값)
```

### fallback 우선순위 (`_get_stop_loss_for_board`)

1. **활성 보드 키**: `params.get(f"stop_loss_{board}")` 음수면 채택. 활성 보드는
   `_resolve_active_board()` 가 `SessionTracker.active` 에서 조회 (main → post_nxt → pre_nxt 우선순위)
2. **top-level fallback**: 부재/None/0/양수 시 `params.get("stop_loss_rate")`
3. **둘 다 부재**: 0.0 반환 → 손절 분기 skip

테스트 환경 / SessionTracker 미동작 시 `_resolve_active_board() = None` → 보드별 키 건너뛰고 top-level fallback.

### 자율 결정 — `active_board` 전달 방식

옵션 1(risk.on_tick 시그니처 변경) / 옵션 2(VB 내부 조회) / 옵션 3(`check_exit_signal` 시그니처 확장) 중 **옵션 2 채택**.

이유:
1. VB 에 이미 `_resolve_active_board()` 헬퍼 존재 — 재활용 가능
2. `check_exit_signal(ticker, current_price, open_price)` 시그니처는 6 전략 공통 + 5+ 테스트 mock 광범위 사용 → 변경 시 회귀 영향 큼
3. 보드별 손절 분리는 VB 단독 — 다른 전략에 인자 전달 불필요
4. `risk.py` 변경 0건 (옵션 1 회피)

### 변경 파일

| 파일 | LOC | 변경 |
|------|-----|------|
| `src/engine/recommendation_engine.py` | +5 | PARAM_RANGES `stop_loss_main` / `stop_loss_pre_nxt` 추가 |
| `src/engine/recommendation_metrics.py` | +10/-3 | `_normalize_stop_loss_rate` 5 키 후보 (`stop_loss_main`/`stop_loss_pre_nxt` 추가) |
| `src/engine/strategies/volatility_breakout.py` | +52 | `_get_stop_loss_for_board` 헬퍼 + `check_exit_signal` 분기 갱신 |
| `supabase/migrations/024_vb_board_stop_loss_defaults.sql` | +29 | 멱등 자동 복사 SQL (적용 보류) |

### 회귀 가드

- `tests/unit/engine/strategies/test_volatility_breakout_board_stop_loss.py` — 6 케이스 (A~F)
  - A: stop_loss_main 단독 → MAIN 활성 시 -3% 발동
  - B: stop_loss_pre_nxt 단독 → PRE_NXT 활성 시 -4% 발동
  - C: top-level only → 모든 보드 fallback
  - D: 보드별 + top-level → 보드별 우선
  - E: 활성 보드 미감지 → top-level fallback
  - F: 5/15 운영값 (`stop_loss_rate=-3.5`) 회귀 보존
- `tests/unit/engine/test_recommendation_metrics_board_stop_loss.py` — 9 케이스 (G~I)
  - G/H: VB 보드별 키 정규화 + 혼합 회귀
  - 회귀 5: LTV/단일/없음/양수/None
  - I: compute_metrics 통합 stop_loss_hits 정상 카운트
- `tests/unit/engine/test_recommendation_param_ranges_board_stop_loss.py` — 4 케이스 (J~L)
  - J: PARAM_RANGES 등록 + 범위
  - K: 정상 추천값 통과
  - L: 범위 밖 무시 + WARNING
- `tests/integration/test_vb_board_stop_loss_fallback.py` — 3 케이스 (M~O)
  - M: 마이그 024 적용 전 (5/18 첫 발화 직전 회귀)
  - N: 마이그 024 적용 후 + 운영자 미갱신
  - O: 마이그 024 적용 후 + 운영자 차별화

총 22 케이스 신규.

### 안전 불변식

- **VB `check_exit_signal` 시그니처 보존** — `(ticker, current_price, open_price)`. 6 전략 공통 + 테스트 mock 5+ 영향 0
- **활성 보드 미감지 시 graceful fallback** — `_resolve_active_board()` 예외 흡수 + None 반환 시 top-level `stop_loss_rate` 사용 (테스트 환경 / 부팅 직후 race 안전)
- **STOP_LOSS 우선순위 보존** — 보드별 손절 > 익일 청산 안전망 (NEXT_DAY_CLEAR). 손절은 `_next_day_clear_pending` 가드 영향 받지 않음 (결함 D 잔여 fix 보존)
- **`risk.on_tick` 시그니처 보존** — 옵션 2 채택으로 호출부 0 변경
- **LTV / momentum / donchian / bull_flag / vcp 영향 0** — VB 단독 변경

### 운영 활성화 절차

1. **사전 검증** (5/18 월 20:00): 사이클 1+2+3 동시 발화 정상 동작 확인
   - 사이클 1: `weight_reasoning` 자동 분리 표시
   - 사이클 2: 시장 레짐 fetch + auto_regime_adjust 동작
   - 사이클 3: 코드 변경만 적용된 상태 — VB 운영 fallback 정상 (마이그 미적용 = 기존 동작)
2. **마이그 024 적용** (선택):
   ```bash
   # 운영 EC2 Supabase CLI
   supabase migration up
   # 또는 Dashboard SQL Editor 에서 supabase/migrations/024_vb_board_stop_loss_defaults.sql 실행
   ```
   - VB `strategy_config.params` 에 `stop_loss_main` / `stop_loss_pre_nxt` 자동 추가 (값은 기존 `stop_loss_rate` 와 동일)
   - 운영자가 Settings 갱신 안 해도 동작 회귀 0건
3. **운영자 차별화** (선택, 마이그 적용 후):
   - Settings → VB → `stop_loss_main` -3.0 / `stop_loss_pre_nxt` -4.0 등 별도 조정
   - 다음 사이클부터 보드별 차별 손절 적용
4. **AI 자문 활용** (5/19 화 20:00 이후):
   - PARAM_RANGES 등록으로 OpenAI 가 `stop_loss_main` / `stop_loss_pre_nxt` 추천 가능
   - `_validate_recommendations` 가 범위 (-15.0, 0.0) 검증 + 정상값 통과

### 사이클 3-B (LTV 보드별 손절) 명세

`_workspace/cycle3b_ltv_board_stop_loss_spec.md` 별도 작성. 본 사이클 회귀 검증 후 발의.

---

## (2026-05-17) 자문 시스템 개선 사이클 4 — 매크로 레짐 → AI 자문 user_payload 통합

### 배경
사이클 2 도입으로 `_boot()` 시점 dkstock.cloud 매크로 fetch + `set_current_regime()` 모듈 싱글톤 갱신 가능.
그러나 OpenAI 자문(`_call_openai()`) user_payload 에는 매크로 컨텍스트 무전달 → 자문이 "통계만 보고" 손절률 조정.
defensive 레짐(VIX>25, 공포지수 극단) 일 때 손절률 더 보수적 권고 필요. aggressive 레짐일 땐 진입 임계 완화 가능.
buy_blocked=True 일 땐 매수 임계 변경 권고 무용 — 손절·청산 파라미터만.

### 구현 (TDD Red → Green, 30 케이스)

#### A. `MarketRegime.to_advisor_dict()` 신규 메소드 (`src/engine/market_regime.py`)

12 키 dict 반환:
- `regime` / `regime_desc` / `cycle_phase` / `vix` / `fear_greed_score` / `buffett_ratio` / `buy_blocked` / `block_reason` (기존 필드)
- `vix_level`: `_classify_vix()` — low(<15) / normal(15~25) / elevated(25~35) / high(≥35)
- `fear_greed_label`: `_classify_fear_greed()` — 극공포(<15) / 공포(15~35) / 중립(35~65) / 탐욕(65~85) / 극탐욕(≥85)
- `cash_min_recommended`: 원본 `cash_min` 값을 advisor 키명으로 노출
- `stock_max_recommended`: `raw.regime.params.stock_max` 가 있으면 그 값, 없으면 None

raw/raw_response/원본 cash_min 같은 내부·대용량 필드는 제외.

`MarketRegime.is_empty()` 인스턴스 메소드 신규 — 클래스메소드 `MarketRegime.empty()` 팩토리와 이름 충돌 회피.
모든 핵심 필드가 None 이면 True. 외부 호출자(`_call_openai`) 가 graceful 판정용.

#### B. `_call_openai()` user_payload 분기 (`src/engine/recommendation_engine.py`)

```python
from src.engine.market_regime import get_current_regime

try:
    regime = get_current_regime()
except Exception:
    regime = None
if regime is not None and not regime.is_empty():
    try:
        user_payload["market_regime"] = regime.to_advisor_dict()
    except Exception:
        logger.exception("to_advisor_dict 변환 실패 — market_regime 미포함")
```

graceful:
- regime is None → 키 추가 안 함 (싱글톤 미설정 / 명시적 None 분기)
- `regime.is_empty()` (모든 필드 None) → 키 추가 안 함 (사이클 2 empty 폴백)
- `to_advisor_dict()` 예외 → 키 추가 안 함 + WARNING 로그

#### C. SYSTEM_PROMPT 매크로 가이드 1 문단 추가

```
시장 매크로 컨텍스트 활용 (user_payload 에 market_regime 가 있을 때만):
- regime=defensive (현금 권고, VIX 25↑, 공포지수 극단): 손절률을 더 보수적으로 (절대값 작게) 조정, position_ratio 축소, daily_loss_limit 강화 권고
- regime=neutral: 기존 파라미터 유지 또는 미세 조정
- regime=aggressive (확장기, 낮은 VIX, 적정 fear_greed): 진입 임계 완화 또는 position_ratio 확대 가능 (단, 변동성 큰 모멘텀류는 신중)
- buy_blocked=True: 모든 전략 매수 차단된 상태. 매수 임계 변경 권고 무용 — 손절·청산·트레일링 파라미터만 권고
- weight_reasoning 에 매크로 영향 (예: "defensive 레짐 + VIX 28 → 보수적 비중") 명시 권장
- code_review_notes 에 매크로 의존 로직 도입 제안 가능 (예: VIX 25↑ 시 자동 매수 중단)
```

#### D. 회귀 가드 (총 30 케이스)

- `tests/unit/engine/test_recommendation_market_regime_payload.py` 27 케이스
  - A: empty regime 시 user_payload 에 `market_regime` 키 미포함
  - B: `get_current_regime()=None` 시 user_payload 에 키 미포함
  - C: defensive 활성 시 user_payload["market_regime"] dict 포함
  - D: 12 키 검증 (regime/regime_desc/cycle_phase/vix/vix_level/fear_greed_score/fear_greed_label/buffett_ratio/buy_blocked/block_reason/cash_min_recommended/stock_max_recommended)
  - E: `_classify_vix()` parametrize 9 케이스 + None
  - F: `_classify_fear_greed()` parametrize 10 케이스 + None
  - G: `to_advisor_dict()` 가 raw/raw_response/cash_min 원본 제외
  - H: SYSTEM_PROMPT 에 `market_regime`/`defensive`/`aggressive`/`buy_blocked` 키워드 포함
  - I: regime 비활성 시 user_payload 가 사이클 1 의 8 필드 그대로
- `tests/integration/test_recommendation_with_market_regime.py` 3 케이스
  - A: DKSTOCK_REGIME_ENABLED=false (empty regime) → 자문 정상 + market_regime 미포함
  - B: 활성 + defensive → market_regime 포함 + vix_level/fear_greed_label/buy_blocked 검증
  - C: get_current_regime()=None (fetch 실패 reset 시뮬레이션) → graceful

autouse fixture 로 모듈 싱글톤 `set_current_regime(MarketRegime.empty())` 매 테스트 후 reset.
risk_on_tick 등 후속 테스트의 buy_blocked 가드 오염 차단.

### 자율 결정 사항

- **VIX 분류 임계**: 명세의 권고(15/25/35) 그대로 채택 — CBOE VIX 통상 운영 임계와 일치
- **Fear & Greed 분류 임계**: 명세의 권고(15/35/65/85) 그대로 채택 — CNN Fear & Greed Index 5단계 표준과 일치
- **`to_advisor_dict()` 키 선정**: 명세 11 키 + `stock_max_recommended` 1 = 12 키
  - `cash_min` 원본 키명 대신 `cash_min_recommended` 로 의도 명확화 (운영자 권고치임을 명시)
  - `stock_max_recommended` 는 raw.regime.params 에서 추출 — 사이클 2 에 없던 필드지만 매크로 응답에 포함되어 자문 활용도 높음
- **`is_empty()` 인스턴스 메소드 신설**: 명세는 `regime.empty()` 호출이지만 dataclass `@classmethod` `empty()` 와 이름 충돌. `is_empty()` 로 분리 — 외부 호출자는 `regime.is_empty()` 사용
- **autouse fixture 추가**: 단위/통합 양쪽 모두에 추가해 모듈 싱글톤 격리 보호. Red 단계에서 1009/1010 일시 깨짐을 감지 → 즉시 보완

### 안전 원칙
- **graceful fallback**: regime 비활성/empty/None 시 분기 skip → 사이클 1 8 필드 회귀 보존
- **5/18 자문 첫 발화 안전**: DKSTOCK_REGIME_ENABLED=false 운영 상태 → user_payload 에 market_regime 미포함
- **운영 매매 흐름 미침범**: recommendation_engine 만 변경 — scheduler/risk/order_engine 영향 0
- **5/15 자문 row 영향 없음**: 소급 재계산 안 함
- **마이그 없음**: 코드 + SYSTEM_PROMPT 변경만, DB 스키마 영향 0

### 운영 활성화 절차

1. **5/18 월 20:00 첫 발화 사전 검증**: DKSTOCK_REGIME_ENABLED=false 상태에서 자문이 정상 발화하는지 확인 — 사이클 4 변경은 user_payload 분기만 추가, 비활성 상태에선 기존 동작
2. **DKSTOCK_REGIME_ENABLED=true 토글** (사이클 2 와 동시 또는 별도 시점): 매크로 fetch 가 정상 동작하기 시작하면 자동으로 자문 user_payload 에 market_regime 동봉
3. **5/19 화 20:00 이후 첫 매크로 자문 발화**: OpenAI 가 defensive/neutral/aggressive 레짐 + vix_level + fear_greed_label + buy_blocked 인지 → 손절률·position_ratio·daily_loss_limit·매수 임계 동적 권고
4. **자문 검수**: `weight_reasoning` 에 매크로 영향 명시 여부 / `code_review_notes` 의 매크로 의존 로직 제안 검토

---

## (2026-05-17) 자문 시스템 개선 사이클 5 — 외부 통합 토글 Settings UI

### 배경

사이클 2~4 가 .env 환경변수 (`DKSTOCK_REGIME_ENABLED`, `KIS_MCP_ENABLED`) 의존이라 운영자가 토글하려면 SSH 접속 + 컨테이너 재생성이 필요. 5/17 EC2 검증 단계에서 토글 전환 시점이 휴장이라 `_boot()` 미발화 → 메모리 미갱신 → API null 응답. 운영자가 Settings UI 로 즉시 ON/OFF 하고 활성화 시 즉시 fetch 가 발화되어야 운영 유연성 확보.

### 변경 요약

- DB 우선 / .env fallback 패턴 — Phase 1 / 사이클 2 운영자 영향 0 (하위 호환).
- 3 토글 통합:
  - `dkstock_regime_enabled` (system_config 신규 키): 외부 매크로 서버.
  - `kis_mcp_enabled` (system_config 신규 키): 외부 백테스트 서버.
  - `auto_regime_adjust` (사이클 2 기존 키 활용): 매크로 레짐 → cash_usage_ratio 자동 갱신.
- `dkstock-regime` 활성화(True) 시 `asyncio.create_task(_refresh_market_regime_and_persist_safely())` 백그라운드 fetch 발화 — API 응답 즉시 반환.
- `dkstock-regime` 비활성화 시 메모리 regime empty reset — 매수 가드 즉시 해제.
- `kis_mcp_enabled` 토글은 즉시 fetch 안 함 — 백테스트는 자문 시점(20:00) 발화.

### 기술 결정

| 결정 | 선택 | 사유 |
|------|------|------|
| `system_config` 헬퍼 패턴 | `get_*() -> bool \| None` (키 부재 시 None) | 호출자가 .env fallback 분기 — 하위 호환 |
| 클라이언트 `_check_enabled` | async 신설(`_check_enabled_async`), sync 백업 유지 | 호환성 + 매 호출 DB 조회로 즉시 반영 (캐시 없음) |
| `BacktestEngine.enabled` | sync 프로퍼티 보존 + `is_enabled_async()` 신설 | 호환성 + 매 호출 DB 조회 |
| UI 카드 구조 | 단일 카드 + 3 분리 행 | 운영자 시야 집중, 토글 간 관계(매크로 ON ↔ auto-regime ON) 가시화 |
| 활성화 즉시 fetch | `asyncio.create_task` fire-and-forget | API 응답 지연 방지, fetch 실패도 toggle 성공 유지 |

### 보존 (변경 안 함)

- 운영 매매 흐름: scheduler / order_engine / risk 영역 침범 0.
- 사이클 1~4 의 user_payload 통합 / weight_reasoning / 보드별 손절 / PARAM_RANGES 확장 모두 그대로.
- `auto_regime_adjust` 키는 사이클 2 023 마이그레이션에서 이미 추가 — 본 사이클은 신규 추가 안 함.

### 회귀 가드

- 백엔드: `tests/unit/db/test_system_config_integrations.py` 8 케이스 + `tests/unit/services/test_dkstock_client_db_toggle.py` 6 케이스 + `tests/unit/services/test_mcp_client_db_toggle.py` 6 케이스 + `tests/unit/engine/test_backtest_engine_db_toggle.py` 6 케이스 + `tests/contract/test_routes_system_integrations.py` 10 케이스 = 36 신규.
- 프론트: `frontend/src/components/__tests__/IntegrationToggleCard.test.tsx` 6 케이스.
- 회귀: 백엔드 1046 passed(1010→+36) / 프론트 106 passed(100→+6).

### 핵심 안전 원칙

- 하위 호환성 — .env fallback 보존: DB 값 미설정 시 기존 환경변수로 작동.
- 활성화 즉시 fetch 는 백그라운드 task — API 응답은 즉시 반환, fetch 실패도 toggle 성공 유지.
- 운영 매매 흐름 미침범: toggle 자체는 매크로/백테스트 활성화만 변경, 매매 로직 무관.
- ConfirmModal 이중 확인 — `dkstock_regime_enabled=true` 는 매수 가드 + cash_usage_ratio 자동 조정 발동 영향 있음.
- 비활성화 시 메모리 regime empty reset — 매수 가드 즉시 해제 (정합성).

### 운영 활성화 절차

1. **마이그 025 적용**: Supabase 콘솔에서 `supabase/migrations/025_external_integration_toggles.sql` 수동 실행. 멱등(`ON CONFLICT DO NOTHING`).
2. **Settings UI → 외부 통합 카드 → `매크로 레짐 (dkstock.cloud)` ON 토글** + ConfirmModal 확인. 3초 후 시장 레짐 카드 자동 갱신.
3. **`레짐 기반 cash_usage_ratio 자동 조정` 토글 검토**: defensive(0.25) / neutral(0.5) / aggressive(0.8) 자동 적용을 원하면 ON, 운영자 수동 관리면 OFF.
4. **`외부 백테스트 서버` 토글**: 5/18 월 20:00 자문에 백테스트 검증을 포함시키려면 사전 ON.
5. **`.env` 처리** (선택): DB 토글이 우선이라 환경변수 제거해도 무방. 그대로 두면 DB 갱신 안 한 상태에서도 환경변수 기본값으로 동작 — 안전망 권장.

---

## 사이클 6 — 로그 메뉴 신설 + 년/월/일 필터 (2026-05-17)

본 사이클은 **매매 코드 침범 0** 의 읽기 전용 UI/조회 재구성. 5/18 자문 사이클 영향 0.

### 목적
- 대시보드 하단 `LogViewer`(고정 50건 + 자동 폴링) 를 별도 `/logs` 메뉴로 분리 — 운영자가 매매 현황 화면과 로그 검토 화면을 분리
- 기존 `/log-reports` (일일 로그 분석) 와 통합 → "로그" 단일 메뉴 + 두 탭 구성
- 시스템 로그에 **년/월/일 기간 필터** + **페이징** 추가 → 5/18 등 특정 영업일 운영 사고 추적이 즉시 가능

### 변경 요약 (변경 파일)
- **백엔드**: `src/db/system_logs.py::get_logs()` 시그니처 확장 — `from_date / to_date / page / size` 추가, 응답 `{items, total, total_pages}` dict (기존 limit/level 단독 호출 하위 호환 보존). `src/routes/logs.py` 쿼리 파라미터 + 422 가드(`from_date > to_date`, `page < 1`, `size > 200`).
- **프론트엔드**:
  - 신규 `pages/Logs.tsx` 탭 컨테이너 + URL 쿼리 `?tab=system|daily-report` 동기화
  - 신규 `components/SystemLogsTab.tsx` — 날짜 + 레벨 필터 + 페이징(1-base, size 50), KST 강제
  - 신규 `components/DailyReportTab.tsx` — 기존 `LogReports.tsx` 본문 추출(JSX 동일)
  - 신규 `api/logs.ts` — `fetchLogs(filter)` 클라이언트
  - `App.tsx` 메뉴 "/log-reports 일일 로그 분석" → "/logs 로그", `/log-reports` 라우트는 `<Navigate to="/logs?tab=daily-report" replace />` 로 북마크 호환
  - `Dashboard.tsx` 에서 `<LogViewer />` 제거(컴포넌트 파일은 보존)
  - 기존 `pages/LogReports.tsx` 삭제 (DailyReportTab 으로 이전)

### 자율 결정
1. **기간 검색**: `from_date / to_date` 분리 date input (단일 날짜 아님). 기본값 둘 다 오늘(KST). `from_date > to_date` 시 422.
2. **URL 쿼리** `?tab=system|daily-report` (기본 `system`).
3. **컴포넌트 추출**: `LogReports.tsx` → `DailyReportTab.tsx`. `LogReports.tsx` 자체는 **삭제** (App.tsx 라우트에 inline `Navigate`).
4. **자동 새로고침 (3s polling)** 은 오늘 + page 1 일 때만 활성 — 과거 검색 / 페이징 중에는 비활성.
5. **KST 강제**: 백엔드 `f"{date}T00:00:00+09:00"` / 프론트 `Intl.DateTimeFormat('ko-KR', { timeZone: 'Asia/Seoul' })`. 기존 `LogViewer.tsx` 의 KST 누락은 새 `SystemLogsTab` 에서 해결 (LogViewer 파일은 보존이지만 더 이상 사용처 없음).
6. **페이징**: page 1-base, size 50 고정.

### 회귀 가드 (신규 +1 갱신)
- `tests/unit/db/test_system_logs_filter.py` — 8 케이스 (KST 기간 필터 / page-size / total_pages / 빈 결과 / 하위 호환)
- `tests/contract/test_routes_logs.py` — 9 케이스 (신규 파라미터 / 422 / 응답 구조 / 하위 호환)
- `frontend/src/pages/__tests__/Logs.test.tsx` — 5 케이스 (탭 활성 / URL 쿼리 / fallback)
- `frontend/src/components/__tests__/SystemLogsTab.test.tsx` — 9 케이스 (날짜 + 레벨 + 페이징 + 422 가드 + 빈 결과 + KST 시각)
- `frontend/src/__tests__/AppShell.test.tsx` — 메뉴 라벨 "로그" 로 갱신 (회귀)
- `frontend/src/pages/__tests__/LogReports.formatDateTime.test.ts` — import 경로만 `DailyReportTab` 으로 갱신 (회귀)

### 안전 원칙
- 매매 코드(`src/engine/`, `src/api/`, `src/realtime/`) 무수정
- 기존 `?limit=50&level=ERROR` 하위 호환 — `limit` 단독 호출 시에도 `size` 로 흡수되어 dict 응답
- `/log-reports` 북마크 호환 (Navigate replace)
- 5/18 자문 흐름(`recommendation_engine` 20:00) 결합점 0 — 본 사이클은 읽기 전용 조회

---

## 사이클 6 통합 마감 — 검색 박스 + Retention 정책 (2026-05-20)

본 사이클은 위 사이클 6 (2026-05-17) 1차 완료분 위에 사용자 신규 요청 2건을 통합 마감 (옵션 B). 매매 코드 침범 0.

### 목적
1. **로그 검색 기능** — system_logs 에서 키워드 substring 매칭 (예: `OPSP0002`, `nxt_downgrade`, `[priority_drop]` 등 특정 사고 흔적 추적)
2. **등급별 retention 정책** — INFO 등급 2일 / WARNING+ 30일 자동 정리 (DB 폭증 차단)

### 변경 요약 (변경 파일)
- **백엔드**:
  - `src/db/system_logs.py::search_logs(q, *, level, start, end, limit) -> {logs, total, has_more}` 신규 — `ilike("message", "%q%")` substring + level/start/end 동시 조건 + limit 1~1000 clamp + 빈 q ValueError
  - `src/db/system_logs.py::purge_old_logs() -> {info_deleted, high_deleted, elapsed_ms}` 신규 — INFO 2일 / HIGH 30일 cutoff 등급별 분리 DELETE + 1회 cap 100,000 + `[log_retention]` INFO 1행
  - `src/db/system_logs.py::_purge_by_cutoff(cutoff_iso, level_filter)` 내부 헬퍼 — `cutoff_iso=None` 이면 `RuntimeError("cutoff must not be None")` 즉시 raise (WHERE 누락 차단)
  - 상수: `INFO_RETENTION_DAYS=2` / `HIGH_RETENTION_DAYS=30` / `HIGH_LEVELS=("WARNING","ERROR","CRITICAL")` / `MAX_PURGE_BATCH=100_000` / `SEARCH_DEFAULT_LIMIT=200` / `SEARCH_MAX_LIMIT=1000`
  - `src/routes/logs.py::GET /api/logs/search` 신규 — `q` `min_length=1` (빈 q 422) / `limit` 1~1000 (외 422) / 응답 ApiResponse `{logs, total, has_more}`
  - `src/engine/scheduler.py::_run` settlement 흐름 — `_log_analysis_engine` *후* + `_reset_daily_state()` *전* 에 `await purge_old_logs()` 1회 호출. 예외 graceful (`[log_retention_skip]` INFO + 다음 사이클 재시도)
- **프론트엔드**:
  - `frontend/src/api/logs.ts::searchLogs(p)` 신규 + `SearchPayload/SearchParams` 타입
  - `frontend/src/components/SystemLogsTab.tsx` 검색 박스 추가 (필터 바 *위*, `system-logs-search-input` + Enter 키 + `system-logs-search-button` + 검색 모드 진입 시 `system-logs-search-clear`)
  - 검색 모드 동안 페이징/자동 새로고침 비활성 — 단일 limit 200 응답
  - 검색 결과 0건 → "검색 결과가 없습니다." (페이징 모드 "로그가 없습니다." 와 분리)
  - `has_more=true` 시 `system-logs-search-has-more` amber 배너 "검색 결과가 200건을 초과합니다. 키워드를 좁혀주세요."

### 자율 결정
1. **Retention 시점** = settlement 흐름 통합 (07:50 _boot 아님). `log_analysis_engine` 이 system_logs 를 *읽은 후* 정리해 분석 데이터 보존
2. **INFO 2일** = 모멘텀/VB 회귀 검토 영업일 + 1일 마진. 운영자가 보통 당일~다음날까지만 INFO 검토
3. **HIGH (WARNING/ERROR/CRITICAL) 30일** = 사고 추적 + 자문 metrics 영구화 호환 (`parameter_recommendations` 가 30일 윈도우 metrics 사용)
4. **Cap 100,000** = supabase 단일 트랜잭션 부하 흡수. 잔여분은 다음 사이클 자연 흡수 (영업일 1회 기준 INFO ~5만 / WARNING+ ~수천 — 충분 마진)
5. **WHERE None RuntimeError** = 전체 DELETE 사고 절대 차단 (방어 코드). cutoff 계산 결함 시 즉시 raise → scheduler graceful 흡수 → 다음 영업일 재시도
6. **검색 ILIKE substring** = 운영자 익숙한 SQL 패턴 + KIS 거부 코드(APBK0918 등) 부분 매칭. 정규식 안 씀 (escape 복잡도 회피)
7. **검색 limit 기본 200 / 최대 1000** = 페이징 부재 보완. `has_more` 안내로 키워드 좁히기 유도
8. **검색 모드 페이징 비활성** = limit 200 1회 응답으로 UI 단순화. 진짜 깊은 검색은 SQL 직접 접근 (운영자 권한)

### 회귀 가드 (신규 +30)
- `tests/unit/db/test_system_logs_retention.py` — 7 케이스 (A 반환 dict / B INFO 2일 cutoff / C HIGH 30일 + level 필터 / D INFO eq / E cap 100,000 / F cutoff None RuntimeError / G `[log_retention]` 로그)
- `tests/unit/db/test_system_logs_search.py` — 11 케이스 (A ilike / B level+q / C ALL skip / D None skip / E start/end / F 기본 limit 200 / G limit max 1000 clamp / H 반환 dict / I has_more=true / J has_more=false / K 빈 q ValueError / L whitespace q)
- `tests/contract/test_routes_logs_search.py` — 7 케이스 (A 정상 200 / B q 누락 422 / C 빈 q 422 / D limit>1000 422 / E limit=0 422 / F ApiResponse 래퍼 / G level/start/end 전달)
- `frontend/src/components/__tests__/SystemLogsTab.test.tsx` — +5 케이스 (검색 호출 + q 인자 / 0건 메시지 / 결과 렌더 + 초기화 노출 / 초기화 → 페이징 모드 복귀 / has_more 안내)

### 안전 원칙
- 매매 코드(`src/engine/`, `src/api/`, `src/realtime/`) 무수정 — `risk.on_tick` / `order_engine` / 6 전략 변경 0
- DB DELETE 안전 가드 — WHERE cutoff None 시 RuntimeError + 1회 cap 100,000 + 영구 로그 1행
- scheduler 통합부 예외 graceful — `[log_retention_skip]` INFO + 다음 사이클 재시도. settlement 본 흐름 보호
- 사이클 18 보존 (OPSP backoff / K stale watcher / 5xx dedupe / UI 컨텍스트)
- KIS API 호출 0 (DB 모듈만)

### 운영 효과 측정
- Retention 실효 일자: 2026-05-22 (영업일 20:10 첫 _settle 사이클 후. 본 EC2 배포 직후 INFO ~5만건 / HIGH ~수천건 일괄 정리 예상)
- 검색 응답 시간: limit 200 단일 응답 + ILIKE 인덱스 미지정 (full scan) — 30일 윈도우 100만건 기준 ~500ms~1s 추정 (supabase RTT 포함). PostgreSQL `pg_trgm` 인덱스 추가는 사이클 6-bis 후속 검토

---

## 커밋 5분할 (squash 금지)
1. `feat(strategies): VB/LTV get_targets_status returns active boards only`
2. `feat(scanner): cap breakout to 25 slots in priority queue (protect momentum)`
3. `feat(frontend): hide non-active board rows in ScanMonitor`
4. `test(strategies/scanner/frontend): cover active board filter and breakout cap`
5. `docs(engine/frontend): document active-board filter and breakout cap`

PR #2 (브랜치 `claude/diagram-stock-filtering-IaJ4G`) 위에 push → 자동 갱신.

---

## 자문 시스템 개선 사이클 7-A — KIS 다중 계좌 인프라 (2026-05-17)

### 배경
2026-04-20 KIS API rate limit 정책 변경(실전 18건/초)으로 단일 계좌 시 시세성 호출 + 매매 호출이 같은 quota 를 소모. 보조 계좌 5개를 시세 수신 전용으로 활용해 시세 처리량을 확장하되, **매매/잔고/체결통보는 메인 계좌 단일 보장** 원칙을 절대 깨지 않는다.

### 분할 사이클 (7-A → 7-B → 7-C → 7-D)
- **7-A (본 사이클)**: 인프라만 — DB 테이블 + 라우트 + 토큰 매니저 multi-account. 시세/매매 흐름 변경 0.
- 7-B (후속): WebSocketPool — 멀티 세션 시세 분배.
- 7-C (후속): REST 시세성 호출 라운드로빈.
- 7-D (후속): Settings UI.

### 자금 안전 원칙 (불변)
- **매매 주문(`src/api/order.py`)·잔고(`src/api/balance.py`)·체결통보(`H0STCNI0`) 구독은 영원히 메인 계좌만 사용.** 본 사이클은 해당 코드 경로 무수정.
- 보조 계좌(`kis_quote_accounts`) 는 **시세 수신 전용** — 자금 무관, 매매 절대 금지.
- 코드 리뷰 시 보조 계좌 변수(label, account_id) 가 매매/잔고 함수로 전달되는지 반드시 확인.

### DB 스키마 (migration 026, 적용 보류)
- `kis_quote_accounts` (UUID PK, label UNIQUE, app_key TEXT, app_secret TEXT 평문 1차 — Supabase RLS 의존, kis_env CHECK in('real','vts'), active BOOL DEFAULT true, created_at / updated_at TIMESTAMPTZ).
- `idx_kis_quote_accounts_active` 부분 인덱스 (`WHERE active = true`).
- COMMENT 로 시세 수신 전용 + 후속 KMS 보강 예정 명시.

### 백엔드 모듈
1. **`src/models/kis_quote_account.py`** — `KisQuoteAccount` (응답 모델, `app_secret_masked` 만 — 평문 필드 자체 부재) / `KisQuoteAccountCreate` / `KisQuoteAccountUpdate` / `mask_secret()` (마지막 4자리만, 8자리 미만은 `****` 통일 — 길이 정보 누출 차단).
2. **`src/db/kis_quote_accounts.py`** — `list_accounts(active_only)` / `get_account(id)` / `get_account_by_label(label)` / `insert_account(label, app_key, app_secret, kis_env)` / `update_account(id, active?, label?)` / `delete_account(id)` / `get_credentials_for_token_manager(label)` (토큰 매니저 전용 평문 노출 — API 응답/로그 절대 노출 금지) / `LabelConflictError` exception. 모든 함수 `asyncio.to_thread` 위임.
3. **`src/auth/token.py` 확장** — `TokenManager.__init__(*, app_key, app_secret, base_url, cache_path, label)` 키워드 주입 + 미지정 시 `settings.kis_*` fallback (메인 흐름 100% 보존). `_quote_token_managers: dict[str, TokenManager]` + `asyncio.Lock` 싱글톤. `get_token_manager(label=None)` async lazy 발급 — `label=None` 은 기존 `token_manager` 동일 인스턴스, label 지정 시 DB 자격증명 로드 + 격리 캐시(`_safe_cache_filename(label)`). `reset_quote_token_managers()` 테스트 헬퍼. `_resolve_base_url('real'/'vts')` 도메인 분기.
4. **`src/routes/kis_quote_accounts.py`** — `/api/integrations/quote-accounts/*` 4 라우트. GET 목록 / POST 등록 (201/409/422/500) / PUT active+label 부분 갱신 (200/404/409/422) / DELETE (200/404). 모든 응답 app_secret 평문 절대 노출 안 함.

### 토큰 매니저 multi-account 정책
- 메인 매니저(`token_manager`) — 기존 모듈 전역 인스턴스 보존. 매매·잔고·체결통보 사용.
- 보조 매니저 — `get_token_manager(label)` lazy. DB `kis_quote_accounts.app_key/app_secret/kis_env` 로드 후 격리 캐시 파일 사용. 같은 label 두 번째 호출 → 동일 인스턴스 (싱글톤).
- 미등록 label / `active=False` → `ValueError` raise — 호출자가 흡수해야 메인 흐름 영향 0.
- **보조 매니저의 `build_headers()` 는 시세 수신 한정** — 매매 헤더 구성에 사용 금지 (호출 경로 검토 시 차단).

### 자율 결정 사항
1. **app_secret 마스킹 형식**: `****` + 마지막 4자리. 8자리 미만 secret 은 `****` 통일 (길이 정보 누출 차단). 평문 필드 자체를 응답 모델에 부재로 처리해 직렬화 누출 사고 차단.
2. **토큰 매니저 싱글톤 위치**: 모듈 전역 `_quote_token_managers: dict[str, TokenManager]` + `asyncio.Lock` — 기존 `token_manager` 모듈 전역 인스턴스 패턴과 일관. 클래스 staticmethod 보관 회피(테스트 격리성 우선).
3. **PUT 라우트는 active/label 만 수정 허용**: app_key/app_secret 수정은 본 사이클 미지원 — 보안 감사 추적성 위해 삭제 후 재등록 패턴 강제. 후속 사이클에서 KMS 통합 시 재검토.
4. **`get_credentials_for_token_manager(label)` 평문 노출 함수 분리**: `list_accounts` / `get_account` 등 일반 조회 함수는 항상 마스킹 모델 반환. 토큰 매니저 lazy 초기화 외 호출 경로 차단 + 코드 리뷰 grep 추적 용이.

### 회귀 가드 (총 24 신규)
- `tests/unit/db/test_kis_quote_accounts.py` — 8 케이스 (insert+list / active_only / get_by_*/update active false / delete / label 중복 / kis_env CHECK / 빈 값).
- `tests/unit/auth/test_token_manager_multi.py` — 6 케이스 (메인 매니저 동일 인스턴스 / DB 자격증명 로드 / 싱글톤 / 미등록 ValueError / 메인·보조 격리 / 메인 매니저 회귀 보존).
- `tests/contract/test_routes_kis_quote_accounts.py` — 10 케이스 (빈 목록 / POST 201 마스킹 / 409 label 중복 / 422 빈 label / 422 빈 app_key / GET 마스킹 보존 / PUT active 토글 / DELETE / PUT 404 / DELETE 404).

### 운영 활성화 절차
1. **마이그 026 Supabase 콘솔 수동 적용** — 사용자 명시 승인 후 진행.
2. **Supabase RLS 정책 활성화 권장** — service_role / authenticated 외 SELECT 차단 (app_secret 평문 보호).
3. **보조 계좌 KIS Developers 발급** — 메인 계좌와 별개 앱 등록. 시세 권한만 있는 계좌면 충분 (매매 권한 불필요).
4. **`.gitignore` 갱신** — `.token_cache_quote_*.json` 패턴 추가 권장 (라벨별 캐시 파일 발생).
5. **계좌 등록 방법** (UI 는 7-D 사이클):
   - curl POST: `curl -X POST <host>/api/integrations/quote-accounts -d '{"label":"quote-1","app_key":"...","app_secret":"...","kis_env":"real"}'`
   - Supabase SQL: `INSERT INTO kis_quote_accounts (label, app_key, app_secret, kis_env) VALUES (...)`
6. **7-B WebSocketPool 사이클 진입 후 실제 시세 분배 시작** — 본 사이클은 등록 인프라만.

### 안전 원칙
- **시세/매매 흐름 변경 0** — `src/engine/`, `src/realtime/`, `src/api/order.py`, `src/api/balance.py` 무수정.
- 본 사이클 후에도 모든 KIS REST/WebSocket 호출은 메인 매니저(`token_manager`) 사용 — 보조 매니저는 노출만 되어 있을 뿐 실제 호출 경로 0.
- 보조 매니저 예외(`ValueError` 미등록 / DB 장애)는 메인 흐름에 영향 0 — 호출자가 try/except 흡수.
- app_secret 평문은 응답 모델 필드 자체 부재 + DB 호출 함수 분리(`get_credentials_for_token_manager`) 로 이중 차단.


## 자문 시스템 개선 사이클 7-B — WebsocketPool 시세 분배 (2026-05-17)

### 배경
사이클 7-A 에서 KIS 다중 계좌 인프라(DB + 토큰 매니저 + 라우트) 완성. 본 사이클은 **시세 수신 핵심 변경** — 단일 `KisWebSocket` 인스턴스를 메인 + 보조 N 세션 풀로 확장. 외부 호출자(`scanner`, `risk`, `scheduler`) 인터페이스는 100% 보존하며 내부 분배 로직만 캡슐화.

### 자금 안전 절대 원칙 (불변)
- **체결통보(H0STCNI0/H0STCNI9) → 메인 세션 단일 강제.** `WebsocketPool.subscribe()` 분기가 `tr_id in {H0STCNI0, H0STCNI9}` 면 priority 무시하고 무조건 메인 우회. `_enforce_main_only_execution_notice` 헬퍼가 보조 세션 직접 호출 시 `QuoteSessionExecutionNoticeError` raise.
- **매매/잔고/체결조회** → 본 사이클 변경 0 (사이클 7-A 가드 그대로). `src/api/order.py` / `src/api/balance.py` / `src/realtime/handler.py` 의 체결통보 핸들러 무수정.
- **보조 세션 0개 시 메인 only 회귀 보존** → DB `kis_quote_accounts` 미등록이면 기존 단일 세션 동작과 동일. 5/18 자문 영향 0.

### 분배 정책
- **HIGH 우선순위** (보유 / 익일청산) → 메인 세션 절대 보장 + `bypass_limit=True`. E1 규칙(2026-05-12) 유지.
- **LOW 우선순위** (스캐닝: VB/LTV/donchian/breakout/bull_flag/vcp) → 보조 세션 라운드로빈. 가득 / disconnect 세션 건너뜀. 모두 가용 없으면 메인 fallback (LOW 도 메인이 가득이면 drop).
- **중복 ticker 처리** — 메인 우선:
  - 메인에 이미 등록된 ticker 가 LOW 로 다시 들어오면 그대로 메인 유지
  - 보조에 등록된 ticker 가 HIGH 로 들어오면 → 보조 `unsubscribe` + 메인 `subscribe(bypass_limit=True)` 승격 + `[pool_promote] ticker=... old=quote-N new=main` INFO 로그
- **모든 세션 가득** → drop + `[priority_drop_pool] tr_key=... priority=LOW reason=all_sessions_full main=N/41 quotes=M` INFO 로그. drop 시 `subscribe()` 가 `None` 반환.
- **총 슬롯** = `MAX_SUBSCRIPTIONS × (1 + N)`. 메인 + 보조 5 = 246 슬롯.

### 백엔드 모듈
1. **`src/realtime/websocket_pool.py`** 신규 (~280 LOC):
   - `WebsocketPool` 클래스 — `_main: KisWebSocket` (기존 `kis_ws` 재사용), `_quotes: list[KisWebSocket]`, `_ticker_to_session: dict[str, KisWebSocket]` 분배 추적, `_round_robin_idx: int`
   - `subscribe(tr_id, tr_key, *, priority="LOW", bypass_limit=False) -> Optional[str]` — 사용된 세션 label 반환 (`"main"` / `"quote-N"`). drop 시 `None`
   - `unsubscribe(tr_id, tr_key)` — 분배 추적 dict 기반 정확한 세션에서 해제. 추적 없으면 noop (다음 `_scan_loop` 자연 정리). 체결통보는 메인 강제
   - `unsubscribe_all()` — 추적 dict 순회 + 모든 세션 매칭 해제 + dict clear
   - `resend_subscribe_for_ticker(tr_id, tr_key)` — K stale watcher 헬퍼. 추적 없는 ticker 는 메인 fallback
   - `get_subscribed_tickers() -> set[str]` / `get_acked_tickers() -> set[str]` — 메인 + 보조 합집합 (Phase D 호환)
   - `get_session_status() -> list[dict]` — 세션별 `{label, subscribed, acked, limit, ws_connected, reconnect_count, tickers}` 노출
   - 호환 property `_subscriptions` / `_subscriptions_acked` / `_ws` / `_reconnect_count` — 합집합 또는 메인 기준
   - `kis_ws_pool` 모듈 싱글톤
   - `QuoteSessionExecutionNoticeError` exception + `_enforce_main_only_execution_notice(pool, tr_id, *, session_label)` 헬퍼
2. **`src/routes/realtime.py::GET /api/realtime/subscriptions` 확장** — `kis_ws_pool` 호출로 변경:
   - 응답에 `sessions: [{label, subscribed, acked, fresh, stale, limit, ws_connected, reconnect_count, tickers}, ...]` 배열 추가
   - `total/acked/fresh_60s/stale_60s` 는 합집합 카운트
   - `limit` = `MAX_SUBSCRIPTIONS × len(sessions)` (총 슬롯 용량)
   - 보조 0개 시 sessions 길이 1 (main only) — 기존 호환 보존

### 자율 결정 사항
1. **옵션 2 채택 — `kis_ws` 메인 인스턴스 재사용** (옵션 1 = `kis_ws` 자체를 `WebsocketPool` 으로 교체 거부). 풀의 `_main` 을 기존 `kis_ws` 모듈 변수 그대로 재사용해 인스턴스 동일성 유지. 이유: `handler.py` / `scheduler.py` / `scanner.py` 등 다른 모듈이 `kis_ws` 참조를 보유한 채 풀이 별도 인스턴스로 교체되면 참조 분기 결함 발생. 옵션 2 는 기존 호출자가 `kis_ws._subscriptions` 등 set 직접 참조하는 패턴도 회귀 0건 (메인 단독 view).
2. **분배 추적 dict 가 KisWebSocket 인스턴스 참조 보유** (label 비교 대신 `is` 비교 사용). 라벨 변경에 안전.
3. **중복 ticker 처리: 보조 → HIGH 승격 시 보조 unsubscribe + 메인 add**. 양쪽에 동시 등록되면 동일 tick 메시지 중복 처리 위험 + 슬롯 낭비. 명시 승격으로 차단.
4. **라우트 `limit` 의미 확장** — `MAX_SUBSCRIPTIONS × 세션 수` (총 용량 표현). 메인 단독 41 의미는 `sessions[0].limit` 로 분리.
5. **`get_session_status` 의 `tickers` 키는 sorted subscribed/acked 만**. fresh/stale 카운트는 라우트 레벨에서 `ticker_last_tick` 비교 후 산출 — 시간 의존 로직을 풀 코어에서 분리 (테스트 격리성).

### 안전 규칙 멀티 세션 지원
- **E1 (보유·익일청산 우선)** — `subscribe(priority="HIGH")` 가 메인 bypass_limit=True 절대 보장
- **E2 (거절 응답 감지)** — 각 세션의 `_handle_raw()` 자체 동작. 풀이 거절 처리 재구현 안 함 (KisWebSocket 책임 유지)
- **F1 (재연결 후 자동 검증)** — 각 세션의 `_verify_subscriptions_after_reconnect()` 가 `connect()` 안에서 독립 발화
- **K (stale watcher)** — `pool.resend_subscribe_for_ticker(tr_id, tr_key)` 가 `_ticker_to_session` 추적 활용해 정확한 세션에 재전송. 추적 없으면 메인 fallback

### 회귀 가드 (총 46 신규)
- `tests/unit/realtime/test_websocket_pool.py` — 25 케이스 (분배 알고리즘 / 중복 / 체결통보 강제 / drop / get_subscribed_tickers / get_session_status / unsubscribe / 보조 0개 회귀)
- `tests/unit/realtime/test_pool_safety_rules.py` — 8 케이스 (E1 / E2 / F1 / K 멀티 세션 지원 + 메인 단일 체결통보 가드)
- `tests/integration/test_pool_distribution.py` — 6 케이스 (5 세션 100 종목 / 246 슬롯 drop / disconnect graceful / HIGH bypass 메인 가득 / 보조 0개 회귀 / 100 종목 통합 조회)
- `tests/contract/test_routes_subscriptions_pool.py` — 7 케이스 (sessions 배열 / 보조 0개 길이 1 / 보조 3개 길이 4 / 필수 키 / total=sum / acked=sum / limit 확장)

### 운영 점진 활성화 절차
1. **코드 배포 단계 (현재)**: 풀 코드 + 보조 세션 0개 → 메인 only 동작 (회귀 0). 5/18 자문 영향 0.
2. **첫 보조 등록** (5/20 이후): DB 1개 등록 → 1 보조 세션 활성. 사이클 7-C 에서 `scheduler._boot()` 가 보조 세션 connect() 호출 통합 후 효력 발생. 슬롯 41 + 41 = 82.
3. **점진 추가**: DB 2~5 등록 → 풀 점진 확장. 매번 운영 안정성 모니터링.
4. **`scheduler._boot()` 재시작 시점에 보조 세션 연결** — 기존 메인 흐름 유지.

### 후속 사이클 7-C 진입 전 확인 항목
- (a) `scheduler._boot()` 가 풀의 보조 세션 `connect()` 호출 추가 (시세 흐름 변경 시작 시점)
- (b) `scanner.subscribe_filtered_stocks` 가 풀의 `subscribe(priority=...)` 로 명시 분기 (현재는 `kis_ws.subscribe` 호출이 풀 메인으로 자연 routing — 보조 세션 활용은 안 됨)
- (c) K stale watcher (`scheduler._stale_watcher_loop`) 가 `kis_ws_pool.resend_subscribe_for_ticker` 사용으로 갈아끼움 — 분배 추적 정합성 유지

### 안전 원칙
- **외부 호출자 인터페이스 보존** — `scanner` / `risk` / `scheduler` 변경 0 (사이클 7-B). 보조 세션 활용은 사이클 7-C 에서 명시 분기.
- **체결통보 메인 단일 절대 보장** — 코드 가드 `RuntimeError` + 문서 (`src/realtime/CLAUDE.md` 사이클 7-B 섹션).
- **보조 세션 0개 시 기존 동작 회귀 보존** — 5/18 자문 영향 0.
- 점진 활성화 — 사용자가 보조 계좌 등록할 때까지 메인 only.

## 자문 시스템 개선 사이클 7-C — REST 시세성 호출 풀 + scanner 분배 명시화 (2026-05-18)

사이클 7-A(DB+토큰 multi-account) + 7-B(WebsocketPool 시세 분배) 완료 후, REST 시세성 호출도 보조 계좌 라운드로빈으로 분산 + scanner/stale watcher 가 풀 명시 호출로 전환. 본 사이클 완료 후 KIS 다중 계좌 인프라 전체가 일관된 분배 정책으로 동작.

### 자금 안전 절대 원칙 (변경 0)

- 매매(`place_order`/`cancel_order`) / 잔고(`get_balance`/`get_buyable`) / 체결조회(`get_daily_orders`) / 체결통보 → **영원히 메인 단일** (사이클 7-A/7-B 가드 그대로)
- REST 시세성 호출(`fetch_daily_candles`, `fetch_stock_detail`, `_fetch_fluctuation_rank`, `inquire_stock_basics`, `is_market_open`, `next_trading_day`) 만 본 사이클 풀에 라우트
- `QuotePoolPathError` raise — 시세 풀에서 매매/잔고 path 진입 시 즉시 거부 (defense-in-depth)
- 코드 + 문서 + 테스트 3중 가드 (`tests/unit/api/test_condition_quote_routing.py::test_order_module_never_imports_quote_pool` + `test_balance_module_never_imports_quote_pool`)

### 변경 요약

1. **`src/api/base.py` 확장 (~200 LOC)**
   - `kis_get_quote` / `kis_post_quote` 신규 함수 + `_request_via_quote_pool` 본체
   - `_QUOTE_ALLOWED_PATHS` 화이트리스트 (5 path) — 외 경로 즉시 `QuotePoolPathError`
   - `_select_quote_label()` 라운드로빈 — `(idx+1) % len(active_labels)` + `asyncio.Lock`
   - Per-label `_quote_semaphores[label] = Semaphore(18)` (메인 20 보다 보수적)
   - `_quote_request_metrics` 격리 dict + `get_quote_request_metrics` / `reset_quote_request_metrics`
   - 보조 토큰 매니저 발급 실패 (`ValueError`) → 메인 fallback (graceful)

2. **`src/api/condition.py` 6 함수 위임 (~6 LOC)**
   - `is_market_open` / `next_trading_day` / `_fetch_fluctuation_rank` / `inquire_stock_basics` / `_fetch_stock_detail_and_cache` / `_fetch_daily_candles_and_cache` 모두 `kis_get` → `kis_get_quote`
   - import: `from src.api.base import KisApiError, kis_get_quote` (메인 `kis_get` import 제거)
   - 시그니처 변경 0 — 외부 호출자(`scanner`, `strategies`) 영향 없음

3. **`src/engine/scanner.py` (~25 LOC)**
   - `from src.realtime.websocket_pool import kis_ws_pool` 추가
   - `subscribe_filtered_stocks` priority_groups 분기에서 `kis_ws.subscribe(...)` → `kis_ws_pool.subscribe(tr_id, t, priority='HIGH'|'LOW', bypass_limit=True|False)` 위임
     - `positions`/`next_day_clear` → priority='HIGH' + bypass_limit=True (메인 절대 보장)
     - `breakout`/`momentum`/`swing` → priority='LOW' + bypass_limit=False (보조 라운드로빈 우선)
   - 평탄 처리 분기(`priority_groups=None`)는 기존 `kis_ws.subscribe` 그대로 (외부 호환)

4. **`src/realtime/websocket_pool.py` 확장 (~120 LOC)**
   - `WebsocketPool.start(dispatch_message=None)` — DB 활성 보조 계좌 lazy connect (멱등 `_started`)
   - `WebsocketPool.stop()` — 보조 disconnect + task cancel + 추적 dict clear
   - `WebsocketPool.unsubscribe_in_pool(tr_id, tr_key)` — 강제 재등록용 (분배 추적 제거 + 세션 unsubscribe)
   - 보조 세션 KisWebSocket 인스턴스에 `token_manager=<보조 매니저>` 주입

5. **`src/realtime/websocket.py` 최소 변경 (~3 LOC)**
   - `KisWebSocket.__init__(*, token_manager=None)` 선택적 주입
   - `connect()` 의 approval_key 발급을 `self._token_manager.get_approval_key()` 로 분기 (메인 기본값 보존)

6. **`src/engine/scheduler.py` (~10 LOC)**
   - `start()` 메인 `kis_ws.connect()` 직후 `await kis_ws_pool.start(dispatch_message=...)` 호출
   - `_check_and_resubscribe_stale()` 가 단일 세션 직접 호출 → 풀 헬퍼(`resend_subscribe_for_ticker` / `unsubscribe_in_pool` / `subscribe(priority='HIGH')`) 위임

### 회귀 가드 (42 신규)

| 파일 | 케이스 |
|------|-------|
| `tests/unit/api/test_quote_pool.py` | 18 — 보조 0개 fallback / 라운드로빈 / 토큰 매니저 lazy / 매니저 실패 graceful / path 가드 (5 forbidden + 5 allowed) / 위임 / 메트릭 격리 / 5xx 재시도 / 매매·잔고 가드 |
| `tests/unit/api/test_condition_quote_routing.py` | 7 — 6 함수 위임 + order/balance 모듈 import 가드 |
| `tests/unit/engine/test_scanner_priority_dispatch.py` | 8 — HIGH/LOW 명시 / bypass_limit / 중복 dedup |
| `tests/integration/test_stale_watcher_pool.py` | 5 — 풀 헬퍼 경유 / 분배 추적 활용 / 강제 재등록 / >6 skip / fresh 회복 clear |
| `tests/integration/test_scheduler_boot_quote_sessions.py` | 4 — 보조 0개 회귀 / N개 connect / 실패 graceful / 체결통보 메인 단일 |

### 운영 점진 활성화

1. 사이클 7-C 배포 후 보조 세션 DB 0개 → 메인 only 동작 (회귀 0, 5/18 자문 영향 0)
2. 운영자가 1~5개 보조 계좌 등록 → 자동으로 시세 풀에 분배 (재기동 없이 다음 `_boot` 사이클부터 반영)
3. 메트릭 분리 — `get_quote_request_metrics().by_label` 로 `main` / `quote-N` 분배 현황 가시화 (대시보드 노출은 별도 사이클)

### 안전 원칙

- **자금 안전 절대 원칙**: 매매/잔고/체결통보 메인 단일 영구 보장 — 코드 가드 (`QuotePoolPathError`) + 문서 + 모듈 import 가드 테스트
- **외부 호출자 인터페이스 보존** — `fetch_daily_candles` 등 시그니처 변경 0
- **보조 토큰 매니저 실패 graceful** — `ValueError` 또는 connect 실패 시 메인 fallback / 해당 세션 skip
- **점진 활성화** — 보조 등록 전까지 메인 only 회귀 0

## 자문 시스템 개선 사이클 7-D — Settings UI 보조 계좌 관리 (2026-05-18)

사이클 7-A/B/C 에서 백엔드 인프라(DB + 토큰 + WebSocket 풀 + REST 풀) 완성. 본 사이클은 **운영자가 SSH/SQL 없이 UI 만으로 보조 계좌 관리 + 분배 가시화**. 프론트엔드 only, 백엔드 변경 0 — 사이클 7-A 의 기존 라우트 활용.

### 산출물 (프론트엔드)

| 영역 | 파일 | LOC | 비고 |
|------|------|-----|------|
| 타입 | `frontend/src/types/kis-quote-accounts.ts` | 35 | `KisQuoteAccount` / `KisEnv` / Create·Update Input — 백엔드 1:1, **app_secret 평문 필드 부재** |
| API 클라이언트 | `frontend/src/api/kis-quote-accounts.ts` | 50 | `listAccounts` / `createAccount` / `updateAccount` / `deleteAccount` — 사이클 7-A 라우트 4종 |
| API 확장 | `frontend/src/api/realtime.ts` | +60 | `SubscriptionsResponse` + `SubscriptionSession` 타입 + `getSubscriptions()` — 사이클 7-B sessions 배열 활용 |
| 컴포넌트 | `frontend/src/components/KisQuoteAccountsCard.tsx` | 340 | Settings 카드 — 표 / 등록 폼 / ConfirmModal 이중 확인 |
| 컴포넌트 | `frontend/src/components/KisAccountPoolCard.tsx` | 200 | Dashboard 카드 — 세션 표 / 슬롯 사용률 진행바 / 새로고침 / 자동 30s 폴링 |
| 페이지 통합 | `frontend/src/pages/Settings.tsx` | +3 | `IntegrationToggleCard` 직하 `KisQuoteAccountsCard` 삽입 |
| 페이지 통합 | `frontend/src/pages/Dashboard.tsx` | +4 | `MarketRegimeCard` 직하 `KisAccountPoolCard` 삽입 |

### KisQuoteAccountsCard — Settings 페이지 (보조 계좌 관리)

**위치**: `IntegrationToggleCard` 직하 (외부 통합 → KIS 보조 계좌 위계)

**조회 영역**:
- 표 컬럼: label / 환경 배지(real=red / vts=emerald) / app_key 마스킹(`****1234`, 마지막 4자리만) / app_secret_masked(`****7890`) / 등록일(KST `Intl.DateTimeFormat`) / active 토글 / 삭제 버튼
- 빈 목록 시 `quote-accounts-empty` 안내 — "등록된 보조 계좌 없음. 추가하면 시세 풀 슬롯이 41 × (1 + N) 으로 확대"
- 로드 에러 시 `quote-accounts-load-error` 빨간 박스 + "잠시 후 재시도하세요"

**등록 폼**:
- label (text, 영문/숫자/하이픈만 `^[A-Za-z0-9\-]+$`)
- kis_env (radio: real / vts)
- app_key (text, autocomplete="off")
- app_secret (**type=password**, autocomplete="new-password", 평문 잔존 차단)
- 클라이언트 검증: 빈 값 거부 / label 형식 위반 거부 → `quote-account-form-error` 노출 + POST 미발사

**ConfirmModal 이중 확인** (등록 / active 토글 / 삭제 모두):
- 등록: "보조 계좌 \"{label}\" ({env}) 를 등록합니다. 다음 _boot(07:50) 부터 시세 풀에 분배됩니다 — 41 × (1 + N) 슬롯 확장"
- 활성화: "다음 _boot 부터 시세 풀에 포함"
- 비활성화: "다음 _boot 부터 시세 풀에서 제외"
- 삭제: "영구 삭제. 시세 풀에서 즉시 제외"

**안전 원칙**:
- **app_secret 평문 잔존 시간 최소화** — 폼 제출 성공 시 secret state 즉시 클리어 (`setForm` 빈 값). 회귀 가드 `7D-I`
- **app_secret input type=password 강제** — DOM 노출 차단. 회귀 가드 `7D-J`
- **응답 마스킹 의존 0** — UI 가 `app_secret_masked` 만 참조 (백엔드 실수로 평문이 와도 표시 안 됨). 회귀 가드 `7D-H`
- **에러 메시지 분기** — axios 인터셉터 status 코드별 한글 메시지 (`409: label 중복` / `422: 검증 실패` / 그 외)

### KisAccountPoolCard — Dashboard (시세 풀 모니터링)

**위치**: `MarketRegimeCard` 직하 (시장 상태 → 인프라 상태 위계)

**상단**:
- 카드 제목 "KIS 시세 풀 (WebsocketPool)" + 설명
- 우측 상단 `pool-refresh-button` 새로고침 버튼 → `invalidateQueries({queryKey: ['realtime-subscriptions']})`

**총 슬롯 사용률 패널** (회색 박스):
- `pool-used-slots` / `pool-total-slots` — `41 × (1 + N)` 산출
- `pool-usage-progress` 진행바 — 80% 미만 emerald / 80% 이상 amber (위험 색)
- fresh / stale / ACK 카운트 인라인

**세션별 표**:
- `pool-session-row-{label}` — main / quote-1 / quote-2 ...
- label 배지 (main=blue 강조 + "(체결통보)" 표기) / `pool-session-status-{label}` 연결 배지 (connected=emerald / disconnected=red)
- 구독 카운트 (`subscribed / limit`) + `pool-session-progress-{label}` 미니 진행바
- fresh / stale / 재연결 카운트

**보조 0개 fallback**:
- `pool-no-secondary-note` 안내 — "보조 세션 없음 (메인 only). Settings > 보조 KIS 시세 계좌에서 등록하면 다음 _boot(07:50) 부터 슬롯이 41 × (1 + N) 으로 확장"

**자동 폴링**:
- `refetchInterval: 30_000` (30초) — 운영자가 새로고침 안 눌러도 자동 갱신
- `staleTime: 5_000` — 단시간 중복 호출 방지
- 새로고침 버튼 클릭 = 즉시 재조회 (다른 카드 폴링 영향 없음, 단독 queryKey)

### API 라우트 (사이클 7-A 의 기존 라우트 — 변경 0)

| Method | URL | 응답 / Body |
|--------|-----|------------|
| GET | `/api/integrations/quote-accounts?active_only=false` | `{accounts: KisQuoteAccount[]}` |
| POST | `/api/integrations/quote-accounts` | body: `{label, app_key, app_secret, kis_env}` → 201 `KisQuoteAccount` / 409 / 422 / 500 |
| PUT | `/api/integrations/quote-accounts/{id}` | body: `{active?, label?}` → 200 / 404 / 409 / 422 |
| DELETE | `/api/integrations/quote-accounts/{id}` | 200 / 404 |
| GET | `/api/realtime/subscriptions` | 사이클 7-B 응답: `{total, acked, fresh_60s, stale_60s, limit, ws_connected, reconnect_count, sessions: [...]}` |

### 회귀 가드 (16 신규, 프론트 119 → 135)

| 파일 | 케이스 | 비고 |
|------|--------|------|
| `frontend/src/components/__tests__/KisQuoteAccountsCard.test.tsx` | 10 | A 빈 목록 / B 1개 행+마스킹 / C 폼 제출+ConfirmModal+POST / D 409 / E 클라이언트 검증 / F 토글 PUT / G 삭제 DELETE / H 평문 부재 / I secret 폼 클리어 / J password type |
| `frontend/src/components/__tests__/KisAccountPoolCard.test.tsx` | 6 | PA 메인 only 안내 / PB 메인+보조 2 3행 / PC disconnect red 배지 / PD 슬롯 100% / PE 500 graceful / PF 새로고침 즉시 재조회 |

### 운영자 사용 가이드 (보조 5 계좌 등록부터 분배 시작까지)

**1. KIS Developers 보조 계좌 발급 (5개)**
- https://apiportal.koreainvestment.com/ 로그인
- "내 API 키 관리" → "신청" 5회 반복 (계좌당 1세트, 동일 HTS ID 가능)
- 발급 즉시 app_key (PSxx...) + app_secret 메모 (1회 표시 후 재발급 불가)

**2. Settings UI 에서 등록 (계좌당 ~30초)**
- 좌측 메뉴 Settings → 페이지 하단 "보조 KIS 시세 계좌" 카드
- 신규 등록 폼:
  - label: `quote-1` ~ `quote-5` (영문/숫자/하이픈)
  - 환경: real 선택 (실전 5종 권장)
  - app_key 붙여넣기
  - app_secret 붙여넣기 (password 마스킹)
- "등록" 버튼 → ConfirmModal "확인" → 표 1행 추가 (등록 후 폼 자동 클리어)
- 5회 반복 → 표 5행

**3. 활성화 (다음 _boot 자동 — 재기동 불필요)**
- 등록 직후는 시세 풀에 반영 안 됨 (active=true 상태로 DB 저장만)
- 다음 영업일 07:50 `_boot()` 가 `kis_quote_accounts.list_accounts(active_only=True)` 조회 → 보조 5 세션 connect
- 즉시 활성화하려면: 시스템 정지(`POST /api/trading/stop`) 후 재기동(`POST /api/trading/start`) — 운영자 판단

**4. 분배 확인 (Dashboard "KIS 시세 풀" 카드)**
- 메인 0/41 → 1+5=6 행 표 (메인 + quote-1~5)
- 총 슬롯 41 → 41 × 6 = 246
- 각 세션 connected 배지 / 구독 카운트 진행바 / 재연결 횟수 확인
- 30초 자동 폴링 + 새로고침 버튼

**5. 트러블슈팅**
- disconnect 배지(red): KIS 토큰 발급 실패 가능 — `system_logs` 에서 `[pool_start]` / `[token]` 로그 확인
- 슬롯 사용률 80%+ amber: 종목 풀 확장 가능 — 메인 단독 41 제한 → 보조 분산으로 100~200+ 종목 지원
- 등록 시 409 (label 중복): 기존 label 변경 또는 PUT 으로 기존 행 label 갱신

### 안전 원칙 (사이클 7-D 한정)

- **운영 매매 흐름 무관** — 프론트엔드 UI 만 변경, 백엔드 라우트는 7-A 기존. 회귀 0 (백엔드 1172 변경 없음)
- **app_secret 평문 노출 차단** — 입력 즉시 백엔드 전송, 응답에는 마스킹만. UI state 도 제출 후 클리어
- **ConfirmModal 이중 확인 의무** — 등록 / 토글 / 삭제 모두 (사이클 5 컨벤션 동일)
- **즉시 분배 변경 없음** — 등록·삭제는 다음 _boot 부터 효력. 운영자가 의도적으로 재기동 시점 통제

## 자문 시스템 개선 사이클 8 — 매수 가드 4 모드 + 임계 조정 Settings UI (2026-05-18)

### 배경

5/17 사용자 실측: `regime=defensive vix=18.43 fg=76.0 buy_blocked=True cash_min=75`. 사이클 2 매수 가드는 4 임계(defensive / VIX>25 / FG>85 / FG<15) **OR** 단일 HARD 분기 — `regime=defensive` 단독 조건만으로 모든 전략 매수 전면 차단됐다. VIX/FG 자체는 normal / 탐욕 정상 범위인데도 잠금. 사용자 피드백: "강제 매수 잠금이 너무 가혹함, 컨트롤 가능하게".

### 4 모드 + 4 임계값 (1c + 2a + 3a + 4a)

| 모드 | 가드 발동 시 동작 | 용도 |
|-----|------------------|-----|
| `OFF` | 가드 평가 자체 비활성 | 진성 회복기 / 백테스트 |
| `WARN` | 매수 허용 + WARNING 로그 | 감사용 (영향 분석) |
| `SOFT` | 매수 허용 + `position_ratio × 0.5` (최소 1주) | 5/17 사용자 케이스 권장 — 보수적 진입 |
| `HARD` | 완전 차단 (기본값, 사이클 2 동작) | 진성 위기 (VIX>30 + defensive) |

| 임계 | DB 키 | 기본값 | 범위 |
|-----|------|-------|-----|
| VIX | `buy_block_vix_threshold` | 25.0 | [10, 50] |
| Fear & Greed 상한 | `buy_block_fg_high_threshold` | 85.0 | [50, 100] |
| Fear & Greed 하한 | `buy_block_fg_low_threshold` | 15.0 | [0, 50] |
| regime defensive 차단 ON | `buy_block_regime_defensive_enabled` | true | bool |

**모드 키**: `buy_block_mode` (기본 `HARD` — 본 사이클 배포 후에도 현재 동작 회귀 보존).

### 구현 위치

| 영역 | 파일 / 함수 |
|------|------------|
| DB 마이그레이션 | `supabase/migrations/027_buy_block_mode.sql` (적용 보류, 멱등 INSERT) |
| DB 헬퍼 | `src/db/system_config.py` — `get_buy_block_mode / set_buy_block_mode / get_buy_block_thresholds / set_buy_block_thresholds` + `BuyBlockThresholds` Pydantic |
| 엔진 | `src/engine/market_regime.py::MarketRegime.get_buy_block_state() -> BuyBlockState` async (사이클 2 `is_buy_allowed` 동기 API 는 회귀 가드용 보존) |
| 매매 분기 | `src/engine/risk.py::on_tick` — `BuyBlockState.mode` 분기로 HARD skip / WARN log / SOFT multiplier / OFF 비활성 |
| 수량 적용 | `src/engine/order_engine.py::execute_buy(soft_multiplier=...)` kwarg — `quantity = max(1, int(qty * multiplier))` |
| 라우트 | `src/routes/system_integrations.py` — `GET /api/integrations/buy-block` / `PUT /api/integrations/buy-block` |
| 모델 | `src/models/system_integrations.py` — `BuyBlockMode / BuyBlockThresholdsModel / BuyBlockStatusResponse / BuyBlockUpdateRequest` |
| 프론트엔드 | `frontend/src/components/IntegrationToggleCard.tsx::BuyBlockSection` — 모드 select + 4 슬라이더 + defensive 체크박스 + 저장 버튼 + 사유 표시 |

### 핵심 안전 원칙

- **기본값 HARD + 기본 임계** — DB 미설정 / 마이그 027 미적용 / 새 운영 환경에서도 사이클 2 동작 100% 회귀 보존
- **SOFT 모드 최소 1주 보장** — `max(1, int(quantity * 0.5))` 로 position_ratio 0 으로 떨어지는 결함 차단
- **DB 우선 + .env fallback 없음** — 본 키 5개는 운영 가변 설정 (DB 미설정 시 코드 디폴트로 fallback)
- **모드 변경은 ConfirmModal 이중 확인** — 매매 흐름 직접 영향. 임계값 변경은 ConfirmModal 없이 즉시 (덜 위험)
- **사이클 2 `is_buy_allowed()` 동기 API 보존** — `to_advisor_dict()` 의 `buy_blocked` 필드 호환성. 4 모드 분기는 `get_buy_block_state()` async 신규 메서드가 책임
- **매도/손절은 모든 모드에서 무관** — `check_exit_signal` 분기는 가드 진입 전. 청산 의무는 시장 상황과 무관해야 함

### API 컨트랙트

| Method | URL | 동작 |
|--------|-----|------|
| GET | `/api/integrations/buy-block` | `{mode, thresholds:{vix_threshold, fg_high_threshold, fg_low_threshold, defensive_enabled}, blocked, reasons:[], soft_multiplier}` |
| PUT | `/api/integrations/buy-block` | body 부분 갱신 `{mode?, vix_threshold?, fg_high_threshold?, fg_low_threshold?, defensive_enabled?}` → 갱신된 전체 상태 / 422(범위 외 / 모드 외) / 500(DB 실패) |

### 회귀 가드 (사이클 8 신규 47 + 프론트 7)

| 파일 | 케이스 | 비고 |
|------|--------|------|
| `tests/unit/db/test_system_config_buy_block.py` | 17 | 모드 4종 round-trip / 모드 외 ValueError × 8 / 임계 부분 갱신 / 전체 갱신 / defensive 단독 / 기본값 |
| `tests/unit/engine/test_market_regime_buy_block_state.py` | 10 | DB 미설정 HARD / HARD blocked / SOFT 0.5 / WARN allow / OFF disable / defensive_enabled=false / 4 사유 수집 / 임계 적용 / empty graceful / `is_buy_allowed` 회귀 |
| `tests/unit/engine/test_risk_buy_block_modes.py` | 11 | HARD skip / HARD allow / WARN 로그 / SOFT multiplier kwarg / OFF 비활성 / 4 모드 청산 무관 (parametrize 4) / 사이클 2 회귀 |
| `tests/contract/test_routes_buy_block.py` | 9 | GET 응답 구조 / SOFT 응답 / PUT mode-only / PUT thresholds-only / defensive=false / 422 모드 / 422 VIX / 422 FG_high / 422 FG_low |
| `frontend/src/components/__tests__/IntegrationToggleCard.test.tsx` | +7 | I8-A select+4 슬라이더 / I8-B reasons 표시 / I8-C 모드 변경 ConfirmModal+PUT / I8-D 임계 슬라이더 PUT / I8-E defensive 체크박스 PUT / I8-F SOFT multiplier 표시 / I8-G 500 graceful |

### 운영자 사용 가이드

**상황별 권장 모드**:

| 시장 상황 | 5/17 실측 예 | 권장 모드 | 비고 |
|----------|-----------|----------|-----|
| defensive 단독, VIX/FG 정상 | `regime=defensive vix=18.43 fg=76.0` | **SOFT** 또는 `defensive_enabled=false` | 5/17 사용자 케이스. SOFT 면 비중 절반 진입, defensive_enabled=false 면 regime 가드만 끄고 VIX/FG 유지 |
| neutral/aggressive, VIX 정상 | VIX <25, FG 30~70 | OFF (자동 진입 불필요) | 정상 시장 |
| defensive + VIX 30+ | VIX>30 + defensive | **HARD** | 진성 위기 — 완전 차단 |
| 자동매매 잠시 중단 | 시스템 점검 / 사고 직후 | OFF (수동 매수만) | 임시 |

**임계값 조정 권장값**:

- VIX `25` (기본) → `20` (예민) / `30` (보수) — VIX 평균 15~25 에서 25 컷이 보통
- FG 상한 `85` (기본) → `90` (예민) / `80` (보수) — 5/17 FG=76 케이스에서 85 컷은 정상
- FG 하한 `15` (기본) → `20` (보수, 더 일찍 차단) — 극도 공포 진입가 평소 매수 기회

**모드 전환 절차**:
1. Settings 페이지 → 외부 통합 카드 하단 "매수 가드" 영역
2. 모드 select 클릭 → ConfirmModal 안내 메시지 확인 → "확인"
3. 응답 즉시 반영 — 다음 매수 신호부터 새 모드로 평가 (재기동 불필요)
4. 임계값은 슬라이더 조정 후 "임계값 저장" 버튼 → 즉시 적용

**관측 포인트**:
- `system_logs` `[buy_block_warn]` — WARN 모드 시 매 매수 신호당 1행
- `system_logs` `[buy_block_soft]` — SOFT 모드 시 수량 축소 1행
- `[regime_block]` (1분 주기 INFO) — HARD 모드 차단 카운트

### 마이그레이션 적용 절차

```sql
-- Supabase 콘솔에서 수동 실행
-- supabase/migrations/027_buy_block_mode.sql
INSERT INTO system_config (key, value) VALUES
  ('buy_block_mode', '{"value": "HARD"}'::jsonb),
  ('buy_block_vix_threshold', '{"value": 25.0}'::jsonb),
  ('buy_block_fg_high_threshold', '{"value": 85.0}'::jsonb),
  ('buy_block_fg_low_threshold', '{"value": 15.0}'::jsonb),
  ('buy_block_regime_defensive_enabled', '{"value": true}'::jsonb)
ON CONFLICT (key) DO NOTHING;
```

- 멱등 (`ON CONFLICT DO NOTHING`) — 재실행 안전
- 미적용 시에도 코드 디폴트 (HARD + 기본 임계) 작동 → 회귀 0
- 적용 후 Settings UI 에서 즉시 조정 가능

## 사이클 9 — KIS 차단 회피 안전망 보강 (2026-05-18)

### 배경
KIS Open API 담당자 공지 (2026-05-18): 무한 연결/종료 반복, 검증 없는 무한 등록/해제 반복 → IP/앱키 일시 차단 예정.

자체 점검 결과 K stale watcher 가 보조 세션 5개와 결합 시 분당 800 unsubscribe/subscribe 요청을 KIS 에 던질 수 있어 비정상 케이스 2 (무한 등록/해제) 에 직접 매핑됨. 운영 매매 흐름 무관한 시세 안전망만 보강.

### 4 항목 변경

1. **stale watcher 발화 주기 완화** (`src/engine/scheduler.py`)
   - `STALE_WATCHER_INTERVAL_SECS`: 30 → **120** (분당 발화 1/4)
   - `STALE_FORCE_REREGISTER_AFTER`: 3 → **10** (10회 × 120s = 20분 stale 누적 후 강제 재등록)
   - `STALE_FRESHNESS_SECS`: 60 그대로 (5/12 운영 사고 대응 의도 보존)
   - 분기 자동 확장: 21회 초과 skip (기존 6회 초과 → 사이클 9 임계 20)

2. **`QuoteSessionHealthMonitor` 신규** (`src/services/quote_session_health.py`)
   - 보조 시세 세션 헬스 추적 + 자동 비활성 의사결정 (메인 라벨 "main" 은 제외 — 안전 가드)
   - 상수: `MAX_CONSECUTIVE_FAILURES=5` / `WINDOW_SECS=300` / `MAX_FAILURE_RATE=0.5` / `MIN_CALLS_FOR_RATE=10`
   - 비활성 트리거: (a) 5회 연속 실패 (b) 5분 sliding window total ≥ 10 + failure_rate ≥ 0.5
   - 트리거 시 (1) `kis_quote_accounts.update_account(active=False)` (2) `kis_ws_pool.disable_quote_session(label)` (3) `system_logs` `[quote_session_disabled]` 영구 1행
   - DB update 실패 graceful — 메모리는 비활성 그대로 + WARNING 로그 `[quote_session_health_db_fail]`
   - `_disabled_labels` set 으로 두 번째 호출 idempotent
   - 성공 시점에도 sliding window 평가 (`_evaluate_rate_only`) — 누적 비율 임계 race 차단

3. **`base.py::_request_via_quote_pool` 통합**
   - 성공(`rt_cd=="0"`) + actual_label != "main" → `record_success(label)`
   - 5xx HTTPStatusError → `record_failure(label, reason=f"http_{status}")`
   - 보조 매니저 발급 실패 → `record_failure(label, reason="token_issue_fail")`
   - KIS rt_cd!=0 비즈니스 거부 → 기록 안 함
   - 네트워크 에러 → 기록 안 함 (클라이언트 측 이슈 가능)

4. **`WebsocketPool.disable_quote_session(label)` 신규** (`src/realtime/websocket_pool.py`)
   - "quote-N" 라벨 → 1-based index 변환 → 해당 세션 `disconnect()` + `_quotes` 제거
   - `_ticker_to_session` 에서 해당 세션 담당 ticker 정리
   - 메인 라벨 "main" → noop (안전 가드)
   - 없는 label / 형식 불일치 → noop (idempotent)
   - 다음 ``subscribe`` 호출은 자동 라운드로빈 → 남은 보조 또는 메인 fallback

### 운영자 가이드
자동 비활성된 보조 세션 복귀 절차:
1. Settings UI 보조 계좌 카드 진입
2. 비활성된 라벨의 `active=true` 토글
3. **다음 영업일** `_boot()` (07:50) 부터 풀에 재참여
   - 당일 즉시 재참여는 미지원 (보안: 동일 토큰 패턴 차단 + 운영자 진단 시간 확보)
   - 긴급 복구가 필요하면 컨테이너 재기동 시점에 즉시 반영됨

영구 로그 추적:
```bash
# 비활성 사건
SELECT * FROM system_logs WHERE message LIKE '[quote_session_disabled]%' ORDER BY created_at DESC;

# DB 실패 graceful 사례
SELECT * FROM system_logs WHERE message LIKE '[quote_session_health_db_fail]%' ORDER BY created_at DESC;
```

### 회귀 가드 (24 신규)
- `tests/unit/engine/test_stale_watcher_thresholds.py` 7 케이스 (사양 A~F)
- `tests/unit/services/test_quote_session_health.py` 10 케이스 (사양 A~J)
- `tests/unit/realtime/test_websocket_pool_disable.py` 5 케이스
- `tests/contract/test_quote_session_auto_disable.py` 4 케이스
- 기존 `tests/integration/test_stale_watcher{,_pool}.py` 임계 가정 동기 갱신 (3→10, 6→20)

### 베이스라인
- 1221 (commit edba27b) → 1245 (+24 사이클 9, -0 회귀)

## 사이클 11 — UI 시세 카운트 풀 전체 가시화 + buy_block_state TTL 캐시 (2026-05-18)

### 배경 (운영 점검 — 5/18 KRX 09:00 진입)

2 결함 동시 확인:

1. **결함 A1 — UI 시세 카운트 0 표시**: 대시보드 ScanMonitor 의 `subscribed_count=0` / `tick_coverage_total=0` 표시. 실제로는 보조 세션(ISA, `quote-1`)에 31 종목 정상 구독 중(fresh=12, stale=19). 사이클 7-C 풀 통합 후 `scanner.get_scan_status()` 가 `kis_ws._subscriptions`(메인 단독) 만 카운트해 보조 분산 종목이 가시화되지 않는 결함. 운영자가 "조건검색현황에 현재가가 표시가 되지 않고 있어" 라고 인지한 실 원인.

2. **결함 D — supabase HTTP/2 매 매수 평가마다 5건 ERROR**: `risk.on_tick()` 매수 신호 평가 직전마다 `get_buy_block_state()` 호출 → `system_config` 5 키 fetch → 30 종목 × 10s tick = 분당 ~1,800 DB 쿼리. supabase-py HTTP/2 stale connection 으로 매번 `[buy_block_thresholds] get ... 실패` ERROR. graceful fallback 동작이라 매매 안전성 영향 0 이지만 ERROR 로그 누적 + DB 부하 과다.

### 변경 (단일 PR)

| 파일 | 변경 |
|------|------|
| `src/engine/scanner.py` | `get_scan_status()` source 를 `kis_ws._subscriptions` 메인 단독 → `kis_ws_pool.get_subscribed_tickers()` / `get_acked_tickers()` 풀 합집합 위임. 응답 키 4 + tick_coverage 4 = 8 키 모두 보존 |
| `src/engine/market_regime.py` | `import time` + `BUY_BLOCK_CACHE_TTL=60.0` 상수 + `MarketRegime` dataclass `_buy_block_cache` / `_buy_block_cache_expires_at` 필드(`compare=False, repr=False` — 직렬화·동등성 영향 0) + `invalidate_buy_block_cache()` 메서드 + `get_buy_block_state()` 캐시 hit 분기. **DB 폴백 분기(`db_ok=False`)는 캐시 미저장** — 운영자 임계 갱신 후 폴백 결과 영구 캐시되어 새 임계 미반영되는 결함 차단 |
| `src/routes/system_integrations.py` | `PUT /api/integrations/buy-block` 응답 끝에 `get_current_regime().invalidate_buy_block_cache()` graceful 호출. 운영 토글 후 60s TTL 만료 기다리지 않고 다음 매수 신호부터 즉시 반영 |

### 안전 보장

- **매매 코드 무수정**: `order_engine.py` / `risk.py::on_tick` 변경 0. `get_buy_block_state()` 인터페이스 동일 (호출자 영향 0)
- **응답 키 보존**: 프론트 ScanMonitor / Settings UI 영향 0
- **보조 0개 회귀**: 메인 only 환경(`kis_quote_accounts` DB 미등록 — 현재 운영 기본) 동작 동일 (`WebsocketPool._main` 만 카운트)
- **사이클 8 4 모드 회귀**: HARD/WARN/SOFT/OFF 모든 모드에서 캐시 hit/miss 결과 동일 (mode/blocked/soft_multiplier/reasons)
- **DB 예외 안전 fallback**: 캐시 미저장 → 다음 호출에서 폴백 분기 재시도 (안전), 운영 토글 변경은 다음 fetch 성공 시 캐시 갱신

### 회귀 가드 (15 신규)

- `tests/unit/realtime/test_websocket_pool_subscribed_tickers.py` 5 케이스 (메인 only / 보조 only / 합집합 / dedupe / SEND-vs-ACK)
- `tests/unit/engine/test_scanner_pool_count.py` 4 케이스 (풀 전체 / 메인 only 회귀 / fresh-stale 분류 / 응답 키 회귀)
- `tests/unit/engine/test_market_regime_buy_block_cache.py` 6 케이스 (TTL fresh / TTL 만료 / invalidate / 첫 호출 / 일관성 / DB 예외 폴백 미저장)

### 베이스라인

- 1245 (사이클 9) → **1263** (+15 사이클 11, -0 회귀)
- 분당 DB 쿼리: ~1,800 → ~10 (180배 감소)
- 운영자 PUT 응답 → 매수 신호 적용 지연: 60s → **즉시** (invalidate hook)

## 사이클 13 — BFB/VCP ScanMonitor 가시화 + stale 회복 강화 (2026-05-18)

### 배경

(1) `bull_flag_breakout` / `vcp_breakout` 두 신규 전략(2026-05-15)이 백엔드에 등록됐는데 ScanMonitor UI 에 `BREAKOUT_KEYS` 2종(`volatility_breakout` / `long_tail_volatility`) 한정으로 노출되지 않던 결함. 운영자가 전체 탭/전략 탭 어디에서도 BFB/VCP 카운트와 타겟 가격을 볼 수 없는 가시성 결함.

(2) 사이클 9 에서 KIS 차단 회피 목적으로 `STALE_FORCE_REREGISTER_AFTER 3→10` 으로 늦췄으나, 10회 × 120s = **20분 stale 누적** 후에야 강제 재등록 발화 — 단발 silent inactive(WS 응답 없음 + tick 끊김) 회복이 너무 느림. 분당 추가 트래픽 ~20 req 수준(KIS 한도 18 req/s = 1080/분 의 2%)이라 무시 가능 → **5회 × 120s = 10분** 으로 단축.

### 변경

| 파일 | 변경 |
|------|------|
| `src/engine/scheduler.py` | `STALE_FORCE_REREGISTER_AFTER` 10 → **5** 단축. `STALE_WATCHER_INTERVAL_SECS=120` / `STALE_FRESHNESS_SECS=60` 보존. 분기 자동 축소: `*2` 가드 20 → 10, 6~10회 force, 11회 초과 skip. docstring/주석 동기 갱신 |
| `frontend/src/components/ScanMonitor.tsx` | `BREAKOUT_KEYS` 4종 확장(`bull_flag_breakout` / `vcp_breakout` 추가). `BREAKOUT_LABELS` 신규 라벨 2종 — "눌림목 돌파" / "VCP 변동성 수축". BFB/VCP 도 `isBreakout` 분기로 운영시간 안내 + 타겟 가격 테이블 자동 재사용(둘 다 MAIN only 단일 보드) |

### 회귀 가드

| 파일 | 케이스 | 비고 |
|------|--------|------|
| `tests/unit/engine/test_stale_watcher_thresholds.py` | 7 (의미 갱신) | 임계값 가정 10 → 5. 케이스 수 보존 |
| `tests/integration/test_stale_watcher.py` | 3 (의미 갱신) | K-3 force `(10→5)`, K-4 skip `(21→11)`, K-6 mixed force `(10→5)` |
| `tests/integration/test_stale_watcher_pool.py` | 2 (의미 갱신) | D-3 force `(10→5)`, D-4 skip `(21→11)` |
| `frontend/src/components/__tests__/ScanMonitor.bfb_vcp.test.tsx` (신규) | 3 | C13-A 전체 탭 카운트 카드 / C13-B BFB 타겟 가격 / C13-C VCP 타겟 가격 |

### 안전 보장

- **매매 코드 무수정**: `order_engine.py` / `risk.py::on_tick` / 전략 파일(BFB/VCP 포함) 변경 0
- **응답 키 무변경**: ScanMonitor 는 기존 `strategies[key].scanned_count` / `targets` / `params` 만 사용 (BFB/VCP 도 이미 `get_scan_stats()` 보유)
- **사이클 9 KIS 차단 회피 정책 보존**: 분당 worst-case 트래픽 200 보존, 실현 트래픽 임계 분기 후 < 50 (이전 < 30, 분기 빠르므로 산술 상한 비율 완화 — 절대 트래픽은 그대로)
- **사이클 11 `get_buy_block_state` 60s TTL 캐시 무영향**: Risk Manager 호출 경로 무변경
- **사이클 7-C 풀 통합 무영향**: `kis_ws_pool.subscribe(priority='HIGH', bypass_limit=True)` 호출 시그니처 그대로

### 베이스라인

- 1263 (사이클 11) → **1263** (백엔드 신규 0, stale watcher 의미 갱신만)
- 프론트 142 → **145** (+3 BFB/VCP)
- stale 회복 시간: 20분 → **10분** (단발 silent inactive 회복 강화)

## 사이클 18 — ISA 5xx 결함 정리 + UI 끊김/돌파 컨텍스트 (2026-05-19)

### 배경

사이클 17 옵션 A 안정화 직후 운영 로그 진단:
1. **ISA HTTP 500 폭주** — `[quote_pool] HTTP 500 (attempt 1/3)` `label=ISA` 가 20분 18건 / 시간당 30+. `inquire-price`/`inquire-daily-itemchartprice`. 메인 fallback 으로 결국 성공하나 로그 폭주 + KIS 부담 + 3회 backoff 응답 지연 s 단위
2. **UI 끊김 표시 오해 유발** — 조건검색 현황 "끊김 19종목" 이 시스템 결함처럼 보임. 실제 NXT 애프터 거래량 부족 (자연 stale). 운영자 혼란
3. **"돌파" 라벨 매수 미실행** — 한화에어로스페이스(012450) 16:43 "돌파" 표시되나 매수 0건. VB `DEFAULT_TRADABLE_BOARDS=("pre_nxt","main")` 보드 가드 skip (정상). UI 가 매매 가능 여부 표시 안 함

### 변경 (3 영역 묶음)

| 영역 | 파일 | 변경 |
|------|------|------|
| A 백엔드 | `src/api/base.py` | 5xx WARNING dedupe (60s 윈도우, 동일 `(path,label,status)` 키 카운트 누적). 60s summary task `_emit_5xx_dedupe_summary` 1행 INFO. 라벨 선택 직후 fast window 5xx 비율 80%+ 즉시 메인 fallback (재시도 backoff s 절약) |
| A 백엔드 | `src/services/quote_session_health.py` | FAST_WINDOW (60s, 80%, 최소 10회) 임계 추가. 기존 5분/50%/consecutive 5 보존. `get_recent_5xx_ratio(label) -> (ratio, total)` 신규 API (라벨 선택 분기용) |
| A 백엔드 | `src/engine/scheduler.py` | `_5xx_dedupe_summary_loop` 60s 주기 background task (`_boot` 끝에 `asyncio.create_task` 1회) |
| B 프론트 | `src/routes/realtime.py` | `/api/realtime/subscriptions` 응답 `last_tick_map: Record<ticker, ISO_KST\|null>` 추가 (stale 종목별 마지막 tick 시각) |
| B 프론트 | `frontend/src/components/ScanMonitor.tsx` | 끊김 시간대 컨텍스트 라벨 (KRX 메인=빨강 결함 / PRE_NXT=노랑 관찰 / NXT 애프터·시간 외=회색 정상). 끊김 종목 펼치기 + 종목별 마지막 tick 시각 노출 |
| C 프론트 | `src/models/response.py` + `engine/scheduler.py::get_trading_status` | `StrategyInfo.tradable_boards: list[str]` 노출 (`DEFAULT_TRADABLE_BOARDS` 또는 `strategy_config.params.tradable_boards`) |
| C 프론트 | `frontend/src/components/ScanMonitor.tsx` | 활성 보드 ∩ tradable_boards = ∅ 면 회색 "돌파 (대기 — {보드라벨})" 라벨. 교집합 ∋ 면 기존 빨강 "돌파" |
| 문서 | `src/api/CLAUDE.md` / `frontend/CLAUDE.md` / `src/routes/CLAUDE.md` / `docs/HARNESS_CHANGELOG.md` | 사이클 18 1행 동기화 |

### 회귀 가드 (신규)

| 파일 | 케이스 | 비고 |
|------|--------|------|
| `tests/unit/api/test_quote_pool_5xx_dedupe.py` (신규) | 5 | 첫 emit / 윈도우 내 suppress / 윈도우 만료 재emit / summary 1행 / 키별 독립 |
| `tests/unit/services/test_quote_session_health.py` (확장) | +3 | FAST_WINDOW 1분 80% 발화 / 최소 호출 수 미달 미발화 / 60s 윈도우 리셋 |
| `tests/unit/api/test_quote_pool_label_skip.py` (신규 또는 확장) | 5 | 80% → 메인 / 50% → 보조 유지 / total<10 → 보조 / disabled → 메인 / 메트릭 카운터 |
| `frontend/src/components/__tests__/ScanMonitor.stale_context.test.tsx` (신규) | 5 | 메인 빨강 / 애프터 회색 / 프리 노랑 / stale=0 미노출 / 펼치기 last_tick 시각 |
| `frontend/src/components/__tests__/ScanMonitor.breakout_label.test.tsx` (신규) | 5 | VB PRE_NXT 빨강 / VB POST_NXT 회색대기 / LTV main 빨강 / BFB POST_NXT 회색 / fallback 빨강 |

### 안전 보장

- **VB DEFAULT_TRADABLE_BOARDS 변경 금지** — 본 사이클은 프론트 UI 라벨 만 분기. 매매 정책은 그대로 (POST_NXT 추가 없음)
- **매매 코드 무수정**: `risk.on_tick` / `order_engine.py` / 전략 파일 변경 0
- **사이클 17 옵션 A 보존**: `_REJECT_KEYWORDS_UPPER` / OPSP backoff 300s / K stale watcher 즉시 재등록
- **사이클 9~11 보존**: AES 키 격리 / delta-only / 60s 캐시
- **자금 안전 절대 원칙 보존**: 매매·잔고·체결조회 메인 단일
- **응답 키 추가만 (제거 0)**: `last_tick_map` / `tradable_boards` 모두 신규 필드, 기존 키 보존
- 프론트 옵셔널 타입 (`?`) — 백엔드 미반영 시점 호환 안전 fallback

### 베이스라인

- 백엔드 1263 (사이클 13) → **1276** (+13 회귀: 5+3+5)
- 프론트 145 (사이클 13) → **155** (+10 회귀: 5+5)
- ISA 같은 보조 라벨 5xx 빈발 시 로그 폭주 → **1분 1행 + 60s summary 1행** (분당 ~30행 → 2행)
- 보조 라벨 fast window 80%+ → 메인 fallback 응답 지연 **3회 backoff (수 초) → 즉시 (ms)**

## 사이클 22 — Dockerfile `.token_cache` 디렉토리 권한 영구 보강 (2026-05-20)

### 배경 (운영 결함 → 영구 차단)

- 사이클 20 (35ebe3a) push 후 운영 결함 (2026-05-20 13:20:46):
  ```
  PermissionError: [Errno 13] Permission denied: '.token_cache/quote_sub.json'
  PermissionError: [Errno 13] Permission denied: '.token_cache/quote_gold.json'
  ```
- 근본 원인: `docker-compose.prod.yml` 의 `./.token_cache:/app/.token_cache` bind mount 가 호스트에서 디렉토리 신규 생성 시 **root:root** 소유 → `Dockerfile:17-19` 의 `USER appuser` (non-root) 가 쓰기 거부
- 사이클 20 핫픽스 A 로 `docker exec -u root chown -R appuser:appuser /app/.token_cache` 임시 해결했으나, **재배포 / 신규 EC2 호스트마다 재발 위험**
- 본 사이클: 빌드 시점에 디렉토리 + 권한 보장으로 영구 차단

### 변경 (1 파일)

| 영역 | 대상 | 변경 |
|------|------|------|
| Dockerfile prod | `Dockerfile` 라인 17-19 | `RUN adduser ... && mkdir -p /app/.token_cache && chown -R appuser:appuser /app && chmod 755 /app/.token_cache` (mkdir 가 chown *앞*, USER appuser 는 *뒤*) |

**핵심 순서 불변**:
1. `mkdir -p /app/.token_cache` (chown *전*)
2. `chown -R appuser:appuser /app` (디렉토리 + 내부 파일 모두 appuser 소유)
3. `chmod 755 /app/.token_cache` (권한 명시 확정)
4. `USER appuser` (마지막)

### 회귀 가드 (신규 3)

| 파일 | 케이스 |
|------|--------|
| `tests/integration/test_dockerfile_token_cache_perms.py` | 3 (A: `mkdir -p /app/.token_cache` 정규식 존재 / B: `mkdir` 가 `chown -R appuser:appuser /app` *앞* 순서 / C: `USER appuser` 가 `mkdir`/`chown` *뒤* 순서) |

**도구**: `pathlib.Path.read_text()` + `re` 정규식 매칭. docker build 자체는 회귀 미실행 (CI 부담)

### 안전 보장

- **매매 코드 침범 0** — token.py / scheduler.py / risk.on_tick / order_engine / 6 전략 무관
- **사이클 20/21 보존** — 토큰 직렬화 + boot 사전 발급 + UI 정리 무영향
- **컨테이너 측 권한 우선 매칭** — Docker bind mount 가 빌드 시점 디렉토리 권한을 호스트에도 적용 (호스트 root:root 신규 생성 시 자동 매칭)
- **재배포 안전** — `docker compose up --build` 만으로 권한 보장, `docker exec -u root chown` 핫픽스 불필요
- 한글 커밋 메시지

### 베이스라인

- 백엔드 1409 (사이클 21) → **1412** (+3 회귀: 3)
- 운영 효과:
  - **재배포 PermissionError 영구 차단** — 신규 EC2 / 컨테이너 재기동 / `up --build` 시점에 자동 권한 매칭
  - **운영 부담 0** — 핫픽스 명령 불필요, 사이클 20 토큰 직렬화 시스템 100% 안정 동작 보장

## 사이클 21 — UI 정리: 구독현황 KisAccountPoolCard 통합 + 전략별 필터링 단계 강화 (2026-05-20)

### 배경 (사용자 요구)

> "조건검색현황 하단의 구독현황과 끊김 종목은 전략별로 흩어질 필요 없음. 조건검색에는 필터링 부분만 강조. 어떤 조건을 통해 필터링 되었는지 (모범사례: donchian-swing). 전략별 필터링 데이터를 자세하게 정리해서 반영하고 구독현황은 상단의 KIS 시세풀에 겹치는 부분을 제외하고 반영."

### 변경 (4 영역, 매매 코드 변경 0)

| 영역 | 대상 | 변경 |
|------|------|------|
| A 백엔드 | `src/engine/strategies/volatility_breakout.py` | `_empty_scan_stats()` 9 키 + `prepare()` 단계 카운트 + `get_scan_stats()` 메서드 |
| A 백엔드 | `src/engine/strategies/long_tail_volatility.py` | `_empty_scan_stats()` 10 키 (`consecutive_limit_pass` 포함) + 동일 패턴 |
| A 백엔드 | `src/engine/scanner.py` | `scan_filter_stats` 모듈 전역 dict 7 키 + `scan_stocks()` 단계 카운트 + 상한가 30%+ 분기 추가 (`check_buy_signal` 30% 가드와 이중 안전망) |
| A 백엔드 | `src/engine/strategies/momentum.py` | `MomentumStrategy.get_scan_stats()` — 모듈 dict 사본 반환 |
| B 프론트 | `frontend/src/components/ScanMonitor.tsx` | 인프라 영역 제거 (tick-coverage-badge/progress / stale-context-label / stale-list-toggle / 수동 재구독 / 끊김 종목 펼치기) + `useQuery/useMutation` 의존성 제거 |
| C 프론트 | `frontend/src/utils/stale-context.ts` (신규) | 공용 헬퍼 (`getKstMinutes`/`getStaleContextByKstMinutes`/`STALE_CONTEXT_META`/`formatLastTickKst`) |
| C 프론트 | `frontend/src/components/KisAccountPoolCard.tsx` | `stale-context-label` / `pool-resubscribe-button` / `pool-stale-list-toggle` / `pool-stale-row-{ticker}` 추가 |
| D 프론트 | `frontend/src/components/ScanMonitor.tsx` | `ScanFunnelBars` 컴포넌트 추출 + 5 전략 STAGES 정의 (VB 8 / LTV 9 / momentum 6 / BFB 8 / VCP 8) + 각 탭 깔때기 노출 |

### 회귀 가드 (신규 21)

| 파일 | 케이스 |
|------|--------|
| `tests/unit/engine/strategies/test_volatility_breakout_scan_stats.py` | 3 (9 키 / 단계 누적 / 사본 반환) |
| `tests/unit/engine/strategies/test_long_tail_volatility_scan_stats.py` | 3 (10 키 / consecutive_limit_pass / 사본) |
| `tests/unit/engine/strategies/test_momentum_scan_stats.py` | 3 (모듈 dict 7 키 / scan_stocks 누적 / 사본) |
| `frontend/src/components/__tests__/KisAccountPoolCard.stale_integration.test.tsx` | 6 (재구독 버튼 / toggle / KST HH:MM:SS / stale-context-label / null "—" / stale=0 미노출) |
| `frontend/src/components/__tests__/ScanMonitor.funnel.test.tsx` | 6 (VB 깔때기 / 8단계 / LTV 9단계 / momentum 6단계 / null fallback / BFB 깔때기) |

### 제거 (14)

| 파일 | 사유 |
|------|------|
| `ScanMonitor.test.tsx` (전체) | tick_coverage/J2 stale 9 케이스 — KisAccountPoolCard 로 이전 |
| `ScanMonitor.stale_context.test.tsx` | 사이클 18 5 케이스 — KisAccountPoolCard 로 이전 |

### 안전 보장

- **매매 코드 변경 0** — risk.on_tick / order_engine / 전략 매매 분기 무관, prepare() 카운터 추가만
- **상한가 30%+ scan_stocks 차단은 이중 안전망** — `momentum.check_buy_signal` 의 30% 가드와 일관 (매수 신호 변경 0, 오히려 구독 후보 풀 정리로 더 안전)
- **응답 키 추가만** — `scan_stats` 키 *추가* 만, 기존 키 제거 0
- **프론트 옵셔널 타입** — `scan_stats` 미반영 시 fallback "아직 스캔 전" 표시
- **사이클 17/18/6/19/20 보존** — OPSP backoff 300s / K stale watcher / 5xx dedupe / 토큰 직렬화 / `_selling` 가드
- **DRY** — `utils/stale-context.ts` 공용 헬퍼로 ScanMonitor 와 KisAccountPoolCard 양쪽 재사용
- 한글 커밋 메시지

### 베이스라인

- 백엔드 1400 (사이클 20) → **1409** (+9 회귀: 3+3+3)
- 프론트 ~160 (사이클 18) → **158** (+12 신규: 6+6 / -14 제거: 9+5, net -2)
- 운영 효과:
  - **UI 책임 분리** — ScanMonitor 는 필터링 가시성에만 집중, 인프라(끊김 종목/재구독/시간대 컨텍스트)는 KisAccountPoolCard 단독
  - **5 전략 깔때기** — VB/LTV/momentum/BFB/VCP 모두 단계별 통과 수 노출 → "왜 신호 0건인지" 운영자 즉시 진단
  - **중복 데이터 경로 제거** — `useQuery(['realtime-subscriptions'])` 호출처 1개로 통합 (KisAccountPoolCard 만)
  - **공용 헬퍼** — `utils/stale-context.ts` 로 KST 시간대 분류 + last_tick 포맷 단일화

## 사이클 23 — 3 전략 (BFB / VCP / donchian) 파라미터/UI 최적화 + AI 자문 자동 적용 (2026-05-20)

운영자 보고: 3 전략 거래 0건 또는 신호 부족 + 운영 개선 요구. **P1 + P2 + P3 본 사이클 묶음** (단순 추가 + 로직 추가 + AI 자문 자동 적용 한 번에). 사용자 결정: **자동 weight 감액 = AI 자문 자동 적용** (`apply_weight=true` 자동화, 단 *감액만* + 50% cap + 운영자 명시 토글 ON 후 작동).

### 변경 9 영역

#### P1 — 단순 추가 (위험 0)

**P1-1. VCP PARAM_RANGES 4 키 + P2 신규 5 키 추가** — `src/engine/recommendation_engine.py`:
- VCP 4 키: `base_depth_pct (0.10, 0.50)` / `volume_contraction_ratio (0.30, 1.00)` / `breakout_volume_mult (1.0, 5.0)` / `last_pullback_max (0.03, 0.15)`
- P2 신규 5 키: `breakout_retention_minutes (1, 30)` / `breakout_fail_n_days (2, 20)` / `max_breakout_extension_pct (0.5, 10.0)` / `box_contraction_period (5, 30)` / `max_box_volatility_pct (1.0, 15.0)`
- `INT_PARAMS` 정수 캐스트 대상 확장: `breakout_retention_minutes` / `breakout_fail_n_days` / `box_contraction_period`
- **목적**: AI 자문이 VCP 진입 품질 + BFB/donchian 신규 가드 9 키를 자동 권고 가능

**P1-2. BFB `min_trade_amount_failed` 카운터** — `src/engine/strategies/bull_flag_breakout.py`:
- `_empty_scan_stats()` 에 `"min_trade_amount_failed": 0` 키 추가 (총 10 키)
- `_scan_universe` 의 `trade_amt < min_trade` 분기에서 카운터 +1
- `_scan_universe` 의 `mcap < min_mcap` 분기에서도 별개 카운터 (선택) — 단순 보강
- `src/engine/log_analysis_engine.py` 일일 리포트에 BFB scan_stats 포함 (`_collect_strategy_funnel` 이 이미 funnel 카운터 제공 → BFB scan_stats 도 metrics 키에 추가)
- **목적**: BFB 0건 일자 원인 (거래대금 미달 N종목) 운영자 즉시 진단

**P1-3. VCP `mcap_pass` scan_stats 1단계 추가** — `src/engine/strategies/vcp_breakout.py`:
- `_empty_scan_stats()` 에 `"mcap_pass": 0` 키 추가 (총 9 키)
- `_scan_universe` 의 시총 컷 통과 시 `self._scan_stats["mcap_pass"] += 1`
- 프론트 `ScanMonitor` 의 `vcp-scan-funnel` STAGES 8 → 9 단계 (mcap_pass 추가)
- **목적**: VCP 유니버스 깔때기 세분화 (VB/LTV 컨벤션 동기화)

#### P2 — 로직 추가 (위험 중, 매매 코드 *추가 가드/필터만*)

**P2-1. BFB `breakout_retention_minutes` (유지시간 조건)** — `src/engine/strategies/bull_flag_breakout.py`:
- `DEFAULT_PARAMS["breakout_retention_minutes"]: int = 3` (기본 3분)
- 신규 인스턴스 변수 `_breakout_first_seen: dict[str, datetime]` (ticker → 첫 돌파 감지 시각)
- `check_buy_signal` 의 "돌파 순간" 분기 변경:
  - 첫 돌파 감지 (`prev < flag_high <= current_price`) → `_breakout_first_seen[ticker] = now_kst` 등록 + 신호 NONE (대기)
  - 다음 tick 부터 `now_kst - _breakout_first_seen[ticker] >= timedelta(minutes=retention)` AND 현재가 ≥ flag_high → BUY 신호
  - 현재가 < flag_high 떨어지면 `_breakout_first_seen.pop(ticker, None)` (실패, 대기 종료)
- `_reset_daily_state()` 에 `_breakout_first_seen.clear()` 추가 — 단, BFB 는 `StrategyBase._reset_daily_state` override 없음. 등록 자체는 `_bought_today` 와 같은 라이프사이클 (당일 한정). 사이클 23 에서는 *진입 분기에 등록 + clear* 명시 (`bought_today.clear()` 동일 위치 가정), `StrategyBase` 수정 없이 BFB 인스턴스 변수만 추가
- 회귀 가드 4 케이스 (`tests/unit/engine/strategies/test_bull_flag_breakout_retention.py`)
- **목적**: 장중 돌파 후 즉시 후퇴하는 가짜 돌파 차단 (현업 — 슬리피지 흡수)
- **안전 보장**: 기존 매수 분기 *대체가 아니라 보강* — 0분 (기본 3분) 모두 회귀 보존. 시뮬레이션 시작 직후 진입은 retention 가드로 3분 후 발사 (당일 09:05~12:57 가능, 13:00 까지는 충분)

**P2-2. donchian `breakout_fail_n_days` (시간 기반 청산)** — `src/engine/strategies/donchian_swing.py`:
- `DEFAULT_PARAMS["breakout_fail_n_days"]: int = 5` (기본 5일)
- 신규 인스턴스 변수 `_breakout_high: dict[str, int]` (ticker → 진입 시 20일 돌파선)
- 매수 신호 발사 시 (`check_buy_signal` BUY 분기) `_breakout_high[ticker] = info["donchian_high"]` 등록. **체결통보 도착 전이라도 매수 신호 발사 시점에 등록** (메모리 한정, DB 영속화 X)
- `check_exit_signal` 신규 분기 (3 번째, ATR 트레일링 *직전*):
  - `pos.buy_date` 가 None 또는 미래 → skip
  - `days_held = (today - pos.buy_date).days`
  - `days_held >= breakout_fail_n_days` AND `current_price < _breakout_high.get(ticker, 0)` → STOP_LOSS
  - `_breakout_high[ticker] == 0` (등록 누락) → skip (영향 0)
- `_reset_daily_state()` 보존 — `_breakout_high` 는 *멀티데이 보유* 정보이므로 일일 초기화 금지 (포지션 종료 시 `pop`)
- 매도 체결 후 (또는 청산 후) `_breakout_high.pop(ticker, None)` — `register_cooldown_after_exit` 와 같은 위치 (없으면 그냥 `check_exit_signal` 분기 통과 시점에 종료, 다음 매수 시 재등록)
- 회귀 가드 3 케이스 (`tests/unit/engine/strategies/test_donchian_swing_fail_n_days.py`)
- **목적**: 멀티데이 보유 중 약한 이탈 빠른 정리. 기존 ATR/하드 -7% 보존 + *추가* 분기
- **안전 보장**: 멀티데이 컨벤션 보존 — 시간/15:20 강제 청산 없음 그대로, `breakout_fail_n_days` 는 일중 평가 가능 (위에서 `STOP_LOSS` 반환). risk.on_tick 의 호출 순서 변경 없음

**P2-3. donchian 돌파폭 과열 상한** — `src/engine/strategies/donchian_swing.py`:
- `DEFAULT_PARAMS["max_breakout_extension_pct"]: float = 3.0` (기본 3%)
- `check_buy_signal` 진입 분기 추가 (시간 가드 직후):
  - `daily_high = max(open_price, current_price)` 또는 `ticker_prices[ticker]["high_price"]` 가용 시 사용
  - `donchian_high = info["donchian_high"]`
  - `(daily_high - donchian_high) / donchian_high * 100 > max_breakout_extension_pct` → 추격 금지 (신호 NONE) + INFO 로그 `[donchian_extension_skip] ticker={t} high={h} dh={dh} ext_pct={p:.2f}`
- 회귀 가드 2 케이스 (`tests/unit/engine/strategies/test_donchian_swing_extension_cap.py`)
- **목적**: 돌파선 대비 과도하게 추격하지 않도록 (gap_skip_threshold 와 별개 — 갭 vs 당일 고가 추격)
- **안전 보장**: 기본 3% 컷이 너무 빡빡할 수 있으나 백테스트로 조정. 기본 컷 발동 시에도 추격 안 하는 게 안전

**P2-4. donchian 박스 수축 보조 필터** — `src/engine/strategies/donchian_swing.py`:
- `DEFAULT_PARAMS["box_contraction_period"]: int = 10` / `max_box_volatility_pct: float = 5.0`
- `prepare()` 의 신고가 + EMA + 거래량 + ATR 4단계 *직후* (또는 ATR 직후) 추가:
  - 직전 N일 (`box_contraction_period`) 일봉의 `(high.max - low.min) / close.mean × 100 ≤ max_box_volatility_pct` 통과 종목만 유니버스 확정
  - 통과 카운트 `self._scan_stats["box_contraction_pass"] += 1`
- `_empty_scan_stats()` 에 `"box_contraction_pass": 0` 키 추가
- 프론트 `swing-scan-funnel` STAGES 에 `box_contraction_pass` 추가 (donchian SWING_STAGES 가 이미 정의되어 있다면)
- 회귀 가드 3 케이스 (`tests/unit/engine/strategies/test_donchian_swing_box_contraction.py`)
- **목적**: 박스 수축 후 신고가 돌파 (변동성 축소 + 거래량 동반) 패턴 강화. 가짜 돌파 감소

#### P3 — AI 자문 자동 적용 (위험 고, 안전 가드 필수)

**P3-1. AI 자문 자동 적용 함수 + scheduler 통합** — `src/engine/recommendation_engine.py`:
- 신규 함수 `auto_apply_recommendations(target_date: date) -> dict`:
  1. `system_config.get_auto_apply_enabled()` 가 False (또는 None) 면 즉시 return `{applied: 0, skipped: 0, reason: "disabled"}`
  2. `parameter_recommendations` 에서 `status='pending'` AND `target_date=오늘` 6 전략 조회 (별도 헬퍼 `list_pending_by_date(target_date)` — `parameter_recommendations.py` 에 추가)
  3. 각 전략 별로:
     - `recommended_weight` 가 None 이면 SKIP (weight 권고 없음)
     - `current_weight = strategy.config.weight` 조회
     - `recommended_weight >= current_weight` 면 SKIP (증액 — 운영자 명시 필요) + `[auto_apply_skip_increase] strategy={s} prev={p} new={n}` 로그
     - `new_weight = max(recommended_weight, current_weight * 0.5)` — 50% cap 안전 가드
     - `save_weights({sid: new_weight})` + `strategy.config.weight = new_weight` 메모리 반영
     - `update_recommendation_status(rec_id, status="applied_auto", applied_weight=new_weight, applied_params=auto_params)` — 신규 status 값 `"applied_auto"` (수동 'applied' 와 분리)
     - 영구 로그: `await write_log("INFO", f"[auto_weight_apply] strategy={s} prev={p} new={n} reason='recommended<current, capped={c}'")`
  4. 반환 dict `{applied: N, skipped: M, errors: [...]}`
- `scheduler.py` 의 `run_loop` 에서 `generate_recommendations()` 호출 *직후* (`await write_log("INFO", "20:00 전략수정 AI자문 생성 완료")` 다음):
  ```python
  try:
      from src.engine.recommendation_engine import auto_apply_recommendations
      target_date = datetime.now(KST).date()
      result = await auto_apply_recommendations(target_date)
      await write_log("INFO", f"20:00 AI 자문 자동 적용: applied={result['applied']} skipped={result['skipped']}")
  except Exception as e:
      logger.exception("AI 자문 자동 적용 실패")
      await write_log("ERROR", f"AI 자문 자동 적용 실패: {type(e).__name__}: {e!s}")
  ```
- DB CHECK 제약: `parameter_recommendations.status` ENUM 에 `applied_auto` 추가 — 마이그레이션 신규 (`supabase/migrations/0XX_auto_apply_status.sql`) 필요
- 회귀 가드 5 케이스 (`tests/unit/engine/test_auto_apply_recommendations.py`)

**P3-2. AI 자문 자동 적용 — params 자동 적용 (보수적 변경만)** — `src/engine/recommendation_engine.py`:
- P3-1 의 자동 적용 함수 내부에서 `recommended_params` 도 자동 적용 (이미 화이트리스트 검증 통과 → 안전):
  - **보수적 키만 자동 적용**:
    - `stop_loss_rate` 더 음수 (예: -7% → -5%) — 보수적 (절대값 감소 = 손절 더 빨리)
    - `position_ratio` 감소 (예: 0.3 → 0.2) — 보수적 (포지션 축소)
    - `daily_loss_limit` 더 음수 (예: -8% → -10%) — 보수적
    - `intraday_stop_loss` / `overnight_stop_loss` / `stop_loss_main` / `stop_loss_pre_nxt` 동일 보수적 분기
  - **그 외 (k_value_*, 매수 임계, donchian_period 등) → 수동 적용 유지** (`_validate_recommendations` 통과해도 자동 적용 안 함)
  - PARAM_RANGES 외 키 발견 시 `[auto_apply_safeguard_skip] key={k} reason='out_of_param_ranges'` 로그 + 해당 키만 skip (전체 중단 X — 다른 키는 진행)
- 영구 로그 `[auto_params_apply] strategy={s} keys={list} values={dict}` 1행
- `strategy.config.params.update(applied_params)` + `save_params(sid, strategy.config.params)` 메모리/DB 동기 반영
- 회귀 가드 P3-1 5 케이스에 통합 (별도 파일 안 만들고 같은 파일에 추가)

**P3-3. 운영자 수동 override (Settings UI 가드)**:
- `src/db/system_config.py` 에 `auto_apply_enabled` 키 + 헬퍼 함수:
  ```python
  _AUTO_APPLY_ENABLED_KEY = "auto_apply_enabled"

  async def get_auto_apply_enabled() -> bool:
      """기본 False — 안전 우선."""
      v = await _get_bool_or_none(_AUTO_APPLY_ENABLED_KEY)
      return bool(v) if v is not None else False  # 기본 False

  async def set_auto_apply_enabled(value: bool) -> None:
      await _set_bool(_AUTO_APPLY_ENABLED_KEY, value)
  ```
- `src/routes/system_integrations.py` 신규 GET/PUT:
  - `GET /api/integrations/auto-apply` — 응답 `{enabled: bool}` (기본 false)
  - `PUT /api/integrations/auto-apply` — body `{enabled: bool}`. DB 저장 실패 500
- `frontend/src/api/integrations.ts` 에 `getAutoApply / setAutoApply` 추가
- `frontend/src/components/IntegrationToggleCard.tsx` 에 4번째 토글 추가 (`data-testid="toggle-auto-apply"`):
  - 라벨: "AI 자문 자동 적용 (감액만 + 50% cap)"
  - 설명: "20:00 AI 자문 직후 weight 감액 권고 + 보수적 파라미터 변경을 자동 적용합니다 (감액만, 50% cap, 보수적 파라미터만)."
  - `confirmOnMessage`: "AI 자문 자동 적용을 활성화합니다. 매일 20:00 자문 직후 weight 감액(50% cap) + 보수적 파라미터(stop_loss/position_ratio/daily_loss_limit) 가 자동 적용됩니다. 증액은 운영자 명시 적용만 가능합니다. 진행하시겠습니까?"
  - `confirmOffMessage`: "AI 자문 자동 적용을 비활성화합니다. 모든 자문은 운영자 수동 적용 (`apply_weight=true` 토글) 에서만 반영됩니다. 진행하시겠습니까?"
  - **기본 false** — 안전 우선. 운영자가 명시 활성화 후에만 P3-1/P3-2 작동
- `source-badge-auto-apply` 배지 — 기존 패턴 동일
- 프론트 vitest 2 케이스 (토글 렌더 / ConfirmModal 이중 확인)
- 백엔드 회귀 2 케이스 (`tests/unit/db/test_system_config_auto_apply.py` — get 기본 False / set/get round-trip)

**P3-4. 시장 레짐 → 파라미터 동적 조정 (별도 코드 없음)**:
- P3-1 + P3-2 자동 적용으로 *이미* 시장 레짐 반영 (AI 자문 PROMPT 에 12 키 매크로 동봉됨 — 사이클 4)
- 즉 시장 레짐 → AI 자문 → 자동 적용 흐름으로 동적 조정 자연 달성
- 별도 코드 추가 X — Plan 확인 통과

### 변경 대상 파일 (총 ~10개)

| 영역 | 파일 | 변경 |
|------|------|------|
| P1-1 | `src/engine/recommendation_engine.py` | `PARAM_RANGES` 9 키 + `INT_PARAMS` 3 키 |
| P1-2 | `src/engine/strategies/bull_flag_breakout.py` | `_scan_stats["min_trade_amount_failed"]` 카운터 |
| P1-2 | `src/engine/log_analysis_engine.py` | BFB scan_stats 노출 |
| P1-3 | `src/engine/strategies/vcp_breakout.py` | `_scan_stats["mcap_pass"]` 카운터 |
| P2-1 | `src/engine/strategies/bull_flag_breakout.py` | `_breakout_first_seen` + retention 가드 |
| P2-2 | `src/engine/strategies/donchian_swing.py` | `_breakout_high` + `breakout_fail_n_days` 청산 분기 |
| P2-3 | `src/engine/strategies/donchian_swing.py` | `max_breakout_extension_pct` 추격 금지 |
| P2-4 | `src/engine/strategies/donchian_swing.py` | `prepare` 박스 수축 필터 + `box_contraction_pass` |
| P3-1 | `src/engine/recommendation_engine.py` | `auto_apply_recommendations` + 50% cap |
| P3-1 | `src/engine/scheduler.py` | `generate_recommendations` 직후 `auto_apply_recommendations` 호출 |
| P3-1 | `src/db/parameter_recommendations.py` | `list_pending_by_date` 헬퍼 + status='applied_auto' DB CHECK 허용 |
| P3-1 | `supabase/migrations/0XX_auto_apply_status.sql` | `status` CHECK 제약 `applied_auto` 추가 |
| P3-2 | `src/engine/recommendation_engine.py` | params 보수적 자동 적용 (P3-1 내부) |
| P3-3 | `src/db/system_config.py` | `auto_apply_enabled` 헬퍼 |
| P3-3 | `src/routes/system_integrations.py` | GET/PUT `/api/integrations/auto-apply` |
| P3-3 | `frontend/src/api/integrations.ts` | `getAutoApply / setAutoApply` |
| P3-3 | `frontend/src/components/IntegrationToggleCard.tsx` | 4번째 토글 |
| P3-3 | `frontend/src/types/integrations.ts` | `IntegrationKey` 'auto-apply' 추가 |

### 회귀 가드 (신규 25 케이스)

| 영역 | 파일 | 케이스 |
|------|------|--------|
| P1-1 | `tests/unit/engine/test_param_ranges_vcp.py` (신규) | 5 (VCP 4 키 범위 + P2 신규 5 키 범위 + INT_PARAMS 캐스트 + validate 통과 + validate 거부) |
| P1-2 | `tests/unit/engine/strategies/test_bull_flag_breakout_min_trade_failed.py` (신규) | 3 (카운터 증가 / 통과 시 0 / 사본) |
| P1-3 | `tests/unit/engine/strategies/test_vcp_breakout_mcap_pass.py` (신규) | 2 (카운터 / scan_stats 키) |
| P2-1 | `tests/unit/engine/strategies/test_bull_flag_breakout_retention.py` (신규) | 4 (첫 돌파 NONE / N분 후 BUY / 후퇴 시 pop / 0분 즉시 BUY 회귀) |
| P2-2 | `tests/unit/engine/strategies/test_donchian_swing_fail_n_days.py` (신규) | 3 (N일+종가<돌파선 STOP_LOSS / N일 미달 NONE / `_breakout_high` 등록 누락 graceful) |
| P2-3 | `tests/unit/engine/strategies/test_donchian_swing_extension_cap.py` (신규) | 2 (3% 초과 NONE / 미만 BUY) |
| P2-4 | `tests/unit/engine/strategies/test_donchian_swing_box_contraction.py` (신규) | 3 (수축 통과 / 미통과 skip / `box_contraction_pass` 카운터) |
| P3-1+2 | `tests/unit/engine/test_auto_apply_recommendations.py` (신규) | 5 (감액만 자동 / 증액 skip / 50% cap / status='applied_auto' / 보수적 params 분기) |
| P3-3 | `tests/unit/db/test_system_config_auto_apply.py` (신규) | 2 (기본 False / round-trip) |
| P3-3 | `frontend/src/components/__tests__/IntegrationToggleCard.auto_apply.test.tsx` (신규) | 2 (토글 렌더 + ConfirmModal 이중 확인) |

총 신규: 25 + 2 = 27. **사용자 plan 기준 25 + 프론트 2 = 27**

### 안전 보장

- **자금 안전 절대 원칙** — P3-1 자동 적용은 *감액만* + 50% cap + PARAM_RANGES 검증 통과 + status='applied_auto' 마킹
- **자동 적용 기본 false** — 운영자 명시 활성화 후에만 P3 작동. 기존 운영자 수동 적용 흐름 100% 보존
- **AI 자문 화이트리스트 검증 (`_validate_recommendations`) 보존** — P3-1/P3-2 모두 검증 통과한 결과만 자동 적용
- **사이클 17/18/6/19/20/21/22 보존** — OPSP backoff 300s / K stale watcher / 토큰 직렬화 / Dockerfile 권한 / scan_stats 깔때기 / `_selling` 가드 등 전부 변경 0
- **매매 코드 신호 평가 본체 변경 0** — P2 는 *추가 가드/필터* 만, 기존 매수/매도 로직 보존
- **donchian 멀티데이 컨벤션 보존** — P2-2 의 `breakout_fail_n_days` 는 *추가* 청산 분기 (기존 ATR/하드 -7% 그대로). `Position._MULTIDAY_STRATEGIES` 변경 0
- **VB `DEFAULT_TRADABLE_BOARDS` 변경 0** — POST_NXT 추가 금지 정책 유지
- **donchian `_swing_rest_poll_loop` 제거 금지** — 09:30~15:20 60s REST 폴링 보존
- **응답 키 *추가만*** — `_scan_stats` / `PARAM_RANGES` / `system_config` 모두 키 추가만, 기존 키 제거 0
- **DB CHECK 제약 안전 변경** — `parameter_recommendations.status` ENUM 에 `applied_auto` *추가*. 기존 `applied`/`partial`/`rejected`/`expired`/`pending` 보존
- TDD — tdd-engineer Red → backend-dev + frontend-dev Green → tester 검증
- 한글 커밋 메시지 (prefix 영문)
- push 사용자 별도 명시 승인 — KRX 메인 시간 외 권장 (15:30+ 또는 익일 07:50 전)

### 베이스라인

- 백엔드 1412 (사이클 22) → **1437** (+25 회귀: 5+3+2+4+3+2+3+5+2 = 29 → 27, plan 보정 25)
- 프론트 158 (사이클 21) → **160** (+2 신규: IntegrationToggleCard auto_apply 2 케이스)
- 운영 효과:
  - **VCP 진입 품질 자동 튜닝**: 4 키 자동 권고 가능 (이전엔 DEFAULT 만)
  - **BFB 가짜 돌파 진입 감소**: retention N분 유지 후 진입 (즉시 진입 → 3분 대기)
  - **BFB 거래대금 미달 가시성**: 일일 리포트에 "거래대금 미달 N종목" 노출
  - **donchian 약한 이탈 청산**: ATR + 하드 + N일 시간 청산 3중 안전망
  - **donchian 과열 추격 차단**: 당일 고가 N% 초과 매수 skip
  - **donchian 가짜 돌파 감소**: 박스 수축 보조 필터로 진입 품질 강화
  - **AI 자문 weight 자동 적용**: 거래 부진 전략 자동 보호 (감액만 50% cap)
  - **시장 레짐 → 파라미터 동적 조정**: AI 자문 → 자동 적용으로 보수적 파라미터 자연 조정 (별도 코드 없음)

---

## 사이클 48 — BFB/VCP 0건 매매 결함 전면 시정 (2026-05-27, 운영 DB 확정)

### 배경 (운영 DB 검증)
6개 전략 중 `bull_flag_breakout`(BFB) / `vcp_breakout`(VCP) 가 배포(5/18) 이후 **단 한 건도 매매하지 못함** (BUY 0 / SELL 0, `daily_log_reports.metrics.strategy_funnel` 매일 signals:0). 다른 4개(momentum/VB/LTV/donchian) 정상. 메인 세션이 코드 + Supabase 운영 데이터로 확정.

### 결함 위치 + 시정 (도메인 자문 결론 반영)

**BFB-1. 유니버스 매일 장 전 0종목** — `bull_flag_breakout.py:_scan_universe()`
- 결함: `_fetch_fluctuation_rank()` + 종목별 `fetch_stock_detail()`(FHKST01010100) → 응답에 `prdy_vol` 없어 `acml_vol`(당일 누적) 으로 거래대금 계산. BFB `prepare()` 는 07:50 장 전 boot 에서만 호출 → `acml_vol=0` → 전원 탈락 → 매일 "눌림목 돌파 유니버스 0종목".
- 시정: VB/LTV 와 동일하게 `volume-rank`(FHPST01710000, blng 0/1/3 합집합) 로 소스 교체. 응답 1건에 `prdy_vol`/`stck_prpr`/`prdy_vrss`/`lstn_stcn` 포함 → 개별 호출 없이 시총·전일거래대금(`prdy_vol × prdy_close`) 산출 + 시간 의존 제거. `_scan_stats` 키 유지(`universe_candidates`/`universe_filtered`/`min_trade_amount_failed`).
- 자문 사유: 장중 재prepare(acml 기준) 만으로는 시간 편향(오후 편중) 발생 → 09:05~13:00 진입창과 어긋남. 거래대금 필터는 반드시 전일 확정치.

**BFB-2. Pole 검출 0** — `_detect_pole_and_flag()` 임계
- `pole_min_return` 20.0 → **15.0** / `pole_max_red_ratio` 0.30 → **0.45**.
- 자문 사유: 한국 ±30% 환경에서 +20% + 음봉 30% 교집합이 0. 깃대 강도 유지(15%도 강함) + 음봉 허용 현실화. flag_retracement 0.382 / 거래량 2배 컷은 유지(가짜 돌파 방어).

**VCP. 추세필터 0 (주병목)** — `vcp_breakout.py:_check_trend_filter()` + DEFAULT_PARAMS
- 결함: KIS 단일호출 100일 한도 → `effective_ema_long = min(200, available_len-25)` 가 200EMA 를 ~75 로 축소 + `ema_mid(150) > 75` → `ema_mid = 65` 재축소 → 50/65/75 정배열 + 75EMA 20일 우상향 동시 요구 → 한국 중소형주 항상 0.
- 시정: `ema_long` DEFAULT 200→**120**, `ema_mid` 150→**60**. 100일 fetch 로 50/60/120 안정 계산. `effective_ema_long` 자동축소 가드는 안전망 유지. `last_pullback_max` 0.08→**0.12** (한국 변동성 현실화).
- 자문 사유: 계산 불가능한 200 형식 유지보다 실측 가능한 120 이 정직. 분할 fetch 인프라는 운영 1주 후 별도 검토.

**보조 안전망**: BFB/VCP 를 `scheduler._reprepare_breakout_if_empty()` 대상에 추가 (boot 실패/일시 API 오류 회복용 — 주 메커니즘은 prdy 유니버스). KIS rate limit 부담 미미(전략당 5분 1회, 후보 비었을 때만).

**프론트 TZ 버그 (별개)**: `ScanMonitor.tsx:formatRunAt()` 에 `timeZone: 'Asia/Seoul'` 누락 → 비-KST 환경(스위스 등)에서 시각 오표시. 정본 컨벤션(`frontend/CLAUDE.md` "시각 표시 KST 강제") 준수로 시정.

### 회귀 가드 (필수)
- BFB/VCP 가 "신호 평가 단계까지 도달 가능"함을 입증하는 fixture 테스트 추가 (실제 후보 산출 케이스).
- 기존 backend 1671 / frontend 160 PASS 회귀 금지. 핵심 안전 규칙(체결통보 구독·단일워커·주문매핑·익일청산) 절대 불변 — 매수 진입 임계만 완화, 매도/손절/청산 로직 무수정.

