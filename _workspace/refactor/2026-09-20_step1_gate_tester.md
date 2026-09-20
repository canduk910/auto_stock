# 1단계 코드리뷰 관문 — tester (행위 보존) · 7~8번 + 판정

> 대상 = `src/engine/order_engine.py::execute_sell` 접수 후 구간 추출
> (`_persist_sell_pending_after_send`). 설계 카드 = [`2026-09-20_step1_card.md`](2026-09-20_step1_card.md)
> 1~6번(로그 byte 대조 · `record` 9필드 · 예외 전파 · `_selling` 무접촉 · 거부 분류 순서)은
> 이미 회신했다. 이 파일은 **7번의 잘린 뒷부분 · 8번 · 판정 줄**만 담는다.

---

## 7. 회귀 실행 결과

측정 시 소스 sha 를 **실행 전후로 확인**했다(워크트리 충돌 사고 뒤라 "그 순간 어느 판본이었나"가
결과의 전제다). 정상 판본 = `f970c625a33b4e63065eb3b27445e6b61b8f23a392c58c6fa017f519c5afb8ca`.

### 7-a. 요구 회귀 목록 — **111 passed**

```
python -m pytest -q -p no:randomly --no-cov \
  tests/unit/engine/test_cycle327_sell_fill_during_insert.py \
  tests/unit/engine/test_order_engine_sell_fallback.py \
  tests/unit/engine/test_cycle229_sell_fallback_e2e.py \
  tests/unit/engine/test_cycle236_sell_qty_exceeded.py \
  tests/unit/engine/test_cycle287_krx_after_exit.py \
  tests/unit/ast/test_cycle185_cluster1_ast.py \
  tests/unit/engine/test_cycle185_cluster1_reset.py \
  tests/integration/test_sell_rejection_integration.py \
  tests/unit/ast/test_cycle328_sell_pending_helper.py
→ 111 passed in 7.44s
```

⚠️ **의뢰 경로 하나가 존재하지 않는다.** `tests/unit/engine/test_cycle185_cluster1_ast.py` 는
없다 — 실제 경로는 `tests/unit/ast/test_cycle185_cluster1_ast.py` 이고,
형제 파일 `tests/unit/engine/test_cycle185_cluster1_reset.py` 를 함께 돌렸다.
(그대로 실행하면 `ERROR: file or directory not found` 로 **한 건도 안 돈다.**)

이 실행은 **격리 스냅샷**(`git archive HEAD` + 현 작업본 `order_engine.py` + 스테이지된
시나리오 I + 워크트리의 `test_cycle328_…`)에서 돌렸다. 공유 워크트리가 동시 편집 중일 수
있어 결과의 재현성을 확보하기 위해서다. 111 = 이전 측정 110 + team-lead 가 추가한
`test_g328_3b` 1건.

### 7-b. AST 가드 전체 — **1805 passed, 4 skipped, 26 xfailed**

```
sha 전: f970c625a33b4e63
1805 passed, 4 skipped, 26 xfailed in 18.40s
sha 후: f970c625a33b4e63
```

이것만은 **실제 워크트리**에서 돌렸다 — `test_cycle253_ast_channel_probe.py` 등 일부 스코프
가드가 `git` 을 직접 호출해 격리 스냅샷(`.git` 없음)에서는 15건이 구조적으로 붉기 때문이다.
실행 전후 sha 가 같아 이 숫자는 정상 판본의 것이 맞다. `order_engine.py` 전체 파일 sha 핀
10파일 재핀이 반영돼 있다.

### 7-c. 새 헬퍼 커버리지 — **미커버 0줄 · 부분 분기 0**

`_persist_sell_pending_after_send` 의 실제 라인 범위는 **`order_engine.py:885-938`** 이다
(`ast` 로 `lineno`/`end_lineno` 실측). 같은 명령의 `term-missing` 결과:

```
Name                         Stmts   Miss Branch BrPart  Cover   Missing
src/engine/order_engine.py    1065    487    318     28    53%   133, 135, 184-185, 195,
  276-283, 390, 393, 405-406, 446-447, 454->460, 457-458, 515-519, 642-653, 678->685,
  680-681, 689-690, 713-714, 739-741, 761-768, 772-774, 781-791, 818-819, 826-827,
  955-1405, 1423-1424, 1448-1450, 1454-1456, 1510->1533, 1518-1519, 1584-1587,
  1737-1738, 1816-1817, 1852, 1892-1893, 1921-1931, 2021->2034, 2029-2030, 2057->1591,
  2068-2069, 2076-2077, 2098-2103, 2127-2189, 2203-2238, 2275-2472, 2502-2622, 2627,
  2651, 2680, 2685->exit, 2694, 2726, 2744-2746, 2768->2796, 2778, 2782-2791,
  2811->2819, 2820-2823, 2826->exit, 2852-2888
85 passed
```

