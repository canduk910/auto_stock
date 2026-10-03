# 8영역 관측 결함 3건 집중 분석 — 2026-10-04

> 읽기 전용 분석. 코드·테스트·git 무접촉. 기준 = main `c3069ce5`(행 번호 전부 이 커밋에서 다시 쟀다).
> 근거 = `_workspace/reports/2026-10-02_night_work.md` · 로그 리뷰 원문 §6 L1·L3·L4.
> 원문이 적은 행 번호는 그 뒤 커밋들(cycle398 등)로 밀렸다 — 아래 표의 「원문 → 지금」 참조.

| 결함 | 원문 행 | 지금 행 (c3069ce5) |
|---|---|---|
| L1 플래그 | `scheduler.py:420` | `scheduler.py:370` (선언) · `:3623` (`_reset_daily_state` 리셋) |
| L1 게이트 | `scheduler.py:2553-2561` | `scheduler.py:2499-2507` |
| L1 확정→확정 허용 | `strategy_funnel.py:129-137` | `strategy_funnel.py:129-148` (SQL `WHERE NOT (…)` = `:146`) |
| L3 WARNING | `order_engine.py:1366-1373` | `order_engine.py:1383-1391` |
| L3 상수 | `order_engine.py:405` | `order_engine.py:418` |
| L4 메인 폴백 | `websocket_pool.py:745` | `websocket_pool.py:741-745` |
| L4 K watcher 해제 | `stale_watcher_core.py:620·654` | `stale_watcher_core.py:829` (force_retry) · `:863` (1~5회) |
| L4 우선 재구독 스냅샷·가드 | `:877·893` | `stale_watcher_core.py:1087` (스냅샷) · `:1103-1104` (가드·해제) |
| L4 두 task | `scheduler.py:675·870` | `scheduler.py:625` (`_stale_watcher_task`) · `:820`/`:850` (`_scan_task`) → `:2464` |

공통 비용 표 (수정 시 깨지는 정확 핀 — 내용 sha 전수 검색 결과):

| 파일 | 8영역? | 파일 내용 sha 핀 | 라인 수 핀 | 비고 |
|---|---|---|---|---|
| `src/engine/scheduler.py` | 아님 · **승인 대상**(라인 상한 <3,900) | **10곳** (274·276·278·282·290·291·292·293·294_ast·297) | **11곳** (위 + 286·287·`tests/unit/engine/test_cycle294_stage3.py`) | 지금 3,730L. `test_cycle298…::test_g298_7` 이 21곳을 한 메시지로 지목한다 |
| `src/engine/order_engine.py` | **8영역** | **10곳** (222a3·223·223f·226·274·278·282·290·294_ast·297) | — | `test_cycle222a3…::_APPROVED_CONTENT_SHA` 인플라이트 승인 절차 |
| `src/realtime/websocket_pool.py` | **8영역** | **13곳** | — | `src/realtime/CLAUDE.md` 를 같이 고치면 그 핀 7곳 추가(메모리 기록) |
| `src/engine/strategy_base.py` | 아님 | 11곳 | — | L3 정밀안(B)에서만 접촉 |
| `src/engine/stale_watcher_core.py` | 아님 | **0** | — | — |
| `src/db/strategy_funnel.py` | 아님 | **0** | — | cycle364 SQL 정규식 가드 2건 있음(아래) |
| `src/engine/funnel_capture.py` | 아님 | 0 | — | — |

세그먼트(함수 단위) sha 핀은 위 표에 없다 — 수정 뒤 `pytest tests/unit/ast -q` 한 번으로 확정한다(메모리 「고친 뒤 전체 스위트 재실행」).

---

## L1 — 재기동한 날 09:30 퍼널 확정 스냅샷이 재기동 뒤 값으로 덮인다

### (1) 재현 경로 (c3069ce5)

