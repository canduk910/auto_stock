# cycle272 U3 — 가드·롤백·테스트 규약 조사 (읽기 전용)

작성 2026-09-10 · 조사 대상 HEAD `a10191b` · **코드 변경 0** (읽기 전용 조사)
전제 = 사용자 결정 D1(오늘) — "체크 없이 KRX 시가를 쓰는 게 원칙 / 기준가를 조회값으로 교체 후
금요일 실측 → 그 다음 구독채널 분리 / 여섯 가지(비중·position_ratio·max_positions·랏 캡 K·K_ρ·
`open_entry_hold_secs` 90초·LTV 청산 규약) 무접촉".
**전략 파일(VB·LTV) 변경은 오늘 D1 으로 승인됐다** — 8영역은 여전히 무접촉이 목표다.

---

## 0. 한눈에 — cycle272 가 반드시 통과해야 할 관문

| # | 관문 | 정본 파일 | 지금 상태 |
|---|---|---|---|
| A | 신규 `DEFAULT_PARAMS` 키 규약(PARAM_RANGES/INT_PARAMS 미편입 + 소스 리터럴 0 + glob 전수 스코프) | `tests/unit/ast/test_cycle262_ast_open_entry_hold.py` | cycle262 가 확립, 그대로 답습 |
| B | **킬스위치 이름 `open_price_scope_mode` 가 `src/**.py` 전역에서 금지돼 있다** | `tests/unit/ast/test_cycle264_scope_and_pins.py::test_c7_no_killswitch_param_introduced` (L279-296) | **cycle272 가 이 가드를 갱신·삭제해야 한다** (아래 §3-①) |
| C | VB/LTV `check_buy_signal` **소스 세그먼트 sha 6개 핀** | `test_cycle264_scope_and_pins.py::_STRATEGY_PINS` (L204-217) | cycle264 가 "cycle265 가 이 핀을 갱신한다"고 **명시 예고** |
| D | 워킹트리 전략 7파일 diff 0 (커밋 전까지) | `test_cycle223_ast_donchian_exit_fix.py::test_g223_12` + `_CYCLE228_STRATEGY_CONTENT_SHA`(L542, **현재 빈 dict**) | VB/LTV 를 한 글자라도 고치면 **즉시 RED** → 승인 하 sha 한시 핀 |
| E | 8영역 diff 0 (4곳 자매 가드 + G3-9b 전수 정합) | 222a3 / 223 / 223f / 226 + `test_cycle223g3_ast_guard_sees_staged.py::test_g3_9b` | 8영역 무접촉이면 **공허 통과** = 목표 |
| F | `scheduler.py` < 3,900L | `test_cycle257_ast_dead_code_removed.py` L277 + `test_cycle264_scope_and_pins.py` L86 | **현재 3,898L — 여유 1행** |
| G | LTV `check_buy_signal` **첫 문장 = 계좌 게이트 If** | `test_cycle233_ast_account_risk.py::test_gate_first_strategies_have_gate_as_first_statement` (L84-94) | LTV 는 `GATE_FIRST_FILES` 멤버 |
| H | VB `check_buy_signal` 게이트는 **최상단 금지 · BUY return 직전** | 같은 파일 L96-124 | VB 는 `GATE_PRE_BUY_FILES` |

기준 회귀 실측(오늘) — `pytest tests/unit/ast/test_cycle264_scope_and_pins.py
tests/unit/ast/test_cycle223g3_ast_guard_sees_staged.py tests/unit/ast/test_cycle262_ast_open_entry_hold.py`
= **57 passed in 0.66s** (워킹트리 클린 기준).

---

## 1. 신규 `DEFAULT_PARAMS` 키 규약 — cycle262 `open_entry_hold_secs` 가 어떻게 넣었나

### 1-a. 소스 배선 (7 지점, VB/LTV 대칭)

| 역할 | VB `volatility_breakout.py` | LTV `long_tail_volatility.py` |
|---|---|---|
| 모듈 상수(창 시작·상한) | `OPEN_ENTRY_HOLD_START_HOUR = 9` L38 · `OPEN_ENTRY_HOLD_MAX_SECS = 600` L39 | L27 · L28 |
| `DEFAULT_PARAMS` 키 | `"open_entry_hold_secs": 90,` **L139** (주석 L130-138) | **L120** |
| cap 필드 2종(별개 인스턴스) | L177-178 | L148-149 |
| 카나리아 호출(매 평가) | L872-873 | L676-678 |
| 판정(발사점) | L937-968 | L743-769 |
| 읽기+클램프 | `_read_open_entry_hold_secs` **L999-1029** | L803-833 |
| 창 판정(순수) | `_open_entry_hold_elapsed` L1031-1048 | L835-… |
| config emit | `_emit_open_entry_hold_config` L1050-1107 | L854-911 |

