"""cycle383 — KRX ETF 일별 시세 보관소 확장의 순수 함수 테스트.

대상 = `tools/archive/krx_daily_archive.py` 의 ETF 절(cycle383) — 파싱(`_extract_etf_row`
/ `_first_present`)과 보정(`_adjust_one`, 주식과 공용)을 순수 함수로 검증한다. 이 파일은
`src/`·8영역·DB·KIS·KRX 호출을 전혀 하지 않는다 — 전부 로컬 인메모리 데이터로만 돈다.

배경: KRX Open API `/etp/etf_bydd_trd` (ETF 일별매매정보)는 2026-09-27 실측 결과 401
("Unauthorized API Call")을 반환한다 — ETP(ETF/ETN/ELW) 카테고리 서비스가 이 계정에
아직 승인되지 않아, 실제 응답 필드를 한 번도 확인하지 못했다(§ 모듈 docstring 「ETF」 절).
그래서 `_extract_etf_row` 의 필드명은 **미확인 가설**이고, 이 테스트는 (a) 가설이 맞을 때
정상 변환되는지 (b) 가설이 완전히 틀렸을 때 조용히 0 을 채우지 않고 시끄럽게(ValueError)
실패하는지를 함께 확인한다 — "추측이 틀렸을 때 숫자가 아니라 예외가 먼저 나온다"는
설계 불변식 자체가 이 테스트의 핵심 대상이다.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[3]
MODULE_PATH = ROOT / "tools" / "archive" / "krx_daily_archive.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("krx_daily_archive_c383", MODULE_PATH)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def mod():
    return _load_module()


# ══════════════════════════════════ 엔드포인트 상수 ══════════════════════════════════


def test_etf_endpoint_path_pinned(mod):
    """엔드포인트 경로 = 외부 정본 2건(krx-rs 계열 명명 관례 + pykrx-openapi constants.py) +
    실측 401(404 아님)로 확인된 값. 오타로 바뀌면 이 테스트가 잡는다."""
    assert mod._ENDPOINT_ETF_BYDD_TRD == "/etp/etf_bydd_trd"


# ══════════════════════════════════ _first_present ══════════════════════════════════


def test_first_present_returns_first_matching_key(mod):
    raw = {"ISU_SRT_CD": "069500", "ISU_NM": "KODEX 200"}
    assert mod._first_present(raw, ("ISU_CD", "ISU_SRT_CD")) == "069500"


def test_first_present_prefers_earlier_candidate(mod):
    raw = {"ISU_CD": "A069500", "ISU_SRT_CD": "069500"}
    # 첫 후보(ISU_CD)가 있으면 그것을 쓴다 — 뒤 후보로 넘어가지 않는다.
    assert mod._first_present(raw, ("ISU_CD", "ISU_SRT_CD")) == "A069500"


def test_first_present_returns_none_when_absent(mod):
    assert mod._first_present({"FOO": 1}, ("ISU_CD", "ISU_SRT_CD")) is None


# ══════════════════════════════════ _extract_etf_row ══════════════════════════════════


def _sample_etf_row(**overrides) -> dict:
    """sto/idx 계열 명명 가설을 따르는 합성 픽스처(실제 KRX 응답 아님 — §모듈 docstring)."""
    row = {
        "ISU_CD": "069500",
        "ISU_NM": "KODEX 200",
        "TDD_OPNPRC": "35,000",
        "TDD_HGPRC": "35,500",
        "TDD_LWPRC": "34,800",
        "TDD_CLSPRC": "35,200",
        "CMPPREVDD_PRC": "200",
        "ACC_TRDVOL": "1,234,567",
        "ACC_TRDVAL": "43,456,789,000",
        "MKTCAP": "5,000,000,000,000",
        "LIST_SHRS": "100,000,000",
    }
    row.update(overrides)
    return row


def test_extract_etf_row_shape_matches_stock_row(mod):
    """반환 모양이 `_row_to_list` 와 같은 12칸이어야 `merge_jsonl` 이 그대로 읽는다."""
    raw = _sample_etf_row()
    out = mod._extract_etf_row(raw)
    assert len(out) == 12
    ticker, name, o, h, l, c, prev_diff, vol, tval, mktcap, list_shrs, market = out
    assert ticker == "069500"
    assert name == "KODEX 200"
    assert (o, h, l, c) == (35000, 35500, 34800, 35200)
    assert prev_diff == 200
    assert vol == 1_234_567
    assert tval == 43_456_789_000
    assert mktcap == 5_000_000_000_000
    assert list_shrs == 100_000_000
    assert market == "ETF"


def test_extract_etf_row_uses_fallback_ticker_key(mod):
    """1차 후보(ISU_CD)가 없고 2차 후보(ISU_SRT_CD)만 있을 때도 동작해야 한다."""
    raw = _sample_etf_row()
    del raw["ISU_CD"]
    raw["ISU_SRT_CD"] = "069500"
    out = mod._extract_etf_row(raw)
    assert out[0] == "069500"


def test_extract_etf_row_uses_fallback_mktcap_candidates(mod):
    """시총 필드가 없고 순자산총액 계열 후보만 있어도 잡는다(ETF 전용 가설 분기)."""
    raw = _sample_etf_row()
    del raw["MKTCAP"]
    raw["INVSTASST_NETASST_TOTAMT"] = "9,999"
    out = mod._extract_etf_row(raw)
    assert out[9] == 9999


def test_extract_etf_row_missing_optional_fields_defaults_to_zero(mod):
    """거래대금 등 부가 필드가 없으면 0 (KRX 휴장/결측일 대비) — 필수 키(종목코드·종가)와는

    다른 취급이다."""
    raw = _sample_etf_row()
    del raw["ACC_TRDVAL"]
    out = mod._extract_etf_row(raw)
    assert out[8] == 0


def test_extract_etf_row_raises_when_core_keys_absent(mod):
    """핵심 키(종목코드·종가) 후보가 전부 없으면 ValueError — 조용한 0 채움 금지가

    이 테스트의 대상이다(가설이 틀렸을 때 데이터가 아니라 예외가 먼저 나와야 한다)."""
    raw = {"SOME_UNEXPECTED_FIELD": "1"}
    with pytest.raises(ValueError, match="ETF 응답 필드 가설이 어긋난다"):
        mod._extract_etf_row(raw)


def test_extract_etf_row_raises_when_only_ticker_present(mod):
    """종목코드는 있어도 종가 후보가 전혀 없으면 여전히 실패해야 한다(부분 가설 불일치)."""
    raw = {"ISU_CD": "069500"}
    with pytest.raises(ValueError):
        mod._extract_etf_row(raw)


# ══════════════════════════════════ normalize_etf_jsonl ══════════════════════════════════


def test_normalize_etf_jsonl_round_trip(mod, tmp_path):
    raw_path = tmp_path / "raw.jsonl"
    out_path = tmp_path / "normalized.jsonl"

    day1 = {"bas_dd": "20260924", "n_rows": 1, "rows": [_sample_etf_row()]}
    day2 = {
        "bas_dd": "20260925",
        "n_rows": 1,
        "rows": [_sample_etf_row(TDD_CLSPRC="35,400", CMPPREVDD_PRC="200")],
    }
    raw_path.write_text(
        json.dumps(day1, ensure_ascii=False) + "\n" + json.dumps(day2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    mod.normalize_etf_jsonl(str(raw_path), str(out_path))

    lines = out_path.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 2
    p1 = json.loads(lines[0])
    assert p1["bas_dd"] == "20260924"
    assert len(p1["rows"]) == 1
    assert p1["rows"][0][0] == "069500"  # ticker
    assert p1["rows"][0][11] == "ETF"  # market tag


def test_normalize_etf_jsonl_skips_blank_lines(mod, tmp_path):
    raw_path = tmp_path / "raw.jsonl"
    out_path = tmp_path / "normalized.jsonl"
    day1 = {"bas_dd": "20260924", "n_rows": 0, "rows": []}
    raw_path.write_text("\n" + json.dumps(day1, ensure_ascii=False) + "\n\n", encoding="utf-8")

    mod.normalize_etf_jsonl(str(raw_path), str(out_path))

    lines = [ln for ln in out_path.read_text(encoding="utf-8").split("\n") if ln]
    assert len(lines) == 1
    assert json.loads(lines[0])["rows"] == []


def test_normalize_etf_jsonl_drops_blank_price_rows_on_holidays(mod, tmp_path):
    """휴장일 응답은 종목 목록만 오고 가격 칸이 전부 빈 값이다(2020-10-01 실측).

    빈 종가를 0 으로 바꿔 넣으면 휴장일마다 가격 0 행이 원장에 들어가므로, 종가가 빈 행은
    버린다. 날짜 줄은 남기고 행만 비운다(`rows: []` — 기존 빈 날짜 규약과 같다).
    """
    raw_path = tmp_path / "raw.jsonl"
    out_path = tmp_path / "normalized.jsonl"
    blank = dict(TDD_CLSPRC="", TDD_OPNPRC="", TDD_HGPRC="", TDD_LWPRC="",
                 ACC_TRDVOL="", ACC_TRDVAL="", CMPPREVDD_PRC="")
    holiday = {"bas_dd": "20201001", "n_rows": 2,
               "rows": [_sample_etf_row(**blank), _sample_etf_row(ISU_CD="102110", **blank)]}
    raw_path.write_text(json.dumps(holiday, ensure_ascii=False) + "\n", encoding="utf-8")

    mod.normalize_etf_jsonl(str(raw_path), str(out_path))

    lines = [ln for ln in out_path.read_text(encoding="utf-8").split("\n") if ln]
    assert len(lines) == 1
    assert json.loads(lines[0]) == {"bas_dd": "20201001", "rows": []}


def test_normalize_etf_jsonl_drops_only_blank_close_rows(mod, tmp_path):
    """같은 날 종가가 빈 행(`""`·`"-"`)만 빠지고 가격이 있는 행은 남는다."""
    raw_path = tmp_path / "raw.jsonl"
    out_path = tmp_path / "normalized.jsonl"
    day = {"bas_dd": "20260923", "n_rows": 3, "rows": [
        _sample_etf_row(),
        _sample_etf_row(ISU_CD="102110", TDD_CLSPRC=""),
        _sample_etf_row(ISU_CD="114800", TDD_CLSPRC="-"),
    ]}
    raw_path.write_text(json.dumps(day, ensure_ascii=False) + "\n", encoding="utf-8")

    mod.normalize_etf_jsonl(str(raw_path), str(out_path))

    rows = json.loads(out_path.read_text(encoding="utf-8").strip())["rows"]
    assert [r[0] for r in rows] == ["069500"]
    assert rows[0][5] > 0  # close


def test_normalize_etf_jsonl_propagates_bad_row_error(mod, tmp_path):
    """가설이 틀린 행이 섞여 있으면 정규화 전체가 멈춘다 — 부분 변환본을 남기지 않는다."""
    raw_path = tmp_path / "raw.jsonl"
    out_path = tmp_path / "normalized.jsonl"
    bad_day = {"bas_dd": "20260924", "n_rows": 1, "rows": [{"UNEXPECTED": 1}]}
    raw_path.write_text(json.dumps(bad_day, ensure_ascii=False) + "\n", encoding="utf-8")

    with pytest.raises(ValueError):
        mod.normalize_etf_jsonl(str(raw_path), str(out_path))


# ══════════════════════════════════ 보정(_adjust_one) — 주식·ETF 공용 ══════════════════════════════════


def test_adjust_one_flat_series_no_adjustment(mod):
    """전일대비가 항상 종가 변화와 일치하면(기준가==전일종가) 조정계수는 전부 1.0."""
    import pandas as pd

    g = pd.DataFrame(
        {
            "bas_dd": pd.to_datetime(["20260101", "20260102", "20260103"], format="%Y%m%d"),
            "open": [100.0, 101.0, 102.0],
            "high": [100.0, 101.0, 102.0],
            "low": [100.0, 101.0, 102.0],
            "close": [100.0, 101.0, 102.0],
            "prev_diff": [0.0, 1.0, 1.0],
        }
    )
    out = mod._adjust_one(g)
    assert out["adj_factor"].tolist() == pytest.approx([1.0, 1.0, 1.0])
    assert out["close_adj"].tolist() == pytest.approx([100.0, 101.0, 102.0])


def test_adjust_one_distribution_event_backward_adjusts_prior_prices(mod):
    """ETF 분배락(또는 주식 배당락) 흉내 — 기준가가 전일종가보다 낮게 찍힌 날, 그 이전 가격이

    같은 비율로 낮춰 조정돼야 한다(cycle362 의 배당락 처리와 동일 메커니즘, §_adjust_one
    docstring 「ETF 분배금 조정 규칙」).
    """
    import pandas as pd

    # day1 close=100 / day2 종가 99.5, CMPPREVDD_PRC(전일대비)=-1.0 →
    # 기준가(base_price)=99.5-(-1.0)=100.5?? 아니다 — 실제로는 "기준가가 전일종가보다 낮게
    # 찍혔다"는 시나리오를 만들기 위해 prev_diff 를 기준가가 95(= prev_close*0.95)가 되도록
    # 역산한다: base_price = close - prev_diff = 95 → prev_diff = close - 95.
    close_day2 = 96.0
    prev_diff_day2 = close_day2 - 95.0  # base_price=95, prev_close=100 → ratio=0.95
    g = pd.DataFrame(
        {
            "bas_dd": pd.to_datetime(["20260101", "20260102"], format="%Y%m%d"),
            "open": [100.0, 95.5],
            "high": [100.0, 96.5],
            "low": [100.0, 95.0],
            "close": [100.0, close_day2],
            "prev_diff": [0.0, prev_diff_day2],
        }
    )
    out = mod._adjust_one(g)
    # 최신일(day2) 조정계수는 1.0, 과거(day1)는 그 비율(0.95)만큼 낮아진다.
    assert out.loc[1, "adj_factor"] == pytest.approx(1.0)
    assert out.loc[0, "adj_factor"] == pytest.approx(0.95)
    assert out.loc[0, "close_adj"] == pytest.approx(100.0 * 0.95)


def test_adjust_one_outlier_ratio_guarded_to_one(mod):
    """비율이 [0.01, 100] 밖이면 1.0 으로 방어 — 극단값(자료 결손·오류 행)이 조용히

    전파되지 않는다."""
    import pandas as pd

    # base_price = close - prev_diff = 1.0 - 0.5 = 0.5, prev_close = 100.0
    # → ratio = 0.5/100 = 0.005 < 0.01 (범위 밖) → 1.0 으로 방어돼야 한다.
    g = pd.DataFrame(
        {
            "bas_dd": pd.to_datetime(["20260101", "20260102"], format="%Y%m%d"),
            "open": [100.0, 1.0],
            "high": [100.0, 1.0],
            "low": [100.0, 1.0],
            "close": [100.0, 1.0],
            "prev_diff": [0.0, 0.5],
        }
    )
    out = mod._adjust_one(g)
    assert out.loc[0, "adj_factor"] == pytest.approx(1.0)
    assert out.loc[1, "adj_factor"] == pytest.approx(1.0)
