# cycle239 — 계좌 SOFT Σ상한 게이트 신선도(stale → fail-open) 시정 (cycle233 활성화 선결)

작성: team-leader, 2026-09-02. 사용자 결정(09-02) = "233 준비 = 선결 시정" — 처방 **900s 초과 stale 이면
`is_soft_gated()`=False(fail-open) + WARNING 1회/일**. 3렌즈 진단(lifecycle·consumers·tests) 검토 후 확정.

> **워킹트리 상태 정정**: 착수 컨텍스트의 "cycle238 미커밋 17파일" 은 낡았다 — `4cbea99` 로 **커밋 완료**,
> 트리 클린, origin 대비 1커밋 ahead(미푸시). `src/engine/risk.py` sha 는 3 가드 핀 `b0e1a477…` 과 일치.
> 따라서 이번 사이클은 **핀 재산출 0 · risk.py 무접촉 · push 금지**(커밋도 사용자 지시 대기)만 지키면 된다.
>
> **Docs 단계 재확인(09-02)**: `4cbea99` 는 origin/main 에 **푸시 완료**(ahead 0). cycle239 산출물(워처·테스트 3·스펙·인덱스·문서 5)은 미커밋 — 사용자 지시 대기. §2.4·§4.2·§6·§7 의 R1 이전 산문은 아래 각 위치에 **R1 정정** 주석으로 재정합(§10 참조).

> **8영역 무접촉**(risk.py · order_engine.py · realtime/ · auth/ · api/order.py · session.py · scanner.py ·
> strategy_registry.py) + scheduler.py 무접촉(G-6 `account_risk` 토큰 0 + 라인 상한 가드). src 변경 =
> `account_risk_watcher.py` **단독**(선택: `log_analysis_engine.py` 관측 1줄). `strategy_base.py` ·
> `routes/portfolio.py` 는 소비처로서 **diff 0 기대**(신규 필드가 사본 dict 로 자연 전파).

## 0. 결정 요약 (착수 질문 ①~⑥)

| # | 질문 | 결정 | 근거 |
|---|---|---|---|
| ① | stale 임계 | **모듈 상수 `_GATE_STALE_MAX_SECS = _WATCH_INTERVAL_SECS * 3`** (=900). system_config 편입 금지, 리터럴 900 금지(AST) | `is_soft_gated()` 는 **동기 hot path** — system_config 게터는 전부 async+DB 라 호출 불가(hot path await 금지 규약). 코드베이스 신선도 임계는 예외 없이 모듈 상수(`STALE_FRESHNESS_SECS`·`IMMEDIATE_FRESH_SKIP_HOURS`·`HEARTBEAT_INTERVAL_SECS`), "3×주기" 곱 파생 선례(`SUBSCRIBE_GRACE_SECS`=3×, `RESUBSCRIBE_THROTTLE_SECS`=3×). 900 = 루프 실주기(평가시간+300s) 기준 **연속 2회 완전 결측** — 오탐 방향이 fail-open 이라 안전측 |
| ② | stale 시 반환·노출 | `is_soft_gated()` → **False**(fail-open). `get_gate_state()` 에 `stale`·`age_secs`·`stale_max_secs`·`effective_gated` **4필드 추가**, 기존 `level` 은 **마지막 평가값 그대로 보존**(재작성 금지) | 반환값만 고치면 대시보드가 계속 `level=block` 을 보고해 **행위-관측 괴리**(렌즈 2 HIGH). `level` 을 stale 시 `ok` 로 덮으면 "마지막 평가가 block 이었다" 는 사실이 지워져 운영자가 동결을 식별 못 한다 → 사실(level)과 행위(effective_gated)를 **나란히** 노출 |
| ③ | 로그 마커·레벨·cap | **`[account_risk_gate] released reason=stale …` WARNING**, cap 키 **`gate_stale`** 1회/일(날짜 키 자기 리셋), peek→로그→mark. **F5 "전이 로그는 cap 밖" 의 명시적 예외** | `released` 는 이미 `reason=` 판별자로 2종(정상 INFO / `eval_failure` WARNING)이 확립돼 운영 grep 키 `[account_risk_gate] released` 하나로 "왜 풀렸나" 를 전수 검색한다 — 신규 prefix 는 그 grep 에서 빠진다. WARNING = 감시자 자체 정지라 `eval_failure` 와 동급(D2 LOUD). cap 이 필요한 이유 = 순수 read 안이라 **전이 엣지가 없다**(매 틱 재판정) — 이걸 안 적어두면 후속 리뷰어가 F5 위반으로 오독. `watch_failed` 와 **다른 키**(실패 경로는 evaluated_at 을 갱신하므로 두 사건은 서로 다른 실패) |
| ④ | `evaluated_at` None | **stale 취급 = fail-open** (+ `_gate_active` True 인 비정상 조합이면 WARNING `age_secs=None`) | 정상 경로에선 `_gate_active` False 와 동시라 **fast path 로 도달 자체가 안 됨** — 현행 기본값과 정합. 방어적으로 순서를 `_gate_active` 먼저 → age 로 고정(반대로 짜면 None 파싱 예외 경로가 생김, 렌즈 2/3 지적) |
| ⑤ | 루프 사멸 후 재스폰 부재 | **이번 = 사멸 LOUD 만**(`add_done_callback` — 예외 사망 WARNING / 정상 종료 INFO). **재스폰·평가 타임아웃은 후속 등재**(§8 A·B) | 소비 시점 재스폰은 scheduler 참조가 없고 동기 hot path 에서 태스크 스폰은 부적절. 진짜 동결 경로는 **hang**(done()=False)이라 재스폰으로는 못 잡고 **stale 규칙이 유일한 방어** — 이번 사이클이 그걸 닫는다. 사멸(BaseException)은 `run_once` 의 `except Exception` 밖이라 fail-open 대입을 건너뛰는데, 이 경우도 stale 규칙이 ≤900s 후 흡수. done_callback 은 "Task exception was never retrieved" 무음을 없애는 **0 행위 관측**. 한 사이클 한 엣지(D+1 귀인) 원칙 |
| ⑥ | 야간·정지 상태 stale 소비 | **별도 처리 없음 — 규칙 그대로**. post_nxt LTV(15:40~19:50)는 `_running` True 구간이라 루프 생존 시 정상 감시. 20:10 이후는 틱 소비자 0(`unsubscribe_all` 20:00) → 매매 영향 0, 대시보드만 `stale=true` 로 **정직 표시**(현행은 전날 block 을 live 처럼 보임). `/stop` 후 `_running` False → 루프 자연 종료 → 게이트 동결이지만 ws 도 내려가 소비 0 → `/start` 가 boot 동기 평가로 갱신 | `_reset_daily_state` 는 watcher 무접촉(G-6 봉인)이 설계 — 밤새 `_gate_active` 가 남아도 stale 규칙이 부팅 전 어떤 소비도 fail-open 으로 만든다. 프로세스 재시작은 전역 리셋(안전) |

