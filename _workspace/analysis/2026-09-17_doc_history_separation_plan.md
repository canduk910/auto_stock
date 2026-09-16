# 문서 덧칠 정리 — 정본/이력 분리 개편 계획서 (승인용)

- 작성일: 2026-09-17 · 기준 HEAD `a4580b6` · 읽기 전용 검사 결과를 바탕으로 작성(파일 변경 0)
- 사용자 원칙(원문): "문서는 덧칠해서 누더기로 만드는게 아니라 **무조건 현재 상태로 관리**하고, 이력이 필요하다면 **별도 history파일을 분리생성**해서 관리해야해."
- 발단: 루트 `CLAUDE.md` 의 "20:20/화 20:30 루틴" 을 "목 20:30 (09-09 화→목 이설, 종전 표기 '화' 는 09-05 시점 값)" 으로 고친 것 — 정확히 금지된 덧칠. 현재 상태만 남기면 "목 20:30 루틴" 이다.

용어 한 줄:
- **정본** = 지금 이 시스템이 어떻게 동작하는지만 적힌 문서(`CLAUDE.md` 들, `README.md`, `docs/architecture.md` 등).
- **history** = "왜 그렇게 됐나, 전에는 어땠나" 를 적는 별도 파일. 정본에서 걷어낸 문장이 여기로 간다.
- **CHANGELOG** = `docs/HARNESS_CHANGELOG.md`. 사이클(작업 단위)별 보고 원문. 이미 있고 계속 그대로 둔다.
- **가드/핀** = 문서의 특정 문장이나 파일 지문(sha)이 바뀌면 붉어지는 자동 테스트. 문서를 고치면 같이 손봐야 하는 비용.

---

## §1 한눈에

| 항목 | 값 |
|---|---|
| 검사 대상 | 정본 15파일 · 9,738행 · 1,407 KB |
| 덧칠 총수 | **426건**(파일별 합은 범위가 겹쳐 약 440) |
| 처분 분류 | **A 현재형으로 다시 쓰기 268 · B history 로 이동 141 · C 삭제 233** (한 건이 둘 이상에 걸릴 수 있음) |
| 정리 후 예상 | **≈6,200행 · ≈760 KB** (행 −36% · 용량 −46%) |
| history 로 가는 양 | ≈300~350 KB / 8~10 파일. 나머지 ≈300 KB 는 CHANGELOG 와 글자까지 같아 삭제만 한다 |
| 걸리는 작업량 | **커밋 6개 · 작업 세션 5~6회 · 달력 3~4일**(src 아래 문서는 장외 창에만 push 가능해서 날짜가 늘어난다) |
| 승인이 따로 필요한 곳 | **1파일** — `src/realtime/CLAUDE.md`(8영역 지문 핀 4곳) |

파일별 분포:

| 파일 | 행 · 용량 | 덧칠 | 정리 후 | 핵심 증상 |
|---|---|---|---|---|
| `CLAUDE.md`(루트) | 278 · 122 KB | 32 | ≈250 · **≈55 KB** | 하네스 이력표 15행이 파일의 38.5%(47 KB), CHANGELOG 와 100% 중복. 배포 절이 사이클 보고서 4편. 자기모순 4건(일봉 16:00 vs 20:30 · 6전략 vs 7전략 · Supabase vs RDS · 배포 창) |
| `src/engine/CLAUDE.md` | 988 · 290 KB | 106 | ≈500 · **≈120 KB** | 모듈 맵 84행이 90 KB — 모듈당 한 줄이 그 모듈의 변경 로그. 86~659행은 사이클 절 15개(CHANGELOG 중복). 신·구 충돌 5건(TaskKey 4 vs 5 등) |
| `_workspace/00_leader_trading_rules.md` | 2,856 · 286 KB | 114 | ≈1,100 · **≈110 KB** | 1311~2856행이 작업 로그. P0 "매수 전면 차단" 이 현재형으로 남아 있음(08-28 종결됨). 평문 비밀값 1건 |
| `frontend/CLAUDE.md` | 834 · 107 KB | 25 | ≈430 · **≈58 KB** | StockMaster 절 283행이 사용자 보고·근본원인 서사. 가드 0 |
| `README.md` | 913 · 107 KB | 19 | ≈890 · **≈98 KB** | 꼬리표·존재하지 않는 기능(원자 전환) 행 |
| `docs/architecture.md` | 1,560 · 119 KB | 30 | ≈1,400 · **≈100 KB** | "최신 cycle278" 류 거짓 시점 · 4모드 매수 가드(실제는 관찰 전용) · 자기 편집 서술 |
| `src/engine/strategies/CLAUDE.md` | 377 · 93 KB | 29 | ≈230 · **≈42 KB** | kojiro 행 7.5 KB · 공통 패턴 12문단이 이력 |
| `src/db/CLAUDE.md` | 369 · 79 KB | 25 | ≈290 · **≈50 KB** | PostgREST 시절 서술 잔존 · 16:10 정산(현 21:30) |
| `src/realtime/CLAUDE.md` 🔴 | 567 · 62 KB | 34 | ≈340 · **≈38 KB** | CRITICAL-1 철회 논증 36행 · §cycle264 관측 73행. **sha 핀 4곳** |
| `src/api/CLAUDE.md` | 317 · 59 KB | 12 | ≈240 · **≈30 KB** | 단위 확정 경위 43행 · `hts_avls` 억원/백만원 모순 |
| `src/routes/CLAUDE.md` | 140 · 52 KB | 17 | ≈136 · **≈39 KB** | 필드 추가 사이클 꼬리표 · 레짐 "실차단" (실제 표시 전용) |
| `docs/backtest-monitoring.md` | 346 · 17 KB | 12 | ≈200 · **≈9.5 KB** | Phase·예정일 · MDD 확정 절차 서사 |
| `src/auth/CLAUDE.md` | 소형 | 3 | 동일 | 소제목이 사이클 번호 |
| `src/CLAUDE.md` · `src/models/CLAUDE.md` | 소형 | 0 | 변경 0 | — |

