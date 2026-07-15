"""사이클 C2 — 퀀트 재무필터 순수 함수 (마법공식 + F-Score-7) Red 테스트.

승인 계획: ~/.claude/plans/partitioned-kindling-lollipop.md (C2 즉시 착수)

대상: src/engine/quant_score.py (신규 순수 함수 모듈, 아직 미존재 → ImportError 로 Red)

성격: 순수 함수 (DB/HTTP/시계 미접촉) → mock/freeze_time 불필요.
매매 무관 (계산 계층, C3/C4 에서 통합·활성).

## Red 로 못박는 계약

### compute_f_score_7(curr, prev) -> int | None
당기 vs 전기 2기 비교, 7지표 각 +1 (최대 7):
  1. cptl_ntin_rate > 0                          (ROA 양수)
  2. curr.cptl_ntin_rate > prev.cptl_ntin_rate   (ΔROA>0)
  3. curr.lblt_rate < prev.lblt_rate             (부채비율↓)
  4. curr.crnt_rate > prev.crnt_rate             (유동비율↑)
  5. curr.sale_totl_rate > prev.sale_totl_rate   (매출총이익율↑)
  6. curr.sale_account/curr.total_aset
       > prev.sale_account/prev.total_aset        (총자산회전율↑, 분모>0 가드)
  7. curr.cpfn <= prev.cpfn                       (자본금 근사 불변/감소)
- 결측/0분모 graceful: 개별 지표 계산 불가 → 그 지표 미가점(+0), 전체 계속.
- 2기 부족(prev=None 또는 필수 필드 전부 결측) → None (fail-open 신호).

### compute_magic_formula(series_by_ticker, mktcap_by_ticker) -> dict[str, dict]
유니버스 상대 순위:
- Earnings Yield: ev_ebitda>0 → ey=1/ev_ebitda, 아니면 폴백 ey=bsop_prti/EV
    (EV = 시총(원) + total_lblt, EV>0 가드). 둘 다 불가 → ey=None.
- ROC: bsop_prti / ((cras - flow_lblt) + fxas) (분모>0 가드, 아니면 None).
- ey_rank/roc_rank: 유니버스 내 내림차순 (높을수록 우량=순위 1). None 은 최하위/제외.
- mf_rank = ey_rank + roc_rank (낮을수록 우량).
- 결정성: 동일 입력 → 동일 랭킹 (정렬 안정성).
"""

import pytest

# 모듈 부재 → ImportError 로 Red 확인. 모듈 생성 후 Green.
from src.engine.quant_score import compute_f_score_7, compute_magic_formula


# ---------------------------------------------------------------------------
# 헬퍼: F-Score-7 기저 재무 dict (7지표 전부 미가점되는 중립 기준점)
# ---------------------------------------------------------------------------
def _base_fin(**overrides):
    """모든 지표가 '미가점' 상태인 중립 기준 재무 dict.

    - cptl_ntin_rate = 0        → 지표1 미가점 (양수 아님)
    - curr==prev 동일값이면      → 지표2~5 미가점 (> 아님)
    - total 회전율 동일          → 지표6 미가점
    - cpfn 동일                 → 지표7 가점 (<= 이므로 동일도 통과)
    개별 테스트가 override 로 특정 지표만 켠다.
    """
    base = {
        "cptl_ntin_rate": 0.0,
        "lblt_rate": 100.0,
        "crnt_rate": 100.0,
        "sale_totl_rate": 20.0,
        "sale_account": 1000.0,
        "total_aset": 2000.0,
        "cpfn": 500.0,
    }
    base.update(overrides)
    return base