**`885-938` 구간이 Missing 목록에 한 줄도 없다.** 인접 구간이 `826-827` 과 `955-1405`
(= `execute_buy` 본문)라 헬퍼가 그 사이에 통째로 덮여 있음이 경계로도 확인된다.
`->` 로 표기되는 부분 분기 28건 중에도 885-938 범위는 없다.
착수 전 미커버였던 폴백 경계(구 `:1951-1952`)는 시나리오 I 가 닫았고, 추출 뒤에는 그 두 줄이
헬퍼의 `except Exception` 한 곳으로 합쳐져 주·폴백 두 경로가 함께 그 줄을 덮는다.

전체 커버리지 53% 가 `fail-under=60` 에 걸리는 것은 **부분 실행의 산물**이고 설계 카드의
착수 전 측정(53%)과 같다 — 이 변경으로 내려간 것이 아니다.

### 7-d. 백엔드 광역 — **7465 passed, 1 failed (선재)**

```
pytest tests/unit/engine tests/integration tests/unit/db
→ 1 failed, 7465 passed, 6 skipped, 281 xfailed, 12 xpassed
FAILED tests/unit/db/test_cycle64_price_filter_scanner_system_config.py::test_A1_get_price_filter_default_no_mode_field
```

**이 1건은 선재 결함이고 이번 변경과 무관하다.** 근거 2:
- 단독 실행하면 초록이다(`4 passed`) — 테스트 간 모듈 전역 오염(순서 의존).
- **HEAD 스냅샷(`4779683`)에서 동일 인자로 돌려도 똑같이 붉다**
  (`2 failed, 7462 passed` — 나머지 1건은 스냅샷에 `.git` 이 없어 붉은 8영역 digest 가드).

---

## 8. 내가 고안한 돌연변이

### 8-A. 공유 워크트리에서 돌린 3건 — 🔴 **결과는 미확증**

`gate-tdd` 와 같은 워크트리에서 동시에 같은 파일을 돌연변이·원복해 충돌 사고가 났다.
아래 결과는 관측된 그대로 적되 **전부 「미확증 — 격리 워크트리 재실시 필요」** 로 내린다.
각 판본의 sha 를 적어 두었으니 재실시 시 적용 직후 sha 대조로 "내 변경만 들어갔다"를
매번 검증할 수 있다.

| # | 돌연변이 | 판본 sha | 관측된 결과 | 상태 |
|---|---|---|---|---|
| T-1 | `_SELL_PENDING_SKIP_PATH_LABEL` 의 두 값을 맞바꿈 (`{"market": "폴백 ", "fallback": ""}`) | `251de7fa…` | 🔴 행위 그물 **92건 전부 초록**. sha 핀 13건만 붉음 | 미확증 |
| T-2 | 두 호출부의 `path` 리터럴 맞바꿈 | `2be5986c…` | ✅ **2건 붉음** — `test_sell_emits_fill_during_insert_marker` · 시나리오 I | 미확증 |
| T-3 | 주 경로 호출부 `record_price=pos.quantity, quantity=pos.buy_price` | `437da673…` | 🔴 백엔드 광역 **7,465건 전부 초록**. sha 핀 1건만 붉음 | 미확증 |

정상 판본 = `f970c625…`. 관측하신 `870d3b77…` 는 위 셋 중 어느 것도 아니다.

**T-1 이 이번 추출이 새로 만든 단일 실패점이다.** 추출 전에는 두 경로의 WARNING 문구가
각자 리터럴이었는데, 지금은 표의 값 두 개가 두 경로의 문구를 **동시에** 결정한다. 그런데
그 문구를 고정하는 단언이 하나도 없다. sha 핀은 주석 한 줄에도 붉어지고 **이 리팩토링이
단계마다 재핀하는 대상**이라 판별기로 쓸 수 없다. 피해는 관측 한정(매매 행위 0)이고
`[sell_fill_during_insert] path=` / `[sell_post_send_error] path=` 가 원문이라 완전히
눈멀지는 않지만, "선행 체결통보가 주 경로에서 왔나 폴백에서 왔나"를 WARNING 한 줄로 읽던
판독이 정반대가 된다.

