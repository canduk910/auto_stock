"""사이클 F Red — TE(트레이딩 예지치) + RR비율(손익비) 순수 함수 회귀 가드.

명세: `_workspace/red/_behaviors_cycleF_te_rr_20260802.md` (F-B1~F-B9)
자문: `_workspace/domain_consult/cycle_te_expectancy_dashboard_20260802.md` (§266-276 회귀 권고)

대상: 신규 순수 함수 `src.engine.te_metrics.compute_te_rr(pairs, *, now, window_days=90,
strategy_id="") -> TeRrMetrics`.

핵심 계약 (구현 전 Red 고정):
- **소스·기준(F-B2)**: TE% = 모집단 `profit_rate`(get_trade_pairs, *진입가 기준*) 단순평균.
  매수 10,000 → 매도 11,000 왕복이 +10.0%(진입가) 로 계산 — 매도가 기준 +9.09% 아님.
  compute_metrics(매도가 기준 pnl/gross) 재사용 절대 금지.
- **분해·보합(F-B3)**: N(전체 왕복) / W(>0) / L(<0) / E(보합=0). win_rate 분모=N(보합 포함).
  TE=net/N 항등. avg_win 양수 / avg_loss 음수.
- **RR·필요RR(F-B4)**: RR=avg_win/|avg_loss|. 필요RR=L/W(W=0→None). margin=RR−필요RR.
  전승(avg_loss=0) 또는 min(W,L)<5 → RR=None + rr_available=False.
  동치: TE>0 ⟺ RR>필요RR (경계 TE≈0 포함). 단일거래 의존 플래그.
- **표본 게이트(F-B5)**: sample_tier N<20 insufficient / 20≤N<50 low / N≥50 normal.
  verdict N<20 undecided / TE>0 superior / TE<0 inferior / TE==0 flat.
- **구조 태그(F-B6)**: N≥20 ∧ rr_available 시만. 저승률·고RR robust / 고승률·저RR fragile /
  그 외 balanced. 미충족 시 None.
- **윈도우(F-B1)**: status=='closed' ∧ sell_date(청산일) ≥ now−window_days. open 제외(F-B9).
  경계 = 매수 D-100·청산 D-30 은 포함 (청산일 기준).

get_trade_pairs 는 mock (합성 pairs 주입). 부분체결은 get_trade_pairs 가 왕복 1건으로
접는 전제(PARTIAL 이중카운트 부재) → 합성 closed 행 개수로 N 정확 검증.

RED 상태: `src.engine.te_metrics` 모듈 부재 → ImportError 로 전 케이스 실패.
"""
from __future__ import annotations

from datetime import datetime

import pytest

from src.db._kst import KST

pytestmark = pytest.mark.unit


# now 고정 (freezegun 대신 명시 파라미터 — compute_te_rr 는 now 를 인자로 받는 순수 함수).
NOW = datetime(2026, 8, 2, 12, 0, 0, tzinfo=KST)


def _pair(
    *,
    profit_rate: float,
    profit_loss: float | None = None,
    sell_date: str | None = "2026-08-01",
    status: str = "closed",
    strategy: str = "momentum",
) -> dict:
    """get_trade_pairs 출력 형식 왕복 1건 합성.

    profit_rate = 진입가 기준 수익률(%). profit_loss = 실현손익(원).
    미지정 시 profit_rate 에 비례한 원값(1%p=1,000원) 사용.
    """
    if profit_loss is None and profit_rate is not None:
        profit_loss = float(profit_rate) * 1000.0
    return {
        "status": status,
        "sell_date": sell_date,
        "sell_time": "13:00:00" if sell_date else None,
        "buy_date": "2026-07-20",
        "profit_rate": None if profit_rate is None else float(profit_rate),
        "profit_loss": None if profit_loss is None else float(profit_loss),
        "strategy": strategy,
        "ticker": "005930",
        "ticker_name": "삼성전자",
        "buy_price": 10000.0,
        "buy_qty": 1,
        "sell_price": 11000.0,
        "sell_qty": 1,
    }