**domain-consult 불요** — 순수 배관 안전 시정. fail-open 방향·900s 는 사용자 승인 + cycle233 D2 독트린 그대로, 진입·청산 파라미터 0 변경.

## 1. 확증된 원인 (3렌즈 코드 실측)

| 사실 | 근거 |
|---|---|
| `is_soft_gated()` 본문 1줄 `return _gate_active` — `evaluated_at` 미참조. 신선도 개념 자체가 코드에 없음 | `account_risk_watcher.py:84-86` |
| `evaluated_at` 은 **어디서도 읽히지 않는 죽은 필드**(src/tests/frontend grep 4건 전부 자기 쓰기) → 이번이 최초 소비자, 깨질 기존 회귀 0 | `:49 :99 :187 :235` |
| 소비처 = `strategy_base._account_soft_gate_blocked` **단 1곳**(7전략 per-tick 동기 hot path). 바깥 try 가 예외를 False(fail-open)로 흡수하나 흔적은 `logger.debug` 뿐 | `strategy_base.py:547-571` |
| 대시보드 `get_gate_state()` 소비처 = `routes/portfolio.py:110-113` 단 1곳. 테스트 커버리지 **0**. 프론트는 `account_gate` 미소비(blast radius 0 — 동시에 화면으로 동결을 알아챌 경로도 0) | `routes/portfolio.py`, `frontend/src/types/portfolio.ts:20-28` |
| 재스폰 경로 0 — `ensure_watch_loop` 유일 호출자 = `boot_manager.py:399`. `_running` True 인 채 루프만 죽으면 `start()` 가 `:568-570` 에서 즉시 return. `_watch_task` 에 await/done_callback 없음 → 사망 완전 무음 | `account_risk_watcher.py:73-81`, `scheduler.py:568-570` |
| 동결의 최소 실현 경로 = **무기한 hang**: `get_balance()`(전역 세마포어·토큰 락) / `system_config.get_*`(`pg._pool.acquire()` 타임아웃 없음). hang 이면 예외 없음 → fail-open 핸들러 미도달, done()=False → 재스폰 no-op, `_gate_active=True` 영구 | `:136 :170-171`, `api/base.py:490-492`, `db/pg.py:128` |
| 평가 **실패** 경로도 `evaluated_at` 갱신(+fail-open) → stale 규칙의 표적은 오직 "루프가 죽거나 멈춰 평가가 아예 안 도는" 경우 | `:231-235` |
| `_running=False` 지점 3곳(`stop()` :1150 / `start()` finally :1038 / `__init__` :365). cycle146 주석 "graceful = finally 진입 안 함" 은 Python 의미론상 **거짓**(except 안 return 도 finally 실행) — 장중 KIS 5xx 1회에 전면 teardown → run_daily ~60s 재부팅으로 자가치유. scheduler.py 무접촉이라 **관측 사실로만 등재**(§8 D) | `scheduler.py:962-988, 1038` |
| 현행은 `block_pct=None`(다크런치)이라 `_gate_active` 가 구조적으로 True 불가 → 결함은 **완전 잠재**. DB `account_risk_block_pct=6.0` 을 켜는 순간 활성화 = "활성화 선결" 전제가 코드로 확증 | `account_risk_guard.py:59-62`, `system_config.py:178-180` |
| 기존 AST 가드 중 `is_soft_gated` 본문을 고정하는 것은 **없음**(G-1~G-7 전수). 함정 = G-4(파일 전체 문자열 `buy_disabled` 0)·G-2(8영역 `account_risk` 토큰 0) — 새 docstring/주석에 그 단어를 쓰면 즉시 FAIL | `tests/unit/ast/test_cycle233_ast_account_risk.py` |

## 2. 시정 설계

### 2.1 판정식 (`account_risk_watcher.py`)

```python
import time

_GATE_STALE_MAX_SECS = _WATCH_INTERVAL_SECS * 3   # 900 — 연속 2회 결측. 리터럴 금지(AST G-239-1)
_evaluated_mono: Optional[float] = None            # 마지막 평가의 monotonic 스탬프(성공·실패 공통)

def _now_mono() -> float:                          # 테스트 seam (cycle238 `_now_kst` 선례)
    return time.monotonic()

def _gate_age_secs() -> Optional[float]:
    if _evaluated_mono is None:
        return None
    return max(0.0, _now_mono() - _evaluated_mono)

def _is_stale(age: Optional[float]) -> bool:
    return age is None or age > _GATE_STALE_MAX_SECS   # 900.0 정확히 = fresh("초과" 가 stale)

def is_soft_gated() -> bool:
    if not _gate_active:               # ① fast path — 99.9% 케이스에서 시각 계산 0회 (첫 문장 고정, AST)
        return False
    try:
        age = _gate_age_secs()
    except Exception:
        age = None                     # 판정 불가 = stale = fail-open
    if _is_stale(age):
        _emit_stale_release(age)       # ② WARNING 1회/일 — 예외 전부 흡수, 반환값에 영향 0
        return False                   # ③ fail-open — 신규 매수 게이트만 해제
    return True
```

- **read-only**: `is_soft_gated()`/`get_gate_state()` 는 `_gate_active`·`_gate_state`·`_evaluated_mono` 를 **쓰지 않는다**
  (함수 내 `global` 선언 금지, AST G-239-4). 단일 기록자 = `run_account_risk_watch_once` — 두 답을 한 곳에서 낸다.
- **monotonic 단일 소스**: 판정은 `_evaluated_mono` 만 본다. `evaluated_at`(KST ISO)은 **표시용으로 유지**(대시보드·로그),
  판정에 재파싱하지 않는다(hot path 비용 + NTP 점프 취약, 렌즈 1/2 권고). AST G-239-3 이 `fromisoformat`/`strptime`/
  `datetime.now`/`time.time` 를 판정 함수군에서 0건으로 봉인.
