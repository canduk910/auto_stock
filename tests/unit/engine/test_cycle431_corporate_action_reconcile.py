"""cycle431 — 액면병합·분할 등 "주문 밖 수량 변경" 대사. 순수 판정 leaf 회귀.

사용자 결정 2026-10-10(안1). 자문 =
`_workspace/domain_consult/2026-10-10_corporate_action_qty_reconcile.md`
(회귀 시나리오 표 C1~C21을 가능한 한 이 레벨에서 고정한다).
"""
from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock

import pytest
from freezegun import freeze_time

from src.engine import corporate_action_reconcile as car

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _reset_state():
    car.reset_state_for_test()
    yield
    car.reset_state_for_test()


# ---------------------------------------------------------------------------
# 비율 증거 — 액면교체(C1 분할/C3 병합) · 감자
# ---------------------------------------------------------------------------


def test_ratio_from_face_value_split_increases_quantity():
    # 분할 1:10 — 액면 5000 → 500, r = 5000/500 = 10 (수량 ×10)
    assert car.ratio_from_face_value("000005000", "000000500") == pytest.approx(10.0)


def test_ratio_from_face_value_merge_decreases_quantity():
    # 병합 10:1 — 액면 500 → 5000, r = 500/5000 = 0.1 (수량 ×0.1)
    assert car.ratio_from_face_value("000000500", "000005000") == pytest.approx(0.1)


@pytest.mark.parametrize("old,new", [(0, 100), (100, 0), ("na", "100"), (None, None)])
def test_ratio_from_face_value_invalid_is_none(old, new):
    assert car.ratio_from_face_value(old, new) is None


def test_ratio_from_capital_decrease_requires_multiply_comp_way():
    assert car.ratio_from_capital_decrease(" 0.50", "곱하기") == pytest.approx(0.5)


def test_ratio_from_capital_decrease_other_comp_way_is_none():
    assert car.ratio_from_capital_decrease(" 0.50", "나누기") is None
    assert car.ratio_from_capital_decrease(" 0.50", None) is None


# ---------------------------------------------------------------------------
# 증거 B — 수량·매입가 두 증거
# ---------------------------------------------------------------------------


def test_qty_ratio_matches_floor():
    # 15주, r=0.1 → floor(1.5) = 1
    assert car.qty_ratio_matches(15, 1, 0.1) is True
    assert car.qty_ratio_matches(15, 2, 0.1) is False


def test_avg_price_ratio_matches_within_tolerance():
    # buy_price=1000, r=10 → expected=100, kis_avg=101(1% 이내)
    assert car.avg_price_ratio_matches(1000, 101, 10) is True
    assert car.avg_price_ratio_matches(1000, 120, 10) is False


def test_best_matching_ratio_picks_first_passing_candidate():
    candidates = [
        car.RatioCandidate(r=5.0, source="rev_split"),
        car.RatioCandidate(r=10.0, source="rev_split"),
    ]
    # r=10 이 수량·매입가 둘 다 맞는다(1000주 → 100 == floor(1000*0.1)? 반대 방향 예시로 단순화)
    matched = car.best_matching_ratio(
        candidates, tracked_qty=1, kis_qty=10, tracked_buy_price=1000, kis_avg_price=100,
    )
    assert matched is not None and matched.r == 10.0


def test_best_matching_ratio_none_when_no_candidate_fits():
    candidates = [car.RatioCandidate(r=3.0, source="rev_split")]
    assert car.best_matching_ratio(
        candidates, tracked_qty=1, kis_qty=10, tracked_buy_price=1000, kis_avg_price=100,
    ) is None


# ---------------------------------------------------------------------------
# classify() — 자문 Q1 분류 표
# ---------------------------------------------------------------------------


def test_classify_match_when_quantities_equal():
    v = car.classify(
        tracked_qty=10, kis_qty=10, tracked_buy_price=1000, kis_avg_price=1000,
        ratio_candidates=[],
    )
    assert v.action == "match"


def test_c1_split_applies_scale():
    """C1 — kojiro 1주, 1:10 분할(H=10, KIS 평균 1/10, 액면 5000→500)."""
    candidates = [car.RatioCandidate(r=10.0, source="rev_split", face_value_old=5000, face_value_new=500)]
    v = car.classify(
        tracked_qty=1, kis_qty=10, tracked_buy_price=10_000, kis_avg_price=1_000,
        ratio_candidates=candidates,
    )
    assert v.action == "apply_scale"
    assert v.r == 10.0
    assert v.source == "rev_split"


