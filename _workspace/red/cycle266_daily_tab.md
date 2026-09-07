# cycle266 Red — 종목마스터 "일봉 (30일)" 탭 결함 3건

작성 = tdd-engineer / 2026-09-07
명세 정본 = [`_workspace/specs/cycle266_daily_tab_fix.md`](../specs/cycle266_daily_tab_fix.md)
진단은 운영 EC2·운영 DB 실측 확정본이며 이 사이클에서 재조사하지 않았다.

**이 문서는 Red 단계 산출물이다.** 구현(Green)은 backend-dev / frontend-dev 가 받는다.
tdd-engineer 는 구현 파일(`src/routes/stock_master.py`, `frontend/src/pages/StockMaster.tsx`,
`frontend/src/types/stock-master.ts`)을 **한 글자도 고치지 않았다** — 목 파일과 테스트 파일만.

---

## 0. 결함의 뿌리 — 왜 3개월간 초록이었나

`stock_master_daily.change_rate`/`prtt_rate` 는 `NUMERIC(8,4)`(migration 033) 이고
asyncpg 는 그것을 `decimal.Decimal` 로 준다. 라우트는 그 dict 를 `ApiResponse.data`(`Any`)
에 그대로 실어 반환하고, **pydantic v2 는 JSON 모드에서 `Decimal` 을 문자열로 직렬화한다.**

실측(라우트를 실제로 태운 결과, `TestClient`):

```
{"success":true,"data":[{"ticker":"005930","bas_dd":"2026-09-05",...,
 "change_rate":"0.0000","flng_cls_code":"","prtt_rate":"1.2300",
 "raw":{"stck_clpr":"75000","nested_dec":"9.8700"}}],"message":"1일 일봉"}
```

`DailyTab` 은 `row.change_rate.toFixed(2)` 를 호출한다 → `TypeError` → StockMaster 에
ErrorBoundary 가 없어 React 루트까지 전파 → **트리 전체 언마운트 = 흰 화면**.

그런데 목 셋이 전부 `change_rate: parseFloat(...)` 로 **진짜 number** 를 만들어
*의도한 계약*만 검증하고 *실제 응답*은 한 번도 검증하지 않았다:

| 목 | 종전 값 |
|---|---|
| `frontend/src/test/handlers.ts` | `change_rate: parseFloat(...)` · `bas_dd: '20260613'` |
| `e2e/fixtures/api-mocks.ts` | 동일 |
| `frontend/src/pages/__tests__/StockMaster.test.tsx` | 동일 |

`bas_dd` 도 같은 계열의 거짓말이다 — 컬럼은 `DATE` 라 직렬화가 `YYYY-MM-DD` 인데
목 셋과 프론트 타입 주석이 모두 KIS 원본 필드 모양인 `YYYYMMDD` 를 쓴다.

⇒ **이번 사이클의 정본 가드는 라우트를 실제로 태워 직렬화된 JSON 본문의 타입을 재는
백엔드 테스트다.** 프론트 목은 그 다음 방벽이다.

---

## 1. 검증 가능한 행위 분해

### A. 백엔드 — `src/routes/stock_master.py::get_stock_master_daily` 단독