1. 정상 아침: `_scan_loop` 첫 회차(`scheduler.py:820` 생성, `SCAN_INTERVAL` 300s 뒤 ≈09:35) → `:2499` `if not self._auto_funnel_snapshot_done_today` → `:2501` `_auto_capture_funnel_snapshots()` → `:3270` `capture_funnel_snapshots(registry, is_provisional=False, target_date=today)` → `strategy_funnel.insert_snapshot(..., is_provisional=False)` → `(D, sid, step)` 확정 행. `:2502` 플래그 True.
2. 같은 날 재기동: 새 프로세스의 `__init__` 이 `:370` 에서 플래그를 **False** 로 새로 만든다(프로세스 메모리, DB 근거 없음).
3. 재기동 시각별 첫 회차:
   - 09:30~15:20 → `:820` `_scan_loop()` = 첫 회차 300s 뒤.
   - 15:20~19:50 → `:850` `_scan_loop(first_delay=0)` = **즉시**(09-29 16:00:33 `first_delay=0.0` → 16:00:34 `saved=52 provisional=False` 가 정확히 이 경로).
4. 라벨 가드 통과: 재기동 `_boot()` 의 `prepare` 가 `_live_prepare_meta = {as_of=오늘, phase=boot, ok=True}` 를 남기므로 `funnel_capture.capture_skip_reason` 다섯 판정 전부 `None`.
5. `strategy_funnel.py:146` `WHERE NOT (기존.is_provisional = FALSE AND EXCLUDED.is_provisional = TRUE)` 는 **잠정→확정만** 막는다. 확정→확정은 `DO UPDATE` 로 통과 → 09:35 행의 `survived_*`·`snapshot_at` 이 재기동 뒤 값으로 교체된다.
6. 하루 1회 리셋은 21:30 `_reset_daily_state`(`:3623`) — 재기동 뒤 첫 캡처가 이미 「그날의 1회」를 다시 써 버렸다.

문서는 이미 이 결함을 알고 있다(`src/engine/CLAUDE.md:490` ⚠️ 문장) — 고치면 그 문장을 현재형 규칙으로 바꿔야 한다.

### (2) 운영 영향
- 매매 영향 **0** — 캡처는 라이브 객체 읽기 → DB 쓰기뿐, 매수·청산 입력에 닿지 않는다.
- 관측 영향: 재기동한 날 20:05·21:30 리포트의 `strategy_funnel_stages`(D)와 화면 퍼널이 「장중 실제로 매매에 쓴 목록」이 아니라 재기동 뒤 재준비 목록을 보인다. 09-29 는 BFB·donchian·kojiro·VCP·VB 9개 단계+99 전부가 16:00 값으로만 남았고, 오전 VB 매수 2건의 「그때 후보였나」를 사후에 잴 수 없다.

### (3) 최소 수정안

**안 A (권고) — 자동 캡처만 「기존 확정 행은 덮지 않는다」 옵션을 단다 (행 단위·원자적)**
- `strategy_funnel.insert_snapshot(..., protect_confirmed: bool = False)` 키워드 추가. `True` 면 기존 `WHERE NOT (…)` **뒤에** 리터럴 한 조각 `AND strategy_funnel_snapshots.is_provisional = TRUE` 를 덧붙인다(= 기존 행이 잠정일 때만 갱신). **바인딩을 늘리지 않는다**(플래그는 파이썬에서 SQL 조각 선택).
  - `False`(기본)일 때 SQL 은 지금과 byte 동일 → `test_cycle364_funnel_protect_confirmed.py::test_c364_3b_1`(정규식) · `3b_2`(`len(args) == 10`) · pg `3b_4`(수동 확정→확정 덮어쓰기) 전부 무접촉.
- `scheduler.capture_funnel_snapshots(…, protect_confirmed: bool = False)` 키워드 추가 → 두 `insert_snapshot` 호출에 전달. `_auto_capture_funnel_snapshots`(`:3270`) 한 곳만 `protect_confirmed=True`.
- 수동 trigger(`routes/strategy_funnel.py:164`)·저녁(`funnel_capture.py:245·318`)은 기본값 그대로 = 행위 불변.
- 효과: 재기동한 날 자동 캡처는 이미 확정된 전략의 행을 전부 거부(`RETURNING` 0행 → `None` → saved 에 안 셈, 기존 `3b_4` 계약)하고, **오전에 확정되지 못한 전략**(그날 아침 `prepare_failed`·`in_progress` 로 건너뛴 전략, 또는 오전 내내 프로세스가 죽어 있던 날)은 재기동 뒤 값으로 채워진다. 「하루의 첫 확정본 보존」 + 「빈 날은 채움」을 행 단위로 동시에 만족한다. 아침 정상 경로(09:35 확정이 07:57 레거시 잠정·전날 21:00 미리보기 잠정을 교체)는 기존 행이 잠정이라 그대로 통과한다.
- 비용:
  - `scheduler.py` — 시그니처 1줄 + 전달 2곳 + docstring Args 2~3줄 ≈ **+3~5L** (3,730 → ≈3,735, 상한 3,900 여유 165). sha 10 + 라인 11 = **21곳 재핀**(G-298-7 이 목록을 준다). 승인 대상(8영역 아님).
  - `strategy_funnel.py` — 핀 0. 정규식 가드 무접촉(위).
