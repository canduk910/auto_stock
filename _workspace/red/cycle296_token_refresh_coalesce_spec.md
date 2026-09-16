# cycle296 — 보조 토큰 재발급: `issue()` in-flight 합류 + T=20:45 + 관측 보강 명세

> **작성 2026-09-17 04:5x KST · 이 문서는 명세다. 코드 변경 0.**
> 직전 배포 = cycle295(`5421a90`, 09-17 01:03 Deploy 성공). 병행 갈래 = cycle297(`llm_features.py`·
> 전략 7파일·`src/db/**`) — 소스 파일은 겹치지 않는다. **테스트 파일은 겹친다**(§8-1).

**표기 규약** — `[실측]` = 이 리포에서 파일을 열거나 명령을 실행해 확인한 값. `[실측·조사]` = 09-16 조사
(브리프)가 EC2 로그에서 읽은 값으로, 이 명세 작성 중 재확인하지 않았다. `[추론]` = 코드 구조에서
끌어냈으나 실행·로그로 확인하지 못한 것. `[미실측]` = 답이 없는 것.

---

## §1 왜

### 1-1 사용자 결정 (2026-09-17, 원문)

> "결정 1 진행"

= ① `src/auth/token.py` `issue()` **매니저 단위 in-flight 합류 승인(8영역 `src/auth/**`)**
② 예정 시각은 두 후보(15:30~16:00 · 20:45~21:00) 중 **20:45 확정** ③ 관측 보강 함께.

### 1-2 증상 `[실측·조사]`

설계 = 활성 보조 계정 7개 × 1회 = **7건/일**. 실제 "토큰 발급 완료(label=quote-*)" 행수:
09-15 **21건**, 09-16 **14건**. 라벨마다 균일(3건씩 / 2건씩) — 무작위 장애가 아니라 **구조적 중복**.
403 · rate limit · ERROR **0건**, 모든 발급이 61초 이상 간격 → KIS 계정 위험은 없다. 손해 =
낭비 + 계정당 61~122초의 토큰 공백.

### 1-3 원인 두 갈래

**(A) 자연 문턱이 항상 강제보다 먼저 온다.** `[실측]` `token.py:219-222`
```python
def _is_valid(self) -> bool:
    if not self.access_token or not self.token_expired:
        return False
    return datetime.now() < self.token_expired - timedelta(minutes=10)
```
19:00 강제 앵커 → 다음 날 문턱 18:50. 보조 계정은 종일 시세 REST 라 그 창에 `get_token()` 이
들어온다(`base.py:781` `token = await manager.get_token()`). `[실측·조사]` 09-16 ISA 문턱
18:51:25 → 실발화 18:55:03, 7/7 산술 일치. 즉 **"문턱 T−10 이 정규장 밖" 이라는 cycle270-C 의
제약은 필요조건이었지 충분조건이 아니었다** — 보조 풀은 장외에도 REST 를 쓴다(5분 주기 stale
가드·15:40 애프터 등).

**(B) `revoke()` 가 여는 61초 공백.** `[실측]` `quote_token_refresh.py:180-198` 이 라벨마다
`await manager.revoke()`(성공 시 `access_token=""`, `token.py:177`) → `await manager.issue()` 를
부른다. `issue()`(`token.py:125-162`)는 전역 락을 쥔 채 `_ISSUE_GAP_SECS=61.0` 만큼 잔다. 그 사이
REST 가 `get_token()` → `_is_valid()` False → `issue()` → **락 대기** → 61초 뒤 KIS 를 한 번 더
친다(유효 토큰이 있으면 같은 토큰·같은 만료를 돌려준다 — cycle270 실측). 로그 `[실측·조사]`:
`19:02:03 폐기(gold) → 19:03:04 발급(gold, 만료 19:03:04) → 19:04:05 발급(gold, 만료 19:03:04 동일)`.

**근본 = `asyncio.Lock` 은 직렬화만 하고 합류시키지 않는다.** 같은 매니저의 토큰을 원하는
두 코루틴이 각각 KIS 를 친다. `_GLOBAL_ISSUE_LOCK`(`token.py:50`)은 모듈 전역 = 8매니저(메인 1 +
보조 7) 공유이고 이건 **맞다**(KIS 분당 1건은 전역 한도) — 문제는 락의 단위가 아니라 **합류 부재**다.

### 1-4 오늘(09-17) 예측 `[추론]`

09-16 앵커 19:0x → 오늘 문턱 18:50~18:59 전부 19:00 이전 → 코드가 그대로면 14~21건.

### 1-5 왜 20:45 인가 `[실측·조사]`

| 후보 | T−10 창의 보조 풀 REST | 체인(7분, 밀리면 09-15 실측 14분 40초) 뒤에 오는 것 |
|---|---|---|
| 15:45 | 15:2x 17행 → 15:3x 21 → 15:4x 28 → 15:5x 28 (15:40 NXT 애프터 + stale 가드로 **증가**) | 16:00 KRX 애프터 개장 — 체인이 밀리면 실시간 체결 초반에 토큰 공백 |
| **20:45** | 20:2x~21:0x **14행 균일**(5분 주기 로그뿐), 20:00~21:30 `quote_pool` REST 마커 **0건** | 21:30 정산까지 35분 여유 |

일봉 적재 20:30:00~20:31:50 종료(메인 계정) → 20:35~20:45 조용. 원 설계 제약(`quote_token_refresh.py:40-46`)
(a) T·T−10 장중 밖 ✅ (b) 7분 체인이 REST 작업과 안 겹침 ✅ (c) 루프 생존 창(정산 21:30 전) ✅.

🔴 `[실측]` `quote_token_refresh.py:52-55` 의 결론 — "20:00 이후는 루프 수명 구조를 바꾸지 않는 한
불가능하다(20:00~정산 은 자문·유니버스·정산의 REST 집중 창이라 더 나쁘다)" — 는 **정산 20:10 시절
잔재**다. 같은 docstring 44행이 "정산(21:30 — cycle283 D3, 종전 20:10)" 으로 갱신돼 있으면서 결론은
안 고쳤다. T 만 옮기고 이 문장을 두면 다음 사람이 읽고 되돌린다 → **함께 정정**(§2-②).

