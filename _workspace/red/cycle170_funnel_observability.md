# 사이클 170 — 전략 funnel 관찰성 결함 3건 시정 (행위 보존 리팩토링)

작업 지시서 (team-leader → tdd-engineer Red → backend-dev Green → tester 검증).
적용 순서 **B → A → C**. 모든 카드 행위 보존 + 회귀 가드 동반.

## 배경 (확정 진단 — 재진단 금지)

funnel 은 **순수 관찰성** (메모리 `_funnel_steps` + DB `strategy_funnel_snapshots` + UI).
매매는 정상 — `list_by_filter` robust (Python `int()` 파싱), donchian 실제 유니버스 321종목.

운영 DB 실측 (project_id=`etaligxesjtjfkbntdve`):
- donchian 필터 재현 (min_market_cap=500억, min_trade_amount=10억): **union 348 → 시총컷 348 → 거래대금컷 321**.
- funnel DB: donchian 6/19 step1=0 / step2=0 / step3=0 / **step4=7** / step5~9=0 (논리 불가능 — 파이프라인 뒤 단계가 앞 단계보다 클 수 없음).

3 결함:
- A — 단계 collapse/오라벨: donchian `prepare()` step1/step2 둘 다 `survived=tickers` (동일 변수) → attrition(348→348→321) 미노출.
- B — per-step UPSERT 비일관: 조기반환/다중 실행 시 실패 run 이 step1~3 만 0 으로 덮고 step4~9 는 이전 성공 run stale(7) 잔존.
- C — 전략 간 기록 불일치: step1 의미 불일치 (donchian 오라벨 / VB·LTV `survived=[]` placeholder / BFB step1 step_name 구버전 의미).

## 매매 안전성 의무 (절대)

`src/engine/scanner.py` / `src/engine/risk.py` (on_tick) / `src/engine/order_engine.py` / `src/realtime/` / `src/auth/` / `src/api/order.py` **diff 0**.
매수 후보 반환 list 불변 (카드 A 는 카운트 *관찰*만, 필터 로직/임계 불변 — 사이클 166/168).
`check_exit_signal` funnel hook 0건. momentum funnel 영구 제외 (사이클 132) — 활성화 금지.
사이클 32 R4 / 38 / 132 / 143 / 145 / 153 / 157 영속.

---

## 카드 B (MEDIUM) — atomic 일관성 [최우선]

채택안 = `_reset_funnel_steps(stages)` 0-시드 + `_record_funnel_step` in-place upsert
(옵션 1 DB delete 보다 견고/단순 — 신규 CRUD 0, scheduler 변경 0, 비원자 윈도우 0).

### 구현

`src/engine/strategy_base.py`:
- `_record_funnel_step` (현 `self._funnel_steps.append(...)` append-only, ~L266): 같은 `step_no` 존재 시 **in-place 교체** (리스트 순회 후 인덱스 대체), 없으면 append. **이 한 줄이 핵심 회귀 표면 — 행위 신중히.**
- `_reset_funnel_steps(stages=None)`: `stages` 의 모든 `FunnelStage` 를 `survived=[]`(count=0) 로 pre-populate (각 step_no 0-시드). `stages=None` 시 현행 (빈 리스트) 회귀 보존.
- 효과: 조기반환/실패 run 도 전 단계 0 일관 UPSERT → step4=7 stale 영구 소멸.

5 전략 (donchian/BFB/VCP/VB/LTV) `prepare()` + retry 루프의 `self._reset_funnel_steps()` → `self._reset_funnel_steps(<해당 전략 STAGES 상수>)` 인자 전달:
- donchian: `_reset_funnel_steps(FUNNEL_STAGES)`
- BFB: `_reset_funnel_steps(FUNNEL_STAGES)`
- VCP: `_reset_funnel_steps(FUNNEL_STAGES)`
- VB: `_reset_funnel_steps(VB_FUNNEL_STAGES)`
- LTV: `_reset_funnel_steps(LTV_FUNNEL_STAGES)`
- 각 전략 prepare() 본체 호출 1건 + retry 루프 내 호출 1건 = 전략별 2건씩.