**핵심 계약 6가지** (그대로 답습할 것):

1. **`DEFAULT_PARAMS` 키여야 한다** — `PUT /api/strategies/{id}/params`(`src/routes/strategies.py`
   **L176-178**)와 `_load_strategy_config`(`src/engine/scheduler.py` **L422-425**)가 둘 다
   `if key in strategy.config.params` **오버레이**라, 코드에 없는 키는 DB 에서 **조용히 버려진다**.
   ⇒ 배포 전 DB 선반영은 무음 실패이고, 장중 롤백도 불가능하다.
   근거 테스트 = `tests/unit/engine/strategies/test_cycle262_open_entry_hold.py::test_c1_1` (L234-251).
2. **읽는 쪽 클램프 + fail-open** — `int(params.get(KEY, 0) or 0)` → 음수 0 → `min(secs, MAX)`.
   `except Exception` 이 **bare** 여야 한다(VB L1025). 좁은 튜플은 `1e400`(유효 JSON) →
   `int(inf)` → `OverflowError` 를 놓치고, 그 예외가 `risk.on_tick`(전략별 try 없음, `risk.py:648`)
   → `handler.py` re-raise → **WS 재연결 폭주**로 이어진다(cycle262 적대 검증 HIGH).
   격자 테스트 = `_OFF_GRID` (test_cycle262_open_entry_hold.py L264-285): 부재/None/""/"abc"/
   음수/0/inf/-inf/nan 전부 OFF.
3. **키 부재 = fail-open 의 방향이 사안마다 다르다.**
   - `open_entry_hold_secs` → 부재 = **0 = OFF = 매수 허용**(P0-1 유령 키 재현 금지).
   - `max_lot_ratio_mult`(cycle245) → **부재 = OFF**(매수를 막는 통제라 반대 관례).
   ⇒ cycle272 킬스위치는 "**부재 = 현행 행위(WS 기준가)**" 인지 "**부재 = 새 행위(REST)**" 인지를
   명세가 **명시**해야 한다. 두 선례가 서로 반대라 관례로 추론할 수 없다. (→ open_questions)
4. **PARAM_RANGES/INT_PARAMS 편입 금지 — 이중 검사**
   - 런타임 축: `test_g262_1a` (AST 파일 L255-265) `KEY not in PARAM_RANGES/INT_PARAMS`
   - 소스 리터럴 축: `test_g262_1b` (L268-284) `recommendation_engine.py` 소스에 키 문자열
     **리터럴 0건** (조건부 편입 `if ...: PARAM_RANGES[KEY]=...` 차단).
   현재 `PARAM_RANGES` = `src/engine/recommendation_engine.py:53`, `INT_PARAMS` = L120-129
   (`INT_PARAMS ⊆ PARAM_RANGES` 규약).
5. **키 스코프는 glob 전수로 못 박는다** — `test_g262_2` (L290-314): 전략 `*.py` 전부를 훑어
   `DEFAULT_PARAMS` 에 키를 가진 파일 집합이 **정확히 {VB, LTV}** 이고 값이 리터럴 90 인지 검사.
   파일엔 있는데 `DEFAULT_PARAMS` 밖이면 `None` 으로 잡아 계약 위반 처리(L304-305).
6. **카나리아 cap 은 값-민감** — `key = f"cfg|{hold_secs}"` (VB L1084).
   `test_g262_7e`(L608-647)가 f-string 보간 존재 + `should_emit` 인자가 상수 문자열이 아님을 강제.
   이유: 장중 유일 롤백 수단인 PUT 으로 값을 바꿔도 **단일 키면 그날 첫 틱이 cap 을 소진해
   바뀐 값을 확인할 마커가 0개**가 된다(cycle245 R1 사각).

### 1-b. 그 밖에 cycle262 AST 가 못 박은 구조 술어 (cycle272 도 같은 형태를 요구받는다)

