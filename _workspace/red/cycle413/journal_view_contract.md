# cycle413 거래일지 화면(1b) — 인터페이스 계약 (Red 가 정한 이름·모양, 구현은 따른다)

정본 명세 = `_workspace/red/cycle413/journal_view_spec.md`(domain-expert). 이 문서는 명세를 **테스트가 부르는 이름**으로 옮긴 것이다.
이 문서·명세와 테스트가 갈리면 **테스트가 정본**이다. 바꿔야 하면 tdd-engineer 와 합의하고 테스트를 함께 고친다.

응답 키 정본 = `tests/fixtures/cycle413_journal_shape.json` — 백엔드 라우트 테스트와 프론트 MSW 정직성 테스트가 **같은 파일**로 키 집합을 비교한다(객체마다 키 집합이 정확히 같아야 한다 — 더하지도 빼지도 않는다).

---

## 0. 금기 (테스트로 고정 — `tests/unit/ast/test_cycle413_scope_guard.py`)

| 금기 | 가드 |
|---|---|
| 8영역·`scheduler.py` 0줄 | 내용 sha(기준 main `8c28e9a6`) — **사이클 한정, 병합 후 삭제** |
| `journal_worker/` 0줄 | 디렉터리 전체 (경로, 내용 sha) digest — 사이클 한정 |
| 마이그레이션 0 (001~047 무수정 · 048 없음) | 파일 수 47 + (이름, sha) digest |
| `journal_view.py` 순수 — `async def`·`await` 0, `src.db`·`src.api`·`src.realtime`·`src.auth`·`scheduler`·8영역·`asyncpg`·`httpx` import 0 | AST |
| KIS 호출 0 — `journal_view.py`·`src/db/trade_journal.py`·`src/routes/history.py` 가 `src.api`·`src.auth` 를 import 하지 않는다 | AST |
| `stock_master_daily` 새 읽기 함수 2개는 SELECT 만 · `trade_journal.py` 의 쓰기 SQL 은 `trade_journal_notes` 만 | AST(문자열 상수) |

Green 이 함께 옮길 기존 가드(새 `src` 파일 2개 — `src/engine/journal_view.py`·`src/db/trade_journal.py`):
- `tests/unit/ast/test_cycle287_ast_scope.py` — `_SRC_TREE_FILES` 179→181 · `_PINNED_DIR_FILE_COUNTS["src/engine"]` +1 · `_SRC_TREE_DIGEST` 재핀(주석에 cycle413 한 줄)
- `tests/unit/ast/test_cycle290_ast_scope.py` — `_ENGINE_PY_FILES["src/engine"]` 에 `journal_view.py` 등재
- `tests/unit/ast/test_cycle291_ast_scope.py` — `src/engine/*.py` 83→84
- `tests/unit/ast/test_cycle412_scope_guard.py` — 머리말 규약(「cycle412 병합 후 삭제」, 병합 = `bd07e291`)대로 **삭제**. 8영역 sha 는 cycle413 가드가 이어 받는다.

---

## 1. 순수 조립 leaf — `src/engine/journal_view.py`

```python
def build_card(
    pair: dict, *,
    fills: list[dict],
    orders: list[dict] | None,        # None = 일지 표 조회 실패
    stops: list[dict] | None,         # None = 조회 실패
    note: dict | None,                # 메모 없음 = None
    closes: list[dict] | None,        # None = 종가 조회 실패
    business_days: list[date] | None, # None = 조회 실패
    llm_evals: list[dict] | None,     # None/[] = 보강 없음
    costs: dict | None,               # None = 비용 조회 실패
    record_start: dict,               # 응답 record_start 와 같은 dict
    now: datetime,                    # aware KST
) -> dict                             # JournalCard (명세 1-2 · shape.json "card")
```

입력 모양 (DB 함수가 돌려주는 그대로 — 테스트 픽스처도 이 모양):
- `pair` = `get_trade_pairs()` 한 행 + `cost_overlay.overlay_pairs()` 가 채운 칸(`fee`·`tax`·`net_profit_loss`·`net_profit_rate`·`cost_status`·`allocated`·`slippage_won`, 보유 중 `partial_fee`·`partial_tax`). 비용 조회 실패면 그 칸들이 **없다**.
- `fills` = `trade_history` 행: `id`(UUID 문자열) · `order_no`(없으면 `''`/None) · `trade_type` · `timestamp`(KST ISO `…+09:00`) · `price` · `quantity` · `order_price`(None 가능) · `profit_loss`(**NULL 은 None 그대로**). 순서 무관(leaf 가 시각순 정렬).
- `orders` = `trade_journal_orders` 행 전 칸: `order_date`(`date`) · `noted_at`(KST ISO 문자열) · `signal`/`params`(dict). 체결과는 `(체결 KST 날짜, order_no, side)` 로 잇는다.
- `stops` = `trade_journal_stops` 행 전 칸: `observed_at`(KST ISO 문자열) · `buy_date`(`date`|None) · `inputs`(dict). **leaf 가** 명세 4-1 창·`pos_order_no` 로 거른다(라우트는 (전략, 종목) 상위 집합을 넘겨도 된다).
- `closes` = `stock_master_daily` 행: `ticker` · `bas_dd`(`date`) · `close_price`(int) · `updated_at`(KST ISO 문자열) · `flng_cls_code` · `prtt_rate`.
- `llm_evals` = `llm_buy_evaluations.list_by_order_nos()` 행: `trade_date`(`date`) · `ticker` · `order_no` · `strategy_id` · `target_won` · `k` · `strategy_board` · `signal_price_won`.
- `costs` = `{trade_id: {"fee", "tax", "cost_status", "allocated"}}` — `cost_overlay.trade_costs()` 와 같은 모양(체결 행 단위).