# ===========================================================================
# F-B2 — 소스·기준 (HIGH): 진입가 기준 profit_rate 단순평균
# ===========================================================================
def test_te_pct_uses_entry_based_profit_rate_not_sell_based():
    """매수 10,000 → 매도 11,000 왕복 = +10.0%(진입가) — 매도가 기준 +9.09% 아님."""
    from src.engine.te_metrics import compute_te_rr

    pairs = [_pair(profit_rate=10.0, profit_loss=1000.0, sell_date="2026-08-01")]
    m = compute_te_rr(pairs, now=NOW, strategy_id="momentum")

    assert m.te_pct == pytest.approx(10.0), "진입가 기준 +10.0% 여야 함"
    assert m.te_pct != pytest.approx(9.0909, abs=0.01), (
        "매도가 기준 +9.09% (compute_metrics) 재사용 금지"
    )


def test_te_pct_is_simple_average_of_profit_rate():
    """TE% = 모집단 profit_rate 단순 산술평균."""
    from src.engine.te_metrics import compute_te_rr

    pairs = [_pair(profit_rate=r) for r in (10.0, -4.0, 6.0, -2.0)]
    m = compute_te_rr(pairs, now=NOW)

    assert m.te_pct == pytest.approx((10.0 - 4.0 + 6.0 - 2.0) / 4)  # 2.5


def test_te_krw_avg_and_realized_sum():
    """TE₩ = profit_loss 평균 / realized_sum_krw = profit_loss 합계."""
    from src.engine.te_metrics import compute_te_rr

    pairs = [
        _pair(profit_rate=10.0, profit_loss=1000.0),
        _pair(profit_rate=-4.0, profit_loss=-400.0),
        _pair(profit_rate=6.0, profit_loss=600.0),
    ]
    m = compute_te_rr(pairs, now=NOW)

    assert m.te_krw_avg == pytest.approx((1000.0 - 400.0 + 600.0) / 3)  # 400.0
    assert m.realized_sum_krw == pytest.approx(1200.0)


# ===========================================================================
# F-B3 — 분해·보합: win_rate 분모=N(보합 포함), TE=net/N 항등
# ===========================================================================
def test_decomposition_even_included_in_denominator_and_net_identity():
    """보합(profit_rate=0, 손절=매수가 청산) 포함 시 win_rate 분모=N, TE=net/N."""
    from src.engine.te_metrics import compute_te_rr

    pairs = [
        _pair(profit_rate=10.0, profit_loss=1000.0),
        _pair(profit_rate=4.0, profit_loss=400.0),
        _pair(profit_rate=-6.0, profit_loss=-600.0),
        _pair(profit_rate=0.0, profit_loss=0.0),  # 보합
    ]
    m = compute_te_rr(pairs, now=NOW)

    assert m.n == 4
    assert m.win == 2
    assert m.loss == 1
    assert m.even == 1
    assert m.win_rate == pytest.approx(2 / 4), "분모=N(보합 포함)"
    assert m.te_pct == pytest.approx((10.0 + 4.0 - 6.0 + 0.0) / 4), "TE=net/N 항등"
    assert m.avg_win_pct == pytest.approx((10.0 + 4.0) / 2), "avg_win 양수"
    assert m.avg_loss_pct == pytest.approx(-6.0), "avg_loss 음수"


# ===========================================================================
# F-B4 — RR·필요RR·동치
# ===========================================================================
def test_rr_ratio_and_required_rr():
    """RR=avg_win/|avg_loss|, 필요RR=L/W, margin=RR−필요RR."""
    from src.engine.te_metrics import compute_te_rr

    pairs = [_pair(profit_rate=8.0) for _ in range(5)] + [
        _pair(profit_rate=-2.0) for _ in range(5)
    ]
    m = compute_te_rr(pairs, now=NOW)

    assert m.avg_win_pct == pytest.approx(8.0)
    assert m.avg_loss_pct == pytest.approx(-2.0)
    assert m.rr == pytest.approx(8.0 / 2.0)  # 4.0
    assert m.required_rr == pytest.approx(5 / 5)  # 1.0 = L/W
    assert m.rr_margin == pytest.approx(4.0 - 1.0)
    assert m.rr_available is True