---

## §2 무엇을 바꾸나 — 파일별

| # | 파일 | 현재 | 변경 | 8영역 |
|---|---|---|---|---|
| ① | `src/auth/token.py` (375L) | `issue()` 125-162행 — 전역 락 + 61s gap 만 | 매니저 단위 in-flight Future 합류 + 상태 스냅샷 규칙 + 실패·취소 시 대기자 해제 + `issue_history` 공개 deque | **안 — 승인됨** |
| ② | `src/engine/quote_token_refresh.py` (244L) | `TIME_QUOTE_TOKEN_REFRESH = time(19, 0)` (133행) · docstring 38-60행 "왜 19:00 인가" | `time(20, 45)` + 절 제목·본문·이력 주석(130-132행) 재작성 + 판독법(115-119행) 갱신 | 밖 |
| ③ | `src/engine/quote_token_refresh.py` | `_SUMMARY_KEYS = ("accounts","issued","failed")` (140행) · 요약 1행 | `+ ("elapsed_s","window_issues_total")` · `refresh_quote_tokens_once` 가 체인 시작 monotonic 을 잡고 종료 시 두 값 산출 | 밖 |
| 테스트 | `tests/unit/engine/test_cycle269_quote_token_refresh.py` `test_c9`(280-342)·`test_c10`(344-) · `summary ==` 등식 6곳(117·174·188·200·213·246행) | 19:00 전제 | 20:45 재핀 + 비충돌 목록 실측 재작성 + 등식 5키 | — |
| 테스트 | `tests/unit/engine/test_cycle270_quote_token_revoke_then_issue.py` `test_c5b`·`test_c5c`(343-372) · 등식 3곳(250·287·314행) | "요약 3필드 불변 — 바꾸려면 별도 사이클" | **이 사이클이 그 별도 사이클** — 5키로 재핀 | — |
| 테스트 | `tests/unit/ast/test_cycle269_quote_token_refresh_wiring.py::test_g269_6` · `test_cycle270_ast_revoke_then_issue.py::G-270-2/3/4` | `_is_valid`·`revoke` 세그먼트 핀 / leaf 심볼 격리 | **값 불변**(§3-1 이 두 메서드를 안 건드린다). docstring 의 "token.py 무접촉" 문구만 "cycle296 이 `issue()` 만 바꿨다" 로 정직화 | — |
| 테스트 | `src/auth/token.py` **파일 전체 sha 핀 10곳** `[실측]` — `test_cycle274_ast_llm_gate.py:581` · `276_ast_order_hook.py:358` · `278_ast_catalog_guards.py:214` · `282_ast_purity.py:404` · `286_ast_scope.py:98` · `287_ast_scope.py:113` · `290_ast_scope.py:128` · `291_ast_scope.py:97` · `293_ast_channel_resolver.py:155` · `294_ast_stage3.py:225` (전부 `049341c7286b57a0…`) | | 그 **한 줄씩만** 갱신(§8-1 충돌 규약) | — |
| 신규 테스트 | `tests/unit/auth/test_cycle296_token_issue_coalesce.py` · `tests/unit/ast/test_cycle296_ast_token_coalesce.py` · `test_cycle269…` 에 leaf 관측 케이스 추가 | | §5 | — |

**건드리지 않는 것** — `scheduler.py`(3,726L, 배선 `:740` 그대로 · 주석 "매일 15:45" 는 낡았지만
무접촉 규칙이 우선 → §6 에 기록) · `src/api/base.py` · `src/db/kis_quote_accounts.py` ·
`TokenManager.get_token/revoke/_is_valid/_save_cache/_load_cache`(byte 동일) · `_GLOBAL_ISSUE_LOCK` ·
`_ISSUE_GAP_SECS` · `tests/unit/ast/test_cycle287_ast_scope.py::_SRC_TREE_DIGEST`(Final 단계).

---

## §3 설계

### 3-1 ① `issue()` in-flight 합류

**불변식**
- I-1 한 매니저에 대해 **동시에 진행 중인 KIS `/oauth2/tokenP` POST 는 최대 1개**. 진행 중이면 뒤에
  온 호출자는 그 결과를 기다리고 **KIS 를 치지 않는다**.
- I-2 전역 61초 직렬화는 그대로다 — 합류는 락 **바깥**의 판단이고, 리더만 락에 들어간다.
  다른 라벨끼리는 여전히 합류하지 않고 직렬화된다(양성 대조군 N5).
- I-3 대기자는 영영 매달리지 않는다 — 리더가 성공·실패·취소 어느 길로 끝나도 Future 는 `finally` 에서
  반드시 결정된다. 2차 방어로 합류 타임아웃.
- I-4 **합류는 "진행 중"에만** 한다. 끝난 Future 에는 합류하지 않는다 — 순차 `issue()` 두 번은 여전히
  KIS 두 번(cycle270 의 revoke→issue 가 이 성질에 기댄다).
- I-5 **줄이는 방향뿐**. 리더 1 + 대기자 N 의 KIS 호출 = 1 ≤ 현행 N+1.

**상태** — `TokenManager.__init__` 에 두 필드:
```python
self._inflight: "asyncio.Future[None] | None" = None   # 진행 중 발급
self._inflight_token_snapshot: str = ""                   # 리더가 진입할 때의 access_token
self.issue_history: collections.deque[float] = deque(maxlen=64)  # 공개 — ③ 이 읽는다 (monotonic)
```

