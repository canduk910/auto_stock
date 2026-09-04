"""cycle233 M5-③ — `[oversized_fallback]` 관측 (R8, 자문 §정정 1 · 부속안 ③).

`_fallback_one_share` 가 notional 상한(`position_ratio × 예산`)을 보지 않아 실측
000815 가 설계 유닛 4.11(상한 3.10배)이 됐다. 사용자 결정 = **관측만** — 수량은
불변(행위 변경 0), `_apply_budget_limit` 최종 수량이 상한을 넘으면 1회/(ticker)/일
INFO. **관측기(`_emit_oversized_fallback`) 자신이** 수량을 바꾸면 부속안 ②(차단)
오구현으로 FAIL 이 계약이다.

⚠️ **cycle242(2026-09-03, 사용자 결정 G0-ⓑ) 재스코프** — `sizing_mode="turtle"`
전략에서는 `max_lot_units`(K=2.0) 상한이 도입돼 **같은 000815 픽스처가 0 이 정답**이다
(`test_cycle242_fallback_notional_cap.py` F-1/F-6 참조). 본 파일의 6 케이스는 전부
`sizing_mode` 미지정 = 캡 게이트 off 경로라 **assertion 은 byte 무변경**으로 유효하다.
`[oversized_fallback]` 은 이제 ρ 축(`position_ratio × 예산`) 관측으로 K 축 행위와
**병존**하며 **비제로가 정상**이다(의미 반전 — 배포 전후 같은 grep 합산 금지).

⚠️ **cycle245(2026-09-04) 재스코프** — 같은 ρ 축(`position_ratio × 예산`)에
**별도 헬퍼**(`_apply_ratio_notional_cap`)로 차단 행위가 도입됐다. 본 파일 픽스처는
`max_lot_ratio_mult` 키가 없어 **캡 OFF 경로**(키 부재 = OFF 가 계약)라 6 케이스
assertion 은 다시 byte 무변경으로 유효하다. 다만 이 마커의 의미는 ρ캡 **앞**에서
발화하게 되어 **"실제로 산 랏" → "사려 했던 랏"** 으로 전환됐다.

`_apply_budget_limit` 내 await 0 (A-PURE/A-ATOMIC) 은 기존 AST 가드가 계속 강제.
"""

from __future__ import annotations

import logging

import pytest

from src.engine.strategy_base import Signal, StrategyBase, StrategyConfig


class _MiniStrategy(StrategyBase):
    """관문 테스트용 최소 구현 (test_cycle185 패턴)."""

    async def prepare(self):  # pragma: no cover
        return None

    def check_buy_signal(self, ticker, current_price, open_price):
        return Signal.NONE

    def check_exit_signal(self, ticker, current_price, open_price):
        return Signal.NONE

    def calc_buy_quantity(self, current_price: int, ticker: str | None = None) -> int:
        return self._apply_budget_limit(0, current_price, ticker)


def _make(ratio: float | None, budget: int) -> _MiniStrategy:
    params: dict = {"exchange": "KRX"}
    if ratio is not None:
        params["position_ratio"] = ratio
    s = _MiniStrategy(StrategyConfig(strategy_id="kojiro", name="k", params=params))
    s.state.total_investment = budget
    return s


class TestR8OversizedFallback:
    def test_consult_case_emits_and_keeps_qty(self, caplog):
        """000815 실측: 405,500원 1주 / cap 130,995 → ratio 3.10 관측, 수량 1 유지."""
        s = _make(0.166, 789_130)
        with caplog.at_level(logging.INFO):
            qty = s._apply_budget_limit(0, 405_500, "000815")
        assert qty == 1  # 행위 불변 — 0 이면 부속안 ② 오구현
        hits = [r for r in caplog.records if "[oversized_fallback]" in r.message]
        assert len(hits) == 1
        assert "3.10" in hits[0].message

    def test_capped_once_per_day(self, caplog):
        s = _make(0.166, 789_130)
        with caplog.at_level(logging.INFO):
            s._apply_budget_limit(0, 405_500, "000815")
            s._apply_budget_limit(0, 405_500, "000815")
        hits = [r for r in caplog.records if "[oversized_fallback]" in r.message]
        assert len(hits) == 1

    def test_within_cap_no_emit(self, caplog):
        """1주 100,000원 ≤ cap 130,995 → 무발화."""
        s = _make(0.166, 789_130)
        with caplog.at_level(logging.INFO):
            qty = s._apply_budget_limit(0, 100_000, "028670")
        assert qty == 1
        assert not [r for r in caplog.records if "[oversized_fallback]" in r.message]

    def test_ratio_missing_no_emit(self, caplog):
        """position_ratio 결측 → cap 정의 불가 → 무발화 (fail-open)."""
        s = _make(None, 789_130)
        with caplog.at_level(logging.INFO):
            qty = s._apply_budget_limit(0, 405_500, "000815")
        assert qty == 1
        assert not [r for r in caplog.records if "[oversized_fallback]" in r.message]

    def test_main_branch_within_cap_no_emit(self, caplog):
        """ratio 경로 정상 수량(명목 ≤ cap)은 무발화."""
        s = _make(0.166, 789_130)
        with caplog.at_level(logging.INFO):
            qty = s._apply_budget_limit(2, 50_000, "028670")  # 100,000 ≤ 130,995
        assert qty == 2
        assert not [r for r in caplog.records if "[oversized_fallback]" in r.message]

    def test_emit_failure_never_breaks_quantity(self, monkeypatch):
        """관측 실패가 수량 산출을 깨지 않는다 (kojiro 캡 fail-open 규약)."""
        s = _make(0.166, 789_130)
        monkeypatch.setattr(
            s, "_emit_oversized_fallback",
            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")),
        )
        # 예외가 전파되면 FAIL — 구현은 emit 을 try/except 로 감싸거나
        # emit 내부에서 흡수해야 한다.
        try:
            qty = s._apply_budget_limit(0, 405_500, "000815")
        except RuntimeError:
            pytest.fail("관측 예외가 매수 수량 산출로 전파됨")
        assert qty == 1
