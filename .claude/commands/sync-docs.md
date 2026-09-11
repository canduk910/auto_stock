---
description: 코드를 분석해 docs/, 각 디렉토리 CLAUDE.md, README.md 를 실제 코드 사실과 정합시킨 뒤 커밋한다. diff 동기화 + 코드 기반 감사 2 모드.
argument-hint: "[영역/파일 (선택) — 지정 시 코드 기반 감사 모드]"
allowed-tools: Bash(git status:*), Bash(git diff:*), Bash(git log:*), Bash(git add:*), Bash(git commit:*), Bash(find:*), Bash(grep:*), Bash(ls:*), Bash(wc:*), Read, Edit, Write, Grep, Glob
---

너는 이 프로젝트의 문서를 **실제 코드 사실**과 정합시키는 작업을 수행한다. 문서의 진실의 원천은 코드다 — 문서가 코드와 어긋나면 코드를 기준으로 문서를 고친다 (그 반대 아님).

추가 컨텍스트 / 대상 영역(선택): $ARGUMENTS

---

## 실행 주체 — `report-writer` 에이전트에 위임한다 (2026-09-11 사용자 결정)

이 명령의 **본 작업(대조·수정·보고)은 메인 세션이 직접 하지 않고** `report-writer` 에이전트가 한다.
문서를 **쉬운 단어와 짧은 문장**으로 유지·개선하는 것이 그 에이전트의 전문이기 때문이다.

```
[메인 세션] 입력 꾸러미 준비(모드·대상 영역·최근 커밋 범위·의심 지점)
   → Agent({subagent_type: "report-writer", model: "opus"})   ← 모델 명시 필수
   → [report-writer] §1~§5 수행(코드 읽기 → 대조 → 문서 수정)
   → [report-writer] §6 4분류 보고 반환 (커밋하지 않는다)
   → [메인 세션] §7 커밋 여부 결정·실행
```

- 메인 세션이 꾸러미에 담을 것: 모드(A/B) · 대상 영역 · 비교 기준(커밋 범위 또는 "현재 코드") ·
  이번 사이클이 바꾼 것 요약 · 이미 아는 드리프트 의심 지점 · **손대면 안 되는 문서**(§금지).
- `report-writer` 는 **커밋·push 를 하지 않는다**(`cycle-report` 스킬과 같은 규약).
- 메인 세션이 직접 수행해도 되는 예외 = 한 줄짜리 오타·경로 수정처럼 위임 비용이 더 큰 경우.

### 쉬운 말 규칙과 그 한계 (정확성이 먼저다)

문서를 쉽게 고치되, **정확성을 깎아서 쉽게 만들지 않는다.** 두 종류를 구분한다.

| 문서 | 우선 순위 | 쓰기 방식 |
|---|---|---|
| `README.md` · `docs/architecture.md` · `docs/backtest-monitoring.md` | **읽는 사람** | 짧은 문장, 쉬운 단어, 도식 우선. 내부 사이클 번호 남발 금지 |
| 각 `CLAUDE.md` · `_workspace/00_leader_trading_rules.md` | **계약의 정확성** | 문장은 짧게 고치되 계약 문구·조건·예외는 **한 글자도 흐리지 않는다** |

**절대 바꾸지 않는 것** — 식별자(함수·파일·컬럼·마커·TR_ID·파라미터 키) · 상수와 임계값 · 불변식 이름
(A-ATOMIC 등) · 금기 목록의 조건과 예외 · sha 핀과 가드 이름. 이들은 쉬운 말 대상이 아니라 **인용 대상**이다.

**쉬운 말이 적용되는 곳** — 그것들을 둘러싼 설명 문장이다. 한 문장에 한 가지만 말하기, 수동태·번역투 줄이기,
같은 것을 두 이름으로 부르지 않기, "왜 이렇게 하는가" 를 먼저 쓰기.

