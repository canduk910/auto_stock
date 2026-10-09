# cycle416 「매크로 화면 시장 등락 통계」 — 인터페이스 계약 (Red → Green)

작성: tdd-engineer (2026-10-09 KST) · 브랜치 `feat/market-breadth` · 기준 `main 3d6f7b52`
명세 정본: [`breadth_spec.md`](breadth_spec.md) — 이 문서는 명세를 **테스트가 실제로 잡는 이름·모양**으로 옮긴 것이다. 숫자·규칙의 근거는 명세에 있고 여기서 되풀이하지 않는다.

Red 상태: 아래 테스트 파일 전부 「모듈 없음」 으로 실패한다. 스크래치 참조 구현(커밋 안 함)으로 **백엔드 129건(leaf 92 + 라우트 37 — `main.py` 등록·소스 읽기 3건 R4b·R5·R6 은 실제 파일이 있어야 해서 제외) · 구조 가드 5건 · 프론트 50건(FG 가드 7건 제외)이 통과 가능함**을 확인했고, 라우트 돌연변이 8종(재시도 제거 · 중복 합치기 제거 · shield 제거 · 빈 응답 영구 캐시 · 세마포어 16 · 실패 캐시 · 예외 본문 로그 · 오늘 포함)을 전부 잡는다.

---

## 0. 테스트 파일

| 쪽 | 파일 | 건수 | 담당 Green |
|---|---|---|---|
| 백엔드 | `tests/unit/engine/test_cycle416_market_breadth_leaf.py` (L1~L8) | 92 | backend-dev |
| 백엔드 | `tests/unit/routes/test_cycle416_market_breadth_route.py` (R1~R6 · W1~W18) | 40 | backend-dev |
| 백엔드 | `tests/unit/ast/test_cycle416_ast_market_breadth.py` (G-416-1~6) | 6 (G-416-6 은 지금도 초록 — krx.py 무변경 핀) | backend-dev |
| 프론트 | `frontend/src/macro/__tests__/MarketBreadthSection.test.tsx` (S1~S14) | 16 | frontend-dev |
| 프론트 | `frontend/src/macro/__tests__/marketBreadthChart.test.ts` (C1~C5) | 5 | frontend-dev |
| 프론트 | `frontend/src/api/__tests__/market-breadth.test.ts` (A1~A4) | 6 | frontend-dev |
| 프론트 | `frontend/src/macro/__tests__/MacroPage.test.tsx` — `mockAll` 에 `/api/market/breadth` 핸들러 + 새 describe 4건 | 4 | frontend-dev |
| 프론트 | `frontend/src/macro/__tests__/_ast_market_breadth_guards.test.ts` (FG1~FG5) | 7 | frontend-dev |
| 프론트 픽스처 | `frontend/src/test/fixtures/marketBreadth.fixture.ts` + `frontend/src/test/handlers.ts` 기본 핸들러 1줄 | — | (Red 가 씀) |

---

## 1. leaf — `src/engine/market_breadth.py`

순수 함수. `await`·`async def`·입출력·`asyncio`·`logging`·`time` import 0, 표준 라이브러리만(`enum` 허용), **벽시계 호출 0**(`.now()`·`.today()`·`.utcnow()`·`.monotonic()` — 오늘·지금은 인자로 받는다). G-416-1 이 잰다.

