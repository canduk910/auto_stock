# cycle404 명세 — 계좌 묶음 배정 기록 (계좌 차원 묶음 쏠림 장치 1단계)

- 작성: team-leader · 2026-10-03 · 사용자 결정 10-03 「모두 권고대로」
- 근거 자문: `_workspace/domain_consult/cycle400_account_risk_budget.md` (R1~R5 · 부기)
- 이 사이클 = 자문 R4 표의 **단계 0**(묶음 배정 기록, 1주). 섀도(단계 1)·enforce(단계 2)·계좌 SOFT block 6.0(D4)·칸 조정(D5)·kojiro 섹터 캡(D6) 은 **범위 밖**.
- **행위 변경 0** — 매수 차단·수량 변경·신호 변경 없음. 읽기(DB SELECT) 와 로그 쓰기만.

---

## 1. 무엇을 하나

매일 아침 부팅에서 전략 `prepare` 와 포지션 복구가 끝난 뒤, 한 번:

1. 대상 종목 = **보유 종목 전부**(`registry.all()` 의 `state.positions` — 꺼진 전략 보유 포함) ∪ **켜진 전략의 후보**(`registry.enabled()` 중 `_candidates` 가 dict 인 전략의 키). `_candidates` 가 없는 전략(momentum·VB)은 후보 기여 0 이고 요약에 그 사실을 남긴다.
2. 종목마다 업종 ETF 요인(§3 목록) 과 KODEX 200(`069500`) 에 대한 120일 일간수익률 상관을 잰다.
3. 배정 규칙(§2) 으로 종목 → 묶음(요인 이름) 또는 `market` / `independent` / `missing` 을 정한다.
4. 묶음별로 보유 유닛·명목·명목 비중·「다음 매수가 막혔을까」(would-be) 를 계산해 `system_logs` 에 **WARNING** 으로 남긴다(§5).
5. 배정표(ticker → 묶음)를 모듈 메모리에 그날 고정해 둔다(읽기 접근자만, 이번 사이클엔 소비처 0).

## 2. 배정 규칙 (자문 R2 안 C — 사전 등록, 섀도 판정 전 변경 금지)

상수(leaf 모듈 한 곳, 파라미터로 열지 않는다):

| 이름 | 값 | 뜻 |
|---|---|---|
| `WINDOW_RETURNS` | 120 | 일간수익률 개수(종가 121봉) |
| `MIN_OVERLAP` | 100 | 종목·요인·시장 세 시계열의 **날짜 교집합** 수익률 개수 하한 |
| `CORR_MIN` | 0.60 | 요인 상관 하한 |
| `MARKET_MARGIN` | 0.03 | 요인 상관이 KODEX 200 상관보다 이만큼 이상 높아야 함 |
| `MARKET_TICKER` | `"069500"` | KODEX 200 |

- 수익률 = `close_t / close_{t-1} − 1`, `bas_dd` 로 정렬·정합(날짜가 빠진 날은 그 쌍의 수익률을 만들지 않는다). 상관 = 피어슨. 표준편차 0 → 그 쌍 상관 없음(None).
- 판정 순서(결정적):
  1. 종목 봉 부족(교집합 < `MIN_OVERLAP`) → `missing`
  2. 시장 상관 `m` 계산 불가 → `missing`
  3. 요인 중 상관 최대 `b`(동률은 §3 목록 순서상 앞의 것). 계산 가능한 요인이 하나도 없으면 `b=None`
  4. `m ≥ CORR_MIN` 이고 (`b is None` 또는 `m ≥ b`) → `market`
  5. `b ≥ CORR_MIN` 이고 `b − m ≥ MARKET_MARGIN` → 그 요인 이름
  6. 그 밖 → `independent`
- `market` · `independent` · `missing` 은 **묶음이 아니다**(유닛을 세지 않는다 = fail-open 방향).
- 요인 ETF 자체의 봉이 부족하면 그 요인은 그날 후보에서 빠지고 `[account_cluster_map]` 에 `factor_missing=` 로 남는다. **시장(069500) 봉이 부족하면 그날 배정 전체를 건너뛴다**(`[account_cluster_unavailable]` WARNING, 배정표 빈 상태).
- 판정은 하루 한 번 고정. 장중 재계산 없음(재시작 시 같은 입력이라 같은 결과 — 부팅 금지창 20:00 이후 재계산 없음).