| ID | 행위 | 테스트 |
|---|---|---|
| A-1-1 | `change_rate`(Decimal) → **직렬화된 JSON 에서 숫자**(str 아님) | `test_c266_a1_1_change_rate_is_json_number_not_string` |
| A-1-2 | `prtt_rate` 동일 + **값 보존**(1.23) | `test_c266_a1_2_prtt_rate_is_json_number_not_string` |
| A-1-3 | 필드명 하드코딩 금지 — 미지의 NUMERIC 컬럼도 자동 변환 | `test_c266_a1_3_conversion_is_field_name_agnostic` |
| A-1-4 | `raw` JSONB **재귀 변환 금지**(사이클 81 G-AST1 "raw 변형 0") | `test_c266_a1_4_raw_jsonb_is_not_recursively_converted` |
| A-1-5 | `date`/`int`/`str`/`None` 은 무접촉 (기존 직렬화 계약 보존) | `test_c266_a1_5_non_decimal_types_untouched` |
| A-1-6 | 원본 row **불변** — 새 dict 사영 (같은 객체가 전략 prepare 로 간다) | `test_c266_a1_6_source_rows_are_not_mutated` |
| A-1-7 | `float()` 실패는 **fail-open** = 원값 유지 + 200, 같은 row 의 다른 필드는 정상 변환 | `test_c266_a1_7_conversion_failure_is_fail_open` |
| A-1-8 | 사영은 **모든 row** 에 적용 (첫 행만 고치는 구현 차단) | `test_c266_a1_8_all_rows_converted_not_just_first` |
| A-1-9 | envelope·호출 인자 계약 무변경 (회귀) | `test_c266_a1_9_envelope_and_call_contract_preserved` |
| A-2-1 | `get_recent_daily` 예외 → **500** (404 로 위장 금지) | `test_c266_a2_1_db_exception_becomes_500_not_404` |
| A-2-2 | 예외는 ERROR + **traceback**(`logger.exception`) + ticker 포함 | `test_c266_a2_2_db_exception_is_logged_with_traceback` |
| A-2-3 | 빈 rows 의 404 를 500 으로 재포장하지 않는다 | `test_c266_a2_3_http_exception_is_not_swallowed_as_500` |
| A-2-4 | 사이클 90 POST-only 경로 405 회귀 | `test_c266_a2_4_post_only_path_still_405` |
| A-3-1 | 404 `detail` = 미적재 취지 (ticker · `"미적재"` · `days=`) | `test_c266_a3_1_404_detail_says_not_loaded_not_error` |
| A-3-2 | `detail` 은 문자열 유지 (응답 형태 변경 최소화) | `test_c266_a3_2_404_detail_stays_a_string_not_a_dict` |

### B. 프론트 — `StockMaster.tsx` + `types/stock-master.ts`

| ID | 행위 | 테스트 |
|---|---|---|
| B-1-1 | 문자열 `change_rate` 에도 테이블 렌더 (트리 언마운트 0) | `B-1-1` |
| B-1-2 | `'1.2300'`→`+1.23%`/상승색 · `'-2.5000'`→`-2.50%`/하락색 · `'0.0000'`→`0.00%`/중립색 | `B-1-2` |
| B-1-3 | 문자열 OHLCV → ko-KR 천단위 서식 (`'74000'`→`74,000`) | `B-1-3` |
| B-1-4 | `null`/`undefined`/비숫자 문자열/`NaN` → `'—'`, 색상 미부여 | `B-1-4` |
| B-1-5 | **숫자 응답도 그대로 통과** (양쪽 다 초록 의무, §C-2) | `B-1-5` |
| B-3-1 | 404 → 회색 **안내**(미적재), `'조회 실패'` 아님 | `B-3-1` |
| B-3-2 | 500 → 빨간 **오류** | `B-3-2` |
| B-3-3 | 네트워크 오류(response 없음) → 빨간 **오류** | `B-3-3` |
| B-3-4 | 200 + 빈 배열 → 안내 (오류 아님) | `B-3-4` |
| G-266-1 | `row.<field>.toFixed(`/`.toLocaleString(` 직접 호출 0건 (정적) | `G-266-1` |
| G-266-2 | `retry: 1` 유지 (사이클 65 H3, 이미 초록 = 보존 가드) | `G-266-2` |
| G-266-3 | 404 판별 `response?.status === 404` 가 2곳 이상 (DetailModal + DailyTab) | `G-266-3` |
| B-2 / G-266-4 | `StockMasterDailyRow.change_rate` 유니온 + `bas_dd` 주석 사실화 | `G-266-4` |

### C. 목 3곳 — 재발 방지

| ID | 행위 | 테스트 |
|---|---|---|
| C-3-1 | 목 3곳 각각 `change_rate` **문자열** 케이스 ≥1 | `test_c266_c3_mock_has_string_change_rate[3]` |
| C-3-2 | 목 3곳 각각 `change_rate` **숫자** 케이스 ≥1 (양쪽 유지) | `test_c266_c3_mock_keeps_numeric_change_rate[3]` |
| C-3-3 | 목 3곳 각각 `bas_dd` 가 `YYYY-MM-DD` | `test_c266_c3_mock_bas_dd_uses_date_format[3]` |

---

## 2. Green 담당자와의 인터페이스 합의 (Red 가 강제하는 계약)

명세가 "최종 문구는 tdd-engineer 와 협의" 로 남긴 부분을 아래로 확정했다.

