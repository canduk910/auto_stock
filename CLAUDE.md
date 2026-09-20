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
- **문서 동기화 → `/sync-docs` 명령 (Phase 4.8, 코드 변경 사이클은 커밋 전 필수)** — 코드 위치 → 갱신 후보 문서
  매핑 표 + **대상 문서 정본 목록** + 모듈 누락 자가 점검을 담은 유일한 체크리스트다.
  ⚠️ 전용 `CLAUDE.md` 가 없는 `src/services/` · `src/middleware/` · `tools/` · `e2e/` 가 누락 반복 지점
  **실행 주체 = `report-writer` 에이전트**(2026-09-11 사용자 결정) — 메인 세션은 꾸러미만 만들어 위임하고
  커밋 여부만 정한다. 쉬운 말로 유지하되 식별자·상수·불변식·금기 조건은 인용 대상이라 흐리지 않는다.
- KIS API 정본 스펙 (TR_ID·응답 구조·거부 코드) → `kis-mcp-query` 스킬 (backend-dev / tdd-engineer / tester / refactor-expert 공유)
- **⚠️ KIS 스펙의 시간 경계 — `docs/kis/*.md` 는 2026-09-11 03:00 워크북 스냅샷이라 「변경 전」 세계를 기술한다.** 거기엔 시간외 단일가(16:00~18:00)가 살아 있고 `H0STOUP0` 가 현역으로 적혀 있다. **2026-09-14 시행 제도 변경(KRX 애프터마켓 16:00~20:00 신설·시간외 단일가 폐지·시가단일가 08:20 확대·KRX 정규장 미체결 자동취소)은 세 곳에 나눠 적혀 있다** — 제도·시간표·보드 영향 = [`src/engine/CLAUDE.md`](src/engine/CLAUDE.md) `session.py` 절 · TR·필드 변경 = [`docs/kis/README.md`](docs/kis/README.md) 「제도 변경 공지 반영」 절(+ 각 필드 자리에 직접 반영, `docs/kis` 재생성 시 그 절을 보고 다시 넣는다) · 우리 할 일·실측 목록 = [`_workspace/00_URGENT_WORKLIST.md`](_workspace/00_URGENT_WORKLIST.md). 09-14 이후의 사실을 `docs/kis/` 에서만 찾으면 틀린 답이 나온다(실증: cycle280 자문이 이 함정에 빠져 존재하지 않는 「저녁 시세 공백」 CRITICAL 을 냈다). 순서 = 위 세 곳 → `kis-mcp-query` → `docs/kis/*.md` 본문
- **외부 검색 → `insane-search` 스킬 (2026-09-11 사용자 지시)** — 리포 밖 정보를 찾을 때 `WebFetch` 로
  시작하지 않는다. 402·403·차단 응답, 스크립트로 그려져 껍데기만 오는 페이지, X·레딧·유튜브·깃헙
  검색·네이버 등 봇 차단이 있는 곳이 대상이다. 단순 검색은 `WebSearch`, KIS 스펙은 `docs/kis/*.md`
  와 `kis-mcp-query` 가 먼저다. **모든 에이전트에 같은 규칙이 적힌다**

**우회 허용 (메인 세션 직접 응답):** 단순 사실 질의, 단발 디버그/grep, 운영 환경 즉시 점검(EC2 SSH 등). 코드 변경 제안이 따라오면 다시 team-leader 로 인계.

### 모델 라우팅

| 작업 유형 | 모델 | 적용 |
|----------|------|------|
| 구현 계획·검수·리팩토링 검토·마무리 보고서 | **opus** | `team-leader`, `tester`, `refactor-expert`, `report-writer` — ⚠️ **모델은 에이전트 정의에 명시한다.** 지정을 지우면 상속이 Fable 로 해석돼 그 모델의 크레딧이 마르면 넷이 한꺼번에 막힌다. 세션 모델이 바뀌면 이 네 줄도 같이 바꾼다 |
| 테스트 설계·도메인 자문 | **opus** | `domain-expert`, `tdd-engineer` |
| 일반 구현 (코드 작성·리팩터·버그 수정) | **sonnet** | `backend-dev`, `frontend-dev` |
| 명령어 작성 (bash/슬래시/스크립트) | **haiku** | 메인 세션 단발 작업 — fork 또는 `claude-haiku-4-5-20251001` 위임 |

### 자율 진행과 승인 빈도 (2026-09-05 사용자 결정)

**승인은 결정 지점에서만 묻는다.** **자율 진행 구간**은 사용자가 (a) 구간의 끝(시각 또는 할 일 목록)과 (b) 커밋·배포 허용 여부를 **명시**했을 때만 성립한다(예: "06:30까지 승인 없이 진행, 커밋은 작업 단위로"). "진행해" 한마디는 그 작업의 구현·검증까지의 승인이며, 커밋·push 는 별도로 묻는다(메모리 "커밋은 명시 지시 시에만" 정책의 유일한 예외가 명시된 자율 구간이다). 구간 안에서는 사전 승인 범위(아래) 에 한해 구현 → 검증 → 커밋(작업 단위) → 배포 → 실측 확인까지 사이클마다 다시 묻지 않고 이어서 진행하고, 구간의 끝에 `cycle-report` 스킬로 **한 번** 보고한다(쉬운 말 아티팩트 + 원문 md + 결정 카드). 보고서의 "결정해 주세요" 카드가 그동안 미룬 승인 요청을 **모아** 전달한다 — 보고서가 승인을 대신하지는 않는다.

- **8영역** = `src/engine/{risk,order_engine,session,scanner,strategy_registry}.py` · `src/api/order.py` · `src/realtime/**` · `src/auth/**` (정본 목록 = `tests/unit/ast/test_cycle222a3_ast_followup_fixes.py::_EIGHT_AREAS`, 승인 시 그 파일의 sha 핀 절차를 따른다). `scheduler.py` 는 8영역은 아니지만 **라인 상한 `<3,900L`**(cycle257 이 세운 영구 상한) 때문에 같은 승인 대상이다 — 여러 AST 가드가 이 상한을 복창하며, **두 수가 갈라지면 항상 더 조인 쪽이 정본이다**.
- **사전 승인 범위** (아래 셋을 **모두** 만족할 때만): (a) 8영역·`scheduler.py` 무접촉 — 8영역 안이면 관측 로그 한 줄도 승인 (b) 배포는 운영 가이드의 장외 창 안 — **15:30~16:00 · 21:35~익일 07:45**(backend 재생성 1~5분 여유) · 주말·공휴일 종일. **20:00~21:35 는 자율 구간 중에도 push 금지**(cycle283 D8 — 20:00 자문·20:05 metrics 1차 스냅샷·20:30 일봉 적재·21:30 정산/`_reset_daily_state` 가 재시작에 끊긴다. 게다가 그 창의 재기동은 `TIME_SESSION_START_CUTOFF`(20:00) 때문에 **거부**되므로 그날 20:30 일봉 적재를 통째로 잃는다). 모드 판정이 불확실하면 full(재시작)로 간주(cycle248) (c) 다음 커밋으로 원복 가능. 테스트·문서·관측 전용 변경도 (a) 를 만족할 때만 포함. DB 스키마는 가산형 마이그레이션(NULL 허용 ADD COLUMN·INDEX·신규 테이블)만 포함.
- **여전히 승인이 필요한 것(구간 중에도 멈추고 묻는다 — 위 범위와 충돌하면 이 목록이 항상 우선)** = 8영역·`scheduler.py` 변경 · 보유 중 장중 push(D6) · 기능·설정 비활성화(심층 검증 의무) · 되돌리기 어려운 운영 조치(DB UPDATE/DELETE·DROP·타입 변경·NOT NULL 백필, 수동 매매, 키 회전, 구독·세션 강제 조작) · 사용자 결정 항목(비중·파라미터 값·전략 on/off·자금 **+ 매매 행위를 바꾸는 코드 변경 — 진입·청산·수량·사이징·손절 규약·`DEFAULT_PARAMS` 신규 키 — 는 파일 위치와 무관하게 승인 + `domain-consult` 선행**) · 외부로 나가는 조치(메일·PR 머지·루틴(schedule) 생성/변경·Notion 쓰기·외부 서비스 설정). 단, **이미 승인된 사이클 명세에 포함된** 외부 설정·배포 전 DB 선반영(예: cycle245 §7.1 K=20 선반영)은 그 승인에 포함된 것으로 보되, 실행 전후 값을 보고서 "서버에 올린 것" 표에 남긴다.
- **보고 시점** = `cycle-report` 스킬 정본의 트리거 4 (① 사이클 3회 이상 연속 완료 ② 자율 진행 구간(주·야간 무관) 종료 ③ 사용자의 "리포트/보고서/정리해 줘" 요청 ④ 세션 종료 전 사용자가 못 본 배포·결정 누적). 사이클 1~2회라도 결정 항목 3개 이상이면 호출. 그 밖에는 터미널 요약으로 충분하다.
- **보고서 기준** = `.claude/agents/report-writer.md` 의 구조·쓰기 규칙(용어 풀이 → 한눈에 → 시간순 → 발견 → 결정 카드 → 확인 목록 → 승인 시 할 일 → 함께 만든 것·배운 점 → 바닥글). 사실은 정본(git·changelog·워크리스트·호출자 검증 결과·포렌식/자문 문서)에서만, 예상과 실측 구분, 커밋 해시는 바닥글에만. report-writer 는 커밋·push 를 하지 않는다(메인 세션이 커밋 정책에 따라 결정). 기준 예시 = `.claude/skills/cycle-report/example_2026-09-05.html` + 원문 `_workspace/reports/2026-09-05_night_autonomous_work.md`.

