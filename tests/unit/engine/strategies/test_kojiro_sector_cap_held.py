"""kojiro 섹터 캡 "전일 보유 미집계" 결함 Red 테스트 (채택안 A — `_position_sectors` 영속 맵).

배경: `max_positions_per_sector` 캡의 카운트(`check_buy_signal` 708~709)가 동일섹터 보유
집계를 `_candidates` 에만 의존 → held 가 ATR 밴드/유니버스 이탈로 `_candidates` 에서 부재하면
`same=0` → 캡이 막으려던 "한 섹터 N종목 집중"을 무력하게 허용.

채택 설계 (자문 `_workspace/domain_consult/kojiro_sector_cap_held_counting.md` §채택안 A):
- 신규 `KojiroMonitor._position_sectors: dict[str, str]` — `_candidates` 와이프에서 독립, 포지션 수명 동안 생존.
- stamp 3지점: recompute_held_atr(보유 정본) + check_buy_signal BUY 반환 직전(당일 매수분) + on_position_closed(pop).
- 카운트 폴백: `(self._candidates.get(t) or {}).get("sector") or self._position_sectors.get(t)`.
- `_reset_daily_state` override **추가 금지**(base no-op 상속 → 멀티데이 held 섹터 밤샘 보존) — AST 로 봉인.

fail-open 불변: cap=0 비활성 / 후보 미분류(독립키) 미차단 / held 미분류 미집계.
캡 = 매수 게이트 전용 — 청산/손절/트레일링/익일청산 절대 미차단(check_exit 무접촉).
"""
from __future__ import annotations

import datetime as _dt
from pathlib import Path
from unittest.mock import AsyncMock

import pandas as pd
import pytest
from freezegun import freeze_time

import src.engine.strategies.kojiro as kmod
from src.engine.strategies.kojiro import KojiroStrategy
from src.engine.strategy_base import Position, Signal, StrategyConfig

pytestmark = pytest.mark.unit
KST = _dt.timezone(_dt.timedelta(hours=9))
WINDOW = _dt.datetime(2026, 5, 8, 9, 10, tzinfo=KST)  # 09:05~09:30 매수창 내 (금요일 영업일)


def _mk(**params):
    return KojiroStrategy(StrategyConfig(strategy_id="kojiro", name="고지로", weight=0.1, params=params))


def _seed_candidate(s, ticker, sector, *, stage=1, prev_close=10000, atr=200.0):
    """strict entry 통과분 재현 — `_candidates` 에 sector 포함 등록."""
    s._candidates[ticker] = {
        "prev_close": prev_close, "atr": atr, "stage": stage,
        "ema_s": 9900.0, "ema_m": 9800.0, "ema_l": 9700.0,
        "atr_ratio": atr / prev_close, "sector": sector,
    }


def _hold_out_of_candidates(s, ticker, *, buy_price=10000):
    """전일 보유 재현 — positions 에만 존재, `_candidates` 부재(ATR 밴드/유니버스 이탈)."""
    s.state.positions[ticker] = Position(
        ticker=ticker, buy_price=buy_price, quantity=10, order_no="O",
        strategy_id="kojiro", buy_date=_dt.date(2026, 5, 1))


def _dummy_candles(n=85):
    """DESC(idx0=최신) 일봉 — 날짜가 오늘 아님 → prev_idx=0, usable=n(≥80)."""
    return [{
        "stck_bsop_date": "20250101", "stck_oprc": "10000", "stck_hgpr": "10100",
        "stck_lwpr": "9900", "stck_clpr": "10000", "acml_vol": "1000000",
    } for _ in range(n)]


def _enriched_row(*, atr=200.0, close=10000, stage=2):
    """recompute 가 iloc[-1] 로 읽는 컬럼(atr/stage/close/ema_*) 만 결정론 제공."""
    return pd.DataFrame({
        "close": [close], "atr": [atr], "stage": [stage],
        "ema_s": [9900.0], "ema_m": [9800.0], "ema_l": [9700.0],
    })


# ─────────────────────────────────────────────────────────────────────────────
# 시나리오 1 [핵심 RED] — 전일 보유(밴드 이탈로 _candidates 부재)가 섹터 캡에 집계돼야 한다
# ─────────────────────────────────────────────────────────────────────────────

