# cycle350 — 저녁 funnel 캡처 A안: 착수 범위와 보류 (team-leader 명세, 2026-09-24)

사용자 결정(2026-09-24): 저녁 funnel 캡처 **A안** · `scheduler.py` 승인 포함 · 자율 구간 · 커밋·push 금지(메인 세션 몫).
규칙: 크리티컬 분기(매매 행위가 바뀌는데 판단 근거가 갈리는 경우)는 구현하지 않고 보류·선택지·권고를 반환한다.

## 0. 결론 먼저

| A안 항목 | 이 사이클 | 이유 (한 줄) |
|---|---|---|
| ① 저녁 캡처를 20:30 적재 뒤로 | **보류** | 전제가 코드와 다르다 — 6전략이 벽시계 「오늘」 날짜 봉을 잘라 20:4x 에 돌려도 여전히 D-1 기준(§2) |
| ② 스냅샷 날짜 = 다음 거래일 | **보류** | ①과 한 몸. 지금 코드로 D+1 라벨을 붙이면 D-1 목록에 D+1 이름표 = 거짓 정보 |
| ③-a 덮어쓸 때 `snapshot_at` 갱신 | **착수 (B1)** | 어느 선택지에서도 필요, 관측 전용, 매매 무관 |
| ③-b 잠정이 확정을 못 덮게 | **보류** | 단독 배포하면 평일 16:20 쓰기가 전부 거부돼 저녁 산출물이 조용히 사라진다 = 사실상 기능 끄기(승인 대상). ①② 결정과 같이 싣는다 |
| ④ 부팅 +600초 즉시 실행 신선도 게이트 | **보류** | 09-14·09-21(월) 실측 — 아침 보충 적재를 라이브 후보에 반영하는 **유일한 경로**다(§3). 사용자 지시의 보류 조건에 해당 |
| ⑤ 소비처 정합 | **착수 (B2, market_ops 만)** | B1 이 `snapshot_at` 뜻을 바꾸므로 그 값을 읽는 유일한 소비처를 맞춘다 |

- `scheduler.py` · `data_load_tasks.py` · `task_loop_helper.py` · 전략 7파일 · 8영역 **무접촉**. 마이그레이션 **없음**. 프론트 **무변경**.
- 바뀌는 코드 = `src/db/strategy_funnel.py`(B1) · `src/routes/market_ops.py`(B2). 둘 다 `src/` 라 배포 모드는 **full**(backend 재시작).

## 1. 09-21 VCP 7→5 원인 (사용자 지시 ④ 선행 확인) — EC2 파일 로그 + 코드

부팅 준비(`_boot` 안 전 전략 `prepare()`)는 `start()` 에서 **데이터 적재 태스크들을 만들기 전에** 끝난다(`scheduler.py` `start()` — `_boot()` 뒤에 `_full_universe_load_task`(+0초)·`_stock_master_daily_load_task`(+240초)·`_stock_master_basics_refresh_task`(+480초)·`_evening_funnel_capture_task`(+600초) 생성). 즉 아침 보충 적재가 무엇을 바꾸든 부팅 준비는 그 전 입력으로 끝나 있고, **+600초 재준비만 그 결과를 라이브 전략 객체에 반영한다.**

10거래일 실측(`auto_stock.log.2026-09-{10..23}`, 부팅 준비 → +600초 재준비):

| 날짜 | 아침 보충 적재 | VB | VCP (후보/유니버스) |
|---|---|---|---|
| 09-10 목 | 셋 다 건너뜀(신선) | 81→81 | 2/673 → 2/673 |
| 09-11 금 | 셋 다 건너뜀 | 55→55 | 2/708 → 2/709 |
| **09-14 월** | full_universe **fetched=2674** · 일봉 즉시 적재 · basics 시작 | **62→73** | **3/665 → 2/689** |
| 09-15~18 | 셋 다 건너뜀 | 같음 | 같음 |
| **09-21 월** | full_universe **fetched=2670**(07:53) · 일봉 즉시 적재(07:56~07:59) · basics 08:00:49~08:15:45 | **81→63** | **7/729 → 5/640** |
| 09-22·23 | 셋 다 건너뜀 | 같음 | 같음 |