**backend-dev**
- 404 `detail` 문자열에 **ticker · `"미적재"` · `days={days}`** 가 모두 들어간다.
  (권장 문구: `f"ticker={ticker} 일봉 미적재 — 일봉은 전 종목이 아니라 전략 유니버스 대상만 적재됩니다 (days={days})"`)
- 예외 로그는 `src.routes.stock_master` 로거에 **`logger.exception`**(= `exc_info` 존재)
  으로 남기고 메시지에 ticker 를 포함한다. 마커 접두는 강제하지 않는다.
- 변환은 **값 타입 판정**(`isinstance(v, decimal.Decimal)`)이며 필드명 열거가 아니다.
- `raw` 키는 **건드리지 않는다**(재귀 금지). 나머지 타입도 무접촉.
- 원본 row 를 제자리에서 바꾸지 않고 **새 dict** 를 만든다.
- `float()` 예외는 그 **한 필드만** 원값으로 두고 나머지는 계속 변환한다(fail-open).

**frontend-dev**
- 두 testid 를 새로 만든다: `stock-master-daily-notice`(404·빈 배열, `text-gray-*`) /
  `stock-master-daily-error`(그 외, `text-red-*`). 둘은 **동시에 렌더되지 않는다**.
- 변환 불가 값의 대체 표기는 em dash **`'—'`**(U+2014) 하나로 통일한다.
- 등락률 색상 클래스는 현행 리터럴을 유지한다: 상승 `text-red-600` / 하락 `text-blue-600` /
  보합 `text-gray-500` (cycle261 `@theme` 별칭이 톤을 입히므로 클래스명 변경 불요).
  `'—'` 셀에는 상승·하락 색을 붙이지 않는다.
- 서식은 현행과 동일: 등락률 `toFixed(2)` + 양수 `+` 접두 + `%`, 금액·수량 `toLocaleString('ko-KR')`.
- 셀 순서는 현행 유지(기준일/시가/고가/저가/종가/거래량/등락률) — 가드가 인덱스로 잰다.

---

## 3. 실제 Red 확인 (명령 + 실패 출력 요약)

### 3.1 백엔드

```bash
python -m pytest -q tests/unit/routes/test_cycle266_daily_route_serialization.py
```

`8 failed, 7 passed`

| 테스트 | 실패 출력 (요약) |
|---|---|
| A-1-1 | `AssertionError: change_rate 가 JSON 숫자가 아니다: '0.0000' (type=str)` |
| A-1-2 | `AssertionError: prtt_rate 가 JSON 숫자가 아니다: '1.2300'` |
| A-1-3 | `AssertionError: 필드명을 열거한 구현으로 보인다 — … future_numeric_col 이 '-3.5000' 로 남았다` |
| A-1-7 | `AssertionError: 한 필드의 변환 실패가 같은 row 의 다른 필드까지 막았다: … 'prtt_rate': '1.2300'` |
| A-1-8 | `AssertionError: row[0] change_rate 미변환: '1.2300'` |
| A-2-1 | `AssertionError: DB 예외가 404 로 위장됐다 … body={"detail":"ticker=000001 일봉 데이터 없음 (days=1)"}` / `assert 404 == 500` |
| A-2-2 | `assert 404 == 500` (500 미도달) |
| A-3-1 | `AssertionError: 404 문구가 미적재 취지가 아니다: 'ticker=123456 일봉 데이터 없음 (days=30)'` |

**초록 7 = 보존 가드**(A-1-4 raw 무변형 / A-1-5 타입 무접촉 / A-1-6 원본 불변 /
A-1-9 envelope / A-2-3 빈 rows 404 / A-2-4 405 / A-3-2 detail str).
이들은 "Green 이 깨면 안 되는 것"을 잰다 — false-red 가 아니라 **의도된 사전 초록**이다.

```bash
python -m pytest -q tests/unit/e2e_mocks/test_cycle266_mock_string_change_rate.py
```

목 수정 **전** = `6 failed, 3 passed`
(`… 의 change_rate 목이 전부 숫자다 — 운영 응답은 "0.0000" 문자열이다` ×3 +
`… 의 bas_dd 목에 YYYY-MM-DD 케이스가 없다` ×3)
목 수정 **후** = `9 passed` (§4 참조).

### 3.2 프론트

```bash
cd frontend && npx vitest run src/pages/__tests__/StockMaster.dailyTab.cycle266.test.tsx
```

