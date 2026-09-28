# cycle387 Red 명세 — 종목 차트(KLineChart, 최근 5년 일봉·주봉·월봉)

- 작성: team-leader(계획) · 2026-09-28(월) 16:5x KST
- 사용자 요청 원문(09-28): 「잔고내역과 거래내역(주문체결내역, 매매손익)에서 종목을 더블클릭하면 KLineChart를 사용한 주식차트조회를 최근 5년치에 대해 일봉/주봉/월봉으로 제공」 · 순서 「cycle386 끝나면 바로」(워크리스트 47행)
- 사용자 규칙: **새 제안 금지 — 요청한 것만 만든다.** 범위 밖은 §10 한 줄 후속으로만
- 무접촉: 8영역(`src/engine/{risk,order_engine,session,scanner,strategy_registry}.py` · `src/api/order.py` · `src/realtime/**` · `src/auth/**`) · `scheduler.py` · `src/middleware/**`(X-API-Key 미들웨어) · `src/api/base.py` · `src/api/condition.py`(상수 import 만) · cycle383/386 미푸시 커밋의 파일들
- 매매 행위 변경 0. 새 경로는 **읽기 전용 KIS 시세 조회** 하나다
- 배포: `src/` + `frontend/` 변경 = **full**(backend 재시작). 이번 실행에서는 배포하지 않는다(§8)

---

## 0. 결론 (한눈에)

| 항목 | 정한 것 |
|---|---|
| 데이터 원천 | KIS `FHKST03010100`(국내주식기간별시세) · 시장 **`J`**(KRX) · **수정주가 `0`** · 기간 `D`/`W`/`M`. 우리 `stock_master_daily` 는 390일 보관이라 5년이 안 된다 → 쓰지 않는다 |
| 호출 경로 | `src/api/base.py::kis_get_quote`(시세 풀 · 전역 초당 제한 · 재시도 · 메트릭) **단일**. `kis_get`/`kis_post`(주문·잔고 경로) 금지 |
| 새 백엔드 경로 | `GET /api/stock-chart/candles?ticker=005930&period=D&years=5` |
| 조회 방식 | 시작일 고정 + **종료일 커서를 과거로 당기는** 날짜 창 페이징(KIS 는 `tr_cont` 다음조회 불가 · 호출당 최대 100봉). 5년 일봉 약 13회 · 주봉 3회 · 월봉 1회 |
| 폭주 방지 | ① (ticker, period, years) 캐시 10분(부분 결과 1분) ② 같은 키 single-flight ③ **모듈 전역 동시 조회 1건**(다른 종목은 줄 선다, 대기 상한 20초) ④ 차트 KIS 호출 사이 0.25초(조회 경계를 넘어서도 — 모든 호출 앞) → 이 기능이 쓰는 KIS 호출은 **초당 4건 이하** ⑤ 요청당 호출 상한 D15·W4·M2 ⑥ 조회 시간 예산 25초 |
| 오늘 봉(cycle386) | **KIS 가 주는 값 그대로 두고 표시만 한다** — 마지막 봉이 아직 확정 전이면 `last_bar_provisional=true`, 화면이 「잠정」 문구를 단다. 값을 고치거나 버리지 않는다 |
| 실패 | 첫 창 실패 = `success=false` + 메시지(HTTP 200). 둘째 창 이후 실패 = 받은 만큼 `success=true, complete=false`(부분) |
| 화면 | 세 그리드의 **행 더블클릭 → 모달**. 일봉/주봉/월봉 토글(기본 일봉) · 캔들 + 거래량 패널 · 로딩/오류/빈/부분/잠정 상태 · ×·ESC·바깥 클릭 닫기 · 폰 폭 대응 |
| 라이브러리 | `klinecharts` **`10.0.3` 정확 고정**(Apache-2.0, 타입 동봉 `dist/index.d.ts`) · 모달은 `React.lazy` 로 분리 청크 |
| 날짜 | 백엔드 `YYYY-MM-DD`(KRX 영업일) → 프론트 `KST 자정 epoch ms` → 표시는 `utils/kst.ts` 새 헬퍼(`timeZone:'Asia/Seoul'`) |

---

## 1. 백엔드

### 1.1 파일

| 파일 | 종류 | 내용 |
|---|---|---|
| `src/api/period_chart.py` | **신규** | KIS 날짜 창 페이징 · 정규화 · 잠정 판정 · 캐시 · single-flight · 동시 1건 세마포어 |
| `src/models/candle_chart.py` | **신규** | pydantic `CandleBar` · `CandleChart`(응답 계약 — `src/api/CLAUDE.md` 「새 API 추가 절차」 4) |
| `src/routes/stock_chart.py` | **신규** | `GET /api/stock-chart/candles` |
| `src/main.py` | 수정 2줄 | `from src.routes import (…, stock_chart)` + `app.include_router(stock_chart.router)` (`src/main.py:31-51`, `:347-366` 블록 끝) |

🔴 **세 파일의 이름(basename)을 서로 다르게 둔다** — 같은 이름 파일쌍은 2026-09-19 덮어쓰기 사고(`routes/market_regime.py` → `engine/market_regime.py`)의 경로다. 백엔드 세 파일은 **한 에이전트가 순서대로** 쓴다.

### 1.2 라우트 계약

```
GET /api/stock-chart/candles?ticker=<6자리 숫자>&period=D|W|M&years=1..5
```

| 파라미터 | 규칙 | 위반 |
|---|---|---|
| `ticker` | `Query(..., pattern=r"^[0-9]{6}$")` — 진입 규칙과 같은 6자리 **ASCII 숫자**(`\d` 는 아랍-인도·전각 숫자도 통과시킨다)(`fetch_daily_candles_ranged` 가드 `src/api/condition.py:729-763` 와 동일) | 422 |
| `period` | `Literal["D","W","M"]`, 기본 `"D"` (대문자만) | 422 |
| `years` | `int`, `ge=1, le=5`, 기본 `5` | 422 |

- 경로에 종목코드를 넣지 않고 **쿼리로** 받는다 — `MetricsMiddleware` 가 raw path 로 키를 만들어(`src/main.py:59-69`) 경로형이면 종목마다 메트릭 키가 는다.
- 인증: 기존 `ApiAuthMiddleware` 가 그대로 덮는다(미들웨어 무변경). 리포터 키는 GET 전체 허용이라 이 경로도 읽는다 — 허용(작업 지시).
- 메서드는 GET 하나. POST 등은 405.

**응답(성공, HTTP 200)** — `ApiResponse{success, data, message}`, `data` = `CandleChart.model_dump(mode="json")`:

```json
{
  "success": true,
  "message": "일봉 1,231개",
  "data": {
    "ticker": "005930",
    "name": "삼성전자",
    "period": "D",
    "years": 5,
    "adjusted": true,
    "market": "J",
    "start_date": "2021-09-28",
    "end_date": "2026-09-28",
    "bars": [
      {"date": "2021-09-28", "open": 76700, "high": 77000, "low": 75800, "close": 76100, "volume": 12345678, "amount": 941234567890},
      "…오래된 것 → 최신 순(오름차순)…"
    ],
    "complete": true,
    "incomplete_reason": null,
    "last_bar_provisional": true,
    "dropped_bars": 0,
    "kis_calls": 13,
    "cached": false,
    "fetched_at": "2026-09-28T16:55:02+09:00"
  }
}
```

- `bars[].date` = `YYYY-MM-DD`(KIS `stck_bsop_date` 를 그대로 변환 — KRX 영업일이라 곧 KST 날짜). 숫자 6칸은 **JSON 정수**(pydantic `int`) — 문자열로 나가면 안 된다(cycle266 계열).
- `name` = 첫 호출 `output1.hts_kor_isnm`(strip, 비면 `null`). 화면은 행의 종목명을 우선 쓴다.
- `start_date`/`end_date` = 요청 구간(§1.3), 첫 봉 날짜가 아니다.
- `incomplete_reason` ∈ `"call_cap" | "time_budget" | "window_error" | "no_progress" | null`.
- `dropped_bars` = 가격 0 행·범위 밖 행으로 버린 수(§1.3-5).
- `kis_calls` = 이 결과를 만든 조회의 KIS 호출 수. `cached` = 이번 응답이 캐시에서 나왔는가.
- `fetched_at` = `src.db._kst.now_kst_iso()`(`+09:00`).
- `message` = 성공 `"{일봉|주봉|월봉} {N:,}개"` · 부분 `"… — 일부 구간만(사유)"` · 빈 결과 `"표시할 봉이 없습니다"`.

**실패(HTTP 200, `success=false`, `data=null`)** — 작업 지시 「KIS failure → success=false message」:

| 원인 | message |
|---|---|
| 첫 창 `KisApiError` | `"KIS 조회 실패 [{msg_cd}] {msg1}"` |
| 대기 초과(`ChartBusyError`) | `"다른 차트 조회가 진행 중입니다 — 잠시 후 다시 시도하세요"` |
| 그 밖의 예외 | `"차트 조회 실패 — 서버 로그 [stock_chart_error] 확인"` (예외 문자열을 응답에 싣지 않는다) |

### 1.3 KIS 조회 계획 (`src/api/period_chart.py`)

**요청 파라미터** — KIS 정본 `docs/kis/domestic-stock-quote.md:5460-5465`:

