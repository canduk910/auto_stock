# cycle273-G 명세 — 주간 자문 **레벨 0(적용 후보 큐)** + "지금 UI 재사용 가능한가" (D4)

- 작성 2026-09-10 · tdd-engineer(그룹 2) · **읽기 전용 사이클**
- 사용자 결정(2026-09-10 목 19:5x) = **"4. D4 주간 자문 — 가장 낮은 단계로 진행.
  혹시 지금처럼 UI에서 간단하게 적용가능한지도 체크해줘."**
- 정본 = `_workspace/domain_consult/weekly_advice_auto_apply_20260910.md` §R4·카드① ·
  `_workspace/analysis/2026-09-10_cycle273_UD_load_and_ui.md` §D4
- 기준 트리 = **HEAD `1df6d7d`**
- 보류 Red = `…/scratchpad/pending_tests/cycle273g/test_cycle273_weekly_advice_level0.py`
  → DEST `tests/unit/routes/test_cycle273_weekly_advice_level0.py`

---

## 1. 레벨 0 의 정의 (자문 원문 전사)

> | 레벨 | 내용 | 승인 | 도입 시점 |
> |---|---|---|---|
> | **0** | **적용 후보 큐** — 파싱·전사·PUT 조립·기본값 대조·게이트 사전판정까지 자동. **적용은 사람이 항목 단위 체크.** | 항목마다 사람 | **지금 권고.** 이번 주 3키 전부 여기서 처리 |

승격 기준(원문): "레벨 0 을 돌리는 동안, 매주 '게이트가 통과시켰을 항목' 과 '사람이 실제로 체크한 항목' 의
집합을 나란히 기록한다. **4주 연속 불일치 0** 이면 승격을 검토한다."

> **레벨 0 은 "자동 적용" 이 아니다.** 사람의 손가락(항목별 체크 + 적용 버튼)은 그대로 남고,
> 없애는 것은 **값을 손으로 옮겨 적는 단계**뿐이다 — 자문의 "없앨 대상은 눈이 아니라 손가락" 과
> 사용자 질문("지금처럼 UI 에서 간단하게")은 **정확히 같은 것을 가리킨다.**

---

## 2. 사용자 질문의 답 — **예 (조건 4개)**

`Recommendations.tsx`(675L)의 키별 체크박스·적용 버튼과 `POST /api/recommendations/{id}/apply` 는
"행이 `parameter_recommendations` 에 `status ∈ {pending, partial}` 로 있으면" **자문의 출처를 묻지 않는다.**
⇒ **적용 UI 자체는 한 줄도 안 고치고 그대로 쓸 수 있다.** 단 아래 4개가 선행하고, **그중 2개는 사용자 결정**이다.

| # | 선행 조건 | 규모 | 승인 |
|---|---|---|---|
| **1** | `parameter_recommendations` 에 `source VARCHAR(16) NOT NULL DEFAULT 'daily'` 추가 | 가산형 마이그레이션 1개 | 사전 승인 범위 |
| **2** | UNIQUE 인덱스를 `(target_date, strategy_id, source)` 로 **교체**(신규 생성 → 구 인덱스 DROP) | 마이그레이션 1개 | 🔴 **DROP INDEX = 별도 승인**(사전 승인 범위는 "NULL 허용 ADD COLUMN·INDEX·신규 테이블" 까지) |
| **3** | `expire_pending_before` 가 `source='weekly'` 를 만료 대상에서 제외(또는 별도 TTL) | `db/parameter_recommendations.py` 1함수, 호출부 무접촉 | 사전 승인 범위(매매 행위 변경 0) |
| **4** | 루틴 → DB 적재 **경로** 결정 (§4 가/나/다/라) | 안에 따라 다름 | 🔴 **사용자 결정** — '가' 는 **보안 계약 개정** |

---

## 3. 걸리는 것 (스키마·경로 실측)