`11 failed | 2 passed (13)`

가장 중요한 실패 출력(=결함 그 자체):

```
⎯⎯⎯ Uncaught Exception ⎯⎯⎯
TypeError: row.change_rate.toFixed is not a function
 ❯ src/pages/StockMaster.tsx:399:66
   399|  {row.change_rate > 0 ? '+' : ''}{row.change_rate.toFix…
 ❯ DailyTab src/pages/StockMaster.tsx:390:17
```

```
⎯⎯⎯ Uncaught Exception ⎯⎯⎯
TypeError: Cannot read properties of null (reading 'toLocaleString')
 ❯ src/pages/StockMaster.tsx:393:94
```

- B-1-1~B-1-4 = 위 두 `TypeError` 로 트리 언마운트 → testid 미발견
- B-3-1~B-3-4 = `stock-master-daily-notice` / `stock-master-daily-error` 미존재
- G-266-1 = `row.open_price.toLocaleString(` 등 6건 직접 호출 검출
- G-266-3 = `response?.status === 404` 가 `DetailModal` 1곳뿐(2 미만)
- G-266-4 = `change_rate: number` 단독 + `YYYYMMDD` 주석 잔존

**초록 2 = 보존 가드** — B-1-5(숫자 응답 현행 동작) · G-266-2(`retry: 1` 이미 존재).

---

## 4. 목 3곳 정합 (§C-3) — tdd-engineer 가 직접 수정한 부분

세 목의 일봉 행을 **명시 리터럴 5행**으로 바꿨다(종전 `Array.from` + `parseFloat` 생성기).
생성기 표현식은 가드가 읽기 어렵고, 무엇이 문자열이고 무엇이 숫자인지 사람이 읽어도 안 보인다.

- 행 1/3/5 = `change_rate: '1.2000' | '0.6000' | '0.0000'` (**운영 응답 모양 = 문자열**)
- 행 2/4 = `change_rate: 0.9 | 0.3` (**A-1 시정 후 모양 = 숫자**)
- 전 행 `bas_dd: '2026-09-0X'`(`YYYY-MM-DD`) + `prtt_rate: '0.0000'` 추가

수정 파일: `frontend/src/test/handlers.ts` · `e2e/fixtures/api-mocks.ts` ·
`frontend/src/pages/__tests__/StockMaster.test.tsx`(`SAMPLE_DAILY_ROWS` + `'20260613'` 단언 1건).

⚠️ **Playwright LIFO 순서는 건드리지 않았다** — `page.route` 등록 위치 무변경.
`tests/unit/e2e_mocks/` 34 케이스 **전부 PASS** 로 실증했다(사이클 80 hotfix #3 / 사이클 85 /
사이클 124 LIFO 가드 포함).

**부수 효과(의도됨)**: 목이 정직해지자 기존 `StockMaster.test.tsx` 의 G-TAB-2 3 케이스가
붉어졌다. 이 셋은 "일봉 탭이 동작한다"고 3개월간 잘못 증언해 온 바로 그 테스트다 —
B-1 Green 과 함께 초록으로 돌아온다. 테스트 코드는 무수정(목 데이터만 바뀜).

---

## 5. 회귀 실증

| 게이트 | 결과 |
|---|---|
| `pytest -q tests/unit/routes tests/unit/e2e_mocks tests/unit/ast` | `8 failed, 1065 passed, 3 skipped, 43 xfailed, 1 xpassed` — **실패 8건 전부 cycle266 신규 Red** |
| `cd frontend && npx tsc -b` | exit 0 (⚠️ `tsc --noEmit` 은 0파일 검사 = 공허, cycle256 교훈) |
| `cd frontend && npx vitest run` | `14 failed | 578 passed (592)` — 11 = cycle266 신규 Red, 3 = G-TAB-2(§4 부수 효과) |
| `grep -rl 'frontend/' tests/unit` | `test_cycle266_mock_string_change_rate.py` 포함 확인 (프론트 전용 사이클 검증 목록 편입, cycle256 g251_2/3 관례) |
| 무접촉 실증 `git diff --name-only` | 8영역 · `scheduler.py` · `strategies/*.py` · **`src/db/stock_master_daily.py`** · `src/routes/stock_master.py` · `StockMaster.tsx` · `types/stock-master.ts` **전부 diff 0** |