def test_c3_merge_applies_scale():
    """C3 — donchian 15주, 10:1 병합(H=1, 액면 500→5000)."""
    candidates = [car.RatioCandidate(r=0.1, source="rev_split", face_value_old=500, face_value_new=5000)]
    v = car.classify(
        tracked_qty=15, kis_qty=1, tracked_buy_price=1_000, kis_avg_price=10_000,
        ratio_candidates=candidates,
    )
    assert v.action == "apply_scale"
    assert v.r == 0.1


def test_c4_merge_to_zero_is_not_auto_applied():
    """C4 — 3주, 10:1 병합 → H=0(잔고에서 사라짐). r 후보가 있어도 수량 0 은 증거 B 가
    floor(3*0.1)=0 로 성립할 수 있지만, 그 경우도 자동 반영 "merger/병합 전액 현금화"는
    보유 소멸 경로(부팅 1차 삭제)로 가지 이 함수가 다루지 않는다 — 여기서는 단순히
    후보가 없을 때(0 매치) unexplained 로 떨어짐만 확인한다.
    """
    v = car.classify(
        tracked_qty=3, kis_qty=0, tracked_buy_price=1_000, kis_avg_price=0,
        ratio_candidates=[],
    )
    assert v.action == "unexplained"


def test_c5_bonus_issue_same_shape_no_face_value_change_unexplained():
    """C5 — 수량 ×2·평균 ÷2 인데 액면가 그대로(무상증자 입고) → 반영 0."""
    # 액면가 불변이면 ratio_from_face_value 후보 자체가 안 생긴다(호출부가 안 만든다) —
    # 여기서는 그 상황(빈 후보)에서 unexplained 로 떨어지는지만 본다.
    v = car.classify(
        tracked_qty=10, kis_qty=20, tracked_buy_price=10_000, kis_avg_price=5_000,
        ratio_candidates=[],
    )
    assert v.action == "unexplained"


def test_c6_mismatched_avg_price_is_unexplained():
    """C6 — 수량만 바뀌고 평균단가 불일치(대체 입고) → 반영 0."""
    candidates = [car.RatioCandidate(r=2.0, source="rev_split")]
    v = car.classify(
        tracked_qty=10, kis_qty=20, tracked_buy_price=10_000, kis_avg_price=9_000,  # 기대값 5000과 다름
        ratio_candidates=candidates,
    )
    assert v.action == "unexplained"


def test_merger_split_detected_when_no_ratio_matches():
    v = car.classify(
        tracked_qty=10, kis_qty=7, tracked_buy_price=1_000, kis_avg_price=1_000,
        ratio_candidates=[], merger_split_found=True,
    )
    assert v.action == "merger_split_detected"


def test_sync_qty_only_when_yesterday_orders_explain_delta():
    """사용자 결정 ② — 어제 주문내역이 정확히 설명하는 통보 유실분."""
    v = car.classify(
        tracked_qty=10, kis_qty=12, tracked_buy_price=1_000, kis_avg_price=1_000,
        ratio_candidates=[], yesterday_fills_net_qty=2,
    )
    assert v.action == "sync_qty_only"
    assert "yesterday_fills_net_qty=2" in v.detail


def test_ratio_evidence_takes_priority_over_yesterday_orders():
    candidates = [car.RatioCandidate(r=10.0, source="rev_split")]
    v = car.classify(
        tracked_qty=1, kis_qty=10, tracked_buy_price=10_000, kis_avg_price=1_000,
        ratio_candidates=candidates, yesterday_fills_net_qty=9,  # 숫자상 우연히도 설명되지만 비율이 우선
    )
    assert v.action == "apply_scale"


def test_c7_missing_face_value_falls_to_unexplained():
    """C7 — 액면가 칸 NULL + 보조 증거 없음 → 반영 0 · ERROR."""
    v = car.classify(
        tracked_qty=10, kis_qty=7, tracked_buy_price=1_000, kis_avg_price=1_000,
        ratio_candidates=[],
    )
    assert v.action == "unexplained"


# ---------------------------------------------------------------------------
# 적용 — 가격 차원 값 옮기기
# ---------------------------------------------------------------------------


def test_apply_ratio_to_price_divides():
    assert car.apply_ratio_to_price(1000, 10) == pytest.approx(100.0)


def test_apply_ratio_to_price_zero_or_missing_value_unchanged():
    assert car.apply_ratio_to_price(0, 10) == 0
    assert car.apply_ratio_to_price(None, 10) is None


def test_apply_ratio_to_volume_multiplies():
    assert car.apply_ratio_to_volume(100, 10) == pytest.approx(1000.0)


