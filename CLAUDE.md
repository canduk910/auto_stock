# CLAUDE.md — 프로젝트 루트

KIS OpenAPI 기반 주식 자동매매시스템. FastAPI(백엔드) + React(프론트엔드) + Supabase(DB). 다중 전략 아키텍처.

> 디렉토리별 상세는 각 하위 `CLAUDE.md` 가 진실의 원천:
> `src/CLAUDE.md` · `src/engine/CLAUDE.md` · `src/engine/strategies/CLAUDE.md` · `src/api/CLAUDE.md` · `src/realtime/CLAUDE.md` · `src/db/CLAUDE.md` · `src/routes/CLAUDE.md` · `frontend/CLAUDE.md`
>
> 사이클별 변경 이력: [`docs/HARNESS_CHANGELOG.md`](docs/HARNESS_CHANGELOG.md)
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
| 계획·검증·자문 (구현 계획, 테스트 설계, 검수, 안전성 검증, 도메인 자문, 리팩토링 검토) | **opus** | `team-leader`, `domain-expert`, `tdd-engineer`, `tester`, `refactor-expert` |
| 일반 구현 (코드 작성·리팩터·버그 수정) | **sonnet** | `backend-dev`, `frontend-dev` |
| 명령어 작성 (bash/슬래시/스크립트) | **haiku** | 메인 세션 단발 작업 — fork 또는 `claude-haiku-4-5-20251001` 위임 |

### 하네스 변경 이력