### 병렬 작업 — 같은 작업 디렉터리는 git 이 지켜 주지 않는다

동시에 여러 에이전트를 띄울 때, **파일을 쓰는 에이전트**는 서로의 편집을 덮어쓸 수 있다. git 이 지키는 것은 **커밋된 것**이고 커밋 전 편집본끼리는 나중에 쓴 쪽이 이긴다. 2026-09-19 실측 사고 = 동시 작업이 `src/routes/market_regime.py` 의 내용을 `src/engine/market_regime.py` 에 써서 750줄 매매 모듈이 123줄 라우트 사본이 됐다.

- **쓰는 에이전트를 동시에 띄우면 `isolation: "worktree"`** — 읽기만 하는 에이전트(조사·검토·렌즈)는 그대로 둔다. 격리는 에이전트당 디스크와 준비 시간을 쓰므로 쓰기가 실제로 겹칠 때만이다.
- **띄우기 전에 `git add -A`** — 그러면 덮어써도 `git checkout -- <path>` 한 줄로 돌아온다(그 사고의 실제 복구 경로다). 커밋이 아니라 인덱스 스냅샷이라 커밋 정책과 무관하다.
- ⚠️ **워크트리를 공유하는 중에는 `git checkout -- <path>` 를 함부로 쓰지 않는다** — 다른 작업이 그 파일에 쓰고 있으면 그쪽 편집이 사라진다.
- 자동 덫 = `tests/unit/deploy/test_cycle319_no_clobbered_module.py` (`src/` 안에 내용이 같은 파일 쌍 = 0). 덮어쓰기는 거의 항상 **다른 파일의 사본**이라 이것으로 잡힌다. 부분 덮어쓰기는 못 잡으므로 위 두 습관이 본체다.

### 하네스 변경 이력

사이클별 변경 이력은 [`docs/HARNESS_CHANGELOG.md`](docs/HARNESS_CHANGELOG.md) 가 **유일한 정본**이다(상단이 최신).
이 문서에는 이력표를 두지 않는다 — 규약은 위 「문서 규약」 절.

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
- `SUPABASE_URL`, `SUPABASE_KEY`: **런타임 미사용이지만 설정은 필수다.** 어느 db 모듈도 참조하지 않고
  (`src/db/supabase.py` 는 롤백용 병존) 값이 무엇이든 동작에 영향이 없지만, `src/config.py:36-37` 의
  `supabase_url: str` / `supabase_key: str` 가 **기본값 없는 필수 필드**라 비우거나 빼면 pydantic 검증에
  걸려 **기동 자체가 실패한다**. 새 환경을 만들 때 "미사용이니 비워도 된다" 로 읽으면 안 된다
- `AUTO_START`: 서버 기동 시 자동 매매 시작 (DB `system_config.auto_start` 우선, 매일 시작 전 재확인)
- `API_AUTH_KEY` (cycle243): 백엔드 `X-API-Key` 인증 키. **미설정이면 fail-closed** — `/health` 를 뺀 전 경로 401 + 기동 시 `[api_auth_key_missing]` CRITICAL. 조용히 끄지 않는다(fail-open 은 "키가 없으면 인증이 사라진다" = 이 결함의 재현). 생성 `python3 -c "import secrets;print(secrets.token_urlsafe(32))"`. 운영에서는 nginx 가 프록시 요청에 주입해 브라우저에 노출되지 않는다. 키 회전은 frontend·backend **동시 재시작**이 필요하므로 장 종료 후에만
- `API_ALLOWED_ORIGINS` (cycle243, 기본 빈 값): 교차 출처 허용 목록(CSV). CORS `allow_origins` 와 상태변경(POST/PUT/PATCH/DELETE) Origin 검사가 이 값 하나를 공유한다. 빈 값 = same-origin 전용(prod). dev 는 vite `changeOrigin` 때문에 `http://localhost:3000` 명시
- `API_REPORTER_KEY` (cycle249, 기본 빈 값 = 리포터 역할 비활성): 리포터 스코프 키 — 허용 범위는 **GET/HEAD 전체 + `POST /api/log-reports/{date}/external` 단 한 경로**뿐이다(20:20 KST 클라우드 루틴이 로그 번들을 읽고 분석 결과를 쓰는 유일한 창구). nginx `map $remote_user` 가 Basic 사용자 `reporter` 에게만 이 값을 주입한다(운영 키를 보내는 `default` 사용자와 다른 값이어야 판정이 성립). 미설정이면 어떤 요청도 리포터로 통과하지 못한다(fail-closed)
- `DKSTOCK_REGIME_ENABLED` (기본 false): 매크로 레짐 수신 + cash_usage_ratio 자동 조정 활성화 (레짐은 관찰 전용 — 매수를 차단하지 않는다). 출처는 **우리 `macro` 컨테이너**(`MACRO_API_URL`, 기본 `http://macro:8000`)다. 🔴 **변수명은 유지한다** — 운영 DB `system_config.dkstock_regime_enabled` 행과 짝이고, 개명하면 그 행이 고아가 된다. 판정은 **DB 우선 / `.env` fallback** 이다(`services/macro_client.py`). 상한 = `MACRO_API_READ_TIMEOUT_SECS`(90초) · 부팅 전용 `MACRO_API_BOOT_TIMEOUT_SECS`(25초)
- `KIS_MCP_ENABLED` (기본 false): 외부 백테스트 MCP 서버 활성화. 자문 직후 활성 전략마다 2 job(`params_kind` = current|recommended) fire-and-forget

## 다중 전략 (요약)

7 전략: `momentum` / `volatility_breakout` / `long_tail_volatility` / `donchian_swing` / `bull_flag_breakout` / `vcp_breakout` / `kojiro`(고지로 대순환 스윙 — 운영 DB `strategy_config.enabled=True` 로 실매매 중, 코드 등록 기본값만 `enabled=False`).

상세 매수/청산/tradable_boards/exchange 는 **`src/engine/strategies/CLAUDE.md`** 참조.

### 새 전략 추가
1. `src/engine/strategies/` 에 `StrategyBase` 서브클래스 (`prepare/check_buy_signal/check_exit_signal/calc_buy_quantity`)
2. `src/engine/scheduler.py` `__init__` 에서 `registry.register()`
3. 필요 시 `scanner.py` 에 스캔 함수 추가
4. `strategies/CLAUDE.md` 표 + `_workspace/00_leader_trading_rules.md` 명세 추가