- 09-21 은 VCP 유니버스 로그가 `818/1068` → `723/973`(시총 100억+ ∩ 거래대금 10억+) — full_universe 재적재가 `stock_master` 의 시총·거래대금 값을 KRX OpenAPI(09-18 기준)로 바꾼 결과다. 방향은 날마다 다르다(09-14 VB +11, 09-21 VB −18) = 편향이 아니라 **입력 갱신**.
- 월요일(주말 뒤)·연휴 뒤마다 `stock_master` 는 시스템 자신의 24h TTL 로 「낡음」 판정이라 부팅 직후 재적재된다. 저녁 적재가 실패한 다음 날도 같은 구조(부팅 준비 = D-2 봉, +240초 즉시 적재가 D-1 을 채움, +600초 재준비가 교정).
- 판정: **단순 재실행 중복이 아니다.** 평일 8일은 중복, 월요일 2일은 그날 실매매 후보를 바꾼 교정 경로다 → ④ 보류(§3).
- 곁가지(이 사이클 무접촉): 월요일 재준비(08:02:54)는 basics 보충(08:00:49~08:15:45) **도중**에 돌아 반쯤 갱신된 `stock_master` 를 읽는다.

## 2. 크리티컬 분기 #1 — A안의 전제가 코드와 다르다 (①②③-b 보류)

A안의 뜻 = 「20:30 에 그날 봉이 들어온 뒤 캡처하면 다음 거래일 후보를 미리 본다」. 그런데 funnel 을 내는 6전략이 전부 **벽시계 오늘(KST) 날짜의 봉을 버린다**:

`prev_idx = 1 if candles[0].get("stck_bsop_date") == today_str else 0` (`today_str = datetime.now(KST)`)
— `volatility_breakout.py:320` · `long_tail_volatility.py:341` · `donchian_swing.py:464` · `bull_flag_breakout.py:349` · `kojiro.py:382` · `vcp_breakout.py:442`

20:30 적재(`_drop_today_bars` 는 20:00 이후 오늘 봉을 **보존**)가 D 봉을 넣어도 20:4x 의 `prepare()` 는 D 봉을 잘라 **D-1 기준**으로 계산한다 = D 아침 목록과 같은 기준. 여기에 D+1 날짜를 붙이면 cycle349 가 경고한 거짓 라벨이 그대로 생긴다. 참이 되려면 prepare 에 「기준일」을 넣어야 하고, 그것은 전략 코드와 라이브 상태를 건드린다:

- A1 — `prepare(*, as_of=None)` 6전략 추가(기본 = 벽시계, 장중 경로 바이트 동일) + 저녁 캡처가 `as_of=다음 거래일` 로 **라이브 객체**를 준비. 20:4x~다음 부팅 사이엔 매매가 없고 다음 부팅이 같은 기준으로 다시 준비하므로 실매매 영향은 원칙상 0. 단 prepare 안의 보유 종목 갱신(BFB·kojiro `_apply_high_since_buy_from_candles`, kojiro `_held_stage3`, donchian `_update_trading_days` 캐시, `_bought_today.clear()`)과 모듈 전역 캐시가 기준일을 일관되게 따르는지 전수 감사가 선결. 21:30 정산의 메모리 기반 `strategy_funnel`(coarse) 지표도 D+1 상태를 읽게 된다.
- A2 — 격리 계산: 같은 파라미터의 별도 전략 인스턴스에 `as_of` 준비 → 그 funnel 만 캡처. 라이브 객체 무접촉. 규모 최대, prepare 가 쓰는 모듈 전역(예: `scanner.ticker_prev_close`)은 격리가 안 되므로 확인 필요.
- A3 — 「미리보기」 목표를 접는다: 16:20 재준비·캡처를 은퇴시키고(애프터마켓 중 라이브 재준비도 함께 사라짐) ③-b 보호만 싣는다. 가장 작다. 기능 끄기라 심층 검증 의무.
- 권고: **A1 을 domain-consult + prepare 부수효과 감사 후 착수.** 급하면 A3(보호 + 은퇴)를 먼저. 실매매 근거: 2026-08-01 이후 16:20~20:00 매수 **0건**(6전략), 매도 2건(kojiro 08-18 17:06 · donchian 09-01 18:09) — 16:20 재준비를 옮겨도 매수 쪽 영향은 실측상 0, 청산 쪽 2건은 원인 미확인.

