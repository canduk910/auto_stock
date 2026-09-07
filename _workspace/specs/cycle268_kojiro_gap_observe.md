# cycle268 명세 — `[kojiro_gap_observe]` 갭 판정 shadow 관측 (**행위 변경 0**)

- 작성 2026-09-07 · team-leader · 사용자 승인 = "관측 넣어보자"(조사 §7.1 **3안 단독**)
- 정본 = `_workspace/consult/2026-09-07_kojiro_gap_contamination.md` ·
  `_workspace/analysis/2026-09-07_open_scope_dplus1_readout.md`
- **이번 사이클은 재기만 한다.** 시정(조사 1안 = `risk.py:646` 에 kojiro 추가)은 **범위 밖**이며
  8영역 승인 사안이다. 이 명세 어디에도 그 변경은 없다.

---

## §0. 범위 — 한 줄

`kojiro.check_buy_signal` 의 갭 판정이 **그 순간 실제로 무엇을 읽었는지**를 하루 수십 행으로 남긴다.
매매 판정·래치·수량·시점은 **한 글자도 바뀌지 않는다.**

### 접촉 파일 (정확히 2개 + 테스트)

| 파일 | 성격 | 변경 |
|---|---|---|
| `src/engine/kojiro_gap_observe.py` | **신규 leaf** (cycle264 `open_price_observe.py` 선례) | 관측 본체 전량 |
| `src/engine/strategies/kojiro.py` | 매매 파일 (8영역 **아님**) | import 1행 + **바 statement 6행** |

**diff 0 을 실증해야 하는 것** — `src/engine/{risk,order_engine,session,scanner,strategy_registry,scheduler}.py` ·
`src/api/**` · `src/realtime/**` · `src/auth/**` · 나머지 전략 6파일 · `DEFAULT_PARAMS`(신규 키 0).

---

## §1. 왜 이 설계인가 — 판독 가능성 먼저

"이 마커 하루치를 보면 무엇을 알 수 있는가" 를 먼저 못박는다. 아래 5가지가 **한 번의 grep 으로** 나와야 한다.

| 알아야 할 것 | 어떻게 나오는가 |
|---|---|
| **경로 A/B 비율** (오염 노출 종목 수) | `verdict=candidate` 행을 `caller` 로 그룹 — `caller=on_tick` = 경로 B(오염), `caller=_swing_buy_poll_loop` = 경로 A(깨끗) |
| **오염으로 판정이 뒤집혔는가 (경로 A 행)** | 같은 행 안의 `verdict` ↔ `ws_verdict` 불일치. `grep 'verdict=skip_up ws_verdict=pass'` = "깨끗한 경로는 걸렀는데 오염 경로였으면 놓쳤을 종목" |
| **오염으로 판정이 뒤집혔는가 (경로 B 행)** | 익일 오프라인 조인 — `arg_open`·`prev_close`·`gap_up`·`gap_down` 이 전부 행에 있으므로 `stock_master_daily` KRX 시가만 붙이면 반사실 재계산이 **완결**된다 (§5 쿼리) |
| **09:05~09:30 구간 직접 관측** (조사 §4.2-2 공백) | 이 마커는 매수 창 안에서만 verdict 행을 낸다 — cycle264 `[open_scope_observe]` 가 09:00 에 cap 소진되던 공백을 정확히 메운다 |
| **결측이 무작위인가** | `verdict=candidate` 행은 있는데 대응하는 판정 행(`pass`/`skip_*`/`collapse`/`no_data`)이 없는 ticker = **갭 블록에 도달하지 못한 코호트**. 그 사유는 시간창 밖 또는 섹터캡(기존 `[kojiro_sector_cap]` 로 조인)이다. **침묵으로 사라지지 않는다** |

> cycle264 가 `reason=ok|rest_zero|rest_error` 로 침묵을 막은 것과 같은 원칙 —
> **"오염이 없었다" 와 "아무것도 못 쟀다" 가 로그에서 구별돼야 한다.**

### 1.1 조사가 남긴 공백 3개와 이 마커의 대응

1. `[open_source_compare]`(cycle264)에 kojiro 가 **구조적으로 못 들어간다**(`_targets` 부재) → 별도 마커로 해결.
2. 09:05~09:30 직접 관측 0건 → 이 마커가 그 창에서 발화한다.
3. 과거 갭스킵 이력 0(INFO 2일 보존) → **오늘부터 쌓기 시작**한다. 20:10 로그 분석이 `system_logs` 로 영속한다.

---

## §2. 마커 사양

### 2.1 서식 (고정 · key=value · **INFO**)

