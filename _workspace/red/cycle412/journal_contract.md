# cycle412 거래일지 1a — 인터페이스 계약 (Red 가 정한 것, 구현은 이름·모양을 따른다)

정본 설계 = main 의 `_workspace/design/2026-10-08_trade_journal_observer.md`(우선) · `_workspace/design/2026-10-08_trade_journal_plan.md`(4절 저장 구조·R8 규칙·화면). 이 브랜치(`feat/trade-journal-1a`, 기준 `feat/cost-overlay` 272c76c1)에는 두 설계 파일이 아직 없다 — main 병합 때 들어온다.
사용자 결정(10-08) = E1a 워커 컨테이너 · E1b G1 · E1c 워커 전용 DB 역할(스크립트만, 운영 DB 실행 금지) · D2 메모 DB · D3 과거 로그 1회 적재.

이 문서와 테스트가 갈리면 테스트가 정본이다. 바꿔야 하면 tdd-engineer 와 합의하고 테스트를 함께 고친다.

---

## 0. 금기 (테스트로 고정)

| 금기 | 가드 |
|---|---|
| 8영역·`scheduler.py`·주문/청산 판단 경로 0줄 | `tests/unit/ast/test_cycle412_scope_guard.py` (내용 sha · `src/**/*.py` 집합 — **사이클 한정, 병합 후 삭제**) |
| `src/` 에서 바뀌는 파일은 `src/routes/balance.py` 하나 | 같은 파일(집합·sha) |
| 워커 `src` import 0 · `KIS_` 0 · `.env` 0 · 체결통보·KIS REST 0 | `journal_worker/tests/test_jw_isolation.py` |
| 기존 마이그레이션 무수정 · 047 은 가산형 | `tests/integration/test_cycle412_trade_journal_pg.py` (정적 검사는 docker 없이도 돈다) |
| 운영 DB 에 역할 생성 금지(스크립트만) | 사람 규약 — `journal_worker/ops/role.sql` 은 마이그레이션 디렉터리 밖 |

---

## 1. DB — `supabase/migrations/047_trade_journal.sql`

전부 `CREATE TABLE IF NOT EXISTS` / `CREATE INDEX IF NOT EXISTS`. `ALTER`·`DROP`·`UPDATE`·`DELETE`·`INSERT` 없음. 두 번 실행해도 오류 0.

### `trade_journal_orders` — 주문 1건 1행
| 칸 | 형식 |
|---|---|
| `id` | BIGSERIAL PRIMARY KEY |
| `order_date` | DATE NOT NULL |
| `order_no` | TEXT NOT NULL |
| `side` | TEXT NOT NULL (`BUY`/`SELL`) |
| `strategy` | TEXT NOT NULL |
| `ticker` | TEXT NOT NULL |
| `source` | TEXT NOT NULL |
| `reason_code` | TEXT NULL |
| `reason_sub` | TEXT NULL |
| `judge_price` | INTEGER NULL |
| `order_price` | INTEGER NULL |
| `order_division` | TEXT NULL |
| `exchange` | TEXT NULL |
| `parent_order_no` | TEXT NULL |
| `fired_line` | INTEGER NULL |
| `effective_line` | INTEGER NULL |
| `signal` | JSONB NULL |
| `params` | JSONB NULL |
| `noted_at` | TIMESTAMPTZ NOT NULL |
- `UNIQUE (order_date, order_no, side)` — 쓰기는 `ON CONFLICT (order_date, order_no, side) DO NOTHING`(처음 값을 지킨다). 예외 하나: `order_division` 이 NULL 인 행만 나중에 채운다(`UPDATE … WHERE order_division IS NULL`).

### `trade_journal_stops` — 손절선 사건
| 칸 | 형식 |
|---|---|
| `id` | BIGSERIAL PRIMARY KEY |
| `strategy`, `ticker` | TEXT NOT NULL |
| `buy_date` | DATE NULL |
| `pos_order_no` | TEXT NULL |
| `observed_at` | TIMESTAMPTZ NOT NULL |
| `event` | TEXT NOT NULL — `first`·`change`·`boot`·`eod`·`paused`·`exit` |
| `stop_price` | INTEGER NULL |
| `stop_kind` | TEXT NULL (= G1 `stop_source`) |
| `target_price` | INTEGER NULL |
| `target_hit` | BOOLEAN NULL |
| `arm_price` | INTEGER NULL |
| `inputs` | JSONB NULL |
- 인덱스 `(strategy, ticker, observed_at)`.

### `trade_journal_notes` — 메모(D2)
`id` BIGSERIAL PK · `anchor_trade_id` UUID NOT NULL UNIQUE · `strategy` TEXT · `ticker` TEXT · `buy_date` DATE · `body` TEXT NOT NULL · `created_at`/`updated_at` TIMESTAMPTZ NOT NULL DEFAULT now(). (1a 는 표만 만든다. API 는 1b.)

### `trade_journal_cursor` — 로그 커서
`name` TEXT PRIMARY KEY(기본 행 `'main'`) · `file_name` TEXT NOT NULL · `inode` BIGINT NOT NULL · `byte_offset` BIGINT NOT NULL · `updated_at` TIMESTAMPTZ NOT NULL DEFAULT now(). (`offset` 은 SQL 예약어라 쓰지 않는다.)

### 워커 전용 역할 — `journal_worker/ops/role.sql` (1회성, 047 뒤 psql 로 실행)
- 역할 이름 **`journal_worker`**, `LOGIN`, `NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS`.
- 비밀번호는 psql 변수 **`:'journal_pw'`** 하나로만 받는다(리터럴 비밀번호 0). 백슬래시 메타명령 0 — 테스트가 `:'journal_pw'` 를 치환해 asyncpg 로 실행한다. `$$` 안에는 psql 변수가 치환되지 않으므로 `CREATE ROLE` 은 `DO $$ … IF NOT EXISTS … $$` 로, 비밀번호는 그 밖의 `ALTER ROLE journal_worker … PASSWORD :'journal_pw'` 로 준다. **두 번 실행해도 오류 0.**
- 권한: `trade_history`·`llm_buy_evaluations` = SELECT 만 · `trade_journal_orders/_stops/_notes/_cursor` = SELECT·INSERT·UPDATE(DELETE 없음) + 그 표들의 시퀀스 USAGE · 그 밖의 표 = 0(`system_logs` 포함 — 대체 경로를 쓰게 되면 그때 더한다).
- 역할 수준 고정값: `statement_timeout=5s` · `lock_timeout=1s` · `idle_in_transaction_session_timeout=5s` (`ALTER ROLE journal_worker SET …`).
- DSN 은 `./secrets/journal_worker.env` 의 **`JOURNAL_DATABASE_URL`** 한 키(git 밖).

---

## 2. G1 — `GET /api/balance/exit-lines` (`src/routes/balance.py`)

- 핸들러 `async def exit_lines()` — `@router.get("/exit-lines")`. 본문에 `await` 0.
- 스냅샷 조립 함수 `def _exit_lines_snapshot(strategies, *, running: bool) -> dict` (await 0).
- 캐시: 모듈 전역 `_EXIT_LINES_CACHE_TTL_S = 5.0` · `_exit_lines_cache = None`(직전 응답 `(monotonic 시각, 직렬화된 본문 str)`) · 시계 seam `_exit_lines_clock = time.monotonic`. 직전 **성공** 응답 뒤 5초 안 재호출은 같은 본문을 그대로 준다(as_of 포함 바이트 동일). 캐시는 `global` 재바인딩으로만 바꾼다.
- 엔진 객체는 핸들러 안에서 `from src.engine.scheduler import trading_scheduler` 로 얻는다(`trading_scheduler.registry.all()` · `trading_scheduler.is_running`). 테스트는 `src.engine.scheduler.trading_scheduler` 를 바꿔 끼운다.
- 직렬화는 핸들러의 `try` 안에서 끝낸다: `json.dumps({...}, default=str)` → `Response(content=…, media_type="application/json")`. 예외 → `{"success": false, "data": null, "message": …}` (HTTP 200) · INFO 이상 로그 0(`logger.debug` 만).
- 응답 `{"success": true, "data": {...}, "message": ""}`, `data`:
  - `running`: bool · `as_of`: KST ISO 문자열(`+09:00`) · `items`: list
  - item 키(전부 필수, 모르면 null): `strategy_id`, `ticker`, `stop_price`, `stop_source`, `target_price`, `target_source`(= `resolve_exit_lines([s], ticker)` 결과 그대로), `buy_price`, `quantity`, `high_since_buy`, `buy_date`(ISO 문자열), `order_no`, `entry_atr`(`_entry_atr.get(t)`, 없으면 kojiro `_position_atr.get(t)`, 둘 다 없으면 null), `kk_armed`(donchian 만 bool, 그 밖 null), `kk_arm_price`(donchian 미무장 = `ceil(E + kk_breakeven_r × (E − 손절선))`, 무장·그 밖 = null)
  - 전략마다 보유 종목마다 1 item(같은 종목을 두 전략이 들고 있으면 2 item).
