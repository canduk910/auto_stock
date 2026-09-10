# cycle273-D 명세 — 보유·익일청산 종목 일봉 적재 **강제 포함** (D5)

- 작성 2026-09-10 · tdd-engineer(그룹 2) · **읽기 전용 사이클**
- 사용자 결정(2026-09-10 목 19:5x) = 보고서 §9 "나머지는 제안대로" 에 포함 — **D5 진행**,
  `scanner.py`(8영역) 변경 **승인 완료**
- 정본 = `_workspace/analysis/2026-09-10_cycle273_UD_load_and_ui.md` §D5 ·
  워크리스트 D5 항목 · 루트 CLAUDE.md(핵심 안전 규칙 "보유 종목 절대 보호")
- 기준 트리 = **HEAD `1df6d7d`**
- 보류 Red = `…/scratchpad/pending_tests/cycle273d/test_cycle273_daily_load_protected.py`
  → DEST `tests/unit/engine/test_cycle273_daily_load_protected.py`

---

## 1. 한 줄 요약

같은 테이블에 대해 **지우는 쪽(16:15 purge)은 보유 종목을 보호**하는데
**채우는 쪽(16:00 load)은 보호하지 않는다.** D5 는 새 원칙 도입이 아니라 **이 비대칭을 없애는 것**이다.

---

## 2. 실측 (운영 RDS, SELECT 전용)

```
stock_master_daily  ticker=004690(삼천리, 보유)
  head(max bas_dd) = 2026-09-04,  결손 = 09-07 · 09-08 · 09-09 · 09-10 (4거래일)
stock_master        hts_avls_eok=5005(≥500 ✓)  acml_tr_pbmn_won=1,131,967,100(≥10억 ✓)
                    is_kospi200=false  is_kosdaq150=false
```

> **004690 은 "자격을 영구히 잃은 종목" 이 아니라 임계선 위아래를 매일 오가는 종목이다.**
> 일 거래대금이 3.2억~12.6억 사이를 오간다(임계 **10억**). 정확한 서술은
> **"그날의 자격을 못 넘긴 날마다 그날 봉을 잃는다"** 이고, 손실이 누적돼 4거래일이 됐다.

**하루 단위 회전 ~100종목**(2026-09-10 실측): 유니버스 1,005 · 09-10 행 1,003 ·
**유니버스인데 09-10 행 없음 101** · 09-10 행 있는데 지금 유니버스 아님 99.

**왜 "오늘은 자격이 있는데 오늘 봉이 없나"** — `stock_master.raw` 를 갱신하는 것은 **16:10 basics refresh**
이고 일봉 적재는 **16:00** 이다. 즉 16:00 적재는 항상 **어제 16:10 기준 `raw`** 로 유니버스를 판정한다.

**결손이 스스로 낫는가** — 증분 모드 `fetch_days=7` → 최근 **7영업일**을 `ON CONFLICT DO UPDATE` 로 덮는다.
⇒ 유니버스에 다시 들어오면 **7영업일치까지 자동 복구**, 그보다 오래된 구멍은 **영구**(`existing_count ≥ 50`
이라 100일 backfill 분기로 못 간다).

| 상태(오늘 유니버스 1,005 기준) | 종목 수 |
|---|---|
| 09-10 행 보유(정상) | 904 |
| head ∈ [09-01, 09-09] — **복구 가능** | 68 |
| head < 09-01 — **영구 구멍** | 25 |
| 일봉 행이 하나도 없음 | 8 |

> **004690 은 아직 "복구 가능" 구간이다(head 09-04, 4영업일).
> 09-16(화) 이전에 배포하면 09-07~09-10 4일이 그대로 메워지고, 미루면 영구 구멍이 된다.**
> `003470`(유안타증권) head 09-09 — 마찬가지로 복구 가능.

---

## 3. 최소 diff (구현 스케치 — U-D §D5-4 채택)

