# cycle273 U-D — D5(보유 종목 일봉 강제 적재) · D8(일봉 적재 18:10 이동) · D4(주간 자문 레벨 0 + UI 재사용)

> **작성 2026-09-10(목) 20:1x~20:4x KST · 읽기 전용 판독.** 코드·테스트·프론트 변경 0 · git 쓰기 0 ·
> 운영 DB 쓰기 0(SELECT 만) · 매매/설정 API 호출 0.
> 기준 커밋 = 판독 착수 시 `a10191b`, 도중 `cda2dd3`(cycle270-B) 가 HEAD 로 올라와 §D8-4 는 그 커밋을 함께 읽었다.
> 운영 DB 조회는 EC2 backend 컨테이너 안에서 `src.db.pg.fetch` 로만 수행했다(SELECT 전용, 임시 스크립트는 `/tmp`).
> **"실측" 이라 적지 않은 문장은 코드 판독이거나 추정이다.**

---

## 0. 세 줄 결론

1. **D5 는 기존 헬퍼 재사용으로 끝난다.** `scanner.py:55` 에 이미 `_collect_protected_tickers_for_scanner()`
   (사이클 32 R4 패턴, fail-open)가 있고, `_stock_master_daily_load_once` 의 유니버스 판정 한 줄
   (`scanner.py:2182`)에 `or ticker in protected` 를 더하는 것이 최소 diff 다. **004690 삼천리의 끊김은 실측으로
   재확인**했다(`stock_master_daily` head = **2026-09-04**, 09-07·08·09·10 **4거래일 결손**). 다만 원인 서술은
   보고서 §6-6 의 "자격을 잃었다" 보다 한 겹 더 정확해야 한다 — **004690 은 지금 자격이 있다**
   (`acml_tr_pbmn_won=1,131,967,100 ≥ 10억`). 16:00 적재는 **16:10 basics 갱신 *전*** 에 돌아 **어제치 `raw`**
   로 유니버스를 판정하므로, 임계 근처 종목이 하루 단위로 들락날락한다(실측: 09-10 적재 1,003종목 중
   **99종목이 오늘 유니버스 밖**, 오늘 유니버스 1,005 중 **101종목이 09-10 행 없음**).
2. **D8(16:00→18:10)은 `scheduler.py:66` 리터럴 한 개(라인 증감 0)이고 충돌 작업이 없다.** 16:20 저녁 funnel
   캡처가 영향을 안 받는다는 워크리스트의 전제도 코드로 **두 겹 확인**했다(전략 7종 `prev_idx` 는 **날짜 비교**
   기반 · 16:20 의 "일봉 적재 완료 대기" 폴링은 `count_all()`(전체 행수)이라 **이미 공허**하다).
   cycle263 D+1 판독도 **DB 로 4거래일 연속 확증**했다(09-07/08/09/10 각각의 `bas_dd` 행이 그날 16:00~16:02 에
   기록됨). ⚠️ **다만 18:10 이동은 부수 효과가 하나 있다** — 유니버스 판정이 *어제치* 에서 *오늘치* `raw` 로
   바뀐다. D5 와 같은 증상을 다루므로 **두 결정은 함께 판단해야 한다.**
3. **🔴 D8 조사 중 별건 HIGH 발견** — 오늘 20:09 커밋된 cycle270-B 의 `TIME_QUOTE_TOKEN_REFRESH = 21:30` 은
   **영원히 발화하지 않는다.** 그 task 는 `scheduler.start()` 의 `finally` 가 cancel 하고 `_running=False` 가
   되는데, 오늘 실측 그 시각이 **20:10:15 KST**("매매 시스템 종료" 로그)다. 21:30 은 그보다 80분 뒤다.
   `.deployed_sha` 는 아직 `4d88aa6` = **미배포**라 지금 막을 수 있다.
   **D4 는 "예/아니오" 로 답하면 — UI 적용 버튼은 그대로 쓸 수 있다(예). 단 조건 4개가 선행한다(아래 §D4-6).**

---

# D5 — 보유·익일청산 종목 일봉 적재 강제 포함

## D5-1. 현행 코드 (HEAD 기준, 읽기 전용)

| 위치 | 내용 |
|---|---|
| `src/engine/scanner.py:2044-2047` | `_DAILY_LOAD_MIN_MCAP_EOK = 500`(억원) · `_DAILY_LOAD_MIN_TRADE_WON = 1_000_000_000`(**10억원**) |
| `src/engine/scanner.py:2098-2111` | `_is_daily_load_universe(row)` — `raw.hts_avls ≥ 500` ∧ `raw.acml_tr_pbmn ≥ 10억`, 비숫자/부재는 `except (ValueError, TypeError) → False` |
| `src/engine/scanner.py:2170-2185` | 페이징 루프. `is_index = is_kospi200 or is_kosdaq150` · `is_qualifier = _is_daily_load_universe(row)` · **`if is_index or is_qualifier:` (`:2182`)** 가 유일한 관문. `vcp_universe_tickers` 는 `is_index` 일 때만 채운다(`:2184-2185`) |
| `src/engine/scanner.py:55-98` | **`_collect_protected_tickers_for_scanner()` — 이미 존재한다.** 사이클 32 R4 패턴: ① `registry.all()` 순회 → `s.state.positions.keys()` 합집합 ② `scheduler.trading_scheduler._pending_next_day_clear`(튜플/문자열 둘 다 처리). 두 블록 모두 `except Exception: logger.debug(...)` = **fail-open**(실패 시 빈 집합) |
| `src/engine/data_load_tasks.py:246-297` | `stock_master_daily_purge_task_loop` — retention purge 는 **이미** 보유·익일청산 protected 를 계산해 `purge_old_rows(protected_tickers=...)` 로 넘긴다 |

