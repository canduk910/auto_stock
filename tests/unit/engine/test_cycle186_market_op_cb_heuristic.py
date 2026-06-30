"""사이클 186 (2026-06-29) — 장운영상태 서킷브레이커 휴리스틱 Red 가드.

`src/engine/market_operation_monitor.py` 신규 *추가만* (기존 추적/`is_ticker_stale_excluded` 불변):
- `get_circuit_breaker_state() -> dict` 휴리스틱 (R 키워드 OR W 비율)
- `get_market_op_state_summary()` 확장 (circuit_breaker + iscd_stat_active_count)
- `record_market_op_event` CB 휴리스틱 첫 발화 시 계측 로그 1회/일 cap

관찰성 전용 — 매수 가드 X. CB 중엔 KRX 가 주문 자연 거부 → 매매 로직 변경 0.
승인 계획: `~/.claude/plans/hazy-prancing-cookie.md`.

Red 가드 매트릭스:
- CB-KEYWORD: 거래정지 사유 "서킷브레이커" → suspected=True + 키워드 근거
- CB-RATIO: observed=14 / halted=12 (86% ≥ 80%, ≥5) → suspected=True
- CB-NO-FALSE-POSITIVE (SAFETY): halted=2/observed=10 + 키워드 무 → suspected=False
- CB-REPRESENTATIVE: 005930 mkop_cls_code 노출 (계측)
- SUMMARY-EXT: summary 에 circuit_breaker + iscd_stat_active_count 키
- INSTRUMENT-CAP: CB 휴리스틱 발화 로그 1회/일 cap (반복 record → 1행)
- SAFETY-STALE-UNCHANGED (HIGH): is_ticker_stale_excluded + VI/halt set 갱신 불변
"""

from __future__ import annotations

import ast
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

from src.api.market_operation import MarketOpEvent
from src.engine import market_operation_monitor as mom


KST = timezone(timedelta(hours=9))

_MODULE_PATH = (
    Path(__file__).resolve().parents[3]
    / "src"
    / "engine"
    / "market_operation_monitor.py"
)

_CB_LOG_PREFIX = "[market_op_cb_suspected]"


def _make_event(
    ticker: str = "005930",
    *,
    trht_yn: str = "N",
    tr_susp_reas_cntt: str = "",
    mkop_cls_code: str = "110",
    vi_cls_code: str = "0",
    ovtm_vi_cls_code: str = "0",
    iscd_stat_cls_code: str = "0",
) -> MarketOpEvent:
    return MarketOpEvent(
        ticker=ticker,
        trht_yn=trht_yn,
        tr_susp_reas_cntt=tr_susp_reas_cntt,
        mkop_cls_code=mkop_cls_code,
        antc_mkop_cls_code="110",
        mrkt_trtm_cls_code="0",
        divi_app_cls_code="0",
        iscd_stat_cls_code=iscd_stat_cls_code,
        vi_cls_code=vi_cls_code,
        ovtm_vi_cls_code=ovtm_vi_cls_code,
        exch_cls_code="KRX",
        received_at=datetime.now(KST),
    )


@pytest.fixture(autouse=True)
def _reset_state():
    """일일 상태 + CB 계측 cap 초기화.

    `reset_market_op_state()` 는 _reset_daily_state 동행 clear 로
    VI/halt/last_event 3 dict + CB 계측 cap 까지 일괄 초기화 의무 (사이클 186 계약).
    """
    mom.reset_market_op_state()
    yield
    mom.reset_market_op_state()


# ==================== CB 휴리스틱 ====================


def test_cb_keyword_circuit_breaker_reason_suspected() -> None:
    """CB-KEYWORD — 거래정지 사유에 "서킷브레이커" → suspected=True + 키워드 근거.

    halted=1 (< _CB_MIN_HALTED=5) → 비율 경로 미발화 = 키워드 경로 단독 검증.
    """
    mom.record_market_op_event(
        _make_event("000020", trht_yn="Y", tr_susp_reas_cntt="서킷브레이커 발동")
    )

    state = mom.get_circuit_breaker_state()

    assert state["suspected"] is True
    assert isinstance(state["reasons"], list) and state["reasons"], "키워드 근거 reasons 누락"
    assert any(("서킷" in r) or ("키워드" in r) for r in state["reasons"]), (
        f"키워드 매칭 근거 부재 — reasons={state['reasons']}"
    )