---

## 6. Green 이 함께 갱신해야 하는 기존 가드 (계약 반전 1건)

`tests/unit/routes/test_cycle124_stock_master_daily_route.py::test_g_daily2b_graceful_on_exception`
이 **정확히 반대**를 못박고 있다:

```python
# 예외 → rows=[] → 404 (graceful, 500 아님)
assert resp.status_code == 404, f"예외 graceful → 404 의무, got {resp.status_code}"
```

A-2-1 이 그 계약을 뒤집는다. Green 단계에서 이 케이스를 **의미 전환**(사이클 66 K-2 관례)
해야 한다 — 삭제가 아니라 "예외는 500, 빈 rows 는 404" 로 다시 쓴다.
현재는 여전히 초록이라 스위트가 자기모순 상태가 **아니다**(라우트가 아직 404 를 준다).

---

## 7. 알려진 한계 · 후속

- **F-1 (명세 §3-A-2 명시)**: `src/db/stock_master_daily.py::get_recent_daily` 자신이
  `except Exception → return []` 로 예외를 삼키므로(258-287행), A-2 의 500 경로는
  **오늘 운영에서 실질적으로 도달하지 않는다**. 이 사이클의 500 가드는 monkeypatch 로만
  재현되는 **계약 가드**이며, 그 사실을 테스트 docstring 에 남겼다. 그 db 모듈은
  6 전략 `prepare()` + 터틀 사이징 ATR + 수정주가 락 게이트를 공유하므로 **별도 승인 +
  `domain-consult` 행위 영향 평가** 대상이다.
- **B-4**: ErrorBoundary 는 이번 범위 밖(명세). 현행 ErrorBoundary 는 프로젝트 전체에서
  `components/DailyReportTab.tsx` 한 곳뿐이며, 그것이 없어 이번 `TypeError` 가
  StockMaster 페이지 **전체**를 언마운트시켰다.
- **일봉 미적재 49.5%** — 404 는 장애가 아니라 정상 상태다(운영 실측 3,583 중 1,773).
  B-3-1 의 안내 문구가 이 사실을 화면에서 말하게 한다.

---

## 마무리 라운드 (2026-09-07, tester 적대 검토 지적 3건 시정)

team-leader 결정 = D-1 / D-2 / D-3 셋 다 시정. D-4(라인 상한)·D-5(폴링)·
B-4(ErrorBoundary)·F-1(db 모듈)은 후속으로 남기고 손대지 않았다.

### D-1 (MEDIUM) — 404 안내가 원인을 단정하던 것

`src/db/stock_master_daily.py::get_recent_daily` 는 **자신이** DB 예외를 삼키고
`[]` 를 돌려준다(무접촉 대상 — 6 전략 `prepare()` + 터틀 ATR + 수정주가 락 게이트 공유).
따라서 라우트가 예외를 더 이상 삼키지 않아도 **진짜 DB 장애는 여전히 404 로 도착**한다.
새 문구 "미적재 — 전략 유니버스 대상만 적재됩니다" 는 종전 "일봉 데이터 없음" 보다
친절하지만 원인을 **단정**해서, 운영자가 장애를 정상으로 읽고 넘길 수 있었다.

⇒ 백엔드 `detail` 과 프론트 안내 **양쪽**에 단서 + 검색 가능한 로그 토큰
`stock_master_daily` 를 실었다(db 마커 `[stock_master_daily] get_recent_daily 실패
graceful` 과 라우트 마커 `[stock_master_daily_route_error]` 를 모두 잡는 접두).

⚠️ 프론트 안내는 `"조회 실패"` 라는 **정확한 표현을 쓰지 않는다** — B-3-1 이
`queryByText(/조회 실패/)` 부재로 오류 분기와 안내 분기를 가르기 때문이다. 그 단언은
완화하지 않고 그대로 두고, 단서는 "가져오지 못한 경우" 표현을 썼다(D-1-3 이 두 분기의
구분이 유지됨을 별도로 못박는다).

