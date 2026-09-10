# cycle278 — 전략 파라미터 카탈로그 + 편집 UI · Red 명세

- **작업 디렉터리** `/Users/koscom/Projects/auto_stock_wt278` (브랜치 `cycle278-param-catalog`, base `34ba9e6`)
- **단계** Red 설계. 이 문서 시점에 존재하는 산출물은 `src/engine/param_catalog.py` **하나**뿐이고
  테스트·프론트·라우트 코드는 **아직 없다**(Green 이 만든다).
- **매매 행위 변경 0.** 이 사이클은 사람이 값을 고칠 **수단**을 만든다. 값 자체는 한 글자도 바꾸지 않는다.
- **무접촉** 8영역(`src/engine/{risk,order_engine,session,scanner,strategy_registry}.py` · `src/api/order.py` ·
  `src/realtime/**` · `src/auth/**`) · `scheduler.py` · `strategy_base.py` · 전략 7파일 ·
  `recommendation_engine.py` 의 `PARAM_RANGES`/`INT_PARAMS`.

---

## 0. 문제 정의 (브리프 §1 실측 정정 2건)

브리프 §1 의 두 문장이 워크트리 실측과 어긋난다. 명세는 **실측 쪽**을 따른다.

| # | 브리프 원문 | 실측 | 이 명세의 처리 |
|---|---|---|---|
| 정정-1 | "`frontend/src/api/` 어디에도 파라미터 PUT 호출이 **없다**" | `frontend/src/api/trading.ts:41-50 updateStrategyParams` 가 존재하고 호출자가 둘이다 — `Settings.tsx:65-76 paramMutation`(24키 하드코딩 화이트리스트 ∩ `typeof === 'number'`) · `Settings.tsx:511-525 ExchangeBoardRow`(`{exchange, tradable_boards}`) | 과제는 "편집 수단 신설"이 아니라 **"프론트 24키 하드코딩 카탈로그 → 백엔드 99키 카탈로그 대체 + 비수치 타입 지원 + 오류 표시 보강"**. §6·§7 의 스코프가 이에 맞춰 넓어진다 |
| 정정-2 | deprecated 예시로 `k_value_nxt_post` 를 지목 | LTV 는 `DEFAULT_TRADABLE_BOARDS=("pre_nxt","main","post_nxt")` 라 그 키를 **야간 목표가에 실제로 곱한다**. 죽은 것은 `("main",)` 인 **VB 에서만**이다 | deprecated 는 키 단위 bool 로 남기고, 전략 한정 무효는 새 필드 `deprecated_for` 로 표현(§1.3) |

정정-1 이 만드는 실제 갭: **99 − 26 = 73키가 화면에서 편집 불가**이고
(`Settings.tsx:365` 가 `k in PARAM_LABELS && typeof params[k] === 'number'` 로 이중 게이팅한다),
그중 `bool`·`str`·`enum`·`list_str` 키는 **구조적으로** 화면에 올 수 없다.

---

## 1. 산출물 1 — `src/engine/param_catalog.py` (작성 완료)

### 1.1 사실 요약 (실측)

| 항목 | 값 |
|---|---|
| 키 총수 | **99** (bfb 35 · vcp 37 · koj 37 · vb 30 · don 29 · ltv 27 · mom 10) |
| 그룹 분포 | 진입 47 · 청산 21 · 사이징·리스크 8 · 스캔·유니버스 5 · 시간·보드 4 · 관측·게이트 6 · 레거시 8 |
| `risk="identity"` | **13** (브리프 목록과 정확히 일치) |
| `deprecated=True` | **8** (전부 `editable=False`) |
| `auto_tunable=True` | **24** = `PARAM_RANGES` 26키 − 유령 2키(`stop_loss_main`·`stop_loss_pre_nxt`) |
| `editable=True` | 91 |
| 범위 출처 | clamp 6 · param_ranges 23 · sign 6 · structural 48 · enum 7 · **none 9** |

`range_src="none"` 9키 = `max_scan_stocks` + 레거시 8키.

### 1.2 범위(min/max)를 **지어내지 않는** 규칙

`clamp`(읽는 쪽 하드 클램프) · `param_ranges`(PARAM_RANGES 원문) · `sign`(코드 부호 규약) ·
`structural`(자료형·구조상 필연) · `enum`(값 집합) 중 하나가 없으면 `min=max=None`,
`range_src="none"` 이고 검증은 **자료형·부호·enum 까지만** 한다.

> ⚠️ **HAZARD-1 (최우선)** — 카탈로그 범위를 `PARAM_RANGES` 에서 **파생시키면 즉시 무매매 사고**다.
> `max_scan_stocks` 의 PARAM_RANGES 상한은 **500** 인데 bfb·vcp·kojiro 의 현재 기본값은 **4000** 이다
> (실측 확인). 파생하면 운영자가 아무것도 안 바꾸고 저장만 눌러도 3 전략이 422 가 된다.
> `PARAM_RANGES` 는 *AI 튜너가 밤새 흔들어도 되는 좁은 안전대*이지 사람의 편집 한계가 아니다.
> 그래서 이 키만 `range_src="none"` 이고, **나머지 23키는 PARAM_RANGES 를 그대로 복사**했다
> (그 23키는 7 전략 기본값을 전부 포함함을 실측으로 확인 — C4 가 잠근다).

### 1.3 `deprecated` vs `deprecated_for`

- `deprecated=True` (8키) — **어느 전략에서도** 행위 참조 0건. 숨기지 않고 회색 + "미사용" 배지 +
  `editable=False`. 값이 바뀌어도 매매가 안 바뀌는 입력란은 운영자를 속인다.
  - 완전 무참조 4: `max_units_per_stock` · `max_units_total` · `quant_min_f_score` · `quant_max_mf_rank`
  - 표시 문자열에서만 읽혀 배제 로직 0인 4: `quant_filter_enabled` · `rs_filter_enabled` ·
    `rsi_filter_enabled` · `rsi_extreme_max`
- `deprecated_for=(전략id,…)` — **그 전략에서만** 현재 기본 설정상 효력 없음.
  유일 사례 `k_value_nxt_pre` · `k_value_nxt_post` → `("volatility_breakout",)`.
  조건부라는 점을 `help` 가 밝힌다(VB 의 `tradable_boards` 에 보드를 추가하면 되살아난다).

### 1.4 `type` 과 단위 — 이름으로 추론 금지

| type | 저장 | 화면 |
|---|---|---|
| `int` / `float` | 그대로 | 그대로 + `unit` |
| `percent` | **비율 0.0~1.0** | ×100 하여 `%` |
| `bool` / `enum` / `list_str` / `str` | 그대로 | 체크박스 / 셀렉트 / 다중선택 / 텍스트 |

> ⚠️ 접미사 `_pct` 가 두 규약에 모두 쓰인다 — 퍼센트(`hard_stop_pct=-8.0`, `min_vol_floor_pct=1.0`,
> `max_open_risk_pct=4.5`, `gap_up_skip_pct=5.0`) vs 비율(`base_depth_pct=0.3`).
> **이름 기반 추론은 폐기된 `v / 100 if v > 1 else v` 휴리스틱의 재현**이다(루트 CLAUDE.md
> "비중 단위 추론 변환 금지"). `type`/`unit` 은 코드의 `/100`·`×100` 사용처로만 판정했다.

화면 포맷터는 **키가 아니라 `unit`** 으로 분기한다(`UNITS` 닫힌 어휘 12종). 이것이 §6(d)
"프론트 키 하드코딩 0건" 가드의 전제다.

### 1.5 브리프 3-1 대비 필드 추가 4건 (근거)

| 필드 | 근거 |
|---|---|
| `applies_to` | 작업 지시 명시 |
| `choices: tuple[Choice, …]` | `type="enum"` 은 값 집합 없이는 사용 불가. 프론트에 값 집합을 두면 **가드 (d) 자체를 위반**한다. `Choice(value, label_ko, deprecated, help)` 로 `krx_open`/`krx_after`(사이클 26 비활성) 같은 **비활성 선택지**까지 표현한다 |
| `pattern` | `entry_start`/`entry_end` 형식 검증이 **선택이 아니라 필수**다 — 파서가 `int()` 캐스트만 하므로 `25:00`·`9시5분` 이 `check_buy_signal` 안에서 `ValueError` 를 던져 `risk.on_tick` 으로 전파된다(HAZARD-8). `exclude_tickers` 항목은 6자리 숫자 |
| `range_src` | 범위 출처의 기계 판독. C4·C5 가드가 이 값으로 "PARAM_RANGES 복사본은 원문과 정확히 일치" 를 잠근다 |
| `deprecated_for` | §0 정정-2 |

### 1.6 불변식 데이터