> **선례가 비대칭이다.** 같은 테이블에 대해 **지우는 쪽(16:15 purge)은 보유 종목을 보호**하는데
> **채우는 쪽(16:00 load)은 보호하지 않는다.** D5 는 새 원칙 도입이 아니라 이 비대칭을 없애는 것이다.

### 발견 F-D5-a (LOW, 문서 드리프트 · 행위 변경 0)

`_is_daily_load_universe` 의 **docstring 이 "trade>=20억" 이라 적는데 상수는 10억**이다
(`scanner.py:2099` vs `:2046`). 호출부 주석 `:2177-2178` 도 "mcap500억&trade20억", `src/engine/CLAUDE.md`
와 워크리스트도 같은 문구를 쓴다. 2026-07 kojiro 전체상장 전환 때 20억→10억으로 내리면서(`:2039-2041` 주석이
그 사실을 적는다) 나머지 서술을 안 고친 것으로 보인다. **이 판독의 지시문에도 "거래대금≥20억" 으로 실려 있어
그대로 두면 D5 명세가 잘못된 임계로 쓰인다.** D5 사이클에서 겸사 정정 권고(코드 변경 0, 주석·문서만).

## D5-2. 004690 삼천리 실측 재확인 (운영 RDS, SELECT)

```
stock_master_daily  ticker=004690  →  head(max bas_dd) = 2026-09-04,  보유 행 수 135
                     결손 = 09-07 · 09-08 · 09-09 · 09-10  (4거래일)
                     ※ 09-05·09-06 은 주말이라 결손이 아니다
```

| bas_dd | trade_value(원) | updated_at |
|---|---|---|
| 2026-08-26 | 317,853,800 | 09-03 07:57 |
| 2026-08-27 | 877,111,100 | 09-06 15:13 |
| 2026-08-28 | 690,868,850 | 09-06 15:13 |
| 2026-08-31 | 853,583,700 | 09-06 15:13 |
| 2026-09-01 | 757,189,150 | 09-06 15:13 |
| 2026-09-02 | 1,045,012,600 | 09-06 15:13 |
| 2026-09-03 | 967,978,900 | 09-06 15:13 |
| **2026-09-04** | **1,261,101,600** | 09-06 15:13 |

`stock_master` 현재값 — `hts_avls_eok=5005`(≥500 ✓) · **`acml_tr_pbmn_won=1,131,967,100`(≥10억 ✓)** ·
`refreshed_at=09-10 16:20` · 지수 편입 아님(`is_kospi200=false, is_kosdaq150=false`).

> **즉 004690 은 "자격을 영구히 잃은 종목" 이 아니라 임계선 위아래를 매일 오가는 종목이다.**
> 위 표만 봐도 일 거래대금이 3.2억~12.6억 사이를 오간다(임계 10억). 보고서 §6-6 의 "자격을 잃는 순간
> 보유 중에도 적재가 멈춘다" 는 **결론은 맞고 사례 서술이 한 단계 거칠다** — 정확히는 **"그날의 자격을
> 못 넘긴 날마다 그날 봉을 잃는다"** 이고, 손실이 누적돼 4거래일이 됐다.

### 왜 "오늘은 자격이 있는데 오늘 봉이 없나" (실행 순서 실측)

`stock_master.raw` 를 갱신하는 것은 **16:10 basics refresh**(`TIME_STOCK_MASTER_BASICS_REFRESH`)이고
일봉 적재는 **16:00** 이다. 즉 **16:00 적재는 항상 어제 16:10 기준 `raw` 로 유니버스를 판정한다.**
보유 10종목의 `refreshed_at` 실측이 전부 `09-10 16:10~16:20` 이라 이 순서가 확인된다.

실측 대조(2026-09-10):

| 항목 | 값 |
|---|---|
| `stock_master` 전체 | 3,583 |
| **지금** 유니버스(index ∪ 자격) | **1,005** (index 348 · 자격 993) |
| 09-10 `bas_dd` 행 수 | **1,003** (전부 09-10 16:00~16:02 기록) |
| 지금 유니버스 ∩ 09-10 행 | 904 |
| **지금 유니버스인데 09-10 행 없음** | **101** |
| 09-10 행이 있는데 지금 유니버스 아님 | 99 |
| 09-09 행 있고 09-10 행 없음 | 85 |
| 09-10 행 있고 09-09 행 없음 | **0** |

> **하루 단위 회전이 ~100종목이다.** 그리고 `09-10 행 있고 09-09 행 없음 = 0` 은 그날의 적재가
> **신규 진입을 만들지 못한다**는 뜻이 아니라(신규는 backfill 로 과거까지 채운다) 이 날 유니버스가
> 순수 축소였다는 뜻이다. 일자별 행 수도 단조 감소한다 — 09-01 **1,290** → 09-02 1,297 → 09-03 1,268 →
> 09-04 1,231 → 09-07 1,197 → 09-08 1,130 → 09-09 1,088 → **09-10 1,003**.
> (워크리스트가 "1,801(07-01) → 1,140(09-03), 의도된 축소인지 확인 필요" 로 등재해 둔 그 추세가 계속된다.)

## D5-3. 결손이 스스로 낫는가 — 7영업일 창

증분 모드는 `fetch_days = 7` → `fetch_daily_candles(ticker, days=7)` 이고, 그 함수는
`window_calendar_days = 7 + 3 + 10 = 20` 달력일을 조회한 뒤 **`output[:7]` = 최근 7영업일**을 돌려준다
(`src/api/condition.py:518-537`). upsert 는 `ON CONFLICT DO UPDATE` 다.

⇒ **유니버스에 다시 들어오면 최대 7영업일치 결손까지는 자동 복구된다. 그보다 오래된 구멍은 영구다**
(`existing_count ≥ 50` 이라 100일 backfill 분기로 절대 못 간다).

실측 분류(오늘 유니버스 1,005종목 기준):