- AST 계약(G1 범위 = `exit_lines` + 이름이 `_exit_lines` 로 시작하는 모듈 함수):
  - 허용 호출만(G1 범위 함수 `_exit_lines*` 끼리의 호출은 허용): 이름 `getattr isinstance list dict tuple int float str bool len round sorted max min abs ceil isfinite resolve_exit_lines build_exit_line_map _exit_lines_snapshot _exit_lines_clock Response ApiResponse now_kst_iso` · 속성 `all items keys values get monotonic now isoformat dumps debug _kk_exit_lines _kk model_dump ceil isfinite`. (`as_of` 는 `src.db._kst.now_kst_iso()` 또는 모듈 상수 KST 로 `datetime.now(KST).isoformat()`)
  - `_kk` 는 문자열 리터럴 `"kk_breakeven_r"` 인자로만.
  - 금지: `check_*`·`on_*`·`prepare`·`calc_*`·`_apply_budget_limit`·`_market_unit_*`·`_effective_setup`·`vars`·`setattr`·`delattr`·`exec`·`eval`·`__dict__` 접근 · 변이 메서드 `pop popitem clear update setdefault sort append extend remove insert add discard`.
  - 대입·증분대입 대상은 이름(또는 이름 튜플)만 · `del` 0 · `global` 은 `_exit_lines_cache` 만.
  - 사본은 dict/list 컴프리헨션·리터럴로 만든다(위 변이 메서드 금지라 `append` 로 모으지 않는다).

---

## 3. 워커 — `journal_worker/` (src 밖, 빌드 컨텍스트 `./journal_worker`)

```
journal_worker/
  Dockerfile              FROM python:3.12-slim · COPY requirements.txt + jw/ 만 · ENTRYPOINT ["python","-m","jw"] · CMD ["run"]
  requirements.txt        정확히 2줄: asyncpg==0.30.0 · httpx==0.28.1
  ops/role.sql            1절
  jw/__init__.py
  jw/__main__.py          argv: run(기본) → jw.main · backfill → jw.backfill(그 분기 안에서만 import)
  jw/config.py            상수
  jw/grammar.py           로그 문법(이 모듈 1곳)
  jw/pairing.py           짝짓기(Pairer)
  jw/stops.py             R8 규칙(StopTracker)
  jw/reconcile.py         대사 항등식 · 외부/미매칭 행
  jw/tailer.py            커서·회전·1회 상한
  jw/http.py              G0·G1 호출
  jw/db.py                자동커밋 단문 DB
  jw/main.py              루프
  jw/backfill.py          과거분(source='log_restore')
  tests/                  __init__.py 두지 않는다(루트 `tests` 패키지와 이름 충돌) · conftest.py 가 journal_worker/ 를 sys.path 앞에 넣는다
  tests/fixtures/golden_2026-09-17_10-07.log      실측 로그에서 필요한 줄만(민감값 0 — 테스트가 검사)
  tests/fixtures/golden_expected.json             골든 기대값(매도 70 · 매수 75)
```
- 루트 `pyproject.toml` `testpaths` 에 `"journal_worker/tests"` 를 더해 CI 가 돌게 한다(Red 테스트 `test_cycle412_journal_compose.py::test_worker_tests_collected_by_root_pytest`).
- 환경변수는 `JOURNAL_DATABASE_URL`·`API_REPORTER_KEY` 둘만 읽는다(`TZ` 는 컨테이너가 쓴다).

### 3.1 `jw/config.py` 상수
`BASE_URL = "http://backend:8000"` · `G0_PATH = "/api/trading/status?include=system,holdings,strategies"` · `G1_PATH = "/api/balance/exit-lines"` · `ALLOWED_PATHS = frozenset({G0_PATH, G1_PATH})` · `CYCLE_SECONDS = 15` · `IDLE_CYCLE_SECONDS = 300` · `BACKOFF_MAX_SECONDS = 300` · `MAX_READ_BYTES = 4 * 1024 * 1024`(7절 N5) · `SIGNAL_RING_TTL_SECONDS = 600` · `REASON_WINDOW_SECONDS = 10` · `BUY_SIGNAL_LOG_WINDOW_SECONDS = 5` · `LOG_DIR = "/app/logs"` · `LOG_FILE = "auto_stock.log"` · `RECONCILE_MIN_AGE_SECONDS = 120` · `BACKFILL_MAX_BYTES_PER_SEC = 5 * 1024 * 1024`.
- 코드 안 `"/api/…"` 문자열은 위 두 경로뿐(테스트가 jw/ 전체를 훑는다).

### 3.2 로그 문법 — `jw/grammar.py`
`parse_line(line: str) -> dict | None` — 줄 꼴 `YYYY-MM-DD HH:MM:SS [LEVEL   ] <logger> — <message>`(줄 끝 `\n` 있어도 됨). 모르는 줄·다른 로거 = `None`. **로거 이름 + 메시지 접두**로 가른다.

공통 키: `ts`(aware datetime, KST +09:00) · `level` · `logger` · `kind` · `raw`(메시지).
종목 표기는 두 꼴 — `이름(코드)` / `코드`. 코드는 **끝에서** 읽는다(`인제니아테라퓨틱스(Reg.S)(950260)` → ticker `950260`, name `인제니아테라퓨틱스(Reg.S)`). 코드만이면 name `None`. 이름에 공백 가능(`CJ ENM(035760)`).

| kind | 로거 | 메시지(생산 쪽 포맷) | 추가 키 |
|---|---|---|---|
| `buy_accept` | `src.engine.order_engine` | `매수 주문 접수: %s %d주 @ %d (주문번호: %s, 전략: %s)` | ticker name qty price order_no strategy |
| `sell_accept` | 같음 | `%s 매도 주문 접수: %s %d주 (주문번호: %s, 전략: %s)` | signal ticker name qty order_no strategy |
| `manual_sell_accept` | `src.routes.trading` | `수동 매도 주문 접수: %s %d주 (주문번호: %s, 전략: %s)%s` | ticker name qty order_no strategy |
| `order_done` | `src.api.order` | `%s 주문 완료: %s %s주 @ %s (주문번호: %s)` | side ticker qty price order_no |
| `order_notice` | `src.realtime.handler` | `[order_notice] order_no=… orig_order_no=… side=… rctf=… kind=… …` (`[order_rejected_notice]` 는 아니다) | order_no orig_order_no(빈값=None) side rctf **division**(=`kind=` 값) ticker qty(int) price(int) acpt |
| `buy_fallback` | `src.engine.order_engine` | `시장가 거부 → 지정가 5호가 폴백: %s @ %d (원인 [%s] %s)` | ticker name price |
| `sell_fallback` | 같음 | `매도 시장가 거부 → 지정가 5호가 폴백: %s @ %d (원인 [%s] %s, 주문번호: %s, 전략: %s)` | ticker name price order_no strategy |
| `reorder` | 같음 | `손절 잔여 재주문: %s %d주` | ticker name qty |
| `status_exit_fire` | `src.engine.status_exit_watch` | `[status_exit_fire] ticker=… strategy=… reason=…` | ticker strategy reason |
| `ndc_defer` | `src.engine.scheduler` | 3 문구(아래) | ticker name strategy reason_sub gap threshold |
| `exit_reason` | `src.engine.strategies.<id>` | 16 문구(아래) | strategy phrase reason_code ticker name buy_price pct threshold line current_price target mode |
| `buy_signal` | `src.engine.strategies.<id>` | 7 문구(아래) | strategy ticker name price |

`strategy` 는 `exit_reason`·`buy_signal` 에서 로거 끝 이름(`src.engine.strategies.kojiro` → `kojiro`).