**`issue()` 골격** (`[추론]` — 구현 시 이 순서를 지킨다, 특히 "첫 `await` 앞" 조건)
```python
async def issue(self) -> None:
    # 1) 합류 판단 — 첫 await 앞에서 동기적으로 (asyncio 단일 스레드 = 체크·설정이 원자적)
    fut = self._inflight
    if fut is not None and not fut.done() and self._inflight_token_snapshot == self.access_token:
        await asyncio.wait_for(asyncio.shield(fut), timeout=_ISSUE_JOIN_TIMEOUT_SECS)
        return
    # 2) 리더 등록
    loop = asyncio.get_running_loop()
    fut = loop.create_future()
    self._inflight = fut
    self._inflight_token_snapshot = self.access_token
    try:
        async with _get_global_issue_lock():
            ... (현행 125-162행 본문 byte 동일: gap sleep → POST → 필드 대입 → _save_cache → _LAST_ISSUE_AT)
            self.issue_history.append(time.monotonic())
        fut.set_result(None)
    except asyncio.CancelledError:
        if not fut.done():
            fut.set_exception(RuntimeError("token issue aborted: leader cancelled"))
        raise
    except BaseException as exc:
        if not fut.done():
            fut.set_exception(exc)
        raise
    finally:
        if self._inflight is fut:
            self._inflight = None
```

**왜 스냅샷 비교인가** — 합류 조건에 `self._inflight_token_snapshot == self.access_token` 을 넣는 이유는
`revoke()` 와의 경합 때문이다 `[추론]`:
- 리더가 옛 토큰(스냅샷 = old)으로 진입해 락·sleep 중인데 leaf 가 `revoke()` 로 `access_token=""` 을
  만들고 `issue()` 를 부르면, 스냅샷(old) ≠ 현재("") 라 **합류하지 않고** 직렬화된다 → 강제 발급이
  실제로 한 번 더 나가 앵커가 옮겨진다(cycle270 계약 보존). 합류시켰다면 리더의 POST 가 revoke 보다
  먼저 끝난 경우 그 라벨은 **폐기된 토큰을 들고** 앵커도 그대로 남는다(자가 치유는 다음 REST 의
  EGW00123 → `base.py:920 manager.issue()` 로 1회 더 돈 뒤에야 — 낭비 + 하루 드리프트).
- (B) 의 공백에서는 leaf 리더가 스냅샷 "" 로 진입하고 REST 대기자도 현재 "" 를 보므로 합류한다 ✅.
- 자연 문턱 경합에서는 리더·대기자 모두 old 를 보므로 합류한다 ✅.
- 비용 = 문자열 비교 1회. 기각한 대안 = `revoke()` 가 세대 카운터를 올리는 방식 — `revoke` 세그먼트가
  G-270-3 으로 핀돼 있고 의미론을 바꿀 이유가 없다.

**실패·취소 의미론** — 대기자는 리더와 **같은 예외**를 받는다(`None` 반환 아님). `get_token()` 은
`await self.issue()` 뒤 `self.access_token` 을 돌려주므로 실패를 삼키면 대기자가 빈 문자열 토큰으로
REST 를 쏜다(무음 401). 리더 **취소**는 `RuntimeError` 로 바꿔 전달한다 — `CancelledError` 를 그대로
심으면 대기자 자신이 취소된 것처럼 보여 `_request` 의 재시도 루프가 통째로 끊긴다. 대기자가 예외를
받으면 `base.py` 의 기존 재시도가 다음 attempt 에서 `get_token()` → 새 리더가 된다.

**합류 타임아웃** — `_ISSUE_JOIN_TIMEOUT_SECS = 600.0` `[추론]`. 상한 근거 = 리더의 최악 대기 =
다른 7매니저의 락 점유(각 61s sleep + 10s POST) + 자기 61s + 10s ≈ 570s. 초과 시 `TimeoutError`
전파(스스로 리더가 되지 않는다 — 폭주 방향 금지). `shield` 필수: `wait_for` 가 공유 Future 를 취소하면
다른 대기자까지 같이 죽는다(N10). 이 값은 리스크 다이얼이 아니라 교착 방지 상한이라 `system_config`
편입 없음.

**기각한 대안**
- (가) 락을 매니저 단위로 분리 — KIS 한도가 전역이라 403 재발(사이클 20 이 고친 결함의 재현). 기각.
- (나) `revoke()` 를 없애고 `issue()` 만 — cycle270 실측(같은 토큰·같은 만료 반환)으로 앵커가 안 옮겨진다. 기각.
- (다) `_is_valid` 마진 10분 축소 — 만료 직전 매매용 REST 401 위험 + 문턱은 어차피 어딘가에 온다(A 를 못 고친다). 기각(g269_6 핀 유지).
- (라) leaf 에서만 처리(예: 강제 발급 중 플래그로 REST 를 막기) — 합류 부재는 `issue()` 의 성질이라 자연 문턱(A) 중복까지는 못 잡는다. 또 G-270-2 가 leaf 의 token 내부 접근을 막는다. 기각.
- (마) `asyncio.Task` 를 in-flight 로 두고 `_inflight_price`(`condition.py:136`) 패턴 답습 — 리더가 호출자 태스크 자신이어야 `CancelledError` 가 자연 전파되고 락 점유 주체가 명확하다. Future 로 충분. 기각.

### 3-2 ② T = 20:45

- `TIME_QUOTE_TOKEN_REFRESH = time(20, 45)`. 이력 주석에 `→ 20:45(cycle296, 2026-09-17)` 추가.
- docstring 절 제목 "왜 19:00 인가" → "왜 20:45 인가 (cycle296)" 로 바꾸고 다음을 담는다:
  1. 19:00 이 틀린 이유 = **문턱 T−10 이 정규장 밖이어도 보조 풀은 종일 REST 를 쓰므로 자연 재발급이
     항상 먼저 온다**(09-16 7/7 산술 일치). 그래서 T−10 창은 "장외" 가 아니라 **"보조 풀 REST 가
     없는 창"** 이어야 한다.
  2. 실측 표(§1-5) — 20:2x~21:0x 보조 풀 REST 14행 균일 · `quote_pool` 마커 0건 · 일봉 적재 20:31:50 종료.
  3. 52-55행 결론 문장 **삭제 후 재작성**: "정산은 21:30(cycle283 D3)이므로 20:00 이후도 루프 안이다.
     20:00 자문·20:00:05 유니버스·20:05 metrics·20:30 일봉(≈20:32 종료) 뒤 **20:35~20:55 가 비어 있고**,
     21:30 정산까지 35분 여유가 있다(체인이 09-15 처럼 14분 40초로 밀려도 21:00 종료)."
  4. **첫 실행일 예외**(§7-2) 를 판독법에 명기.
