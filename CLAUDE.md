# CLAUDE.md — 프로젝트 루트

KIS OpenAPI 기반 주식 자동매매시스템. FastAPI(백엔드) + React(프론트엔드) + Supabase(DB). 다중 전략 아키텍처.

> 디렉토리별 상세는 각 하위 `CLAUDE.md`가 진실의 원천:
> `src/CLAUDE.md` · `src/engine/CLAUDE.md` · `src/api/CLAUDE.md` · `src/realtime/CLAUDE.md` · `src/db/CLAUDE.md` · `src/routes/CLAUDE.md` · `frontend/CLAUDE.md`

## 하네스: TDD-First Trading Team

**목표:** 모든 코드 변경을 Red→Green→Refactor 사이클로 강제하고, 변경 시 영향받는 테스트만 실행할 수 있는 정적 인덱스를 유지한다.

### 기본 진입점 — `team-leader` 우선

사용자의 모든 요청은 1차로 `Agent({subagent_type: "team-leader"})`로 라우팅한다. team-leader가 트레이더 관점에서 해석 후 하위 에이전트에 분배한다.

- 코드 변경 → `auto-trading-orchestrator` 스킬 (TDD 사이클: `tdd-engineer` Red → `backend-dev`/`frontend-dev` Green → `tester` 검증)
- 단위/회귀 테스트 → `tdd-cycle` (백엔드 pytest+respx+freezegun / 프론트엔드 vitest+RTL+MSW)
- 영향 인덱스 → `test-impact-index`
- 통합/경계면/E2E/안전성 → `trading-test`

**우회 허용 (메인 세션 직접 응답):** 단순 사실 질의, 단발 디버그/grep, 운영 환경 즉시 점검(EC2 SSH 등). 코드 변경 제안이 따라오면 다시 team-leader로 인계.

### 모델 라우팅

| 작업 유형 | 모델 | 적용 |
|----------|------|------|
| 계획·검증 (구현 계획, 테스트 설계, 검수, 안전성 검증) | **opus** | `team-leader`, `tdd-engineer`, `tester` |
| 일반 구현 (코드 작성·리팩터·버그 수정) | **sonnet** | `backend-dev`, `frontend-dev` |
| 명령어 작성 (bash/슬래시/스크립트) | **haiku** | 메인 세션 단발 작업 — fork 또는 `claude-haiku-4-5-20251001` 위임 |

라우팅은 에이전트 frontmatter에서 강제된다. 모호하면(예: 구현+검증) 비중 큰 쪽으로 분리 분배.

### 테스트 실행

```bash
pip install -r requirements-dev.txt          # 1회
python -m pytest -q                          # 백엔드 전체
cd frontend && npm install && npm test       # 프론트엔드 전체
cd .. && npx playwright install && npx playwright test --config=e2e/playwright.config.ts  # E2E

# 영향 테스트만 (PR 빠른 피드백)
python tools/test_impact/build_index.py
node  tools/test_impact/build_index_frontend.mjs
pytest $(python tools/test_impact/affected.py origin/main --target=backend)
```

**변경 이력**은 [`docs/HARNESS_CHANGELOG.md`](docs/HARNESS_CHANGELOG.md)로 분리.

## 빌드 & 실행

```bash
# Docker (권장)
docker compose up --build                                 # 개발: 프론트 :3000, 백엔드 :8002
docker compose -f docker-compose.prod.yml up --build -d   # 프로덕션: Nginx :80

# 로컬
pip install -r requirements.txt && uvicorn src.main:app --host 0.0.0.0 --port 8001 --reload
cd frontend && npm install && npm run dev
```

## 환경 변수
`.env` 필수 (`.env.example` 참고).
- `KIS_ENV`: `vts`(모의) | `real`(실전)
- `KIS_APP_KEY_REAL/VTS`, `KIS_APP_SECRET_REAL/VTS`, `KIS_ACCOUNT_NO_REAL/VTS`
- `KIS_HTS_ID`: 실전 체결통보(H0STCNI0) 구독 키
- `SUPABASE_URL`, `SUPABASE_KEY`
- `AUTO_START`: 서버 기동 시 자동 매매 시작 (DB `system_config.auto_start`가 우선, 매일 시작 전 재확인)