def test_te_rr_equivalence_including_boundary():
    """동치 회귀: TE>0 ⟺ RR>필요RR (경계 TE≈0 포함, 보합 존재해도 성립)."""
    from src.engine.te_metrics import compute_te_rr

    # 경계: net=0 → TE==0 ⟺ RR==필요RR (보합 1건 섞어도 성립).
    # N≥20 으로 스케일 — F-B5 표본 게이트(N<20 → 'undecided')와 충돌 없이
    # 동치(TE≈0 ⟺ RR≈필요RR) 검증. 10승(+2%)+10패(−2%)+보합1 = N=21.
    boundary = (
        [_pair(profit_rate=2.0) for _ in range(10)]
        + [_pair(profit_rate=-2.0) for _ in range(10)]
        + [_pair(profit_rate=0.0)]
    )
    mb = compute_te_rr(boundary, now=NOW)
    assert mb.te_pct == pytest.approx(0.0)
    assert mb.rr == pytest.approx(mb.required_rr), "경계 동치 RR==필요RR"
    assert mb.rr_margin == pytest.approx(0.0)
    assert mb.verdict == "flat"

    # 우위: TE>0 ⟺ RR>필요RR
    sup = [_pair(profit_rate=6.0) for _ in range(5)] + [
        _pair(profit_rate=-2.0) for _ in range(5)
    ]
    ms = compute_te_rr(sup, now=NOW)
    assert ms.te_pct > 0
    assert ms.rr > ms.required_rr

    # 열위: TE<0 ⟺ RR<필요RR
    inf = [_pair(profit_rate=1.0) for _ in range(5)] + [
        _pair(profit_rate=-6.0) for _ in range(5)
    ]
    mi = compute_te_rr(inf, now=NOW)
    assert mi.te_pct < 0
    assert mi.rr < mi.required_rr


def test_all_win_rr_none():
    """전승(avg_loss=0) → RR 산정 불가(None) + rr_available False + margin None."""
    from src.engine.te_metrics import compute_te_rr

    pairs = [_pair(profit_rate=5.0) for _ in range(6)]  # L=0
    m = compute_te_rr(pairs, now=NOW)

    assert m.loss == 0
    assert m.rr is None
    assert m.rr_available is False
    assert m.rr_margin is None


def test_all_loss_required_rr_none():
    """전패(W=0) → 필요RR=L/W 산정 불가(None) + RR None."""
    from src.engine.te_metrics import compute_te_rr

    pairs = [_pair(profit_rate=-3.0) for _ in range(6)]  # W=0
    m = compute_te_rr(pairs, now=NOW)

    assert m.win == 0
    assert m.required_rr is None, "W=0 → 필요RR None"
    assert m.rr is None
    assert m.rr_available is False


def test_rr_gate_min_wl_below_5():
    """min(W,L)<5 → rr_available False + RR None. min(W,L)=5 경계 활성."""
    from src.engine.te_metrics import compute_te_rr

    # W=10, L=4 → min=4 < 5
    pairs = [_pair(profit_rate=5.0) for _ in range(10)] + [
        _pair(profit_rate=-2.0) for _ in range(4)
    ]
    m = compute_te_rr(pairs, now=NOW)
    assert m.win == 10 and m.loss == 4
    assert m.rr_available is False, "min(W,L)=4 < 5"
    assert m.rr is None

    # W=10, L=5 → min=5 활성
    pairs2 = [_pair(profit_rate=5.0) for _ in range(10)] + [
        _pair(profit_rate=-2.0) for _ in range(5)
    ]
    m2 = compute_te_rr(pairs2, now=NOW)
    assert m2.rr_available is True, "min(W,L)=5 경계 활성"
    assert m2.rr == pytest.approx(5.0 / 2.0)


def test_single_trade_dominant_flag():
    """단일거래 의존: 최대 승 profit_loss > 총 이익합 × 0.5 → True."""
    from src.engine.te_metrics import compute_te_rr

    # 총이익합 12,000 중 한 승자 10,000 = 83% > 50%
    dominant = (
        [_pair(profit_rate=20.0, profit_loss=10000.0)]
        + [_pair(profit_rate=2.0, profit_loss=1000.0)]
        + [_pair(profit_rate=2.0, profit_loss=1000.0)]
        + [_pair(profit_rate=-1.0, profit_loss=-100.0) for _ in range(5)]
    )
    md = compute_te_rr(dominant, now=NOW)
    assert md.single_trade_dominant is True

    # 균등 분포 (승 5건 각 1,000, 최대=1,000 ≤ 2,500) → False
    even_dist = [_pair(profit_rate=5.0, profit_loss=1000.0) for _ in range(5)] + [
        _pair(profit_rate=-2.0, profit_loss=-400.0) for _ in range(5)
    ]
    me = compute_te_rr(even_dist, now=NOW)
    assert me.single_trade_dominant is False


