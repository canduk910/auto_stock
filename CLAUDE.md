# CLAUDE.md — 프로젝트 루트

KIS OpenAPI 기반 주식 자동매매시스템. FastAPI(백엔드) + React(프론트엔드) + AWS RDS PostgreSQL(DB). 다중 전략 아키텍처.

> 디렉토리별 상세는 각 하위 `CLAUDE.md` 가 진실의 원천:
> `src/CLAUDE.md` · `src/engine/CLAUDE.md` · `src/engine/strategies/CLAUDE.md` · `src/api/CLAUDE.md` · `src/realtime/CLAUDE.md` · `src/db/CLAUDE.md` · `src/routes/CLAUDE.md` · `frontend/CLAUDE.md`
>
> 사이클별 변경 이력 (verbatim): [`docs/HARNESS_CHANGELOG.md`](docs/HARNESS_CHANGELOG.md)
> 시스템 흐름 도식: [`docs/architecture.md`](docs/architecture.md)

## 하네스: TDD-First Trading Team

**목표:** 모든 코드 변경을 Red→Green→Refactor 사이클로 강제하고, 변경 시 영향받는 테스트만 실행할 수 있는 정적 인덱스를 유지한다. *매매 의사결정의 깊이* 는 도메인 전문가의 사전 자문으로 보완하고, *코드 품질 드리프트* 는 리팩토링 전문가의 주기적 검토로 흡수한다.

### 기본 진입점 — `team-leader` 우선

사용자의 모든 요청은 1차로 `Agent({subagent_type: "team-leader"})` 로 라우팅한다. team-leader 가 트레이더 관점에서 해석 후 하위 에이전트에 분배한다.

- 코드 변경 → `auto-trading-orchestrator` 스킬 (TDD 사이클: `tdd-engineer` Red → `backend-dev`/`frontend-dev` Green → `tester` 검증)
- 매매 의사결정 자문 (신규 전략·파라미터·보드 행태·시장 레짐·KIS 거부 해석) → `domain-consult` 스킬 (`domain-expert` 에이전트) — Phase 2.5 명세 분해 *전* 또는 사이클 중 행위 영향 평가 시
- 주기적 리팩토링 검토 (사이클 5회 누적 또는 명시 요청) → `refactor-review` 스킬 (`refactor-expert` 에이전트) — Phase 4.5
- 단위/회귀 테스트 → `tdd-cycle` (백엔드 pytest+respx+freezegun / 프론트엔드 vitest+RTL+MSW)
- 영향 인덱스 → `test-impact-index`
- 통합/경계면/E2E/안전성 → `trading-test`
- KIS API 정본 스펙 (TR_ID·응답 구조·거부 코드) → `kis-mcp-query` 스킬 (backend-dev / tdd-engineer / tester / refactor-expert 공유)

**우회 허용 (메인 세션 직접 응답):** 단순 사실 질의, 단발 디버그/grep, 운영 환경 즉시 점검(EC2 SSH 등). 코드 변경 제안이 따라오면 다시 team-leader 로 인계.

### 모델 라우팅

| 작업 유형 | 모델 | 적용 |
|----------|------|------|
| 구현 계획·검수·리팩토링 검토 | **fable** | `team-leader`, `tester`, `refactor-expert` |
| 테스트 설계·도메인 자문 | **opus** | `domain-expert`, `tdd-engineer` |
| 일반 구현 (코드 작성·리팩터·버그 수정) | **sonnet** | `backend-dev`, `frontend-dev` |
| 명령어 작성 (bash/슬래시/스크립트) | **haiku** | 메인 세션 단발 작업 — fork 또는 `claude-haiku-4-5-20251001` 위임 |

### 하네스 변경 이력 (요약)

이 표는 **최근 ~15개 사이클의 한 줄 요약만** 유지한다. 각 행은 반드시 한 줄 — verbatim 금지. 신규 사이클 완료 시: (1) 이 표 상단에 한 줄 요약 1행 추가 + 가장 오래된 1행 제거(15행 유지), (2) 사용자 보고 verbatim·회귀 가드·영속 의무·검증 수치 등 상세는 [`docs/HARNESS_CHANGELOG.md`](docs/HARNESS_CHANGELOG.md) 에만 append.