def test_cb_ratio_mass_halt_suspected() -> None:
    """CB-RATIO — observed=14 / halted=12 (86% ≥ 80%, ≥5) → suspected=True (키워드 무)."""
    for i in range(12):
        mom.record_market_op_event(_make_event(f"{600000 + i:06d}", trht_yn="Y"))
    for i in range(2):
        mom.record_market_op_event(_make_event(f"{700000 + i:06d}", trht_yn="N"))

    state = mom.get_circuit_breaker_state()

    assert state["halted"] == 12
    assert state["observed"] == 14
    assert state["halt_ratio"] == pytest.approx(12 / 14, abs=1e-6)
    assert state["suspected"] is True
    # 전 시장 거래정지 비율 근거 (예: "전 시장 거래정지 12/14 (86%)")
    assert any(("%" in r) or ("12/14" in r) for r in state["reasons"]), (
        f"비율 급증 근거 부재 — reasons={state['reasons']}"
    )


def test_cb_no_false_positive_minority_halt(caplog) -> None:
    """CB-NO-FALSE-POSITIVE (SAFETY) — halted=2/observed=10 + 키워드 무 → suspected=False.

    개별 거래정지를 CB 로 오판 0건 (운영자 오인 차단).
    """
    for i in range(2):
        mom.record_market_op_event(_make_event(f"{600000 + i:06d}", trht_yn="Y"))
    for i in range(8):
        mom.record_market_op_event(_make_event(f"{700000 + i:06d}", trht_yn="N"))

    state = mom.get_circuit_breaker_state()

    assert state["halted"] == 2
    assert state["observed"] == 10
    assert state["suspected"] is False, "소수 거래정지를 CB 로 오판 — false-positive"


def test_cb_representative_mkop_cls_code_exposed() -> None:
    """CB-REPRESENTATIVE — 005930 대표 종목 mkop_cls_code 계측 노출."""
    mom.record_market_op_event(_make_event("005930", mkop_cls_code="121"))

    state = mom.get_circuit_breaker_state()
    assert state["representative_mkop_cls_code"] == "121"


def test_cb_representative_empty_when_005930_absent() -> None:
    """CB-REPRESENTATIVE — 005930 미수신 시 빈 문자열 graceful."""
    mom.record_market_op_event(_make_event("000660", mkop_cls_code="110"))

    state = mom.get_circuit_breaker_state()
    assert state["representative_mkop_cls_code"] == ""


def test_cb_halt_reasons_sample_distinct_nonempty() -> None:
    """CB-RATIO 보조 — halt_reasons_sample = distinct 비어있지 않은 사유 최대 5."""
    mom.record_market_op_event(
        _make_event("000020", trht_yn="Y", tr_susp_reas_cntt="서킷브레이커 발동")
    )
    mom.record_market_op_event(
        _make_event("000030", trht_yn="Y", tr_susp_reas_cntt="")  # 빈 사유 제외
    )

    state = mom.get_circuit_breaker_state()
    sample = state["halt_reasons_sample"]
    assert isinstance(sample, list)
    assert "" not in sample, "빈 문자열 사유는 sample 제외 의무"
    assert "서킷브레이커 발동" in sample
    assert len(sample) <= 5


# ==================== summary 확장 ====================


def test_summary_ext_circuit_breaker_and_iscd_stat_keys() -> None:
    """SUMMARY-EXT — summary 에 circuit_breaker + iscd_stat_active_count 키 + 기존 5키 보존."""
    # iscd_stat 이상 (정지/관리 상태) 1건
    mom.record_market_op_event(_make_event("005930", iscd_stat_cls_code="51"))

    summary = mom.get_market_op_state_summary()

    # 기존 5 키 보존
    for key in (
        "vi_active_count",
        "halt_active_count",
        "last_event_count",
        "vi_active_sample",
        "halt_active_sample",
    ):
        assert key in summary, f"기존 summary 키 소실 — {key}"

    # 신규 2 키
    assert "circuit_breaker" in summary, "circuit_breaker 키 누락"
    assert isinstance(summary["circuit_breaker"], dict)
    assert "suspected" in summary["circuit_breaker"]

    assert "iscd_stat_active_count" in summary, "iscd_stat_active_count 키 누락"
    assert summary["iscd_stat_active_count"] >= 1