- 경계: `age > 900` stale. `age == 900.0` fresh.

### 2.2 `get_gate_state()` — 사실과 행위를 나란히

```python
def get_gate_state() -> dict:
    snap = dict(_gate_state)                 # level·reasons·open_risk_pct·evaluated_at… 기존 키 전부 보존
    try:
        age = _gate_age_secs()
    except Exception:
        age = None
    stale = _is_stale(age)
    snap["age_secs"] = None if age is None else int(age)
    snap["stale"] = stale
    snap["stale_max_secs"] = _GATE_STALE_MAX_SECS
    snap["effective_gated"] = bool(_gate_active and not stale)   # == is_soft_gated() 의 답, 단 로그 미발화
    return snap
```

- `level` **재작성 금지** — stale 이어도 `level=block` 이면 그대로. 대시보드 판독 = `level=block ∧ effective_gated=false ∧ stale=true`
  가 "동결됐다가 fail-open 으로 풀린 상태" 의 서명이다.
- `get_gate_state()` 는 **WARNING 을 발화하지 않는다**(대시보드 폴링이 소비처 cap 을 선소비하면 안 됨 — cycle233 F1 동형).
  로그는 소비 경로(`is_soft_gated`)와 감시자 재개 경로(§2.4)만.
- 미평가 상태(부팅 직후·프로세스 재시작): `age_secs=None, stale=true, effective_gated=false, level=ok` — "아직 평가 없음" 의 정직 표시.
  `stale` 의 의미 = **liveness**("마지막 평가가 900s 안에 없다"), `effective_gated` 의 의미 = **행위**.

### 2.3 관측 — `[account_risk_gate] released reason=stale`

```
[account_risk_gate] released reason=stale age_secs=%s max_secs=%d evaluated_at=%s level=%s
  — 감시 루프 정지/사멸 의심, fail-open(신규 매수 게이트만 해제 · 청산·손절 무관)
```
- 레벨 **WARNING**. cap 키 `"gate_stale"` — 기존 `_peek_emit`/`_mark_emitted` 재사용(날짜 키 자기 리셋 내장, scheduler 훅 미의존).
- 순서 = **peek → 로그 → mark**. 로그가 던지면 cap 미소비(다음 틱 재시도) **이고** 그 틱의 반환값은 여전히 False(관측 실패 ≠ 행위 변화).
- `_emit_stale_release` 전체 try/except — hot path 에서 관측 실패가 게이트 판정을 오염시키지 않는다. `logger` 만(DB write/await 금지).
- **hot path 비용**: `_gate_active` False 면 0. True∧fresh = `_now_mono()` 1회 + 비교. True∧stale = 위 + `_peek_emit`(`datetime.now(KST)` 1회
  + set 조회) — 병리 상태에서만, 소비처가 이미 gated 시 매 틱 `datetime.now(_KST)` 를 부르므로 동급.
- `age_secs=None` 은 ④ 비정상 조합(`_gate_active` True ∧ 스탬프 None)에서만 찍힌다 — 그 자체가 "기록자 계약 위반" 신호.
- ⚠️ 새 문자열·주석에 `buy_disabled` 단어 금지(G-4 파일 전체 substring 검사).

### 2.4 `run_account_risk_watch_once` 연동 — 스탬프 + ~~fresh-aware~~ **원시** `was_active` (R1 정정)

> **R1 정정(§10 g1)** — 아래 코드 블록의 `was_active = is_soft_gated()` 는 **폐기**됐다. 기록자는 **원시 `_gate_active`** 를 읽는다
> (기록자가 fresh-aware 를 부르면 정상 일일 라이프사이클 — 20:10 루프 정상 종료 → 밤새 `_gate_active` 잔존 → 익일 07:55 부팅
> 동기 평가 — 마다 소비자용 `gate_stale` WARNING 이 거짓 발화하고 그날 cap 을 선소비한다). 재개 시 전이 로그는 raw 기준
> (`entered`/`reconfirm`/`released`) 그대로이고, 아래 "재개 자체가 로그로 남는다" 서술은 **소비자 경로 한정**으로 좁혀졌다
> (틱 소비자가 없는 야간 구간의 재개는 기록자 로그 `[account_risk_watch]`/전이 로그로만 남는다). 스탬프·await 0 계약은 불변.

```python
        was_active = is_soft_gated()           # (변경) 원시 _gate_active 대신 fresh-aware — stale 은 '비활성' 취급
        _gate_active = level == "block"
        _evaluated_mono = _now_mono()          # (신규) _gate_active 대입과 같은 동기 블록, 사이 await 0 (AST G-239-5)
        _gate_state = {..., "evaluated_at": datetime.now(KST).isoformat()}   # 기존 그대로
    except Exception as exc:
        was_active = is_soft_gated()           # (변경) 동일
        _gate_active = False
        _evaluated_mono = _now_mono()          # (신규) 실패도 '살아 있음' — 루프 생존 중 연속 실패는 stale 이 아니다
        _gate_state = {"level": "error", ...}
```

- 의미: 루프가 900s+ 멈췄다가 재개해 다시 block 이면 `was_active=False` → **`transition=entered` WARNING(cap 밖)** 이 나간다
  (원시값을 쓰면 `reconfirm`(1회/일 cap)으로 떨어져 "stale 로 풀렸다 → 다시 닫혔다" 의 후반이 **무음** — F5 위반).
  재개 시 ok 면 기존 `released —` INFO 는 안 나가고(이미 stale WARNING 이 해제를 알렸다) 이중 로그 없음.
- `was_active` 읽기 위치는 현행 그대로(대입 **직전**, 시각 라벨·판정 사이 await 0) — 재개 시점의 `is_soft_gated()` 호출이 stale WARNING 을
  1회 발화하므로, **틱 소비자가 없던 구간(야간 등)에서도 재개 자체가 로그로 남는다**.
- 기존 로그 4종의 **서식 byte 불변**(운영 grep 연속성). 성공/실패 경로의 다른 문장 무변경.

### 2.5 루프 사멸 LOUD — `ensure_watch_loop` done_callback (0 행위)

