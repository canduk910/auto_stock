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
| `volatility_breakout` | 보드별 K값 × 전일Range 돌파 (PRE_NXT/MAIN) | -3% 손절, 15:20 KRX 메인 일괄 청산 (OVERNIGHT 거부) |
| `long_tail_volatility` | VB 방식 + 상한가 도달 시 익일 청산 모드 전환 (PRE_NXT/MAIN) | 당일 -3% / 상한가 모드 -5%, **15:20 상한가 미도달 일괄 청산** / 상한가 모드는 익일 NXT 프리 청산 + POST_NXT 손절 모니터링 |
| `donchian_swing` | 코스피200+코스닥150 고정 유니버스, 20일 신고가+60일 EMA+거래대금 1.5×, 익일 09:05 시장가 (MAIN만) | ATR(14)×2 트레일링 / -7% 하드. 시간 청산 없음, 멀티데이 보유 |
| `bull_flag_breakout` | 폴(3~10일 +20%↑)+플래그(38.2% 이내 조정+거래량 수축)→플래그 상단 돌파+거래량≥평균×2 (MAIN 09:05~13:00) | -5% 손절 / 플래그 하단 이탈 / 측정된 이동(폴 폭) 익절+잔여 ATR×2 트레일링 / 5영업일 시간 청산. 종목당 1회 + 청산 후 3영업일 쿨다운 |
| `vcp_breakout` | 미네르비니식 VCP — 추세(50/150/200EMA 정렬+200EMA 1개월 우상향)+베이스(5~15주, 깊이≤25%)+2~4회 pullback 점진 수축+거래량 수축→베이스 상단 돌파+거래량≥20일 평균×1.5 (MAIN 09:05~14:30) | -7% 손절 / 베이스 하단 이탈 / ATR×2 트레일링 / 50일 EMA 이탈. 시간 청산 없음 — **멀티데이 보유** (`_MULTIDAY_STRATEGIES`). 종목당 1회 + 청산 후 7영업일 쿨다운 |

전략 동작·보드별 K값 분리·익일 청산 안정화·자금 락·라우팅 등 상세는 **`src/engine/CLAUDE.md`**.

### 외부 백테스트 + 자문 시스템 개선 사이클 (2026-05-16~17)
- **백테스트 통합 Phase 0~6.1**: 20:00 AI 자문 INSERT 직후 외부 MCP 백테스트 서버(`http://43.202.187.5:3846/mcp`)에 6 전략 × 2 kind=12 job fire-and-forget → `parameter_recommendations.backtest_summary` JSONB 동봉. (a) 외부 YAML 표현 3종(momentum/VB/donchian) / (b) 폴백 위임 3종(LTV/bull_flag/vcp). Phase 6 MCP content unwrap + 중첩 메트릭(`data.result.metrics.{basic,risk,trading}`) → 8 평탄 키 매핑. Phase 6.1 `max_drawdown` 양수(절대값) 컨벤션 확정 (`signInverted=true`)
- **자문 시스템 개선 사이클 1~4 (2026-05-17)**: 비중조절 사유 별도 필드(`weight_reasoning` 마이그 021) + UI 자산 배정 카드 최상단 / 시장 레짐 필터(dkstock.cloud 매크로 — `regime/vix/fear_greed` 복합 임계 매수 가드 + `cash_usage_ratio` 자동 조정, 마이그 022/023) / VB 보드별 손절 분리(`stop_loss_main`/`stop_loss_pre_nxt` 마이그 024) / 매크로 레짐 → AI 자문 user_payload 12 키 통합
- **활성화 토글**: `KIS_MCP_ENABLED=true` (백테스트) + `DKSTOCK_REGIME_ENABLED=true` (매크로) — 둘 다 비활성 기본. 외부 다운 시 graceful — 자문 INSERT 보존, summary=null, 매수 가드 비활성
- 운영 가이드 [`docs/backtest-monitoring.md`](docs/backtest-monitoring.md)

### 새 전략 추가
1. `src/engine/strategies/`에 StrategyBase 서브클래스 (prepare/check_buy_signal/check_exit_signal/calc_buy_quantity)
2. `src/engine/scheduler.py` `__init__`에서 `registry.register()`
3. 필요 시 `scanner.py`에 스캔 함수 추가
4. `_workspace/00_leader_trading_rules.md`에 명세 추가