| 이름 | 계약 |
|---|---|
| 상수 | `KRX_TICK_TABLE_20230125`(모양 자유) · `PRICE_LIMIT_PCT=30` · `ADR_REFERENCE={"oversold":75,"overheated":120}` · `DEFAULT_DAYS=20` · `MIN_DAYS=1` · `MAX_DAYS=60` · `MIN_LOOKBACK_CALENDAR_DAYS=40` · `PUBLISH_PENDING_CUTOFF=time(10,0)` |
| `tick_size(price:int)->int` | 명세 §3.3 표 |
| `price_limits(base:int)->tuple[int,int]` | `(upper, lower)` — 정의 (가′) |
| `parse_krx_int(v)->int\|None` | `None`·`""`·`"-"`·공백 → None · 쉼표 제거 · `"+1,200"`→1200 · 정수가 아니거나 읽을 수 없으면(`"12.5"`·`"abc"`) None |
| `classify_row(row:dict)->RowClass` | 속성 `kind`(`"unparsed"\|"no_trade"\|"up"\|"down"\|"flat"`) · `limit_up` · `limit_down` · `out_of_band` · `sign_mismatch`(전부 bool) |
| `aggregate_rows(rows)->DayStats` | 속성 `rows` · `traded` · `up` · `down` · `flat` · `limit_up` · `limit_down` · `no_trade` · `out_of_band` · `unparsed` · `up_ratio`(`round(up/traded,4)`, traded 0 → None) · `sign_mismatch`(정수) |
| `merge_stats(a,b)->DayStats` | 정수 키 합 · `up_ratio` 재계산 |
| `summarize(list[DayStats])->SummaryStats` | 속성 `n_days` · `up` · `down` · `flat` · `limit_up` · `limit_down` · `no_trade` · `up_ratio`(Σ, 4자리) · `adr`(`round(Σup/Σdown×100,1)`, Σdown 0 → None). 빈 목록 → n_days 0 · 둘 다 None |
| `stats_to_dict(DayStats\|SummaryStats)->dict` | DayStats → 11키(`sign_mismatch` 제외) · SummaryStats → 9키 |
| `lookback_calendar_days(days)->int` | `max(40, 2×days)` |
| `candidate_weekdays(today:date, days:int)->list[date]` | `today−1 … today−L` (**한도일 포함**) 중 평일, 최신 먼저. 오늘은 없다 |
| `next_weekday(d)->date` | d 다음 첫 평일(토·일 → 월) |
| `is_publish_pending(d, d1, now)->bool` | `d == d1 ∧ now < next_weekday(d1) 10:00 KST`. `now` 가 UTC 같은 다른 시간대로 와도 KST 로 바꿔 판정 |
| `DayStatus` | 멤버 `TRADING`·`EMPTY`·`MISSING`, `.value` 는 같은 이름 문자열(`str` Enum 권장) |
| `classify_day(kospi:DayStats\|None, kosdaq:DayStats\|None)->DayStatus` | None(호출 실패)이 하나라도 → MISSING · 둘 다 `rows>0` → TRADING · 둘 다 `rows==0` → EMPTY · 한쪽만 0 → MISSING |

### 1.1 명세에 없어 테스트가 정한 것 (tdd 해석 — 다르게 원하면 team-leader 확인)

- **고가·저가가 빈 값(`""`·None)인 거래 행**은 0 과 같이 본다 — 상·하한·밴드 판정을 건너뛰고 방향만 센다(`unparsed` 아님). 명세는 「0」 만 적었다.
- `FLUC_RT` 가 안 읽히면(`""`) `sign_mismatch=False`.

---

## 2. 라우트 — `src/routes/market_breadth.py`

### 2.1 공개 이름

```python
router = APIRouter(prefix="/api/market", tags=["market-breadth"])

@router.get("/breadth", response_model=ApiResponse)
async def get_breadth(days: int = Query(20, ge=1, le=60)) -> ApiResponse:
    return await compute_breadth(days)

async def compute_breadth(days: int) -> ApiResponse   # 라우트 본문 전체 — 테스트 seam
def reset_state() -> None                            # 캐시·진행 중 표·하루 카운터·예산 경고 래치·세마포어 비우기
```

`src/main.py`: `from src.routes import (…, market_breadth)` 1건 + `app.include_router(market_breadth.router)` 1건(추가 prefix 없음). R5 가 잰다.

### 2.2 모듈 상수 — 호출 시점에 모듈 전역을 읽는다

테스트가 `monkeypatch.setattr(mod, "_X", …)` 로 바꾼다. 함수 기본 인자·클로저로 미리 묶으면 테스트가 실패한다.

`_KRX_CONCURRENCY=4` · `_REQUEST_DEADLINE_SECS=45.0` · `_RETRY_DELAY_SECS=1.0`(리터럴 `1.0` — R4b 가 소스에서 읽는다) · `_EMPTY_TTL_SECS=600` · `_EMPTY_PERMANENT_AFTER_DAYS=7` · `_DAILY_CALL_BUDGET=1_000` · `_CACHE_MAX_ENTRIES=512`

