# 1단계 관문 — tdd-engineer(그물) 보고

> 대상: `execute_sell` 접수 후 구간 통합 · 설계 카드 = [`2026-09-20_step1_card.md`](2026-09-20_step1_card.md)
> 이 문서는 **4번의 뒷부분 · 5 · 6 · 판정**만 담는다(1~3번은 회신으로 전달됨).
> 기준 소스 sha = `f970c625a33b4e63065eb3b27445e6b61b8f23a392c58c6fa017f519c5afb8ca`

---

## 4. 그물 공백 — 호출부가 헬퍼로 넘기는 **값**

### 4.1 무엇이 없는가

새 헬퍼 `_persist_sell_pending_after_send` 는 호출부에서 **이름 있는 인자 6개**를 받는다
(`ticker` · `order_no` · `strategy_id` · `record_price` · `quantity` · `path`).
그 중 **`order_no` 와 `path` 만** 그물이 있고 나머지는 없다.

| 인자 | 주 경로 | 폴백 경로 | 덮는 테스트 |
|---|---|---|---|
| `order_no` | 있음 | 있음 | 폴백 = `test_order_engine_sell_fallback.py:264` `record.order_no == "ORDER-C-1"` · 주 = 마커의 `order_no=` |
| `path` | 있음 | 있음 | `test_cycle327_...::test_sell_emits_fill_during_insert_marker` 의 `"path=market"` · 시나리오 I 의 `"path=fallback"` (둘 다 **예외 분기**) |
| `record_price` | **없음** | **없음** | — |
| `quantity` | **없음** | **없음** | — |
| `strategy_id` | **없음** | **없음** | — |
| `ticker` | **없음** | **없음** | — |

리포 전체에서 `insert_trade` 레코드를 단언하는 자리는 4곳뿐이고, `.price` 를 보는 것은
**매수 축 3곳**(`tests/unit/engine/test_order_engine_buy.py:211`·`:463`,
`tests/unit/engine/test_cycle291_pre_nxt_gtp.py:662`)이다. **매도 축은 주·폴백 어느 쪽도 없다.**
cycle327 결함(흡수기가 매수에만 있었다)과 **같은 모양의 비대칭**이다.

### 4.2 실측 근거

돌연변이를 넣고 백엔드 **전체** 스위트를 돌린 결과다(기준선 = 11,122 passed / 0 failed).

| 돌연변이 | 결과 |
|---|---|
| 폴백 `record_price=fallback_price` → `pos.buy_price` **+** `quantity=pos.quantity` → `1` | `14 failed, 11108 passed` — 붉어진 14건은 **전부 sha/byte 동일성 핀**(핀 10 + 메타가드 4). **행위 단언 0건 반응** |
| `_SELL_PENDING_SKIP_PATH_LABEL` 의 `"폴백 "` → `""` | 대상 세트 **30 전부 초록** |

`gate-tester` 의 T-3(주 경로 `record_price`/`quantity` 맞바꿈, 광역 7,465건 초록)과
T-1(라벨 두 값 맞바꿈, 행위 그물 92건 초록)이 **같은 구멍의 다른 쪽**이다.
관문 둘이 독립적으로 같은 결론에 닿았다.

### 4.3 이 추출이 만든 것은 아니지만, 위험을 키웠다

diff 를 읽어 확인했다 — 넘기는 값은 추출 전 인라인 `TradeRecord(...)` 리터럴과 **정확히 같다**.
결함은 원래 있었다. 다만 추출 후 두 호출부는 **7줄짜리 거의 동일한 블록**이 되어
`result`↔`fb_result`, `pos.buy_price`↔`fallback_price` 두 글자만 다르다.
복붙 한 번이 조용히 통과한다. 그리고 **카드의 돌연변이 표 M5 행이 없는 단언을 있다고 적어 두었다**
(`test_..._limit_fallback_at_5_ticks_down` 의 "(`record.price` 단언)" — 그 테스트는
`record.order_no` 하나만 본다). 그 표를 근거로 통과시키면 관문이 자기 근거를 검증하지 않은 셈이 된다.

---