# ===========================================================================
# 함수 1: compute_f_score_7 — 7지표 경계
# ===========================================================================
class TestFScore7IndicatorBoundaries:
    """7지표 각각 같음/초과/미만 경계에서 정확히 +1/+0 판정."""

    # --- 지표1: cptl_ntin_rate > 0 (ROA 양수) ---
    def test_g_c2_ind1_roa_positive_scores(self):
        """ROA>0 이면 지표1 가점. 나머지 지표는 미가점 기준 유지."""
        curr = _base_fin(cptl_ntin_rate=5.0)
        prev = _base_fin(cptl_ntin_rate=5.0)  # 동일 → 지표2 미가점
        # 지표1(+1), 지표7 cpfn 동일(+1) = 2점
        assert compute_f_score_7(curr, prev) == 2

    def test_g_c2_ind1_roa_zero_no_score(self):
        """ROA 정확히 0 → 미가점 (> 0 이 아님)."""
        curr = _base_fin(cptl_ntin_rate=0.0)
        prev = _base_fin(cptl_ntin_rate=0.0)
        # 지표1 미가점, 지표7 cpfn 동일(+1) = 1점
        assert compute_f_score_7(curr, prev) == 1

    def test_g_c2_ind1_roa_negative_no_score(self):
        """ROA 음수 → 미가점."""
        curr = _base_fin(cptl_ntin_rate=-3.0)
        prev = _base_fin(cptl_ntin_rate=-3.0)
        assert compute_f_score_7(curr, prev) == 1  # 지표7만

    # --- 지표2: ΔROA > 0 ---
    def test_g_c2_ind2_delta_roa_positive_scores(self):
        """당기 ROA > 전기 ROA → 지표2 가점 (+ 지표1 양수)."""
        curr = _base_fin(cptl_ntin_rate=8.0)
        prev = _base_fin(cptl_ntin_rate=5.0)
        # 지표1(+1) + 지표2(+1) + 지표7(+1) = 3
        assert compute_f_score_7(curr, prev) == 3

    def test_g_c2_ind2_delta_roa_equal_no_score(self):
        """당기 ROA == 전기 ROA → 지표2 미가점 (> 아님)."""
        curr = _base_fin(cptl_ntin_rate=5.0)
        prev = _base_fin(cptl_ntin_rate=5.0)
        assert compute_f_score_7(curr, prev) == 2  # 지표1 + 지표7

    def test_g_c2_ind2_delta_roa_negative_no_score(self):
        """당기 ROA < 전기 ROA → 지표2 미가점."""
        curr = _base_fin(cptl_ntin_rate=3.0)
        prev = _base_fin(cptl_ntin_rate=5.0)
        assert compute_f_score_7(curr, prev) == 2  # 지표1(3>0) + 지표7

    # --- 지표3: lblt_rate 감소 (부채비율↓) ---
    def test_g_c2_ind3_debt_ratio_down_scores(self):
        curr = _base_fin(lblt_rate=80.0)
        prev = _base_fin(lblt_rate=100.0)
        assert compute_f_score_7(curr, prev) == 2  # 지표3 + 지표7

    def test_g_c2_ind3_debt_ratio_equal_no_score(self):
        curr = _base_fin(lblt_rate=100.0)
        prev = _base_fin(lblt_rate=100.0)
        assert compute_f_score_7(curr, prev) == 1  # 지표7만

    def test_g_c2_ind3_debt_ratio_up_no_score(self):
        curr = _base_fin(lblt_rate=120.0)
        prev = _base_fin(lblt_rate=100.0)
        assert compute_f_score_7(curr, prev) == 1

    # --- 지표4: crnt_rate 증가 (유동비율↑) ---
    def test_g_c2_ind4_current_ratio_up_scores(self):
        curr = _base_fin(crnt_rate=150.0)
        prev = _base_fin(crnt_rate=100.0)
        assert compute_f_score_7(curr, prev) == 2

    def test_g_c2_ind4_current_ratio_equal_no_score(self):
        curr = _base_fin(crnt_rate=100.0)
        prev = _base_fin(crnt_rate=100.0)
        assert compute_f_score_7(curr, prev) == 1

    # --- 지표5: sale_totl_rate 증가 (매출총이익율↑) ---
    def test_g_c2_ind5_gross_margin_up_scores(self):
        curr = _base_fin(sale_totl_rate=25.0)
        prev = _base_fin(sale_totl_rate=20.0)
        assert compute_f_score_7(curr, prev) == 2

    def test_g_c2_ind5_gross_margin_equal_no_score(self):
        curr = _base_fin(sale_totl_rate=20.0)
        prev = _base_fin(sale_totl_rate=20.0)
        assert compute_f_score_7(curr, prev) == 1

    # --- 지표6: 총자산회전율 sale_account/total_aset 증가 ---
    def test_g_c2_ind6_asset_turnover_up_scores(self):
        # curr: 1200/2000 = 0.60 > prev: 1000/2000 = 0.50
        curr = _base_fin(sale_account=1200.0, total_aset=2000.0)
        prev = _base_fin(sale_account=1000.0, total_aset=2000.0)
        assert compute_f_score_7(curr, prev) == 2  # 지표6 + 지표7

    def test_g_c2_ind6_asset_turnover_equal_no_score(self):
        # 동일 비율 0.5 == 0.5
        curr = _base_fin(sale_account=1000.0, total_aset=2000.0)
        prev = _base_fin(sale_account=1000.0, total_aset=2000.0)
        assert compute_f_score_7(curr, prev) == 1

    def test_g_c2_ind6_asset_turnover_zero_denom_graceful(self):
        """total_aset == 0 → 지표6 계산 불가 → 미가점, 전체는 계속."""
        curr = _base_fin(sale_account=1000.0, total_aset=0.0)
        prev = _base_fin(sale_account=1000.0, total_aset=2000.0)
        # 지표6 미가점 (0분모), 지표7 cpfn 동일(+1) = 1
        assert compute_f_score_7(curr, prev) == 1

    def test_g_c2_ind6_prev_zero_denom_graceful(self):
        """prev.total_aset == 0 → 지표6 미가점 graceful."""
        curr = _base_fin(sale_account=1000.0, total_aset=2000.0)
        prev = _base_fin(sale_account=1000.0, total_aset=0.0)
        assert compute_f_score_7(curr, prev) == 1  # 지표7만

    # --- 지표7: cpfn 불변/감소 (자본금 근사) ---
    def test_g_c2_ind7_capital_decrease_scores(self):
        curr = _base_fin(cpfn=400.0)
        prev = _base_fin(cpfn=500.0)
        assert compute_f_score_7(curr, prev) == 1

    def test_g_c2_ind7_capital_equal_scores(self):
        """cpfn 동일 → <= 이므로 가점."""
        curr = _base_fin(cpfn=500.0)
        prev = _base_fin(cpfn=500.0)
        assert compute_f_score_7(curr, prev) == 1

    def test_g_c2_ind7_capital_increase_no_score(self):
        """cpfn 증가 (유상증자/오버행) → 미가점."""
        curr = _base_fin(cpfn=600.0)
        prev = _base_fin(cpfn=500.0)
        assert compute_f_score_7(curr, prev) == 0


