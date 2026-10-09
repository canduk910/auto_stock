# cycle417 Red 계약 — 일봉 증분 적재 구멍 메우기

- 사용자 결정(10-09): 「일봉표 감소원인 확인해보자」 → 조사 보고 → 「지금 고치기」 = **`src/engine/scanner.py`(8영역) 변경 승인**. 승인 사유 문자열 = `cycle417 사용자 승인 10-09 — 일봉 증분 적재 구멍`.
- 범위 = `src/engine/scanner.py` + `src/db/stock_master_daily.py`(8영역 아님). 그 밖 8영역(risk·order_engine·session·strategy_registry·api/order.py·realtime·auth)·`scheduler.py` 무접촉. 매매 행위 무변경 · KIS 호출 수 증가 0 · 마이그레이션 0.
- Red 테스트 3파일
  - `tests/unit/engine/test_cycle417_daily_gap_fill.py` — scanner 증분 분기(대역) + 순수 함수 + AST
  - `tests/unit/db/test_cycle417_gap_scan_contract.py` — 헬퍼 상수·시그니처·예외 전파·루프 안 await 금지
  - `tests/integration/test_cycle417_daily_gap_scan_pg.py` — 헬퍼 SQL 의미(실 Postgres, pg 하네스)

## 1. 결함 (출처 = 메인 세션 운영 DB 실측, 읽기 전용 — Red 는 재측정하지 않았다)

- 날짜별 종목 수 감소(09-01 1,646 → 10-08 1,029)는 유실이 아니다 — 대상에서 빠진 종목의 이후 날짜가 안 쌓인 것. 밤마다 적재 대상 970~1,095 로 안정, 대상 교체 밤마다 약 100종목.
- 🔴 결함: 증분 분기(`existing_count >= _DAILY_LOAD_VCP_BACKFILL_DAYS(225)`)의 `fetch_days = 7` 이 `condition.fetch_daily_candles(days=7)` — 달력 창 `7 + 7//2 + 10 = 20`일에서 최근 7봉(`output[:7]`)만 받는다. 깊이 판정은 행 수뿐이라 **7영업일 넘게 대상 밖에 있다 돌아온 종목은 그 사이가 영영 빈다**. 10-08 대상 1,029종목 중 14종목·34일(전부 09-21~09-28, 예: 003200 은 09-21·22·23·28 없음).
- 영향 = 20일 고가·ATR·EMA 가 빈 날을 건너뛰고 계산된다. 신선도 게이트(`DAILY_STALENESS_DAYS=4`)는 마지막 날짜만 봐서 못 잡는다.

## 2. DB 헬퍼 — `src/db/stock_master_daily.py`

```python
GAP_HORIZON = 100
GAP_CALENDAR_MIN_ROWS = 300

async def earliest_missing_bas_dd(
    tickers, *, before: date,
    horizon: int = GAP_HORIZON, min_rows: int = GAP_CALENDAR_MIN_ROWS,
) -> dict[str, date]: ...
```

- 시장 달력 = `bas_dd < before` 인 날짜 중 **그날 행 수 `>= min_rows`** 인 날의 **최근 `horizon` 개**. 우리 DB 로 만든다(KIS 휴장 API 0).
- 종목마다 「첫 행(`min(bas_dd)`) **이후** 달력 날짜 중 그 종목 행이 없는 가장 이른 날」. 첫 행 이전은 구멍이 아니다(신규 상장). **마지막 행 뒤의 달력 날짜는 구멍이다**(이번 결함 본체).
- 반환 = 구멍 있는 **요청 종목만** `{ticker: datetime.date}`. DB 에 없는 종목·요청 밖 종목은 없다.
- 쿼리 **1~2회, 종목 수와 무관한 상수**(루프·컴프리헨션 안 `await` 금지 — AST D4). `ticker = ANY($1::text[])`.
- 🔴 **예외를 삼키지 않는다**(`list_provisional_rows` 선례) — 빈 dict 로 접으면 「판정 실패」 가 「구멍 없음」 으로 둔갑한다. 호출부가 fail-open 한다.
- 참고 SQL(참조 구현이 통합 테스트 6건 통과):