```python
def ensure_watch_loop(scheduler):
    global _watch_task
    if _watch_task is not None and not _watch_task.done():
        return
    _watch_task = asyncio.create_task(watch_loop(scheduler))
    _watch_task.add_done_callback(_on_watch_loop_done)      # (신규)

def _on_watch_loop_done(task) -> None:
    try:
        if task.cancelled():
            logger.info("[account_risk_watch_loop_exit] reason=cancelled"); return   # 프로세스 종료 시 정상
        exc = task.exception()          # 회수 = "Task exception was never retrieved" 무음 제거
        if exc is not None:
            logger.warning("[account_risk_watch_loop_died] %s: %s — 감시 정지. 게이트는 ≤%ds 후 stale fail-open. "
                           "복구 = POST /api/trading/restart", type(exc).__name__, str(exc)[:150], _GATE_STALE_MAX_SECS)
        else:
            logger.info("[account_risk_watch_loop_exit] reason=running_false")       # 매일 20:10 직후 1건 = 정상
    except Exception:
        pass
```
- `watch_loop` 본문 무변경(G-6 구조 가드 보존). BaseException 은 계속 전파(CancelledError 종료 의미론 보존).
- 정상 종료 INFO 가 **매일 1건 자연 발생** = 공짜 liveness 데이터포인트(§7). cap 불요.
- 운영 복구 = `POST /api/trading/restart`(stop→start → `_boot` 동기 평가 + `ensure_watch_loop` 가 done 태스크를 재스폰).
  ⚠️ hang(done()=False) 은 restart 로도 루프가 안 살아난다(boot 동기 평가로 값만 갱신) → §8 A.

### 2.6 `reset_state_for_test()` — `_evaluated_mono = None` 동반 리셋. `_watch_task` 는 기존대로 미접촉.

### 2.7 테스트 결정성 seam

- 시각 축은 **`_now_mono` monkeypatch 단일**: `monkeypatch.setattr(watcher, "_now_mono", lambda: T)`. freezegun 은 이 프로젝트에서
  `time.monotonic` 도 동결한다(cycle187 교훈) — seam 은 항상 이긴다. 날짜 키(cap 리셋) 검증만 `freeze_time` 병행, **동기 함수만** 호출
  (동결 monotonic 아래 실 `asyncio.sleep` 금지).
- 신규 테스트 파일은 `_reset_watcher_state` autouse 픽스처를 **자기 파일에 재정의**(tests/unit/engine/conftest 부재, 상태는 모듈 전역).
- 루트 autouse 2종(`_neutralize_call_auction_gate`, `_pin_pre_market_clock`)은 watcher 무간섭(참조 0). 신규 마커 불요.
- caplog 은 `logger="src.engine.scheduler"`.

## 3. 불변 계약

1. **fail-open 방향 고정** — stale·None·판정 예외 전부 False. 조용히 닫히는(True) 구현은 FAIL.
2. **청산·손절 경로 무관** — 소비처는 `check_buy_signal` 게이트 1곳뿐(구조적). 이번 변경은 그 게이트를 **더 자주 여는** 방향만.
3. **단일 기록자** — `_gate_active`/`_evaluated_mono`/`_gate_state` 쓰기는 `run_account_risk_watch_once` 뿐. read 함수는 `global` 금지.
4. **스탬프 원자성** — `_gate_active` 대입과 `_evaluated_mono` 대입 사이 await 0(양 분기). "새 판정 + 낡은 스탬프" 조합 관측 불가.
5. **기존 로그 서식 byte 불변** — `transition=entered/reconfirm/released/released reason=eval_failure`, `[account_risk_watch]*`.
6. **F5 예외 명시** — `released reason=stale` 만 cap 1회/일(read 경로, 전이 엣지 부재). 다른 전이는 계속 cap 밖.
7. **D1 이원화 불변** — `buy_disabled` 토큰 0(G-4), 8영역 `account_risk` 0(G-2), scheduler 0(G-6), watch_loop 구조(G-6), boot 배선(G-7).
8. **strategy_base 위치 이원화 불변** — G-1(5전략 첫 문장 / momentum·VB pre-BUY) 무접촉.
9. `is_soft_gated()` 첫 문장 = `if not _gate_active: return False` — hot path 비용 상한 계약.

## 4. Red 테스트 목록

### 4.1 `tests/unit/engine/test_cycle239_gate_freshness.py` (신규 — ID 접두 `test_f*_`)

리그: cycle233 파일의 `_fake_scheduler/_fake_strat/_patch_balance/_patch_thresholds` 를 import 재사용(중복 금지). `(현행 FAIL)` 없는 항목은 회귀 가드.