```
[kojiro_gap_observe] ticker=131290 verdict=skip_up caller=_swing_buy_poll_loop ws_cmp=ws_ne \
 arg_open=252500 ws_open=236500 prev_close=236500 gap_rate=6.77 ws_gap=0.00 ws_verdict=pass \
 cur=253000 gap_up=5.0 gap_down=-4.0
```

(실제로는 한 줄. 필드 **순서 고정** — 과거 로그 대조 가능성을 위해 이후 사이클에서도 순서·이름을 바꾸지 않는다.)

| 필드 | 값 | 비고 |
|---|---|---|
| `ticker` | 6자리 | |
| `verdict` | `candidate` \| `no_data` \| `skip_up` \| `skip_down` \| `collapse` \| `pass` | §2.2 |
| `caller` | 호출자 함수명 원문 (`on_tick` / `_swing_buy_poll_loop` / 그 외 원문) \| `?` | **경로 판별 정본**. 정규화 금지 — 미지 호출자가 생기면 그 이름이 그대로 보여야 한다 |
| `ws_cmp` | `ws_absent` \| `ws_eq` \| `ws_ne` | WS 캐시 대조 **사실만**. 해석 라벨(`rest`/`ws`) 금지 |
| `arg_open` | 판정에 **실제로 쓰인** `open_price` | **이 마커의 정본 값** |
| `ws_open` | `scanner.ticker_prices[ticker]["open_price"]`, 부재 `-` | 경로 A 행에서 이것이 곧 **오염 대조군** |
| `prev_close` | `info["prev_close"]` (DB 일봉, 깨끗) | |
| `gap_rate` | `arg_open` 기준 갭률, 소수 2자리. 산출 불가 `-` | |
| `ws_gap` | `ws_open` 기준 갭률(반사실). 불가 `-` | |
| `ws_verdict` | `ws_gap` 을 **같은 임계**로 판정한 결과 `skip_up`/`skip_down`/`pass`. 불가 `-` | **갭 게이트만** 재현(붕괴 가드 제외) — 명세에 명시 |
| `cur` | `current_price` | 붕괴 가드 사후 재구성용 |
| `gap_up` / `gap_down` | 그 순간 **실제 적용된** 파라미터 | PUT 로 장중 변경 가능하므로 값을 함께 남긴다 |

### 2.2 `verdict` 6종과 발화 위치 (kojiro.py 삽입 지점 6곳)

`check_buy_signal` 본체 순서 그대로:

| # | 위치 | verdict | 의미 |
|---|---|---|---|
| 1 | `info`/`stage!=1` 통과 직후, **섹터캡·시간창 판정 전** | `candidate` | "이 ticker 가 이 경로로 후보 평가에 도달했다" = **A/B 비율의 분모** |
| 2 | `if open_price > 0 and prev_close > 0:` 의 **else** | `no_data` | 갭 게이트가 평가조차 안 됨 |
| 3 | `gap_rate >= gap_up` 분기 안, 기존 `logger.info` **뒤**, `_bought_today.add` **앞** | `skip_up` | |
| 4 | `gap_rate <= gap_down` 분기 안, 같은 자리 | `skip_down` | |
| 5 | `current_price < open_price` 붕괴 분기 안 | `collapse` | |
| 6 | 붕괴 가드 통과 후 `self._bought_today.add(ticker)` **앞** | `pass` | 매수 신호로 간다 |

- 6곳 모두 **바 statement 삽입**이다. 기존 코드의 재배열·조건 병합·early return 이동 **금지**.
- 기존 `logger.info("고지로 갭업 스킵: ...")` 두 줄은 **byte 불변**(과거 로그 대조 유지).
- `no_data` 를 위한 `else:` 추가는 허용(그 블록 안에 관측 호출 1행만).

### 2.3 cap

`KstDailyEmitCap[tuple[str, str, str]]`, 키 = **`(ticker, caller, verdict)`**.

- 팀장 지시("1회/(ticker,판정)/일")의 **초집합**이며 상한이 더 조인다: ticker × 2 caller × 6 verdict = **10행/ticker/일 이론 최대**, 실측 예상 2~3행. 후보 13~24 종목 ⇒ **하루 30~70행**. cycle237 폭주(1만행) 위험 없음.
- `caller` 를 키에 넣는 이유 = 넣지 않으면 **같은 ticker 가 경로 A·B 양쪽에서 심사받은 사실이 지워진다** — 그것이 이 사이클이 재려는 바로 그 값이다(004020 이 오늘 그 코호트였다).
- 날짜 리셋은 `KstDailyEmitCap` 자기 리셋에 맡긴다(호출부에 날짜 블록 금지 — cycle258 표준).

---

## §3. 안전 계약 (행위 변경 0 의 실체)

