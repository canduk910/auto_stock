# 사이클 231 행위 분해 — kojiro `_held_stage3` 날짜 키 (P2-5)

명세 `cycle231_stage3_stale_spec.md` W1~W4 를 **검증 가능한 행위 단위**로 쪼갠 목록.
테스트 파일 = `tests/unit/engine/strategies/test_cycle231_stage3_date_key.py`.

## 전제 (테스트 관점)

- 소비 지점은 `check_exit_signal` §3 하나 (`kojiro.py:897`). §1(−8%)·§2(2ATR floor)·§4(2.5ATR 샹들리에)
  는 **무변경**이고, §3 억제가 그 셋을 막지 않는다는 것 자체가 하나의 행위다.
- 기록 지점은 `prepare()` 1곳 + `recompute_held_atr` 5곳(fetch 예외 / 빈 응답 / 워밍업 부족 /
  성공 / 계산 예외). 실패 4곳은 `:649` docstring 이 이미 fail-open 을 계약화했다.
- 날짜 = **판정 수행일** `datetime.now(KST).date()` (봉 날짜 아님).
- freezegun 은 naive 를 UTC 로 동결 → 이 파일의 freeze 인자는 전부 UTC, KST = UTC+9h.
  kojiro 는 프리장 청산 평가 보류 대상이라 09:10 KST(= UTC 00:10)로 고정한다.

## B1 — 소비 판정 (W1)

| # | 조건 | 기대 |
|---|------|------|
| B1-1 | `(오늘, True)` | `Signal.TRAILING_STOP` + `[kojiro_stage3_exit]` 에 `judged_on=오늘` (기존 문구 앞부분 byte 보존) |
| B1-2 | `(어제, True)` | `Signal.NONE` (§3 미발화) |
| B1-3 | `(오늘, False)` | `Signal.NONE` + stale_skip 로그 **0** (정상 미발화). ⚠️ 현행은 `if self._held_stage3.get(t):` 라 **비어 있지 않은 튜플을 전부 참**으로 읽는다 — 형태만 바꾸고 판정을 안 고치면 `False` 판정이 오히려 청산을 만든다 |
| B1-4 | 엔트리 부재 | `Signal.NONE` + stale_skip 로그 **0** |
| B1-5 | 억제 후 값 보존 | stale 억제가 `_held_stage3` 를 덮어쓰지 않는다(사후 복기·관측 유지) |
| B1-6 | `on_position_closed` | 튜플 값이어도 `pop` 정상 |

## B2 — 억제 관측 (W2)

| # | 조건 | 기대 |
|---|------|------|
| B2-1 | `(어제, True)` | `[kojiro_stage3_stale_skip] ticker=… judged_on=… age_days=1` **INFO** |
| B2-2 | `(그제, True)` | 동일 문구 `age_days=2` **WARNING** (`_DbLogHandler` INFO 컷 통과) |
| B2-3 | 같은 종목 같은 날 10회 평가 | 로그 **1행** (cap 1회/ticker/일) |
| B2-4 | 날짜 넘김 | 다시 1행 (날짜 키 자기 리셋 — `_reset_daily_state` 훅 미의존) |
| B2-5 | 두 종목 같은 날 | 2행 (cap 키 = ticker) |

## B3 — 억제가 다른 청산을 막지 않는다 (자문 Q1 비대칭 비용의 근거)

| # | 조건 | 기대 |
|---|------|------|
| B3-1 | stale True + 현재가 ≤ −8% | `STOP_LOSS` (§1 생존) |
| B3-2 | stale True + 현재가 ≤ 샹들리에 | `TRAILING_STOP` **via §4** (`[kojiro_trailing]` 발화 / `[kojiro_stage3_exit]` 부재) |

## B4 — 기록 형식 (W1 기록 지점)

| # | 조건 | 기대 |
|---|------|------|
| B4-1 | `prepare()` 보유 + stage3 | `_held_stage3[t] == (오늘, True)` |
| B4-2 | `prepare()` 보유 + stage≠3 | `(오늘, False)` |
| B4-3 | `recompute_held_atr` 성공 + stage3 | `(오늘, True)` |
| B4-4 | recompute 실패 4경로(fetch 예외/빈 응답/워밍업 부족/계산 예외) | 전부 `(오늘, False)` = fail-open 계약 형태 전환 후 유지 |

## B5 — 설계 의도 보존 (자문 §"가장 중요한 검증")

D 저녁 prepare 가 `(D, True)` 를 찍고 D+1 09:00 에 소비되면 억제된다 — 그러나 그 사이
**D+1 07:55 recompute** 가 같은 D 확정봉으로 재판정해 `(D+1, True)` 로 기록한다.

| # | 흐름 | 기대 |
|---|------|------|
| B5-1 | D+1, recompute **전** | `NONE` + stale_skip 1행 |
| B5-2 | 같은 D+1, recompute **후** | `(D+1, True)` 기록 → `TRAILING_STOP` |

## B6 — 부수 방어 (W3, 매매 무변경)

`kojiro.py:685` `pos.buy_date < today` 가 per-ticker try **밖**이라 `buy_date` 가 date 가
아니면 TypeError 가 루프를 뚫고 나가 **그 뒤 보유 종목의 ATR/stage3/floor 재계산이 통째 유실**
(cycle226 L-2 동형).

| # | 조건 | 기대 |
|---|------|------|
| B6-1 | 보유 2종목, 첫 종목 `buy_date` 가 str | 예외 미전파 + **둘째 종목 재계산 생존**(`_candidates`/`_held_stage3`/`_position_atr`) + `[kojiro_recompute]` WARNING 1행(해당 ticker 명시) |

## B7 — AST 가드 (자기 공허화 주의)

| # | 대상 | 기대 |
|---|------|------|
| B7-1 | 판별기 자체 | 뮤테이션 소스(`if self._held_stage3.get(ticker):`) → **False**, 시정 소스 → **True** — 비-공허성 실증 (cycle224/226 교훈) |
| B7-2 | 실제 `check_exit_signal` | §3 분기의 `test` 가 `_held_stage3` 와 **날짜**를 함께 참조(지역 대입 전이 추적) |
| B7-3 | `_held_stage3` subscript 대입 | 전부 `ast.Tuple` (bare bool 재발 차단) |
| B7-4 | FREEZE | `trail_atr=2.5` / `stop_atr=2.0` / `hard_stop_pct=-8.0` 불변 · `check_buy_signal` 에 stage3 토큰 0 · `_reset_daily_state` override 부재 |

## W4 의미 전환 (Red 단계에서 동반 수행)

기존 주입이 새 계약의 **문서**가 되는 케이스라 xfail 이 아니라 갱신이 맞다.

- `test_kojiro.py:167` — `is True` 단언 → `== (오늘, True)`
- `test_kojiro.py:277` · `:303` — `= True` 주입 → `= (오늘, True)`
- `test_cycle220_kojiro_breakeven_floor.py:371` — `= True` 주입 → `= (_today(), True)`

각 지점에 1줄 주석 `# cycle231 — 날짜 키 계약 …`.
