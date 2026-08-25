# 사이클 227 — 검증 가능한 행위 분해 (Red 착수 문서)

> 작성: tdd-engineer, 2026-08-25
> 명세 정본: `_workspace/red/cycle227_acml_vol_stage0_spec.md`
> 배경: `_workspace/00_URGENT_WORKLIST.md` P0-1 · P0-2 / `_workspace/domain_consult/bfb_vcp_acml_vol_gate.md`

---

## 0. W6 선행 — KIS 정본 확인 결과 (필수 확인 항목)

**질의**: `FHKST01010300`(주식현재가 체결, `inquire_ccnl`) 응답 output row 에 `acml_vol` 이 있는가.

**출처**: KIS MCP `mcp__kis-code-assistant__search_domestic_stock_api(subcategory="기본시세",
function_name="inquire_ccnl")` → `mcp__kis-code-assistant__read_source_code`
(`examples_llm/domestic_stock/inquire_ccnl/inquire_ccnl.py` + `chk_inquire_ccnl.py`).

**정본 응답 컬럼 (chk 파일 `COLUMN_MAPPING` 전수 — 7개)**

| 키 | 의미 |
|---|---|
| `stck_cntg_hour` | 주식 체결 시간 |
| `stck_prpr` | 주식 현재가 |
| `prdy_vrss` | 전일 대비 |
| `prdy_vrss_sign` | 전일 대비 부호 |
| `cntg_vol` | **체결 거래량 (한 건의 체결량)** |
| `tday_rltv` | 당일 체결강도 |
| `prdy_ctrt` | 전일 대비율 |

### 판정 — **`acml_vol` 부재 확정 (7 컬럼 어디에도 없다)**

⇒ 명세 W6-2 의 "존재하면 첫 row 추출·추가 KIS 호출 0" 분기는 **성립하지 않는다.**
⇒ **`FHKST01010100`(`inquire_price` 주식현재가 시세) 폴백이 확정 경로다.**

- path `/uapi/domestic-stock/v1/quotations/inquire-price` — `src/api/base.py::_QUOTE_ALLOWED_PATHS`
  **화이트리스트 기존재** (첫 항목). 신규 등록 불필요.
- 응답 `output.acml_vol` (누적 거래량) 존재 — 프로젝트가 이미 이 경로로 `acml_vol` 을
  수집 중(`src/api/condition.py::inquire_stock_basics` 사이클 107, `src/api/CLAUDE.md:263`),
  로컬 캐시 `docs/kis/domestic-stock-quote.md:128` 도 동일.
- `today_volume`(= `cntg_vol` ~30행 합)이 "진짜 당일 누적"이 **아니라는** 진단(P0-2)도
  이 정본이 산술적으로 확증한다 — `cntg_vol` 은 정의상 **체결 1건의 거래량**이다.

### W6 계약 확정 (Red 테스트가 고정하는 것)

1. 1순위 = `tick_volume.get_observed_acml_vol(ticker)` → `vol_source="tick"` (KIS 호출 0)
2. 2순위 = **신규** `src.api.quotation.inquire_acml_vol(ticker) -> int | None`
   (FHKST01010100, targets 한정, 50ms sleep) → `vol_source="rest"`
3. 둘 다 부재 → **제외 보류** (`_universe_excluded_today` 미등록 · unsubscribe 미호출)

---

## 1. 행위 목록 (테스트 파일 ↔ 행위 ↔ Red 예상)

### W1 · handler `_parse_acml_vol` + on_tick 전달
파일: `tests/unit/realtime/test_cycle227_handler_acml_vol.py`

| # | 행위 | Red 예상 |
|---|---|---|
| W1-1 | `handler._parse_acml_vol(fields)` 가 존재하고 `fields[13]` 을 int 로 돌려준다 | RED (함수 부재) |
| W1-2 | `len(fields) < 14` → `-1` (sentinel, **`0` 금지**) | RED |
| W1-3 | 파싱 실패(빈 문자열/영문/소수점/과학표기) → `-1` | RED |
| W1-4 | 음수 응답 → `-1` (미수신과 동일 취급) | RED |
| W1-5 | `_handle_tick` 이 `acml_vol=` **키워드**로 콜백에 전달 | RED |
| W1-6 | `len(fields) < 10` 가드 불변 — 9필드 payload 는 여전히 silent drop | **즉시 PASS** (현행 보존 검증) |
| W1-7 | 10~13 필드 payload 는 **틱이 살고** `acml_vol=-1` | RED |
| W1-8 | acml_vol 파싱 실패가 예외를 던지지 않는다 (재연결 오발화 차단) | RED |
| W1-9 | `day_high` 전달 계약 동시 유지 (cycle222-a 회귀) | RED (한 호출에 둘 다 요구) |
| W1-10 | 다중 레코드 프레임(46×2)에서 `fields[13]` = **첫 레코드** 값 (자문 §9.5 명시적 고정) | RED |