- `test_c9` 재작성: (i) `T > 15:30` (ii) `T−10 > 15:30` (iii) `T < TIME_SETTLEMENT` (iv) **신규**
  `T + 15분 ≤ TIME_SETTLEMENT`(체인 지연 14분 40초 실측 마진) (v) **신규** `T − 10분 ≥
  TIME_STOCK_MASTER_DAILY_LOAD + 5분`(문턱이 일봉 적재 종료 뒤 — 19:00 을 되돌리는 뮤테이션을 이 줄이
  잡는다) (vi) 기존 `collisions` 전수 스캔 창 = **[20:35, 20:53]** — `[실측]` `vars(scheduler)` 의
  `TIME_*` 중 이 창 안은 없다(20:30 일봉 · 21:30 정산 · 20:05 metrics · 20:00 자문/컷오프/애프터 종료 ·
  20:00:05 유니버스 · 19:50 매수중단 전부 밖) (vii) 기존 `abs(load − T) ≥ 10` → 15분 ✅.
  **삭제**: `(T + 8분) < TIME_RECOMMENDATION` — 이 단언은 "T 가 20:00 앞" 을 강제하는 프록시였고,
  그 의도("REST 집중 창 침범 금지")는 (vi) 가 정확히 잰다.
- `test_c10` 은 값만 바뀌어도 초록(20:45 < 21:30) — 변경 없음.
- 자매 가드 `[실측]` `test_cycle283_evening_window.py::test_c283_5d`(창을 T 에서 계산 → 자동 편입, docstring
  의 "[18:50, 19:08]" 만 정직화) · `test_cycle273_daily_load_1810.py::test_g273f_3`(20:30 ∉ [20:35, 20:53] ✅
  변경 없음) · `tests/unit/routes/test_cycle285_market_ops_route.py`(`scheduled_at` 을 상수에서 읽음 ·
  `_no_evidence_status` 가 `now < scheduled` 면 `scheduled` 라 20:25/20:35 고정 시각 케이스에서 표시가
  `unknown`→`scheduled` 로 바뀔 수 있다 — `[추론]` 그 케이스들은 다른 행만 단언하지만 **실행으로 확인**).

### 3-3 ③ 관측 보강

- `refresh_quote_tokens_once` 진입 직후 `t0 = time.monotonic()`(leaf 에 `import time` 추가 — G-270-4 가
  금지하는 것은 `asyncio` import 와 `sleep` 호출뿐 `[실측]` `test_cycle270_ast_revoke_then_issue.py:176-204`).
- 루프에서 성공적으로 얻은 `manager` 를 리스트에 모은다. 종료 시:
  - `elapsed_s = int(time.monotonic() - t0)`
  - `window_issues_total = Σ_manager count(ts in getattr(manager, "issue_history", ()) if ts >= t0 - 900)`
    — **−15분** 은 첫날 문턱(T−10)의 자연 재발급과 20:35 문턱 창을 둘 다 덮기 위함. `getattr` 폴백은
    테스트 더미(`_DummyMgr`·`_KisLikeMgr`)와 미래의 매니저 교체에 never-raise.
  - 산출 실패는 `_trace_failure("window_count")` 로 흔적만 남기고 두 값 0 — 관측이 체인을 막지 않는다.
- `_SUMMARY_KEYS = ("accounts", "issued", "failed", "elapsed_s", "window_issues_total")`,
  `_SUMMARY_LOG_FORMAT = MARKER + " accounts=%d issued=%d failed=%d elapsed_s=%d window_issues_total=%d"`.
  `run_periodic_task_loop._build_log_args` 가 `%d` 에 `summary.get(key, 0)` 을 넣으므로 정수여야 한다 `[실측]`.
  계정 목록 조회 실패 경로의 조기 return dict 도 5키 0 으로.
- G-270-2 유지 — `src.auth.token` 에서 가져오는 이름은 여전히 `get_token_manager` 하나. `issue_history` 는
  `_FORBIDDEN_TOKEN_SYMBOLS` 에 없고 매니저의 **공개 속성**이다(`[실측]` 금지 목록은 `_` 접두 내부 심볼 +
  `reset_global_issue_state`). 새 공개 함수 import 로 세지 않는다(그러면 `imported_from_token ==
  ["get_token_manager"]` 등식이 깨져 가드를 완화해야 한다 — 기각).
- 왜 monotonic 인가 — `token.py` 는 naive `datetime.now()`(컨테이너 TZ=KST)를 쓰고 leaf 는 KST aware 를
  쓸 수 있어 섞이면 9시간이 어긋난다. 창 산술만 필요하므로 tz 개념이 없는 monotonic 이 맞다.

---

## §4 잃는 것·위험