def test_compute_applied_scale_rounds_buy_price_and_scales_high():
    applied = car.compute_applied_scale(
        ticker="001390", kis_qty=10, tracked_buy_price=10_000,
        tracked_high_since_buy=12_000, r=10.0, source="rev_split",
    )
    assert applied.new_qty == 10
    assert applied.new_buy_price == 1_000
    assert applied.new_high_since_buy == pytest.approx(1_200.0)


def test_rederive_guard_ok_true_when_old_close_divided_by_r_matches_reference():
    # 분할 r=10(가격 1/10) — 옛 종가 50000 ÷ 10 = 5000 ≈ 오늘 기준가 5000
    assert car.rederive_guard_ok(50_000, 5_000, 10.0) is True


def test_rederive_guard_ok_false_when_still_old_scale():
    # 옛 종가 50000 ÷ 10 = 5000 인데 기준가가 아직 50000(옛 눈금 그대로)
    assert car.rederive_guard_ok(50_000, 50_000, 10.0) is False


# ---------------------------------------------------------------------------
# net_qty_from_order_rows — 통보 유실 판정용 순증감
# ---------------------------------------------------------------------------


def test_net_qty_from_order_rows_buy_plus_sell_minus():
    rows = [
        {"pdno": "005930", "sll_buy_dvsn_cd": "02", "tot_ccld_qty": "5"},
        {"pdno": "005930", "sll_buy_dvsn_cd": "01", "tot_ccld_qty": "2"},
    ]
    assert car.net_qty_from_order_rows(rows) == 3


def test_net_qty_from_order_rows_skips_unparseable_row():
    rows = [
        {"sll_buy_dvsn_cd": "02", "tot_ccld_qty": "oops"},
        {"sll_buy_dvsn_cd": "02", "tot_ccld_qty": "4"},
    ]
    assert car.net_qty_from_order_rows(rows) == 4


def test_net_qty_from_order_rows_empty_is_zero():
    assert car.net_qty_from_order_rows([]) == 0
    assert car.net_qty_from_order_rows(None) == 0


# ---------------------------------------------------------------------------
# 하루 상태 — 날짜 키 자기 리셋
# ---------------------------------------------------------------------------


def test_rescaled_today_registry_is_date_scoped():
    d1 = date(2026, 10, 10)
    d2 = date(2026, 10, 11)
    car.mark_rescaled_today("001390", today=d1)
    assert car.is_rescaled_today("001390", today=d1) is True
    assert car.is_rescaled_today("001390", today=d2) is False


def test_buy_blocked_today_registry_is_date_scoped():
    d1 = date(2026, 10, 10)
    d2 = date(2026, 10, 11)
    car.block_buy_today("001390", today=d1)
    assert car.is_buy_blocked_today("001390", today=d1) is True
    assert car.is_buy_blocked_today("001390", today=d2) is False


def test_rescaled_today_default_today_resolves_via_kst_wall_clock():
    """07:45 부팅 호출은 `today=` 를 명시 전달하지만, 기본값(`None`) 경로도
    KST 벽시계(`today_kst()`)로 정확히 날짜를 가른다 — 자정 경계에서 서버
    로컬 타임존이 섞이면 날짜 키가 어긋나 가드가 하루 일찍/늦게 풀린다.
    """
    with freeze_time("2026-10-10 15:30:00+09:00"):  # KST 2026-10-10 15:30
        car.mark_rescaled_today("005930")
        assert car.is_rescaled_today("005930") is True

    with freeze_time("2026-10-11 00:30:00+09:00"):  # KST 날짜가 넘어갔다
        assert car.is_rescaled_today("005930") is False


def test_c2_idempotent_second_pass_is_noop():
    """C2 — C1 반영 뒤 같은 판정 재실행 → 변화 0(멱등)."""
    candidates = [car.RatioCandidate(r=10.0, source="rev_split")]
    # 1차 반영 뒤 tracked==kis 이므로 재실행은 match.
    v = car.classify(
        tracked_qty=10, kis_qty=10, tracked_buy_price=1_000, kis_avg_price=1_000,
        ratio_candidates=candidates,
    )
    assert v.action == "match"


# ---------------------------------------------------------------------------
# ratio_candidates_from_* 파서
# ---------------------------------------------------------------------------


def test_ratio_candidates_from_rev_split_rows_builds_candidates():
    rows = [{"inter_bf_face_amt": "000000500", "inter_af_face_amt": "000002500"}]
    cands = car.ratio_candidates_from_rev_split_rows(rows)
    assert len(cands) == 1
    assert cands[0].r == pytest.approx(0.2)
    assert cands[0].source == "rev_split"


def test_ratio_candidates_from_rev_split_rows_skips_unparseable():
    rows = [{"inter_bf_face_amt": "", "inter_af_face_amt": ""}]
    assert car.ratio_candidates_from_rev_split_rows(rows) == []