| 날짜 | 사이클 | 한 줄 요약 |
|------|--------|-----------|
| 2026-07-31 | 사이클 E-1 지수ETF 레짐 신호 (관찰) | 사용자 지시 "최종 레짐판정에 dkstock뿐 아니라 지수ETF 고지로 스테이지도 고려" — domain-consult GO(다크런치 우선). KODEX200(069500)+코스닥150(229200) 일봉→`kojiro_indicators.ema/stage_of` 스테이지 계산(방어집합 {3,4,5}, 2일 연속 확인, OR 결합, 신선도 게이트). **dkstock 독립 신호**(다운 시 fallback = 프래질리티 완화). **E-1 = 관찰 전용 다크런치**(`etf_regime_enabled=False`, 계산+boot 로그+API 4필드 노출만, **매수 가드 행위 byte 동일·배제 0**). block 통합·SOFT 상한·reasons 태깅은 2주 관찰 후 E-2 인계. FREEZE 무관(stage_of 순수함수 재사용, 5/20/40 정체성 상수). 실측 검증 = 양지수 현재 stage4·whipsaw 60일 2~3회·dkstock=defensive 부합. 매매 안전성 8영역 diff 0, 백엔드 4,072 PASS |
| 2026-07-31 | 사이클 D 레짐 가드 무력 가시화 | dkstock.cloud 인증서 07-27 만료(`certificate has expired`) → 레짐 매수 가드가 4일간 silent 무력화됐으나 경보 0(대시보드 "정상+평온" 오인). 근본 결함 = `get_buy_block_state()` 가 "데이터 있고 평온"과 "데이터 없음(empty)"을 동일 `blocked=False,reasons=[]` 반환. 시정(관찰성 전용, 매매 행위 byte 동일): `MarketRegime.has_regime_data` + `BuyBlockState.data_available` + boot `[regime_guard_inert]` 경보(empty∧mode≠OFF) + API `guard_inert` + 프론트 red 무력 배너(`buy-block-guard-inert`). fail-open 보존(fail-safe 전환·수동 오버라이드·인증서 갱신은 별도 인계). 매매 안전성 8영역 diff 0, 백엔드 4,036 PASS + 프론트 vitest 362 PASS |
| 2026-07-30 | 사이클 C 브레이크이븐 확산 | domain-consult 채택 — VCP/BFB 에 브레이크이븐 승격(1.5N, live-ATR un-latch 병리 방지 boolean 래치 + tighten-only) **default-off(`breakeven_promote_atr=0.0`) 배포** + VCP `recompute_high_since_buy` 이식·부팅 훅 배선(C-V6 dead code 가드). kojiro 는 FREEZE 표본 오염 판정으로 8월 하순 보류, 2단계 ratchet 기각. 활성화 게이트 = donchian 실측(승격 발화+whipsaw 부재) 후 DB 토글. 안전성 5영역 diff 0, 백엔드 4,019 PASS |
| 2026-07-29 | P1 복기 결함 2건 | 주간 복기(실현 -24,800원 중 79%가 donchian 트레일링 미발화) → A: donchian 레이어드 청산(`_entry_atr` 트레일 폴백 + `_breakout_high` 재도출 + 브레이크이븐 승격 1.5N + 10일 채널 청산, 신규 2키 PARAM_RANGES 미편입) + B: 체결통보 중복 수신 멱등 가드(`_completed_buy_orders`) + momentum 폴백 held-conflict skip + 고아 CRITICAL(377450 실사고 재발 차단). 매매 안전성 4영역 diff 0, 백엔드 3,996 PASS. 자문 모델 gpt-5.6-luna 전환 동반 |
| 2026-07-25 | market_op import 시정 | `_subscribe_market_operation_tickers` 함수-로컬 import 가 `from src.realtime.websocket import kis_ws, kis_ws_pool` 로 매 호출 ImportError(kis_ws_pool 은 websocket_pool 정의) → cycle214 이래 H0UNMKO0 후보/보유 종목별 구독 100% 사망(07-24 로그분석 발견 117건=일일 ERROR 94%, 만성). import 2줄 분리 시정 + kojiro 퍼널 step5 라벨 4.5→6.0% 정합. 매매 hot path diff 0(손절=시세틱/체결통보 무관), cycle214 patch 경로 적응 3건, 회귀 가드 5(런타임 ImportError·AST import 경로·kojiro 라벨) |
| 2026-07-25 | kojiro 종목명 견고성 | KojiroMonitor 후보 종목명이 정산(20:10 `_reset_daily_state` 의 `ticker_names.clear`)·저녁·주말엔 사라지던 견고성 갭 시정 — 이름을 volatile `ticker_names` 대신 `_candidates[ticker]` 에 prepare/recompute 시점 저장(자기기술적) + `get_targets_status`/buy_signal 저장값 우선·실시간 폴백. 일일 reset 견딤(f6cc0cd 후속). 백엔드 kojiro.py 전용, 관찰성 UI, hot path diff 0 |
| 2026-07-24 | kojiro 후보 종목명 | KojiroMonitor "후보 종목" 그리드가 종목번호만 표시하던 버그 시정 — 백엔드 `get_targets_status`/buy_signal 에 `resolve_ticker_name(ticker)` 추가 + 프론트 `KojiroMonitor.tsx` `t.name\|\|ticker`(스텁 `prices[ticker]?ticker:ticker` 제거) + `KojiroTarget.name?`. 앞선 funnel COALESCE fix 와 별개인 `targets` 경로 결손. 관찰성 UI, 매매 hot path diff 0 |
| 2026-07-24 | 화면폭 슬라이더 | 대시보드 나브바에 콘텐츠 폭 슬라이더 신규 — `App.tsx <main>`·나브 컨테이너 `max-w-7xl`(1280px 캡) → 동적 `max(1024px, {60+level*0.4}%)`, **기본 전체폭**(넓은 화면 여백 민원 해소). localStorage(`autostock.contentWidth`) 저장·전 페이지 적용·모바일 미노출. 프론트 전용, 백엔드 diff 0 |
| 2026-07-24 | backtest DB토글 | `_enqueue_backtest_jobs`(recommendation_engine.py) 가 정적 `.env`(engine.enabled) 대신 `await engine.is_enabled_async()`(DB 우선) 사용 — Settings UI `kis_mcp_enabled` 토글이 재시작 없이 즉시 반영(그전엔 DB=true 여도 backtest 전량 skip=AI자문 부분실명). kojiro 실측 조사서 발견. auto_apply 무접촉, hot path diff 0 |
| 2026-07-24 | 종목명 폴백 | `list_by_filter` SELECT `name` → `COALESCE(NULLIF(name,''), NULLIF(TRIM(master_raw->>'hts_kor_isnm'),''), '')` — 전체상장 스캔(kojiro 등) funnel 후보가 종목번호만 표시되던 버그 시정(마스터파일 한글명 읽기 폴백, G-AST1 준수·쓰기 무변경, 6전략+funnel 일괄). 매매 hot path diff 0 |
| 2026-07-23 | NXT prelimit stale selling | 익일청산 갭<임계 NXT 프리 지정가 조기청산 폐지 → `_pending_next_day_clear`(reason=nxt_underthreshold) 09:00 KRX 시장가 단일 청산(Tier 1) + stale `_selling` 재대조 훅(`_sync_positions_from_balance`, 보유∧열린주문無∧`_selling_since`≥180s → discard → on_tick 손절 재평가 재개) — Defect 2(stale `_selling` 손절 마비) 시정. 안전성 8영역 중 익일청산·`_selling` 2영역 의도 시정·6영역 diff 0 |
| 2026-07-18 | Phase 2A-2 게이트0+1 | donchian 터틀 유닛 sizing + 하드손절 ATR화 opt-in (sizing_mode=turtle, buy−2.0×entry_atr + −9% backstop, entry_atr 인메모리+recompute buy_date 재도출, DB 플립 활성화) — 매매 안전성 8영역 diff 0 |
| 2026-07-17 | kojiro Phase 1 | 고지로 대순환 스윙 전략 신규 (EMA 5/20/40 스테이지 + 2ATR/2.5ATR/스테이지3 청산, 멀티데이, position_ratio, 다크런치 enabled=False) — 매매 안전성 8영역 diff 0 |
| 2026-07-16 | RDS 이전 M0~M6 | Supabase(PostgREST)→AWS RDS PostgreSQL+asyncpg 전면 교체 (17 db 모듈, DATE 핫픽스, 매매 안전성 diff 0) |
| 2026-07-15 | 214 | H0UNMKO0 후보 구독 풀 분산 + cap 20→60 (41-cap 드롭 시정) |

