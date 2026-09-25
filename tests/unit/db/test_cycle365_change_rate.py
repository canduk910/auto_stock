"""사이클 365 P4 — stock_master_daily.change_rate 앞으로 계산 회귀 가드.

배경 (`_workspace/reports/2026-09-25_daily_and_advice_review.md` §4 F-C):
FHKST03010100 output2(일봉)에는 `prdy_ctrt`(전일 대비율)가 없다 — `output1`
(단건 요약) 전용 필드다. `_KIS_KEY_CHANGE_RATE="prdy_ctrt"` 를 그대로 읽던
구현은 적재 시작(06-12)부터 `change_rate` 전 행이 0 이었다(실측 — `change_rate
<> 0` 인 행 0건).

시정: `prdy_vrss`(전일 대비, 부호 포함 원 단위) ÷ 전일종가 × 100 으로 후처리
산출한다. 전일종가 = 종가 − `prdy_vrss`(`scanner._trade_amount_key` 의
`prdy_close = stck_prpr - prdy_vrss` 와 같은 부호 규약). 과거 적재 행 백필은
범위 밖(DB UPDATE 는 별도 승인) — 이 사이클은 **앞으로 적재할 행**만 고친다.

회귀 가드 매트릭스:
- G-365-P4-1 — 실제 KIS output2 형태(prdy_ctrt 없음)에서 prdy_vrss 로 등락률 산출
- G-365-P4-2 — 하락일(음수 prdy_vrss) 부호 보존
- G-365-P4-3 — prdy_vrss_sign 교차검증으로 부호 누락 원본 보정
- G-365-P4-4 — 보합(sign=3)은 0.0
- G-365-P4-5 — prdy_vrss 결측 시 0.0 (과거 동작과 동일값 — graceful)
- G-365-P4-6 — 분모(전일종가) 0 이면 0.0 (ZeroDivisionError 미발생)
- G-365-P4-7 — `prdy_ctrt` 가 있으면(미래 호환) 그 값을 그대로 쓴다
- G-365-P4-8 — `_candle_to_row` 종단 통합 (upsert 경로 전체)
- G-365-P4-9 — 매매 코드는 이 칼럼을 읽지 않는다(회귀 방지 grep 가드)
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from src.db.stock_master_daily import _candle_to_row, _derive_change_rate

pytestmark = pytest.mark.unit


def _real_output2_row(bas_dd="20260923", close="71000", vrss="-1000", sign="5") -> dict:
    """실제 FHKST03010100 output2 row 형태 — `prdy_ctrt` 필드 자체가 없다.

    docs/kis/domestic-stock-quote.md:5514-5518 Response Body 표 + KIS MCP
    `chk_inquire_daily_itemchartprice.py` COLUMN_MAPPING 재확인 — output2 는
    stck_bsop_date/stck_clpr/stck_oprc/stck_hgpr/stck_lwpr/acml_vol/
    acml_tr_pbmn/flng_cls_code/prtt_rate/mod_yn/prdy_vrss_sign/prdy_vrss/
    revl_issu_reas 뿐이다.
    """
    return {
        "stck_bsop_date": bas_dd,
        "stck_oprc": "70500",
        "stck_hgpr": "71500",
        "stck_lwpr": "70000",
        "stck_clpr": close,
        "acml_vol": "1000000",
        "acml_tr_pbmn": "71000000000",
        "flng_cls_code": "00",
        "prtt_rate": "0",
        "mod_yn": "N",
        "prdy_vrss_sign": sign,
        "prdy_vrss": vrss,
        "revl_issu_reas": "",
    }


# ---------------------------------------------------------------------------
# G-365-P4-1/2 — 실제 output2 형태에서 정상 계산 (하락일)
# ---------------------------------------------------------------------------
def test_g365_p4_1_derives_from_prdy_vrss_when_prdy_ctrt_absent():
    row = _real_output2_row(close="71000", vrss="-1000", sign="5")
    assert "prdy_ctrt" not in row, "실제 output2 는 prdy_ctrt 를 아예 갖지 않는다"

    rate = _derive_change_rate(row)

    # 전일종가 = 71000 - (-1000) = 72000, 등락률 = -1000/72000*100
    assert rate == pytest.approx(-1.3889, abs=1e-4)


def test_g365_p4_2_up_day_positive_vrss_positive_rate():
    row = _real_output2_row(close="71000", vrss="1000", sign="2")
    rate = _derive_change_rate(row)
    # 전일종가 = 71000 - 1000 = 70000, 등락률 = 1000/70000*100
    assert rate == pytest.approx(1.4286, abs=1e-4)


# ---------------------------------------------------------------------------
# G-365-P4-3 — sign 교차검증 (원본 문자열에 부호가 빠진 경우 보정)
# ---------------------------------------------------------------------------
def test_g365_p4_3_sign_mismatch_corrected_down():
    """vrss 문자열이 양수인데 sign 이 하락(4/5)이면 음수로 보정한다."""
    row = _real_output2_row(close="71000", vrss="1000", sign="5")
    rate = _derive_change_rate(row)
    assert rate == pytest.approx(-1.3889, abs=1e-4)


def test_g365_p4_3_sign_mismatch_corrected_up():
    """vrss 문자열이 음수인데 sign 이 상승(1/2)이면 양수로 보정한다."""
    row = _real_output2_row(close="71000", vrss="-1000", sign="2")
    rate = _derive_change_rate(row)
    assert rate == pytest.approx(1.4286, abs=1e-4)


# ---------------------------------------------------------------------------
# G-365-P4-4 — 보합
# ---------------------------------------------------------------------------
def test_g365_p4_4_flat_sign_forces_zero():
    row = _real_output2_row(close="71000", vrss="0", sign="3")
    assert _derive_change_rate(row) == 0.0


# ---------------------------------------------------------------------------
# G-365-P4-5/6 — graceful 결측·분모 0
# ---------------------------------------------------------------------------
def test_g365_p4_5_missing_prdy_vrss_returns_zero():
    row = {"stck_bsop_date": "20260923", "stck_clpr": "71000"}
    assert _derive_change_rate(row) == 0.0


def test_g365_p4_6_zero_denominator_returns_zero_no_raise():
    """전일종가 = 종가 - vrss = 0 이면 ZeroDivisionError 없이 0.0."""
    row = _real_output2_row(close="1000", vrss="1000", sign="2")
    assert _derive_change_rate(row) == 0.0


# ---------------------------------------------------------------------------
# G-365-P4-7 — prdy_ctrt 미래 호환(있으면 우선)
# ---------------------------------------------------------------------------
def test_g365_p4_7_prdy_ctrt_present_wins_over_derived():
    row = _real_output2_row(close="71000", vrss="-1000", sign="5")
    row["prdy_ctrt"] = "9.99"
    assert _derive_change_rate(row) == pytest.approx(9.99)


# ---------------------------------------------------------------------------
# G-365-P4-8 — _candle_to_row 종단 통합
# ---------------------------------------------------------------------------
def test_g365_p4_8_candle_to_row_end_to_end():
    row = _real_output2_row(close="71000", vrss="-1000", sign="5")
    db_row = _candle_to_row("005930", row)
    assert db_row is not None
    assert db_row["change_rate"] == pytest.approx(-1.3889, abs=1e-4)
    assert db_row["close_price"] == 71000
    # raw JSONB 는 원본 그대로 보존 (G-AST1)
    assert db_row["raw"]["prdy_vrss"] == "-1000"


# ---------------------------------------------------------------------------
# G-365-P4-9 — 매매 코드가 이 칼럼을 읽지 않는다는 grep 회귀 가드
# ---------------------------------------------------------------------------
def test_g365_p4_9_no_trading_code_reads_stock_master_daily_change_rate():
    """`stock_master_daily.change_rate` 는 UI 표시 전용이다 — 전략/리스크/스캐너가
    이 칼럼(문자열 리터럴 "change_rate" 딕셔너리 접근)을 읽으면 이 가드가 붉어진다.

    `src/db/stock_master_daily.py` 자신(정의처)과 `src/engine/risk.py`·
    `src/engine/scheduler.py`·전략 모듈들의 **실시간 change_rate**(시가 대비 등,
    이 테이블과 무관한 별개 변수)는 대상에서 제외한다 — 그 모듈들은 이 테이블의
    row dict 를 애초에 다루지 않는다(`_candle_to_row`/`get_recent_daily*` 반환값을
    `["change_rate"]`/`.get("change_rate")` 로 접근하는 호출부가 있는지만 잰다).
    """
    engine_dir = Path(__file__).resolve().parents[3] / "src" / "engine"
    offenders: list[str] = []

    for py_file in engine_dir.rglob("*.py"):
        source = py_file.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source, filename=str(py_file))
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            # dict["change_rate"] 또는 dict.get("change_rate") 형태만 딕셔너리
            # 접근으로 간주한다 — 지역 변수 대입(`change_rate = ...`)은 이 테이블과
            # 무관한 실시간 계산이라 대상이 아니다.
            if isinstance(node, ast.Subscript) and isinstance(node.ctx, ast.Load):
                key = node.slice
                if isinstance(key, ast.Constant) and key.value == "change_rate":
                    offenders.append(f"{py_file}:{node.lineno} (subscript)")
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr == "get" and node.args:
                    first = node.args[0]
                    if isinstance(first, ast.Constant) and first.value == "change_rate":
                        offenders.append(f"{py_file}:{node.lineno} (.get)")

    assert offenders == [], (
        "src/engine/ 안에서 change_rate 딕셔너리 키를 읽는 코드가 발견됐다 — "
        "stock_master_daily.change_rate 는 UI 표시 전용이라는 계약을 재확인할 것: "
        f"{offenders}"
    )