- `BUDGET_INVARIANT` — `position_ratio × max_positions <= 1.0`. **422 로 강제**(브리프 3(c)).
- `ORDER_INVARIANTS` (12건, `enforced=False`) — `lo_key <= hi_key` 쌍. 위반해도 코드가 막지 않지만
  **무증상으로** 후보가 0 이 되거나 설계 의도가 죽는다. 422 가 아니라 `warnings` 로 알린다(§5.4).

---

## 2. 산출물 2 — 신규 leaf `src/engine/param_validation.py` (Green 작성)

브리프 §4 산출물 목록에 없는 **추가**다. 근거 3가지:

1. 검증 로직을 라우트에 두면 `src/routes/strategies.py` 가 240L → ~400L 이 되고 순수 함수로 테스트할 수
   없다(§7 백엔드 Red 14건이 라우트 없이 도는 것이 이 파일 덕분이다).
2. HAZARD-6 — AI 자문 적용 경로(`src/routes/recommendations.py:177-183`)는 PUT 라우트를 거치지 않고
   `strategy.config.params` 를 직접 쓴다. 검증을 **순수 함수로 뽑아 두면** 후속 사이클에서 그 경로에
   같은 함수를 붙이는 것이 한 줄이다(이번 사이클에서는 붙이지 않는다 — 무접촉 범위 확대 금지).
3. 뮤테이션 대상이 명확해진다(M3~M5·M10~M12 가 전부 이 파일 안).

```python
def validate_params(
    strategy_id: str,
    current_params: Mapping[str, Any],   # 병합 전 그 전략의 현재 params
    incoming: Mapping[str, Any],         # 요청 바디의 params
) -> ValidationResult                    # (errors, warnings, accepted)
```

- 순수 함수. I/O·로깅·전역 상태 0. `param_catalog` 만 import 한다.
- `ValidationResult.errors: tuple[ParamError, …]` — 비어 있지 않으면 라우트가 **422**.
- `ValidationResult.warnings: tuple[ParamWarning, …]` — 200 응답에 실린다.
- `ValidationResult.accepted: dict` — 통과분만. 라우트는 이것만 병합한다.

---

## 3. 계약 C1..C46

브리프 §5 검증 게이트를 계약으로 전개한다. **각 계약은 최소 1건의 Red 테스트를 가진다**(§7 매핑).

### 3.1 카탈로그 데이터 (C1~C10)

| # | 계약 |
|---|---|
| **C1** | 7 전략 `DEFAULT_PARAMS` 키 합집합(AST 추출)과 `param_catalog.all_keys()` 가 **집합으로 동일**하다. 어느 쪽에만 있어도 실패 — 신규 전략·신규 키가 조용히 카탈로그를 빠져나가지 못한다 |
| **C2** | `len(PARAM_SPECS) == 99` 이고 키 중복 0 |
| **C3** | 모든 키의 `applies_to` 가 그 키를 `DEFAULT_PARAMS` 에 가진 전략 집합과 **정확히 일치**하고, 순서는 `STRATEGY_IDS` 순이다. `applies_to` 가 빈 키(유령 키) 0건 — 브리프 6(c) |
| **C4** | `auto_tunable=True` 집합 ⊆ `recommendation_engine.PARAM_RANGES` 키 집합. **카탈로그가 그 집합을 넓히지 않는다** — 브리프 6(b) |
| **C5** | `range_src == "param_ranges"` 인 키는 `(min, max)` 가 `PARAM_RANGES[key]` 와 **정확히 동일**하고 `auto_tunable=True` 다. 역으로 `PARAM_RANGES` 키 중 어느 전략 `DEFAULT_PARAMS` 에 존재하는 24키는 전부 `auto_tunable=True` 다 |
| **C6** | 99키 전수에 대해, `applies_to` 의 모든 전략의 **기본값이 그 키의 `[min, max]` 안**이고 `type` 과 모순되지 않는다(`int` 키는 기본값이 `int`, `enum` 키는 기본값이 `choices` 안, `str`/`list_str` 은 `pattern` 통과). 브리프 §5 3번째 게이트 |
| **C7** | `deprecated=True` 인 키는 반드시 `editable=False` 이고, 그 역은 성립하지 않아도 된다. `deprecated` 집합은 **정확히 8키**다 |
| **C7b** | `risk="identity"` 집합은 브리프 3-1 의 **13키와 정확히 동일**하다(더도 덜도 아니다). 카탈로그가 2단계 확인 대상을 임의로 넓히거나 좁히지 못한다 |
| **C8** | `deprecated_for` 의 모든 원소는 그 키의 `applies_to` 안에 있다 |
| **C9** | `range_src == "none"` 인 키는 `min is None and max is None` 이다(범위 없음을 숫자로 위장하지 않는다) |
| **C10** | 모듈 순수성 — `param_catalog.py` 의 AST 에 `src.*` import 0건, 모듈 레벨 실행문(상수 정의·docstring 외) 0건, `open`/`requests`/`logging` 호출 0건. `import` 만으로 아무 부작용도 없다 |

### 3.2 스키마 API `GET /api/strategies/params-schema` (C11~C16)

| # | 계약 |
|---|---|
| **C11** | 200 + `{success:true, data:{...}}`. `data.params` 는 **99 항목**이고 각 항목이 §4 의 필드 전부를 가진다 |
| **C12** | `data.strategies` 는 레지스트리에 등록된 전략마다 1행이고, `keys` 는 `keys_for_strategy(sid)` 와 동일하며 `params`(현재값)·`defaults`(코드 기본값)를 **함께** 준다 |
| **C13** | `defaults` 는 그 전략 클래스의 `DEFAULT_PARAMS` **깊은 복사본**이다. 응답을 만드는 과정에서 `DEFAULT_PARAMS` 나 `config.params` 가 **변경되지 않는다**(전후 동일성 단언) |
| **C14** | `data.groups` 는 `GROUPS` 순서 그대로, `data.units`/`types`/`risks` 는 닫힌 어휘를 그대로 준다 — 화면이 어휘를 하드코딩하지 않게 하는 것이 목적이다 |
| **C15** | `data.invariants.budget` 과 `data.invariants.order`(12건)를 준다 |
| **C16** | 이 엔드포인트는 `PUT /{strategy_id}/params` 와 **경로 충돌하지 않는다** — 메서드가 다르고 라우터에 `GET /{strategy_id}` 가 없다(실측). 알 수 없는 전략 id 로도 이 경로가 가로채지 않는다 |

### 3.3 저장 API `PUT /api/strategies/{id}/params` (C17~C30)

| # | 계약 |
|---|---|
| **C17** | `ParamsRequest.params` 의 유니언에 **`bool` 이 맨 앞**에 온다: `bool \| float \| int \| str \| list[str] \| None`. pydantic 2.11.2 실측 — 현행 유니언은 `True → 1.0(float)` 로 강등하고, `bool` 을 맨 앞에 두면 `True → True` 이면서 `5 → 5(int)` 도 유지된다(HAZARD-5) |
| **C18** | **(a) 미지 키 → 422.** 그 전략의 `config.params` 에 없는 키는 조용히 버리지 않고 `code="unknown_key"` 로 거부한다. 브리프 3(a) |
| **C19** | **(b) 자료형 위반 → 422** `code="type_mismatch"` (`int` 키에 `2.5`, `bool` 키에 `"yes"`, `list_str` 키에 문자열 등) |
| **C20** | **(b) 범위 위반 → 422** `code="out_of_range"`. `range_src=="sign"` 키는 메시지에 **부호 사유**를 담는다(예: `turtle_backstop_pct` 에 0/양수 → "음수가 아니면 코드가 조용히 비활성한다") |
| **C21** | **(b) enum/목록 위반 → 422** `code="not_in_choices"`, 정규식 위반 → `code="pattern_mismatch"`. `entry_start="25:00"` 은 반드시 422 다(HAZARD-8) |
| **C22** | `editable=False`(레거시 8키) 저장 시도 → 422 `code="not_editable"`. **값이 매매를 안 바꾸는 키에 저장 성공을 돌려주지 않는다** |
| **C23** | **(c) 예산 불변식.** `p = merged.position_ratio × merged.max_positions` 에 대해 §5.3 진리표대로 판정한다. 위반 시 422 `code="budget_invariant"` 이고 메시지가 **두 값과 그 곱**을 함께 보여 준다 |
| **C24** | **(d) 통과분만 병합 저장.** 요청에 없는 키는 보존된다(부분 dict 병합). 오류가 **하나라도** 있으면 **아무것도 저장하지 않는다**(all-or-nothing) — 절반만 반영된 상태를 만들지 않는다 |
| **C25** | 422 응답 본문은 §5.2 형태이고, `detail` 은 **배열**이며 각 원소가 `msg`(한글)를 가진다 — 프론트의 기존 추출기 `extractValidationMessage`(`detail[0].msg`)가 그대로 동작한다 |
| **C26** | 알 수 없는 `strategy_id` 는 **현행대로 200 + `success=false`** 다(422 로 바꾸지 않는다). 이 경로를 건드리면 기존 호출자의 오류 처리가 달라진다 |
| **C27** | 검증 전부 통과 시 응답은 200 + `success=true` + `data.applied`(실제 저장된 키·값) + `data.warnings`. **`data.applied` 를 응답에 담는 것이 계약이다** — 서버가 무엇을 저장했는지 화면이 확인할 수 없으면 조용한 데이터 소실이 계속 보이지 않는다(HAZARD-11) |
| **C28** | `save_params` 는 **병합된 전체 dict** 로 호출된다(현행 동작 보존). 단 병합의 입력은 `validate_params(...).accepted` 뿐이다 |
| **C29** | `deprecated_for` 에 그 전략이 있는 키를 저장하면 **200 + `warnings[code="no_effect_for_strategy"]`** 다(422 아님 — 값 자체는 유효하고 보드를 바꾸면 되살아난다) |
| **C30** | `range_src=="none"` 인 키(`max_scan_stocks`)를 저장하면 200 + `warnings[code="range_unbounded"]` 다. 범위 근거가 없다는 사실이 화면에 남는다 |