## 3. 업종 ETF 요인 목록 (사전 등록)

> domain-expert 확정본으로 채운다 — `_workspace/domain_consult/cycle404_factor_etf_list.md`. 조건: 10~15개 · 각 ETF 가 `stock_master_daily` 에 121봉 이상 있음(10-03 실측) · 일봉 적재 대상(지수·자격·보호)에 계속 들어갈 근거. 목록 순서 = 동률 판정 순서.

(확정 목록 표: `ticker · 요인 이름(마커에 쓰는 짧은 이름, 공백 없음) · 적재 대상 근거`)

## 4. 유닛·명목·would-be (자문 R1 — 사전 등록)

| 이름 | 값 | 뜻 |
|---|---|---|
| `CLUSTER_CAP_U` | 4 | 묶음 유닛 상한 |
| `CLUSTER_CAP_PCT` | 20.0 | 묶음 명목 ÷ 순자산 상한(%) |
| `ACCOUNT_CAP_U` | 18 | 계좌 이름 수 안전판 |

- 유닛: 보유 1종목 = 1U(피라미딩 없음). 같은 종목을 두 전략이 들고 있을 수 없으므로(`is_ticker_blocked_for_buy`) 종목 수 = 유닛 수.
- 명목 = `buy_price × quantity`(메모리, I/O 0). 분모 = 부팅 `summary.net_asset`(0 이하이면 명목% = None, would-be 의 명목 축은 판정하지 않음).
- `would_block_next` (묶음별) = `held_u ≥ CLUSTER_CAP_U` **또는** `notional_pct ≥ CLUSTER_CAP_PCT` → 1, 아니면 0. 「이 묶음 후보가 지금 BUY 를 내면 섀도에서 막혔을 것」 의 뜻이다(기록만).
- `account_over` = 계좌 보유 유닛 합 ≥ `ACCOUNT_CAP_U` → 1.

## 5. 마커 (전부 never-raise · `system_logs` 영속을 위해 WARNING)

`system_logs` INFO 는 2일, WARNING+ 는 30일 보관이다(`src/db/system_logs.py:32-33`). 단계 1 섀도 판정(20영업일 ≈ 28일)까지 남기려면 WARNING 이어야 한다(자문 부기). 정상 동작인데 WARNING 인 이유를 메시지 첫머리에 `기록 전용` 으로 적는다.

1. `[account_cluster_assign] summary` — 1행/부팅:
   `mode= date= phase=boot net_asset= held_u= account_cap_u=18 account_over= targets= clustered= market= independent= missing= factor_missing= cand_sources=sid:n,... elapsed_ms=`
2. `[account_cluster_assign] cluster=<요인>` — 묶음(보유 또는 후보가 1개 이상 배정된 요인)마다 1행:
   `held_u= cap_u=4 notional= notional_pct= cap_pct=20 would_block_next= held=<ticker:sid:corr>,... cand=<ticker:sid,...>(최대 40개, 넘으면 +N)`
3. `[account_cluster_assign] group=market|independent|missing` — 각 1행: `held=<ticker:sid>,... cand_n=` (보유는 전부, 후보는 개수만)
4. `[account_cluster_unavailable] reason=` — 시장 봉 부족 · 예외 · 타임아웃 · 레지스트리 없음. WARNING 1회/부팅.
5. `[account_cluster_mode] value=<원문> effective=<off|record> reason=` — 키 값이 `record`/`off`/부재가 아닐 때만 WARNING(아래 §6).

숫자 형식: 상관 소수 2자리, 명목% 소수 1자리, 명목 원 단위 정수.

## 6. 계좌 키 `account_cluster_mode` (자문 R4 킬스위치)

- 저장 = `system_config` 키 `account_cluster_mode`, JSONB `{"value": str}`(기존 `_get_string_or_none` 형식). **전략 `params` 에 넣지 않는다**(계좌 통제는 전략 소유가 아니다). `PARAM_RANGES`·`INT_PARAMS`·`DEFAULT_PARAMS`·AI 자문 자동 적용 경로 편입 금지.
- 해석(부팅 시 1회 읽기):
  | 키 값 | 동작 |
  |---|---|
  | 부재 | `record` (사용자 지시: 기본 record — 행위 변경 0 이라 「없으면 기록」 이 안전) |
  | `"off"` | 아무 것도 계산·기록하지 않음(INFO 1행 `[account_cluster_assign] mode=off skip`) |
  | `"record"` | 기록 |
  | `"shadow"`·`"enforce"` | **이번 사이클 미구현** → `record` 로 동작 + `[account_cluster_mode]` WARNING(`reason=not_implemented`) |
  | 그 밖(오타·비문자열) | `record` + WARNING(`reason=invalid`) |
  | DB 조회 실패 | `record` + WARNING(`reason=read_error`) |