| 가드 | 무엇을 | 라인 |
|---|---|---|
| G-262-3a | 판정(blocked 마커)이 `_prev_price` **쓰기보다 뒤** | L336-359 |
| G-262-3b | VB 는 `_account_soft_gate_blocked` **뒤** | L362-383 |
| G-262-4 | 보류 참조 함수에 naive `datetime.now()` 0 ∧ tz-aware ≥1 (`strftime` 표시용은 제외) | L390-414 |
| G-262-5 | 보드 리터럴·`tradable_boards` 토큰 0 (**시간창 단독** 판정) | L421-449 |
| G-262-6a/b | `KstDailyEmitCap` 재사용 · 신규 cap 클래스 0 · `now=` 키워드 전용 | L456-491 |
| G-262-7a/b/c | 마커 존재 · emit 이 `Try` 하위 ∧ 흡수기가 **bare `except Exception`** · `write_log`/`await` 0 | L498-567 |
| G-262-7d | **peek → 로그 → mark** 순서(lineno 부등식) | L571-604 |
| G-262-8 | `check_exit_signal`/`calc_buy_quantity`/`check_force_clear` 에 토큰 0 | L654-667 |
| G-262-9 | VB ↔ LTV 상호 import 0 | L674-688 |
| 비-공허성 | `_require_hold_funcs`(L115-121) — 기준선 함수가 0이면 **명시 FAIL** | — |

> ⚠️ 이 파일은 **`ast.dump` sha 를 쓰지 않는다**(3.12 CI vs 3.13 로컬 출력 차이). 구조 술어만 쓴다
> (파일 docstring L39-44). 소스 스캔에 `git grep`/`git ls-files` 도 쓰지 않는다(미추적 파일 누락).

---

## 2. 관측 규약

### 2-a. `KstDailyEmitCap` (`src/engine/daily_emit_cap.py` L113-209)
- `DailyEmitCap` 의 서브클래스. **날짜 키 자기 리셋** 내장 — `_reset_daily_state` 훅에 의존하면
  서브클래스 override 하나로 관측이 영구 침묵한다(VB L172-176 주석이 그 이유를 명시).
- `should_emit(key, *, now=None)` / `mark_emitted(key, *, now=None)` — **`now` 는 키워드 전용**
  (L122-124). 위치로 넘기면 `TypeError` 가 관측 try 안에서 흡수돼 **그날 관측이 무증상 소실**.
- 선점 계약(K-13, L126-131): 최초 동기화는 프라이밍만 하고 `reset_daily()` 를 부르지 않는다.
- 날짜 산출 실패는 `""` 로 흡수(L138-145) = never-raise.
- **관측기마다 별개 인스턴스**가 계약이다(VB L172-178: config 1행이 그날 blocked 표본을 통째로
  침묵시키는 것을 막는다 — cycle236 '별개 cap 가드' / donchian OB-11 선례).

### 2-b. `observer_trace.trace_observer_failure` (`src/engine/observer_trace.py` L31-84)
- 시그니처 `(marker, key, cap=None, *, now=None, dest_logger=None)`.
- `debug` 스택(항상) + WARNING **1회/(marker,key)/일**(cap 있을 때).
  키 = `f"{marker}|{key}__observer_failed__"` (L28, L79) — **정상 관측 키와 절대 공유 금지**.
- **never-raise** — 이미 `except` 안에서 불리므로 모든 단계를 자체 try 로 감싼다.
- `dest_logger` 에 **호출자 모듈 로거**를 넘긴다(VB L1104 / L964) — 그래야 기존
  `caplog.at_level(..., logger=<모듈>)` 스코프 테스트와 호환된다.
- 호출 자체도 다시 `try/except Exception: pass` 로 감싼다(VB L1100-1107, `# pragma: no cover`).

### 2-c. 마커 명명·보존
- 대괄호 접두 `[snake_case]` + `key=value` 공백 구분 필드. 값-민감 cap 키는 `f"cfg|{값}"` 형태.
- 로그는 `logger.info(...)` 로 남기고 **`write_log`(DB 직접 쓰기)는 금지**(G-262-7c) —
  `src/main.py::_DbLogHandler`(L166-207, `setLevel(INFO)`, 500ms dedupe)가 `src.*` 로거를
  자동으로 `system_logs` 로 큐잉한다.
- **보존 = INFO 2일 / WARNING+ 30일** — `src/db/system_logs.py` L32-33
  (`INFO_RETENTION_DAYS = 2` / `HIGH_RETENTION_DAYS = 30`), `purge_old_logs()` L339-382.
  ⇒ D+1 판독은 **2일 안에** 하거나 구조 덤프를 떠야 한다.