---

## §2 원칙을 규약으로

### 2-1. 루트 `CLAUDE.md` 에 넣을 문장 초안 (「하네스」 절 바로 아래, 6줄)

> ### 문서 규약 — 정본은 현재 상태만, 이력은 history 파일
> - 정본(`CLAUDE.md` 전부 · `README.md` · `docs/architecture.md` · `docs/backtest-monitoring.md` · `_workspace/00_leader_trading_rules.md`)에는 **지금 동작하는 규칙만** 현재형으로 적는다. "종전엔 X 였다", "cycleN 이 Y 로 바꿨다", 취소선, "(구)/(신)", "이 문장은 N 시점 기록" 은 쓰지 않는다.
> - 바뀐 경위·실측 수치·결정 근거가 필요하면 **`docs/history/<정본 이름>.history.md`** 에 append 하고, 정본은 새 값으로 **덮어쓴다**. history 파일은 고치지 않는다(append-only).
> - 남기는 것 = 값의 출처 사이클 번호(`K=2.0(cycle242)`) · 금기와 그 이유 **한 문장**(`X 금지 — 2026-08-08 Y 사고`). 이유가 한 문단을 넘으면 history 링크로 줄인다.
> - 사이클별 보고 원문은 `docs/HARNESS_CHANGELOG.md` 하나에만 둔다. 정본 안에 이력 표를 두지 않는다.
> - 같은 사실을 두 문서에 적지 않는다. 두 곳이 필요하면 한 곳은 링크다.
> - `/sync-docs` 의 덧칠 검사(아래)가 0 이어야 커밋한다.

### 2-2. `/sync-docs` 에 넣을 검사 초안

정본 목록을 돌며 아래 패턴을 센다. **0 이어야 통과**. history·CHANGELOG·`_workspace/{red,analysis,domain_consult,reports,forensics}` 는 검사 대상이 아니다.

| 패턴(정규식) | 잡는 덧칠 유형 | 오탐 주의 |
|---|---|---|
| `종전(에는\|엔\| 표기\| 값)?` | 시점 주석 | 코드 식별자 인용(`advance_if_passed`) 무관 |
| `~~[^~]+~~` | 취소선 폐기 표시 | — |
| `\(구\)\|\(신\)\|구 서술\|구 결정` | 신·구 병존 | — |
| `당시(의)? \|시점 값\|시점 기록\|시점 서술` | 시점 주석 | "당시" 가 사고 서술의 일부인 금기 문장은 history 로 |
| `→ 완료\|→ 폐기\|→ cycle\d+ (완료\|착지)` | 인계 목록 이행 표시 | — |
| `이제 (더 이상\|는)?` | 변경 접속 | 규칙 문장에서 "이제" 는 거의 항상 덧칠 |
| `(정정\|갱신) —\|— \d{4}-\d{2}-\d{2} 정정` | 정정 각주 | — |
| `\|\s*20\d\d-\d\d-\d\d\s*\|\s*.*cycle\d+.*\|` (표 행) | 정본 안 이력 표 | CHANGELOG 제외 |
| `\d+ PASS\|\d+,\d+ PASS\|0 failed\|diff 0` | 검증 수치(git 이 갖고 있음) | — |

