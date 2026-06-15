# CLAUDE.md — 프로젝트 루트

KIS OpenAPI 기반 주식 자동매매시스템. FastAPI(백엔드) + React(프론트엔드) + Supabase(DB). 다중 전략 아키텍처.

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
| 계획·검증·자문 (구현 계획, 테스트 설계, 검수, 안전성 검증, 도메인 자문, 리팩토링 검토) | **opus** | `team-leader`, `domain-expert`, `tdd-engineer`, `tester`, `refactor-expert` |
| 일반 구현 (코드 작성·리팩터·버그 수정) | **sonnet** | `backend-dev`, `frontend-dev` |
| 명령어 작성 (bash/슬래시/스크립트) | **haiku** | 메인 세션 단발 작업 — fork 또는 `claude-haiku-4-5-20251001` 위임 |

### 하네스 변경 이력 (요약)

각 행은 한 줄 요약. 사용자 보고 verbatim / 회귀 가드 / 영속 의무 매트릭스 / 운영 효과 등 상세는 [`docs/HARNESS_CHANGELOG.md`](docs/HARNESS_CHANGELOG.md) 참조.

| 날짜 | 변경 내용 | 대상 | 사유 |
|------|----------|------|------|
| 2026-06-15 | 사이클 137 — AST 가드 49 파일 DRY 2차 마이그레이션 (LOW, 10 파일) | `tests/unit/ast/_ast_helpers.py` 185L → 240L (+55L 2 헬퍼 `find_constant_value` + `count_string_occurrences`) / `tests/unit/ast/test_cycle137_ast_dry_continuation.py` 신규 (149L 4 케이스) / 10 파일 마이그레이션 (사이클 72/74/79/81/84/90/93/122/124/128) | 사이클 130 권고 카드 #25 (LOW) 후속 마이그레이션. 누적 17 파일 (사이클 136 7 + 137 10) + 잔존 ~22 파일 (사이클 138/139 종결 예상). 의미 전환 1건 (사이클 136 D1 compact 200L → 250L K-2). 백엔드 2,708 PASS × 2회 flakiness 0 / AST 디렉토리 전수 138 PASS / 매매 안전성 무영향 (테스트 영역 한정) |
| 2026-06-15 | 사이클 136 — AST 가드 49 파일 DRY 1차 마이그레이션 (LOW, 7 파일 헬퍼 위임) | `tests/unit/ast/_ast_helpers.py` 신규 (185L, 5 헬퍼) / `tests/unit/ast/test_cycle136_ast_helpers.py` 신규 (279L, 8 케이스) / 7 파일 헬퍼 위임 (사이클 78/89/101/102/110/127/129) | 사이클 130 권고 카드 #25 (LOW, 4순위) 1차 마이그레이션. 점진 마이그레이션 (사이클 136 = 7 파일 / 사이클 137+ = 10 파일/사이클). 사이클 89 G-AST1 의미 전환 영속 헬퍼 영역 보존 + 사이클 101 await + Call 자연 흡수 (ast.walk recursive). 백엔드 2,704 PASS × 2회 flakiness 0 / 사이클 136 격리 8 PASS / AST 디렉토리 전수 134 PASS / 매매 안전성 무영향 (테스트 영역 한정, production 영향 0). 사이클 137 인계: AST DRY 후속 마이그레이션 10 파일/사이클 |
| 2026-06-15 | 사이클 135 — WebSocket 구독 ACK grace period 신규 (MEDIUM~HIGH, +93L net) | `src/engine/stale_diagnostics.py` (+12L `SUBSCRIBE_GRACE_SECS = 180` 상수) / `src/engine/stale_manager.py` (+3L facade re-export, `__all__` 11 상수) / `src/engine/stale_watcher_core.py` (+30L grace 가드 `_is_within_grace`) / `src/realtime/websocket.py` (+30L `_subscribed_at` dict + 5 사이트 record/pop) / `src/realtime/websocket_pool.py` (+18L 합산 property) | Phase 1 진단 = 구독 ACK 직후 60s 이내 첫 시세 미입수 시 즉시 stale 판정 → 강제 재등록 KIS LMS chain 위험. 사용자 결정 Q1=A 의제 채택 + Q2=180s + Q3=A domain-expert 자문 + Q4=A HIGH 일관 grace. 자문 산출물 `_workspace/domain_consult/cycle135_websocket_grace_period.md` 5건 채택 (P95 안전 마진 정합). G-GRACE-7 직접 검증 (첫 시세 입수 후 60s 변경 0 = 사이클 29 005935 보호) + G-SAFETY-1/2 (STALE_FRESHNESS_SECS=60 변경 0, risk/order_engine import 0). 사이클 88 G-REJECT-3 4 dict → **5 dict 분리** (`_subscribed_at` 신규). 백엔드 2,696 PASS × 2회 flakiness 0 / 사이클 135 격리 14 PASS / 매매 안전성 무영향 (stale_watcher_core 영역 한정). 사이클 136 인계: 카드 #25 AST 가드 49 파일 DRY (LOW, -1,500L) |
| 2026-06-15 | 사이클 134 — scheduler 4 task loop 공통 헬퍼 추출 (MEDIUM, -103L) | `src/engine/task_loop_helper.py` 신규 (111L `run_periodic_task_loop` 팩토리) / `src/engine/scheduler.py` 3,501L → 3,398L (-103L, -2.9%) 4 task loop facade 전환 | 사이클 130 권고 카드 #21 (MEDIUM, 3순위) Green + 사이클 133 master metrics 통합 후 자연 발주. 사이클 67 facade + 사이클 79 G-AST2 task_attrs 4 위치 + 사이클 106 race 차단 + 사이클 88 graceful 헬퍼 흡수. 백엔드 2,682 PASS × 2회 flakiness 0 / 사이클 134 격리 14 PASS / 사이클 66 K-2 의미 전환 4건 (cycle106/122 가드 = 헬퍼 위임 + task_loop_helper.logger + summary prefix 흡수) / 매매 안전성 무영향 (lifecycle hook 영역 한정). 사이클 135 인계: WebSocket 구독 ACK grace period (Q3=A 180s 영구 영속, P95 안전 마진 정합) |
| 2026-06-15 | 사이클 133 — metrics 3 모듈 공통 헬퍼 + master metrics 일관성 통합 (LOW) | `src/engine/metrics_collector.py` 신규 (100L 공통 헬퍼 `make_metrics_collector` 팩토리) / `src/engine/stock_master_master_metrics.py` 신규 (39L master 일관성 facade) / 3 기존 facade 298L → 132L (-166L, -56% — 사이클 67 stale_manager.py 패턴 답습) / `src/engine/scheduler.py` (+4L master metrics 통합) | 사이클 130 권고 카드 #24 (LOW, 2순위) Green + 사이클 129 master_load_once metrics collector 부재 일관성 결함 해소. 백엔드 2,668 PASS × 3회 / 프론트 312 PASS / 사이클 133 격리 15 PASS / 사이클 66 K-2 의미 전환 1건 (사이클 89 G-AST1 `_has_function_def` 모듈-레벨 export 흡수) / 매매 안전성 무영향 (metrics 영역 한정, risk/order/realtime/auth 변경 0) |
| 2026-06-15 | 사이클 132 — strategy_funnel 결함 시정 (momentum funnel 영구 제외 + 휴장일 UI 안내) (MEDIUM) | `src/engine/strategies/momentum.py` (+13L docstring) / `src/routes/strategy_funnel.py` (+41L `_resolve_business_day` + 응답 확장) / `frontend/src/pages/StrategyFunnel.tsx` (+30L amber 배너 + 안내) / `frontend/src/api/strategy-funnel.ts` (+6L 타입) | 사용자 보고 "VB/LTV 2,3,4 단계 0 / donchian/BFB 전부 0 / VCP 베이스 이후 0". Supabase MCP READ-ONLY 진단 = VB/LTV/momentum hook 호출 0건 (사이클 39+41 명세 누락) + donchian/BFB/VCP 휴장일 영역만 0 (영업일 정상). 사용자 결정 Q1=C VB/LTV → 사이클 133 domain-expert 자문 + Q2=C momentum 영구 제외 + Q3=A 휴장일 UI + Q4=A TDD. 백엔드 2,653 PASS × 3회 / 프론트 312 PASS / 사이클 132 격리 13 PASS / 매매 안전성 무영향 (prepare 메모리 적재 + GET 응답 schema 한정) |
| 2026-06-15 | 사이클 131 — routes 4 POST fire-and-forget 헬퍼 추출 (LOW, -45L) | `src/routes/stock_master.py` 372L → 327L (헬퍼 `_make_background_runner` + `_TASK_REGISTRY` + `_dispatch_refresh` 추출) | 사이클 130 권고 카드 #22 1순위 Green. 4 POST 라우트 (universe/basics/daily/master) 동일 fire-and-forget 패턴 통합. 행위 보존 + 사이클 127 BackgroundTasks 영속 + 사이클 128 envelope 영속. 사이클 66 K-2 의미 전환 4건 (cycle110/120/127 가드 헬퍼 dispatch chain 흡수). 백엔드 2,645 PASS / 사이클 131 격리 13 PASS / 매매 안전성 무영향 (라우트 영역 한정, scanner/risk/order/realtime/auth 변경 0) |
| 2026-06-14 | 사이클 130 — refactor-review 권고 카드 6장 산출 (코드 변경 0 / 매매 안전성 무영향) | `_workspace/refactor/2026-06-14_review.md` 신규 (322L) | 사이클 67 (`stale_manager.py` 1,099L 분해 카드 #14 종결) 이후 62 사이클 누적 = CLAUDE.md "5 사이클 누적" 12배 초과 영구 차단 의무. 사용자 결정 Q1=A refactor-review 단독 + Q2=E refactor-expert 자율 범위 + Q3=A HIGH 카드만 domain-expert 평가 + Q4=A 권고만 + 사이클 131+ Green 별도. 권고 카드 6장: #21 scheduler 4 task loop 헬퍼 (MEDIUM, -193L) / #22 routes 4 POST fire-and-forget 헬퍼 (LOW, -115L) / **#23 scanner.py 분해 (HIGH, -2,581L, 사이클 67 패턴 답습)** / #24 stock_master metrics 3 모듈 공통 헬퍼 (LOW, -218L) / #25 AST 가드 49 파일 DRY (LOW, -1,500L 추정) / **#26 scheduler.py 추가 분해 (HIGH, -3,297L, 매매 hot path 인접)**. 합계 -7,904L 추정 (사이클 67 -1,003L 대비 7.9배). 사이클 131 = #22 단독 Green (refactor-expert 1순위 우선) |
| 2026-06-14 | 사이클 129 — KIS 공식 일일 마스터 파일 (kospi_code.mst / kosdaq_code.mst) 도입 + master_raw 별도 컬럼 + 16:30 KST 자동 task (HIGH) | `src/api/kis_master.py` 신규 (294L) / `supabase/migrations/034_stock_master_master_raw.sql` 신규 / `src/engine/scanner.py` (+289L 시총 환산 × 100 + 1단계 차단 7건 + master_load_once) / `src/engine/scheduler.py` (+86L 16:30 task) / `src/routes/stock_master.py` POST `/master/refresh` / `frontend/src/pages/StockMaster.tsx` 4번째 버튼 | 사용자 verbatim "종목마스터 만들 때 아래 소스코드 참고해줘" + KIS 공식 샘플 코드 제공. 사용자 결정 Q4=A 마스터 우선 + Q5=C 전수 보존 + Q6=C master_raw 별도 컬럼 + Q12=A × 100 단위 환산 (team-leader 자체 자문 영역 "× 10,000" 결함 자체 발견 + 사용자 verbatim "× 100" 정합 검증 후 시정). KOSPI 70 / KOSDAQ 64 field_specs 분기 + cp949 + ZIP + httpx SSL 옵션 C (verify=True 우선 + 폴백). 백엔드 2,632 PASS / 프론트 307 PASS / e2e 30 PASS × 3회 flakiness 0 / 사이클 129 격리 36 PASS / 매매 안전성 무영향 (scanner 매수 진입 전 영역 한정, risk/order/realtime/auth 변경 0) |
| 2026-06-13 | 사이클 128 — 종목목록 4 필터 신규 + 전체현황 4 카운트 silent cap 영구 시정 (HIGH) | `src/db/stock_master.py::get_stats()` 4 카운트 count="exact" + filter 분리 / `src/db/stock_master.py::list_paged_by_filter()` 신규 / `src/routes/stock_master.py` GET /list 4 query param + envelope 응답 / `frontend/src/pages/StockMaster.tsx` 상단 인라인 4 컨트롤 | 사용자 보고 "전체종목수를 제외하고는 페이징처리 중에 엉망" = `.range(0, 9999)` PostgREST 1000행 silent cap 영구 확정 (nxt 실측 400 → UI ~150 잠재 silent 결함). 4 카운트 모두 count="exact" + filter (사이클 126 패턴 답습) + JSONB jsonb operator path (`raw->'hts_avls'` numeric 비교, Supabase MCP 검증). 종목목록 = 시장 select + 시총/거래대금 억원 input + 종목명 검색 + 400ms 디바운스 + URL query 동기화. 백엔드 2,287 PASS / 프론트 302 PASS / 사이클 128 격리 26 PASS / xfail 의미 전환 3건 (사이클 124/126 패턴) / 매매 안전성 무영향 |
| 2026-06-13 | 사이클 127 — 3 작업 fire-and-forget BackgroundTasks + 5초 폴링 진행 가시화 (HIGH) | `src/engine/refresh_progress.py` 신규 / `src/routes/stock_master.py` (BackgroundTasks 전환 + GET /refresh-progress) / `frontend/src/components/RefreshProgressBanner.tsx` 신규 | 사이클 126 사용자 보고 "13분 후 KIS API 일시 결함 토스트" = axios timeout silent 결함 시정. 라우트 동기 응답 → BackgroundTasks (response 후 schedule) + 상단 배너 동적 5초/60초 폴링 + state 기반 409 가드. 백엔드 2,271 PASS / 프론트 295 PASS / 사이클 127 격리 33 PASS / xfail 의미 전환 9건 (사이클 66 K-2 패턴) / 매매 안전성 무영향 |
| 2026-06-13 | 사이클 126 — 종목마스터 UI/데이터 결함 4건 통합 시정 (1000 cap + 목록 4 컬럼 부족 + NXT/정지/관리 미입수 + 일봉 미적재) (MEDIUM) | `src/db/stock_master.py::get_stats()` count="exact" / `src/engine/scanner.py::_stock_master_basics_refresh_once` 신규 / `src/routes/stock_master.py` POST 2 신규 | get_stats PostgREST 1000행 한도 시정 + 리스트 4 컬럼 (시총/거래대금/현재가/전일대비) + KRX 폴백 하드코딩 False 시정 (KIS CTPF1002R 매스 보강 task 매일 16:10 KST) + 일봉 task 진단 강화. 백엔드 2,250 PASS / 프론트 289 PASS / 사이클 126 격리 16 PASS / 매매 안전성 무영향 (scanner 단계 한정) |
| 2026-06-12 | 사이클 124 — 종목마스터 UI 확장 + 신규 데이터 UI 동기화 영구 가드 (MEDIUM) | `src/db/stock_master.py` (+25L) / `src/db/stock_master_daily.py` (+15L) | 사용자 보고 ("정보가 너무 제한적" + "신규 수집 데이터 UI 노출 의무" + "지침 추가") 즉시 시정 (단순 시정 + LOW 위험 + UI + READ-ONLY 영역 ... |
| 2026-06-12 | 사이클 123 — donchian_swing `prepare()` `get_donchian_high` 헬퍼 전환 (LOW) | `src/engine/strategies/donchian_swing.py` (+14L L237 직전) / `tests/unit/engine/strategie... | 사용자 메시지 "다음 사이클" → 사이클 122 인계 HIGH 카드 1차 처리. team-leader Phase 1 진단 (Q1~Q4 4 의제 정리) + 사용자 결정 전수 채... |
| 2026-06-12 | 사이클 122 — KIS 일봉 도입 + `stock_master_daily` 정규화 | `supabase/migrations/033_stock_master_daily.sql` 신규 / `src/db/stock_master_daily.py` 신규... | 사용자 보고 "KIS로 일봉 가져오고 신규 테이블로 저장하자" 의도 달성. team-leader Phase 1 진단 결정적 발견 = `fetch_daily_candles` (... |
| 2026-06-12 | 사이클 121 — Plan Phase B donchian `stock_master` 전환 (MEDIUM) | `src/engine/strategies/donchian_swing.py` (+82/-39 _scan_universe) / `tests/unit/engine... | 사이클 100 인계 Plan Phase B (사이클 119 발주 시점, team-leader 자동 진행). MEDIUM 위험 = 멀티데이 보유 영역. Q2=D 임시 완화 = ... |
| 2026-06-12 | 사이클 120 — TTL 우회 옵션 추가 (HIGH) | `src/engine/scanner.py` (force 인자 3 함수) / `src/routes/stock_master.py` (force=True 디폴트) | 사이클 119 효과 검증 시점 TTL 영역 결함 발견 (skipped_ttl=2,697 = 사이클 116/118/119 매핑 미적용). 사용자 즉시 결정 = force 인자 ... |
| 2026-06-12 | 사이클 119 — KRX → KIS 정합 키 전수 매핑 확장 (HIGH) | `src/engine/scanner.py` (+30L 4 매핑) / `tests/unit/engine/scanner/test_cycle119_krx_kis_... | 사용자 보고 정밀 진단 + KIS MCP 정본 검증 + 4 Explore agent 병렬. 사용자 가설 "TR 코드 못 찾음" 반박 (TR 코드 정합 영구 확정). 진짜 원인... |
| 2026-06-12 | 사이클 118 — KRX ACC_TRDVAL → KIS `acml_tr_pbmn` 거래대금 매핑 (HIGH) | `src/engine/scanner.py` (+ACC_TRDVAL 매핑) / 7 PASS | 사이클 117 운영 실측에서 발견된 거래대금 매핑 누락. 사이클 108 list_by_filter 영역 정합 의무. 매매 안전성 무영향. 사이클 119+ 후속: Plan Ph... |
| 2026-06-12 | 사이클 117 — hotfix — KRX basDd 전일 영업일 영역 + 빈 응답 시 KIS 폴백 + source 키 (HIGH) | `src/engine/scanner.py` (+~30L basDd 전일 + 7일 재시도) / `src/routes/stock_master.py` (+~7L ... | 사용자 보고 즉시 시정 (사이클 115 도입 후 영업일 영역 결함 발견). 사용자 결정 C 통합 = basDd 전일 + 빈 응답 재시도 + KIS 폴백 trigger + so... |
| 2026-06-12 | 사이클 116 — KRX MKTCAP (원) → KIS `hts_avls` (백만원) 단위 환산 (HIGH) | `src/engine/scanner.py` (+11L MKTCAP 환산) / 6 PASS | 사이클 115 KRX 1차 분기 활성 시 단위 정합 의무 (1,000,000배 왜곡 차단). 사이클 81 G-AST1 의도 정확 해석 = KIS CTPF 호출 영역 키 보호 ... |
| 2026-06-12 | 사이클 115 — KRX OPEN API endpoint 실제 통합 | `src/api/krx.py` (+98L 4 endpoint) / `src/engine/scanner.py` (+~190L Q3=C 폴백) | Phase 1 진단 결정적 발견 = 사이클 112 인프라 추상 결함 3건 시정 (외부 정본 2건 독립 일치 검증). 사용자 키 활성화 후 401/400 silent 결함 차단... |
| 2026-06-12 | 사이클 114 — CI fail 무시 차단 패턴 영구 가드 | `.github/workflows/deploy.yml` (workflow_run + conclusion success 가드) / `.github/workfl... | 사이클 108~112 5 사이클 연속 CI red 무시 push 위험 패턴 = 단일 근본 원인 (deploy.yml on push 직접 trigger). workflow_ru... |
| 2026-06-12 | 사이클 113 — hotfix — CI fail 시정 | `tests/unit/ast/test_cycle93_ast_chain_required.py` xfail / `frontend/src/api/realtime-... | 사이클 108부터 누적 4건 일괄 시정. 사이클 110 시정 의미 전환 = 사이클 93 AST 의도 보존 + xfail 자동 가시화 (사이클 66 K-2 패턴). 사이클 10... |
| 2026-06-12 | 사이클 112 — openapi.krx.co.kr 정식 OPEN API 인프라 사전 구성 | `src/models/krx_open_api.py` 신규 / `src/db/system_config.py` (+120L) | 사용자 요구 (사이클 110 인계 KRX 정보데이터시스템 OPEN API 도입 영역). Phase 1 진단 결정적 발견 (인증 / URL / 호출 / Rate Limit / ... |
| 2026-06-11 | 사이클 110 — routes/stock_master.py silent 결함 (LOW) | `src/routes/stock_master.py` (L52~L83, 28L 시정 — `_full_universe_load_once` 단일 호출 + 응답 7... | 사용자 보고 (운영자 "지금 새로고침" 100% 실패) 즉시 시정 (근본 원인 = 사이클 101 시정 동행 누락 silent 결함). team-leader Phase 1 진단... |
| 2026-04-22 | 초기 구성 (team-leader / backend-dev / frontend-dev / tdd-engineer / tester) | 전체 | TDD-First Trading Team 출범 |
| 2026-05-21 | `domain-expert` (데이/스윙 트레이더 자문) + `refactor-expert` (주기적 리팩토링) 합류, KIS MCP 접근 명시 (backend-dev / tdd-engineer / tester /  | 에이전트 7명 / 스킬 9개 | 매매 의사결정 깊이 보강 + 코드 품질 드리프트 흡수 + KIS 스펙 정본 통일 |
| 2026-05-21 | `kis-mcp-query` 스킬에 KIS 공식 저장소 경로 + 설치 가이드 + 공식 프롬프트 도구 (`kis_easy_code`/`kis_detailed_code`) 활용 안내 추가 | skills/kis-mcp-query | 공식 저장소 (koreainvestment/open-trading-api) 가 정본임을 명시, 비공식 fork 사용 차단 |
| 2026-05-21 | 사이클 28 — ~37 (운영 진단 + 결함 | `src/engine/scheduler.py` 외 다수 + 신규 라우트 `/api/strategy-funnel` + migration 029/030 | 09:13 VB 미매수 사고 진단을 시작점으로 stale 추적 → 결함 가시화 → 시정 + funnel DB 추적 → UI 강화. 백엔드 1625 PASS / 프론트 160 ... |
| 2026-05-22 | 사이클 38 — ~43 (정책 명문화 + funnel 진단 + ping-pong 가시성 + 라벨 통일 6 사이클) — 상세는 `docs/HARNESS_CHANGELOG.md... | `src/engine/strategies/long_tail_volatility.py` / `strategy_base.py` | 백엔드 1671 PASS / 프론트 160 PASS / 매매 안전성 무영향. 사이클 33 BFB+VCP fix 효과 확인 (BFB 30→24, VCP 113→113), 사이클... |
| 2026-06-11 | 사이클 109 — `market-cap` 화이트리스트 누락 silent 결함 (HIGH) | `src/api/base.py` (+4L `_QUOTE_ALLOWED_PATHS` 1 path 추가) / `tests/unit/api/test_cycle10... | 사용자 보고 (stock_master 192 ticker 잔존 = 사이클 106 시정 후 미반영) 즉시 시정 (근본 원인 = 사이클 101 도입 시점 silent 결함). t... |
| 2026-06-11 | 사이클 108 — **Plan Phase A 완료 (LOW) | `src/api/condition.py` (+1L `hts_avls` 5번째 키 추가) / `src/db/stock_master.py` (+~60L `lis... | team-leader Phase 1 진단 (사이클 104 인계 Q5=B LOW 위험 자문 생략 영속 + 사이클 107 raw 보강 의존성 해소 완료 영구 영속 확인) + 사용... |
| 2026-06-11 | 사이클 107 — **stock_master raw 보강 (HIGH) | `src/api/condition.py` (+44L `inquire_stock_basics` CTPF1002R + FHKST01010100 merge 영역 ... | team-leader Phase 1 진단 결정적 발견 (CTPF1002R 3 키 부재 + FHKST01010100 3 키 존재 KIS MCP 정본 영구 영속 확정) + 사용자... |
| 2026-06-11 | 사이클 106 — **stock_master 갱신 영역 영구 (LOW) | `src/engine/scheduler.py` (+21/-14L 순증 +7L `_full_universe_load_task_loop` start() 직후 즉... | 사용자 보고 (191 ticker stock_master 영구 영속 결함 + UI 사이클 94 안내 배너 무효 영역) 즉시 시정 (4 영역 통합). 41 사이클 연속 옵션 A... |
| 2026-06-11 | 사이클 104 — **Playwright E2E spec 신규 | `e2e/realtime-health.spec.ts` 신규 (8 케이스, 380L) / `e2e/strategies.spec.ts` 신규 (9 케이스, 188L) | E2E spec 신규 (사이클 103 신규 페이지 검증) + silent 결함 2 영구 시정. 40 사이클 연속 옵션 A 패턴 영속. tdd-engineer Red + fro... |
| 2026-06-11 | 사이클 103 — **4 영역 통합 (LOW) | `frontend/src/types/realtime-health.ts` 신규 (33L) / `frontend/src/api/realtime-health.ts... | 사이클 102.5 회고 결정적 사실 (코미코 STOP_LOSS 운영 가시화 부족 = 단일 근본 원인 운영 영역 -2.4% apply) 즉시 시정 (4 영역 통합). 39 사이... |
| 2026-06-11 | 사이클 102 — **시세 구독 영역 전면 재검토 (HIGH) | `src/realtime/websocket.py` (+7L L162~L165 `_last_ws_message_at` 인스턴스 변수 + L607~L609 `_... | 사용자 신규 요구 (재구독 영역 전면 재검토) + refactor-expert + domain-expert 병렬 자문 일치 = 사이클 88 G-REJECT 영구 영속 (재구독... |
| 2026-06-11 | 사이클 100 — **UI prefix 정정 (LOW) | `src/db/stock_master.py` (+13/-7L count_eager_refresh_today 3 prefix OR) / `tests/unit/... | 사이클 99 D+1 운영 측정 (2026-06-11 목 08:01 KST) 시점 사용자 첨부 UI = "오늘 자동 갱신 횟수 0" 결함 영역 즉시 시정 + 사용자 요구 4 영... |
| 2026-06-10 | 사이클 99 — **사이클 91 페이징 영역 영구 폐기 (LOW) | `src/engine/scanner.py` (-53L 순감, 페이징 영역 전수 폐기 + 단일 호출 + docstring 명문화) / `tests/unit/e... | 사용자 보고 (60 ticker + 3952ms 영속 페이징 시도) = KIS API 본질 한계 영구 확정 (volume_rank + fluctuation 모두 페이징 미지원... |
| 2026-06-10 | 사이클 98 — **KIS fluctuation API `FID_RANK_SORT_CLS_CODE` 1줄 silent 결함 (LOW) | `src/engine/scanner.py` (+4L 1줄 시정 + docstring chk 인용) / `tests/unit/engine/scanner/tes... | 사용자 보고 (0 ticker + 262ms 영역) = 사이클 97 즉시 silent 결함. team-leader Phase 1 진단 (Supabase MCP 운영 실증 OP... |
| 2026-06-10 | 사이클 97 — **KIS volume_rank API 영구 폐기 (LOW) | `src/engine/scanner.py` (+113/-106 = 순 +7L, KIS fluctuation 영역 신규 + KIS volume_rank 영역 ... | 사용자 보고 (60 ticker 영속 + 3438ms 소요 영역) = 사이클 91 페이징 영역 코드 정합 영속 + KIS API 영역 자체 한도 영구 확정. 단일 근본 원인 ... |
| 2026-06-10 | 사이클 96 — **KIS API "0000" 응답 단일 페이지 30 한도 (LOW) | `src/engine/scanner.py` (-5L 순감 = +55/-60 영역 복원 + 페이징 결합 + post-split 폐기) / `tests/unit... | 사용자 보고 (29 ticker 영속) 즉시 시정 (사이클 94 도입 KIS API "0000" 단일 페이지 한도 + 페이징 미지원 silent 결함 단일 근본 원인 확정).... |
| 2026-06-10 | 사이클 95 — **chicken-and-egg lock-in 영구 (LOW) | `src/engine/scanner.py` (+9L unknown 영역 + emit 확장) / `frontend/src/pages/StockMaster.ts... | 사용자 보고 (78 ticker 영속) 즉시 시정 (사이클 94 chicken-and-egg lock-in 단일 근본 원인 확정). 32 사이클 연속 옵션 A 패턴 영속. t... |
| 2026-06-10 | 사이클 94 — **FID_INPUT_ISCD 60 ticker silent 결함 영구 (LOW) | `src/engine/scanner.py` (L1368~1559 `_MARKET_INPUT_ISCD` 단일화 + `_classify_market` 헬퍼 + ... | 사용자 보고 (60 ticker 영속 결함) 즉시 시정 (사이클 91 페이징 시정 후에도 영속 = 별개 단일 근본 원인 KIS 정본 `FID_INPUT_ISCD = "0000... |
| 2026-06-10 | 사이클 93 — **호출 chain broken silent 결함 영구 (LOW) | `src/engine/scheduler.py` (+16L L2591~L2660 `_universe_eager_refresh_loop` 2 분기 chain +... | 사용자 보고 stock_master 60 ticker 영속 결함 + 사이클 87 Phase 2 Q3/Q9 0건 silent 결함 = 단일 근본 원인 (가설 E 호출 chain... |
| 2026-06-10 | 사이클 92 — **07:50 KIS API 강제 중단 충돌 영구 (LOW) | `src/engine/scheduler.py` (+2L L51~L53 시간 상수 시정) / `src/realtime/websocket.py` (+85L im... | 사용자 운영 보고 (07:45 우리 기동 vs 07:50 KIS API 강제 접속 중단 충돌) 즉시 시정 (사용자 결정 Q28~Q33 + Q32 domain-expert P1... |
| 2026-06-09 | 사이클 91 — **KIS volume_rank 페이징 누적 누락 silent 결함 영구 (LOW) | `src/api/base.py` (+36L tr_cont 시그너처 + 응답 헤더 주입 + AsyncMock graceful) / `src/engine/sca... | 사이클 89 silent 결함 (KIS volume_rank 페이징 누적 누락) + 사용자 운영 실측 보고 즉시 시정 (사용자 결정 A 즉시 발주). 28 사이클 연속 옵션 ... |
| 2026-06-09 | 사이클 90 — **stock_master 500+ 수동 trigger API (POST /api/stock-master/refresh-universe) + UI "지금 새... (LOW) | `src/routes/stock_master.py` (+37L POST /refresh-universe + asyncio.Lock + 409 Conflict... | 사이클 89 후속 (장 종료 후 즉시 발화 영역 보강) — 사용자 보고 "장 종료 후라 시작이 안돼" 즉시 시정. 27 사이클 연속 옵션 A 패턴 영속. team-leader... |
| 2026-06-09 | 사이클 89 — **stock_master 500+ universe 확장 | `src/engine/stock_master_metrics.py` 신규 (84L) / `src/engine/scanner.py` (+신규 함수 5 + 상수 4) | 사용자 요구 (stock_master 500+ 확장 + 각 전략 필터링) + UI 결함 2 영역 (종목명 미표시 + 영문 필드명 + 사이클 언급 + 영문 용어) 통합 시정. ... |
| 2026-06-09 | 사이클 88 — **외부 LLM 의견서 영구 기록 + 영구 차단 AST 가드 3** (코드 변경 0, **25 사이클 연속 옵션 A 패턴 (MEDIUM) | `_workspace/external_llm_reviews/2026-06-09_realtime_review.md` 신규 (디렉토리 + 통합 영구 기록 7 영... | 타 LLM 외부 의견서 (사용자 첨부, 시세 수신 오류 + 구조 단순화 관점) 처리 방침 결정 사이클 — Plan 영속 (A 점진 흡수). 25 사이클 연속 옵션 A 패턴 영... |
| 2026-06-09 | 사이클 85 — **stock_master UI 메뉴 구축 프론트 단독 단계 (LOW) | `frontend/src/types/stock-master.ts` 신규 (45L) / `frontend/src/api/stock-master.ts` 신규 (... | 사이클 83 후속 3 단계 분할 2/3 (프론트 단독) — stock_master UI 메뉴 구축 (사용자 요구 영속). team-leader Phase 1 진단 (5 의제 ... |
| 2026-06-09 | 사이클 84 — **stock_master UI 메뉴 구축 백엔드 단독 단계 | `supabase/migrations/032_stock_master_history.sql` 신규 / `src/db/stock_master.py` (+97L) | 사이클 83 후속 3 단계 분할 1/3 (백엔드 단독) — stock_master UI 메뉴 구축 (사용자 요구). team-leader Phase 1 진단 (5 의제 Q5~... |
| 2026-06-09 | 사이클 83 — **#82-A 옵션 1 (MEDIUM) `_scan_loop` 후보 풀 ticker `stock_master` eager refresh 영역 확장 (MEDIUM) | `src/engine/scanner.py` / `src/engine/scheduler.py` | 사이클 82 진단 인계 후속 #82-A (MEDIUM 신규) 영구 시정 — 사이클 81 시정 실효성이 stock_master 적재 영역에 결정적 의존 → eager refre... |
| 2026-06-08 | 사이클 81 — **사이클 64 silent 결함 (HIGH) | `src/engine/scanner.py` (-7L 순감, L166 `prdy_clpr` → `bfdy_clpr` 가격필터 키 시정 + L188~198 로그... | 사이클 64 시점 silent 결함 (Q2 자문 옵션 A KIS API 응답 키 명명 가정 오류) 영구 시정 — 단일 근본 원인 (`prdy_clpr` ≠ `bfdy_clpr... |
| 2026-06-08 | 사이클 80 — hotfix 4 단계 통합 — **사이클 79 e2e fail → 사이클 65 hotfix #2 가드 잘못된 FIFO 가정 영구 (MEDIUM) | `frontend/src/pages/Settings.tsx` (+2L, L43 + L692 useQuery retry:1 명시) / `frontend/src... | 사이클 79 1차 + 재실행 모두 fail (flaky 아닌 진짜 결함 확정) → 옵션 C 정밀 조사 (Playwright trace console error + resour... |
| 2026-06-08 | 사이클 79 — 카드 (LOW) | `src/engine/scheduler.py` (+2L, L742 finally + L866 stop() 양쪽 task_attrs 튜플에 `_api_reco... | 사이클 78 부차 발견 (`stop()` task cancel 목록 `_api_recovered_collector_task` 누락) 영구 시정. team-leader 진단 생... |
| 2026-06-08 | 사이클 78 — **사이클 74 도입 누락 silent 결함 (HIGH) | `src/engine/scheduler.py` (+26L / -2L, `_api_recovered_collector_loop` 본체 swing/stale f... | 사이클 78 C 진단 (Supabase READ-ONLY) 으로 카드 #19 거짓 알람 종결 + 사이클 74 도입 누락 silent 결함 (flush 호출 사이트 0건 = 메... |
| 2026-06-08 | 사이클 77 — hotfix 2단 통합 — **e2e flaky 영구 차단 | `e2e/fixtures/api-mocks.ts` (hotfix #1 +26L + hotfix #2 +7/-2 = 합 +31L / -2L, 4 라우트 추가 ... | 사이클 73 1차 + 사이클 74 1차 + 사이클 76 1차/재실행 = flaky → 진짜 결함 확정 chain. 사이클 77 hotfix 2단 진화 = ECONNREFUSE... |
| 2026-06-08 | 사이클 76 — 카드 #23 (MEDIUM) **api retry 5.80x dup 시정 (MEDIUM) | `src/api/base.py` (+150L, 신규 헬퍼 7 + state 3 + 모듈 상수 2 + `_request` 호출자 정정 `_warn_http_s... | 사이클 74 발견 신규 결함 시정 (api retry 5.80x dup) — 사이클 18 60s WARNING dedupe + 사이클 74 5분 recovered collec... |
| 2026-06-08 | 사이클 75 — 카드 #19' (HIGH) **e2e api-mocks flaky 영구 차단 (HIGH) | `e2e/fixtures/api-mocks.ts` (+53L, 7 endpoint group 추가 — cash-usage-ratio + 4 integrati... | 사이클 73 1차 + 사이클 74 1차 e2e fail (flaky 2회 누적 확인) — 진짜 결함 영역 확정 후 사이클 65 hotfix #2/#3 패턴 답습. team-l... |
| 2026-06-08 | 사이클 74 — **WebSocket 로그 sampling/aggregation/rate cap (옵션 E-1) 도입 (HIGH) | `src/realtime/websocket.py` +95L (collector + record/flush + metrics_loop + lifecycle +... | 사이클 71/73 운영 실증 잔존 dup 영역 (합법적 반복) 흡수 = 사이클 42 `[ws_heartbeat]` 5분 통계 패턴 답습. team-leader Phase 1 ... |
| 2026-06-08 | 사이클 73 — 카드 #19 (HIGH) **WebSocket dup 핵심 영역 (HIGH) | `src/realtime/websocket.py` (-19L 합, R-1 `_verify_subscriptions_after_reconnect` write_... | 사이클 72 hotfix F-2 (WebSocket dup 핵심 영역) 즉시 인계 카드 #19 (HIGH) 완전 종결 — R-1/R-2/S-1 3 사이트 시정 + AST G-... |
| 2026-06-08 | 사이클 72 — hotfix — system_logs **이중 INSERT 시정 (HIGH) | `src/main.py` (+30 lines, `_DbLogHandler` 500ms TTL dedupe 캐시 신규) / `src/realtime/webso... | 사이클 71 운영 hot path 실증 발견 silent 결함 (이중 INSERT 2.89x dup) 즉시 시정 — 사용자 결정 (매매 미발생 09:25 영역 안전). tea... |
| 2026-06-08 | 사이클 69 — 카드 #18 (LOW) **영구 폐기 (LOW) | `src/db/CLAUDE.md` (+19 lines, §TIMESTAMPTZ 사실 명문화 신규) / `docs/HARNESS_CHANGELOG.md` 사이... | 사이클 68 인계 카드 #18 (UTC 잔존 데이터 백필) = 사실 점검 결과 **불필요** 확정. team-leader Supabase MCP 13 테이블 전수 점검 후 r... |
| 2026-06-07 | 사이클 68 — 카드 #17 (LOW) 기타 INSERT 모듈 UTC → KST 일관성 (LOW) | `src/db/_kst.py` 신규 35L / `src/db/stock_master.py` (G-2 upsert + G-11 is_stale, +12 lines) | 사이클 65 hotfix H2/H2-bis 인계 카드 #17 (LOW) 완전 종결 — system_logs 외 기타 INSERT/UPSERT 모듈 timestamp KST 일... |
| 2026-06-06 | 사이클 67 — refactor #2 후속 카드 #14 (MEDIUM) `stale_manager.py` 1,099L → **4 sub-module + facade 96L 분해 (MEDIUM) | `src/engine/stale_manager.py` 1,099 → 96L (facade) / `src/engine/stale_diagnostics.py` ... | refactor #2 후속 카드 #14 (MEDIUM) **완전 종결** — `stale_manager.py` 1,099L 모듈 비대화 해소 + 책임 분리 (진단/복구/유니버... |
| 2026-06-06 | 사이클 66 — `_resubscribe_stale_priority` cap=10 결함 (HIGH) | `src/engine/stale_manager.py` ~22L 교체 (L1023-L1057) + docstring Q6-4 의미 전환 명시 / `tests/... | 사이클 63 발견 결함 (K-2 PASS = 결함 confirm) 영속 시정 — 사이클 29 005935 사고 패턴 영구 차단. domain-expert 자문 옵션 A 전부 ... |
| 2026-06-06 | 사이클 65 — hotfix — e2e settings.spec.ts FAIL 시정 | `frontend/src/components/PriceFilterCard.tsx` (+1) / `frontend/src/components/TradeAmou... | 사이클 65 e2e 결함 = TradeAmountFilterCard 추가로 카드 수 임계 초과 + React Query 기본 retry 3회 누적 → 5초 timeout 초과... |
| 2026-06-06 | 사이클 65 — 거래대금 동행 필터 — scanner 단계 작전주 차단 보강 (HIGH) | `src/db/system_config.py` (TradeAmountFilter + 2 함수) / `src/engine/scanner.py` +234L (t... | Q7-5 (사이클 64 자문) HIGH 즉시 발주 확정 인계 — 사이클 62 갭상승 회피 효과 폐기 위험 보강. 사이클 64 패턴 직답습 (HIGH 3 = C 2 + G 1)... |
| 2026-06-06 | 사이클 64 — 가격 필터 scanner 이전 + 단순화 (HIGH) | `src/db/system_config.py` (mode 폐기, 2 키) / `src/engine/risk.py` -178L (가격 필터 전체 폐기) | 사용자 의도 재정의: 사이클 62 `risk.on_tick` (매수 신호 판단용) → scanner 단계 (WS 구독 *전* 종목 풀 차단) — 자원 절약 + 후보 풀 자체 ... |
| 2026-06-06 | 사이클 63 — Phase 2-A3 — refactor #2 stale_manager 추출 3단계 (HIGH) | `src/engine/stale_manager.py` +345L (731→1,076) / `src/engine/scheduler.py` -308L (3,31... | refactor #2 stale_manager 3 단계 분할 **완료** (A1+A2+A3 = 11 함수 + 10 상수 누적 ~937L 이주). 사이클 51 boot_mana... |
| 2026-06-05 | 사이클 62 — 가격 필터 — 매수 진용 가격대 차단 신규 기능 | `src/db/system_config.py` (PriceFilter Pydantic + 3 키 헬퍼) / `src/engine/risk.py` (on_ti... | domain-expert 자문 Q1~Q6 + Q7~Q11 전부 적용 (옵션 A) — Q2 fallback / Q4 3 모드 (HARD 단일 반박, 시장 신뢰 형성) / Q5 ... |
| 2026-06-05 | 사이클 61 — Phase 2-A2 — refactor #2 stale_manager 추출 2단계 (MEDIUM) | `src/engine/stale_manager.py` +373L (358→731) / `src/engine/scheduler.py` −290L (3,605→... | A1 완료 후 도메인 자문 옵션 B 3 단계 분할의 2 단계 — 사이클 60 패턴 직답습 (logger 명시 binding / re-export / 12 파일 분리). tes... |
| 2026-06-04 | 사이클 60 — Phase 2-A1 — refactor #2 stale_manager 추출 1단계 (LOW) | `src/engine/stale_manager.py` 신규 / `src/engine/scheduler.py` 5 상수 re-export + 5 wrapper | refactor-review 2026-06-04 카드 #2 (HIGH) 의 A1 단독 진행 — 사이클 51 boot_manager 답습 + 도메인 자문 (영구 hot path... |
| 2026-06-04 | 사이클 60 — hotfix — CI backend-test 6시간 hang 영구 차단 | `tests/unit/engine/test_b1_market_closed_zombie_block.py` / `tests/unit/engine/test_ord... | 사이클 58 hotfix 와 유사 패턴 (production code 변경 → mock 갱신 누락). 영구 timeout 가드로 동일 결함 재발 시 1분 내 FAIL 보장. ... |
| 2026-05-31 | 사이클 49 — VCP Pullback "마지막 폭 0.0%" 결함 | `src/engine/strategies/vcp_breakout.py` (DEFAULT_PARAMS + `_check_pullback_sequence` 재설... | 백엔드 1748 PASS (1742→+6) / 다른 5 전략 + scan/매매 흐름 무영향 — 매수 진입 임계만 시정. 사이클 41 funnel 진단의 종결 (진단만 했고 시... |

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
- **NXT 매도 거부 좀비 차단** — `is_market_closed_rejection` (APBK0918 + 장운영시간 외) 이면 `execute_sell` 이 positions(메모리/DB) 보존 + 재시도 중단. `is_insufficient_quantity` / `is_insufficient_cash` 와 분리. `SellRejectionTracker.is_blocked()` 진입 게이트는 **2단계 TTL** — KRX 메인(09:00~15:30) 거부 = 5분 TTL (일시 장애 가정), NXT 시간대(08:00~09:00 / 15:30~20:00) 거부 = 다음 KST 09:00 TTL. `market_order_disallowed` 거부 = 30초 TTL (동일 tick 폭주 차단). NXT 폴백 실패 시 `_pending_next_day_clear` 익일 청산 자동 전환. `_reset_daily_state` 동행 clear (`_sell_rejection.reset_daily()` 4 필드 일괄 위임, `OrderEngine.reset_daily_state()` 캡슐화 보존). 호환 layer property `_market_closed_blocked` / `_market_closed_blocked_logged_today` 는 tracker 내부 dict/set 직접 노출 (is 동일성 보장)
- **매수/매도 시장가 거부 → 지정가 5호가 폴백 1회** — `is_market_order_disallowed` (msg1 키워드 `시장가매매불가` / `시장가호가불가` / `최유리/최우선지정가 주문만` / `지정가 및 최유리` — APBK1943/APBK3013) 매칭 시 `step_up(buy)/step_down(sell)` 으로 `LIMIT` 재시도. 매핑 동기 + race 가드 동일 규약
- **KIS 거부 응답 영구 저장** — `_request` 가 `rt_cd != "0"` 시 `system_logs` prefix `[kis_rejection]` + path/tr_id/msg_cd/msg1 + body 주요 키 (민감 키 마스킹) fire-and-forget
- **WebSocket 시세 보유·익일청산 우선 보장** — `MAX_SUBSCRIPTIONS=41` KIS 공식 한도. HIGH (보유/익일청산) `bypass_limit=True` 절대 보장. 후순위 drop 시 `[priority_drop]` INFO + WARNING `system_logs`. HIGH 단독 41 초과 ERROR
- **WebSocket 다중 안전망** — F1 (재연결 1회) + `_scan_loop` (5분) + K stale watcher (120s, 1~5회 즉시 강제 재등록 + 6회 초과 시 5분 cooldown 기반 시간 기반 force_retry + 시간당 12회 cap) + `_resubscribe_stale_priority` (5분 우선) 4중. K stale watcher 양쪽 분기에 우선순위 분리 (positions/`_pending_next_day_clear` HIGH+bypass=True, 그 외 후보 LOW+bypass=False — 메인 편중 차단). `_subscriptions` ACK 정합성 가드 (orphan ACK race 차단)
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
| `daily_log_reports` | 20:10 일일 로그 분석 (target_date UNIQUE, metrics 에 api_metrics/strategy_funnel/by_ticker_pnl/by_hour_pnl/next_day_clear 포함). 토큰/지연/비용 5 컬럼 — input_tokens/output_tokens/total_tokens/latency_ms/cost_estimate_usd (migration 031, 모두 NULL 허용) |
| `stock_master` | KIS CTPF1002R 캐시 (ticker PK, 24h TTL) + **사이클 129 `master_raw` JSONB + `master_raw_updated_at TIMESTAMPTZ` 신규** (KIS 공식 일일 마스터 파일 영역 — 시총/거래정지/관리종목/지수편입/재무 ~30 키, raw 영역 분리 보호). NXT 거래가능 사전 판별 |
| `stock_master_daily` | KIS FHKST03010100 일봉 정규화 (migration 033). PK `(ticker, bas_dd)` + OHLCV + change_rate + raw JSONB. 매일 16:00 KST 적재 (백필 시 T-100일, 이후 D-1 영업일 증분). donchian (20일 신고가) / VCP (베이스+Pullback) / VB (ATR) 전략 활용 |
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
- 자동 배포: `git push origin main` → GitHub Actions 가 EC2 SSH → `git pull` + 재빌드 (`.github/workflows/deploy.yml`). push 시각 → pool_start 지연 1~5분
- GitHub Secrets: `EC2_HOST`, `EC2_USERNAME`, `EC2_SSH_KEY`
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