## 다중 전략 (요약)

| 전략 ID | 매수 | 청산 |
|---------|------|------|
| `momentum` | 전일종가 +29% 돌파 (KRX_OPEN+MAIN) | -7.5% 손절, 익일 NXT 프리 청산. `exchange`(KRX/NXT/SOR) |
| `volatility_breakout` | 보드별 K값 × 전일Range 돌파 (PRE_NXT/MAIN/POST_NXT) | -3% 손절, 15:20 KRX 메인 청산 |
| `long_tail_volatility` | VB 방식 + 상한가 도달 시 익일 청산 모드 전환 | 당일 -3% / 상한가 모드 -5%, 15:20(상한가 미도달만) |
| `donchian_swing` | 코스피200+코스닥150 고정 유니버스, 20일 신고가+60일 EMA+거래대금 1.5×, 익일 09:05 시장가 (MAIN만) | ATR(14)×2 트레일링 / -7% 하드. 시간 청산 없음, 멀티데이 보유 |

전략 동작·보드별 K값 분리·익일 청산 안정화·자금 락·라우팅 등 상세는 **`src/engine/CLAUDE.md`**.

### 새 전략 추가
1. `src/engine/strategies/`에 StrategyBase 서브클래스 (prepare/check_buy_signal/check_exit_signal/calc_buy_quantity)
2. `src/engine/scheduler.py` `__init__`에서 `registry.register()`
3. 필요 시 `scanner.py`에 스캔 함수 추가
4. `_workspace/00_leader_trading_rules.md`에 명세 추가

### 자금 관리
- 프론트 Settings → `PUT /api/strategies/weights` → `StrategyRegistry.allocate_funds()`
- `position_ratio`는 **전략 할당 자금 기준** (순자산 × 전략비중 × position_ratio = 종목당 매수금액)
- 전략 간 동일 종목 중복 매수 방지: `registry.is_ticker_blocked_for_buy()` (보유/주문중/당일매도 통합 차단)

## 핵심 안전 규칙 (절대 깨지 말 것)

상세 메커니즘은 `src/engine/CLAUDE.md`·`src/realtime/CLAUDE.md` 참조. 여기서는 **금기**만:

- **체결통보 구독(H0STCNI0/H0STCNI9) 제거 금지** — 미구독 시 포지션 등록·손절 불가
- **uvicorn 단일 워커 필수** — `--workers` 금지 (스케줄/포지션/WebSocket 중복)
- **주문번호 매핑(`_order_qty/_order_strategy/_order_ticker/_pending_buy_orders`)은 `place_order` 응답 직후 동기 영역에서 등록**, `await insert_trade` 진입 전 — 시장가 즉시체결 race 시 매핑 누락하면 기본값 "momentum"으로 잘못 INSERT됨. 자동매매·수동 매도(`/api/trading/manual-sell`) 모두 동일 순서
- **체결통보 선행 race 가드(`_completed_orders` set + UPDATE 0건 보정 INSERT) 제거 금지** — 시장가 즉시체결 + REST 응답 지연 시 trade_history가 PENDING으로 영구 잔존
- **`_reset_daily_state()` 제거 금지** — 정산 후 미초기화 시 pending_buys/positions/sold_today가 다음 날까지 잔류
- **익일 청산은 scheduler에서 시가 수신 후 30s 안정화 처리** — 시가 수신 시 NXT 지정가(`step_down(open,1)`) / 미수신 시 `_pending_next_day_clear`로 보류 후 09:00 KRX 시장가. `high_since_buy` 폴백 금지(갭률 0% 즉시 청산 결함). on_tick 즉시 청산 금지
- **NXT 프리/애프터 매도 거부 좀비 차단** — `is_market_closed_rejection`(APBK0918 + 장운영시간 외 키워드)이면 `execute_sell`이 positions(메모리/DB) 보존 + 재시도 중단. `is_insufficient_quantity`/`is_insufficient_cash`로 잘못 분류되어 positions 삭제하던 결함 차단
- **매수 시장가 거부(`is_market_order_disallowed`) → 지정가 5호가 폴백 1회** — msg1 키워드(`시장가매매불가` 변형, `시장가호가불가` 포함) 매칭 시 `execute_buy`가 `step_up(current_price, 5)` 가격으로 지정가(`OrderDivision.LIMIT`) 1회 재시도. 매핑 동기 등록 + 체결통보 선행 race 가드는 시장가 경로와 동일 규약. 폴백 실패 시 `block_low_funds(ticker, 900s)` cooldown 등록. 좀비 pending_buys 차단. 2026-05-11 계양전기 사례 대응 — `docs/kis/error-codes.md`
- **매도 시장가 거부(`is_market_order_disallowed`) → 지정가 5호가 폴백 1회** (Phase C, 2026-05-11) — `execute_sell`이 `order_division==MARKET` 시장가 매도 경로에서 `step_down(current_price, 5)` 가격으로 지정가 1회 폴백. 매핑 동기 등록 + `_completed_orders` race 가드 + `insert_trade(PENDING, price=fallback_price)`는 매수 폴백·시장가 경로와 동일 동기 순서. 폴백 실패 시 **cooldown 등록 안 함**(매도는 청산 의무 — 다음 사이클 자연 재트리거), 메모리/DB positions **보존**. 지정가 매도(`limit_price>0`)에서는 폴백 안 함(이미 지정가, 기존 3회 재시도 유지). 키워드 `시장가호가불가` 추가(APBK1943, 2026-05-11 계양전기 09:00:21 매도 ×3 실패 원문). **APBK3013(NXT 애프터 16:05~ 3건 발생)도 동일 폴백 자동 적용** — 키워드 `최유리/최우선지정가 주문만` / `지정가 및 최유리` 매칭(Phase H1, 2026-05-11). stock_master 사후 보강은 NXT `is_market_closed_rejection` 전용 — APBK1943/APBK3013은 호가 정책 자체 사유라 NXT 무관 — `docs/kis/error-codes.md` 5-4절
- **KIS 거부 응답 영구 저장(Phase A1)** — `_request`가 `rt_cd != "0"` 시 `KisApiError` raise 직전에 `system_logs`에 prefix `[kis_rejection]` + path/tr_id/msg_cd/msg1 + body 주요 키(`PDNO`/`ORD_DVSN`/`ORD_UNPR`/`ORD_QTY`/`EXCG_ID_DVSN_CD`/`SLL_BUY_DVSN_CD`)를 fire-and-forget 저장. 민감 키(`CANO`/`ACNT_PRDT_CD`) 마스킹. 다음 거부 사례의 정확한 msg_cd 즉시 추적 가능
- **WebSocket 시세 구독 보유·익일청산 우선 보장(E1, 2026-05-12)** — `MAX_SUBSCRIPTIONS=41`(KIS 공식 한도, 이전 200은 과대 설정으로 silently 거절 차단 못 함). `subscribe_filtered_stocks(priority_groups=...)` 가 보유→익일청산→swing→momentum→breakout 순으로 처리, 보유·익일청산은 `bypass_limit=True` 로 한도 무시 absolute 보장. 후순위만 잔여 슬롯 초과 시 drop + `[priority_drop] swing=X momentum=Y breakout=Z` INFO 로그. HIGH 단독 41 초과 시 ERROR + `system_logs`. 2026-05-12 donchian 조기 손절 사건(보유 종목 시세 누락) 대응
- **WebSocket 구독 거절 응답 감지(E2, 2026-05-12)** — `_handle_raw()` JSON 분기가 `rt_cd != "0"` 또는 `msg1` 키워드(영문 ERROR/FAIL/REJECT/NOT ALLOWED/LIMIT/EXCEED/DUPLICATE + 한국어 한도/초과/이미/중복/허용되지/권한) 매칭 시 `_subscriptions.discard` + ERROR 로그 + `write_log("ERROR", "[ws_subscribe_reject] tr_id=... tr_key=... rt_cd=... msg_cd=... msg1=...")` fire-and-forget. silently drop 차단 + `_subscriptions` 정합성 자동 회복. 다음 5분 `_scan_loop` 사이클에서 E1 우선순위 큐로 자연 재시도
- **WebSocket 재연결 후 자동 시세 검증(F1, 2026-05-12)** — `connect()` 가 재연결 성공 직후(`_reconnect_count > 0`) `_verify_subscriptions_after_reconnect()` task 발화. `VERIFY_AFTER_SECS=60` 대기 후 `scanner.ticker_last_tick` 기준 `VERIFY_FRESHNESS_SECS=60` 내 tick 없는 TICK 구독을 `_send_subscribe(subscribe=True)` 1회 재전송. KIS silent inactive(거절 응답도 시세도 없음 — E2 거절 감지 무력화 영역) 차단. `_reverify_in_progress` 플래그로 동시 task 중첩 방지, 첫 연결은 발화 안 함, 검증 중 `_ws is None`/`_running is False` 면 조용히 종료, 예외 발생 시 ERROR 로그 + 플래그 해제. WARNING 시 `[ws_reverify] reconnect_count=N stale=M/T preview=[...]` 영구 로그(sorted 처음 10개만 표시 + 전체 카운트). 재구독 1회로 부족하면 다음 5분 `_scan_loop` 자연 회복에 위임
- **NXT 거래가능 사전 판별(Phase G, 2026-05-11)** — KIS `CTPF1002R` 응답 `cptt_trad_tr_psbl_yn=="Y" AND nxt_tr_stop_yn=="N"`로 `nxt_tradable` 파생. `stock_master` 테이블(24h TTL) 캐시 → `OrderEngine._strategy_exchange_async(strategy_id, ticker=...)`가 `nxt_tradable=False` 시 NXT/SOR → KRX 강제 다운그레이드 + `[nxt_downgrade]` 로그. `scheduler._execute_next_day_clear`는 1순위 판별로 사용 → 시가 폴링/안정화 거치지 않고 즉시 `_pending_next_day_clear` 등록(NXT 주문 시도 0). `execute_sell`이 `is_market_closed_rejection` NXT 시간대 거부 받으면 `stock_master.upsert_one(ticker, nxt_tradable=False)` 사후 보강 — 다음 사이클부터 자동 다운그레이드. `docs/kis/error-codes.md` 5-3절
- **stock_master eager 사전 갱신(I3, 2026-05-12)** — `scheduler._boot()` 마지막에 `_eager_refresh_stock_master_for_held_positions()` 호출. 보유 ticker + `_pending_next_day_clear` 합집합(6자리 영숫자만)을 sequential await 로 `is_stale(24h)` 체크 후 `inquire_stock_basics`→`upsert_one`. Phase G lazy 갱신 한계(캐시 miss 첫 사이클은 전략 기본 exchange SOR/NXT 그대로 발사 → KIS 거부) 차단. 2026-05-12 09:00:12 KST 계양전기(012200) NEXT_DAY_CLEAR EXCG_ID_DVSN_CD=SOR 거부 사례 대응. parallel(`asyncio.gather`) 금지, 종목별 예외 흡수, `[stock_master_eager]` total/refreshed/skipped INFO 로그 1행. 매수 진입/익일청산 호출부 추가 eager 금지(_boot 1회로 충분)
- **high_since_buy 일봉 폴백 (donchian_swing, E3, 2026-05-12)** — `_boot()` → `recompute_held_atr()` 시점에 매수일 다음 영업일~전영업일 KIS 일봉 high max 로 `pos.high_since_buy` 보정. 시세 미수신 누적으로 chandelier 트레일링이 매수가 부근에 동결되어 첫 갭다운에 즉시 청산되는 결함 차단. 매수일 당일/미래일 skip(미래는 WARNING). sequential await(`asyncio.gather` 금지) + 종목별 fetch 예외 격리. 보정값이 기존 `high_since_buy` 초과 시 `db.positions.update_high` + `system_logs` `[high_since_buy_recover]` 1행. 다른 전략(momentum/VB/LTV) 호출 확장은 별도 단계 — donchian만 적용. `risk.py:72` 실시간 시세 기반 `max(pos.high_since_buy, current_price)` 갱신은 그대로 유지(boot 시점 1회 복구만)
- **종목코드 형식 비대칭**: 진입은 6자리 숫자만(`ticker.isdigit()`), 사후처리는 6자리 영숫자(`isalnum()`) — ETF·신주인수권 자동매매 차단 + 좀비 포지션 방지
- **1주 폴백은 전략 잔여 자금 기준(2026-05-11 P1)** — 4개 전략 `calc_buy_quantity()`는 `StrategyBase._fallback_one_share(current_price)` 공통 헬퍼 사용. 잔여 = `total_investment - (positions buy_price×qty 합 + pending_buy_amounts 합)`. 결함 차단: 고정 `total_investment`와 직접 비교 → 자금 90% 점유 후 1주 추가 매수 → 전략 한도 초과(2026-05-11 운영 사고). `pending_buy_amounts`는 OrderEngine에서 `pending_buys.add` 옆 동기 등록(시장가/지정가 폴백/boot 복구) + `pending_buys.discard` 옆 동시 정리(체결/거부/실패/체결통보 매핑 실패) + `_reset_daily_state()` clear
- 매매 파라미터(`DEFAULT_PARAMS`) 변경 시 `_workspace/00_leader_trading_rules.md` 동기화