# ===========================================================================
# 함수 1: compute_f_score_7 — 총점 0/7/1 경계
# ===========================================================================
class TestFScore7TotalScoreBoundaries:
    """0점, 7점 만점, 1점(≤1 배제 경계) 시나리오."""

    def test_g_c2_score_zero(self):
        """모든 지표 미가점 → 0점.

        지표1 ROA=0(미가점), 지표2~6 악화, 지표7 cpfn 증가(미가점).
        """
        curr = _base_fin(
            cptl_ntin_rate=0.0,   # 지표1 미가점
            lblt_rate=120.0,      # 부채비율↑ 지표3 미가점
            crnt_rate=80.0,       # 유동비율↓ 지표4 미가점
            sale_totl_rate=15.0,  # 매출총이익율↓ 지표5 미가점
            sale_account=800.0,   # 회전율↓ 지표6 미가점 (0.4)
            total_aset=2000.0,
            cpfn=600.0,           # 자본금↑ 지표7 미가점
        )
        prev = _base_fin(
            cptl_ntin_rate=0.0,   # ΔROA=0 지표2 미가점
            lblt_rate=100.0,
            crnt_rate=100.0,
            sale_totl_rate=20.0,
            sale_account=1000.0,  # 0.5
            total_aset=2000.0,
            cpfn=500.0,
        )
        assert compute_f_score_7(curr, prev) == 0

    def test_g_c2_score_seven_perfect(self):
        """7지표 전부 개선 → 7점 만점."""
        curr = _base_fin(
            cptl_ntin_rate=8.0,   # 지표1 양수 + 지표2 ΔROA>0
            lblt_rate=80.0,       # 지표3 부채비율↓
            crnt_rate=150.0,      # 지표4 유동비율↑
            sale_totl_rate=25.0,  # 지표5 매출총이익율↑
            sale_account=1400.0,  # 지표6 회전율↑ (0.70)
            total_aset=2000.0,
            cpfn=400.0,           # 지표7 자본금↓
        )
        prev = _base_fin(
            cptl_ntin_rate=5.0,
            lblt_rate=100.0,
            crnt_rate=100.0,
            sale_totl_rate=20.0,
            sale_account=1000.0,  # 0.50
            total_aset=2000.0,
            cpfn=500.0,
        )
        assert compute_f_score_7(curr, prev) == 7

    def test_g_c2_score_one_exclusion_boundary(self):
        """정확히 1점 (VB C4 에서 ≤1 배제 경계 = 배제 대상).

        지표7 cpfn 동일만 가점, 나머지 미가점.
        """
        curr = _base_fin(
            cptl_ntin_rate=0.0,
            lblt_rate=100.0,
            crnt_rate=100.0,
            sale_totl_rate=20.0,
            sale_account=1000.0,
            total_aset=2000.0,
            cpfn=500.0,
        )
        prev = _base_fin(
            cptl_ntin_rate=0.0,
            lblt_rate=100.0,
            crnt_rate=100.0,
            sale_totl_rate=20.0,
            sale_account=1000.0,
            total_aset=2000.0,
            cpfn=500.0,
        )
        assert compute_f_score_7(curr, prev) == 1

    def test_g_c2_score_two_pass_boundary(self):
        """정확히 2점 (VB C4 에서 ≥2 통과 경계 = 통과 대상).

        지표1(ROA 양수) + 지표7(cpfn 동일) = 2.
        """
        curr = _base_fin(cptl_ntin_rate=5.0, cpfn=500.0)
        prev = _base_fin(cptl_ntin_rate=5.0, cpfn=500.0)
        assert compute_f_score_7(curr, prev) == 2


