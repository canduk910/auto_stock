# cycle299 — 일봉 보존·백필 확장 (Red)


> ⚠️ **확정값 정정(2026-09-18)** — 이 메모는 Red 작성 시점 기록이라 목표를 `380/220` 으로 적는다.
> 사용자 결정으로 **retention 390 · target 225** 로 확정됐다(보유 225 에서 `effective_ema_long` 이
> 정확히 200 이 된다. 220 이면 195). 경위 = `docs/history/*.history.md` 의 cycle299 (2026-09-18) 항목.

작성 2026-09-17 · tdd-engineer · **Red only, `src/` 무접촉**

## 1. 명세

200일 EMA 를 쓰려면 일봉이 220 영업일 필요하다. KIS `FHKST03010100` 의 100일은 **호출당**
한도이고 `src/api/condition.py::fetch_daily_candles_backfill(ticker, total_days, *, window=100)`
이 이미 날짜 윈도우를 `ceil(total_days/window)` 개로 쪼개 순차 호출·병합한다. 총량을 막는 것은
KIS 가 아니라 우리 상수 둘뿐이다.

| 파일 | 상수 | 현재 | 목표 |
|---|---|---|---|
| `src/db/stock_master_daily.py:710` | `DAILY_RETENTION_DAYS` | 230 | **380** (달력일) |
| `src/engine/scanner.py:2804` | `_DAILY_LOAD_VCP_BACKFILL_DAYS` | 120 | **220** (영업일) |

🔴 **두 값은 반드시 함께 간다.** target 이 retention 의 실보유 영업일을 넘으면
`existing_count` 가 영원히 target 에 못 닿아 매일 밤 전량 재backfill(churn)이다
(사이클 192 → 196 이 시정한 바로 그 결함).

**이 사이클은 매매 행위를 바꾸지 않는다.** VCP `prepare()` 는 여전히 100일만 읽는다.

## 2. 행위 무변경의 구조적 근거 (재확인 완료)

| 근거 | 위치 | 확인 |
|---|---|---|
| 읽기 깊이 하드 클램프 `max(1, min(days, 100))` | `src/db/stock_master_daily.py:271` | ✅ |
| 행 반환 읽기 전부가 위 함수 경유 (`get_donchian_high`·`get_atr`·`get_recent_daily_with_fallback`·`get_recent_daily_normalized`) | 동 모듈 | ✅ |
| `KIS_DAILY_CANDLES_MAX = 100` | `src/engine/strategies/vcp_breakout.py:262` | ✅ |
| `fetch_days = min(ema_long + base_max + 10, KIS_DAILY_CANDLES_MAX)` | `:263` | ✅ |
| 나머지 소비처는 스칼라 집계 (`max_bas_dd`·`count_all`·`count_by_ticker`·`routes/market_ops.py`) | — | ✅ |

→ retention 을 380 으로 늘려도 **어느 소비처도 100행 넘게 못 읽는다**.

## 3. 실측 수치 (환산 앵커 = 사이클196 실측 230cal ⇄ 154영업일)

| | 현행 (230/120) | 목표 (380/220) |
|---|---|---|
| backfill 윈도우 수 `ceil(t/100)` | 2 | **3** |
| 최고 도달 달력일 `int(t*7/5)+10` | 178 | **318** |
| retention 여유 (retention − 도달) | 52cal | **62cal** |
| retention 실보유 영업일 | 154 | **254** |
| 정상상태 마진 (보유 − target) | 34 | **34** ← 정확히 보존 |
| 1회 backfill 도달 영업일 | 119 | **212** |
| 1회 부족분 (target − 도달) | 1 | **8** ← 아래 §6 |

도달 달력일은 수식 복제가 아니라 `fetch_daily_candles_ranged` 윈도우 `(start,end)` 캡처로
**실측**했다(사이클196 `_capture_windows` 패턴 답습, 외부 시계 의존 0).

## 4. 신규 Red 가드