### 자금 관리
- 프론트 Settings → `PUT /api/strategies/weights` → `StrategyRegistry.allocate_funds()`
- `position_ratio`는 **전략 할당 자금 기준** (순자산 × 전략비중 × position_ratio = 종목당 매수금액)
- 전략 간 동일 종목 중복 매수 방지: `registry.is_ticker_blocked_for_buy()` (보유/주문중/당일매도 통합 차단)
- **`cash_usage_ratio` (J3, 2026-05-12 → 사이클 2 확장 2026-05-17)**: `system_config.cash_usage_ratio` 키 — `_boot()` 가 `summary.net_asset × ratio` 로 `allocate_funds()` 호출. 범위 **[0.0, 1.0]** (마이그 023 — 사이클 2 매크로 자동 조정 수용), 5% 단위, 기본 1.0. Settings 슬라이더로 조정, **다음 영업일부터 반영**. `auto_regime_adjust=true` (기본) + `DKSTOCK_REGIME_ENABLED=true` 시 매크로 레짐 `cash_min` 기반 자동 갱신 (`clamp((100-cash_min)/100, 0.0, 1.0)`) — 운영자 Settings 에서 OFF 토글 가능 (수동값 보존)

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
- **WebSocket 시세 silent inactive 자동 복구 (K, 2026-05-12)**: 30s 주기 `_stale_watcher_loop` 가 `STALE_FRESHNESS_SECS=60s` 미수신 ticker 에 `_send_subscribe(subscribe=True)` 재발송. 3회 초과(`STALE_FORCE_REREGISTER_AFTER=3`) 시 `unsubscribe`+`subscribe(bypass_limit=True)` 강제 재등록(KIS 측 슬롯 리셋). 6회 초과 시 skip(다음 `_scan_loop` 5분 사이클 위임). fresh 회복 시 `_stale_retry_count` 자동 clear, `_reset_daily_state` 에서도 clear. F1(재연결 1회) + `_scan_loop`(5분) + K(30s) 3중 안전망. `start()` finally 블록에서 `_stale_watcher_task` cancel + None. `_subscriptions` set 직접 수정 금지 — `kis_ws.subscribe/unsubscribe/_send_subscribe` 만 사용. 2026-05-12 11:48 fresh=1/stale=26 운영 사고 대응
- **보드별 시가 확정 호출 `board=...` 명시 의무 (2026-05-15, 결함 A)**: `_confirm_breakout_open_prices()` 자동 결정 분기는 `SessionTracker.active` 를 main → post_nxt → pre_nxt 우선순위로 검색하는데, `_session_loop` 가 30초 주기라 보드 경계 정각 호출과 race 발생. 보드 경계 정각 3개는 반드시 명시 인자 — 08:00 `board="pre_nxt"` / 09:00:05 `board="main"` / 15:30 `board="post_nxt"`. 자동 결정 허용은 중간 부팅 / 스캔 시작 직전 재확정 같은 시점 가변 호출에 한정. 2026-05-14, 5/15 운영 사고 — 09:00:05 자동 결정이 `pre_nxt` 폴백 → `boards["main"]` 영영 비어 KRX 메인 시간대 VB/LTV 매수 신호 0건. 회귀 가드: `tests/integration/test_post_nxt_open_price_confirm.py` Case C/D
- **VB·LTV 당일 15:20 일괄매도 정책 (2026-05-15, 결함 D)**: VB/LTV 둘 다 `DEFAULT_TRADABLE_BOARDS = ("pre_nxt", "main")` — POST_NXT 제외, NXT 애프터 매수 비활성. `_force_clear_main_only` 가 keeps_post_nxt=False 분기로 `check_force_clear()` 호출 → VB 전체 / LTV 상한가 미도달 종목 시장가 청산. 19:50 청산 코드 부재 + POST_NXT 활성 조합으로 OVERNIGHT 자연 보유 결함 회복 (005930 5/13~5/15, 066570 5/15 사고). LTV 상한가 모드 종목은 `_limit_up_reached` set 분기로 `check_force_clear()` 가 제외 → 익일 NXT 프리 청산. POST_NXT 손절 모니터링은 `risk.on_tick` 청산 평가가 보드 가드 영향 받지 않아 그대로 작동 (보유 종목 시세는 항상 WS 구독). DB `strategy_config` 동시 갱신 필요. 회귀 가드: `tests/unit/engine/test_vb_force_clear_at_15_20.py`
- **VB 익일 청산 안전망 (2026-05-15, 결함 D 잔여 fix)**: `_execute_next_day_clear()` overnight_strategies 에 `volatility_breakout` 추가. VB Position 의 `is_next_day=True` 면 다음 영업일 NXT 프리 시가 청산. VB `__init__` 에 `_next_day_clear_pending=False` 초기화 + `check_exit_signal` 에 익일 청산 분기(pending 가드 + STOP_LOSS 우선) 추가. VB 정책상 정상 경로는 당일 15:20 일괄 청산이지만 그게 누락되는 비상 상황(POST_NXT 설정 오류, 시세 미수신, 시장가 거부, 프로세스 재시작 race)에서 본 경로가 발동. 2026-05-15 LG전자(066570) 사고 회복용 안전망. 회귀 가드: `tests/unit/engine/test_vb_next_day_clear_safety_net.py` 5 케이스
- **`_force_clear_main_only` KRX 메인 마감 시간 가드 (2026-05-15 hot fix)**: 함수 진입 즉시 `datetime.now().time() >= TIME_KRX_MAIN_CLOSE(15:30)` 이면 skip + 익일 청산 안전망 위임. 2026-05-15 16:04 재시작 시 line 380 의 `_force_clear_main_only()` 무조건 호출이 VB 보유(000100/066570) 를 SOR 시장가 매도 시도 → KRX 애프터 시간대 APBK3013(애프터마켓 지정가만 가능) 거부 × 3회 + 시세 캐시 미확보로 `step_down(가격,5)` 폴백 불발 → CRITICAL 매도 실패 6건 사고 차단. 회귀 가드: `tests/unit/engine/test_force_clear_time_guard.py` 3 케이스
- **donchian_swing 일중 시세 REST 폴링 (`_swing_rest_poll_loop`, B, 2026-05-15, 결함 B) 제거 금지**: 09:30~15:20 KRX 메인 시간대 60s 주기로 `donchian._scanned_tickers ∪ state.positions ∪ state.pending_buys` 합집합을 `fetch_stock_detail` 폴링 → `scanner.ticker_prices` 갱신 + `ticker_last_tick` touch + `ticker_names` 보강. 보유 종목 한정 `RiskManager.on_tick` 호출 → 기존 트레일링/하드 -7% 손절 평가 재사용 (별도 청산 경로 신설 금지). WebSocket stale(2026-05-15 ratio 11~45%) 대비 보강 — 멀티데이 보유의 손절 평가가 끊기지 않도록. 매수 평가는 `_swing_buy_poll_loop`(09:05~09:30) 전용 — 본 loop 는 시세 갱신 + 보유 평가만 책임. `risk.py:on_tick` 의 donchian_swing 매수 skip 가드 보존. WS 우선순위 큐(E1) 무관(REST 경로). 종목 사이 `await asyncio.sleep(0.05)` Rate Limit 보호. 회귀 가드: `tests/unit/engine/test_swing_rest_poll.py` 5 케이스
- **종목코드 형식 비대칭**: 진입은 6자리 숫자만(`ticker.isdigit()`), 사후처리는 6자리 영숫자(`isalnum()`) — ETF·신주인수권 자동매매 차단 + 좀비 포지션 방지
- **1주 폴백은 전략 잔여 자금 기준(2026-05-11 P1)** — 4개 전략 `calc_buy_quantity()`는 `StrategyBase._fallback_one_share(current_price)` 공통 헬퍼 사용. 잔여 = `total_investment - (positions buy_price×qty 합 + pending_buy_amounts 합)`. 결함 차단: 고정 `total_investment`와 직접 비교 → 자금 90% 점유 후 1주 추가 매수 → 전략 한도 초과(2026-05-11 운영 사고). `pending_buy_amounts`는 OrderEngine에서 `pending_buys.add` 옆 동기 등록(시장가/지정가 폴백/boot 복구) + `pending_buys.discard` 옆 동시 정리(체결/거부/실패/체결통보 매핑 실패) + `_reset_daily_state()` clear
- 매매 파라미터(`DEFAULT_PARAMS`) 변경 시 `_workspace/00_leader_trading_rules.md` 동기화

