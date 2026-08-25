# 사이클 227 — Red 실행 결과

> 작성: tdd-engineer, 2026-08-25
> 명세: `_workspace/red/cycle227_acml_vol_stage0_spec.md` / 분해: `_workspace/red/cycle227_behaviors.md`
> 프로덕션 코드 변경 **0** (Red 단계). 기존 테스트 수정 **0**.

---

## 1. 실행 명령 · 결과 요약

```bash
python -m pytest -q --timeout=60 \
  tests/unit/realtime/test_cycle227_handler_acml_vol.py \
  tests/unit/engine/test_cycle227_tick_volume.py \
  tests/unit/engine/test_cycle227_risk_on_tick_acml.py \
  tests/unit/engine/strategies/test_cycle227_bfb_vol_gate_observe.py \
  tests/unit/engine/strategies/test_cycle227_vcp_vol_gate_observe.py \
  tests/unit/engine/test_cycle227_universe_guard_acml.py \
  tests/unit/ast/test_cycle227_ast_acml_vol_guards.py \
  tests/unit/engine/test_cycle227_e2e_acml_vol_pipeline.py
```

```
ERROR tests/unit/engine/test_cycle227_tick_volume.py
ERROR tests/unit/engine/test_cycle227_risk_on_tick_acml.py
ERROR tests/unit/engine/strategies/test_cycle227_bfb_vol_gate_observe.py
ERROR tests/unit/engine/strategies/test_cycle227_vcp_vol_gate_observe.py
ERROR tests/unit/engine/test_cycle227_universe_guard_acml.py
ERROR tests/unit/engine/test_cycle227_e2e_acml_vol_pipeline.py
!!!!!!!!!!!!!!!!!!! Interrupted: 6 errors during collection !!!!!!!!!!!!!!!!!!!!
E   ImportError: cannot import name 'tick_volume' from 'src.engine'
```

**RED 확인.** `src/engine/tick_volume.py`(W3) 부재로 6 파일이 **수집 단계에서 중단**된다.

### 1.1 세부 분류를 얻기 위한 임시 스텁 실행

수집 중단 상태로는 "신규 행위 RED" 와 "보존 검증 즉시 PASS" 를 구분할 수 없어,
**스크래치패드 전용 pytest 플러그인**으로 W3 계약대로 동작하는 `tick_volume` 스텁을
`sys.modules` 에 주입해 한 번 더 돌렸다. **프로덕션 소스는 무접촉**이고 Green 단계에서는 쓰지 않는다.

```
63 failed, 40 passed in 1.68s      # 스텁 주입 상태
```

스텁이 만족시킨 14건(= `test_cycle227_tick_volume.py` 전량)은 실제로는 ImportError RED 이므로,

| 구분 | 건수 |
|---|---|
| **RED (신규 행위 — Green 이 만들어야 함)** | **77** |
| **즉시 PASS (현행 보존 검증 · Stage 0 봉인)** | **26** |
| 합계 | 103 |

---

## 2. 파일별 결과

| 파일 | 총 | RED | 즉시 PASS | 비고 |
|---|---|---|---|---|
| `tests/unit/realtime/test_cycle227_handler_acml_vol.py` (W1) | 22 | 19 | 3 | `_parse_acml_vol` 부재 |
| `tests/unit/engine/test_cycle227_tick_volume.py` (W3) | 14 | 14 | 0 | 모듈 부재 (ImportError) |
| `tests/unit/engine/test_cycle227_risk_on_tick_acml.py` (W2) | 9 | 7 | 2 | `on_tick` 이 kwarg 거부 |
| `tests/unit/engine/strategies/test_cycle227_bfb_vol_gate_observe.py` (W4) | 18 | 13 | 5 | 관측 훅 부재 |
| `tests/unit/engine/strategies/test_cycle227_vcp_vol_gate_observe.py` (W5) | 18 | 14 | 4 | 관측 훅 부재 |
| `tests/unit/engine/test_cycle227_universe_guard_acml.py` (W6) | 14 | 8 | 6 | 판정 소스 미전환 |
| `tests/unit/ast/test_cycle227_ast_acml_vol_guards.py` (W7) | 5 | 1 | 4 | AST-4 만 RED(모듈 부재) |
| `tests/unit/engine/test_cycle227_e2e_acml_vol_pipeline.py` (W7) | 3 | 1 | 2 | 배관 단절 |