- 알려진 한계: 단계 수가 아침과 달라지면(아침 7단계·재기동 9단계) 새 단계 행만 추가돼 한 전략 안에 두 시각이 섞인다. 지금 단계 수는 전략별 상수라 실현 가능성 낮음 — `snapshot_at` 이 그대로 드러낸다.

**안 B — 게이트를 DB 근거로 (전략 전체 단위)**
- `funnel_capture.py`(leaf, 핀 0)에 `async def confirmed_capture_exists(label) -> bool | None` (`list_snapshots(target_date=label, raise_on_error=True)` 중 `is_provisional=False` 1행 이상). `_auto_capture_funnel_snapshots` 첫머리에서 `True` 면 캡처 없이 반환(호출부가 플래그 True), `None`(DB 실패)이면 현행대로 캡처.
- 비용: `scheduler.py` ≈ +3L, 같은 21곳 재핀. SQL 무접촉.
- 단점: 전부-아니면-전무라 「오전에 빠진 전략을 재기동 뒤 채움」이 사라진다 · 조회↔쓰기 사이 TOCTOU(실해 없음) · DB 조회 1회 추가.

**기각 — 시간창 게이트**(예: 15:20 이후 재기동이면 캡처 안 함): 09:30~15:20 재기동을 못 막고, 오전 내내 죽어 있던 날의 유일한 기록을 지운다.

### (4) 회귀 테스트 설계 (Red → Green)
- **R1 pg 통합**(`tests/integration/`, CI postgres, `clean_strategy_funnel` 픽스처 재사용 — `test_cycle364_funnel_protect_confirmed_pg.py` 형식):
  1. `(D, vcp, 1)` 확정 행 INSERT → `snapshot_at` 기록 → `insert_snapshot(..., is_provisional=False, protect_confirmed=True, survived_count=다른값)` → 반환 `None`, 행의 `survived_count`·`snapshot_at` 불변. **Red** = 지금은 키워드 없음 `TypeError`(구현 전), 키워드만 받고 무시하면 값이 바뀌어 붉음.
  2. 기존 행이 **잠정** → `protect_confirmed=True` 확정 쓰기 → 갱신·`is_provisional=False`(09:35 정상 교체 보존).
  3. 행 없음 → 삽입(빈 날 채움).
  4. 기존 `pg_3b_4`(수동 확정→확정 덮어쓰기)는 그대로 초록 = 기본값 불변의 증거.
- **R2 단위 SQL**: `protect_confirmed=False` 의 SQL 문자열이 현행 상수와 **완전 동일**(문자열 비교) · `True` 면 `WHERE NOT (…) AND strategy_funnel_snapshots.is_provisional = TRUE` 순서 · 바인딩 10개.
- **R3 호출자 계약**(단위, `insert_snapshot` monkeypatch): `_auto_capture_funnel_snapshots` → 모든 호출 `protect_confirmed=True` · 라우트 `trigger_snapshot`·`evening_capture_once` → `protect_confirmed` 미전달 또는 False.
- **R4 재기동 시나리오**(단위): 새 `TradingScheduler` 인스턴스(플래그 False) + 가짜 `insert_snapshot` 이 기존 확정 키에 `None` 을 돌려주게 → `_scan_loop` 게이트 1회 → saved=0 · 플래그 True · 두 번째 회차 캡처 미호출.
- 행위 불변 조건: `_scan_loop` 의 다른 단계 호출 순서·예외 흡수 불변 · 저녁·수동 경로 SQL byte 동일.

### (5) 권고
안 A. 함께 고칠 문서 = `src/engine/CLAUDE.md:490` ⚠️ 문장 → 「자동 캡처는 그날 이미 확정된 행을 덮지 않는다(`protect_confirmed`), 수동 trigger 는 덮는다」 · `src/db/CLAUDE.md` `strategy_funnel.py` 절(덮어쓰기 조합 4→5). `scheduler.py` 승인 + 21곳 재핀을 한 커밋에.