| 상태 | 종목 수 |
|---|---|
| 09-10 행 보유(정상) | 904 |
| head ∈ [09-01, 09-09] — **재진입 시 복구 가능** | 68 |
| head < 09-01 — **영구 구멍** (7영업일 창 밖) | **25** |
| 일봉 행이 **하나도 없음** | 8 |

- **004690 은 지금 "복구 가능" 구간에 있다**(head 09-04, 4영업일). D5 를 **09-16(화) 이전에 배포하면**
  09-07~09-10 4일이 그대로 메워진다. 그 뒤로 미루면 영구 구멍이 된다.
- 003470 유안타증권은 head 09-09(1영업일) — 마찬가지로 복구 가능.
- 나머지 보유 8종목은 head 09-10 정상이다.

## D5-4. 최소 diff 제안 (구현 아님 — 명세용 스케치)

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
(`tickers` 는 상한 20개 절단. 보유는 최대 수십 종목이므로 폭주 없음.)

**계약·불변식 (명세에 그대로 옮길 것)**

| # | 계약 | 근거 |
|---|---|---|
| C1 | `vcp_universe_tickers` 에 **보호 종목을 넣지 않는다** | 넣으면 120일 분할 backfill(3회 KIS)로 새는데, 보호의 목적은 "오늘 봉" 이지 "220일 이력" 이 아니다 |
| C2 | 판정 실패는 **fail-open**(현행 후보 집합 유지) | 헬퍼가 이미 `except → debug` 다. fail-closed 는 P0-1 유령 키 방향 |
| C3 | `latest >= today` **신선도 skip 은 우회하지 않는다** | 보호는 "후보에 넣는다" 까지다. 이미 오늘 봉이 있으면 `skipped_fresh` 로 가는 게 맞다 |
| C4 | 6자리 숫자 ticker 만 통과 | 진입 게이트 비대칭 규약(ETF·신주인수권 차단)과 같은 필터 |
| C5 | 결과 집합은 **현행의 상위집합**(⊇) | 어떤 종목도 새로 배제되지 않는다 = 회귀 방향 0 |
| C6 | `_candidates`·`_targets`·registry 를 **읽기만** 한다 | 헬퍼는 read-only(`positions.keys()` 복사) |

**비용** — 보호 종목은 보통 유니버스 안이라 실효 추가는 오늘 기준 **2종목**(004690·003470). 종목당
KIS 1회 + `asyncio.sleep(0.05)` ⇒ **추가 ~0.1초**. 결손이 커서 `existing_count < 50` 인 종목이 섞이면
그 종목만 100일 backfill 1회.

**기존 테스트 영향(예상)** — `tests/unit/engine/test_cycle206_daily_load_universe.py` 는 `list_all` 을
mock 하고 registry 를 주입하지 않는다 ⇒ 헬퍼가 빈 집합을 반환해 `summary["total"]` 단언이 그대로 통과할
것으로 **예상**한다(실행하지 않았다 — 이 워크플로는 읽기 전용). AST 가드
`test_universe6_ast_universe_gate_present` 는 함수 본문에 `_is_daily_load_universe`·`is_index`·`is_qualifier`
문자열이 있을 것만 요구하므로 `is_protected` 추가는 무해하다.

**승인·절차** — `scanner.py` 는 **8영역**이다. 사용자 승인은 09-10 D5 로 받았고, 커밋 시
**sha 핀 4곳 절차**가 따른다:
`tests/unit/ast/test_cycle222a3_ast_followup_fixes.py::_APPROVED_CONTENT_SHA` ·
`test_cycle223_ast_donchian_exit_fix.py::_PREEXISTING_CONTENT_SHA` ·
`test_cycle223f_ast_manual_apply_safeguard.py::_PREEXISTING_CONTENT_SHA` ·
`tests/unit/engine/strategies/test_cycle226_zero_breakout_defense.py::_ALLOWED_CONTENT_SHA`.
현재 네 dict 는 **전부 비어 있다**(cycle271 이 `4d88aa6` 으로 비웠다). 순서 = **소스 확정 → `shasum -a 256
src/engine/scanner.py` 재산출 → 4곳 동시 등록 → 커밋 → 즉시 후속 커밋으로 비움**.
참고: HEAD 의 `scanner.py` sha = `fa4f7f2f49cbe8d363bee6a972e96fdfc95e787abf341ea35edfd0149b44bc11`
(cycle263 이 핀했던 값과 동일 = 그 뒤로 1 byte 도 안 바뀌었다).

---

# D8 — 일봉 적재 16:00 → 18:10

## D8-1. 상수 위치와 변경 규모

- **`src/engine/scheduler.py:66` — `TIME_STOCK_MASTER_DAILY_LOAD = time(16, 0)`** 한 곳뿐이다.
  `data_load_tasks.stock_master_daily_load_task_loop` 는 `wait_time` 을 **인자로 받을 뿐**이고
  (`data_load_tasks.py:84-96`), 모듈 안에 시각 리터럴이 없다(모듈 docstring `:9-10` 이 그 규약을 적는다).
- 배선은 `scheduler.py:3008` 한 줄. **리터럴 1개 교체 = 라인 증감 0.**
  `scheduler.py` 현재 **3,898L / 상한 <3,900L** 이므로 여유 2행은 그대로 남는다.
- `scheduler.py` 는 8영역이 아니지만 **라인 상한 때문에 같은 승인 대상**이다(루트 CLAUDE.md).
- 함께 고칠 주석 = `:66` 인라인("KRX 메인 종료 30분 후 안전 마진") · `src/engine/CLAUDE.md` 시각 표 ·
  `data_load_tasks.py:96` 의 `# 16:00 KST` 주석 · 워크리스트 D-9 행.

## D8-2. 18:10 과 겹치는 작업 — 없다 (전수 대조)

`scheduler.py` 의 `TIME_*` 전수(정의 `:57-76`):