# ===========================================================================
# 함수 1: compute_f_score_7 — 결측/2기 부족 graceful
# ===========================================================================
class TestFScore7MissingAndInsufficient:
    """개별 지표 결측 미가점 + 2기 부족 None (fail-open)."""

    def test_g_c2_missing_indicator_no_score_others_continue(self):
        """특정 지표 필드 결측 → 그 지표만 미가점, 나머지 계속."""
        # cptl_ntin_rate 결측 → 지표1·2 미가점, 나머지 정상 평가
        curr = _base_fin(lblt_rate=80.0, cpfn=400.0)  # 지표3 + 지표7
        prev = _base_fin(lblt_rate=100.0, cpfn=500.0)
        curr.pop("cptl_ntin_rate")
        prev.pop("cptl_ntin_rate")
        # 지표1·2 미가점, 지표3(+1), 지표7(+1) = 2
        assert compute_f_score_7(curr, prev) == 2

    def test_g_c2_missing_indicator_none_value(self):
        """지표 값이 None → 미가점 graceful (KeyError/TypeError 없음)."""
        curr = _base_fin(cptl_ntin_rate=None, cpfn=500.0)
        prev = _base_fin(cptl_ntin_rate=None, cpfn=500.0)
        # 지표1·2 미가점, 지표7 cpfn 동일(+1) = 1
        assert compute_f_score_7(curr, prev) == 1

    def test_g_c2_missing_indicator_nonnumeric_string(self):
        """비숫자 문자열 값 → 미가점 graceful."""
        curr = _base_fin(lblt_rate="", crnt_rate="N/A")
        prev = _base_fin(lblt_rate="", crnt_rate="N/A")
        # 지표3·4 미가점, 지표7만 = 1
        assert compute_f_score_7(curr, prev) == 1

    def test_g_c2_prev_none_returns_none(self):
        """prev = None (2기 부족) → None 반환 (fail-open, 배제 아님)."""
        curr = _base_fin(cptl_ntin_rate=8.0)
        assert compute_f_score_7(curr, None) is None

    def test_g_c2_prev_all_missing_returns_none(self):
        """prev 필수 필드 전부 결측 → None (2기 유효 비교 불가)."""
        curr = _base_fin(cptl_ntin_rate=8.0, lblt_rate=80.0)
        prev = {}  # 빈 dict = 전부 결측
        assert compute_f_score_7(curr, prev) is None

    def test_g_c2_curr_none_returns_none(self):
        """curr = None → None (당기 없이 점수 불가)."""
        prev = _base_fin(cptl_ntin_rate=5.0)
        assert compute_f_score_7(None, prev) is None

    def test_g_c2_return_type_is_int_or_none(self):
        """반환 타입 계약: 유효 시 int, 부족 시 None (float/bool 금지)."""
        curr = _base_fin(cptl_ntin_rate=5.0)
        prev = _base_fin(cptl_ntin_rate=3.0)
        result = compute_f_score_7(curr, prev)
        assert isinstance(result, int)
        assert not isinstance(result, bool)  # bool 은 int 서브클래스라 명시 차단
        assert compute_f_score_7(curr, None) is None


