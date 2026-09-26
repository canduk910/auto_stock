"""cycle369 Red — A. 종목상태 분류 `status_exit_watch.classify` (순수 · never-raise).

명세 §2 · 자문 §2.3 실측 응답 7건이 픽스처다(`_cycle369_support.LIVE`).

판정 규칙(명세 §2 — 자문 대비 변경: `iscd` 는 전용 플래그가 **비었을 때만** 쓴다):

    정규화     : str 이면 .strip().upper(); "Y"/"N" 만 유효. 그 밖은 None + unknown_values
    managed    : mang == "Y"       or (mang is None       and iscd == "51")
    overheat   : short_over == "Y" or (short_over is None and iscd == "59")
    halted     : iscd == "58" or temp_stop_yn == "Y"
    flags_missing : (mang is None and iscd != "51") or (short_over is None and iscd != "59")
    price_ok   : stck_prpr 가 양의 정수 문자열
    fetch_fail : 응답이 dict 가 아님 · 비어 있음
    iscd_conflict : (mang == "N" and iscd == "51") or (short_over == "N" and iscd == "59")

쓰지 않는 것 = `ssts_hot_yn`(공매도과열) · master `short_over_cls_code`(1=예고) · DB 값.
"""
from __future__ import annotations

import copy

import pytest

from tests.unit.engine._cycle369_support import LIVE, fhkst, leaf

pytestmark = [pytest.mark.unit, pytest.mark.real_status_watch]


def _c(output):
    return leaf().classify(output)


def test_a1_294140_managed_iscd_51_flag_y():
    r = _c(LIVE["294140"])
    assert r.managed is True
    assert r.overheat is False
    assert r.halted is False
    assert r.fetch_fail is False
    assert r.price_ok is True
    assert r.reason == "managed"


def test_a2_016790_managed_and_halted_iscd_58():
    """iscd 58 이 관리를 가린다 — 전용 플래그 `mang_issu_cls_code` 가 없으면 못 잡는다(K3)."""
    r = _c(LIVE["016790"])
    assert r.managed is True, "iscd 58(정지)에 가려진 관리종목 — 전용 플래그가 판정 소스여야 한다"
    assert r.halted is True
    assert r.overheat is False


@pytest.mark.parametrize("ticker", ["005160", "000545"])
def test_a3_overheat_designated_and_extended(ticker):
    r = _c(LIVE[ticker])
    assert r.overheat is True
    assert r.managed is False
    assert r.halted is False
    assert r.reason == "overheat"


def test_a4_356680_overheat_notice_is_not_overheat():
    """예고(`short_over_yn=N`, iscd 57)는 지정이 아니다(K2 — 09-23 기준 예고 21 > 지정 10)."""
    r = _c(LIVE["356680"])
    assert r.overheat is False
    assert r.managed is False
    assert r.reason in ("", None)


def test_a5_043090_flags_none_price_zero_is_unknown_not_clean():
    """칸이 None 으로 오는 관리종목 — 「모름」이지 「해당 없음」이 아니다(K6)."""
    r = _c(LIVE["043090"])
    assert r.managed is False
    assert r.flags_missing is True, "mang None ∧ iscd 00 → 전용 플래그 결측"
    assert r.price_ok is False, "현재가 0"
    assert r.fetch_fail is False


def test_a6_short_sale_overheat_only_is_not_flagged():
    """`ssts_hot_yn`(공매도과열)은 단기과열이 아니다(K1 — 보유 중 035760 CJ ENM 도 이 표본)."""
    out = fhkst("035760", iscd="55", mang="N", short_over="N", ssts_hot_yn="Y")
    r = _c(out)
    assert r.managed is False
    assert r.overheat is False


@pytest.mark.parametrize("iscd", ["52", "53", "54", "55", "57", "00"])
def test_a7_other_status_codes_are_not_flagged(iscd):
    r = _c(fhkst("123450", iscd=iscd, mang="N", short_over="N"))
    assert (r.managed, r.overheat, r.halted) == (False, False, False)


@pytest.mark.parametrize("raw", ["y", " Y ", "Y\n"])
def test_a8_flag_normalization(raw):
    r = _c(fhkst("123450", iscd="55", mang=raw, short_over="N"))
    assert r.managed is True
    assert r.mang == "Y"


def test_a9_out_of_vocabulary_value_is_none_and_reported():
    r = _c(fhkst("123450", iscd="55", mang="1", short_over="N"))
    assert r.managed is False, "규칙 밖 값은 해당으로 읽지 않는다"
    assert r.mang is None
    assert "1" in list(r.unknown_values)
    assert r.flags_missing is True


def test_a10_managed_and_overheat_reason_is_composed():
    r = _c(fhkst("123450", iscd="59", mang="Y", short_over="Y"))
    assert r.managed is True and r.overheat is True
    assert r.reason == "managed+overheat"


def test_a11_iscd_51_fallback_when_mang_flag_missing():
    out = fhkst("123450", iscd="51", mang=None, short_over="N")
    out.pop("mang_issu_cls_code")
    r = _c(out)
    assert r.managed is True, "전용 플래그가 비었을 때만 iscd 51 폴백"


def test_a12_explicit_n_wins_over_iscd_51():
    """명시 `N` 을 iscd 가 뒤집지 못한다(K3' — cycle203 실측 「51=정상 ETF/스팩/우선주」)."""
    r = _c(fhkst("123450", iscd="51", mang="N", short_over="N"))
    assert r.managed is False
    assert r.iscd_conflict is True


def test_a12b_explicit_n_wins_over_iscd_59():
    r = _c(fhkst("123450", iscd="59", mang="N", short_over="N"))
    assert r.overheat is False
    assert r.iscd_conflict is True


def test_a13_iscd_59_fallback_when_short_over_missing():
    r = _c(fhkst("123450", iscd="59", mang="N", short_over=None))
    assert r.overheat is True


@pytest.mark.parametrize("bad", [None, "not-a-dict", [], {}, 0])
def test_a14_non_dict_or_empty_is_fetch_fail(bad):
    r = _c(bad)
    assert r.fetch_fail is True
    assert r.managed is False and r.overheat is False


def test_a15_temp_stop_is_halted():
    r = _c(fhkst("123450", iscd="55", mang="Y", short_over="N", temp_stop="Y"))
    assert r.managed is True
    assert r.halted is True


@pytest.mark.parametrize("prpr", ["0", "", None, "abc", "-5"])
def test_a16_price_ok_requires_positive_integer(prpr):
    r = _c(fhkst("123450", iscd="51", mang="Y", short_over="N", prpr=prpr))
    assert r.price_ok is False


def test_a17_classify_is_pure_and_never_raises():
    out = LIVE["294140"]
    before = copy.deepcopy(out)
    _c(out)
    assert out == before, "classify 가 입력을 바꿨다"
    weird = {"mang_issu_cls_code": object(), "short_over_yn": b"Y", "stck_prpr": 3.5}
    r = _c(weird)  # 예외 없이 결과를 낸다
    assert r.managed is False, "str 이 아닌 플래그 값은 해당으로 읽지 않는다"
    assert r.overheat is False