### W2 · risk.on_tick 키워드 수용 + 관측 기록
파일: `tests/unit/engine/test_cycle227_risk_on_tick_acml.py`

| # | 행위 | Red 예상 |
|---|---|---|
| W2-1 | 시그니처 `acml_vol` = KEYWORD_ONLY, 기본값 **-1** | RED |
| W2-2 | `acml_vol=N (N>=0)` → `tick_volume.get_observed_acml_vol(t) == N` | RED |
| W2-3 | 미전달(기본 -1) → 미기록(`None`) | RED |
| W2-4 | `acml_vol=-1` 명시 → 미기록 | RED |
| W2-5 | `acml_vol=0` → **기록됨**(`0`) — 진짜 거래량 0 과 미수신을 타입 분리 | RED |
| W2-6 | `ticker_prices[t]` 는 정확히 4키 — **`acml_vol` 키 부재** (donchian `ext_pct` 커플링 차단) | **즉시 PASS** (현행 보존 검증 · 회귀 봉인) |
| W2-7 | 기존 4-positional 호출 그대로 동작 | **즉시 PASS** |
| W2-8 | `day_high` 앵커 행위 불변 (동시 전달 회귀) | RED (동시 전달이 시그니처 요구) |

### W3 · 신규 leaf 모듈 `src/engine/tick_volume.py`
파일: `tests/unit/engine/test_cycle227_tick_volume.py`

| # | 행위 | Red 예상 |
|---|---|---|
| W3-1 | 모듈 import 가능 + 3 API(`record_acml_vol`/`get_observed_acml_vol`/`reset_for_test`) | RED (ImportError) |
| W3-2 | 미관측 → **`None`** (`0` sentinel 금지) | RED |
| W3-3 | record → get 왕복 항등 | RED |
| W3-4 | `value < 0` 무시 — 기록 안 됨 + **기존 값 덮어쓰지 않음** | RED |
| W3-5 | `value == 0` 은 유효 관측 → `0` 반환(`None` 아님) | RED |
| W3-6 | 마지막 기록 우선 (last-write-wins) | RED |
| W3-7 | 저장 날짜(KST) != 오늘 → `get` 이 `None` (크로스데이 오염 차단) | RED |
| W3-8 | 날짜 전환 후 `record` → 이전 날짜 전체 clear | RED |
| W3-9 | 날짜 판정은 **KST** (UTC 15:00 이후 = 익일 KST) | RED |
| W3-10 | `reset_for_test()` 격리 | RED |

> **명세 모호 1건 (team-leader 확인 대상, Red 는 문자 그대로 고정)** —
> W3-6 을 `max(기존, 신규)` 로 할지 last-write-wins 로 할지 명세에 없다.
> 자문 §9.5 가 "다중 레코드 프레임에서 배치 중 가장 오래된 레코드를 읽는다(과소 계상)"
> 를 인지된 노이즈원으로 남겨 뒀으므로 `max()` 가 그 노이즈를 줄일 여지는 있으나,
> 명세 문구("기록")대로 **last-write-wins 로 고정**한다. `max()` 로 바꾸는 것은
> 관측값의 의미를 "마지막 관측"에서 "당일 최대 관측"으로 바꾸는 **행위 변경**이라
> Stage 0(행위 변경 0) 범위를 벗어난다.

### W4 · BFB would_pass 관측 훅 (행위 변경 0)
파일: `tests/unit/engine/strategies/test_cycle227_bfb_vol_gate_observe.py`