③-b(보호)를 단독으로 싣지 않는 이유: 09:35 확정 캡처가 모든 `(오늘, 전략, 단계)` 키를 먼저 채우므로, 지금 일정(16:20·오늘 날짜)에서는 저녁 쓰기가 **평일마다 전부 거부**된다 → 저녁 산출물이 조용히 사라지고 `market_ops` 저녁 행이 매일 `not_fired` 로 보인다. 준비된 설계(착수 시 그대로): `ON CONFLICT … DO UPDATE SET … WHERE NOT (strategy_funnel_snapshots.is_provisional = FALSE AND EXCLUDED.is_provisional = TRUE)` — 거부되면 `RETURNING` 이 빈 → `insert_snapshot` 이 None → 저장 수에서 빠진다. 마이그레이션 불필요.

## 3. 크리티컬 분기 #2 — +600초 즉시 실행 게이트 (④ 보류)

- 4a 조건부 게이트: 아침 보충 셋(full_universe `fetched==0` · 일봉 즉시 실행 건너뜀 · basics 즉시 실행 건너뜀)이 **모두 아무것도 안 했을 때만** 건너뜀 → 평일 중복 제거 + 월요일 교정 보존. 태스크 간 신호가 필요하고, basics 가 +600초보다 늦게 끝나는 문제는 그대로.
- 4b **현행 유지(게이트 없음)** — 비용은 평일 07:56 전 전략 재준비 1회(≈1분, NXT 프리장 08:00 전). 월요일은 부팅 준비가 길어 08:02~08:03 에 돌아 **프리장 안**이다 — LTV `prepare` 가 `_targets`·`_open_confirmed`·`_prev_price` 를 비우므로(`long_tail_volatility.py:247-249`) 그동안 LTV 프리장 매수 평가가 빈다(청산 무관, 시가는 다음 틱에 다시 잡힘). ③-b 보호가 들어오면 07:57 잠정 행은 09:35 확정이 덮으므로 기록 오염도 없다.
- 교정은 순서 보장이 아니라 경합에 기댄다 — 재준비는 `count_all() > 0` 만 기다리고 +240초 일봉 보충 적재의 **완료**를 기다리지 않는다(09-21 은 07:59 에 끝나 우연히 맞았다). 4c 에서 함께 닫는다.
- 4c 구조 교정: 보충 적재를 부팅 준비 **앞**으로, 또는 보충 적재(basics 포함) **완료 뒤** 재준비 — 월요일 반쪽 입력 문제까지 닫는다. 월요일 실매매 후보의 시점이 바뀌므로 domain-consult 대상.
- 권고: **4b 지금, 4c 는 별도 사이클.** catch-up 이 쓰는 날짜 = 오늘(현행 그대로).

## 4. 착수 범위 — 행위 명세 (tdd-engineer Red 입력)

### B1 — `insert_snapshot` 이 덮어쓸 때 `snapshot_at` 을 갱신한다 (`src/db/strategy_funnel.py`)