| # | 장애물 | 근거 | 최소 해소책 |
|---|---|---|---|
| **B-1** | **UNIQUE 부분 인덱스** `idx_param_rec_unique_per_day ON (target_date, strategy_id) WHERE status IN ('pending','applied','partial')` | `supabase/migrations/007_*.sql:18-20` | 목요일 20:00 일일 자문이 이미 `(오늘, kojiro)` 를 점유한다. 주간 행 INSERT 는 23505 로 거부되고 `insert_recommendation` 이 **`None` 을 조용히 반환**한다(`db/parameter_recommendations.py:89-95` 가 `duplicate/unique/23505` 를 WARNING 1행으로 흡수) ⇒ **주간 행이 소리 없이 사라진다.** 조건 1+2 |
| **B-2** | `source`/`provider` 컬럼 **없음** (007 + 028 까지 확인) | 마이그레이션 목록 | 조건 1 |
| **B-3** | 인덱스 **교체**는 가산형이 아니다 | 루트 CLAUDE.md 사전 승인 범위 | 조건 2 = 별도 승인 |
| **B-4** | `expire_pending_before` 가 `status='pending' ∧ target_date < 오늘` 을 **전부** expired 로 | `db/parameter_recommendations.py:211-218`, 호출 = `recommendation_engine.py:399`(매일 20:00 진입부) | 목 20:30 에 넣은 주간 행이 **금 20:00 에 만료** = 사람에게 **약 24시간**. 주간 주기엔 짧다 ⇒ 조건 3 |
| **B-5** | 루틴이 DB 에 쓸 **경로가 없다** | `src/middleware/api_auth.py:262-269` — 리포터 키는 GET/HEAD 전체 + `POST /api/log-reports/{YYYY-MM-DD}/external` **정확히 1경로**, 그 외 403 | §4 |
| **B-6** | `PARAM_RANGES` **밖의 키는 적용 버튼이 조용히 버린다** | `routes/recommendations.py:74-97` — 미등재 키는 `[manual_apply_safeguard_skip]` 후 제외, `applied_params` 에 안 들어가 `remaining` 에 남아 **`status='partial'`** | 이번 주 3건 중 LTV `trailing_stop_rate`·`overnight_stop_loss` 는 PARAM_RANGES **안**, VCP `last_pullback_max` 는 **밖**이라 체크해도 안 먹는다. **레벨 0 의 "게이트 사전판정" 이 정확히 이 자리** |
| **B-7** | 신규/이력 탭 분기가 **`target_date` 최대값 단독** | `Recommendations.tsx:154-174` | 같은 날짜면 한 그룹에 섞이고, 다른 날짜로 넣으면 주간이 "신규" 탭을 통째로 차지 ⇒ `source` 배지·필터 권장 |

---

## 4. 루틴이 결과를 넣는 경로 — **여기가 진짜 병목** (사용자 결정)

현행 인증 계약(`api_auth.py:88-100` **주석 원문**):
> "`|` 로 경로를 늘리는 변경은 '유일한 쓰기 경로' 라는 스코프의 근거 자체를 무너뜨리므로 **금지**."

| 안 | 내용 | 평가 |
|---|---|---|
| **가. 인증 스코프 확장** | `REPORTER_WRITE_PATH_RE` 에 경로 1개 추가 | 코드는 1줄이지만 **위 주석이 금지한 변경**이고 `src/middleware/` 는 인터넷 노출 보안 경계다. **사용자 승인 + 계약 문구 개정 선행** |
| **나. 기존 유일 경로에 얹기** | 주간 결과를 `POST /api/log-reports/{date}/external` 로 | 인증 변경 0. 그러나 목요일은 20:20 일일 리포트가 **같은 경로·같은 날짜**를 쓴다 → 충돌·덮어쓰기 + 두 종류를 한 테이블에 섞는 설계 부채 |
| **다. 세션이 전사** | 클라우드 루틴은 지금처럼 PR/Notion 만 쓰고, **메인 세션(운영 키 보유)이 PR md 를 파싱해 PUT/INSERT 를 조립** | **인증·스키마 변경 0.** 레벨 0 의 정의("파싱·전사·PUT 조립·기본값 대조·게이트 사전판정")를 그대로 만족. 주 1회 사람이 세션을 여는 것을 전제 |
| **라. 백엔드가 당겨오기** | GitHub/Notion 폴링 | 새 외부 자격·의존. 범위 과대 |