```sql
WITH cal AS (
    SELECT bas_dd FROM stock_master_daily
    WHERE bas_dd < $2
    GROUP BY bas_dd HAVING count(*) >= $4
    ORDER BY bas_dd DESC LIMIT $3
),
firsts AS (
    SELECT ticker, min(bas_dd) AS first_dd FROM stock_master_daily
    WHERE ticker = ANY($1::text[]) GROUP BY ticker
)
SELECT f.ticker, min(c.bas_dd) AS earliest_missing
FROM firsts f JOIN cal c ON c.bas_dd > f.first_dd
WHERE NOT EXISTS (
    SELECT 1 FROM stock_master_daily d WHERE d.ticker = f.ticker AND d.bas_dd = c.bas_dd
)
GROUP BY f.ticker
```

## 3. scanner — `_stock_master_daily_load_once`

- 상수: `_DAILY_LOAD_INCREMENTAL_DAYS = 7`(종전 리터럴 7) · `_DAILY_LOAD_GAP_MARGIN_DAYS = 2` · 상한은 기존 `_DAILY_LOAD_FETCH_DAYS = 100`.
- 순수 함수 `_gap_fill_need_days(earliest_missing: date, today: date) -> int` = 빈 날부터 오늘까지 **평일 수(양 끝 포함, 휴일 미차감)** + 2. 예: 09-21 → 10-12 = 평일 16 + 2 = **18** · 10-13 이면 19 · 05-28 → 100 · 05-27 → 101.
- 판정 호출 = 함수 안 **1곳**, 종목 루프 **밖**, `today = today_kst()` 뒤: `await stock_master_daily.earliest_missing_bas_dd(all_tickers, before=today)`(보호 종목 포함 적재 대상 전부, `before=` 키워드).
- 증분 분기만: 구멍 있으면 `fetch_days = min(max(need, 7), 100)`, 없으면 7. KIS 호출은 그대로 `fetch_daily_candles(ticker, days=fetch_days)` **1콜**.
- 무변경: 깊은 backfill 분기(행 수 < 225 → `fetch_daily_candles_backfill(total_days=225)`, 구멍과 무관) · `skipped_fresh`(오늘 봉 있으면 구멍이 있어도 skip — 다음 밤에 메운다) · `force`(skip 만 우회) · 보호 종목 포함 규약과 `[daily_load_protected_forced]` 1행 · `_drop_today_bars` · upsert.
- 관측(실행당 1행, 종목당 금지) — 종목 루프 뒤:
  `[daily_load_gap_fill] tickers=%d widened=%d max_fetch_days=%d beyond_horizon=%d errors=%d` (INFO)
  - `tickers` = 판정이 구멍을 보고한 **적재 대상** 종목 수(대상 밖 키 제외, 날짜 아닌 값 제외)
  - `widened` = 증분 분기에서 7 보다 큰 창을 요청한 종목 수
  - `max_fetch_days` = widened 종목 창의 최댓값, widened=0 이면 0
  - `beyond_horizon` = 필요 창 `> 100` 이라 100 으로 잘린 종목 수(정확히 100 은 아님)
  - `errors` = 판정 예외(1) + 날짜가 아닌 값 수
- `summary["gap_fill"] = {"tickers","widened","max_fetch_days","beyond_horizon","errors"}`(int 5칸). 기존 summary 키 전부 유지.
- fail-open: 판정 예외 → 구멍 없음으로 진행(전 종목 7) + WARNING `[daily_load_gap_fill_skipped] reason=gap_scan_error` **실행당 1행** + `errors=1`. 날짜가 아닌 값 → 그 종목만 7 + `errors` 증가 + 같은 접두 WARNING 1행. 판정 실패를 `failed`(KIS 실패 전용)로 세지 않는다.

