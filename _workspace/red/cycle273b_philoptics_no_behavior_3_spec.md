# cycle273b Red 명세 — D2(다) 필옵틱스 무행위 3건: F-3 관측 → F-1/F-2 WHERE `order_no` → F-7 `_selling` 가시화

- 작성 2026-09-10 · tdd-engineer · **기준 HEAD `1df6d7d`**
- 사용자 결정 원문(09-10 목) = "**2. D2 주문/청산 안전 3건 — 가, 다, 나 순서로 진행하자.**" ⇒ 이 문서가 **(다)**
- 정본 = `_workspace/analysis/2026-09-10_161580_root_cause.md` ·
  `_workspace/analysis/2026-09-10_cycle273_UA_order_engine.md` §5·§6·§7 ·
  보고서 §9 · 워크리스트(필옵틱스 F-1~F-9)
- ⚠️ 여기서 말하는 **F-3 은 `[trade_status_multi_update]` 관측**이다.
  **kojiro 갭 판정 오염 차단(D2 나)의 F-3 과 이름만 같고 다른 항목**이다 —
  후자는 `cycle273e_kojiro_gap_gate_spec.md`. (워크리스트 두 축의 번호 충돌, 혼동 주의)

---

## 0. 한 줄

세 항목 전부 **매매 행위 0**이다. 순서는 **F-7 → (F-3 + F-1/F-2)** 를 권고한다
(F-7 이 `scheduler.py` 라인 예산을 −27행 만들어 주고, 그 여유가 cycle273a S1 에도 필요하다).

| 항목 | 무엇 | 무행위 근거 |
|---|---|---|
| **F-3** | `update_trade_status` 가 `affected > 1` 이면 WARNING 1행 | 반환값·SQL·인자 불변, 로그만 추가 |
| **F-1/F-2** | WHERE 에 `AND order_no = $n` 추가 | WHERE 를 **좁히기만** 한다. 기본값 `None` 이면 SQL byte 동일 |
| **F-7** | stale `_selling` **유지** 3분기 가시화 | 판정(`continue` 3개·`discard` 순서·`write_log` 문자열) byte 동일 이동 + 로그 추가 |

---

## 1. F-3 — `[trade_status_multi_update]`

### 1-a. 사실

`update_trade_status`(`trade_history.py:88-123`)의 매칭 키는
`(ticker, trade_type, status='PENDING', strategy)` 이고 **`ORDER BY`·`LIMIT` 이 없다**.
docstring `:96` 의 "최신 PENDING" 은 SQL 과 어긋난다 — "최신" 이 없다.
⇒ 조건을 만족하는 행이 여럿이면 **전부** 갱신된다.

`affected` 는 오늘 `logger.debug`(`:121-122`)로만 남는다. `src/main.py::_DbLogHandler` 가
**INFO 컷**이라 debug 는 `system_logs` 에 도달하지 않는다 ⇒ **과거 재발 여부에 무증거(D-3)**.

### 1-b. 어디에 놓는가 — **`trade_history.update_trade_status` 안** (권고)

정본 §6 표는 `order_engine.py` 2지점(C1·C3)을 적었으나 코드 근거는 db 쪽이 낫다:

1. **범위** — C1·C3 만이 아니라 C2·C4·**C5·C6**(CANCELLED)까지 덮는다. 데이터가
   *소실*되는 쪽이 바로 CANCELLED 축이다(cycle273a §2).
2. **8영역 diff 축소** — `order_engine.py`(8영역) 대신 `trade_history.py`. 관측을 8영역
   밖에 두는 것은 cycle258 `observer_trace` 관례와도 맞는다.
3. **단일 진실원** — F-1 과 같은 함수라 diff 가 한 덩어리로 읽힌다.

⚠️ **정본 표의 문면을 바꾸는 제안이다** — 사용자 결정 원문은 지점을 지정하지 않았다(§9 O-B1).

### 1-c. 형태

```python
affected = _parse_affected(result)
if affected > 1:
    logger.warning(
        "[trade_status_multi_update] ticker=%s trade_type=%s status=%s strategy=%s "
        "order_no=%s affected=%d — 한 주문의 체결이 다중 행을 덮었다",
        ticker, trade_type.value, status.value, strategy, order_no or "-", affected,
    )
```

- **WARNING 이상**(INFO/DEBUG 는 `system_logs` 미적재).
- **cap 불필요** — 발화가 곧 결함이고 정상 운영에서는 0 이어야 한다.
- `%r` 없음 ⇒ 포맷 예외 여지 없음. 굳이 방어한다면 `observer_trace.trace_observer_failure`.