- 이번 사이클에 PUT 라우트·DB 행 생성 없음(DB 쓰기 금지). 끄려면 운영자가 키를 `"off"` 로 넣고 다음 부팅부터.

## 7. 배선 (자문 R5 · 사용자 제약)

- **새 leaf 모듈** `src/engine/account_cluster.py`. import 허용 = 표준 라이브러리 · `src.db.stock_master_daily`(`get_recent_daily` — DB 전용, KIS 폴백 없는 함수) · `src.db.system_config`(읽기) · logging. **금지** = `src.api.*`(KIS 호출 0) · `scheduler` · `risk` · `order_engine` · `strategy_registry` · `session` · `scanner` · `src.realtime.*` · `src.auth.*`. 레지스트리는 인자로 받는다(duck typing: `.all()` · `.enabled()`).
- 순수 함수와 I/O 를 나눈다: `assign_one(...)`(순수) · `summarize(...)`(순수) · `async run_boot_assign(registry, net_asset)`(I/O) · `spawn_boot_assign(scheduler_or_registry, net_asset)`(await 없이 task 생성, 모듈 전역 강한 참조 집합 · done 시 자기 제거 — `funnel_capture._BG_TASKS` 선례).
- **부팅 훅 = `src/engine/boot_manager.py` 한 곳**, 포지션 복구 뒤(= prepare 뒤). 위치 = `_fc.spawn_funnel_boot_vs_evening(...)` 바로 뒤. 호출은 **await 없이** spawn 만 하고 `try/except Exception` 으로 감싼다(부팅을 막지 않는다). 순자산은 `summary.net_asset` 을 넘긴다.
- task 는 시작 후 `INITIAL_DELAY_SECS`(30초, 테스트 seam) 기다린 뒤 실행 — 부팅 직후 WS 연결·첫 틱 처리와 DB 풀 경합을 피한다. 전체 상한 `RUN_TIMEOUT_SECS`(120초) — 넘으면 `[account_cluster_unavailable] reason=timeout`.
- 보유·후보 스냅샷은 task 실행 시점에 메모리에서 읽는다(`dict(...)` 사본, 순회 중 변경 안전).
- 일봉 읽기: 종목·요인·시장마다 `get_recent_daily(ticker, 121)` 1회. 동시성 상한 `READ_CONCURRENCY`=4(세마포어). 요인·시장 시계열은 1회만 읽어 재사용.
- **무접촉** = 8영역(`risk`·`order_engine`·`session`·`scanner`·`strategy_registry`·`src/api/order.py`·`src/realtime/**`·`src/auth/**`) · `scheduler.py` · `strategy_base.py` · 전략 파일 전부 · `_apply_budget_limit` · 매수·청산 경로. 매매 hot path(틱·신호·주문) I/O 0.
- **never-raise**: `run_boot_assign`·`spawn_boot_assign` 및 task 본체는 어떤 예외도 밖으로 내지 않는다(`CancelledError` 는 다시 던져도 된다). 종목 하나의 읽기·계산 실패 → 그 종목 `missing`, 나머지 계속.

## 8. 사전 등록 — 다음 단계 판정 기준 (이 사이클은 기록만, 기준은 지금 고정)

자문 R4 를 그대로 옮긴다. 결과를 보고 바꾸지 않는다.

- 단계 0 → 1 이행: 배정 기록 **1주(5영업일)** 뒤 사용자 결정.
- 단계 1(섀도) 기간: **20 영업일 이상 그리고 `would_block` ≥ 10건**, 둘 다.
- enforce 판정:
  1. 알파 손실 — would_block 매수의 실현 R 평균 − 통과 매수 실현 R 평균 ≥ **0.3R** → enforce 안 함(상한 올려 재섀도)
  2. 목조르기 — BUY 신호 중 would_block 비율 > **25%** → enforce 안 함
  3. 분류 안정성 — 종목별 묶음 배정이 20일 중 바뀐 날 비율 중앙값 ≤ **10%**, 넘으면 margin 키우고 재섀도 (← 이번 사이클 기록이 이 지표의 원천이다)
  4. 갭 실증 — 묶음 내 2종목 이상 같은 날 −5% 이하 마감일의 묶음 명목 × 낙폭 기록(증거, 통과 조건 아님)
  5. 1·2 통과 → 사용자 승인 후 enforce. enforce 후 20 영업일마다 1·2 재측정.
