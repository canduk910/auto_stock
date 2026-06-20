# refactor-review — 전략 funnel 관찰성 (2026-06-20, 사이클 170)

행위 보존 권고 카드 3장. 매매 안전성 무영향 (funnel = 순수 관찰성: 메모리 `_funnel_steps`
+ DB `strategy_funnel_snapshots` + UI). 매수 후보 반환 list 불변.

## 진단 요약

운영 DB 실측 (project_id=`etaligxesjtjfkbntdve`):
- donchian 실제 유니버스: union 348 → 시총컷 348 → 거래대금컷 321 (정상).
- funnel DB: donchian 6/19 step1=0/step2=0/step3=0/**step4=7**/step5~9=0 (논리 불가능).

근본 원인 3건 (관찰성 결함, 매매 정상):

| 카드 | 결함 | 위험 | 근본 원인 |
|------|------|------|----------|
| B | per-step UPSERT 비일관 → step4=7 stale 잔존 | MEDIUM | 조기반환/다중 실행 시 실패 run 이 step1~3 만 0 덮고 step4~9 stale 잔존. `_record_funnel_step` append-only + `_reset_funnel_steps` 빈 리스트. |
| A | 단계 collapse/오라벨 (attrition 미노출) | MEDIUM | donchian step1/step2 둘 다 `survived=tickers` (동일 변수). `list_by_filter` 가 단일 호출로 union+시총+거래대금 한 번에 → 최종 list 만 반환. |
| C | 전략 간 step1 의미 불일치 | LOW | VB/LTV `survived=[]` placeholder / BFB step_conditions 구버전 문구 / donchian 오라벨. |

## 권고 카드

### 카드 B (MEDIUM) — atomic 일관성

채택안: `_reset_funnel_steps(stages)` 0-시드 + `_record_funnel_step` in-place upsert.
- 옵션 1 (DB delete 결합) 대비 우월: 신규 CRUD 0, scheduler 변경 0, 비원자 윈도우 0.
- 회귀 표면: `_record_funnel_step` append → in-place 교체 1줄.
- 회귀 가드 6 (G-B-1~6, G-B-3 HIGH).

### 카드 A (MEDIUM) — 단계 노출

채택안: `list_by_filter(return_stage_counts=True)` (단일 호출 단일 진실).
- 분리측정 (별도 호출 2회) 대비 우월: 불일치 0, 필터 로직/임계 불변.
- 기존 호출자 전원 미지정 → 회귀 0.
- 회귀 가드 6 (G-A-1~6, G-A-1 HIGH = 행위 보존 핵심).

### 카드 C (LOW) — 5 전략 표준화

채택안: step1 의미 통일 ("원천 유니버스 후보 (필터 전)").
- VB/LTV: `survived=[]` → `_universe_candidate_tickers` 실제 후보.
- BFB: step_conditions 구버전 문구 정합.
- VCP: list_by_filter union 노출 검토.
- 회귀 가드 5 + SAFETY 2 (G-C-3/C-4 SAFETY).

## 사용자 결정

B + A + C 전부, 적용 순서 B → A → C. TDD 사이클 (tdd-engineer Red → backend-dev Green → tester 검증).

## 재사용 자산 (신규 추상화 최소화)

- `StrategyBase._record_funnel_pipeline_step(FunnelStage, ...)` (사이클 47) — 호출 인자만 교정.
- `FunnelStage` dataclass + `*_FUNNEL_STAGES` 상수 — 구조 유지.
- `strategy_funnel.insert_snapshot` UPSERT (사이클 145) — 변경 0.
- `scheduler._auto_capture_funnel_snapshots` — 변경 0.
- `list_by_filter` (사이클 108/153/166) 필터 로직/임계 — 불변 (카드 A 는 카운트 관찰만 추가).

## 미발의 (안전 규칙 차단)

- momentum funnel 적재 — 사이클 132 영구 제외 위반.
- scanner step_no=97/98 funnel — scanner 변경 0 제약.
- list_by_filter 필터 임계/순서 변경 — 매수 풀 변동 = 매매 영향.