**T-3 은 추출이 만든 결함은 아니지만(HEAD 도 동일하게 무방비) 추출이 위험 표면을 키운다.**
폴백은 `test_execute_sell_when_market_disallowed_then_limit_fallback_at_5_ticks_down` 이
`record.price == fallback_price` 를 잡지만, **주 경로 PENDING `record` 의 `price`/`quantity`
를 단언하는 회귀가 리포 전체에 0건**이다. 이제 두 인자가 같은 모양의 키워드 두 줄로
나란히 서고 호출부 둘이 거의 동일해서 복붙 오류 표면이 늘었다. 잘못 들어가면
`trade_history` 에 `price=10, quantity=4500` 인 매도 PENDING 행이 남고(주문 자체는 정상)
체결통보의 `price=` 보정이 `quantity` 는 덮지 않으므로 **손익 산출이 조용히 틀어진다**.

→ tdd-engineer 의뢰 후보 2건: (1) 두 경로 선행체크 WARNING 의 **렌더 결과**를 caplog 로 고정
(2) 주 경로 `record.price == pos.buy_price` · `record.quantity == pos.quantity` 단언.

### 8-B. 🔴 경계 축소 돌연변이 — **격리 스냅샷에서 실측, 도메인 지적이 그대로 재현된다**

team-lead 요청으로 캡처 하네스를 **경계 축소 판본**에 물렸다. 공유 워크트리의 `src/` 는
한 글자도 쓰지 않았다 — 격리 디렉터리 두 개를 새로 떠서 그 안에서만 돌렸다.

| 스냅샷 | 구성 | `order_engine.py` sha |
|---|---|---|
| `work_snapshot` | `git archive HEAD` + 현 작업본 src + 스테이지된 시나리오 I + `test_cycle328_…` | `f970c625a33b4e63065e` |
| `narrow_snapshot` | 위의 사본 + 헬퍼 경계만 `except (UniqueViolationError, TimeoutError, OSError)` 로 축소 | `14b3a3d39d1dc60f80ba` |

바꾼 것은 **그 한 줄뿐**이다. 7 시나리오(`N1`~`N7`)를 양쪽에서 돌려 JSON 을 diff 했다.

#### 답 1 — 어떤 필드가 달라지는가

| 시나리오 | `raised` | `place_order` | `_selling` | `_pending_next_day_clear` |
|---|---|---|---|---|
| **N1** 주 · `RuntimeError` | `None` → `None` | **1 → 3** 🔴 | `['012200']` → `[]` 🔴 | 변화 없음 |
| **N2** 폴백 · `RuntimeError` | `None` → **`RuntimeError`** 🔴 | 2 → 2 | 변화 없음 | 변화 없음 |
| **N3** 폴백 · `KisApiError` | `None` → `None` | 2 → 2 | `['012200']` → `[]` 🔴 | 변화 없음(장중) |
| **N4** 폴백 · `KisApiError` + NXT 시간대 | `None` → `None` | 2 → 2 | `['012200']` → `[]` 🔴 | `[]` → **`['012200\|momentum']`** 🔴 |
| **N5** 주 · `KisApiError` | `None` → `None` | **1 → 3** 🔴 | `['012200']` → `[]` 🔴 | 변화 없음 |
| **N6** 폴백 · `TimeoutError` | — | — | — | — (**완전 동일**) |
| **N7** 주 · `TimeoutError` | — | — | — | — (**완전 동일**) |

`positions` 는 7 시나리오 전부에서 변하지 않는다 — 포지션은 보존되므로 **화면·DB 로는
정상으로 보인다.** 그것이 이 결함이 조용한 이유다.

🔴 **N6·N7 이 왜 중요한가** — 좁힌 튜플 **안**의 예외는 행위가 완전히 같다. 기존 회귀
(`test_sell_does_not_refire_on_generic_insert_error` 와 시나리오 I)가 **둘 다
`TimeoutError`/`UniqueViolationError` 를 쓴다.** 그래서 경계를 좁혀도 13건이 전부
초록이었던 것이고, 이것이 `test_g328_3b`(최상위 `try` 의 핸들러가 정확히 1개이고 타입이
`Exception`) 가 **구조 가드일 수밖에 없는 이유**다 — 행위 테스트로 덮으려면 튜플 밖
예외 타입을 열거해야 하는데 그 열거 자체가 같은 종류의 누락에 노출된다.