### 2.3 시계

- **시한**(45초)은 이벤트 루프 시계로 잰다 — `asyncio.wait(timeout=…)` / `asyncio.timeout`. 테스트는 freezegun `real_asyncio=True` 라 벽시계를 얼려도 루프 시계는 흐른다.
- **빈 응답 캐시 수명**은 `time.monotonic()` 또는 `datetime.now(KST)` — freezegun `tick()` 이 움직이는 시계여야 W12 가 통과한다(`loop.time()` 금지).
- **하루 호출 카운터**의 날짜는 `datetime.now(KST).date()`(또는 `today_kst()`).
- 세마포어는 **실행 중 루프마다** 만든다(전역 하나를 import 때 만들면 TestClient 가 요청마다 새 루프를 써서 「다른 루프에 묶임」 오류가 난다). `reset_state()` 가 비운다.

### 2.4 seam (테스트가 갈아끼우는 자리)

| 무엇 | 라우트가 쓰는 꼴 | 테스트가 바꾸는 이름 |
|---|---|---|
| KRX 두 함수 | `from src.api import krx` → `krx.fetch_stk_bydd_trd(ymd)` · `krx.fetch_ksq_bydd_trd(ymd)` | `src.api.krx.fetch_*` |
| 설정 | `from src.db import system_config` → `await system_config.get_krx_open_api_config()` 요청당 1번 | `src.db.system_config.get_krx_open_api_config` |
| leaf | `from src.engine import market_breadth` (모듈 참조, 별칭 자유) → `market_breadth.aggregate_rows(...)` 등 | `src.engine.market_breadth.aggregate_rows`(W14c) |

`fetch_krx_open_api` 를 직접 부르지 않는다(테스트가 AssertionError 로 막아 둔다). `src/api/krx.py` 는 한 글자도 고치지 않는다(G-416-6 핀).

### 2.5 행위 — 테스트 ID 와 짝

| ID | 잡는 것 |
|---|---|
| R1·W1 | §2.3 예시 창(20칸, 09-08~10-08) · `empty_dates` 3개 최신 먼저 · `days[]` 최신 먼저 · 키 집합 정확 · 정수는 JSON int · 합계 up_ratio 재계산 · 요약 · `asof_kst` `+09:00` · 오늘·주말·한도 밖 조회 0 · **배치**(조회 날짜 ≤ 25개 = 22 + 3) · 같은 키 1회 |
| W2·W3·W4 | pending 정의(d1 · 다음 평일 10:00) — pending 은 `empty_dates` 에 넣지 않고 칸도 안 쓴다 |
| W5 | 실패 1회 재시도(정확히 2번 호출) · MISSING 이 칸을 쓴다 · `[market_breadth_fetch_error] market= date= err=KrxApiError` 1줄(예외 본문 없음) |
| W5b | 실패는 캐시하지 않는다 — 다음 조회에서 실패한 (시장, 날짜)만 다시 |
| W6 | 한 시장만 빈 날 = MISSING |
| W7·W8 | 한도 L 안에서만 조회 · 못 채우면 `complete=false` · days=60 → 06-11 까지 내려간다 |
| W9 | 시한 초과 → 끝난 날만 days · 남은 태스크는 **취소하지 않고**(내부 태스크는 `asyncio.shield` 로 감싼다) 끝까지 돌아 캐시를 채운다 |
| W10 | 동시 요청 둘 → (시장, 날짜) 호출 1번(진행 중 표 공유) |
| W11 | 가짜 KRX 안 최대 동시 실행 = 4 |
| W12 | ok 영구 · 최근 빈 날 600초 · 8일 이전 빈 날 영구 |
| W13·W13b | 꺼짐·키 없음·설정 예외 → 정해진 문장, KRX 호출 0, 설정 예외는 `[market_breadth_error] stage=… err=RuntimeError` |
| W14·W14b·W14c | 전부 실패 / 전부 빈 응답 / 집계 예외 → HTTP 200 + `success=false`, 500 없음, 예외 본문 미노출 |
| W15·W15b | 하루 상한(재시도 포함) · `[market_breadth_budget_exhausted]` **하루 1번**(같은 날 두 번째 요청에도 다시 안 찍는다) · KST 날짜가 바뀌면 카운터 초기화 · 상한 0 → 한도 문장 |
| W16·W16b | 0·61·-1·"abc"·"1.5" → 422(설정 읽기·KRX 호출 0) · 1·60 은 통과 |
| W17 | 키 표지 문자열이 응답·**모든 수준 로그**에 0 — 예외 메시지에 섞여 와도 로그는 클래스 이름만 |
| W18 | 부호 어긋남 → 분류 그대로 · `[market_breadth_sign_mismatch] market=kospi date=2026-10-08 n=1` WARNING 1줄 · 응답에 `sign_mismatch` 키 없음 |
| R2~R6 | GET 만 · prefix `/api/market`(`/api/macro` 밑 금지) · 상수 · main 등록 · 실제 인증(무키 401) |