```python
params = {
    "FID_COND_MRKT_DIV_CODE": "J",        # KRX 정규 — UN/NX 금지(정규장 종가가 없다, cycle386 §4-1)
    "FID_INPUT_ISCD": ticker,
    "FID_INPUT_DATE_1": start_yyyymmdd,   # 모든 창에서 고정
    "FID_INPUT_DATE_2": cursor_yyyymmdd,  # 창마다 과거로 당긴다
    "FID_PERIOD_DIV_CODE": period,        # "D" | "W" | "M"
    "FID_ORG_ADJ_PRC": "0",               # 수정주가 — 기존 3 함수와 같은 값
}
data = await kis_get_quote(DAILY_PRICE_URL, "FHKST03010100", params)
```

- URL 은 `from src.api.condition import DAILY_PRICE_URL`(`condition.py:198`, 이미 시세 풀 화이트리스트 `base.py:78-80`). condition.py 의 최상위 import 는 `base`·`config` 뿐이라 결합이 가볍다.
- TR_ID 는 `"FHKST03010100"` 리터럴 — FH 접두사 TR 은 실전·모의 동일이라 `settings.get_tr_id()` 를 쓰면 `VH…` 로 깨진다(`src/api/finance.py:13-15` 규약과 같다).
- `tr_cont` 로 다음 페이지를 받을 수 없다(`docs/kis/domestic-stock-quote.md:5448`) → 날짜 창 페이징이 유일한 길이다. 한 호출에 최대 100봉이고 KIS 는 **구간 안의 최신 100봉**을 최신순으로 준다(KIS MCP 샘플 「한 번의 호출에 최대 100건」 · 기존 `_fetch_daily_candles_and_cache` 가 `output[:days]` 로 같은 성질에 기댄다, `condition.py:596-642`).

**1) 구간** — `today = now_kst.date()`(`now_kst` 는 주입 seam, 기본 `datetime.now(KST)`):

| period | `start` | `end` |
|---|---|---|
| D | `today` 에서 `years` 년 전 같은 월·일(2/29 → 2/28) | `today` |
| W | 위 날짜가 속한 ISO 주의 **월요일** | `today` |
| M | 위 날짜가 속한 달의 **1일** | `today` |

W·M 시작을 버킷 첫날로 맞추는 이유 = 첫 봉이 반쪽 주·반쪽 달로 잘리지 않게.

**2) 버킷** — 봉이 대표하는 기간. D = 그 날, W = ISO 주(`date.isocalendar()` 의 (year, week)), M = (year, month). KIS 가 주봉·월봉 날짜를 기간의 첫날로 찍는지 마지막 날로 찍는지는 정본에 없다 — **버킷으로 다루면 어느 쪽이든 맞는다.**

**3) 커서 페이징** — 창 k 가 돌려준 봉 중 가장 오래된 날짜를 `oldest` 라 할 때:

| period | 다음 커서 `next_end` |
|---|---|
| D | `oldest − 1일` |
| W | `oldest` 주의 월요일 − 1일(= 전 주 일요일) |
| M | `oldest` 달의 1일 − 1일(= 전달 말일) |

`FID_INPUT_DATE_1` 은 모든 창에서 `start` 로 고정한다(창 사이 구멍·겹침이 원천적으로 없다 — `fetch_daily_candles_backfill` 의 stride 함정 `condition.py:708-725` 을 피한다).

**4) 멈춤 조건** — 매 호출 뒤 이 순서로 본다:

| # | 조건 | 결과 |
|---|---|---|
| 1 | 호출 예외 — **첫 창** | 예외 전파 → 라우트가 `success=false` |
| 2 | 호출 예외 — 둘째 창 이후 | 멈춤, `complete=false`, `window_error` |
| 3 | 날짜 있는 행 0개 | 멈춤, complete |
| 4 | 날짜 있는 행 < 100 | 멈춤, complete(KIS 가 구간 끝까지 다 줬다 — 상장 5년 미만 종목 포함) |
| 5 | `oldest` 버킷 첫날 ≤ `start` | 멈춤, complete |
| 6 | `next_end < start` | 멈춤, complete |
| 7 | `next_end ≥ 현재 커서`(진전 없음) | 멈춤, `complete=false`, `no_progress` + WARNING |
| 8 | 호출 수 = 상한(D15·W4·M2) | 멈춤, `complete=false`, `call_cap` |
| 9 | 경과 > 25초(다음 호출 **전** 판정, 호출 도중 취소 없음) | 멈춤, `complete=false`, `time_budget` |

그 외 → 다음 창. 간격은 창 사이가 아니라 **모든 KIS 호출 앞**에서 지킨다 — 모듈 전역 「마지막 차트 호출 시각」 으로부터 0.25초가 될 때까지만 쉰다(세마포어 안, 조회 경계를 넘어서도). 그래서 줄 선 다음 조회의 첫 호출·월봉(1회 호출)도 쉰다. 프로세스의 첫 호출 앞에는 sleep 이 없다.
「날짜 있는 행」 = `stck_bsop_date` 가 빈 placeholder 를 뺀 행(기존 3 함수와 같은 필터). 가격 0 행도 100 계산에는 넣는다(날짜가 있으면 KIS 가 준 행이다).

**5) 병합·정규화**
- 병합 키 = 버킷. 같은 버킷이 두 번 오면 **먼저 받은 것(더 최신 창)** 을 남긴다.
- 문자열 → 정수: 빈 값·비숫자 = 0. 필드 매핑 `stck_oprc→open` · `stck_hgpr→high` · `stck_lwpr→low` · `stck_clpr→close` · `acml_vol→volume` · `acml_tr_pbmn→amount`.
- **버리는 행**(`dropped_bars` 로 센다): 시가·고가·저가·종가 중 하나라도 ≤ 0(체결 없는 날 — KIS `mod_yn=Y`, `docs/kis/domestic-stock-quote.md:5524`) · 날짜 > `today` · 버킷 첫날 < `start`. 0을 가격으로 그리면 y축이 0까지 늘어난다(cycle383 휴장일 0 행 결함과 같은 계열).
- 오름차순(오래된 것 먼저)으로 정렬해 돌려준다(KLineChart 가 요구하는 순서).

**6) 잠정 판정 `last_bar_provisional`** — 순수 함수 `_is_provisional(last_date, period, now_kst)`:

```
latest_open_day = (now_kst − 6시간).date()
provisional = 마지막 봉 버킷 안에 「평일 d ≥ latest_open_day」 가 하나라도 있으면 True
              (D 의 버킷 = 그 날 하루)
```

근거(cycle386 실측, `src/engine/CLAUDE.md:198`): KIS `J` 일봉은 D일 20:00 뒤에도 종가를 19:59 애프터마켓 마지막 체결가로, 고저를 애프터마켓까지 넣은 범위로 준다. 정규장 값으로 바뀌는 것은 D일 23:12 뒤 ~ D+1일 05:28 전이다 → 06:00 을 경계로 쓴다(`daily_bar_finalize` 의 06:00 경계와 같은 값). 장중에는 당연히 진행 중인 봉이다.
판정 예(테스트 S11·S12 가 그대로 잰다): 월 10:00 오늘 봉 → True · 화 03:00 월요일 봉 → True · 화 07:00 → False · 토 03:00 금요일 봉 → True · 토 07:00 → False · 일 12:00 지난주 주봉 → False · 수 10:00 이번 주 주봉 → True · 9/30 21:00 9월 월봉 → True · 10/1 07:00 9월 월봉 → False.

🔴 **값은 고치지 않는다.** 잠정 봉을 버리거나 전일 값으로 바꾸지 않는다 — 장중에는 그 봉이 운영자가 보고 싶은 값이다. 거래량·거래대금은 확정 봉도 애프터마켓을 포함한다(같은 절) — 표시 문구에 넣지 않는다(확정 봉과 다르지 않으므로).

### 1.4 캐시 · single-flight · 동시성 · 호출 상한