⚠️ 금기 문장을 짧게 만들다가 **조건이나 예외가 빠지면 그것은 개선이 아니라 결함**이다. 줄이기 애매하면 그대로 둔다.

## 0. 모드 결정 (먼저 판단)

| 모드 | 트리거 | 무엇을 하나 |
|------|--------|------------|
| **A. diff 동기화** (기본) | 인자 없음 / "최근 변경" / "방금 작업" | 최근 코드 변경(working tree + 최근 커밋)을 문서에 반영. 빠른 정합. |
| **B. 코드 기반 감사** | 인자로 영역·파일 지정 ("README", "src/api", "architecture.md", "전체 점검", "감사") | 지정 영역의 **코드를 직접 읽어** 문서와 전수 대조. git diff 와 무관하게 **누적 드리프트**(오래 전 머지됐지만 문서에 안 반영된 불일치)까지 잡는다. |

> 핵심: 모드 A 는 "무엇이 바뀌었나"(diff)를 묻고, 모드 B 는 "지금 코드가 무엇인가"(사실)를 묻는다. git diff 는 *방금 바뀐 것*만 잡으므로, 이미 머지된 코드와 문서의 불일치(예: 함수 시그니처가 초기 설계안 그대로 잔존, 단위 명세 오류)는 모드 B 로만 잡힌다. 사용자가 영역을 주면 항상 모드 B 를 우선한다.

---

## 1. 대상 수집

### 모드 A (diff 동기화)
다음을 병렬 실행한다.
- `git status` — 작업 트리 상태
- `git diff HEAD` — HEAD 대비 unstaged + staged diff
- `git log -10 --oneline` — 최근 커밋 흐름
- 필요 시 `git diff origin/main...HEAD` — 분기 차이

### 모드 B (코드 기반 감사)
git diff 를 보지 말고 **지정 영역의 코드를 직접 읽는다**.
- 대상 코드 파일 전수 Read (또는 Explore 에이전트로 구조 파악)
- 대응 문서(아래 매핑) 전수 Read
- 코드의 사실과 문서의 기술을 **2단 대조표**로 만든다 (§3 체크리스트)

---

## 2. 영향 영역 매핑

변경/감사 위치를 보고 갱신 후보 문서를 정한다.