- B1-1 같은 `(target_date, strategy_id, step_no)` 로 두 번째 호출하면 그 행의 `snapshot_at` 이 **두 번째 쓰기 시각**(DB `now()`)이 된다. 첫 INSERT 는 지금처럼 기본값 `now()`.
- B1-2 나머지 UPSERT 의미는 불변 — 컬럼 목록·`is_provisional` 덮어쓰기 규칙(마지막 쓰기가 이김)·cap 200/20·반환형·graceful None. 🔴 **「잠정이 확정을 덮는다」를 단언하는 테스트를 새로 만들지 않는다**(③-b 착수 때 뒤집힐 결함을 봉인하지 않는다).
- B1-3 식은 `snapshot_at = now()` (DB 시계 하나 — 애플리케이션 시계를 섞지 않는다).
- 호출자 무변경(`scheduler.capture_funnel_snapshots` · 스캐너 97/98 훅 · 수동 trigger).

### B2 — `market_ops` 저녁 캡처 증거에 시각 게이트 (`src/routes/market_ops.py`)

- B2-1 `funnel_rows` = 오늘 `target_date` 의 `is_provisional=TRUE` 행 중 **`snapshot_at >= 오늘 TIME_EVENING_FUNNEL_CAPTURE(KST) − _SCHEDULE_EVIDENCE_GRACE`** 인 것만 센다. 다른 행이 쓰는 기존 evidence-time 게이트(`_evidence_after_schedule`, 2시간)와 **같은 규칙**이다. 효과 = 부팅 +600초(≈07:57) 잠정 행이 07:57~09:35 동안 「저녁 캡처 완료」로 보이던 오판이 사라진다.
- B2-2 하한은 새 순수 헬퍼 하나로 만든다: `_funnel_evidence_floor(today: date) -> datetime` = `datetime.combine(today, TIME_EVENING_FUNNEL_CAPTURE, tzinfo=_KST) - _SCHEDULE_EVIDENCE_GRACE` (**tz-aware**). 라우트 호출 = `pg.fetchrow(_COMBINED_SQL, to_date(today), _funnel_evidence_floor(today))`. 시각 리터럴 금지(기존 AST 가드 `test_cycle285_ast_market_ops.py`).
- B2-3 경계 `>=` — 하한과 같은 순간의 행은 센다.
- B2-4 `funnel_last_at` 은 뜻을 바꾸지 않는다(전체 기간 잠정 행의 `snapshot_at` 최댓값 = 이 태스크의 마지막 쓰기, 다른 행의 마커 `last_success_at` 과 같은 의미). B1 덕분에 16:21 저녁 쓰기 뒤 07:57 이 아니라 16:21 을 보인다.
- B2-5 evidence 키(`snapshot_rows_today`)·상태 어휘·응답 모양 불변 → 프론트·MSW·e2e mock 무변경.

## 5. 제약

- 운영 DB 는 SELECT 만. 8영역·`scheduler.py` 무접촉(sha 핀 재핀 필요 없음이 정상 — 붉어지면 멈추고 보고).
- 이 두 파일을 sha/digest 로 핀하는 가드(예: `tests/unit/ast/test_cycle287_ast_scope.py:409` 근처)는 **값만** 재핀하고 사유 주석 한 줄.
- 기존 `test_cycle285_market_ops_pg_roundtrip.py`(직접 `pg.fetchrow(_COMBINED_SQL, to_date(_D))` 호출)·`test_cycle285_market_ops_route.py` 는 새 인자에 맞춰 **의미 보존**으로 갱신.
- PG 왕복은 로컬 docker(Docker Desktop 기동됨) — `pg_harness` 가 `postgres:15` 를 띄운다. 벽시계 의존 금지: 왕복 테스트에서 행 시각은 INSERT 뒤 **직접 UPDATE 로 고정**해 만든다(테스트 DB 한정).

## 6. 돌연변이 (≥6, 각각 붉어지는 테스트 이름 기록)