| 시각 | 상수 | 18:10 과의 관계 |
|---|---|---|
| 15:20 / 15:30 / 15:40 | BUY_STOP / MAIN_CLOSE / POST_NXT_OPEN | 이전 |
| **16:00** | STOCK_MASTER_DAILY_LOAD | ← 이동 대상 |
| 16:10 / 16:15 / 16:20 / 16:30 / 16:40 | BASICS / DAILY_PURGE / EVENING_FUNNEL / MASTER / FINANCIAL | 이전 |
| **16:41 ~ 19:49** | — | **예정 작업 0건** |
| 19:50 | NXT_POST_BUY_STOP | 이후(1시간 40분 여유) |
| 20:00 / 20:00:05 / 20:10 | RECOMMENDATION·NXT_POST_CLOSE / FULL_UNIVERSE_LOAD / SETTLEMENT | 이후 |

- **토큰 강제 재발급과의 충돌은 성립하지 않는다** — 오늘 20:09 커밋 `cda2dd3`(cycle270-B)가
  `TIME_QUOTE_TOKEN_REFRESH` 를 15:45 → **21:30** 으로 옮겼다. 18:10 과 무관하다.
  **단 그 21:30 자체가 발화하지 않는다 — §D8-4.**
- 16:40 재무 적재는 주1회(`immediate_skip_if_fresh_hours=168`)이고 18:10 보다 앞이라 무관.
- 20:00:05 전체 유니버스 적재는 1시간 50분 뒤라 무관.
- **적재 소요 실측** = 09-10 16:00~16:02, 1,003종목(`updated_at` 히스토그램 전량 `09-10 16` 시간대).
  18:10~18:12 로 옮겨도 다음 예정 작업(19:50)까지 1시간 38분 여유다.

## D8-3. cycle263 D+1 실측 (09-07~09-10) — DB 로 4거래일 연속 확증

⚠️ **docker 로그는 이미 못 쓴다** — cycle271 배포로 backend 컨테이너가 **09-10 18:58** 에 재생성돼
그 이전 로그가 사라졌다. `--since 2026-09-07` 로 남는 daily-load 행은 단 1줄이다:
`2026-09-10 19:02:21 [stock_master_daily_load] immediate run skip — fresh last_success=2026-09-10T16:02:00.987774+09:00`
(= 재기동 immediate 가 20h 게이트로 정상 skip 된 증거).
그래서 **DB 의 `updated_at` 으로 대체 검증**했다.

| bas_dd | 행 수 | `min(updated_at)` | `max(updated_at)` |
|---|---|---|---|
| 2026-09-07 | 1,197 | **09-07 16:00** | 09-10 16:02 |
| 2026-09-08 | 1,130 | **09-08 16:00** | 09-10 16:02 |
| 2026-09-09 | 1,088 | **09-09 16:00** | 09-10 16:02 |
| 2026-09-10 | 1,003 | **09-10 16:00** | 09-10 16:02 |

- **네 거래일 모두 그날 16:00 에 그날 봉이 기록됐다** = cycle263 이 설계대로 동작 중.
  (`max(updated_at)` 이 전부 09-10 인 것은 7영업일 증분 창이 과거 행을 `ON CONFLICT DO UPDATE` 로
  다시 덮기 때문이다 — 정상.)
- 저장소 문서에 남은 로그 실측은 09-07(`skipped_fresh=0 fetched=995`,
  `_workspace/reports/2026-09-07_weekday_verification.md:188`)과 09-10(`total=1003 fetched=1003
  upserted_rows=7,891 skipped_fresh=0 failed=0`, 목요일 보고서 §3) 두 날뿐이다. 09-08·09-09 는 **문서 미기록**
  이고 위 DB 증거가 그 자리를 메운다.

⇒ **판정: 지금 옮겨도 된다.** 워크리스트가 걸어 둔 조건("화 09-08 cycle263 D+1 확인 후")은 충족을
넘어 **4거래일 연속**으로 확인됐다.

### 18:10 이 실제로 얻는 것 / 잃는 것

| | 내용 |
|---|---|
| **얻는 것** | 16:00~18:00 시간외 단일가 물량이 **그날 봉에 들어온다**(현재는 다음날 16:00 의 7영업일 창이 하루 늦게 보정). 워크리스트가 "16:00 유지의 유일한 잔여 비용" 으로 적어 둔 항목이 사라진다 |
| **미확인 1건 (그대로 남는다)** | NXT 애프터(~20:00) 물량까지 이 일봉에 잡히는지는 **여전히 미확인**이다. 잡힌다면 18:10 도 그 부분은 다음날 보정에 맡긴다. 이번 판독에서 KIS 를 호출하지 않았다(읽기 전용 규약) |
| **잃는 것** | 16:00~18:10 사이에 `stock_master_daily` 를 읽는 소비자는 그동안 헤드가 **어제 봉**이다. 아래 두 소비자를 확인했다 |

**소비자 확인 2건 (코드 판독)**

1. **16:20 저녁 funnel 캡처 — 영향 없음(두 겹 확인).**
   (a) 전략 7종이 오늘 봉을 자르는 방식이 `prev_idx = 1 if candles[0]["stck_bsop_date"] == today_str else 0`
   = **날짜 비교**다(`volatility_breakout.py:293` · `long_tail_volatility.py:293` · `kojiro.py:352,743` ·
   `donchian_swing.py:445` · `bull_flag_breakout.py:330`). 오늘 행이 없으면 `prev_idx=0` 이 되어 **같은
   전일 봉**을 쓴다 — 결과 동일.
   (b) `_evening_funnel_capture_once` 의 "16:00 일봉 적재 완료 대기" 폴링은 `count_all()`(**테이블 전체
   행 수**)이 `> 0` 인지만 본다(`scheduler.py:3041-3056`). 수십만 행이 상시 존재하므로 **이 게이트는 지금도
   공허**하고, 18:10 이동으로 새로 깨지는 것이 없다.
   > 부수 발견 **F-D8-a(INFO)**: 그 docstring 의 "16:00 일봉 적재 완료 대기 … 일봉 미적재 시 빈 funnel
   > 영속 방지" 는 **오늘 이미 사실이 아니다**(빈 테이블만 막는다). 18:10 이동 시 주석을 정직화할 것.