> 사이클 200 이하 및 초기 하네스 구성 전체 이력(verbatim): [`docs/HARNESS_CHANGELOG.md`](docs/HARNESS_CHANGELOG.md)

### 테스트 실행

```bash
pip install -r requirements-dev.txt # 1회
python -m pytest -q # 백엔드 전체
cd frontend && npm install && npm test # 프론트엔드 전체
cd.. && npx playwright install && npx playwright test --config=e2e/playwright.config.ts # E2E

# 영향 테스트만 (PR 빠른 피드백)
python tools/test_impact/build_index.py
node tools/test_impact/build_index_frontend.mjs
pytest $(python tools/test_impact/affected.py origin/main --target=backend)
```

## 빌드 & 실행

```bash
# Docker (권장)
docker compose up --build # 개발: 프론트 :3000, 백엔드 :8002
docker compose -f docker-compose.prod.yml up --build -d # 프로덕션: Nginx :80

# 로컬
pip install -r requirements.txt && uvicorn src.main:app --host 0.0.0.0 --port 8001 --reload
cd frontend && npm install && npm run dev
```

## 환경 변수
`.env` 필수 (`.env.example` 참고).
- `KIS_ENV`: `vts`(모의) | `real`(실전)
- `KIS_APP_KEY_REAL/VTS`, `KIS_APP_SECRET_REAL/VTS`, `KIS_ACCOUNT_NO_REAL/VTS`
- `KIS_HTS_ID`: 실전 체결통보(H0STCNI0) 구독 키
- `DATABASE_URL`: AWS RDS PostgreSQL asyncpg DSN (`?sslmode=require`). **현재 DB 정본** — 전 db 모듈이 `src/db/pg.py` 풀로 사용
- `SUPABASE_URL`, `SUPABASE_KEY`: **런타임 미사용** (settings/.env 에 잔존하나 어느 db 모듈도 참조 안 함, `src/db/supabase.py` 롤백용 병존)
- `AUTO_START`: 서버 기동 시 자동 매매 시작 (DB `system_config.auto_start` 우선, 매일 시작 전 재확인)
- `DKSTOCK_REGIME_ENABLED` (기본 false): dkstock.cloud 매크로 + 매수 가드 + cash_usage_ratio 자동 조정 활성화
- `KIS_MCP_ENABLED` (기본 false): 외부 백테스트 MCP 서버 활성화. 자문 직후 6 전략 × 2 kind = 12 job fire-and-forget