- caplog 단언은 **레벨(INFO 이상) + 로거명 + prefix 3중 한정**
  (`test_cycle262_open_entry_hold.py::_marker_lines` L203-217) — CI 루트 로거가 DEBUG 라
  `observer_failed` debug 흔적까지 섞인다.

---

## 3. 전략 파일(VB·LTV)을 고칠 때 붉어지는 가드 전수

### ① `test_cycle264_scope_and_pins.py::test_c7_no_killswitch_param_introduced` (L279-296) — **이름 그대로 금지**
```python
banned = ("open_price_scope_mode", "open_scope_observe_enabled", "open_source_compare_enabled")
for path in _SRC.rglob("*.py"):   # src/** 전역
    hits = [b for b in banned if b in text]
```
`src/**` **어느 .py 에든** `open_price_scope_mode` 문자열이 나타나면 FAIL 한다. 킬스위치 이름을
그대로 쓸 거라면 **cycle272 가 이 가드를 삭제하거나 금지 목록에서 빼야 한다**(docstring 이
"자문 §8.2 는 cycle265 시정에만 `open_price_scope_mode` 를 권고했다"고 이미 인정하고 있으나,
이 테스트는 **사이클 한정으로 표시돼 있지 않다** — 파일 docstring L5-12 는 `test_c7_working_tree_…`
와 `test_c4_…` 만 갱신 대상으로 예고했다). **cycle272 명세에 이 항목을 명시적으로 넣어야 한다.**

### ② `test_cycle264_scope_and_pins.py::test_c4_strategy_entry_methods_pinned` (L204-249) — 6 sha 핀
`ast.get_source_segment` 의 sha256 6개(VB/LTV × `check_buy_signal`/`check_exit_signal`/
`calc_buy_quantity`). VB `check_buy_signal` 을 한 글자만 고쳐도 RED.
파일 docstring L8-10 이 **"cycle265(기준가 시정)가 이 핀을 갱신하거나 이 테스트를 삭제한다"**
고 명시 예고했다 ⇒ cycle272 가 정당한 갱신자다. **다만 `check_exit_signal`·`calc_buy_quantity`
4개 핀은 손대지 말고 그대로 두는 것이 D1 "여섯 가지 무접촉"의 기계적 증거가 된다.**

### ③ `test_cycle264_scope_and_pins.py::test_c7_markers_live_only_in_two_files` (L259-276)
`[open_scope_observe]`·`[open_source_compare]` 마커가 `_ALLOWED_SRC`
(`handler.py`·`scheduler.py`·`open_price_observe.py`·`realtime/CLAUDE.md`, L46-53) 밖에
나타나면 FAIL. **전략 파일에서 cycle264 마커를 재사용하지 마라** — 새 마커 이름을 쓴다.

### ④ `test_cycle223_ast_donchian_exit_fix.py::test_g223_12_other_strategy_files_diff_zero` (L545-568)
전략 7파일(kojiro/vcp/bfb/momentum/VB/LTV)의 **워킹트리 diff(staged+unstaged) 0** 을 요구한다.
면제 dict `_CYCLE228_STRATEGY_CONTENT_SHA`(L542)는 **현재 빈 dict**.
⇒ VB/LTV 를 고치는 순간 RED. 승인 하 작업이므로 **커밋 직전 마지막 단계**에
`shasum -a 256 src/engine/strategies/volatility_breakout.py` / `…long_tail_volatility.py` 로
두 항목을 한시 등록하고(cycle262 선례 = 같은 파일 L518-536 주석), **커밋 직후 삭제**한다.
⚠️ 실패 메시지가 "핀을 먼저 재산출하지 마라"라고 경고한다 — 절차 1·2(diff 눈으로 확인)를 먼저.

### ⑤ 8영역 sha 핀 **자매 가드 4곳** + 전수 정합 (8영역을 건드릴 때만)
| 파일 | dict 이름 | 현재 |
|---|---|---|
| `tests/unit/ast/test_cycle222a3_ast_followup_fixes.py` L449 | `_APPROVED_CONTENT_SHA` | 빈 dict |
| `tests/unit/ast/test_cycle223_ast_donchian_exit_fix.py` L437 | `_PREEXISTING_CONTENT_SHA` | 빈 dict |
| `tests/unit/ast/test_cycle223f_ast_manual_apply_safeguard.py` L338 | `_PREEXISTING_CONTENT_SHA` | 빈 dict |
| `tests/unit/engine/strategies/test_cycle226_zero_breakout_defense.py` L1140 | `_ALLOWED_CONTENT_SHA` | 빈 dict |