2. **16:15 retention purge** — cutoff 가 T-230일이라 헤드 유무와 무관. 순서만 앞뒤가 바뀐다(무해).

### ⚠️ D8 의 **문서화되지 않은 부수 효과** (D5 와 직결)

18:10 은 **16:10 basics refresh 뒤**다. 즉 유니버스 판정이 **어제치 `raw` → 오늘치 `raw`** 로 바뀐다.

- 좋은 쪽 — 오늘 거래대금이 임계를 넘긴 종목이 **그날 바로** 적재된다. 오늘 실측의
  "유니버스인데 09-10 행 없음 101종목" 중 상당수가 이 하루 지연 때문일 가능성이 크다.
- 나쁜 쪽 — 오늘 거래대금이 임계 **아래**로 떨어진 종목은 어제까지 받던 봉을 **그날부터 즉시** 잃는다.
  회전 자체는 사라지지 않고 **위상만 하루 당겨진다.**
- ⇒ **D8 은 D5 를 대체하지 못한다.** 004690 처럼 자기 거래대금이 임계 근처인 보유 종목은 18:10 로 옮겨도
  그날 거래대금이 9억이면 여전히 빠진다. **두 결정은 함께 가야 하고, D5 가 본질이다.**
- ⇒ 그리고 이 부수 효과는 **회귀 방향이 양방향**이라, 배포 D+1 에 `[stock_master_daily_load_begin]
  candidates=` 와 `[..._summary] total/fetched` 를 **이동 전후로 나란히** 봐야 한다(합산 금지).

## D8-4. 🔴 별건 HIGH — cycle270-B 의 21:30 은 발화하지 않는다

**사실 (실측 + 코드)**

1. `cda2dd3`(09-10 20:09 커밋, cycle270-B)가 `src/engine/quote_token_refresh.py:112` 를
   `TIME_QUOTE_TOKEN_REFRESH = time(21, 30)` 으로 바꿨다.
2. 그 task 는 `run_periodic_task_loop` 위임이고 `while scheduler._running:` 안에서
   `await scheduler._wait_until(21:30, advance_if_passed=True)` 로 잠든다
   (`task_loop_helper.py:153-156` · `_wait_until` 도 `while self._running:` — `scheduler.py:3890`).
3. `scheduler.start()` 는 **20:10 정산 → 로그 분석 → purge → `_reset_daily_state()` → ws disconnect**
   를 마치면 본문이 끝나고, `finally` 블록이 백그라운드 task 를 전부 cancel 한다. 그 목록에
   **`_quote_token_refresh_task` 가 들어 있다**(`scheduler.py:1013`). 직후 `self._running = False`(`:1045`).
4. `run_daily()` 는 그 뒤 **익일 `TIME_AUTO_START`(07:45)** 까지 잠든다.
5. **오늘 실측(EC2 backend 로그, 읽기 전용)**:
   ```
   2026-09-10 20:10:15 [INFO] src.engine.scheduler — 매매 시스템 종료
   2026-09-10 20:10:15 [INFO] src.engine.scheduler — 금일 매매 종료, 익일 자동 시작 대기
   2026-09-10 20:10:20 [INFO] src.engine.scheduler — [account_risk_watch_loop_exit] reason=running_false
   ```
   ⇒ 오늘 loop 이 죽은 시각은 **20:10:15**. 21:30 은 **80분 뒤**다.

**결론** — 이 코드가 배포되면 보조 시세계정 토큰 강제 재발급은 **매일 0회**가 된다. cycle269→270 이
고치려던 드리프트가 **조용히 원상 복귀**하고, 로그에는 부팅 시 `[quote_token_refresh] scheduled at=21:30`
한 줄만 남아 "배선은 살아 있다" 처럼 보인다(발화 요약 `accounts=… issued=…` 이 아예 안 나온다).

**왜 가드가 못 막았나** — `test_c9_schedule_time_invariants`(`tests/unit/engine/test_cycle269_quote_token_refresh.py:280`)는
`scheduler.TIME_*` 와의 **창 충돌 0** 은 검사하지만 **loop 생존 시간**은 검사하지 않는다. 오히려
`assert threshold.time() > time(TIME_SETTLEMENT.hour, 15)`(= T−10분 > 20:15 ⇒ **T > 20:25**)가
**T 를 loop 사망 시각 뒤로 밀어내도록 강제**한다. 가드가 결함을 승인해 준 구조다.

**상태** — EC2 `.deployed_sha` = **`4d88aa6`** = `cda2dd3` **미배포**. 지금 막을 수 있다.

**시정 방향 (선택지, 결정은 사용자·팀장)**

| 안 | 내용 | 비용 |
|---|---|---|
| **A. T 를 loop 생존 창 안으로** | 정산(20:10) **전**, KRX 장중 밖, T−10분도 장중 밖, 7분 직렬화 창이 16:00~16:40 데이터 층·19:50·20:00 과 안 겹치는 시각. 예: **17:00** 또는 **19:00**(D8 이 18:10 을 쓰면 18:10~18:12 을 피해). 리터럴 1개 + 가드 1줄 | 최소 |
| **B. 원복** | 15:45(cycle269/270 원안)로 되돌린다. 검증된 시각 | 최소, 단 사용자 요구("20:00 이후")를 못 지킴 |
| **C. 구조 변경** | task 를 `uvicorn` lifespan 으로 빼 20:10 이후에도 살린다 | D-11 과 같은 재설계. 이번 범위 밖 |

