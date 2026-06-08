"""사이클 72 G-D1 ~ G-D3 — `_DbLogHandler` 500ms TTL dedupe 캐시 (Red 단계).

옵션 D (사용자 결정): `_DbLogHandler.emit` 에 500ms TTL dedupe 캐시 도입 —
동일 메시지가 500ms 내 중복 emit 되면 두 번째는 INSERT skip.

옵션 A' (write_log 호출 제거) 와 D 의 결합:
- A': 11 사이트에서 logger + write_log 동시 호출 → logger 단독
- D: logger 의 자동 retry, 모듈간 같은 메시지 중복 emit 등 silent 결함 영구 차단

Red 단계 — `_DbLogHandler.emit` 미구현 → 모두 FAIL (동일 메시지 100ms 내 2 회 emit 시 INSERT 2회).
Green 단계 — 500ms TTL dedupe → 100ms 내 1회 / 600ms 후 2회.

설계 (Green 단계 backend-dev 인계):
- `_DbLogHandler` 인스턴스 변수 `_dedupe_cache: dict[str, float]` (message → expiry monotonic)
- `_DEDUPE_TTL_SECS = 0.5` (500ms)
- `emit()` 진입 직후 `time.monotonic()` 기준 expiry 비교 → 미만이면 skip
- 만료 항목 lazy evict (메모리 폭주 차단)
"""
from __future__ import annotations

import logging
from unittest.mock import patch

import pytest


@pytest.fixture
def db_log_handler():
    """`_DbLogHandler` 인스턴스 + `_insert_log_to_db` 모킹."""
    from src.main import _DbLogHandler
    handler = _DbLogHandler()
    # ThreadPoolExecutor.submit 을 모의 — 실제 DB INSERT 호출 차단
    return handler


def _make_record(message: str, level: int = logging.INFO) -> logging.LogRecord:
    """LogRecord 생성 — record.name 은 `src.*` 로 시작해야 `_DbLogHandler` 처리."""
    return logging.LogRecord(
        name="src.engine.scheduler",
        level=level,
        pathname=__file__,
        lineno=1,
        msg=message,
        args=None,
        exc_info=None,
    )


def test_g_d1_same_message_within_100ms_inserts_once() -> None:
    """G-D1: 동일 메시지 100ms 내 2회 emit → 두 번째 INSERT skip.

    Green 검증: `_insert_log_to_db` 호출 1회.
    Red (현재): 호출 2회 — FAIL.
    """
    from src.main import _DbLogHandler
    handler = _DbLogHandler()

    record1 = _make_record("[ws_heartbeat] label=main window=300s pingpong_recv=22")

    # freezegun + monotonic 패치 — 0.0s 와 0.1s
    monotonic_values = iter([0.0, 0.0, 0.1, 0.1])

    with patch("src.main._LOG_DB_EXECUTOR.submit") as mock_submit, \
         patch("time.monotonic", side_effect=lambda: next(monotonic_values, 0.1)):
        handler.emit(record1)
        handler.emit(record1)  # 100ms 후 동일 메시지 → dedupe skip

    assert mock_submit.call_count == 1, (
        f"동일 메시지 100ms 내 2회 emit → _insert_log_to_db 호출 "
        f"{mock_submit.call_count}회 (기대: 1회 — 500ms TTL dedupe 캐시 필요)"
    )


def test_g_d2_same_message_after_600ms_inserts_twice() -> None:
    """G-D2: 동일 메시지 600ms 후 2회 emit → 두 번째 INSERT 정상.

    Green 검증: `_insert_log_to_db` 호출 2회 (TTL 경과 후 정상 emit).
    Red: 호출 2회 — PASS 가능 (Green 과 동일 결과 — 핵심은 G-D1 차단 후 만료 동작).
    그래도 Red 단계 = `_DEDUPE_TTL_SECS` 상수 미존재 시 FAIL.
    """
    from src.main import _DbLogHandler
    handler = _DbLogHandler()

    record1 = _make_record("[stale_watcher] subscribed=30 stale=2 force_reregistered=2 skipped=0")

    monotonic_values = iter([0.0, 0.0, 0.6, 0.6])

    with patch("src.main._LOG_DB_EXECUTOR.submit") as mock_submit, \
         patch("time.monotonic", side_effect=lambda: next(monotonic_values, 0.6)):
        handler.emit(record1)
        handler.emit(record1)  # 600ms 후 동일 메시지 → TTL 경과 → 정상 INSERT

    # Green: 정확히 2회 (500ms TTL 경과 시 dedupe 해제)
    # Red (현재 _DbLogHandler 미구현 dedupe): 2회 (단순 통과 가능)
    # → Green 단계 의미: TTL 가드 구현 후에도 600ms 후엔 2회 INSERT 보장
    # 이 케이스 Red 단계 FAIL 보장 위해 _DEDUPE_TTL_SECS 상수 존재 확인 추가:
    import src.main as main_mod
    assert hasattr(main_mod, "_DEDUPE_TTL_SECS"), (
        "`_DbLogHandler` dedupe 캐시 TTL 상수 `_DEDUPE_TTL_SECS` 미정의 — "
        "사이클 72 옵션 D 미구현"
    )
    assert main_mod._DEDUPE_TTL_SECS == 0.5, (
        f"_DEDUPE_TTL_SECS={main_mod._DEDUPE_TTL_SECS}, 기대 0.5 (500ms)"
    )
    assert mock_submit.call_count == 2, (
        f"동일 메시지 600ms 후 emit → _insert_log_to_db 호출 "
        f"{mock_submit.call_count}회 (기대: 2회 — TTL 경과 정상 INSERT)"
    )


def test_g_d3_different_messages_both_insert_within_100ms() -> None:
    """G-D3: 다른 메시지 100ms 내 emit → 둘 다 INSERT.

    Green 검증: `_insert_log_to_db` 호출 2회 (메시지 키 dedupe 정확성).
    Red: 호출 2회 — PASS 가능. 핵심: dedupe 키가 "message" 단위인지 정적 확인.
    """
    from src.main import _DbLogHandler
    handler = _DbLogHandler()

    record1 = _make_record("[stale_watcher_detail] session=main sub=30/41 fresh=20 stale=10")
    record2 = _make_record("[stale_watcher_detail] session=ISA sub=12/41 fresh=11 stale=1")

    monotonic_values = iter([0.0, 0.0, 0.05, 0.05])

    with patch("src.main._LOG_DB_EXECUTOR.submit") as mock_submit, \
         patch("time.monotonic", side_effect=lambda: next(monotonic_values, 0.05)):
        handler.emit(record1)
        handler.emit(record2)

    assert mock_submit.call_count == 2, (
        f"다른 메시지 100ms 내 emit → _insert_log_to_db 호출 "
        f"{mock_submit.call_count}회 (기대: 2회 — 메시지별 dedupe 정확)"
    )

    # 추가: dedupe 캐시가 dict 또는 OrderedDict 구조 인스턴스 변수로 존재해야 함
    import src.main as main_mod
    assert hasattr(handler, "_dedupe_cache"), (
        "`_DbLogHandler` 인스턴스 `_dedupe_cache` dict 변수 미존재 — "
        "사이클 72 옵션 D 미구현"
    )