### `tests/unit/db/test_cycle299_retention_expansion.py`
| ID | 내용 | Red |
|---|---|---|
| G-299-1 | `DAILY_RETENTION_DAYS == 380` | **FAIL** |
| G-299-3a | 실측 도달 달력일 < `DAILY_RETENTION_DAYS` (커플링) | PASS (불변식) |
| G-299-3b | 실측 도달 + 30cal ≤ retention (마진) | PASS (불변식) |
| G-299-3c | `retained_trading(retention) ≥ target + 30` (정상상태 churn 자유) | PASS (불변식) |
| G-299-7a | `get_recent_daily` 본체 `min(days, 100)` 존재 (+detector self-test) | PASS (불변식) |
| G-299-7b | `KIS_DAILY_CANDLES_MAX = 100` + `fetch_days` cap 표현 존속 | PASS (불변식) |

### `tests/unit/engine/test_cycle299_backfill_target_expansion.py`
| ID | 내용 | Red |
|---|---|---|
| G-299-2 | `_DAILY_LOAD_VCP_BACKFILL_DAYS == 220` | **FAIL** |
| G-299-5 | VCP + count=219 → `backfill(total_days=220)` (하드코딩 220) | **FAIL** |
| G-299-4 | VCP + count = `trading_days_in(retention)` → 재backfill 금지 + days=7 | PASS (불변식) |
| G-299-6 | count == 상수 → strict-`<` False → 증분 (경계) | PASS (불변식) |
| G-299-8 | SAFETY — 매매/구독 hot path 무접촉 + 이웃 상수(100/50) 불변 | PASS (불변식) |
| G-299-9 | 1회 backfill 영업일 부족분 ≤ 10 (전이 유계) | PASS (불변식) |

**"불변식" 가드의 일은 값을 끌어오는 것이 아니라 두 상수 중 하나만 움직인 반쪽 Green 을
붉게 만드는 것이다.** 실측 검증 = §5.

## 5. Red / Green / 반쪽 Green 실측

```
Red (230/120)            8 failed, 9090 passed   ← tests/unit/{db,api,engine,ast}
Green 시뮬 (380/220)     112 passed, 0 failed    ← 영향 10파일, src 즉시 원복 완료
반쪽 (230/220)           G-299-1 · 3a · 3b · 3c · 4 → 5 FAIL  ← 커플링 가드 작동 확인
```

Red 8건 = G-299-1 · G-299-2 · G-299-5 + 의미 전환 5건(§7). 나머지 9,090 전부 통과 =
부수 피해 0.

## 6. 발견 — 1회 backfill 이 target 에 못 닿는다 (팀장 판단 필요)

`fetch_daily_candles_backfill` 의 달력 환산 `int(n*7/5)+10` 은 영업일당 달력일을 **1.40**
으로 가정하는데 실측은 `230/154 = 1.494` 다. target 이 커질수록 과소 도달한다.

- target 120 → 178cal ≈ 119 영업일 → **1 부족**
- target 220 → 318cal ≈ 212 영업일 → **8 부족**

**영구 churn 은 아니다.** 매일 밤 윈도우가 하루씩 미끄러지고 이전 행은 retention(380cal)
안이라 purge 되지 않으므로 `count` 가 하루 1 영업일씩 자란다 → 약 8 영업일 뒤 220 도달 후
증분 전환. 즉 **VCP universe 전량이 8박 동안 3윈도우 backfill 을 도는 전이 비용**이다
(사이클196 은 같은 전이가 1박이었다).

G-299-9 가 부족분을 10 으로 유계 고정한다. 0 으로 만들려면
`int(n*7/5)+10` 을 실측 비율로 고치는 **별개 사이클**이 필요하다 — cycle299 Green 에 섞지 않는다.

## 7. 의미 전환 (intent 보존, 값만 이동)