### 3.4 무접촉·봉인 (C31~C36)

| # | 계약 |
|---|---|
| **C31** | 8영역 8 경로 + `scheduler.py` + `strategy_base.py` + 전략 7파일의 `git diff` **0줄** |
| **C32** | `recommendation_engine.py` 의 `PARAM_RANGES` / `INT_PARAMS` **소스 세그먼트 sha256 불변**. `ast.dump` 의 sha 를 핀하지 않는다(3.12 CI ↔ 3.13 로컬 출력 상이 — cycle256/259 실측). `ast.get_source_segment` 기반 |
| **C33** | 7 전략 `DEFAULT_PARAMS` 의 **값**이 base(`34ba9e6`)와 동일하다 — 소스 세그먼트 sha 핀 7개 |
| **C34** | 읽는 쪽 하드 클램프 6곳이 **존재한다**(`strategy_base._MAX_LOT_UNITS_MIN/MAX` · `_MAX_LOT_RATIO_MULT_MIN/MAX` · `open_entry_hold_secs` `[0,600]` · `llm_buy_gate` 3키). 라우트에 422 가 생겼다고 이 클램프를 "중복"으로 제거하면 DB 직접 UPDATE·구버전 행·부팅 로드가 전부 무방비가 된다(HAZARD-7) |
| **C35** | **프론트 키 하드코딩 0건** — `frontend/src/components/StrategyParamsEditor.tsx` · `frontend/src/pages/Strategies.tsx` · `frontend/src/pages/Settings.tsx` 세 파일의 소스에 99키 중 어떤 키 이름 문자열 리터럴도 없다. **예외 3건만 허용**: ① `Strategies.tsx:70-75 THRESHOLD_KEYS` 4키(읽기 전용 요약 그리드) ② `Settings.tsx` `ExchangeBoardRow` 의 `exchange`·`tradable_boards`(라디오/체크박스 특화 UI) ③ 없음. 브리프 6(d) |
| **C36** | 위 세 파일 중 **어느 것도** `utils/paramLabels.ts` 를 import 하지 않는다. 그 파일은 `pages/Recommendations.tsx`(AI 자문 추천 표) 전용으로 남는다 — 삭제하면 자문 화면이 영문 키로 퇴행한다 |

### 3.5 화면 (C37~C44)

| # | 계약 |
|---|---|
| **C37** | 편집 패널은 스키마 응답만으로 렌더한다. 그룹 아코디언 순서 = `data.groups` 순서, 그룹 안 키 순서 = `data.params` 순서 |
| **C38** | 모든 키 행에 **현재값과 기본값이 병기**되고, 다른 경우 "기본값으로 되돌리기" 가 노출된다 |
| **C39** | 변경분 **diff 미리보기**가 저장 전에 뜬다: 키 · 라벨 · 이전값 → 새값(표시 단위 적용) |
| **C40** | `risk="identity"` 키가 변경분에 하나라도 있으면 **2단계 확인** — 체크박스를 켜기 전에는 저장 버튼이 비활성이다. `ConfirmModal`(`message: string` 단일 props)로는 목록형 확인을 담을 수 없으므로 **확인 체크박스는 편집 패널 안**에 두고 최종 확인만 공용 `ConfirmModal` 을 재사용한다(props 확장 금지 — cycle276 과 동시 편집 충돌 지점) |
| **C41** | KST **09:00~15:30** 이면 "즉시 반영" 경고 배너를 띄운다. 판정은 `frontend/src/utils/kst.ts` 에 신설하는 `kstMinutesOfDay(now?: Date)` · `isKrxMainSession(now?: Date)` 로 하고 **`now` 주입 seam 을 가진다**(CI 시각 의존 실패 재발 차단 — `owns_board(now<09:05)` 선례). `new Date().getHours()` 는 전역 금지 |
| **C42** | 422 는 **필드별 오류**로 표시한다 — `detail[]` 의 각 원소를 `key` 로 그 행에 붙이고, `key` 가 없는 오류(불변식 등)는 폼 레벨에 표시한다. 오류 표시 후에도 패널은 **닫히지 않는다** |
| **C43** | 200 + `warnings[]` 는 저장 성공으로 처리하되 경고 목록을 보여 준다(패널은 닫는다) |
| **C44** | `deprecated=True` 키는 **숨기지 않는다** — 회색 + "미사용" 배지 + 입력 비활성. `deprecated_for` 에 해당 전략이 있으면 "이 전략에선 무효" 배지 |

### 3.6 목·E2E (C45~C46)

| # | 계약 |
|---|---|
| **C45** | MSW(`frontend/src/test/handlers.ts`)와 Playwright(`e2e/fixtures/api-mocks.ts`)에 스키마 엔드포인트가 등록된다. **미등록이면 vitest 는 즉시 붕괴**(`setup.ts:6 onUnhandledRequest:"error"`)하고 e2e 는 실서버로 새어 ECONNREFUSED 타임아웃이다. 두 파일 모두 **말단 append 만** 하고 기존 줄을 재배열하지 않는다(cycle276 병합 충돌 최소화). Playwright 는 LIFO 라 `installApiMocks` **본문 최말단**에 등록한다(파일 자신의 주석이 이 관례의 정본) |
| **C46** | MSW 목의 `params-schema` 응답은 **실제 카탈로그 형태**를 담는다 — 최소한 `percent`·`enum`·`bool`·`list_str`·`str`·`deprecated`·`identity`·`range_src="none"` 각 1키 이상. 목이 *의도한 계약*만 담고 *실제 응답*을 안 담아 3개월 초록이었던 cycle266 선례(`change_rate` Decimal 문자열)를 반복하지 않는다 |

---

## 4. 스키마 API 응답 형태

```
GET /api/strategies/params-schema
```