`scheduler._auto_capture_funnel_snapshots` + `insert_snapshot` UPSERT 변경 0.

### 회귀 가드 (B 6 케이스)

- G-B-1: `_reset_funnel_steps(STAGES)` 후 `_funnel_steps` 길이 == len(STAGES), 각 step survived_count=0.
- G-B-2: 같은 step_no 2회 `_record_funnel_step` → 길이 불변 + 최신 값 반영 (append-only 회귀 차단).
- **G-B-3 (HIGH)**: donchian universe=0 조기반환 시 step1~9 전부 존재 + step4~9 survived_count=0 (stale 패턴 소멸).
- G-B-4: auto_capture 가 0-시드 step 도 step_no 누락 없이 UPSERT (step_no 집합 == 1..N + 99).
- G-B-5: `_reset_funnel_steps()` (인자 None) 호출 시 현행 빈 리스트 회귀 보존.
- G-B-6 (AST): 5 전략 prepare() 의 `_reset_funnel_steps` 호출이 모두 STAGES 상수 인자 전달 (인자 없는 호출 0건).

---

## 카드 A (MEDIUM) — 단계 노출

채택안 = `list_by_filter(return_stage_counts=True)` (단일 호출 단일 진실 — 분리측정 불일치 0, 기존 호출자 회귀 0).

### 구현

`src/db/stock_master.py::list_by_filter` (L562-696): 신규 keyword `return_stage_counts: bool = False`.
단일 필터 루프 (L634-694) 내 단계별 생존 ticker 누적 (cap 200, `_FUNNEL_SURVIVED_CAP` 와 정합 = 상수 재사용 또는 동일 값):
- `union`: index/형식/exclude 통과, 시총·거래대금 컷 *전*.
- `mcap`: 시총컷 통과 후.
- `trade`: 거래대금컷 통과 후 (= 최종 filtered).
- True → `(filtered, {"union_tickers": [...], "mcap_tickers": [...], "trade_tickers": [...]})`, False → `filtered` (현행).
- **기존 호출자 전원 미지정 → list 그대로 (회귀 0).** ticker 누적은 `row["ticker"]` 문자열.

`src/engine/strategies/donchian_swing.py`:
- `_scan_universe` L489-497: `rows, stage = await list_by_filter(..., return_stage_counts=True)` + `self._scan_stage_counts = stage` (관찰성 전용 신규 인스턴스 필드, `__init__` 에 `{}` 초기화).
  - 주의: 기존 graceful except 분기는 `self._scan_stage_counts = {}` 도 설정.
- `prepare()` L153-162: step1 `survived=stage["union_tickers"]`(348) + step2 `survived=stage["trade_tickers"]`(321) + step_conditions "시총 348 → 거래대금 321 통과". step2 라벨 "시총+거래대금 컷 통과" (FUNNEL_STAGES 개수 불변, 최소 변경 — step_name 상수는 그대로 두고 step_conditions 만 명확화 가능. 단 step2 survived 를 trade_tickers 로 교체).
  - donchian `prepare()` 가 `_scan_universe` 결과(filtered ticker list)와 `_scan_stage_counts` 양쪽 접근. `_scan_universe` 반환 시그너처는 **유지** (list[str]) — stage 는 인스턴스 필드 경유.

### 회귀 가드 (A 6 케이스)

- **G-A-1 (HIGH)**: `return_stage_counts=True` 의 filtered == `return_stage_counts=False` 의 결과 (원소 + 순서 동일). 매수 풀 불변 핵심.
- G-A-2: union ⊇ mcap ⊇ trade, len(trade_tickers) == len(filtered) (단조 감소).
- G-A-3: 실측 348/348/321 픽스처 재현.
- G-A-4: 미지정 호출자 → 반환 list (tuple 아님).
- G-A-5: donchian prepare 후 step1 survived_count=348 / step2 survived_count=321 (collapse 차단).
- G-A-6 (AST): `list_by_filter` 시그너처 `return_stage_counts` keyword 존재 + donchian `_scan_universe` 가 `return_stage_counts=True` 전달.