| 날짜 | 변경 내용 | 대상 | 사유 |
|------|----------|------|------|
| 2026-04-22 | 초기 구성 (team-leader / backend-dev / frontend-dev / tdd-engineer / tester) | 전체 | TDD-First Trading Team 출범 |
| 2026-05-21 | `domain-expert` (데이/스윙 트레이더 자문) + `refactor-expert` (주기적 리팩토링) 합류, KIS MCP 접근 명시 (backend-dev / tdd-engineer / tester / refactor-expert) | 에이전트 7명 / 스킬 9개 | 매매 의사결정 깊이 보강 + 코드 품질 드리프트 흡수 + KIS 스펙 정본 통일 |
| 2026-05-21 | `kis-mcp-query` 스킬에 KIS 공식 저장소 경로 + 설치 가이드 + 공식 프롬프트 도구 (`kis_easy_code`/`kis_detailed_code`) 활용 안내 추가 | skills/kis-mcp-query | 공식 저장소 (koreainvestment/open-trading-api) 가 정본임을 명시, 비공식 fork 사용 차단 |
| 2026-05-21 | 사이클 28~37 (운영 진단 + 결함 시정 11 사이클) — 상세는 `docs/HARNESS_CHANGELOG.md` 참조. 코드 본체: stale 추적 강화 / force_retry / silent_inactive 비율 / 우선순위 분리 / `_sync_orders_to_db` 핑퐁 수정 / risk_silent_skip 가시화 / universe 가드 + `inquire_ccnl` / BFB acml_vol + VCP fetch 한도 / funnel DB + 세션 UI / KST NameError + backtest pending / KIS 체결시각 UI | `src/engine/scheduler.py` 외 다수 + 신규 라우트 `/api/strategy-funnel` + migration 029/030 | 09:13 VB 미매수 사고 진단을 시작점으로 stale 추적 → 결함 가시화 → 시정 + funnel DB 추적 → UI 강화. 백엔드 1625 PASS / 프론트 160 PASS / 매매 안전성 무영향 |
| 2026-05-22 | 사이클 38~43 (정책 명문화 + funnel 진단 + ping-pong 가시성 + 라벨 통일 6 사이클) — 상세는 `docs/HARNESS_CHANGELOG.md` 참조. 38(LTV 디폴트 PRE_NXT+MAIN+POST_NXT 복원 + `tradable_boards` 매수 진입 전용 정책 명문화) / 39(BFB·VCP·donchian funnel 단계별 자동 hook + VCP 프론트 키 매핑 시정 + 09:30 자동 snapshot) / 40(BFB 폴 음봉 임계 완화 DB only) / 41(funnel 단계별 종목명 + 탈락 사유 정밀 추적 + UI 조건 툴팁) / 42(PINGPONG echo DEBUG + `[ws_heartbeat]` 5분 통계) / 43(세션 라벨 `quote-1/2/3` → DB 라벨 `ISA/sub/gold` 통일) | `src/engine/strategies/long_tail_volatility.py` / `strategy_base.py` / `risk.py` / 3 전략 prepare / `src/realtime/websocket.py` / `websocket_pool.py` / `frontend/src/pages/StrategyFunnel.tsx` / `ScanMonitor.tsx` / `KisAccountPoolCard.tsx` | 백엔드 1671 PASS / 프론트 160 PASS / 매매 안전성 무영향. 사이클 33 BFB+VCP fix 효과 확인 (BFB 30→24, VCP 113→113), 사이클 41 Pullback 9→0 새 결함 위치 영구 기록. 사이클 42 운영 실측: 메인 PINGPONG 11~14s 간격 정상, 보조 시세 세션은 PINGPONG 미수신 (KIS 정책 추정). 사이클 43 라벨 통일로 `[ws_heartbeat]` / `[tick_coverage_session]` / `[stale_watcher_detail]` 모두 사용자 DB 라벨 (ISA/sub/gold) 일관 |
| 2026-06-05 | 사이클 62 가격 필터 — 매수 진용 가격대 차단 신규 기능 (백엔드 + 프론트 단일 사이클, MEDIUM, domain-expert 옵션 A 자문 전부 적용). `system_config` 3 키 (`price_filter_min` / `price_filter_max` / `price_filter_mode`, 디폴트 0/0/OFF). risk.on_tick 단일 진입점 (`check_exit_signal` 분기 *후*, `check_buy_signal` *전* — 사이클 38 명문화 영속). **3 모드** (HARD/WARN/OFF). **Q2 fallback**: `scanner.ticker_prev_close` 우선 + `current_price` fallback (갭상승 시점 결함 회피). 60s TTL 캐시 (사이클 56-E 답습). **Q3 가드**: 시장가 거부 5호가 폴백 시 필터 재평가 0건 (E-4 AST 정적 영속). 일일 집계 `[price_filter_daily_summary]` `_settle()` 직전. 신규 라우트 `GET/PUT /api/system/price-filter`. 신규 UI `PriceFilterCard` (9 testid + 권장값 툴팁 5,000/1,000,000). 회귀 가드 38 케이스 (백 33 + 프 5). 백엔드 1882 → **1915 PASS** (+33) / 프론트 160 → **167 PASS** (+7) / 전체 **2082 PASS** / coverage 80.96% / flakiness 0 (3 회 반복) / 회귀 0 / V12 백엔드↔프론트 정합 100%. **매도 영향 0** (사이클 38 명문화 영속 + Q3 가드). | `src/db/system_config.py` (PriceFilter Pydantic + 3 키 헬퍼) / `src/engine/risk.py` (on_tick 필터 분기 + 60s TTL 캐시 + emit 3종 + reset 확장) / `src/engine/scheduler.py` (`_settle` 직전 daily_summary) / `src/routes/system.py` (GET/PUT + invalidate 즉시 반영) / `frontend/src/types/price-filter.ts` 신규 / `frontend/src/api/price-filter.ts` 신규 / `frontend/src/components/PriceFilterCard.tsx` 신규 282L / `frontend/src/pages/Settings.tsx` (+3) / 테스트 11 파일 신규 (백 10 + 프 1) / `src/db/CLAUDE.md` + `src/engine/CLAUDE.md` + `frontend/CLAUDE.md` 동기화 | domain-expert 자문 Q1~Q6 + Q7~Q11 전부 적용 (옵션 A) — Q2 fallback / Q4 3 모드 (HARD 단일 반박, 시장 신뢰 형성) / Q5 즉시 + 60s TTL (5분 grace 금지). 사이클 60/61 hotfix flakiness 차단 패턴 영속 (카테고리 분리 측정 + 3 회 반복). 사이클 38 명문화 (`tradable_boards` 매수 진입 전용) 답습 + Q3 추가 가드 (order_engine 폴백 무변경). 매매 안전성 무영향 — 디폴트 OFF + 매수 차단만 (자금 손실 영역 아님). Q7 거래대금 동행 필터 = **사이클 63 별개 카드 #13** 발의. tester V12 백엔드 ApiResponse<PriceFilter> 래퍼 ↔ 프론트 `data.data` 추출 정합성 100% 확인. |
| 2026-06-05 | 사이클 61 Phase 2-A2 — refactor #2 stale_manager 추출 2단계 (MEDIUM, 4 함수 314L + 5 상수 추가 이주). 사이클 60 A1 패턴 답습. `_detect_silent_inactive_sessions` (62L, KIS LMS/앱키 정지 위험) + `_force_reconnect_session` (83L) + `_delta_unsubscribe_dropped` (52L) + `_evaluate_universe_guard` (117L, 보유/익일청산 보호). 5 상수 추가 (`STALE_FRESHNESS_SECS` + `SILENT_INACTIVE_*` 4). 누적 9 함수 + 10 상수. **사이클 60 lazy import 빚 청산** + `sys.modules.get` 패턴 (D-1 AST 가드 통과 + patch 호환). scheduler.py 3,605 → 3,315L (−290L). stale_manager.py 358 → 731L. 회귀 가드 20 케이스 (HIGH 3: C cap dict / I universe 보유 / J universe 익일청산). 백엔드 **1862 → 1882 PASS** (+20, 회귀 0) / coverage 80.66% / flakiness 0 (3 회 반복 확인). 매매 안전성 무영향 (행위 보존). 누적 scheduler.py 감소: 사이클 51 전 ~4,185 → 현 3,315 (**−870L, −21%**). | `src/engine/stale_manager.py` +373L (358→731) / `src/engine/scheduler.py` −290L (3,605→3,315) / `tests/unit/engine/test_cycle61_phase2A2_*.py` 12 파일 신규 (20 케이스) / `src/engine/CLAUDE.md` 모듈 맵 + 본문 사이클 61 행 / `_workspace/test_index.yaml` 영향 인덱스 갱신 | A1 완료 후 도메인 자문 옵션 B 3 단계 분할의 2 단계 — 사이클 60 패턴 직답습 (logger 명시 binding / re-export / 12 파일 분리). tester 카테고리 분리 측정 + flakiness 3 회 반복 = 사이클 58/60 hotfix 패턴 영구 절차화. A3 (사이클 63) = `_check_and_resubscribe_stale` 221L + `_resubscribe_stale_priority` 100L = WebSocket 4 중 안전망 핵심 — 주말 push 의무 + 월요일 1h verify. 신규 발견: stale_manager.py 731L 비대화 → 향후 sub-module 분해 (cap_per_hour / fresh_ratio / universe_guard) refactor-expert 검토 대상 등록 권고. |
| 2026-06-04 | 사이클 60 Phase 2-A1 — refactor #2 stale_manager 추출 1단계 (LOW, 5 함수 + 5 상수). domain-expert 자문 옵션 B 3 단계 분할 전체 채택 — A2/A3 별도 사이클 (61/62). `src/engine/stale_manager.py` 신규 358L (사이클 51 boot_manager 패턴 답습 — scheduler 인자 + 2 줄 wrapper 위임). scheduler.py 3,880 → 3,605L (−275L, −7.1%). hotfix 1건: logger `__name__` → `"src.engine.scheduler"` 명시 binding (사이클 28 회귀 가드 4 FAIL → 4 PASS + I1 영구 가드 신규). 백엔드 **1844 → 1862 PASS** (+18, 회귀 0) / coverage 80.62%. 매매 안전성 무영향 (행위 보존). | `src/engine/stale_manager.py` 신규 / `src/engine/scheduler.py` 5 상수 re-export + 5 wrapper / `tests/unit/engine/test_cycle60_phase2A1_stale_manager.py` 18 케이스 / `src/engine/CLAUDE.md` 모듈 맵 + 본문 사이클 60 행 / `_workspace/test_index.yaml` 영향 인덱스 | refactor-review 2026-06-04 카드 #2 (HIGH) 의 A1 단독 진행 — 사이클 51 boot_manager 답습 + 도메인 자문 (영구 hot path / KIS LMS/앱키 정지 chain 위험) 반영해 3 단계 분할 채택. tester 가 카테고리 분리 측정으로 flakiness (4 FAIL caplog 누수) 영구 차단 — 사이클 58 hotfix 패턴 답습. 별개 위험 식별: `src/engine/*.py` 14 모듈 `__name__` logger 사용 — 운영 logging.yaml 한정 핸들러 영향 잠재 (별도 risk-review 카드 후보). Q6 별개 카드 #11 (보드 전환 ↔ K stale watcher mutex) 본 사이클 종료 후 발의. |
| 2026-06-04 | 사이클 60 hotfix — CI backend-test 6시간 hang 영구 차단 (사이클 55+ 회귀). 사이클 55 R-1 Q3 `get_balance()` 호출 추가 후 unit 테스트 mock 누락 → `.env` 없는 CI 환경에서 무한 hang → GitHub Actions 6시간 cancel (run 5건 누적). `test_b1::S3a` + `test_order_engine_sell_fallback::D1` 두 위치에 `mock_get_balance` fixture 추가 + 영구 가드 도입 (pytest-timeout 60s + ci.yml `timeout-minutes: 15` 2중). 변경 통계 5 files / +40 / production code 무변경. 백엔드 **1844 passed in 47.04s** / coverage 80.38% / 회귀 0건. | `tests/unit/engine/test_b1_market_closed_zombie_block.py` / `tests/unit/engine/test_order_engine_sell_fallback.py` / `pyproject.toml` (`timeout = 60`) / `requirements-dev.txt` (`pytest-timeout>=2.3`) / `.github/workflows/ci.yml` (`backend-test.timeout-minutes: 15`) | 사이클 58 hotfix 와 유사 패턴 (production code 변경 → mock 갱신 누락). 영구 timeout 가드로 동일 결함 재발 시 1분 내 FAIL 보장. CI run 5건 = 30시간 wasted compute 회수. 향후 tester 체크리스트 *push 후 CI conclusion 확인 의무화* 권고. |
| 2026-05-31 | 사이클 49 — VCP Pullback "마지막 폭 0.0%" 결함 시정 (운영 funnel 확정). 사이클 48 BFB/VCP 전면 시정 후에도 VCP 단독 30일 연속 0건 매매 잔존 → 5/26~5/29 funnel 33/33 우량주 step 6 동일 사유 탈락 → `_check_pullback_sequence` 의 (a) 마지막 swing 미완성 누락 + (b) 등호 포함 노이즈 swing 폭주 root cause 시정. ATR threshold ZigZag (신규 `min_swing_atr_mult=0.5`) + state machine 마지막 swing 포함 + funnel reason 정확성 (`last_pullback_pct` 항상 기록). | `src/engine/strategies/vcp_breakout.py` (DEFAULT_PARAMS + `_check_pullback_sequence` 재설계) + 회귀 가드 `tests/unit/engine/strategies/test_cycle49_vcp_pullback_width_fix.py` 6 케이스 + `_workspace/00_leader_trading_rules.md` 6-F 명세 동기화 + `src/engine/strategies/CLAUDE.md` VCP 행 갱신 | 백엔드 1748 PASS (1742→+6) / 다른 5 전략 + scan/매매 흐름 무영향 — 매수 진입 임계만 시정. 사이클 41 funnel 진단의 종결 (진단만 했고 시정 안 된 채 누적). 다음 영업일(2026-06-01) 09:30 funnel snapshot step 6 통과 카운트 > 0 확인 + 첫 거래 발생 시 4중 청산 (손절/베이스 하단/ATR 트레일링/50일 EMA) 정상 발화 tester 검증 필요. PR #16 (카피 정합화) 무관 별도 브랜치 `cycle49/vcp-pullback-width-fix` |

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
- **NXT 매도 거부 좀비 차단** — `is_market_closed_rejection` (APBK0918 + 장운영시간 외) 이면 `execute_sell` 이 positions(메모리/DB) 보존 + 재시도 중단. `is_insufficient_quantity` / `is_insufficient_cash` 와 분리. **사이클 55 R-1 (2026-06-03) `SellRejectionTracker.is_blocked()` 진입 게이트**: **2단계 TTL** — KRX 메인(09:00~15:30) 거부 = 5분 TTL (일시 장애 가정), NXT 시간대(08:00~09:00 / 15:30~20:00) 거부 = 다음 KST 09:00 TTL. `market_order_disallowed` 거부 = 30초 TTL (동일 tick 폭주 차단). NXT 폴백 실패 시 `_pending_next_day_clear` 익일 청산 자동 전환. `_reset_daily_state` 동행 clear (`_sell_rejection.reset_daily()` 4 필드 일괄 위임, `OrderEngine.reset_daily_state()` 캡슐화 보존). 호환 layer property `_market_closed_blocked` / `_market_closed_blocked_logged_today` 는 tracker 내부 dict/set 직접 노출 (is 동일성 보장)
- **매수/매도 시장가 거부 → 지정가 5호가 폴백 1회** — `is_market_order_disallowed` (msg1 키워드 `시장가매매불가` / `시장가호가불가` / `최유리/최우선지정가 주문만` / `지정가 및 최유리` — APBK1943/APBK3013) 매칭 시 `step_up(buy)/step_down(sell)` 으로 `LIMIT` 재시도. 매핑 동기 + race 가드 동일 규약
- **KIS 거부 응답 영구 저장** — `_request` 가 `rt_cd != "0"` 시 `system_logs` prefix `[kis_rejection]` + path/tr_id/msg_cd/msg1 + body 주요 키 (민감 키 마스킹) fire-and-forget
- **WebSocket 시세 보유·익일청산 우선 보장** — `MAX_SUBSCRIPTIONS=41` KIS 공식 한도. HIGH (보유/익일청산) `bypass_limit=True` 절대 보장. 후순위 drop 시 `[priority_drop]` INFO + WARNING `system_logs`. HIGH 단독 41 초과 ERROR
- **WebSocket 다중 안전망** — F1 (재연결 1회) + `_scan_loop` (5분) + K stale watcher (120s, 1~5회 즉시 강제 재등록 + 사이클 29-R1: 6회 초과 시 5분 cooldown 기반 시간 기반 force_retry + 시간당 12회 cap) + `_resubscribe_stale_priority` (5분 우선) 4중. K stale watcher 양쪽 분기에 우선순위 분리 (사이클 29-R3: positions/`_pending_next_day_clear` HIGH+bypass=True, 그 외 후보 LOW+bypass=False — 메인 편중 차단). `_subscriptions` ACK 정합성 가드 (orphan ACK race 차단)
- **세션 단위 silent inactive 자동 reconnect** — `_detect_silent_inactive_sessions` 3중 가드 (사이클 29-R2): `fresh_ratio < SILENT_INACTIVE_FRESH_RATIO_THRESHOLD(=0.2, 20%)` + `subscribed_count >= 5` + 5분 지속 → `_ws.close()` 강제 reconnect. 시간당 세션당 2회 cap (LMS/앱키 정지 위험 차단)
- **stale universe 가드** (사이클 32) — `_evaluate_universe_guard`: stale>5 + `today_volume < UNIVERSE_LOW_VOLUME_THRESHOLD(=10_000)` 종목 자동 unsubscribe + `_universe_excluded_today` 등록 + `[universe_excluded]` INFO + `inquire_ccnl` 으로 마지막 체결시각 로그. 보유/익일청산 절대 보호 + `_reset_daily_state` 동행 clear (영구 블랙리스트 금지)
- **`trade_history` 중복 INSERT 차단** (사이클 30) — `_sync_orders_to_db` 는 `get_today_buy_trades_for_sync()` / `get_today_sell_trades_for_sync()` 사용 (dedupe 없음 + CANCELLED 제외). DB 부분 UNIQUE 인덱스 `(ticker, order_no, trade_type)` 이중 안전망. 기존 `get_today_buy_trades()` 의 ticker dedupe 는 포지션 복구용 — 절대 sync 중복 판정에 사용 금지
- **NXT 거래가능 사전 판별** — `stock_master.nxt_tradable=False` 면 NXT/SOR → KRX 강제 다운그레이드 + `[nxt_downgrade]`. `_boot()` eager 사전 갱신 (보유 + `_pending_next_day_clear` 합집합). 거부 사후 보강 `stock_master.upsert_one(ticker, nxt_tradable=False)`
- **종목코드 형식 비대칭** — 진입은 6자리 숫자만 (`isdigit()`), 사후처리는 6자리 영숫자 (`isalnum()`) — ETF·신주인수권 자동매매 차단 + 좀비 포지션 방지
- **1주 폴백은 전략 잔여 자금 기준** — 6 전략 `calc_buy_quantity()` 가 `StrategyBase._fallback_one_share(current_price)` 공통 헬퍼. 잔여 = `total_investment - (positions buy_price×qty + pending_buy_amounts 합)`
- **VB 당일 15:20 일괄매도** — `DEFAULT_TRADABLE_BOARDS=("main",)` (사이클 26), POST_NXT 추가 금지. `_force_clear_main_only` 가 15:20 일괄 청산. 15:30 이후 호출은 시간 가드로 skip
- **`tradable_boards` 는 매수 진입 전용** (사이클 38, 2026-05-22 명문화) — 매도/손절/Trailing/익일청산/15:20 강제청산/상한가 손절 모니터링은 어떤 전략에서도 PRE/MAIN/POST 무관 항상 작동. `risk.on_tick` 의 `check_exit_signal` 분기는 `session_tracker.is_tradable` 검사 *전* 진입. LTV `DEFAULT_TRADABLE_BOARDS=("pre_nxt", "main", "post_nxt")` (사이클 38 사용자 의도 복원 — 연속 상한가 익일 청산 + 야간 매수)
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
| `daily_log_reports` | 20:10 일일 로그 분석 (target_date UNIQUE, metrics 에 api_metrics/strategy_funnel/by_ticker_pnl/by_hour_pnl/next_day_clear 포함). **사이클 58 V-2**: input_tokens/output_tokens/total_tokens/latency_ms/cost_estimate_usd 5 컬럼 추가 (migration 031, 모두 NULL 허용) |
| `stock_master` | KIS CTPF1002R 캐시 (ticker PK, 24h TTL). NXT 거래가능 사전 판별 |
| `backtest_runs` | 외부 MCP 백테스트 영속화 (`(target_date, strategy_id, params_kind)` UNIQUE. 6 전략 × 2 kind = 12 row/사이클) |
| `market_regime_snapshots` | dkstock.cloud 매크로 일일 스냅샷. `_boot()` 시점 1행. `buy_blocked`/`computed_cash_usage_ratio`/`raw_response JSONB` 영구 기록 |
| `kis_quote_accounts` | 보조 KIS 시세 수신 계좌 (UUID PK, label UNIQUE, active=true 부분 인덱스). `list_accounts()` 60s TTL 메모리 캐시 |
| `strategy_funnel_snapshots` | 사이클 34 — 전략별 조건검색 단계별 후보/탈락 종목 영구 추적. `(target_date, strategy_id, step_no, snapshot_at)` UNIQUE. `survived_tickers` JSONB cap 200 / `excluded_sample` JSONB cap 20. 수동 trigger `POST /api/strategy-funnel/snapshot` (현재 최종 단계 `step_no=99` 만, 자동 hook 은 후속 사이클) |