### 대표 RED 메시지 (Green 판정 기준)

```
E  AssertionError: WS payload 의 누적거래량이 관측 모듈에 도달하지 않았다 (got=None).
   소비처만 있고 대입부가 없는 상태 = P0-1 그 자체다
   assert None == 3628183
   → tests/unit/engine/test_cycle227_e2e_acml_vol_pipeline.py
     ::test_ws_payload_reaches_tick_volume_through_production_code

E  TypeError: RiskManager.on_tick() got an unexpected keyword argument 'acml_vol'
E  AssertionError: `_parse_acml_vol` 부재 — 누적거래량이 payload 에 실려 오는데도 파싱조차 안 한다
E  IndexError: list index out of range        # [bfb_vol_gate_observe] 로그 0행
E  AssertionError: 실측 당일 누적 1,500,000 인 종목이 축출됐다
   — 안전조건 소스가 여전히 `today_volume`(최근 체결 합) 이다
```

---

## 3. 즉시 PASS 26건 전수 (false-red 아님 — 분류 근거)

Red 시점부터 통과하는 테스트는 **"이번 변경이 깨면 안 되는 것"** 을 고정한다.
Green 구현이 이걸 깨면 그때 FAIL 로 잡히는 것이 존재 이유다.

### (a) Stage 0 봉인 — 행위 변경 0 (10건)

```
bfb ::test_gate_still_returns_none_regardless_of_observation[no_obs|below|exact|far_above]
vcp ::test_gate_still_returns_none_regardless_of_observation[no_obs|below|exact|far_above]
ast ::test_AST2_existing_volume_gate_block_is_byte_identical[bfb]
ast ::test_AST2_existing_volume_gate_block_is_byte_identical[vcp]
```

⚠️ **AST-2 는 게이트 전환 사이클에서 의미 전환할 가드다.** 지금 이게 실패하면
관측 사이클이 행위 변경 사이클로 미끄러진 것이다.

### (b) P0 결함 재발·확산 차단 (4건)

```
ast  ::test_AST1_no_acml_vol_assignment_into_ticker_prices     # donchian ext_pct 커플링
risk ::test_on_tick_when_acml_vol_omitted_then_not_recorded
e2e  ::test_pipeline_never_writes_acml_vol_into_ticker_prices
ast  ::test_AST3_handle_tick_field_guard_stays_at_ten          # len(fields)<10 상향 금지
```

### (c) 기존 계약 보존 (9건)

```
handler ::test_handle_tick_when_9_fields_then_still_silent_drops
handler ::test_handle_tick_when_price_unparsable_then_still_silent_drops
risk    ::test_legacy_positional_call_still_works
guard   ::test_held_ticker_never_excluded
guard   ::test_next_day_clear_ticker_never_excluded
guard   ::test_stale_within_threshold_not_evaluated
guard   ::test_ccnl_none_still_defers
guard   ::test_threshold_constant_unchanged
guard   ::test_excluded_log_keeps_legacy_fields
```

### (d) ⚠️ 약한 PASS — 지금은 공허하고 **Green 후에 의미가 생긴다** (3건)

```
handler ::test_handle_tick_when_acml_vol_unparsable_then_does_not_raise
bfb     ::test_no_observe_log_while_retention_pending
e2e     ::test_pipeline_when_acml_vol_unparsable_then_no_observation_and_tick_survives
```

지금은 "파싱도 관측도 아예 없으니 당연히 통과" 하는 상태다.
사이클 224 가 **자기 가드 공허성**(정의상 항상 참인 AST 가드)에서 배운 교훈대로
여기 명시해 둔다 — Green 이후에 이 3건이 **여전히 통과하는지**가 진짜 검증이다.

---

## 4. Green 착수 전 알려야 할 사항 (backend-dev 인계)