```jsonc
{
  "success": true,
  "message": "",
  "data": {
    "catalog_version": "cycle278.1",

    "groups": [
      { "id": "entry", "label_ko": "진입",
        "description": "무엇을 언제 사는가 — 후보 조건·돌파 판정·재진입 쿨다운" }
      // … GROUPS 순서 그대로 7개
    ],
    "types":  ["int","float","percent","bool","enum","list_str","str"],
    "risks":  ["normal","high","identity"],
    "units":  ["","%","배","유닛","원","일","봉","분","초","개","회","점"],

    "params": [
      {
        "key": "position_ratio",
        "label_ko": "종목당 비중",
        "group": "sizing_risk",
        "type": "percent",
        "min": 0.01, "max": 1.0, "step": 0.01,
        "unit": "",
        "editable": true,
        "risk": "high",
        "auto_tunable": true,
        "deprecated": false,
        "deprecated_for": [],
        "range_src": "param_ranges",
        "pattern": null,
        "choices": [],
        "applies_to": ["momentum","volatility_breakout","long_tail_volatility",
                       "donchian_swing","bull_flag_breakout","vcp_breakout","kojiro"],
        "help": "종목당 매수금액 = 순자산 × 현금사용비율 × … **비율 저장**(0.25 = 25%). …"
      },
      {
        "key": "tradable_boards",
        "label_ko": "매매 허용 보드",
        "group": "time_board",
        "type": "list_str",
        "min": null, "max": null, "step": null,
        "unit": "",
        "editable": true, "risk": "identity",
        "auto_tunable": false, "deprecated": false, "deprecated_for": [],
        "range_src": "enum", "pattern": null,
        "choices": [
          { "value": "pre_nxt",   "label_ko": "NXT 프리마켓 (08:00~09:00)",
            "deprecated": false, "help": "" },
          { "value": "krx_open",  "label_ko": "KRX 동시호가 (비활성)",
            "deprecated": true,
            "help": "사이클 26 에 비활성 — 선택해도 매매 시각이 생기지 않는다" },
          { "value": "main",      "label_ko": "KRX 메인 (09:00~15:39:59)",
            "deprecated": false, "help": "" },
          { "value": "krx_after", "label_ko": "KRX 시간외 (비활성)",
            "deprecated": true,  "help": "사이클 26 에 비활성 …" },
          { "value": "post_nxt",  "label_ko": "NXT 애프터마켓 (15:40~20:00)",
            "deprecated": false, "help": "" }
        ],
        "applies_to": ["momentum", "…7개"],
        "help": "**매수 진입 전용**이다 — 매도·손절·… 은 보드와 무관하게 항상 작동한다. …"
      }
      // … 99개
    ],

    "strategies": [
      {
        "strategy_id": "momentum",
        "name": "모멘텀",
        "enabled": true,
        "keys": ["tradable_boards","exchange","buy_threshold","…"],   // 10개
        "params":   { "buy_threshold": 29.0, "max_positions": 4, "…": "…" },  // 현재값
        "defaults": { "buy_threshold": 29.0, "max_positions": 4, "…": "…" },  // 코드 기본값
        "deprecated_for_keys": []
      },
      {
        "strategy_id": "volatility_breakout",
        "…": "…",
        "deprecated_for_keys": ["k_value_nxt_pre", "k_value_nxt_post"]
      }
      // … 등록된 전략 전부
    ],

    "invariants": {
      "budget": {
        "expr": "position_ratio * max_positions <= 1.0",
        "keys": ["position_ratio", "max_positions"],
        "enforced": true,
        "description": "한 전략이 배정 자금의 100% 를 넘게 청약하지 못한다. 7 전략 중 6 전략의 기본값이 정확히 1.0 이라 한쪽만 올리면 반드시 위반한다."
      },
      "order": [
        { "lo_key": "base_min_days", "hi_key": "base_max_days",
          "strategies": ["vcp_breakout"], "enforced": false,
          "consequence": "역전 시 탐색 range 가 비어 후보 0(무증상)" }
        // … 12건
      ]
    }
  }
}
```

**현재값(`params`)과 기본값(`defaults`)을 스키마 응답에 함께 담는다.** 별도 `GET /api/strategies`
(staleTime 15s + refetchInterval 60s)와 섞으면 diff 미리보기가 낡은 기준값으로 계산된다.
편집 패널은 **이 한 응답**으로 렌더한다.

프론트 useQuery 규약: `queryKey: ['strategy-params-schema']`, **`retry` 명시 필수**
(`_ast_useQuery_retry_required.test.ts` 관례 — 신규 컴포넌트와 `Strategies.tsx` 를 그 가드의
`TARGET_FILES`/`TARGET_PAGES` 에 등재한다). 패널을 열 때 lazy fetch 라면 `enabled` 와 함께
`retry` 도 명시한다.

---

## 5. PUT 검증 규칙과 422 본문

### 5.1 판정 순서 (앞 단계에서 오류가 나도 **뒤 단계를 계속 돌려 전 오류를 모은다**)

```
0) strategy 조회 실패        → 200 + success=false (현행 보존, C26)
1) 키 존재                    → unknown_key
2) editable                   → not_editable
3) 자료형                     → type_mismatch
4) enum / choices / pattern   → not_in_choices / pattern_mismatch
5) min / max                  → out_of_range
6) 예산 불변식(병합 결과)      → budget_invariant       ← 유일한 다중 키 오류
7) 순서 불변식(병합 결과)      → warning only
8) errors 비어 있으면 병합 저장 → 200 + applied + warnings
```

한 번의 저장으로 여러 필드를 고치는 화면이므로 **첫 오류에서 멈추지 않는다** — 멈추면 운영자가
오류를 하나씩 왕복하며 고치게 되고, 그 왕복마다 C24 의 all-or-nothing 이 다시 걸린다.

### 5.2 422 본문

```jsonc
// HTTP 422
{
  "detail": [
    {
      "key": "position_ratio",
      "code": "out_of_range",
      "msg": "종목당 비중은 0.01 ~ 1.0 이어야 합니다 — 받은 값 1.5 (비율 저장, 화면 표시는 %)",
      "strategy_id": "momentum",
      "given": 1.5,
      "expected": { "min": 0.01, "max": 1.0, "type": "percent", "range_src": "param_ranges" }
    },
    {
      "key": "entry_start",
      "code": "pattern_mismatch",
      "msg": "매수 시작 시각은 HH:MM(24시간) 형식이어야 합니다 — 받은 값 '25:00'. 형식이 틀리면 장중 매수 판정에서 예외가 납니다",
      "strategy_id": "bull_flag_breakout",
      "given": "25:00",
      "expected": { "pattern": "^([01][0-9]|2[0-3]):[0-5][0-9]$", "type": "str" }
    },
    {
      "key": null,
      "code": "budget_invariant",
      "msg": "종목당 비중 × 동시 보유 종목수 = 0.3 × 4 = 1.20 으로 1.0 을 넘습니다 — 두 값을 같은 저장에서 함께 조정하세요",
      "strategy_id": "momentum",
      "given": { "position_ratio": 0.3, "max_positions": 4, "product": 1.2 },
      "expected": { "max_product": 1.0 }
    }
  ]
}
```

- `detail` 은 **배열**이고 각 원소가 `msg`(한글)를 가진다 → 프론트의 기존 `extractValidationMessage`
  (`detail[0].msg`)가 재포장 없이 동작한다(C25). 새 편집 패널은 배열 전체를 읽어 `key` 별로 붙인다.
- `msg` 에 pydantic 접두사(`Value error, `)를 **넣지 않는다**. `PYDANTIC_MSG_PREFIX_RE` 가
  알려진 접두사만 제거하므로 접두사 없는 한글 메시지는 그대로 통과한다.
- `code` 어휘: `unknown_key` · `not_editable` · `type_mismatch` · `not_in_choices` ·
  `pattern_mismatch` · `out_of_range` · `budget_invariant`.

### 5.3 예산 불변식 진리표 (HAZARD-3 / HAZARD-4)

`p_before` = 저장 전 값의 곱, `p_after` = 병합 결과의 곱, `EPS = 1e-9`.

| p_after | p_before | 판정 | 근거 |
|---|---|---|---|
| `<= 1.0 + EPS` | — | **통과** | 정상 |
| `> 1.0 + EPS` | `<= 1.0 + EPS` | **422** `budget_invariant` | 사람이 새로 위반을 만들었다 |
| `> 1.0 + EPS` | `> 1.0 + EPS`, `p_after <= p_before + EPS` | **통과 + warning `budget_invariant_preexisting`** | 이미 위반 중인 상태를 **악화시키지 않는** 편집까지 막으면 그 전략은 **영구 편집 불가**가 되고 복구 수단이 DB 직접 UPDATE 밖에 안 남는다(장중 재시작 금지 D6 때문에 더 위험) |
| `> 1.0 + EPS` | `> 1.0 + EPS`, `p_after > p_before + EPS` | **422** | 악화 |
| 두 키 중 하나라도 병합 결과에 없음 | — | **검사 생략** | 판정 불가는 fail-open |

- `EPS` 필수 — `0.15 × 6 = 0.8999999999999999`, `0.3 × 4 = 1.2000000000000002` (부동소수 실측).
  경계 `1.0` 은 **통과**여야 한다(7 전략 중 **6 전략의 현재 기본값이 정확히 1.0** — 실측:
  mom 0.25×4 · vb 0.1×10 · don 0.2×5 · bfb 0.25×4 · vcp 0.2×5 · koj 0.2×5, LTV 만 0.9).
  부등호를 `<` 로 바꾸면 그 6 전략이 **전면 저장 불가**가 된다(뮤테이션 M5).
- 부팅 시점 관찰(`portfolio_risk.check_budget_invariant`)은 **그대로 유지**한다 — 라우트 검증이
  그 관찰을 대체하지 않는다(DB 직접 UPDATE·구버전 행은 라우트를 안 거친다).

### 5.4 경고(200 동반) 어휘

| code | 조건 |
|---|---|
| `budget_invariant_preexisting` | §5.3 3행 |
| `order_invariant` | `ORDER_INVARIANTS` 12건 중 병합 결과가 `lo > hi` 인 것 |
| `no_effect_for_strategy` | `deprecated_for` 에 그 전략이 있는 키를 저장(C29) |
| `range_unbounded` | `range_src == "none"` 인 키를 저장(C30) |