### 1-d. ⚠️ 진단력의 정직한 한계

**F-1 과 같은 커밋에 들어가면 F-3 는 과거를 재지 못한다.** F-1 이 `order_no` 를 WHERE 에
넣는 순간 migration 029 부분 UNIQUE `(ticker, order_no, trade_type)` 때문에 `affected > 1` 은
**비어 있지 않은 order_no 에 대해 구조적으로 불가능**해진다. ⇒ F-3 는 D-3("과거 재발을 셀 수
없다")을 **닫지 못하고**, 대신 **영구 회귀 감시자**가 된다(WHERE·인덱스가 후퇴하면 붉어진다 /
`order_no=''` 인 수기 행에는 여전히 유효).

순서를 "F-3 먼저 → 며칠 뒤 F-1" 로 나누면 **미래 며칠치**는 셀 수 있지만 그동안 161580
오염이 계속 일어난다. ⇒ **권고 = 같은 커밋** + §2-c 의 `affected == 0` 진단을 함께 넣어
F-1 의 부작용을 즉시 보이게 한다.

---

## 2. F-1/F-2 — WHERE 에 `order_no`

### 2-a. 최소 설계

```python
# 시그니처 (cycle273a 의 match_partial 과 같은 자리)
async def update_trade_status(..., *, order_no: str | None = None, match_partial: bool = False) -> int
# WHERE
if order_no is not None:
    args.append(order_no)
    where += f" AND order_no = ${len(args)}"
```

`order_no=None`(기본)이면 SQL 은 **현행과 byte 동일** ⇒ scheduler 의 죽은 import·기존 117 hit 무영향.

### 2-b. 어느 호출부에 넣는가 — **6곳 전부** (권고)

정본 F-2 는 C1·C3 만 적었다. 코드 근거로는 전부다:

| # | 이유 |
|---|---|
| C1·C3 | 161580 본 사건(같은 ticker·strategy 의 **다른 주문** PENDING 행을 덮었다) |
| C2·C4 | 같은 오염이 PARTIAL 축에서 일어난다 — 좁히기만 하므로 무해 |
| **C5·C6** | 🔴 **가장 위험**. 부분체결 주문 A 의 30초 타이머가 같은 ticker·strategy 의 **다른 주문 B 의 PENDING 행**을 `CANCELLED` 로 뒤집을 수 있다. 그러면 B 의 체결통보는 1차 UPDATE 0 → 보정 INSERT UniqueViolation → **강제 UPDATE 는 `PENDING∪PARTIAL` 만 보므로 CANCELLED 인 B 를 못 집는다** ⇒ `[buy_fill_correction_forced_update_zero]` ERROR + **B 행 영구 CANCELLED** = 정산·sync 양쪽 소실 |

⚠️ 정본 문면(2곳)과 다르므로 §9 O-B2.

### 2-c. 🔴 이 사이클 최대 위험 — `order_no` 문자열 표기 불일치

- 체결통보: `src/realtime/handler.py:682` `order_no = fields[2]` — **정규화 0**
- REST: `src/api/order.py:75` `order_no=output["ODNO"]` — **정규화 0**
- 09-10 `004990` 로그에서는 둘 다 `0000305100` 으로 일치(**실측 1건뿐**)

표기가 다르면 `AND order_no = $n` 이 **항상 0건** → 모든 체결이 보정 INSERT 로 낙하하고,
그때는 UniqueViolation 이 **아니라** 새 order_no 로 **중복 행이 조용히 INSERT** 된다
⇒ **정산 이중계상.** 이번 사이클에서 유일하게 "조용히 나빠질 수 있는" 경로다.

**방어 3종**
1. **D+1 서명(신규 코드 0줄)** — `"체결통보 선행 race — COMPLETED 직접 INSERT"` WARNING
   (`:1303-1306` / `:1468-1471`) 발화가 **배포 전 기준선 대비 증가 0**. 늘면 즉시 롤백.
2. **`[trade_status_order_no_miss]` 진단(권고, §9 O-B4)** — `if affected == 0:` 분기는 이미
   DB 왕복 1회를 하는 희소 경로다. 그 앞에 진단 SELECT 하나:
   ```sql
   SELECT order_no, status FROM trade_history
   WHERE ticker=$1 AND trade_type=$2 AND strategy=$3 AND status = ANY(['PENDING','PARTIAL']) LIMIT 3
   ```
   결과 있음 = **F-1 이 실제로 가로챈 오염 1건**(161580 계열) 또는 **표기 불일치**.
   둘의 구별은 `notice_order_no` 와 `rows` 의 order_no 를 눈으로 비교하면 즉시 된다.
   결과 없음 = 진짜 선행 race(정상). ⇒ D-3 의 **미래분 대체 측정기**.
