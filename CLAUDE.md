# CLAUDE.md — 프로젝트 루트

KIS OpenAPI 기반 주식 자동매매시스템. FastAPI(백엔드) + React(프론트엔드) + Supabase(DB). 다중 전략 아키텍처.

> 디렉토리별 상세는 각 하위 `CLAUDE.md` 가 진실의 원천:
> `src/CLAUDE.md` · `src/engine/CLAUDE.md` · `src/engine/strategies/CLAUDE.md` · `src/api/CLAUDE.md` · `src/realtime/CLAUDE.md` · `src/db/CLAUDE.md` · `src/routes/CLAUDE.md` · `frontend/CLAUDE.md`
>
> 사이클별 변경 이력: [`docs/HARNESS_CHANGELOG.md`](docs/HARNESS_CHANGELOG.md)
> 시스템 흐름 도식: [`docs/architecture.md`](docs/architecture.md)

## 하네스: TDD-First Trading Team

**목표:** 모든 코드 변경을 Red→Green→Refactor 사이클로 강제하고, 변경 시 영향받는 테스트만 실행할 수 있는 정적 인덱스를 유지한다.

### 기본 진입점 — `team-leader` 우선

사용자의 모든 요청은 1차로 `Agent({subagent_type: "team-leader"})` 로 라우팅한다. team-leader 가 트레이더 관점에서 해석 후 하위 에이전트에 분배한다.

- 코드 변경 → `auto-trading-orchestrator` 스킬 (TDD 사이클: `tdd-engineer` Red → `backend-dev`/`frontend-dev` Green → `tester` 검증)
- 단위/회귀 테스트 → `tdd-cycle` (백엔드 pytest+respx+freezegun / 프론트엔드 vitest+RTL+MSW)
- 영향 인덱스 → `test-impact-index`
- 통합/경계면/E2E/안전성 → `trading-test`

**우회 허용 (메인 세션 직접 응답):** 단순 사실 질의, 단발 디버그/grep, 운영 환경 즉시 점검(EC2 SSH 등). 코드 변경 제안이 따라오면 다시 team-leader 로 인계.

### 모델 라우팅

| 작업 유형 | 모델 | 적용 |
|----------|------|------|
| 계획·검증 (구현 계획, 테스트 설계, 검수, 안전성 검증) | **opus** | `team-leader`, `tdd-engineer`, `tester` |
| 일반 구현 (코드 작성·리팩터·버그 수정) | **sonnet** | `backend-dev`, `frontend-dev` |
| 명령어 작성 (bash/슬래시/스크립트) | **haiku** | 메인 세션 단발 작업 — fork 또는 `claude-haiku-4-5-20251001` 위임 |

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
- `AUTO_START`: 서버 기동 시 자동 매매 시작 (DB `system_config.auto_start` 우선, 매일 시작 전 재확인)
- `DKSTOCK_REGIME_ENABLED` (기본 false): dkstock.cloud 매크로 + 매수 가드 + cash_usage_ratio 자동 조정 활성화
- `KIS_MCP_ENABLED` (기본 false): 외부 백테스트 MCP 서버 활성화. 자문 직후 6 전략 × 2 kind = 12 job fire-and-forget

## 다중 전략 (요약)

