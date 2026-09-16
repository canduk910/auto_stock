"""cycle296 — `TokenManager.issue()` **매니저 단위 in-flight 합류** 회귀 가드 (RED).

정본 = `_workspace/red/cycle296_token_refresh_coalesce_spec.md` §3-1 / §5-1.

## 무엇이 문제였나 (09-15 21건 / 09-16 14건, 설계는 7건/일)

`asyncio.Lock` 은 **직렬화만 하고 합류시키지 않는다.** 같은 매니저의 토큰을 원하는
두 코루틴이 각각 KIS `/oauth2/tokenP` 를 친다. 두 경로로 드러났다:

- **(A) 자연 문턱 경합** — `_is_valid()` 의 10분 선제 갱신 마진 때문에 T−10 창에
  시세 REST 가 몰리면 `get_token()` 여러 개가 동시에 `issue()` 로 떨어진다.
- **(B) `revoke()` 가 여는 61초 공백** — leaf(`quote_token_refresh`)가 `revoke()` 로
  `access_token=""` 을 만든 직후 `issue()` 가 전역 락을 쥔 채 61초 잠드는데, 그
  사이 들어온 REST 가 `_is_valid()=False` → `issue()` → 락 대기 → 61초 뒤 **한 번 더**
  KIS 를 친다. 실측 로그: `19:02:03 폐기(gold) → 19:03:04 발급 → 19:04:05 발급(만료 동일)`.

## 이 파일이 잠그는 불변식

| ID | 내용 |
|----|------|
| I-1 | 한 매니저에 **동시 진행 중인 POST 는 최대 1개** — 뒤에 온 호출자는 결과만 기다린다 |
| I-2 | 전역 61초 직렬화는 그대로다. **다른 라벨끼리는 합류하지 않는다**(N5 양성 대조군) |
| I-3 | 리더가 성공·실패·취소 어느 길로 끝나도 대기자는 풀린다(예외는 **전파**, 삼킴 금지) |
| I-4 | 합류는 "진행 중" 에만 — 끝난 Future 에는 합류하지 않는다(cycle270 revoke→issue 보존) |
| I-5 | 줄이는 방향뿐 — 리더 1 + 대기자 N 의 KIS 호출 = 1 ≤ 현행 N+1 |

⚠️ **양성 대조군 규약** — 이 파일의 모든 케이스는 "POST 가 줄었다"(부정 단언) 옆에
"토큰이 실제로 발급됐다 / 대기자가 그 토큰을 받았다"(긍정 단언)를 함께 둔다.
`issue()` 를 통째로 no-op 으로 만드는 뮤테이션은 POST 0 으로 부정 단언을 통과시킨다.
"""
from __future__ import annotations

import asyncio
import collections
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import httpx
import pytest

pytestmark = pytest.mark.unit

_MISSING = object()


# ===========================================================================
# 픽스처 / 하네스 (`test_token_global_serialization.py` 패턴 재사용)
# ===========================================================================

@pytest.fixture(autouse=True)
def reset_token_state(monkeypatch: pytest.MonkeyPatch, tmp_path):
    """모듈 전역 lock + 마지막 발급 시각 + 캐시 경로 격리."""
    from src.auth import token as token_mod

    monkeypatch.setattr(token_mod, "_TOKEN_CACHE_DIR", tmp_path / ".token_cache")
    monkeypatch.setattr(
        token_mod, "_TOKEN_CACHE_PATH", tmp_path / ".token_cache" / "main.json"
    )
    monkeypatch.setattr(
        token_mod, "_LEGACY_MAIN_CACHE_PATH", tmp_path / ".token_cache.json"
    )
    token_mod.reset_quote_token_managers()
    token_mod.reset_global_issue_state()
    yield
    token_mod.reset_quote_token_managers()
    token_mod.reset_global_issue_state()