3. **계약 테스트** — 같은 KIS 응답 픽스처로 REST `ODNO` 와 WS `fields[2]` 가 동일 문자열임을 고정
   (보류 Red 는 대신 **실패 모드**를 명시적으로 잰다 — `test_f2_order_no_mismatch_...`).

---

## 3. F-7 — `_selling` 장기 유지 가시화

### 3-a. 사실

`scheduler.py:3572-3601` 의 stale `_selling` 재대조는 **해제할 때만** WARNING 을 낸다
(`:3593-3599`). 유지 3분기는 전부 `continue` 뿐이라 **통째로 무음**이다:

| 줄 | 사유 | 의미 |
|---|---|---|
| `:3586-3587` | `held_qty.get(tk,0) <= 0` | 보유 없음 — 정상 매도 진행 가능성 |
| `:3588-3589` | `tk in open_sell_tickers` | 열린 매도주문 — double-sell 방지 |
| `:3590-3592` | `age < SELLING_RECONCILE_MIN_AGE_S`(=180, `:80`) | 갓 접수 — KIS 전파 지연 레이스 방지 |

필옵틱스 사례의 **6h45m 유지**가 로그에 한 행도 남지 않았다.

### 3-b. 🔴 라인 예산 — 인라인 추가 불가

`scheduler.py` = **3,898L** / 영구 상한 **<3,900L**
(`tests/unit/ast/test_cycle257_ast_dead_code_removed.py::TestA4SchedulerLineCount::test_line_count_below_3900`
+ cycle264 자매 가드가 리터럴 자동 대조). **여유 1행** ⇒ 3분기 안에 로그를 넣을 수 없다.

⇒ **블록 통째 leaf 위임.** 선례 = cycle233 `account_risk_watcher` · cycle259
`log_metrics_collector` · cycle264 `open_price_observe`. 순증 대신 **약 −27행**.

### 3-c. leaf 인터페이스 (⚠️ **제안** — §9 O-B3)

```python
# src/engine/selling_reconcile.py  (비8영역 leaf)
SELLING_HOLD_MARKER = "[selling_hold]"
_hold_cap: KstDailyEmitCap          # 1회/(ticker, reason)/일

async def reconcile_stale_selling(order_engine, holdings, *, min_age_s: float, now=None) -> None
```
- 본문은 `scheduler.py:3572-3601` 의 **byte 동일 이동**(`get_daily_orders` 호출·판정·해제 로그·
  `write_log` 문자열 전부 그대로).
- 관측 호출은 각 `continue` **직전**(판정 뒤·행동 앞)에 추가.
- scheduler 는 3행 이내로 축소:
  ```python
  if self.order_engine._selling:
      await reconcile_stale_selling(
          self.order_engine, holdings, min_age_s=SELLING_RECONCILE_MIN_AGE_S,
      )
  ```

### 3-d. 관측 형태

