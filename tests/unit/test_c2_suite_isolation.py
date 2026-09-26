"""2026-09-26 C2(테스트 위생) — 스위트 결과가 **KIS 서버 속도**와 **수집 순서**에 묶이던 것.

## (a) CI 부팅 테스트 2개가 60초를 넘던 것 — 실제 KIS 모의 서버로 나가고 있었다

2026-09-25 CI 첫 시도(커밋 `c52a53f`, run 36070256596 attempt 1)가 08:09:45~08:11:46 KST 에
아래 두 테스트의 60초 타임아웃으로 취소됐다(재실행은 초록). 수집 순서 6258·6262 번째다.

- `tests/unit/engine/test_boot_manager_buy_date_date_object.py::test_boot_recovers_position_with_date_object_buy_date`
- `tests/unit/engine/test_boot_manager_extraction.py::test_boot_calls_preissue_before_token_and_load_config`

두 테스트는 `boot_manager.boot()` 를 부르는데, 그 안의 VI 시드(`inquire_vi_status_today`)와
계좌 리스크 감시(`account_risk_watcher` → `get_balance`)는 패치돼 있지 않아 **실제**
`openapivts.koreainvestment.com:29443` 으로 나간다. 전체 실행에서는 앞선
`tests/unit/auth/test_token_manager_multi.py` 가 주계정 토큰 싱글턴에 유효 토큰(만료 = 벽시계 +1h)을
남겨 두기 때문에, 토큰 발급(즉시 403)을 건너뛰고 REST 를 **두 경로 × 3회(재시도·백오프) = 6회** 친다.
한 번에 최대 10초(`timeout=10`)라 KIS 가 느린 시각에는 60초를 넘는다. 같은 날 같은 실행에서
07:59~08:01(수집 144~211 — 부팅 통합 테스트들)과 08:08(5599 — BFB funnel)도 몇 배 느렸는데,
그 구간에 든 테스트가 전부 이 목록(실측: 전체 스위트 28개 테스트가 KIS 로 214번 DNS·연결)에 있다.

시정 = `tests/conftest.py::_block_external_network`(autouse) — 루프백이 아닌 DNS 조회·소켓 연결을
**즉시 실패**시킨다(DNS 실패와 같은 모양, httpx 는 `ConnectError`). 누수 원천
(`test_token_manager_multi.py`)은 monkeypatch 로 고쳤다.

## (b) `test_cycle64_…::test_A1` 순서 의존 실패 — 모듈 전역 폴백 dict 누수

`src/db/system_config.py::_price_filter_memory_override` 는 DB 쓰기가 실패하면 값을 담는 모듈 전역
dict 다. `tests/unit/engine/test_cycle83_sk_square_fixture.py` 와 `test_cycle83_r6_frequency_regression.py`
가 DB 없이 진짜 `set_price_filter(max_price=500_000)` 를 불러 그 dict 에 500,000 을 남기고, 그 뒤에
도는 `test_A1`(기본값 0 기대)이 `assert 500000 == 0` 으로 붉어진다.
재현 = `pytest -p no:randomly tests/unit/engine/test_cycle83_sk_square_fixture.py
tests/unit/db/test_cycle64_price_filter_scanner_system_config.py`.

시정 = 두 테스트가 monkeypatch 로 새 dict 를 쓰게 하고(원천), `tests/conftest.py::
_reset_price_filter_memory_override`(autouse)가 테스트 전·후로 비운다(재발 방지).
"""
from __future__ import annotations

import asyncio
import socket
import time
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from freezegun import freeze_time

pytestmark = pytest.mark.unit

_KST = timezone(timedelta(hours=9))
_KIS_VTS_HOST = "openapivts.koreainvestment.com"


# ---------------------------------------------------------------------------
# (a) 외부 네트워크 차단
# ---------------------------------------------------------------------------
def test_kis_dns_lookup_is_refused_instantly(blocked_network_attempts) -> None:
    """KIS 호스트 DNS 조회가 **즉시** 실패한다 — 서버 속도에 결과가 묶이지 않는다."""
    started = time.perf_counter()
    with pytest.raises(socket.gaierror) as exc_info:
        socket.getaddrinfo(_KIS_VTS_HOST, 29443)
    elapsed = time.perf_counter() - started

    assert elapsed < 1.0, f"차단이 즉시가 아니다 ({elapsed:.2f}s)"
    assert "[test_network_blocked]" in str(exc_info.value)
    assert any(_KIS_VTS_HOST in a["host"] for a in blocked_network_attempts), blocked_network_attempts