### 금기 대조
매매 경로 무접촉(캡처는 관찰 경로) · `_reset_daily_state` 무접촉 · cycle364 「잠정은 확정을 덮지 못한다」 불변(오히려 조인다) · 「레거시 즉시 1회에 게이트 금지」(`src/engine/CLAUDE.md` 레거시 분기)와 무관(그쪽은 `is_provisional=True` 경로).

---

## L3 — 「매수 수량 0 → 900s cooldown (투자금: …)」 이 원인을 가르지 못한다

### (1) 재현 경로 (c3069ce5)
1. `order_engine.execute_buy` `:1365` `quantity = strategy.calc_buy_quantity(current_price, ticker)`.
2. `calc_buy_quantity` 의 모든 return 이 `StrategyBase._apply_budget_limit`(`strategy_base.py:641`)를 지난다. 0 이 되는 갈래:
   - **자금**: `qty <= 0` → `_fallback_one_share`(`:625`)가 `remaining < price` 면 0 (`:639`) · `qty > 0` → `min(qty, remaining // price)` 가 0 (`:684`, 이때 `[budget_clamp]` INFO 만).
   - **K축**: `_apply_lot_units_cap`(`:794`)이 `floor(K×예산×risk_pct÷ATR)=0` 이면 0.
   - **ρ축**: `_apply_ratio_notional_cap`(`:1176`)이 `cutoff // price = 0` 이면 0 + `[ratio_notional_blocked]` INFO(`:1250-1271`, (전략,종목)당 하루 1회).
   - **시장 유닛**: 터틀 4전략 `calc_buy_quantity` 첫머리(관문 앞)가 0 — 정상이면 신호 단계(`Signal.NONE`)에서 이미 걸러져 여기 오지 않는다.
   - 그 밖: kojiro 오픈리스크 캡, 가격 ≤0.
3. `order_engine.py:1383-1391` — `quantity <= 0` 이면 원인과 무관하게 `state.block_low_funds(ticker, now+LOW_FUNDS_COOLDOWN)`(`:418` = 900.0) + 같은 WARNING 「매수 수량 0 → 900s cooldown: … (투자금: %d, 현재가: %d, 전략: %s)」.
4. 원인 마커는 INFO 라 2일 보관(`src/db/system_logs.py:32`)이고 21:30 `top_patterns`(WARNING 이상, `log_metrics_collector.py:73` `_normalize_message`)에 안 실린다. 자금 갈래는 마커가 아예 없다. → 이틀 뒤엔 원인 없는 WARNING 만 남고, 리포트는 「투자금 부족」으로 읽는다(`src/engine/CLAUDE.md:885` 「오귀인 판독」이 사람 손 판독 규칙으로 메우는 중).

### (2) 운영 영향
- 매매 영향 **0**(관측 결함). 쿨다운 900s 는 원인과 무관하게 같은 행위이고, 그 행위는 이번 수정 대상이 아니다.
- 관측 영향: 09-28 ρ 10·자금 3 / 09-29 ρ 2·자금 2 / 09-30 ρ 1 — 일일 리포트·주간 자문(10-01 D7)이 ρ 차단을 자금 부족으로 오독했다. K_ρ=1.0(09-25 D6③) 이후 ρ 비중이 커졌다.

### (3) 최소 수정안

**안 A (권고) — `order_engine` 한 파일, 사후 판정 1개를 WARNING 꼬리에 붙인다**
- `quantity <= 0` 분기 안에서 순수 동기 읽기로 원인 판정:
  - `remaining = state.total_investment - strategy._calc_used_funds()` (선례: 같은 파일 `:1587`·`:1693` 이 이미 이 접근을 쓴다).
  - `remaining < current_price` → `cause=funds` (ρ·K 와 겹쳐도 자금이 충분조건이므로 우선 — 09-28 042700 처럼 K_ρ 를 올려도 막혔을 종목이 맞게 귀속된다).
  - 그 외 → `cause=cap` (K축·ρ축·오픈리스크·시장 유닛 등 사이징 상한).
  - 판정 예외 → `cause=unknown` (흡수, 행위 불변).