#### 답 2 — 도메인이 말한 「거래소에 살아 있는 주문을 장부에 거부로 적고 익일청산 큐에 넣는다」가 재현되는가

**정확히 재현된다.** N4 가 그것이다. `place_order` 가 2회 = 폴백 주문 `ORD-N4_…` 가
**접수에 성공**한 상태인데, 산출물은 "폴백 모두 거부"다.

```json
// narrow_snapshot — N4_fb_KisApiError_nxt   🔴 결함 재현
{
  "raised": null,
  "place_order_calls": 2,                      // ← 폴백 주문은 접수됐다
  "positions": ["012200"],
  "selling": [],                               // ← 손절 진행 표식 해제
  "pending_next_day_clear": ["012200|momentum"],   // ← 익일 09:00 청산 큐 등록
  "write_log": [
    "WARNING|매도 시장가+지정가 폴백 모두 거부 — 포지션 보존: 012200 (전략: momentum, [EGW00201] 초당 거래건수를 초과하였습니다.)",
    "WARNING|[next_day_clear_deferred] ticker=012200 strategy=momentum reason=market_order_disallowed_nxt_fallback_fail"
  ],
  "error": [
    "매도 지정가 폴백도 거부 — 재시도 중단, 포지션 보존: 012200 ([APBK1943] 시장가호가불가로 주문이 불가합니다. → [EGW00201] 초당 거래건수를 초과하였습니다.)"
  ]
}
```

```json
// work_snapshot — N4_fb_KisApiError_nxt   ✅ 현행(정상)
{
  "raised": null,
  "place_order_calls": 2,
  "positions": ["012200"],
  "selling": ["012200"],
  "pending_next_day_clear": [],
  "write_log": [],
  "error": [
    "[sell_post_send_error] ticker=012200 order_no=ORD-N4_fb_KisApiError_nxt strategy=momentum path=fallback — 주문은 접수됐다. 재발사하지 않고 체결통보·동기화에 맡긴다."
  ]
}
```

사슬 = 헬퍼에서 샌 `KisApiError` 가 폴백 호출부의 **형제 핸들러** `except KisApiError as fb_err`
(`order_engine.py:1995-2043`)에 걸린다 → 그 핸들러는 "폴백 주문이 거부됐다"는 전제로
`_selling.discard` → `write_log("WARNING", "폴백 모두 거부")` →
`register_market_order_disallowed(fallback_succeeded=False)` → NXT 시간대면
`_pending_next_day_clear.add((ticker, strategy_id))` → `return`.
그 결과 **익일 09:00 `_drain_pending_next_day_clear` 가 같은 종목을 KRX 시장가로 다시 판다.**
장부(`write_log`)와 거래소의 사실이 정반대가 되고, `_selling` 이 풀려 그 사이 `risk.on_tick`
재평가까지 열린다.

그리고 주 경로(N1·N5)는 **cycle327 실사고 그 자체가 되살아난다** — 발사 1회 → **3회**:

```json
// narrow_snapshot — N1_main_RuntimeError   🔴 cycle327 재현
{
  "raised": null,
  "place_order_calls": 3,
  "selling": [],
  "positions": ["012200"],
  "warning": [
    "매도 주문 실패 (시도 1/3): 012200 — DB 드라이버 내부 오류",
    "매도 주문 실패 (시도 2/3): 012200 — DB 드라이버 내부 오류",
    "매도 주문 실패 (시도 3/3): 012200 — DB 드라이버 내부 오류"
  ],
  "write_log": ["CRITICAL|매도 주문 최종 실패: 012200 STOP_LOSS — DB 드라이버 내부 오류"]
}
```

주문 **3건이 거래소에 살아 있는데** 장부에는 `CRITICAL 매도 주문 최종 실패` 가 남는다.

결론 — `test_g328_3b`(핸들러 1개 · 타입 `Exception`)의 존재 근거는 추측이 아니라 실측이다.
**경계 타입을 좁히는 것은 매도 두 경로에서 서로 다른 세 가지 사고를 동시에 되살린다**:
① 주 경로 재발사(N1·N5) ② 폴백 `risk.on_tick` 틱 중단(N2) ③ 폴백 오귀인 + 익일청산
중복 매도(N3·N4).