---

## 카드 C (LOW) — 5 전략 표준화

B 0-시드가 조기반환 보장 제공 → C 는 step1 의미 통일 + 오라벨 제거 집중.

### 구현

- VB(`volatility_breakout.py`) + LTV(`long_tail_volatility.py`): step1 `survived=[]` placeholder → `_scan_universe` 가 보관한 실제 후보 리스트 (신규 인스턴스 필드 `self._universe_candidate_tickers`, `__init__` 에 `[]` 초기화). `_scan_universe` 가 filtered 확정 직후 `self._universe_candidate_tickers = list(filtered)` 보관. prepare step1 `survived=self._universe_candidate_tickers`.
- BFB(`bull_flag_breakout.py`): step1 step_name 의미 정합 — `FUNNEL_STAGES[0].step_name` 이미 "유니버스 후보" (구버전 "KRX 등락률 순위"는 step_conditions). step_conditions 의 "KRX 등락률 순위 상위" 문구 → 실제 소스 (stock_master.list_by_filter, 사이클 108) 정합 문구로 교정.
- VCP(`vcp_breakout.py`): 카드 A 패턴 적용 검토 — VCP 도 list_by_filter union → step1 union 노출. **단 VCP `_scan_universe` 가 min_trade_amount=0 (거래대금 필터 미사용)** 이므로 union==mcap==trade. step1 union_tickers 노출은 선택 (tester 판단). 최소: step1 survived 를 `_scan_universe` 보관 후보로 교체 (VB/LTV 패턴 통일).
- `src/engine/strategies/CLAUDE.md` + docstring: `*_FUNNEL_STAGES` step1 = "원천 유니버스 후보 (필터 전)" 의미 통일 명시. 전략별 단계 수는 고유 단계라 유지.

### 회귀 가드 (C 5 케이스 + SAFETY)

- G-C-1: 5 전략 prepare 후 `_funnel_steps` step_no 전 단계 (1..N) 포함 (auto_capture step_no=99 는 scheduler 영역).
- G-C-2: step1 survived 가 빈 placeholder 아님 (universe>0 정상 시 비어있지 않음).
- **G-C-3 (SAFETY)**: 5 전략 `check_exit_signal` / `check_buy_signal` funnel hook 호출 0건 (사이클 143 G-143-SAFETY-3 답습).
- **G-C-4 (SAFETY)**: risk/order_engine/realtime/auth/scanner import 0건 (전략 파일 funnel 영역).
- G-C-5 (AST): VB/LTV step1 survived 가 `[]` 리터럴 placeholder 아님 (universe_candidate_tickers 필드 참조).

---

## 검증 (end-to-end)

1. 각 카드 Red→Green. 기존 회귀 PASS 유지:
   `python -m pytest tests/unit/engine/strategies/ tests/unit/db/test_cycle108_list_by_filter.py tests/unit/engine/test_cycle47_*.py tests/unit/engine/strategies/test_cycle143_*.py tests/unit/engine/strategies/test_cycle157_*.py -q` + 신규 가드 green.
2. **G-A-1 직접 검증**: `return_stage_counts=True` 의 filtered == False 결과 (원소·순서) — 매수 풀 불변.
3. 전체 백엔드 `python -m pytest -q` PASS (현 3,081 기준) × flakiness 0.
4. git diff 로 매매 안전성 영역 0 확인.

## 의미 전환 (사이클 66 K-2 패턴)

- 사이클 47 D-6 (`test_cycle47_funnel_pipeline_dry.py`): BFB prepare 후 `_funnel_steps == 8` (사이클 157 = 9 의미 전환 이미 적용). 카드 B 0-시드 후에도 9 유지 의무 — in-place 교체로 보장. 깨질 경우 의미 전환 명시.
- 사이클 143 D-6 류 (`_reset_funnel_steps` 호출 count): 인자 추가는 호출 count 불변 → 통과 예상.