| 코드 위치 | 갱신 후보 문서 |
|---|---|
| `src/api/*` | `src/api/CLAUDE.md`, `src/CLAUDE.md`, `CLAUDE.md`(TR_ID/호출 패턴), `README.md`(API 엔드포인트 표) |
| `src/auth/*` | `src/auth/CLAUDE.md`, `src/CLAUDE.md` |
| `src/realtime/*` | `src/realtime/CLAUDE.md`, `src/CLAUDE.md`, `CLAUDE.md`(체결통보·구독 핵심 규칙) |
| `src/engine/*` (전략·스케줄러·OrderEngine·RiskManager) | `src/engine/CLAUDE.md`, `src/engine/strategies/CLAUDE.md`, `src/CLAUDE.md`, `CLAUDE.md`(전략/규칙), `docs/architecture.md`(흐름), `README.md`(전략 표·스케줄) |
| `src/db/*` | `src/db/CLAUDE.md`, `src/CLAUDE.md`, `CLAUDE.md`(DB 스키마 섹션), `docs/architecture.md`(9. DB 스키마) |
| `src/services/*` | `src/CLAUDE.md`(디렉토리 역할), `CLAUDE.md`(외부 통합) — **전용 CLAUDE.md 없음, 누락 주의** |
| `src/models/*` | `src/models/CLAUDE.md` |
| `src/routes/*` | `src/routes/CLAUDE.md`, `README.md`(API 엔드포인트 표) |
| `src/middleware/*` | `src/CLAUDE.md`(의존 관계·진입점 표), `CLAUDE.md`(API 인증 규칙·환경 변수) — **전용 CLAUDE.md 없음, 누락 주의**(cycle243 API 인증이 여기 산다) |
| `tools/deploy/*`, `.github/workflows/deploy.yml` | `CLAUDE.md`(Docker/배포 — 선택적 배포 3모드), `README.md`(배포) |
| `tools/ops/*` | `CLAUDE.md`(운영 가이드 — TLS 단계·자격 회전 등 운영자 실행 절차) |
| `tools/analysis/*`, `tools/test_impact/*` | `CLAUDE.md`(테스트 실행 / 관측 도구), 해당 산출물 디렉터리의 README 성격 문서 |
| `e2e/*` | `frontend/CLAUDE.md`(E2E 규약), `README.md`(테스트 실행) |
| `frontend/*` | `frontend/CLAUDE.md`, `README.md`(UI 화면 표), `docs/architecture.md`(10. 프론트엔드 구조) |
| `supabase/migrations/*` | `CLAUDE.md`(DB 스키마 표), `src/db/CLAUDE.md`, `docs/architecture.md`(9. DB 스키마), `README.md`(마이그레이션 목록) |
| `Dockerfile`, `docker-compose*.yml`, `.github/workflows/*` | `CLAUDE.md`(Docker/배포), `README.md`(빌드/실행), `docs/architecture.md`(12. 배포) |
| `requirements.txt`, `frontend/package.json` | `README.md`(의존성 — 영향 있을 때만) |
| 신규 전략/매매 규칙 | `CLAUDE.md`(다중 전략 섹션) + 전략 명세 + `_workspace/00_leader_trading_rules.md` 동기화 여부 안내 |
| 사이클 단위 변경 이력 (하네스) | `docs/HARNESS_CHANGELOG.md`(verbatim 상세) + `CLAUDE.md`(하네스 변경 이력 요약 표 1줄) |
| `.claude/agents/*`, `.claude/skills/*`, `.claude/commands/*` | `CLAUDE.md`(하네스 절 — 에이전트 목록·모델 라우팅·스킬 트리거). 하네스 구성을 바꿨으면 **루트 CLAUDE.md 가 정본**이므로 반드시 같이 본다 |
| 운영 결함·후속 과제 발생 | `_workspace/00_URGENT_WORKLIST.md` — 루트 CLAUDE.md 가 "다른 작업 전에 먼저 읽을 것"으로 지목한 문서다. 열린 과제가 생기거나 닫히면 **여기가 정본**이다 |

### 대상 문서 정본 목록 (2026-09-07 전수 집계)

이 목록에 없는 `.md` 가 리포에 새로 생겼으면 **먼저 이 목록에 넣을지 판단**한다(§6 보고에 명시).

| 문서 | 성격 |
|---|---|
| `CLAUDE.md` | 루트 정본 — 안전 규칙·전략·DB·배포·하네스 |
| `README.md` · `frontend/README.md` | 외부 독자용 |
| `src/CLAUDE.md` + `src/{api,auth,db,engine,engine/strategies,models,realtime,routes}/CLAUDE.md` (9) | 디렉터리 정본 |
| `frontend/CLAUDE.md` | 프론트 정본 |
| `docs/architecture.md` | 흐름 도식 (실제로 변했을 때만) |
| `docs/HARNESS_CHANGELOG.md` | verbatim 누적 (행 추가만) |
| `docs/backtest-monitoring.md` | 외부 통합(백테스트 MCP·매크로 레짐) 운영 가이드 |
| `_workspace/00_URGENT_WORKLIST.md` | 열린 과제 정본 |
| `_workspace/00_leader_trading_rules.md` | 매매 규칙 정본 (`DEFAULT_PARAMS` 변경 시 동기화 의무) |
| `.claude/agents/*.md` · `.claude/skills/**/SKILL.md` · `.claude/commands/*.md` | 하네스 구성 |