익일청산 보류 3문구 → `reason_sub`:
- `stock_master nxt_tradable=False — 익일 청산 보류 (09:00 KRX 시장가 청산 예약): %s (전략: %s)` → `krx_only`
- `NXT 시가 미수신 — 익일 청산 보류 (KRX 시가 확정 후 재시도): %s (전략: %s)` → `nxt_open_missing`
- `익일 청산 보류 (갭 %.1f%% < 임계 %.1f%%, 09:00 KRX 시장가 청산 예약): %s (전략: %s)` → `gap_below` (gap·threshold float)

청산 사유 16문구 → `phrase` · `reason_code`(이 이름으로 보정 저장):
| phrase | 문구 머리 | reason_code | 숫자 |
|---|---|---|---|
| `kojiro_hard_stop` | `[kojiro_hard_stop] %s 매수가(%d) 대비 %.1f%% ≤ %.1f%%` | STOP_LOSS | buy_price pct threshold |
| `kojiro_atr_stop` | `[kojiro_atr_stop] %s 손절선(%d) = 매수가(%d) - …` | STOP_LOSS | line buy_price (식 문구는 쓰지 않는다) |
| `kojiro_trailing` | `[kojiro_trailing] %s 고점(%d) - … = %d / 현재가 %d` | TRAILING_STOP | line current_price |
| `kojiro_stage3_exit` | `[kojiro_stage3_exit] %s 스테이지3 진입 …` | TREND_EXIT | |
| `bfb_turtle_stop` | `[bfb_turtle_stop] %s 손절선(%d) = 매수가(%d) − …` (U+2212) | STOP_LOSS | line buy_price |
| `bfb_turtle_backstop` | `[bfb_turtle_backstop] %s 매수가(%d) 대비 %.1f%% ≤ %.1f%%` | STOP_LOSS | buy_price pct threshold |
| `bfb_pullback_stop` | `눌림목 손절: %s 매수가(%d) 대비 %.1f%%` | STOP_LOSS | buy_price pct |
| `bfb_measured_target` | `눌림목 측정된 이동 도달: %s 현재가(%d) ≥ 타겟(%d) …` | TAKE_PROFIT | current_price target |
| `bfb_time_exit` | `눌림목 시간 청산: %s buy_date=…` | TIME_EXIT | |
| `ltv_intraday_stop` | `롱테일VB 당일 손절: %s %.1f%%` | STOP_LOSS | pct · mode=`intraday` |
| `ltv_limit_up_stop` | `롱테일VB 손절(상한가 모드): %s %.1f%%` | STOP_LOSS | pct · mode=`limit_up` |
| `vb_stop` | `변동성돌파 손절: %s 매수가(%d) 대비 %.1f%% (현재가: %d)` | STOP_LOSS | buy_price pct current_price |
| `momentum_stop` | `손절 신호: %s 매수가(%d) 대비 %.1f%% (임계: %.1f%%, 현재가: %d)` | STOP_LOSS | buy_price pct threshold current_price |
| `donchian_time_exit` | `[donchian_time_exit] ticker=%s reason=%s …` | TIME_EXIT | |
| `donchian_time_exit_legacy` | `도치안 시간 기반 청산: %s 보유 … 현재가(%d) < 돌파선(%d)` (옛 문구, 과거분) | TIME_EXIT | current_price |
| `donchian_trailing_legacy` | `도치안 스윙 트레일링: %s 고점(%d) - … = %d / 현재가 %d` (옛 문구, 과거분) | TRAILING_STOP | line current_price |

매수 신호 7문구(`buy_signal`, price = 현재가 · BFB·VCP 는 None): `[bfb_vol_gate_pass] ticker=` · `[vcp_vol_gate_pass] ticker=` · `고지로 매수 신호: %s 현재가(%d) — …` · `도치안 스윙 매수 신호: %s 현재가(%d) — …` · `변동성돌파 매수 신호 [%s]: %s 현재가(%d) >= …` · `롱테일 변동성 돌파 매수 신호 [%s]: %s 현재가(%d) >= …` · `매수 신호: %s 전일종가(%d) 대비 %.1f%% (현재가: %d, …)`.

생산 쪽 문구는 `tests/unit/ast/test_cycle412_log_phrase_pins.py` 가 소스 AST 문자열 상수로 고정한다(옛 문구 2개 제외).

### 3.3 짝짓기 — `jw/pairing.py`
```python
class Pairer:
    def __init__(self, *, source: str = "log_harvest"): ...   # "log_harvest" 면 경로별 source, 그 밖의 값(과거분 "log_restore")이면 모든 행이 그 값 — 문자열 'log_restore' 는 jw/backfill.py 에만 둔다
    def feed_snapshot(self, g0: dict | None, g1: dict | None, observed_at: datetime) -> None
    def feed_events(self, events: list[dict]) -> None          # parse_line 결과(None 제외), 로그 순서
    def drain(self, *, final: bool = False, trade_strategies: dict[str, str] | None = None) -> dict
        # -> {"orders": [row, ...], "stops": [exit_event, ...]}
    def external_notice_orders(self) -> set[str]   # [order_notice](rctf=="0") 에만 있고 엔진 완료·접수·수동 줄이 없는 주문번호
```
- **한 회전 보류**: 앵커 줄(접수·완료·폴백·재주문·수동)은 그 줄을 먹은 회전의 `drain()` 에서는 내보내지 않고 **다음** `drain()` 에서 내보낸다. `final=True` 는 모두 즉시 내보낸다(과거분). 보류 중에 온 `[order_notice]` 의 `division` 이 그 행에 실린다.
- **링**: `feed_snapshot` 이 `g0["strategies"][sid]["buy_signals"]` 를 (전략, 종목, 신호 시각) 링에 쌓는다. 신호 `time`(`HH:MM:SS`, KST)은 `observed_at` 날짜로 읽는다. (전략, 종목, 신호 시각) 으로 중복을 없앤다. **TTL 은 신호 시각 기준** — 신호 시각이 최신 `observed_at` 보다 `SIGNAL_RING_TTL_SECONDS`(600초) 넘게 이르면 버리고 다시 받지 않는다(G0 `buy_signals[-10:]` 는 같은 신호를 계속 돌려주므로 관측 시각 기준 TTL 은 영영 안 끝난다). 처음 본 스냅샷의 `params` 사본을 함께 둔다.
- **매수 행**: 같은 (전략, 종목) 링 신호 중 **신호 시각 ≤ 접수 시각**인 마지막 것 → `signal` = 그 dict 사본 + `"signal_src": "ring"`, `params` = 그 사본, `judge_price` = 신호 `price`. 내보낼 때(보류 뒤)에도 링에 없으면 접수 시각 이전 `BUY_SIGNAL_LOG_WINDOW_SECONDS`(5초) 안의 같은 (전략, 종목) `buy_signal` 줄 → `"signal_src": "log_only"`, `judge_price` = 그 줄 price(BFB·VCP None), `params` None. 그것도 없으면 `"signal_src": "none"`. `reason_code="ENTRY"` · `order_price` = 접수 줄 `@` 가격.
- **매도 행**(접수 줄): `signal` 에 `signal_name`(접수 줄 원래 이름) · `reason_line`(원문 또는 None) · `phrase` · 파싱 숫자 · `judge_src` · (스냅샷 있으면) `snapshot_age_s`·`stop_kind`.
  - `reason_code`: 접수 이름이 `STOP_LOSS TRAILING_STOP TIME_EXIT TAKE_PROFIT TREND_EXIT` 중 하나면, 접수 시각 이전 `REASON_WINDOW_SECONDS`(10초) 안 **같은 전략 로거**의 같은 종목 `exit_reason` 줄 중 마지막 것의 `reason_code` 로 보정(없으면 접수 이름). `FORCE_CLEAR`·`NEXT_DAY_CLEAR`·`STATUS_EXIT` 는 이름 그대로(사유 줄 안 봄).
  - `NEXT_DAY_CLEAR` → 같은 날 접수 이전 같은 (전략, 종목) `ndc_defer` 의 `reason_sub` · `signal.gap`·`signal.gap_threshold`.
  - `STATUS_EXIT` → 10초 안 같은 (전략, 종목) `[status_exit_fire]` 의 `reason` 이 `reason_sub`.
  - `fired_line`(발동선): 줄에 선 가격(`line`) → 그 값 · 줄에 임계(`threshold`)+매수가 → `round(buy × (1 + threshold / 100))` · LTV 두 문구 → 스냅샷 `params` 의 `intraday_stop_loss`/`overnight_stop_loss` 로 같은 식 · 그 밖의 가격 청산(BFB 눌림목·VB 등) → 직전 스냅샷 `stop_price` · 가격 무관 청산·스냅샷 없음 → None.
  - `judge_price`: 줄의 `current_price` → `judge_src="log_price"` · 없으면 줄의 `pct` 로 `round(buy × (1 + pct / 100))` → `"log_pct"` · 없으면 None(1b 가 `trade_history.order_price` 로 채운다). kojiro ATR 손절은 `signal.judge_upper = line`.
  - 매수가(`buy`) 출처: 줄의 `buy_price` → 직전 G1 스냅샷 item `buy_price` → 같은 (전략, 종목) 의 마지막 `buy_accept` 가격(LTV 과거분은 이것뿐).
  - `effective_line`: 접수 시각 **이전**(≤) 의 가장 최근 G1 스냅샷 item `stop_price` + `signal.snapshot_age_s = 접수시각 − 스냅샷시각`(초, int). 스냅샷은 원본을 보관하지 않고 손절 관련 칸만 담은 압축 기록 2~8개(6절 결함 1). 없으면 None(관측 전 청산). 이때 `stops` 에 `event="exit"` 사건 1개(inputs 에 `snapshot_age_s`·`sell_order_no`).