---

## 2. DB 읽기·쓰기 (라우트가 **모듈 속성 경유**로 부른다 — 테스트가 그 속성을 갈아 끼운다)

새 모듈 `src/db/trade_journal.py`:
```python
async def list_orders(order_nos: list[str], *, date_from: date, date_to: date) -> list[dict]
async def list_stops(keys: list[tuple[str, str]], *, since: datetime, until: datetime) -> list[dict]
        # keys = [(strategy, ticker)], observed_at ∈ [since, until]
async def list_notes(anchor_ids: list[str]) -> list[dict]          # anchor_trade_id(str)·body·created_at·updated_at(KST ISO)
async def get_record_start() -> dict                              # {orders_restored, orders_live, stops, order_price} 'YYYY-MM-DD'|None
async def upsert_note(anchor_trade_id: str, body: str, *, strategy: str, ticker: str, buy_date: date) -> dict
        # ON CONFLICT (anchor_trade_id) DO UPDATE SET body, updated_at=now() → {anchor_trade_id, body, created_at, updated_at}
async def delete_note(anchor_trade_id: str) -> bool
```
- 빈 목록 인자 = **쿼리 없이** `[]`.
- 예외를 삼키지 않는다 — 라우트가 「조회 실패」(`lookup_failed`)와 「행 없음」을 가른다.
- 쓰기 SQL 은 `trade_journal_notes` 만(워커 표 `trade_journal_orders/_stops/_cursor` 에 쓰지 않는다).

`src/db/trade_history.py` 추가:
```python
async def get_trades_by_ids(ids: list[str]) -> list[dict]   # 명세 1-1 칸 + strategy·ticker·status, profit_loss NULL → None
```
`src/db/stock_master_daily.py` 추가 (SELECT 만, 예외 전파):
```python
async def get_closes_in_range(tickers: list[str], start: date, end: date) -> list[dict]
async def list_business_days(start: date, end: date) -> list[date]   # DISTINCT bas_dd 오름차순
```
재사용: `src.db.llm_buy_evaluations.list_by_order_nos(order_nos)`.

---

## 3. 라우트 — `src/routes/history.py` (같은 `router`, prefix `/api/history`)

- `GET /api/history/journal` — 쿼리·검증·고르는 규칙 = 명세 1-1. 응답 = `ApiResponse(data=JournalResponse)`.
  - `get_trade_pairs` 는 지금처럼 이 모듈의 전역 이름으로 부른다(테스트가 `src.routes.history.get_trade_pairs` 를 바꾼다).
  - 비용 원천은 요청 1번에 **`trade_cost.get_trades_by_status` 1회**(c411 F8 원칙 — 방법은 backend-dev).
  - 원천마다 실패 격리 → 200 + 그 칸만 `lookup_failed`. 카드 세부는 **그 페이지 카드만** 읽는다.
- `PUT /api/history/journal/notes/{anchor_trade_id}` — 명세 1-3. 본문 `{"body": str}`.
  - 검증 순서: UUID 꼴 아님 422 → body 가 문자열 아님 422 → strip 뒤 4,000자(코드포인트) 초과 422 → `get_trades_by_ids([id])` 에 BUY 행 없음 404 → strip 뒤 빈 문자열이면 `delete_note` + `data: null` → 아니면 `upsert_note(strip 한 body, strategy·ticker·buy_date = 그 BUY 행)`.

---

## 4. 프론트

- `History.tsx` 세 번째 탭 버튼 testid `history-tab-journal`(글자 「거래일지」). 기본 탭은 그대로 「주문체결내역」 — 일지 탭을 누르기 전엔 `/api/history/journal` 을 부르지 않는다.
- 표기 정본 `frontend/src/utils/journalLabels.ts` — named export:
  `reasonCodeLabel(code)` · `reasonSubLabel(sub)` · `phraseLabel(phrase)` · `sourceLabel(source)` · `stopKindLabel(kind)` · `stopEventLabel(event)` · `divisionLabel(code)` · `judgeSrcLabel(src)` · `signalSrcLabel(src)` · `valSrcLabel(src)` · `costStatusLabel(status)` · `boardLabel(board)` · `naLabel(na)` — 값 = 명세 2절·5절 표.