def test_non_loopback_ip_connect_is_refused_instantly(blocked_network_attempts) -> None:
    """IP 리터럴 연결(예: 백테스트 MCP `43.202.187.5`)도 DNS 를 거치지 않으므로 따로 막는다."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(3.0)
    started = time.perf_counter()
    try:
        with pytest.raises(OSError) as exc_info:
            sock.connect(("203.0.113.7", 9))  # TEST-NET-3 — 실제로는 아무 데도 안 간다
    finally:
        sock.close()
    elapsed = time.perf_counter() - started

    assert elapsed < 1.0, f"차단이 즉시가 아니다 ({elapsed:.2f}s)"
    assert "[test_network_blocked]" in str(exc_info.value)
    assert any(a["host"] == "203.0.113.7" for a in blocked_network_attempts), blocked_network_attempts


async def test_httpx_request_to_kis_fails_fast_with_connect_error() -> None:
    """프로덕션 경로(`httpx.AsyncClient`)가 보는 모양 — `ConnectError` 가 즉시 온다."""
    started = time.perf_counter()
    with pytest.raises(httpx.ConnectError):
        async with httpx.AsyncClient() as client:
            await client.post(f"https://{_KIS_VTS_HOST}:29443/oauth2/tokenP", json={}, timeout=10)
    assert time.perf_counter() - started < 1.0


def test_loopback_is_still_allowed(blocked_network_attempts) -> None:
    """CI Postgres(127.0.0.1)·로컬 docker 하네스·테스트 서버는 루프백이라 그대로 통과한다."""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = server.getsockname()[1]
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        client.settimeout(3.0)
        client.connect(("127.0.0.1", port))
        assert socket.getaddrinfo("localhost", port)
    finally:
        client.close()
        server.close()
    assert blocked_network_attempts == []


@pytest.mark.real_network
def test_real_network_marker_opts_out() -> None:
    """옵트아웃 규약 — 마커가 붙으면 차단 함수가 끼지 않는다(여기서 실제로 나가지는 않는다).

    표준 함수와 **같음**이 아니라 차단 함수가 **아님**을 본다 — 다른 도구(진단 플러그인 등)가
    소켓 함수를 감싸 둔 환경에서도 이 규약만 잰다.
    """
    assert getattr(socket.getaddrinfo, "__name__", "") != "_guarded_getaddrinfo", socket.getaddrinfo
    assert getattr(socket.socket.connect, "__name__", "") != "_guarded_connect", socket.socket.connect
    assert getattr(socket.socket.connect_ex, "__name__", "") != "_guarded_connect_ex"


# ---------------------------------------------------------------------------
# (a) 회귀 — 문제의 두 부팅 테스트를 여러 KST 시각에 돌려도 KIS 로 안 나가고 빨리 끝난다
# ---------------------------------------------------------------------------
_BOOT_TIMES_KST = [
    datetime(2026, 9, 25, 7, 59, 30, tzinfo=_KST),   # 그날 첫 느린 구간
    datetime(2026, 9, 25, 8, 9, 45, tzinfo=_KST),    # 첫 타임아웃 테스트 시작 시각
    datetime(2026, 9, 25, 8, 10, 46, tzinfo=_KST),   # 두 번째 타임아웃 테스트 시작 시각
    datetime(2026, 9, 28, 9, 0, 5, tzinfo=_KST),     # 정규장 개장 직후
    datetime(2026, 9, 28, 15, 45, 0, tzinfo=_KST),   # cycle295 완전 휴식 창
    datetime(2026, 9, 28, 20, 30, 0, tzinfo=_KST),   # 일봉 적재 시각
]


def _run_flaky_boot_tests() -> None:
    from tests.unit.engine import test_boot_manager_buy_date_date_object as boot_date
    from tests.unit.engine import test_boot_manager_extraction as boot_ext

    asyncio.run(boot_date.test_boot_recovers_position_with_date_object_buy_date())
    asyncio.run(boot_ext.test_boot_calls_preissue_before_token_and_load_config())


@pytest.mark.parametrize("at", _BOOT_TIMES_KST, ids=lambda d: d.strftime("%m%d_%H%M%S"))
def test_flaky_boot_tests_are_hermetic_at_any_kst_time(at, blocked_network_attempts) -> None:
    started = time.perf_counter()
    with freeze_time(at, tick=True):
        _run_flaky_boot_tests()
    elapsed = time.perf_counter() - started

    kis = [a for a in blocked_network_attempts if "koreainvestment" in a["host"]]
    # 공허성 방지 — 부팅 경로가 KIS 를 **시도**했고, 그것을 차단기가 받았다.
    assert kis, "부팅 경로가 KIS 를 시도하지 않았다 — 이 회귀 가드가 공허하다"
    assert elapsed < 10.0, f"{at.isoformat()} 에서 {elapsed:.1f}s — 시각·서버 속도에 묶여 있다"


def test_flaky_boot_test_with_leaked_main_token_stays_far_below_timeout(
    monkeypatch: pytest.MonkeyPatch, blocked_network_attempts
) -> None:
    """최악 조건 재현 — CI 순서처럼 주계정 토큰 싱글턴에 유효 토큰이 남아 있어도.

    이 조건에서는 토큰 발급을 건너뛰고 REST 재시도(3회·백오프)까지 간다. 차단이 없으면
    한 번에 최대 10초 × 6회 — 그날 08:10 의 60초 초과가 이 경로다. 차단이 있으면 남는 것은
    결정적인 백오프 대기뿐이다.
    """
    from src.auth.token import token_manager
    from tests.unit.engine import test_boot_manager_extraction as boot_ext

    monkeypatch.setattr(token_manager, "access_token", "LEAKED-MAIN-TOKEN")
    monkeypatch.setattr(token_manager, "token_expired", datetime.now() + timedelta(hours=1))

    started = time.perf_counter()
    with freeze_time(datetime(2026, 9, 25, 8, 10, 46, tzinfo=_KST), tick=True):
        asyncio.run(boot_ext.test_boot_calls_preissue_before_token_and_load_config())
    elapsed = time.perf_counter() - started

    kis = [a for a in blocked_network_attempts if "koreainvestment" in a["host"]]
    assert len(kis) >= 2, f"REST 재시도 경로를 타지 않았다 — 공허하다: {kis}"
    assert elapsed < 30.0, f"{elapsed:.1f}s — pytest-timeout(60s) 절반을 넘는다"


# ---------------------------------------------------------------------------
# (b) `_price_filter_memory_override` 누수 — 같은 파일 안 두 테스트로 순서를 고정해 재현한다
# ---------------------------------------------------------------------------
class _FailingPg:
    """DB 미가동 흉내 — `set_price_filter` 가 인메모리 폴백으로 떨어지게 한다."""

    async def execute(self, *_a, **_k):
        raise RuntimeError("db down (test)")

    async def fetch(self, *_a, **_k):
        raise RuntimeError("db down (test)")

    async def fetchrow(self, *_a, **_k):
        raise RuntimeError("db down (test)")

    async def fetchval(self, *_a, **_k):
        raise RuntimeError("db down (test)")


async def test_price_filter_override_1_starts_clean_then_pollutes(monkeypatch) -> None:
    """첫째 — 깨끗하게 시작하고, cycle83 두 테스트와 같은 경로로 오염시킨다."""
    from src.db import system_config

    assert system_config._price_filter_memory_override == {}, (
        "앞선 테스트가 남긴 가격 필터 폴백이 보인다 — 테스트 간 누수"
    )
    monkeypatch.setattr(system_config, "pg", _FailingPg())
    await system_config.set_price_filter(min_price=0, max_price=500_000)
    # 공허성 방지 — 누수 경로가 실제로 존재한다
    assert system_config._price_filter_memory_override.get("price_filter_max") == 500_000


async def test_price_filter_override_2_is_clean_after_polluter(fake_pg_kv, monkeypatch) -> None:
    """둘째 — 바로 앞 테스트가 오염시켜도 기본값(0/0)을 본다 = `test_A1` 의 조건."""
    from src.db import system_config

    assert system_config._price_filter_memory_override == {}, (
        "앞 테스트의 set_price_filter 폴백 값이 남았다 — test_cycle64 A1 순서 의존 실패의 원인"
    )
    monkeypatch.setattr(system_config, "pg", fake_pg_kv)
    pf = await system_config.get_price_filter()
    assert (pf.min_price, pf.max_price) == (0, 0)


# ---------------------------------------------------------------------------
# 메타 가드 — 두 픽스처가 autouse 로 남아 있는가 (지우면 여기서 붉어진다)
# ---------------------------------------------------------------------------
def test_conftest_isolation_fixtures_are_autouse(request) -> None:
    names = set(request.fixturenames)
    assert "_block_external_network" in names, "외부 네트워크 차단 픽스처가 autouse 가 아니다"
    assert "_reset_price_filter_memory_override" in names, "가격 필터 폴백 초기화 픽스처가 autouse 가 아니다"