## 4.4 리더 제안 회귀 판정 — 무엇이 잡히고 무엇이 빠지는가

### 제안이 잡는 것: 전부 잡는다

| 돌연변이 | 잡는 단언 | 판정 |
|---|---|---|
| M5 (폴백 `record_price`→`pos.buy_price`) | 폴백 `price == fallback_price` | 잡힘 |
| M13 (폴백 `quantity`→`1`) | 폴백 `quantity == pos.quantity` | 잡힘 |
| M12 (라벨 `"폴백 "`→`""`) | 폴백 문구에 `"폴백"` 있음 | 잡힘 |
| T-1 (라벨 두 값 맞바꿈) | 주 경로 `"폴백"` 없음 **+** 폴백 `"폴백"` 있음 — **쌍이라서 잡힌다** | 잡힘 |
| T-3 (주 경로 `price`/`quantity` 맞바꿈) | 주 경로 `price == pos.buy_price` · `quantity == pos.quantity` | 잡힘 (값 판별력은 4.5) |

### 빠진 축 3개

**① 폴백 record 의 나머지 4필드 — `trade_type` · `status` · `ticker` · `strategy`**

제안 목록은 주 경로엔 6필드를 다 넣고 폴백엔 `price`·`quantity` 둘만 넣는다.
그런데 이 결함이 실제로 일어나는 방식은 **주 경로 블록을 폴백에 복붙하고 두 줄만 고치는 것**이다.
그러면 고치지 않은 나머지가 틀린 채로 남는데, 폴백에 단언이 둘뿐이면 그 나머지가 무방비다.
`order_no` 는 기존 `record.order_no == "ORDER-C-1"` 가 이미 덮으므로 **실질 추가는 4개**다.

> **두 경로에 같은 6필드를 대칭으로 넣기를 권한다. 비대칭이 이 결함의 뿌리였다.**

**② `ticker_name` 파생식 (가치 낮음, 선택)**

`t(ticker).split("(")[0] if "(" in t(ticker) else ""` — 추출 때 통째로 옮겨온 파생식인데
어디서도 보지 않는다. 표시용이라 자본 위험 0. 넣는다면 주 경로 record 단언에 한 줄이면 족하다.

**③ `path` 는 추가 불필요 — 이미 덮인다**

`path` 는 예외 분기 둘에서 이미 덮이고(`"path=market"` · `"path=fallback"`),
제안의 문구 단언 2건이 **skip 분기**까지 덮는다. 세 분기 전부 덮이므로 더 세울 것이 없다.

---

## 4.5 픽스처 판별력 — 실측값으로 검산했다

### 폴백 경로 (`tests/unit/engine/test_order_engine_sell_fallback.py`)

픽스처 실측: `pos.buy_price = 4500` · `pos.quantity = 10` ·
`_scanner.ticker_prices["012200"] = {"current_price": 4500}`
→ `step_down(4500, steps=5) = 4475` (직접 실행해 확인)

| 맞바꿈 | 비교 | 판별 |
|---|---|---|
| `record_price` → `pos.buy_price` | `4475` vs `4500` | 된다 |
| `quantity` → `1` | `10` vs `1` | 된다 |
| `price` ↔ `quantity` | `4475` vs `10` | 된다 |

**다만 `4475` 와 `4500` 은 25원 차이이고 둘 다 4자리다.** 지금은 다르지만,
누가 `current_price` 를 4,505로 바꾸거나 호가단위 구간 경계(1,000~5,000원 = 5원)를 건드리면
**우연히 같아질 수 있고, 같아지는 순간 단언은 조용히 공허해진다**(초록인데 아무것도 재지 않는다).

> **권고 A (최소 · 기존 픽스처 무접촉 · 이것만으로 충분)** — 단언 위에 전제 봉인 한 줄.
>
> ```python
> assert expected_fallback != strategy.state.positions["012200"].buy_price, (
>     "픽스처 전제 붕괴 — 폴백가와 매수가가 같아지면 아래 price 단언이 공허하다"
> )
> ```
>
> 「가드는 고치면 초록이 되어야 한다」 원칙에 맞다 — 우연히 같아지면 이 줄이 붉어져 알려 준다.