| # | 위험 | 등급 | 완화 |
|---|---|---|---|
| R1 | 리더 실패가 대기자 N 개에 **동시에** 전파 → 그 순간의 REST N 건이 한꺼번에 재시도 | LOW | 현행도 N 건이 각각 61초 뒤 실패하던 것을 즉시 실패로 당길 뿐. `_request` 재시도 루프가 흡수 |
| R2 | 리더가 KIS 응답 대기 중 매달리면 대기자도 같이 매달림 | LOW | httpx `timeout=10` 이 리더를 묶고, 합류 타임아웃 600s 가 2차 |
| R3 | `shield` 누락 시 한 대기자의 타임아웃이 공유 Future 를 취소 → 전원 실패 | MED | N10 회귀 가드 |
| R4 | 스냅샷 비교 누락 시 revoke→issue 강제 발급이 자연 리더에 합류해 **앵커가 안 옮겨짐**(cycle270 회귀) | MED | N7 회귀 가드 |
| R5 | `_inflight` 를 `finally` 에서 안 지우면 끝난 Future 에 영구 합류 → **이후 모든 issue() 가 KIS 를 안 침** = 만료 뒤 전 REST 401 | HIGH | N6(순차 두 번 = POST 2) + N3(실패 뒤 새 리더) |
| R6 | 20:35 문턱과 20:30 일봉 적재의 간격이 5분 — 적재가 보조 풀을 쓰거나 20:35 를 넘기면 자연 재발급이 문턱에 걸림 | LOW | ③ `window_issues_total` 이 그날 바로 드러낸다(>7). 적재가 메인 계정을 쓴다는 것은 `[실측·조사]` — §8-3 |
| R7 | 배포 = `src/**` 변경이라 **full 모드 = backend 재시작**. 보유 중 장중 push 금지(D6)·20:00~21:35 금지(D8) | — | 장외 창(15:30~19:55 · 21:35~익일 07:45)에만. 재시작 시 `.token_cache` 볼륨이 토큰을 보존하므로 발급 폭주 없음 |
| R8 | 첫 실행일 14건이 "결함" 으로 오독 | — | §7-2 명기 |
| R9 | 메인 매니저(`label=None`, 매매용)도 같은 `issue()` 를 탄다 — 합류 로직이 메인에도 적용 | LOW | 메인은 부팅 시 `_preissue_all_tokens` 와 EGW00123 경로에서만 `issue()` 가 돌고 동시성이 사실상 0. 적용되더라도 방향은 "KIS 호출 감소" 뿐. 매매 헤더·주문 경로 무접촉 |
| R10 | 매매 행위 영향 | **0** | 보조 계정은 주문에 쓰이지 않는다. `risk/order_engine/session/scanner/strategy_registry/api/order/realtime/**`·전략 7파일 diff 0 |

롤백 = 1커밋 revert(파라미터·DB 없음). 되돌리면 T=19:00·중복 발급으로 복귀할 뿐 계정 위험은 없다.

---

## §5 회귀 가드 + 뮤테이션 대조표

### 5-1 신규 `tests/unit/auth/test_cycle296_token_issue_coalesce.py` (기존 `test_token_global_serialization.py` 픽스처·`_MonotonicClock`·`_Client` 재사용)

| ID | 케이스 | 단언 |
|---|---|---|
| N1 | 같은 매니저 `gather(get_token() ×5)`, 토큰 없음 | POST **1회** · 5개 반환값 동일 · `sleep` 0회(`_LAST_ISSUE_AT=0`) |
| N2 | (B) 재현 — 테스트가 전역 락을 먼저 쥐고, 리더 `issue()` 기동(락 대기), 그 뒤 `get_token()` 기동, 락 해제 | POST 1회 · 두 코루틴 모두 정상 종료 |
| N3 | 리더 POST 가 `httpx.HTTPStatusError` | 리더·대기자 **모두** 같은 예외 · `_inflight is None` · 다음 `issue()` 는 새 리더(POST 누계 2) |
| N4 | 리더 태스크 `cancel()` | 대기자는 `RuntimeError`(CancelledError 아님) · `_inflight is None` |
| N5 | 라벨 `m1`·`m2` gather | POST 2회 · `sleep(61.0)` 1회 (= 기존 test_E 와 동일, 양성 대조군) |
| N6 | 같은 매니저 순차 `issue()` 두 번 | POST 2회 (끝난 Future 에 합류 없음) |
| N7 | 리더(스냅샷 old) 락 대기 중 `access_token=""` 로 바꾼 뒤 `issue()` | 합류하지 않음 → POST 2회 |
| N8 | `issue_history` | 리더 성공마다 1개 append · 대기자는 append 0 · 실패 시 append 0 · `maxlen=64` |
| N9 | `get_token()` 캐시 hit | `issue()` 미호출·`_inflight` 미생성 (기존 test_D 보존) |
| N10 | 대기자 A 가 타임아웃(모의 `wait_for`), 대기자 B 는 계속 대기 | A `TimeoutError` · B 는 리더 결과 수신(공유 Future 미취소) |
| N11 | 기존 `test_token_global_serialization.py` A~E | **무변경 통과** |

### 5-2 신규 `tests/unit/ast/test_cycle296_ast_token_coalesce.py`

| ID | 내용 |
|---|---|
| A1 | `issue()` 안에 `async with _get_global_issue_lock()` 존재 + `_ISSUE_GAP_SECS == 61.0` + `_GLOBAL_ISSUE_LOCK` 모듈 레벨 유지 |
| A2 | `issue()` 첫 `Await` 노드 **앞**에 `self._inflight` 읽기·쓰기가 있다(합류 판단이 첫 await 앞 = 원자성) |
| A3 | `issue()` 에 `Try` + `finally` 가 있고 그 안에서 `_inflight` 를 `None` 으로 대입 |
| A4 | 합류 경로에 `asyncio.shield` 호출 존재 |
| A5 | `get_token`·`revoke`·`_is_valid` 세그먼트 sha **불변**(`e35d4974…`·`0d454ce0…`·`d58f356b…`) `[실측]` — 새 `issue()` 세그먼트 sha 는 구현 뒤 핀 |
| A6 | leaf: `_SUMMARY_KEYS` 5키 + 포맷 문자열 일치 · `import time` 허용, `asyncio` import 0(G-270-4 유지) · `src.auth.token` import 는 `get_token_manager` 뿐(G-270-2 유지) |

### 5-3 leaf 테스트 추가 (`test_cycle269_quote_token_refresh.py` 또는 신규 `test_cycle296_quote_token_refresh_observe.py`)