### 코딩 컨벤션
- Python: pydantic + async/await
- TS: 모든 API 응답은 `frontend/src/types/` 정의 사용
- API 응답 래퍼: `{ success: bool, data: T, message: str }` (`models/response.py` `ApiResponse`)
- KIS 호출은 반드시 `src/api/base.py::kis_request()` 경유 (Rate Limit·재시도·메트릭)
- TR_ID는 `settings.get_tr_id()` 사용 — 하드코딩 금지 (실전 T → 모의 V 자동 변환, FH 접두사는 동일)
- **모든 시각 데이터 UI 표출 시 한국시(KST, `Asia/Seoul`) 강제** — 백엔드는 `src/db/trade_history.py::_to_kst(iso)` 헬퍼로 ISO 파싱 후 `astimezone(KST).strftime()` 으로 명시 변환(UTC ISO 단순 슬라이스 금지). DB 비교 쿼리도 `_today_kst_iso()` 로 timezone 명시(`f"{today}T00:00:00+09:00"`) — TZ-naive 문자열은 PostgreSQL TIMESTAMPTZ 가 UTC 로 해석해 KST 09시 이전 매수 기록을 누락한다. 프론트엔드는 `Intl.DateTimeFormat / toLocaleString('ko-KR', { timeZone: 'Asia/Seoul', ... })` 명시 — `new Date(iso).getHours()` 등 브라우저 로컬타임 추출 금지. 적용 대상: 매매손익(`get_trade_pairs`) / 주문체결내역(`TradeHistoryGrid`) / 일일로그분석(`LogReports.formatDateTime`) / 모든 timestamp 필드. 2026-05-12 005930 보완 INSERT 사고(timezone 결함으로 09시 이전 매수 기록 누락 → 다른 가격/strategy 로 중복 INSERT) 대응