- **경로별 source**(실시간; 과거분은 전부 `log_restore`, 경로는 `signal.path`): 접수 = `log_harvest`(path `accept`) · 매도 폴백 = `fallback_inferred`(`sell_fallback` 줄, 사유는 10초 안 사유 줄) · 매수 폴백 = `fallback_inferred`(`BUY 주문 완료` + 같은 종목 `buy_fallback`, 접수 줄 없음, 전략은 `trade_strategies[order_no]`, 없으면 `"unknown"` — 6절 결함 2) · 재주문 = `reorder_inferred`(`SELL 주문 완료` 뒤 같은 종목·같은 수량 `reorder`, 접수 줄 없음, `parent_order_no` = 같은 종목 직전 매도 접수 주문번호, 전략·사유는 부모 것) · 수동 = `manual_api`(`src.routes.trading` 로거, `reason_code="MANUAL"`).
- `order_date` = 앵커 줄 KST 날짜 · `noted_at` = 앵커 줄 시각(aware KST) · `order_division` = 그 주문번호 첫 `[order_notice]`(`rctf=="0"`) 의 `division`.

### 3.4 손절선 사건 — `jw/stops.py`
```python
class StopTracker:
    def __init__(self, *, last_rows: dict[tuple[str, str], dict] | None = None): ...  # DB 의 (전략,종목)별 마지막 행
    def observe(self, *, observed_at: datetime, g0: dict | None, g1: dict | None,
                new_holding_keys: frozenset = frozenset()) -> list[dict]
```
사건 dict 키 = 2절 표 칸(`id` 제외) — `strategy ticker buy_date pos_order_no observed_at event stop_price stop_kind target_price target_hit arm_price inputs`.
- 엔진 정지·idle(`g0` 없음 · `running` 거짓 · `phase=="idle"` · g1 없음) → 사건 0. 사라진 보유를 청산으로 보지 않는다(21:30 `positions.clear()`).
- `phase=="booting"` 회전 → 0. 그 뒤 **booting 이 아닌 첫 회전도 0**(재구성 전 값 차단) · 그 회전의 값으로 기억도 갱신하지 않는다. 그다음 회전: 직전 행과 값이 **조금이라도** 다르면 `boot`(문턱 없음), 같으면 0.
- 처음 보는 보유(직전 행 없음 · 또는 `new_holding_keys` 에 있음) → `first`.
- 이어지는 보유: 손절선이 **내려가면 1원이라도** `change` · 올라가면 직전 **기록** 대비 `≥ 0.5%` 일 때만 `change`(조금씩 오르면 누적이 0.5% 를 넘는 회전에 1번) · `stop_kind` 가 바뀌면 `change` · `target_price`/`target_hit`/`arm_price` 가 바뀌면 `change`.
- `eod`: 15:30(KST) 이후 첫 관측에 (전략,종목)마다 하루 1번(값이 같아도). 같은 회전에 변화가 있어도 행은 `eod` 1개.
- `paused`: `g0.strategies[sid].enabled` 가 거짓인 전략의 보유 → 꺼짐 구간마다 1번(다시 켜졌다 꺼지면 또 1번).
- `target_hit` = item `target_source == "measured_move_hit"` · `arm_price` = item `kk_arm_price`, 무장(null) 뒤에는 마지막 무장가 유지.
- `inputs` = `buy_price quantity high_since_buy entry_atr kk_armed stop_source target_source`.
- 한 회전·한 (전략,종목)에 행은 1개. 우선순위 `first` > `boot` > `paused` > `eod` > `change`(15:30 뒤 첫 관측이 `first` 면 그날 `eod` 는 따로 쓰지 않는다).

### 3.5 대사 — `jw/reconcile.py`
```python
def check_identities(events: list[dict], rows: list[dict]) -> dict
    # -> {"sell_done", "sell_rows", "buy_done", "buy_rows", "unknown_reason_sells", "ok"}
def emit_gap(result: dict, logger: logging.Logger) -> bool      # ok 가 아니면 WARNING 1줄 "[journal_gap] sell_done=… sell_rows=… buy_done=… buy_rows=… unknown_reason_sells=…"
def rows_from_trade_history(trade_rows: list[dict], journal_keys: set, notice_orders: set[str], *, now: datetime) -> list[dict]
```
- `sell_done`/`buy_done` = `order_done` 줄 수(SELL/BUY) · `*_rows` = 그 side 행 중 source 가 `external`·`unmatched` 가 아닌 것 · `unknown_reason_sells` = 그 매도 행 중 `reason_code` 가 None.
- `rows_from_trade_history`: `trade_rows`(키 `order_no trade_type strategy ticker timestamp status price order_price`) 중 status `COMPLETED`/`PARTIAL`, `timestamp ≤ now − RECONCILE_MIN_AGE_SECONDS`(워커는 `now` 에 벽시계가 아니라 대사 기준 시각 W 를 넘긴다 — 7절 N1), `(KST 날짜, order_no, trade_type)` 가 `journal_keys` 에 없는 것 → `notice_orders` 에 있으면 `source="external"`, 없으면 `"unmatched"`. `reason_code=None`. PENDING·CANCELLED·[order_notice] 만 있는 주문(미체결 외부) = 행 0.

### 3.6 HTTP — `jw/http.py`
```python
def build_client(*, base_url: str, reporter_key: str, transport=None) -> httpx.AsyncClient   # follow_redirects=False, 헤더 X-API-Key
async def fetch(client: httpx.AsyncClient, path: str) -> dict   # path ∉ ALLOWED_PATHS → ValueError(요청 0) · 3xx/4xx/5xx/success=false → JournalFetchError · 성공 = data
class JournalFetchError(Exception)
```

### 3.7 DB — `jw/db.py` (자동커밋 단문만)
```python
class JournalDB:
    def __init__(self, conn): ...   # asyncpg Connection 또는 Pool (execute/fetch/fetchrow/fetchval)
    async def insert_order(self, row: dict) -> bool                   # INSERT … ON CONFLICT (order_date, order_no, side) DO NOTHING · 새로 넣었으면 True(7절 N1)
    async def promote_order(self, row: dict) -> bool                  # UPDATE … 빈 행(unmatched·external)의 빈 칸만 채우고 source 를 로그 행 것으로 · 바꿨으면 True(7절 N1)
    async def fill_order_division(self, order_date, order_no, side, division) -> None   # UPDATE … WHERE … AND order_division IS NULL
    async def insert_stop(self, event: dict) -> None
    async def load_cursor(self, name: str = "main") -> dict | None    # {"file_name","inode","byte_offset"}
    async def save_cursor(self, cursor: dict, name: str = "main") -> None   # INSERT … ON CONFLICT (name) DO UPDATE
    async def last_stop_rows(self) -> dict                            # (전략,종목) → 마지막 행(pos_order_no 포함 — 6절 결함 6)
    async def trades_since(self, since: datetime) -> list[dict]       # trade_history SELECT
```
- 메서드마다 `execute/fetch/fetchrow/fetchval` 정확히 1번 · SQL 은 문장 1개 · `transaction()` 0 · `BEGIN/COMMIT` 0. jw/ 어디에도 `.transaction(` 없음. `jw/db.py` 는 httpx·sleep 을 모른다.