| # | 행위 | Red 예상 |
|---|---|---|
| W4-1 | 관측 있음 · `observed >= threshold` → INFO `[bfb_vol_gate_observe] ... would_pass=True` | RED |
| W4-2 | 관측 있음 · `observed < threshold` → `would_pass=False` | RED |
| W4-3 | 미관측 → `[bfb_vol_gate_observe] ticker=... reason=no_observation threshold=...` | RED |
| W4-4 | **게이트 반환은 세 경우 모두 `Signal.NONE`** (Stage 0 행위 변경 0) | **즉시 PASS** (핵심 봉인) |
| W4-5 | `_scan_stats` 3 카운터(`vol_gate_observe_pass`/`_fail`/`_no_obs`) 누적 | RED |
| W4-6 | cap = `(ticker, outcome)` 1회/일 — 반복해도 로그 1행, **카운터는 계속 증가** | RED |
| W4-7 | 같은 ticker 의 다른 outcome 은 별도 cap (최대 3행/종목/일) | RED |
| W4-8 | 다른 ticker 는 별도 cap | RED |
| W4-9 | 날짜 전환 시 cap 자기 리셋 (재emit) | RED |
| W4-10 | 관측기 자기실패 → `[bfb_vol_gate_observe_failed]` **WARNING 1행** + 매수 평가 생존(NONE, 예외 미전파) | RED |
| W4-11 | 로그 본문에 타 마커 문자열 미포함 (P2-7 grep 정밀성) | RED |
| W4-12 | retention 대기 중(1차 감지)에는 관측 로그 0행 — 완주 직후에만 | RED |
| W4-13 | 카운터 3키가 `get_scan_stats()` 에 **항상 존재**(신규 인스턴스 0) | RED |

### W5 · VCP 동일 훅 (행위 변경 0)
파일: `tests/unit/engine/strategies/test_cycle227_vcp_vol_gate_observe.py`
— W4 와 동형(마커 `[vcp_vol_gate_observe]`) + 추가 1건:

| # | 행위 | Red 예상 |
|---|---|---|
| W5-x | `vol_threshold <= 0` → 게이트가 통과시키므로 `would_pass=True`(outcome=pass) **거울 정합** | RED |

### W6 · universe 가드 안전조건 시정
파일: `tests/unit/engine/test_cycle227_universe_guard_acml.py`

| # | 행위 | Red 예상 |
|---|---|---|
| W6-1 | tick 관측 있음 → 그 값으로 판정 + `vol_source=tick` + **REST 폴백 미호출** | RED |
| W6-2 | tick 관측 `>= 10_000` → 제외 안 함 (`today_volume` 이 미달이어도) | RED (현행은 축출) |
| W6-3 | tick 관측 `< 10_000` → 제외 + 로그 `acml_vol=... vol_source=tick` | RED |
| W6-4 | tick 미관측 → REST 폴백(`inquire_acml_vol`, FHKST01010100) 호출 | RED |
| W6-5 | REST 값 `>= 10_000` → 제외 안 함 / `< 10_000` → 제외 + `vol_source=rest` | RED |
| W6-6 | **둘 다 부재 → 제외 보류** (set 미등록 · unsubscribe 미호출) | RED |
| W6-7 | `today_volume` 로그 필드 유지 (운영 grep 연속성) | RED |
| W6-8 | `today_volume` 은 더 이상 **판정 소스가 아니다** (높아도 acml_vol 낮으면 제외) | RED |
| W6-9 | 보유 종목 절대 보호 (평가 대상 자체 제외) | **즉시 PASS** |
| W6-10 | 익일청산 종목 절대 보호 | **즉시 PASS** |
| W6-11 | `stale <= MAX_STALE_RETRIES` 는 평가 안 함 | **즉시 PASS** |
| W6-12 | `ccnl is None` → 기존대로 제외 보류 | **즉시 PASS** |
| W6-13 | `UNIVERSE_LOW_VOLUME_THRESHOLD == 10_000` 값 불변 | **즉시 PASS** |
| W6-14 | 50ms sleep · unsubscribe 순서 등 기존 계약 불변 | **즉시 PASS** |

### W7 · AST 가드 + end-to-end
파일: `tests/unit/ast/test_cycle227_ast_acml_vol_guards.py`
     `tests/unit/engine/test_cycle227_e2e_acml_vol_pipeline.py`