```python
# scanner.py  _stock_master_daily_load_once  내부, list_all 페이징 루프 **앞**
    # cycle273 D5 — 보유·익일청산 종목은 유니버스 자격과 무관하게 적재한다(사이클 32 R4).
    # 헬퍼는 fail-open(예외 → 빈 집합)이라 판정 실패가 현행 후보 집합을 바꾸지 않는다.
    protected_universe = {
        t for t in _collect_protected_tickers_for_scanner()
        if t and len(t) == 6 and t.isdigit()          # 진입 게이트와 같은 6자리 숫자 규약
    }

# 루프 안 (:2182)
-            if is_index or is_qualifier:
+            is_protected = ticker in protected_universe
+            if is_index or is_qualifier or is_protected:
                 all_tickers.append(ticker)
                 if is_index:
                     vcp_universe_tickers.add(ticker)
+            if is_protected:
+                protected_universe.discard(ticker)     # 아래 잔여 합집합에서 중복 제거

# 페이징 루프 **뒤**, summary["total"] 계산 **앞**
+    # `list_all` 이 예외로 조기 break 하면 보유 종목이 실린 페이지가 통째로 빠진다.
+    # 보호 대상만은 그 실패에도 살아남아야 하므로 잔여를 합집합한다(중복은 위에서 discard).
+    forced_extra = sorted(protected_universe)
+    all_tickers.extend(forced_extra)
```

관측(신규 마커, **실행당 1행** INFO — 종목당 emit 금지, 사이클 237 교훈):

```
[daily_load_protected_forced] protected=%d forced_in_universe=%d forced_extra=%d tickers=%s
```
(`tickers` 상한 20개 절단. `protected` = 6자리 필터 통과 후 총수 · `forced_in_universe` = 루프 안에서
보호로 들어온 수 · `forced_extra` = `list_all` 이 못 보여준 잔여.)

⚠️ **헬퍼는 재사용한다.** `_collect_protected_tickers_for_scanner()`(`scanner.py:55-98`, 사이클 32 R4)가
이미 ① 전 전략 `positions` 합집합 ② `trading_scheduler._pending_next_day_clear`(튜플/문자열 둘 다)를
**fail-open** 으로 모은다. 새 판정을 발명하지 않는다.

---

## 4. 계약·불변식

| # | 계약 | 근거 | 테스트 |
|---|---|---|---|
| C1 | `vcp_universe_tickers` 에 **보호 종목을 넣지 않는다** | 넣으면 120일 분할 backfill(KIS 3회)로 새는데, 보호의 목적은 "오늘 봉" 이지 "220일 이력" 이 아니다 | `test_c1_protected_never_enters_vcp_universe` · `test_g273d_4_ast_gate_has_three_branches` |
| C2 | 판정 실패는 **fail-open**(현행 후보 집합 유지) | 헬퍼가 이미 `except → debug`. fail-closed 는 P0-1 유령 키 방향 | `test_c2_helper_failure_is_fail_open` |
| C3 | `latest >= today` **신선도 skip 은 우회하지 않는다** | 보호는 "후보에 넣는다" 까지다 — KIS 를 한 번 더 때리는 권한이 아니다 | `test_c3_freshness_skip_is_not_bypassed` |
| C4 | **6자리 숫자** ticker 만 통과 | 진입 게이트 비대칭 규약(ETF·신주인수권 차단) | `test_c4_non_six_digit_protected_is_ignored` |
| C5 | 결과 집합은 현행의 **상위집합**(⊇) | 어떤 종목도 새로 배제되지 않는다 = 회귀 방향 0 | `test_c5_result_is_superset_of_current` · `test_c5b_…not_duplicated` |
| C6 | registry·scheduler 를 **읽기만** 한다 | 헬퍼는 read-only(`positions.keys()` 복사) | `test_c6_registry_state_is_untouched` |