- WARNING 은 **앞부분 byte 유지 + 꼬리 추가**: `"매수 수량 0 → %ds cooldown: %s (투자금: %d, 현재가: %d, 전략: %s, 원인: %s, 잔여: %d)"`. grep 연속성(「매수 수량 0 → 900s cooldown」) 유지, `_normalize_message` 뒤에도 `원인: funds` / `원인: cap` 이 다른 패턴으로 갈라져 `top_patterns` 에서 바로 보인다(잔여 숫자는 `<N>` 로 마스킹돼 패턴을 쪼개지 않는다). WARNING 이라 30일 보관.
- **행위 불변**: `block_low_funds(+900)` · `return` · 순서 그대로. await 0 추가 → A-ATOMIC(`test_budget_limit_ast.py::test_execute_buy_sizing_to_pending_is_await_free`) 유지.
- 비용: 8영역 `order_engine.py` **sha 10곳** + `test_cycle222a3…::_APPROVED_CONTENT_SHA` 인플라이트 등록(그 파일 주석의 「자매 가드 네 곳 전부 같은 값」 절차) · ≈ +8~12L(라인 핀 없음).
- 한계: `cap` 안의 세부(K·ρ·오픈리스크)는 가르지 않는다 — 그날 같은 (전략,종목)의 `[ratio_notional_blocked]`·`[fallback_notional_capped]` INFO 로 2일 안에서 세분. 「자금 vs 캡」이 L3·D7 의 실제 질문이라 이것으로 닫힌다.

**안 B (정밀) — 관문이 0 의 원인을 남기고 엔진이 읽는다**
- `StrategyBase` 에 `_last_zero_qty_cause: dict[str, str]`(종목 키) — 0 을 만드는 각 갈래(`_fallback_one_share`·잔여 클램프·K축·ρ축·오픈리스크·시장 유닛 4전략)가 동기로 기록, 엔진이 `pop` 해서 WARNING 에 `원인: rho|k|funds|open_risk|market_unit`.
- 비용: `strategy_base.py` sha 11곳 + 관문 함수 세그먼트 핀(A-PURE G-242-2/10·G-245-2 류) + 터틀 4전략 파일(전략 7파일 sha 핀 다수) + `order_engine` 10곳. 관문 순서 계약(`폴백 → K축 → 관측 → ρ축`)을 건드리는 diff 라 리뷰 면적이 크다.
- 기각 사유: 0계명 순위 1(누락 위험) 기준으로 오히려 나쁘다 — 0 을 만드는 갈래가 새로 생길 때마다 기록을 빠뜨릴 자리가 하나씩 는다. 안 A 는 갈래 수와 무관하게 「자금이냐 아니냐」를 한 곳에서 잰다.

**비권고 — 원인별 쿨다운 차등**(cap 이면 쿨다운 없음 등): 매수 행위 변경 = 사용자 결정 + `domain-consult` 선행 대상(루트 「여전히 승인이 필요한 것」). 이번 범위 밖.

### (4) 회귀 테스트 설계
- **R1 단위**(`tests/unit/engine/`, `test_order_engine_buy.py` 픽스처 재사용): `calc_buy_quantity` 를 0 으로 스텁.
  1. 자금: `total_investment=100_000`, 보유로 `_calc_used_funds()=95_000`, 가격 10_000 → WARNING 에 `원인: funds` · `잔여: 5000`.
  2. 캡: `total_investment=1_000_000`, 사용 0, 가격 10_000 → `원인: cap`.
  3. `_calc_used_funds` 가 예외 → `원인: unknown`, 예외 전파 없음.
  - 세 경우 공통 불변: `state.block_low_funds` 가 `(ticker, now+900)` 로 1회 · `pending_buys`·`pending_buy_amounts` 무변경 · `place_order`·`get_buyable` 추가 호출 0 · 메시지 접두 「매수 수량 0 → 900s cooldown: 」 유지(caplog 는 WARNING+접두로 한정 — 메모리 「caplog 단언」).
  - **Red** = 지금 메시지에 `원인:` 없음.
- **R2 정규화**: `_normalize_message` 에 두 메시지를 넣으면 결과가 서로 다르고, 같은 원인끼리는 같다(잔여 숫자 무관).
- **R3 구조**: A-ATOMIC 기존 가드 그대로 초록 · 새 판정 코드에 `Await` 0(같은 함수라 기존 가드가 덮는다).
- 실측 확인(배포 뒤): 다음 ρ 차단 발생일 `system_logs` 에서 `원인: cap` 행과 같은 시각·종목의 `[ratio_notional_blocked]` 짝 1:1(워크리스트 `:3601` 판독 규칙이 그대로 자동화되는지).