실행 스케치(`.claude/commands/sync-docs.md` 에 추가):
```bash
PAT='종전|~~[^~]+~~|\(구\)|\(신\)|구 서술|구 결정|시점 값|시점 기록|→ 완료|→ 폐기|이제 더 이상| PASS|0 failed|diff 0'
for f in CLAUDE.md README.md docs/architecture.md docs/backtest-monitoring.md \
         src/CLAUDE.md src/engine/CLAUDE.md src/engine/strategies/CLAUDE.md \
         src/api/CLAUDE.md src/realtime/CLAUDE.md src/db/CLAUDE.md src/routes/CLAUDE.md \
         src/auth/CLAUDE.md src/models/CLAUDE.md frontend/CLAUDE.md _workspace/00_leader_trading_rules.md; do
  n=$(grep -cE "$PAT" "$f"); [ "$n" -gt 0 ] && echo "DOC_OVERPAINT $f $n"
done
```
첫 도입 시에는 "현재 값 → 0 으로 내려가는 것" 을 목표로 하고, 정리가 끝난 커밋부터 0 강제. `tests/unit/ast/` 에 같은 검사를 pytest 로 한 벌 더 두면 CI 가 막아 준다(별건 카드 §7-④).

---

## §3 history 구조

### 권고 = (나) 정본 파일별 `docs/history/<이름>.history.md`

| 안 | 장점 | 기각/채택 이유 |
|---|---|---|
| (가) CHANGELOG 하나에 다 넣기 | 새 파일 없음 | 기각 — 이미 309행 **1.55 MB** 단일 파일. 여기에 300 KB 를 더 얹으면 열기도 힘들고, "이 규칙이 왜?" 를 찾으려면 사이클 번호를 먼저 알아야 한다 |
| **(나) 정본별 history** | 정본을 읽던 사람이 **같은 이름**의 history 를 연다 — 색인이 필요 없다. CHANGELOG(사이클축)와 역할이 갈려 중복이 아니다 | **채택** — "다음 사람이 어디를 열지 자명한가" 에 유일하게 답한다 |
| (다) 주제별(채널·토큰·배포…) | 한 주제를 한 파일에서 | 기각 — 주제 분류표가 또 하나의 드리프트 원천. 「채널」만 해도 realtime·engine·routes·README 네 정본에 걸친다 |

### 규약

1. 경로 = `docs/history/` 한 곳. 이름 = 정본 경로를 `-` 로 이은 것.
   - `CLAUDE.history.md` · `src-engine-CLAUDE.history.md` · `src-engine-strategies-CLAUDE.history.md` · `src-db-CLAUDE.history.md` · `src-realtime-CLAUDE.history.md` · `src-api-CLAUDE.history.md` · `src-routes-CLAUDE.history.md` · `frontend-CLAUDE.history.md` · `docs-architecture.history.md` · `docs-backtest-monitoring.history.md` · `workspace-00_leader_trading_rules.history.md`
   - `_workspace/` 정본의 history 도 `docs/history/` 에 둔다 — `_workspace/` 는 시점 문서 영역이라 거기 두면 "시점 문서 vs 이력" 이 흐려진다.
2. 항목 형식:
   ```
   ## <정본 절 제목 그대로>
   ### 2026-09-05 cycle255 — TLS 1단계 준비 경위
   (정본에서 옮긴 원문 그대로, 편집 금지)
   → CHANGELOG: cycle255 행
   ```
   규칙에서 "왜?" 가 궁금한 사람은 절 제목으로, 사이클 사고를 재구성하는 사람은 CHANGELOG 로.
3. **append-only**. history 안의 낡은 문장은 고치지 않는다(이력이므로).
4. 정본 파일 **상단 1줄**만 `> 이력: docs/history/<이름>.history.md`. 절마다 링크를 달지 않는다(그게 다시 덧칠 통로가 된다).
5. history 에 넣을 본문이 CHANGELOG 행과 글자까지 같으면 넣지 않고 삭제(C). 루트 이력표 15행, engine 86~659 사이클 절이 이 경우.
6. `.claude/commands/sync-docs.md` 정본 목록에 `docs/history/*.history.md — 이력(append-only, 검사 대상 아님)` 1행 추가. 기존 AST 문서 스캐너(`_LIVE_DOCS`·`_DOC_FILES`)는 정본만 읽으므로 무접촉 — 단, **앞으로 `docs/**` 글롭으로 스캔하는 가드를 만들지 않는다**(만들면 history 가 죽은 심볼 가드에 걸린다).
7. 비밀값(`DKSTOCK_PASSWORD=AUTOSTOCK1`, rules L1429)은 history 로도 옮기지 않고 삭제한다.

---

## §4 파일별 개편 카드

표기: "전 → 후" 는 대표 3건. 행 번호는 현재 파일 기준.

### 4-1. `CLAUDE.md`(루트) — 32건 · 278행/122 KB → ≈250행/≈55 KB

| 대표 3건 | 전 | 후 |
|---|---|---|
| L84-105 하네스 표 | 15행 47 KB, 행당 최대 7,158자 | 절 삭제 + "이력은 CHANGELOG 가 유일한 정본" 2줄 (**§7-① 결정 카드**) |
| L235 `stock_master_daily` | "매일 16:00 KST 적재 … 사이클 172 … 사이클 196 …" | "매일 **20:30** KST 적재(`TIME_STOCK_MASTER_DAILY_LOAD`)" — 코드와 L233·L264 와 정합 |
| L261-262 TLS | "1단계 **준비** … 아직 443 을 열지 않는다"(09-05 시점) | "`auto.dkstock.cloud` **가동 중**(1단계 09-05 · 2단계 09-08). 스위치 = `.tls_enabled`/`.tls_stage2`. 301 · HSTS 86400 · 자격 회전 완료" 5줄 |