#### 재현 자산 (전부 scratchpad, 리포 밖)

```
.../scratchpad/work_snapshot/        격리 정상 판본 (src sha f970c625…)
.../scratchpad/narrow_snapshot/      격리 축소 판본 (src sha 14b3a3d3…)
.../scratchpad/test_zz_boundary_capture.py   7 시나리오 하네스 (양쪽에 복사해 실행)
.../scratchpad/boundary_WORK.json    정상 판본 산출물
.../scratchpad/boundary_NARROW.json  축소 판본 산출물
.../scratchpad/order_engine_WORK.py  정상 판본 백업 (f970c625…)
.../scratchpad/order_engine_HEAD.py  HEAD(4779683) 판본 (2e10df62…)
.../scratchpad/render_compare.py     1·2번 로그 렌더 byte 대조 스크립트
.../scratchpad/test_zz_behavior_capture.py   1~6번 12 시나리오 하네스
```

`.../scratchpad` = `/private/tmp/claude-501/-Users-koscom-Projects-auto-stock/0ab1df6c-a50f-4d03-a764-95fae85df295/scratchpad`

⚠️ N4 의 NXT 시간대는 `is_nxt_session_hours` 를 `True` 로 주입해 만든 조건이다(측정이
장중이었다). N3 이 같은 사슬의 장중 판이고, 주입 없이도 `_selling` 해제와 거부 오기록은
그대로 난다 — 주입이 바꾸는 것은 익일청산 큐 등록 여부 한 가지다.

---

## 부수 효과 — 21:30 일일 리포트 `top_patterns` 키가 바뀐다

의도된 폴백 꼬리 변경의 **관측 측 파급**이다. `log_metrics_collector._normalize_message`
(`src/engine/log_metrics_collector.py:45`)는 종목코드와 숫자만 마스킹하고 **메시지 전문을
200자까지 패턴 키로 쓴다.** 이 메시지는 150자라 꼬리까지 키에 들어간다.

```
HEAD   : [src.engine.order_engine] [sell_post_send_error] ticker=<TICKER> order_no=<N> strategy=momentum path=fallback — 주문은 접수됐다. 재발사하지 않는다.
WORK   : [src.engine.order_engine] [sell_post_send_error] ticker=<TICKER> order_no=<N> strategy=momentum path=fallback — 주문은 접수됐다. 재발사하지 않고 체결통보·동기화에 맡긴다.
```

- 🔴 **09-20 전후로 폴백 패턴 문자열이 달라진다 — 두 날짜의 패턴 문자열을 직접 비교하지 않는다.**
  그날의 **건수**는 영향이 없다(집계는 하루 단위이고 키가 하나로 모인다).
- ✅ **`market` 과 `fallback` 두 키가 병합되지는 않는다** — 꼬리가 같아져도 `path=market` /
  `path=fallback` 이 키에 남아 두 경로는 계속 별개 패턴으로 집계된다(실측 확인).
- 실질 영향은 없다 — `[sell_post_send_error]` 는 cycle327 이 **오늘** 착지해 운영 발생
  이력이 0건이다. 즉 비교 대상이 될 과거 패턴 자체가 없다.

## 부수 효과 — 로그 레코드 메타데이터

`logger.exception` 의 `record.funcName` 이 `execute_sell` → `_persist_sell_pending_after_send`
로 바뀌고 traceback 에 프레임이 한 겹 는다. **소비처는 없다** —
`src/main.py:75` 의 `LOG_FORMAT` 에 `funcName` 이 없고,
`_DbLogHandler.emit`(`src/main.py:200`)은 `record.getMessage()` 만 써서 `system_logs` 에
traceback 을 싣지 않는다. 리포 전체 `funcName` grep 0건.

---

## 판정

1~6번(격리 대조로 확정) + 7번(정상 판본 회귀 전량 초록, 헬퍼 미커버 0)을 근거로 판정한다.
8-A 의 T-1·T-3 은 **판정의 근거가 아니라 그물의 빈 곳을 찾는 추가 탐색**이고, 둘 다 이 단계를
되돌릴 사유가 아니다(T-1 은 관측 한정 · T-3 은 HEAD 와 동치). 8-B 는 team-lead 가 이미 세운
`test_g328_3b` 의 존재 근거를 실측으로 뒷받침한 것이고, 그 가드가 있는 현재 판본에서는
경계 축소가 구조적으로 막힌다.

행위 보존: 확인
