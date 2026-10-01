# CLAUDE.md — 프로젝트 루트

> 이력: [`docs/history/CLAUDE.history.md`](docs/history/CLAUDE.history.md)

KIS OpenAPI 기반 주식 자동매매시스템. FastAPI(백엔드) + React(프론트엔드) + AWS RDS PostgreSQL(DB). 다중 전략 아키텍처.

---

## 🔴 최우선 과제 — 먼저 읽을 것

**[`_workspace/00_URGENT_WORKLIST.md`](_workspace/00_URGENT_WORKLIST.md)** 가 현재 최우선 작업 지시서다.
다른 작업을 시작하기 전에 이 문서를 먼저 읽는다.

---

> 디렉토리별 상세는 각 하위 `CLAUDE.md` 가 진실의 원천:
> `src/CLAUDE.md` · `src/engine/CLAUDE.md` · `src/engine/strategies/CLAUDE.md` · `src/api/CLAUDE.md` · `src/realtime/CLAUDE.md` · `src/db/CLAUDE.md` · `src/routes/CLAUDE.md` · `frontend/CLAUDE.md`
>
> 사이클별 변경 이력 (verbatim): [`docs/HARNESS_CHANGELOG.md`](docs/HARNESS_CHANGELOG.md)
> 시스템 흐름 도식: [`docs/architecture.md`](docs/architecture.md)

## 하네스: TDD-First Trading Team

**목표:** 모든 코드 변경을 Red→Green→Refactor 사이클로 강제하고, 변경 시 영향받는 테스트만 실행할 수 있는 정적 인덱스를 유지한다. *매매 의사결정의 깊이* 는 도메인 전문가의 사전 자문으로 보완하고, *코드 품질 드리프트* 는 리팩토링 전문가의 주기적 검토로 흡수한다.

### 문서 규약 — 정본은 현재 상태만, 이력은 history 파일

- 정본(`CLAUDE.md` 전부 · `README.md` · `docs/architecture.md` · `docs/backtest-monitoring.md` · `docs/macro-lite.md` · `_workspace/00_leader_trading_rules.md`)에는 **지금 동작하는 규칙만** 현재형으로 적는다. 전에는 어땠는지, 어느 사이클이 무엇을 바꿨는지, 취소선, 신·구 병기, 시점 꼬리표는 쓰지 않는다.
- 바뀐 경위·실측 수치·결정 근거가 필요하면 **`docs/history/<정본 이름>.history.md`** 에 append 하고 정본은 새 값으로 **덮어쓴다**. history 는 고치지 않는다(append-only · 규약 = [`docs/history/README.md`](docs/history/README.md)).
- 정본에 남기는 것 = 값의 출처 사이클 번호(`K=2.0(cycle242)`) · 금기와 그 이유 **한 문장**(`X 금지 — 2026-08-08 KRX OpenAPI 3,577→60 사고`). 이유가 한 문단을 넘으면 history 링크로 줄인다.
- 사이클별 보고 원문은 [`docs/HARNESS_CHANGELOG.md`](docs/HARNESS_CHANGELOG.md) 하나에만 둔다 — **이력의 유일한 정본**이다. 정본 안에 이력 표를 두지 않는다.
- 같은 사실을 두 문서에 적지 않는다. 두 곳이 필요하면 한 곳은 링크다.
- `/sync-docs` 의 **덧칠 패턴 검사**가 0 이어야 커밋한다(패턴 표 = [`.claude/commands/sync-docs.md`](.claude/commands/sync-docs.md)).

### 기본 진입점 — `team-leader` 우선

사용자의 모든 요청은 1차로 `Agent({subagent_type: "team-leader"})` 로 라우팅한다. team-leader 가 트레이더 관점에서 해석 후 하위 에이전트에 분배한다.

- 코드 변경 → `auto-trading-orchestrator` 스킬 (TDD 사이클: `tdd-engineer` Red → `backend-dev`/`frontend-dev` Green → `tester` 검증)
- 매매 의사결정 자문 (신규 전략·파라미터·보드 행태·시장 레짐·KIS 거부 해석) → `domain-consult` 스킬 (`domain-expert` 에이전트) — Phase 2.5 명세 분해 *전* 또는 사이클 중 행위 영향 평가 시
- 주기적 리팩토링 검토 (사이클 5회 누적 또는 명시 요청) → `refactor-review` 스킬 (`refactor-expert` 에이전트) — Phase 4.5
- 긴 작업 주기의 마무리 보고 (트리거 4 = `cycle-report` 스킬 정본: 사이클 3회 이상 연속 · 자율 진행 구간 종료 · 사용자 "리포트/보고서" 요청 · 세션 종료 전 미보고 누적; 결정 항목 3개 이상이면 사이클 1~2회도) → `cycle-report` 스킬 (`report-writer` 에이전트) — Phase 5. 쉬운 말 아티팩트 보고서 + 원문 md(`_workspace/reports/`) + 결정 카드
- 단위/회귀 테스트 → `tdd-cycle` (백엔드 pytest+respx+freezegun / 프론트엔드 vitest+RTL+MSW)
- 영향 인덱스 → `test-impact-index`
- 통합/경계면/E2E/안전성 → `trading-test`
- **문서 동기화 → `/sync-docs` 명령 (Phase 4.8, 코드 변경 사이클은 커밋 전 필수)** — 코드 위치 → 갱신 후보 문서 매핑 표 + **대상 문서 정본 목록** + 모듈 누락 자가 점검을 담은 유일한 체크리스트다. ⚠️ 전용 `CLAUDE.md` 가 없는 `src/services/` · `src/middleware/` · `tools/` · `e2e/` 가 누락 반복 지점. **실행 주체 = `report-writer` 에이전트**(2026-09-11 사용자 결정) — 메인 세션은 꾸러미를 만들어 위임하고 커밋 여부만 정한다. 식별자·상수·불변식·금기 조건은 인용 대상이라 쉬운 말로 흐리지 않는다.
- KIS API 정본 스펙 (TR_ID·응답 구조·거부 코드) → `kis-mcp-query` 스킬 (backend-dev / tdd-engineer / tester / refactor-expert 공유)
- **⚠️ KIS 스펙의 시간 경계 — `docs/kis/*.md` 는 2026-09-11 03:00 워크북 스냅샷이라 「변경 전」 세계다**(시간외 단일가 16:00~18:00 · `H0STOUP0` 가 현역으로 적혀 있다). 2026-09-14 시행 제도 변경(KRX 애프터마켓 16:00~20:00 신설·시간외 단일가 폐지·시가단일가 08:20 확대·KRX 정규장 미체결 자동취소)은 세 곳에 있다 — 제도·시간표·보드 영향 = [`src/engine/CLAUDE.md`](src/engine/CLAUDE.md) `session.py` 절 · TR·필드 = [`docs/kis/README.md`](docs/kis/README.md) 「제도 변경 공지 반영」 절(`docs/kis` 재생성 시 각 필드 자리에 다시 넣는다) · 할 일·실측 = [`_workspace/00_URGENT_WORKLIST.md`](_workspace/00_URGENT_WORKLIST.md). 찾는 순서 = 위 세 곳 → `kis-mcp-query` → `docs/kis/*.md` 본문(본문에서만 찾으면 09-14 이후 사실이 틀린다)
- **외부 검색 → `insane-search` 스킬 (2026-09-11 사용자 지시)** — 리포 밖 정보는 `WebFetch` 로 시작하지 않는다(402·403·차단 응답 · 스크립트로 그려져 껍데기만 오는 페이지 · X·레딧·유튜브·깃헙 검색·네이버 등 봇 차단 사이트). 단순 검색은 `WebSearch`, KIS 스펙은 `docs/kis/*.md`·`kis-mcp-query` 가 먼저다. **모든 에이전트에 같은 규칙이 적힌다**

**우회 허용 (메인 세션 직접 응답):** 단순 사실 질의, 단발 디버그/grep, 운영 환경 즉시 점검(EC2 SSH 등). 코드 변경 제안이 따라오면 다시 team-leader 로 인계.

### 모델 라우팅

| 작업 유형 | 모델 | 적용 |
|----------|------|------|
| 구현 계획·검수·리팩토링 검토·마무리 보고서 | **opus** | `team-leader`, `tester`, `refactor-expert`, `report-writer` — ⚠️ **모델은 에이전트 정의에 명시한다**(지우면 Fable 상속으로 해석돼 그 크레딧이 마를 때 넷이 함께 막힌다). 세션 모델이 바뀌면 이 네 줄도 바꾼다 |
| 테스트 설계·도메인 자문 | **opus** | `domain-expert`, `tdd-engineer` |
| 일반 구현 (코드 작성·리팩터·버그 수정) | **sonnet** | `backend-dev`, `frontend-dev` |
| 명령어 작성 (bash/슬래시/스크립트) | **haiku** | 메인 세션 단발 작업 — fork 또는 `claude-haiku-4-5-20251001` 위임 |

### 자율 진행과 승인 빈도 (2026-09-05 사용자 결정)

**승인은 결정 지점에서만 묻는다.** **자율 진행 구간**은 사용자가 (a) 구간의 끝(시각 또는 할 일 목록)과 (b) 커밋·배포 허용 여부를 **명시**했을 때만 성립한다. "진행해" 한마디는 구현·검증까지의 승인이고 커밋·push 는 따로 묻는다(명시된 자율 구간이 메모리 "커밋은 명시 지시 시에만" 정책의 유일한 예외다). 구간 안에서는 사전 승인 범위(아래)에 한해 구현 → 검증 → 커밋(작업 단위) → 배포 → 실측 확인을 사이클마다 묻지 않고 잇고, 구간 끝에 `cycle-report` 스킬로 **한 번** 보고한다. 보고서의 "결정해 주세요" 카드는 미룬 승인 요청을 **모아** 전달할 뿐 승인을 대신하지 않는다.