> **레벨 0 의 정의는 "적용 실행" 이 아니라 "전사와 사전판정" 이다.** 그렇다면 **다**가 가장 싸고 계약 위반이 0이다.
> 다만 **"지금 UI 의 적용 버튼" 을 쓰려면 결국 DB 행이 필요**하므로 B-1~B-4 는 어느 안에서도 남는다.
> **이 명세는 어느 안도 전제하지 않는다** — 보류 Red 는 '다' 를 기본으로 두되 '가' 를 **금지 가드**로 고정했다.

---

## 5. 최소 변경 목록

| # | 대상 | 내용 | 승인 |
|---|---|---|---|
| 1 | `supabase/migrations/043_parameter_recommendations_source.sql`(신규) | `ADD COLUMN source VARCHAR(16) NOT NULL DEFAULT 'daily'` | 사전 승인 |
| 2 | 같은 파일 | 새 UNIQUE 부분 인덱스 `(target_date, strategy_id, source) WHERE status IN ('pending','applied','partial')` 생성 → **구 `idx_param_rec_unique_per_day` DROP** | 🔴 **사용자 결정** |
| 3 | `src/db/parameter_recommendations.py` | `insert_recommendation(..., source: str = "daily")` · `expire_pending_before` 에서 주간 제외 | 사전 승인 |
| 4 | `src/routes/recommendations.py` | 응답에 `source` + **`appliable_keys`(= `PARAM_RANGES` 교집합 사전판정)** | 사전 승인 |
| 5 | `frontend/src/types/recommendations.ts` · `pages/Recommendations.tsx` | `source` 배지("일일"/"주간") · 탭/필터에 `source` · **PARAM_RANGES 밖 키 회색 처리 + 사유 표시** | 사전 승인 |
| 6 | `frontend/src/test/handlers.ts` · `e2e/fixtures/api-mocks.ts` | MSW·Playwright 목 동기화 — **cycle266 이 실증한 재발 지점**(목이 *의도한 계약* 만 담으면 3개월 초록일 수 있다) | 사전 승인 |
| 7 | `src/middleware/api_auth.py` | **리포터 스코프 POST 경로 추가 여부** | 🔴 **사용자 결정 항목 — 보안 영향.** 기본은 **하지 않는다** |

**하지 말아야 할 우회 2가지**
1. 주간 행에 **다른 `target_date`**(예: 금요일)를 넣어 UNIQUE 를 피하는 것 — B-7 로 "신규" 탭을 주간이
   차지하고, 날짜가 사실이 아니게 되어 이후 모든 집계가 어긋난다.
2. `status` 를 우회해 넣는 것(예: 처음부터 `partial`) — 부분 UNIQUE 가 `partial` 도 포함하므로 해결되지 않고
   `actionable` 판정만 흐려진다.

**마지막으로, 레벨 0 은 "적용을 집행하는 경로" 를 만들지 않는다.** 위 7개 어디에도 `apply` 를 자동 호출하는
코드는 없고, **없어야 한다.**

---

## 6. Red 계약 ↔ 테스트 (현재 **7 failed / 4 passed**)

| 테스트 | 내용 | 현재 |
|---|---|---|
| `test_g273g_1_source_column_is_additive` | 마이그레이션에 `ADD COLUMN … DEFAULT 'daily'` | **RED** |
| `test_g273g_1b_unique_index_is_replaced…` | 구 인덱스 DROP + 새 3키 UNIQUE + status 부분 조건 보존 | **RED** |
| `test_g273g_2_insert_accepts_source_with_daily_default` | `insert_recommendation(source="daily")` | **RED** |
| `test_g273g_2b_daily_engine_call_site_unchanged` | 20:00 엔진은 `source` 미명시(기본값에 맡긴다) | PASS(유지 계약) |
| `test_g273g_3_expire_pending_excludes_weekly` | 24시간 만료 방지 | **RED** |
| `test_g273g_4_apply_route_exposes_appliable_keys` | **게이트 사전판정**(B-6) | **RED** |
| `test_g273g_4b_list_response_carries_source` | 배지 전제 | **RED** |
| `test_g273g_5_no_auto_apply_path_for_weekly` | `_CONSERVATIVE_KEYS == frozenset()` 유지 + 엔진이 weekly 를 모른다 | PASS(**경계 가드**) |
| `test_g273g_6_reporter_scope_write_path_unchanged` | 리포터 쓰기 경로 1개 유지(`|` 0) | PASS(**경계 가드**) |
| `test_g273g_7_no_date_shifting_workaround` | 날짜 위조 우회 금지 | **RED** |
| `test_g273g_7b_status_is_pending_not_partial` | status 우회 금지 | PASS |