**전용 `CLAUDE.md` 가 없는 코드 디렉터리** (누락이 반복되는 지점): `src/services/` · `src/middleware/` ·
`tools/` · `e2e/`. 이 넷은 상위 문서(`src/CLAUDE.md` 또는 루트 `CLAUDE.md`)가 정본이므로 **거기를 본다**.

### 모듈 누락 자가 점검 (모드 B 필수)

디렉터리 정본은 그 디렉터리의 모듈을 **빠짐없이** 담아야 한다. 기계적으로 확인한다:

```bash
for f in src/engine/*.py; do b=$(basename $f .py); [ "$b" = "__init__" ] && continue;
  grep -q "$b" src/engine/CLAUDE.md || echo "누락: $b.py"; done
```
`src/{api,db,engine,models,realtime,routes}` 각각에 같은 검사를 돌린다.
(2026-09-07 실측으로 engine 4건·routes 1건·middleware 1건이 이 검사로 드러났다.)

**손대지 않는 영역**:
- `docs/kis/` — KIS 공식 API 스펙. 코드 동기화 대상 아님.
- `docs/architecture.md` — 시스템 흐름이 실제로 변한 경우에만 갱신 (도식·시퀀스 보존).
- `docs/HARNESS_CHANGELOG.md` — verbatim 누적 이력. 신규 사이클 행 추가만, 기존 행 재작성 금지.

---

## 3. 코드 ↔ 문서 대조 체크리스트

각 후보 문서를 Read 하고, **코드에서 다음 사실을 추출해** 문서 기술과 1:1 대조한다. 어긋난 항목을 분류한다.

| # | 사실 유형 | 추출법 | 흔한 드리프트 |
|---|----------|--------|--------------|
| 1 | **함수/클래스 시그니처** (이름·인자·반환 타입) | `grep -n "^def \|^async def \|^class "` | 문서가 초기 설계안 그대로 (인자/반환 타입 불일치, 없는 함수 설명, 폐기 함수 잔존) |
| 2 | **모듈/파일 경로** | `find` / `ls` | 이동·삭제된 파일, 신규 모듈 누락 (예: `src/services/` 전용 문서 부재) |
| 3 | **상수·임계값** (`TIME_*`, `MAX_*`, TTL 등) | `grep -n "= [0-9]"` | 코드에서 값 바뀐 뒤 문서 미반영 |
| 4 | **시각** (스케줄) | scheduler `TIME_*` | 시각 변경 후 README 스케줄 표 미갱신 |
| 5 | **단위** (원/백만원/억원/천주 등) | 코드 주석 + 실제 연산 (`// 1_000_000` 등) | ⚠️ **코드·문서가 함께 틀릴 수 있음 → §4 의미 검증 필수** |
| 6 | **TR_ID** | `settings.get_tr_id` / `grep TR_ID` | 누락·오타 |
| 7 | **DB 스키마** (컬럼·PK·인덱스) | `supabase/migrations/*.sql` | 마이그레이션 추가 후 CLAUDE.md DB 표 / README 마이그레이션 목록 미갱신 |
| 8 | **라우트 경로** | `src/routes/*` `@router` | README API 엔드포인트 표 누락 |
| 9 | **폐기 잔존** | 문서에 적힌 함수/패턴을 `grep` → 코드 0건이면 잔재 | 삭제된 함수·패턴이 문서에 남음 |

---

## 4. 의미 사실 검증 (코드 텍스트만으로 부족한 것)

단위·임계·스키마 같은 **의미적 사실**은 코드를 읽어도 "선언된 가정"이 맞는지 확인 못 한다. 코드와 문서가 **함께 틀린** 경우(예: 둘 다 "hts_avls=백만원"인데 실제 억원)는 정적 대조로 못 잡는다.

이런 항목은 **외부 사실로 교차검증**한다:
- **단위/실데이터 분포** → 운영 DB 실측 (Supabase MCP READ-ONLY). 예: `실제시총(원) ÷ 컬럼값 = 10^8 → 억원 확정`.
- **KIS API 응답 의미** → KIS MCP (`kis-mcp-query` 스킬). 응답 필드 단위·정의 정본 인용.