| ID | 시나리오 | 기대 |
|---|---|---|
| F-1 **(현행 FAIL — 핵심)** | `run_once`(block=1.0, 큰 포지션) → `is_soft_gated()` True 확인 → `_now_mono` +901s | `is_soft_gated() is False` |
| F-2 | 같은 설정, +899s / +900.0s / +900.001s | True / True / False (경계 = "초과") |
| F-3 (현행 FAIL) | F-1 상태에서 `is_soft_gated()` 50회 | `[account_risk_gate] released reason=stale` **정확 1회**, `levelname == WARNING`, 메시지에 `age_secs=901` `max_secs=900` `evaluated_at=` `level=block` 포함, 50회 전부 False |
| F-4 (현행 FAIL) cap | (a) `freeze_time` 로 날짜 키 이월 → 재발화 1회 (b) `logger.warning` 이 raise → cap 미소비(다음 호출에서 발화) **이고** 그 호출의 반환값 False (c) `reset_state_for_test()` 후 재발화 | peek→로그→mark + 관측 실패 ≠ 행위 |
| F-5 (현행 FAIL) | `_gate_active=True` 직접 주입 + `_evaluated_mono=None` | False + WARNING `age_secs=None` 1회 |
| F-6 fast path | `_gate_active=False`(미평가 또는 stale 스탬프) + `_now_mono` 를 호출 카운팅 spy 로 교체 → `is_soft_gated()` 100회 | 전부 False, **spy 호출 0**, 로그 0행 |
| F-7 (현행 FAIL) `get_gate_state()` | (a) 미평가: `age_secs None · stale True · effective_gated False · level ok · stale_max_secs 900` (b) fresh block: `stale False · effective_gated True · level block · 0 ≤ age_secs ≤ 1` (c) +901s: `stale True · effective_gated False · level == "block"` **유지** (d) 호출 100회에도 `released reason=stale` 로그 **0행**(대시보드 무발화) (e) 기존 키 집합(`level/reasons/open_risk_pct/evaluated_at/...`) 전부 보존 |
| F-8 (현행 FAIL) 재개 전이 | fresh block → +901s → `run_once` 다시 block | 로그 순서 = `released reason=stale`(WARNING) → `transition=entered`(WARNING, **reconfirm 아님**). 대신 ok 로 재개하면 `released —` INFO **0행**(이중 해제 로그 금지) |
| F-9 스탬프 | `run_once` 성공 직후 `get_gate_state()["age_secs"] <= 1` ∧ `stale False`; `_now_mono` 를 고정값 T 로 두면 `_evaluated_mono == T` | 성공 경로 스탬프 |
| F-10 (현행 FAIL) | `get_balance` raise 로 `run_once` 실패 → `get_gate_state()` | `level error ∧ stale False ∧ age_secs ≤ 1`(살아 있는 실패는 stale 아님) |
| F-11 | `reset_state_for_test()` | `_evaluated_mono is None` + F-7(a) 상태 |
| F-12 (현행 FAIL) 사멸 LOUD | `watch_loop` 를 (a) `RuntimeError` 던지는 코루틴 (b) 즉시 정상 반환 (c) 스폰 후 cancel 로 각각 교체 → `ensure_watch_loop` → 완료 대기 | (a) `[account_risk_watch_loop_died] RuntimeError` WARNING + `restart` 안내 포함 (b) `[account_risk_watch_loop_exit] reason=running_false` INFO (c) `reason=cancelled` INFO. (a) 에서 "Task exception was never retrieved" 미발생(`pytest.warns` 없음/`filterwarnings=error` 통과) |
| F-13 소비처 통합 | 실 `DonchianSwingStrategy` 인스턴스 + 실 `is_soft_gated`(monkeypatch 없음): fresh block → `_account_soft_gate_blocked("A") is True`; +901s → False | strategy_base **무변경**으로 전파됨 실증 |
| F-14 기존 회귀 | `test_cycle233_watcher_gate.py` 3클래스 + `test_cycle233_account_risk_guard.py` + AST G-1~G-7 | 전부 그대로 PASS(R6 는 평가 직후 단언, R7 은 monkeypatch 면역, G-6 watch_loop 무변경) |

### 4.2 `tests/unit/ast/test_cycle239_ast_gate_freshness.py` (신규 — cycle233 AST 파일은 봉인 기록으로 무접촉)

| ID | 검사 | 뮤테이션 표적 |
|---|---|---|
| G-239-1 | `_GATE_STALE_MAX_SECS` 의 값 노드 = `BinOp(Name("_WATCH_INTERVAL_SECS"), Mult, Constant(3))`(좌우 무관) ∧ import 후 `== 900 == 3 * _WATCH_INTERVAL_SECS` | 리터럴 900 / system_config 이관 |
| G-239-2 | `is_soft_gated` 첫 문장 = `If(UnaryOp(Not, Name _gate_active))` 본문 `Return(Constant False)` 단독 | fast path 제거·순서 반전 |
| G-239-3 | `is_soft_gated`·`_gate_age_secs`·`_is_stale`·`get_gate_state` 본문에 `fromisoformat`/`strptime`/`datetime.now`/`time.time` 호출 0 ∧ `Await` 0 ∧ `_gate_age_secs` 안에 `_now_mono` 호출 존재 | ISO 재파싱·벽시계 판정 |
| G-239-4 | 위 4함수 안에 `Global` 문 0 (read-only 계약) | read 경로 상태 변조 |
| G-239-5 | `run_account_risk_watch_once` try-body 와 handler-body **각각**: `_gate_active` Assign 과 `_evaluated_mono` Assign 존재, 두 문장 사이(포함) 구간에 `Await` 0, `was_active` Assign 의 값이 ~~`Call(is_soft_gated)`~~ → **R1: 원시 `Name _gate_active`**(`Call(is_soft_gated)` 금지 — `test_g239_5b_was_active_is_raw_gate_active`) | 스탬프 누락(실패 경로 포함)·await 삽입·fresh-aware was_active(R1 반전) |
| G-239-6 | `ensure_watch_loop` 안에 `add_done_callback` Call 존재 ∧ `_on_watch_loop_done` 정의 존재 | 콜백 제거 |
| G-239-7 | 8영역 diff 0 = 기존 `test_g223_10/g223f_9/cycle226` 가드 재사용(핀 무변경). Green 후 `git diff HEAD --name-only ∪ untracked` ⊆ §5 허용 목록 | 범위 이탈 |

### 4.3 `tests/unit/routes/test_cycle239_portfolio_gate_state.py` (신규 — 라우트 커버리지 0 봉합)

`test_cycleH_portfolio_route.py` 의 `_install_fakes` 리그 재사용, 라우트 함수 **직접 await**(TestClient 금지 — 사이클 127).
`snapshot["account_gate"]` 에 `stale/age_secs/stale_max_secs/effective_gated` 4키 존재 + 미평가 시 `effective_gated False`.
`get_gate_state` 가 raise 해도 라우트 200(기존 graceful 분기 보존).

## 5. Green 범위

- `src/engine/account_risk_watcher.py` **단독**: `import time` · `_GATE_STALE_MAX_SECS` · `_evaluated_mono` · `_now_mono` ·
  `_gate_age_secs` · `_is_stale` · `_emit_stale_release` · `is_soft_gated` 재구성 · `get_gate_state` 4키 · `run_once` 양 분기
  (`was_active`·스탬프) · `ensure_watch_loop` 콜백 + `_on_watch_loop_done` · `reset_state_for_test` · 모듈 docstring 로그 목록에
  `released reason=stale`(1회/일, F5 예외)·`loop_died`/`loop_exit` 추가.
- (선택, 권고) `src/engine/log_analysis_engine.py::_build_portfolio_risk_snapshot` 의 기존 over_cap try 블록에
  `snapshot["account_gate"] = get_gate_state()` 1줄 — 20:10 리포트에 **매일 결정적 liveness 표본**(`age_secs`) 확보. 관측 전용·graceful.
  채택 시 회귀 1건(리포트 metrics 에 키 존재) 동반.