- **8영역** = `src/engine/{risk,order_engine,session,scanner,strategy_registry}.py` · `src/api/order.py` · `src/realtime/**` · `src/auth/**` (정본 목록 = `tests/unit/ast/test_cycle222a3_ast_followup_fixes.py::_EIGHT_AREAS`, 승인 시 그 파일의 sha 핀 절차를 따른다). `scheduler.py` 는 8영역이 아니지만 **라인 상한 `<3,900L`**(cycle257 영구 상한) 때문에 같은 승인 대상이다 — 상한을 복창하는 가드들의 수가 갈라지면 **항상 더 조인 쪽이 정본이다**.
- **사전 승인 범위** (아래 셋을 **모두** 만족할 때만): (a) 8영역·`scheduler.py` 무접촉 — 8영역 안이면 관측 로그 한 줄도 승인 (b) 배포는 운영 가이드의 장외 창 안 — **15:30~16:00 · 21:35~익일 07:45**(backend 재생성 1~5분 여유) · 주말·공휴일 종일. **20:00~21:35 는 자율 구간 중에도 push 금지**(cycle283 D8 — 이유 = 아래 「Docker / 배포」 운영 가이드). 모드 판정이 불확실하면 full(재시작)로 간주(cycle248) (c) 다음 커밋으로 원복 가능. 테스트·문서·관측 전용 변경도 (a) 를 만족할 때만 포함. DB 스키마는 가산형 마이그레이션(NULL 허용 ADD COLUMN·INDEX·신규 테이블)만 포함.
- **여전히 승인이 필요한 것(구간 중에도 멈추고 묻는다 — 위 범위와 충돌하면 이 목록이 항상 우선)** = 8영역·`scheduler.py` 변경 · 보유 중 장중 push(D6) · 기능·설정 비활성화(심층 검증 의무) · 되돌리기 어려운 운영 조치(DB UPDATE/DELETE·DROP·타입 변경·NOT NULL 백필, 수동 매매, 키 회전, 구독·세션 강제 조작) · 사용자 결정 항목(비중·파라미터 값·전략 on/off·자금 **+ 매매 행위를 바꾸는 코드 변경 — 진입·청산·수량·사이징·손절 규약·`DEFAULT_PARAMS` 신규 키 — 는 파일 위치와 무관하게 승인 + `domain-consult` 선행**) · 외부로 나가는 조치(메일·PR 머지·루틴(schedule) 생성/변경·Notion 쓰기·외부 서비스 설정). 단, **이미 승인된 사이클 명세에 포함된** 외부 설정·배포 전 DB 선반영은 그 승인에 포함된 것으로 보되, 실행 전후 값을 보고서 "서버에 올린 것" 표에 남긴다.
- **보고 시점** = 위 「기본 진입점」 의 `cycle-report` 트리거 4. 그 밖에는 터미널 요약으로 충분하다.
- **보고서 기준** = `.claude/agents/report-writer.md`(구조·쓰기 규칙·사실 출처·커밋 금지). 기준 예시 = `.claude/skills/cycle-report/example_2026-09-05.html` + 원문 `_workspace/reports/2026-09-05_night_autonomous_work.md`.

### 병렬 작업 — 같은 작업 디렉터리는 git 이 지켜 주지 않는다

동시에 여러 에이전트를 띄울 때, **파일을 쓰는 에이전트**는 서로의 편집을 덮어쓸 수 있다. git 이 지키는 것은 **커밋된 것**이고 커밋 전 편집본끼리는 나중에 쓴 쪽이 이긴다(2026-09-19 `src/engine/market_regime.py` 덮어쓰기 사고).

- **쓰는 에이전트를 동시에 띄우면 `isolation: "worktree"`** — 읽기만 하는 에이전트(조사·검토·렌즈)는 그대로 둔다(격리는 디스크·준비 시간을 쓴다).
- **띄우기 전에 `git add -A`** — 덮어써도 `git checkout -- <path>` 한 줄로 돌아온다. 인덱스 스냅샷이라 커밋 정책과 무관하다.
- ⚠️ **워크트리를 공유하는 중에는 `git checkout -- <path>` 를 함부로 쓰지 않는다** — 다른 작업이 그 파일에 쓰고 있으면 그쪽 편집이 사라진다.
- 자동 덫 = `tests/unit/deploy/test_cycle319_no_clobbered_module.py`(`src/` 안에 내용이 같은 파일 쌍 = 0) — 다른 파일의 사본으로 덮인 경우만 잡으므로 부분 덮어쓰기는 위 두 습관이 막는다.

### 하네스 변경 이력

이력의 유일한 정본 = [`docs/HARNESS_CHANGELOG.md`](docs/HARNESS_CHANGELOG.md)(상단이 최신). 이 문서에는 이력표를 두지 않는다(위 「문서 규약」 절).

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
- `SUPABASE_URL`, `SUPABASE_KEY`: **런타임 미사용이지만 비우면 기동이 실패한다** — 어느 db 모듈도 읽지 않지만(`src/db/supabase.py` 는 롤백용 병존) `src/config.py:36-37` 의 `supabase_url: str` / `supabase_key: str` 가 **기본값 없는 필수 필드**라 pydantic 검증에 걸린다. "미사용이니 비워도 된다" 로 읽지 않는다
- `AUTO_START`: 서버 기동 시 자동 매매 시작 (DB `system_config.auto_start` 우선, 매일 시작 전 재확인)
- `API_AUTH_KEY` (cycle243): 백엔드 `X-API-Key` 인증 키. **미설정이면 fail-closed** — `/health` 를 뺀 전 경로 401 + 기동 시 `[api_auth_key_missing]` CRITICAL(금기 = 「핵심 안전 규칙」 API 인증 항목). 생성 `python3 -c "import secrets;print(secrets.token_urlsafe(32))"`. 운영에서는 nginx 가 주입해 브라우저에 노출되지 않는다. 키 회전은 frontend·backend **동시 재시작**이 필요해 장 종료 후에만
- `API_ALLOWED_ORIGINS` (cycle243, 기본 빈 값): 교차 출처 허용 목록(CSV). CORS `allow_origins` 와 상태변경(POST/PUT/PATCH/DELETE) Origin 검사가 이 값 하나를 공유한다. 빈 값 = same-origin 전용(prod). dev 는 vite `changeOrigin` 때문에 `http://localhost:3000` 명시
- `API_REPORTER_KEY` (cycle249, 기본 빈 값 = 리포터 역할 비활성 · fail-closed): 리포터 스코프 키 — **GET/HEAD 전체 + `POST /api/log-reports/{date}/external` 한 경로**만 허용한다(20:20 KST 클라우드 루틴이 로그 번들을 읽고 분석 결과를 쓰는 창구). nginx `map $remote_user` 가 Basic 사용자 `reporter` 에게만 주입하므로 운영 키(`default` 사용자)와 다른 값이어야 판정이 성립한다
- `DKSTOCK_REGIME_ENABLED` (기본 false): 매크로 레짐 수신 + cash_usage_ratio 자동 조정 활성화. 출처는 **우리 `macro` 컨테이너**(`MACRO_API_URL`, 기본 `http://macro:8000`)다. 🔴 **변수명은 유지한다** — 운영 DB `system_config.dkstock_regime_enabled` 행과 짝이고, 개명하면 그 행이 고아가 된다. 판정은 **DB 우선 / `.env` fallback** 이다(`services/macro_client.py`). 상한 = `MACRO_API_READ_TIMEOUT_SECS`(90초) · 부팅 전용 `MACRO_API_BOOT_TIMEOUT_SECS`(25초)
- `KIS_MCP_ENABLED` (기본 false): 외부 백테스트 MCP 서버 활성화. 자문 직후 활성 전략마다 2 job(`params_kind` = current|recommended) fire-and-forget

## 다중 전략 (요약)

7 전략: `momentum` / `volatility_breakout` / `long_tail_volatility` / `donchian_swing` / `bull_flag_breakout` / `vcp_breakout` / `kojiro`(고지로 대순환 스윙). 문서는 코드 기본값을 적는다 — 활성 여부·비중·파라미터의 운영값은 DB `strategy_config` 가 정본이다(`GET /api/strategies`).

상세 매수/청산/tradable_boards/exchange 는 **`src/engine/strategies/CLAUDE.md`** 참조.

### 새 전략 추가
절차(`StrategyBase` 서브클래스 · `registry.register()` · 스캔 함수 · AST 목록 등재 · 7전략 공통 키 · `param_catalog` 등재 · `_workspace/00_leader_trading_rules.md` 명세)의 정본 = `src/engine/strategies/CLAUDE.md` 「새 전략 추가」 절.

