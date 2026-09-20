"""cycle330 — 합류자 0명인 토큰 발급 실패가 **고아 Future** 를 남긴다.

## 결함

`TokenManager.issue()`(cycle296)는 동시 발급을 한 번으로 합치려고 공유 Future
`self._inflight` 를 둔다. 여러 곳이 동시에 토큰을 필요로 하면 **리더 한 명만**
KIS 를 치고 나머지는 그 Future 를 기다린다(`/oauth2/tokenP` 는 분당 1개 한도다).

실패 경로(`src/auth/token.py`)는 이렇게 한다.

```
except BaseException as exc:
    if not fut.done():
        fut.set_exception(exc)   # 공유 상자에 오류를 담고
    raise                        # 자기 호출자에게도 던진다
```

리더 자신은 `raise` 로 오류를 정상 처리한다. 그런데 **합류자가 0명이면**
(= 그 순간 토큰을 원한 곳이 리더뿐이면) 상자에 담긴 오류 사본을 **아무도 읽지
않는다**. 파이썬이 그 Future 를 회수할 때 asyncio 가

    ERROR  Future exception was never retrieved

를 찍는다. 이것이 **고아 Future** 다.

## 피해

1. **운영 로그 오염** — 토큰 발급이 실패할 때마다(KIS 점검 · 분당 한도 초과 ·
   네트워크 순단) 원인을 알 수 없는 ERROR 가 쌓인다. `log_analysis_engine` 이
   WARNING 이상만 `top_patterns` 에 넣으므로 **21:30 리포트에 올라가 진짜 사고를 가린다**.
2. **CI 차단(실측 2026-09-20)** — CI 에는 KIS 자격이 없어 토큰 요청이 403 이고,
   그 고아 Future 가 `tests/unit/api/test_condition_cache.py` 의
   `gc.collect()` + `caplog` 단언을 오염시켜 **cycle329 의 Deploy 가 두 번 skip** 됐다.
   ⚠️ 그 테스트는 자기가 지킨다는 것을 판정하지 못한다(보호장치를 떼도 초록) —
   **무관한 누수에만 붉어지는** 가드라, 그쪽을 고치는 것은 증상 가리기다.

## 시정

오류를 담은 **직후 한 번 읽어** 회수 표시를 남긴다(`fut.exception()`).
파이썬 Future 는 예외를 한 번 조회하면 `__log_traceback` 이 내려가 경고를 내지 않는다.

🔴 **대기자 동작은 한 글자도 바뀌지 않는다** — 나중에 합류한 대기자가 `await fut`
하면 여전히 같은 예외를 받는다. 읽었다는 표시만 남기는 것이다.

⚠️ **자격을 CI 에 심는 것은 해법이 아니다**(2026-09-20 검토) — 403 이 사라져 증상은
가려지지만 고아 Future 는 그대로라 토큰 발급이 실패하는 날 운영·CI 양쪽에서 재발한다.
게다가 그 키는 **주문을 낼 수 있고**, `/oauth2/tokenP` 분당 1개 한도를 EC2 운영과
공유하며, `revoke()` 를 부르는 테스트가 있으면 **운영 토큰을 죽인다**.
"""
from __future__ import annotations

import asyncio

import pytest

pytestmark = pytest.mark.unit


def _will_warn_on_gc(fut: asyncio.Future) -> bool:
    """이 Future 가 회수될 때 asyncio 가 고아 경고를 낼 것인가.

    🔴 **`gc.collect()` 로는 이것을 판정할 수 없다**(실측 2026-09-20). 예외 객체가
    traceback → 프레임 → 지역변수 경로로 Future 를 계속 참조해서, 테스트 안에서는
    수집되지 않는다. 실제로 회수 표시를 떼어내도 gc 기반 단언은 **초록**이었다 —
    자기가 지킨다는 것을 판정하지 못하는 가드다(이 사이클을 부른
    `test_condition_cache.py` 의 단언과 같은 함정).

    그래서 **기전을 직접 본다.** `asyncio.Future.__del__` 은 `_log_traceback` 이
    False 면 조용히 지나간다(CPython `asyncio/futures.py`). `exception()` 을 한 번
    조회하면 그 플래그가 내려간다 — 그것이 "회수했다" 의 정의다.
    """
    return bool(getattr(fut, "_log_traceback", False))