- history 로: P0-1 마커 반전 시점 · 09-06 모델 크레딧 사고 · 08-04 3.2유닛 실측 · max_lot 4.94/15.61배 실측 · 09-04 LTV 000500 사고 · KRX OpenAPI 오판 경위 상세 · TLS 준비 절차 전문 · Compose v5.1 LastTagTime 재현 · cycle232 donchian 소실 (≈8 KB)
- 삭제(C): 이력표 · L263 cycle279 계획 · L277 `src/workers`(존재하지 않음) · "종전 20:10" · "7곳→15곳" · 사이클 I 경위 2곳 중 1곳
- 가드: sha 핀 **없음**. 유지 조건 = `test_c283_12`(`20:00~21:35` 존재 · `20:20~익일 07:45`/`20:00~20:15` 부재) · `test_c283_12b`(`21:35` 포함 줄 ≥2 → L79·L264 둘 다 창 문구 유지) · `test_c283_10b`(`cycle283` 존재 — L79·L264 인용으로 통과). `tools/test_impact/manual_overrides.yaml` 이 통합 테스트 풀을 돌린다(시간 비용만).
- 재발 차단: 표 갱신을 지시하는 문장은 리포 전체에서 **2곳**(루트 표 머리말 · `.claude/commands/sync-docs.md:100`). 같은 커밋에서 둘 다 지운다.

### 4-2. `src/engine/CLAUDE.md` — 106건 · 988행/290 KB → ≈500행/≈120 KB

| 대표 3건 | 전 | 후 |
|---|---|---|
| L27 `market_operation_monitor` 6,379자 | 사이클 149 → 186 → 214 → "⚠️ 07-25 정정 — cycle214 완전 미작동" 순으로 층층 | 수신·상태 추적 역할·API·금기 5줄. 송신은 L83 leaf 가 정본이라 삭제 |
| L28 refresh_progress | "TaskKey **4** 확장" | **5키**(코드 `refresh_progress.py:34`, L93 과 모순 해소) |
| L221-227 사이클 172 검증 절 | git diff 0 · +219L · 회귀 27 · 3,161 PASS | 절 삭제. 🔴 정확 문자열 `TIME_STOCK_MASTER_DAILY_LOAD = time(20, 30)` 은 **파일에 이 줄뿐** → L508 대체문에 그대로 옮긴다 |