**동반 권고(영속 가드)** — `run_periodic_task_loop` 의 모든 `wait_time` 에 대해
**`wait_time < TIME_SETTLEMENT` 를 단언**하는 AST/불변식 가드 1건. 이 결함 계열(= "루프 밖 시각")은
일봉 적재 23:00/05:00 안이 이미 같은 이유로 기각된 적이 있다(워크리스트 D-11) — **두 번째 재발이다.**
가드가 있으면 세 번째가 없다.

---

# D4 — 주간 자문 레벨 0 + "지금 UI 에서 간단하게 적용 가능한가"

## D4-1. 레벨 0 의 정의 (자문 원문 전사)

`_workspace/domain_consult/weekly_advice_auto_apply_20260910.md` §R4 표, **원문 그대로**:

> | 레벨 | 내용 | 승인 | 도입 시점 |
> |---|---|---|---|
> | **0** | **적용 후보 큐** — 파싱·전사·PUT 조립·기본값 대조·게이트 사전판정까지 자동. **적용은 사람이 항목 단위 체크.** | 항목마다 사람 | **지금 권고.** 이번 주 3키 전부 여기서 처리 |

카드 ① 원문: "**A. 레벨 0 — 적용 후보 큐** (파싱·전사·PUT 조립·기본값 대조·게이트 사전판정 자동,
**적용은 사람이 항목 단위 체크**)" · "**권고: A**, 그리고 4주 새도 관측(게이트 판정 vs 사람 선택 불일치 0)이
쌓인 뒤에 B 를 재검토."

승격 기준(원문): "레벨 0 을 돌리는 동안, 매주 '게이트가 통과시켰을 항목' 과 '사람이 실제로 체크한 항목' 의
집합을 나란히 기록한다. **4주 연속 불일치 0** 이면 승격을 검토한다."

> **레벨 0 은 "자동 적용" 이 아니다.** 사람의 손가락(항목별 체크 + 적용 버튼)은 그대로 남고,
> 없애는 것은 **값을 손으로 옮겨 적는 단계**뿐이다. 자문이 "없앨 대상은 눈이 아니라 손가락" 이라고 적은 것과
> 사용자 질문("지금처럼 UI 에서 간단하게 적용 가능한가")은 **정확히 같은 것을 가리킨다.**

## D4-2. 지금 UI 가 하는 일 (코드 판독)

| 위치 | 사실 |
|---|---|
| `frontend/src/pages/Recommendations.tsx` (675L) | 탭 2개 — **신규** = `target_date` 가 가장 최근인 행 전부(status 무관, `:162-167`) / **이력** = 그 밖 + status·전략 필터(`:170-174`). 날짜별 그룹 → `strategy_id` 정렬(`:178-190`) |
| `:511-534` | **키별 체크박스**. `selectableKeys = recommended_params 키 − applied_params 키`(`:329`). `actionable = status ∈ {pending, partial}`(`:212`) |
| `:401-402` | weight 적용 별도 체크박스 |
| `:595-652` | 적용 버튼 → 확인 모달 → `applyRecommendation(id, keys, {applyWeight})` |
| `src/routes/recommendations.py:29-33` | `GET /api/recommendations` = `list_recommendations(days=30)` = `SELECT * … WHERE target_date >= $1` — **필터·스코프 없음** |
| `:45-` | `POST /api/recommendations/{rec_id}/apply` — `status ∈ {pending, partial}` 이 아니면 거부(`:63-66`) → `keys ∩ recommended_params ∩ PARAM_RANGES` 만 적용(`:74-97`) → `save_params` + in-memory `strategy.config.params` 갱신 → 잔여 있으면 `partial`, 없으면 `applied` |

⇒ **UI·라우트는 "행이 `parameter_recommendations` 에 `status='pending'` 으로 있으면" 자문의 출처를 묻지
않는다.** 그래서 재사용 자체는 성립한다.

## D4-3. 같은 표에 넣을 때 걸리는 것 (스키마·경로 실측)

| # | 장애물 | 근거 | 최소 해소책 |
|---|---|---|---|
| **B-1** | **UNIQUE 부분 인덱스** `idx_param_rec_unique_per_day ON (target_date, strategy_id) WHERE status IN ('pending','applied','partial')` | `supabase/migrations/007_*.sql:18-20` | 목요일 20:00 일일 자문이 이미 `(오늘, kojiro)` 를 점유한다. 주간 행 INSERT 는 **중복으로 거부되고 `insert_recommendation` 이 `None` 을 조용히 반환**한다(`db/parameter_recommendations.py:89-95` — `duplicate/unique/23505` 를 WARNING 1행으로 흡수). ⇒ **주간 행이 소리 없이 사라진다.** 해소 = `source` 컬럼 추가 + 인덱스를 `(target_date, strategy_id, source)` 로 교체 |
| **B-2** | `source`/`provider` 컬럼이 **없다** | migration 007 + 028(status에 `applied_auto` 추가)까지 컬럼 목록 확인 | `ALTER TABLE … ADD COLUMN source VARCHAR(16) NOT NULL DEFAULT 'daily'` (가산형) |
| **B-3** | 인덱스 **교체**는 가산형이 아니다 | 루트 CLAUDE.md 사전승인 범위 = "NULL 허용 ADD COLUMN·INDEX·신규 테이블" | 새 UNIQUE 인덱스 생성 후 구 인덱스 DROP = **별도 승인 필요**(되돌리기는 재생성으로 가능) |
| **B-4** | `expire_pending_before(target_date)` 가 **`status='pending'` ∧ `target_date < 오늘` 을 전부 expired 로** 만든다 | `db/parameter_recommendations.py:211-218`, 호출 = `recommendation_engine.py:399`(매일 20:00 `generate_recommendations` 진입부) | 목 20:30 에 넣은 주간 행은 **금 20:00 에 만료**된다 = 사람에게 **약 24시간**. 주간 주기엔 짧다. `source='weekly'` 는 만료에서 제외하거나 별도 TTL |
| **B-5** | 루틴이 DB 에 쓸 **경로가 없다** | `src/middleware/api_auth.py:262-269` — 리포터 키는 GET/HEAD 전체 + `POST /api/log-reports/{YYYY-MM-DD}/external` **정확히 1경로**, 그 외는 403 | §D4-4 |
| **B-6** | `PARAM_RANGES` **밖의 키는 적용 버튼이 조용히 버린다** | `routes/recommendations.py:74-97` — 미등재 키는 `[manual_apply_safeguard_skip]` 후 제외, `applied_params` 에 안 들어가 `remaining` 에 남아 **status='partial'** | 이번 주 권고 3건 중 LTV `trailing_stop_rate`·`overnight_stop_loss` 는 **PARAM_RANGES 안**(`recommendation_engine.py:56,72`)이라 정상 적용. VCP `last_pullback_max` 는 **밖**이라 체크해도 안 먹고 partial 로 남는다. UI 에 사전 표시가 없다 → **레벨 0 의 "게이트 사전판정" 이 정확히 이 자리다** |
| **B-7** | 신규/이력 탭 분기가 **`target_date` 최대값 단독** | `Recommendations.tsx:154-174` | 주간 행이 일일 행과 같은 날짜면 한 그룹에 섞이고, 다른 날짜(예: 금요일)로 넣으면 **주간이 "신규" 탭을 통째로 차지**해 그날 일일 자문이 이력으로 밀린다 |

