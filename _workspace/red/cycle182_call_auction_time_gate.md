# Red 메모 — 사이클 182: `is_call_auction_now()` 시간창 게이트 (stale-1 HIGH + stale-5 LOW)

작성: tdd-engineer / 2026-06-28
대상: `src/engine/session.py::SessionTracker.is_call_auction_now`
설계: `_workspace/domain_consult/cycle182_call_auction_time_gate.md` (방식 A 시간창 게이트 단독 채택)
단계: **Red** — 실패 테스트만 작성, production 코드 미변경. Green 은 backend-dev 별도.

---

## 결함 (현재 코드)

```
209  if self._last_nxt_mkop_code in ("110", "121"):   # 시간창 게이트 0 → 고착 시 영구 True
210      return True
213  now = now or datetime.now()                       # stale-5: naive (KST 위반)
```

- **stale-1 (HIGH)**: 고착 코드("121"/"110") 가 시간 무관 영구 True. KIS H0UNMKO0 가 동시호가
  *종료* 전환 코드(112/129)를 reliably push 하지 않으면 `_last_nxt_mkop_code` 영구 고착.
  - stuck-121 (사용자 보고): 15:30~20:00 NXT 애프터 내내 stale 탐지 OFF.
  - stuck-110 (자문 신규, 더 위험): 09:00~15:20 MAIN 전체 stale 탐지 OFF (보유 손절 피크).
  - `_last_nxt_mkop_code` 리셋/시간 게이트 0건 (전수 grep 확정).
- **stale-5 (LOW)**: `now=None` 폴백이 naive `datetime.now()` = KST 불변식 위반 (잠재 — 유일
  production 호출자 stale_watcher_core 가 KST-aware 명시 전달 + EC2 TZ=KST → 운영 영향 0).

## Green 목표 (테스트가 가정하는 동작 — domain-expert load-bearing 조건식)

```python
_KST = timezone(timedelta(hours=9))   # session.py 모듈 로컬 (scanner 순환 import 회피)

def is_call_auction_now(self, now=None):
    now = now or datetime.now(_KST)                              # stale-5: KST 강제
    t = now.time()
    code = self._last_nxt_mkop_code
    if code == "110" and time(8, 25) <= t < time(9, 5):    return True   # 110 유효창 ±5분
    if code == "121" and time(15, 15) <= t < time(15, 35): return True   # 121 유효창 ±5분
    if time(8, 30) <= t < time(9, 0):    return True            # 시간 폴백 (사이클 162 보존)
    if time(15, 20) <= t < time(15, 30): return True
    return False
```

## 의제 → 가드 매핑

| 가드 | 케이스 | 검증 | 현재 코드 |
|------|--------|------|-----------|
| stuck 차단 (HIGH) | `G-182-STUCK` (parametrize 4) | 121@16:00 / 110@11:00 / 121@10:00 / 110@14:00 → **False** | **FAIL = Red** (4건 모두 True 반환) |
| 마진 경계 (±5분) | `G-182-MARGIN` (parametrize 9) | 포함=08:25/08:29/09:04:59/15:15/15:34:59 → True · 배제=08:24:59/09:05/15:14:59/15:35 → False | 배제 4종 **FAIL = Red**, 포함 5종 pass |
| 사이클 162 보존 (HIGH) | `G-182-PRESERVE` (parametrize 6) | 110@08:45 / 121@15:25 / ''@08:45 / ''@15:25 → True, ''@11:00 → False, 121@15:21 → True | pass (현재/Green 동일, 보존) |
| 방식 B 내재 | `G-182-TRANSITION` | 121→129 재대입 후 16:00 → False | pass (129 비-동시호가, 보존) |
| stale-5 KST (LOW) | `G-182-STALE5` ×2 (freezegun) | UTC 23:45=KST 08:45 / UTC 06:25=KST 15:25, now=None → True | **FAIL = Red** (naive → 창 밖 False) |
| AST 게이트 (HIGH) | `G-182-AST-1` | '110'/'121' 코드 상수가 `time()` 게이트 `and` 동반 의무 | **FAIL = Red** (게이트 0) |
| AST naive now (LOW) | `G-182-AST-2` | 함수 내 naive `datetime.now()` (인자 0개) 0건 | **FAIL = Red** (L213 0-arg) |
| AST sanity | `G-182-AST-3` | '110'/'121' 코드 상수 실제 존재 (비공허) | pass |

## 현재 코드에서 FAIL 하는 근거 (실측)

- `G-182-STUCK` 4건: 현재 L209 `in ("110","121")` 무조건 True → 단언 `is False` FAIL.
- `G-182-MARGIN` 배제 4건 (08:24:59 / 09:05:00 / 15:14:59 / 15:35:00): 코드 분기 True → `is False` FAIL.
- `G-182-STALE5` 2건: freezegun UTC 23:45/06:25 → naive `datetime.now()` → 23:45/06:25 → 시간 폴백
  창 밖 → False → 단언 `is True` FAIL (Green 의 `datetime.now(_KST)` 시 KST 08:45/15:25 → True).
- `G-182-AST-1`: `"110"`/`"121"` 가 `Tuple` 내 `Compare(In)` — 감싸는 `BoolOp(And)` 없음 + `time()` 동반 0 → FAIL.
- `G-182-AST-2`: L213 `datetime.now()` 인자 0개 Call 1건 → FAIL.

## 의미 전환 2건 (사이클 66 K-2 패턴)

기존 `tests/unit/engine/test_cycle162_call_auction_stale_skip.py` 가 결함을 정상으로 박제 →
`@pytest.mark.xfail(strict=False)` 마킹 + docstring 의미 전환 명시 (단언 본문/구조 보존):

- `G-162-E-1` (L22): code="110" @ 14:00(MAIN) → 현 `assert True` (주석 "시간 무관 코드 즉시 True")
  = stuck-110-during-MAIN 결함. → xfail(strict=False). 현재 = XPASS (허용), Green 후 = 자동 XFAIL.
- `G-162-E-2` (L31): code="121" @ 10:00(MAIN) → 현 `assert True` = stuck-121-during-MAIN. → 동일.

정답(False) 단언은 `G-182-STUCK` 신규 케이스가 보유. 사이클 162 의 *정당한* skip 테스트
(진짜 동시호가 시간대 G-162-E-3~E-10) 는 변경 0 — Green 후에도 전부 PASS 유지.

## 작성 규칙 준수

- 시간 분기는 `is_call_auction_now(now=datetime(...))` 직접 주입 = 날짜/타임존 의존 0 (사이클 176 교훈).
- stale-5(now=None 경로) 만 freezegun (KST-aware 강제 검증 불가피).
- AST 가드 = source 텍스트 스캔 아닌 AST 노드 (사이클 167/179 패턴, docstring/주석 false positive 차단).
- production 코드 변경 0. Green = backend-dev (session.py `is_call_auction_now` + import 2 + `_KST` 상수).

## 파일

- `tests/unit/engine/test_cycle182_call_auction_time_gate.py` (행위 가드 23 invocations)
- `tests/unit/ast/test_cycle182_call_auction_ast_gate.py` (AST 가드 4)
- `tests/unit/engine/test_cycle162_call_auction_stale_skip.py` (의미 전환 2건 — xfail)