# ===========================================================================
# 함수 2: compute_magic_formula — EY 직접/폴백
# ===========================================================================
class TestMagicFormulaEarningsYield:
    """Earnings Yield = ev_ebitda 직접 우선, 폴백 bsop_prti/EV."""

    def test_g_c2_ey_direct_from_ev_ebitda(self):
        """ev_ebitda > 0 → ey = 1/ev_ebitda (직접)."""
        series = {
            "A": {
                "ev_ebitda": 10.0,     # ey = 0.1
                "bsop_prti": 999.0,    # 폴백 미사용 (직접 우선)
                "total_lblt": 0.0,
                "cras": 100.0, "flow_lblt": 10.0, "fxas": 10.0,
            },
        }
        mktcap = {"A": 1_000_000.0}
        out = compute_magic_formula(series, mktcap)
        assert out["A"]["ey"] == pytest.approx(0.1)

    def test_g_c2_ey_fallback_when_ev_ebitda_nonpositive(self):
        """ev_ebitda <= 0 → 폴백 ey = bsop_prti / EV, EV = 시총 + total_lblt."""
        series = {
            "A": {
                "ev_ebitda": 0.0,      # 직접 불가
                "bsop_prti": 200.0,
                "total_lblt": 800.0,
                "cras": 100.0, "flow_lblt": 10.0, "fxas": 10.0,
            },
        }
        mktcap = {"A": 1200.0}  # EV = 1200 + 800 = 2000
        out = compute_magic_formula(series, mktcap)
        # ey = 200 / 2000 = 0.1
        assert out["A"]["ey"] == pytest.approx(0.1)

    def test_g_c2_ey_fallback_negative_ev_ebitda(self):
        """ev_ebitda 음수 (EBITDA<0) → 폴백 경로."""
        series = {
            "A": {
                "ev_ebitda": -5.0,
                "bsop_prti": 300.0,
                "total_lblt": 1000.0,
                "cras": 100.0, "flow_lblt": 10.0, "fxas": 10.0,
            },
        }
        mktcap = {"A": 2000.0}  # EV = 3000
        out = compute_magic_formula(series, mktcap)
        assert out["A"]["ey"] == pytest.approx(0.1)  # 300/3000

    def test_g_c2_ey_none_when_both_unavailable(self):
        """ev_ebitda<=0 AND EV<=0 → ey=None (랭킹 제외)."""
        series = {
            "A": {
                "ev_ebitda": 0.0,
                "bsop_prti": 300.0,
                "total_lblt": 0.0,
                "cras": 100.0, "flow_lblt": 10.0, "fxas": 10.0,
            },
        }
        mktcap = {"A": 0.0}  # EV = 0 → 폴백 0분모 가드
        out = compute_magic_formula(series, mktcap)
        assert out["A"]["ey"] is None

    def test_g_c2_ey_none_when_ev_zero_and_no_ebitda(self):
        """시총 결측(0) + total_lblt 0 → EV=0 → ey None graceful."""
        series = {
            "A": {
                "ev_ebitda": 0.0,
                "bsop_prti": 100.0,
                "total_lblt": 0.0,
                "cras": 50.0, "flow_lblt": 5.0, "fxas": 5.0,
            },
        }
        mktcap = {}  # A 시총 결측
        out = compute_magic_formula(series, mktcap)
        assert out["A"]["ey"] is None