- 무변경 기대: `strategy_base.py` · `routes/portfolio.py` · 7전략 · 8영역 · scheduler.py · pyproject(신규 마커 불요).
- 인덱스: `python tools/test_impact/build_index.py`(test_index.yaml 은 4cbea99 에 커밋됨 — 재생성 diff 는 이번 사이클 몫).
- 전체 스위트는 Docs 단계 1회(`python -m pytest -q -p no:cacheprovider`), 표적 실행은 경로 지정.

## 6. 적대 검증 (tester) 뮤테이션 체크리스트

| # | 변조 | 검출 기대 |
|---|---|---|
| m1 | `is_soft_gated` 를 `return _gate_active` 로 환원 | F-1/F-3/F-5/F-8/F-13 FAIL |
| m2 | `>` → `>=` (900.0 을 stale 로) | F-2 FAIL |
| m3 | `_GATE_STALE_MAX_SECS = 900` 리터럴 | G-239-1 FAIL |
| m4 | mark-before-log | F-4(b) FAIL |
| m5 | fast path 제거(age 를 `_gate_active` 검사보다 먼저 계산) | F-6 spy FAIL + G-239-2 FAIL |
| m6 | None 을 fresh 로 취급 | F-5 FAIL |
| m7 | `get_gate_state` 가 stale 시 `level="ok"` 로 재작성 | F-7(c) FAIL |
| m8 | `is_soft_gated` 가 stale 시 `_gate_active=False` 대입(read 경로 쓰기) | G-239-4 FAIL |
| m9 | ~~원시값 환원~~ **R1 반전**: `run_once` 의 `was_active = is_soft_gated()`(fresh-aware) 로 변조 | F-8(레코더 경로 `reason=stale` 0건 단언) + F-8b + G-239-5b FAIL |
| m10 | 실패 경로에서 `_evaluated_mono` 미갱신 | F-10 FAIL |
| m11 | `add_done_callback` 제거 | F-12 FAIL + G-239-6 FAIL |
| m12 | `_gate_active` 대입과 `_evaluated_mono` 대입 사이 `await asyncio.sleep(0)` 삽입 | G-239-5 FAIL |
| m13 | 판정을 `datetime.fromisoformat(evaluated_at)` 벽시계로 교체 | G-239-3 FAIL(행위 테스트는 seam 덕에 생존할 수 있음 — 구조 가드가 표적) |
| m14 | `get_gate_state()` 에서 `_emit_stale_release` 호출 | F-7(d) FAIL |

추가 렌즈: hot path 비용(`_gate_active` False 경로 시각 호출 0 실증 = F-6, True∧fresh 경로 ≤ 수백 ns) · 3,000틱 차분 —
fresh 상태에서 `is_soft_gated()` 결과가 현행과 **동일**(행위 변경은 age>900 구간에만) · 기존 로그 4종 서식 byte 비교 ·
`git diff HEAD --name-only` ⊆ 허용 목록 · G-4/G-2 문자열 함정 재확인(`buy_disabled` 0).

## 7. D+1 판독 채널 + 활성화 게이트

| 채널 | 정상 서명 | 이상 서명 → 해석 |
|---|---|---|
| `[account_risk_watch_loop_exit] reason=running_false` | 매일 20:10 직후 **1건** | 부재 = 루프가 그 전에 죽었거나(→ `loop_died` 동반) **hang**(동반 없음 → §8 A 트리거) |
| `[account_risk_gate] released reason=stale` | **0건**(R1 후 정상 라이프사이클에서 실제로 0 — 기록자는 이 채널을 안 탄다) | ≥1 = 감시 정지 중 block 이 **소비자 경로**(전략 on_tick)에서 소비됐다(활성화 후에만 가능). `loop_died` 유무로 사멸/hang 분리 |
| `[account_risk_watch_loop_died]` | 0건 | 예외명이 곧 원인. 복구 = `/api/trading/restart` |
| `GET /api/portfolio/risk` → `account_gate` | 장중 `age_secs ≤ ~360`, `stale=false` | `age_secs > 900` = 루프 정지 실측. `level=block ∧ effective_gated=false` = fail-open 작동 중 |
| (선택) 20:10 `portfolio_risk_snapshot.account_gate.age_secs` | ≤ 600 | 하루 끝 liveness 결정 표본 |
| `[account_risk_gate] released reason=stale` 뒤 `transition=entered|reconfirm` | — | R1 후 짝은 **소비자 경로가 stale 을 관측한 경우에만** 생긴다(기록자는 raw 기준이라 재개 시 `reconfirm` 1회/일 cap 으로 떨어질 수 있음 — 무음 아님: stale WARNING 이 이미 해제를 알렸다). 순서가 뒤집혀 있으면(entered 가 먼저) 기록자 재개가 소비보다 앞선 정상 경로 |

**활성화 게이트(DB `account_risk_block_pct=6.0`)** = cycle239 배포 후 **2 영업일** 연속 `reason=stale` 0 ∧ `loop_exit running_false` 매일 1 ∧
장중 `age_secs` 표본 ≤ 600 — **AND** cycle233 의 2주 관측 창(~09-12) 만료. 두 조건 충족 시 사용자 결정으로 DB 한 줄.
⚠️ 활성화 D+1 첫 관측 항목 = `transition=entered` 발화 시 `effective_gated` 가 대시보드에서 true 로 보이는지(행위-관측 정합).

## 8. 후속 등재 (이번 사이클 밖)

- **A. 평가 타임아웃(hang 근본 시정)** — `run_once` 본체를 `asyncio.wait_for(…, timeout=_WATCH_INTERVAL_SECS)` 로 감싸 hang →
  `TimeoutError` → 기존 fail-open + 스탬프 갱신 + `watch_failed` WARNING, **루프 생존**. 검토 필수 = cancel 시 KIS `_semaphore`/토큰 락/
  `pg._pool.acquire()` 의 cancel 안전성(`async with` 는 해제되나 토큰 발급 중 cancel 의 상태 잔존 여부). 8영역 무접촉. **우선순위 1** —
  stale 규칙은 ≤900s 거짓 차단을 허용하는 완화책이지 hang 자체를 못 푼다.
