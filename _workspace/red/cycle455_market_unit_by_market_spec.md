# cycle455 — 시장 유닛: 종목 소속 시장별 판정 + 원천을 종합지수로 (명세)

- 사용자 결정 2026-10-14 밤: 「시장유닛 코스닥도 적용하자」 → 방식 B(소속 시장별 집행) · 코스닥 원천 = 코스닥 종합지수 새로 적재 · 코스피 원천 = 코스피 **종합**지수(「종합지수가 좀 더 대표성이 있지 않아?」 — 처음 설계 cycle376 의 검증 원천도 `^KS11` 종합지수였고 069500 은 운영 편의 대용이었다).
- 자문 = `_workspace/domain_consult/2026-10-13_market_unit_kosdaq.md`(B 의 실무 쟁점·후속 검증 §B·§195~198) + `cycle376_market_unit.md` §3.6.
- 매매 행위 변경(진입 수량·진입 여부) — 사용자 승인 완료. 8영역·`scheduler.py` **무접촉**.
- 번호: cycle455 · migration 053(클라우드 세션이 052 까지 사용).

## 1. 바뀌는 행위 (한 문단)
터틀 4전략(`kojiro`·`donchian_swing`·`bull_flag_breakout`·`vcp_breakout`)의 시장 유닛 배수 m 을 **종목마다** 정한다. 종목의 소속 시장(`stock_master.excg_dvsn_cd`: `"03"` = 코스닥, 그 밖·미상 = 코스피)에 따라 코스피 종목은 **코스피 종합지수(KIS 업종 `0001`)**, 코스닥 종목은 **코스닥 종합지수(`1001`)** 일봉 종가로 같은 4단계 판정(`market_unit.classify`, 60일선 위치·기울기, 배수 1/0.75/0.5/0)을 한다. 판정식·배수·모드(`off|shadow|enforce`)·설계 랏·관문·마커 의미는 그대로다. 069500(KODEX 200) 은 더 이상 시장 유닛 원천이 아니다(다른 소비처 `market_regime` ETF 스테이지·`market_regime_label` 화면은 무접촉).

## 2. 결측 규칙 (fail-open 유지, 자문 §145 + 대칭)
- 종목 시장의 스냅샷이 `ok` → 그 m.
- 아니면 **다른 시장 스냅샷이 `ok` 면 그 m**(코스닥 결측 → 코스피 배수, 코스피 결측 → 코스닥 배수). 🔴 「한쪽 결측 → 그 시장 종목만 m=1」 금지 — 약세장에서 결측 쪽만 풀배수로 열린다.
- 둘 다 아니면 m=1.0(현행 fail-open). 
- 종목 → 시장 해석 실패(지도에 없음·지도 미적재·예외) = 코스피.
- `ticker=None` 으로 묻는 호출(etf_trend · 섀도 마커 · donchian 1931행 등 기존 무인자 호출) = 코스피 판정(지금의 "시장 하나" 의미 보존).