@pytest.mark.asyncio
async def test_plain_set_exception_would_warn_baseline():
    """양성 대조군 — **맨** `set_exception` 은 경고 예정 상태로 남는다.

    이 줄이 없으면 아래 단언이 "원래 항상 False" 인지 "우리가 내렸는지" 를 못 가른다.
    """
    loop = asyncio.get_running_loop()
    fut: asyncio.Future = loop.create_future()
    fut.set_exception(RuntimeError("KIS 403 (모의)"))
    assert _will_warn_on_gc(fut) is True, (
        "맨 set_exception 이 경고 예정 상태가 아니다 — 이 테스트의 전제가 깨졌다"
    )
    fut.exception()   # 이 테스트 자신이 고아를 남기지 않도록 회수


@pytest.mark.asyncio
async def test_lone_leader_failure_leaves_no_orphan_future():
    """🔴 합류자 0명인 발급 실패가 **고아 Future 를 남기지 않는다**.

    이것이 이 사이클의 계약이다. `issue()` 의 실패 분기와 같은 모양으로 태우고,
    그 Future 가 회수될 때 경고를 낼 상태인지 본다.
    """
    from src.auth.token import TokenManager

    tm = TokenManager.__new__(TokenManager)
    tm._inflight = None
    tm._label = "test"

    loop = asyncio.get_running_loop()
    fut: asyncio.Future = loop.create_future()
    tm._inflight = fut
    with pytest.raises(RuntimeError, match="KIS 403"):
        try:
            raise RuntimeError("KIS 403 (모의)")
        except BaseException as exc:
            tm._mark_inflight_failed(fut, exc)
            raise
        finally:
            if tm._inflight is fut:
                tm._inflight = None

    assert _will_warn_on_gc(fut) is False, (
        "합류자 0명인데 공유 Future 가 **경고 예정 상태로 남았다** — "
        "회수 표시가 없으면 토큰 발급이 실패할 때마다 운영 로그에 "
        "원인 불명 ERROR 가 쌓이고 21:30 리포트가 오염된다"
    )


@pytest.mark.asyncio
async def test_waiter_still_receives_the_exception():
    """🔴 회수 표시를 남겨도 **대기자는 여전히 같은 예외를 받는다**.

    이 단언이 없으면 「경고를 없앴다」가 「예외를 삼켰다」로 조용히 번질 수 있다.
    그러면 합류자가 토큰 실패를 모른 채 진행한다 — 경고 하나 없애려다
    발급 실패를 은폐하는 것이라 훨씬 나쁘다.
    """
    from src.auth.token import TokenManager

    tm = TokenManager.__new__(TokenManager)
    loop = asyncio.get_running_loop()
    fut: asyncio.Future = loop.create_future()

    err = RuntimeError("KIS 403 (모의)")
    tm._mark_inflight_failed(fut, err)

    with pytest.raises(RuntimeError, match="KIS 403"):
        await asyncio.shield(fut)


@pytest.mark.asyncio
async def test_mark_inflight_failed_is_idempotent_and_never_raises():
    """이미 완료된 Future 에 불려도 터지지 않는다.

    `issue()` 는 `CancelledError` 분기와 `BaseException` 분기 **두 곳**에서 부르고,
    그 사이에 다른 경로가 Future 를 완료시켰을 수 있다. 관측·정리 성격의 호출이
    발급 경로를 깨뜨리면 안 된다.
    """
    from src.auth.token import TokenManager

    tm = TokenManager.__new__(TokenManager)
    loop = asyncio.get_running_loop()

    done: asyncio.Future = loop.create_future()
    done.set_result(None)
    tm._mark_inflight_failed(done, RuntimeError("무시돼야 한다"))
    assert done.result() is None, "이미 완료된 Future 의 결과가 덮였다"

    cancelled: asyncio.Future = loop.create_future()
    cancelled.cancel()
    tm._mark_inflight_failed(cancelled, RuntimeError("무시돼야 한다"))
    assert cancelled.cancelled()