**순서 불변식을 422 로 올리지 않는 이유**: 브리프 3(c)가 강제를 요구한 것은 예산 불변식 하나이고,
순서 불변식을 422 로 만들면 두 키를 동시에 뒤집는 정상 편집(예: 창을 통째로 옮기기)이 중간
상태에서 막힌다. 다만 **위반이 무증상**이라는 것이 이 프로젝트가 가장 싫어하는 성질이므로
경고로 반드시 남긴다. 422 승격은 §9 이견 D3 으로 남긴다.

### 5.5 기존 계약 테스트 2건이 **의도적으로 깨진다** (은폐 금지)

| 파일:라인 | 현행 단언 | 새 계약 |
|---|---|---|
| `tests/contract/test_routes_strategies.py:90` `test_update_params_ignores_unknown_keys` | 미지 키는 조용히 무시 + 200 | **422 `unknown_key`** (C18). 테스트를 새 이름 `test_update_params_when_unknown_key_then_422` 로 다시 쓴다 |
| `tests/contract/test_routes_strategies.py:75` `test_update_params_when_known_strategy_then_applied` | momentum 에 `position_ratio=0.3` → 200 | `0.3 × 4 = 1.2 > 1.0` → **422 `budget_invariant`** (C23). 200 을 유지하려면 `max_positions` 를 함께 보내거나 `position_ratio=0.2` 로 바꾼다 — **후자를 택하고**, 전자(두 키 동시 전송 → 200)를 검증하는 케이스를 신설한다 |

두 변경 모두 커밋 메시지·사이클 보고서에 **명시**한다. 조용히 고치면 계약 변경이 은폐된다.

### 5.6 호출자 전수 확인 (브리프 §3 ⚠️ 대응)

| 호출자 | 이 변경으로 깨지는가 | 조치 |
|---|---|---|
| `Settings.tsx:65-76 paramMutation` (24키·number 전용) | **깨진다.** `handleSaveParams` 는 편집한 키만이 아니라 **패널이 연 키 전체**를 매번 보내므로(`Settings.tsx:168-175`), 그중 한 키라도 범위를 벗어나면 그 전략의 저장이 통째로 422 다 (HAZARD-2) | 이 구 편집 패널을 **새 `StrategyParamsEditor` 로 교체**한다(§6.1) |
| `Settings.tsx:511-525 ExchangeBoardRow` (`{exchange, tradable_boards}`) | **깨지지 않는다.** 두 키는 7 전략 `DEFAULT_PARAMS` 전부에 있고(실측) 값이 `choices` 안이다 | 유지. C35 의 키 하드코딩 예외 ②로 명시 |
| `src/routes/recommendations.py:177-183` (AI 자문 수동 적용) | **깨지지 않는다** — PUT 라우트를 거치지 않고 `config.params` 를 직접 쓴다 | 이번 사이클 무접촉. **검증 비대칭이 남는다**(§9 이견 D2) |
| `recommendation_engine.py:637` 자동 적용 | 이미 dead (`_CONSERVATIVE_KEYS = frozenset()`) | 무접촉 |
| `tools/` · `.github/` · 스크립트 | 호출 0건 (실측) | 없음 |
| 운영자 `curl` (리포 밖) | **깨질 수 있다** — 미지 키·범위 밖 값을 보내던 curl 이 이제 422 를 받는다 | 문서 3곳(`src/routes/CLAUDE.md` · `_workspace/00_leader_trading_rules.md` · 루트 CLAUDE.md)에 새 계약을 명시 |

---

## 6. 화면 구성과 testid

### 6.1 컴포넌트 배치 (단일 진실원)

```
frontend/src/components/StrategyParamsEditor.tsx   ← 신규. 편집기의 유일한 구현
        ▲                                   ▲
        │ 진입점 (브리프 §4)                  │ 구 24키 패널 자리를 대체
frontend/src/pages/Strategies.tsx        frontend/src/pages/Settings.tsx
  전략 카드 "파라미터" 버튼                  전략 카드 파라미터 섹션
```

- 같은 값을 고치는 화면이 둘이면 한쪽이 반드시 뒤처진다. 편집기 구현은 **하나**다.
- `Settings.tsx` 의 구 편집 폼(L363~407)과 `PARAM_LABELS` import(L15)를 걷어낸다.
  ⚠️ `Settings.tsx:367 if (editableKeys.length === 0) return null` 의 의미가 바뀐다 —
  카탈로그 전환 후 **7 전략 전수 렌더**를 스냅샷으로 잡는다(전략 카드가 통째로 사라지거나
  새로 나타나는 회귀 차단).
- `utils/paramLabels.ts` 는 **삭제하지 않는다**(`Recommendations.tsx:506` 이 계속 쓴다). C36 이
  세 파일에서의 import 0건을 잠근다.
- 공용 `ConfirmModal.tsx` 는 **수정하지 않는다**(`message: string` 단일 props 유지) — cycle276
  워크트리와 동시 편집 시 가장 충돌하기 쉬운 파일이다. 목록형 확인·diff 는 편집기 자체 UI 로 만든다.

### 6.2 패널 구조

```
┌ StrategyParamsEditor ────────────────────────────────────────────┐
│ [헤더] 전략명 · 카탈로그 버전 · 닫기(×)                            │
│ [배너] 장중(09:00~15:30 KST) → "지금 저장하면 즉시 반영됩니다"      │
│ [아코디언] 진입 / 청산 / 사이징·리스크 / 스캔·유니버스 /            │
│            시간·보드 / 관측·게이트 / 레거시                        │
│   └ 각 행: 라벨 · [배지들] · 입력 · 현재값 · 기본값 · [되돌리기]     │
│            └ help(접기) · 필드 오류                                │
│ [diff 미리보기] 변경분만 — 라벨 · 이전 → 새값                       │
│ [identity 확인] 체크박스 ("리스크 정체성 상수 N개를 바꿉니다")       │
│ [폼 오류] 불변식 등 key 없는 422                                   │
│ [경고] 200 + warnings                                             │
│ [취소] [저장]  → ConfirmModal (message: string)                    │
└──────────────────────────────────────────────────────────────────┘
```

**입력 위젯** — `int`/`float`/`percent` 는 `type="text" inputMode="decimal"`
(`Settings.tsx:402-407` 현행 관례), `bool` 은 체크박스, `enum` 은 `<select>`,
`list_str`(choices 있음)은 체크박스 그룹, `list_str`(pattern)은 콤마 구분 텍스트,
`str` 은 텍스트.

> ⚠️ **슬라이더(`<input type="range">`) 를 넣지 않는다.**
> `frontend/src/__tests__/designSystem.v2.test.ts:246-274` 가 문자열 리터럴
> `accentColor: '…'` 사이트를 **정확히 5** 로 고정한다(현행 5 = App 1 + TradeAmountFilterCard 1 +
> CashUsageRatioCard 1 + PriceFilterCard 2, 실측 일치). 슬라이더를 추가하면 5→6 으로 즉시 붉어진다.
> 꼭 필요하면 그 가드를 **명세 근거와 함께** 6 으로 갱신해야 하며, 무단 갱신은 가드 무력화다.

**색** — Tailwind 클래스만 쓴다. 새 hex 리터럴 금지(`designSystem.v2.test.ts:139 LEGACY_HEX` 가
`src/**` 전수를 스캔한다). 손익색 `text-pnl-*` 는 **쓰지 않는다**(손익 전용 구역).
읽기 전용 요약 4키 그리드는 기존 `Strategies.tsx:54 thresholdColor` 를 그대로 재사용하고
편집 폼에는 확장하지 않는다.

### 6.3 testid 목록

키 접미는 **밑줄 → 하이픈**(`Strategies.tsx:387` 관례). `{k}` = 하이픈화된 키,
`{sid}` = 전략 id, `{g}` = 그룹 id.

| testid | 대상 |
|---|---|
| `strategy-params-open-{sid}` | 전략 카드의 "파라미터" 버튼 |
| `strategy-params-editor` | 패널 루트 |
| `strategy-params-title` | 헤더 전략명 |
| `strategy-params-version` | 카탈로그 버전 |
| `strategy-params-close` | 닫기(`aria-label="닫기"`) |
| `strategy-params-market-warning` | 장중 경고 배너 |
| `strategy-params-group-{g}` | 아코디언 헤더 버튼 |
| `strategy-params-group-body-{g}` | 아코디언 본문 |
| `strategy-params-row-{k}` | 키 행 |
| `strategy-params-input-{k}` | 텍스트 입력 |
| `strategy-params-select-{k}` | enum 셀렉트 |
| `strategy-params-checkbox-{k}` | bool 체크박스 |
| `strategy-params-choice-{k}-{value}` | list_str 선택지 체크박스 |
| `strategy-params-current-{k}` | 현재값 |
| `strategy-params-default-{k}` | 기본값 |
| `strategy-params-reset-{k}` | 기본값 되돌리기 |
| `strategy-params-help-{k}` | help 본문 |
| `strategy-params-badge-identity-{k}` | "정체성 상수" |
| `strategy-params-badge-autotune-{k}` | "AI 자동조정" |
| `strategy-params-badge-deprecated-{k}` | "미사용" (회색) |
| `strategy-params-badge-inactive-{k}` | "이 전략에선 무효" (`deprecated_for`) |
| `strategy-params-badge-unbounded-{k}` | "범위 근거 없음" (`range_src="none"`) |
| `strategy-params-error-{k}` | 필드별 422 메시지 |
| `strategy-params-diff` | diff 미리보기 컨테이너 |
| `strategy-params-diff-row-{k}` | diff 한 줄 |
| `strategy-params-identity-ack` | identity 2단계 체크박스 |
| `strategy-params-form-error` | key 없는 422 (불변식) |
| `strategy-params-warnings` | 200 동반 경고 목록 |
| `strategy-params-warning-{code}` | 경고 한 줄 |
| `strategy-params-save` | 저장 |
| `strategy-params-cancel` | 취소 |