| 자리 | 최종 문구 |
|---|---|
| 백엔드 404 `detail` | `ticker={ticker} 일봉 미적재 — 전략 유니버스 대상만 적재됩니다 (days={days}). 단, 서버 조회 실패도 같은 404 로 보일 수 있으니(cycle266 D-1) 로그에서 stock_master_daily 를 확인하세요` |
| 프론트 안내 | `일봉 미적재 — 일봉은 전 종목이 아니라 전략 유니버스 대상만 적재됩니다. 단, 서버가 데이터를 가져오지 못한 경우에도 같은 안내가 나올 수 있으니, 계속 보이면 시스템 로그에서 stock_master_daily 를 확인하세요.` |

A-3 필수 3요소(ticker · `"미적재"` · `days=`)와 B-3 의 `"미적재"` 토큰은 유지된다.

### D-2 (LOW) — 타입이 실제 응답 필드를 숨기던 것

라우트는 `SELECT *` 라 migration 033 의 **14 컬럼 전수**를 내보내는데
`StockMasterDailyRow` 는 8필드만 선언했다. 나머지 6개를 **선택 필드**로 명시했다
(`ticker` / `flng_cls_code` / `prtt_rate` / `raw` / `created_at` / `updated_at`).
`prtt_rate` 는 `change_rate` 와 같은 `NUMERIC(8,4)` 출신이라 `number | string`.
**렌더 로직 무변경**(런타임 영향 0 — 구조적 타이핑).

### D-3 (LOW) — E2E 레인이 일봉 탭을 한 번도 열지 않던 것

`grep -n "daily" e2e/*.spec.ts` = 0건이었다 ⇒ 통과한 E2E 33 은 이 결함에 대해
아무 증거도 주지 않았다. `e2e/stock-master.spec.ts` 에 **G-E2E-9** 1건 추가 —
목록 행 클릭 → 일봉 탭 전환 → `stock-master-daily-table` 가시 →
문자열 목 `"1.2000"` 이 `+1.20%` 로, 숫자 목 `0.9` 가 `+0.90%` 로 렌더되는지
셀 단위(`td` nth(6))로 단언 + `NaN`·`'—'` 부재.
Playwright LIFO 규약 유지 — 목록 라우트만 `installApiMocks` **뒤에** 등록해 덮고,
일봉 목은 `e2e/fixtures/api-mocks.ts` 정본(문자열/숫자 혼합 5행)을 그대로 쓴다.

안정성 확인 = 전체 E2E **3회 반복 34/34 PASS**(17.8s / 17.7s / 17.7s) — flaky 아님.

### 뮤테이션 실증 (가드가 실제로 잡는지)

| 뮤테이션 | 결과 |
|---|---|
| `toSafeNumber` 의 문자열 분기 삭제 | G-E2E-9 **FAILED**(KILLED) |
| 타입에서 `created_at?` 삭제 | G-266-5 **FAILED**(KILLED) |
| `prtt_rate?: number \| string` → `number` | G-266-6 **FAILED**(KILLED) |

### 추가 가드

* `tests/unit/routes/test_cycle266_daily_route_serialization.py`
  — `test_c266_d1_1_404_detail_does_not_assert_the_cause_alone` /
  `..._d1_2_404_detail_carries_a_greppable_log_token` /
  `..._d1_3_log_token_in_detail_matches_the_real_markers`(라우트·db 소스의 **실제**
  로그 리터럴과 안내 토큰을 대조 — db 모듈은 **읽기만** 한다)
* `frontend/src/pages/__tests__/StockMaster.dailyTab.cycle266.test.tsx`
  — D-1-1 ~ D-1-4(행위) · G-266-5/G-266-6(D-2 타입 14필드 + prtt_rate) ·
  G-266-7(D-1 안내 리터럴 정적 핀)
* `tests/unit/e2e_mocks/test_cycle266_mock_string_change_rate.py`
  — `test_c266_d3_e2e_spec_opens_the_daily_tab` /
  `..._d3_e2e_spec_asserts_string_change_rate_rendering`

### 게이트 (실측)

| 명령 | 결과 |
|---|---|
| `python -m pytest -q` | **7,321 passed** · 11 skipped · 328 xfailed · 13 xpassed (228s) |
| `npx tsc -b` | exit **0** |
| `npm test` | 78 파일 / **599 passed** |
| `npx playwright test` ×3 | **34 / 34 / 34 passed** |
| `wc -l src/routes/stock_master.py` | **338L** (상한 340L, 여유 2행 유지) |

8영역 · `src/engine/scheduler.py` · `src/engine/strategies/*.py` ·
`src/db/stock_master_daily.py` **diff 0**.