def test_ratio_candidates_from_cap_decrease_rows_only_multiply():
    rows = [
        {"reduce_cap_rate": " 1.00", "comp_way": "곱하기"},
        {"reduce_cap_rate": " 0.50", "comp_way": "나누기"},
    ]
    cands = car.ratio_candidates_from_cap_decrease_rows(rows)
    assert len(cands) == 1
    assert cands[0].r == pytest.approx(1.0)
    assert cands[0].source == "cap_decrease"


# ---------------------------------------------------------------------------
# observe_mid_session_sync — 15분 동기화, 관측만(쓰지 않는다) — C12~C16
# ---------------------------------------------------------------------------


class _Pos:
    def __init__(self, qty):
        self.quantity = qty


class _Strategy:
    def __init__(self, positions):
        self.state = type("S", (), {"positions": positions})()


class _Registry:
    def __init__(self, strategies):
        self._strategies = strategies

    def all(self):
        return self._strategies


class _Holding:
    def __init__(self, ticker, quantity):
        self.ticker = ticker
        self.quantity = quantity


@pytest.mark.asyncio
async def test_observe_mid_session_sync_noop_when_no_mismatch(monkeypatch):
    registry = _Registry([_Strategy({"005930": _Pos(10)})])
    holdings = [_Holding("005930", 10)]
    called = AsyncMock()
    monkeypatch.setattr("src.api.balance.get_daily_orders", called)
    await car.observe_mid_session_sync(registry, holdings)
    called.assert_not_called()


@pytest.mark.asyncio
async def test_c12_open_sell_order_is_in_progress(monkeypatch, caplog):
    """C12 — 매도 걸어 둠(rmn_qty>0), H=T → 보류, 로그 0 수준(INFO)."""
    registry = _Registry([_Strategy({"005930": _Pos(10)})])
    holdings = [_Holding("005930", 8)]
    rows = [{"pdno": "005930", "rmn_qty": "2", "sll_buy_dvsn_cd": "01", "tot_ccld_qty": "0"}]
    monkeypatch.setattr("src.api.balance.get_daily_orders", AsyncMock(return_value=rows))
    with caplog.at_level("INFO", logger="src.engine.scheduler"):
        await car.observe_mid_session_sync(registry, holdings)
    assert any("result=in_progress" in r.message for r in caplog.records)
    assert not any("holding_qty_unexplained" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_c13_explained_by_sell_fill_logs_info_not_error(monkeypatch, caplog):
    """C13 — 우리 매도 체결, 통보 대기 → INFO, 장부 무변경(그 자체로 확인됨 — 관측뿐)."""
    registry = _Registry([_Strategy({"005930": _Pos(10)})])
    holdings = [_Holding("005930", 8)]
    rows = [{"pdno": "005930", "rmn_qty": "0", "sll_buy_dvsn_cd": "01", "tot_ccld_qty": "2"}]
    monkeypatch.setattr("src.api.balance.get_daily_orders", AsyncMock(return_value=rows))
    with caplog.at_level("INFO", logger="src.engine.scheduler"):
        await car.observe_mid_session_sync(registry, holdings)
    assert any("result=explained_by_orders" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_c15_unexplained_delta_logs_error(monkeypatch, caplog):
    """C15 — 설명 안 되는 Δ, 주문내역 0 → ERROR 1회/종목·날."""
    registry = _Registry([_Strategy({"005930": _Pos(10)})])
    holdings = [_Holding("005930", 7)]
    monkeypatch.setattr("src.api.balance.get_daily_orders", AsyncMock(return_value=[]))
    with caplog.at_level("INFO", logger="src.engine.scheduler"):
        await car.observe_mid_session_sync(registry, holdings)
    assert any(
        r.levelname == "ERROR" and "holding_qty_unexplained" in r.message
        for r in caplog.records
    )


@pytest.mark.asyncio
async def test_c16_order_lookup_failure_logs_warning(monkeypatch, caplog):
    """C16 — 주문내역 조회 실패 → WARNING, 장부 무변경."""
    registry = _Registry([_Strategy({"005930": _Pos(10)})])
    holdings = [_Holding("005930", 7)]
    monkeypatch.setattr(
        "src.api.balance.get_daily_orders", AsyncMock(side_effect=RuntimeError("boom")),
    )
    with caplog.at_level("WARNING", logger="src.engine.scheduler"):
        await car.observe_mid_session_sync(registry, holdings)
    assert any(
        r.levelname == "WARNING" and "result=lookup_failed" in r.message
        for r in caplog.records
    )