## 4. 설계에서 정한 것과 근거 (메인 세션 설계를 구체화한 부분)

1. **달력은 `before`(오늘) 미만 날짜만** — 오늘 봉은 20:00 전 실행에선 `_drop_today_bars` 가 버리고, 20:30 뒤 재실행에선 이미 7봉 창이 덮는다. 오늘을 달력에 넣으면 부분 적재 중인 오늘이 구멍으로 잡힌다(통합 I5 가 `<=` 돌연변이를 잡는다).
2. **영업일 수 = 평일 산술, 휴일 미차감** — 과대 계산이 안전 방향이다: `output[:N]` 의 N 이 실제 영업일보다 크면 빈 날을 반드시 포함하고, 작으면 놓친다. DB 달력으로 세면 행 수 미달 날을 빼먹어 과소 계산 위험이 있고, KIS 휴장 API 는 금지다. 대가 = 휴일 수만큼 봉을 몇 개 더 받는다(upsert 멱등 · 호출 수 불변).
3. **하한 7** = 현행 보정 창 보존(D+1 20:30 이 직전 영업일 봉을 다시 쓴다, cycle263 G2). 구멍이 최근이면 7 그대로라 `widened` 에 세지 않는다.
4. **`beyond_horizon` 은 관측값** — 평일 과대 계산 때문에 실제로는 100봉 안에 드는 구멍도 셀 수 있다. 100 영업일보다 오래된 구멍은 이번 범위 밖이다(100 으로 받아 최근 쪽만 채운다).
5. **헬퍼는 예외 전파, scanner 가 fail-open** — `count_by_ticker`(삼킴) 가 아니라 `list_provisional_rows`(전파) 쪽 규약.
6. **중립화 픽스처를 두지 않는다** — 기존 일봉 적재 테스트 15파일은 헬퍼를 대역하지 않는다. 단위 테스트에는 풀이 없어(`pg._pool is None`, 통합 `pg_pool` 픽스처는 함수 스코프로 닫는다) 실 헬퍼가 예외 → fail-open → 7 로 가므로 그 파일들의 단언(7일·1콜)이 그대로 성립한다. F2 가 이 경로를 핀한다. WARNING 은 접두가 달라 기존 caplog 단언(`[daily_load_today_filter_skipped]` 등)과 겹치지 않는다.
7. **거래정지 등으로 KIS 가 빈 날 봉을 안 주면** 구멍이 남아 매일 밤 넓은 창을 다시 요청한다 — 1콜 그대로, 창은 밤마다 평일 하나씩 커지다 100 에서 멈춘다(K2). 그 날이 달력 지평(최근 100개) 밖으로 밀리면 판정에서 사라진다.

## 5. 알려진 한계 (이번 범위 밖)

- 그날 전체 행 수가 300 미만인 날(대규모 적재 실패일)은 달력에 들지 않아 그날의 구멍을 못 잡는다 — 7영업일 안이면 다음 밤 7봉 창이 덮는다.
- 판정은 「첫 행 이후」만 본다 — 첫 행보다 오래된 이력 부족(신규 상장·retention)은 깊은 backfill(행 수 < 225)의 몫이다.
- `skipped_fresh` 종목의 구멍은 그날 메우지 않는다(다음 밤).

## 6. 테스트 매트릭스와 Red 실측 (2026-10-09, 로컬 Python 3.13 + docker Postgres)

**39 failed / 4 passed** (통과 4 = 불변식이라 Red·Green 양쪽 초록: W2 · K1 · U1 · A2).

