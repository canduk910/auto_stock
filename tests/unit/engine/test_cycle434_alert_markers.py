"""사이클 434 — 대시보드 경고등 명부 + 순수 집계(`src/engine/alert_markers.py`).

사용자 지시(2026-10-10): "잔고/권리 불일치 등 일일작업 작업오류 발생 시 대시보드에
경고등 추가". 이 파일은 `GET /api/system/alerts` 가 참조하는 명부·집계 함수의 단위
계약을 검증한다(DB 무접촉 — 순수 함수).

요구 행위:
- A. `CATEGORIES` 3범주(장부 불일치=red · 주문 결과 모름/청산 실패=red · 일일 작업
     실패=yellow), 각 `AlertCategory(key, label, color)`.
- B. `categorize(message)` — 명부 패턴에 걸리면 그 범주 key, 아니면 `None`.
- C. `build_summary(rows, as_of_iso=...)` — 범주별 count/max_level/first_at/last_at/
     recent_messages 집계 + 전체 `status`(red>yellow>green).
- D. `unknown_summary(as_of_iso)` — 전부 모름, `status == "unknown"`.
- E. 패턴은 `_DbLogHandler` 의 `[record.name] message` 이중 래핑에도 걸린다(포함 매칭).
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


def _import():
    from src.engine import alert_markers as _mod
    return _mod


# ---------------------------------------------------------------------------
# A. 명부 구조
# ---------------------------------------------------------------------------
def test_categories_are_three_with_expected_colors():
    m = _import()
    keys = {c.key: c.color for c in m.CATEGORIES}
    assert keys == {
        "ledger_mismatch": "red",
        "order_unknown_or_exit_failure": "red",
        "daily_job_failure": "yellow",
    }


def test_all_patterns_nonempty_and_deduped():
    m = _import()
    assert len(m.ALL_PATTERNS) > 0
    assert len(m.ALL_PATTERNS) == len(set(m.ALL_PATTERNS))


# ---------------------------------------------------------------------------
# B. categorize()
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "message,expected_category",
    [
        (
            "[holding_qty_unexplained] ticker=005930 tracked=10 kis=8 delta=-2 phase=midsync",
            "ledger_mismatch",
        ),
        (
            "[corporate_action_ctrga_reconciled] result=mismatch ticker=005930 bass_dt=20261001",
            "ledger_mismatch",
        ),
        (
            "[corporate_action_ctrga_reconciled] result=match ticker=005930 bass_dt=20261001",
            None,  # match 는 불일치가 아니다 — 명부가 걸면 안 된다
        ),
        ("[corporate_action_ctrga_merger_held] ticker=005930 bass_dt=20261001 rght_type_cd=11", "ledger_mismatch"),
        ("[sell_insufficient_unexplained] ticker=005930 strategy=kojiro ...", "ledger_mismatch"),
        ("[boot_recover_strategy_unknown] path=kis_supplement ticker=005930 order_no=", "ledger_mismatch"),
        ("[buy_fill_fallback_orphan] order_no=123 ticker=005930 신규 포지션 등록됨", "ledger_mismatch"),
        ("[no_feed_held] ticker=005930 strategy=momentum", "ledger_mismatch"),
        ("[sell_send_unknown] ticker=005930 strategy=momentum path=primary exc=TimeoutError", "order_unknown_or_exit_failure"),
        ("[force_clear_ticker_error] ticker=005930 strategy=momentum err=ValueError", "order_unknown_or_exit_failure"),
        ("[sell_post_send_error] ticker=005930 order_no=1 strategy=momentum path=x", "order_unknown_or_exit_failure"),
        ("[buy_post_send_error] ticker=005930 order_no=1 strategy=momentum path=x qty=1 price=1", "order_unknown_or_exit_failure"),
        ("매도 주문 최종 실패: 005930 SELL — RuntimeError", "order_unknown_or_exit_failure"),
        ("[after_exit_giveup] ticker=005930 fails=5 next_day_clear=1", "order_unknown_or_exit_failure"),
        ("[status_exit_giveup] ticker=005930 strategy=momentum fires=3", "order_unknown_or_exit_failure"),
        ("20:00 전략수정 AI자문 생성 실패: type=TimeoutError msg=x trace=y", "daily_job_failure"),
        ("AI 자문 자동 적용 실패: TimeoutError: x", "daily_job_failure"),
        ("[daily_metrics_snapshot_failed] target_date=2026-10-10", "daily_job_failure"),
        ("[stock_master_daily_load] 초기 실행 예외 graceful", "daily_job_failure"),
        ("[stock_master_daily_load] task loop 예외 graceful", "daily_job_failure"),
        ("일일 로그 분석 리포트 생성 실패: type=TimeoutError", "daily_job_failure"),
        ("[trade_cost_reconcile_failed] reason=timeout limit_s=60 today=2026-10-10", "daily_job_failure"),
        ("[daily_head_stale] max_bas_dd=2026-10-08 expected=2026-10-09", "daily_job_failure"),
        ("[daily_bar_finalize] phase=boot mode=x result=error head= since=", "daily_job_failure"),
        ("아무 관계 없는 평범한 INFO 로그", None),
    ],
)
def test_categorize_matches_manifest(message, expected_category):
    m = _import()
    assert m.categorize(message) == expected_category


def test_categorize_matches_through_db_log_handler_module_prefix_wrapping():
    """`_DbLogHandler` 가 `f"[{record.name}] {message}"` 로 한 번 더 감싸도 걸린다."""
    m = _import()
    wrapped = "[src.engine.order_engine] [sell_insufficient_unexplained] ticker=005930 ..."
    assert m.categorize(wrapped) == "ledger_mismatch"


def test_categorize_empty_message_returns_none():
    m = _import()
    assert m.categorize("") is None


# ---------------------------------------------------------------------------
# C. build_summary()
# ---------------------------------------------------------------------------
def test_build_summary_empty_rows_is_green():
    m = _import()
    out = m.build_summary([], as_of_iso="2026-10-10T12:00:00+09:00")
    assert out["status"] == "green"
    assert out["as_of"] == "2026-10-10T12:00:00+09:00"
    assert len(out["categories"]) == 3
    for c in out["categories"]:
        assert c["count"] == 0
        assert c["max_level"] is None
        assert c["first_at"] is None
        assert c["last_at"] is None
        assert c["recent_messages"] == []


def test_build_summary_red_wins_over_yellow():
    m = _import()
    rows = [
        {
            "log_level": "WARNING",
            "message": "[stock_master_daily_load] 초기 실행 예외 graceful",
            "timestamp": "2026-10-10T20:30:00+09:00",
        },
        {
            "log_level": "CRITICAL",
            "message": "[holding_qty_unexplained] ticker=005930 ...",
            "timestamp": "2026-10-10T21:30:00+09:00",
        },
    ]
    out = m.build_summary(rows, as_of_iso="2026-10-10T22:00:00+09:00")
    assert out["status"] == "red"
    by_key = {c["key"]: c for c in out["categories"]}
    assert by_key["ledger_mismatch"]["count"] == 1
    assert by_key["ledger_mismatch"]["max_level"] == "CRITICAL"
    assert by_key["daily_job_failure"]["count"] == 1
    assert by_key["order_unknown_or_exit_failure"]["count"] == 0


def test_build_summary_first_last_at_and_max_level_accumulate():
    m = _import()
    rows = [
        {"log_level": "ERROR", "message": "[sell_send_unknown] a", "timestamp": "2026-10-10T10:00:00+09:00"},
        {"log_level": "WARNING", "message": "[sell_send_unknown] b", "timestamp": "2026-10-10T09:00:00+09:00"},
        {"log_level": "CRITICAL", "message": "[sell_send_unknown] c", "timestamp": "2026-10-10T15:00:00+09:00"},
    ]
    out = m.build_summary(rows, as_of_iso="2026-10-10T16:00:00+09:00")
    cat = next(c for c in out["categories"] if c["key"] == "order_unknown_or_exit_failure")
    assert cat["count"] == 3
    assert cat["max_level"] == "CRITICAL"
    assert cat["first_at"] == "2026-10-10T09:00:00+09:00"
    assert cat["last_at"] == "2026-10-10T15:00:00+09:00"


def test_build_summary_recent_messages_capped():
    m = _import()
    rows = [
        {"log_level": "WARNING", "message": f"[no_feed_held] ticker={i}", "timestamp": f"2026-10-10T0{i}:00:00+09:00"}
        for i in range(9)
    ]
    out = m.build_summary(rows, as_of_iso="2026-10-10T12:00:00+09:00", recent_limit=5)
    cat = next(c for c in out["categories"] if c["key"] == "ledger_mismatch")
    assert cat["count"] == 9
    assert len(cat["recent_messages"]) == 5


def test_build_summary_ignores_unmatched_rows():
    m = _import()
    rows = [{"log_level": "ERROR", "message": "그냥 평범한 에러", "timestamp": "2026-10-10T10:00:00+09:00"}]
    out = m.build_summary(rows, as_of_iso="2026-10-10T12:00:00+09:00")
    assert out["status"] == "green"
    assert all(c["count"] == 0 for c in out["categories"])


# ---------------------------------------------------------------------------
# D. unknown_summary()
# ---------------------------------------------------------------------------
def test_unknown_summary_status_and_shape():
    m = _import()
    out = m.unknown_summary("2026-10-10T12:00:00+09:00")
    assert out["status"] == "unknown"
    assert len(out["categories"]) == 3
    for c in out["categories"]:
        assert c["count"] is None
        assert c["max_level"] is None