## D4-4. 루틴이 결과를 넣는 경로 — 여기가 진짜 병목

현행 인증 계약(`api_auth.py:88-100` 주석 **원문**):
> "`|` 로 경로를 늘리는 변경은 '유일한 쓰기 경로' 라는 스코프의 근거 자체를 무너뜨리므로 **금지**."

즉 **"리포터 키에 `POST /api/recommendations/weekly/{date}` 를 한 줄 더 허용" 은 현행 계약이 명시적으로
금지한 변경**이다. 선택지는 넷이다.

| 안 | 내용 | 평가 |
|---|---|---|
| **가. 인증 스코프 확장** | `REPORTER_WRITE_PATH_RE` 에 경로 1개 추가 | 코드는 1줄이지만 **위 주석이 금지한 변경**이고 `src/middleware/` 는 인터넷 노출 보안 경계다. **사용자 승인 + 계약 문구 개정**이 선행. 자문도 C-6 을 MEDIUM 으로 등재 |
| **나. 기존 유일 경로에 얹기** | 주간 결과를 `POST /api/log-reports/{date}/external` 로 보내고 백엔드가 파싱 | 인증 변경 0. 그러나 목요일은 20:20 일일 리포트가 **같은 경로·같은 날짜**를 이미 쓴다 → 충돌·덮어쓰기 위험. 두 종류를 한 테이블에 섞는 설계 부채 |
| **다. 세션이 전사** | 클라우드 루틴은 지금처럼 PR/Notion 만 쓰고, **메인 세션(운영 키 보유)이 PR md 를 파싱해 PUT/INSERT 를 조립** | **인증·스키마 변경 0.** 자문의 "파싱·전사·PUT 조립·기본값 대조·게이트 사전판정" 을 그대로 만족한다. 주 1회 사람이 세션을 여는 것을 전제 |
| **라. 백엔드가 당겨오기** | 백엔드가 GitHub/Notion 을 폴링 | 새 외부 자격·의존. 범위 과대 |

> **레벨 0 의 정의는 "적용 실행" 이 아니라 "전사와 사전판정" 이다.** 그렇다면 **다** 가 가장 싸고
> 계약 위반이 0 이다 — 다만 산출물을 어디에 둘지(DB 행 vs 세션이 만든 체크리스트 문서)가 갈리고,
> **"지금 UI 의 적용 버튼" 을 쓰려면 결국 DB 행이 필요**하므로 B-1~B-4 는 그대로 남는다.

## D4-5. 자문이 짚은 정합성 충돌 중 코드로 재확인한 것

| # | 자문 주장 | 이 판독의 코드 대조 |
|---|---|---|
| C-1/C-2 | `_CONSERVATIVE_KEYS = frozenset()` 이라 방향 게이트가 아무것도 통과시키지 못한다 | **확인.** `recommendation_engine.py:531` 이 빈 frozenset(사이클 210). `:637-638` 의 `if k not in _CONSERVATIVE_KEYS: continue` 가 **모든 키를 건너뛴다** ⇒ params 자동 적용은 구조적으로 0건 |
| C-3 | `auto_apply_enabled` 에 provider 스코프가 없다 | **확인.** 20:00 경로 하나뿐(`scheduler.py:897-900` 부근에서 `auto_apply_recommendations` 호출). 켜면 일일 weight 감액이 함께 깨어난다 |
| — | weight 자동 감액은 `enabled=False` 방지 장치를 겸한다 | **확인.** `new_weight = max(rw, current × 0.5)`(`:622-623`)는 `current > 0` 인 한 0 에 닿지 않는다. `save_weights` 는 `enabled = weight > 0`(`db/strategy_config.py:64`) |
| C-4 | UNIQUE 로 목요일 두 자문이 충돌 | **확인** (§D4-3 B-1) |
| C-5 | 20:00 auto_apply 가 20:30 산출물보다 30분 먼저 돌고 다음날 expire 가 먼저 지운다 | **확인** (§D4-3 B-4) |
| C-6 | 리포터 키로는 DB·params 에 쓸 수 없다 | **확인**, 그리고 **경로 추가는 코드 주석이 금지**한다는 사실이 자문 기술보다 한 단계 강하다 |
| 한계 7 | 운영 DB `auto_apply_enabled` 실측 미수행 | **이 판독도 확인하지 않았다** — 설정 조회는 지시 범위 밖(운영 설정 API 호출 금지)이라 `system_config` 를 건드리지 않았다. **T-1 은 여전히 열려 있다** |