`test_cycle223g3_ast_guard_sees_staged.py::test_g3_9a`(L322-331)가 **자매 가드 파일 목록 자체**를
`git grep -l _CONTENT_SHA` 실측과 대조하고, `test_g3_9b`(L334-369)가 워킹트리 8영역 변경이
**네 곳 전부에 같은 값**으로 핀됐는지 강제한다(8영역 무접촉이면 공허 통과, L352-353).
`_EIGHT_AREAS` 정본 = 222a3 L430-439 (`src/realtime`·`src/auth` 는 **디렉터리 글롭이라 .md 도
8영역**이다 — cycle264 가 `src/realtime/CLAUDE.md` 를 네 곳에 함께 핀한 이유).

### ⑥ 그 밖에 전략 파일 편집으로 붉어질 수 있는 가드
| 가드 | 무엇 | 위치 |
|---|---|---|
| cycle233 G1 | **LTV**: 게이트 If 가 `check_buy_signal` **첫 문장**(부작용·로그 emit 도 그 앞 금지) | `test_cycle233_ast_account_risk.py` L84-94 |
| cycle233 G1 | **VB**: 게이트가 `return Signal.BUY` 와 **같은 블록 그 앞**, 그리고 **최상단 금지** | 같은 파일 L96-124 |
| cycle229 G-1/2/3/5 | VB 매수컷: naive `datetime.now().time()` 0 · `BUY_CUTOFF_KST` 모듈 상수 15:20 · 컷이 `_prev_price` 참조보다 **앞** · tz-aware | `test_cycle229_ast_cutoff_guards.py` L137·L180·L212·L273 |
| cycle262 G-262-1~9 | §1-b 표 전부 (보류 코드가 이동하면 부등식이 깨진다) | `test_cycle262_ast_open_entry_hold.py` |
| A-GATE / A-PURE / A-ATOMIC | `calc_buy_quantity` 의 모든 return 이 `_apply_budget_limit` 경유 · 관문 내 await/DB 0 | `tests/unit/ast/test_budget_limit_ast.py` L62·L101·L123 |
| C-DEFAULT | `position_ratio × max_positions ≤ 1.0` | 같은 파일 L165 |
| cycle242 G-242-1 / cycle245 G-245-1 | `max_lot_units`·`max_lot_ratio_mult` 의 PARAM_RANGES 미편입 + 7전략 glob 전수 | `test_cycle242_ast_fallback_notional_cap.py` · `test_cycle245_ast_ratio_notional_cap.py` |
| cycle201 / cycle213 / cycle180 / cycle143 | VB·LTV 쿨다운 multi-day 상태 prepare 리셋 금지, funnel hook | `test_cycle201_vb_cooldown_ast.py` · `test_cycle213_ltv_cooldown_ast.py` · `test_cycle180_prepare_reset_ast.py` |
| 문서 가드 선례 | `src/engine/strategies/CLAUDE.md` 본문 문구 검사(cycle254 G-254-4) — 정본 문서 개정 누락을 기계가 잡는 패턴 | `test_cycle254_ast_ratio_cap_min.py` L201-260 |

### ⑦ **바꾸면 안 되는 시그니처**
`check_buy_signal(self, ticker, current_price, open_price) -> Signal` 은
`src/engine/strategy_base.py` L400-403 의 abstractmethod 이고 **호출부가 `src/engine/risk.py:648`
(8영역)** 이다. 인자를 늘리면 8영역 접촉이 된다 ⇒ **시그니처 불변이 8영역 0 의 전제**다.

---

## 4. `scheduler.py` 라인 가드 — 현재 3,898L / 상한 <3,900

- 정본 가드 = `tests/unit/ast/test_cycle257_ast_dead_code_removed.py` **L277 `assert count < 3900`**
  (L284 에 구 상한 4,000 단언도 병존).
- 자체 가드 = `tests/unit/ast/test_cycle264_scope_and_pins.py` **L86 `assert lines < 3900`**,
  그리고 **L91-108 `test_c7_scheduler_line_cap_matches_cycle257_guard`** 가 두 파일의 리터럴을
  정규식으로 뽑아 **자체 상한이 cycle257 보다 느슨하면 FAIL** 시킨다(느슨한 자체 가드가
  위반을 초록으로 덮던 cycle264 적대 검증 HIGH 의 재발 차단).