**비용** — 보호 종목은 보통 유니버스 안이라 실효 추가는 오늘 기준 **2종목**(004690·003470).
종목당 KIS 1회 + `asyncio.sleep(0.05)` ⇒ **추가 ~0.1초**. 결손이 커서 `existing_count < 50` 인 종목만 100일 backfill 1회.

---

## 5. Red 계약 ↔ 테스트 (현재 **7 failed / 5 passed**)

| 테스트 | 내용 | 현재 |
|---|---|---|
| `test_g273d_1_held_non_qualifier_is_loaded` | **004690 실사례** — 자격 미달 + 보유 → 포함 | **RED**(현행 total=1) |
| `test_g273d_1b_pending_next_day_clear_is_loaded` | 익일청산(튜플/문자열 둘 다) | **RED** |
| `test_c1_protected_never_enters_vcp_universe` | backfill 0회 | **RED** |
| `test_c2_helper_failure_is_fail_open` | 헬퍼 예외 → 현행 유지 | PASS(유지 계약) |
| `test_c3_freshness_skip_is_not_bypassed` | `skipped_fresh=1`, KIS 0회 | **RED** |
| `test_c4_non_six_digit_protected_is_ignored` | `ABC123`/`00469`/`0046900`/빈값/None | PASS(유지 계약) |
| `test_c5_result_is_superset_of_current` | 보호 0건 = 현행 동일 | PASS |
| `test_c5b_…_not_duplicated` | 유니버스 안 보호 종목 1회만 | PASS |
| `test_g273d_2_protected_survives_list_all_failure` | `list_all` 예외에도 적재 | **RED** |
| `test_g273d_3_marker_is_one_line_per_run` | **실행당 1행** + 3필드 | **RED** |
| `test_c6_registry_state_is_untouched` | 상태 무변경 | PASS |
| `test_g273d_4_ast_gate_has_three_branches` | 게이트 3갈래 + 헬퍼 재사용 + VCP 봉인 | **RED** |

**기존 테스트 영향** — `tests/unit/engine/test_cycle206_daily_load_universe.py` 는 `list_all` 을 mock 하고
registry 를 주입하지 않으므로 헬퍼가 빈 집합을 반환해 `summary["total"]` 단언이 그대로 통과할 것으로
**예상**한다(이 워크플로는 읽기 전용이라 실행하지 않았다 — **Green 착수 시 첫 확인 항목**).
AST 가드 `test_universe6_ast_universe_gate_present` 는 본문에 `_is_daily_load_universe`·`is_index`·
`is_qualifier` 문자열이 있을 것만 요구하므로 `is_protected` 추가는 무해하다.

---

## 6. 뮤테이션 (최소 5종)

| # | 뮤테이션 | KILL |
|---|---|---|
| M1 | `or is_protected` 삭제 | `test_g273d_1` |
| M2 | `if is_protected: vcp_universe_tickers.add(...)` 추가 | `test_c1` |
| M3 | 6자리 필터 삭제 | `test_c4` |
| M4 | `forced_extra` 합집합 삭제 | `test_g273d_2` |
| M5 | 마커를 종목당 emit 으로 | `test_g273d_3` |
| M6 | 신선도 skip 앞에 `is_protected` 우회 추가 | `test_c3` |

---

## 7. 승인·핀 절차 (⚠️ `scanner.py` = **8영역**)

사용자 승인 = 2026-09-10 D5. 커밋 시 **sha 핀 4곳** 절차가 따른다:

1. `tests/unit/ast/test_cycle222a3_ast_followup_fixes.py::_APPROVED_CONTENT_SHA`
2. `tests/unit/ast/test_cycle223_ast_donchian_exit_fix.py::_PREEXISTING_CONTENT_SHA`
3. `tests/unit/ast/test_cycle223f_ast_manual_apply_safeguard.py::_PREEXISTING_CONTENT_SHA`
4. `tests/unit/engine/strategies/test_cycle226_zero_breakout_defense.py::_ALLOWED_CONTENT_SHA` (⚠️ ast 디렉터리가 아니다)