### 3.8 꼬리 읽기 — `jw/tailer.py`
```python
def read_chunk(log_dir, cursor: dict | None, *, max_bytes: int = MAX_READ_BYTES,
               file_name: str = LOG_FILE) -> tuple[list[str], dict]
```
- cursor = `{"file_name","inode","byte_offset"}`. None → 현재 파일 0 부터. 반환 줄은 개행 없이 · **완결된 줄만**(끝의 미완성 줄은 다음에) · 한 번에 `max_bytes` 이하.
- 회전(이름 바꾸기): cursor inode ≠ 현재 파일 inode → 디렉터리에서 그 inode 파일(`auto_stock.log.YYYY-MM-DD`)을 찾아 offset 부터 끝까지 → 다 읽으면 새 파일 0 으로. 옛 파일이 없으면 새 파일 0. 같은 inode 인데 크기 < offset(잘림) → 0. utf-8 `errors="replace"`.

### 3.9 루프 — `jw/main.py`
```python
def backoff_delay(failures: int) -> float          # min(CYCLE_SECONDS * 2 ** failures, BACKOFF_MAX_SECONDS)
async def run_forever(rotate, *, sleep=asyncio.sleep, stop=lambda: False) -> None
class Worker:
    def __init__(self, *, client, db, log_dir, pairer=None, tracker=None, now=None): ...
    async def rotate(self) -> str                  # "active" | "idle" | "degraded"
```
- `run_forever`: `while not stop()` 마다 `try: status = await rotate() … except Exception … finally: await sleep(delay)`. active → 15 · idle → 300 · degraded·예외 → 연속 실패 수로 `backoff_delay`(30, 60, 120, 240, 300, 300…), 성공하면 0 으로.
- `rotate` 순서: (첫 회전만 `load_cursor`·`last_stop_rows`) → G0 → (idle 아니면) G1 → `feed_snapshot` → 로그 이어 읽기(`read_chunk`) → `feed_events` → `drain` → 행·사건 쓰기 → `StopTracker.observe` 사건 쓰기 → **커서 저장**. idle(G0 `running` 거짓 또는 `phase=="idle"`) → G1·로그·DB 쓰기 0. G0/G1 실패(`JournalFetchError`) → 스냅샷 없이 로그 수확은 계속하고 `"degraded"`. 동시 요청 0(`gather`/`create_task`/`TaskGroup` 금지).
- **커서는 행이 DB 에 다 쓰인 청크 끝까지만 전진한다** — 한 회전 보류 때문에 회전 k 에 읽은 청크의 행은 회전 k+1 에 쓰인다. 그래서 회전 k 의 쓰기 뒤에는 **회전 k−1 청크 끝** 커서를 저장한다(첫 회전은 저장하지 않거나 offset 0). 재시작하면 보류 중이던 청크를 다시 읽고, 이미 쓴 행은 `ON CONFLICT DO NOTHING` 이 걸러 준다.
- 대사(3.5)는 `rotate` 안에서 60초마다 — 단 기준 시각 W(행까지 쓴 로그 줄의 시각)가 생긴 뒤부터, 읽기 창이 꽉 찬 회전은 건너뛴다(7절 N1). 연결·로그·거짓 경보 금지는 6절 결함 3 · 경고 빈도는 7절 N2.

### 3.10 과거분 — `jw/backfill.py`
```python
def iter_log_lines(paths, *, max_bytes_per_sec: int = BACKFILL_MAX_BYTES_PER_SEC, sleep=time.sleep) -> Iterator[str]   # .gz·평문
def restore_rows(lines) -> list[dict]          # Pairer(source="log_restore") + drain(final=True) 의 orders
async def run_backfill(paths, db, *, max_bytes_per_sec: int = BACKFILL_MAX_BYTES_PER_SEC, sleep=time.sleep) -> dict
    # -> {"lines": 읽은 줄 수, "rows": 만든 행 수} · db.insert_order 로만 쓴다(6절 결함 8)
```
- 기동 경로(`jw.main`·Dockerfile CMD·compose `command`)는 backfill 을 부르지 않는다. 문자열 `'log_restore'` 는 jw/ 에서 `backfill.py` 에만.

---

## 4. 배포

### compose (`docker-compose.prod.yml` **본체**)
```yaml
  journal_worker:
    build:
      context: ./journal_worker
    env_file: ./secrets/journal_worker.env
    environment:
      - TZ=Asia/Seoul
      - API_REPORTER_KEY=${API_REPORTER_KEY}
    volumes:
      - ./logs:/app/logs:ro
    mem_limit: 160m
    cpus: 0.25
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"
    restart: unless-stopped
```
`ports:` 없음 · `.token_cache` 없음 · `KIS_` 없음 · `env_file` 은 그 파일 하나(`.env` 금지) · `command:` 에 backfill 없음 · tls 오버레이에 정의 없음.

### 배포 축 — `tools/deploy/compose_up_changed.sh`
- `JOURNAL_RE='^journal_worker/'`(한 줄 정의) — BACKEND_RE 에 걸리지 않는다.
- 축 이름 `journal` → 서비스 `journal_worker`. 선택 모드 = 걸린 축을 `frontend`·`macro`·`journal` 순서로 `+` 로 잇는다(`journal`, `frontend+journal`, `macro+journal`, `frontend+macro+journal`, 기존 `frontend`·`macro`·`frontend+macro` 그대로). reason = 축을 `_and_` 로 이어 `_only`(`journal_only`, `frontend_and_macro_only` …).
- `--no-deps` 줄은 여전히 하나(`"${SERVICES[@]}"`), up 줄 총 3 · `SERVICES+=(journal_worker)` · backend 히트 → full(불변).

### CI 에서 워커 테스트 돌리기
- 루트 `pyproject.toml` `testpaths = ["tests", "journal_worker/tests"]` (W7). 기존 가드 `test_cycle303_macro_isolation.py::test_pyproject_when_read_then_testpaths_is_tests_only` 는 이 Red 에서 「`tests` 포함 · ⊆ {tests, journal_worker/tests} · macro 0」 으로 갱신했다(vendor `macro/tests` 배제라는 이빨은 그대로).
- 영향 인덱스(`tools/test_impact/build_index.py`)는 `tests/` 만 본다 — 워커 테스트는 인덱스 밖이다(워커는 `src` 를 import 하지 않으므로 「src 변경 → 영향 테스트」 매핑 대상도 아니다).

## 5. 테스트 파일 ↔ 담당

| 담당 | 테스트 파일 | 만들거나 고칠 파일 |
|---|---|---|
| 백엔드/배포 | `tests/unit/routes/test_cycle412_g1_exit_lines.py` · `tests/unit/ast/test_cycle412_g1_purity.py` | `src/routes/balance.py`(G1 + 5초 캐시, 약 30~60줄) |
| 백엔드/배포 | `tests/integration/test_cycle412_trade_journal_pg.py` | `supabase/migrations/047_trade_journal.sql` · `journal_worker/ops/role.sql` · (선택) `tests/integration/pg_harness.py` 문서 줄 001~047 |
| 백엔드/배포 | `tests/unit/deploy/test_cycle412_journal_compose.py` | `docker-compose.prod.yml`(journal_worker 서비스) · `pyproject.toml`(testpaths) |
| 백엔드/배포 | `tests/unit/deploy/test_cycle412_journal_deploy_classification.py` · `tests/unit/ast/test_cycle248_deploy_pipeline.py`(G-248-2j·4j·5) | `tools/deploy/compose_up_changed.sh`(JOURNAL_RE · 모드 일반화) |
| 백엔드/배포(핀) | `tests/unit/ast/test_cycle287_ast_scope.py`·`test_cycle291_ast_scope.py` 등의 `_SRC_TREE_DIGEST` | `balance.py` 가 바뀌므로 digest 만 다시 계산(파일 수 핀 182·96·85 등은 그대로 — src 새 파일 0) |
| 워커 | `journal_worker/tests/test_jw_*.py` 11개 | `journal_worker/Dockerfile` · `requirements.txt` · `jw/{__init__,__main__,config,grammar,pairing,stops,reconcile,tailer,http,db,main,backfill}.py` |
| 가드(지금 초록) | `tests/unit/ast/test_cycle412_scope_guard.py`(사이클 한정, 병합 후 삭제) · `tests/unit/ast/test_cycle412_log_phrase_pins.py` | 없음 — 붉어지면 범위 위반 |
| 워커(보완) | `journal_worker/tests/test_jw_memory.py` · `test_jw_pairing_fixes.py` · `test_jw_worker_ops.py` + 기존 `test_jw_{stops,db,reconcile,backfill,isolation}.py` 끝의 「보완 Red」 블록 | 6절 |
| 백엔드/배포(보완) | `tests/integration/test_cycle412_trade_journal_pg.py::test_k10_*` | `jw/backfill.py`(`run_backfill`) |
| 워커(보완2) | `journal_worker/tests/test_jw_reconcile_timing.py`(신규) · `test_jw_worker_ops.py`(W3·W3b·W3c 다시 씀 + W10·W11) · `test_jw_db.py` B1(promote_order)·B7·B8 · `test_jw_memory.py` M5 · `test_jw_isolation.py` I12 · `test_jw_tailer.py` T3b(4MiB) · `test_jw_loop.py` FakeDB(반환값) · `jw_testkit.py`(FakeJournalDB·LiveLog) | 7절 — `jw/{main,db,config,pairing,__main__}.py` · `Dockerfile` |
| 백엔드/배포(보완2) | `tests/integration/test_cycle412_trade_journal_pg.py::test_k11_*` | `jw/db.py`(`insert_order` 반환 · `promote_order`) |