| # | 돌연변이 | 잡아야 할 행위 |
|---|---|---|
| M1 | `DO UPDATE SET` 에서 `snapshot_at = now()` 삭제 | B1-1 (+ B2 왕복: 16:21 덮어쓰기 뒤에도 07:57 로 남아 `funnel_rows=0`) |
| M2 | `funnel_last_at` 에도 같은 시각 게이트를 붙임 | B2-4 (07:57 잠정 쓰기가 최신일 때 그 값을 보여야 한다) |
| M3 | `funnel_rows` 의 `snapshot_at >= $2` 삭제 | B2-1 (07:57 행이 완료로 셈) |
| M4 | `>=` → `>` | B2-3 경계 |
| M5 | 하한에서 `_SCHEDULE_EVIDENCE_GRACE` 제거(= 16:20 정각) | B2-1/B2-3 (14:20~16:20 사이 행) |
| M6 | 하한을 naive datetime 으로(`tzinfo` 누락) | B2 왕복(9시간 어긋남) |
| M7 | 하한에 `time(16, 20)` 리터럴 | AST 가드 또는 `TIME_EVENING_FUNNEL_CAPTURE` monkeypatch 테스트 |

## 7. 문서 (report-writer, `/sync-docs` 꾸러미)

- `src/db/CLAUDE.md` `strategy_funnel.py` 절 — `snapshot_at` = 마지막 쓰기 시각.
- `src/routes/CLAUDE.md` `/api/market-ops` 행 — 저녁 funnel 증거도 evidence-time 게이트를 탄다.
- `src/engine/CLAUDE.md` 「funnel 스냅샷 캡처」 절 — (a) +600초 재준비 = 월요일·연휴 뒤 보충 적재를 라이브 후보에 반영하는 유일한 경로(게이트 금지 사유 한 문장) (b) 20:30 뒤로 옮겨도 전략 오늘봉 절단이 벽시계 날짜 비교라 D-1 — 미리보기는 기준일 주입이 선결 (c) 결함 서술은 유지(③-b 미착수).
- `docs/HARNESS_CHANGELOG.md` 상단 cycle350 1행. 루트 CLAUDE.md 일정 서술은 일정이 안 바뀌어 무변경.
- 워크리스트 결정 항목은 메인 세션 몫.

## 8. Red 확정 인터페이스 (tdd-engineer, 2026-09-24)

### 8.1 Green 이 맞출 인터페이스

- `src/db/strategy_funnel.py::insert_snapshot` — `ON CONFLICT ... DO UPDATE SET` 에 **`snapshot_at = now()`** 한 줄 추가(`CURRENT_TIMESTAMP` 도 통과). INSERT 컬럼 10개·바인딩 10개·기존 `col = EXCLUDED.col` 6개·충돌 키·`RETURNING *` 불변. 파이썬 `datetime` 바인딩 금지. `DO UPDATE` 뒤 `WHERE` 유무는 어느 테스트도 보지 않는다(③-b 자리).
- `src/routes/market_ops.py`
  - 모듈 수준 순수 함수 `_funnel_evidence_floor(today: date) -> datetime` = `datetime.combine(today, TIME_EVENING_FUNNEL_CAPTURE, tzinfo=_KST) - _SCHEDULE_EVIDENCE_GRACE`. 두 상수는 **호출 시점에 모듈 전역에서** 읽는다(기본 인자로 묶으면 monkeypatch 테스트가 붉다).
  - `_COMBINED_SQL` 의 `funnel_rows` 서브쿼리에만 `AND snapshot_at >= $2`. `$2` 는 다른 서브쿼리에 쓰지 않는다. `funnel_last_at` 무변경.
  - 라우트 호출 = `pg.fetchrow(_COMBINED_SQL, to_date(today), _funnel_evidence_floor(today))` (위치 인자 3개). `datetime.now(` 1회·`HH:MM` 문자열 리터럴 0건(기존 AST A1·A3) 유지.

### 8.2 테스트 파일 · RED 결과 (4파일 35건 = 26 붉음 / 9 초록, PG 왕복 실제 실행 — skip 0)

