"""cycle252 Red — 무송출(no_feed) 종목 레지스트리 (`src/engine/no_feed_registry.py`).

> 정본 명세: `spec_cycle252_no_feed_churn.md` §2 (신규 leaf) / §3 R1~R7
> 포렌식 근거: `_workspace/forensics/stale_candidates_0904.md` ① · ②-5 · ③(S7)

## 왜 이 모듈이 필요한가

`stock_master.nxt_tradable=False`(KRX 단독, NXT 거래대상 아님) 종목은 통합 채널
`H0UNCNT0` 로 SUBSCRIBE → `SUBSCRIBE SUCCESS` ACK 까지 정상인데 **체결 프레임이 하루
1건도 오지 않는다**(09-01~09-04 나흘 × ~200종목, 예외 0 · 유동주 포함 = 침묵이 아니라
채널 결함). K stale watcher 가 그 종목들을 하루 ~134회 재등록해 SEND ≈14,600 ·
`[ws_ack_orphan]` 7,120 을 만들지만 회복 가치는 나흘간 0 이다.

이 레지스트리는 "그 종목이 어느 것인가" 를 **DB 1회 조회 + TTL 캐시**로 답한다.

## 계약 (Red 단계 = 모듈 부재 → 전부 FAIL)

| ID | 계약 |
|----|------|
| R1 | 첫 호출 = 조회 1회. `False`→no_feed / `True`·`None`→아님. `_known` = 요청 전부 |
| R2 | ttl 내 재호출(요청이 `_known` 부분집합) = 조회 0 |
| R3 | 미지 ticker 가 섞이면 ttl 내라도 조회 1회 — 인자는 **전체 tickers** |
| R4 | ttl 경과 = 조회 1회 |
| R5 | 조회 예외 = 이전 집합 유지 · WARNING 1회/일 · `_loaded_mono` 미갱신(재시도) |
| R6 | 빈 tickers = 조회 0 · 집합 유지 |
| R7 | `reset_state_for_test()` 후 전부 초기 |

fail-open 이 설계의 뼈대다(§1 D3) — 집합이 비면 호출자는 **현행 byte 동일**로 돌아간다.
"""
from __future__ import annotations

import logging

import pytest
from freezegun import freeze_time

pytestmark = pytest.mark.unit

_MARKER = "[no_feed_registry_refresh_failed]"


# ---------------------------------------------------------------------------
# 헬퍼 — 모듈 부재 시 SKIP 이 아니라 FAIL (Red 는 붉어야 한다)
# ---------------------------------------------------------------------------
def _registry():
    try:
        from src.engine import no_feed_registry  # type: ignore[attr-defined]
    except ImportError as exc:  # pragma: no cover - Red 단계 경로
        pytest.fail(
            "cycle252 §2 — 신규 leaf `src/engine/no_feed_registry.py` 미존재. "
            f"import 실패: {exc}"
        )
    return no_feed_registry


@pytest.fixture
def reg():
    """매 테스트 전/후 모듈 전역 상태 초기화."""
    mod = _registry()
    reset = getattr(mod, "reset_state_for_test", None)
    assert callable(reset), (
        "cycle252 §2 — `reset_state_for_test()` 미정의. 모듈 전역 상태를 쓰는 leaf 는 "
        "테스트 격리 seam 이 필수다."
    )
    reset()
    yield mod
    reset()


class _Spy:
    """`stock_master.get_nxt_tradable_map` 대역 — 호출 인자/횟수 기록."""

    def __init__(self, mapping: dict | None = None, raises: Exception | None = None):
        self.mapping = mapping if mapping is not None else {}
        self.raises = raises
        self.calls: list[list[str]] = []

    async def __call__(self, tickers):
        self.calls.append(list(tickers))
        if self.raises is not None:
            raise self.raises
        # 요청 ticker 전부를 키로 반환하는 것이 DB 계약(D2) — 대역도 동일하게 흉내낸다.
        return {t: self.mapping.get(t) for t in tickers}


def _install_spy(monkeypatch, spy: _Spy) -> None:
    import src.db.stock_master as sm_mod

    monkeypatch.setattr(sm_mod, "get_nxt_tradable_map", spy, raising=False)