## 3. 데이터 — 새 테이블·KIS 래퍼·적재
### 3.1 migration `053_domestic_index_daily.sql` (가산형)
`domestic_index_daily(index_code text, bas_dd date, close_price numeric NOT NULL, raw jsonb NOT NULL DEFAULT '{}', updated_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(index_code, bas_dd))`. 모양은 `048_overseas_index_daily.sql` 을 따른다(그 파일을 읽고 같은 관례 — IF NOT EXISTS 등).
### 3.2 DB 모듈 `src/db/domestic_index.py` — `src/db/overseas_index.py` 와 같은 모양
`upsert_many(index_code, rows: list[tuple[str(YYYYMMDD), float]], *, raw_by_date=None) -> int`(예외 = 0 + logger.exception) · `get_recent_closes(index_code, *, limit) -> list[tuple[date, float]]` 오름차순 · `max_bas_dd(index_code) -> date|None` · `count(index_code) -> int`. 상수 `TABLE_NAME`.
### 3.3 KIS 래퍼 `src/api/domestic_index.py`
- TR `FHKUP03500100` · path `/uapi/domestic-stock/v1/quotations/inquire-daily-indexchartprice` · params `FID_COND_MRKT_DIV_CODE="U"`, `FID_INPUT_ISCD=<코드>`, `FID_INPUT_DATE_1/2=YYYYMMDD`, `FID_PERIOD_DIV_CODE="D"`. **1회 최대 50봉, 연속조회(tr_cont) 불가** → 기간을 쪼개 받는다.
- `kis_get_quote` 경유(시세 풀). path 를 `src/api/base.py::_QUOTE_ALLOWED_PATHS` 에 추가(주석 한 줄).
- `fetch_index_daily(index_code, start: date, end: date) -> list[tuple[str, float]]`(output2 의 `stck_bsop_date`·`bstp_nmix_prpr`, 0 이하·비수치 행 버림, 날짜 오름차순, 중복 제거) — 한 번 호출. `fetch_index_daily_history(index_code, end: date, min_rows: int) -> list[...]` = end 부터 과거로 50봉 창을 내려가며 `min_rows` 를 채울 때까지(상한 6회, 창 사이 `asyncio.sleep(0.2)`). 응답 0행이면 멈춘다. 실측(2026-10-14): `0001` 종합 · `1001` KOSDAQ · `2001` KOSPI200 모두 rt_cd=0, 50행, 최신 먼저.
- 예외는 호출자에게 올린다(적재 leaf 가 흡수).
### 3.4 적재 leaf `src/engine/domestic_index_ingest.py`
- 상수 `INDEX_CODES = {"kospi": "0001", "kosdaq": "1001"}` — 🔴 단일 정본(market_unit 이 여기서 읽거나, market_unit 에 두고 이 모듈이 import — 둘 중 하나만. 권장: `market_unit.INDEX_CODE_BY_MARKET` 를 정본으로, ingest 가 import).
- `async ensure_fresh(*, now_kst=None) -> dict` — never-raise(`CancelledError` 만 전파). 시장마다: DB 행 수 < `TARGET_ROWS`(130) 이면 `fetch_index_daily_history(code, end=오늘, min_rows=130)` 전체 적재, 아니면 증분 `fetch_index_daily(code, start=max_bas_dd−7일, end=오늘)`. **오늘 봉은 15:40 KST 이전이면 버린다**(장중 미확정 — 지수는 정규장 종가로 확정, 애프터마켓 영향 없음). upsert 후 요약.
- 마커 `[domestic_index_ingest] phase= kospi_rows= kospi_head= kosdaq_rows= kosdaq_head= fetched= upserted= failed= elapsed_ms=` 실행당 1행(실패 있으면 WARNING, 아니면 INFO).
- import 제약: 8영역·`scheduler`·`src.realtime`·`src.auth` import 0.
### 3.5 배선 (scheduler.py 무접촉)
- **부팅**: `boot_manager.boot()` 에서 `daily_bar_finalize.wait_for_boot(...)` 바로 **뒤**·`emit_daily_head_staleness()` **앞**에 `await asyncio.wait_for(domestic_index_ingest.ensure_fresh(phase="boot"), timeout=BOOT_INDEX_BUDGET_SECS)`(20초) — 예외·타임아웃 흡수 + WARNING. prepare(시장 유닛 계산)가 그 뒤라 오늘 아침 판정이 전날 종가 지수를 본다.
- **저녁**: `data_load_tasks.stock_master_daily_load_task_loop` 의 `once_callable` 을 `_financial_load_with_extras` 와 같은 합성 패턴으로 — 일봉 적재(`scanner._stock_master_daily_load_once`, 호출 시점 모듈 속성) 뒤 `ensure_fresh(phase="evening")`(흡수). 반환·요약 서식은 일봉 적재 것 그대로. 21:00 저녁 미리보기가 그날 지수 봉을 본다. 🔴 일봉 적재 성공 마커 시점 바뀜 주의(지수 적재까지 끝난 뒤 찍힘 — 수 초).

## 4. 판정 leaf `src/engine/market_unit.py`
- `SOURCE_TICKER` 제거 → `INDEX_CODE_BY_MARKET = MappingProxyType({"kospi": "0001", "kosdaq": "1001"})` · `MARKETS = ("kospi", "kosdaq")` · `MARKET_OF_EXCG = {"03": "kosdaq"}`(그 밖 kospi).
- `compute_snapshot(as_of_date, *, preview, market="kospi") -> Snapshot` — 원천만 `src.db.domestic_index.get_recent_closes(INDEX_CODE_BY_MARKET[market], limit=FETCH_ROWS)`(함수 안 지연 import, monkeypatch seam). 판정 순서·stale·`bad_close`·never-raise 그대로. `Snapshot` 에 `market: str` 칸 추가(기본값 없이 생성자 전부 갱신 — `_unavailable` 포함).
- `async load_market_map() -> dict[str, str]` — `stock_master` 의 `ticker → "kospi"|"kosdaq"`(1쿼리, `src.db.stock_master` 에 `get_excg_map()` 같은 헬퍼 추가 또는 `pg.fetch` 를 쓰는 DB 함수). never-raise(예외 = `{}`).
- `market_of(ticker, market_map) -> str` 순수(미상 = `"kospi"`).
- 순수 `classify`·`normalize_mode` 무변경.