| 파일 | 건수 | 붉음 | 초록(보존) |
|---|---|---|---|
| `tests/unit/db/test_cycle350_funnel_snapshot_at.py` (가짜 pg, SQL·인자 캡처) | 4 | `test_c350_b1_1_conflict_update_when_same_key_then_set_clause_assigns_snapshot_at` · `test_c350_b1_3_snapshot_at_refresh_when_overwritten_then_uses_db_clock_not_app_clock` | `..._b1_2_first_insert_...` · `..._b1_2_conflict_update_..._existing_assignments_preserved` |
| `tests/unit/routes/test_cycle350_market_ops_funnel_floor.py` (헬퍼·호출 인자·SQL 문구) | 14 | floor 헬퍼 4 + 규칙 동치 파라미터 5 + 라우트 인자 2 + `funnel_rows` 게이트 1 | `..._b2_4_combined_sql_..._no_floor_gate` · `..._b2_5_..._evidence_key_and_status_unchanged` |
| `tests/integration/test_cycle350_funnel_snapshot_at_pg.py` (실 PG 왕복) | 13 | B1 두 번째 쓰기 1 + B2 SQL 6 + TZ=UTC 1 + 라우트 2 | `..._b1_1_first_insert_...default_now` · `..._b1_2_overwrite_...last_write_values` · `test_c350_pg_route_evening_row_..._then_done` |
| `tests/integration/test_cycle285_market_ops_pg_roundtrip.py` (의미 보존 갱신) | 4 | `pg_1` · `pg_2` (하한 인자 추가분) | `pg_3` · `pg_4` |

붉은 이유는 전부 **구현 없음**이다 — import·fixture 오류 0건.
- `_funnel_evidence_floor 미구현 (Red — cycle350 B2-2)` assert: 18건(헬퍼를 `getattr` 로 찾아 import 오류 대신 assert 로 붉게 했다)
- `DO UPDATE SET` 에 `snapshot_at` 없음: 2건(unit) · 두 번째 쓰기 뒤에도 07:57 그대로: 1건(PG)
- `_COMBINED_SQL` 인자 1개(하한 누락): 2건 · `funnel_rows` 에 `snapshot_at >= $2` 없음: 1건
- 라우트가 07:57 잠정 행 때문에 `done` 을 냄(10:00 기대 `scheduled`, 18:00 기대 `not_fired`): 2건 — 행위 기반 붉음

`test_cycle285_market_ops_pg_roundtrip.py` 갱신 내용 — `pg.fetchrow(_COMBINED_SQL, to_date(_D))` 3곳을 `(…, _funnel_floor(_D))` 로, 벽시계 의존을 없애려고 저녁 행 `snapshot_at` 을 16:21 로 고정(`pg_1`·`pg_2`·`pg_4`), `pg_2` 의 `funnel_last_at is not None` 을 정확한 값(`2026-09-13T16:21:00+09:00`)으로 좁혔다.
`tests/unit/routes/test_cycle285_market_ops_route.py` 는 **갱신 불필요**다 — 가짜 `fetchrow` 가 인자를 보지 않고 G13 의 SQL 문구 단언(`is_provisional = TRUE` 2곳)은 새 게이트와 공존한다(참조 구현에서 초록 확인).

⚠️ 기존 `pg_1` 은 이미 「확정 행을 잠정 쓰기가 덮으면 저녁 증거로 센다」(False→True 덮어쓰기 뒤 `row2["funnel_rows"] == 1`)를 단언한다 — 이 사이클이 만든 봉인이 아니라 cycle285 부터 있던 것이다. 의미만 보존했고 강화하지 않았다. **③-b 착수 때 이 단언을 다시 짜야 한다.**

### 8.3 돌연변이 → 붉어지는 테스트 (스크래치 복사본에 참조 Green 을 얹고 실측, 전부 잡힘)