- **B. 재스폰 경로** — `ensure_watch_loop` 두 번째 호출 지점. scheduler.py 는 G-6 토큰 0 + 라인 상한이라 불가 → 후보 ①
  `uptime_monitor.heartbeat_loop`(60s, scheduler ref 보유, 비8영역)에서 idempotent 호출 ② done_callback 내 `_scheduler_ref` 약참조로
  일 cap 3 재스폰. hang 엔 무력(done()=False) → A 선행.
- **C. `uptime_monitor` 동형 결함** — 하트비트 루프도 무감시 태스크(자기 종료 + boot 단일 스폰). 동일 done_callback 적용.
- **D. scheduler.py:962-985 cycle146 주석 거짓** — `except` 안 `return` 도 `finally` 를 탄다. 장중 KIS 5xx 1회 → 전면 teardown → run_daily
  60s 재부팅(자가치유되나 1~5분 tick blind — cycle234 `[tick_blind_boot]` 가 부팅마다 잡으므로 실측 가능). scheduler 소관, 별도 결정.
- **E. `pg._pool.acquire()` 타임아웃 미지정**(`db/pg.py:128`, max_size=10) — hang 의 공통 뿌리, 전역 사안.
- **F. 프론트 `PortfolioRiskCard`** — `account_gate` 미표시. `stale`/`effective_gated` 배지 + `age_secs`. `types/portfolio.ts` 동기 의무.
- **G. `[account_risk_watch]` 요약이 1회/일 cap** 이라 장중 liveness 를 못 보인다 — 20:10 리포트 `account_gate` 병기(§5 선택)로 대체하거나
  평가 카운터 `evaluations_today` 노출.

## 9. 문서 동기화 (Docs 단계)

- 루트 `CLAUDE.md` 하네스 표: 상단 1행 추가 + 최고령 1행(2026-08-18 비중 단위) 제거, 15행 유지, 한 줄.
- `docs/HARNESS_CHANGELOG.md` 최상단 append(현 최상단 = 2026-09-02 cycle238).
- `src/engine/CLAUDE.md:37` account_risk_watcher 문단: `is_soft_gated` 신선도 규칙(900s=3×주기, fail-open, `released reason=stale` 1회/일 —
  F5 명시 예외) + `get_gate_state` 4키 + done_callback + 단일 기록자 계약 + 운영 복구 `restart`.
- `_workspace/00_URGENT_WORKLIST.md:193` G3′ 행: "활성화 = DB 한 줄" 앞에 **cycle239 선결 완료 + §7 활성화 게이트** 명시. §8 A~G 후속 등재.
- `_workspace/00_leader_trading_rules.md`: 파라미터 변경 0 이라 무변경(리스크 규칙 절에 게이트 신선도 한 줄만 있으면 추가).
- 커밋·푸시는 사용자 지시 대기(현재 origin 대비 1커밋 ahead 상태 유지).

## 10. 적대 검증 확증/시정 (cycle239-R1, 2026-09-02, 착수 직후 회귀 라운드)

착수 직후 반박자 3렌즈 + tester 가 독립 수렴한 결함 10건(중복 서술 포함, 실질 4건)을
회귀 테스트 먼저(Red 확인) → 최소 시정 순으로 닫았다. 8영역 무접촉·`risk.py` 등
cycle238 산출물 무접촉 유지, 커밋 없음.

| 확증 결함(실질) | 등급 | 처방(리드 g1~g6) | 시정 |
|---|---|---|---|
| 기록자(`run_account_risk_watch_once`) 의 `was_active = is_soft_gated()`(fresh-aware) 가 소비자용 `gate_stale` WARNING/cap 을 선소비 — 정상 일일 라이프사이클(20:10 `_running=False`→루프 정상 종료→밤새 `_gate_active` 잔존→익일 07:55 부팅)마다 거짓 '사멸 의심' WARNING 발화 | HIGH/MEDIUM | g1: 기록자는 원시 `_gate_active` 를 읽는다(소비자 채널 선소비 금지) | `was_active = is_soft_gated()` → `was_active = _gate_active`(양 분기). 기록자는 `is_soft_gated()`/`_emit_stale_release` 를 더 이상 호출하지 않는다 |
| 위 거짓 발화가 그날의 `gate_stale` cap(1회/일)을 선소비해, 같은 날 장중 진짜 hang 이 나도 소비자 경로 stale WARNING 이 무음 — D2 'fail-open+LOUD' 의 LOUD 절반이 실사건에서만 빠짐 | HIGH | g1 로 자동 종결(기록자가 cap 을 아예 안 건드림) + g3: `gate_stale` 이 `gate_block`/`watch_failed` 와 공유되지 않음을 회귀로 고정 | 신규 F-8c(`test_f8c_stale_cap_when_recorder_reconfirms_same_day_then_independent`) — 같은 날 `gate_block` cap 소비 후에도 `gate_stale` 은 별도 1회 발화(x3 뮤테이션으로 검출 실증) |
| `released reason=stale` 메시지가 "감시 루프 정지/사멸 의심" 을 단정 — 실제로는 정상 일일 라이프사이클의 첫 부팅일 확률이 높다 | MEDIUM | g2: '사멸' 단정 대신 사실만 남기고, g1 만으로 아침 거짓 발화가 닫히는지 실증 | 메시지를 "최근 평가 갱신 없음(임계 초과) … 전일 마감 후 첫 부팅 직후 1건은 정상 — 장중 지속·반복 시 감시 루프 점검"으로 완화. F-3(필드 substring 단언)은 문구 무관 필드만 검사해 영향 없음. F-8(재설계)로 g1 만으로 아침 거짓 발화가 실제 닫힘을 실증(레코더 경로에서 `reason=stale` 0건) |
| `is_soft_gated()` 판정 예외 흡수(`except Exception: age=None`)를 `return True`(fail-closed)로 변조해도 검출하는 테스트 부재(뮤테이션 m6 이스케이프) — F-5 는 `_evaluated_mono=None` 직접 주입이라 이 경로를 타지 않음 | HIGH | g4: `_now_mono` raise 주입으로 실제 예외 전파 경로를 별도 실증 | 신규 F-5b(`test_f5b_gate_when_age_computation_raises_then_fail_open_not_closed`) — `_now_mono` raise + `_evaluated_mono` not-None(예외가 `_gate_age_secs` 에서 propagate) → False 단언. m6 변조 시 FAIL 실증 |
| AST 가드 G-239-7 이 **전 트리** `git diff HEAD --name-only ∪ ls-files --others` 를 cycle239 4파일+3prefix 로만 허용 — 선례(g223_10/g223f_9/cycle222a3)와 달리 경로 한정이 없어, 커밋 후 클린 트리에서만 통과하고 이후 어떤 사이클(동시 활성 cycle238 포함)이든 목록 밖 파일을 하나만 건드리면 거짓 FAIL | HIGH | g5: 삭제 또는 `account_risk_watcher.py` 단일 파일 내용 검사로 축소 | `test_g239_7_change_scope_within_allowlist` + `_ALLOWED_EXACT`/`_ALLOWED_PREFIX`/`_git` 헬퍼 **삭제**(`subprocess` import 도 동반 제거). 8영역 diff-zero 는 기존 경로 한정 가드가 담당한다는 점을 파일 상단 주석으로 명시 |