## 다중 전략 (요약)

7 전략: `momentum` / `volatility_breakout` / `long_tail_volatility` / `donchian_swing` / `bull_flag_breakout` / `vcp_breakout` / `kojiro`(고지로 대순환 스윙, 2026-07 Phase 1 다크런치 `enabled=False`).

상세 매수/청산/tradable_boards/exchange 는 **`src/engine/strategies/CLAUDE.md`** 참조.

### 새 전략 추가
1. `src/engine/strategies/` 에 `StrategyBase` 서브클래스 (`prepare/check_buy_signal/check_exit_signal/calc_buy_quantity`)
2. `src/engine/scheduler.py` `__init__` 에서 `registry.register()`
3. 필요 시 `scanner.py` 에 스캔 함수 추가
4. `strategies/CLAUDE.md` 표 + `_workspace/00_leader_trading_rules.md` 명세 추가

### 자금 관리
- 프론트 Settings → `PUT /api/strategies/weights` → `StrategyRegistry.allocate_funds()`
- `position_ratio` 는 **전략 할당 자금 기준** (순자산 × 전략비중 × position_ratio = 종목당 매수금액)
- 전략 간 동일 종목 중복 매수 방지: `registry.is_ticker_blocked_for_buy()` (보유/주문중/당일매도 통합 차단)
- **`cash_usage_ratio`**: `system_config.cash_usage_ratio` 키 — `_boot()` 가 `summary.net_asset × ratio` 로 `allocate_funds()` 호출. 범위 `[0.0, 1.0]`, 5% 단위, 기본 1.0. Settings 슬라이더로 조정 → **다음 영업일부터 반영**. `auto_regime_adjust=true` (기본) + `DKSTOCK_REGIME_ENABLED=true` 시 매크로 레짐 `cash_min` 기반 자동 갱신 (`clamp((100-cash_min)/100, 0.0, 1.0)`)

### 외부 통합 (백테스트 + 매크로 레짐)
- 20:00 AI 자문 INSERT 직후 외부 MCP 백테스트 (`http://43.202.187.5:3846/mcp`) — 6 전략 × 2 kind = 12 job fire-and-forget → `parameter_recommendations.backtest_summary` JSONB
- 매크로 레짐 (`dkstock.cloud`) — `regime/vix/fear_greed` 4 임계 OR 매수 가드 (4 모드: HARD/WARN/SOFT/OFF) + `cash_usage_ratio` 자동 조정
- 활성화 토글: `KIS_MCP_ENABLED` / `DKSTOCK_REGIME_ENABLED` (Settings UI 즉시 토글 가능). 외부 다운 시 graceful — 자문 INSERT 보존, summary=null, 매수 가드 비활성
- 운영 가이드: [`docs/backtest-monitoring.md`](docs/backtest-monitoring.md)

## 핵심 안전 규칙 (절대 깨지 말 것)

상세 메커니즘은 `src/engine/CLAUDE.md` · `src/realtime/CLAUDE.md` 참조. 여기서는 **금기**만:

- **체결통보 구독 (H0STCNI0/H0STCNI9) 제거 금지** — 미구독 시 포지션 등록·손절 불가
- **uvicorn 단일 워커 필수** — `--workers` 금지 (스케줄/포지션/WebSocket 중복)
- **주문번호 매핑** (`_order_qty/_order_strategy/_order_ticker/_pending_buy_orders`) 등록은 `place_order` 응답 직후 동기 영역, `await insert_trade` 진입 전 — 시장가 즉시체결 race 시 매핑 누락하면 기본값 "momentum" 으로 잘못 INSERT됨
- **체결통보 선행 race 가드** (`_completed_orders` set + UPDATE 0건 보정 INSERT) 제거 금지 — 시장가 즉시체결 + REST 응답 지연 시 trade_history 가 PENDING 영구 잔존
- **`_reset_daily_state()` 제거 금지** — 정산 후 미초기화 시 pending_buys/positions/sold_today 가 다음 날까지 잔류
- **익일 청산** 은 scheduler 에서 시가 수신 후 30s 안정화 처리 — `_pending_next_day_clear` 보류 후 09:00 KRX 시장가. `high_since_buy` 폴백 금지. on_tick 즉시 청산 금지
- **NXT 매도 거부 좀비 차단** — `is_market_closed_rejection` (APBK0918 + 장운영시간 외) 이면 `execute_sell` 이 positions(메모리/DB) 보존 + `_selling` **discard** (진입 게이트 `SellRejectionTracker.is_blocked()` 가 이후 차단 담당 — `_selling` 을 보존하면 그게 곧 stale `_selling` 좀비=손절 마비이므로 반드시 해제) + 재시도 중단. `is_insufficient_quantity` / `is_insufficient_cash` 와 분리. `SellRejectionTracker.is_blocked()` 진입 게이트는 **2단계 TTL** — KRX 메인(09:00~15:30) 거부 = 5분 TTL (일시 장애 가정), NXT 시간대(08:00~09:00 / 15:30~20:00) 거부 = 다음 KST 09:00 TTL. `market_order_disallowed` 거부 = 30초 TTL (동일 tick 폭주 차단). NXT 폴백 실패 시 `_pending_next_day_clear` 익일 청산 자동 전환. `_reset_daily_state` 동행 clear (`_sell_rejection.reset_daily()` 4 필드 일괄 위임, `OrderEngine.reset_daily_state()` 캡슐화 보존). 호환 layer property `_market_closed_blocked` / `_market_closed_blocked_logged_today` 는 tracker 내부 dict/set 직접 노출 (is 동일성 보장)
- **매수/매도 시장가 거부 → 지정가 5호가 폴백 1회** — `is_market_order_disallowed` (msg1 키워드 `시장가매매불가` / `시장가호가불가` / `최유리/최우선지정가 주문만` / `지정가 및 최유리` — APBK1943/APBK3013) 매칭 시 `step_up(buy)/step_down(sell)` 으로 `LIMIT` 재시도. 매핑 동기 + race 가드 동일 규약
- **KIS 거부 응답 영구 저장** — `_request` 가 `rt_cd != "0"` 시 `system_logs` prefix `[kis_rejection]` + path/tr_id/msg_cd/msg1 + body 주요 키 (민감 키 마스킹) fire-and-forget
- **WebSocket 시세 보유·익일청산 우선 보장** — `MAX_SUBSCRIPTIONS=41` KIS 공식 한도. HIGH (보유/익일청산) `bypass_limit=True` 절대 보장. 후순위 drop 시 `[priority_drop]` INFO + WARNING `system_logs`. HIGH 단독 41 초과 ERROR
- **WebSocket 다중 안전망** — F1 (재연결 1회) + `_scan_loop` (5분) + K stale watcher (120s 주기, 1~5회 즉시 강제 재등록 + 6회 초과 시 10분 cooldown 기반 시간 기반 force_retry + 시간당 6회 cap, 사이클 102 임계 상향) + `_resubscribe_stale_priority` (5분 우선) 4중. K stale watcher 양쪽 분기에 우선순위 분리 (positions/`_pending_next_day_clear` HIGH+bypass=True, 그 외 후보 LOW+bypass=False — 메인 편중 차단). `_subscriptions` ACK 정합성 가드 (orphan ACK race 차단)
- **세션 단위 silent inactive 자동 reconnect** — `_detect_silent_inactive_sessions` 3중 가드: `fresh_ratio < SILENT_INACTIVE_FRESH_RATIO_THRESHOLD(=0.2, 20%)` + `subscribed_count >= 5` + 5분 지속 → `_ws.close()` 강제 reconnect. 시간당 세션당 2회 cap (LMS/앱키 정지 위험 차단)
- **stale universe 가드** — `_evaluate_universe_guard`: stale>5 + `today_volume < UNIVERSE_LOW_VOLUME_THRESHOLD(=10_000)` 종목 자동 unsubscribe + `_universe_excluded_today` 등록 + `[universe_excluded]` INFO + `inquire_ccnl` 으로 마지막 체결시각 로그. 보유/익일청산 절대 보호 + `_reset_daily_state` 동행 clear (영구 블랙리스트 금지)
- **`trade_history` 중복 INSERT 차단** — `_sync_orders_to_db` 는 `get_today_buy_trades_for_sync()` / `get_today_sell_trades_for_sync()` 사용 (dedupe 없음 + CANCELLED 제외). DB 부분 UNIQUE 인덱스 `(ticker, order_no, trade_type)` 이중 안전망. 기존 `get_today_buy_trades()` 의 ticker dedupe 는 포지션 복구용 — 절대 sync 중복 판정에 사용 금지
- **NXT 거래가능 사전 판별** — `stock_master.nxt_tradable=False` 면 NXT/SOR → KRX 강제 다운그레이드 + `[nxt_downgrade]`. `_boot()` eager 사전 갱신 (보유 + `_pending_next_day_clear` 합집합). 거부 사후 보강 `stock_master.upsert_one(ticker, nxt_tradable=False)`
- **종목코드 형식 비대칭** — 진입은 6자리 숫자만 (`isdigit()`), 사후처리는 6자리 영숫자 (`isalnum()`) — ETF·신주인수권 자동매매 차단 + 좀비 포지션 방지
- **1주 폴백은 전략 잔여 자금 기준** — 6 전략 `calc_buy_quantity()` 가 `StrategyBase._fallback_one_share(current_price)` 공통 헬퍼. 잔여 = `total_investment - (positions buy_price×qty + pending_buy_amounts 합)`
- **VB 당일 15:20 일괄매도** — `DEFAULT_TRADABLE_BOARDS=("main",)`, POST_NXT 추가 금지. `_force_clear_main_only` 가 15:20 일괄 청산. 15:30 이후 호출은 시간 가드로 skip
- **`tradable_boards` 는 매수 진입 전용 (명문화)** — 매도/손절/Trailing/익일청산/15:20 강제청산/상한가 손절 모니터링은 어떤 전략에서도 PRE/MAIN/POST 무관 항상 작동. `risk.on_tick` 의 `check_exit_signal` 분기는 `session_tracker.is_tradable` 검사 *전* 진입. LTV `DEFAULT_TRADABLE_BOARDS=("pre_nxt", "main", "post_nxt")` (사용자 의도 — 연속 상한가 익일 청산 + 야간 매수)
- **donchian_swing `_swing_rest_poll_loop`** 제거 금지 — 09:30~15:20 60s REST 폴링으로 멀티데이 손절 평가 보강
- **모든 시각 데이터 KST 강제** — 백엔드 `_to_kst(iso)` 헬퍼 + `_today_kst_iso()` timezone 명시 (`+09:00`). 프론트 `Intl.DateTimeFormat(timeZone='Asia/Seoul')` 명시. `new Date(iso).getHours()` 브라우저 로컬타임 추출 금지
- 매매 파라미터 (`DEFAULT_PARAMS`) 변경 시 `_workspace/00_leader_trading_rules.md` 동기화