| ID | 케이스 | 단언 |
|---|---|---|
| L1 | 더미 매니저 `issue_history=[t0-1000, t0-800, t0-100, t0+10]` (monotonic 모의) | `window_issues_total == 3`(−900 경계 포함, −1000 제외) |
| L2 | `issue_history` 속성 없는 더미 | 0 · 예외 없음 · `issued` 는 정상 |
| L3 | `elapsed_s` | 정수 · monotonic 모의로 `== 420` |
| L4 | 계정 목록 조회 실패 | 5키 전부 0 |
| L5 | 등식 9곳(cycle269 6 + cycle270 3) | 5키 dict 로 갱신(`elapsed_s`·`window_issues_total` 은 더미에서 0) |
| L6 | `test_c9` 재작성(§3-2) · `test_c5b/c5c` 5키 재핀 |

### 5-4 뮤테이션 대조표 (구현 뒤 전수 실행, ESCAPED 0 이어야 한다)

| M | 뮤테이션 | 잡는 가드 |
|---|---|---|
| M1 | 합류 분기 제거 | N1(POST 5)·N2 |
| M2 | `finally` 의 `_inflight = None` 제거 | N6(POST 1)·N3 |
| M3 | `_inflight` 설정을 락 획득 **뒤**로 이동 | N2(POST 2)·A2 |
| M4 | 실패 시 `fut.set_result(None)` (예외 삼킴) | N3(대기자 예외 없음) |
| M5 | 스냅샷 비교 제거 | N7(POST 1) |
| M6 | 취소를 `CancelledError` 그대로 전파 | N4 |
| M7 | `shield` 제거 | N10(B 도 취소)·A4 |
| M8 | 대기자도 `issue_history.append` | N8 |
| M9 | `T = time(19, 0)` 복귀 | c9 (v) `T−10 ≥ 20:35` |
| M10 | `T = time(21, 0)` | c9 (iv) `T+15 ≤ 21:30` … 21:15 ✅ 통과 → **(iv) 만으로는 못 잡는다**. `T = time(21, 20)` 은 잡는다. 21:00 은 유효한 후보였으므로 ESCAPE 가 아니라 허용 범위 — 명세는 20:45 를 **값 자체로도 핀**한다(`assert T == time(20, 45)`, 사용자 확정값) |
| M11 | 창 `−900` → `0` | L1(== 1) |
| M12 | `_SUMMARY_KEYS` 3키로 복귀 | A6·c5b |
| M13 | 락 매니저 단위로 분리 | N5(sleep 0회) |
| M14 | `_ISSUE_GAP_SECS` 변경 | A1·기존 test_B |

### 5-5 실행 규약 (절대 제약 5·6)
세 덩어리 분할 실행(`tests/unit/ast/` · `tests/unit/engine/` · 나머지) · caplog 는 WARNING 이상 + `[quote_token_refresh]` prefix ·
시각 고정은 freezegun · 마지막에 `TZ=UTC` 재실행 · `test_cycle287_ast_scope.py::test_s1b` 붉음은 Final 전까지 예상 상태.

---

## §6 문서 동기화 목록 (메인 세션 `/sync-docs` — 이 갈래는 손대지 않는다)

| 문서 | 위치 | 내용 |
|---|---|---|
| `src/engine/CLAUDE.md` | 59행 `quote_token_refresh.py` 절 | "현재 19:00, cycle270-C" → 20:45(cycle296) + 원인 (A)/(B) 두 줄 + 요약 5키 |
| `src/engine/CLAUDE.md` | 883행 시각표 | `19:00` → `20:45` |
| 루트 `CLAUDE.md` | 하네스 이력 표 | cycle296 1행 추가 + 최하단 1행 제거 |
| `docs/HARNESS_CHANGELOG.md` | append | verbatim |
| `_workspace/00_URGENT_WORKLIST.md` | 1321행 부근 cycle269/270 항목 | "cycle270-C 19:00" 이력에 "→ cycle296 20:45" · 09-15 21건/09-16 14건 원인·종결 |
| `src/auth/` | CLAUDE.md 없음 | `token.py` 모듈 docstring 에 cycle296 절 추가(코드 안 docstring = 이 갈래가 한다) |
| `src/engine/scheduler.py` | `:740`·`:1037`·`:1164`·`:1200` 주석 "매일 15:45 KST" | **낡은 주석, 무접촉 규칙으로 방치** — 워크리스트에 "다음 scheduler 접촉 사이클이 20:45 로 고친다" 1행 |
| `src/routes/CLAUDE.md` | 120행 | 시각 리터럴 없음 — 변경 불요 `[실측]` |
| 테스트 docstring | `test_cycle285_ast_market_ops.py:103` "19:00" · `test_cycle283_evening_window.py::test_c283_5d` "[18:50, 19:08]" · `test_cycle273_daily_load_1810.py:37` | 이 갈래가 정직화(테스트 파일) |

---

## §7 D+1 판독 기준

기준 grep (EC2 `system_logs` 또는 컨테이너 로그):
```
A = "[quote_token_refresh] accounts="            # 요약 1행
B = "토큰 발급 완료(label=quote"                   # 보조 발급 전건
C = "[token] 분당 한도 대기"                       # 락 대기 행
```

### 7-1 정상 상태(둘째 날부터)
- A: `accounts=7 issued=7 failed=0 elapsed_s≈420~450 window_issues_total=7`, 발화 시각 20:52~20:53.
- B: 하루 **7건**, 전부 20:45~20:53. 20:35~20:45 창에 0건(문턱 창이 조용하다는 증거).
- C: 20:45~20:53 에 6~7건(체인 자체의 정상 대기). 그 밖 시간대 0건.
- 각 라벨 `expired=` 가 다음 날 20:4x~20:5x.

### 7-2 첫 실행일 예외 (결함 아님)
- 새 T 가 처음 발화하는 날, 전날 앵커(19:0x)의 자연 문턱 18:50~18:59 에 자연 재발급 7건이 **먼저** 나고
  20:45 강제 7건이 또 난다 → **B = 14건**. 단 합류 덕에 18:5x 도 7건이지 14건이 아니다.