⚠️ **`test_g273g_5` · `test_g273g_6` 은 지금 초록이며, 초록으로 남는 것이 계약이다.**
Green 이 이 둘을 깨면 그것은 레벨 0 이 아니라 레벨 1 이상으로 넘어간 것이다.

**뮤테이션** — M1 `DEFAULT 'daily'` 제거(`g273g_1`) · M2 구 인덱스 DROP 누락(`g273g_1b`) ·
M3 `source` 기본값을 `"weekly"` 로(`g273g_2`) · M4 만료 쿼리에서 source 조건 제거(`g273g_3`) ·
M5 `appliable_keys` 를 `recommended_params` 전량으로(`g273g_4`).

---

## 7. 자문이 짚은 정합성 충돌 — 코드로 재확인한 것

| # | 자문 주장 | 코드 대조 |
|---|---|---|
| C-1/C-2 | `_CONSERVATIVE_KEYS = frozenset()` 이라 방향 게이트가 아무것도 통과시키지 못한다 | **확인.** `recommendation_engine.py:531` 빈 frozenset(사이클 210). `:637-638` 의 `if k not in _CONSERVATIVE_KEYS: continue` 가 **모든 키를 건너뛴다** ⇒ params 자동 적용은 구조적으로 0건 |
| C-3 | `auto_apply_enabled` 에 provider 스코프가 없다 | **확인.** 20:00 경로 하나뿐 — 켜면 일일 weight 감액이 함께 깨어난다 |
| C-4 | UNIQUE 로 목요일 두 자문이 충돌 | **확인**(B-1) |
| C-5 | 20:00 auto_apply 가 20:30 산출물보다 30분 먼저 돌고 다음날 expire 가 먼저 지운다 | **확인**(B-4) |
| C-6 | 리포터 키로는 DB·params 에 쓸 수 없다 | **확인**, 그리고 **경로 추가는 코드 주석이 금지**한다는 사실이 자문 기술보다 한 단계 강하다 |
| 한계 7 | 운영 DB `auto_apply_enabled` 실측 미수행 | **이 워크플로도 확인하지 않았다**(설정 조회는 지시 범위 밖) — **T-1 은 여전히 열려 있다** |

---

## 8. 미해결 (결정 필요)

| # | 항목 | 권고 |
|---|---|---|
| **OQ-D4-1** | 조건 2 **DROP INDEX** 승인 | 되돌리기는 구 인덱스 재생성으로 가능. 대안(구 인덱스 유지 + 주간을 다른 테이블)은 UI 재사용을 포기하는 것이라 사용자 질문의 답이 "아니오" 가 된다 |
| **OQ-D4-2** | 조건 4 **적재 경로** 가/나/다/라 | **다(세션이 전사)** — 인증·스키마 변경 0, 레벨 0 정의를 그대로 만족 |
| **OQ-D4-3** | 리포터 스코프 POST 허용(§5-7) | **하지 않는다**(기본). 하려면 계약 문구 개정 + 보안 검토가 선행 — **사용자 결정 항목으로 표기** |
| **OQ-D4-4** | 주간 행의 `target_date` 를 무엇으로 둘 것인가 | **자문 실행일 그대로.** 날짜 위조 금지(§5 우회 1) |
| **OQ-D4-5** | 주간 행의 TTL(만료 정책) | 다음 주간 자문이 들어올 때까지(7일) 또는 `source='weekly'` 만료 제외. **7일 TTL 권고** — 무기한은 큐가 쌓인다 |
| **OQ-D4-6** | 승격 관측(4주 불일치 0)을 이번에 배선하는가 | **이번 범위 밖.** 레벨 0 이 돌기 시작한 뒤 별도 카드 |
| **OQ-D4-7** | 운영 DB `auto_apply_enabled` 현재값 | **미확인(T-1).** 레벨 0 은 그 값과 무관하지만, 켜져 있으면 일일 weight 감액이 매일 돌고 있다는 뜻이라 **별도 확인 권고** |