### 코딩 컨벤션
- Python: pydantic + async/await
- TS: 모든 API 응답은 `frontend/src/types/` 정의 사용
- API 응답 래퍼: `{ success: bool, data: T, message: str }` (`models/response.py` `ApiResponse`)
- KIS 호출은 반드시 `src/api/base.py::kis_request()` 또는 `kis_get_quote()` 경유 (Rate Limit·재시도·메트릭)
- TR_ID 는 `settings.get_tr_id()` 사용 — 하드코딩 금지
- DB 접근은 `src/db/pg.py` (asyncpg) 네이티브 async — `pg.fetch`/`pg.execute` 경유. JSONB=raw dict 바인딩(codec) / TIMESTAMPTZ 쓰기=`datetime.fromisoformat(now_kst_iso())`·읽기=`to_char(...,'+09:00')` / DATE=`_kst.to_date()` 강제 (상세 `src/db/CLAUDE.md`)

## DB 스키마 (AWS RDS PostgreSQL)

마이그레이션: `supabase/migrations/`. CRUD 모듈 상세: `src/db/CLAUDE.md`. (마이그레이션 디렉토리명은 supabase/ 유지 — 스키마 SQL 정본, RDS 에 순차 적용)

| 테이블 | 용도 |
|--------|------|
| `trade_history` | 거래 내역 (status: PENDING/COMPLETED/PARTIAL/CANCELLED) |
| `daily_performance` | 일일 실적 (date+strategy 복합PK, TWR 누적, 실현손익 기준) |
| `positions` | 보유 포지션 영속화 (ticker PK) |
| `strategy_config` | 전략 설정 (strategy_id PK, params JSONB) |
| `system_config` | 시스템 설정 (auto_start, cash_usage_ratio, buy_block_mode + 4 임계값, dkstock_regime_enabled, kis_mcp_enabled 등) |
| `system_logs` | 시스템 로그 |
| `parameter_recommendations` | 20:00 AI자문 (target_date+strategy_id UNIQUE). `recommended_weight`/`code_review_notes`/`applied_weight`/`weight_reasoning`/`backtest_summary` JSONB |
| `daily_log_reports` | 20:10 일일 로그 분석 (target_date UNIQUE, metrics 에 api_metrics/strategy_funnel/by_ticker_pnl/by_hour_pnl/next_day_clear 포함). 토큰/지연/비용 5 컬럼 — input_tokens/output_tokens/total_tokens/latency_ms/cost_estimate_usd (migration 031, 모두 NULL 허용) |
| `stock_master` | KIS CTPF1002R 캐시 (ticker PK, 24h TTL) + **사이클 129 `master_raw` JSONB + `master_raw_updated_at TIMESTAMPTZ` 신규** (KIS 공식 일일 마스터 파일 영역 — 시총/거래정지/관리종목/지수편입/재무 ~30 키, raw 영역 분리 보호). NXT 거래가능 사전 판별. **사이클 168 생성 컬럼 `hts_avls_eok bigint`(억원) + `acml_tr_pbmn_won bigint`(원) GENERATED ALWAYS STORED** (migration 039 — raw.hts_avls/acml_tr_pbmn 가 jsonb *문자열* 로 저장되어 UI `list_paged_by_filter` jsonb numeric gte 가 0건 silent 결함 → 생성 컬럼 numeric 비교 + 인덱스로 시정. 비숫자는 `~ '^[0-9]+$'` 가드로 NULL. raw 읽기만 = 사이클 81 G-AST1 영속) |
| `stock_master_daily` | KIS FHKST03010100 일봉 정규화 (migration 033). PK `(ticker, bas_dd)` + OHLCV + change_rate + raw JSONB. 매일 16:00 KST 적재 (백필 시 T-100일, 이후 D-1 영업일 증분). **사이클 172 — VCP universe (KOSPI200∪KOSDAQ150) backfill** (분할 fetch) + retention `DAILY_RETENTION_DAYS=230`. **사이클 196 (2026-07-07) — VCP backfill target 220→120 수렴** (retention 230cal=154영업일 실측 < 220 → 무한 재backfill churn → target 120 하향 + `fetch_daily_candles_backfill` 윈도우 클램프, VCP prepare 실사용 100일 << 154 보유 무영향). donchian (20일 신고가) / VCP (베이스+Pullback, prepare 100일 cap) / VB (ATR) 전략 활용 |
| `stock_master_financial` | KIS 재무 5 TR 정규화 (migration 041, 사이클 C1). PK `(ticker, stac_yymm, div_cls)` (div_cls 0=년/1=분기) + 18 NUMERIC 컬럼(손익 5/대차 7/수익성 2/안정성 2/기타 2) + raw JSONB + refreshed_at. 마법공식(EV/EBITDA·ROC) + F-Score-7 원천 데이터. 주1회 16:40 적재. 매매 hot path 무관 |
| `backtest_runs` | 외부 MCP 백테스트 영속화 (`(target_date, strategy_id, params_kind)` UNIQUE. 6 전략 × 2 kind = 12 row/사이클) |
| `market_regime_snapshots` | dkstock.cloud 매크로 일일 스냅샷. `_boot()` 시점 1행. `buy_blocked`/`computed_cash_usage_ratio`/`raw_response JSONB` 영구 기록 |
| `kis_quote_accounts` | 보조 KIS 시세 수신 계좌 (UUID PK, label UNIQUE, active=true 부분 인덱스). `list_accounts()` 60s TTL 메모리 캐시 |
| `strategy_funnel_snapshots` | 전략별 조건검색 단계별 후보/탈락 종목 영구 추적. `(target_date, strategy_id, step_no, snapshot_at)` UNIQUE. `survived_tickers` JSONB cap 200 / `excluded_sample` JSONB cap 20. 수동 trigger `POST /api/strategy-funnel/snapshot` (현재 최종 단계 `step_no=99` 만, 자동 hook 은 후속 사이클) |