| 상수 | 값 | 뜻 |
|---|---|---|
| `_KIS_MAX_ROWS` | 100 | 호출당 최대 봉 |
| `_MAX_CALLS_PER_FETCH` | `{"D": 15, "W": 4, "M": 2}` | 요청당 KIS 호출 상한(5년 기준 필요량 13·3·1 + 여유) |
| `_WINDOW_SLEEP_SECS` | 0.25 | 차트 KIS 호출 사이 최소 간격(조회 경계를 넘어서도) |
| `_FETCH_CONCURRENCY` | 1 | 모듈 전역 동시 조회 수 |
| `_QUEUE_WAIT_SECS` | 20.0 | 세마포어 대기 상한 → 넘으면 `ChartBusyError` |
| `_FETCH_TIME_BUDGET_SECS` | 25.0 | 한 조회의 시간 예산(§1.3-4 #9) |
| `_CACHE_TTL_SECS` | 600.0 | 완전한 결과 보관 |
| `_PARTIAL_CACHE_TTL_SECS` | 60.0 | 부분 결과 보관(같은 실패로 반복 호출하는 것을 1분 누른다) |
| `_CACHE_MAX_ENTRIES` | 32 | LRU 상한(5년 일봉 1건 ≈ 1,230봉 — 메모리 2GB 박스 고려) |
| `_PROVISIONAL_CUTOFF` | `timedelta(hours=6)` | §1.3-6 |

동작 순서(공개 함수 `fetch_candle_chart(ticker, period="D", years=5, *, now_kst=None) -> CandleChart`):

1. 인자 검증 — 위반은 `ValueError`(라우트는 FastAPI 검증이 먼저 422 로 막으므로 방어선 2).
2. 캐시 조회 — 유효하면 `model_copy(update={"cached": True})` 반환, KIS 0회.
3. single-flight — 같은 키의 진행 중 task 가 있으면 그것을 `asyncio.shield` 로 기다린다(`condition.py:645-686` 패턴). 없으면 task 생성 + `add_done_callback` 으로 예외 회수(joiner 0명일 때 경고 방지 — `condition.py:83` 과 같은 역할의 **로컬** 헬퍼, private 함수를 import 하지 않는다).
4. task 본체 — `asyncio.wait_for(semaphore.acquire(), _QUEUE_WAIT_SECS)` → 실패 시 `ChartBusyError`. 얻으면 페이징 전체가 끝날 때까지 쥔다(다른 종목·기간은 줄 선다).
5. 결과 저장 — 완전 = 600초, 부분 = 60초, **예외는 저장하지 않는다**. 저장할 때 이미 만료된 항목을 걷어낸다. inflight 정리는 `finally`.
6. 요청이 끊겨도(모달 닫힘) task 는 shield 로 끝까지 돌고 캐시를 채운다 — 다시 열면 캐시에서 나온다.

**상한의 산수** — 이 기능이 KIS 로 보내는 호출은 직렬 1건 × 호출 사이 0.25초(조회 경계 포함)라 **초당 4건 이하**, 요청 하나당 최대 15건(+ `_request_via_quote_pool` 자체 재시도 최대 3회/건, 네트워크·5xx 한정). 프로세스 전역 `_rate_limit()`(초당 20, `base.py:437-451`)을 주문·잔고 경로와 **함께** 쓰므로 이 몫이 20% 를 넘지 않게 묶는 것이 간격의 목적이다. 여러 사용자·연속 더블클릭은 캐시 → single-flight → 세마포어 순으로 흡수된다.

**보조 시세 계정** — `kis_get_quote` 는 활성 보조 계정을 라운드로빈으로 쓰고, 보조 계정이 없거나 토큰 발급·5xx 급증 때 **메인 토큰으로 넘어간다**(기존 시세 풀 동작, `base.py:693-772` · `:767`). 이번 사이클은 `base.py` 를 건드리지 않으므로 이 폴백을 그대로 받는다 — 메인으로 넘어가도 위 간격·직렬이 메인 키 몫을 초당 4건 이하로 묶는다. 차트 전용 폴백 금지는 §10 후속.

**테스트 seam** — `_reset_state_for_tests()` 가 캐시·inflight·세마포어·잠금을 **새로 만든다**(asyncio 프리미티브는 처음 기다린 루프에 묶여, 테스트마다 새 루프면 재사용 시 `RuntimeError`). 시계는 모듈 속성 `_monotonic = time.monotonic` 을 테스트가 갈아끼운다. `kis_get_quote`·`asyncio.sleep` 은 모듈 이름으로 참조해 monkeypatch 가능하게 둔다.

### 1.5 관측

| 마커 | 레벨 | 언제 |
|---|---|---|
| `[stock_chart_fetch] ticker= period= years= calls= bars= dropped= complete= reason= elapsed_ms=` | INFO | KIS 조회 1건이 끝날 때마다(캐시 적중은 남기지 않는다) |
| `[stock_chart_partial] ticker= period= reason= calls= bars= oldest=` | WARNING | `complete=false` |
| `[stock_chart_error] ticker= period= stage=first_window|unexpected err=` | WARNING | 라우트가 `success=false` 로 답할 때(예외 문자열은 로그에만) |
| `[stock_chart_busy] ticker= period= waited_s=` | WARNING | 대기 초과 |

KIS 거부 원문은 이미 `base._request*` 가 `[kis_rejection]` 으로 영구 저장한다 — 중복 저장하지 않는다.

### 1.6 무접촉 · 재핀

- 8영역·`scheduler.py`·`base.py`·`condition.py`·미들웨어·`boot_manager.py`·전략 파일: 한 줄도 바꾸지 않는다(기존 sha 핀이 그대로 초록이어야 한다 — `tests/unit/ast/test_cycle222a3_ast_followup_fixes.py`).
- **재핀(값만, 사유 주석)** — `tests/unit/ast/test_cycle287_ast_scope.py`:
  - `_SRC_TREE_FILES` 163 → **166**(신규 3 파일) — 주석: 「cycle387 종목 차트 — 신규 `src/api/period_chart.py`·`src/models/candle_chart.py`·`src/routes/stock_chart.py` + `src/main.py` 등록 2줄. 매매 행위 변경 없음. 직전 값 = 163」
  - `_SRC_TREE_DIGEST` 새 값 — 주석 끝에 직전 값 `09bf5172aa7dde199fcab116470a4f4ad18d33e28d2265a8c29623e50762a354`
  - `_PINNED_DIR_FILE_COUNTS` 는 **움직이지 않는다**(`src/api`·`src/models`·`src/routes` 는 핀 대상 밖). 움직이면 파일을 잘못 둔 것이다
- 전체 스위트에서 그 밖의 핀이 붉어지면 **값만** 옮기고 사유를 적는다. 단언을 약하게 만들지 않는다.

---

## 2. 프론트엔드

### 2.1 파일

| 파일 | 종류 | 내용 |
|---|---|---|
| `frontend/package.json` · `package-lock.json` | 수정 | `"klinecharts": "10.0.3"`(캐럿 없이) — `cd frontend && npm install klinecharts@10.0.3 --save-exact` |
| `frontend/src/types/stock-chart.ts` | 신규 | `ChartPeriod = 'D' \| 'W' \| 'M'` · `StockChartBar` · `StockChartData`(백엔드 `CandleChart` 1:1, 필드명 동일) |
| `frontend/src/api/stock-chart.ts` | 신규 | `getStockChart(ticker, period, years = 5)` |
| `frontend/src/utils/stockChart.ts` | 신규 | 순수 함수 — `isChartableTicker` · `isInteractiveTarget` · `toKLineData` · `PERIOD_TO_KLINE` · `PERIOD_LABEL` |
| `frontend/src/utils/kst.ts` | 수정 | 새 헬퍼 3개(§2.5) |
| `frontend/src/components/StockChartModal.tsx` | 신규 | 모달 + KLineChart(기본 export, lazy 대상) |
| `frontend/src/components/useStockChartOpener.tsx` | 신규 | 훅 — 열림 상태 + 행 더블클릭 핸들러 + lazy 모달 요소 |
| `frontend/src/components/BalanceTable.tsx` | 수정 | 행 `onDoubleClick` + testid + title, 모달 요소 렌더 |
| `frontend/src/components/TradeHistoryGrid.tsx` | 수정 | 같음 |
| `frontend/src/components/TradePnLGrid.tsx` | 수정 | 같음 |
| `frontend/src/test/handlers.ts` · `frontend/src/test/fixtures/stockChart.fixture.ts` | 수정·신규 | MSW 기본 응답 |
| `e2e/fixtures/api-mocks.ts` · `e2e/fixtures/stock-chart.fixture.ts` | 수정·신규 | Playwright 목 |

`api/stock-chart.ts` 와 `types/stock-chart.ts` 는 리포 관례(`stock-master.ts` 쌍)대로 같은 이름이다 — **frontend-dev 한 명이 순서대로** 쓴다.

### 2.2 행 더블클릭 — 세 그리드

| 그리드 | 행 렌더 자리(수정 지점) | 종목코드·이름 | 더블클릭에서 빼야 할 버튼 |
|---|---|---|---|
| 잔고 `BalanceTable` | `BalanceTable.tsx:257-341` 의 `<tr key={h.ticker} …>` = **:262** | `h.ticker` · `h.name`(`types/balance.ts:2-3`). 행 목록은 이미 `^[0-9A-Z]{6}$` 로 거른다(:184) | 「매도」 `:326-337`(클릭 = 매도 확인창 `:348-360`) |
| 주문체결내역 `TradeHistoryGrid` | `TradeHistoryGrid.tsx:385-393` 의 `<tr key={row.id} …>` = **:386** | `row.original.ticker` · `ticker_name`(`types/trading.ts:217-218`, 열 정의 `:148-155`) | 「AI 자문」 `:279-292` |
| 매매손익 `TradePnLGrid` | `TradePnLGrid.tsx:369-383` 의 `<tr …>` = **:372-375** | `row.original.ticker` · `ticker_name`(`types/trading.ts:242-243`, 열 정의 `:81-88`) | 「AI 자문」 `:208-223` |

탭 전환 = `pages/History.tsx:37`(탭을 바꾸면 그리드가 언마운트돼 모달도 닫힌다 — 정상).

각 행에 더하는 것:
```tsx
<tr
  …기존 key·className 그대로…
  data-testid={`balance-row-${h.ticker}`}          // 잔고 / 체결: `trade-row-${row.index}` / 손익: `pnl-row-${row.index}`
  title="더블클릭 — 종목 차트"
  onDoubleClick={(e) => openChart(e, h.ticker, h.name)}
>
```
- `openChart(e, ticker, name)` = `useStockChartOpener()` 가 돌려주는 핸들러:
  1. `isInteractiveTarget(e.target)` 이면 **무시** — `button, a, input, select, textarea, label` 또는 그 자손. 「매도」 두 번 누름이 차트를 같이 열면 안 된다(매도 확인창과 차트 모달이 겹친다).
  2. `window.getSelection()?.removeAllRanges()` — 더블클릭이 셀 글자를 선택한 흔적을 지운다.
  3. `setTarget({ ticker: String(ticker ?? '').trim(), name: String(name ?? '').trim() })`.
- 모달 요소는 각 그리드의 최상위 `div` 안 마지막에 `{chartModal}` 로 둔다(기존 `LlmEvaluationModal`·`ConfirmModal` 자리 옆).
- 한 번 클릭은 아무것도 열지 않는다. 기존 동작(정렬·버튼·페이징)은 그대로.

### 2.3 모달 UX (`StockChartModal.tsx`)

셸은 `LlmEvaluationModal.tsx` 관용구를 그대로 쓴다 — ESC 닫기 `:204-212` · 열기 전 포커스 복귀 `:214-222` · 바깥 클릭 닫기/안쪽 `stopPropagation` · `role="dialog" aria-modal aria-labelledby`(`:233-258`).

```
┌ {종목명} ({ticker}) — 종목 차트                         [×] ┐
│ [일봉] [주봉] [월봉]      2021-09-28 ~ 2026-09-28 · 1,231봉 · 수정주가 · KRX │
│ (부분/잠정/오류 안내 줄)                                         │
│ ┌──────────── 캔들 (KLineChart) ────────────┐                │
│ ├──────────── 거래량 패널 ──────────────────┤                │
│ └───────────────────────────────────────────┘                │
└──────────────────────────────────────────────────────────────┘
```

- 제목 = 행의 이름 → 없으면 응답 `name` → 없으면 종목코드만.
- 토글 = 세 버튼(`aria-pressed`, testid `stock-chart-period-D|W|M`). 기본 **일봉**. 기간마다 조회는 그 기간을 처음 누를 때 한 번(React Query 캐시로 되돌아가면 재요청 없음).
- 메타 줄(`stock-chart-meta`) = `start_date ~ end_date · N봉 · 수정주가 · KRX`. 수정주가라 분할·병합 전 봉은 체결 내역의 실제 체결가와 다를 수 있다 — 「수정주가」 표기가 그 신호다.
- 상태(서로 배타, 우선순위 순):

| 상태 | testid | 모양 |
|---|---|---|
| 지원 안 되는 코드(`^\d{6}$` 아님) | `stock-chart-unsupported` | 회색 「6자리 숫자 종목코드만 차트를 볼 수 있습니다 (받은 값: …)」 · **요청 0건** |
| 로딩 | `stock-chart-loading` | 차트 자리 위 안내 「차트 불러오는 중… (5년 일봉은 수 초 걸립니다)」 |
| 오류 | `stock-chart-error` + `stock-chart-retry` | 빨강, 백엔드 `message`(또는 422 `detail`·네트워크 오류 문구) + 「다시 시도」 = `refetch()` |
| 빈 결과 | `stock-chart-empty` | 회색 「표시할 봉이 없습니다」 |
| 부분 | `stock-chart-partial` | 주황(beige) 줄 「일부 구간만 받았습니다({bars[0].date}부터) — {사유}. 1분 뒤 다시 열면 다시 받습니다」, 차트는 그린다 |
| 잠정 | `stock-chart-provisional` | 회색 작은 글씨 「마지막 봉({date})은 잠정값입니다 — 장중이거나 애프터마켓(16:00~20:00) 가격이 종가·고저에 섞여 있을 수 있습니다(다음 날 06:00 무렵 확정)」. W·M 이면 「이번 주/이번 달 봉은 진행 중입니다」 |

- 닫기 = × 버튼(`stock-chart-close`, `aria-label="닫기"`) · ESC · 바깥 클릭. 모달 루트 testid `stock-chart-modal`, 제목 `stock-chart-title`.
- 크기 = `w-[calc(100vw-16px)] sm:w-full sm:max-w-5xl mx-2 sm:mx-4 max-h-[92vh]`, 차트 자리(`stock-chart-canvas-host`) `h-[55vh] min-h-[280px]`. 폰 폭(375px)에서 가로 스크롤 없이 들어간다 — 토글·메타 줄은 `flex-wrap`.
- `useQuery({ queryKey: ['stockChart', ticker, period, 5], queryFn: () => getStockChart(ticker, period, 5), enabled: isChartableTicker(ticker), retry: 1, staleTime: (q) => (q.state.data?.complete === false ? 60_000 : 10 * 60_000), gcTime: 30 * 60_000 })` — `retry: 1` 명시는 리포 규약(`frontend/CLAUDE.md` 「테스트 규약」 1), `staleTime` 은 서버 캐시와 같은 값(완전 10분 · 부분 1분 — 부분 안내 「1분 뒤 다시 열면 다시 받습니다」 가 참이 되는 조건). 폴링 없음.
- 숫자 표시(메타 봉 수)는 `toLocaleString` 전에 방어 변환한다(규약 5).

### 2.4 KLineChart 통합 (`klinecharts@10.0.3`)

v10 API 로 쓴다(v9 의 `applyNewData`·`setCustomApi` 는 없다). 타입은 패키지의 `import type { Chart, KLineData, Period, DataLoader } from 'klinecharts'`.

마운트(effect, 의존성 `[ticker]`):
```ts
registerLocale('ko-KR', { time: '날짜', open: '시가', high: '고가', low: '저가', close: '종가',
  volume: '거래량', turnover: '거래대금', change: '등락', second: '초', minute: '분', hour: '시',
  day: '일', week: '주', month: '월', year: '년' })            // 모듈 최상위 1회
const chart = init(hostEl, {
  locale: 'ko-KR',
  timezone: 'Asia/Seoul',
  formatter: { formatDate: ({ timestamp, type }) =>
      type === 'xAxis' && periodRef.current === 'M'
        ? formatKstYearMonthFromEpochMs(timestamp)
        : formatKstDateFromEpochMs(timestamp) },
  styles: {
    candle: { bar: {
      upColor: PROFIT_HEX, upBorderColor: PROFIT_HEX, upWickColor: PROFIT_HEX,
      downColor: LOSS_HEX, downBorderColor: LOSS_HEX, downWickColor: LOSS_HEX,
      noChangeColor: NEUTRAL_HEX, noChangeBorderColor: NEUTRAL_HEX, noChangeWickColor: NEUTRAL_HEX } },
    indicator: { bars: [{ upColor: PROFIT_HEX, downColor: LOSS_HEX, noChangeColor: NEUTRAL_HEX }] },
  },
})
chart.setSymbol({ ticker, pricePrecision: 0, volumePrecision: 0 })
chart.createIndicator('VOL')                                    // 캔들 아래 거래량 패널(새 pane)
chart.setDataLoader({ getBars: ({ type, callback }) =>
    callback(type === 'init' ? barsRef.current : [], false) })  // 더 불러오기 없음
// ResizeObserver(hostEl) → chart.resize()  (jsdom 등 부재 시 건너뜀)
// 언마운트: observer.disconnect(); dispose(hostEl)
```
- 색은 `utils/pnlColor.ts` 의 `PROFIT_HEX`·`LOSS_HEX`·`NEUTRAL_HEX` 를 import 한다 — **새 hex 리터럴 금지**(`designSystem.v2.test.ts`). 국내 관례 = 상승 적색·하락 청색(라이브러리 기본은 반대).
- 데이터 교체(effect, 의존성 `[period, query.data]`):
  - 이 기간 데이터가 준비됨 → `barsRef.current = toKLineData(data.bars)` → `chart.setPeriod({ type: PERIOD_TO_KLINE[period], span: 1 })`. v10 의 `setPeriod` 는 매번 새 객체면 `resetData()` 를 거쳐 로더의 `init` 을 다시 부른다(`dist/index.esm.js` `StoreImp.setPeriod`→`resetData`→`_processDataLoad('init')` 확인).
  - 이 기간을 아직 받는 중 → `barsRef.current = []` → `chart.resetData()`(이전 기간 봉을 새 기간 이름으로 보여 주지 않는다).
- `PERIOD_TO_KLINE = { D: 'day', W: 'week', M: 'month' }`.
- `toKLineData(bars)` = 각 봉 `{ timestamp: kstDateToEpochMs(date), open, high, low, close, volume, turnover: amount }`. 숫자는 `toSafeNumber` 계열 방어 변환, 날짜·OHLC 중 하나라도 변환 실패인 봉은 버린다. 오름차순 보장(정렬 한 번 더).
- 모달은 `React.lazy(() => import('./StockChartModal'))` 로 **분리 청크**다(라이브러리 ESM 약 675KB, min 약 234KB — 세 그리드 초기 로딩에 싣지 않는다). `Suspense` fallback = 모달 셸 모양의 「차트 모듈 불러오는 중…」(testid `stock-chart-chunk-loading`). 그 바깥을 오류 경계가 감싼다 — 청크 로딩 실패(프론트 재배포 뒤 옛 탭)가 앱 전체를 내리지 않고 모달 자리에 안내 `stock-chart-chunk-error` + 닫기 `stock-chart-chunk-error-close` 를 띄운다.

### 2.5 KST 헬퍼 (`utils/kst.ts` 에 추가 — 새 `Intl.DateTimeFormat` 을 다른 파일에 만들지 않는다)

| 함수 | 반환 | 잘못된 입력 |
|---|---|---|
| `formatKstDateFromEpochMs(ms: number)` | `YYYY-MM-DD`(기존 `DATE_PART_FORMATTER` 재사용) | `'—'` |
| `formatKstYearMonthFromEpochMs(ms: number)` | `YYYY-MM` | `'—'` |
| `kstDateToEpochMs(ymd: string)` | `Date.parse(`${ymd}T00:00:00+09:00`)` — `^\d{4}-\d{2}-\d{2}$` 아니면 | `null` |

`StockChartModal.tsx`·`utils/stockChart.ts` 를 K4 가드의 `DELEGATING_FILES` 에 넣는다(`frontend/src/utils/__tests__/kst.test.ts`).

### 2.6 API 클라이언트 (`api/stock-chart.ts`)

기존 패턴 = `api/client.ts:3-19`(단일 axios 인스턴스, 기본 timeout 10초 `:5`) · `api/history.ts:12-24`(`ApiResponse<T>` 풀기) · `api/llm-evaluations.ts:66-76`(`params` 객체) · 요청별 timeout 선례 `api/macro.ts:33`.

```ts
export const STOCK_CHART_TIMEOUT_MS = 60_000   // 대기 20s + 조회 예산 25s + 마지막 호출. nginx `/api/` 는 proxy_read_timeout 미설정 = 기본 60s(120s 는 `/api/macro/` 전용)
export const getStockChart = async (ticker: string, period: ChartPeriod, years = 5): Promise<StockChartData> => {
  const { data } = await apiClient.get<ApiResponse<StockChartData | null>>('/stock-chart/candles', {
    params: { ticker, period, years }, timeout: STOCK_CHART_TIMEOUT_MS })
  if (!data.success || !data.data) throw new Error(data.message || '차트 조회 실패')
  return data.data
}
```
- axios 오류(422·500·네트워크)는 **잡지 않고** 흘린다(`llm-evaluations.ts:10-13` 규약) — 모달이 `axios.isAxiosError` 로 422 `detail` 을 꺼내 보여 준다.
- 인터셉터 추가 없음.

---

## 3. 테스트 목록 (Red)

모든 KIS 응답 목은 정본 응답 예시의 **문자열 모양 그대로**(`docs/kis/domestic-stock-quote.md:5582-5596` output2 행: 숫자가 전부 문자열, `mod_yn`·`flng_cls_code` 포함)로 만든다. 프론트 목은 §3.2-F 의 방식으로 만든 백엔드 JSON 을 **리터럴로** 옮긴다(`frontend/CLAUDE.md` 「테스트 규약」 5).

### 3.1 백엔드

**`tests/unit/api/test_cycle387_period_chart_fetch.py`** — `kis_get_quote`·`asyncio.sleep`·`_monotonic` 을 모듈에서 monkeypatch, autouse fixture 가 `_reset_state_for_tests()`. KIS 가짜 = 「(DATE_1, DATE_2) 구간 안 최신 100봉을 최신순으로」 주는 합성 달력(평일만, 필요 시 공휴일 목록).

| ID | 검증 |
|---|---|
| S1 | 첫 호출 인자 = (`condition.DAILY_PRICE_URL`, `"FHKST03010100"`, 정확한 params 6키 — `J` · `ORG_ADJ_PRC "0"` · `DATE_1=20210928` · `DATE_2=20260928` · `PERIOD "D"`) |
| S2 | D 5년(now 2026-09-28 10:00 KST 고정): 호출 수 = ceil(봉수/100) · 모든 호출의 `DATE_1` 동일 · 각 `DATE_2` = 직전 `oldest − 1일` · 결과 오름차순·중복 0·개수 = 달력 봉수 · 첫 봉 ≥ start · 마지막 봉 = today |
| S3 | 상장 5년 미만(2025-03-10 상장) → 마지막 호출이 100 미만에서 멈춤, **빈 호출 추가 0**, `complete=true` |
| S4 | 봉수가 정확히 100의 배수이고 `oldest == start` → 추가 호출 없이 멈춤(멈춤 #5) |
| S5 | 첫 응답 빈 목록 → `bars=[]`, `complete=true`, 호출 1 |
| S6 | W · 월요일 날짜 봉: `start = 2021-09-27`(월) · 호출 3 · 2번째 `DATE_2` = 1번째 oldest 의 전 주 **일요일** · ISO 주 중복 0 |
| S7 | W · **금요일 날짜 봉** 변형: S6 과 같은 커서(목요일이 아니라 전 주 일요일) · ISO 주 중복 0 — 날짜 규약이 어느 쪽이든 맞는다 |
| S8 | M: `start = 2021-09-01` · 61봉 → 호출 1 · (년,월) 중복 0 |
| S9 | 가짜가 창끼리 겹치는 봉을 주면 버킷당 1개, **더 최신 창의 값**이 남는다 |
| S10 | 정규화: 문자열→정수 · 출력 키 정확히 `{date, open, high, low, close, volume, amount}` · `date` = `YYYY-MM-DD` · `stck_oprc "0"`(mod_yn Y) 행 제거 + `dropped_bars` 증가 · 날짜 > today 행 제거 · 날짜 없는 placeholder 는 100 계산에서 빠진다 |
| S11 | 잠정 D: §1.3-6 의 다섯 시각 그대로(freezegun/`now_kst` 주입) |
| S12 | 잠정 W·M: 일 12:00 지난주 → False · 수 10:00 이번 주 → True · 9/30 21:00 → True · 10/1 07:00 → False |
| S13 | 호출 상한: `_MAX_CALLS_PER_FETCH["D"]=3` 으로 낮추면 3회에서 멈춤, `complete=false`, `call_cap` |
| S14 | 진전 없음: 가짜가 매번 같은 100봉 → 2회에서 멈춤, `no_progress`, WARNING `[stock_chart_partial]`(caplog 는 WARNING 이상 + 접두어로만 단언) |
| S15 | 시간 예산: `_monotonic` 이 2회 뒤 26초를 넘기면 3번째 호출 없이 `time_budget` |
| S16 | 첫 창 `KisApiError` → 그대로 전파 · **캐시 안 됨**(다시 부르면 KIS 다시 호출) |
| S17 | 3번째 창 예외 → 앞 두 창의 봉 + `complete=false` + `window_error` · 60초 안 재호출은 캐시(KIS 0회) · 61초 뒤 재호출은 새 조회 |
| S18 | 간격: 첫 호출 앞에는 없고, 이후 모든 호출 앞에서 직전 호출로부터 0.25초가 될 때까지만 쉰다(호출 시간 0.0625초면 sleep 0.1875) · 호출 간격 = 0.25 |
| S18b | 월봉 두 조회를 잇달아 → 두 KIS 호출 간격 ≥ 0.25초 |
| S18c | 서로 다른 40종목(D·W·M 섞어) 동시 요청 → 모든 호출 간격 ≥ 0.25초 · 어느 1초 창에도 4건 이하 |
| S19 | 캐시: 같은 키 두 번 → 조회 1번, 두 번째 `cached=true` · 601초 뒤 → 새 조회 · 33번째 키가 들어오면 가장 오래 안 쓴 키 퇴출 |
| S19b | 저장할 때 만료된 항목을 걷어낸다(601초 지난 키는 다른 키 저장 뒤 `_cache` 에 없다) · 살아 있는 항목은 남는다 |
| S20 | single-flight: 같은 키 동시 2요청 → KIS 호출은 한 조회분, 두 결과 동일 |
| S21 | 직렬: 다른 키 동시 2요청 → 가짜가 잰 **동시 진행 KIS 호출 최대 1**, 둘 다 완료 |
| S22 | 대기 초과: 세마포어를 쥔 채 `_QUEUE_WAIT_SECS` 를 작게 → `ChartBusyError`, KIS 0회 |
| S23 | 검증: ticker `'A12345'`·`'12345'`·`'0059300'`·`None`·아랍-인도 숫자 `'٠٠٥٩٣٠'`·전각 숫자 `'００５９３０'` / period `'Y'`·`'d'` / years `0`·`6` → `ValueError`, KIS 0회 |
| S24 | years=1 구간 · 윤일: now 2028-02-29 → D start 2023-02-28 |
| S25 | 호출자 취소(모달 닫힘): 기다리던 코루틴을 cancel 해도 조회 task 는 끝나고 캐시가 채워진다 |
| S26 | respx 계약(선례 `tests/unit/api/test_cycleC1_finance_fetch.py` G-C1-FIN-8): `kis_get_quote` 를 respx 가 가로챈 httpx 응답으로 대체해, 실제 KIS JSON 모양(문자열 숫자·`output1`·`output2`)이 끝까지 정수 봉으로 나오는지 |

**`tests/unit/routes/test_cycle387_stock_chart_route.py`** — 라우터만 실은 독립 앱(`tests/unit/routes/test_cycle266_daily_route_serialization.py:60-66` 패턴), `period_chart.fetch_candle_chart` 를 AsyncMock 으로.

| ID | 검증 |
|---|---|
| R1 | 성공: `success=true` · `data` 키 집합이 §1.2 와 정확히 같다 · `bars[*]` 여섯 숫자가 **JSON 정수**(문자열·bool 아님) · `date` 문자열 · `fetched_at` 이 `+09:00` 로 끝남 · `message` 「일봉 N개」 |
| R2 | 422: ticker `00593`·`0059300`·`ABCDEF`·빈 값·아랍-인도 숫자·전각 숫자 / period `Y`·`d` / years `0`·`6` — 서비스 호출 0 |
| R3 | `KisApiError("1","EGW00123","…")` → 200 · `success=false` · `data=null` · message 에 msg_cd |
| R4 | 일반 예외 → `success=false` · message 에 예외 문자열 없음 · `[stock_chart_error]` WARNING |
| R5 | `ChartBusyError` → `success=false` 대기 문구 |
| R6 | 부분 결과 → `success=true` · `complete=false` · message 에 「일부 구간만」 |
| R7 | 빈 결과 → `success=true` · message 「표시할 봉이 없습니다」 |
| R8 | POST → 405 |
| R9 | `src/main.py` AST: `stock_chart` import 1 · `include_router(stock_chart.router)` 1(선례 `test_cycle276_llm_evaluations_route.py:458-473`) |
| R10 | 인증 무변경: `real_api_auth` 마커로 실제 `authorize` — 무키 401 · 운영 키 통과 · 리포터 키 GET 통과(미들웨어 코드 diff 0) |

**`tests/unit/ast/test_cycle387_ast_stock_chart_scope.py`**

| ID | 검증 |
|---|---|
| G1 | `src/api/period_chart.py` import 허용 목록 = 표준 라이브러리 · `src.api.base`(`kis_get_quote`·`KisApiError` 만) · `src.api.condition`(`DAILY_PRICE_URL` 만) · `src.db._kst` · `src.models.candle_chart`. `kis_get`·`kis_post`·`kis_request`·`src.api.order`·`src.engine`·`src.realtime`·`src.auth` 0건 |
| G2 | KIS 호출은 `kis_get_quote(DAILY_PRICE_URL, "FHKST03010100", …)` 한 곳 · params 리터럴에 `"FID_COND_MRKT_DIV_CODE": "J"` 와 `"FID_ORG_ADJ_PRC": "0"` |
| G3 | `src/routes/stock_chart.py`: 라우트 데코레이터는 `get` 만 · `src.engine`·`scheduler`·`src.api.order` import 0 |
| G4 | 상수 핀: `_MAX_CALLS_PER_FETCH == {"D": 15, "W": 4, "M": 2}` · `_WINDOW_SLEEP_SECS >= 0.2` · `_FETCH_CONCURRENCY == 1` · `_CACHE_TTL_SECS == 600` · `_PARTIAL_CACHE_TTL_SECS == 60` |
| G5 | `condition.DAILY_PRICE_URL in base._QUOTE_ALLOWED_PATHS`(화이트리스트 무변경으로 충분함을 못박는다) |
| G6 | 세 신규 파일 basename 이 서로 다르다(덮어쓰기 사고 경로 차단) |

### 3.2 프론트엔드 (vitest + RTL + MSW)

| 파일 | ID | 검증 |
|---|---|---|
| `utils/__tests__/stockChart.cycle387.test.ts` | U1 | `isChartableTicker`: `005930` 참 · `0080G0`·`Q12345`·`''`·`'-'`·`null` 거짓 |
| | U2 | `isInteractiveTarget`: button·a·input·select·textarea·label 과 그 자손(`<button><span/></button>` 의 span) 참, 일반 td 거짓 |
| | U3 | `toKLineData`(TZ=UTC, 동적 import — kst.test 방식): 오름차순 · `timestamp === Date.UTC(2026,8,24,15)` for `2026-09-25` · 문자열 숫자 변환 · 날짜·OHLC 불량 봉 제거 · `turnover = amount` |
| | U4 | `PERIOD_TO_KLINE` = day/week/month |
| `utils/__tests__/kst.test.ts`(추가) | K6~K8 | §2.5 세 함수(TZ=UTC 에서 KST 날짜 · 잘못된 입력) + `DELEGATING_FILES` 에 두 파일 추가(K4 가 날짜용 `Intl.DateTimeFormat`·`toLocale*String` 0건을 잰다) |
| `components/__tests__/StockChartModal.cycle387.test.tsx` — `vi.mock('klinecharts', …)`(`init` 이 가짜 chart 반환, `dispose`·`registerLocale` spy). jsdom 에는 canvas 가 없으므로 실제 라이브러리를 돌리지 않는다 | M1 | 열림 → 로딩 → `init(hostEl, { locale:'ko-KR', timezone:'Asia/Seoul', formatter, styles })` · `setSymbol({ticker, pricePrecision:0, volumePrecision:0})` · `createIndicator('VOL')` · 데이터 도착 뒤 `setPeriod({type:'day', span:1})` · **마지막으로 등록된 로더**의 `getBars({type:'init'})` 가 목 봉을 오름차순 KLineData 로 준다 · `forward`/`backward` 는 빈 목록 |
| | M2 | 주봉 클릭 → MSW 가 `period=W` 요청을 받는다 · `setPeriod({type:'week'})` · 로더가 주봉을 준다 · 일봉으로 되돌리면 **새 요청 0**(캐시) |
| | M3 | `success=false` → `stock-chart-error` 에 백엔드 message · 「다시 시도」 → 요청 1건 더 |
| | M4 | 빈 `bars` → `stock-chart-empty`, 캔버스 로더에 빈 목록 |
| | M5 | `complete=false` → `stock-chart-partial` 에 첫 봉 날짜·사유 · 부분 결과는 61초 뒤 되돌아오면 재요청(M5-c) · 완전 결과는 61초 뒤에도 재요청 0(M5-d) |
| | M6 | `last_bar_provisional=true` → `stock-chart-provisional` 에 마지막 봉 날짜(주봉이면 「이번 주」 문구) · false 면 요소 없음 |
| | M7 | 코드 `Q12345` → `stock-chart-unsupported`, 요청 0 |
| | M8 | ×·ESC·바깥 클릭 → `onClose` · 안쪽 클릭은 닫지 않음 · 닫힌 뒤 연 요소로 포커스 복귀 |
| | M9 | 언마운트 → `dispose(hostEl)` 1회 |
| | M10 | `styles.candle.bar.upColor === PROFIT_HEX` · `downColor === LOSS_HEX` · 거래량 `indicator.bars[0]` 도 같은 두 색 |
| | M11 | TZ=UTC 에서 `formatter.formatDate({timestamp: Date.UTC(2026,8,24,15), type:'tooltip'})` = `2026-09-25` · 월봉 x축 = `2026-09` |
| | M12 | 메타 줄 = 기간·봉 수(천 단위)·「수정주가 · KRX」 |
| | M13 | 422(axios 오류, `detail`) → `stock-chart-error` 에 detail 문구 |
| `components/__tests__/stockChartOpen.cycle387.test.tsx` | O1 | 잔고 행 더블클릭 → `stock-chart-modal` · 제목에 이름(코드) · 요청 ticker 일치 |
| | O2 | 잔고 「매도」 버튼 더블클릭 → 차트 모달 **없음**(매도 확인창 동작은 기존 그대로) |
| | O3 | 주문체결내역 행 더블클릭 → 모달 · 그 행의 `ticker`·`ticker_name` |
| | O4 | 체결 「AI 자문」 버튼 더블클릭 → 차트 모달 없음 |
| | O5 | 매매손익 행 더블클릭 → 모달 · 그 행의 `ticker`·`ticker_name` |
| | O6 | 코드가 `-`/비정상인 행 → `stock-chart-unsupported`, 요청 0 |
| | O7 | 한 번 클릭 → 모달 없음 |
| `components/__tests__/LazyStockChartModal.cycle387.test.tsx` | C1 | 차트 청크 동적 import 실패 → `stock-chart-chunk-error`(새로고침 안내) + 닫기(`aria-label` 닫기) · 모달을 연 그리드는 남는다 · 닫으면 안내가 사라지고 그리드는 그대로 |
| 기존 가드 확장 | A1 | `components/__tests__/_ast_useQuery_retry_required.test.ts` `TARGET_FILES` 에 `'StockChartModal.tsx'` |
| | A2 | `components/__tests__/_ast_api_mocks_coverage.test.ts` 에 `/api/stock-chart/candles` 등록 확인 블록 |

**목 동기화**
- `frontend/src/test/handlers.ts` — `http.get(`${base}/stock-chart/candles`, …)` 기본 = 요청의 `period` 에 맞는 픽스처(`test/fixtures/stockChart.fixture.ts`, D·W·M 각 5봉 정도). 🅵 픽스처 만드는 법: Green 에서 R1 과 같은 독립 앱 + S26 의 문자열 KIS 목으로 라우트를 실제로 태워 나온 JSON 을 **그대로 리터럴로** 옮긴다(생성기로 합성하지 않는다). 배포 뒤 실제 응답 1건으로 교체는 §10.
- `e2e/fixtures/api-mocks.ts` — `page.route("**/api/stock-chart/candles*", …)` + `isRealApiCall`(`:182`) 경로 가드 + `resourceType()==='script'` 통과(규약 4). 응답은 `e2e/fixtures/stock-chart.fixture.ts` 의 같은 리터럴. `MockOptions` 에 `stockChart?: Partial<Record<'D'|'W'|'M', AnyJson>>` 덮어쓰기.

### 3.3 E2E (`e2e/history.spec.ts`)

| ID | 검증 |
|---|---|
| F32 | 주문체결내역 행 더블클릭 → `stock-chart-modal` 보임 · 모달 안 `canvas` 보임 · 메타 줄 · 「주봉」 클릭 → `period=W` 요청 관측(`page.waitForRequest`) · ESC 로 닫힘 · 화면에 `NaN` 없음 |
| F33 | 매매손익 탭 행 더블클릭 → 모달 · 제목에 그 행 종목 |

잔고 표는 대시보드라 vitest O1·O2 가 맡는다.

---

## 4. Green 절차 (순서)

1. backend-dev(한 명, 순서대로): `src/models/candle_chart.py` → `src/api/period_chart.py` → `src/routes/stock_chart.py` → `src/main.py` 2줄. 재핀(§1.6).
2. frontend-dev(한 명, 순서대로): `npm install klinecharts@10.0.3 --save-exact` → types → api → utils(`kst.ts`·`stockChart.ts`) → `StockChartModal.tsx` → `useStockChartOpener.tsx` → 세 그리드 → 목·픽스처.
   - 두 개발자를 동시에 띄우면 쓰는 파일이 겹치지 않아도 **착수 전 `git add -A`**(루트 CLAUDE.md 「병렬 작업」).
3. 인덱스: `python tools/test_impact/build_index.py` · `node tools/test_impact/build_index_frontend.mjs`. `tools/test_impact/manual_overrides.yaml` 에 추가 — 동적 import(`lazy`)와 소스 텍스트를 읽는 가드는 정적 분석이 못 잡는다:
   - `"frontend/src/components/StockChartModal.tsx"` → 세 그리드 테스트 + `stockChartOpen.cycle387.test.tsx`
   - `"src/api/period_chart.py"`·`"src/routes/stock_chart.py"`·`"src/main.py"` → `tests/unit/ast/test_cycle387_ast_stock_chart_scope.py` + `tests/unit/routes/test_cycle387_stock_chart_route.py`
4. 검증: `python -m pytest -q`(전체) · `cd frontend && npm test` · `npx tsc -b` · `npm run lint` · `npm run build`(분리 청크 생성 확인) · e2e F32·F33. **고친 뒤 전체 스위트 재실행**(주석 한 줄도 핀을 깬다).
5. 커밋·푸시는 하지 않는다(메인 세션이 정책대로 결정).

---

## 5. 문서 동기화 후보 (Phase 4.8 · `/sync-docs` · report-writer)

- `src/api/CLAUDE.md` — `period_chart.py` 절(TR·파라미터·커서·멈춤 조건·상한·캐시·잠정 판정·보조 계정 폴백)
- `src/routes/CLAUDE.md` — 엔드포인트 표에 `GET /api/stock-chart/candles` 1행
- `frontend/CLAUDE.md` — 「핵심 라이브러리」에 KLineChart(`10.0.3` 고정) · 새 절 「종목 차트 모달」(열기 규칙·상태·KST·색·lazy) · `BalanceTable`/`History` 절에 더블클릭 한 줄
- 루트 `CLAUDE.md` 「디렉토리 역할」 `src/api/` 한 줄(차트 조회 추가) — 필요 시
- `docs/HARNESS_CHANGELOG.md` cycle387 항목

---

## 6. 현 코드·문서와의 정합성

- 루트 규약 「KIS 호출은 `kis_get_quote` 경유」 ✔ · 「TR_ID 는 `get_tr_id`」의 FH 예외는 `finance.py` 가 이미 문서화 ✔ · 「API 응답 래퍼」 ✔ · 「KST 강제」(백엔드 `now_kst_iso`, 프론트 `utils/kst.ts`) ✔ · 「목은 실제 응답」 ✔(§3.2) · 「`useQuery` retry 명시」 ✔ · 「새 hex 금지」 ✔.
- `stock_master_daily`·`daily_bar_finalize`·20:30 적재와 **데이터를 공유하지 않는다**(차트 전용 메모리 캐시). 매매 코드는 이 모듈을 읽지 않는다.
- 같은 TR 을 20:30 적재·07:45 확정도 쓰므로 그 시각의 차트 조회는 전역 초당 제한을 나눠 쓴다 — 간격 0.25초가 차트 몫을 초당 4건 이하로 묶는다.

## 7. 반례 · 한계

1. KIS 가 구간에 더 있는데도 100봉 미만을 주면 멈춤 #4 가 조용히 자른다 — 정본(「최대 100건」)과 기존 코드가 기대는 성질이라 받아들이고, 배포 뒤 실측(§8)으로 확인한다.
2. 주봉·월봉 날짜 규약 미확인 — 버킷 처리로 어느 쪽이든 맞게 짰다(S6·S7).
3. 잠정 판정의 06:00 경계는 KIS 야간 처리가 늦는 날 몇 분 틀릴 수 있다(cycle386 반례 1 과 같은 성질) — 표시 문구일 뿐 값은 KIS 그대로다.
4. 수정주가라 분할 전 봉과 체결 내역의 실제 체결가가 다를 수 있다 — 메타 줄 「수정주가」 표기로 알린다.
5. 보조 시세 계정이 없으면 메인 토큰으로 조회한다(§1.4).
6. 한 번에 한 조회만 돈다 — 여러 종목을 연달아 열면 뒤 것은 최대 20초 기다리고, 넘으면 「진행 중」 안내가 뜬다.

## 8. 배포 메모 (이번 실행 밖)

- 모드 = **full**(`src/` + `frontend/` → backend·frontend 재생성). 창 = **21:35~익일 07:45** 또는 주말. 20:00~21:35 push 금지. 보유 중 09:00~15:30 push 금지(D6).
- 배포 전 EC2 메모리·디스크 점검(동시 빌드 OOM 이력).
- 배포 뒤 확인(읽기 전용): 보유 종목 하나를 열어 `[stock_chart_fetch]` 한 줄 — 005930 기준 예상 D `calls≈13 bars≈1,2xx` · W `calls=3 bars≈26x` · M `calls=1 bars≈61`. 확정된 날의 일봉 종가를 `stock_master_daily` 같은 날짜 종가와 대조(같은 TR·`J`·수정주가라 같아야 한다). 연속 더블클릭 시 두 번째부터 `cached=true`.

## 9. 인용 (file:line)

| 무엇 | 자리 |
|---|---|
| 잔고 행 렌더 · `<tr>` · 매도 버튼 · 확인창 · 코드 필터 | `frontend/src/components/BalanceTable.tsx:257-341` · `:262` · `:326-337` · `:348-360` · `:184` |
| 체결 행 렌더 · `<tr>` · 코드/이름 열 · AI 버튼 · 모달 자리 | `frontend/src/components/TradeHistoryGrid.tsx:385-393` · `:386` · `:148-155` · `:279-292` · `:421-427` |
| 손익 행 렌더 · `<tr>` · 코드/이름 열 · AI 버튼 · 모달 자리 | `frontend/src/components/TradePnLGrid.tsx:369-383` · `:372-375` · `:81-88` · `:208-223` · `:411-417` |
| 탭 전환 | `frontend/src/pages/History.tsx:37` |
| axios 인스턴스(timeout 10s) | `frontend/src/api/client.ts:3-19`(`:5`) |
| 응답 풀기 · params · try/catch 금지 · 요청별 timeout | `frontend/src/api/history.ts:12-24` · `api/llm-evaluations.ts:66-76` · `:10-13` · `api/macro.ts:33` |
| 모달 셸 관용구 | `frontend/src/components/LlmEvaluationModal.tsx:195-258` |
| KST 유틸 · 손익 색 상수 | `frontend/src/utils/kst.ts:35-80` · `frontend/src/utils/pnlColor.ts:7-9` |
| 시세 풀 화이트리스트 · 전역 초당 제한 · `kis_get_quote` · 메인 폴백 | `src/api/base.py:78-80` · `:437-451` · `:656-676` · `:693-772`(`:767`) |
| TR URL 상수 · 6자리 가드 형제 · single-flight 선례 · 예외 회수 · 윈도 stride 함정 | `src/api/condition.py:198` · `:729-763` · `:645-686` · `:83` · `:708-725` |
| FH TR_ID 하드코딩 규약 | `src/api/finance.py:13-15` |
| KIS 정본 파라미터 · 다음조회 불가 · `mod_yn` · 응답 예시 | `docs/kis/domestic-stock-quote.md:5460-5465` · `:5448` · `:5524` · `:5582-5596` |
| 잠정 봉 사실(cycle386) | `src/engine/CLAUDE.md:198` |
| raw path 메트릭 | `src/main.py:59-69` |
| 라우터 등록 블록 | `src/main.py:31-52` · `:347-366` |
| 라우트 테스트 독립 앱 · main 등록 AST 선례 | `tests/unit/routes/test_cycle266_daily_route_serialization.py:60-66` · `tests/unit/routes/test_cycle276_llm_evaluations_route.py:458-473` |
| 소스 트리 핀 | `tests/unit/ast/test_cycle287_ast_scope.py:243`(`_SRC_TREE_FILES`) · `:638-640`(`_SRC_TREE_DIGEST`) |

## 10. 후속 (한 줄씩 — 이번 범위 밖)

- 행 키보드 열기(포커스 + Enter)
- 폰에서 두 번 탭으로 열기(터치 브라우저는 dblclick 을 보장하지 않는다)
- 보조 시세 계정이 없을 때 차트 조회의 메인 토큰 폴백 금지 옵션(`base.py` 변경 필요)
- 목 리터럴을 배포 뒤 실제 응답 1건으로 교체
- 대시보드 잔고 표 더블클릭 E2E 시나리오

---

## 11. Red 기록 (tdd-engineer, 2026-09-28 17:4x KST)

### 11.1 만든 파일 (테스트·목만 — `src/`·`frontend/src` 비테스트 무접촉)

| 파일 | 내용 |
|---|---|
| `tests/unit/api/test_cycle387_period_chart_fetch.py` | S1~S26(파라미터화 포함 60) — 합성 달력 KIS 가짜 · `_monotonic`/`asyncio.sleep` 주입 · S26 은 **실제 `kis_get_quote`** 를 respx 로 태운다 |
| `tests/unit/routes/test_cycle387_stock_chart_route.py` | R1~R10(24) — 독립 앱 · R9 `src/main.py` AST + 앱 경로 표 · R10 `real_api_auth` |
| `tests/unit/ast/test_cycle387_ast_stock_chart_scope.py` | G1~G7(8) — G5 는 현행으로 이미 초록(무변경 확인 가드) · G7 = 명세 §6 「매매 코드는 이 모듈을 읽지 않는다」 |
| `frontend/src/utils/__tests__/stockChart.cycle387.test.ts` | U1~U4 |
| `frontend/src/utils/__tests__/kst.test.ts`(수정) | `DELEGATING_FILES` += 두 파일 · K6~K8 · **K9 `KST_TIME_ZONE`** |
| `frontend/src/components/__tests__/StockChartModal.cycle387.test.tsx` | M1~M13(24) |
| `frontend/src/components/__tests__/stockChartOpen.cycle387.test.tsx` | O1~O7(8) — 세 그리드 |
| `_ast_useQuery_retry_required.test.ts` · `_ast_api_mocks_coverage.test.ts`(수정) | A1 · A2(`G-AST13`) |
| `frontend/src/test/fakeKlinecharts.ts` | `klinecharts` 가짜(init·dispose·registerLocale + 기록 Proxy 차트 + `collectBars`) |
| `frontend/src/test/fixtures/stockChart.fixture.ts` · `handlers.ts`(수정) | MSW 기본 응답 — §3.2 🅵 대로 **참조 라우트를 실제로 태운 JSON 리터럴**(생성 스크립트 `scratchpad/c387_gen_fixture.py`) |
| `e2e/fixtures/stock-chart.fixture.ts` · `e2e/fixtures/api-mocks.ts`(수정) · `e2e/history.spec.ts`(F32·F33 추가) | Playwright 목 + `MockOptions.stockChart` |

### 11.2 Red 확인

- 백엔드: `92 중 91 FAIL/ERROR`(G5 만 초록) — 전부 `ModuleNotFoundError: src.api.period_chart / src.models.candle_chart` 또는 `… 부재 (cycle387 Red)`.
- 프론트: 새 6파일 FAIL(모달·utils 파일은 import 해석 실패, O1~O7 은 행 testid 부재로 타임아웃, K4/K6~K9, A1·A2). **기존 97파일 초록 유지.**
- 부수 Red(Green 이 풀 것): `tests/unit/deploy/test_cycle318_impact_index_freshness.py` 2건 — 새 테스트가 `src.main` 을 import 해 인덱스가 낡는다(인덱스 재생성으로 해소).

### 11.3 명세가 열어 둔 곳을 테스트가 이렇게 정했다 (Green 이 따를 계약)

1. **라우트는 서비스를 모듈 참조로 부른다** — `from src.api import period_chart` 후 `period_chart.fetch_candle_chart(...)`. 테스트가 `src.api.period_chart.fetch_candle_chart` 를 갈아끼운다(`from … import fetch_candle_chart` 로 묶으면 R1~R7 이 실제 KIS 경로를 탄다).
2. `router = APIRouter(prefix="/api/stock-chart")` · `main.py` 는 `app.include_router(stock_chart.router)`(추가 prefix 없음). R9 가 prefix 와 앱 경로 표 둘 다 본다.
3. `ChartBusyError(Exception)` 는 메시지 하나로 생성 가능해야 한다(`ChartBusyError("busy")`). **`[stock_chart_busy]` WARNING 은 `period_chart` 가 남긴다**(대기 시간 `waited_s` 를 아는 곳 — S22).
4. `_is_provisional(last_date: datetime.date, period, now_kst: datetime) -> bool` — 첫 인자는 `date` 객체.
5. `_monotonic`·`_QUEUE_WAIT_SECS`·`_MAX_CALLS_PER_FETCH` 는 **호출 시점에 모듈 전역으로 읽는다**(기본 인자·클로저에 묶지 않는다 — 테스트가 갈아끼운다). `asyncio.sleep` 은 `asyncio.sleep(...)` 로 부른다.
6. 캐시 적중은 **LRU 순서를 갱신**한다(S19 — 1번 키를 다시 쓴 뒤 33번째가 들어오면 2번 키가 나간다).
7. 성공 message 의 부분 꼬리 = `"{라벨} {N:,}개 — 일부 구간만(…)"` 에서 테스트는 `startswith("일봉 200개")` + `"일부 구간만" in` 만 본다(괄호 안 표기는 자유).
8. 프론트 모달 = 기본 export `StockChartModal({ ticker, name?, onClose })`. 루트 testid `stock-chart-modal` 은 **오버레이**(LlmEvaluationModal 관용구 — 패널에 두면 테스트가 부모를 오버레이로 본다). `stock-chart-canvas-host` 는 로딩 중에도 DOM 에 있다(`init` 이 마운트 effect 에서 돈다).
9. 🔴 **`kst.ts` 가 `KST_TIME_ZONE = 'Asia/Seoul'` 을 export 하고 모달은 그것을 `init({ timezone })` 에 쓴다** — 명세 §2.5 가 모달을 `DELEGATING_FILES` 에 넣었는데 K4-c 는 그 파일의 `'Asia/Seoul'` 리터럴을 금지한다. 둘을 함께 만족하는 유일한 길이라 K9 로 못박았다.
10. 모달이 `klinecharts` 에서 가져오는 값은 `init`·`dispose`·`registerLocale` 셋(타입은 `import type`). 가짜 모듈이 그 셋만 준다 — 다른 값을 import 하면 `undefined` 다.
11. 부분 안내(`stock-chart-partial`)에는 `incomplete_reason` **원값**(예: `window_error`)이 들어간다(한글 풀이 병기는 자유). 잠정 안내는 D=마지막 봉 날짜 · W=「이번 주」 · M=「이번 달」.
12. 422 오류 문구 = FastAPI `detail`(문자열이면 그대로, 배열이면 각 `msg`).
13. 행 이름이 비면 제목은 응답 `name` 을 쓴다(M1-c). 비정상 코드도 모달은 연다 → `stock-chart-unsupported`(받은 값 표시) · 요청 0.

### 11.4 통과 가능성 증명 (scratch 참조 구현 — 리포에 넣지 않았다)

- 참조 구현 = `scratchpad/c387ref`(rsync 사본) · `scratchpad/c387git`(`git clone --local`, 메인 작업트리 무접촉) — `src/api/period_chart.py`·`src/models/candle_chart.py`·`src/routes/stock_chart.py`·`main.py` 2줄 + 프론트 types·api·utils·모달·훅·세 그리드.
- 백엔드: 새 92/92 초록. **돌연변이 26종 전부 사망**(세마포어 제거·W 커서 −1일·뒤 창 값 덮어쓰기·sleep 제거·부분 600초 캐시·LRU 미갱신·06:00 경계 제거·주말 포함·UN 시장·원주가·<100 멈춤 제거·0가 미제거·미래 미제거·상한/예산/진전 제거·첫 창 예외 삼킴·shield 제거·single-flight 제거·검증 제거·윤일 오류·라우트 직접 import·예외 문자열 노출·float 봉·name 미strip).
- git 클론 전체 가드: 실패는 `test_cycle287_ast_scope.py::test_s1b`(166 ≠ 163 — 명세 §1.6 재핀 대상) 하나. `_PINNED_DIR_FILE_COUNTS`(s1d) 초록.
- 프론트: 전체 103파일/1,022 초록 · `tsc -b` 0 · 새 테스트 eslint 0. **돌연변이 25종 전부 사망**(버튼 가드·색 반전·로컬 날짜·월봉 축·retry·queryKey·staleTime·dispose·비정상 코드 요청·정렬·로더 forward·tz 리터럴·422 detail·setPeriod·잠정 문구·ESC·포커스 복귀·오버레이 닫기·ticker/name 뒤바뀜·영숫자 허용·손익 행 핸들러·YYYY-MM 로컬·사유 누락·천 단위).
- E2E: 참조 dev server(:3387) + 실제 `klinecharts@10.0.3`(Chromium)로 `history.spec.ts` 5/5 초록(F32 캔버스·주봉 요청·ESC, F33 손익 행).

### 11.5 Green 에게 남은 것 (명세 §4 그대로)

`npm install klinecharts@10.0.3 --save-exact` · 재핀(`_SRC_TREE_FILES` 163→166 + `_SRC_TREE_DIGEST`, 사유 주석) · 인덱스 재생성(백엔드 → 프론트 순) · `manual_overrides.yaml`(명세 §4-3) · 전체 스위트 재실행.