1. **never-raise 2중.** 관측 함수 전체를 `try/except Exception` 으로 감싸고, 그 안에서
   `observer_trace.trace_observer_failure("[kojiro_gap_observe]", ticker, cap)` 로 흔적만 남긴다.
   무흔적 `pass` 금지(cycle258 카드 #5). 반환값은 항상 `None` — **호출부는 반환값을 쓰지 않는다.**
2. **read-only.** `self._bought_today` · `self._candidates` · `self.state` · `self.config.params` ·
   `scanner.ticker_prices` 를 **읽기만** 한다. 어떤 dict 도 생성·변경하지 않는다(cycle242 G-242-8 동형).
3. **`await`/DB/HTTP 0건.** `check_buy_signal` 은 동기 함수이고 그 hot path 다.
   `fetch_stock_detail`·`pg.*`·`kis_request`·`asyncio.create_task` **전부 금지**(AST 가드).
4. **비용 순서.** cap peek 를 **가장 먼저** 한다 — `caller` 해석(프레임 1회) → 키 조립 → `should_emit`
   → False 면 즉시 return. WS 캐시 조회·갭 산술·문자열 포맷은 **cap 을 통과한 뒤에만** 한다.
   (틱당 수십~수백 호출되는 경로다. cap 뒤 작업을 앞에 두면 관측이 비용이 된다.)
5. **파라미터 무접촉.** `gap_up_skip_pct`·`gap_down_skip_pct` 값 변경 금지, `DEFAULT_PARAMS` 신규 키 0.
   임계는 `self.config.params` 에서 **읽어서 로그에 싣기만** 한다.

### 3.1 `caller` 해석 규약

leaf 안에서 `sys._getframe(depth)` 로 호출자 함수명을 읽는다.

- `depth` 는 **키워드 기본값 2** (leaf 함수 → `check_buy_signal` → 실제 호출자).
- 따라서 **kojiro.py 는 leaf 함수를 직접 호출한다** — `self._observe(...)` 같은 래퍼 메서드를 두면
  깊이가 어긋난다. AST 가드가 6개 호출 지점이 모두 **직접 호출**임을 강제한다.
- 실패·부재는 `?`. 미지 호출자는 **원문 그대로** 남긴다(화이트리스트 정규화 금지 — 새 호출 경로가
  생기면 그 사실이 로그에 드러나야 한다).

---

## §4. 왜 KRX 대조를 hot path 에서 하지 않는가

팀장 지시는 "가능하면 KRX 기준 대조값, hot path 에서 못 하면 백그라운드 분리" 였다. **둘 다 하지 않는다.**

- hot path 대조는 §3-3 위반(DB/HTTP)이라 불가.
- 백그라운드 대조(cycle264 `[open_source_compare]` 방식)는 **task 생성·등록이 `scheduler.py`** 에 있어야
  하는데, scheduler 는 **라인 상한 <3,900**(cycle257 영구 가드, 현재 3,896L — **여유 3행**)이고 8영역이다.
  관측 하나를 위해 그 가드를 건드리는 것은 위험 대비 이득이 없다.
- **대신 반사실이 로그만으로 완결된다** — 경로 A 행은 `ws_verdict` 로 **행 안에서** 뒤집힘이 보이고,
  경로 B 행은 `arg_open`·`prev_close`·임계가 다 있으므로 익일 `stock_master_daily` 조인 한 번으로
  재계산된다(§5). 조사 §4.3-(가)가 오늘 실제로 돌려 8/8 미탐을 낸 바로 그 방법이다.

> 후속 등재 — 백그라운드 KRX 대조가 필요해지면 `scheduler.py` 접촉 승인 + 라인 여유 확보가 선결이다.

---

## §5. 익일 판독 절차 (경로 B 반사실)

```sql
-- 마커 행에서 ticker/arg_open/prev_close/gap_up/gap_down 을 파싱해 임시 테이블 t 로 적재한 뒤
SELECT t.ticker, t.caller, t.verdict, t.arg_open, d.open_price AS krx_open,
       round((t.arg_open - t.prev_close)::numeric / t.prev_close * 100, 2) AS gap_used,
       round((d.open_price - t.prev_close)::numeric / t.prev_close * 100, 2) AS gap_krx
FROM t JOIN stock_master_daily d
  ON d.ticker = t.ticker AND d.bas_dd = <그날>;
-- gap_used 와 gap_krx 를 t.gap_up / t.gap_down 으로 각각 판정해 전이표를 만든다.
```

판독 시 **반드시** 지킬 것:

- **`caller=on_tick` 행에서만** 오염 판정이 성립한다. `caller=_swing_buy_poll_loop` 행의 `arg_open` 은
  REST 값이라 KRX 확정 시가와 일치하는 것이 **정상**이며, 그 일치는 "오염 없음"의 증거가 아니라
  **경로 A 가 깨끗함의 재확인**일 뿐이다(cycle264 `used_src=rest` 함정과 동형).
- `ws_verdict=-` 행(WS 캐시 부재)을 "일치" 로 세지 마라. 대조 자체가 성립하지 않은 행이다.
- **의미 반전 없음** — 이 마커는 신규라 배포 전 로그가 존재하지 않는다. 전후 합산 문제도 없다.

---

## §6. 검증 게이트 (tdd-engineer / backend-dev / tester)

### 6.1 행위 보존 실증 (**최우선**)

- **골든 매트릭스**: 갭업/갭다운/붕괴/통과/무데이터 × WS캐시 유무 조합 전수에서
  `check_buy_signal` 의 **반환 Signal · `_bought_today` 집합 · `state.buy_signals` 내용**이
  관측 도입 전(HEAD) 과 동일함을 단언한다.
- **관측기 폭사 내성**: leaf 함수를 `side_effect=Exception` 으로 monkeypatch 한 상태에서 위 매트릭스를
  **다시** 돌려 결과가 동일함을 단언한다(cycle262 fail-open 계약 동계열).
- **131290 재현 케이스(필수)**: `prev_close=236500`, WS시가 `236500`, KRX시가 `252500`, 임계 5.0.
  - 경로 A(arg=252500): `verdict=skip_up`, `ws_gap=0.00`, `ws_verdict=pass` → **뒤집힘이 한 행에서 보인다**
  - 경로 B(arg=236500): `verdict=pass`, `ws_cmp=ws_eq` → 오프라인 조인으로만 드러난다
- **cap 계약**: 같은 (ticker,caller,verdict) 2회차 무발화 / caller 만 다르면 발화 / 날짜 롤오버 리셋.

### 6.2 AST·구조 가드

- leaf 의 `src.*` import = `daily_emit_cap` · `observer_trace` + 함수-지역 `scanner` 뿐.
- leaf·호출 6지점에 `await` · `pg.` · `kis_` · `create_task` · `fetch_stock_detail` **0건**.
- kojiro.py 의 관측 호출 6곳이 **직접 호출**(래퍼 메서드 경유 0) — `caller` depth=2 전제 보존.
- 기존 `"고지로 갭업 스킵"` / `"고지로 갭다운 스킵"` 로그 문자열 **byte 불변**.
- `DEFAULT_PARAMS` 키 집합 불변.
- `git diff --name-only` 가 §0 표의 2개 src 파일 + 테스트만 포함함을 테스트로 잠근다.

### 6.3 뮤테이션 (tester)

- 6개 호출 지점을 **하나씩 삭제**했을 때 각각 최소 1개 테스트가 붉어져야 한다(관측을 지워도 초록이면 공허).
- cap 키에서 `caller` 를 빼면 붉어져야 한다.
- `ws_verdict` 판정 부등호(`>=` → `>`)를 뒤집으면 붉어져야 한다.
- `arg_open` 과 `ws_open` 필드를 **서로 바꿔치기**하면 붉어져야 한다(정본 값 혼동은 판독을 통째로 뒤집는다).

### 6.4 회귀

- `python -m pytest -q` 전체 **회귀 0**.
- `git diff --name-only` 로 8영역·`scheduler.py`·타 전략 6파일 diff 0 실증(수동 확인 + 6.2 가드).

---

## §7. 금지 사항 재확인

- 커밋·push **금지**(메인 세션 결정).
- `risk.py:646` 에 kojiro 추가(조사 1안) **금지** — 이번 승인 범위 밖.
- `gap_up_skip_pct` / `gap_down_skip_pct` 값 변경 금지.
- `DEFAULT_PARAMS` 신규 키 금지(필요하면 **멈추고 보고**).
- `scheduler.py` 접촉 금지(라인 여유 3행).

---

## §8. 곁다리 — 등재만 (이번 사이클에서 고치지 않는다)

조사 §6.1 이 찾은 **momentum·LTV `check_exit_signal` 익일청산 갭률의 동일 오염**을
워크리스트 후속 **F-3b** 로 등재한다. 방향이 kojiro 와 **반대**(손실 확대가 아니라 **기대수익 훼손** —
갭률 과소측정 → 트레일링으로 갈 종목이 즉시청산)이고 임계가 10.0% 로 높아 뒤집힘 빈도가 낮을 것으로
보이나(추론, 미측정), **현재 어느 목록에도 없다**. 08:00 `_execute_next_day_clear` 경로는 설계 의도상
프리장 시가 기준이 맞으므로 **오염이 아니다** — 문제는 MAIN 구간 `on_tick` 이 같은 낡은 값을 계속 읽는 것.