- A 의 `window_issues_total` 은 창이 [20:30, 종료] 라 **7** 이다(18:5x 는 창 밖) — 브리프의 "첫날
  `window_issues_total=14` 허용" 은 창 정의와 맞지 않아 **B=14 · A.window=7** 로 정정한다(§8-2).
- 어느 날이 첫날인가 = 배포 시각에 달렸다. 09-17 07:45 전 배포 → 첫날 09-17(18:5x 7 + 20:45 7). 09-17
  21:35 이후 배포 → 09-17 은 구 코드 19:00 발화(≈14~21건, 예측대로) · 첫날 = 09-18.

### 7-3 실패 서명
| 관측 | 뜻 |
|---|---|
| B > 7 (둘째 날 이후) 또는 `window_issues_total > issued` | 합류 미작동 또는 20:35 문턱 창에 REST 가 있다(R6). C 의 시각 분포로 어느 쪽인지 가른다 |
| `window_issues_total < issued` | `issue_history` 배관 결손(리더가 append 안 함) |
| `elapsed_s > 900` | 체인이 15분 넘게 밀림 — 락 경합 주체 조사 |
| A 없음 | 루프 미발화 — `scheduled at=20:45` 카나리아 유무로 배선/수명 판별 |
| `failed > 0` | 계정별 `강제 재발급 실패` 행 원문 |
| 대기자 `TimeoutError`(`[quote_pool]` 재시도 급증) | R2 — 리더 매달림 |
| 18:5x 자연 재발급이 **둘째 날에도** 남음 | 앵커가 안 옮겨짐(R4) — `revoked=` 필드와 스냅샷 규칙 점검 |

---

## §8 열린 질문

1. **테스트 파일 충돌** — 파일 전체 sha 핀 10곳(§2)은 같은 dict 에 cycle297 대상(전략 7파일·`llm_features.py`·
   `src/db/**`)도 들어 있다 `[실측]`(예: `test_cycle278_ast_catalog_guards.py` 24건). 두 갈래가 같은 파일을
   편집한다. 규약 제안: 각 갈래는 **자기 파일의 한 줄만** 바꾸고, Final 이 병합 뒤 전체 재실행. 메인 세션 확인 필요.
2. **첫날 `window_issues_total`** — 브리프 ③ 은 첫날 14 허용이라 했으나 창 [체인 시작−15분, 종료] 로는 7 이다.
   창을 "그날 00:00 이후" 로 넓히면 14 가 되지만 그러면 지표가 "체인 주변" 이 아니라 "하루 총량" 이 되어
   R6(20:35 문턱 창) 신호가 흐려진다. **창 −15분 유지 + 판독 기준을 B=14 로 정정**을 제안한다.
3. **일봉 적재 20:30 이 메인 계정만 쓰는가** `[실측·조사]` — 참이면 20:35 문턱은 조용하다. 거짓이거나 적재가
   길어져 20:35 를 넘기면 그날 `window_issues_total` 이 8+ 로 나온다. 첫 정상일(둘째 날) 판독에서 확정.
4. **합류 타임아웃 600s** `[추론]` — 포함 여부. I-3 의 1차 보장은 `finally` 결정이라 구조적으로 교착이 없고,
   타임아웃은 리더의 HTTP 가 httpx timeout 을 뚫고 매달리는 경우만 잡는다. 빼면 코드가 10줄 준다. 기본 제안 = 포함.
5. **메인 매니저에도 합류 적용**(R9) — 제외하려면 `label is None` 분기가 생겨 코드가 두 갈래가 된다.
   방향이 "KIS 호출 감소" 뿐이므로 **동일 적용**을 제안한다.
6. **`issue_history` maxlen 64** — 하루 정상 7건 + 첫날 14 + 재시도 여유. 30일 보관이 필요하면 별도 영속화가
   맞지 관측 deque 를 키울 일이 아니다.
7. 배포 창 — 지금 04:5x KST. 07:45 부팅 전 배포면 오늘이 첫날이고, 못 넣으면 오늘 19:00 에 구 코드가 14~21건을
   한 번 더 낸다(§1-4). 어느 쪽이든 계정 위험은 없다 — 사용자 판단.

---

## §9 Red 로그 (tdd-engineer, 2026-09-17 · 구현 0)

`src/` diff **0** 상태에서 실패 테스트만 작성했다. 프로토타입 검증(§9-4)은 실행 후 원복했다.

### 9-1 신규 파일 3

| 파일 | 케이스 | Red | Green(=지금 통과, 양성 대조군) |
|---|---|---|---|
| `tests/unit/auth/test_cycle296_token_issue_coalesce.py` | N1~N10 (10) | 8 | 2 = **N5**(다른 라벨은 합류 안 함 + `sleep(61.0)` 1회) · **N7**(revoke 후 스냅샷 불일치 → 합류 금지) |
| `tests/unit/ast/test_cycle296_ast_token_coalesce.py` | A1·A2·A3·A4·A5×3·A5b·A6·A6b (10) | 5 | 5 = **A1**(락·gap·발급 본체 생존) · **A5×3**(`get_token`/`revoke`/`_is_valid` 세그먼트 sha 불변) · **A6b**(G-270-2/4 격리 계약) |
| `tests/unit/engine/test_cycle296_quote_token_refresh_observe.py` | L0~L5 (7) | 7 | — (전부 Red, 양성 대조군은 각 케이스 **안**에 있다: `issued` 정상·발급 순서·`accounts` 등) |

### 9-2 기존 테스트 재핀 (구 계약과 정면 충돌 → 함께 Red)