### 코딩 컨벤션
- Python: pydantic + async/await
- TS: 모든 API 응답은 `frontend/src/types/` 정의 사용
- API 응답 래퍼: `{ success: bool, data: T, message: str }` (`models/response.py` `ApiResponse`)
- KIS 호출은 반드시 `src/api/base.py::kis_request()` 경유 (Rate Limit·재시도·메트릭)
- TR_ID는 `settings.get_tr_id()` 사용 — 하드코딩 금지 (실전 T → 모의 V 자동 변환, FH 접두사는 동일)

## DB 스키마 (Supabase)

마이그레이션: `supabase/migrations/`. CRUD 모듈 상세: `src/db/CLAUDE.md`.

| 테이블 | 용도 |
|--------|------|
| `trade_history` | 거래 내역 (status: PENDING/COMPLETED/PARTIAL/CANCELLED) |
| `daily_performance` | 일일 실적 (date+strategy 복합PK, TWR 누적) |
| `positions` | 보유 포지션 영속화 (ticker PK) |
| `strategy_config` | 전략 설정 (strategy_id PK, params JSONB) |
| `system_config` | 시스템 설정 (auto_start 등) |
| `system_logs` | 시스템 로그 |
| `parameter_recommendations` | 19:50 AI자문 (target_date+strategy_id unique) |
| `daily_log_reports` | 20:10 일일 로그 분석 (target_date unique, metrics에 api_metrics/strategy_funnel/by_ticker_pnl/by_hour_pnl 포함) |
| `stock_master` | KIS CTPF1002R 캐시 (ticker PK, 24h TTL). NXT 거래가능 사전 판별 (migration 015) |