### 4.1 KIS 정본 확인 결과가 명세를 한 곳 정정한다 (W6)

`FHKST01010300`(`inquire_ccnl`) 응답 output row 는 **7 컬럼**이고 `acml_vol` 이 **없다**
(`stck_cntg_hour`/`stck_prpr`/`prdy_vrss`/`prdy_vrss_sign`/`cntg_vol`/`tday_rltv`/`prdy_ctrt`).

⇒ 명세 W6-2 의 "존재하면 첫 row 추출 · 추가 KIS 호출 0" 분기는 **성립하지 않는다.**
⇒ REST 폴백은 **`FHKST01010100`(`/uapi/domestic-stock/v1/quotations/inquire-price`,
`output.acml_vol`) 확정**. 그 path 는 `base.py::_QUOTE_ALLOWED_PATHS` 에 **이미 있다**
(화이트리스트 추가 불필요). 테스트가 요구하는 신규 API 는
`src.api.quotation.inquire_acml_vol(ticker, market="J") -> int | None`.

부수 확증: `cntg_vol` 이 정본상 **"체결 1건의 거래량"** 이므로,
"`today_volume`(~30행 합)이 10,000 을 사실상 항상 미달한다" 는 P0-2 진단이 산술적으로 맞다.

### 4.2 구현 제약 1건 — 관측 함수는 **호출 시점 해석**

BFB/VCP 는 `tick_volume.get_observed_acml_vol(...)` 형태(모듈 참조)로 불러야 한다.
모듈 상단에서 `from src.engine.tick_volume import get_observed_acml_vol` 로 이름을
당겨오면 관측기 자기실패 경로(W4-10/W5-11)를 테스트로 재현할 수 없다.
같은 파일이 이미 `from src.engine.scanner import ticker_prices` 를 **함수 안**에서 하는
관행과 일치한다.

### 4.3 `freezegun` 함정 (실제로 이번에 걸렸다)

`freeze_time` 은 `time.monotonic` 까지 얼려서 이벤트 루프 시계가 전진하지 않는다.
`await asyncio.sleep(...)` 이 있는 코드를 freeze 아래서 테스트하면 **영원히 행(hang)** 한다
(universe 가드의 50ms Rate Limit sleep 에서 재현, 5분 타임아웃).
그래서 `test_cycle227_universe_guard_acml.py` 는 freeze 를 쓰지 않는다 —
기존 `test_universe_guard.py` 도 같은 이유다.

### 4.4 명세 모호 1건 (team-leader 확인 대상 — Red 는 문자 그대로 고정)

`record_acml_vol` 재기록 시 **last-write-wins vs `max(기존, 신규)`** 가 명세에 없다.
자문 §9.5 가 "다중 레코드 프레임에서 `fields[13]` 은 배치 중 가장 오래된 레코드를 읽는다
(과소 계상)" 를 인지된 노이즈원으로 남겨 뒀으므로 `max()` 가 그 노이즈를 줄일 여지는 있다.
다만 그건 값의 의미를 *마지막 관측* → *당일 최대 관측* 으로 바꾸는 **행위 변경**이라
Stage 0 범위를 벗어난다. ⇒ **last-write-wins 로 고정**했다
(`test_record_twice_when_same_day_then_last_write_wins`).
전환이 필요하면 그 테스트의 **의미 전환**으로 처리한다.

### 4.5 `_scan_stats` 3 카운터 저장 위치

`get_scan_stats()` 가 신규 인스턴스에서도 3키를 0으로 노출해야 한다
(`_empty_scan_stats()` 편입이 가장 단순한 만족 경로).
알려진 한계: `prepare()` 가 `_scan_stats` 를 재생성하므로 카운터가 그때 초기화된다.
BFB 는 prepare 가 사실상 부팅 1회라 일 누적이 보존되고, VCP 는 후보 0일 때 재-prepare 가
돌지만 그 경우 관측 자체가 0이라(후보 없으면 `check_buy_signal` 이 게이트 전에 return)
정합이 깨지지 않는다. **`_reset_daily_state` 배선은 요구하지 않는다** — scheduler diff 0 유지.