- **실측: `wc -l src/engine/scheduler.py` = 3,898 ⇒ 여유 1행.**
  주석 1줄만 추가해도 3,899(통과), 2줄이면 3,900(FAIL). **사실상 순증 불가.**
- ⇒ **leaf 위임이 강제**다. 선례 3건: `account_risk_watcher`(cycle233) ·
  `log_metrics_collector`(cycle259) · **`open_price_observe.py`(cycle264, 327L)**.

### leaf 등록 체크리스트 (cycle264 가 만든 패턴)
1. task 속성명은 **`_*_task`** — `_*_task_handle` 은 cycle79 수집기에 안 잡힌다
   (`test_cycle264_scope_and_pins.py::test_c7_open_source_compare_task_registered` L183-194).
2. `stop()` · `start()` · `run_daily()` **세 목록 전부**의 cancel 튜플에 등재
   (`test_c7_every_create_task_is_cancelled_everywhere` L167-180, `_create_task_attrs` 는
   이름 패턴이 아니라 `self._X = asyncio.create_task(...)` 대입 전수로 수집).
3. leaf 안에서 관측 cap/trace 를 쓴다(`open_price_observe.py` L104·L109 가 모듈 전역
   `KstDailyEmitCap`, L112-116 `reset_*_cap()` 테스트 훅, L318 `_trace_failure`).
4. 마커 문자열은 `_ALLOWED_SRC` 밖으로 새지 않게 한다(§3-③).

---

## 5. 롤백 경로 — 킬스위치를 `params` 로 두면 장중에 되돌릴 수 있나

### 5-a. 두 경로의 반영 시점 (CLAUDE.md 정본 + 코드 실측)
| 수단 | 코드 | 반영 시점 |
|---|---|---|
| `PUT /api/strategies/{id}/params` | `src/routes/strategies.py` L176-182 | **즉시** — in-memory `strategy.config.params` 를 덮고 그 뒤 `save_params` 로 JSONB 영속 |
| `strategy_config` SQL UPDATE | `scheduler._load_strategy_config` L404-425 | **다음 백엔드 재시작에서만** (`_config_loaded` 가 프로세스당 1회, 07:55 `_boot` 재호출은 no-op) |

cycle232 D6(보유 중 장중 재시작 금지) 때문에 **장중 실효 롤백 수단은 PUT 하나뿐**이다.

### 5-b. 두 개의 함정
1. **배포 전 PUT 은 무음 실패한다.** `update_params` 는 `if key in strategy.config.params` 로
   미지 키를 조용히 버리고 **`config.params` 전체를 JSONB 로 덮어써** 먼저 넣은 SQL 값까지 지운다
   (CLAUDE.md cycle245 항목에 명문화). ⇒ 킬스위치는 **배포 후에만** 조작 가능.
2. **⚠️ cycle262 와 결정적으로 다른 점 — 기준가는 틱마다 재평가되지 않는다.**
   `open_entry_hold_secs` 는 `check_buy_signal` 이 매 틱 `config.params` 를 다시 읽으므로 PUT 이
   그 즉시 행위를 바꿨다. 반면 목표가 기준가는 **`on_open_price_confirmed` 가 09:00:05 에 한 번
   계산해 `_targets[t]["boards"]["main"]` 에 박아 넣는 값**이다(VB L824-846 / LTV L637-651).
   ⇒ 장중에 킬스위치를 `off` 로 PUT 해도 **이미 확정된 그날의 목표가는 바뀌지 않는다.**
   되돌아오는 경로는 (a) `_open_confirmed` 가 아직 False 인 종목의 이후 확정
   (b) `_scan_loop` 5분 주기 `_confirm_breakout_open_prices_if_pending()`(scheduler L2375·L2447)
   (c) `prepare` 재실행(`_reprepare_breakout_if_empty` → `_open_confirmed` clear) 뿐이다.
   **⇒ 킬스위치의 실질 롤백 단위는 "다음 영업일" 이고, 장중 PUT 은 미확정 잔여분에만 듣는다.**
   이 한계를 명세·보고서에 **명시**해야 한다(→ open_questions / risks).
3. 관측 카나리아를 값-민감 cap 으로 두면(§1-a-6) PUT 직후 2행째가 남아 **롤백이 실제로 먹혔는지**
   확인할 수 있다. 단일 키면 확인 채널이 0행이다.