> **`trade_history` 부분 UNIQUE 인덱스 (사이클 30, migration 029)**: `uq_trade_history_ticker_order_no_type ON (ticker, order_no, trade_type) WHERE order_no IS NOT NULL AND order_no != ''`. `_sync_orders_to_db` 핑퐁 INSERT 영구 차단 + NULL/빈 order_no (수동 매매 사전 등) 호환.

## Docker / 배포

- `Dockerfile` / `frontend/Dockerfile` 멀티스테이지 (dev: hot-reload / prod: non-root + Nginx)
- `docker-compose.yml` (개발 hot-reload) / `docker-compose.prod.yml` (prod)
- **토큰 캐시 영속화 (사이클 20, 2026-05-20)**: `./.token_cache:/app/.token_cache` 디렉토리 볼륨 양쪽 compose 동일 마운트. KIS `/oauth2/tokenP` 분당 1개 한도 + 컨테이너 재기동 시 토큰 24h 유효 보존. `.gitignore` 등록 (`.token_cache/` + 구 `.token_cache_quote_*.json` 호환). 구 경로 `.token_cache.json` 존재 시 자동 마이그레이션
- **`.token_cache` 빌드 시점 권한 보장 (사이클 22, 2026-05-20)**: `Dockerfile` prod 스테이지가 `mkdir -p /app/.token_cache` → `chown -R appuser:appuser /app` → `USER appuser` 순서. 호스트 bind mount 가 root:root 로 생성되어 `appuser` 가 쓰기 거부되던 결함 영구 차단 (회귀 가드: `tests/integration/test_dockerfile_token_cache_perms.py`)
- `frontend/nginx.conf`: 정적파일 + `/api` → backend:8000 프록시
- 타임존 `TZ=Asia/Seoul`, vite 프록시 타겟은 `VITE_API_URL` 분기
- **EC2 t4g.small (ARM, ap-northeast-2)** 서비스 경로 `~/auto_stock/`
- 자동 배포: `git push origin main` → GitHub Actions 가 EC2 SSH → `git pull` + 재빌드 (`.github/workflows/deploy.yml`). push 시각 → pool_start 지연 1~5분
- GitHub Secrets: `EC2_HOST`, `EC2_USERNAME`, `EC2_SSH_KEY`
- **로컬과 EC2 동시 실행 금지** — KIS 동일 계정 동시 접속 충돌
- 운영 가이드: KRX 메인 시간 (09:00~15:30) 중 빈번한 push 자제 — `_scan_loop` 5분 race 가능. NXT 애프터 (15:30~) 또는 익일 07:50 _boot 전 push 권장