## D4-6. 사용자 질문에 대한 답 — 예/아니오 + 조건

> **질문**: "혹시 지금처럼 UI에서 간단하게 적용가능한지도 체크해줘."

**답: 예 — 적용 UI 자체는 한 줄도 안 고치고 그대로 쓸 수 있다. 단 아래 4개가 선행해야 하고,
그중 2개는 사용자 결정 사안이다.**

| # | 선행 조건 | 규모 | 승인 |
|---|---|---|---|
| **1** | `parameter_recommendations` 에 `source VARCHAR(16) NOT NULL DEFAULT 'daily'` 추가 | 가산형 마이그레이션 1개 | 사전 승인 범위 |
| **2** | UNIQUE 인덱스를 `(target_date, strategy_id, source)` 로 교체(신규 생성 → 구 인덱스 DROP) | 마이그레이션 1개 | **DROP INDEX = 별도 승인** |
| **3** | `expire_pending_before` 가 `source='weekly'` 를 만료 대상에서 제외(또는 별도 TTL) | `db/parameter_recommendations.py` 1함수 + 호출부 무접촉 | 사전 승인 범위(매매 행위 변경 0) |
| **4** | 루틴 → DB 적재 경로 결정 (§D4-4 가/나/다/라) | 안에 따라 다름 | **사용자 결정**(가 는 보안 계약 개정) |

**UI 쪽 권장(필수는 아님)** — 있으면 "간단하게" 가 실제로 간단해지는 것들:

| 항목 | 파일 | 이유 |
|---|---|---|
| `source` 배지("일일"/"주간") | `types/recommendations.ts` + `Recommendations.tsx` | 같은 날짜 그룹에 두 출처가 섞인다(B-7) |
| 탭 또는 필터에 `source` 추가 | `Recommendations.tsx:162-174` | "신규 = 최신 target_date" 단독 분기가 주간과 충돌 |
| **`PARAM_RANGES` 밖 키를 UI 에서 미리 회색 처리 + 사유 표시** | 라우트가 화이트리스트를 응답에 실어야 함 | **B-6 이 지금 가장 실질적인 함정이다.** 체크했는데 안 먹고 `partial` 로 남는 경험은 "간단" 의 반대다. 레벨 0 의 "게이트 사전판정" 이 이 자리 |
| MSW·Playwright 목 동기화 | `frontend/src/test/handlers.ts` · `e2e/fixtures/api-mocks.ts` | cycle266 이 실증한 재발 지점 — 목이 *의도한 계약*만 담으면 3개월 초록일 수 있다 |

**하지 말아야 할 우회 2가지**
1. **주간 행에 다른 `target_date`(예: 금요일)를 넣어 UNIQUE 를 피하는 것** — B-7 로 "신규" 탭을 주간이
   차지하고, 날짜가 사실이 아니게 되어 이후 모든 집계가 어긋난다.
2. **`status` 를 우회해 넣는 것**(예: 처음부터 `partial`) — 부분 UNIQUE 가 `partial` 도 포함하므로
   해결되지 않고, `actionable` 판정만 흐려진다.

**마지막으로, 레벨 0 은 "적용을 집행하는 경로" 를 만들지 않는다.** 자문이 §"team-leader 에게" 에서
"레벨 0 도 하네스 계약상 '매매 행위를 바꾸는 코드 변경' 의 인접 영역" 이라고 적은 이유는 **큐가 곧 실행이
되지 않도록 경계를 명시적으로 그으라는 뜻**으로 읽는 것이 맞다 — 위 4개 선행 조건 어디에도
`apply` 를 자동 호출하는 코드는 없고, **없어야 한다.**

---

## 부록 A — 이 판독이 실제로 실행한 것 (재현 가능)

- `git show HEAD:<path>` 로만 소스를 읽었다(워킹트리 무접촉). 판독 도중 HEAD 가 `a10191b` → `cda2dd3` 로
  이동했고 §D8-4 는 그 새 커밋을 대상으로 한다.
- EC2 읽기 전용 2종 — ① `docker compose -f docker-compose.prod.yml logs backend`(grep)
  ② `docker compose … exec -T -e PYTHONPATH=/app backend python /tmp/q*.py` 로 **SELECT 만** 수행.
  스크립트는 컨테이너 `/tmp` 에만 두었고 DB 쓰기·KIS 호출·설정 변경 0.
- 로컬 산출물은 이 파일 하나. `src/**`·`tests/**`·`frontend/**` diff 0.

## 부록 B — 후속 등재 후보 (이번 사이클 범위 밖)

| # | 내용 | 등급 |
|---|---|---|
| **F-D8-b** | `run_periodic_task_loop` 의 `wait_time < TIME_SETTLEMENT` 영속 가드 신설(= "루프 밖 시각" 3차 재발 차단) | **HIGH** |
| **F-D5-a** | `_is_daily_load_universe` docstring·호출부 주석·`src/engine/CLAUDE.md`·워크리스트의 "거래대금 20억" → **10억** 정정 | LOW(문서) |
| **F-D8-a** | `_evening_funnel_capture_once` 의 "일봉 적재 완료 대기" 주석 정직화(`count_all()` 은 빈 테이블만 막는다) | INFO |
| **F-D5-b** | 오늘 유니버스 1,005 중 **일봉 행이 하나도 없는 8종목** · **7영업일 창 밖 영구 구멍 25종목** 처분(강제 backfill 트리거 필요 여부) | MEDIUM |
| **F-D5-c** | 일자별 적재 종목 수 단조 감소(09-01 1,290 → 09-10 1,003, 07-01 기준 1,801)가 의도된 축소인지 — 워크리스트 기존 등재 항목의 최신 실측 | MEDIUM |

---

*작성 = cycle273 U-D 판독 에이전트 · 읽기 전용 · 코드/테스트/프론트/DB 쓰기 0*