| ID | 내용 | Red |
|---|---|---|
| P1 ×8 | `_gap_fill_need_days` 평일+2 (18·19·3·3·7·5·100·101) | FAIL(부재) |
| P2 | 상수 7·2·100 | FAIL |
| W1 ×2 | 09-21 구멍 → 18, 20:30·07:50 두 시각(커트오프 앞·뒤) | FAIL(7) |
| W2 | 무구멍 → 7 | 불변 |
| W3 ×6 | 하한 7·상한 100 + `widened`·`beyond_horizon`·`max_fetch_days` | FAIL(창 또는 summary 칸) |
| K1 | 섞여도 종목당 1콜, backfill 0 | 불변 |
| K2 | 거래정지 구멍: 밤1 18 → 밤2 19 → 먼 밤 100, 매번 1콜 | FAIL |
| U1 | 행 수 224 + 구멍 → 225일 backfill 그대로 | 불변 |
| U2 | fresh + 구멍 → skip 그대로 | FAIL(summary 칸) |
| U3 | force → 확대 | FAIL |
| U4 | 보호 종목도 같은 규칙 + 판정 인자 포함 + 보호 마커 1행 | FAIL |
| C1 | 판정 실행당 1회, 인자 = 대상 전부 + `before=오늘` | FAIL |
| O1 | 마커 1행·필드 정확값(4·2·100·1·0) + summary + 호출 모양 | FAIL |
| O2 | 구멍 0 이어도 마커 1행(전부 0), WARNING 0 | FAIL |
| F1 | 판정 예외 → 7 + WARNING 1행 `reason=gap_scan_error` + errors=1, `failed` 불변 | FAIL |
| F2 | 헬퍼 미대역 + 풀 없음 → fail-open(기존 15파일 상태) | FAIL |
| F3 | 날짜 아닌 값 → 그 종목만 7, errors=1, tickers=1 | FAIL |
| A1 | 판정 호출 1곳·루프 밖 (AST) | FAIL |
| A2 | KIS 호출 자리 2곳 그대로 (AST) | 불변 |
| A3 | 적재 경로·need 함수에 `trading_calendar`·`is_trading_day`·`kis_get` 0 | FAIL(부재) |
| D1~D4 | 헬퍼 상수 100·300 · `before` 키워드 전용 · 예외 전파 · 루프 안 await 0 | FAIL(부재) |
| I1 | 달력 경계 `>= 300`(300행 날 포함, 299행 날 제외) — 기본 상수 | FAIL |
| I2 | 첫 행 이전은 구멍 아님 | FAIL |
| I3 | 가장 이른 빈 날 · 무구멍/DB 없음/요청 밖 제외 · 값 타입 `date` | FAIL |
| I4 | 마지막 행 뒤 = 구멍(돌아온 종목) | FAIL |
| I5 | 달력 = `before` 미만의 **최근** horizon 개 | FAIL |
| I6 | 쿼리 수 2종목 = 40종목, 1~2회 | FAIL |

검증(참조 구현 = 스크래치 `.../scratchpad/c417/red/make_reference.py`, 커밋 안 함): 새 테스트 43건 + 기존 일봉 적재 15파일 + `tests/unit/db` 전부 **313 passed**. 돌연변이 **19/19 사살**(달력 `>`·`<=`·ASC·첫 행 무시 · 여유 없음·달력일 계수·오늘 제외 · 상·하한 제거 · beyond `>=` · widened 전수 · 대상 필터 제거 · fail-open 제거 · 값 검사 제거 · fresh 우회 · 마커 조건부 · `before` 내일 · 종목당 판정 · 깊은 분기 오염). 참조 구현은 매 실행 뒤 원본으로 되돌렸고 sha 일치를 확인했다.

## 7. 8영역 핀 — 「승인 전」 상태는 붉어야 정상이다 (실측)

`scanner.py`(+`stock_master_daily.py`) 끝에 주석 1줄을 덧붙여 `tests/unit/ast` · `tests/unit/engine/strategies` · `tests/unit/db` 를 돌린 결과 **21 failed**(둘 중 scanner 만 바꿔도 같은 21). 원본 복원 후 sha 일치 확인. 이것이 정상 — 승인 절차는 「Green 이 sha 를 재핀해야 초록」 이다.