### 5-c. 그 밖의 롤백 수단
- **코드 롤백(다음 커밋 원복)** — 사전 승인 범위 (c) 조건. `src/**` 변경이라 배포는
  cycle248 **full 모드**(backend 재생성 1~5분) ⇒ 장외 창(15:30~19:55 · 20:20~익일 07:45 ·
  주말/공휴일, **20:00~20:15 금지**)에서만.
- **전략 단위 분리 롤백** — cycle262 가 `DEFAULT_PARAMS` 키를 두 파일에 **각각** 두고 상호 import 를
  금지한(G-262-9) 이유가 "VB 90 유지 · LTV 0" 같은 **한쪽만 롤백**을 가능하게 하기 위함이다.
  cycle272 도 전략별 키로 두면 같은 자유를 얻는다.

---

## 6. 이번 변경으로 **의도적으로 깨질** 기존 테스트 후보

> 전제: A안 = `board=="main"` 의 목표가 기준가를 **항상 KRX REST(`stck_oprc`)** 로 세운다
> (자문 §3-Q6-1 "오염 시가 아니라 항상"). 그러면 **WS 캐시/WS 틱이 `main` 기준가를 만든다**는
> 현행 계약을 단언하는 테스트가 반전된다.

### 6-a. 확실히 깨진다 — 계약 자체가 반전되는 것
| 파일 | 테스트 | 지금 무엇을 단언하나 |
|---|---|---|
| `tests/integration/test_confirm_open_prices.py` | `test_confirm_main_board_when_open_price_in_cache_then_target_set` (L28-44) | `scanner.ticker_prices["005930"]={"open_price":80000}` → `boards["main"]["target_price"]==80500`. **WS 캐시가 main 기준가** |
| 같은 파일 | `test_confirm_falls_back_to_kis_api_when_open_price_missing` (L66-95) | REST 는 **WS 결측 시에만** 쓴다는 우선순위. A안은 이 우선순위를 뒤집는다 |
| 같은 파일 | `test_confirm_is_idempotent_when_all_already_confirmed` (L150-198) / `test_confirm_proceeds_when_partially_confirmed` (L199-) | WS 캐시 시드로 confirmed 를 만든다 — 시드 경로가 바뀌면 셋업이 무효 |
| `src/engine/scheduler.py` L1652-1668 (1차 WS 폴링 루프)의 회귀 | — | 루프 자체가 A안에서 **폴백**으로 강등되거나 삭제 대상 |

### 6-b. VB/LTV 인라인 자동확정(`check_buy_signal` 안 WS `open_price` → `on_open_price_confirmed`)에 기대는 테스트
현행 경로 = VB **L898-901** / LTV **L705-707**. A안이 이 인라인 경로를 `main` 에서 막거나
REST 로 갈아 끼우면 아래가 전부 셋업 단계에서 무너진다.

| 파일 | 테스트 | 라인 |
|---|---|---|
| `tests/unit/engine/strategies/test_volatility_breakout.py` | `test_buy_when_target_unset_then_none` (주석 "시가 0 → 자동 확정도 못 함") | L130-134 |
| 같은 파일 | `test_buy_first_tick_per_board_records_only` | L150-156 |
| 같은 파일 | `test_buy_when_breakout_moment_then_buy` | L161-172 |
| 같은 파일 | `test_buy_when_above_target_but_no_breakout_moment_then_none` | L175-182 |
| 같은 파일 | `test_buy_signal_per_board_is_independent` | L187-203 |
| 같은 파일 | `test_buy_when_no_active_board_then_none` / `test_buy_when_active_board_not_in_tradable_then_none` / `test_buy_when_already_held_then_none` | L117-144 (앞선 가드에서 NONE 이라 **살아남을 가능성 높음**) |
| `tests/unit/engine/strategies/test_long_tail_volatility.py` | `test_buy_when_prdy_rate_below_min_then_none` | L74-85 |
| 같은 파일 | `test_buy_when_breakout_and_prdy_rate_above_min_then_buy` | L88-98 |