| # | 돌연변이 | 붉어지는 테스트 |
|---|---|---|
| M1 | `snapshot_at = now()` 삭제 | unit `b1_1`·`b1_3` · PG `b1_1_second_write` · PG `b1_b2_evening_overwrite` (4) |
| M2 | `funnel_last_at` 에도 `snapshot_at >= $2` | unit `b2_4` · PG `b2_1_morning` · PG 라우트 `..._then_scheduled` · c285 `pg_2` (4) |
| M3 | `funnel_rows` 의 `snapshot_at >= $2` 삭제(인자는 그대로) | unit `b2_1_combined_sql` + PG 13(c285 `pg_1`·`pg_2`·`pg_4` 포함 — 실 PG 가 인자 수 불일치로 집계 쿼리 전체 실패) (14) |
| M3b | 게이트를 `$2::timestamptz IS NOT NULL` 로 무력화(인자는 살림) | unit `b2_1_combined_sql` · PG `b2_1_morning` · PG `b2_3_boundary` · PG 라우트 2 (5) |
| M4 | `>=` → `>` | unit `b2_1_combined_sql` · PG `b2_3_boundary` (2) |
| M5 | 하한에서 유예 제거(16:20 정각) | unit 헬퍼 5 + 라우트 인자 2 · PG `grace_window` · PG `b2_3_boundary` · PG `tz_utc` (10) |
| M5b | 유예를 `timedelta(hours=2)` 리터럴로 | unit `b2_2_floor_when_grace_constant_moves` (1) |
| M6 | 하한 naive(`tzinfo` 누락) | unit 헬퍼 9 + 라우트 인자 2 · PG `b2_2_floor_when_process_tz_is_utc` (12) |
| M7 | 하한에 `time(16, 20)` 리터럴 | unit `b2_2_floor_when_capture_constant_moves_then_floor_follows` (1) — **기존 AST 가드 `test_cycle285_ast_market_ops.py` 는 못 잡는다**(A1 = 문자열 `HH:MM` 만, A2 = `N * 60` 만. M7 적용 상태에서 그 파일 전건 초록 실측) |

- M6 는 PG 에서 **로컬 맥(KST)에서는 숨는다** — asyncpg `timestamptz_encode` 가 naive 값을 `obj.astimezone(utc)`(= 프로세스 로컬 TZ)로 해석해서다. CI 러너(UTC)에서는 9시간 어긋난다. 그래서 PG 테스트 하나가 픽스처로 프로세스 TZ 를 UTC 로 바꿔(`os.environ["TZ"]` + `time.tzset()`, teardown 복원) 로컬에서도 잡는다.
- 참조 Green 은 `TZ=UTC` + `--log-level=DEBUG` 에서도 초록(78건)이다.

### 8.4 재핀 대상 (Green 뒤 backend-dev 가 값만)

참조 Green 을 얹은 복사본과 HEAD 복사본의 `tests/unit`+`tests/contract` 전수(11,456건) 차이 + git 기반 가드는 합성 HEAD 위에서 따로 돌렸다.

| 가드 | 사유 |
|---|---|
| `tests/unit/ast/test_cycle287_ast_scope.py::_SRC_TREE_DIGEST` (`test_s1b_whole_src_tree_is_byte_identical_except_the_three`) | `src/**/*.py` 전수 digest — 두 파일 내용이 바뀌면 움직인다. 파일 수(155)·`_PINNED_DIR_FILE_COUNTS` 는 불변(신규 파일 0) |

- 그 밖의 파일 sha·세그먼트 sha 핀 중 두 파일을 잡는 것은 **없다**(`test_cycle282_ast_purity.py` 는 `strategy_funnel` 을 docstring 에서만 언급). git diff 기반 사이클 한정 가드(`test_cycle253_*` 등)는 은퇴(skip) 상태라 무관.
- 영향 인덱스 — 새 테스트 3파일 때문에 `tests/unit/deploy/test_cycle318_impact_index_freshness.py::test_backend_index_is_fresh` 가 붉어져 `python tools/test_impact/build_index.py` 로 재생성했다(diff = 새 3파일 경로 추가 + `backend_tests` 1081→1084 + `generated_at` 뿐). 🔴 **프론트 도구(`build_index_frontend.mjs`)는 돌리지 않는다** — 커밋본이 PyYAML 형식이라 js-yaml 이 뒤에 쓰면 26만 줄 포맷 diff 가 난다(실측, 즉시 원복).