> **권고 B (더 튼튼 · 새 테스트에서만)** — 현재가를 매수가와 크게 떼어 놓는다.
> `buy_price=4500` · `current_price=8000` → 호가단위 10원 → `step_down(8000,5) = 7950`.
> `7950` vs `4500` vs `10` 셋이 자릿수까지 다르다. ⚠️ **기존 시나리오 C 를 고치면
> 같은 테스트의 `second_call.kwargs["price"] == expected_fallback` 도 함께 움직이므로**,
> 값 변경은 새 테스트에서만 하고 기존 시나리오 C 에는 권고 A 만 얹는 것이 안전하다.

### 주 경로

두 후보 픽스처 모두 맞바꿈 판별력은 충분하다.

| 픽스처 | `price` vs `quantity` | 쓸 수 있는가 |
|---|---|---|
| `test_order_engine_sell_fallback.py` | `4500` vs `10` | **쓸 수 있다** |
| `test_cycle327_sell_fill_during_insert.py` (`PRICE=70_000`, `QTY=10`) | `70000` vs `10` | 🔴 **못 쓴다** — 그 파일의 `fake_insert_trade`(`:114-124`)는 **첫 SELL 레코드에서 `UniqueViolationError` 를 던진다**. 성공 PENDING 레코드가 애초에 생기지 않는다 |

---

## 4.6 세울 테스트 — 픽스처 · 주입 지점 · 단언

### (a) 주 경로 성공 PENDING record — **신규 테스트 1개**

**파일**: `tests/unit/engine/test_order_engine_sell_fallback.py` (기존 픽스처 6종을 그대로 쓴다 —
`engine` · `strategy` · `mock_insert_trade` · `mock_place_order` · `mock_write_log` ·
`mock_strategy_exchange`. **새 픽스처 0개**)

**주입 지점**: `mock_place_order.side_effect = [_success_result("ORDER-M-1")]`
— 1차 시장가가 거부 없이 접수되므로 헬퍼의 `else` 분기(성공 INSERT)에 닿는다.

```python
@pytest.mark.asyncio
async def test_execute_sell_when_accepted_then_pending_record_carries_position_values(
    engine, strategy, mock_insert_trade, mock_place_order,
    mock_write_log, mock_strategy_exchange,
):
    """주 경로 PENDING record 의 6필드가 포지션 값 그대로인가 (gate-tester T-3)."""
    mock_place_order.side_effect = [_success_result("ORDER-M-1")]
    pos = strategy.state.positions["012200"]
    assert pos.buy_price != pos.quantity, "픽스처 전제 — 두 값이 같으면 맞바꿈을 못 잰다"

    await engine.execute_sell("012200", Signal.STOP_LOSS, "momentum")

    assert mock_insert_trade.await_count == 1
    record = mock_insert_trade.await_args.args[0]
    assert record.order_no == "ORDER-M-1"
    assert record.ticker == "012200"
    assert record.trade_type is TradeType.SELL
    assert record.status is TradeStatus.PENDING
    assert record.strategy == "momentum"
    assert record.quantity == pos.quantity          # 10
    assert record.price == pos.buy_price            # 4500 — 주 경로는 매수가가 정답
```

### (b) 폴백 PENDING record — **기존 테스트에 단언 추가**

**파일·위치**: `tests/unit/engine/test_order_engine_sell_fallback.py`
`test_execute_sell_when_market_disallowed_then_limit_fallback_at_5_ticks_down` 의 **`:264` 바로 아래**.
주입 지점·픽스처 모두 이미 있다.

```python
    pos = strategy.state.positions["012200"]
    assert expected_fallback != pos.buy_price, (
        "픽스처 전제 붕괴 — 폴백가와 매수가가 같아지면 아래 price 단언이 공허하다"
    )
    assert record.ticker == "012200"
    assert record.trade_type is TradeType.SELL
    assert record.status is TradeStatus.PENDING
    assert record.strategy == "momentum"
    assert record.quantity == pos.quantity          # 10
    assert record.price == expected_fallback, (     # 4475 — 매수가 4500 이 아니다
        f"폴백 PENDING 가격 {record.price} (기대 {expected_fallback}) — "
        "매수가가 아니라 실제 발주한 폴백 지정가여야 한다"
    )
```