---

## 5. 회귀 안전성 (신규 파일이 기존 테스트를 건드리지 않았음)

```bash
python -m pytest -q tests/unit/realtime/ tests/unit/ast/ \
  tests/unit/engine/strategies/test_bull_flag_breakout.py \
  tests/unit/engine/strategies/test_bull_flag_breakout_retention.py \
  tests/unit/engine/strategies/test_vcp_breakout.py \
  tests/unit/engine/test_universe_guard.py \
  --ignore=<cycle227 신규 2파일>
→ 805 passed, 1 skipped, 26 xfailed in 5.20s
```

은폐 테스트 3파일(`test_bull_flag_breakout.py` / `..._retention.py` / `test_vcp_breakout.py`)의
`ticker_prices["acml_vol"]` 손주입은 **명세대로 이번엔 유지**했다 —
Stage 0 에서는 게이트가 여전히 그 키를 읽으므로 지금 제거하면 그 파일들이 깨진다.
전환 의무 주석 마커는 Green 단계에서 backend-dev 가 단다.

---

## §6. 8영역 diff-zero 가드 면제 핀 (Green 후속)

Green 완료(cycle227 103/103 PASS) 후 전체 회귀에서 **6건**이 남았다. 전부 사이클 223/226 이
심어둔 "8영역 diff 0" 자기소멸형 가드이고, **이번 사이클의 사용자 승인 변경이 설계 의도대로
걸린 것**이다. 가드가 마련해 둔 정규 면제 절차(**내용 sha256 핀**)로 처리했다.

### 6.1 걸린 원인 (핀 전 실측)

```
8영역 변경    : src/engine/risk.py, src/realtime/handler.py
전략 파일 변경: src/engine/strategies/bull_flag_breakout.py,
                src/engine/strategies/vcp_breakout.py
```

핀 전에 네 파일의 `git diff HEAD` 를 전수 육안 확인했다 — 가드 실패 메시지가
*"핀을 먼저 재산출하지 마라"* 를 명시하기 때문이고, 그 절차를 건너뛰면 범위 밖 8영역
변경이 그대로 새 스냅샷으로 봉인된다.

| 파일 | diff | 판정 |
|---|---|---|
| `handler.py` | `_parse_acml_vol`(fields[13], 실패 시 **-1**) + `_handle_tick` 의 `acml_vol=` 키워드 전달 + docstring | 승인 범위(W1). `len(fields) < 10` 가드 byte 불변 |
| `risk.py` | `on_tick(*, acml_vol: int = -1)` + `acml_vol >= 0` 시 `tick_volume.record_acml_vol` | 승인 범위(W2). `ticker_prices` 4키 불변 |
| `bull_flag_breakout.py` | **+78/-0** — `_scan_stats` 3키 · cap 헬퍼 · `_observe_vol_gate` | 승인 범위(W4). 기존 거래량 컷 블록 무접촉 |
| `vcp_breakout.py` | **+81/-0** — 동형 + `vol_threshold<=0` 거울 정합 | 승인 범위(W5). 동일 |

두 전략 파일은 **순수 추가(159 insertions / 0 deletions)** 이고, 게이트 블록 불변은
`test_cycle227_ast_acml_vol_guards.py::test_AST2_...` 의 소스 pin 이 독립적으로 강제한다
= Stage 0(행위 변경 0) 이중 봉인.

### 6.2 핀 위치 (3 파일 · 4 dict)

| 가드 파일 | dict | 핀 대상 | 비고 |
|---|---|---|---|
| `tests/unit/ast/test_cycle223_ast_donchian_exit_fix.py` | `_PREEXISTING_CONTENT_SHA` | risk.py, handler.py | 기존 기전 재사용(빈 dict → 2항목) |
| 같은 파일 | `_CYCLE227_STRATEGY_CONTENT_SHA` **(신설)** | BFB, VCP | `test_g223_12` 는 면제 기전이 **없었다**(`out == ""`) → 동일 패턴 이식 |
| `tests/unit/ast/test_cycle223f_ast_manual_apply_safeguard.py` | `_PREEXISTING_CONTENT_SHA` | risk.py, handler.py | 자매 가드와 **같은 값**(값이 갈리면 그 자체가 결함 신호) |
| `tests/unit/engine/strategies/test_cycle226_zero_breakout_defense.py` | `_ALLOWED_CONTENT_SHA` **(교체)** | risk.py, handler.py | `_ALLOWED: set[str]`(**파일명** 면제 = 영구) → 내용 sha 핀(**자기소멸**) |