- 상한 값: 묶음 4U · 순자산 20% · 계좌 18U(§4). kojiro·BFB 칸 증설은 enforce 뒤(D5). kojiro 섹터 캡 무접촉(D6).

## 9. 테스트 요구 (tdd-engineer Red)

1. **순수 배정** — 합성 시계열: (a) 요인 최대 ∧ ≥0.60 ∧ 시장+0.03 → 그 요인 (b) 요인 0.62 · 시장 0.60(차 0.02) → `independent` (c) 교집합 99 → `missing` (d) 시장 최대 ∧ ≥0.60 → `market` (e) 시장 최대지만 < 0.60, 요인도 < 0.60 → `independent` (f) 동률 → 목록 앞 요인 (g) 표준편차 0 요인 → 후보 제외 (h) 날짜 어긋남(한쪽에만 있는 날) 정합.
2. **실측 고정 픽스처** — 10-03 보유 13종목 + 요인 ETF + 069500 종가(domain-expert 추출 `tests/fixtures/cycle404_cluster_closes.json`)로 자문 §3 표 재현: 반도체 묶음 = 232140·101160·083450·046890·011790·425040, 005930 = `market`, 나머지 6 = `independent`. (확정 목록에서 반도체 요인 이름이 무엇이든 그 6종목이 같은 묶음)
3. **요약** — held_u·notional·notional_pct·would_block_next 경계(3U/4U, 19.9%/20.0%), net_asset 0 → 명목 축 미판정, account_over 경계 17/18.
4. **모드 해석** — §6 표 전 행(부재·off·record·shadow·enforce·오타·비문자열·조회 예외).
5. **never-raise** — 일봉 읽기 예외(종목 하나 / 시장) · 레지스트리 `.all()` 예외 · 타임아웃 → 예외 전파 0, 해당 마커.
6. **마커** — summary·cluster·group 행이 WARNING 이고 prefix 정확, 목록 상한 40 / `+N`, `off` 일 때 WARNING 0.
7. **부팅 배선** — `boot_manager.boot` 가 포지션 복구 뒤 spawn 을 await 없이 1회 부른다 · spawn 예외가 부팅을 막지 않는다.
8. **AST 가드** (`tests/unit/ast/test_cycle404_ast_account_cluster.py`)
   - leaf import 금지 목록(§7) 0건
   - `src/engine/strategies/*.py`·`strategy_base.py`·`risk.py`·`order_engine.py`·`scheduler.py`·`strategy_registry.py` 가 `account_cluster` 를 import 하지 않는다(이번 사이클 소비처 0 = 행위 변경 0 봉인. 단계 1 에서 이 가드를 의도적으로 고친다)
   - `account_cluster_mode` 가 `PARAM_RANGES`·`INT_PARAMS`·어느 전략 `DEFAULT_PARAMS` 에도 없다
   - leaf 안 `src.api`·KIS 호출 0, `get_recent_daily_with_fallback`·`get_recent_daily_normalized` 미사용(KIS 폴백 경로 차단)
   - `boot_manager.py` 의 호출이 `await` 가 아니다(spawn)
9. 8영역·`scheduler.py` 기존 sha 핀 테스트 전부 초록(무접촉 증명).

## 10. 범위 밖 (후속 — 워크리스트에만)

- 단계 1 섀도 게이트(`StrategyBase` 헬퍼 · 전략 BUY 직전 호출 · `[account_cluster_cap]`)
- KIS 대분류 관측 `[account_sector_watch]` · 계좌 이름 수 `[account_names_cap]` 별도 마커
- `account_cluster_mode` PUT 라우트(즉시 반영)
- 섀도 20영업일 판정이 30일 보관창에 빠듯함(20영업일 ≈ 28일 + 연휴) — 단계 1 착수 때 일일 집계 테이블 여부 결정