```
[selling_hold] ticker=… reason=held_zero|open_order|too_young elapsed_s=…
```
- **WARNING**(INFO 는 `system_logs` 미적재)
- cap = `KstDailyEmitCap` **1회/(ticker, reason)/일** — reason 을 키에 넣지 않으면
  사유 전이(`too_young` → `held_zero`)가 첫 사유에 먹힌다(cycle258 카드 #4)
- 실패는 `observer_trace.trace_observer_failure`(무흔적 `pass` 금지, cycle258 카드 #5)
- **never-raise** — 관측 실패가 유지/해제 판정을 바꾸면 안 된다

---

## 4. 계약 (Red)

| # | 계약 | HEAD |
|---|---|---|
| F3-1 | `affected=2` → `[trade_status_multi_update]` WARNING(ticker/trade_type/affected 포함) | RED |
| F3-2 | `affected=1` → 무발화 (뮤테이션 `>1`→`>=1` KILL) | GREEN |
| F3-3 | `affected=0` → 무발화 (`!=1` 류 뒤집기 KILL). 0 은 **정상 경로**다 | GREEN |
| F1-1 | `order_no=` 전달 시 SQL 에 `AND order_no = $` + 값 바인딩, 기존 4-eq 조건 **유지**(넓히지 않음) | RED |
| F1-2 | `order_no` 는 **keyword-only**, 기본 `None` | RED |
| F1-3 | 미전달 시 SQL **byte 동일** + args 동일 | GREEN |
| F1-4 | 같은 ticker·strategy 의 PENDING 2행(다른 order_no) → 주문 A 전량체결 시 **A 행만** COMPLETED (매수) | RED |
| F1-5 | 매도 축 동일 | RED |
| F2-1 | order_no 표기 불일치 시 **중복 행이 INSERT 되는 경로**를 명시적으로 고정(경보의 근거) | RED |
| F7-1/2/3 | 유지 3사유 각각 `[selling_hold]` WARNING 1행 + `_selling` **유지** | RED |
| F7-4 | 해제 경로: `discard` + `_selling_since` pop + 기존 WARNING 문구 + `write_log("WARNING", "[selling_reconcile] stale _selling 해제: …")` **불변**, 유지 관측 미발화 | RED |
| F7-5 | cap = 1회/(ticker, reason)/일, 사유 전이 시 별도 1행 | RED |
| F7-6 | `_hold_cap.emit_once` 가 던져도 판정 불변(never-raise) | RED |
| AST1 | `order_engine.py` 의 `update_trade_status` 호출 **전부**가 `order_no=` 전달(기준선 ≥6곳) | RED |
| AST2 | `[trade_status_multi_update]` emit 지점이 **정확히 1곳**, `src/db/trade_history.py`, `logger.warning` | RED |
| AST3 | leaf 존재 + `[selling_hold]` 를 `logger.warning` 으로 emit | RED |
| AST4 | scheduler 에 `open_sell_tickers` 토큰 **0건**(인라인 소멸) ∧ `reconcile_stale_selling` 호출 존재 | RED |
| AST5 | `scheduler.py` < 3,900L (cycle257 영구 상한 자매) | GREEN |
| AST6 | leaf 가 `KstDailyEmitCap` + `trace_observer_failure` 사용 | RED |

---

## 5. 최소 diff 계획

### 5.1 `src/db/trade_history.py` (8영역 아님) — 약 +20행
`:88-95` 시그니처(`*, order_no=None`) · `:96` docstring 정정 · `:107-117` WHERE 조건부 ·
`:119` 뒤 F-3 WARNING.

### 5.2 `src/engine/order_engine.py` (🔴 8영역 — D2 승인) — 약 +6행
C1~C6 여섯 곳에 `order_no=order_no` **한 인자씩**. (cycle273a 와 같은 커밋이면 O4/O5 와 합류.)

### 5.3 `src/engine/scheduler.py` (라인 상한 대상) — 약 **−27행**
`:3572-3601` → leaf 위임 3행. `SELLING_RECONCILE_MIN_AGE_S`(`:80`) 는 scheduler 에 남기고
인자로 넘긴다(상수 소유권 이동 금지 — 이동하면 무행위 diff 가 커진다).

### 5.4 신규 `src/engine/selling_reconcile.py` (비8영역 leaf)
이동 블록 + 관측 3호출 + `_hold_cap`. `src.*` import 는 최소로(`daily_emit_cap`,
`observer_trace`, `db.system_logs`, `api.balance`, `engine.scanner.KST_TZ`).

---

## 6. 검증 게이트 · 뮤테이션 · D+1

### 게이트
1. 보류 Red 17건 GREEN 전환
2. `pytest tests/unit/db tests/unit/engine tests/unit/ast` 회귀 0
3. `pytest tests/integration/` 전체(특히 `test_cycleM2a_hotpath_roundtrip.py` 실 PG 왕복)
4. **실 PG 통합 케이스 추가 권고** — F1-4 를 `tests/integration/` 에서 한 번 더(부분 UNIQUE 인덱스 실물 확인)
5. 백엔드 전체 PASS(기준선 7,548) + `--log-level=DEBUG` 재실행
6. `scheduler.py` 라인 수 실측 재확인(< 3,900)

### 뮤테이션
| # | 뮤테이션 | 잡는 가드 |
|---|---|---|
| N1 | `affected > 1` → `>= 1` | F3-2 |
| N2 | `affected > 1` → `!= 1` | F3-3 |
| N3 | `order_no` WHERE 조건 삭제 | F1-1 · F1-4 |
| N4 | `order_no` 를 C5/C6 에만 누락 | AST1 |
| N5 | F-3 를 `logger.info` 로 강등 | AST2 |
| N6 | 관측 cap 키에서 `reason` 제거 | F7-5 |
| N7 | leaf 의 `continue` 3개 중 하나를 `pass` 로 | F7-1/2/3(유지 단언) + F7-4 |
| N8 | leaf 관측을 `continue` **뒤**로 이동(도달 불가) | F7-1/2/3 |

### D+1 실측 서명
| 서명 | 기대 | 비고 |
|---|---|---|
| `체결통보 선행 race — COMPLETED 직접 INSERT` | **증가 0** | 🔴 §2-c 표기 불일치 조기경보 — 늘면 즉시 롤백 |
| `[trade_status_multi_update]` | 0건 | 발화 시 WHERE/인덱스 후퇴 의심 |
| `[buy_fill_correction_forced_update_zero]` | 0건 | |
| `[selling_hold]` | ≥0행, 사유 분포가 보인다 | **신규 마커 — 배포 전 0행은 당연**(합산 무의미) |
| `[selling_reconcile] stale _selling 해제` | **불변** | 해제 판정 byte 동일의 증거 |
| `trade_history` 행 수 · 정산 `buy_total`/`sell_total` | **불변** | 무행위의 증거 |

---

## 7. 보류 Red 파일

| 보류 경로 | → 최종 목적지 | RED/GREEN(HEAD) |
|---|---|---|
| `…/cycle273b/test_cycle273b_trade_status_order_no_and_multi_update.py` | `tests/unit/db/test_cycle273b_trade_status_order_no_and_multi_update.py` | 3 RED / 3 GREEN |
| `…/cycle273b/test_cycle273b_161580_cross_order_overwrite.py` | `tests/unit/engine/test_cycle273b_161580_cross_order_overwrite.py` | 3 RED / 0 |
| `…/cycle273b/test_cycle273b_selling_hold_observe.py` | `tests/unit/engine/test_cycle273b_selling_hold_observe.py` | 6 RED / 0 |
| `…/cycle273b/test_cycle273b_ast_no_behavior_guards.py` | `tests/unit/ast/test_cycle273b_ast_no_behavior_guards.py` | 5 RED / 1 GREEN |
| **합계** | | **17 RED / 4 GREEN** |

F-7 6건은 **모듈 부재**로 RED 다 — 수집 오류가 아니라 테스트 내부 `pytest.fail` 로 드러낸다
(다른 워크플로의 스위트를 붉히지 않기 위해 보류 위치에 둔 이유와 같은 원칙).

---

## 8. 8영역 절차 · 배포

- `src/engine/order_engine.py` = 8영역 ⇒ **sha 핀 4곳 등록 → 커밋 → 후속 커밋으로 비움**
  (목록·절차는 `cycle273a_c235v2_cancel_timer_and_partial_spec.md` §8.1 과 동일).
- `src/engine/scheduler.py` 는 8영역은 아니지만 **라인 상한 때문에 같은 승인 대상**이다.
- `src/engine/selling_reconcile.py` 는 신규 leaf(비8영역) — 핀 대상 아님.
- 배포 모드 = **full**. 창·D6 금지는 cycle273a §8.2 와 동일.
- ⚠️ **cycle272 동시 작업** — 병합 전 `scheduler.py` 의 그쪽 diff 와 충돌 여부를 본다
  (cycle272 는 `_confirm_breakout_open_prices` 부근, F-7 은 `:3572-3601` — 겹치지 않을 것으로 예상하나 실측 필요).

---

## 9. Open questions (team-leader/사용자 결정 — 재해석 금지)

| # | 질문 | tdd-engineer 권고 |
|---|---|---|
| **O-B1** | F-3 관측 지점: 정본 표의 `order_engine.py` 2지점 vs `trade_history.update_trade_status` 1지점 | **db 1지점**(§1-b 근거 3) — 단 정본 문면을 바꾸는 제안이라 확인 필요 |
| **O-B2** | F-1/F-2 `order_no` 를 넣을 호출부: 정본 2곳(C1·C3) vs 6곳 전부 | **6곳 전부**(§2-b) — C5/C6 가 가장 위험 |
| **O-B3** | F-7 leaf 모듈명·진입점 시그니처(`src/engine/selling_reconcile.py::reconcile_stale_selling`) | 제안대로. 다르게 가면 보류 Red 상단 상수 2개(`_LEAF_MODULE`·`_ENTRY`)만 수정 |
| **O-B4** | `[trade_status_order_no_miss]` 진단 SELECT 를 이번에 넣는가 | **넣는다** 권고 — §2-c 의 유일한 실시간 조기경보이자 D-3 미래분 대체 측정기. 다만 **미승인 신규 DB 왕복**이라 확인 필요(희소 경로 한정, hot path 비용 ≈0) |
| **O-B5** | F-7 을 (가)보다 **먼저** 넣는가 | **먼저** 권고 — `scheduler.py` 3,898L 에서 cycle273a S1(+1행)이 상한에 딱 붙는다. F-7(−27행)이 선행하면 여유가 생긴다 |
| **O-B6** | F-4~F-6·F-8·F-9(워크리스트 잔여) | 이번 범위 밖. 사용자 결정은 F-3/F-1/F-2/F-7 **네 건**만 지정했다 |