def _pin_mono(monkeypatch, reg, holder: list[float]) -> None:
    """`time.monotonic` seam(`_now_mono`) 을 리스트 셀로 고정."""
    assert hasattr(reg, "_now_mono"), (
        "cycle252 §2 — `time.monotonic` 은 모듈 전역 `_now_mono` seam 이어야 한다 "
        "(TTL 경과를 벽시계 없이 검증하기 위한 유일한 결정론 seam)."
    )
    monkeypatch.setattr(reg, "_now_mono", lambda: holder[0])


# ===========================================================================
# R1 — 첫 호출: 조회 1회 · False 만 no_feed · known 은 요청 전부
# ===========================================================================
async def test_r1_first_call_queries_once_and_classifies(reg, monkeypatch):
    """`False` 만 no_feed. `True`·`None`(마스터 부재) 은 no_feed 가 **아니다**.

    `None` 을 no_feed 로 분류하면 마스터 적재 전 부팅 구간에서 전 종목이 재등록
    제외 대상이 되어(= 사실상 fail-closed) 진짜 세션 결함을 못 고친다.
    """
    spy = _Spy({"003490": False, "005930": True})  # 000815 는 마스터 부재(None)
    _install_spy(monkeypatch, spy)
    _pin_mono(monkeypatch, reg, [1_000.0])

    await reg.ensure_fresh(["005930", "003490", "000815"])

    assert len(spy.calls) == 1, f"첫 호출은 조회 1회 — actual={len(spy.calls)}"
    assert spy.calls[0] == ["000815", "003490", "005930"], (
        "인자는 `sorted(tickers)` — 정렬 고정이 SQL 캐시/로그 재현성의 전제 "
        f"(actual={spy.calls[0]})"
    )
    assert reg.is_no_feed("003490") is True, "nxt_tradable=False → no_feed"
    assert reg.is_no_feed("005930") is False, "nxt_tradable=True → no_feed 아님"
    assert reg.is_no_feed("000815") is False, (
        "마스터 부재(None) → no_feed 아님 (fail-open — 모르면 현행 churn 유지)"
    )
    assert reg.snapshot() == frozenset({"003490"}), (
        f"snapshot() 은 no_feed 집합만 — actual={reg.snapshot()}"
    )


# ===========================================================================
# R2 — TTL 내 재호출(known 부분집합) = 조회 0
# ===========================================================================
async def test_r2_within_ttl_known_subset_does_not_requery(reg, monkeypatch):
    """120s 주기 hot path 에서 DB 를 매번 때리면 안 된다 — TTL 600s 캐시."""
    spy = _Spy({"003490": False, "005930": True})
    _install_spy(monkeypatch, spy)
    mono = [1_000.0]
    _pin_mono(monkeypatch, reg, mono)

    await reg.ensure_fresh(["003490", "005930"])
    assert len(spy.calls) == 1

    mono[0] = 1_000.0 + 599.0  # ttl(600s) 미경과
    await reg.ensure_fresh(["003490"])          # known 부분집합
    await reg.ensure_fresh(["003490", "005930"])  # known 전체

    assert len(spy.calls) == 1, (
        f"ttl 내 known 부분집합 재호출은 조회 0 — actual={len(spy.calls)}"
    )
    assert reg.is_no_feed("003490") is True


# ===========================================================================
# R3 — 미지 ticker 가 섞이면 TTL 내라도 즉시 재조회 (전체 tickers 로)
# ===========================================================================
async def test_r3_unknown_ticker_forces_requery_with_full_set(reg, monkeypatch):
    """유니버스는 `_scan_loop` 마다 바뀐다 — 신규 종목이 TTL 만료까지 미분류로
    남으면 그동안 churn 이 그대로 돈다. 미지 ticker 는 즉시 재조회 트리거다.
    """
    spy = _Spy({"003490": False, "005930": True, "079650": False})
    _install_spy(monkeypatch, spy)
    mono = [500.0]
    _pin_mono(monkeypatch, reg, mono)

    await reg.ensure_fresh(["003490", "005930"])
    assert len(spy.calls) == 1

    mono[0] = 500.0 + 10.0  # ttl 한참 이내
    await reg.ensure_fresh(["003490", "005930", "079650"])

    assert len(spy.calls) == 2, (
        f"미지 ticker(079650) 유입 = 즉시 재조회 — actual={len(spy.calls)}"
    )
    assert spy.calls[1] == ["003490", "005930", "079650"], (
        "재조회 인자는 미지분만이 아니라 **전체 tickers**(sorted) — 부분 조회는 "
        f"`_known` 을 쪼개 다음 사이클을 또 미지로 만든다. actual={spy.calls[1]}"
    )
    assert reg.is_no_feed("079650") is True