### (5) 권고
안 A. 함께 고칠 문서 = `src/engine/CLAUDE.md:885` 「오귀인 판독」 → `원인:` 꼬리로 읽는다는 현재형 한 줄 · `src/engine/strategies/CLAUDE.md:171`·`src/engine/CLAUDE.md:792` 의 「오귀인된다」 문구는 「`원인: cap` 으로 남는다」로. 워크리스트 「cycle382 후속 #7」·주간 자문 D7 동시 종결.

### 금기 대조
A-ATOMIC(await 0) 유지 · 관문 무접촉(분기 순서 계약 불변) · 「수량 0 반환으로 막지 않는다」 규칙은 신호 단계 차단에 관한 것이라 무관 · `buy_paused`·시장 유닛 신호 단계 차단 무접촉.

---

## L4 — K stale watcher 와 `_resubscribe_stale_priority` 경합 → 헛 UNSUBSCRIBE 가 메인으로 간다

### (1) 재현 경로 (c3069ce5)
두 task 는 서로 독립이다 — `_stale_watcher_task`(`scheduler.py:625`, 120s 주기 → `stale_watcher_core.check_and_resubscribe_stale`)와 `_scan_task`(`:820`/`:850` → `_scan_loop` `:2464` → `stale_watcher_core.resubscribe_stale_priority`). 공유 잠금 없음.

경로 ① (10-01 19:40:48 실측형 — 우선 재구독이 뒤):
1. 우선 재구독이 `:1087` 에서 구독 스냅샷을 **한 번** 찍는다(035420 포함). 대상 최대 10개를 돌며 종목마다 `asyncio.sleep(0.05)` ×2 + `subscribe` await → 수백 ms~1초 동안 스냅샷이 낡는다.
2. 그 사이 K watcher(`:729` 루프)가 035420 을 `:863`(1~5회 갈래) `unsubscribe_in_pool` → `websocket_pool.py:741` `_ticker_to_session.pop` → RIA 세션 `unsubscribe`(`websocket.py:646` 집합 제거 + UNSUBSCRIBE SEND) → `:864` `sleep(0.05)`.
3. 우선 재구독이 035420 차례 — `:1103` `if ticker in subscribed_snapshot` 가 **낡은 스냅샷**이라 참 → `:1104` `unsubscribe_in_pool` → `:741` pop 결과 `None` → `:745` **메인 폴백** → `main.unsubscribe` → 메인 `_subscriptions` 엔 없지만 `if self._ws:` 라 SEND(`websocket.py:651-652`) → KIS `OPSP0003 not found` → `[ws_subscribe_reject]` ERROR.
4. 둘 다 이어서 `subscribe` → 먼저 끝난 쪽이 매핑을 세우면 뒤쪽은 중복 분기(`websocket_pool.py:382`) noop. 최종 구독은 정상(실측: 1004 세션).

경로 ② (거울상): 우선 재구독이 먼저 pop → `sleep` 중 → K watcher `:863` 은 구독 여부를 **아예 보지 않고** 해제(`:510` 스냅샷은 대상 선정용일 뿐) → 같은 메인 폴백.

경로 ③ (이론, 미관측): 두 쪽이 모두 pop 뒤 sleep 을 지나 매핑이 비어 있는 동안 동시에 `subscribe` 의 LOW 갈래(`websocket_pool.py:433-460`)에 들어가면, 매핑은 `await chosen.subscribe(...)` **뒤**(`:457`)에 세워지므로 둘 다 `existing is None` 을 보고 서로 다른 세션을 고를 수 있다 → 이중 구독(한쪽 튜플은 매핑 밖 고아, 슬롯 1개 잠식).

`unsubscribe_in_pool` 의 프로덕션 호출자는 이 세 곳(`stale_watcher_core.py:829·863·1104`)뿐이다(`src/` grep).