### 2.6 메시지 (`ApiResponse.message`)

명세 §5.5 표 그대로. 테스트가 정한 해석 둘:

- 「최근 {n}영업일 ({from}~{to})」 의 **n = 창의 칸 수 = `n_days + len(missing_dates)`**. 빠진 날이 있으면 「최근 20영업일 (2026-09-11~2026-10-08) — 1일은 KRX 응답이 없어 비었습니다」(W5). 빠진 날이 없으면 n = n_days(W7 「최근 5영업일 (2026-08-31~2026-10-08)」).
- 칸이 있는데 전부 MISSING 일 때 그중 하나라도 사유가 「한도」 면 한도 문장, 아니면 「KRX 에서 자료를 받지 못했습니다 — 잠시 후 다시 시도하세요」.
- 그 밖의 예상 못 한 예외의 문장은 테스트가 고정하지 않는다(`success=false`·`data=null`·WARNING `[market_breadth_` 접두어만). 권장: 「시장 등락 통계를 만들지 못했습니다 — 서버 로그 [market_breadth_error] 확인」.

### 2.7 `empty_dates` 범위

칸 채우기 루프가 **멈추기 전까지 지나간** EMPTY 평일만 넣는다(pending 날 제외). 칸이 다 차서 멈추면 그보다 오래된 날은 넣지 않는다 — 다음 배치에서 이미 불렀더라도.

---

## 3. 구조 가드 (G-416-1~6)

| ID | 내용 |
|---|---|
| G-416-1 | leaf 순수성 — §1 첫 문단 |
| G-416-2 | 라우트 import 에 `src.api.base`·`src.api.order`·`src.auth`·`src.realtime`·8영역 엔진 모듈·`src.engine.scheduler`·`kis` 이름 0 · `from src.api import krx` 있음 · `from src.api.krx import fetch_*` 없음(`KrxApiError` 는 괜찮다) · `from src.engine import market_breadth` 있음 |
| G-416-3 | `krx.` 뒤 `fetch*` 이름 = 정확히 `{fetch_stk_bydd_trd, fetch_ksq_bydd_trd}` · 소스에 `fetch_krx_open_api`·`isu_base_info` 문자열 0 |
| G-416-4 | `logger.*` · `ApiResponse(...)` · `HTTPException(...)` · `*Error(...)` 인자에 `.key` 속성 0 |
| G-416-5 | leaf 를 import 하는 파일 = `src/routes/market_breadth.py` 하나 · 라우트를 import 하는 파일 = `src/main.py` 하나(`Path.rglob` + AST) |
| G-416-6 | `src/api/krx.py` 최상위 정의 6개 이름 집합 + 각 본문 `ast.get_source_segment` sha256 핀 |

8영역·`scheduler.py` **파일 무접촉**은 기존 `tests/unit/ast/test_cycle222a3_ast_followup_fixes.py`(8영역 diff 가드)가 잡는다. `scheduler.py` 는 그 가드 밖이라 tester 가 병합 전 `git diff --stat main -- src/engine/scheduler.py` 가 비었는지 확인한다(자기소멸 핀을 새로 두지 않았다 — 가드 금기 「커밋 직후 공허해지는 diff 가드」).