6 전략: `momentum` / `volatility_breakout` / `long_tail_volatility` / `donchian_swing` / `bull_flag_breakout` / `vcp_breakout`.

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
- **NXT 매도 거부 좀비 차단** — `is_market_closed_rejection` (APBK0918 + 장운영시간 외) 이면 `execute_sell` 이 positions(메모리/DB) 보존 + 재시도 중단. `is_insufficient_quantity` / `is_insufficient_cash` 와 분리
- **매수/매도 시장가 거부 → 지정가 5호가 폴백 1회** — `is_market_order_disallowed` (msg1 키워드 `시장가매매불가` / `시장가호가불가` / `최유리/최우선지정가 주문만` / `지정가 및 최유리` — APBK1943/APBK3013) 매칭 시 `step_up(buy)/step_down(sell)` 으로 `LIMIT` 재시도. 매핑 동기 + race 가드 동일 규약
- **KIS 거부 응답 영구 저장** — `_request` 가 `rt_cd != "0"` 시 `system_logs` prefix `[kis_rejection]` + path/tr_id/msg_cd/msg1 + body 주요 키 (민감 키 마스킹) fire-and-forget
- **WebSocket 시세 보유·익일청산 우선 보장** — `MAX_SUBSCRIPTIONS=41` KIS 공식 한도. HIGH (보유/익일청산) `bypass_limit=True` 절대 보장. 후순위 drop 시 `[priority_drop]` INFO + WARNING `system_logs`. HIGH 단독 41 초과 ERROR
- **WebSocket 다중 안전망** — F1 (재연결 1회) + `_scan_loop` (5분) + K stale watcher (120s, 5회 누적 후 강제 재등록) + `_resubscribe_stale_priority` (5분 우선) 4중. `_subscriptions` ACK 정합성 가드 (orphan ACK race 차단)
- **NXT 거래가능 사전 판별** — `stock_master.nxt_tradable=False` 면 NXT/SOR → KRX 강제 다운그레이드 + `[nxt_downgrade]`. `_boot()` eager 사전 갱신 (보유 + `_pending_next_day_clear` 합집합). 거부 사후 보강 `stock_master.upsert_one(ticker, nxt_tradable=False)`
- **종목코드 형식 비대칭** — 진입은 6자리 숫자만 (`isdigit()`), 사후처리는 6자리 영숫자 (`isalnum()`) — ETF·신주인수권 자동매매 차단 + 좀비 포지션 방지
- **1주 폴백은 전략 잔여 자금 기준** — 6 전략 `calc_buy_quantity()` 가 `StrategyBase._fallback_one_share(current_price)` 공통 헬퍼. 잔여 = `total_investment - (positions buy_price×qty + pending_buy_amounts 합)`
- **VB 당일 15:20 일괄매도** — `DEFAULT_TRADABLE_BOARDS=("pre_nxt", "main")`, POST_NXT 추가 금지. `_force_clear_main_only` 가 15:20 일괄 청산. 15:30 이후 호출은 시간 가드로 skip
- **donchian_swing `_swing_rest_poll_loop`** 제거 금지 — 09:30~15:20 60s REST 폴링으로 멀티데이 손절 평가 보강
- **모든 시각 데이터 KST 강제** — 백엔드 `_to_kst(iso)` 헬퍼 + `_today_kst_iso()` timezone 명시 (`+09:00`). 프론트 `Intl.DateTimeFormat(timeZone='Asia/Seoul')` 명시. `new Date(iso).getHours()` 브라우저 로컬타임 추출 금지
- 매매 파라미터 (`DEFAULT_PARAMS`) 변경 시 `_workspace/00_leader_trading_rules.md` 동기화

### 코딩 컨벤션
- Python: pydantic + async/await
- TS: 모든 API 응답은 `frontend/src/types/` 정의 사용
- API 응답 래퍼: `{ success: bool, data: T, message: str }` (`models/response.py` `ApiResponse`)
- KIS 호출은 반드시 `src/api/base.py::kis_request()` 또는 `kis_get_quote()` 경유 (Rate Limit·재시도·메트릭)
- TR_ID 는 `settings.get_tr_id()` 사용 — 하드코딩 금지

## DB 스키마 (Supabase)

마이그레이션: `supabase/migrations/`. CRUD 모듈 상세: `src/db/CLAUDE.md`.