# ===========================================================================
# R4 — TTL 경과 = 조회 1회
# ===========================================================================
async def test_r4_ttl_elapsed_requeries(reg, monkeypatch):
    """`stock_master` 는 16:15 일괄 갱신 + 07:5x eager 갱신 — NXT 편출(064550 형)이
    반영되려면 캐시가 만료돼야 한다.
    """
    spy = _Spy({"064550": True})
    _install_spy(monkeypatch, spy)
    mono = [0.0]
    _pin_mono(monkeypatch, reg, mono)

    await reg.ensure_fresh(["064550"])
    assert reg.is_no_feed("064550") is False

    spy.mapping = {"064550": False}  # NXT 편출 반영
    mono[0] = 601.0                  # ttl(600s) 경과
    await reg.ensure_fresh(["064550"])

    assert len(spy.calls) == 2, f"ttl 경과 = 재조회 — actual={len(spy.calls)}"
    assert reg.is_no_feed("064550") is True, "재조회 결과가 집합에 반영돼야 한다"


async def test_r4b_ttl_boundary_is_inclusive(reg, monkeypatch):
    """경과 == ttl 정각도 재조회(>= 비교) — `>` 면 정각 표본이 영원히 stale."""
    spy = _Spy({"003490": False})
    _install_spy(monkeypatch, spy)
    mono = [0.0]
    _pin_mono(monkeypatch, reg, mono)

    await reg.ensure_fresh(["003490"])
    mono[0] = 600.0
    await reg.ensure_fresh(["003490"])

    assert len(spy.calls) == 2, (
        f"경과 600.0 == ttl 600.0 은 재조회(>=) — actual={len(spy.calls)}"
    )


# ===========================================================================
# R5 — 조회 예외: 이전 집합 유지 · WARNING 1회/일 · `_loaded_mono` 미갱신
# ===========================================================================
async def test_r5_refresh_failure_keeps_previous_set_and_warns_once_per_day(
    reg, monkeypatch, caplog
):
    """DB 실패는 **조용히 지나가면 안 되고**(관측 소실) **집합을 지워도 안 된다**.

    - 집합을 비우면 그날 no_feed 판정이 전부 풀려 churn 이 되살아난다(잡음 폭증).
    - `_loaded_mono` 를 갱신하면 실패가 성공처럼 굳어 TTL 동안 재시도가 없다.
    - 로그는 1회/일 — 120s 주기 × 실패 지속 = 하루 360행 폭주 차단.
    """
    spy_ok = _Spy({"003490": False, "005930": True})
    _install_spy(monkeypatch, spy_ok)
    mono = [0.0]
    _pin_mono(monkeypatch, reg, mono)

    with freeze_time("2026-09-07 10:00:00+09:00"):
        await reg.ensure_fresh(["003490", "005930"])
    assert reg.snapshot() == frozenset({"003490"})

    spy_bad = _Spy(raises=RuntimeError("pg down"))
    _install_spy(monkeypatch, spy_bad)
    caplog.set_level(logging.DEBUG)

    with freeze_time("2026-09-07 10:02:00+09:00"):
        mono[0] = 601.0
        await reg.ensure_fresh(["003490", "005930"])   # 실패 #1 → WARNING
        mono[0] = 602.0
        await reg.ensure_fresh(["003490", "005930"])   # 실패 #2 → 무로그

    # (a) 예외 전파 0 — 위 await 가 raise 하지 않았다는 사실 자체가 단언
    # (b) 이전 집합 유지
    assert reg.snapshot() == frozenset({"003490"}), (
        f"조회 실패 시 이전 집합 유지 — actual={reg.snapshot()}"
    )
    assert reg.is_no_feed("003490") is True
    assert reg.is_no_feed("005930") is False

    # (c) `_loaded_mono` 미갱신 = 다음 호출에서 즉시 재시도
    assert len(spy_bad.calls) == 2, (
        "실패는 `_loaded_mono` 를 갱신하지 않는다 → 다음 호출도 조회 시도. "
        f"actual={len(spy_bad.calls)}"
    )

    # (d) WARNING 1회/일
    warns = [
        r for r in caplog.records
        if _MARKER in r.getMessage() and r.levelno >= logging.WARNING
    ]
    assert len(warns) == 1, (
        f"{_MARKER} 는 하루 1회 (levelno>=WARNING) — actual={len(warns)} "
        f"msgs={[r.getMessage() for r in caplog.records if _MARKER in r.getMessage()]}"
    )

    # (e) 날짜 키 자기 리셋 — 다음 날 다시 1회
    caplog.clear()
    with freeze_time("2026-09-08 09:10:00+09:00"):
        mono[0] = 700.0
        await reg.ensure_fresh(["003490", "005930"])

    warns_d2 = [
        r for r in caplog.records
        if _MARKER in r.getMessage() and r.levelno >= logging.WARNING
    ]
    assert len(warns_d2) == 1, (
        f"날짜 키 변경 시 cap 자기 리셋 → 다시 1회 — actual={len(warns_d2)}"
    )