> **`trade_history` 부분 UNIQUE 인덱스 (migration 029)**: `uq_trade_history_ticker_order_no_type ON (ticker, order_no, trade_type) WHERE order_no IS NOT NULL AND order_no != ''`. `_sync_orders_to_db` 핑퐁 INSERT 영구 차단 + NULL/빈 order_no (수동 매매 사전 등) 호환.

> **`stock_master` / `stock_master_daily` UI 동기화 의무**: stock_master 컬럼 / raw JSONB 키 / stock_master_daily 컬럼 추가 시 UI 동기화 의무 영속. 전략에서 종목마스터 데이터 참고 시점 영역부터 신규 수집 데이터는 UI 노출 의무. 절차 = (1) `frontend/src/types/stock-master.ts` interface 갱신 (2) `frontend/src/api/stock-master.ts` 호출 영역 갱신 (3) `frontend/src/pages/StockMaster.tsx::FIELD_LABELS` 한글 라벨 + `CATEGORY_KEYS` 배치 + `HIGHLIGHT_KEYS` 핵심 키 추가 (4) `GET /api/stock-master/stats` 응답에 진단 카운트 추가 + 카드 1개 추가 (5) `frontend/src/test/handlers.ts` MSW + `e2e/fixtures/api-mocks.ts` Playwright LIFO 정합 갱신 (6) 회귀 가드 추가. 상세는 `frontend/CLAUDE.md` 참조.