# ===========================================================================
# F-B5 — 표본 게이트
# ===========================================================================
def test_sample_tier_boundaries():
    """sample_tier: N=19 insufficient / 20 low / 49 low / 50 normal."""
    from src.engine.te_metrics import compute_te_rr

    def _tier(n: int) -> str:
        pairs = [_pair(profit_rate=1.0) for _ in range(n)]
        return compute_te_rr(pairs, now=NOW).sample_tier

    assert _tier(19) == "insufficient"
    assert _tier(20) == "low"
    assert _tier(49) == "low"
    assert _tier(50) == "normal"


def test_verdict_gate_and_sign():
    """verdict: N<20 undecided / TE>0 superior / TE<0 inferior / TE==0 flat."""
    from src.engine.te_metrics import compute_te_rr

    # N<20 → undecided (TE 부호 무관)
    small = [_pair(profit_rate=5.0) for _ in range(10)]
    assert compute_te_rr(small, now=NOW).verdict == "undecided"

    # N≥20, TE>0 → superior
    sup = [_pair(profit_rate=3.0) for _ in range(15)] + [
        _pair(profit_rate=-1.0) for _ in range(10)
    ]
    m_sup = compute_te_rr(sup, now=NOW)
    assert m_sup.n == 25 and m_sup.te_pct > 0
    assert m_sup.verdict == "superior"

    # N≥20, TE<0 → inferior
    inf = [_pair(profit_rate=1.0) for _ in range(10)] + [
        _pair(profit_rate=-3.0) for _ in range(15)
    ]
    m_inf = compute_te_rr(inf, now=NOW)
    assert m_inf.te_pct < 0
    assert m_inf.verdict == "inferior"

    # N≥20, TE==0 → flat
    flat = [_pair(profit_rate=2.0) for _ in range(10)] + [
        _pair(profit_rate=-2.0) for _ in range(10)
    ]
    m_flat = compute_te_rr(flat, now=NOW)
    assert m_flat.te_pct == pytest.approx(0.0)
    assert m_flat.verdict == "flat"


# ===========================================================================
# F-B6 — 구조 태그 (4분면)
# ===========================================================================
def test_structure_tag_quadrants():
    """저승률·고RR robust / 고승률·저RR fragile / 그 외 balanced. 게이트 미충족 None."""
    from src.engine.te_metrics import compute_te_rr

    # 저승률(8/25=0.32)·고RR(10/2=5.0) → robust (돌파 전형)
    robust = [_pair(profit_rate=10.0) for _ in range(8)] + [
        _pair(profit_rate=-2.0) for _ in range(17)
    ]
    mr = compute_te_rr(robust, now=NOW)
    assert mr.win_rate < 0.5 and mr.rr >= 1.0
    assert mr.structure_tag == "robust"

    # 고승률(18/25=0.72)·저RR(2/8=0.25) → fragile
    fragile = [_pair(profit_rate=2.0) for _ in range(18)] + [
        _pair(profit_rate=-8.0) for _ in range(7)
    ]
    mf = compute_te_rr(fragile, now=NOW)
    assert mf.win_rate >= 0.5 and mf.rr < 1.0
    assert mf.structure_tag == "fragile"

    # 저승률(8/25=0.32)·저RR(1/3=0.33) → balanced (robust/fragile 어디에도 미해당)
    balanced = [_pair(profit_rate=1.0) for _ in range(8)] + [
        _pair(profit_rate=-3.0) for _ in range(17)
    ]
    mb = compute_te_rr(balanced, now=NOW)
    assert mb.win_rate < 0.5 and mb.rr < 1.0
    assert mb.structure_tag == "balanced"

    # N<20 → None
    small = [_pair(profit_rate=5.0) for _ in range(10)] + [
        _pair(profit_rate=-2.0) for _ in range(5)
    ]
    assert compute_te_rr(small, now=NOW).structure_tag is None

    # N≥20 이지만 min(W,L)<5 → rr_available False → structure_tag None
    no_rr = [_pair(profit_rate=5.0) for _ in range(21)] + [
        _pair(profit_rate=-2.0) for _ in range(3)
    ]
    m_no = compute_te_rr(no_rr, now=NOW)
    assert m_no.n == 24 and m_no.rr_available is False
    assert m_no.structure_tag is None