## DB 스키마 (Supabase)

마이그레이션: `supabase/migrations/`. CRUD 모듈 상세: `src/db/CLAUDE.md`.

| 테이블 | 용도 |
|--------|------|
| `trade_history` | 거래 내역 (status: PENDING/COMPLETED/PARTIAL/CANCELLED) |
| `daily_performance` | 일일 실적 (date+strategy 복합PK, TWR 누적) |
| `positions` | 보유 포지션 영속화 (ticker PK) |
| `strategy_config` | 전략 설정 (strategy_id PK, params JSONB) |
| `system_config` | 시스템 설정 (auto_start, **cash_usage_ratio** J3 등) |
| `system_logs` | 시스템 로그 |
| `parameter_recommendations` | 20:00 AI자문 (target_date+strategy_id unique). **J4 migration 016** — `recommended_weight`/`code_review_notes`/`applied_weight` 자산배정+로직 자문. **Phase 3 migration 020** `backtest_summary` JSONB. **사이클 1 migration 021** `weight_reasoning` 별도 사유 필드 (≤1000자) |
| `daily_log_reports` | 20:10 일일 로그 분석 (target_date unique, metrics에 api_metrics/strategy_funnel/by_ticker_pnl/by_hour_pnl 포함) |
| `stock_master` | KIS CTPF1002R 캐시 (ticker PK, 24h TTL). NXT 거래가능 사전 판별 (migration 015) |
| `backtest_runs` | 외부 MCP 백테스트 실행 영속화 (migration 019, Phase 2). `(target_date, strategy_id, params_kind)` UNIQUE. 6 전략 × 2 kind = 12 row/사이클, status ∈ queued/running/completed/failed/skipped |
| `market_regime_snapshots` | dkstock.cloud 매크로 일일 스냅샷 (migration 022, 사이클 2). `_boot()` 시점 1행. `buy_blocked`/`computed_cash_usage_ratio`/`raw_response JSONB` 영구 기록 |

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
- `src/engine/` — 매매 핵심 (전략·레지스트리·주문·리스크·스케줄러, 20:00 AI자문 `recommendation_engine.py`, 20:10 일일 로그 분석 `log_analysis_engine.py`, 백테스트 엔진 `backtest_engine.py`/`backtest_yaml.py`, 시장 레짐 `market_regime.py`)
- `src/services/` — 외부 서비스 클라이언트 (`mcp_client.py` 백테스트 MCP, `dkstock_client.py` 매크로)
- `src/db/` — Supabase CRUD
- `src/routes/` — FastAPI 엔드포인트
- `src/models/` — Pydantic 모델
- `frontend/` — React 대시보드