### (c) 선행 체크 WARNING 문구 2건 — **기존 테스트 2개에 `caplog` 추가**

두 skip 분기를 만드는 테스트가 **이미 있다**. 새 시나리오가 필요 없다.

| 경로 | 파일::테스트 | 이미 하는 것 |
|---|---|---|
| 폴백 | `tests/unit/engine/test_order_engine_sell_fallback.py::test_execute_sell_when_fallback_and_completion_arrives_first_then_no_pending_insert` (`:421-451`) | `engine._completed_orders.add(fallback_order_no)` |
| 주 | `tests/integration/test_sell_rejection_integration.py::test_c8_when_completed_orders_race_then_pending_insert_skipped` (`:553-572`) | `engine._completed_orders.add(order_no)` |

> 주 경로를 단위로 가져오고 싶으면 (a) 의 신규 테스트에 `engine._completed_orders.add("ORDER-M-1")`
> 변형을 하나 더 두면 된다(그러면 `mock_insert_trade.await_count == 0` 이 된다).

🔴 **caplog 단언은 레벨 + 접두로 한정한다.** CI 루트 로거가 DEBUG 라 개수 단언이 실패 흔적
debug 행까지 잡는다(2026-09-05 사고). 이 메시지는 `[marker]` 접두가 **없고** `"매도 "` 로 시작한다.

```python
    caplog.set_level(logging.WARNING, logger="src.engine.order_engine")
    # ... execute_sell ...
    hits = [
        r.getMessage() for r in caplog.records
        if r.levelno >= logging.WARNING
        and r.getMessage().startswith("매도 ")
        and "PENDING INSERT 생략" in r.getMessage()
    ]
    assert len(hits) == 1, f"선행 체크 WARNING {len(hits)}행 (기대 1행): {hits}"
    assert "폴백" in hits[0]        # 폴백 경로
    # 주 경로는:  assert "폴백" not in hits[0]
```

이 **쌍**이 M12(라벨 비우기)와 T-1(라벨 맞바꿈)을 **둘 다** 잡는 유일한 축이다.
한쪽만 세우면 맞바꿈이 통과한다.

---

## 5. 영향 인덱스

- `_workspace/test_index.yaml` — `generated_at: 2026-09-20T04:15:50.179Z`, 재생성 반영 확인.
- 신규 `tests/unit/ast/test_cycle328_sell_pending_helper.py` 가 diff 에 **119곳** 추가돼 있고
  `backend['src/engine/order_engine.py'].direct_tests` 에 포함된다. 수정된
  `tests/unit/engine/test_order_engine_sell_fallback.py` 도 그대로 있다. **반영 완료.**
- ⚠️ 다만 `src/engine/order_engine.py` 의 `direct_tests` 가 **1,067개 = 백엔드 테스트 전부**이고
  `transitive_tests` 는 0 이다(`src/engine/risk.py` 도 동일. 비교: `turtle_sizing.py` direct 2 /
  `scheduler.py` direct 239). **이 모듈은 인덱스 선택력이 0** 이라 "영향 테스트만 돌린다" 가
  곧 "전체를 돌린다" 이다. 과선택이라 안전 방향이고 결함은 아니지만,
  **이 파일을 고치는 사이클에서 인덱스를 시간 절약 근거로 쓸 수 없다.**
- 위 (a)~(c) 테스트를 추가한 뒤 `python tools/test_impact/build_index.py` 재실행이 따라온다
  (신규 테스트 함수는 기존 파일 안이면 파일 단위 인덱스가 이미 덮는다 — 신규 **파일**을 만들 때만 필수).

---

## 6. sha 재핀 정합 — 10곳 전부 일치, 핀은 살아 있다