### 자금 관리
- 프론트 Settings → `PUT /api/strategies/weights` → `StrategyRegistry.allocate_funds()`
- **전략 비중 단위 = 비율 `0.0~1.0` (2026-08-18 확정)** — `PUT /api/strategies/weights` 요청 바디 · `GET /api/strategies` 응답 `weight` · `strategy_config.weight` 컬럼 · AI 자문 `save_weights` 경로가 **모두 같은 단위**라 GET↔PUT 왕복이 항등이다. 라우트가 범위 위반은 422, Σ>1.0 payload 는 `success=false`(저장 미수행)로 거부하고, 부팅 시 `_load_strategy_config` 가 **레지스트리 등록 전략 행**의 개별 `weight > 1.0` 또는 Σ `> 1.001` 을 `[weight_config_anomaly]` WARNING 으로 관찰만 한다 — **자동 클램프·정규화 금지**(오염 값을 조용히 그럴듯하게 만들면 운영자가 실측할 근거가 사라진다), fail-open
- `position_ratio` 는 **전략 할당 자금 기준** — 정확한 식은 `순자산 × cash_usage_ratio × (weight / Σweight_enabled) × position_ratio` = 종목당 매수금액. `allocate_funds` 가 **Σ 로 정규화**하므로 Σ≠1 이어도 자산 전액이 배분된다
- **전략별 투자한도 — 삼중** — ① 개수 `max_positions` + ② 명목 `Σ매수금액 ≤ total_investment` + ③ **리스크 `Σ오픈리스크 ≤ max_open_risk_pct × 예산`**(kojiro 한정). 터틀의 유닛 캡이 통제하려던 값은 ③이고 유닛 **개수는 프록시**일 뿐 — 수량 절삭·`hard_stop_pct` 캡·사이징 혼재로 프록시가 헐거워진다. **개수 캡을 리스크 캡으로 대체 금지**(저ATR 종목 포지션 수 폭증). ②는 `StrategyBase._apply_budget_limit` 공통 관문이 7 전략 `calc_buy_quantity` 의 모든 return 을 통과시켜 강제하며, 잔여가 부족하면 **부분 매수**(잔여 < 1주 → 0). 불변식 **`position_ratio × max_positions ≤ 1.0`** — DEFAULT_PARAMS 는 AST 가드(C-DEFAULT)가, AI 추천은 `_validate_recommendations` 교차검증이 강제. `max_positions` 는 리스크 정체성 상수라 `PARAM_RANGES`/`INT_PARAMS` **편입 금지**
- **1회 투자금액 ATR 유닛화 (`sizing_mode="turtle"`)** — `unit = floor(전략예산 × risk_pct ÷ ATR)`. **손절이 ATR 기반인 전략에만 적용**한다: 손절이 고정%면 명목이 종목 무관 상수라 `position_ratio` 가 이미 리스크 균등이고, 사이징만 ATR 로 바꾸면 정규화가 깨진다(함정 #1). 현재 배선 = donchian(라이브) · kojiro · VCP/BFB(다크런치, 하드손절 ATR화 동반). momentum/VB/LTV 는 제외 — 제외 사유는 전략마다 다르다: **momentum** = ATR 부재 · **VB** = 당일 15:20 청산 · **LTV** = 상한가 2모드 재설계 선행. ⚠️ VB·LTV 는 prepare 가 이미 일봉을 읽으므로 **ATR 산출 자체는 추가 I/O 0 으로 가능**하다(제외 근거가 데이터 부재가 아니라 함정 #1 이다). `compute_unit_qty_guarded` 의 notional 상한이 `position_ratio × 예산` 이라 **터틀 수량 ≤ 비중 수량**이 항상 성립 = 전환은 순수 축소 방향.
  🔴 **유닛화가 랏 미세화를 풀지 못한다**(2026-09-20 실측) — 정수 절삭은 유닛식에도 똑같이 있어, 유닛을 쓰는 donchian·kojiro 도 매수의 **76%·52%가 1주**다. 랏이 1주 언저리인 원인은 사이징 방식이 아니라 **설계 랏 ÷ 그 전략이 사는 종목의 주가**(= `q`)다. `q` 는 **순자산에 정비례**한다 — 2026-09-20 입금(250만→500만) **전** 실측 = VB **0.37** · LTV **0.55** · donchian 1.35 · momentum 2.17 · BFB 2.83 · kojiro 5.06, **후**(순자산 약 500만) = 각각 **2배**(VB 0.74 · LTV 1.11 · donchian 2.70 · momentum 4.34 · BFB 5.66 · kojiro 10.11). ⚠️ **과거 체결 데이터는 전부 「전」 구간**이다 — 그때 VB 설계 랏은 44,031원인데 중앙 주가가 118,750원이라 **반 주도 못 샀다**. 비중·자금을 손대지 않은 채 유닛만 도입하면 `floor(예산 × risk_pct ÷ ATR) = 0` 이 되어 그 전략이 **전면 무매매**가 된다.
  🔴 **그리고 이것은 자본 부족이 아니라 배분 문제다** — `q ≥ N` 을 요구하면 필요 비중 `w_i = N × P_i × m_i / A` 이고, N=5 에서 **Σ 필요 비중 = 0.97**(체결 있는 6전략, **입금 후 순자산 약 500만 기준**)이라 **입금 후 자본으로는 충분하다**(입금 전 250만 기준이면 Σ 1.94 로 불가능했다). 어긋난 것은 배분이다 — kojiro 는 0.40 을 쥐고 0.197 만 필요한데(랏이 10주라 정밀도가 남는다) VB 는 0.236 이 필요한데 0.05 뿐이다. ⚠️ `q` 계산의 분모는 **중앙 주가**이지 중앙 명목이 아니다(다주 랏이 섞이면 갈라진다 — VB 실측 주가 118,750 vs 명목 150,600)
- **랏당 최대 유닛 상한 `max_lot_units` (K=2.0, cycle242)** — `sizing_mode="turtle"` 전략의 **모든** 매수 랏(터틀 유닛·`position_ratio` 낙하·1주 폴백)을 `floor(K × 예산 × risk_pct ÷ ATR)` 주 이하로 자르고, 그 값이 0 이면 **매수하지 않는다**. **매수를 줄이는 방향뿐**이다(캡은 `min()` 이라 수량을 늘리지 않는다) — 1주 폴백이 `risk_pct` 통제를 진입 시점에 무력화하던 과잉 피라미딩 시정이다. 캡 산출은 `turtle_sizing.compute_unit_qty(budget, atr, risk_pct, fraction=K)` **재사용**(새 수식 금지), ATR 은 터틀 분기와 **같은 소스** `_candidates[ticker]` 를 read-only 로 읽는다. K 는 **리스크 정체성 상수** — `PARAM_RANGES`/`INT_PARAMS` **편입 금지**(AST G-242-1: 런타임 dict + 소스 리터럴 이중), 읽는 쪽 `[1.0, 20.0]` 클램프(**하한 1.0 = 정상 터틀 랏이 캡에 안 걸리는 수학적 전제**, 상한 20.0 = 롤백 다이얼). ATR 결측·모호(`atr`↔`atr14` 상이)·`risk_pct ≤ 0`·예외는 **fail-open**(현행 수량 유지 + `[fallback_cap_skipped]` WARNING) — fail-closed 는 유령 키가 두 전략을 전 기간 체결 0건으로 만든 그 방향이라 금지. ⚠️ **"K유닛 = 예산 2.0% 노출" 은 `_entry_atr` 스탬프 랏(2×ATR 손절) 한정** — 폴백·PR 낙하 랏은 미스탬프라 고정% 손절을 타므로 실효 상한은 `cap_qty × price × |stop_loss_rate|` 다. **고정%손절 5전략**(momentum/VB/LTV + `position_ratio` 모드 VCP/BFB)은 **범위 밖**(position_ratio 가 이미 리스크 균등 — 유닛 캡을 씌우면 정규화 역전, 함정 #1). 피라미딩(사다리 증량) 착수 시 **K→1.0** 으로 조인다(K=2 랏 + 4유닛 사다리 = 8유닛 = R15 재위반). 롤백 = 해당 전략 `max_lot_units = 20.0` — 코드 재배포는 불필요하지만 **반영 시점이 다르다**: `PUT /api/strategies/{id}/params` 는 **즉시**(라우트가 in-memory `config.params` 를 덮는다), `strategy_config` SQL UPDATE 는 **다음 백엔드 재시작에서만**(`_load_strategy_config` 의 `_config_loaded` 가 프로세스당 1회이고 `_boot` 재호출은 no-op) — cycle232 D6 가 보유 중 장중 재시작을 금지하므로 **장중 실효 수단은 PUT 뿐**이다. **그리고 당일 캡→0 으로 `_bought_today` 가 소진된 종목은 어느 수단으로도 다음 세션부터만 되살아난다**(`cap_qty` 는 D-1 ATR 기반 일중 상수)
- **랏 명목 ρ축 상한 `max_lot_ratio_mult` (K_ρ=2.5, cycle245)** — 관문을 지나는 **모든** 랏의 명목을 `K_ρ × position_ratio × 예산` 이하로 자르고, **1주도 못 사면 매수하지 않는다**. 1주 폴백 랏의 크기가 설계가 아니라 **그 종목 주가**로 결정되던 결함 시정이고, **매수를 줄이는 방향뿐**이다(`min` 이라 수량을 늘리지 않는다). 산식 = `cutoff = int(K_ρ × int(예산 × position_ratio))` · `cap_qty = cutoff // 현재가`. **K축이 심사한 랏도 ρ축이 `min` 으로 후심사한다(cycle254)** — `_apply_ratio_notional_cap` 의 조기탈출은 판정 기준 `_lot_units_cap_governs`(= turtle ∧ ticker ∧ `risk_pct>0` ∧ 예산>0 ∧ ATR 해석 성공) **자체가 실패한 경우**(`probe_error`)만 fail-open 으로 남기고, 그 외엔 K축 심사 여부와 무관하게 컷오프를 적용한다. 사이즈드 터틀 랏·`position_ratio` 낙하 랏은 `compute_unit_qty_guarded` 의 notional 상한(`min(qty, int(예산×position_ratio)//price)`)이 명목을 이미 컷오프 이하로 묶어 두므로 `final <= cap_qty` 로 **항등적으로 무접촉**이고, **실효는 1주 폴백 랏뿐**이다. `[ratio_cap_config]` 라벨은 `off|on` 2종이다. **키 부재 = OFF**(`max_lot_units` 관례와 **반대** — 매수를 막는 통제라 "설정이 없으면 막는다"는 유령 키 재현 경로다). 키는 **7 전략 전부**의 `DEFAULT_PARAMS` 에 명시하고 AST 가 glob 전수로 강제한다. K_ρ 는 **리스크 정체성 상수** — `PARAM_RANGES`/`INT_PARAMS` **편입 금지**(AST G-245-1) + AI 자문 자동 적용 경로 편입 금지, 읽는 쪽 `[1.0, 20.0]` 클램프(**하한 1.0 = 정상 비중 랏이 캡에 안 걸리는 수학적 전제** — 1.0 미만은 주 분기까지 잘라 전면 무매매, 상한 20.0 = 롤백 다이얼). `position_ratio` 결측·예산 0·초소액·판정 예외는 전부 **fail-open**(현행 수량 + `[ratio_cap_skipped]` WARNING). 롤백 = 해당 전략 K_ρ=20.0 — **`PUT /api/strategies/{id}/params` 는 즉시, `strategy_config` SQL UPDATE 는 다음 백엔드 재시작에서만** 반영되므로 보유 중 장중 롤백은 PUT 이 유일 경로다(cycle232 D6)
- 전략 간 동일 종목 중복 매수 방지: `registry.is_ticker_blocked_for_buy()` (보유/주문중/당일매도 통합 차단)
- **`cash_usage_ratio`**: `system_config.cash_usage_ratio` 키 — `_boot()` 가 `summary.net_asset × ratio` 로 `allocate_funds()` 호출. 범위 `[0.0, 1.0]`, 5% 단위, 기본 1.0. Settings 슬라이더로 조정 → **다음 영업일부터 반영**. `auto_regime_adjust=true` (기본) + `DKSTOCK_REGIME_ENABLED=true` 시 매크로 레짐 `cash_min` 기반 자동 갱신 (`clamp((100-cash_min)/100, 0.0, 1.0)`)

### 외부 통합 (백테스트 + 매크로 레짐)
- 20:00 AI 자문 INSERT 직후 외부 MCP 백테스트 (`http://43.202.187.5:3846/mcp`) — 활성 전략마다 2 job(`params_kind` = current|recommended) fire-and-forget → `parameter_recommendations.backtest_summary` JSONB
- 매크로 레짐 (**우리 `macro` 컨테이너**, cycle315) — `regime/vix/fear_greed` 관찰 + `cash_usage_ratio` 자동 조정 (`auto_regime_adjust`, `clamp((100-cash_min)/100)`). **레짐은 관찰 지표다 — 매수를 차단·축소하지 않는다**(`buy_block_mode` 는 표시 전용, `get_buy_block_state` 는 대시보드/자문 payload 만 소비). ETF 레짐·포트폴리오 리스크 관찰 활성
- 활성화 토글: `KIS_MCP_ENABLED` / `DKSTOCK_REGIME_ENABLED` / `etf_regime_enabled` (Settings UI 즉시 토글). 외부 다운 시 graceful — 자문 INSERT 보존, summary=null, 레짐 관찰 비활성
- 운영 가이드: [`docs/backtest-monitoring.md`](docs/backtest-monitoring.md)

## 핵심 안전 규칙 (절대 깨지 말 것)

상세 메커니즘은 `src/engine/CLAUDE.md` · `src/realtime/CLAUDE.md` 참조. 여기서는 **금기**만:

- **기능·설정 비활성화(disable / toggle off / dead 판정) 시 심층 검증 의무** — 무언가를 "미사용/dead/낭비"라고 단정하기 **전에 소비처(consumers)를 `grep` 으로 전수 확인**하고, 비활성화 **후에는 그 소비처의 산출물(예: 적재 종목수)을 라이브 실측**으로 확인한다. **비활성화는 "제거"가 아니라 "경로 변경"일 수 있다** — 주 경로를 끄면 폴백 경로가 조용히 degrade 된다. 설정 토글은 CI/Deploy 를 안 타므로 자동 검증도 없다. 실측 없는 비활성화 금지 — 2026-08-08 `krx_open_api_enabled` 를 "무효 키·낭비"로 오판해 끈 결과 주 소스 `scanner._full_universe_load_krx_primary` 가 폴백으로 밀려 `full_universe_load` 가 3,577→60종목으로 degrade 됐고 D+1 에야 발견됐다
- 🔴 **보유 포지션이 있는 전략을 끄지 않는다 — 끄는 순간 그 포지션의 손절이 멈춘다.** `risk.on_tick` 이 `registry.enabled()`(= `config.enabled` 참인 것만) **단일 순회**라, 끈 전략의 보유분은 손절·트레일링·익일청산·15:20 강제청산이 **전부 정지**하고 아무도 보지 않는 채 남는다(`src/engine/risk.py` 의 전략 순회 · `strategy_registry.enabled()`). 끄기 전에 **그 전략 보유 0 을 확인**하거나 먼저 청산한다. `enabled` 축 시정은 미착수이고 `src/engine/CLAUDE.md` 가 「의도적 미시정」으로 적어 둔 상태다. ⚠️ 「전략 수를 줄여 전략당 예산을 키운다」는 처방이 이 함정을 정면으로 밟는다. 두 용도를 구분한다 — **랏을 키우려면** `max_positions`(슬롯)를 줄이고 `position_ratio`(종목당 비율)를 올린다(`position_ratio × max_positions ≤ 1.0` 불변식 유지, **`weight` 는 무접촉**). 🔴 **한 전략을 「보유한 채로」 멈추는 수단은 없다. `weight=0` 은 더 나쁘다** — `registry.update_weights` 가 **`config.enabled = weight > 0` 을 자동 토글**하므로 비중 0 = **즉시 비활성화 = 손절 정지**다(이 금기를 우회하는 길이 아니라 **금기 그 자체를 밟는 길**이다). 게다가 **`PUT /api/strategies/weights` 는 보유 매수금액 비율 미만의 비중을 거부한다**(`routes/strategies.py` 「매수금액 하한선 검증」 — "보유 종목 매도 후 비중을 줄여주세요"). 즉 금기가 겨냥한 바로 그 상황에서 도달 불가다. 지금 할 수 있는 것은 **그 전략 보유를 먼저 비우고** 끄는 것뿐이다. 보유한 채로 신규 유입만 줄이려면 **`position_ratio`·`max_positions`(PUT params — `enabled` 를 건드리지 않고 하한선 검증도 없다)** 를 쓴다. `enabled` 축 시정과 함께 후속 대상
- **체결통보 구독 (H0STCNI0/H0STCNI9) 제거 금지** — 미구독 시 포지션 등록·손절 불가
- **uvicorn 단일 워커 필수** — `--workers` 금지 (스케줄/포지션/WebSocket 중복)
- **주문번호 매핑** (`_order_qty/_order_strategy/_order_ticker/_pending_buy_orders`) 등록은 `place_order` 응답 직후 동기 영역, `await insert_trade` 진입 전 — 시장가 즉시체결 race 시 매핑 누락하면 기본값 "momentum" 으로 잘못 INSERT됨
- **체결통보 선행 race 가드** (`_completed_orders` set + UPDATE 0건 보정 INSERT) 제거 금지 — 시장가 즉시체결 + REST 응답 지연 시 trade_history 가 PENDING 영구 잔존. 그 가드가 못 덮는 두 번째 창(PENDING `insert_trade` 의 `await` 도중 체결통보가 먼저 완주 → 보정 INSERT 가 같은 `(ticker, order_no, trade_type)` 를 선점 → migration 029 부분 UNIQUE 위반으로 `execute_buy` 가 ERROR 종료·`buy_succeeded` 후처리 누락)은 `_insert_pending_buy_or_absorb_race`(cycle271)가 **`_completed_orders` 에 그 주문번호가 있을 때만** `UniqueViolationError` 를 흡수·discard 해서 막는다. 증거 없는 위반은 그대로 전파(다른 원인 은폐 금지) — 무조건 삼키기·`sizing`·재시도 INSERT 로 바꾸지 않는다
- **`_reset_daily_state()` 제거 금지** — 정산 후 미초기화 시 pending_buys/positions/sold_today 가 다음 날까지 잔류
- **익일 청산** 은 scheduler 에서 시가 수신 후 30s 안정화 처리 — `_pending_next_day_clear` 보류 후 09:00 KRX 시장가. `high_since_buy` 폴백 금지. on_tick 즉시 청산 금지
- **NXT 매도 거부 좀비 차단** — `is_market_closed_rejection` (APBK0918 + 장운영시간 외) 이면 `execute_sell` 이 positions(메모리/DB) 보존 + `_selling` **discard** (진입 게이트 `SellRejectionTracker.is_blocked()` 가 이후 차단 담당 — `_selling` 을 보존하면 그게 곧 stale `_selling` 좀비=손절 마비이므로 반드시 해제) + 재시도 중단. `is_insufficient_quantity` / `is_insufficient_cash` 와 분리. `SellRejectionTracker.is_blocked()` 진입 게이트는 **2단계 TTL** — KRX 메인(09:00~15:30) 거부 = 5분 TTL (일시 장애 가정), NXT 시간대(08:00~09:00 / 15:30~20:00) 거부 = 다음 KST 09:00 TTL. `market_order_disallowed` 거부 = 30초 TTL (동일 tick 폭주 차단). NXT 폴백 실패 시 `_pending_next_day_clear` 익일 청산 자동 전환. `_reset_daily_state` 동행 clear (`_sell_rejection.reset_daily()` 4 필드 일괄 위임, `OrderEngine.reset_daily_state()` 캡슐화 보존). 호환 layer property `_market_closed_blocked` / `_market_closed_blocked_logged_today` 는 tracker 내부 dict/set 직접 노출 (is 동일성 보장)
- **매수/매도 시장가 거부 → 지정가 5호가 폴백 1회** — `is_market_order_disallowed` (msg1 키워드 `시장가매매불가` / `시장가호가불가` / `최유리/최우선지정가 주문만` / `지정가 및 최유리` — APBK1943/APBK3013) 매칭 시 `step_up(buy)/step_down(sell)` 으로 `LIMIT` 재시도. 매핑 동기 + race 가드 동일 규약
- **KIS 거부 응답 영구 저장** — `_request` 가 `rt_cd != "0"` 시 `system_logs` prefix `[kis_rejection]` + path/tr_id/msg_cd/msg1 + body 주요 키 (민감 키 마스킹) fire-and-forget
- **WebSocket 시세 보유·익일청산 우선 보장** — `MAX_SUBSCRIPTIONS=41` KIS 공식 한도. HIGH (보유/익일청산) `bypass_limit=True` 절대 보장. 후순위 drop 시 `[priority_drop]` INFO + WARNING `system_logs`. HIGH 단독 41 초과 ERROR
- **WebSocket 다중 안전망** — F1 (재연결 1회) + `_scan_loop` (5분) + K stale watcher (120s 주기, 1~5회 즉시 강제 재등록 + 6회 초과 시 10분 cooldown 기반 시간 기반 force_retry + 시간당 6회 cap) + `_resubscribe_stale_priority` (5분 우선) 4중. K stale watcher 양쪽 분기에 우선순위 분리 (positions/`_pending_next_day_clear` HIGH+bypass=True, 그 외 후보 LOW+bypass=False — 메인 편중 차단). `_subscriptions` ACK 정합성 가드 (orphan ACK race 차단)
- **세션 단위 silent inactive 자동 reconnect** — `_detect_silent_inactive_sessions` 3중 가드: `fresh_ratio < SILENT_INACTIVE_FRESH_RATIO_THRESHOLD(=0.2, 20%)` + `subscribed_count >= 5` + 5분 지속 → `_ws.close()` 강제 reconnect. 시간당 세션당 2회 cap (LMS/앱키 정지 위험 차단). **세션 상대 판정 (cycle241)** — 판정 가능 세션(`subscribed >= 5`)이 **2개 이상이고 그 전부**가 `fresh_ratio < 0.2` 이면 '세션 고장'이 아니라 **시장 침묵**(NXT 프리 마감·장후 동시호가·마감 흡수)으로 보고 그 사이클을 **기각 + 판정 가능 전 라벨 `first_seen` pop**(누적 후 필터 금지 — 시장 재개 순간 지각 세션이 즉발한다); 다른 세션이 하나라도 fresh 면 현행대로 발화(진짜 세션 결함 보존), 판정 가능 세션 < 2 면 현행 유지(fail-open) = 결과 집합 ⊆ 현행. 기각은 `[silent_inactive_market_wide_skip] transition=entered|persisting|exited` 로만 관측(30분 이상 지속 시 WARNING). **시장 침묵 기각에 시간창 리터럴(08:30/15:20)·`tradable_boards`·`session` import 를 쓰지 않는다** — 세션 간 비교만이 마감 흡수 구간의 갭까지 닫는다(AST G-241-5)
- **무송출(no_feed) 종목은 K stale watcher 가 재등록하지 않는다 (cycle252)** — SUBSCRIBE 가 SUCCESS ACK 를 받아도 체결 프레임이 영구 0 인 종목이 있어, 재등록은 회복 가치 0 이고 SEND 만 하루 ≈14,600 을 만든다. `stale_watcher_core.check_and_resubscribe_stale` 은 `no_feed_registry`(`stock_master` 조회, 600s TTL, **fail-open** = 집합 ∅·조회 예외·미지 ticker 면 현행 byte 동일)로 **LOW no_feed 종목의 SEND·`_stale_last_resubscribe_at` 스탬프·force_retry history 만** 건너뛴다. **HIGH(보유·익일청산) 경로는 byte 동일** — 가설이 어떤 보유 종목에 대해 틀렸을 때 잃는 것이 손절 커버리지이기 때문이다. 대신 `[no_feed_held]` WARNING 1회/일이 "보유 종목이 WS blind, 손절은 REST 폴만" 을 남긴다. `_stale_retry_count` 는 계속 증가(r>5 홀드)해 `stale_universe_guard` 의 저유동 축출 경로를 보존한다. 근본 시정인 채널 리졸버(cycle293 속성축 → cycle294 시간축 = 통합 채널 소멸)가 착지한 지금은 `[no_feed_held]` 와 `[stale_watcher_summary] no_feed_skipped=` 가 **0 에 수렴하는 것이 정상**이다 — 상세 = `src/realtime/CLAUDE.md` 「시세 채널」 절, 킬스위치 = `PUT /api/realtime/tick-channel-mode`. ⚠️ 이 두 마커와 `[tick_coverage] stale` 의 의미는 2026-09-14 배포로 뒤집혔다 — **그 전후 로그를 합산하지 않는다**. 5분 `resubscribe_stale_priority` 는 무접촉(후보 소스 `ticker_last_tick` 에 no_feed 종목은 프레임 0 이라 애초에 없다). 금기 = no_feed 를 stale 집계에서 **빼서** 숫자를 좋게 만드는 것, HIGH 를 skip 에 넣는 것, 관측 헬퍼가 예외를 전파해 HIGH 재등록 사이클을 끊는 것
- **stale universe 가드** — `_evaluate_universe_guard`: stale>5 + `today_volume < UNIVERSE_LOW_VOLUME_THRESHOLD(=10_000)` 종목 자동 unsubscribe + `_universe_excluded_today` 등록 + `[universe_excluded]` INFO + `inquire_ccnl` 으로 마지막 체결시각 로그. 보유/익일청산 절대 보호 + `_reset_daily_state` 동행 clear (영구 블랙리스트 금지)
- **`trade_history` 중복 INSERT 차단** — `_sync_orders_to_db` 는 `get_today_buy_trades_for_sync()` / `get_today_sell_trades_for_sync()` 사용 (dedupe 없음 + CANCELLED 제외). DB 부분 UNIQUE 인덱스 `(ticker, order_no, trade_type)` 이중 안전망. 기존 `get_today_buy_trades()` 의 ticker dedupe 는 포지션 복구용 — 절대 sync 중복 판정에 사용 금지
- **NXT 거래가능 사전 판별** — `stock_master.nxt_tradable=False` 면 NXT/SOR → KRX 강제 다운그레이드 + `[nxt_downgrade]`. `_boot()` eager 사전 갱신 (보유 + `_pending_next_day_clear` 합집합). 거부 사후 보강 `stock_master.upsert_one(ticker, nxt_tradable=False)`
- **종목코드 형식 비대칭** — 진입은 6자리 숫자만 (`isdigit()`), 사후처리는 6자리 영숫자 (`isalnum()`) — ETF·신주인수권 자동매매 차단 + 좀비 포지션 방지
- **매수 수량은 전략 잔여 자금 기준** — 7 전략 `calc_buy_quantity()` 의 **모든 return** 이 `StrategyBase._apply_budget_limit()` 관문을 경유한다 (AST 가드 A-GATE). 잔여 = `total_investment - (positions buy_price×qty + pending_buy_amounts 합)`. 비중 기준 0주면 관문이 `_fallback_one_share` 로 위임 — **이 분기 순서가 계약이다**. 관문 **안의 순서도 계약이다**: 폴백·잔여 클램프 → `_apply_lot_units_cap`(K축, cycle242) → `[oversized_fallback]` 관측 → `_apply_ratio_notional_cap`(ρ축, cycle245) → `return`. ρ축을 관측 **앞**에 두면 차단된 랏의 ρ 관측이 `final_qty < 1` 로 통째로 사라지고, K축 **앞**에 두면 조기탈출로 cycle242 마커 3종이 사라진다. 관문 안에서 `await`/DB/HTTP **절대 금지**(AST A-PURE — 두 사이클의 신규 헬퍼 14개 전부에 적용: G-242-2/G-242-10 · G-245-2) — `execute_buy` 의 `calc_buy_quantity`↔`pending_buys.add` 사이 await 0건(AST 가드 A-ATOMIC)이 원자성의 전제이고, 이게 깨지면 두 코루틴이 같은 잔여를 보고 각자 매수해 예산 클램프가 조용히 무력화된다. 관측 emit 3종은 전부 예외를 흡수하고 **행위는 cap 밖**이다(관측 실패가 매수 수량을 바꾸면 안 된다). K축 캡 ATR 은 사이징과 **같은** `_candidates[ticker]` 를 read-only 로 읽고 `("atr","atr14")` 두 키가 서로 다른 값이면 **불채택**(fail-open) — `_candidates` 를 생성·변경하지 않는다(AST G-242-8). 캡 스코프는 폴백 랏이 아니라 **관문을 지나는 모든 랏**이고, 관문 반환 타입은 **`int`** 여야 한다(float 이면 `api/order.py` 가 `ORD_QTY="2.0"` 을 KIS 로 보낸다 — G-245 회귀가 봉인)
- **API 인증은 조용히 꺼지지 않는다 (cycle243)** — `ApiAuthMiddleware` 는 **최외곽**(`MetricsMiddleware` 보다 바깥, starlette 는 마지막 `add_middleware` 가 가장 바깥)에서 `/health` 를 뺀 **전 경로**를 `X-API-Key` 로 지킨다. `API_AUTH_KEY` 미설정·빈 문자열·비교 예외는 전부 **401(fail-closed)** — fail-open 은 "키가 없으면 인증이 사라진다" 는 뜻이라 금지다(매매 엔진은 in-process 라 API 가 잠겨도 매매 영향 0, 대시보드만 멈춘다). 금기 = (a) `/api` 접두사 스코프로 좁히기(`/docs`·`/openapi.json` 이 열린다) (b) 프로덕션 코드에 테스트 우회 플래그 두기 — 테스트는 모듈 전역 `authorize` 를 monkeypatch 하는 seam **하나**만 쓴다(`tests/conftest.py::_neutralize_api_auth` + 옵트아웃 마커 `real_api_auth`) (c) `API_ALLOWED_ORIGINS=*` — 와일드카드는 코드가 **버리고 경고**한다(CORS credentialed preflight 전면 개방 + CSRF Origin 검사 무력화가 한 값에 동시에 딸려온다) (d) 개발 예외·개발용 기본키(커밋된 기본키는 공격자가 프로덕션에 가장 먼저 시도할 값) — dev 는 vite proxy 가 서버 측에서 `X-API-Key`·`Origin` 을 넣어 산다. 상태변경(POST/PUT/PATCH/DELETE)은 Origin 검사 추가(부재는 허용 = curl 비상 매도 경로 보존). **알려진 한계 = 단일 공유 키**(감사 추적 없음). **리포터 스코프(cycle249)** — `authorize()` 가 운영 키 판정 **뒤**에 리포터 키(`API_REPORTER_KEY`)를 본다: GET/HEAD 는 경로 무관 통과, `POST /api/log-reports/{date}/external` 정확 경로만 통과, 그 외는 유일하게 **403**(`reporter_scope`, 다른 사유는 전부 401). 스코프는 요청 헤더가 아니라 nginx `map $remote_user` 가 고르는 **Basic 사용자**에서 나온다(`location /api/` 가 클라이언트 헤더를 무조건 치환하므로 "루틴이 스코프 키를 보낸다"는 설계는 성립하지 않는다)
- **비중 단위 추론 변환 금지** — 전략 비중은 **어느 계층에서도 값 크기로 단위를 추측하지 않는다**. 폐기된 `v / 100 if v > 1 else v`(라우트)와 `totalW <= 1.01 ? round(w*100) : round(w)`(프론트 로드)는 1%(정수 `1`)를 100%로 저장하고 그 오염을 "균등분배" 화면으로 **위장**했다 — 추론 분기는 오염 시에만 깨어나므로 결함이 아니라 결함 은폐 장치다. 단위는 계약으로 고정(비율 0.0~1.0)하고 위반은 조용히 흡수하지 말고 422 / `success=false` 로 **시끄럽게 거부**한다. AST 가드 = `tests/unit/ast/test_ast_weight_no_magnitude_heuristic.py`(`update_weights` 내 `IfExp` · `/ 100` 0건, Σ 가드가 저장보다 선행 + 사이에 early return) + `frontend/src/components/__tests__/_ast_weight_unit_guard.test.ts`(`Settings.tsx` 내 `1.01` 리터럴 · `Math.round(s.weight)` 0건)
- **터틀 ATR 손절 게이트는 `_entry_atr` 스탬프 존재** — `sizing_mode` 로 게이팅 금지. DB 토글 하나로 **기보유 포지션의 손절 규약**이 바뀌면 안 된다. position_ratio 매수는 미스탬프라 기존 % 손절 경로를 byte 동일하게 탄다. 스탬프 값은 반드시 sizing 에 쓴 ATR 과 동일(커플링 불변식). 이 금기는 **청산** 규약이다 — 진입 사이징(`calc_buy_quantity`·`max_lot_units` 캡)이 `sizing_mode` 로 분기하는 것은 충돌이 아니다
- **VB 당일 15:20 일괄매도** — `DEFAULT_TRADABLE_BOARDS=("main",)`, POST_NXT 추가 금지. `_force_clear_main_only` 가 15:20 일괄 청산. 15:30 이후 호출은 시간 가드로 skip
- **`tradable_boards` 는 매수 진입 전용 (명문화)** — 매도/손절/Trailing/익일청산/15:20 강제청산/상한가 손절 모니터링은 어떤 전략에서도 PRE/MAIN/POST 무관 항상 작동. **유일한 예외 = NXT 프리장(08:00~09:00) 청산 평가 보류 게이트**(2026-08-06 사용자 결정, `risk._PRE_MARKET_EXIT_EVAL_STRATEGIES` 화이트리스트 = LTV 만) — 프리장 왜곡 틱(전일 상한가 종목 시초가 하한가 형성 등)의 허깨비 손절·트레일링 고점 오염을 차단하고 09:00 KRX 시세로 재평가한다. **평가 보류이지 주문 보류가 아니다**(주문만 보류하면 허깨비 신호가 09:00 실매도로 전환). 게이트는 `tradable_boards` 가 아니라 **명시 상수**로 판정(AST 가드) — 매수 목적 보드 변경이 청산 규약을 바꾸는 커플링 차단. 매도 시장가는 `execute_sell` 이 프리장 단독 구간에서 `step_down(현재가,5)` 지정가로 사전 변환(매수 PR-F 대칭, 실효 대상 LTV). `risk.on_tick` 의 `check_exit_signal` 분기는 `session_tracker.is_tradable` 검사 *전* 진입. LTV `DEFAULT_TRADABLE_BOARDS=("pre_nxt", "main", "post_nxt")` (사용자 의도 — 연속 상한가 익일 청산 + 야간 매수)
- **VB·LTV `main` 목표가 기준가 = KRX REST 단일 출처 (cycle272 — 사용자 결정 D1)** — `board=="main"` 목표가는 WS 세션 시가(KRX 확정 시가와 어긋난다) 대신 **KRX REST `stck_oprc`(`J`) 만** 기준가로 삼는다. 좁은 목 `on_open_price_confirmed(..., board="main", *, source="ws")` — `source` 신뢰 목록은 `("rest",)` 뿐이고 기본값이 불신 `"ws"` 라 WS 확정 경로는 조용히 거부된다. 킬스위치 `open_price_scope_mode`(전략별 `DEFAULT_PARAMS`, 기본 `"enforce"`, `"off"` 만 롤백 — `PARAM_RANGES`/`INT_PARAMS` 편입 금지). REST 확보는 leaf `src/engine/open_price_rest.py`(09:00:35 부터 30초 간격 **19라운드**(마지막 09:09:35) → 5분 간격 15:20 까지, 프린트 안 된 종목은 그 시점 매수 불가). `pre_nxt`/`post_nxt` 보드는 게이트 스코프 밖 — LTV 08:00~09:00 프리장·야간 매수 무접촉. 상세 = `src/engine/strategies/CLAUDE.md`
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
| `daily_log_reports` | **21:30** 일일 로그 분석(cycle283 D3) + **20:05 metrics 1차 스냅샷**(같은 행을 upsert) (target_date UNIQUE, metrics 에 api_metrics/strategy_funnel/by_ticker_pnl/by_hour_pnl/next_day_clear 포함). 토큰/지연/비용 5 컬럼 — input_tokens/output_tokens/total_tokens/latency_ms/cost_estimate_usd (migration 031, 모두 NULL 허용) |
| `stock_master` | KIS CTPF1002R 캐시 (ticker PK, 24h TTL) + `master_raw` JSONB + `master_raw_updated_at TIMESTAMPTZ` (KIS 공식 일일 마스터 파일 영역 — 시총/거래정지/관리종목/지수편입/재무 ~30 키, raw 영역 분리 보호). NXT 거래가능 사전 판별. 생성 컬럼 `hts_avls_eok bigint`(억원) + `acml_tr_pbmn_won bigint`(원) GENERATED ALWAYS STORED (migration 039 — raw 의 `hts_avls`/`acml_tr_pbmn` 이 jsonb **문자열**이라 UI 의 jsonb numeric 비교가 0건으로 조용히 실패했다. 비숫자는 `~ '^[0-9]+$'` 가드로 NULL). **raw 는 읽기만 한다**(AST G-AST1 영속) |
| `stock_master_daily` | KIS FHKST03010100 일봉 정규화 (migration 033). PK `(ticker, bas_dd)` + OHLCV + change_rate + raw JSONB. **매일 20:30 KST 적재**(`TIME_STOCK_MASTER_DAILY_LOAD`) — 백필 시 T-100일, 이후 D-1 영업일 증분. **일봉 적재 대상 전부**(index ∪ 시총·거래대금 자격 ∪ 보유·익일청산 보호) backfill target **225일**(cycle302 가 대상을 지수에서 전체로 넓혔다 — 비지수 1,526 종목의 225행 도달률이 0% 였다. 첫 채움만 종목당 3콜이고 수렴 후에는 증분 1콜이다. cycle299 — `effective_ema_long = min(ema_long, 보유 − 20 − 5)` 라 보유 225 에서 실효 장기선이 정확히 **200** 이 된다) · retention `DAILY_RETENTION_DAYS=390`(390 캘린더일 ≈ 261 영업일이라 target 위로 36 영업일 마진. 두 값은 함께 움직인다 — target 이 보유 영업일을 넘으면 무한 재backfill churn). donchian(20일 신고가) / VCP(베이스+Pullback, 읽기 깊이는 전략 파라미터 `daily_fetch_depth_mode` — 기본 `"cap100"`=100봉 / `"full"`=`ema_long+base_max+10`, cycle300) / VB(노이즈비율 K·전일 Range — **ATR 아님**) 전략 활용. 읽기 관문 상한 = `get_recent_daily` 의 `_MAX_DAILY_ROWS=400` |
| `stock_master_financial` | KIS 재무 5 TR 정규화 (migration 041, 사이클 C1). PK `(ticker, stac_yymm, div_cls)` (div_cls 0=년/1=분기) + 18 NUMERIC 컬럼(손익 5/대차 7/수익성 2/안정성 2/기타 2) + raw JSONB + refreshed_at. 마법공식(EV/EBITDA·ROC) + F-Score-7 원천 데이터. 주1회 16:40 적재. 매매 hot path 무관 |
| `llm_buy_evaluations` | **cycle276** AI 매수평가(LLM shadow)를 주문 발화 시점에 기록 (migration 043). PK `(trade_date, account_no, ticker, order_no)` + 53열 — 점수/임계/`would_block`·사유·핵심위험·무효화조건 · 주문 스냅샷(주문가·수량·구분·경로·거래소·보드) · 모델/토큰/비용/지연 3종 · 회고 층화 `prompt_version`/`feature_version` · 주문 시점 제약 `budget_total_won`/`budget_remaining_after_won`/`open_positions_n` · `input_payload` JSONB(`build_messages` 3인자 전체 = 오프라인 재채점의 다리) · `raw_response` JSONB(파싱 전 원문). **주문 1건 = 1행(성공·실패 모두)**, 실패 행도 payload 를 담고 `score=NULL`. 조인 = `order_no`→`trade_history` 체결(`(trade_date, ticker, order_no)` 3축) · `buy_order_nos`→`get_trade_pairs` 실현손익. 인덱스 4 |
| `backtest_runs` | 외부 MCP 백테스트 영속화 (`(target_date, strategy_id, params_kind)` UNIQUE. 활성 전략마다 2 row/자문(`params_kind` = current|recommended)) |
| `market_regime_snapshots` | 매크로 레짐 일일 스냅샷(출처 = 우리 `macro` 컨테이너). `_boot()` 시점 1행. `buy_blocked`/`computed_cash_usage_ratio`/`raw_response JSONB` 영구 기록 |
| `kis_quote_accounts` | 보조 KIS 시세 수신 계좌 (UUID PK, label UNIQUE, active=true 부분 인덱스). `list_accounts()` 60s TTL 메모리 캐시 |
| `strategy_funnel_snapshots` | 전략별 조건검색 단계별 후보/탈락 종목 영구 추적. `(target_date, strategy_id, step_no, snapshot_at)` UNIQUE. `survived_tickers` JSONB cap 200 / `excluded_sample` JSONB cap 20. 09:30 자동 캡처(`scheduler._auto_capture_funnel_snapshots`, 단계별 + `step_no=99`) + 수동 trigger `POST /api/strategy-funnel/snapshot`(`capture_funnel_snapshots(registry, is_provisional=False)`) |

> **`trade_history` 부분 UNIQUE 인덱스 (migration 029)**: `uq_trade_history_ticker_order_no_type ON (ticker, order_no, trade_type) WHERE order_no IS NOT NULL AND order_no != ''`. `_sync_orders_to_db` 핑퐁 INSERT 영구 차단 + NULL/빈 order_no (수동 매매 사전 등) 호환.

> **`stock_master` / `stock_master_daily` UI 동기화 의무**: stock_master 컬럼 / raw JSONB 키 / stock_master_daily 컬럼 추가 시 UI 동기화 의무 영속. 전략에서 종목마스터 데이터 참고 시점 영역부터 신규 수집 데이터는 UI 노출 의무. 절차 = (1) `frontend/src/types/stock-master.ts` interface 갱신 (2) `frontend/src/api/stock-master.ts` 호출 영역 갱신 (3) `frontend/src/pages/StockMaster.tsx::FIELD_LABELS` 한글 라벨 + `CATEGORY_KEYS` 배치 + `HIGHLIGHT_KEYS` 핵심 키 추가 (4) `GET /api/stock-master/stats` 응답에 진단 카운트 추가 + 카드 1개 추가 (5) `frontend/src/test/handlers.ts` MSW + `e2e/fixtures/api-mocks.ts` Playwright LIFO 정합 갱신 (6) 회귀 가드 추가. 상세는 `frontend/CLAUDE.md` 참조.

## Docker / 배포

- `Dockerfile` / `frontend/Dockerfile` 멀티스테이지 (dev: hot-reload / prod: non-root + Nginx)
- `docker-compose.yml` (개발 hot-reload) / `docker-compose.prod.yml` (prod)
- **토큰 캐시 영속화**: `./.token_cache:/app/.token_cache` 디렉토리 볼륨 양쪽 compose 동일 마운트. KIS `/oauth2/tokenP` 분당 1개 한도 + 컨테이너 재기동 시 토큰 24h 유효 보존. `.gitignore` 등록 (`.token_cache/` + 구 `.token_cache_quote_*.json` 호환). 구 경로 `.token_cache.json` 존재 시 자동 마이그레이션
- **`.token_cache` 빌드 시점 권한 보장**: `Dockerfile` prod 스테이지가 `mkdir -p /app/.token_cache` → `chown -R appuser:appuser /app` → `USER appuser` 순서. 호스트 bind mount 가 root:root 로 생성되어 `appuser` 가 쓰기 거부되던 결함 영구 차단 (회귀 가드: `tests/integration/test_dockerfile_token_cache_perms.py`)
- `frontend/nginx.conf.template`: 정적파일 + `/api` → backend:8000 프록시 + **사이트 전체 Basic Auth**(cycle243). `nginx:alpine` 엔트리포인트가 `/etc/nginx/templates/*.template` → `/etc/nginx/conf.d/` 로 envsubst 렌더(`NGINX_ENVSUBST_FILTER=^API_(AUTH|REPORTER)_KEY$` 로 치환 변수 2개 제한). `map $remote_user $api_key_for_user { default "${API_AUTH_KEY}"; reporter "${API_REPORTER_KEY}"; }` 가 http 컨텍스트(server 블록 밖·앞)에서 Basic 사용자별 키를 고르고, `location /api/` 는 `proxy_set_header X-API-Key $api_key_for_user;` 로 그 결과를 주입한다(치환 구문은 `map` 블록 안에만 둔다). 자격 파일은 호스트 `./secrets/.htpasswd` bind mount(**git 커밋 금지**). ⚠️ 권한: nginx worker 는 컨테이너 안 **uid 101(nginx)** 이고 호스트 파일은 `ubuntu`(uid 1000) 소유라 `chmod 600`·디렉터리 `chmod 700` 이면 전면 500 이다 → `chmod 755 secrets` + `chmod 644 secrets/.htpasswd`. 결손 진단 3갈래 — **무자격은 어떤 상태에서도 401**(정상과 동일 = 무자격 curl 로는 결손을 판별할 수 없다) / 자격 + 파일 부재 → **403** / 자격 + 권한 거부 → **500**. `auth_basic off;` 는 이 템플릿에 **절대 쓰지 않는다** — 한 줄로 Basic Auth 와 백엔드 X-API-Key 주입이 동시에 뚫린다(AST 가드 D-1-b). 구 `frontend/nginx.conf` 를 되살리지 않는다(인증 없는 구버전이 조용히 서빙되는 fail-open)
- 타임존 `TZ=Asia/Seoul`, vite 프록시 타겟은 `VITE_API_URL` 분기
- **EC2 t4g.small (ARM, ap-northeast-2)** 서비스 경로 `~/auto_stock/`
- 자동 배포: `git push origin main` → GitHub Actions 가 EC2 SSH → `git pull` + **선택적 재빌드**(`.github/workflows/deploy.yml` → `tools/deploy/compose_up_changed.sh`, cycle248). push 시각 → pool_start 지연 1~5분(backend 가 재생성될 때만). deploy.yml 은 push 후 `supabase/migrations/*.sql` 을 EC2 psql 로 순차 적용 (`SUPABASE_DB_URL` secret — **이름은 유지하되 값이 RDS DSN**, graceful skip)
- CI (`.github/workflows/ci.yml`): `postgres:15` service 컨테이너 + `DATABASE_URL_TEST` 로 통합 테스트 실행 (`tests/integration/pg_harness.py` 가 migration 001~043 적용)
- GitHub Secrets: `EC2_HOST`, `EC2_USERNAME`, `EC2_SSH_KEY`, `SUPABASE_DB_URL` (값=RDS DSN)
- **로컬과 EC2 동시 실행 금지** — KIS 동일 계정 동시 접속 충돌
- **선택적 배포 (cycle248)** — `tools/deploy/compose_up_changed.sh` 가 **마지막 성공 배포 SHA 마커**(`.deployed_sha`, git 밖)와 HEAD 의 누적 diff 로 모드를 고른다. **full**(`src/`·`requirements.txt`·`Dockerfile`·`docker-compose.prod.yml`·`.dockerignore`·`deploy.yml`·`tools/deploy/` 중 하나라도 변경 → `up --build` = **backend 재시작**) / **선택 배포**(backend 축 무변경 + `frontend/`·`tools/ops/tls_stage2/`·`macro/` 중 변경된 축만 → `up --build --no-deps <서비스…>`, backend 무접촉. 모드 이름이 곧 서비스 목록이다 — `frontend` · `macro` · `frontend+macro`) / **none**(그 외 tests·`tools/test_impact`·`pyproject.toml` 등 또는 마커==HEAD 재실행 → 빌드 없는 `up -d`). 판정 불가(마커 없음·미지 SHA·diff 실패)는 전부 **full**(fail-safe). backend 히트가 하나라도 있으면 그 즉시 full 로 확정되므로 **backend 가 선택 목록에 들어갈 길은 구조적으로 없다**. 마커는 compose 성공 뒤에만 쓴다. 분류의 근거는 루트 Dockerfile COPY 소스가 `requirements.txt`·`src/` 뿐이라는 구성적 사실(가드 D-8)이고, `test_cycle248_deploy_pipeline.py::G-248-2` 가 COPY 소스 ↔ 정규식 정합을 강제한다(COPY 를 늘리면 붉어진다)
- ⚠️ 배포 모드 함정 넷: (a) `**.md`·`docs/**`·`_workspace/**` 만 바꾼 push 는 CI `paths-ignore` 로 **CI/Deploy 자체가 뜨지 않는다**(마커는 다음 배포의 누적 diff 가 따라잡는다) (b) `src/**` 는 확장자 무관 이미지 입력이다(`src/CLAUDE.md` 수정도 full) (c) `.env` 는 git 밖이라 스크립트가 못 본다 — 손댄 뒤에는 운영자가 `docker compose up -d` 로 직접 재생성하고 **마커는 건드리지 않는다**(마커는 git SHA 의 배포 상태만 뜻한다) (d) none 모드의 `up -d` 도 `.env` 등 구성이 어긋나 있으면 재생성한다(none ≠ 무조건 무재시작)
- 배포 모드 사전 확인 = push **전** 로컬에서 `git diff --name-only <EC2 .deployed_sha 값> HEAD` 의 경로를 위 규칙에 대보는 것(EC2 dry-run 은 이미 pull 된 HEAD 만 본다). EC2 에서는 `DEPLOY_DRY_RUN=1 bash tools/deploy/compose_up_changed.sh`(docker 미호출·마커 미기록, `true` 동치·미지 값 exit 2). **EC2 에서 git 을 손으로 움직였거나(reset/checkout/revert/stash) 수동 `docker compose build|up --build` 를 했으면 `rm ~/auto_stock/.deployed_sha`** — 마커는 git SHA 의 배포 상태만 뜻하고 실행 중 이미지와 대조하지 않는다. 직전 배포가 중간에 죽으면 `.deployed_sha.attempt` 가 남아 다음 배포가 자동으로 full 이다
- **TLS — `auto.dkstock.cloud` 2단계 가동 중**(1단계 2026-09-05 · 2단계 09-08). 80 은 **301** 로 https 로 보내고, 443 은 Basic Auth + HSTS `max-age=86400`(includeSubDomains·preload 없음). ACME HTTP-01 챌린지 location(`^~ /.well-known/acme-challenge/`, `satisfy any; allow all; root /var/www/certbot;`)만 301 밖이다. 스위치는 호스트 마커 파일 2개(git 밖) — `.tls_enabled`(1단계 = `docker-compose.tls.yml` + `frontend/nginx.tls.conf.template`) · `.tls_stage2`(2단계 = `docker-compose.tls2.yml` 이 `tools/ops/tls_stage2/` 스니펫을 마운트). 켜고 끄는 것은 `tools/ops/tls_enable.sh` · `tools/ops/tls_stage2_enable.sh` 이고, 사후 검증에 실패하면 두 스크립트가 **마커 삭제 + 이전 단계 원복까지 스스로 실행**한다. `compose_up_changed.sh` 는 마커가 있을 때만 `-f` 오버레이를 덧붙이고 **모드 판정에는 개입하지 않는다**(개입하면 TLS 를 켠 날부터 모든 배포가 backend 재시작이 되어 cycle248 이 없앤 비용이 부활한다). 인증서 갱신은 `certonly --deploy-hook` 으로 renewal conf 에 영속돼 snap/apt timer 가 돌린다 — **crontab 을 두지 않는다**(ubuntu crontab 은 `/etc/letsencrypt` 쓰기 불가, 상대경로 compose 는 cron cwd 에서 실패). 🔴 **TLS 템플릿에 `map` 을 중복 정의하지 않는다** — nginx 는 **정상 기동**하고 뒤에 include 되는 map 이 조용히 이겨 모든 사용자의 `X-API-Key` 가 빈 값이 된다(무증상 backend 전면 401). 텍스트 가드 G-255-2f 가 유일한 방어다. `auth_basic off;` 금지는 여기서도 불변(D-1-b). **Basic 자격 회전은 `tools/ops/rotate_basic_auth.sh` 로 한다**(실행 이력은 워크리스트) — 301 은 서버가 자격을 요구하지 않게 할 뿐 브라우저가 선제로 보내는 옛 자격까지 막지 못한다. 새 비밀번호는 화면에 찍지 않고 `secrets/.rotated-<ts>`(권한 600) 로만 전달되므로, 운영자가 그 값을 클라우드 루틴의 `REPORTER_BASIC_PASSWORD` 에 넣고 브라우저를 재로그인해야 회전이 끝난다
- ⚠️ EC2 사전 생성 규약: `~/auto_stock/secrets/` 와 `~/auto_stock/certbot-www/` 는 **사람이 먼저 만든다**. compose 의 bind mount 가 먼저 만들면 root:root 가 되어 `ubuntu` 가 쓸 수 없다(`.token_cache` root 소유 사고와 같은 계열)
- **프로세스 분리 1단계 = `llm_worker` 컨테이너**(AI 매수평가를 분리, 큐로 쓸 대상은 신규 브로커가 아니라 `llm_buy_evaluations` 테이블 = migration 043). **아직 코드가 없다** — 배포 모드는 full / 선택 배포(`frontend`·`macro`·`frontend+macro`) / none 이고 미지 모드는 `exit 2` 다. 착수 시 제약 둘 — (a) `llm_worker` 는 `docker-compose.prod.yml` **본체**에 정의한다(오버레이에만 두면 그 오버레이를 안 붙이는 `full`·`none` 배포의 `--remove-orphans` 가 돌던 워커를 orphan 으로 삭제한다) (b) 워커 코드를 `src/` 아래 그대로 두면 워커 전용 변경도 `full` 로 분류돼 backend 가 재시작된다(`BACKEND_RE` 첫 대안이 `src/`). 2~4단계 도식과 보류 근거의 파일:행 인용 = [`docs/architecture.md`](docs/architecture.md) 15장
- 운영 가이드 — **보유 포지션이 있으면 KRX 메인 시간(09:00~15:30) push(=EC2 자동 배포) 금지**(cycle232 D6): 재시작 1~5분 tick blind 동안 손절 사각 + `_scan_loop` 5분 race. 보유 0이면 빈번한 push 자제 수준. **20:00~21:35 도 피한다**(cycle283 D8 — 20:00 AI 자문 · 20:05 metrics 1차 스냅샷 · 20:30 일봉 적재 · 21:30 정산/`_reset_daily_state`. 그 창의 재기동은 `TIME_SESSION_START_CUTOFF`(20:00)에 막혀 그날 저녁 블록 전체(20:30 일봉 적재 · `_settle()` · 일일 로그 분석 · 로그 retention)가 통째로 결손된다. `[daily_head_stale]` WARNING 이 다음 아침 `_boot()` 에서 일봉 결손을 알리고, 복구 절차 3종은 `src/routes/CLAUDE.md` 의 `/api/trading/restart` 행에 있다). **16:00~20:00 은 KRX 애프터마켓 실시간 연속체결**, **08:00~08:50 은 NXT 프리장** — 둘 다 실매매 구간이라 재시작이 같은 tick blind 를 만든다. 즉 장외 배포 창은 **15:30~16:00 · 21:35~익일 07:45** 와 주말·공휴일이다. 이 금지는 backend 가 재생성되는 push(full 모드)에만 실질 적용되지만, **어느 모드인지 확신이 없으면 full 로 간주**한다(`tools/deploy/` 나 `deploy.yml` 이 섞인 커밋은 항상 full)

## 디렉토리 역할
- `src/auth/` — KIS OAuth 인증/토큰 (메인 + 보조 multi)
- `src/api/` — KIS REST (주문·잔고·조건검색·일봉) + 시세 풀 (`base.py::_request_via_quote_pool` + path 화이트리스트 가드). `quotation.py::inquire_ccnl(ticker, market='J')` — FHKST01010100 주식현재가 시세, output[0] + today_volume 합산 + graceful None (stale universe 가드용)
- `src/realtime/` — KIS WebSocket (시세·체결통보·H0NXMKO0) + WebsocketPool 멀티 세션 분배
- `src/engine/` — 매매 핵심 (전략·레지스트리·주문·리스크·스케줄러). `recommendation_engine.py` 20:00 AI자문 / `log_analysis_engine.py` 21:30 일일 분석(cycle283 D3) / `daily_metrics_snapshot.py` 20:05 metrics 1차 스냅샷 / `backtest_engine.py` + `backtest_yaml.py` / `market_regime.py`
- `src/engine/strategies/` — 7 전략 명세 (전용 CLAUDE.md)
- `src/services/` — 서비스 클라이언트 (`mcp_client.py` 백테스트 MCP / `macro_client.py` 매크로 레짐 — 우리 `macro` 컨테이너를 평문 GET 으로 부른다, 인증 없음 / `quote_session_health.py` 보조 세션 health monitor)
- `src/db/` — PostgreSQL(asyncpg) CRUD. 전 모듈이 `src/db/pg.py` 풀을 쓴다 (`supabase.py` 는 롤백용 병존, 런타임 미참조)
- `src/middleware/` — API 인증(`X-API-Key`)·리포터 스코프 최외곽 미들웨어 (전용 CLAUDE.md 없음)
- `src/routes/` — FastAPI 엔드포인트
- `src/models/` — Pydantic 모델
- `src/workers/` — 워커 진입점이 들어올 자리. **아직 없다.** 계획 = [`docs/architecture.md`](docs/architecture.md) 15.2 · 15.5
- `frontend/` — React 대시보드
- `macro/` — **매크로 API 별도 컨테이너** (경기사이클·투자체제·금리차·하이일드·환율·원자재 5섹션 = `GET /api/macro/*`). 자체 `Dockerfile`·`requirements.txt`(pandas/numpy/yfinance)·`main.py` 를 갖고 매매 이미지와 완전 분리된다 — **`src/` 아래로 옮기지 않는다**(옮기면 macro 변경마다 매매 backend 가 재시작된다). `macro/macro_lite/` 는 stock-manager 추출 패키지의 **무수정 vendor** 라 재이식 시 통째로 덮어쓴다. 캐시는 `MACRO_LITE_CACHE_DIR` 영속 bind mount 필수(FRED 가 OAS 를 3년치만 주므로 누적 store 가 유실되면 하이일드 **차트**의 10년·5년 구간이 3년으로 영구 퇴행). **매매 레짐의 출처이기도 하다**(cycle315) — `src/engine/market_regime.py` 가 `src/services/macro_client.py` 로 이 컨테이너를 부른다. 다만 레짐은 여전히 **관찰 지표**라 매수를 차단·축소하지 않는다. 운영 가이드 = [`docs/macro-lite.md`](docs/macro-lite.md)