Green 재핀 절차(cycle380 커밋 `50321c58` 선례):
1. scanner.py 의 새 sha(`shasum -a 256 src/engine/scanner.py`)로 **아래 16파일의 리터럴** `611568c078c6f3779344e05b3dfa308c792c64e1c5e02480de6313200282f54f` 를 모두 교체하고, 각 자리 위에 한 줄 주석 `# 🔁 cycle417(2026-10-09) 재핀 — cycle417 사용자 승인 10-09 — 일봉 증분 적재 구멍(증분 분기 창 확대 + 구멍 판정 1회 호출). 나머지 7영역 diff 0.` 을 단다.
   - 자매 가드 4곳(`test_cycle223g3::_PIN_GUARD_FILES` — 같은 값 의무, G3-9b): `tests/unit/ast/test_cycle222a3_ast_followup_fixes.py` · `tests/unit/ast/test_cycle223_ast_donchian_exit_fix.py` · `tests/unit/ast/test_cycle223f_ast_manual_apply_safeguard.py` · `tests/unit/engine/strategies/test_cycle226_zero_breakout_defense.py`
   - 기준선 핀 12곳: `tests/unit/ast/test_cycle274_ast_llm_gate.py` · `test_cycle276_ast_order_hook.py` · `test_cycle278_ast_catalog_guards.py` · `test_cycle282_ast_purity.py` · `test_cycle286_ast_scope.py` · `test_cycle287_ast_scope.py` · `test_cycle290_ast_scope.py` · `test_cycle291_ast_scope.py` · `test_cycle297_ast_scope.py` · `test_cycle405_ast_donchian_kk.py` · `test_cycle411_ast_scope.py` · `test_cycle412_scope_guard.py`
2. `tests/unit/ast/test_cycle287_ast_scope.py::_SRC_TREE_DIGEST` 재핀(`stock_master_daily.py` 변경이 여기에 잡힌다 — 주석에 직전 값 `edcd6038ac6bcc6c977b1e17cef42bbcb6400275ea7502ca2f19476b0256b266` 기록). **새 src 파일을 만들지 않는다**(만들면 `_SRC_TREE_FILES`=179·`_PINNED_DIR_FILE_COUNTS` 도 움직인다).
3. 승인 전 실패 21건 목록(재핀 뒤 전부 초록이어야 한다):
   `222a3::test_ga3_6` · `223::test_g223_10` · `223f::test_g223f_9` · `223g3::test_g3_7[223]`·`[223f]`·`test_g3_9b` · `274::test_c15_1[scanner]` · `276::test_c5_1[scanner]`·`test_c6_4c` · `278::test_eight_areas…[scanner]` · `282::test_h3[scanner]` · `286::test_g1[scanner]` · `287::test_s1[scanner]`·`test_s1b` · `290::test_g290_1[scanner]` · `291::test_a1[scanner]` · `297::test_g2_9a[scanner]` · `405::test_g405_6[scanner]` · `411::test_g1[scanner]` · `412::test_s1[scanner]` · `226::test_common_1`
4. 「커밋 후 비우기」: 222a3 의 `_APPROVED_CONTENT_SHA` 는 scanner 항목을 **값 교체**로 유지한다(cycle380 이 그랬다 — 항목 삭제가 아니라 재핀).

## 8. Green 이 함께 지킬 기존 가드

- `test_cycle302_backfill_scope_expansion.py::G-302-3` 「수렴 유니버스 종목당 1콜·전량 7」 — 헬퍼 미대역이라 fail-open 경로로 초록이어야 한다.
- cycle263 G2(7일 보정 창) · cycle273 보호 마커 1행 · cycle283 커트오프 시뮬 · cycle304 실 KIS 차단 · cycle127 진행 훅.
- 문서(Phase 4.8 `/sync-docs`): `src/engine/CLAUDE.md` 「저녁 데이터 적재」 절 · `src/db/CLAUDE.md` `stock_master_daily` 절 · 정본 규약(현재형만, 경위는 history).