### 6-c. 깨지지 않을 가능성이 높은 것 (셋업이 `on_open_price_confirmed` **직접 호출**)
`tests/unit/engine/strategies/test_cycle262_open_entry_hold.py`(L176-179 `_armed` 가
`s.on_open_price_confirmed(t, open_price=_OPEN, board=b)` 직접 호출) ·
`test_cycle201_vb_reentry_cooldown.py` · `test_cycle213_ltv_reentry_cooldown.py` ·
`test_cycle229_vb_buy_cutoff.py` · `test_cycleG_vb_failed_breakout_exit.py` ·
`test_on_open_records_top_level_compat_for_first_confirmed_board`(test_volatility_breakout.py L103-111).
⇒ **setter 시그니처를 유지**하면 이 묶음은 무접촉이다. (setter 를 고치면 이들도 전부 깨진다.)

### 6-d. 구조/AST 단언이라 살아남지만 **재확인 필요**
`tests/integration/test_post_nxt_open_price_confirm.py`(L114·L147·L195·L243 — `start()` AST 에서
`board="main"`/`"pre_nxt"`/`"post_nxt"` 인자 명시 검사) ·
`tests/unit/engine/scheduler/test_confirm_open_prices_main_only.py`(pre_nxt/post_nxt 에서
VB/LTV 대상 0건) · `tests/unit/engine/test_cycle164_open_confirm_retry_chain.py`(재시도 chain) ·
`tests/unit/engine/test_cycle264_open_source_compare.py`(leaf 09:05:30 대조 — `used_src` 라벨
의미가 반전되면 이 파일의 기대도 재검토 대상).

---

## 7. cycle272 착수 전 체크리스트 (절차)

1. `git status` 클린 확인 → 기준 회귀 스냅샷 저장(전체 `pytest -q` 카운트).
2. Red 테스트 작성(신규 파일 `tests/unit/engine/strategies/test_cycle272_*.py` +
   `tests/unit/ast/test_cycle272_*.py`) — cycle262 AST 9가드 형태를 답습.
3. 구현 — **전략 파일 2개 + (필요 시) leaf 신규 모듈**. `scheduler.py` 는 여유 1행이므로
   순증 금지, 불가피하면 leaf 위임 + 3목록 등재.
4. `test_cycle264_scope_and_pins.py` 손질: `_STRATEGY_PINS` 의 **VB/LTV `check_buy_signal` 2개만**
   재산출(나머지 4개 불변 = 무접촉 증거), `test_c7_no_killswitch_param_introduced` 의 금지 목록에서
   `open_price_scope_mode` 제거(또는 테스트 삭제 + 사유 주석).
5. 커밋 **직전** `shasum -a 256` 로 `_CYCLE228_STRATEGY_CONTENT_SHA` 에 VB/LTV 2항목 한시 등록,
   **커밋 직후 삭제**(TODO 주석 관례). 8영역을 안 건드리면 자매 4곳은 손대지 않는다.
6. `/sync-docs` (Phase 4.8) — `src/engine/strategies/CLAUDE.md` · `src/engine/CLAUDE.md` ·
   루트 `CLAUDE.md` · `_workspace/00_leader_trading_rules.md`(DEFAULT_PARAMS 동기화 의무).
7. 배포 = cycle248 **full 모드**(src/** 변경) ⇒ 장외 창에서만 push.

---

## 8. 조사 시점 워킹트리 상태 (2026-09-10, 이 조사 중 실측)

`git status --short` = **클린이 아니다.** 병행 작업(cycle270 후속 추정)의 미커밋 변경 8파일:
`CLAUDE.md` · `_workspace/00_URGENT_WORKLIST.md` · `docs/HARNESS_CHANGELOG.md` ·
`src/engine/CLAUDE.md` · `src/engine/quote_token_refresh.py` ·
`tests/unit/engine/test_cycle269_*.py` · `test_cycle270_*.py` · `test_scheduler_stop_zombie_tasks.py`.

- **8영역 0 · 전략 7파일 0 · `scheduler.py` 0** ⇒ §3-④/⑤ 의 핀 가드는 지금도 공허 통과한다
  (실측 `pytest -q tests/unit/ast/` = **913 passed, 3 skipped, 26 xfailed**).
- ⚠️ 다만 sha 핀 가드는 **파일이 아니라 워킹트리 전체**를 본다. cycle272 가 VB/LTV 를 고치는
  동안 다른 에이전트가 전략 파일이나 8영역을 건드리면 핀이 뒤엉킨다
  (cycle263 이 "한 곳만 등록 → 7 failed" 로 겪은 그 계열). **작업 창을 겹치지 않게 잡거나
  커밋 직전에 `git status` 를 다시 확인**하는 절차가 필요하다.