**중요 — 코드 결함 발견 시**: 의미 검증에서 "문서뿐 아니라 코드도 틀렸다"가 드러나면, **문서만 고치지 말 것**. 이는 sync-docs 범위를 벗어난 코드 결함이다. 문서에는 (a) 확정된 사실을 반영하되, (b) 코드 결함을 **별도로 사용자에게 보고**하고 team-leader 시정 사이클을 권고한다. (sync-docs 가 코드를 직접 고치지 않는다 — §금지)

---

## 5. 문서 수정

원칙:
- 코드 사실(경로·시그니처·상수·시각·단위·스키마)과 어긋난 부분을 **코드 기준으로** 정정.
- 문서가 이미 정확하면 손대지 않는다 (불필요한 리포맷·재배열 금지).
- 신규 개념은 기존 문서 톤·구조(간결·명사형·표/코드 블록)에 맞춰 흡수.
- 폐기된 개념은 문서에서도 제거.
- 추측·미래형 금지. "현재 코드 그대로"의 사실만.
- 의미 검증 미완(외부 확인 필요)인 항목은 단정하지 말고 ⚠️ 표시 + 검증 대기 명시.

Edit/Write 로 필요한 부분만 갱신한다.

---

## 6. 검증 + 분류 보고

수정 후:
- `git diff -- '*.md'` — 문서 변경 요약
- 코드 사실 ↔ 문서 라인 paired 요약 (어느 코드 사실이 어느 문서 라인에 반영됐는지)

사용자에게 **4분류**로 보고:
1. **정정** — 코드와 어긋나 고친 항목
2. **누락 보강** — 코드에 있으나 문서에 없던 것 (신규 모듈·라우트·컬럼·마이그레이션)
3. **폐기 제거** — 코드에 없는데 문서에 남았던 것
4. **의미 불일치(검증 필요/완료)** — 단위·임계 등 외부 검증 항목 + **코드 결함 의심 시 별도 플래그**

손대지 않은 후보 문서는 그 이유를, `_workspace/00_leader_trading_rules.md` 등 추가 동기화 필요 항목은 함께 안내.

---

## 7. 커밋

빈 변경(문서 갱신 불필요)이면 커밋하지 말고 보고만 한다.

커밋 주의:
- 코드가 이미 별도 커밋이고 문서만 남았다면 문서 단독 커밋.
- 코드가 unstaged 면 묶을지/분리할지 사용자에게 짧게 확인.
- 메시지: 한국어, 1줄 제목 + 본문. "왜"가 코드 커밋과 같다면 반복 말고 "코드 사실 동기화" 관점으로.
- `--no-verify` / `--no-gpg-sign` 금지. 훅 실패 시 원인 진단 후 재시도.
- HEREDOC 으로 줄바꿈 보존.

```
git commit -m "$(cat <<'EOF'
docs: <한 줄 요약>

- <세부 변경 1>
- <세부 변경 2>

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

push 후에는 `gh run list` 로 CI/Deploy 상태 확인 (fail 시 즉시 hotfix — 무시 금지).

---

## 금지 사항
- `docs/kis/` 하위 KIS 공식 스펙 md 수정 금지.
- **코드 수정 금지** — 이 커맨드의 범위는 "문서를 코드에 정합"이지 코드 변경이 아니다. 코드 결함을 발견하면 문서에 반영(확정 사실)·플래그하고 **사용자/team-leader 에 보고**, 코드는 손대지 않는다.
- 추측성·미래형으로 문서 채우지 말 것. 현재 코드의 사실만.
- 의미 검증(단위·임계)이 안 끝난 항목을 단정 금지 — ⚠️ 검증 대기로 표기.
- `docs/HARNESS_CHANGELOG.md` 기존 행 재작성 금지 (신규 사이클 행 추가만).