---

## 6. 보완 결정 (10-09 — 직전 판정 「보완 필요」 11건, 메인 세션 결정)

결함 번호는 판정 원문 그대로다. 8영역·`scheduler.py`·기존 마이그레이션은 여전히 0줄이고 047 의 NOT NULL 도 바꾸지 않는다. 테스트가 정본이다(이 절과 갈리면 테스트).

| # | 결정 | 테스트 |
|---|---|---|
| 1 (높음) | **보관 정책을 바꾼다**(개수 상한 뒤 줄이기 금지). G0·G1 원본 dict 는 들고 있지 않는다. 남기는 것 = ① 링: (전략,종목)별, 신호 시각 기준 600초 — 만료 키 집합을 따로 두지 않고 TTL 밖 신호는 처음부터 넣지 않는다 ② 전략별 `params` 사본(LTV 발동선용)과 G1 압축 기록(`stop_price stop_source buy_price buy_date order_no target_price target_source kk_arm_price`) 최근 2~8개 ③ 짝짓기 대기 항목(완료 줄·접수 전문·사유 줄·신호 줄·종목상태 줄) = 이벤트 시각 기준 TTL(창보다 넉넉히, 한 회전 보류를 덮게) ④ 날 단위 상태(익일청산 보류 줄·그날 신규 접수 전문 번호·앵커 번호)는 날이 바뀌면 비운다 ⑤ (전략,종목)별 마지막 매수 접수가는 키당 1개. 과거분 모드(`source != "log_harvest"`)는 입력 전체를 한 번에 넣으므로 이 정책 밖이다(골든 P8) | `test_jw_memory.py` M1(500·2000·5000 회전, 같은 시각에 재서 첫날→둘째 날 +25%·둘째 날→넷째 날 +2%·절대 2MB 미만) · M2(원본 dict·안 쓰는 칸 값이 닿지 않음) · M3(Worker 전체) · M4 |
| 2 (중간) | 전략 = 줄 → (재주문) 부모 → `trade_strategies[주문번호]` → `"unknown"`. 채운 출처는 `signal["strategy_src"]`(`"trade_history"`·`"unknown"`). 워커는 `JournalDB.trades_since(KST 오늘 00:00)` 로 `{주문번호: 전략}` 을 만들어 `drain` 에 넘긴다(새 DB 메서드 없음 · 조회 실패 = WARNING 후 빈 dict). **행 단위 예외 격리** — `insert_order`·`insert_stop` 한 건 실패는 WARNING(주문번호) 뒤 다음 행으로, 커서 저장은 계속, `rotate()` 는 예외를 올리지 않는다 | F2a~F2f · W2 · W2b · W2c |
| 3 (중간) | 대사를 `rotate` 에 연결한다 — 60초마다(첫 회전 포함): `trades_since(KST 오늘)` → `rows_from_trade_history(…, 오늘 일지 키, external_notice_orders(), now)` → 격리된 `insert_order` → `check_identities(120초 지난 완료 줄, 120초 지난 행)` → `emit_gap`. 대사 실패 = WARNING, 그 회전의 수확·커서는 계속. 정상 흐름(한 회전 보류 포함)에서 `[journal_gap]` 0줄 · 일지에 있는 주문으로 대사 행을 다시 쓰지 않는다. 날 단위 누적(그날 완료 줄·행·키)은 날이 바뀌면 비운다(M3). **로깅** = 모듈마다 `logging.getLogger(__name__)`(`jw.*`) · `python -m jw` 가 `main()` 안에서 표준 출력·평문·INFO 로 설정(가져오기만으로는 설정하지 않는다) · `run_forever` 예외 = WARNING(예외 문구 포함) + 백오프 · G0/G1 실패 = WARNING · 쓰기 실패 = WARNING | W3 · W3b · W3c · W3d · W3e · W3f · W3g · C9 |
| 4 (중간) | 사유 줄의 `reason_code` 가 `TIME_EXIT`·`TAKE_PROFIT`·`TREND_EXIT` 면 `fired_line=None`(설계 「시각·시간·추세 청산 = 미발동, 참고값」). `effective_line` 은 그대로 스냅샷 값. 선·임계가 없는 가격 손절(BFB 눌림목·VB)은 여전히 스냅샷 손절선 | F4 · F4b |
| 5 (중간) | 접수·수동·매도 폴백 줄은 같은 주문번호 완료 줄에 「사용」 표시. 폴백 매수·재주문은 같은 종목(재주문은 같은 수량) 미사용 완료 줄 중 **시각이 가장 가까운** 것 | F5a~F5d |
| 6 (중간) | 보유 식별 = (전략, 종목) + 보유 주문번호(G1 `order_no`). 주문번호가 바뀌면(사라졌다 다시 산 경우·회전 사이에 바뀐 경우) `first`. 같은 주문번호가 한 회전 빠졌다 돌아오면 새 보유가 아니다. DB 마지막 행의 `pos_order_no` 와 다르면 `first`, 마지막 행에 주문번호가 없으면(옛 행) 이어 붙인다. `last_stop_rows` 가 `pos_order_no` 를 읽는다 | S13 · S13b · S13c · S14 · B6 |
| 7 (낮음) | 대사의 날짜 키·`order_date` 는 KST 날짜, `noted_at` 은 KST aware(asyncpg 는 UTC aware 로 준다) | C8 · C8b |
| 8 (낮음) | D3 을 실제로 동작하게 한다 — `async run_backfill(paths, db, *, max_bytes_per_sec, sleep) -> {"lines","rows"}`(3.10절) · CLI `python -m jw backfill <경로…>`(종료 코드 0, 경로가 없으면 사용법 오류이고 DB 에 붙지 않는다) · `insert_order`(ON CONFLICT DO NOTHING)로 멱등 · 손절선 사건·커서는 건드리지 않는다 · 읽기 속도 상한(1초 단위 sleep) · `.gz` 같은 결과. 기동 경로 밖(K1·K2 그대로). **운영 적재는 10-13 배포와 분리**(사람이 장외 창에 1회) | K6~K9 · W9c · W9d · pg K10(워커 역할로 두 번 → 145행 그대로) |
| 9 (낮음) | `create_pool(dsn, min_size=…, max_size=…)` 명시, 1 ≤ min ≤ max ≤ 2(run·backfill 둘 다) | W9 · W9b |
| 10 (낮음) | Dockerfile 마지막 `USER` = root·0 이 아닌 사용자, 빌드 단계(RUN·COPY) 뒤·ENTRYPOINT 앞. 빌드 문맥 `journal_worker/.dockerignore` = `tests`·`ops`·`__pycache__`·`*.pyc`·`.env*` 를 빼고 `jw/`·`requirements.txt`·`Dockerfile` 은 남긴다. ⚠️ 배포 전 확인: 호스트 `~/auto_stock/logs` 파일을 그 uid 가 읽을 수 있어야 한다(로그 파일 권한이 644 가 아니면 워커가 로그를 못 읽는다) | I9 · I10 |
| 11 (낮음) | `ops/role.sql` 예시 = `PW=$(openssl rand -hex 24)` 로 변수에 먼저 담고 `-v journal_pw="$PW"` — 같은 값을 `secrets/journal_worker.env` 의 `JOURNAL_DATABASE_URL` 에 넣는다(base64 의 `/`·`+`·`=` 는 DSN 을 깬다) | I11 |