# ===========================================================================
# 함수 2: compute_magic_formula — ROC 분모 가드
# ===========================================================================
class TestMagicFormulaROC:
    """ROC = bsop_prti / ((cras - flow_lblt) + fxas), 분모>0 가드."""

    def test_g_c2_roc_basic(self):
        """정상 ROC 계산."""
        series = {
            "A": {
                "ev_ebitda": 10.0,
                "bsop_prti": 200.0,
                "total_lblt": 0.0,
                "cras": 300.0, "flow_lblt": 100.0, "fxas": 100.0,
            },
        }
        # 분모 = (300-100)+100 = 300, roc = 200/300
        mktcap = {"A": 1000.0}
        out = compute_magic_formula(series, mktcap)
        assert out["A"]["roc"] == pytest.approx(200.0 / 300.0)

    def test_g_c2_roc_none_when_denom_zero(self):
        """분모 == 0 → roc None graceful."""
        series = {
            "A": {
                "ev_ebitda": 10.0,
                "bsop_prti": 200.0,
                "total_lblt": 0.0,
                "cras": 100.0, "flow_lblt": 100.0, "fxas": 0.0,
            },
        }
        # 분모 = (100-100)+0 = 0
        mktcap = {"A": 1000.0}
        out = compute_magic_formula(series, mktcap)
        assert out["A"]["roc"] is None

    def test_g_c2_roc_none_when_denom_negative(self):
        """분모 < 0 (운전자본 크게 음수) → roc None (>0 가드)."""
        series = {
            "A": {
                "ev_ebitda": 10.0,
                "bsop_prti": 200.0,
                "total_lblt": 0.0,
                "cras": 50.0, "flow_lblt": 200.0, "fxas": 10.0,
            },
        }
        # 분모 = (50-200)+10 = -140
        mktcap = {"A": 1000.0}
        out = compute_magic_formula(series, mktcap)
        assert out["A"]["roc"] is None

    def test_g_c2_roc_missing_fields_graceful(self):
        """ROC 구성 필드 결측 → roc None (KeyError 없음)."""
        series = {
            "A": {
                "ev_ebitda": 10.0,
                "bsop_prti": 200.0,
                "total_lblt": 0.0,
                # cras/flow_lblt/fxas 결측
            },
        }
        mktcap = {"A": 1000.0}
        out = compute_magic_formula(series, mktcap)
        assert out["A"]["roc"] is None


