"""사이클 28 Red (2026-05-21) — `WebsocketPool.get_subscriptions_by_session()` 헬퍼.

배경:
- 2026-05-21 09:13 VB 돌파 미매수 정밀 진단 부수 발견 — stale 16/30 (53%) 가 메인/보조
  어느 세션에 분산되어 있는지 알 수 없어 분산 로직 점검 불가.
- `_ticker_to_session: dict[str, KisWebSocket]` 은 이미 존재. 본 헬퍼는 *역인덱싱* 만 — 신규
  영속 dict 추가 금지 (G — 명세 §2).

검증 사양 (`_workspace/cycle28_stale_subscription_tracing_spec.md` §5.1):

1. `get_subscriptions_by_session() -> dict[str, set[str]]` 시그니처
2. 메인 only — `{"main": {ticker1, ticker2, ...}}` 반환
3. 메인 + 보조 1개 → 각 라벨별 분리 반환
4. 매핑이 0건 → 빈 dict
5. 세션 객체가 풀에서 제거됐는데 매핑 잔류 → "unknown" 라벨로 묶음 (G4 보조 미등록 환경 + race 대응)
6. _ticker_to_session 외 신규 영속 dict 추가 금지 (인스턴스 attribute 추가 0건 가드)
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

pytestmark = pytest.mark.unit


@pytest.fixture
def fresh_pool():
    """매 테스트마다 격리된 WebsocketPool — 메인 세션 mock 으로 교체."""
    from src.realtime.websocket_pool import WebsocketPool

    pool = WebsocketPool()
    main_mock = MagicMock(name="main-session")
    main_mock._subscriptions = set()
    pool._main = main_mock
    return pool


def test_get_subscriptions_by_session_signature(fresh_pool):
    """헬퍼가 존재하고 dict[str, set[str]] 형태를 반환한다."""
    pool = fresh_pool
    assert hasattr(pool, "get_subscriptions_by_session"), (
        "WebsocketPool.get_subscriptions_by_session() 헬퍼 미구현"
    )
    result = pool.get_subscriptions_by_session()
    assert isinstance(result, dict)


def test_get_subscriptions_by_session_main_only(fresh_pool):
    """메인 only 케이스 — 모든 ticker 가 'main' 라벨로 묶임."""
    pool = fresh_pool
    # ticker → main 세션 매핑
    pool._ticker_to_session["005930"] = pool._main
    pool._ticker_to_session["000660"] = pool._main
    pool._ticker_to_session["035720"] = pool._main

    result = pool.get_subscriptions_by_session()
    assert result == {"main": {"005930", "000660", "035720"}}


def test_get_subscriptions_by_session_main_and_quote(fresh_pool):
    """메인 + 보조 1개 → 라벨별 분리 set."""
    pool = fresh_pool
    quote1 = MagicMock(name="quote-1")
    quote1._label = "quote-1"  # 사이클 43 (2026-05-22) — label 매칭
    pool._quotes.append(quote1)

    pool._ticker_to_session["005930"] = pool._main
    pool._ticker_to_session["000660"] = pool._main
    pool._ticker_to_session["035720"] = quote1
    pool._ticker_to_session["051910"] = quote1

    result = pool.get_subscriptions_by_session()
    assert result == {
        "main": {"005930", "000660"},
        "quote-1": {"035720", "051910"},
    }


def test_get_subscriptions_by_session_empty(fresh_pool):
    """매핑 0건 → 빈 dict."""
    pool = fresh_pool
    result = pool.get_subscriptions_by_session()
    assert result == {}


def test_get_subscriptions_by_session_unknown_label_for_stale_mapping(fresh_pool):
    """세션이 풀에서 제거됐는데 매핑이 남으면 'unknown' 라벨."""
    pool = fresh_pool
    # 풀에 없는 세션을 매핑 (disable_quote_session 등으로 _quotes 에서 제거된 잔재 케이스)
    stale_session = MagicMock(name="orphan-session")
    pool._ticker_to_session["999999"] = stale_session
    pool._ticker_to_session["005930"] = pool._main

    result = pool.get_subscriptions_by_session()
    assert result.get("unknown") == {"999999"}
    assert result.get("main") == {"005930"}


def test_get_subscriptions_by_session_does_not_add_persistent_dict(fresh_pool):
    """헬퍼는 역인덱싱만 — _ticker_to_session 외 신규 영속 dict 추가하지 않는다.

    호출 전후 인스턴스 속성 set 가 동일해야 한다 (헬퍼가 lazy attr 등록 금지).
    """
    pool = fresh_pool
    quote1 = MagicMock(name="quote-1")
    pool._quotes.append(quote1)
    pool._ticker_to_session["005930"] = pool._main
    pool._ticker_to_session["035720"] = quote1

    attrs_before = set(vars(pool).keys())
    _ = pool.get_subscriptions_by_session()
    attrs_after = set(vars(pool).keys())
    assert attrs_before == attrs_after, (
        f"헬퍼가 신규 속성 등록: {attrs_after - attrs_before}"
    )