# ==================== 계측 로그 cap ====================


def test_instrument_cap_cb_log_emitted_once_per_day(caplog) -> None:
    """INSTRUMENT-CAP — CB 휴리스틱 발화 로그 1회/일 cap (반복 record → 1행)."""
    with caplog.at_level(logging.INFO, logger="src.engine.market_operation_monitor"):
        # CB 발화 (키워드) 이벤트 반복 record
        mom.record_market_op_event(
            _make_event("000020", trht_yn="Y", tr_susp_reas_cntt="서킷브레이커 발동")
        )
        mom.record_market_op_event(
            _make_event("000020", trht_yn="Y", tr_susp_reas_cntt="서킷브레이커 발동")
        )
        mom.record_market_op_event(
            _make_event("000030", trht_yn="Y", tr_susp_reas_cntt="매매거래중단")
        )

    cb_logs = [
        r for r in caplog.records if r.getMessage().startswith(_CB_LOG_PREFIX)
    ]
    assert len(cb_logs) == 1, (
        f"CB 계측 로그 cap 위반 — {len(cb_logs)}행 (1행 의무, 폭주 차단)"
    )


# ==================== SAFETY — 기존 stale-skip 행위 불변 ====================


def test_safety_stale_excluded_behavior_unchanged() -> None:
    """SAFETY-STALE-UNCHANGED (HIGH) — VI/halt set 갱신 + is_ticker_stale_excluded 불변.

    사이클 149 stale 회피 행위 보존 (record_market_op_event 후 vi/halt set 정확).
    """
    mom.record_market_op_event(_make_event("005930", vi_cls_code="1"))
    mom.record_market_op_event(_make_event("000020", trht_yn="Y"))
    mom.record_market_op_event(_make_event("000660", vi_cls_code="0", trht_yn="N"))

    # VI/halt set 정확 (사이클 149 영속)
    assert "005930" in mom.get_vi_active_tickers()
    assert "000020" in mom.get_halt_active_tickers()

    # stale 회피 hook 불변
    assert mom.is_ticker_stale_excluded("005930") is True  # VI 활성
    assert mom.is_ticker_stale_excluded("000020") is True  # 거래정지
    assert mom.is_ticker_stale_excluded("000660") is False  # 정상
    assert mom.is_ticker_stale_excluded("999999") is False  # 미수신


def test_safety_ast_signatures_and_set_update_lines_unchanged() -> None:
    """SAFETY-STALE-UNCHANGED (HIGH) AST — 시그너처 + VI/halt 판정 라인 불변.

    backend-dev 가 CB 추가 시 기존 stale-skip 로직을 건드리지 않도록 정적 가드.
    """
    source = _MODULE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)

    funcs = {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }

    # 시그너처 불변
    assert "is_ticker_stale_excluded" in funcs, "is_ticker_stale_excluded 소실"
    stale_args = [a.arg for a in funcs["is_ticker_stale_excluded"].args.args]
    assert stale_args == ["ticker"], f"is_ticker_stale_excluded 시그너처 변경 — {stale_args}"

    assert "record_market_op_event" in funcs, "record_market_op_event 소실"
    rec_args = [a.arg for a in funcs["record_market_op_event"].args.args]
    assert rec_args == ["event"], f"record_market_op_event 시그너처 변경 — {rec_args}"

    # VI/halt set 갱신 라인 불변 (사이클 149 영속)
    for needle in (
        "_vi_active_tickers.add",
        "_vi_active_tickers.discard",
        "_halt_active_tickers.add",
        "_halt_active_tickers.discard",
    ):
        assert needle in source, f"VI/halt set 갱신 라인 소실 — {needle}"