# ===========================================================================
# 함수 2: compute_magic_formula — 랭킹 내림차순 + 결정성
# ===========================================================================
class TestMagicFormulaRanking:
    """ey_rank/roc_rank 내림차순 + mf_rank 합산 + 결정성."""

    @staticmethod
    def _universe():
        """3종목 유니버스: EY·ROC 명확히 차별화."""
        series = {
            # 높은 EY(0.20) + 높은 ROC(0.50) = 최우량
            "TOP": {
                "ev_ebitda": 5.0,        # ey = 0.20
                "bsop_prti": 500.0,
                "total_lblt": 0.0,
                "cras": 1100.0, "flow_lblt": 100.0, "fxas": 0.0,  # roc=500/1000=0.5
            },
            # 중간 EY(0.10) + 중간 ROC(0.25)
            "MID": {
                "ev_ebitda": 10.0,       # ey = 0.10
                "bsop_prti": 250.0,
                "total_lblt": 0.0,
                "cras": 1100.0, "flow_lblt": 100.0, "fxas": 0.0,  # roc=250/1000=0.25
            },
            # 낮은 EY(0.05) + 낮은 ROC(0.10)
            "LOW": {
                "ev_ebitda": 20.0,       # ey = 0.05
                "bsop_prti": 100.0,
                "total_lblt": 0.0,
                "cras": 1100.0, "flow_lblt": 100.0, "fxas": 0.0,  # roc=100/1000=0.10
            },
        }
        mktcap = {"TOP": 1000.0, "MID": 1000.0, "LOW": 1000.0}
        return series, mktcap

    def test_g_c2_ey_rank_descending(self):
        """EY 높을수록 rank 1 (내림차순)."""
        series, mktcap = self._universe()
        out = compute_magic_formula(series, mktcap)
        assert out["TOP"]["ey_rank"] == 1
        assert out["MID"]["ey_rank"] == 2
        assert out["LOW"]["ey_rank"] == 3

    def test_g_c2_roc_rank_descending(self):
        """ROC 높을수록 rank 1 (내림차순)."""
        series, mktcap = self._universe()
        out = compute_magic_formula(series, mktcap)
        assert out["TOP"]["roc_rank"] == 1
        assert out["MID"]["roc_rank"] == 2
        assert out["LOW"]["roc_rank"] == 3

    def test_g_c2_mf_rank_sum(self):
        """mf_rank = ey_rank + roc_rank (낮을수록 우량)."""
        series, mktcap = self._universe()
        out = compute_magic_formula(series, mktcap)
        assert out["TOP"]["mf_rank"] == 2   # 1 + 1
        assert out["MID"]["mf_rank"] == 4   # 2 + 2
        assert out["LOW"]["mf_rank"] == 6   # 3 + 3

    def test_g_c2_ranking_deterministic(self):
        """동일 입력 → 동일 랭킹 (정렬 안정성, 2회 호출 identical)."""
        series, mktcap = self._universe()
        out1 = compute_magic_formula(series, mktcap)
        out2 = compute_magic_formula(series, mktcap)
        assert out1 == out2

    def test_g_c2_ranking_tie_deterministic(self):
        """동점 종목 → 결정적 순위 (재호출 시 동일 배정)."""
        series = {
            "X": {
                "ev_ebitda": 10.0, "bsop_prti": 250.0, "total_lblt": 0.0,
                "cras": 1100.0, "flow_lblt": 100.0, "fxas": 0.0,
            },
            "Y": {  # X 와 완전 동일 지표 → 동점
                "ev_ebitda": 10.0, "bsop_prti": 250.0, "total_lblt": 0.0,
                "cras": 1100.0, "flow_lblt": 100.0, "fxas": 0.0,
            },
        }
        mktcap = {"X": 1000.0, "Y": 1000.0}
        out1 = compute_magic_formula(series, mktcap)
        out2 = compute_magic_formula(series, mktcap)
        # 결정적: 동일 입력 2회 → 동일 랭크 배정
        assert out1["X"]["ey_rank"] == out2["X"]["ey_rank"]
        assert out1["Y"]["ey_rank"] == out2["Y"]["ey_rank"]

    def test_g_c2_missing_ranked_last(self):
        """ey/roc 결측(None) 종목 → 최하위 순위 (유량 종목보다 뒤)."""
        series = {
            "GOOD": {
                "ev_ebitda": 5.0, "bsop_prti": 500.0, "total_lblt": 0.0,
                "cras": 1100.0, "flow_lblt": 100.0, "fxas": 0.0,
            },
            "MISS": {  # ey/roc 둘 다 계산 불가
                "ev_ebitda": 0.0, "bsop_prti": 100.0, "total_lblt": 0.0,
                "cras": 100.0, "flow_lblt": 100.0, "fxas": 0.0,  # roc 분모 0
            },
        }
        mktcap = {"GOOD": 1000.0}  # MISS 시총 결측 → EV 0 → ey None
        out = compute_magic_formula(series, mktcap)
        assert out["MISS"]["ey"] is None
        assert out["MISS"]["roc"] is None
        # GOOD 이 MISS 보다 우량 (낮은 mf_rank)
        assert out["GOOD"]["mf_rank"] < out["MISS"]["mf_rank"]

    def test_g_c2_all_tickers_present_in_output(self):
        """입력 전 종목이 출력에 존재 (결측도 제외 아닌 None 표기)."""
        series, mktcap = self._universe()
        out = compute_magic_formula(series, mktcap)
        assert set(out.keys()) == {"TOP", "MID", "LOW"}
        for t in out:
            assert set(out[t].keys()) >= {"ey", "roc", "ey_rank", "roc_rank", "mf_rank"}

    def test_g_c2_empty_universe(self):
        """빈 유니버스 → 빈 dict (예외 없음)."""
        assert compute_magic_formula({}, {}) == {}

    def test_g_c2_single_ticker_ranks_one(self):
        """단일 종목 → rank 모두 1, mf_rank 2."""
        series = {
            "S": {
                "ev_ebitda": 10.0, "bsop_prti": 250.0, "total_lblt": 0.0,
                "cras": 1100.0, "flow_lblt": 100.0, "fxas": 0.0,
            },
        }
        mktcap = {"S": 1000.0}
        out = compute_magic_formula(series, mktcap)
        assert out["S"]["ey_rank"] == 1
        assert out["S"]["roc_rank"] == 1
        assert out["S"]["mf_rank"] == 2