- 현재 소스 sha = `f970c625a33b4e63065eb3b27445e6b61b8f23a392c58c6fa017f519c5afb8ca`
- 카드가 나열한 **10개 파일 전부 같은 값**으로 박혀 있고, 그 10개를 실행해 **472 passed** 확인.
- 핀이 공허하지 않음도 확인 — 파일 끝에 주석 한 줄을 붙이자 **10개가 전부** 붉어졌고, 원복하자 전부 초록.
- 참고: 재핀을 틀리면 붉어지는 **지점은 14곳**이다 — 핀 10 + 핀을 감시하는 메타가드 4
  (`test_cycle223g3_ast_guard_sees_staged` 3건 · `test_cycle276_ast_order_hook::test_c6_4c`).
  카드의 "10개 파일" 은 **파일 기준으로는 맞다**.
- 🔴 **`95cbb103…` 은 order_engine 핀이 아니다.** `tests/unit/ast/test_cycle282_ast_purity.py:387`
  의 `"src/engine/scanner.py":` 아래 값이고, 실제 `src/engine/scanner.py` sha 와 일치한다.
  그 AST 파일들은 여러 소스를 한꺼번에 핀하므로 **`order_engine.py` 핀만 골라 봐야 한다.**
  재핀할 것이 없다.

### 워크트리 오염 기록

- 리더가 13:23 에 관측한 `870d3b77f5ac7564…` 는 **tdd-engineer 의 M5 돌연변이 판본**이다
  (돌연변이 판본들을 repo 무접촉으로 메모리에서 재생성해 해시를 재계산했다).
  그 상태로 전체 스위트를 돌리느라 **약 6분 30초** 파일을 잡고 있었다. M13+M5 조합
  (`880fd04b…`)도 약 5분 36초 창이 있었다.
- tdd-engineer 가 쓴 repo 파일은 `src/engine/order_engine.py` **하나뿐**이다
  (돌연변이 20회 + 직접 append 1회, **매번 직후 원복**). AST 핀 파일·`tests/**`·`_workspace/**` 는
  **한 글자도 쓰지 않았다.** 마지막 상태는 원복본이고 `shasum` · `git diff --stat` ·
  전체 스위트 11,122 passed 로 3중 확인했다.
- 백업(복원하지 않음): `/private/tmp/claude-501/-Users-koscom-Projects-auto-stock/0ab1df6c-a50f-4d03-a764-95fae85df295/scratchpad/order_engine.ORIG.py`
- 🔴 **반대 방향 오염도 성립한다** — tdd-engineer 의 원복이 `gate-tester` 의 돌연변이를 덮었을 수 있다.
  두 관문의 돌연변이 결과는 서로 교차 검증된 것(T-1↔M12, T-3↔M5/M13)만 확정으로 읽는다.

---

## 판정

- **미커버 구간은 없다.** 헬퍼 `src/engine/order_engine.py:885-938` 은 미커버 줄 0 · 미커버 분기 0이고
  세 분기(hit·miss·`except`)가 전부 실측 도달한다. 진행 규약 5절의
  「회귀를 못 세운다」에 해당하지 않는다 — **세울 수 있고, 4.6 에 정확히 적었다.**
- **구조 축은 강하게 판정된다** — 접수 후 경계의 위치·폭(`test_g328_3`·`3b`) · 매핑↔호출 순서와
  그 사이 `await`(`test_g328_1`) · 최초 양보점(`test_g328_2`) · 라벨 조회 안전성(`test_g328_4`).
  카드가 "그물 없음"이라 적은 M7·M8 은 선행 의뢰 ②가 실제로 닫았다.
- **행위 축도 예외 경계와 선행 체크는 판정된다** — M1·M2·M6·M4a·M4b·M3 전부 붉어진다.
- 🔴 **판정되지 않는 것은 호출부가 헬퍼로 넘기는 값이다.** 6개 인자 중 4개가 두 호출부 모두
  무방비이고, 전체 스위트 11,108개 행위 단언 중 0개가 반응한다. 관문 둘이 독립적으로 같은 결론에 닿았다.
- **판정을 뒤집는 조건**: 4.6 의 (a)·(b)·(c) 가 착지하고, 각각에 대해 M5·M12·M13·T-1·T-3 을
  다시 넣어 **붉어지는 것을 확인**하면 「예」다. 되돌림이 커밋 revert 를 뜻할 필요는 없다 —
  그 단언들을 먼저 착지시킨 뒤 2단계로 가면 된다.