## 디렉토리 역할
- `src/auth/` — KIS OAuth 인증/토큰 (메인 + 보조 multi)
- `src/api/` — KIS REST (주문·잔고·조건검색·일봉) + 시세 풀 (`base.py::_request_via_quote_pool` + path 화이트리스트 가드). 사이클 32: `quotation.py::inquire_ccnl(ticker, market='J')` 신규 (FHKST01010100 주식현재가 시세, output[0] + today_volume 합산 + graceful None)
- `src/realtime/` — KIS WebSocket (시세·체결통보·H0NXMKO0) + WebsocketPool 멀티 세션 분배
- `src/engine/` — 매매 핵심 (전략·레지스트리·주문·리스크·스케줄러). `recommendation_engine.py` 20:00 AI자문 / `log_analysis_engine.py` 20:10 일일 분석 / `backtest_engine.py` + `backtest_yaml.py` / `market_regime.py`
- `src/engine/strategies/` — 6 전략 명세 (전용 CLAUDE.md)
- `src/services/` — 외부 서비스 클라이언트 (`mcp_client.py` 백테스트 MCP / `dkstock_client.py` 매크로 / `quote_session_health.py` 보조 세션 health monitor)
- `src/db/` — Supabase CRUD
- `src/routes/` — FastAPI 엔드포인트
- `src/models/` — Pydantic 모델
- `frontend/` — React 대시보드