## Docker / 배포

- `Dockerfile` / `frontend/Dockerfile` 멀티스테이지 (dev: hot-reload / prod: non-root + Nginx)
- `docker-compose.yml` (개발 hot-reload) / `docker-compose.prod.yml` (prod)
- **토큰 캐시 영속화**: `./.token_cache:/app/.token_cache` 디렉토리 볼륨 양쪽 compose 동일 마운트. KIS `/oauth2/tokenP` 분당 1개 한도 + 컨테이너 재기동 시 토큰 24h 유효 보존. `.gitignore` 등록 (`.token_cache/` + 구 `.token_cache_quote_*.json` 호환). 구 경로 `.token_cache.json` 존재 시 자동 마이그레이션
- **`.token_cache` 빌드 시점 권한 보장**: `Dockerfile` prod 스테이지가 `mkdir -p /app/.token_cache` → `chown -R appuser:appuser /app` → `USER appuser` 순서. 호스트 bind mount 가 root:root 로 생성되어 `appuser` 가 쓰기 거부되던 결함 영구 차단 (회귀 가드: `tests/integration/test_dockerfile_token_cache_perms.py`)
- `frontend/nginx.conf`: 정적파일 + `/api` → backend:8000 프록시
- 타임존 `TZ=Asia/Seoul`, vite 프록시 타겟은 `VITE_API_URL` 분기
- **EC2 t4g.small (ARM, ap-northeast-2)** 서비스 경로 `~/auto_stock/`
- 자동 배포: `git push origin main` → GitHub Actions 가 EC2 SSH → `git pull` + 재빌드 (`.github/workflows/deploy.yml`). push 시각 → pool_start 지연 1~5분. deploy.yml 은 push 후 `supabase/migrations/*.sql` 을 EC2 psql 로 순차 적용 (`SUPABASE_DB_URL` secret — **이름은 유지하되 값이 RDS DSN**, graceful skip)
- CI (`.github/workflows/ci.yml`): `postgres:15` service 컨테이너 + `DATABASE_URL_TEST` 로 통합 테스트 실행 (`tests/integration/pg_harness.py` 가 migration 001~041 적용)
- GitHub Secrets: `EC2_HOST`, `EC2_USERNAME`, `EC2_SSH_KEY`, `SUPABASE_DB_URL` (값=RDS DSN)
- **로컬과 EC2 동시 실행 금지** — KIS 동일 계정 동시 접속 충돌
- 운영 가이드: KRX 메인 시간 (09:00~15:30) 중 빈번한 push 자제 — `_scan_loop` 5분 race 가능. NXT 애프터 (15:30~) 또는 익일 07:50 _boot 전 push 권장

## 디렉토리 역할
- `src/auth/` — KIS OAuth 인증/토큰 (메인 + 보조 multi)
- `src/api/` — KIS REST (주문·잔고·조건검색·일봉) + 시세 풀 (`base.py::_request_via_quote_pool` + path 화이트리스트 가드). `quotation.py::inquire_ccnl(ticker, market='J')` — FHKST01010100 주식현재가 시세, output[0] + today_volume 합산 + graceful None (stale universe 가드용)
- `src/realtime/` — KIS WebSocket (시세·체결통보·H0NXMKO0) + WebsocketPool 멀티 세션 분배
- `src/engine/` — 매매 핵심 (전략·레지스트리·주문·리스크·스케줄러). `recommendation_engine.py` 20:00 AI자문 / `log_analysis_engine.py` 20:10 일일 분석 / `backtest_engine.py` + `backtest_yaml.py` / `market_regime.py`
- `src/engine/strategies/` — 6 전략 명세 (전용 CLAUDE.md)
- `src/services/` — 외부 서비스 클라이언트 (`mcp_client.py` 백테스트 MCP / `dkstock_client.py` 매크로 / `quote_session_health.py` 보조 세션 health monitor)
- `src/db/` — Supabase CRUD
- `src/routes/` — FastAPI 엔드포인트
- `src/models/` — Pydantic 모델
- `frontend/` — React 대시보드