기존 `strategy-card-{sid}` · `strategy-{sid}-{k}`(요약 4키) · `te-*`/`rr-*` 는 **그대로 둔다**
(e2e H-ST2 가 라벨 문자열을 직접 단언한다).

### 6.4 `updateStrategyParams` 보강 (선결 조건)

`frontend/src/api/trading.ts:41-50` 은 현재 **`data.success` 검사도 422 분기도 없다**.
이 상태로 라우트만 조이면 운영자에게 `Request failed with status code 422` 라는 opaque 문자열만
보이고, `success:false`(알 수 없는 전략 id)는 **저장 성공으로 보인다**. 그래서 422 도입 **전에**
같은 파일의 `updateStrategyWeights:74-96` 과 **동형**으로 보강한다:

1. `if (!data.success) throw new Error(data.message || '파라미터 변경 실패')`
2. `axios.isAxiosError(err) && err.response?.status === 422` → `detail` 배열 전체를 담은
   구조화 오류를 던진다(기존 `extractValidationMessage` 는 요약 메시지용으로 재사용).
3. `!data.success` 가 던진 일반 `Error` 는 **재포장 금지**(기존 주석의 계약).

---

## 7. Red 목록

### 7.1 백엔드 — 5 파일 / **69건**

#### `tests/unit/engine/test_cycle278_param_catalog.py` (24건) → C1~C10

| # | 테스트 | 계약 |
|---|---|---|
| B01 | `test_catalog_when_compared_to_default_params_then_key_sets_identical` (AST 로 7 전략 추출) | C1 |
| B02 | `test_catalog_when_counted_then_99_specs_no_duplicates` | C2 |
| B03 | `test_catalog_when_key_missing_from_default_params_then_fails` (합성 결손 시나리오) | C1 |
| B04 | `test_applies_to_when_compared_then_matches_default_params_exactly` (99키 전수 파라메트라이즈) | C3 |
| B05 | `test_applies_to_when_ordered_then_follows_strategy_ids_order` | C3 |
| B06 | `test_applies_to_when_empty_then_none` (유령 키 0건) | C3 |
| B07 | `test_auto_tunable_when_compared_then_subset_of_param_ranges` | C4 |
| B08 | `test_auto_tunable_when_param_ranges_key_exists_in_defaults_then_marked_true` (24키) | C5 |
| B09 | `test_range_src_param_ranges_when_read_then_bounds_equal_param_ranges_verbatim` | C5 |
| B10 | `test_defaults_when_checked_then_within_catalog_range` (99키 × applies_to 전수) | C6 |
| B11 | `test_defaults_when_type_int_then_default_is_int_not_float` | C6 |
| B12 | `test_defaults_when_type_enum_then_default_in_choices` | C6 |
| B13 | `test_defaults_when_type_str_then_default_matches_pattern` (`entry_start`/`entry_end`) | C6 |
| B14 | `test_defaults_when_type_list_str_then_items_valid` (`tradable_boards`·`exclude_tickers`) | C6 |
| B15 | `test_max_scan_stocks_when_read_then_range_is_none_not_param_ranges` (HAZARD-1 회귀) | C9 |
| B16 | `test_deprecated_when_true_then_editable_false` | C7 |
| B17 | `test_deprecated_when_listed_then_exactly_eight_keys` | C7 |
| B18 | `test_deprecated_for_when_set_then_subset_of_applies_to` | C8 |
| B19 | `test_k_value_nxt_post_when_read_then_not_globally_deprecated_but_inactive_for_vb` (§0 정정-2) | C8 |
| B20 | `test_identity_when_listed_then_exactly_thirteen_brief_keys` | C7b |
| B21 | `test_enum_when_typed_then_choices_non_empty` | C6 |
| B22 | `test_unit_when_read_then_within_closed_vocabulary` | C14 |
| B23 | `test_module_when_parsed_then_no_src_imports_and_no_side_effects` (AST) | C10 |
| B24 | `test_module_when_imported_twice_then_specs_identical_objects` (부작용 0) | C10 |

#### `tests/unit/engine/test_cycle278_param_validation.py` (18건) → C17~C24

| # | 테스트 | 계약 |
|---|---|---|
| B25 | `test_validate_when_unknown_key_then_error_unknown_key` | C18 |
| B26 | `test_validate_when_key_not_in_this_strategy_then_error_even_if_in_catalog` (`buy_threshold` → vcp) | C18 |
| B27 | `test_validate_when_legacy_key_then_error_not_editable` (8키 전수) | C22 |
| B28 | `test_validate_when_int_key_gets_float_then_error_type_mismatch` | C19 |
| B29 | `test_validate_when_bool_key_gets_string_then_error_type_mismatch` | C19 |
| B30 | `test_validate_when_list_key_gets_scalar_then_error_type_mismatch` | C19 |
| B31 | `test_validate_when_below_min_then_error_out_of_range` | C20 |
| B32 | `test_validate_when_above_max_then_error_out_of_range` | C20 |
| B33 | `test_validate_when_sign_gated_key_gets_positive_then_error_message_explains_sign` (`turtle_backstop_pct`·`hard_stop_pct`·`gap_down_skip_pct`) | C20 |
| B34 | `test_validate_when_enum_value_unknown_then_error_not_in_choices` (`exchange="BAD"`) | C21 |
| B35 | `test_validate_when_board_value_unknown_then_error_not_in_choices` (오타 무증상 차단) | C21 |
| B36 | `test_validate_when_entry_start_malformed_then_error_pattern_mismatch` (`"25:00"`·`"9시5분"`) | C21 |
| B37 | `test_validate_when_ticker_not_six_digits_then_error_pattern_mismatch` | C21 |
| B38 | `test_validate_when_range_src_none_then_only_type_checked` (`max_scan_stocks=4000` 통과) | C30 |
| B39 | `test_validate_when_multiple_errors_then_all_reported_not_just_first` | §5.1 |
| B40 | `test_budget_invariant_when_product_exactly_one_then_pass` (6 전략 기본값, EPS 경계) | C23 |
| B41 | `test_budget_invariant_when_newly_violated_then_error` (`position_ratio=0.3` on mom) | C23 |
| B42 | `test_budget_invariant_when_both_keys_sent_together_then_pass` (`0.3` + `max_positions=3`) | C23 |

#### `tests/unit/routes/test_cycle278_params_schema.py` (10건) → C11~C16

| # | 테스트 | 계약 |
|---|---|---|
| B43 | `test_schema_when_requested_then_200_with_99_params` | C11 |
| B44 | `test_schema_when_read_then_each_param_has_all_fields` | C11 |
| B45 | `test_schema_when_read_then_strategies_have_keys_params_defaults` | C12 |
| B46 | `test_schema_when_read_then_defaults_match_class_default_params` | C12 |
| B47 | `test_schema_when_called_then_default_params_not_mutated` (호출 전후 동일성) | C13 |
| B48 | `test_schema_when_called_then_config_params_not_mutated` | C13 |
| B49 | `test_schema_when_read_then_groups_units_types_risks_are_closed_vocab` | C14 |
| B50 | `test_schema_when_read_then_invariants_budget_and_twelve_order_rules` | C15 |
| B51 | `test_schema_when_vb_read_then_deprecated_for_keys_lists_two_k_values` | C12 |
| B52 | `test_schema_path_when_registered_then_does_not_shadow_put_params` | C16 |

#### `tests/unit/routes/test_cycle278_params_validation.py` (14건) → C17~C30