def test_prev_day_held_out_of_candidates_counts_toward_sector_cap():
    s = _mk(max_positions_per_sector=2)
    # 동일섹터 2종목 전일 보유 — ATR 밴드 이탈 재현으로 _candidates 에서 제거된 상태
    _hold_out_of_candidates(s, "P1")
    _hold_out_of_candidates(s, "P2")
    # 채택안 A 신규 영속 맵 — recompute stamp 결과 재현
    s._position_sectors = {"P1": "바이오", "P2": "바이오"}
    # 같은 섹터 3번째 후보
    _seed_candidate(s, "C3", "바이오")
    with freeze_time(WINDOW):
        # 현행: same=0(held 미집계) → BUY 통과 = RED. 수정 후: 폴백 카운트 2 ≥ 2 → 차단.
        assert s.check_buy_signal("C3", 10100, 10050) == Signal.NONE


# ─────────────────────────────────────────────────────────────────────────────
# 시나리오 2 — 재-prepare 와이프에도 _position_sectors 는 생존 + 카운트 유지
# ─────────────────────────────────────────────────────────────────────────────

def test_position_sectors_survives_candidates_wipe():
    s = _mk(max_positions_per_sector=2)
    _hold_out_of_candidates(s, "P1")
    _hold_out_of_candidates(s, "P2")
    s._position_sectors = {"P1": "철강", "P2": "철강"}
    # prepare 재-스캔이 _candidates 전량 재생성(와이프)하는 상황 재현
    s._candidates = {}
    _seed_candidate(s, "C3", "철강")
    # 영속 맵은 _candidates 와이프와 독립 — 생존
    assert getattr(s, "_position_sectors", {}) == {"P1": "철강", "P2": "철강"}
    with freeze_time(WINDOW):
        assert s.check_buy_signal("C3", 10100, 10050) == Signal.NONE


# ─────────────────────────────────────────────────────────────────────────────
# 시나리오 3 — recompute_held_atr 가 보유 종목 섹터를 _position_sectors 에 stamp
# ─────────────────────────────────────────────────────────────────────────────

async def test_recompute_held_atr_stamps_position_sector(monkeypatch):
    s = _mk(max_positions_per_sector=2)
    _hold_out_of_candidates(s, "005930")
    monkeypatch.setattr("src.db.stock_master_daily.get_recent_daily_normalized",
                        AsyncMock(return_value=_dummy_candles()))
    monkeypatch.setattr(kmod, "enrich", lambda df, cfg: _enriched_row(atr=200.0, close=10000))
    # master_raw KRX 바이오 플래그 → _kojiro_sector_key = "바이오" (실 소스 경로 검증)
    monkeypatch.setattr("src.db.stock_master.get_master_raw",
                        AsyncMock(return_value={"krx_bio_yn": "Y"}))
    await s.recompute_held_atr()
    # 사전조건: recompute 가 실제 실행돼 _candidates 도 채웠는지(fail-open 아님) 확인
    assert s._candidates.get("005930", {}).get("sector") == "바이오"
    # 핵심: 영속 맵에도 stamp — 현행은 미stamp → RED
    assert getattr(s, "_position_sectors", {}).get("005930") == "바이오"


# ─────────────────────────────────────────────────────────────────────────────
# 시나리오 4 — on_position_closed 가 _position_sectors 에서 pop
# ─────────────────────────────────────────────────────────────────────────────

def test_on_position_closed_pops_position_sector():
    s = _mk(max_positions_per_sector=2)
    s._position_sectors = {"P1": "바이오", "P2": "은행"}
    s.on_position_closed("P1")
    # 현행 on_position_closed 는 _held_stage3/_stop_floor 만 pop → P1 잔존 = RED
    assert "P1" not in getattr(s, "_position_sectors", {"P1": "바이오"})
    # 타 종목 섹터는 보존
    assert getattr(s, "_position_sectors", {}).get("P2") == "은행"


# ─────────────────────────────────────────────────────────────────────────────
# 시나리오 5 [fail-open 봉인] — held 미분류(독립키)는 후보와 매칭 안 됨 → 미집계 → 미차단
# ─────────────────────────────────────────────────────────────────────────────

def test_unclassified_held_not_counted_failopen():
    s = _mk(max_positions_per_sector=2)
    _hold_out_of_candidates(s, "P1")
    _hold_out_of_candidates(s, "P2")
    # held 섹터가 미분류(종목별 유니크 독립키) — 후보 실섹터와 절대 매칭 안 됨
    s._position_sectors = {"P1": "미분류-P1", "P2": "미분류-P2"}
    _seed_candidate(s, "C3", "바이오")
    with freeze_time(WINDOW):
        # 상관 못읽는 종목은 세지 않는다(위양성 차단) — 현행/수정 후 모두 통과
        assert s.check_buy_signal("C3", 10100, 10050) == Signal.BUY