순서 = **소스 확정 → `shasum -a 256 src/engine/scanner.py` 재산출 → 4곳 동시 등록 → 커밋 →
즉시 후속 커밋으로 비움**. 현재 네 dict 는 **전부 비어 있다**(cycle271 `4d88aa6`).
참고: HEAD 의 `scanner.py` sha = `fa4f7f2f49cbe8d363bee6a972e96fdfc95e787abf341ea35edfd0149b44bc11`.

배포 모드 = **full**(`src/**`) — 장외 창 15:30~19:55 / 20:20~익일 07:45, **20:00~20:15 금지**.

---

## 8. D+1 서명

| # | 서명 | 어긋나면 |
|---|---|---|
| S1 | `[daily_load_protected_forced]` **1행**, `protected` = 그날 보유+익일청산 수 | 0행 = 미배선 · 다수 행 = 종목당 emit(폭주) |
| S2 | `[stock_master_daily_load_begin] candidates=` 가 이동 전 대비 **+(보호 중 비유니버스 수)** | 큰 폭 증가 = 6자리 필터·중복 제거 실패 |
| S3 | `004690` 의 `stock_master_daily` head == 그날 | 아니면 보호가 안 먹었거나 KIS 실패 |
| S4 | 배포 후 첫 실행에서 `004690` 의 09-07~09-10 4행이 채워짐 | 7영업일 창을 이미 넘겼다면 영구 구멍 확정 → 별도 backfill 결정 |
| S5 | `failed` 가 이동 전 대비 급증하지 않음 | 보호 종목의 KIS 실패가 새 실패원인지 확인 |

---

## 9. 겸사 정정 · 후속

| # | 항목 | 등급 |
|---|---|---|
| **F-D5-a** | `_is_daily_load_universe` **docstring 이 "trade>=20억" 인데 상수는 10억**(`scanner.py:2099` vs `:2046`). 호출부 주석 `:2177-2178` · `src/engine/CLAUDE.md` · 워크리스트도 같은 문구. 2026-07 kojiro 전체상장 전환 때 20억→10억으로 내리며 서술을 안 고친 것 ⇒ **이 사이클에서 겸사 정정**(코드 변경 0, 주석·문서만) | LOW(문서) |
| **F-D5-b** | 오늘 유니버스 1,005 중 **일봉 행이 하나도 없는 8종목** · **7영업일 창 밖 영구 구멍 25종목** 처분(강제 backfill 트리거 필요 여부) | MEDIUM — **후속** |
| **F-D5-c** | 일자별 적재 종목 수 단조 감소(09-01 1,290 → 09-10 1,003, 07-01 기준 1,801)가 의도된 축소인지 | MEDIUM — **후속**(워크리스트 기존 등재의 최신 실측) |

---

## 10. 미해결 (결정 필요)

| # | 항목 | 권고 |
|---|---|---|
| **OQ-D5-1** | 보호 종목이 **자격도 지수도 아닌데 `existing_count < 50`** 이면 100일 backfill 이 돈다(KIS 1회 + 긴 응답). 보호 종목 수가 수십이면 첫 실행이 길어진다 | 현행 분기 그대로 둔다(예외를 만들면 "보호 종목만 다른 적재 규약" 이 생긴다). 실측으로 문제 시 후속 |
| **OQ-D5-2** | D5 와 **D8(18:10 이동)의 순서** | **D5 가 본질이다.** D8 은 유니버스 판정을 오늘치 raw 로 바꿔 **위상만 하루 당길 뿐** 회전을 없애지 못한다 — 004690 이 그날 9억이면 18:10 이어도 빠진다. 두 결정은 함께 가되 **D5 를 먼저** 배포해도 무방 |
| **OQ-D5-3** | 004690 복구 시한 | **09-16(화) 전 배포**가 4거래일 자동 복구의 조건. 미루면 영구 구멍 → 별도 backfill 결정이 필요해진다 |