핀 값:

```
58d7ceea73b24b292ebaeb95e570e9dbe5015349c7eeacc92725b049f4e16463  src/engine/risk.py
d43b6ad4dbd5ec580832ee08ac6213ff5d1858e3a93503992bde25424d965362  src/realtime/handler.py
a8ec2ae51330f8a2290adc0629b8c005f56f5db948fa00e5c6ab3cd8c7c87375  src/engine/strategies/bull_flag_breakout.py
a9338a699df5286e96209b6a47b42d930af2af390bef64512eba8c232b6ec3d9  src/engine/strategies/vcp_breakout.py
```

`test_cycle223g3_ast_guard_sees_staged.py` 의 2건은 위 두 가드를 그대로 호출하는 래퍼라
**자연 해소**됐다(별도 조치 없음). 같은 파일의 `test_g3_8_pins_match_current_tree` 가
핀 스테일을 추가로 교차 검증한다.

### 6.3 가드 완화는 하지 않았다

- **검사 로직 본체 무변경** — 면제 dict / `_content_sha` 헬퍼만 추가. skip·xfail·파일명
  면제 일절 없음.
- 핀에 **없는** 8영역·전략 파일이 바뀌면 여전히 즉시 FAIL.
- 핀에 **있는** 파일도 내용이 1바이트라도 달라지면 FAIL.
- **자기소멸** — cycle227 이 커밋되면 네 경로는 `git diff HEAD` 에 나타나지 않아 면제가
  조회조차 되지 않는다. 각 dict 에 `TODO(cycle227 커밋 후): 항목 삭제` 를 남겼다.
- 특히 `test_cycle226` 은 원래 `_ALLOWED: set[str]`(빈 집합)이었다. 거기에 파일명을
  넣는 순간 면제가 **영구**가 되므로 — cycle222-a3 이 *"제외 결정이 한쪽 경로에만
  걸리면 제외가 아니다"* 를 근거로 파일명 면제를 버린 바로 그 이유 — 이름을 등록하는
  대신 자매 가드의 자기소멸 기전을 이식했다.

### 6.4 뮤테이션 검증 — 면제가 가드를 공허화하지 않았음을 실증

사이클 224 의 **자기 가드 공허성**(정의상 항상 참이던 AST 가드가 뮤테이션 전후 모두 통과)
교훈에 따라, 핀이 "그 파일을 영원히 무시" 로 퇴화하지 않았는지 직접 확인했다.

```
handler.py 끝에 주석 1줄 추가 → sha d43b6ad4… → 37e36155…
→ 6 failed  (test_g223_10 / test_g223f_9 / test_g3_7[×2] / test_g3_8 /
             test_common_1_eight_areas_untouched)
원복 → shasum 재확인 d43b6ad4dbd5ec580832ee08ac6213ff5d1858e3a93503992bde25424d965362 ✅
```

**새로 이식한 `test_cycle226` 가드도 함께 FAIL** 했다 — 이식이 형식만 옮긴 것이 아니라
실제로 동작한다는 뜻이다. 원복 후 네 파일의 sha 는 핀 값과 정확히 일치한다.

### 6.5 검증 수치

```
6건 재실행 (+ g3 파일 전체)         : 19 passed
cycle227 신규 8파일                 : 103 passed
전체 백엔드 (__pycache__ 청소 후)   : 5,617 passed / 9 skipped / 328 xfailed / 13 xpassed
                                      실패 0  (124.01s)
```

사이클 226 기준선 5,514 → **5,617** = cycle227 신규 103 정확히 일치(기존 테스트 증감 0).