- 구조 처방: (a) 모듈 맵 = 모듈당 "역할·API·불변식·금기(근거 1문장)" (b) 86~659행 사이클 절 15개 → 현행 규칙 절 7개(`_wait_until` 계약 · 일봉 적재(유니버스·backfill·오늘봉 필터·보호 종목) · 저녁 순서 TIME_* · funnel 캡처 · 진입 차단 7건 · basics/master 적재 · 체결단가) (c) 중복 항목(kojiro_gap_observe 42·57행) 통합.
- history 로: HTTP/2 폭주·basics 17분 풀런 배경 · stale-1/5 고착 · 07-25 ImportError 117건/일 · cycle250 무한 hang · 토큰 269→270-B→270-C · LLM 훅 신호→주문 이동 이유 · 마커 3세대 반전 · 176 raw 머지 6/3573 · 05-20 OPSP0002 · cycle241 통계 (≈50 KB)
- 가드: sha 핀 **없음**(8영역 글롭 밖). 정확 문자열 4 = `TIME_STOCK_MASTER_DAILY_LOAD = time(20, 30)` · `` `_DAILY_LOAD_TODAY_BAR_CUTOFF`(= `time(20, 0)` `` · `| \`TIME_SETTLEMENT\` | 21:30 |` · 킬스위치 키 2(`order_exchange_clock_mode`·`after_market_exit_division`). 존재 = `TIME_SESSION_START_CUTOFF` · `TIME_METRICS_SNAPSHOT` · `cycle257` · (`gap_hold` 언급 시) `cycle295`. 부재 = `time(15, 40)` · `time(18, 10)` · `장중 킬스위치 없음` · `ρ축은 조용히 통과한다` · `20:10  _settle()` · 죽은 심볼 5종. **조건부 3건(`18:10`엔 `종전` / `상호배타`엔 `cycle254` / `미등재`엔 `cycle290`)은 그 단어 자체를 안 써서 회피.**

### 4-3. `_workspace/00_leader_trading_rules.md` — 114건 · 2,856행/286 KB → ≈1,100행/≈110 KB

| 대표 3건 | 전 | 후 |
|---|---|---|
| L815-818 · L964-966 P0 | "BFB·VCP 매수 **전면 차단**" 현재형 | cycle228 게이트(tick_volume 실측+래치+추격 상한) 현재형 — **가장 위험한 신·구 병존**(08-28 종결된 사실이 살아 있음) |
| L359-370 momentum 손절 | 시계열 + "영구 영속" 반복 | "손절값 정본 = DB `strategy_config.params`" 1문장(메모리 no_redundant_phrases 위반 해소) |
| L1311-2856 작업 로그 | 사이클 1~48 옵션 비교·자율 결정·커밋 지시문 | 통째 history 이동. 살아 있는 규칙만 추려 **§8 운영 규칙** 신설(≈40행: 레짐 4줄 · VB 보드별 손절 3줄 · 자문 payload 2줄 · 토글 DB 우선 2줄 · 로그 retention 4줄 · 보조 계좌 3줄 · 풀 분배 4줄 · `buy_block_mode` 표시 전용 2줄 · stale 임계 3값 · 5xx dedupe · 포트폴리오 리스크 3줄) |

- history 로: 07-20 kojiro 백테스트 PF · 08-18 Σ=2.97 비중 오염 · 09-04 잔여 노출 표 · MAX_SUBSCRIPTIONS 발단 · 백테스트 결함 A~D' 서사 · 파라미터 완화 경위 · 1311~2856 전체 (≈180 KB)
- 삭제(C): 커밋 5분할 지시문(1835-1844) · 사이클 22(루트·auth 정본 有) · 스테일 각주 · `STALE_FORCE_REREGISTER_AFTER`(08-19 삭제된 상수가 현행처럼 적힘) · 비밀값 L1429
- 가드: 없음. 유지 = `| \`TIME_SETTLEMENT\` | 21:30 |` · `TIME_SESSION_START_CUTOFF` · 키 3(`order_exchange_clock_mode`·`after_market_exit_division`·`open_price_scope_mode`, 전부 1~1400 에 있고 1311~1400 엔 0건 → 이동 안전). ⚠️ DEFAULT_PARAMS 사본(L890·L1043)의 "K축 우선, fail-open 시 백스톱" 주석은 cycle254 후 거짓 — 문서만 고치고 **소스 주석은 전략 7파일 sha 핀 → 별도 승인**(§7-⑤).

### 4-4. `src/engine/strategies/CLAUDE.md` — 29건 · 377행/93 KB → ≈230행/≈42 KB

| 대표 3건 | 전 | 후 |
|---|---|---|
| L159 kojiro 행 7.5 KB | 07-20 백테스트 · 273c 복원 · H-1 논거 | 규칙 2.5 KB + 파일명 `kojiro.py` 기재 |
| L3 | "2026-07 Phase 1 다크런치 `enabled=False`" | "운영 DB `enabled=True`·비중 30% 실매매 중, 코드 기본값만 False" |
| L213-215 volume-rank | 33→48→108 변천이 모순되게 병존 | `list_by_filter` 단일 서술 |

- history 로: open_entry_hold 20/20·53/93 Fisher · cycle274→276 이동 이유·`slip_bp` 반전 · 08-08 유니버스 확대 결정값 · T0~T4 자본 단계표 · 08-24 192820 사고 · 11,453건 폭주 실측 · box 필터 삭제 목록 (≈50 KB)
- 가드: 없음. 유지 = `open_price_scope_mode`(G-272-28f) · 킬스위치 키 2(G-290-5). 부재 = `fail-open 시에만` · `cap=backstop`(G-254-4d). sync-docs `.py` 자가 점검 = 표 행에 `bull_flag_breakout.py`·`donchian_swing.py`·`kojiro.py` 기재.

### 4-5. `src/db/CLAUDE.md` — 25건 · 369행/79 KB → ≈290행/≈50 KB

| 대표 3건 | 전 | 후 |
|---|---|---|
| L13/20/23-24 | PostgREST 매핑 서술 | asyncpg 계약만 |
| L118 | "16:10 정산" | 21:30 |
| L212-216 `list_by_filter` 10 KB | 사이클별 시그니처 변천 | 단일 시그니처(`sort_by` 포함, 코드 :523) |

- history 로: cycle276 B-2/B-4 · 7/3 크래시 · 사이클 72 2.89x 실측 · 필터 2종 경위 (≈28 KB)
- 가드: 없음. 유지 = `` `insert_log_report()` `` 백틱 행 + 같은 행 `ON CONFLICT`/`upsert`(test_c283_11b) · `supabase.py` · `pending_next_day_clear.py` 문자열(sync-docs 자가 점검) · `gap_hold_enabled` 언급 시 `cycle295` 동반(언급을 지우면 무관).

### 4-6. 🔴 `src/realtime/CLAUDE.md` — 34건 · 567행/62 KB → ≈340행/≈38 KB

| 대표 3건 | 전 | 후 |
|---|---|---|
| L147-182 CRITICAL-1 철회 36행 | 갭 홀드 도입→철회 논증 전문 | "15:30~16:00 완전 휴식, KRX 유지(cycle295)" 1문단 |
| L372-444 §cycle264 관측 73행 | 포렌식·추정치·"아직 열려 있는 것"(거짓) | REST 단일 출처와 정합한 12행 |
| L503-505 구독 표 | "H0NXCNT0 15:40~16:00 HIGH" | cycle295 후 거짓 → 정정 |

- history 로: 05-19 AES 격리 사고 11건 · 15:15 ratio 0.0% 사고 상세 · 2단계 규약 4항 · CRITICAL-1 논증 전문 · 자동 원복 3구멍 · 마커 반전 (≈8 KB — 채널 단계 이력은 전부 이 파일에 모은다)
- 가드 🔴: **sha 핀 4 dict**(`test_cycle222a3:497` · `test_cycle223:479` · `test_cycle223f:390` · `test_cycle226:1183`, 현재 전부 `061c5c5c…`) + `test_cycle276::test_c6_4c`(승인 집합에 이 파일 포함 — 항목 삭제 금지) + `test_cycle264 _ALLOWED_SRC:10`. **절차(한 커밋)**: 문서 재작성 → `shasum -a 256` → 4 dict 값 교체 + `# 📄 문서 전용 변경(덧칠 정리) — 프로덕션 영향 0` 주석 → 관련 pytest 6파일 초록. 문구 = `cycle257` 1회 이상 · 죽은 심볼 5종 0건. **8영역 글롭 = 사용자 승인 대상**(문서 전용이라도 규약상).

### 4-7. `src/api/CLAUDE.md` — 12건 · 317행/59 KB → ≈240행/≈30 KB

| 대표 3건 | 전 | 후 |
|---|---|---|
| L295-300 12.6 KB | 107→177 단위 확정 경위 | `inquire_stock_basics` 계약 + `hts_avls` **억원**(L299 백만원 모순 해소) |
| L35 화이트리스트 | 12개 열거 | **13개 전부**(`inquire-vi-status` 누락 시정) |
| L178-252 krx 대조표 | 112/115 대조 | 호출 규약 1문단 |

- history 로: 사이클 76 5.80x 실측 · 164 false alarm·166 실측 (≈3 KB). 가드: 없음. 「단일 호출 최대 100일」 문장 유지(docstring 인용).

### 4-8. `src/routes/CLAUDE.md` — 17건 · 140행/52 KB → ≈136행/≈39 KB

| 대표 3건 | 전 | 후 |
|---|---|---|
| L82/87/94-95 레짐 | "실차단" | 표시 전용(코드 정합) |
| L75 | `TICK_TR_ID` 단일 | 채널별(코드 :580~613) |
| L79-80 gap_hold 3키 | 철회 서술 | 언급 제거 → G-D3h 무관 |

- history 로: J4/N1 배경 · D6 upsert 경위 (≈2 KB). 가드: `20:00~21:30` 리터럴 유지(test_c283 :320).

### 4-9. `frontend/CLAUDE.md` — 25건 · 834행/107 KB → ≈430행/≈58 KB

| 대표 3건 | 전 | 후 |
|---|---|---|
| L221-503 StockMaster 283행 | 사용자 보고·근본 원인·13분 39초 실측·결정 Q 번호 | 화면 단위 ≈110행 |
| L604-636 인증 취소선 | nginx 상세까지 이중 정본 | 규칙 2줄 + 루트 링크 |
| L113-124 Dashboard | VB 8단계·violet·20:10 자기모순 | 현행 |

- history 로: 깜박임 실측 · ΔE 거리 · StockMaster 서사 · cycle246/247 실측 (≈20 KB). 가드: **없음**(읽는 테스트 0).

### 4-10. `README.md` — 19건 · 913행/107 KB → ≈890행/≈98 KB
- 꼬리표(647·652·657·670-673) · 존재하지 않는 "원자 전환" 행(494) · 사이클 I 3곳→1곳 · 종전 창(827-829) · gap_hold 런북(487·557) 제거. history 0(CHANGELOG 有). 가드: 죽은 심볼 0건 · `openssl passwd -stdin` 레시피(L739) 유지(test_cycle243 D-15b).

### 4-11. `docs/architecture.md` — 30건 · 1,560행/119 KB → ≈1,400행/≈100 KB
- 도식 시각 코드 정합(15:40·20:00·20:30) · "최신 cycle278" 거짓 시점 · 4모드 매수 가드→관찰 전용(`soft_multiplier` 호출자 0 재확인 후) · 13·14장 사이클축→주제별 · 자기 편집 서술 삭제 · L35 TLS 부재→443 가동. history ≈5 KB. 가드: 죽은 심볼 0건 · 도식 `21:30`·`20:30` 존재 · `20:10  _settle()` 부재.

### 4-12. `docs/backtest-monitoring.md` — 12건 · 346행/17 KB → ≈200행/≈9.5 KB
- Phase·예정일 제거 · `.env` sed 절차→Settings 토글 정본 · MDD "양수 절대값, diffSignInverted" 3줄 · 응답 키 확정 스키마 표. history: Case A 폐기 경위 · 05-16 실측 표(≈4 KB). 가드 없음.

### 4-13. 소형 — `src/auth/CLAUDE.md`(소제목 사이클→규칙 이름, 3건) · `src/CLAUDE.md`·`src/models/CLAUDE.md`(변경 0)

---

## §5 실행 순서

원칙: 가드가 없고 배포에 안 걸리는 것부터. 각 단계 = **1커밋**, 커밋 뒤 `python -m pytest tests/unit/ast tests/unit/engine/test_cycle283_evening_window.py tests/unit/engine/test_cycle273_daily_load_1810.py -q --log-level=DEBUG` 초록 + `/sync-docs` 의 `.py` 단어경계 자가 점검 통과가 조건.

| # | 커밋(한글 메시지) | 내용 | 배포 영향 | 승인 | 순서 이유 |
|---|---|---|---|---|---|
| 0 | (결정) | **§7 카드 ①②③ 회신** | — | 사용자 | 표 처분·history 구조가 1번 커밋의 모양을 정한다 |
| 1 | `docs: history 디렉터리 신설 + 정본 규약 명문화 + 루트·docs 덧칠 정리` | `docs/history/` 생성(원문 verbatim 이관) · §2-1 규약 문장 · 루트 `CLAUDE.md`(표 처분은 카드 ① 결과대로) · `README.md` · `docs/architecture.md` · `docs/backtest-monitoring.md` · `sync-docs.md` 2곳(표 갱신 문구 삭제 · history 1행 추가) | **없음**(`paths-ignore`) | 사전 승인 범위 | 가드 3건뿐, 재시작 0, 효과 최대(−47 KB 표) |
| 2 | `docs: 매매 규칙 정본 현행화 + 작업 로그 history 이관` | rules 1311~2856 이동 · §8 신설 · 1~1310 정리 · 비밀값 삭제 | 없음 | 사전 승인 범위(값 변경 0, 서술만) | P0 "전면 차단" 거짓 현재형 제거가 급하다 |
| 3 | `docs: src 정본 5파일 덧칠 정리 (engine·strategies·db·api·routes·auth)` | 정확 문자열 4 + 존재/부재 조건 유지하며 재작성 | **다음 배포 full**(`BACKEND_RE` 첫 대안이 `src/`) | 사전 승인 범위 · **장외 창 push**(15:30~16:00 · 21:35~07:45) | 한 커밋으로 묶어 재시작 1회만 |
| 4 | `docs: src/realtime/CLAUDE.md 정리 + sha 핀 4곳 재핀` | 문서 + 4 dict 값 교체 **같은 커밋** | 다음 배포 full | 🔴 **8영역 사용자 승인** | 3번과 같은 창에 태워 재시작을 합친다 |
| 5 | `docs: frontend/CLAUDE.md 화면 단위 재편` | 프론트 정본 | 없음(문서만 → none) | 사전 승인 범위 | 가드 0, 급하지 않음 |
| 6 | `test: 덧칠 관례 가드 5건을 부재 단언으로 반전 + 덧칠 패턴 검사 신설` | §7-④ | 없음 | 사전 승인 범위(테스트 전용) | 정리가 끝나야 부재 단언이 초록이 된다 |

3·4 는 같은 날 같은 창에서 연속 push 하면 backend 재시작이 1회로 끝난다(cycle248 누적 diff 판정). 그 창까지 `.deployed_sha` 대비 diff 를 `git diff --name-only <마커> HEAD` 로 미리 확인한다.

---

## §6 하지 말 것

1. **시점 문서는 손대지 않는다** — `_workspace/red/*` · `analysis/*` · `domain_consult/*` · `reports/*` · `forensics/*` · `docs/HARNESS_CHANGELOG.md`. 이력 그 자체다.
2. **금기의 근거 문장은 지우지 않는다** — "X 금지 — 2026-08-08 KRX OpenAPI 3,577→60 사고" 처럼 한 문장은 정본에 남긴다. 세 문단이면 한 문장 + history.
3. **식별자·상수·마커 이름은 인용 대상이다** — `TIME_STOCK_MASTER_DAILY_LOAD = time(20, 30)` 같은 정확 문자열은 가드가 잡고 있다. 문장을 다듬다 백틱·공백 하나를 바꾸면 붉어진다. §4 의 "정확 문자열" 은 복사해서 옮긴다.
4. **`src/realtime/CLAUDE.md` 는 핀 갱신과 한 커밋** — 문서만 먼저 밀면 그 사이 CI 가 붉다.
5. **history 를 편집하지 않는다** — 옮긴 원문에 "정정" 을 덧붙이고 싶어지면 그건 정본을 고쳐야 한다는 신호다.
6. **값을 바꾸지 않는다** — 이번 작업은 서술 정리다. 파라미터·시각·비중 숫자가 코드와 다르면 **코드 쪽 값**으로 문서를 맞추되, 어느 쪽이 맞는지 불확실하면 계획서에 적고 사용자에게 묻는다(예: architecture §13.3 4모드).
7. **8영역 규약을 문서라고 건너뛰지 않는다** — "관측 로그 한 줄도 승인" 이 규약이고 `src/realtime/CLAUDE.md` 가 그 글롭 안이다.
8. **`docs/**` 글롭 스캐너를 새로 만들지 않는다** — history 가 죽은 심볼·구 시각 가드에 걸린다.
9. **소스 주석은 이번에 손대지 않는다** — 전략 7파일 sha 핀(`_STRATEGY_PINS`). 문서 사본만 고친다.

---

## §7 사용자 결정 카드

### ① 루트 `CLAUDE.md` 하네스 이력표 처분

| 안 | 내용 | 원칙 부합 | 비용 | 권고 |
|---|---|---|---|---|
| **(i)** | 표 제거 + "이력은 CHANGELOG 가 유일 정본" 2줄 | ✅ 정본에 이력표 없음 | −47 KB · sync-docs 문구 1줄 · `test_c283_10b` 는 통과하나 의도가 죽어 별건 정리 | **권고** |
| (ii) | 표 유지, 진짜 80자 한 줄 15행 | ⚠️ 여전히 정본 안 이력표. 80자 규칙은 표가 생긴 이래 한 번도 지켜진 적 없음 — 지키려면 행 길이 가드를 새로 만들어야 함 | 15행 재작성 + 가드 신설 | 기각 |
| (iii) | 현행 유지 | ❌ | 0 | 기각 |

### ② history 구조

| 안 | 권고 |
|---|---|
| (가) CHANGELOG 하나 | 기각 — 1.55 MB 단일 파일, 사이클 번호를 알아야 찾음 |
| **(나) 정본별 `docs/history/<이름>.history.md`** | **권고** — 열 파일 이름이 정본 이름에서 자동으로 나온다 |
| (다) 주제별 | 기각 — 주제 분류표가 새 드리프트 원천 |

### ③ 범위 — 이번에 전부 vs 큰 파일 3개 먼저

| 안 | 내용 | 장단 |
|---|---|---|
| (A) 전부(커밋 6개, 3~4일) | §5 전체 | 한 번에 끝나고 §2-2 검사를 0 으로 켤 수 있다. realtime 승인 1건 필요 |
| **(B) 큰 3개 먼저**(루트 · engine · rules = 덧칠 252건, 용량 698 KB → ≈285 KB) | 커밋 1·2·3(engine 만) | 효과의 60% 를 위험 낮은 곳에서 먼저. 나머지는 다음 주. 단 §2-2 검사는 "감소 목표" 로만 켠다 | **권고 — 단, 커밋 3 은 engine 하나만이라도 full 배포라 장외 창 필요** |
| (C) 루트 하나만 | 커밋 1 | 가장 빠르지만 engine 290 KB·rules 의 거짓 현재형(P0 전면 차단)이 남는다 |

### ④ 덧칠 관례 가드 5건 반전(테스트 전용 커밋, 사전 승인 범위 — 동의만 확인)
- `test_gd3h`("식별자를 지우지 말고 철회 표시를 달아라") → 정본 5파일에서 `gap_hold_enabled`/`nxt_gap` **부재** 단언
- `test_cycle257::…records_removal` → `cycle257` 조건 유지, docstring 을 "history 링크로 대체" 로
- `test_g290_5b`(`미등재` 줄에 `cycle290`) → `미등재` 부재
- `test_g254_4a`(`상호배타`+`min` 줄에 `cycle254`) → `상호배타` 부재
- `test_c283_11c`(`18:10` 줄에 `종전`) → `18:10` 부재 · `test_c283_10b` 삭제(`test_c283_10` 이 CHANGELOG 를 이미 본다)
- 추가: §2-2 덧칠 패턴 검사를 pytest 로 한 벌

### ⑤ 별건(이번 범위 밖, 기록만)
- 소스 주석 정정(전략 7파일 `_STRATEGY_PINS`) — 코드 사이클에서 별도 승인
- `test_c283_12b` 완화(배포 창 문구를 루트 한 곳만 정본으로) — 지금은 두 곳 같은 짧은 문장으로 유지
- rules L1429 평문 비밀값은 git 이력에 남는다 — 키 회전 여부는 사용자 판단
- `architecture.md` §13.3 4모드 vs 관찰 전용 · `frontend/CLAUDE.md` L114 P0-1 "원인 확정" vs 종결 — 정리 커밋에 포함 권장

---

바닥글: 근거 = 2026-09-17 읽기 전용 전수 스캔(15파일) + `grep -rln "CLAUDE.md" tests/unit/ast/` 전수 + `shasum` 핀 위치 실측. 수치는 ±10% 추정치이며 실제 정리 커밋의 `wc` 로 대체한다.