async def test_r5b_first_call_failure_leaves_empty_set_fail_open(reg, monkeypatch):
    """부팅 직후 첫 조회가 실패하면 집합은 **빈 채로** 남는다 = 전 종목 현행 churn.

    §1 D3 fail-open — "모르면 막지 않는다".
    """
    _install_spy(monkeypatch, _Spy(raises=RuntimeError("boom")))
    _pin_mono(monkeypatch, reg, [0.0])

    await reg.ensure_fresh(["003490"])

    assert reg.snapshot() == frozenset(), (
        f"첫 조회 실패 = 빈 집합 유지(fail-open) — actual={reg.snapshot()}"
    )
    assert reg.is_no_feed("003490") is False


# ===========================================================================
# R6 — 빈 tickers = 조회 0 · 집합 유지
# ===========================================================================
async def test_r6_empty_tickers_is_noop(reg, monkeypatch):
    """`get_subscribed_tickers()` 가 빈 경우 호출부는 이미 return 하지만,
    레지스트리 자체도 빈 입력에 DB 를 때리지 않고 **집합을 지우지 않는다**.
    """
    spy = _Spy({"003490": False})
    _install_spy(monkeypatch, spy)
    mono = [0.0]
    _pin_mono(monkeypatch, reg, mono)

    await reg.ensure_fresh(["003490"])
    assert len(spy.calls) == 1

    mono[0] = 10_000.0  # ttl 한참 경과 — 그래도 빈 입력이면 조회 0
    await reg.ensure_fresh([])
    await reg.ensure_fresh(set())

    assert len(spy.calls) == 1, (
        f"빈 tickers = 조회 0 — actual={len(spy.calls)}"
    )
    assert reg.snapshot() == frozenset({"003490"}), (
        "빈 입력이 기존 집합을 지우면 안 된다 (churn 재발) — "
        f"actual={reg.snapshot()}"
    )


# ===========================================================================
# R7 — reset_state_for_test() 후 전부 초기
# ===========================================================================
async def test_r7_reset_state_for_test_clears_everything(reg, monkeypatch):
    spy = _Spy({"003490": False, "005930": True})
    _install_spy(monkeypatch, spy)
    mono = [0.0]
    _pin_mono(monkeypatch, reg, mono)

    await reg.ensure_fresh(["003490", "005930"])
    assert reg.snapshot() == frozenset({"003490"})

    reg.reset_state_for_test()

    assert reg.snapshot() == frozenset(), "reset 후 no_feed 집합 초기화"
    assert reg.is_no_feed("003490") is False, "reset 후 판정도 초기화"

    # `_known`/`_loaded_mono` 도 초기화 = 같은 ticker 라도 재조회가 일어난다
    await reg.ensure_fresh(["003490"])
    assert len(spy.calls) == 2, (
        "reset 은 `_known`/`_loaded_mono` 까지 초기화 — 재조회 발생 의무. "
        f"actual={len(spy.calls)}"
    )


# ===========================================================================
# R7b — 공개 API 표면 (스펙 §2 계약)
# ===========================================================================
def test_r7b_public_api_surface(reg):
    for name in ("ensure_fresh", "is_no_feed", "snapshot", "reset_state_for_test"):
        assert hasattr(reg, name), f"cycle252 §2 — 공개 API `{name}` 미정의"
    assert isinstance(reg.snapshot(), frozenset), (
        "`snapshot()` 은 frozenset (호출자가 내부 집합을 변조하지 못하게)"
    )