def _make_token_response(token: str = "ACCESS-TOK", hours: int = 23) -> MagicMock:
    expired = (datetime.now() + timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json = MagicMock(
        return_value={"access_token": token, "access_token_token_expired": expired}
    )
    return resp


class _PostRecorder:
    """KIS `/oauth2/tokenP` POST 를 세고, 필요하면 게이트로 잡아 둔다.

    게이트는 **진짜 이벤트 루프 양보**를 만든다 — 더블이 양보하지 않으면 첫 코루틴이
    끝까지 달려 버려 "동시 진입" 자체가 재현되지 않고 테스트가 가짜 GREEN 이 된다.
    """

    def __init__(self, token: str = "TOK") -> None:
        self.calls = 0
        self.token = token
        self.gate: asyncio.Event | None = None
        self.fail: BaseException | None = None

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from src.auth import token as token_mod

        rec = self

        class _Client:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return None

            async def post(self, *_a, **_kw):
                rec.calls += 1
                if rec.gate is not None:
                    await rec.gate.wait()
                if rec.fail is not None:
                    raise rec.fail
                return _make_token_response(rec.token)

        monkeypatch.setattr(token_mod.httpx, "AsyncClient", lambda: _Client())


async def _pump(rounds: int = 40) -> None:
    """이벤트 루프를 여러 번 돌려 대기 중인 코루틴을 각자의 park 지점까지 보낸다."""
    for _ in range(rounds):
        await asyncio.sleep(0)


def _new_manager(tmp_path: Path, label: str | None = None):
    from src.auth import token as token_mod

    return token_mod.TokenManager(
        app_key="key", app_secret="secret", base_url="https://kis.test",
        cache_path=tmp_path / f"{label or 'main'}.json", label=label,
    )


def _no_gap(monkeypatch: pytest.MonkeyPatch) -> None:
    """61초 gap sleep 제거 — 합류 자체를 재는 케이스에서 시간 의존을 뺀다.

    ⚠️ 상수 자체는 **바꾸지 않는다**(A1/N5 가 61.0 을 지킨다). 여기서는 테스트
    런타임에서만 0 으로 두어 `asyncio.sleep` 전역 패치를 피한다(전역 패치는
    `_pump()` 의 진짜 양보까지 죽인다).
    """
    from src.auth import token as token_mod

    monkeypatch.setattr(token_mod, "_ISSUE_GAP_SECS", 0.0)


# ===========================================================================
# N1 — 동시 get_token() N개 → KIS POST 1회
# ===========================================================================

@pytest.mark.asyncio
async def test_n1_concurrent_get_token_issues_once(monkeypatch, tmp_path):
    """N1 — 같은 매니저에 `get_token()` 5개가 동시에 떨어져도 KIS 는 **1번**만 친다.

    RED(현행) = 5번. 락은 직렬화만 하므로 5개가 차례로 각자 POST 한다.
    """
    _no_gap(monkeypatch)
    rec = _PostRecorder(token="TOK-N1")
    rec.install(monkeypatch)
    mgr = _new_manager(tmp_path, "n1")
    rec.gate = asyncio.Event()

    tasks = [asyncio.create_task(mgr.get_token()) for _ in range(5)]
    await _pump()
    assert rec.calls >= 1, "아무도 KIS 를 치지 않았다 — 더블 배선이 깨졌다"
    rec.gate.set()
    tokens = await asyncio.gather(*tasks)

    # 양성 대조군 — 실제로 발급됐고 다섯 호출자 전부가 그 토큰을 받았다.
    assert tokens == ["TOK-N1"] * 5, f"실측 {tokens}"
    assert mgr.access_token == "TOK-N1"
    assert mgr.token_expired is not None

    assert rec.calls == 1, (
        f"동시 5호출에 KIS POST 가 {rec.calls}회 — `issue()` 에 매니저 단위 in-flight "
        "합류가 없다(asyncio.Lock 은 직렬화만 하고 합류시키지 않는다)"
    )


# ===========================================================================
# N2 — (B) revoke→issue 61초 공백에 들어온 REST 가 합류한다
# ===========================================================================

@pytest.mark.asyncio
async def test_n2_rest_during_issue_gap_joins_instead_of_reissuing(
    monkeypatch, tmp_path
):
    """N2 — 리더가 전역 락을 기다리는 동안 들어온 `get_token()` 이 합류한다.

    이것이 09-16 로그의 `19:03:04 발급 → 19:04:05 발급(만료 동일)` 재현이다.
    테스트가 전역 락을 먼저 쥐어 "리더가 61초 sleep 중" 상태를 대신한다.
    """
    _no_gap(monkeypatch)
    from src.auth import token as token_mod

    rec = _PostRecorder(token="TOK-N2")
    rec.install(monkeypatch)
    mgr = _new_manager(tmp_path, "n2")

    lock = token_mod._get_global_issue_lock()
    await lock.acquire()
    try:
        leader = asyncio.create_task(mgr.issue())
        await _pump()
        follower = asyncio.create_task(mgr.get_token())
        await _pump()
        assert rec.calls == 0, "락을 쥐고 있는 동안 POST 가 나갔다 — 직렬화 자체가 깨졌다"
    finally:
        lock.release()

    await leader
    token = await follower

    # 양성 대조군 — 공백이 메워졌고 대기자가 유효 토큰을 받았다.
    assert token == "TOK-N2"
    assert mgr.access_token == "TOK-N2"

    assert rec.calls == 1, (
        f"revoke→issue 공백에 들어온 호출자가 KIS 를 또 쳤다(POST {rec.calls}회) — "
        "합류 부재. 09-15 21건 / 09-16 14건의 직접 원인이다"
    )


# ===========================================================================
# N3 — 리더 실패는 대기자에게 **그대로** 전파된다
# ===========================================================================

@pytest.mark.asyncio
async def test_n3_leader_failure_propagates_to_waiters_and_clears_inflight(
    monkeypatch, tmp_path
):
    """N3 — 실패를 삼키면 대기자가 **빈 문자열 토큰**으로 REST 를 쏜다(무음 401).

    또한 실패 뒤 `_inflight` 가 남아 있으면 이후 모든 `issue()` 가 끝난 Future 에
    영구 합류해 KIS 를 영영 안 친다(R5, HIGH).
    """
    _no_gap(monkeypatch)
    rec = _PostRecorder(token="TOK-N3")
    rec.install(monkeypatch)
    mgr = _new_manager(tmp_path, "n3")

    rec.gate = asyncio.Event()
    rec.fail = httpx.HTTPStatusError(
        "500 Server Error",
        request=httpx.Request("POST", "https://kis.test/oauth2/tokenP"),
        response=httpx.Response(500),
    )

    leader = asyncio.create_task(mgr.issue())
    await _pump()
    waiter = asyncio.create_task(mgr.issue())
    await _pump()
    rec.gate.set()
    res = await asyncio.gather(leader, waiter, return_exceptions=True)

    assert isinstance(res[0], httpx.HTTPStatusError), f"리더 실측 {res[0]!r}"
    assert isinstance(res[1], httpx.HTTPStatusError), (
        f"대기자가 리더의 실패를 못 받았다 — 실측 {res[1]!r}. `None` 반환/예외 삼킴은 "
        "`get_token()` 이 빈 토큰을 돌려주게 만든다(무음 401)"
    )
    assert str(res[1]) == str(res[0])

    assert rec.calls == 1, f"대기자가 별도로 KIS 를 쳤다 — POST {rec.calls}회"
    assert getattr(mgr, "_inflight", _MISSING) is None, (
        "실패 뒤 `_inflight` 가 남아 있다 — 끝난 Future 에 영구 합류하면 만료 후 전 REST 401"
    )

    # 양성 대조군 — 실패는 흡수되지 않고, 다음 호출은 **새 리더**로 KIS 를 다시 친다.
    rec.fail = None
    rec.gate = None
    await mgr.issue()
    assert rec.calls == 2, f"복구 발급이 KIS 를 치지 않았다 — POST 누계 {rec.calls}"
    assert mgr.access_token == "TOK-N3"


# ===========================================================================
# N4 — 리더 취소는 CancelledError 가 아니라 RuntimeError 로 건네진다
# ===========================================================================

@pytest.mark.asyncio
async def test_n4_leader_cancellation_does_not_cancel_waiters(monkeypatch, tmp_path):
    """N4 — 대기자에게 `CancelledError` 를 그대로 심으면 **대기자 자신이 취소된 것**
    처럼 보여 `base.py::_request` 의 재시도 루프가 통째로 끊긴다. RuntimeError 로 바꾼다.
    """
    _no_gap(monkeypatch)
    rec = _PostRecorder(token="TOK-N4")
    rec.install(monkeypatch)
    mgr = _new_manager(tmp_path, "n4")
    rec.gate = asyncio.Event()

    leader = asyncio.create_task(mgr.issue())
    await _pump()
    waiter = asyncio.create_task(mgr.issue())
    await _pump()

    leader.cancel()
    rec.gate.set()  # 대기자가 (합류 실패 시) 영원히 매달리지 않게 풀어 준다
    res = await asyncio.gather(leader, waiter, return_exceptions=True)

    assert isinstance(res[0], asyncio.CancelledError), f"리더 실측 {res[0]!r}"
    assert isinstance(res[1], RuntimeError), (
        f"대기자 실측 {res[1]!r} — 리더 취소는 대기자에게 RuntimeError 로 전달돼야 한다"
    )
    assert not isinstance(res[1], asyncio.CancelledError), (
        "`CancelledError` 를 그대로 전파하면 대기자의 상위 재시도 루프가 죽는다"
    )
    assert rec.calls == 1, f"대기자가 별도 POST 를 냈다 — {rec.calls}회"
    assert getattr(mgr, "_inflight", _MISSING) is None


# ===========================================================================
# N5 — 양성 대조군: **다른 라벨끼리는 합류하지 않는다**
# ===========================================================================

@pytest.mark.asyncio
async def test_n5_different_managers_still_serialize_with_61s_gap(
    monkeypatch, tmp_path
):
    """N5 — KIS 분당 1개는 **전역** 한도다. 합류는 매니저 단위여야 한다.

    합류를 전역으로 넓히면 서로 다른 계정이 남의 토큰을 기다리게 되고(=발급 누락),
    락을 매니저 단위로 쪼개면 403 이 돌아온다(사이클 20 이 고친 결함의 재현).
    이 케이스는 **지금도 GREEN 이고 앞으로도 GREEN 이어야 한다**.
    """
    from src.auth import token as token_mod

    sleep_calls: list[float] = []

    async def fake_sleep(secs):
        sleep_calls.append(secs)

    monkeypatch.setattr(token_mod.asyncio, "sleep", fake_sleep)
    rec = _PostRecorder(token="TOK-N5")
    rec.install(monkeypatch)

    class _Clock:
        def __init__(self, start: float) -> None:
            self._now = start

        def __call__(self) -> float:
            return self._now

    monkeypatch.setattr(token_mod.time, "monotonic", _Clock(100.0))

    m1 = _new_manager(tmp_path, "m1")
    m2 = _new_manager(tmp_path, "m2")

    await asyncio.gather(m1.issue(), m2.issue())

    assert rec.calls == 2, (
        f"라벨이 다른 두 매니저가 합류했다(POST {rec.calls}회) — 합류 단위는 **매니저**다"
    )
    assert m1.access_token == "TOK-N5" and m2.access_token == "TOK-N5"
    assert sleep_calls == pytest.approx([61.0], rel=0.01), (
        f"전역 61초 직렬화가 사라졌다 — 실측 {sleep_calls}. 락을 매니저 단위로 쪼개면 "
        "KIS 분당 1개 한도 위반(403 → 앱키 정지 위험)"
    )


# ===========================================================================
# N6 — 순차 issue() 두 번은 여전히 KIS 두 번 (I-4)
# ===========================================================================

@pytest.mark.asyncio
async def test_n6_sequential_issue_calls_are_not_coalesced(monkeypatch, tmp_path):
    """N6 — 끝난 Future 에 합류하면 cycle270 의 `revoke()`→`issue()` 가 무력화된다.

    합류는 **진행 중**에만 성립한다. `finally` 의 `_inflight = None` 이 그 보증이다.
    """
    _no_gap(monkeypatch)
    rec = _PostRecorder(token="TOK-N6")
    rec.install(monkeypatch)
    mgr = _new_manager(tmp_path, "n6")

    await mgr.issue()
    assert getattr(mgr, "_inflight", _MISSING) is None, (
        "성공 뒤 `_inflight` 가 안 지워졌다 — 이후 모든 발급이 조용히 건너뛰어진다"
    )
    await mgr.issue()

    assert rec.calls == 2, (
        f"순차 두 번이 KIS 를 {rec.calls}회 쳤다 — 1회면 cycle270 앵커 이동이 죽는다"
    )
    assert mgr.access_token == "TOK-N6"


# ===========================================================================
# N7 — 스냅샷 비교: revoke 로 토큰이 비면 합류하지 않는다 (cycle270 계약 보존)
# ===========================================================================

@pytest.mark.asyncio
async def test_n7_revoked_state_does_not_join_an_older_leader(monkeypatch, tmp_path):
    """N7 — 리더가 **옛 토큰**으로 진입한 뒤 leaf 가 `revoke()` 했다면, 강제 발급은
    그 리더에 합류하면 안 된다.

    합류시키면 리더의 POST 가 revoke 보다 먼저 끝난 경우 그 계정은 **폐기된 토큰**을
    들고 앵커도 그대로 남는다(cycle270 의 앵커 이동이 조용히 무효가 된다).
    """
    _no_gap(monkeypatch)
    rec = _PostRecorder(token="TOK-N7")
    rec.install(monkeypatch)
    mgr = _new_manager(tmp_path, "n7")
    mgr.access_token = "OLD-TOK"
    mgr.token_expired = datetime.now() + timedelta(hours=23)
    rec.gate = asyncio.Event()

    leader = asyncio.create_task(mgr.issue())  # 스냅샷 = "OLD-TOK"
    await _pump()

    mgr.access_token = ""  # leaf 의 revoke() 가 한 일
    forced = asyncio.create_task(mgr.issue())
    await _pump()

    rec.gate.set()
    await asyncio.gather(leader, forced)

    assert rec.calls == 2, (
        f"폐기 뒤 강제 발급이 옛 리더에 합류했다(POST {rec.calls}회) — 그 계정은 "
        "폐기된 토큰을 들고 앵커도 안 옮겨진다(cycle270 회귀)"
    )
    assert mgr.access_token == "TOK-N7"


# ===========================================================================
# N8 — issue_history (관측 ③ 의 원천)
# ===========================================================================

@pytest.mark.asyncio
async def test_n8_issue_history_records_only_real_kis_calls(monkeypatch, tmp_path):
    """N8 — `issue_history` 는 **실제 KIS 를 친 리더**만 기록한다.

    leaf 의 `window_issues_total` 이 이 deque 를 읽는다. 대기자까지 세면 지표가
    "합류 전 세계" 를 그대로 재현해 합류 성공을 영영 못 본다.
    """
    _no_gap(monkeypatch)
    rec = _PostRecorder(token="TOK-N8")
    rec.install(monkeypatch)
    mgr = _new_manager(tmp_path, "n8")

    hist = getattr(mgr, "issue_history", _MISSING)
    assert isinstance(hist, collections.deque), (
        f"`TokenManager.issue_history` 가 없다(실측 {hist!r}) — leaf 의 "
        "`window_issues_total` 이 읽을 원천이 없다"
    )
    assert hist.maxlen == 64, f"maxlen 실측 {hist.maxlen}"
    assert len(hist) == 0
    assert getattr(mgr, "_inflight", _MISSING) is None

    rec.gate = asyncio.Event()
    tasks = [asyncio.create_task(mgr.get_token()) for _ in range(3)]
    await _pump()
    rec.gate.set()
    await asyncio.gather(*tasks)

    assert len(mgr.issue_history) == 1, (
        f"리더 1 + 대기자 2 에 기록이 {len(mgr.issue_history)}건 — 대기자는 세지 않는다"
    )
    assert all(isinstance(ts, float) for ts in mgr.issue_history)

    # 실패는 기록하지 않는다 — "KIS 를 친 횟수" 가 아니라 "발급된 횟수" 지표다.
    rec.gate = None
    rec.fail = RuntimeError("KIS down")
    with pytest.raises(RuntimeError):
        await mgr.issue()
    assert len(mgr.issue_history) == 1, "실패까지 세면 window 지표가 부풀려진다"


# ===========================================================================
# N9 — 캐시 hit 는 합류 상태를 만들지도 않는다 (기존 test_D 보존)
# ===========================================================================

@pytest.mark.asyncio
async def test_n9_cache_hit_never_touches_inflight_state(monkeypatch, tmp_path):
    """N9 — 운영의 정상 흐름(캐시 hit)은 `issue()` 에 들어가지도 않는다."""
    _no_gap(monkeypatch)
    rec = _PostRecorder(token="TOK-N9")
    rec.install(monkeypatch)
    mgr = _new_manager(tmp_path, "n9")
    mgr.access_token = "CACHED-TOK"
    mgr.token_expired = datetime.now() + timedelta(hours=2)

    tok = await mgr.get_token()

    assert tok == "CACHED-TOK"
    assert rec.calls == 0
    assert getattr(mgr, "_inflight", _MISSING) is None
    assert len(getattr(mgr, "issue_history", [])) == 0, (
        "캐시 hit 인데 발급 이력이 남았다 — window 지표가 오염된다"
    )


# ===========================================================================
# N10 — 한 대기자의 타임아웃이 공유 Future 를 죽이지 않는다 (shield)
# ===========================================================================

@pytest.mark.asyncio
async def test_n10_waiter_timeout_does_not_cancel_the_shared_future(
    monkeypatch, tmp_path
):
    """N10 — `shield` 없이 `wait_for(fut)` 를 쓰면 한 대기자의 타임아웃·취소가
    **공유 Future 를 취소**해 다른 대기자까지 전부 죽는다(R3).
    """
    _no_gap(monkeypatch)
    rec = _PostRecorder(token="TOK-N10")
    rec.install(monkeypatch)
    mgr = _new_manager(tmp_path, "n10")
    rec.gate = asyncio.Event()

    leader = asyncio.create_task(mgr.issue())
    await _pump()
    impatient = asyncio.create_task(asyncio.wait_for(mgr.issue(), timeout=0.05))
    patient = asyncio.create_task(mgr.issue())
    await _pump()

    await asyncio.sleep(0.15)  # impatient 만 타임아웃시킨다
    rec.gate.set()
    res = await asyncio.gather(leader, impatient, patient, return_exceptions=True)

    assert isinstance(res[1], asyncio.TimeoutError), f"조급한 대기자 실측 {res[1]!r}"
    assert res[0] is None and res[2] is None, (
        f"리더/인내하는 대기자가 함께 죽었다 — 실측 {res!r}. 공유 Future 를 "
        "`asyncio.shield` 로 감싸지 않으면 한 대기자의 타임아웃이 전원을 취소한다"
    )
    assert mgr.access_token == "TOK-N10"
    assert rec.calls == 1, f"POST {rec.calls}회 — 대기자가 별도로 KIS 를 쳤다"