---

## 4. 프론트

### 4.1 파일·이름

| 파일 | 계약 |
|---|---|
| `frontend/src/types/market-breadth.ts` | `BreadthMarketKey='kospi'\|'kosdaq'\|'total'` · `BreadthDayStats`(11키) · `BreadthSummary`(9키, `adr: number\|null`, `up_ratio: number\|null`) · `BreadthDay`(`date`+3시장) · `MarketBreadthData`(명세 §5.4 9키, `window` 6키). 픽스처가 이 타입을 쓴다 |
| `frontend/src/api/market-breadth.ts` | `export const MARKET_BREADTH_TIMEOUT_MS = 60_000` · `export const getMarketBreadth = async (days = 20): Promise<MarketBreadthData>` — `apiClient.get('/market/breadth', { params: { days }, timeout: MARKET_BREADTH_TIMEOUT_MS })`. `success=false` → `Error(message)` · axios 오류(HTTP·네트워크) → `Error('시장 등락 통계를 불러오지 못했습니다')` |
| `frontend/src/macro/hooks/useMarketBreadth.ts` | `useAsyncState` 꼴 · `getMarketBreadth` 호출 · `{data, loading, error, load}`. `useMacro.ts` 는 건드리지 않는다(FG3) |
| `frontend/src/macro/marketBreadthChart.ts` | `buildBreadthChartRows(days, market)` — 오래된 것 → 최신, 입력 배열 제자리 변경 금지, 행 `{date,label,up,down(음수),flat,no_trade,limit_up,limit_down,up_ratio_pct(null 유지)}` · `breadthAxisMax(rows)` — M ≥ max, M < 2×max(데이터가 있을 때), 빈 창도 > 0 · `mmdd(d)` 문자열 자르기 · `formatUpRatio(r)` `'32.5%'`/`'—'` |
| `frontend/src/macro/components/MarketBreadthSection.tsx` | default export, props `{data, loading, error, days?=20}` |
| `frontend/src/macro/MacroPage.tsx` | 원자재 다음 6번째 · mount 때 `load()` · `useMarketBreadth` 사용 |
| `e2e/fixtures/api-mocks.ts` | `page.route("**/api/market/breadth*", …)` 등록(FG5 — G-AST12 와 같은 이유) |

### 4.2 섹션 DOM 계약

- 래퍼 `data-testid="macro-section-market-breadth"` 는 **로딩·실패·정상 모든 상태**에 있고 제목 「시장 등락 통계」를 단다(다른 5섹션과 다르다 — 첫 조회가 길어 무엇을 기다리는지 보여야 한다).
- 로딩 문장에 「최근 {days}영업일 전 종목 시세를 받는 중」 · 실패는 `ErrorAlert`(「오류:」 + 메시지).
- 머리줄: `{from}~{to}` · `{n_days}영업일` · `KRX` · `formatKstDateTime(asof_kst)`.
- 토글 `breadth-market-{kospi|kosdaq|total}` 버튼, 글자 코스피·코스닥·합계, `aria-pressed`, 기본 합계.
- 칩 `breadth-chip-adr`(「ADR 74.9」 / n_days<requested 면 「ADR(3일) …」 / null → 「—」, 숫자 없음, 판정 문구 없음) · `breadth-chip-up`(빨강 클래스) · `breadth-chip-down`(파랑 클래스) · `breadth-chip-limit-up`(「상한가 …」) · `breadth-chip-limit-down`(「하한가 …」) · `breadth-chip-up-ratio`(「… 40.8%」).
- 차트 래퍼 `breadth-chart`, `data-market` = 선택 시장.
- 각주 `breadth-footnote` — 기준선 숫자는 `adr_reference` 에서 읽는다.
- 표 `breadth-table`(클래스 `min-w-[560px]`, 조상에 `overflow-x-auto` 상자) · 머리줄은 `<thead>` 안 `<th>` 8개 「날짜·상승·하락·보합·상한가·하한가·거래 없음·상승 비율」 · 행 `breadth-row-{YYYY-MM-DD}` 최신 먼저 + 마지막 `breadth-row-total`(「{n_days}일 합계」) · 칸 `breadth-cell-{date|up|down|flat|limit_up|limit_down|no_trade|up_ratio}`, 숫자 `toLocaleString()`, 비율 `formatUpRatio`.
- 색 클래스: 상승·상한가 칸 = `text-red-NNN` 또는 `text-pnl-profit` · 하락·하한가 칸 = `text-blue-NNN` 또는 `text-pnl-loss`(반대 색 클래스 금지). 차트 색은 `var(--color-red-500)`·`var(--color-blue-500)`, hex 리터럴 0(FG2).
- 상태 줄: `breadth-missing`(「{k}일 자료를 받지 못했습니다: MM-DD, …」) · `breadth-short`(complete=false ∧ 빠진 날 없음, 「…{n_days}일뿐…」) · `breadth-pending`(「{MM-DD} 자료는 아직 KRX 에 올라오지 않았습니다…」) · 정상 상태엔 셋 다 없음 · `empty_dates` 는 표시 안 함.
- 섹션·차트 계산 파일에 `new Date(`·`new Intl.DateTimeFormat`·`getHours(`·`Asia/Seoul` 0(FG1).

