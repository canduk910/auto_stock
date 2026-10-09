"""cycle416 Red — 시장 등락 통계 순수 leaf `src/engine/market_breadth.py` (L1~L13).

명세: `_workspace/red/cycle416/breadth_spec.md` §2 · §3 · §4 · §5.1 · §7.1 · §7.2
계약: `_workspace/red/cycle416/breadth_contract.md` 「1. leaf」

## 봉인하는 계약 (이름·형태가 다르면 FAIL)

`src/engine/market_breadth.py` — `await`·DB·HTTP·`asyncio`·`logging` 없는 순수 함수 모음.
  * 상수 `KRX_TICK_TABLE_20230125` · `PRICE_LIMIT_PCT=30` · `ADR_REFERENCE` · `DEFAULT_DAYS=20` ·
    `MIN_DAYS=1` · `MAX_DAYS=60` · `MIN_LOOKBACK_CALENDAR_DAYS=40` · `PUBLISH_PENDING_CUTOFF=time(10,0)`
  * `tick_size` · `price_limits` · `parse_krx_int` · `classify_row` · `aggregate_rows` · `merge_stats` ·
    `summarize` · `lookback_calendar_days` · `candidate_weekdays` · `next_weekday` ·
    `is_publish_pending` · `classify_day` · `DayStatus` · `stats_to_dict`

경계 픽스처 E1~E9 는 KRX 보관소 원자료 값(명세 §7.2)이고, 10-08 픽스처는 메인 세션 실측
숫자(코스피 942행 · 코스닥 1,823행)를 그대로 재현하는 합성 행이다(§7.1).

RED: 모듈 부재 → import 실패로 전 케이스 FAIL.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Any

import pytest

pytestmark = pytest.mark.unit

KST = timezone(timedelta(hours=9))

KRX_KEYS = (
    "BAS_DD", "ISU_CD", "ISU_NM", "MKT_NM", "SECT_TP_NM", "TDD_CLSPRC", "CMPPREVDD_PRC",
    "FLUC_RT", "TDD_OPNPRC", "TDD_HGPRC", "TDD_LWPRC", "ACC_TRDVOL", "ACC_TRDVAL", "MKTCAP",
    "LIST_SHRS",
)
DAY_KEYS = {
    "rows", "traded", "up", "down", "flat", "limit_up", "limit_down", "no_trade",
    "out_of_band", "unparsed", "up_ratio",
}
SUMMARY_KEYS = {"n_days", "up", "down", "flat", "limit_up", "limit_down", "no_trade", "up_ratio", "adr"}


def _mb():
    from src.engine import market_breadth

    return market_breadth


# ─────────────────────────────────────────────────────────────────────────────
# 행 만들기 — 실제 KRX 키 15개 전부, 값은 문자열(쉼표 선택)
# ─────────────────────────────────────────────────────────────────────────────

def _fmt(v: int | None, comma: bool) -> str:
    if v is None:
        return ""
    return f"{v:,}" if comma else str(v)


def _row(
    *,
    close: int | str | None,
    cmp: int | str | None,
    vol: int | str | None = 1_000,
    high: int | str | None = None,
    low: int | str | None = None,
    opn: int | str | None = None,
    fluc: str | None = None,
    comma: bool = False,
    mkt: str = "KOSPI",
    code: str = "000000",
) -> dict[str, str]:
    """`*_PRC`·`ACC_TRDVOL` 은 int 를 주면 문자열로(쉼표 선택), str 을 주면 그대로 싣는다."""

    def s(v: int | str | None) -> str:
        if isinstance(v, str):
            return v
        return _fmt(v, comma)

    c = close if isinstance(close, int) else None
    d = cmp if isinstance(cmp, int) else None
    if high is None:
        high = c if c is not None else ""
    if low is None:
        low = c if c is not None else ""
    if opn is None:
        opn = low
    if fluc is None:
        if c is not None and d is not None and (c - d) != 0:
            fluc = f"{Decimal(d) * 100 / Decimal(c - d):.2f}"
        else:
            fluc = "0.00"
    return {
        "BAS_DD": "20261008",
        "ISU_CD": code,
        "ISU_NM": f"종목{code}",
        "MKT_NM": mkt,
        "SECT_TP_NM": "",
        "TDD_CLSPRC": s(close),
        "CMPPREVDD_PRC": s(cmp),
        "FLUC_RT": fluc,
        "TDD_OPNPRC": s(opn),
        "TDD_HGPRC": s(high),
        "TDD_LWPRC": s(low),
        "ACC_TRDVOL": s(vol),
        "ACC_TRDVAL": "123,456,789" if comma else "123456789",
        "MKTCAP": "9,876,543,210" if comma else "9876543210",
        "LIST_SHRS": "1,000,000" if comma else "1000000",
    }


# 기준가 표 — 호가대가 다른 값들(일반 상승·하락 행에 돌려 쓴다)
_BASES = (980, 1_500, 3_200, 7_450, 15_800, 32_000, 88_500, 244_000, 610_000)


def _tick(p: int) -> int:
    for bound, t in ((2_000, 1), (5_000, 5), (20_000, 10), (50_000, 50), (200_000, 100), (500_000, 500)):
        if p < bound:
            return t
    return 1_000


def _up_row(i: int, mkt: str) -> dict[str, str]:
    base = _BASES[i % len(_BASES)]
    close = base + _tick(base)
    return _row(close=close, cmp=close - base, high=close, low=base, comma=(i % 2 == 0), mkt=mkt, code=f"U{i:05d}")


def _down_row(i: int, mkt: str) -> dict[str, str]:
    base = _BASES[i % len(_BASES)]
    close = base - _tick(base)
    return _row(close=close, cmp=close - base, high=base, low=close, comma=(i % 3 == 0), mkt=mkt, code=f"D{i:05d}")


def _flat_row(i: int, mkt: str) -> dict[str, str]:
    base = _BASES[i % len(_BASES)]
    return _row(close=base, cmp=0, high=base + _tick(base), low=base - _tick(base), comma=(i % 2 == 1), mkt=mkt, code=f"F{i:05d}")


def _no_trade_row(i: int, mkt: str) -> dict[str, str]:
    base = _BASES[i % len(_BASES)]
    return _row(close=base, cmp="0", vol="0", high="0", low="0", opn="0", fluc="0.00", comma=True, mkt=mkt, code=f"N{i:05d}")


# 상한가(정확히 upper, 고가=종가) — (기준가, 상한가). 등락률 ≥ 29.5 여야 한다.
_LIMIT_UP_PAIRS = (
    (1_500, 1_950),      # +30.00%
    (15_800, 20_500),    # +29.75% (20,540 아님 — 위쪽 호가대 절사)
    (9_180, 11_930),     # +29.96%
    (3_000, 3_900),      # +30.00%
    (48_000, 62_400),    # +30.00%
    (120_000, 156_000),  # +30.00%
)
# 하한가(정확히 lower, 저가=종가) — (기준가, 하한가). 등락률 ≤ -29.5.
_LIMIT_DOWN_PAIRS = ((244_000, 171_000),)  # -29.92% (170,800 아님)


def _limit_up_row(i: int, mkt: str) -> dict[str, str]:
    base, upper = _LIMIT_UP_PAIRS[i % len(_LIMIT_UP_PAIRS)]
    return _row(close=upper, cmp=upper - base, high=upper, low=base, comma=True, mkt=mkt, code=f"L{i:05d}")


def _limit_down_row(i: int, mkt: str) -> dict[str, str]:
    base, lower = _LIMIT_DOWN_PAIRS[i % len(_LIMIT_DOWN_PAIRS)]
    return _row(close=lower, cmp=lower - base, high=base, low=lower, comma=True, mkt=mkt, code=f"M{i:05d}")


def _market_rows(*, up: int, limit_up: int, down: int, limit_down: int, flat: int, no_trade: int, mkt: str) -> list[dict]:
    rows: list[dict] = []
    rows += [_limit_up_row(i, mkt) for i in range(limit_up)]
    rows += [_up_row(i, mkt) for i in range(up - limit_up)]
    rows += [_limit_down_row(i, mkt) for i in range(limit_down)]
    rows += [_down_row(i, mkt) for i in range(down - limit_down)]
    rows += [_flat_row(i, mkt) for i in range(flat)]
    rows += [_no_trade_row(i, mkt) for i in range(no_trade)]
    return rows


def kospi_1008() -> list[dict]:
    """2026-10-08 코스피 재현 — 942행(상승 252 그중 상한 3 · 하락 625 · 보합 50 · 거래 없음 15)."""
    return _market_rows(up=252, limit_up=3, down=625, limit_down=0, flat=50, no_trade=15, mkt="KOSPI")


def kosdaq_1008() -> list[dict]:
    """2026-10-08 코스닥 재현 — 1,823행(상승 618 그중 상한 13 · 하락 1,031 그중 하한 1 · 보합 99 · 거래 없음 75)."""
    return _market_rows(up=618, limit_up=13, down=1_031, limit_down=1, flat=99, no_trade=75, mkt="KOSDAQ")


def _stats(**kw: Any):
    """DayStats 를 aggregate_rows 로 만든다(생성자 시그니처에 묶이지 않게)."""
    rows = _market_rows(
        up=kw.get("up", 0), limit_up=kw.get("limit_up", 0), down=kw.get("down", 0),
        limit_down=kw.get("limit_down", 0), flat=kw.get("flat", 0), no_trade=kw.get("no_trade", 0),
        mkt="KOSPI",
    )
    return _mb().aggregate_rows(rows)


# ═════════════════════════════════════════════════════════════════════════════
# L1 — 상수
# ═════════════════════════════════════════════════════════════════════════════

def test_l1_constants():
    """L1 — 명세 §5.1 상수 값."""
    mb = _mb()
    assert mb.PRICE_LIMIT_PCT == 30
    assert mb.ADR_REFERENCE == {"oversold": 75, "overheated": 120}
    assert (mb.DEFAULT_DAYS, mb.MIN_DAYS, mb.MAX_DAYS) == (20, 1, 60)
    assert mb.MIN_LOOKBACK_CALENDAR_DAYS == 40
    assert mb.PUBLISH_PENDING_CUTOFF == time(10, 0)
    assert mb.KRX_TICK_TABLE_20230125, "호가가격단위표 상수 — 이름에 시행일(2023-01-25)을 박는다"


# ═════════════════════════════════════════════════════════════════════════════
# L2 — 호가단위 · 가격제한폭
# ═════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize(
    ("price", "tick"),
    [
        (1, 1), (1_999, 1), (2_000, 5), (4_999, 5), (5_000, 10), (19_999, 10), (20_000, 50),
        (49_999, 50), (50_000, 100), (199_999, 100), (200_000, 500), (499_999, 500),
        (500_000, 1_000), (3_000_000, 1_000),
    ],
)
def test_l2_tick_size_boundaries(price, tick):
    """L2 — 2023-01-25 호가가격단위(코스피·코스닥 공통) 경계값 (명세 §7.2)."""
    assert _mb().tick_size(price) == tick


@pytest.mark.parametrize(
    ("base", "upper", "lower"),
    [
        (82, 106, 58),             # E2 골든센츄리 — 1원 절사
        (1_500, 1_950, 1_050),
        (2_000, 2_600, 1_400),     # E9 엘에스스팩1호 기준가
        (9_180, 11_930, 6_430),    # E1 덕성 — 상한 11,930
        (15_800, 20_500, 11_060),  # E3 유유제약2우B — 상한 20,540 아니라 20,500(위 호가대 절사)
        (25_550, 33_200, 17_900),  # E8 엑스페릭스 — 하한 17,900
        (244_000, 317_000, 171_000),  # E4 삼천리 — 하한 171,000(170,800 아님 — 하한은 추가 절사 없음)
        (100_000, 130_000, 70_000),
    ],
)
def test_l2_price_limits(base, upper, lower):
    """L2 — 제한폭 w = 기준가 30% 를 기준가 호가단위로 절사 · 상한은 자기 가격대 호가로 한 번 더 절사 ·
    하한은 추가 절사 없음 (명세 §3.3 정의 (가′))."""
    assert _mb().price_limits(base) == (upper, lower)


# ═════════════════════════════════════════════════════════════════════════════
# L3 — 숫자 읽기
# ═════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, None), ("", None), ("-", None), ("   ", None), (" - ", None),
        ("1,234,500", 1_234_500), ("-1,500", -1_500), ("+1,200", 1_200), (" 42 ", 42),
        ("0", 0), ("12.5", None), ("abc", None),
    ],
)
def test_l3_parse_krx_int(raw, expected):
    """L3 — 쉼표·부호·공백 처리 · 정수가 아니면 None (명세 §3.1)."""
    assert _mb().parse_krx_int(raw) == expected


# ═════════════════════════════════════════════════════════════════════════════
# L4 — 행 분류: 실제 KRX 과거 사례 E1~E11 (명세 §7.2)
# ═════════════════════════════════════════════════════════════════════════════

def _cls(row: dict) -> tuple[str, bool, bool, bool]:
    rc = _mb().classify_row(row)
    return (rc.kind, rc.limit_up, rc.limit_down, rc.out_of_band)


def test_l4_e1_one_tick_below_limit_is_not_limit_up():
    """E1 덕성 2023-08-07 — 고가로 끝났지만 상한가(11,930) 1호가 아래. (나) 규칙의 오판 사례."""
    row = _row(close=11_900, cmp=2_720, high=11_900, low=9_180, comma=True)
    assert _cls(row) == ("up", False, False, False)


def test_l4_e2_penny_stock_true_limit_up_below_29_5_pct():
    """E2 골든센츄리 2023-12-27 — +29.27% 인데 진짜 상한가(1원 절사). 29.5% 문턱이 놓치는 사례."""
    row = _row(close=106, cmp=24, high=106, low=81)
    assert _cls(row) == ("up", True, False, False)


def test_l4_e3_upper_cut_by_upper_price_band_tick():
    """E3 유유제약2우B 2023-12-07 — 상한 = 20,500 (20,540 아님)."""
    row = _row(close=20_500, cmp=4_700, high=20_500, low=15_800, comma=True)
    assert _cls(row) == ("up", True, False, False)


def test_l4_e4_locked_limit_down_no_extra_cut():
    """E4 삼천리 2023-04-26 — 시고저종 171,000 잠긴 하한가 (170,800 아님)."""
    row = _row(close=171_000, cmp=-73_000, high=171_000, low=171_000, opn=171_000, comma=True)
    assert _cls(row) == ("down", False, True, False)


def test_l4_e5_listing_day_is_out_of_band_not_limit_up():
    """E5 DS단석 2023-12-22 신규상장 +300% — out_of_band, 상한가 아님."""
    row = _row(close=400_000, cmp=300_000, high=400_000, low=350_500, comma=True)
    assert _cls(row) == ("up", False, False, True)


def test_l4_e6_liquidation_trading_is_out_of_band_not_limit_down():
    """E6 에코바이브 2023-10-27 정리매매 −97.7% — out_of_band, 하한가 아님."""
    row = _row(close=150, cmp=-6_260, high=300, low=150, comma=True)
    assert _cls(row) == ("down", False, False, True)


def test_l4_e7_zero_volume_with_base_change_is_no_trade_not_down():
    """E7 하이트진로홀딩스우 2023-09-08 — 거래량 0 · 대비 −10(기준가만 바뀐 날) → no_trade (하락 아님)."""
    row = _row(close=12_240, cmp=-10, vol="0", high="0", low="0", opn="0", fluc="-0.08", comma=True)
    assert _cls(row) == ("no_trade", False, False, False)


def test_l4_e8_one_tick_above_limit_down_is_not_limit_down():
    """E8 엑스페릭스 2023-06-28 — 종가 17,910, 하한 17,900."""
    row = _row(close=17_910, cmp=-7_640, high=26_400, low=17_910, comma=True)
    assert _cls(row) == ("down", False, False, False)


def test_l4_e9_spac_listing_day_close_equals_calc_upper_but_out_of_band():
    """E9 엘에스스팩1호 2025-07-22 상장일 — 종가가 계산 상한(2,600)과 같지만 고가 5,040 이 밴드 밖 → 상한가 아님."""
    row = _row(close=2_600, cmp=600, high=5_040, low=2_545, comma=True)
    assert _cls(row) == ("up", False, False, True)


def test_l4_e10_commas_and_negative_sign_parse():
    """E10 쉼표·부호 — `"1,234,500"` · `"-1,500"` → down, 파싱 성공."""
    row = _row(close="1,234,500", cmp="-1,500", vol="12,345", high="1,240,000", low="1,230,000", fluc="-0.12")
    assert _cls(row) == ("down", False, False, False)


@pytest.mark.parametrize(
    "overrides",
    [
        {"TDD_CLSPRC": ""},
        {"TDD_CLSPRC": "-"},
        {"TDD_CLSPRC": "0"},
        {"TDD_CLSPRC": "-100"},
        {"CMPPREVDD_PRC": None},
        {"CMPPREVDD_PRC": ""},
        {"ACC_TRDVOL": ""},
        {"ACC_TRDVOL": None},
        {"ACC_TRDVOL": "-1"},
    ],
)
def test_l4_e11_unparsed(overrides):
    """E11 판독 불가 — 종가 None/≤0 · 대비 None · 거래량 None/<0 → unparsed (상·하한·밴드 플래그 전부 False)."""
    row = _row(close=10_000, cmp=100, high=10_100, low=9_900)
    row.update(overrides)
    assert _cls(row) == ("unparsed", False, False, False)


def test_l4_zero_volume_checked_before_direction_even_at_limit_price():
    """분류 순서 — 거래량 0 이 방향(대비 부호)보다 먼저 (명세 §3.2 순서 2)."""
    row = _row(close=1_950, cmp=450, vol="0", high="0", low="0", opn="0", fluc="30.00")
    assert _cls(row) == ("no_trade", False, False, False)


def test_l4_flat_traded_row():
    row = _row(close=10_000, cmp="0", high=10_050, low=9_950, fluc="0.00")
    assert _cls(row) == ("flat", False, False, False)


def test_l4_flat_out_of_band_counts_as_out_of_band():
    """out_of_band 는 up·down·flat 모두에 걸린다 (명세 §3.3) — 신규상장일 보합 마감."""
    row = _row(close=2_000, cmp="0", high=5_000, low=1_500, fluc="0.00")
    assert _cls(row) == ("flat", False, False, True)


@pytest.mark.parametrize(("high", "low"), [("0", "0"), ("", ""), ("0", "9,900"), ("10,100", "")])
def test_l4_traded_row_without_high_low_skips_limit_judgement(high, low):
    """거래가 있는데 고가·저가가 0(또는 빈 값)이면 상·하한·밴드 판정을 건너뛰고 방향만 센다 (명세 §3.3)."""
    row = _row(close=1_950, cmp=450, high=high, low=low, fluc="30.00")
    assert _cls(row) == ("up", False, False, False)


def test_l4_sign_mismatch_flag_does_not_change_direction():
    """§3.4 — `FLUC_RT` 부호가 대비와 어긋나면 sign_mismatch=True, 분류는 대비 기준 그대로."""
    mb = _mb()
    rc = mb.classify_row(_row(close=10_100, cmp=100, high=10_100, low=10_000, fluc="-1.00"))
    assert rc.kind == "up" and rc.sign_mismatch is True
    ok = mb.classify_row(_row(close=10_100, cmp=100, high=10_100, low=10_000, fluc="1.00"))
    assert ok.sign_mismatch is False
    unreadable = mb.classify_row(_row(close=10_100, cmp=100, high=10_100, low=10_000, fluc=""))
    assert unreadable.sign_mismatch is False, "FLUC_RT 가 안 읽히면 교차확인 대상 아님"


# ═════════════════════════════════════════════════════════════════════════════
# L5 — 10-08 재현 픽스처 (명세 §7.1)
# ═════════════════════════════════════════════════════════════════════════════

EXPECTED_1008 = {
    "kospi": dict(rows=942, traded=927, up=252, down=625, flat=50, limit_up=3, limit_down=0,
                  no_trade=15, out_of_band=0, unparsed=0, up_ratio=0.2718),
    "kosdaq": dict(rows=1_823, traded=1_748, up=618, down=1_031, flat=99, limit_up=13, limit_down=1,
                   no_trade=75, out_of_band=0, unparsed=0, up_ratio=0.3535),
    "total": dict(rows=2_765, traded=2_675, up=870, down=1_656, flat=149, limit_up=16, limit_down=1,
                  no_trade=90, out_of_band=0, unparsed=0, up_ratio=0.3252),
}
EXPECTED_ADR_1008 = {"kospi": 40.3, "kosdaq": 59.9, "total": 52.5}


def _fluc_counts(rows: list[dict]) -> tuple[int, int, int, int, int]:
    """메인 세션 실측과 같은 잣대 — FLUC_RT 부호 · ±29.5 문턱."""
    f = [Decimal(r["FLUC_RT"]) for r in rows]
    return (
        sum(1 for x in f if x > 0), sum(1 for x in f if x < 0), sum(1 for x in f if x == 0),
        sum(1 for x in f if x >= Decimal("29.5")), sum(1 for x in f if x <= Decimal("-29.5")),
    )


def test_l5_fixture_matches_main_session_raw_measurement():
    """교차 단언 — 픽스처를 FLUC_RT 로 센 값 = 메인 세션 10-08 실측(252/625/65/3 · 618/1,031/174/13/1)."""
    kp, kq = kospi_1008(), kosdaq_1008()
    assert len(kp) == 942 and len(kq) == 1_823
    assert _fluc_counts(kp) == (252, 625, 65, 3, 0)
    assert _fluc_counts(kq) == (618, 1_031, 174, 13, 1)
    for r in kp[:3] + kq[-3:]:
        assert set(r) == set(KRX_KEYS), "실제 KRX 키 15개"
        assert all(isinstance(v, str) for v in r.values()), "KRX 값은 문자열"
    assert any("," in r["TDD_CLSPRC"] for r in kp), "쉼표 숫자가 섞여 있어야 파싱 경로를 탄다"


@pytest.mark.parametrize("market", ["kospi", "kosdaq"])
def test_l5_aggregate_rows_reproduces_1008(market):
    """L5 — aggregate_rows 가 10-08 숫자를 그대로 낸다 (명세 §7.1 기대값 표)."""
    rows = kospi_1008() if market == "kospi" else kosdaq_1008()
    s = _mb().aggregate_rows(rows)
    for k, v in EXPECTED_1008[market].items():
        assert getattr(s, k) == v, f"{market}.{k}={getattr(s, k)!r} (기대 {v!r})"
    assert s.sign_mismatch == 0


def test_l5_merge_stats_total_and_daily_adr():
    """L5 — 합계 = 정수 키 합 · up_ratio 는 합계 숫자로 재계산 · 하루 ADR 40.3 / 59.9 / 52.5."""
    mb = _mb()
    kp = mb.aggregate_rows(kospi_1008())
    kq = mb.aggregate_rows(kosdaq_1008())
    tot = mb.merge_stats(kp, kq)
    for k, v in EXPECTED_1008["total"].items():
        assert getattr(tot, k) == v, f"total.{k}={getattr(tot, k)!r} (기대 {v!r})"
    for name, s in (("kospi", kp), ("kosdaq", kq), ("total", tot)):
        summ = mb.summarize([s])
        assert summ.adr == EXPECTED_ADR_1008[name], f"{name} 하루 ADR"
        assert summ.n_days == 1


# ═════════════════════════════════════════════════════════════════════════════
# L6 — 집계 세부 (명세 §4)
# ═════════════════════════════════════════════════════════════════════════════

def test_l6_unparsed_rows_excluded_from_rows_but_counted():
    mb = _mb()
    rows = [
        _row(close=10_100, cmp=100, high=10_100, low=10_000),
        _row(close="", cmp=100),
        _row(close=10_000, cmp=None),
    ]
    s = mb.aggregate_rows(rows)
    assert (s.rows, s.traded, s.up, s.unparsed) == (1, 1, 1, 2)


def test_l6_up_ratio_none_when_no_traded_rows():
    mb = _mb()
    s = mb.aggregate_rows([_no_trade_row(0, "KOSPI"), _no_trade_row(1, "KOSPI")])
    assert (s.rows, s.traded, s.no_trade) == (2, 0, 2)
    assert s.up_ratio is None
    empty = mb.aggregate_rows([])
    assert (empty.rows, empty.traded, empty.unparsed) == (0, 0, 0)
    assert empty.up_ratio is None


def test_l6_merge_recomputes_ratio_not_average():
    """합계 up_ratio 는 두 비율의 평균이 아니다: (1/1, 1/3) → 2/4 = 0.5 (평균이면 0.6667)."""
    mb = _mb()
    a = _stats(up=1)
    b = _stats(up=1, down=2)
    assert a.up_ratio == 1.0
    assert b.up_ratio == 0.3333
    assert mb.merge_stats(a, b).up_ratio == 0.5


def test_l6_summarize_sums_and_adr():
    mb = _mb()
    days = [_stats(up=2, down=1, flat=1, no_trade=1, limit_up=1), _stats(up=1, down=2, limit_down=1)]
    s = mb.summarize(days)
    assert (s.n_days, s.up, s.down, s.flat, s.limit_up, s.limit_down, s.no_trade) == (2, 3, 3, 1, 1, 1, 1)
    assert s.up_ratio == round(3 / 7, 4)
    assert s.adr == 100.0


def test_l6_summarize_adr_none_when_no_down_and_empty_input():
    mb = _mb()
    s = mb.summarize([_stats(up=3, flat=1)])
    assert s.adr is None, "Σ하락 0 → ADR null (0 나눗셈 금지)"
    assert s.up_ratio == 0.75
    z = mb.summarize([])
    assert z.n_days == 0 and z.adr is None and z.up_ratio is None


def test_l6_stats_to_dict_keys_exclude_sign_mismatch():
    """응답 직렬화 — DayStats 11키(sign_mismatch 제외) · SummaryStats 9키 (명세 §5.4)."""
    mb = _mb()
    d = mb.stats_to_dict(mb.aggregate_rows(kospi_1008()))
    assert set(d) == DAY_KEYS
    assert d["up"] == 252 and d["up_ratio"] == 0.2718
    sd = mb.stats_to_dict(mb.summarize([mb.aggregate_rows(kospi_1008())]))
    assert set(sd) == SUMMARY_KEYS
    assert sd["adr"] == 40.3


# ═════════════════════════════════════════════════════════════════════════════
# L7 — 날짜 창 (명세 §2.1)
# ═════════════════════════════════════════════════════════════════════════════

@pytest.mark.parametrize(("days", "lookback"), [(1, 40), (20, 40), (21, 42), (60, 120)])
def test_l7_lookback_calendar_days(days, lookback):
    assert _mb().lookback_calendar_days(days) == lookback


def test_l7_candidate_weekdays_excludes_today_and_weekends_newest_first():
    """오늘(금 10-09) 제외 · 어제부터 평일만 · 최신 먼저 · 한도 today−40(=08-30, 일) 포함."""
    mb = _mb()
    today = date(2026, 10, 9)
    c = mb.candidate_weekdays(today, 20)
    assert c[0] == date(2026, 10, 8)
    assert today not in c
    assert all(d.weekday() < 5 for d in c)
    assert c == sorted(c, reverse=True)
    assert len(set(c)) == len(c)
    assert min(c) >= today - timedelta(days=40)
    expected = [today - timedelta(days=k) for k in range(1, 41)]
    assert c == [d for d in expected if d.weekday() < 5]


def test_l7_candidate_weekdays_lookback_boundary_inclusive():
    """월 10-12 − 40일 = 09-02(수) — 한도일 자체가 후보에 든다(포함)."""
    mb = _mb()
    c = mb.candidate_weekdays(date(2026, 10, 12), 20)
    assert c[0] == date(2026, 10, 9), "월요일이면 직전 금요일부터"
    assert c[-1] == date(2026, 9, 2)
    c60 = mb.candidate_weekdays(date(2026, 10, 9), 60)
    assert c60[-1] >= date(2026, 6, 11) and min(c60) == date(2026, 6, 11), "60일 → 한도 120일(06-11 목)"


@pytest.mark.parametrize(
    ("d", "nw"),
    [
        (date(2026, 10, 8), date(2026, 10, 9)),   # 목 → 금
        (date(2026, 10, 9), date(2026, 10, 12)),  # 금 → 월
        (date(2026, 10, 10), date(2026, 10, 12)),  # 토 → 월
        (date(2026, 10, 11), date(2026, 10, 12)),  # 일 → 월
    ],
)
def test_l7_next_weekday(d, nw):
    assert _mb().next_weekday(d) == nw


@pytest.mark.parametrize(
    ("d", "d1", "now", "pending"),
    [
        # W2/W3 — 수 10-07 미게시 판정: 목 10-08 10:00 전이면 pending
        (date(2026, 10, 7), date(2026, 10, 7), datetime(2026, 10, 8, 9, 30, tzinfo=KST), True),
        (date(2026, 10, 7), date(2026, 10, 7), datetime(2026, 10, 8, 9, 59, 59, tzinfo=KST), True),
        (date(2026, 10, 7), date(2026, 10, 7), datetime(2026, 10, 8, 10, 0, tzinfo=KST), False),
        (date(2026, 10, 7), date(2026, 10, 7), datetime(2026, 10, 8, 10, 30, tzinfo=KST), False),
        # W4 — 금 10-09 는 다음 평일 월 10-12 10:00 전까지 pending(주말 내내)
        (date(2026, 10, 9), date(2026, 10, 9), datetime(2026, 10, 11, 15, 0, tzinfo=KST), True),
        (date(2026, 10, 9), date(2026, 10, 9), datetime(2026, 10, 12, 9, 59, tzinfo=KST), True),
        (date(2026, 10, 9), date(2026, 10, 9), datetime(2026, 10, 12, 10, 0, tzinfo=KST), False),
        # d1 이 아닌 날은 언제나 pending 아님
        (date(2026, 10, 6), date(2026, 10, 7), datetime(2026, 10, 8, 9, 30, tzinfo=KST), False),
    ],
)
def test_l7_is_publish_pending(d, d1, now, pending):
    """§2.2 — pending ⇔ d == d1 ∧ now < 다음 평일 10:00 KST."""
    assert _mb().is_publish_pending(d, d1, now) is pending


def test_l7_is_publish_pending_uses_kst_for_utc_input():
    """now 가 UTC 로 와도 KST 로 판정 — 2026-10-08 00:59Z = 09:59 KST(pending) · 01:00Z = 10:00 KST(아님)."""
    mb = _mb()
    d = date(2026, 10, 7)
    assert mb.is_publish_pending(d, d, datetime(2026, 10, 8, 0, 59, tzinfo=timezone.utc)) is True
    assert mb.is_publish_pending(d, d, datetime(2026, 10, 8, 1, 0, tzinfo=timezone.utc)) is False


# ═════════════════════════════════════════════════════════════════════════════
# L8 — 날짜 판정 (명세 §2.1 표)
# ═════════════════════════════════════════════════════════════════════════════

def test_l8_classify_day():
    """TRADING = 두 시장 유효 행 ≥1 · EMPTY = 둘 다 0 · MISSING = 한쪽 실패(None) 또는 한쪽만 빔."""
    mb = _mb()
    ok = _stats(up=1)
    empty = mb.aggregate_rows([])
    all_unparsed = mb.aggregate_rows([_row(close="", cmp=1), _row(close="-", cmp=1)])
    assert all_unparsed.rows == 0 and all_unparsed.unparsed == 2
    DS = mb.DayStatus
    assert mb.classify_day(ok, ok) == DS.TRADING
    assert mb.classify_day(empty, empty) == DS.EMPTY
    assert mb.classify_day(all_unparsed, empty) == DS.EMPTY, "행은 있으나 전부 판독 불가 = EMPTY"
    assert mb.classify_day(empty, ok) == DS.MISSING, "한 시장만 빈 날 = 부분 → MISSING"
    assert mb.classify_day(ok, empty) == DS.MISSING
    assert mb.classify_day(None, ok) == DS.MISSING, "호출 실패 = None"
    assert mb.classify_day(ok, None) == DS.MISSING
    assert mb.classify_day(None, empty) == DS.MISSING, "실패가 빈 응답보다 우선"
    assert mb.classify_day(None, None) == DS.MISSING
    assert {DS.TRADING.value, DS.EMPTY.value, DS.MISSING.value} == {"TRADING", "EMPTY", "MISSING"}