| # | 행위 | Red 예상 |
|---|---|---|
| AST-1 | 전 `src/**/*.py` 에서 `ticker_prices[...]["acml_vol"]` **대입** 0건 (유령 키 재발 + donchian 커플링 영구 차단) | **즉시 PASS** (영구 봉인) |
| AST-2 | BFB·VCP 기존 거래량 컷 블록 **소스 텍스트 pin** (Stage 0 봉인) | **즉시 PASS** (게이트 전환 사이클에서 의미 전환) |
| AST-3 | handler `_handle_tick` 의 `len(fields) < 10` 가드 상수 불변 (상향 금지) | **즉시 PASS** |
| AST-4 | `tick_volume.py` = leaf — scheduler/8영역 import 0건 | RED (모듈 부재) |
| E2E-1 | payload `fields[13]` → `_handle_tick` → **프로덕션 `RiskManager.on_tick`** → `tick_volume` 기록. 중간 mock 0 | RED — **P0 를 처음부터 잡았을 바로 그 테스트** |
| E2E-2 | 같은 경로에서 `ticker_prices` 에는 `acml_vol` 이 **끝내 안 들어간다** | RED |

---

## 2. "즉시 PASS"는 false-red 가 아니다 (분류 근거)

Red 사이클에서 **처음부터 통과하는 테스트**가 다음 두 부류로 존재하며, 이는 결함이 아니다.

1. **현행 보존 검증** (W1-6 · W2-6/7 · W6-9~14 · AST-1/2/3)
   — "이번 변경이 **깨면 안 되는 것**"을 고정한다. Red 시점 PASS = 정상.
   Green 구현이 이걸 깨면 그때 FAIL 로 잡히는 것이 존재 이유다.
   특히 **AST-2 는 이번 사이클의 핵심 봉인**(Stage 0 = 게이트 byte 불변)이고,
   **W2-6 / AST-1 은 P0 결함의 재발·확산 차단**이다.
2. **행위 변경 0 봉인** (W4-4)
   — 관측 훅을 넣고도 반환이 여전히 `Signal.NONE` 임을 고정한다.

⇒ Red 판정은 **"신규 행위 테스트가 전부 실패하는가"** 로 하고,
보존 검증류의 PASS 는 별도 집계한다(`cycle227_red_result.md` 에 분리 기록).

---

## 3. mock 금지선 (이 사이클이 잡으려는 은폐 패턴)

- ❌ `ticker_prices` 에 `acml_vol` **손주입** — 그게 바로 P0 를 6개월 숨긴 장치다.
  신규 테스트는 어디서도 하지 않는다.
- ❌ `_parse_acml_vol` 을 mock 하고 `_handle_tick` 만 보는 식의 계층 단절.
  E2E-1 은 handler→risk→tick_volume 을 **프로덕션 코드로** 통과시킨다.
- ✅ 외부 경계(KIS REST `inquire_ccnl`/`inquire_acml_vol`, WebSocket) 만 대역.

기존 은폐 테스트 3파일(`test_bull_flag_breakout.py` · `test_bull_flag_breakout_retention.py`
· `test_vcp_breakout.py`)은 **Stage 0 에서 게이트가 여전히 그 키를 읽으므로 유지**한다.
주석 마커(전환 의무)는 Green 단계에서 backend-dev 가 단다.

---

## 4. 결정론 확보

- 시각: 전부 `freezegun`. BFB/VCP 시간 가드가 `datetime.now().time()`(naive, UTC)라
  기존 테스트 관행대로 **naive 시각을 진입창 안**(BFB 09:05~13:00 / VCP 09:05~14:30)에 둔다.
- 날짜 전환 케이스는 **naive 시각을 같게 두고 날짜만 하루 이동**(`09:30` 고정)한다 —
  UTC 15:00 이후로 밀면 naive 시각이 진입창을 벗어나 훅에 도달하지 못한다.
- `tick_volume` 의 KST 날짜 판정만 UTC 15:00 경계(`W3-9`)로 직접 검증한다.
- `scanner.ticker_prices` 는 모듈 전역이라 **테스트마다 빈 dict 로 monkeypatch** 한다
  (타 테스트 오염 차단 + 프로덕션 실제 상태 = `acml_vol` 부재 재현).
- `tick_volume.reset_for_test()` 를 fixture teardown 에서 호출.