그물 판정 가능: 아니오  *(1차 — 아래 「재판정」이 최종이다)*

---

## 재판정 (시나리오 J 착지 후)

### 방법 — 격리 사본에서만 깼다

원본 리포는 **읽기만** 했다. `rsync` 로
`/private/tmp/claude-501/-Users-koscom-Projects-auto-stock/0ab1df6c-a50f-4d03-a764-95fae85df295/scratchpad/iso`
에 사본을 만들고 돌연변이는 전부 그 안에서만 넣고 뺐다. 매 단계 원본
`src/engine/order_engine.py` sha 가 `f970c625…` 로 **불변**임을 확인했다.

### 돌연변이 14종 — 전부 붉어진다

대상 = `test_order_engine_sell_fallback.py`(11) + `test_cycle327_sell_fill_during_insert.py` +
`test_cycle328_sell_pending_helper.py` (기준선 24 passed).

| # | 깬 것 | 붉어진 테스트 |
|---|---|---|
| M5 | 폴백 `record_price` → `pos.buy_price` | `test_sell_fallback_pending_record_carries_fallback_price_not_buy_price` |
| M13 | 폴백 `quantity` → `1` | 〃 |
| **M5+M13** | **4.2 의 그 돌연변이** | 〃 (전에는 전체 11,108 행위 단언 중 **0건**) |
| M12 | 라벨 `"폴백 "` → `""` | `test_sell_pending_skip_warning_distinguishes_market_and_fallback` |
| M12swap | 라벨 두 값 맞바꿈 (T-1) | 〃 |
| T3 | 주 경로 `record_price` ↔ `quantity` | `test_sell_pending_record_carries_buy_price_and_position_qty` |
| J-STRAT-FB | 폴백 `strategy_id` 오염 | 폴백 record 단언 |
| J-STRAT-MAIN | 주 경로 `strategy_id` 오염 | 주 경로 record 단언 |
| J-TICKER-FB | 폴백 `ticker` 오염 | 폴백 record 단언 |
| CP1 | 폴백 `path` 만 `"market"` | 문구 쌍 + 시나리오 I (2건) |
| CP2 | 폴백 `order_no` 만 `result.order_no` | **6건** |
| CP3 | 주 경로 `path` 만 `"fallback"` | 문구 쌍 + `test_sell_emits_fill_during_insert_marker` (2건) |
| CP-2LINE | 복붙 후 두 줄만 고치고 `path` 는 안 고침 | 시나리오 I + 문구 쌍 (2건) |
| CP-FULL | 폴백 블록 = 주 경로 블록 **그대로** | **6건** |

### 1. 빠진 축 ①은 닫혔다

「주 경로 블록을 복붙하고 두 줄만 고치는」 실패 모드를 **5가지 조합으로 분해해 전부 돌렸고
하나도 빠져나가지 못한다**(CP1 · CP2 · CP3 · CP-2LINE · CP-FULL).

두 호출부의 실제 차이는 `order_no` · `record_price` · `path` **세 줄**뿐이고, 각각을
단독으로 틀리게 해도 잡힌다 — 즉 어떤 부분 조합도 통과하지 못한다(단독이 전부 잡히면
합집합도 잡힌다).

**CP2 는 단언이 아니라 예외 전파로 잡힌다** — 폴백 시점에 `result` 는 1차 `place_order` 가
raise 해서 바인딩돼 있지 않으므로, `result.order_no` 는 **호출부에서 인자를 평가하는 순간**
터져 헬퍼의 `except Exception` 안으로 들어가지도 못하고 `execute_sell` 을 관통한다.
조용한 실패가 아니라 **크래시**라 더 시끄럽다. 6건이 붉어진다.

**남은 미판정 조합은 `ticker_name` 파생식 하나뿐이다**
(`t(ticker).split("(")[0] if "(" in t(ticker) else ""`). 표시용이고 자본 위험 0 이라
넣지 않기로 한 판단에 **동의한다** — 다르게 볼 이유를 찾지 못했다.

### 2. 4.2 의 돌연변이 재실행 — 반응한다