# ===========================================================================
# F-B1 — 청산일 윈도우 필터
# ===========================================================================
def test_window_filter_by_sell_date():
    """sell_date < now−window_days 왕복은 모집단 제외 (청산일 기준)."""
    from src.engine.te_metrics import compute_te_rr

    pairs = [
        _pair(profit_rate=10.0, sell_date="2026-07-15"),  # 윈도우 내
        _pair(profit_rate=-50.0, sell_date="2026-03-01"),  # 윈도우 밖 (제외)
    ]
    m = compute_te_rr(pairs, now=NOW, window_days=90)

    assert m.n == 1, "윈도우 밖 왕복 제외"
    assert m.te_pct == pytest.approx(10.0), "-50 미포함"


def test_window_includes_roundtrip_closed_within_window_regardless_of_buy_date():
    """매수 D-100(윈도우 밖) 이지만 청산 D-30(윈도우 내) → 포함 (경계 미절단)."""
    from src.engine.te_metrics import compute_te_rr

    p = _pair(profit_rate=7.0, sell_date="2026-07-03")  # 청산 D-30
    p["buy_date"] = "2026-04-24"  # 매수 D-100 (필터 무관)
    m = compute_te_rr([p], now=NOW, window_days=90)

    assert m.n == 1
    assert m.te_pct == pytest.approx(7.0)


# ===========================================================================
# F-B9 — 미실현(open) 제외 + 부분체결 왕복 1건
# ===========================================================================
def test_open_pairs_excluded():
    """status=='open'(미실현) 왕복은 모집단 제외."""
    from src.engine.te_metrics import compute_te_rr

    pairs = [
        _pair(profit_rate=10.0, sell_date="2026-08-01", status="closed"),
        _pair(profit_rate=None, profit_loss=None, sell_date=None, status="open"),
    ]
    m = compute_te_rr(pairs, now=NOW)

    assert m.n == 1, "open 제외"
    assert m.te_pct == pytest.approx(10.0)


def test_partial_fill_folded_counts_single_roundtrip():
    """get_trade_pairs 가 분할매도를 왕복 1건으로 접은 전제 → closed 행 개수로 N 정확."""
    from src.engine.te_metrics import compute_te_rr

    # 각 closed 행 = 왕복 1건 (분할매도가 3거래로 부풀지 않음)
    pairs = [
        _pair(profit_rate=5.0, sell_date="2026-08-01"),
        _pair(profit_rate=-3.0, sell_date="2026-08-01"),
    ]
    m = compute_te_rr(pairs, now=NOW)

    assert m.n == 2, "PARTIAL 이중카운트 부재 — closed 행 개수 정확"


# ===========================================================================
# 엣지 — 빈 모집단 + strategy_id 전달
# ===========================================================================
def test_empty_population_safe_defaults():
    """윈도우 내 closed 0건(BFB/VCP N0) → 안전 디폴트."""
    from src.engine.te_metrics import compute_te_rr

    m = compute_te_rr([], now=NOW, strategy_id="bull_flag_breakout")

    assert m.strategy_id == "bull_flag_breakout"
    assert m.n == 0
    assert m.win == 0 and m.loss == 0 and m.even == 0
    assert m.te_pct == 0.0
    assert m.rr is None
    assert m.required_rr is None
    assert m.rr_available is False
    assert m.sample_tier == "insufficient"
    assert m.verdict == "undecided"
    assert m.structure_tag is None
    assert m.single_trade_dominant is False


def test_strategy_id_passthrough():
    """strategy_id 인자 → TeRrMetrics.strategy_id 반영."""
    from src.engine.te_metrics import compute_te_rr

    m = compute_te_rr([_pair(profit_rate=1.0)], now=NOW, strategy_id="donchian_swing")
    assert m.strategy_id == "donchian_swing"