| # | 테스트 | 계약 |
|---|---|---|
| B53 | `test_put_when_bool_sent_then_stored_as_bool_not_float` (pydantic 유니언 순서) | C17 |
| B54 | `test_put_when_int_sent_then_stays_int_after_bool_union` (왕복 항등) | C17 |
| B55 | `test_put_when_unknown_key_then_422_unknown_key` | C18 |
| B56 | `test_put_when_out_of_range_then_422_with_key_and_expected` | C20 |
| B57 | `test_put_when_legacy_key_then_422_not_editable` | C22 |
| B58 | `test_put_when_budget_invariant_violated_then_422_with_product_in_message` | C23 |
| B59 | `test_put_when_preexisting_violation_and_not_worsened_then_200_with_warning` (§5.3 3행) | C23 |
| B60 | `test_put_when_preexisting_violation_and_worsened_then_422` | C23 |
| B61 | `test_put_when_any_error_then_nothing_saved` (save_params 미호출 단언) | C24 |
| B62 | `test_put_when_partial_dict_then_unsent_keys_preserved` (병합 보존) | C24 |
| B63 | `test_put_when_422_then_detail_is_list_with_msg_first_element` | C25 |
| B64 | `test_put_when_unknown_strategy_then_200_success_false_not_422` | C26 |
| B65 | `test_put_when_success_then_response_contains_applied_keys` | C27 |
| B66 | `test_put_when_vb_k_value_nxt_post_sent_then_200_with_no_effect_warning` | C29 |

#### `tests/unit/ast/test_cycle278_ast_catalog_guards.py` (9건) → C31~C36

| # | 테스트 | 계약 |
|---|---|---|
| B67 | `test_param_ranges_source_segment_sha_unchanged` (`ast.get_source_segment` 기반 — **`ast.dump` sha 금지**) | C32 |
| B68 | `test_int_params_source_segment_sha_unchanged` | C32 |
| B69 | `test_seven_strategy_default_params_source_sha_unchanged` (7 핀) | C33 |
| B70 | `test_eight_areas_and_scheduler_and_strategy_base_untouched` (base 대비) | C31 |
| B71 | `test_reading_side_clamps_still_present` (6곳 상수·비교식 존재) | C34 |
| B72 | `test_frontend_editor_files_have_no_param_key_literals` (`Path.rglob` — **`git grep` 금지**, 미추적 파일 누락) | C35 |
| B73 | `test_frontend_editor_files_do_not_import_param_labels_util` | C36 |
| B74 | `test_threshold_keys_exception_is_exactly_four_and_documented` | C35 |
| B75 | `test_catalog_module_has_no_src_imports` (C10 과 별도 — AST 가드 계층) | C10 |

> 이 파일은 **프론트 파일을 읽는 백엔드 가드**를 포함한다(B72·B73). 파일 헤더에 그 사실을 적고,
> 프론트 전용 사이클의 검증 목록(`grep -rl 'frontend/' tests/unit`)에 걸리게 한다(cycle256 관례).

### 7.2 프론트엔드 — 5 파일 / **37건**

#### `frontend/src/components/__tests__/StrategyParamsEditor.test.tsx` (20건)

| # | 테스트 | 계약 |
|---|---|---|
| F01 | `그룹 아코디언이 스키마 groups 순서대로 7개 렌더된다` | C37 |
| F02 | `그룹을 열면 그 그룹의 키만 보인다` | C37 |
| F03 | `percent 키는 저장값 0.25 를 25% 로 표시하고 편집값은 비율로 되돌린다` | C37 |
| F04 | `float+unit=% 키는 -7.5 를 그대로 -7.5% 로 표시한다` (percent 와 혼동 금지) | §1.4 |
| F05 | `unit=원 키는 천단위·억 보조 표기로 렌더된다` (키가 아니라 unit 으로 분기) | C35 |
| F06 | `enum 키는 select 로, choices 라벨이 한글로 렌더된다` | C37 |
| F07 | `bool 키는 체크박스로 렌더된다` (구 화면에서 구조적으로 못 오던 타입) | C37 |
| F08 | `list_str+choices 키는 체크박스 그룹, 비활성 선택지는 회색 배지를 단다` | C37/C44 |
| F09 | `현재값과 기본값이 병기되고 다를 때만 되돌리기가 보인다` | C38 |
| F10 | `변경 전에는 diff 가 비어 있고 변경 후 그 키만 나타난다` | C39 |
| F11 | `identity 키를 바꾸면 확인 체크박스가 나타나고 켜기 전 저장이 비활성이다` | C40 |
| F12 | `identity 아닌 키만 바꾸면 확인 체크박스가 없다` | C40 |
| F13 | `deprecated 키는 숨기지 않고 회색+"미사용"+입력 비활성으로 렌더된다` | C44 |
| F14 | `deprecated_for 에 걸린 키는 그 전략에서만 "무효" 배지를 단다` (VB vs LTV 두 케이스) | C44 |
| F15 | `range_src=none 키는 "범위 근거 없음" 배지를 단다` | C44 |
| F16 | `422 detail 의 각 원소가 key 로 그 행에 붙는다` | C42 |
| F17 | `key 가 null 인 422(불변식)는 폼 레벨에 표시된다` | C42 |
| F18 | `422 를 받아도 패널이 닫히지 않는다` | C42 |
| F19 | `200+warnings 는 성공으로 처리하고 경고 목록을 보여 준다` | C43 |
| F20 | `저장은 ConfirmModal 을 거치고 취소하면 mutate 가 호출되지 않는다` | C40 |

#### `frontend/src/pages/__tests__/StrategiesParams.test.tsx` (6건)

| # | 테스트 |
|---|---|
| F21 | `전략 카드마다 "파라미터" 버튼이 있고 누르면 편집기가 열린다` |
| F22 | `읽기 전용 요약 4키 그리드는 그대로 남는다` (회귀) |
| F23 | `장중(09:00~15:30 KST) 시각 고정에서 경고 배너가 보인다` — C41 |
| F24 | `장외(예: 20:30 KST) 시각 고정에서 경고 배너가 없다` — C41 |
| F25 | `스키마 쿼리는 retry 를 명시한다` (AST/소스 단언) |
| F26 | `7 전략 전수 렌더 스냅샷` (Settings 의 `editableKeys.length === 0` 회귀 차단) |

#### `frontend/src/api/__tests__/trading.params.test.ts` (6건) → §6.4

| # | 테스트 |
|---|---|
| F27 | `success:false 2xx 응답이면 throw 한다` (현행 무증상 결함) |
| F28 | `422 detail 배열을 구조화 오류로 던진다` |
| F29 | `422 detail 이 문자열이어도 메시지를 뽑는다` |
| F30 | `pydantic 접두사 없는 한글 메시지는 잘리지 않는다` |
| F31 | `!data.success 가 던진 Error 는 재포장되지 않는다` |
| F32 | `2xx 성공 응답의 warnings 를 그대로 전달한다` |

#### `frontend/src/utils/__tests__/kstMinutes.test.ts` (4건) → C41

| # | 테스트 |
|---|---|
| F33 | `kstMinutesOfDay(now) 는 주입한 시각의 KST 분을 준다` (UTC·KST·미국 TZ 3 케이스) |
| F34 | `isKrxMainSession 은 08:59 false / 09:00 true` |
| F35 | `isKrxMainSession 은 15:29 true / 15:30 false` |
| F36 | `TZ 환경변수와 무관하게 같은 결과` (`beforeAll` TZ 고정 + 동적 import) |

#### `frontend/src/components/__tests__/_ast_param_key_hardcode.test.ts` (1건) → C35

| # | 테스트 |
|---|---|
| F37 | `편집 3파일에 99키 리터럴 0건 (예외 THRESHOLD_KEYS 4 + ExchangeBoardRow 2)` |

### 7.3 E2E — 1건

`e2e/tests/strategy-params.spec.ts` · `G-E2E-278`
: 전략 화면 진입 → "파라미터" 버튼 → 그룹 아코디언 확장 → `percent` 키 1개 수정 →
diff 확인 → identity 키 1개 수정 → 확인 체크박스 → 저장 → 200 → 목록 갱신 확인.
추가로 **범위 밖 값 → 422 → 필드 오류가 그 행에 붙고 패널이 안 닫힘**까지 1 시나리오.

### 7.4 목 갱신 (C45/C46)

- `frontend/src/test/handlers.ts` — 배열 **최말단**(L471 `),` 와 L472 `];` 사이)에
  `http.get('/api/strategies/params-schema', …)` + `http.put('/api/strategies/:id/params', …)`
  (422 시나리오 분기 포함). 기존 줄 **0줄 변경**.
- `e2e/fixtures/api-mocks.ts` — `installApiMocks` 본문 **최말단**(L631 주석 뒤, L632 `}` 앞)에
  `page.route("**/api/strategies/params-schema", …)`. LIFO 관례 준수. `envelope()` 헬퍼 사용.
- `frontend/src/components/__tests__/_ast_api_mocks_coverage.test.ts` 의 엔드포인트 목록에 추가.
- `frontend/src/components/__tests__/_ast_useQuery_retry_required.test.ts` 의
  `TARGET_FILES` 에 `StrategyParamsEditor.tsx`, `TARGET_PAGES` 에 `Strategies.tsx` 추가.