- 타입 `frontend/src/types/journal.ts` — `NaKind`·`ValSrc`·`CostStatus` type + `JournalResponse`·`JournalCard`·`OrderLine`·`ExitLine`·`Slip`·`Reason`·`StopPoint`·`Target`·`StopTrack`·`StopRow`·`Costs`·`Excursion`·`ExPoint` interface(키 = shape.json).
- MSW 기본 핸들러(`src/test/handlers.ts`) — `GET /api/history/journal`(shape.json 키 그대로 · na 5종이 모두 한 번 이상) · `PUT /api/history/journal/notes/:id`(`{anchor_trade_id, body, created_at, updated_at}`). 테스트 픽스처 `src/test/fixtures/journal.fixture.ts` 를 그대로 써도 된다.
- testid(명세 8-3) + 필터 testid: `journal-filter-period-7|30|90`(버튼) · `journal-filter-status`·`journal-filter-outcome`·`journal-filter-sort`(`<select>`, option value = API 코드) · `journal-counts` · `journal-filter-toggle`(400px 「필터」 버튼, DOM 에 있으면 된다). 청산 블록 testid = `journal-exit-{order_no}`(order_no 없으면 `journal-exit-{index}`).
- 손절선 변화 행 `journal-stop-row` 에 `data-event`·`data-direction`(`up`|`down`|`flat`|빈 값) 속성. 접힘이 기본 — 접힌 동안 행을 **그리지 않는다**(`journal-stop-toggle` 에 `aria-expanded`).
- 400px(`window.innerWidth=400`): 카드 안 `<table>` 0 · 고정 폭 클래스(`min-w-[NNNpx]`·`w-[NNNpx]`, NNN>400) 0 · 인라인 `style.width`/`minWidth` 0.
- 메모: 버튼 `journal-note-save` 로만 PUT · 자동 저장 0 · 4,000 초과면 저장 비활성 · 실패면 입력 유지 + 「저장 실패」 · 성공 「저장됨」 · 바뀌면 「저장 안 됨」. `dangerouslySetInnerHTML`·새 `Intl.DateTimeFormat` 금지(이름에 journal 이 든 프론트 파일 전수).

---

## 5. Red 파일과 담당

| 파일 | 담당 | 비고 |
|---|---|---|
| `tests/unit/engine/test_cycle413_journal_view.py` | backend-dev | leaf `build_card` T1~T7 |
| `tests/unit/routes/test_cycle413_journal_routes.py` | backend-dev | GET 필터·정렬·페이지·실패 격리·shape·/pnl 패리티 · PUT 메모. `test_n8`(리포터 키 403)은 기존 미들웨어로 이미 초록 — 회귀 가드 |
| `tests/unit/db/test_cycle413_journal_db.py` | backend-dev | 빈 입력 무쿼리 · 예외 전파 · NULL 손익 유지 |
| `tests/integration/test_cycle413_journal_pg.py` | backend-dev | 047 표 실 Postgres 왕복 + 라우트 왕복(httpx ASGITransport) |
| `tests/unit/ast/test_cycle413_scope_guard.py` | backend-dev | S1~S3 은 지금 초록(핀) · S4~S6 은 새 파일이 생기면 초록 |
| `tests/fixtures/cycle413_journal_shape.json` | 공용 | 응답 키 정본 — 바꾸면 백엔드·프론트 테스트가 함께 움직인다 |
| `frontend/src/utils/__tests__/journalLabels.cycle413.test.ts` | frontend-dev | 표기표 |
| `frontend/src/pages/__tests__/History.journal.cycle413.test.tsx` | frontend-dev | 탭·카드·배지·토글·손절선 변화·메모·필터·400px |
| `frontend/src/components/__tests__/handlers.honesty.cycle413.test.ts` | frontend-dev | MSW 기본 목(`src/test/handlers.ts`)·타입(`src/types/journal.ts`)·금지 API |
| `frontend/src/test/fixtures/journal.fixture.ts` | 공용 | 화면 테스트 응답 — 기본 목에 그대로 써도 된다 |

검산: Red 가 scratch 시제품(커밋 안 함)으로 백엔드 leaf 117 · 라우트·DB 단위 · 통합 21 · 프론트 화면 19 건을 모두 통과시켜 **서로 모순 없이 만족 가능함**을 확인했다. 남은 판단은 구현 쪽 자유다(함수 분할·컴포넌트 이름·정렬 방식).