- `test_cycle269_quote_token_refresh.py` — `summary ==` 등식 **6곳**을 `_core(summary) == …` 로(관측 2키는 성질로 검사 후 분리) · `test_c8` 두 단언(`time(19,0)`→`time(20,45)`, 3키→5키) · **`test_c9` 전면 재작성**(§3-2 (i)~(vii), `(T+8) < TIME_RECOMMENDATION` 삭제, 신규 (iv)(v) 가 M9 를 잡는다, `vars(scheduler)` TIME_* ≥20개 양성 대조군 추가). → **8 Red**
- `test_cycle270_quote_token_revoke_then_issue.py` — 등식 **3곳** + `test_c5b`(의미 전환: "3필드 불변" → "5필드, `revoked` 는 여전히 제외") + `test_c5c`. → **5 Red**
- `test_cycle285_market_ops_route.py` — `test_g8` 의 `quote_token_refresh` 기대값을 **T 에서 계산**(20:30 이 T 앞이면 `scheduled`→휴장 치환 `holiday`). 신규 `test_g8a` 가 "예정 시각 경계에서 `scheduled`↔`unknown` 이 실제로 갈린다"를 잰다. **T 무관하게 통과**(19:00·20:45 양쪽 실행 확인).
- docstring·주석만 정직화(행위 0) — `test_cycle285_ast_market_ops.py:103` · `test_cycle283_evening_window.py::test_c283_5d` · `test_cycle273_daily_load_1810.py`(모듈 docstring + `test_g273f_3`) · `test_scheduler_stop_zombie_tasks.py:273`.

### 9-3 실행 명령과 결과 (`src/` 무변경)

```
python -m pytest tests/unit/auth/test_cycle296_token_issue_coalesce.py -q -p no:randomly
  → 8 failed, 2 passed
python -m pytest tests/unit/ast/test_cycle296_ast_token_coalesce.py -q -p no:randomly
  → 5 failed, 5 passed
python -m pytest tests/unit/engine/test_cycle296_quote_token_refresh_observe.py -q -p no:randomly
  → 7 failed
python -m pytest tests/unit/engine/test_cycle269_quote_token_refresh.py -q -p no:randomly
  → 8 failed, 3 passed
python -m pytest tests/unit/engine/test_cycle270_quote_token_revoke_then_issue.py -q -p no:randomly
  → 5 failed, 6 passed
TZ=UTC … --log-level=DEBUG (위 5파일 + 자매 4파일)  → 33 failed, 149 passed  # KST 와 동일 집합
tests/unit/auth 3회 반복                            → 매회 8 failed, 7 passed  # flaky 0
```

세 덩어리 전수(`src/` 무변경, cycle297 제외):
`tests/unit/ast` → cycle296 밖 실패는 `test_cycle287_ast_scope.py::test_s1b` **하나뿐**(Final 전까지 예상 상태) ·
`tests/unit/engine` → cycle269/270 재핀분 **13건**뿐 · 나머지 → **0건**.

### 9-4 프로토타입 검증 — 이 Red 는 실제로 Green 이 된다 (실행 후 원복)

§3-1 골격 + §3-3 관측을 그대로 구현해 한 번 돌리고 되돌렸다.

```
tests/unit/auth                                        → 29 passed   # N1~N10 + 기존 A~E(N11)
cycle296 engine/ast + 재핀 cycle269/270               → 39 passed
```

⇒ **불가능한 Red 는 없다.** 특히 N1(POST 5→1) · N4(취소→RuntimeError) · N10(shield) ·
L1(창 경계 9100 포함/9000 제외) · L3(`elapsed_s==420`) 전부 골격대로 통과했다.

### 9-5 Green 이 함께 손대야 하는 가드 (프로토타입 실행으로 **실측**)

`src/auth/token.py` 는 8영역이라 파일 sha 핀이 널려 있다. 프로토타입 상태에서 붉어진 것:

1. **파일 전체 sha 핀 10곳** — `test_cycle274_ast_llm_gate.py:581` · `276_ast_order_hook.py:358` ·
   `278_ast_catalog_guards.py:214` · `282_ast_purity.py:404` · `286_ast_scope.py:98` ·
   `287_ast_scope.py:113` · `290_ast_scope.py:128` · `291_ast_scope.py:97` ·
   `293_ast_channel_resolver.py:155` · `294_ast_stage3.py:225` (현재 값 전부 `049341c7286b57a0…`).
   ⚠️ **10곳을 같은 값으로 동시에** 옮긴다(한 곳만 넣으면 나머지가 "코드를 되돌려라" 로 오도한다).
2. **8영역 한시 pin dict 4곳** — `test_cycle223g3_ast_guard_sees_staged.py::test_g3_9b` 가 요구한다:
   `test_cycle222a3_ast_followup_fixes.py` · `test_cycle223_ast_donchian_exit_fix.py` ·
   `test_cycle223f_ast_manual_apply_safeguard.py` · `tests/unit/engine/strategies/test_cycle226_zero_breakout_defense.py`.
   **커밋 직후 네 곳을 함께 비운다.**
3. `test_cycle287_ast_scope.py::test_s1b`(`_SRC_TREE_DIGEST`) — **Final 단계가 한 번에** 갱신한다(이 갈래는 손대지 않는다).

### 9-6 Green 에게 넘기는 주의 4

- **`asyncio.sleep` 전역 패치 금지**(N1~N4·N6~N10) — 테스트가 `_ISSUE_GAP_SECS=0.0` 으로 gap 을 없애고
  `await asyncio.sleep(0)` 로 루프를 돌린다. `sleep` 을 패치하면 그 양보가 죽어 "동시 진입" 자체가
  재현되지 않는다. N5 만 기존 관례대로 `fake_sleep` + 고정 monotonic 을 쓴다.
- **`issue_history` 는 리더 성공에만 append**(N8) — 대기자·실패를 세면 `window_issues_total` 이
  합류 전 세계를 그대로 재현해 성공을 영영 못 본다.
- **leaf 는 `time.monotonic()` 을 쓴다**(L1·L3) — 테스트가 `time` 모듈 속성을 패치하므로
  `from time import monotonic` 처럼 import 시점 바인딩을 하면 더블이 안 걸린다.
- **조기 return 경로도 5키**(L4) — 3키를 돌려주면 `_build_log_args` 의 `summary.get(key, 0)` 폴백에
  가려져 "측정했더니 0" 과 "측정조차 안 함" 이 구별되지 않는다.