- 테스트 도우미(`jw_testkit.py`) — `FakeJournalDB`(047 의 UNIQUE·NOT NULL 을 흉내 내는 가짜 DB, `trades_since` 는 `timestamp >= since` 만) · `retained_bytes`/`reachable_ids`(객체 그래프 크기·도달 집합, 클래스·모듈·함수·로거 제외) · `ORDER_KEYS`·`ORDER_NOT_NULL`·`STOP_KEYS`.
- 충족 가능성 — Red 가 scratchpad 시제품(리포 밖)으로 워커 테스트 전부와 pg K10 통과를 확인했다(M1 보관 크기 500·2000·5000 회전 모두 같은 값).

---

## 7. 보완 결정 2 (10-09 — 직전 판정 「보완 필요」 N1·N1-b·N2~N8, 메인 세션 결정: 전부 고친다)

번호는 판정 원문 그대로다. 6절과 같은 금기(8영역·`scheduler.py`·기존 마이그레이션 0줄 · 047 NOT NULL 그대로 · 워커 `src` import 0·KIS 0·`.env` 0)가 그대로 선다. backfill 운영 적재는 여전히 10-13 배포와 분리. 테스트가 정본이다.

### N1 (중간) 대사가 로그를 앞질러 실측 행을 빈 행으로 선점한다

- **대사 기준 시각 W** = 「행까지 쓴 로그 줄의 시각」 — 이번 회전 `drain` 이 내보낸(= 직전 회전에 읽은) 청크의 **마지막 줄 시각**. 줄 앞머리 `YYYY-MM-DD HH:MM:SS`(KST)를 읽는다 — **문법이 모르는 줄도 센다**(운영 로그는 스캔 루프 같은 줄이 끊임없이 찍힌다. 문법 줄만 보면 조용한 시간대에 W 가 멈춰 그날 마지막 주문들이 대사·항등식 밖에 남는다). 청크에 행이 0개여도 그 청크의 마지막 줄이 W 다.
- W 가 없으면(첫 기동·재시작 직후, 아직 행까지 쓴 청크가 없음) 대사를 건너뛴다. **읽기 창이 꽉 찬 회전(따라잡는 중)도 건너뛴다**(판정 지시 — 단 W 기준만으로 같은 효과가 나서 테스트로는 구별되지 않는다: 돌연변이 0건. 리뷰 항목).
- `rows_from_trade_history(…, now=W)` · `check_identities` 는 `ts ≤ W − RECONCILE_MIN_AGE_SECONDS(120)` 인 완료 줄·행만. 60초 간격은 그대로(벽시계).
- **승격** — `JournalDB.promote_order(row) -> bool`(단문 UPDATE 1개): 같은 키(`order_date, order_no, side`)의 행이 `source IN ('unmatched','external')` 일 때만, NULL 칸은 `COALESCE(기존, 새 값)` · 전략 `'unknown'` 은 빈 칸으로 보고 새 값 · `source` = 로그 행 것 · `ticker`·`noted_at`·키는 그대로 → `UPDATE 1` 이면 True. 이미 실측인 행·없는 키 → False(행 그대로). `insert_order` 는 `INSERT 0 1` 이면 True, `INSERT 0 0` 이면 False 를 돌려준다(SQL 은 그대로 DO NOTHING).
- 워커 쓰기 — 로그 행(`source` 가 `unmatched`·`external` 아님): `insert_order` False 면 `promote_order`. **항등식에 세는 것 = DB 에 실측 행이 있음이 확인된 키**: insert True · promote True · 둘 다 False(충돌 상대가 이미 실측 행 — promote 는 빈 행만 바꾸므로). 예외(어느 쪽이든)면 WARNING 후 세지 않는다. 즉 `INSERT 0 0` 은 그 자체로 쓴 행이 아니다 — 충돌 상대가 빈 행이면 승격이 성공해야만 센다. 대사 행(`unmatched`·`external`)은 예외만 아니면 일지 키에 넣는다(재시도 방지), 항등식에는 세지 않는다(C4 그대로).
- 테스트: `test_jw_reconcile_timing.py` N1a(주문 5분 뒤 첫 기동) · N1b(첫 기동 15:45 재생 8건) · N1c(6분 정지 뒤 재시작) · N1d(≈10MB 따라잡기 — 읽기 창 여럿) · N1e(승격) · N1f(승격 실패 = 세지 않음) · N1i(커서가 뒤로 간 채 재시작 — 이미 실측인 키는 센다) · `test_jw_db.py` B1·B7·B8·B8b · pg K11. 공통 단언 = 최종 행 `log_harvest` · 그 주문으로 빈 행 쓰기 시도 0 · `[journal_gap]` 0.
- 시험 장치: 대사가 도는 시험은 로그가 가짜 시계를 따라 자란다(`jw_testkit.LiveLog` + `heartbeats()` — 문법이 모르는 `src.engine.scanner` 줄 15초 간격). 그래서 정적 로그를 쓰던 W3·W3b·W3c 는 살아 있는 로그로 다시 썼다(W3 은 「첫 회전」 → 「행까지 쓴 첫 회전(둘째)」, W3c 는 외부 체결 1건이 `external` 행이 되는 것으로 대사가 실제로 돌았음을 확인).

### N1-b (N1 과 함께) 커서 저장 실패 → 같은 덩어리 재읽기로 거듭 집계

- 완료 줄과 행 모두 **(주문번호, side) 고유값**으로 센다(날이 바뀌면 비운다).
- 테스트: N1g(저장 실패 3회 + 접수 줄 없는 매수 1건 — 경고 값 `sell_done=1 sell_rows=1 buy_done=1 buy_rows=0 unknown_reason_sells=0`) · N1h(저장 실패 3회 + 정상 주문 — `[journal_gap]` 0).

### N2 (낮음) 어긋난 항등식이 60초마다 경고(하루 598줄)

- `[journal_gap]` 은 **직전 대사 결과와 값이 다를 때만** 1줄(ok → 어긋남으로 돌아온 경우 포함). 접두·형식은 3.5절 그대로.
- 테스트: N2(15분 동안 값 두 가지 → 정확히 2줄, 값 순서대로).

### N3 (낮음) 재시작·첫 기동 직후 거짓 경고 1회

- N1 의 W 규칙으로 없어진다. 테스트 = N1a·N1b·N1c·N1i 의 `[journal_gap]` 0.

### N4 (낮음) httpx 요청 줄 하루 약 6,600줄

- `python -m jw` 의 로깅 설정(`main()` 안)에서 `logging.getLogger("httpx")` 를 WARNING 으로. `jw.*` INFO 는 그대로. 테스트 = W10.

### N5 (낮음) 따라잡기 순간 메모리 ≈100MB(상한 160m 의 80%)

- `MAX_READ_BYTES = 4 * 1024 * 1024`(`read_chunk` 기본값도 같은 상수). 테스트 = T3b · N1d(한 회전 커서 전진 ≤ 4MiB).

### N6 (참고) 정리가 64개 넘을 때만 돌아 날을 넘겨 남음

- `Pairer` 는 날이 바뀌는 첫 이벤트에서 개수와 무관하게 대기 항목(사유 줄·신호 줄·종목상태 줄·접수 전문·짝 없는 완료 줄)을 TTL 로 정리한다. 테스트 = M5(종류마다 10개 — 다음 날 첫 이벤트 뒤 전날 시각 0개).

### N7 (참고) backfill 을 인자 없이 부르면 안내 없이 exit 2

- 종료 코드 2 + 표준 오류에 사용법(`backfill` 과 `usage`/`사용법`). DB 에 붙지 않는다(W9d 그대로). 테스트 = W11.

### N8 (참고) 실행 사용자가 자기 코드를 쓸 수 있다