## Docker / 배포

- `Dockerfile` / `frontend/Dockerfile` 멀티스테이지(dev: hot-reload, prod: non-root + Nginx)
- `docker-compose.yml`(개발 hot-reload) / `docker-compose.prod.yml`(prod)
- `frontend/nginx.conf`: 정적파일 + `/api` → backend:8000 프록시
- 타임존 `TZ=Asia/Seoul`, vite 프록시 타겟은 `VITE_API_URL` 분기
- **EC2 t4g.small (ARM, ap-northeast-2)** 서비스 경로 `~/auto_stock/`
- 자동 배포: `git push origin main` → GitHub Actions가 EC2 SSH → `git pull` + 재빌드 (`.github/workflows/deploy.yml`)
- GitHub Secrets: `EC2_HOST`, `EC2_USERNAME`, `EC2_SSH_KEY`
- **로컬과 EC2 동시 실행 금지** — KIS 동일 계정 동시 접속 충돌

## 디렉토리 역할
- `src/auth/` — KIS OAuth 인증/토큰
- `src/api/` — KIS REST (주문·잔고·조건검색·일봉)
- `src/realtime/` — KIS WebSocket (시세·체결통보·H0NXMKO0)
- `src/engine/` — 매매 핵심 (전략·레지스트리·주문·리스크·스케줄러, 19:50 AI자문 `recommendation_engine.py`, 20:10 일일 로그 분석 `log_analysis_engine.py`)
- `src/db/` — Supabase CRUD
- `src/routes/` — FastAPI 엔드포인트
- `src/models/` — Pydantic 모델
- `frontend/` — React 대시보드