`M5+M13`(폴백 `record_price`→`pos.buy_price` **+** `quantity`→`1`)을 다시 넣었다.

- **전**: 백엔드 전체 `14 failed, 11108 passed` — 붉어진 14건이 **전부 sha/byte 핀**, 행위 단언 0건
- **후**: `test_sell_fallback_pending_record_carries_fallback_price_not_buy_price` **1건** 붉음

격리 사본에서 실행했고 원본은 무접촉이다.

### 3. 전체 스위트 기준선 — 11,125 확인

격리 사본 전체 실행 = `17 failed, 11108 passed, 12 skipped, 329 xfailed, 12 xpassed`.
합계 **11,125** 로 리더 실측과 일치한다.

⚠️ 그 17건은 **사본에 `.git` 이 없어서** 나는 것이다(`*_diff_zero` · `guard_sees_staged` ·
`gitignored` · `tracked` · `changed_files` 계열 = 전부 git 의존 가드). 원본에서는 이 17건이
초록이므로 **사본으로는 git 의존 가드를 검증할 수 없다** — 그 축은 아래 6번의 직접 대조로 갈음했다.

### 4. 판정

값 축이 닫혔다. 1차에서 「판정을 뒤집는 조건」으로 적은 것
(4.6 의 (a)·(b)·(c) 착지 + M5·M12·M13·T-1·T-3 재확인)이 **전부 충족**됐고,
거기에 복붙 실패 모드 5종과 대칭 필드 3종을 더 넣어도 빠져나가는 것이 없다.

이제 이 변경은 **구조 축**(경계 위치·폭 · 매핑↔호출 순서 · 최초 양보점 · 라벨 조회 안전성)과
**행위 축**(예외 경계 · 선행 체크 · 흡수기 인자 · 호출부가 넘기는 값 6개 전부)이 모두 판정된다.

---

## 5·6 재확인 (리더 변경 이후)

- **영향 인덱스** — `generated_at: 2026-09-20T04:58:26.800Z` 로 재생성됐다.
  `backend['src/engine/order_engine.py'].direct_tests` 에 `test_order_engine_sell_fallback.py` ·
  `test_cycle328_sell_pending_helper.py` **둘 다 포함**. **반영 완료.**
  ⚠️ `direct 1067 / transitive 0` 은 **그대로**다 — 이 모듈의 인덱스 선택력은 여전히 0이고,
  "영향 테스트만" 이 곧 "전체" 다. 안전 방향이라 결함은 아니지만 시간 절약 근거로는 못 쓴다.
- **sha 재핀 정합** — 현재 소스 sha `f970c625a33b4e63065eb3b27445e6b61b8f23a392c58c6fa017f519c5afb8ca`,
  10곳 핀 **10/10 일치**(직접 grep 대조). **소스 sha 가 1차 때와 같다** —
  정본 2곳 수정은 문서였고 `src/` 를 건드리지 않았으므로 재핀이 필요 없다.
  `95cbb103…` 은 여전히 `src/engine/scanner.py` 의 핀이고 그 파일 실제 sha 와 일치한다.

---

## 2단계로 넘기는 것 (이번 판정 밖)

1. **`test_g328_0c` 는 2단계에서 반드시 뒤집히거나 삭제된다** — 매수를 같은 헬퍼로 승격하는
   순간 그 단언(`execute_buy` 에서 헬퍼 호출 0건)이 거짓이 된다. 파일 docstring 에 이미 적혔다.
2. 🔴 **매수 축에는 아직 대칭 단언이 없다.** `tests/unit/engine/test_order_engine_buy.py:211`·`:463`
   이 `record_arg.price` 만 보고(한 곳은 `order_no` 추가), `quantity`/`strategy`/`ticker`/
   `trade_type`/`status` 는 **주·폴백 어느 쪽도 단언하지 않는다.** 2단계가 매수 2곳을 같은
   헬퍼로 올리면 **지금 매도에서 닫은 그 구멍이 매수 쪽에 그대로 열린 채로** 인자 4개가
   추가된다. 2단계 착수 시 시나리오 J 와 같은 대칭 단언을 매수에도 세워야 한다.

그물 판정 가능: 예