- Dockerfile 에서 `chown` 을 없앤다 — COPY 한 코드는 root 소유 그대로, 실행 사용자(`journal`)는 읽기만. COPY `--chown`/`--chmod` 0 · `chmod` 는 쓰기를 빼는 것만 · 실행 사용자 홈이 `/app` 아님. 테스트 = I12(이어 쓴 줄 `\` 도 합쳐 본다). ⚠️ 배포 전 확인(6절 10 과 같음): 호스트 로그 파일을 uid 1000 이 읽을 수 있어야 한다.

### 충족 가능성

- Red 가 scratchpad 시제품(리포 밖, `jw/{main,db,config,pairing,__main__}.py`·`Dockerfile` 만 고친 사본)으로 워커 280 전부 통과(`--log-level=DEBUG` 포함) · pg K10·K11 통과(실 Postgres, 워커 역할)를 확인했다.
- 시제품 돌연변이 10종 — 벽시계 기준 → N1d · W 없을 때도 대사 → N1a·N1b·N1c·N1d·N1i · 승격 없음 → N1e·N1f · 승격 실패도 셈 → N1f · 완료 줄/행 중복 집계 → N1g·N1h · 경고 매번 → N2 · 엄격 집계(이미 실측=안 셈) → N1i · 날짜 경계 정리 없음 → M5 가 잡는다. 창 꽉 참 건너뜀 제거만 0건(위 N1 둘째 줄).
- 문서: `journal_worker/README.md` 의 「1회 상한 20MB」 는 Green/동기화 때 4MiB 로 고친다.

---

## 8. 마무리 (10-09 — 최종 판정 「배포 가능」 뒤 남은 낮음 N9·N10, 메인 세션 결정: 고친다)

번호는 판정 원문 그대로다. 6·7절의 금기가 그대로 선다. 047 스키마는 바꾸지 않는다(코드만으로 막는다). 이 절은 `/sync-docs` 가 시정 커밋 `a7db32a1` 의 코드·테스트를 옮겨 적은 것이다 — 테스트가 정본이다.

### N9 (낮음) 커서 저장 실패 뒤 재읽기로 `exit` 사건이 겹친다

- 원인 — `trade_journal_stops` 에는 UNIQUE 가 없다. 같은 덩어리를 다시 읽으면 같은 매도가 다시 drain 되고, `result["stops"]` 의 `exit` 가 검사 없이 또 들어갔다(저장 실패 3회 → `exit` 3행).
- 규칙 — `Worker._write_row(row) -> bool` 이 「이 회전에 실측 행을 **새로** 넣었거나 승격했는가」(`inserted or promoted`)를 돌려준다. 빈 행(`unmatched`·`external`)·예외·`INSERT 0 0` + 승격 False 는 False. `exit` 사건은 `inputs.sell_order_no` 가 그 회전에 True 를 받은 SELL 행의 주문번호일 때만 쓴다. 항등식 집계(7절 N1 「둘 다 False 도 센다」)는 그대로다.
- 테스트 = `test_jw_loop.py::test_n9_cursor_save_failures_do_not_duplicate_exit_stops`(저장 실패 3회 + 매도 1건 → `exit` 1행 · 매도 행 `log_harvest` 1개).

### N10 (낮음) 완료 줄과 행이 1초 벌어지면 기준선이 그 사이에 걸려 거짓 `[journal_gap]` 1줄

- 규칙 — `_cutoff_split(done_events, day_rows, cutoff) -> (kept_done, kept_rows)`(`jw/main.py`). 완료 줄과 행을 (주문번호, side) 로 짝지어 **두 시각 중 늦은 쪽**이 `cutoff`(= W − `RECONCILE_MIN_AGE_SECONDS`) 이하일 때 둘 다 남긴다. 짝이 없으면 자기 시각 그대로. `_reconcile` 이 `check_identities` 앞에서 이것을 쓴다. `rows_from_trade_history` 의 기준(`trade_history.timestamp ≤ W − 120초`)은 그대로다.
- 해소 로그 — 직전 결과가 어긋남이고 이번이 ok 면 INFO `[journal_gap_resolved] sell_done=… sell_rows=… buy_done=… buy_rows=… unknown_reason_sells=…` 1줄. 경고 규칙(7절 N2 — 값이 바뀔 때만 1줄)은 그대로다.
- 테스트 = `test_jw_reconcile_timing.py` `test_n10a_*`(짝 있는 주문은 경계 −3~+3초 전 위상에서 함께 남거나 함께 빠짐 · 짝 없는 줄은 자기 시각) · `test_n10b_*`(`_reconcile` 실제 경로, 경계가 두 시각 사이 → `[journal_gap]` 0) · `test_n10c_*`(WARNING 1줄 뒤 해소 INFO 1줄).

---

## 9. 마무리 2 (10-09 — 「머지·배포 가능」 판정 뒤 마지막 손질 N11, backend-dev 결정: 고친다)

번호는 판정 원문 그대로다. 6·7·8절의 금기가 그대로 선다 — 8영역·`scheduler.py`·마이그레이션 0줄, 워커 `src` import 0. 테스트가 정본이다.

### N11-a (낮음) 날짜 경계에서 `_last_reconcile_result` 를 비우지 않아 거짓 `[journal_gap_resolved]`

- 원인 — `_roll_day` 가 날짜별 집계(`_done_events`·`_day_rows`·`_journal_keys` 등)는 비우면서 `_last_reconcile_result` 는 그대로 둔다. 미해소 gap(`ok=False`)을 안고 날이 바뀌면, 다음 날 첫 대사는 그날 사건이 없어 trivially `ok=True` 인데, `_reconcile` 의 비교 대상이 여전히 전날의 `ok=False` 라 "어긋남이 풀렸다"로 오판해 거짓 `[journal_gap_resolved]` INFO 1줄을 남긴다.
- 규칙 — `_roll_day(now)`: 날짜가 바뀌는 순간, 비우기 **전에** `self._last_reconcile_result` 가 있고 그 값이 `ok=False` 였으면 `[journal_gap_unresolved_at_rollover] day=… sell_done=… sell_rows=… buy_done=… buy_rows=… unknown_reason_sells=…` WARNING 1줄(그 날의 마지막 값 — 운영자가 "하루가 미해소로 끝났다"를 알 수 있게). 그 뒤 `self._last_reconcile_result = None`. 전날이 이미 `ok=True` 였으면 경고 없이 비우기만 한다. 첫 기동(`self._day is None`)은 이 경고 대상이 아니다.
- 테스트 = `test_jw_reconcile_timing.py::test_n11a_roll_day_warns_and_clears_unresolved_result`(미해소 상태 → 경고 1줄 + None) · `test_n11a_roll_day_is_quiet_when_prior_day_was_ok`(ok 상태 → 경고 0 + None) · `test_n11b_reconcile_does_not_falsely_resolve_across_day_rollover`(`_reconcile` 실제 경로 — 1일차 미해소 → `_roll_day` → 2일차 trivially ok 대사에서 `[journal_gap_resolved]` 0).

### N11-b (낮음) `JournalDB.fill_order_division` 호출 0곳 — 행을 쓴 뒤 온 접수 통보의 주문구분이 NULL 로 남는다

- 원인 — 보류 중(같은 회전 안)에 도착한 `[order_notice]` 는 `Pairer._finalize` 가 `self._order_notices` 에서 읽어 `order_division` 을 채우지만(3.3절, Q7), 한 회전 보류가 끝나 행이 이미 DB 에 쓰인 **뒤**에 도착한 통보는 어디서도 다시 그 행을 보지 않는다. `jw/db.py::fill_order_division` 은 1절의 예외(`UPDATE … WHERE order_division IS NULL`)를 구현해 두고도 jw/ 안에서 부르는 곳이 없었다.
- 규칙 — `Worker.rotate()` 가 그 회전에 읽은 `events` 를 훑을 때, `kind=="order_notice"` 이고 `rctf=="0"`(최초 확정)이고 `division` 이 있으면 `_fill_division(e)` → `self.db.fill_order_division(e["ts"] 의 KST 날짜, e["order_no"], e["side"], e["division"])`. **보류 중인 행이든 이미 쓰인 행이든 똑같이 부른다** — 빈 칸만 채우는 쪽은 DB 쪽 `WHERE order_division IS NULL` 이 지키므로(M4, pg 통합 테스트), 보류 중 경로(Pairer)와 겹쳐 불러도 덮어쓰지 않는다. 행 단위 예외 격리(`_fill_division`)는 `_write_row` 와 같은 규약 — 통보 1건 실패가 그 회전의 다른 처리를 막지 않는다(WARNING `[journal_write_error] division order_no=… side=… …`).
- 테스트 = `test_jw_loop.py::test_n11_late_order_notice_fills_division_after_row_already_written`(SELL 행이 2회전째 `log_harvest` 로 쓰인 뒤, 3회전째 읽은 늦은 `[order_notice]` 가 그 행의 `order_division` 을 NULL → `"01"` 로 채운다).