**합계 — 백엔드 69 · 프론트 37 · E2E 1.** (요구: 백엔드 ≥45 · 프론트 ≥25)

---

## 8. 뮤테이션 후보 14종 (게이트 = **12종 이상 KILLED**)

| # | 뮤테이션 | 죽이는 테스트 | 죽지 않으면 뜻하는 것 |
|---|---|---|---|
| **M1** | 카탈로그에서 키 1개 삭제 (99→98) | B01·B02 | 신규/기존 키가 조용히 화면에서 사라진다 |
| **M2** | 어느 키의 `applies_to` 에서 전략 1개 제거 | B04 | 그 전략 화면에서 그 키가 사라지고, 저장 시 `unknown_key` 오탐 |
| **M3** | `unknown_key` 오류를 만들지 않고 조용히 무시 (현행 복귀) | B25·B55 | 브리프 3(a) 무력화 — 오타가 성공 응답을 받는다 |
| **M4** | 예산 불변식 검사 삭제 | B41·B58 | 예산 200% 청약 사고 경로 부활 |
| **M5** | 예산 불변식 부등호 `<=` → `<` | B40 | **6 전략이 전면 저장 불가**(기본값이 정확히 1.0) |
| **M6** | identity 2단계 확인 없이 저장 허용 (프론트) | F11 | 리스크 정체성 상수가 한 번의 클릭으로 바뀐다 |
| **M7** | `auto_tunable` 을 `PARAM_RANGES` 밖 키에도 `True` | B07 | 카탈로그가 AI 튜닝 집합을 몰래 넓힌다 — 브리프 6(b) 위반 |
| **M8** | `deprecated` 키를 화면에서 필터링(숨김) | F13 | "미사용"을 숨기면 그 키가 왜 없는지 아무도 모른다 |
| **M9** | 부분 병합을 전체 덮어쓰기로 (요청에 없는 키 삭제) | B62 | 조용한 데이터 소실 |
| **M10** | `ParamsRequest` 유니언에서 `bool` 을 `int` 뒤로 이동 | B53·B54 | `True → 1.0` 강등 — bool 키 저장 전건 실패 |
| **M11** | `range_src="sign"` 키의 `max=0.0` → `None` | B33 | `hard_stop_pct=+8` 저장 가능 → **전 포지션 즉시 손절** |
| **M12** | `pattern` 검증 제거 | B36·B37 | `entry_start="25:00"` 이 매매 루프에서 `ValueError` 를 던진다 |
| **M13** | 카탈로그 `min/max` 를 `PARAM_RANGES` 에서 파생 | B15·B10 | `max_scan_stocks` 기본 4000 이 상한 500 을 넘어 **3 전략 저장 전면 422**(HAZARD-1) |
| **M14** | 읽는 쪽 하드 클램프 1곳 제거 (`max_lot_units`) | B71 | DB 직접 UPDATE·부팅 로드가 무방비(HAZARD-7) |

보조(선택): M15 `applies_to` 순서를 뒤집기(B05) · M16 `deprecated_for` 를 전역 `deprecated` 로
승격(B19·F14) · M17 `kstMinutesOfDay` 를 `new Date().getHours()` 로 교체(F33·F36).

---

## 9. 이견·결정 필요 (구현을 임의로 바꾸지 않고 여기 남긴다)

| # | 항목 | 조사 근거 | 이 명세의 처리 | 권고 |
|---|---|---|---|---|
| **D1** | 브리프 §1 "프론트에 PUT 호출 없음" 이 거짓 | `trading.ts:41-50` + 호출자 2곳 | 스코프를 "24키 하드코딩 → 99키 카탈로그 대체"로 정정, `Settings.tsx` 구 편집 패널 교체를 **필수**로 편입(브리프 수정 목록에 없던 파일) | 승인 |
| **D2** | 검증 비대칭 — AI 자문 적용 경로(`routes/recommendations.py:177-183`)는 PUT 을 안 거친다 | 실측 | 이번 사이클 **무접촉**. 검증을 순수 함수로 뽑아 후속 연결이 한 줄이 되게만 해 둔다 | 후속 사이클에서 연결 |
| **D3** | 순서 불변식 12건을 422 로 올릴 것인가 | 위반이 **무증상**으로 후보 0 | 이번엔 `warnings` 만 | 1주 관측 후 승격 검토 |
| **D4** | `risk="identity"` 를 코드가 실제로 "정체성 상수"라 부르는 10키까지 넓힐 것인가 — `buy_threshold`·`donchian_period`·`max_breakout_extension_pct`·`atr_trail_mult`·`breakout_fail_n_days`·`breakeven_promote_atr`·`channel_exit_period`·`rank_w_macd3/band/fresh` | 각 키의 AST 가드·PARAM_RANGES 제외 주석 | **브리프 13키를 그대로** 유지(C7b 가 잠근다). 위 10키는 `risk="high"` 로만 올렸다 | 2단계 확인 대상 확대는 사용자 결정 |
| **D5** | `max_scan_stocks` 를 `editable=False` 로 둘 것인가 | 범위 근거가 없다(작업 지시 "unresolved → editable=False") | **`editable=True` + `range_src="none"` + `risk="high"` + 배지**로 뒀다. 이유: 이 키는 **`auto_tunable=True`(AI 는 바꿀 수 있다)** 라, 사람만 못 바꾸게 하면 정확히 거꾸로다. 또 이 사이클의 목적("모든 파라미터를 UI 에서 설정 가능하게")과 정면 충돌한다 | `editable=False` 로 뒤집으려면 한 줄(그 스펙의 `editable`)만 바꾸면 된다 |
| **D6** | 브리프 3-1 필드에 4개(`applies_to`·`choices`·`pattern`·`range_src`) + 1개(`deprecated_for`) 추가 | §1.5 | 추가함 | 승인 |
| **D7** | 신규 leaf `src/engine/param_validation.py` (브리프 산출물 목록 밖) | §2 | 추가함 | 승인 |
| **D8** | 장중 배너 창을 09:00~15:30 으로 할 것인가 | 브리프 §4 는 09:00~15:30. 그러나 LTV/VB 는 `post_nxt`(~20:00) 와 `pre_nxt`(08:00~) 에서도 매매한다 | **브리프대로 09:00~15:30**. 배너 문구에 "NXT 프리/애프터 시간대에도 즉시 반영됩니다" 를 병기해 사각을 덮는다 | 창 확대는 사용자 결정 |
| **D9** | `PARAM_RANGES` 23키를 사람 편집 범위로 그대로 쓰면 사람의 한계 = AI 의 한계가 된다 | §1.2 | 근거 있는 유일한 숫자라 그대로 씀(넓히지 않음). 좁아서 막히면 그때 근거와 함께 넓힌다 | 관측 후 재검토 |
| **D10** | 기존 계약 테스트 2건이 의도적으로 깨진다 | §5.5 | 명세·커밋·보고서에 명시하고 다시 쓴다 | 승인 |

---

## 10. Red → Green 로그

| 시각(KST) | 단계 | 내용 |
|---|---|---|
| 2026-09-11 | Red 설계 | 브리프 + 조사 A·B 수신. 7 전략 `DEFAULT_PARAMS` AST 추출로 **99키** 재확인(bfb 35·don 29·koj 37·ltv 27·mom 10·vcp 37·vb 30) |
| 2026-09-11 | Red 설계 | `PARAM_RANGES` 26키 × 전략 기본값 교차 검사 → **`max_scan_stocks` 단독 충돌**(상한 500 vs 기본 4000 × 3 전략) 실측 확인 = HAZARD-1 성립 |
| 2026-09-11 | Red 설계 | pydantic 2.11.2 실측 — 현행 유니언 `True → 1.0(float)`, `bool` 선두 배치 시 `True → True` ∧ `5 → 5(int)` 확인 = C17 근거 |
| 2026-09-11 | 산출물 1 | `src/engine/param_catalog.py` 작성(1,221L). 자체 검증 스크립트로 C1~C10 전 항목 통과 확인(키 집합 동일 · applies_to 99키 전수 일치 · 기본값 전수 범위 안 · auto_tunable ⊆ PARAM_RANGES · param_ranges 복사본 원문 일치 · identity 13 · deprecated 8 · 순수성) |
| 2026-09-11 | 무접촉 확인 | 8영역 · `scheduler.py` · `strategy_base.py` · 전략 7파일 · `recommendation_engine.py` **git diff 0줄**(신규 파일 1개만 untracked) |
| — | **Red 대기** | 이 명세의 §7 (백엔드 69 · 프론트 37 · E2E 1)을 실패 테스트로 작성 → 전건 RED 확인 → backend-dev/frontend-dev 에 Green 요청 |