### 4.3 픽스처

`frontend/src/test/fixtures/marketBreadth.fixture.ts` 는 Red 가 명세 §5.4 키로 손으로 쓴 3영업일 값이다(합계·비율·요약은 파이썬으로 검산). **Green 뒤 백엔드 라우트를 실제로 태워 나온 JSON 으로 바꿔 넣는다**(cycle266 「목은 실제 응답을 담는다」) — 그때 컴포넌트 테스트 숫자도 같이 바꾼다.

---

## 5. 돌리는 법

```bash
# 백엔드 (작업 디렉터리 /Users/koscom/Projects/auto_stock_c416)
python -m pytest -q tests/unit/engine/test_cycle416_market_breadth_leaf.py tests/unit/routes/test_cycle416_market_breadth_route.py tests/unit/ast/test_cycle416_ast_market_breadth.py
python -m pytest -q tests/unit/ast/test_cycle222a3_ast_followup_fixes.py    # 8영역 무접촉
# 프론트
cd frontend && npx vitest run src/macro src/api/__tests__/market-breadth.test.ts
```

caplog 단언은 전부 `levelno >= WARNING ∧ 접두어` 로 한정했다(W17 만 「없어야 한다」 라 모든 수준).

---

## 6. Red 실행 결과 (2026-10-09 KST, 기준 `main 3d6f7b52`)

| 범위 | 결과 |
|---|---|
| 백엔드 전체 `python -m pytest -q` | 16,245 통과 · 102 실패 · 40 오류. cycle416 밖 실패 6건 = ① 영향 인덱스 3건(`test_cycle316`·`318`·`320` — 이 워크트리에 루트 `node_modules` 가 없어 `build_index_frontend.mjs` 가 `js-yaml` 을 못 찾는다. 메인 저장소 `node_modules` 를 잠시 이어 붙이면 13/13 통과, 링크는 지움) ② 인덱스 신선도 1건(재생성으로 해소) ③ `tests/unit/replay/test_ra_us*.py` 2건(로컬 보관소 parquet 읽기 오류 `Repetition level histogram size mismatch` — 손대지 않은 메인 체크아웃에서도 같은 실패, CI 는 파일이 없어 건너뛴다) |
| 백엔드 cycle416 | 136건 전부 Red(모듈 없음) — G-416-6(krx.py 핀) 만 초록 |
| 프론트 전체 `npx vitest run` | 1,138 통과 · 11 실패 + 3파일 import 실패 — 전부 cycle416 새 테스트. 기존 `MacroPage.test.tsx` 19건은 초록 유지(핸들러를 먼저 넣어 두었다) |
| 영향 인덱스 | `build_index.py` · `build_index_frontend.mjs` 재생성 → `_workspace/test_index.yaml` |
| eslint(새·바뀐 프론트 파일) | 0 |