### 자금 관리
- 프론트 Settings → `PUT /api/strategies/weights` → `StrategyRegistry.allocate_funds()`
- **전략 비중 단위 = 비율 `0.0~1.0`** — 요청 바디·`GET /api/strategies` 의 `weight`·`strategy_config.weight`·AI 자문 `save_weights` 가 같은 단위라 GET↔PUT 왕복이 항등이다(추론 변환 금지 = 「핵심 안전 규칙」). 부팅 오염 감지 `[weight_config_anomaly]` 는 관찰만 한다 — **자동 클램프·정규화 금지**. 경로별 검증 = `src/routes/CLAUDE.md` 「전략 설정 쓰기 경로 — 비중 · 파라미터 · AI 자문 적용」 절 · 부팅 감지 = `src/engine/CLAUDE.md` `scheduler.py` 절 `_load_strategy_config()`
- `position_ratio` 는 **전략 할당 자금 기준** — 정확한 식은 `순자산 × cash_usage_ratio × (weight / Σweight_enabled) × position_ratio` = 종목당 매수금액. `allocate_funds` 가 **Σ 로 정규화**하므로 Σ≠1 이어도 자산 전액이 배분된다
- **전략별 투자한도 — 삼중** — ① 개수 `max_positions` ② 명목 `Σ매수금액 ≤ total_investment`(관문 `StrategyBase._apply_budget_limit` — 잔여 부족 = **부분 매수**, 잔여 < 1주 → 0) ③ **리스크 `Σ오픈리스크 ≤ max_open_risk_pct × 예산`**(kojiro 한정). **개수 캡을 리스크 캡으로 대체 금지**(저ATR 종목 포지션 수 폭증). 불변식 **`position_ratio × max_positions ≤ 1.0`**(AST C-DEFAULT · `_validate_recommendations`). `max_positions` 는 리스크 정체성 상수라 `PARAM_RANGES`/`INT_PARAMS` **편입 금지**. 상세 = `src/engine/strategies/CLAUDE.md` 「자금관리 — 사이징 방식 × 손절 기준 매트릭스」 절
- **1회 투자금액 ATR 유닛화 (`sizing_mode="turtle"`)** — `unit = floor(전략예산 × risk_pct ÷ ATR)`. **손절이 ATR 기반인 전략에만 적용**한다 — 손절이 고정%면 `position_ratio` 가 이미 리스크 균등이라 사이징만 바꾸면 정규화가 깨진다(함정 #1). 터틀 수량 ≤ 비중 수량이라 전환은 순수 축소다. 🔴 **유닛화는 랏 미세화를 풀지 못한다** — 비중·자금을 그대로 두고 유닛만 도입하면 `floor(예산 × risk_pct ÷ ATR) = 0` 으로 그 전략이 **전면 무매매**가 된다(고칠 대상은 사이징이 아니라 전략 간 배분). 배선·제외 사유·`q` = 위 매트릭스 절
- **랏당 최대 유닛 상한 `max_lot_units` (K=2.0, cycle242)** — `sizing_mode="turtle"` 전략의 **모든** 매수 랏을 `floor(K × 예산 × risk_pct ÷ ATR)` 주 이하로 자르고 0 이면 매수하지 않는다(`min` — 줄이는 방향뿐). ATR 결측·모호·`risk_pct ≤ 0`·예외는 **fail-open**(`[fallback_cap_skipped]`) — fail-closed 는 유령 키 사고(전 기간 체결 0건)의 방향이라 금지. K 는 리스크 정체성 상수 — `PARAM_RANGES`/`INT_PARAMS` **편입 금지**(AST G-242-1), 클램프 `[1.0, 20.0]`. 롤백 = `max_lot_units = 20.0` — `PUT /api/strategies/{id}/params` 는 **즉시**, `strategy_config` SQL UPDATE 는 **다음 백엔드 재시작에서만** 반영되므로 보유 중 장중 롤백은 PUT 뿐이다(cycle232 D6). 나머지 = strategies 「자금관리」 절
- **랏 명목 ρ축 상한 `max_lot_ratio_mult` (K_ρ=2.5, cycle245)** — 관문을 지나는 **모든** 랏의 명목을 `K_ρ × position_ratio × 예산` 이하로 자르고 1주도 못 사면 매수하지 않는다(실효는 1주 폴백 랏뿐, K축 뒤에 `min` 후심사 — cycle254). **키 부재 = OFF**(`max_lot_units` 와 **반대** — 매수를 막는 통제라 "설정이 없으면 막는다" 는 유령 키 재현 경로다). 키는 **7 전략 전부** `DEFAULT_PARAMS` 에 둔다(AST glob 전수). 결측·판정 예외 = **fail-open**(`[ratio_cap_skipped]`). K_ρ 도 리스크 정체성 상수 — `PARAM_RANGES`/`INT_PARAMS`·AI 자문 자동 적용 경로 **편입 금지**(AST G-245-1), 클램프 `[1.0, 20.0]`. 롤백 = K_ρ=20.0(반영 시점은 K축과 같다). 산식·조기탈출·마커 = strategies 「자금관리」 절
- **시장 유닛 `market_unit_mode` (cycle382, 사용자 결정 2026-09-27)** — 장세(KODEX 200 `069500` 직전 영업일 봉의 60일선 위치·기울기)에 따라 터틀 4전략(`kojiro`·`donchian_swing`·`bull_flag_breakout`·`vcp_breakout`)의 **신규 진입 설계 랏만** 1 / 0.75 / 0.5 / 0 배로 줄인다(예산 경로·K축·ρ축·보유분·청산은 무접촉). 못 사는 종목은 수량 0 이 아니라 **신호 단계 `Signal.NONE`** 으로 거른다(수량 0 은 900s cooldown 으로 오귀인된다). 결측·예외 = **m=1** + WARNING. 모드 `off|shadow|enforce`(부재·오타 = `off`, 4전략 기본 `shadow`)는 PUT params 로 **즉시** 바뀐다. `PARAM_RANGES`/`INT_PARAMS`·AI 자문 자동 적용 경로 **편입 금지**. 🔴 **매크로 레짐과 다른 축이다**. 규칙 = `src/engine/strategies/CLAUDE.md` 「시장 유닛 — 터틀 4전략 (cycle382)」 절 · 계산 자리·마커 = `src/engine/CLAUDE.md` `strategy_base.py` 절
- 전략 간 동일 종목 중복 매수 방지: `registry.is_ticker_blocked_for_buy()` (보유/주문중/당일매도 통합 차단)
- **`cash_usage_ratio`**: `system_config.cash_usage_ratio` — `_boot()` 가 `summary.net_asset × ratio` 로 `allocate_funds()` 호출. 범위 `[0.0, 1.0]`, 5% 단위, 기본 1.0, Settings 슬라이더 → **다음 영업일부터 반영**. `auto_regime_adjust` 가 켜져 있고 `DKSTOCK_REGIME_ENABLED=true` 면 매크로 레짐 `cash_min` 으로 자동 갱신(`clamp((100-cash_min)/100, 0.0, 1.0)`). `auto_regime_adjust` 판독 불가(키 없음·형식 오류·예외)는 전부 **false(수동 모드)** 다(`src/db/CLAUDE.md` 「system_config.py — 시스템 설정 키-값 헬퍼」 절)

### 외부 통합 (백테스트 + 매크로 레짐)
- 20:00 AI 자문 INSERT 직후 외부 MCP 백테스트 (`http://43.202.187.5:3846/mcp`) — 활성 전략마다 2 job(`params_kind` = current|recommended) fire-and-forget → `parameter_recommendations.backtest_summary` JSONB
- 매크로 레짐 (**우리 `macro` 컨테이너**, cycle315) — `regime/vix/fear_greed` 관찰 + `cash_usage_ratio` 자동 조정(식 = 위 「자금 관리」). **매크로 레짐은 관찰 지표다 — 매수를 차단·축소하지 않는다**(`buy_block_mode` 는 표시 전용, `get_buy_block_state` 는 대시보드/자문 payload 만 소비). 장세에 따른 신규 진입 축소는 **시장 유닛**(「자금 관리」 `market_unit_mode`)이 전략 사이징에서 한다. ETF 레짐·포트폴리오 리스크 관찰 활성
- 활성화 토글: `KIS_MCP_ENABLED` / `DKSTOCK_REGIME_ENABLED` / `etf_regime_enabled` (Settings UI 즉시 토글). 외부 다운 시 graceful — 자문 INSERT 보존, summary=null, 레짐 관찰 비활성
- 운영 가이드: [`docs/backtest-monitoring.md`](docs/backtest-monitoring.md)

## 핵심 안전 규칙 (절대 깨지 말 것)

상세 메커니즘은 항목마다 링크한 하위 `CLAUDE.md` 절이 정본이다. 여기서는 **금기**와 그 이유만 둔다:

- **기능·설정 비활성화(disable / toggle off / dead 판정) 시 심층 검증 의무** — "미사용/dead/낭비" 라고 단정하기 **전에 소비처(consumers)를 `grep` 으로 전수 확인**하고, 끈 **뒤에는 그 소비처의 산출물(예: 적재 종목수)을 라이브 실측**한다. 비활성화는 "제거" 가 아니라 **"경로 변경"** 일 수 있다(주 경로를 끄면 폴백 경로가 조용히 degrade 된다). 설정 토글은 CI/Deploy 를 안 타 자동 검증도 없다. 실측 없는 비활성화 금지 — 2026-08-08 `krx_open_api_enabled` 오판으로 `full_universe_load` 가 3,577→60종목으로 degrade 된 사고
- 🔴 **보유 포지션이 있는 전략을 끄지 않는다 — 끄는 순간 그 포지션의 손절이 멈춘다.** `risk.on_tick` 이 `registry.enabled()` **단일 순회**라 끈 전략의 보유분은 손절·트레일링·익일청산·15:20 강제청산이 **전부 정지**한다. 끄기 전에 **그 전략 보유 0 을 확인**하거나 먼저 청산한다. 🔴 **`weight=0` 도 끄기다** — `registry.update_weights` 가 `config.enabled = weight > 0` 을 자동 토글하므로, 보유가 있는 전략의 비중 0 은 `PUT /api/strategies/weights` 와 `POST /api/recommendations/{id}/apply` 가 모두 거부한다(apply 는 비중만 거부하고 파라미터 적용은 진행한다). ⚠️ 「전략 수를 줄여 전략당 예산을 키운다」 처방이 이 금기를 밟는다. 대신 — **랏을 키우려면** `max_positions` 를 줄이고 `position_ratio` 를 올린다(불변식 유지, `weight` 무접촉) · 신규 유입을 **줄이려면** `position_ratio`·`max_positions`(PUT params — `enabled` 를 건드리지 않고 하한선 검증도 없다) · **멈추려면** `buy_paused`(바로 아래). 경로별 가드·하한선 검증·조회 실패 처리 = `src/routes/CLAUDE.md` 「전략 설정 쓰기 경로 — 비중 · 파라미터 · AI 자문 적용」 절
- 🔴 **신규 매수만 멈추기 = `buy_paused` (cycle384 — 사용자 결정 2026-09-27 「돈키언 신규매수 중지」)** — 7 전략 공통 `DEFAULT_PARAMS["buy_paused"]=False`. `PUT /api/strategies/{id}/params {"params":{"buy_paused":true}}` 로 켜면 그 전략의 **신규 매수 신호만** 멈추고 보유분 청산·손절은 그대로 돈다(**즉시** 반영, DB 저장으로 재시작 뒤에도 유지). 🔴 **신호 단계에서 막는다**(공통 게이트 `StrategyBase._account_soft_gate_blocked` 둘째 문장) — 수량 0 반환·`buy_disabled`·`enabled`·`weight` 로 대신하지 않는다. 🔴 **`is True` 일 때만 멈춘다**(PUT 은 bool 이 아니면 422). 🔴 `PARAM_RANGES`/`INT_PARAMS` **편입 금지**(AI 자문이 켜고 끄면 안 된다 — AST `test_cycle384_ast_buy_paused.py` A11). 🔴 **멈춰 둔 동안 코드에서 키를 지우지 않는다** — `_load_strategy_config` 가 DB 의 `true` 를 버려 조용히 풀린다. 상세 = `src/engine/CLAUDE.md` `strategy_base.py` 절 · `src/engine/strategies/CLAUDE.md` 각주 ⑨
- **체결통보 구독 (H0STCNI0/H0STCNI9) 제거 금지** — 미구독 시 포지션 등록·손절 불가
- **uvicorn 단일 워커 필수** — `--workers` 금지 (스케줄/포지션/WebSocket 중복)
- **주문번호 매핑** (`_order_qty/_order_strategy/_order_ticker/_pending_buy_orders`) 등록은 `place_order` 응답 직후 동기 영역, `await insert_trade` 진입 전 — 시장가 즉시체결 race 시 매핑 누락하면 기본값 "momentum" 으로 잘못 INSERT됨
- **체결통보 선행 race 가드** (`_completed_orders` set + UPDATE 0건 보정 INSERT) 제거 금지 — 시장가 즉시체결 + REST 응답 지연 시 trade_history 가 PENDING 영구 잔존. 두 번째 창(PENDING `insert_trade` 의 `await` 도중 체결통보가 먼저 완주해 migration 029 부분 UNIQUE 위반 → `execute_buy` ERROR 종료로 스윙 폴의 `buy_succeeded` 후처리(매수 직후 HIGH 구독)가 빠진다)은 `_insert_pending_or_absorb_race(side=…)` 가 **`_completed_orders` 에 그 주문번호가 있을 때만** `UniqueViolationError` 를 흡수·discard 해서 막는다. 증거 없는 위반은 그대로 전파한다 — 무조건 삼키기·재시도 INSERT 금지. 상세 = `src/engine/CLAUDE.md` `order_engine.py` 절 「체결통보 race 가드」
- **주문이 나간 뒤의 실패로 재발사 금지 (cycle327·335)** — `place_order` 가 성공한 주문은 이미 거래소에 있으므로 그 뒤의 어떤 예외도 재시도·발사 실패 정리로 되돌리지 않는다. 매수·매도 4 경로는 축별 경계 래퍼(`_persist_buy_pending_after_send` · `_persist_sell_pending_after_send`)가 `try/except Exception` 으로 닫고 `[buy_post_send_error]`/`[sell_post_send_error]`(**무cap ERROR**)를 남긴다. 🔴 두 래퍼의 `except Exception` 을 **좁히지 않는다**(행위 회귀가 초록인 채로 새서 구조 가드 `test_cycle328_sell_pending_helper.py::test_g328_3b` 가 유일한 방어다). 🔴 매도는 재시도 직전 `strategy.state.positions.get(ticker)` 를 **재조회**해 사라졌으면 `[sell_position_gone]` 후 중단한다(루프 밖 지역 참조 `pos` 는 체결 뒤에도 옛 수량이라 이미 판 것을 다시 판다). 🔴 매수는 `pending_buys`/`pending_buy_amounts` 를 **풀지 않는다**(KIS 가 이미 묶은 자금). 피라미딩 착수 선결 = `pending_buy_amounts` 키를 `(ticker, order_no)` 로 바꾸기(지금은 `ticker` 단일 키라 같은 종목 두 번째 주문이 첫 번째를 덮는다). 상세 = `src/engine/CLAUDE.md` 「접수 후 PENDING 영속화 — 1코어 + 축별 경계 래퍼 2」 절 · `order_engine.py` 절(매도 재조회)
- **체결통보 주문수량은 3단 출처 (cycle329)** — `await place_order` 동안 주문번호 매핑이 비어 그 창의 통보는 **부분 체결이 전량으로 오판**되므로 `map`(`_order_qty`) → `payload`(체결통보 `fields[16] ODER_QTY`) → `increment` 순으로 읽는다. 🔴 **전량 판정에 출처 게이트를 걸지 않는다**(수동 전량 매도가 유보돼 `_selling` 좀비 = 손절 마비) · 🔴 **재주문 타이머는 `qty_src=="map"` 일 때만**(없으면 **사람이 낸 주문을 30초 뒤 취소하고 다시 낸다**) · 🔴 **체결수량 소스 `fields[9]` 는 무접촉**(257720 사고, `test_cycle235_ast_execution_qty.py` 봉인). 상세 = `src/engine/CLAUDE.md` 「체결통보 주문수량 — 출처 3단 (cycle329)」 절
- **매도 체결은 두 축으로 판정한다 (cycle385 — 사용자 결정 2026-09-26·27, 분할 매도 허용)** — `_handle_sell_fill` 의 **주문 축**(`total_filled >= ordered_qty`)은 장부·매핑·타이머·`_selling` 을, **보유 축**(`pos.quantity` 차감 후 0 인가)은 포지션 삭제·`on_position_closed`·`sold_today`·구독 해제를 정한다. 불변식 셋 = **추적 밖 실보유 0** · **우리 주문 합 ≤ 추적 수량**(운영자 몫은 팔지 않는다) · **안 잠긴 추적 잔여는 팔 수 있어야 한다**. 🔴 보유 축에도 출처 게이트를 걸지 않는다 · 🔴 주문이 끝나면 보유가 남아도 `_selling` 을 조건 없이 푼다(남기면 잔여 손절이 멈춘다) · 🔴 「안 걸렸다」 판정은 `order_engine._sell_not_placed_reason(exc)` 한 곳뿐이다. 나머지 조건·알려진 한계의 정본 = `src/engine/CLAUDE.md` 「매도 체결 — 주문 축과 보유 축 (cycle385)」 절
- **`_reset_daily_state()` 제거 금지** — 정산 후 미초기화 시 pending_buys/positions/sold_today 가 다음 날까지 잔류
- **익일 청산** 은 scheduler 에서 시가 수신 후 30s 안정화 처리 — `_pending_next_day_clear` 보류 후 09:00 KRX 시장가. `high_since_buy` 폴백 금지. on_tick 즉시 청산 금지
- **관리종목(51)·단기과열(59) 보유 청산 + 당일 매수 차단 (cycle369 — 사용자 결정 2026-09-25·26)** — 보유 종목(꺼진 전략 포함)을 REST 전용 플래그 `mang_issu_cls_code`·`short_over_yn` 으로 읽어 KRX 정규장 **09:00:30~15:28** 안에서 `Y` 면 시장가로 판다(종목당 하루 3회). 🔴 창 밖 발사 금지(16:00~20:00 애프터는 단기과열종목을 거래 대상에서 뺀다) · 🔴 **매도는 종목상태 코드 51·59 폴백만으로 쏘지 않는다**(정상 ETF·스팩·우선주에도 붙는다) · 🔴 `ssts_hot_yn`·`short_over_cls_code`·`stock_master` DB 값으로 판정하지 않는다 · 🔴 **보유 종목 구독은 끊지 않는다**(청산이 거부되면 손절이 눈을 감는다). 킬스위치 `system_config.status_exit_mode`·`status_buy_block_mode`(키 없음 = `enforce`) · 즉시 반영 `PUT /api/integrations/status-exit`. ⚠️ 특별 개장일(지연 개장)에는 개장 전에 `sell_mode` 를 `off`/`observe` 로 내린다. 상세 = `src/engine/CLAUDE.md` 「종목상태 청산·당일 매수 차단」 절
- **NXT 매도 거부 좀비 차단** — `is_market_closed_rejection`(APBK0918 + 장운영시간 외)이면 `execute_sell` 이 positions(메모리/DB)를 보존하고 `_selling` 을 **discard** 하고 재시도를 멈춘다(보존하면 stale `_selling` 좀비 = 손절 마비 — 이후 차단은 진입 게이트 `SellRejectionTracker.is_blocked()` 가 맡는다). `is_insufficient_quantity` / `is_insufficient_cash` 와 분리. 진입 게이트 **2단계 TTL** = KRX 메인(09:00~15:30) 거부 **5분**(일시 장애 가정) · NXT 시간대(08:00~09:00 / 15:30~20:00) 거부 **다음 KST 09:00** · `market_order_disallowed` 거부 **30초**(동일 tick 폭주 차단). NXT 폴백 실패면 `_pending_next_day_clear` 익일 청산으로 자동 전환. `_reset_daily_state` 동행 clear. 구현 = `src/engine/CLAUDE.md` `order_engine.py` 절 · 분류 헬퍼 = `src/api/CLAUDE.md` 「KIS 거부 응답 분류 헬퍼」 절
- **매수/매도 시장가 거부 → 지정가 5호가 폴백 1회** — `is_market_order_disallowed`(msg1 키워드 판정, APBK1943/APBK3013 — 키워드 목록 정본 = `src/api/CLAUDE.md` 「KIS 거부 응답 분류 헬퍼」 절) 매칭 시 `step_up(buy)/step_down(sell)` 으로 `LIMIT` 재시도. 매핑 동기 + race 가드 동일 규약
- **KIS 거부 응답 영구 저장** — `_request` 가 `rt_cd != "0"` 시 `system_logs` `[kis_rejection]` 을 fire-and-forget 으로 남긴다(민감 키 마스킹). 접수 **뒤** 거래소가 거부한 주문은 체결통보 채널의 접수 전문으로 와서 `[order_rejected_notice]` WARNING 이 된다. 상세 = `src/api/CLAUDE.md` 「base.py — 공통 래퍼 (메인 단일)」 · `src/realtime/CLAUDE.md` 「접수 전문 기록」
- **WebSocket 시세 보유·익일청산 우선 보장** — `MAX_SUBSCRIPTIONS=41`(KIS 공식 한도)에서도 HIGH(보유/익일청산)는 `bypass_limit=True` 로 절대 보장한다. 후순위 drop = `[priority_drop]` INFO + WARNING `system_logs`, HIGH 단독 41 초과 = ERROR. 상세 = `src/engine/CLAUDE.md` `scanner.py` 절 · `src/realtime/CLAUDE.md` 「우선순위 정책」
- **WebSocket 다중 안전망** — F1(재연결 후 검증) + `_scan_loop`(5분) + K stale watcher(120s) + `_resubscribe_stale_priority`(5분 우선) **4중**을 단일 복구로 대체하지 않는다. K stale watcher 재등록은 보유·`_pending_next_day_clear` = HIGH + `bypass=True`, 그 외 후보 = LOW + `bypass=False`(메인 편중 차단). 횟수·cooldown·cap = `src/engine/CLAUDE.md` `scheduler.py` 절 `_stale_watcher_loop()` · 구조 단순화 금기 = `src/realtime/CLAUDE.md` 「안전 규칙 (멀티 세션)」 절 · `_subscriptions` 정합성 가드(orphan ACK race 차단) = 같은 문서 「subscribe / 거절 감지 / ACK 추적」 절
- **세션 단위 silent inactive 자동 reconnect** — `fresh_ratio < SILENT_INACTIVE_FRESH_RATIO_THRESHOLD(=0.2)` + `subscribed_count >= 5` + 5분 지속이면 `_ws.close()` 로 강제 재연결한다(시간당 세션당 2회 cap — LMS/앱키 정지 위험 차단). 판정 가능 세션 ≥2 가 **전부** 침묵이면 **시장 침묵**으로 보고 그 사이클을 기각한다(`[silent_inactive_market_wide_skip]`). 🔴 기각 판정에 시간창 리터럴·`tradable_boards`·`session` import 를 쓰지 않는다(AST G-241-5) · 🔴 `first_seen` 을 누적한 뒤 거르지 않는다(pop — 시장 재개 순간 지각 세션이 즉발한다). fail-open 조건·대상 슬롯 = `src/engine/CLAUDE.md` 모듈 맵 `stale_session_recovery.py` · `scheduler.py` 절
- **무송출(no_feed) 종목은 K stale watcher 가 재등록하지 않는다 (cycle252)** — `stale_watcher_core.check_and_resubscribe_stale` 이 `no_feed_registry`(**fail-open**)로 **LOW no_feed 종목의 SEND·스탬프·force_retry history 만** 건너뛴다. 🔴 **HIGH(보유·익일청산) 경로는 byte 동일**하다 — 가설이 틀렸을 때 잃는 것이 손절 커버리지다(대신 `[no_feed_held]` WARNING). 금기 = no_feed 를 stale 집계에서 **빼서** 숫자를 좋게 만들기 · HIGH 를 skip 에 넣기 · 관측 헬퍼가 예외를 올려 HIGH 재등록 사이클을 끊기. ⚠️ 이 마커들과 `[tick_coverage] stale` 은 2026-09-14 배포 전후 로그를 **합산하지 않는다**. 상세 = `src/engine/CLAUDE.md` 모듈 맵 `stale_watcher_core.py` · 채널 = `src/realtime/CLAUDE.md` 「시세 채널 — 시간축 전환 + 프리 창 속성축 보정」 절
- 🔴 **전제 — 넥스트트레이드(NXT)에서 거래되는 종목은 전부 KRX 상장 종목이다.** NXT 는 대체거래소(ATS)라 **자체 상장이 없다**. 그래서 `nxt_tradable` 은 상장 위치가 아니라 「KRX **에 더해** NXT 에서도 거래되나」다(정의 = `cptt_trad_tr_psbl_yn=="Y" ∧ nxt_tr_stop_yn=="N"`, `api/condition.py::inquire_stock_basics`). `nxt_tradable=False` 는 **「KRX 전용」**이고 09:00~20:00 KRX 정규장·애프터에서 정상 매매된다. 「NXT 미상장」·「NXT 에만 있는 종목」 같은 말은 쓰지 않는다 — 실재하지 않는 상태다.
- **NXT 시세 채널은 프리장(08:00~09:00) 전용이다** — 리졸버 `scanner._resolve_channel` 은 시각축이 KRX 창을 주면 속성축을 **호출하지 않는다**. 그래서 **09:00~20:00 은 `nxt_tradable` 과 무관하게 전 종목이 `H0STCNT0`** 이고(자동 원복 래치가 선 날은 예외), 전환은 하루 **1회**(`pre_to_krx`)다. 리졸버 구조 = `src/engine/CLAUDE.md` 「모듈 맵」 「시세 채널 (통합 채널 소멸 후)」 · 채널 규칙 = `src/realtime/CLAUDE.md` 「시세 채널 — 시간축 전환 + 프리 창 속성축 보정」 절
- **`nxt_tradable` 은 「어느 거래소로 보낼까」 에만 쓴다 — 「살까 말까」 에는 쓰지 않는다 (사이클 156 Q0 · cycle336 원복)** — 후보를 `list_by_filter` 로 뽑는 6전략은 전부 `nxt_tradable=None`(코드 기본값)이고(momentum 은 `list_by_filter` 를 쓰지 않는다 · `src/engine/strategies/CLAUDE.md` 「prepare 공통」), `risk.on_tick` 의 매수 평가에도 코호트 게이트가 **없다. 되살리지 마라** — 채널 판정으로 매수 평가를 건너뛰는 `if chan_buy_blocked: continue` 꼴 금지(계측기 `_tick_buy_eval_blocked_by_channel` = `src/realtime/CLAUDE.md` 「시세 채널」 절). 🔴 반대로 **남겨야 하는 세 배선**은 전부 주문·청산 쪽이고 걷었을 때의 대가가 다르다: ① `order_engine._probe_nxt_downgrade_base`(NXT **거래대상이 아닌** 종목의 NXT 주문 = 거부 · **KRX 애프터 44/41 청산 변환의 전제**) ② `scheduler` 익일청산 KRX 예약(걷으면 08:00 프리장 NXT 시장가가 `APBK0918` 거부 → 다음 09:00 TTL 로 그날 청산이 잠긴다) ③ 프리장 시세 채널 선택(걷으면 **프리 창 한 시간의 KRX 프레임만** 잃는다 — 청산은 깨지지 않고, 그 창의 유일한 청산 소비자는 LTV 다)
- **stale universe 가드** — `_evaluate_universe_guard` 가 stale>5 ∧ `today_volume < UNIVERSE_LOW_VOLUME_THRESHOLD(=10_000)` 종목을 그날만 구독 해제한다(`[universe_excluded]`). 보유/익일청산은 절대 보호하고 `_reset_daily_state` 가 함께 비운다(영구 블랙리스트 금지). 상세 = `src/engine/CLAUDE.md` `scheduler.py` 절
- **`trade_history` 중복 INSERT 차단** — `_sync_orders_to_db` 는 `get_today_buy_trades_for_sync()` / `get_today_sell_trades_for_sync()`(dedupe 없음 + CANCELLED 제외)만 쓴다. 포지션 복구용 `get_today_buy_trades()` 의 ticker dedupe 를 sync 중복 판정에 쓰지 않는다 — 다른 `order_no` 가 가려져 핑퐁 INSERT 가 난다. 이중 안전망 = 부분 UNIQUE `(ticker, order_no, trade_type)`(migration 029). 상세 = `src/db/CLAUDE.md` 「trade_history.py — 거래 내역」 절
- **NXT 거래가능 사전 판별** — `stock_master.nxt_tradable=False` 면 NXT/SOR → KRX 강제 다운그레이드(`[nxt_downgrade]`). `_boot()` 가 보유 + `_pending_next_day_clear` 를 eager 갱신한다. 거부 사후 보강 `stock_master.upsert_one(ticker, nxt_tradable=False)` 는 NXT/SOR 주문의 프리장(08:00~08:50) 거부일 때만 쓴다 — 🔴 KRX 로 보낸 주문의 거부에는 쓰지 않는다(잘못된 낙인은 다음 영업일 프리장까지 ≈24h 남는 래치가 된다). 상세 = `src/engine/CLAUDE.md` `order_engine.py` 절
- **종목코드 형식 비대칭** — 진입은 6자리 숫자만 (`isdigit()`), 사후처리는 6자리 영숫자 (`isalnum()`) — 영숫자 코드(신주인수권 등)·7자리 ETN 코드 자동매매 차단 + 좀비 포지션 방지. 🔴 **이 규칙은 ETF 를 막지 못한다**(ETF 코드도 6자리 숫자다) — ETF/ETN 매수 제외는 `src/engine/etf_like.py::is_etf_like`(cycle380)가 맡는다. 판정 규약 = `src/engine/CLAUDE.md` 모듈 맵 `etf_like.py`
- **매수 수량은 전략 잔여 자금 기준** — 7 전략 `calc_buy_quantity()` 의 **모든 return** 이 `StrategyBase._apply_budget_limit()` 관문을 지난다(AST 가드 A-GATE). 잔여 = `total_investment - (positions buy_price×qty + pending_buy_amounts 합)`. **관문 안의 순서가 계약이다** — 폴백(`_fallback_one_share`)·잔여 클램프 → `_apply_lot_units_cap`(K축) → `[oversized_fallback]` 관측 → `_apply_ratio_notional_cap`(ρ축) → `return`(순서를 바꾸면 관측·마커가 사라진다). 관문 안 `await`/DB/HTTP **절대 금지**(AST A-PURE) — `execute_buy` 의 `calc_buy_quantity`↔`pending_buys.add` 사이 await 0건(A-ATOMIC)이 깨지면 두 코루틴이 같은 잔여를 보고 각자 매수한다. 관측 실패가 수량을 바꾸면 안 된다(행위는 cap 밖). 반환 타입은 **`int`**(float 이면 `api/order.py` 가 `ORD_QTY="2.0"` 을 KIS 로 보낸다). 헬퍼·마커·가드·시장 유닛 분기 자리 = `src/engine/CLAUDE.md` `strategy_base.py` 절
- **API 인증은 조용히 꺼지지 않는다 (cycle243)** — `ApiAuthMiddleware` 가 **최외곽**(`MetricsMiddleware` 바깥 — starlette 는 마지막 `add_middleware` 가 가장 바깥)에서 `/health` 를 뺀 **전 경로**를 `X-API-Key` 로 지킨다. `API_AUTH_KEY` 미설정·빈 문자열·비교 예외는 전부 **401(fail-closed)** — fail-open 은 "키가 없으면 인증이 사라진다" 는 뜻이라 금지다(매매 엔진은 in-process 라 API 가 잠겨도 매매 영향 0). 금기 = (a) `/api` 접두사 스코프로 좁히기(`/docs`·`/openapi.json` 이 열린다) (b) 프로덕션 코드의 테스트 우회 플래그 — 테스트는 `authorize` monkeypatch seam **하나**만 쓴다(`tests/conftest.py::_neutralize_api_auth` + 옵트아웃 마커 `real_api_auth`) (c) `API_ALLOWED_ORIGINS=*` — 코드가 **버리고 경고**한다(CORS credentialed preflight 개방 + CSRF Origin 검사 무력화) (d) 개발 예외·개발용 기본키 — dev 는 vite proxy 가 서버 측에서 `X-API-Key`·`Origin` 을 넣는다. **리포터 스코프(cycle249)** — 운영 키 판정 **뒤**에 `API_REPORTER_KEY` 를 본다: GET/HEAD 는 통과, `POST /api/log-reports/{date}/external` 정확 경로만 통과, 그 외는 유일하게 **403**(`reporter_scope`). 스코프는 nginx `map $remote_user` 가 고르는 **Basic 사용자**에서 나온다(`location /api/` 가 클라이언트 헤더를 치환한다). Origin 검사·응답 형식·포트별 인증·단일 공유 키 한계 = `src/routes/CLAUDE.md` 「인증 — deny-by-default」 절
- **비중 단위 추론 변환 금지** — 전략 비중은 **어느 계층에서도 값 크기로 단위를 추측하지 않는다** — `v / 100 if v > 1 else v` 같은 추론 분기는 1%(정수 `1`)를 100%로 저장하고 그 오염을 "균등분배" 화면으로 위장하는 결함 은폐 장치다. 단위는 계약(비율 0.0~1.0)이고 위반은 조용히 흡수하지 않고 422 / `success=false` 로 **시끄럽게 거부**한다. AST 가드 = `tests/unit/ast/test_ast_weight_no_magnitude_heuristic.py` + `frontend/src/components/__tests__/_ast_weight_unit_guard.test.ts`
- **터틀 ATR 손절 게이트는 `_entry_atr` 스탬프 존재** — `sizing_mode` 로 게이팅 금지(DB 토글 하나로 **기보유 포지션의 손절 규약**이 바뀌면 안 된다). 스탬프 값 = sizing 에 쓴 ATR(커플링 불변식). 이 금기는 **청산** 규약이라 진입 사이징이 `sizing_mode` 로 분기하는 것과 충돌하지 않는다. 재시작 재도출은 그 전략이 지금 `sizing_mode="turtle"` 일 때만 한다(`StrategyBase._entry_atr_rederive_allowed`, AST G6). ⚠️ 보유 중 `sizing_mode` 를 바꾸면 기보유분이 새 설정의 손절을 탄다 — 전환은 그 전략 보유 0 에서 한다. 상세 = `src/engine/strategies/CLAUDE.md` 「자금관리 — 사이징 방식 × 손절 기준 매트릭스」 절
- **VB 당일 15:20 일괄매도** — `DEFAULT_TRADABLE_BOARDS=("main",)`, POST_NXT 추가 금지. `_force_clear_main_only` 가 15:20 일괄 청산. 15:30 이후 호출은 시간 가드로 skip
- **`tradable_boards` 는 매수 진입 전용 (명문화)** — 매도/손절/Trailing/익일청산/15:20 강제청산/상한가 손절 모니터링은 어떤 전략에서도 PRE/MAIN/POST 무관 항상 작동(`risk.on_tick` 의 `check_exit_signal` 분기는 `session_tracker.is_tradable` 검사 *전* 진입). **유일한 예외 = NXT 프리장(08:00~09:00) 청산 평가 보류 게이트**(2026-08-06 사용자 결정, `risk._PRE_MARKET_EXIT_EVAL_STRATEGIES` 화이트리스트 = LTV 만) — 프리장 왜곡 틱의 허깨비 손절을 막고 09:00 KRX 시세로 재평가한다. **평가 보류이지 주문 보류가 아니다**(주문만 보류하면 허깨비 신호가 09:00 실매도가 된다). 게이트는 `tradable_boards` 가 아니라 **명시 상수**로 판정한다(AST 가드). LTV `DEFAULT_TRADABLE_BOARDS=("pre_nxt", "main", "post_nxt")`. 상세 = `src/engine/CLAUDE.md` 「risk.py」·「order_engine.py」 절 · `src/engine/strategies/CLAUDE.md` 「안전 규칙」
- **VB·LTV `main` 목표가 기준가 = KRX REST 단일 출처 (cycle272 — 사용자 결정 D1)** — `board=="main"` 목표가는 WS 세션 시가(KRX 확정 시가와 어긋난다) 대신 **KRX REST `stck_oprc`(`J`) 만** 기준가로 삼는다(`on_open_price_confirmed` 의 `source` 신뢰 목록 = `("rest",)`, 기본 `"ws"` 는 조용히 거부). 프린트 안 된 종목은 그 시점 매수 불가. 킬스위치 `open_price_scope_mode`(전략별, 기본 `"enforce"`, `"off"` 만 롤백 — `PARAM_RANGES`/`INT_PARAMS` 편입 금지). `pre_nxt`/`post_nxt` 보드는 게이트 밖이다. REST 확보 일정 = `src/engine/CLAUDE.md` 모듈 맵 `open_price_rest.py` · 상세 = `src/engine/strategies/CLAUDE.md` 각주 ③
- **donchian_swing `_swing_rest_poll_loop`** 제거 금지 — 09:30~15:20 60s REST 폴링으로 멀티데이 손절 평가 보강
- **모든 시각 데이터 KST 강제** — 백엔드 `_to_kst(iso)` 헬퍼 + `_today_kst_iso()` timezone 명시 (`+09:00`). 프론트는 `src/utils/kst.ts`(단일 진실원, `timeZone='Asia/Seoul'`)에 위임한다 — 새 `Intl.DateTimeFormat` 생성 금지(`frontend/CLAUDE.md` 「시각적 컨벤션」 절). `new Date(iso).getHours()` 브라우저 로컬타임 추출 금지
- 매매 파라미터 (`DEFAULT_PARAMS`) 변경 시 `_workspace/00_leader_trading_rules.md` 동기화

### 코딩 컨벤션
- Python: pydantic + async/await
- TS: 모든 API 응답은 `frontend/src/types/` 정의 사용
- API 응답 래퍼: `{ success: bool, data: T, message: str }` (`models/response.py` `ApiResponse`)
- KIS 호출은 반드시 `src/api/base.py` 래퍼 경유 — `kis_get()`·`kis_post()`(메인 단일: 매매·잔고·체결조회) 또는 `kis_get_quote()`·`kis_post_quote()`(시세성 보조 풀) (Rate Limit·재시도·메트릭 — 상세 `src/CLAUDE.md` 「공통 규칙 (전역)」 절)
- TR_ID 는 **실전 값**으로 넘기고 모의 TR_ID 를 하드코딩하지 않는다 — 모의 변환은 `settings.get_tr_id()` 를 `TokenManager.build_headers` 가 모든 요청 헤더에 적용한다(`src/api/CLAUDE.md` 「새 API 추가 절차」 절)
- DB 접근은 `src/db/pg.py` (asyncpg) 네이티브 async — `pg.fetch`/`pg.execute` 경유. JSONB=raw dict 바인딩(codec) / TIMESTAMPTZ 쓰기=`datetime.fromisoformat(now_kst_iso())`·읽기=`to_char(...,'+09:00')` / DATE=`_kst.to_date()` 강제 (상세 `src/db/CLAUDE.md`)

## DB 스키마 (AWS RDS PostgreSQL)

마이그레이션: `supabase/migrations/` (디렉토리명은 supabase/ 유지 — 스키마 SQL 정본, RDS 에 순차 적용). 테이블별 컬럼·키·계약의 정본 = `src/db/CLAUDE.md` 모듈 절.

| 테이블 | 용도 |
|--------|------|
| `trade_history` | 거래 내역 (status: PENDING/COMPLETED/PARTIAL/CANCELLED) |
| `daily_performance` | 일일 실적 (date+strategy 복합PK, TWR 누적, 실현손익 기준) |
| `positions` | 보유 포지션 영속화 (ticker PK) |
| `pending_next_day_clear` | 익일청산 큐 영속화 (migration 038) — 재기동이 메모리 `_pending_next_day_clear` 를 잃지 않게 한다 |
| `strategy_config` | 전략 설정 (strategy_id PK, params JSONB) |
| `system_config` | 시스템 설정 키-값 (auto_start, cash_usage_ratio, 외부 연동 토글, 킬스위치 등) |
| `system_logs` | 시스템 로그 |
| `parameter_recommendations` | 20:00 AI자문 (target_date+strategy_id UNIQUE) — 권고 파라미터·비중·백테스트 요약 |
| `daily_log_reports` | 21:30 일일 로그 분석 + 20:05 metrics 1차 스냅샷 (target_date UNIQUE, 같은 행을 upsert) |
| `stock_master` | KIS CTPF1002R 캐시 (ticker PK, 24h TTL) + KIS 일일 마스터 파일 `master_raw` JSONB. NXT 거래가능 사전 판별. **raw 는 읽기만 한다**(AST G-AST1) |
| `stock_master_history` | `stock_master` 직전본 (migration 032·036, PK `(ticker, seq)` — 트리거가 쓴다) |
| `stock_master_daily` | KIS 일봉 정규화 (migration 033, PK `(ticker, bas_dd)`). 매일 20:30 KST 적재. 🔴 **20:30 에 쓴 그날 봉의 종가·고가·저가는 잠정이다** — 다음 거래일 아침 부팅이 prepare 직전에 `daily_bar_finalize` 로 확정한다. 적재 대상·깊이·retention = `src/engine/CLAUDE.md` 「저녁 데이터 적재 (scanner + data_load_tasks)」 절 |
| `stock_master_financial` | KIS 재무 5 TR 정규화 (migration 041). 주1회 16:40 적재, 매매 hot path 무관 |
| `llm_buy_evaluations` | AI 매수평가(LLM shadow)를 주문을 낼 때 기록 (migration 043, 주문 1건 = 1행). 열 정의 = `src/db/CLAUDE.md` 「llm_buy_evaluations.py — AI 매수평가 기록」 절 |
| `backtest_runs` | 외부 MCP 백테스트 영속화 (`(target_date, strategy_id, params_kind)` UNIQUE) |
| `market_regime_snapshots` | 매크로 레짐 일일 스냅샷 (출처 = 우리 `macro` 컨테이너, `_boot()` 시점 1행) |
| `kis_quote_accounts` | 보조 KIS 시세 수신 계좌 (UUID PK, label UNIQUE) |
| `strategy_funnel_snapshots` | 전략별 조건검색 단계별 후보/탈락 종목 (`(target_date, strategy_id, step_no)` UNIQUE). 잠정 쓰기는 확정 행을 덮지 못한다 |

> **`stock_master` / `stock_master_daily` UI 동기화 의무**: `stock_master` 컬럼 / `raw` JSONB 키 / `stock_master_daily` 컬럼을 추가하면 UI 에 노출한다. 절차 = `frontend/CLAUDE.md` 「(6) 신규 데이터 추가 시 UI 동기화 절차 (영구 가드)」 절.

## Docker / 배포

- `Dockerfile` / `frontend/Dockerfile` 멀티스테이지 (dev: hot-reload / prod: non-root + Nginx)
- `docker-compose.yml` (개발 hot-reload) / `docker-compose.prod.yml` (prod)
- **토큰 캐시 영속화**: `./.token_cache:/app/.token_cache` 디렉토리 볼륨(양쪽 compose 동일) — KIS `/oauth2/tokenP` 분당 1개 한도라 재기동 뒤에도 24h 토큰을 재사용한다. `.gitignore` 등록(`.token_cache/` + 구 `.token_cache_quote_*.json`). 구 경로 `.token_cache.json` 은 자동 마이그레이션
- **`.token_cache` 빌드 시점 권한 보장**: `Dockerfile` prod 스테이지가 `mkdir -p /app/.token_cache` → `chown -R appuser:appuser /app` → `USER appuser` 순서를 지킨다(호스트 bind mount 가 root:root 면 `appuser` 쓰기 거부 — 가드 `tests/integration/test_dockerfile_token_cache_perms.py`)
- `frontend/nginx.conf.template`: 정적파일 + `/api` → backend:8000 프록시 + **사이트 전체 Basic Auth**(cycle243). `nginx:alpine` 엔트리포인트가 `/etc/nginx/templates/*.template` → `/etc/nginx/conf.d/` 로 envsubst 렌더한다(`NGINX_ENVSUBST_FILTER=^API_(AUTH|REPORTER)_KEY$` — 치환 변수 2개). http 컨텍스트(server 블록 밖·앞)의 `map $remote_user $api_key_for_user { default "${API_AUTH_KEY}"; reporter "${API_REPORTER_KEY}"; }` 가 Basic 사용자별 키를 고르고 `location /api/` 가 `proxy_set_header X-API-Key $api_key_for_user;` 로 주입한다(치환 구문은 `map` 블록 안에만). 자격 파일 = 호스트 `./secrets/.htpasswd`(**git 커밋 금지**, 권한 `755 secrets` + `644` — 600·700 이면 전면 500). 🔴 `auth_basic off;` 를 두 템플릿(`nginx.conf.template`·TLS 의 `nginx.tls.conf.template`)에 쓰지 않는다 — 한 줄로 Basic Auth 와 X-API-Key 주입이 함께 뚫린다(AST 가드 D-1-b · TLS 사본 = `test_cycle255_tls_assets.py`). 구 `frontend/nginx.conf` 를 되살리지 않는다(인증 없는 구버전 fail-open). 자격 파일 작성·결손 진단(401/403/500) = `README.md` 「배포 전 호스트 준비 (하드 게이트)」 절
- 타임존 `TZ=Asia/Seoul`. vite 프록시 타겟 분기 = `frontend/CLAUDE.md` 「실행」 절
- **EC2 t4g.small (ARM, ap-northeast-2)** 서비스 경로 `~/auto_stock/`
- 자동 배포: `git push origin main` → GitHub Actions 가 EC2 SSH → `git pull` + **선택적 재빌드**(`.github/workflows/deploy.yml` → `tools/deploy/compose_up_changed.sh`). backend 가 재생성될 때만 push → pool_start 지연 1~5분. deploy.yml 은 `supabase/migrations/*.sql` 을 EC2 psql 로 순차 적용한다(graceful skip). GitHub Secrets = `EC2_HOST`·`EC2_USERNAME`·`EC2_SSH_KEY`·`SUPABASE_DB_URL`(**이름은 유지하되 값이 RDS DSN**)
- CI (`.github/workflows/ci.yml`): `postgres:15` service 컨테이너 + `DATABASE_URL_TEST` 로 통합 테스트 실행 (`tests/integration/pg_harness.py` 가 migration 001~043 적용)
- **로컬과 EC2 동시 실행 금지** — KIS 동일 계정 동시 접속 충돌
- **선택적 배포 (cycle248)** — `tools/deploy/compose_up_changed.sh` 가 마커 `.deployed_sha`(마지막 성공 배포 SHA, git 밖)와 HEAD 의 누적 diff 로 **full**(`up --build` = **backend 재시작**) / **선택 배포**(`frontend` · `macro` · `frontend+macro` — `--no-deps`, backend 무접촉) / **none**(빌드 없는 `up -d`) 중 하나를 고른다. 판정 불가(마커 없음·미지 SHA·diff 실패)는 전부 **full**(fail-safe)이고, backend 히트가 하나라도 있으면 full 이라 **backend 가 선택 목록에 들어갈 길은 없다**. 마커는 compose 성공 뒤에만 쓴다. 분류 근거 = 루트 Dockerfile COPY 소스가 `requirements.txt`·`src/` 뿐이라는 사실(가드 D-8 · `test_cycle248_deploy_pipeline.py::G-248-2` 가 COPY 소스 ↔ 정규식 정합 강제). 모드별 경로 표 = `README.md` 「선택적 배포 (cycle248)」 절
- ⚠️ 배포 모드 함정 넷: (a) `**.md`·`docs/**`·`_workspace/**` 만 바꾼 push 는 CI `paths-ignore` 로 **CI/Deploy 자체가 뜨지 않는다**(마커는 다음 배포의 누적 diff 가 따라잡는다) (b) `src/` 안 `.md` 는 `IMAGE_EXCLUDED_RE='^src/.*\.md$'`(`tools/deploy/compose_up_changed.sh`)가 backend 히트에서 덜어내 full 이 아니다(정합 가드 `tests/unit/ast/test_cycle322_image_excluded_paths.py`) — 🔴 `.*\.md$` 로 넓히지 않는다(`tools/deploy/` 축이 흔들린다) (c) `.env` 는 git 밖이라 스크립트가 못 본다 — 손댄 뒤 운영자가 `docker compose up -d` 로 재생성하고 **마커는 건드리지 않는다**(마커는 git SHA 의 배포 상태만 뜻한다) (d) none 모드의 `up -d` 도 구성이 어긋나 있으면 재생성한다(none ≠ 무조건 무재시작)
- EC2 에서 git 을 손으로 움직였거나(reset/checkout/revert/stash) 수동 `docker compose build|up --build` 를 했으면 **`rm ~/auto_stock/.deployed_sha`** — 마커는 git SHA 의 배포 상태만 뜻하고 실행 중 이미지와 대조하지 않는다. push **전에** 모드를 아는 길은 로컬 `git diff --name-only <EC2 .deployed_sha 값> HEAD` 하나다 — EC2 `DEPLOY_DRY_RUN=1` 은 이미 pull 된 HEAD 만 본다. 경로 표·dry-run·`.deployed_sha.attempt` = `README.md` 「선택적 배포 (cycle248)」·「수동 배포」 절
- **TLS — `auto.dkstock.cloud` 2단계 가동 중**. 80 은 **301** 로 https 로, 443 은 Basic Auth + HSTS `max-age=86400`(includeSubDomains·preload 없음). ACME HTTP-01 챌린지 location(`^~ /.well-known/acme-challenge/`, `satisfy any; allow all; root /var/www/certbot;`)만 301 밖이다. 스위치 = 호스트 마커 `.tls_enabled`(1단계 — `docker-compose.tls.yml` + `frontend/nginx.tls.conf.template`) · `.tls_stage2`(2단계 — `docker-compose.tls2.yml` 이 `tools/ops/tls_stage2/` 스니펫 마운트). 마커는 `-f` 오버레이만 덧붙이고 **배포 모드 판정에 개입하지 않는다**(개입하면 모든 배포가 backend 재시작이 된다). 인증서 갱신은 `certonly --deploy-hook` 으로 renewal conf 에 영속돼 snap/apt timer 가 돌린다 — **crontab 을 두지 않는다**(ubuntu crontab 은 `/etc/letsencrypt` 를 쓸 수 없다). 🔴 **TLS 템플릿에 `map` 을 중복 정의하지 않는다** — nginx 가 정상 기동한 채 뒤 map 이 이겨 전 사용자의 `X-API-Key` 가 빈 값(무증상 backend 전면 401)이 된다. 텍스트 가드 G-255-2f 가 유일한 방어다. 켜고 끄기(`tools/ops/tls_enable.sh`·`tls_stage2_enable.sh`, 검증 실패 시 스스로 원복)·Basic 자격 회전(`tools/ops/rotate_basic_auth.sh` — 새 값으로 클라우드 루틴 `REPORTER_BASIC_PASSWORD` 와 브라우저 로그인을 갱신해야 끝난다) = `README.md` 「TLS (HTTPS)」 절
- ⚠️ EC2 사전 생성 규약: `~/auto_stock/secrets/` 와 `~/auto_stock/certbot-www/` 는 **사람이 먼저 만든다** — compose bind mount 가 먼저 만들면 root:root 라 `ubuntu` 가 쓸 수 없다(절차 = `README.md` 「배포 전 호스트 준비 (하드 게이트)」 절)
- **프로세스 분리 1단계 = `llm_worker` 컨테이너**(AI 매수평가 분리, 큐 = `llm_buy_evaluations` 테이블). **아직 코드가 없다.** 착수 시 제약 둘 — (a) `docker-compose.prod.yml` **본체**에 정의한다(오버레이에만 두면 `--remove-orphans` 가 워커를 지운다) (b) 워커 코드를 `src/` 아래 두면 워커 전용 변경도 `full` 이 되어 backend 가 재시작된다(`BACKEND_RE`). 근거·2~4단계 = [`docs/architecture.md`](docs/architecture.md) 15장
- 운영 가이드 — **보유 포지션이 있으면 KRX 메인 시간(09:00~15:30) push(=EC2 자동 배포) 금지**(cycle232 D6) — 재시작 1~5분 tick blind 동안 손절 사각 + `_scan_loop` 5분 race. 보유 0이면 빈번한 push 자제 수준. **20:00~21:35 도 피한다**(cycle283 D8 — 20:00 AI 자문 · 20:05 metrics 1차 스냅샷 · 20:30 일봉 적재 · 21:30 정산/`_reset_daily_state`) — 그 창의 재기동은 `TIME_SESSION_START_CUTOFF`(20:00)에 막혀 **재기동 시점 이후의** 저녁 블록 전체(`_settle()` · 일일 로그 분석 · 로그 retention 포함)를 잃는다(다음 아침 `[daily_head_stale]` WARNING · 복구 3종 = `src/routes/CLAUDE.md` 의 `/api/trading/restart` 행). **16:00~20:00 KRX 애프터마켓**과 **08:00~08:50 NXT 프리장**도 실매매 구간이다. 즉 장외 배포 창은 **15:30~16:00 · 21:35~익일 07:45** 와 주말·공휴일이다. 이 금지는 backend 가 재생성되는 push(full)에만 실질 적용되지만, **모드가 불확실하면 full 로 간주**한다(`tools/deploy/`·`deploy.yml` 이 섞인 커밋은 항상 full)

## 디렉토리 역할
- `src/auth/` — KIS OAuth 인증/토큰 (메인 + 보조 multi)
- `src/api/` — KIS REST (주문·잔고·조건검색·일봉) + 시세 풀 (`base.py::_request_via_quote_pool` + path 화이트리스트 가드). `quotation.py::inquire_ccnl` = stale universe 가드용 체결 조회(`src/api/CLAUDE.md` 「quotation.py — 주식현재가 체결」)
- `src/realtime/` — KIS WebSocket (시세·체결통보·H0NXMKO0) + WebsocketPool 멀티 세션 분배
- `src/engine/` — 매매 핵심 (전략·레지스트리·주문·리스크·스케줄러). `recommendation_engine.py` 20:00 AI자문 / `log_analysis_engine.py` 21:30 일일 분석 / `daily_metrics_snapshot.py` 20:05 metrics 1차 스냅샷 / `backtest_engine.py` + `backtest_yaml.py` / `market_regime.py`
- `src/engine/strategies/` — 7 전략 명세 (전용 CLAUDE.md)
- `src/services/` — 서비스 클라이언트(`mcp_client.py` 백테스트 MCP · `macro_client.py` 우리 `macro` 컨테이너, 인증 없음 · `quote_session_health.py` 보조 세션 health · `exceptions.py`). 전용 CLAUDE.md 없음 — 목록 정본 = `src/CLAUDE.md` 「진입점」 절
- `src/db/` — PostgreSQL(asyncpg) CRUD. 전 모듈이 `src/db/pg.py` 풀을 쓴다 (`supabase.py` 는 롤백용 병존, 런타임 미참조)
- `src/middleware/` — API 인증(`X-API-Key`)·리포터 스코프 최외곽 미들웨어 (전용 CLAUDE.md 없음 — `src/CLAUDE.md` 「진입점」 절)
- `src/routes/` — FastAPI 엔드포인트
- `src/models/` — Pydantic 모델
- `src/workers/` — 워커 진입점이 들어올 자리. **아직 없다.** 계획 = [`docs/architecture.md`](docs/architecture.md) 15.2 · 15.5
- `frontend/` — React 대시보드
- `macro/` — **매크로 API 별도 컨테이너**(5섹션 = `GET /api/macro/*`, 자체 `Dockerfile`·`requirements.txt`·`main.py`). **`src/` 아래로 옮기지 않는다** — 옮기면 macro 변경마다 매매 backend 가 재시작된다. `macro/macro_lite/` 는 **무수정 vendor**(재이식 시 통째로 덮어쓴다). 캐시 `MACRO_LITE_CACHE_DIR` 는 영속 bind mount 필수(유실 시 하이일드 **차트**의 10년·5년 구간이 3년으로 영구 퇴행). 매매 레짐의 출처이기도 하다(cycle315, `src/services/macro_client.py` — 관찰 지표). 운영 가이드 = [`docs/macro-lite.md`](docs/macro-lite.md)