| 테이블 | 용도 |
|--------|------|
| `trade_history` | 거래 내역 (status: PENDING/COMPLETED/PARTIAL/CANCELLED) |
| `daily_performance` | 일일 실적 (date+strategy 복합PK, TWR 누적, 실현손익 기준) |
| `positions` | 보유 포지션 영속화 (ticker PK) |
| `strategy_config` | 전략 설정 (strategy_id PK, params JSONB) |
| `system_config` | 시스템 설정 (auto_start, cash_usage_ratio, buy_block_mode + 4 임계값, dkstock_regime_enabled, kis_mcp_enabled 등) |
| `system_logs` | 시스템 로그 |
| `parameter_recommendations` | 20:00 AI자문 (target_date+strategy_id UNIQUE). `recommended_weight`/`code_review_notes`/`applied_weight`/`weight_reasoning`/`backtest_summary` JSONB |
| `daily_log_reports` | 20:10 일일 로그 분석 (target_date UNIQUE, metrics 에 api_metrics/strategy_funnel/by_ticker_pnl/by_hour_pnl/next_day_clear 포함) |
| `stock_master` | KIS CTPF1002R 캐시 (ticker PK, 24h TTL). NXT 거래가능 사전 판별 |
| `backtest_runs` | 외부 MCP 백테스트 영속화 (`(target_date, strategy_id, params_kind)` UNIQUE. 6 전략 × 2 kind = 12 row/사이클) |
| `market_regime_snapshots` | dkstock.cloud 매크로 일일 스냅샷. `_boot()` 시점 1행. `buy_blocked`/`computed_cash_usage_ratio`/`raw_response JSONB` 영구 기록 |
| `kis_quote_accounts` | 보조 KIS 시세 수신 계좌 (UUID PK, label UNIQUE, active=true 부분 인덱스). `list_accounts()` 60s TTL 메모리 캐시 |

## Docker / 배포

- `Dockerfile` / `frontend/Dockerfile` 멀티스테이지 (dev: hot-reload / prod: non-root + Nginx)
- `docker-compose.yml` (개발 hot-reload) / `docker-compose.prod.yml` (prod)
- **토큰 캐시 영속화 (사이클 20, 2026-05-20)**: `./.token_cache:/app/.token_cache` 디렉토리 볼륨 양쪽 compose 동일 마운트. KIS `/oauth2/tokenP` 분당 1개 한도 + 컨테이너 재기동 시 토큰 24h 유효 보존. `.gitignore` 등록 (`.token_cache/` + 구 `.token_cache_quote_*.json` 호환). 구 경로 `.token_cache.json` 존재 시 자동 마이그레이션
- `frontend/nginx.conf`: 정적파일 + `/api` → backend:8000 프록시
- 타임존 `TZ=Asia/Seoul`, vite 프록시 타겟은 `VITE_API_URL` 분기
- **EC2 t4g.small (ARM, ap-northeast-2)** 서비스 경로 `~/auto_stock/`
- 자동 배포: `git push origin main` → GitHub Actions 가 EC2 SSH → `git pull` + 재빌드 (`.github/workflows/deploy.yml`). push 시각 → pool_start 지연 1~5분
- GitHub Secrets: `EC2_HOST`, `EC2_USERNAME`, `EC2_SSH_KEY`
- **로컬과 EC2 동시 실행 금지** — KIS 동일 계정 동시 접속 충돌
- 운영 가이드: KRX 메인 시간 (09:00~15:30) 중 빈번한 push 자제 — `_scan_loop` 5분 race 가능. NXT 애프터 (15:30~) 또는 익일 07:50 _boot 전 push 권장

## 디렉토리 역할
- `src/auth/` — KIS OAuth 인증/토큰 (메인 + 보조 multi)
- `src/api/` — KIS REST (주문·잔고·조건검색·일봉) + 시세 풀 (`base.py::_request_via_quote_pool` + path 화이트리스트 가드)
- `src/realtime/` — KIS WebSocket (시세·체결통보·H0NXMKO0) + WebsocketPool 멀티 세션 분배
- `src/engine/` — 매매 핵심 (전략·레지스트리·주문·리스크·스케줄러). `recommendation_engine.py` 20:00 AI자문 / `log_analysis_engine.py` 20:10 일일 분석 / `backtest_engine.py` + `backtest_yaml.py` / `market_regime.py`
- `src/engine/strategies/` — 6 전략 명세 (전용 CLAUDE.md)
- `src/services/` — 외부 서비스 클라이언트 (`mcp_client.py` 백테스트 MCP / `dkstock_client.py` 매크로 / `quote_session_health.py` 보조 세션 health monitor)
- `src/db/` — Supabase CRUD
- `src/routes/` — FastAPI 엔드포인트
- `src/models/` — Pydantic 모델
- `frontend/` — React 대시보드