### (2) 운영 영향
- 매매 영향 **0**: 헛 SEND 1건 + ERROR 1행. 최종 구독 정상. 09-14 채널 분리 뒤 H0STCNT0 `OPSP0003` 3건(09-15·09-17·10-01), 전부 LOW.
- 잠재: KIS 「비정상 등록/해제 반복」(LMS·앱키 정지) 판정 표본에 헛 SEND 가 섞인다 · 경로 ③ 이 실현되면 41 슬롯 잠식. HIGH 종목도 같은 경합에 들어갈 수 있으나 HIGH 는 메인 고정이라 메인 폴백이 우연히 맞는 세션이 된다(ERROR 는 동일하게 남는다).

### (3) 최소 수정안

**안 A (권고) — `stale_watcher_core` 한 파일, 종목 단위 「재등록 진행 중」 표식 (8영역 무접촉 · 핀 0)**
- 모듈 전역 `_RESUB_INFLIGHT: set[str]` + 동기 헬퍼 `_claim(ticker) -> bool`(이미 있으면 False, 없으면 add 후 True) · `_release(ticker)`(discard).
- 세 해제 지점(`:829` · `:863` · `:1103-1104` 블록) **바로 앞**에서 `_claim` — 실패하면 그 종목을 이번 회차에서 건너뛴다(다른 경로가 지금 같은 일을 하고 있다). 성공하면 기존 `try` 블록에 `finally: _release(ticker)` 를 붙여 `subscribe` 완료·예외·취소(15:20·20:00 `_scan_task.cancel()`) 모두에서 푼다.
- 원자성 근거: `_claim` 과 `unsubscribe_in_pool` 첫 문장의 `pop` 사이에 `await` 가 없다 → 다른 코루틴이 끼어들 수 없다. 표식은 `subscribe` 의 매핑 기록까지 덮으므로 경로 ③ 의 두 경로 간 창도 닫힌다.
- 건너뛴 쪽의 부수 효과: 우선 재구독 쪽은 `resubscribed` 에 안 넣고 `_stale_last_resubscribe_at` 도 안 찍는다(실제로 한 일이 없다). K watcher 쪽은 `:730` 의 `_stale_retry_count` 증가가 이미 일어난 뒤라 그 회차 1회 몫이 소모된다 — 관측 숫자만의 영향이고 force_retry 게이트(`>MAX`)·universe guard(`<=MAX`) 판정은 다음 회차에 그대로 수렴한다. 건너뜀은 DEBUG 1행(새 마커를 WARNING 으로 만들지 않는다 — `[stale_watcher_summary]` 형식 불변).
- 비용: `stale_watcher_core.py` 만, sha 핀 **0**, `scheduler.py` 무접촉(속성을 scheduler 에 두지 않으므로 라인·sha 21곳 무접촉). 기존 `unsubscribe_in_pool` 호출 테스트(`test_cycle215…` 47 · `test_cycle217…` 46 등)는 단일 코루틴이라 표식이 늘 비어 있어 행위 동일.

**안 B (방어 심층, 선택) — `websocket_pool.unsubscribe_in_pool` 의 메인 폴백을 「실제로 들고 있는 세션 찾기」로**
- `:743-745` 를: 매핑이 없으면 메인+보조 각 세션 `_subscriptions` 에서 `tr_key` 가 같은 튜플을 찾아 그 세션에만 해제, 아무도 없으면 SEND 없이 DEBUG 반환.
- 장점: 호출자가 누구든 헛 SEND 가 구조적으로 0. cycle217 의 「미구독 종목엔 UNSUBSCRIBE 를 보내지 않는다」 원칙을 풀 계층으로 옮긴다.
- 비용: 8영역 `websocket_pool.py` **sha 13곳** + 인플라이트 승인 절차. 경로 ③(이중 구독)은 못 닫는다.
- 위험: `:744` 주석의 「추적 없는 ticker — 메인에서 시도 (안전 디폴트)」 가 지키던 경우(세션 집합엔 없는데 KIS 쪽엔 남은 구독을 메인 SEND 로 정리)가 사라진다. 그런 상태가 실재하는지 증거가 없어 판단 보류가 맞다.