| 파일 | 전환 | 근거 |
|---|---|---|
| `tests/unit/db/test_cycleM2b_stock_master_daily_pg.py:324~` | 230 → 380 | 재던 것은 "asyncpg 전환이 상수를 흔들지 않았나"이지 값 자체가 아님 |
| `tests/unit/db/test_cycle150_supabase_capacity.py:153~` | 230 → 380 | 계보 150→230→380 을 docstring 에 이어 적음 |
| `tests/unit/db/test_cycle172_retention_and_adapter.py` RET-1 | 230 → 380 (+함수명 `test_ret1_retention_days`) | 사이클172 의 `220+10=230` 은 **영업일과 달력일을 섞어 센 오독**이었음을 docstring 에 명기 |
| `test_cycle196_vcp_backfill_convergence.py` B-1 | 120 → 220 (+함수명 일반화) | 재던 부등식(target ⊂ retention 실보유)은 불변, 값만 이동 |
| 〃 B-2 | count 154 → **254** (+함수명 `..._retained_max_...`) | 재던 것은 "그 시점 retention 의 **보유 가능 최대치**"라는 역할. 154 를 두면 `154<220` 으로 의도가 정반대(backfill 발화)로 뒤집힘 |
| 〃 B-3 | count 119 → 219, `total_days` 120 → 220 (하드코딩 규약 유지) | 재던 것은 **target−1** 이라는 역할 |
| 〃 B-4 docstring | Red/Green 예시값 갱신 | 동적 취득이라 코드 무변경 |
| `test_cycle172_vcp_universe_backfill.py` | 모듈 docstring + dead `_VCP_BACKFILL_THRESHOLD` 주석 | 케이스(count 100/50/230)가 임계 120·220 어느 쪽에서도 같은 분기라 **코드 무변경** |

무변경 확인: `tests/unit/api/test_cycle196_backfill_window_clamp.py`(A-2 가 이미 `total_days=220`
→ 3윈도우·318cal 을 인자로 직접 검증) · `tests/unit/api/test_cycle172_daily_ranged_backfill.py`
(`total_days=220` 명시 전달) · `tests/unit/engine/strategies/test_cycle173_prepare_db_equivalence.py`
(100일 cap — G-299-7b 와 동일 대상, 보강 관계).

## 8. backend-dev 가 건드릴 정확한 위치

1. `src/db/stock_master_daily.py:710` — `DAILY_RETENTION_DAYS = 230` → `380`
   (위 주석 블록 `:700~709` 의 "230달력일 ≈ 154영업일 / VCP backfill target 120 / 220 미사용" 서술도 함께 갱신)
2. `src/engine/scanner.py:2804` — `_DAILY_LOAD_VCP_BACKFILL_DAYS = 120` → `220`
   (`:2802~2803` 주석 + `:3049` 의 "< 220" 주석 + `:3055` 의 "VCP 220일 backfill" 주석 정합)

그 외 `src/` 무접촉. 문서(별도, `/sync-docs` 대상) = `src/db/CLAUDE.md:283` ·
`src/engine/CLAUDE.md:155,156` · `src/api/CLAUDE.md:273`.

## 9. 운영 주의

- 배포 분류 **full** (`src/` 변경) → backend 재시작. 장외 창 준수.
- Green 직후 첫 20:30 적재부터 VCP universe(KOSPI200∪KOSDAQ150) 전량이 **3윈도우** backfill 로
  전환된다(종목당 KIS 호출 2 → 3). 약 8 영업일 전이 후 증분으로 수렴(§6).
- retention 확대로 `stock_master_daily` 행 수가 종목당 154 → 254 (약 1.65배)로 증가한다.

## 10. 작업 중 겪은 함정 (기록)

Red/Green 검증을 위해 `src/` 상수를 잠시 바꿨다가 `git checkout` 으로 원복했는데, 바뀐 값이
**같은 길이**(`120`↔`220`, `230`↔`380`)이고 패치와 원복이 **같은 초 안**에 일어나 타임스탬프
기반 `__pycache__` 가 무효화되지 않았다. 그 결과 `.py` 는 120 인데 import 되는 값은 220 인
상태로 전체 스위트가 한 번 돌아 실패 목록이 뒤집혔다. `find src -name __pycache__ -exec rm -rf`
후 재실행해 정정했다. **src 를 임시로 고쳤다 되돌린 뒤에는 바이트코드 캐시를 지우고 상수를
직접 print 해 확인한다.**