g6(`log_analysis_engine.py` 정합 확인) — §5 의 "선택" 항목(20:10 리포트에 `account_gate` 병기)은 이번 라운드에서도 **미채택**(git diff 로 무접촉 확인) — 확인만 하고 skip.

### 연쇄 수정 (기존 회귀 재설계, 신규 아님)

- `test_g239_5b_was_active_is_fresh_aware` → `test_g239_5b_was_active_is_raw_gate_active` — g1 결정으로 원시값 단언으로 반전(AST).
- F-8(`test_f8_resume_when_still_block_then_entered_not_reconfirm`) → `test_f8_recorder_when_silent_gap_then_no_stale_warning_raw_transition` — "entered 강제" 기대를 "stale WARNING 0건 + raw 기준 reconfirm" 으로 재설계.
- F-8b(`test_f8b_resume_when_ok_then_no_duplicate_release_log`) → `test_f8b_recorder_when_silent_gap_resolves_ok_then_single_release_log` — "이중 로그 금지" 전제(기록자가 stale 를 먼저 관측한다는 가정)가 사라져 "release 정보 로그 1건 + stale 미동반" 으로 재설계.

### 검증

- `python -m pytest -q -p no:cacheprovider tests/unit/engine/test_cycle239_gate_freshness.py tests/unit/engine/test_cycle233_watcher_gate.py tests/unit/engine/test_cycle233_account_risk_guard.py tests/unit/ast/test_cycle233_ast_account_risk.py tests/unit/ast/test_cycle239_ast_gate_freshness.py tests/unit/routes/test_cycle239_portfolio_gate_state.py` → **79 passed**(cycle233 세 파일 전부 무접촉·PASS 유지).
- 뮤테이션 실증(수작업, `__pycache__` 정리 후 재검증 — 초기 1회는 mtime 충돌로 stale bytecode 오탐, 캐시 삭제 후 재현해 결과 확정): m6(`except Exception: return True`) → F-5b FAIL(원복 시 PASS). x3(`gate_stale`→`gate_block` 키 공유) → F-8c FAIL(원복 시 PASS).
- `python -m pytest -q -p no:cacheprovider tests/unit/engine/ tests/unit/ast/ tests/unit/routes/` → **4,138 passed, 3 skipped, 172 xfailed, 5 xpassed**, 회귀 0.
- 8영역(+`strategy_base.py`/`routes/portfolio.py`/`scheduler.py`) `git diff` 0. 변경 파일 = `src/engine/account_risk_watcher.py`(코드+docstring) · `tests/unit/engine/test_cycle239_gate_freshness.py` · `tests/unit/ast/test_cycle239_ast_gate_freshness.py` · `_workspace/test_index.yaml`(재생성) · 본 스펙 파일. 커밋 없음(사용자 지시 대기 유지).

### 잔여(이번 라운드 밖)

- ~~§7 D+1 판독표는 g1 시정으로 "정상 0건" 서술이 실제로 참이 되었으나(레코더 경로가 stale 채널을 안 탐), §2.4 서술("재개 자체가 로그로 남는다")은 소비자 경로 한정으로 좁혀졌다 — 다음 문서 동기화 라운드에서 §2.4/§7 문구를 g1 이후 상태로 재정합할 것~~ → **§11 Docs 단계에서 재정합 완료**(§2.4 R1 정정 블록·§4.2 G-239-5·§6 m9·§7 2행 + `run_account_risk_watch_once` docstring 의 잔존 "fresh-aware" 서술 정정).

## 11. Docs 단계 최종 상태 (team-leader, 2026-09-02)

- **표적** 6파일(cycle239 3 + cycle233 3) **79 PASS** · 신규 회귀 **36**(engine 25 · ast 8 · routes 3) · 전체 백엔드 **5,940 PASS**(10 skipped · 328 xfailed · 13 xpassed, 133.8s)****.
- **변경 파일(미커밋)**: `src/engine/account_risk_watcher.py`(코드+docstring) · `tests/unit/engine/test_cycle239_gate_freshness.py` · `tests/unit/ast/test_cycle239_ast_gate_freshness.py` · `tests/unit/routes/test_cycle239_portfolio_gate_state.py` · `_workspace/test_index.yaml`(재생성) · 본 스펙 · `CLAUDE.md`(하네스 표 상단 1행 + cycle223 행 제거, 15행) · `docs/HARNESS_CHANGELOG.md`(상세 append) · `src/engine/CLAUDE.md`(account_risk_watcher 문단 신선도 계약) · `_workspace/00_URGENT_WORKLIST.md`(G3′ 행 선결 완료 + 활성화 잔여 조건 + 후속 A~G 등재).
- **8영역 + `scheduler.py` + `strategy_base.py` + `routes/portfolio.py` diff 0**, sha 핀 재산출 0. `_workspace/00_leader_trading_rules.md` 무변경(파라미터 변경 0, 계좌 리스크 절 부재).
- **활성화(DB `account_risk_block_pct=6.0`) 전 남은 선결 = 코드 0.** 남은 것은 §7 관측 게이트(배포 후 2영업일 + cycle233 2주 창 만료)와 사용자 결정뿐. 후속 A(평가 타임아웃)는 활성화의 선결이 아니라 **hang 지속 시간 단축**(900s 거짓 차단 창 → 300s)의 개선 과제.
- 커밋·푸시 사용자 지시 대기.