## 5. `StrategyBase` (strategy_base.py — 8영역 아님)
- `_market_unit_snaps: dict[date, dict[str, Snapshot]]`(날짜 → 시장 → 스냅샷). 🔴 `routes/strategies.py` 모니터(`_market_unit_snaps[오늘]` 를 읽음, 650~700행)를 새 모양에 맞춘다: 응답 `market_unit` 은 기존 키(`mode`·`ok`·`m`·`state`·`bar_date`·`reason`)를 **코스피 값**으로 유지 + `by_market: {kospi:{…}, kosdaq:{…}}` 추가. 프론트 타입 `frontend/src/types/` 의 해당 타입에 `by_market?` 선택 칸 추가(표시 변경은 선택 — 최소 = 타입만).
- `_refresh_market_unit(*, as_of_date, preview)` — 두 시장 모두 `compute_snapshot(..., market=)` + `load_market_map()` 을 부르고(지도는 `self._market_unit_market_map` 에 보관, 비면 기존 지도 유지), 보존 규칙(`kept`)·과거 키 삭제·마커를 **시장별로**. 정확히 1회 호출 규약(AST A08)은 호출부 기준 그대로.
- `_market_unit_view(ticker: str | None = None) -> MarketUnitView` — 순수(`await`·DB 0, AST A05). §2 결측 규칙. `MarketUnitView` 에 `market`(판정에 쓴 시장)·`fallback`(`"-"`|`"other_market"`|`"none"`) 칸 추가.
- `_market_unit_sizing(price, ticker)`·`_market_unit_blocks_entry(ticker, price)` 는 `_market_unit_view(ticker)` 를 쓴다. 나머지(설계 랏·스킵 사유) 무변경.
- 마커: `[market_unit_state]` 의 `source=` 값 = 지수 코드(`0001`/`1001`) + ` market=` 칸 추가. `[market_unit] where=calc|signal` 끝에 ` market= fallback=` 추가. `[market_unit_unavailable]` 에 ` market=` 추가. `[market_unit_daily]` 는 전략당 1줄 유지하되 `state=`/`m=` 를 코스피 값으로 두고 ` kq_state= kq_m=` 추가(집계 숫자는 합산 그대로). 🔴 마커 서식 변경 = 배포 전후 로그 합산 금지(문서에 한 줄).
- 기존 무인자 호출부(etf_trend 187·742, donchian 1931, strategy_base 1817 섀도 마커)는 그대로 두면 코스피 판정 — 단 donchian 1931·섀도 마커처럼 종목이 손에 있는 자리는 `ticker` 를 넘기는 게 맞는지 확인하고, 넘기는 것이 의미상 맞으면 넘긴다(섀도 `[shadow_buy] m=` 는 종목 시장 기준이 맞다).

## 6. 문서 (같은 사이클)
루트 `CLAUDE.md` 「자금 관리」 시장 유닛 줄(KODEX 200 → 종목 소속 시장 종합지수) · `src/engine/CLAUDE.md` 모듈 맵 `market_unit.py`·새 `domestic_index_ingest.py`·`strategy_base.py` 시장 유닛 절·`boot_manager.py` 배선·`data_load_tasks.py` 합성 · `src/engine/strategies/CLAUDE.md` 「시장 유닛」 절 · `src/db/CLAUDE.md`(새 표·모듈) · `src/api/CLAUDE.md`(새 래퍼·허용 path) · 루트 DB 스키마 표에 `domestic_index_daily` 행 · `_workspace/00_leader_trading_rules.md` 시장 유닛 항목 · `docs/HARNESS_CHANGELOG.md` cycle455 행. 정본은 현재형만(history 규약).

## 7. 테스트 (Red 먼저)
- leaf: `compute_snapshot(market=)` 가 `domestic_index.get_recent_closes` seam 을 그 코드로 부른다 · 069500 미참조 · `market_of` · `load_market_map` 예외 → `{}`.
- view 결측 규칙 4칸: (kq ok, ks ok) · (kq 결측 → ks m) · (ks 결측 → kq m) · (둘 다 → 1.0), 지도 미상 → kospi, `ticker=None` → kospi.
- **같은 전략 같은 날 코스피 종목 m=0 · 코스닥 종목 m=0.75 가 동시에 선다**(자문 ③) — `_market_unit_blocks_entry` 가 코스피 종목만 True.
- 미리보기(다음 거래일 칸)와 오늘 칸이 시장별로 섞이지 않는다(자문 ④).
- 적재 leaf: 행 부족 → history 경로 · 충분 → 증분 · 15:40 전 오늘 봉 버림 · KIS 예외 흡수 + 마커.
- KIS 래퍼: 50봉 창 페이징·정렬·0 이하 버림·`_QUOTE_ALLOWED_PATHS` 포함.
- 배선: boot 순서(`wait_for_boot` < ensure_fresh < `emit_daily_head_staleness`) · 저녁 합성(일봉 예외여도 지수 적재 후 재발생 — financial 패턴과 동일).
- 기존 가드 갱신: `tests/unit/ast/test_cycle382_ast_market_unit.py`(A01 import 제약에 `src.db.domestic_index` 허용 · A02 상수 정본 · A05 순수 · A08), cycle382 단위 테스트 픽스처(`_cycle382_support.py`)가 069500 seam 을 쓰면 새 seam 으로. 모니터 라우트·AST(`test_cycle414_monitor_purity.py`) 회귀.
- 실 Postgres 통합: migration 053 적용 + upsert/조회 왕복(`tests/integration/` 의 overseas 선례 따라).
- 전체 스위트 초록 + `python tools/test_impact/build_index.py` 재생성(인덱스 낡음 = CI 실패 선례).