### (4) 회귀 테스트 설계
- **R1 경합 재현**(단위, `tests/unit/engine/stale_manager/`): 실제 `WebsocketPool` 대신 매핑 dict·세션 2개(메인·보조)를 가진 가짜 풀. 가짜 `subscribe` 는 `asyncio.Event` 를 기다리게 해 「진행 중」 창을 고정한다.
  1. K watcher 코루틴을 시작해 종목 X 의 `subscribe` 대기에 멈춘다.
  2. 그 상태에서 `resubscribe_stale_priority`(X 가 스냅샷·대상에 포함) 실행.
  3. 단언: 메인 세션 `unsubscribe` 호출 0 · 전체 UNSUBSCRIBE 1회(보조 세션) · 우선 재구독 결과에 X 없음.
  4. Event 해제 → X 최종 매핑 1개·튜플 1개(경로 ③ 부재).
  - **Red** = 지금은 3번에서 메인 `unsubscribe` 1회(폴백).
- **R2 거울상**: 순서를 바꿔 우선 재구독이 먼저 멈추고 K watcher(`:863` 갈래와 `:829` force_retry 갈래 각각)가 들어온다 → 같은 단언.
- **R3 해제 보장**: `subscribe` 예외 · 코루틴 `cancel()` 뒤 `_RESUB_INFLIGHT` 가 비어 있다(표식 누수 = 그 종목 재등록 영구 정지 — 가장 비싼 실패라 반드시 핀).
- **R4 HIGH 보장**: 경합이 없을 때 HIGH 종목의 K watcher·우선 재구독 호출 인자(`priority="HIGH", bypass_limit=True`)가 기존과 같다 · 경합 시 HIGH 는 다른 경로가 같은 HIGH 인자로 재등록 중일 때만 건너뛴다.
- 행위 불변 조건: 기존 stale_manager·no_feed(cycle252)·force_retry·cap 테스트 전부 초록.

### (5) 권고
안 A 단독. 8영역을 열지 않고 관측된 경합(경로 ①②)과 이론상 이중 구독(③, 두 경로 사이)까지 닫는다. 안 B 는 「세션 집합엔 없고 KIS 쪽엔 남은 구독」이 실재하는지 증거가 생길 때까지 보류. 문서 = `src/realtime/CLAUDE.md` 는 고치지 않는다(8영역 핀 7곳) — `src/engine/CLAUDE.md` 의 stale watcher 절에 「두 재등록 경로는 종목 단위 진행 표식으로 서로 배제한다」 한 줄.

### 금기 대조
- WebSocket 다중 안전망 4중: 경로 수·주기·우선순위 분리(positions/`_pending_next_day_clear` HIGH+bypass) 불변. 건너뜀은 「다른 경로가 같은 종목을 지금 재등록 중」일 때만이라 보유 종목 커버리지 손실 없음.
- 체결통보 구독(H0STCNI0/9): 이 경로에 없음(`unsubscribe_in_pool` 은 시세 tr 만).
- `MAX_SUBSCRIPTIONS=41`·HIGH bypass: 무접촉. 오히려 경로 ③ 슬롯 잠식 창을 닫는다.
- no_feed(cycle252): LOW no_feed skip 은 해제 지점보다 앞이라 무접촉.
- KIS 「등록/해제 반복」: SEND 수가 줄기만 한다.

---

## 처리 순서 제안

1. **L4 안 A** — 8영역·`scheduler.py` 무접촉, 핀 0. 가장 싸고 독립적.
2. **L3 안 A** — 8영역 `order_engine.py` 1파일, sha 10곳 + 인플라이트 승인. 주간 자문 D7 종결.
3. **L1 안 A** — `scheduler.py` 승인 + 21곳 재핀(+ `strategy_funnel.py` 핀 0). 재핀 면적이 커서 다른 `scheduler.py` 변경과 같은 커밋에 묶지 않는다.

세 건 모두 매매 행위 변경 0 → `domain-consult` 불요. 배포 창은 full 모드(backend 재시작) 규칙 그대로(15:30~16:00 · 21:35~07:45, 20:00~21:35 금지). 각 수정 뒤 `pytest tests/unit/ast -q` + 전체 스위트 재실행.

## 비권고 (검토했으나 제외)
- L1 시간창 게이트 — 위 (3) 기각 사유.
- L3 원인별 쿨다운 차등 — 매수 행위 변경, 사용자 결정 대상.
- L3 안 B(관문 기록) — 누락 위험이 커지는 방향.
- L4 per-ticker `asyncio.Lock` — `set` 표식과 효과가 같고 대기(블로킹)가 생겨 120s·5분 주기 경로가 서로를 기다리게 된다. 건너뛰기가 맞다.