# ─────────────────────────────────────────────────────────────────────────────
# 시나리오 6 [봉인] — _reset_daily_state override 추가 금지 (멀티데이 held 섹터 밤샘 보존)
# ─────────────────────────────────────────────────────────────────────────────

def test_reset_daily_state_does_not_wipe_position_sectors():
    s = _mk(max_positions_per_sector=2)
    s._position_sectors = {"P1": "바이오", "P2": "바이오"}
    # base no-op _reset_daily_state (kojiro override 부재) → 정산 후에도 보존
    s._reset_daily_state()
    assert getattr(s, "_position_sectors", {}) == {"P1": "바이오", "P2": "바이오"}


def test_kojiro_has_no_reset_daily_state_override():
    # ★ AST 봉인: kojiro 클래스에 _reset_daily_state def 추가 시 멀티데이 held 섹터가
    #   20:10 정산에 소멸 → 캡 무력. base no-op 상속만 허용.
    assert "_reset_daily_state" not in KojiroStrategy.__dict__


# ─────────────────────────────────────────────────────────────────────────────
# 시나리오 7 — 당일 매수(BUY 반환) 가 _position_sectors 에 stamp + 재-prepare 에도 반영
# ─────────────────────────────────────────────────────────────────────────────

def test_buy_signal_stamps_position_sector():
    s = _mk(max_positions_per_sector=2)
    _seed_candidate(s, "C1", "바이오")
    with freeze_time(WINDOW):
        assert s.check_buy_signal("C1", 10100, 10050) == Signal.BUY
    # 현행 BUY 경로는 _position_sectors 미stamp → RED
    assert getattr(s, "_position_sectors", {}).get("C1") == "바이오"


def test_buy_stamp_persists_across_candidates_wipe_for_next_candidate():
    # 섹터당 1 — 당일 첫 매수(C1) 후 재-prepare 와이프에도 다음 후보(C2) 카운트에 반영
    s = _mk(max_positions_per_sector=1)
    _seed_candidate(s, "C1", "바이오")
    with freeze_time(WINDOW):
        assert s.check_buy_signal("C1", 10100, 10050) == Signal.BUY   # 첫 매수(held 0 → 통과)
    # execute_buy 가 pending_buys 등록하는 상황 재현
    s.state.pending_buys.add("C1")
    # 재-prepare 와이프
    s._candidates = {}
    _seed_candidate(s, "C2", "바이오")   # 동일섹터 2번째 후보
    with freeze_time(WINDOW):
        # 현행: C1 이 _candidates 에서 사라져 same=0 → C2 통과 = RED. 수정 후: 폴백 1 ≥ 1 → 차단.
        assert s.check_buy_signal("C2", 10100, 10050) == Signal.NONE


# ─────────────────────────────────────────────────────────────────────────────
# 시나리오 8 [SAFETY] — check_exit 무접촉 + 신규 필드는 kojiro.py 단독(8 안전영역 무접촉)
# ─────────────────────────────────────────────────────────────────────────────

def test_check_exit_signal_has_no_position_sectors_token():
    import inspect
    src = inspect.getsource(KojiroStrategy.check_exit_signal)
    # 캡은 매수 게이트 전용 — 청산 경로에 섹터 상태 주입 금지
    assert "_position_sectors" not in src
    assert "max_positions_per_sector" not in src


_SAFETY_FILES = [
    "src/engine/risk.py",
    "src/engine/order_engine.py",
    "src/engine/scheduler.py",
    "src/engine/session.py",
    "src/engine/strategy_registry.py",
    "src/api/order.py",
    "src/realtime/handler.py",
    "src/realtime/websocket.py",
    "src/realtime/websocket_pool.py",
    "src/auth/token.py",
]


def test_position_sectors_isolated_to_kojiro():
    # 섹터 캡 held 집계 = kojiro.py 단독 변경 — 매매 안전성 8영역에 _position_sectors 참조 0건.
    root = Path(__file__).resolve().parents[4]
    for rel in _SAFETY_FILES:
        p = root / rel
        assert p.exists(), f"안전영역 경로 부재: {rel}"
        assert "_position_sectors" not in p.read_text(encoding="utf-8"), (
            f"신규 필드가 안전영역에 누설됨: {rel}"
        )
