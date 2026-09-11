"""cycle282 Red — 장운영상태 leaf `src/engine/market_state.py` (A·B·C·D·E·F).

정본 = 브리프 `scratchpad/cycle282_brief.md` §1 표 + 명세
`_workspace/red/cycle282_market_state_spec.md` §1 · §6 · §7.1.

## 이 파일의 성격

**Red 다.** 작성 시점에 `src/engine/market_state.py` 는 존재하지 않는다. 모듈 import 는
전부 **지연**(`_ms()`)이라 수집(collection)은 성공하고, 각 테스트는 "미구현" 메시지와 함께
FAIL 한다 — 수집 오류 0 · RED N 이 이 파일의 초기 상태다.

## 왜 표를 테스트 안에 다시 적는가

`_ROWS` / `_DIVISIONS` 는 **브리프 1절 표의 사본**이다. 구현 모듈에서 읽어 와 비교하면
"자기 자신과 같다" 는 공허한 검사가 된다(행을 지우면 기대값도 같이 지워진다). 표가 바뀌는
날에는 *이 파일과 구현 둘 다* 고쳐야 하고, 그 이중 편집이 곧 표 변경의 승인 절차다.
뮤테이션 m1(K2 삭제)·m4(K3 start 1초 이동)가 여기서 죽는다.

## Green 에게 거는 구조 제약 하나

`B8`·`B9` 는 `monkeypatch.setattr(market_state, "MARKET_TABLE", ...)` 로 합성 행을 넣어
우선순위 규칙을 검증한다. 따라서 `get_market_state` / `get_market_table` 은 **호출 시점에
모듈 전역 `MARKET_TABLE` 을 읽어야** 한다(import 시점에 파생 인덱스를 굳혀 두면 그 둘이
붉어진다). 데이터가 바뀔 때 파생이 따라오지 않는 구조를 애초에 막는다는 뜻도 된다.

## 반개구간 `[start, end)` 가 이 사이클의 중심 계약

09:00:00 은 K1(시가 단일가)이 아니라 K3(정규장)다. 끝을 포함하면 두 행이 같은 순간에
살아 있게 되어 커서가 `ambiguous` 가 되고, 화면은 "단일가인데 시장가 주문 가능" 이라는
모순을 띄운다. `test_c_grid_half_open_membership` 52 케이스가 13행 전부의 네 모서리를 잰다.

## ⚠️ 명세와 다르게 고정한 것 — NXT 09:00:00~09:00:29 (C-f)

명세 §7.1 `C-f` 는 이 30초를 `N2`(BREAK)로 기대하지만, **정본 표의 N2 는 08:50~09:00** 이고
구간은 반개구간이다. 그러므로 09:00:00 에 N2 는 이미 살아 있지 않다 — 그 30초는 **어느 행에도
속하지 않는 공백**이고 명세 §1.8 알고리즘대로면 `row_id=None · phase=CLOSED` 다.
표를 데이터로 넓혀(N2.end 를 09:00:30 으로) 메우는 것은 정정-2("09-13 공백을 데이터로 메우지
않는다")가 금지한 바로 그 행위다. 그래서 이 파일은 **데이터에 충실한 쪽**을 고정하고,
어느 해석에서도 참인 안전 성질(`is_open is False` · `can_order is False`)을 함께 잠근다.
→ 결과의 `spec_disagreements` 에 보고.
"""

from __future__ import annotations

import dataclasses
import importlib
import os
import time as _time_mod
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from functools import lru_cache

import pytest
from freezegun import freeze_time

pytestmark = pytest.mark.unit

_KST = timezone(timedelta(hours=9))
_UTC = timezone.utc


# ---------------------------------------------------------------------------
# 지연 import — 미구현 단계에서 **수집 오류 대신 FAIL** 이 되게 한다.
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def _import_market_state():
    try:
        return importlib.import_module("src.engine.market_state"), None
    except Exception as exc:  # noqa: BLE001 — Red 단계 메시지로 환원
        return None, exc


def _ms():
    mod, exc = _import_market_state()
    if mod is None:
        pytest.fail(
            "src/engine/market_state.py 미구현 (Red) — "
            f"{type(exc).__name__}: {exc}"
        )
    return mod


def _attr(name: str):
    mod = _ms()
    if not hasattr(mod, name):
        pytest.fail(f"market_state.{name} 미구현 (Red) — 명세 §1.1~§1.10")
    return getattr(mod, name)


def _state(now, market: str):
    return _attr("get_market_state")(now, market=market)


def _table(on_date=None):
    return _attr("get_market_table")(on_date)


def _at(d: date, t: time) -> datetime:
    return datetime.combine(d, t, tzinfo=_KST)


def _live_ids(state) -> set:
    """커서 + 동시 유효 행 = 그 순간 '살아 있는' 행 집합."""
    ids = set(state.concurrent_row_ids or ())
    if state.row_id is not None:
        ids.add(state.row_id)
    return ids


def _phase_name(value) -> str:
    """`MarketPhase` enum / str 어느 쪽이 와도 이름 문자열로."""
    return getattr(value, "value", value)


# ---------------------------------------------------------------------------
# 정본 표 사본 — 브리프 §1 (명세 §1.3)
# ---------------------------------------------------------------------------
_KRX_REGULAR = (
    "00", "01", "02", "03", "04",
    "11", "12", "13", "14", "15", "16",
    "21", "22", "23", "24",
)
_NXT_CONT = (
    "00", "03", "04",
    "11", "12", "13", "14", "15", "16",
    "21", "22", "23", "24",
)
_NXT_PRE = _NXT_CONT + ("27", "28", "29")
_KRX_AFTER = ("41", "42", "43", "44", "45", "46", "47")

_D_0911 = date(2026, 9, 11)   # 금 — K7 유효 · K6 미유효 · 27~29 pending
_D_0912 = date(2026, 9, 12)   # 토 — K7 마지막 유효일
_D_0913 = date(2026, 9, 13)   # 일 — K6·K7 둘 다 없음(정정-2)
_D_0914 = date(2026, 9, 14)   # 월 — 전환일. K6 등장 · 27~29·41~47 유효
_D_0915 = date(2026, 9, 15)   # 화 — 09-14 와 동일


@dataclass(frozen=True)
class Row:
    row_id: str
    market: str
    start: time
    end: time
    phase: str
    name_ko: str
    match_kind: str
    match_ko: str
    divisions: tuple          # 선언(날짜 해석 **전**) 상위집합
    priority: int
    overlap_ok: bool
    effective_from: "date | None"
    effective_to: "date | None"
    confidence: str
    grid_date: date           # 경계 격자를 재는 날짜(그 행이 유효한 날)


_ROWS: tuple = (
    Row("K1", "KRX", time(8, 20), time(9, 0), "PRE_AUCTION", "시가 단일가",
        "single_auction", "단일가(09:00 일괄)", ("00", "01"), 10, False,
        None, None, "unconfirmed", _D_0911),
    Row("K2", "KRX", time(8, 30), time(8, 40), "PRE_CLOSE_FIXED", "장전 시간외 종가",
        "fixed_price", "전일 종가 고정", ("05",), 20, True,
        None, None, "confirmed", _D_0911),
    Row("K3", "KRX", time(9, 0), time(15, 20), "REGULAR", "정규장",
        "continuous", "실시간 접속매매", _KRX_REGULAR, 10, False,
        None, None, "confirmed", _D_0911),
    Row("K4", "KRX", time(15, 20), time(15, 30), "CLOSE_AUCTION", "종가 단일가",
        "single_auction", "단일가(15:30 일괄)", ("00", "01"), 10, False,
        None, None, "confirmed", _D_0911),
    Row("K5", "KRX", time(15, 30), time(16, 0), "AFTER_CLOSE_FIXED", "장후 시간외 종가",
        "fixed_price", "당일 종가 고정", ("06",), 10, False,
        None, None, "confirmed", _D_0911),
    Row("K6", "KRX", time(16, 0), time(20, 0), "AFTER_MARKET", "애프터마켓",
        "continuous", "실시간", _KRX_AFTER, 10, False,
        _D_0914, None, "confirmed", _D_0914),
    Row("K7", "KRX", time(16, 0), time(18, 0), "AFTER_SINGLE", "시간외 단일가",
        "periodic_auction", "10분 주기", ("07",), 10, True,
        None, _D_0912, "confirmed", _D_0911),
    Row("N1", "NXT", time(8, 0), time(8, 50), "PRE_MARKET", "프리마켓",
        "continuous", "실시간", _NXT_PRE, 10, False,
        None, None, "confirmed", _D_0911),
    Row("N2", "NXT", time(8, 50), time(9, 0), "BREAK", "휴장",
        "none", "—", (), 10, False,
        None, None, "confirmed", _D_0911),
    Row("N3", "NXT", time(9, 0, 30), time(15, 20), "REGULAR", "정규장",
        "continuous", "실시간", _NXT_CONT, 10, False,
        None, None, "unconfirmed", _D_0911),
    Row("N4", "NXT", time(15, 20), time(15, 30), "BREAK", "휴장",
        "none", "—", (), 10, False,
        None, None, "confirmed", _D_0911),
    Row("N5", "NXT", time(15, 30), time(15, 40), "AFTER_SINGLE", "애프터 단일가",
        "single_auction", "단일가", (), 10, False,
        None, None, "unconfirmed", _D_0911),
    Row("N6", "NXT", time(15, 40), time(20, 0), "AFTER_MARKET", "애프터마켓",
        "continuous", "실시간", _NXT_CONT, 10, False,
        None, None, "confirmed", _D_0911),
)

_ROW_BY_ID = {r.row_id: r for r in _ROWS}

#: 주문유형 카탈로그 사본 — (code, exchanges, exchanges_unknown, eff_from, eff_to, confidence)
_DIVISIONS: tuple = (
    ("00", ("KRX", "NXT", "SOR"), (), None, None, "confirmed"),
    ("01", ("KRX", "SOR"), (), None, None, "confirmed"),
    ("02", ("KRX",), (), None, None, "confirmed"),
    ("03", ("KRX", "NXT", "SOR"), (), None, None, "confirmed"),
    ("04", ("KRX", "NXT", "SOR"), (), None, None, "confirmed"),
    ("05", ("KRX",), (), None, None, "confirmed"),
    ("06", ("KRX",), (), None, None, "confirmed"),
    ("07", ("KRX",), (), None, _D_0912, "confirmed"),
    ("11", ("KRX", "NXT", "SOR"), (), None, None, "confirmed"),
    ("12", ("KRX", "NXT", "SOR"), (), None, None, "confirmed"),
    ("13", ("KRX", "NXT", "SOR"), (), None, None, "confirmed"),
    ("14", ("KRX", "NXT", "SOR"), (), None, None, "confirmed"),
    ("15", ("KRX", "NXT", "SOR"), (), None, None, "confirmed"),
    ("16", ("KRX", "NXT", "SOR"), (), None, None, "confirmed"),
    ("21", ("KRX", "NXT"), (), None, None, "confirmed"),
    ("22", ("KRX", "NXT"), (), None, None, "confirmed"),
    ("23", ("KRX", "NXT"), (), None, None, "confirmed"),
    ("24", ("KRX", "NXT"), (), None, None, "confirmed"),
    ("27", ("NXT",), ("SOR",), _D_0914, None, "name_unconfirmed"),
    ("28", ("NXT",), ("SOR",), _D_0914, None, "name_unconfirmed"),
    ("29", ("NXT",), ("SOR",), _D_0914, None, "name_unconfirmed"),
    ("41", ("KRX",), ("SOR",), _D_0914, None, "name_unconfirmed"),
    ("42", ("KRX",), ("SOR",), _D_0914, None, "name_unconfirmed"),
    ("43", ("KRX",), ("SOR",), _D_0914, None, "name_unconfirmed"),
    ("44", ("KRX",), ("SOR",), _D_0914, None, "name_unconfirmed"),
    ("45", ("KRX",), ("SOR",), _D_0914, None, "name_unconfirmed"),
    ("46", ("KRX",), ("SOR",), _D_0914, None, "name_unconfirmed"),
    ("47", ("KRX",), ("SOR",), _D_0914, None, "name_unconfirmed"),
)

#: 전 구간 스윕용 시각 — 모든 행의 start/end 와 그 1초 전.
_SWEEP_TIMES: tuple = tuple(sorted({
    t
    for r in _ROWS
    for t in (
        r.start,
        r.end,
        (datetime.combine(date(2026, 1, 1), r.start) - timedelta(seconds=1)).time(),
        (datetime.combine(date(2026, 1, 1), r.end) - timedelta(seconds=1)).time(),
    )
} | {time(3, 0), time(20, 30), time(23, 59, 59)}))

_ALL_DATES: tuple = (_D_0911, _D_0912, _D_0913, _D_0914, _D_0915)


def _declared_codes_for(market: str) -> set:
    return {c for c, ex, unk, *_ in _DIVISIONS if market in ex}


# ===========================================================================
# A. 데이터 무결성 (A1~A14)
# ===========================================================================
def test_a1_table_has_13_rows_with_expected_ids():
    """A1 — 13행 · row_id 집합 == {K1..K7, N1..N6} · 중복 0."""
    table = _attr("MARKET_TABLE")
    ids = [r.row_id for r in table]
    assert len(table) == 13, f"MARKET_TABLE 13행 계약 위반 — {len(table)}행"
    assert len(ids) == len(set(ids)), f"row_id 중복 — {ids}"
    assert set(ids) == {r.row_id for r in _ROWS}, (
        f"row_id 집합 불일치 — 기대 {sorted(r.row_id for r in _ROWS)} / 실제 {sorted(ids)}"
    )


def test_a2_every_row_start_before_end():
    """A2 — 모든 행 `start < end` (자정 넘는 창 0)."""
    for r in _attr("MARKET_TABLE"):
        assert r.start < r.end, f"{r.row_id}: start({r.start}) >= end({r.end})"


def test_a3_every_row_market_in_market_order():
    """A3 — `market` 은 `MARKET_ORDER` 원소."""
    order = tuple(_attr("MARKET_ORDER"))
    assert order == ("KRX", "NXT"), f"MARKET_ORDER 계약 위반 — {order}"
    for r in _attr("MARKET_TABLE"):
        assert r.market in order, f"{r.row_id}: 미지 market {r.market!r}"


def test_a4_closed_vocabularies():
    """A4 — phase·match_kind·confidence 가 닫힌 어휘 안."""
    mod = _ms()
    phase_values = {_phase_name(p) for p in _attr("MarketPhase")}
    match_kinds = set(_attr("MATCH_KINDS"))
    confidences = set(_attr("CONFIDENCE_LEVELS"))
    evidences = set(_attr("EVIDENCE_LEVELS"))
    assert match_kinds == set(
        ("continuous", "single_auction", "periodic_auction", "fixed_price", "none")
    ), f"MATCH_KINDS 계약 위반 — {sorted(match_kinds)}"
    assert confidences == {"confirmed", "unconfirmed", "ambiguous"}, (
        f"CONFIDENCE_LEVELS 계약 위반 — {sorted(confidences)}"
    )
    for r in mod.MARKET_TABLE:
        assert _phase_name(r.phase) in phase_values, f"{r.row_id}: 미지 phase"
        assert r.match_kind in match_kinds, f"{r.row_id}: 미지 match_kind {r.match_kind!r}"
        assert r.confidence in confidences, f"{r.row_id}: 미지 confidence {r.confidence!r}"
        assert r.quote_channel_evidence in evidences, f"{r.row_id}: 미지 evidence"


def test_a5_row_divisions_subset_of_exchange_available_raw():
    """A5 (M2 raw) — 선언 `order_divisions` ⊆ 그 거래소 가용 코드 집합."""
    mod = _ms()
    available = {
        m: {d.code for d in mod.ORDER_DIVISIONS if m in set(d.exchanges)}
        for m in ("KRX", "NXT")
    }
    for r in mod.MARKET_TABLE:
        extra = set(r.order_divisions) - available[r.market]
        assert not extra, (
            f"{r.row_id}({r.market}): {r.market} 가용 집합 밖 코드 {sorted(extra)} — M2 위반"
        )


def test_a6_every_row_code_exists_in_catalog():
    """A6 — 행이 쓰는 코드는 전부 카탈로그에 있다."""
    mod = _ms()
    known = {d.code for d in mod.ORDER_DIVISIONS}
    for r in mod.MARKET_TABLE:
        missing = set(r.order_divisions) - known
        assert not missing, f"{r.row_id}: 카탈로그에 없는 코드 {sorted(missing)}"


def test_a7_row_divisions_sorted_unique_tuple():
    """A7 — `order_divisions` 는 tuple · 오름차순 · 중복 0."""
    for r in _attr("MARKET_TABLE"):
        codes = r.order_divisions
        assert isinstance(codes, tuple), f"{r.row_id}: order_divisions 가 tuple 이 아니다"
        assert list(codes) == sorted(codes), f"{r.row_id}: 정렬 위반 {codes}"
        assert len(set(codes)) == len(codes), f"{r.row_id}: 중복 {codes}"


def test_a8_catalog_has_28_codes():
    """A8 — 28 코드 · 중복 0 · 형식 `^\\d{2}$`."""
    import re

    divisions = _attr("ORDER_DIVISIONS")
    codes = [d.code for d in divisions]
    assert len(divisions) == 28, f"ORDER_DIVISIONS 28행 계약 위반 — {len(divisions)}"
    assert len(set(codes)) == 28, f"코드 중복 — {codes}"
    assert set(codes) == {c for c, *_ in _DIVISIONS}, (
        f"코드 집합 불일치 — 기대 {sorted(c for c, *_ in _DIVISIONS)} / 실제 {sorted(codes)}"
    )
    for c in codes:
        assert re.fullmatch(r"\d{2}", c), f"코드 형식 위반 {c!r}"


def test_a9_exchange_sets_disjoint_and_bounded():
    """A9 — `exchanges ∩ exchanges_unknown == ∅`, 둘 다 ⊆ EXCHANGE_ORDER, 합집합 ≥ 1."""
    allowed = set(_attr("EXCHANGE_ORDER"))
    assert tuple(_attr("EXCHANGE_ORDER")) == ("KRX", "NXT", "SOR")
    for d in _attr("ORDER_DIVISIONS"):
        ex, unk = set(d.exchanges), set(d.exchanges_unknown)
        assert not (ex & unk), f"{d.code}: exchanges ∩ unknown = {sorted(ex & unk)}"
        assert ex <= allowed and unk <= allowed, f"{d.code}: 미지 거래소 {sorted((ex | unk) - allowed)}"
        assert ex or unk, f"{d.code}: 거래소 정보가 비어 있다"


def test_a10_finding1_market_order_absent_on_nxt():
    """A10 — 발견 1 봉인: `01`(시장가)은 NXT 에 **없다**(미확인도 아니다)."""
    d = {x.code: x for x in _attr("ORDER_DIVISIONS")}["01"]
    assert "NXT" not in set(d.exchanges), "01(시장가)이 NXT 가용으로 바뀌었다 — 발견 1 붕괴"
    assert "NXT" not in set(d.exchanges_unknown), "01 의 NXT 는 '미확인' 이 아니라 '미지원' 이다"
    assert set(d.exchanges) == {"KRX", "SOR"}, f"01 exchanges 계약 위반 — {sorted(d.exchanges)}"


@pytest.mark.parametrize("code", ["05", "06", "07"])
def test_a11_finding2_sor_has_no_after_hours_codes(code):
    """A11 — 발견 2 봉인: SOR 에 시간외 코드(05·06·07)가 없다."""
    d = {x.code: x for x in _attr("ORDER_DIVISIONS")}[code]
    assert "SOR" not in set(d.exchanges), f"{code}: SOR 가용으로 바뀌었다 — 발견 2 붕괴"
    assert "SOR" not in set(d.exchanges_unknown), f"{code}: SOR 는 미확인이 아니라 미지원이다"
    assert set(d.exchanges) == {"KRX"}, f"{code} exchanges 계약 위반 — {sorted(d.exchanges)}"


def test_a12_new_codes_effective_dates_and_unknown_sor():
    """A12 — 27~29 / 41~47 / 07 의 유효기간과 `exchanges_unknown == {SOR}`."""
    by_code = {x.code: x for x in _attr("ORDER_DIVISIONS")}
    for code in ("27", "28", "29"):
        d = by_code[code]
        assert set(d.exchanges) == {"NXT"}, f"{code}: NXT 전용이어야 한다 — {sorted(d.exchanges)}"
        assert d.effective_from == _D_0914, f"{code}: effective_from {d.effective_from}"
        assert set(d.exchanges_unknown) == {"SOR"}, f"{code}: SOR 미확인 표시가 사라졌다"
    for code in ("41", "42", "43", "44", "45", "46", "47"):
        d = by_code[code]
        assert set(d.exchanges) == {"KRX"}, f"{code}: KRX 전용이어야 한다"
        assert d.effective_from == _D_0914, f"{code}: effective_from {d.effective_from}"
        assert set(d.exchanges_unknown) == {"SOR"}, f"{code}: SOR 미확인 표시가 사라졌다"
    assert by_code["07"].effective_to == _D_0912, (
        f"07(시간외단일가) 폐지일 계약 위반 — {by_code['07'].effective_to}"
    )


def test_a13_frozen_dataclasses_and_tuple_containers():
    """A13 — 행/코드 자료구조가 frozen 이고 컨테이너가 tuple 이다(런타임 변조 차단)."""
    mod = _ms()
    for cls_name in ("MarketRow", "OrderDivisionSpec"):
        cls = _attr(cls_name)
        assert dataclasses.is_dataclass(cls), f"{cls_name} 이 dataclass 가 아니다"
        assert cls.__dataclass_params__.frozen, f"{cls_name} 이 frozen 이 아니다"
    assert isinstance(mod.MARKET_TABLE, tuple), "MARKET_TABLE 이 tuple 이 아니다"
    assert isinstance(mod.ORDER_DIVISIONS, tuple), "ORDER_DIVISIONS 가 tuple 이 아니다"
    with pytest.raises(dataclasses.FrozenInstanceError):
        mod.MARKET_TABLE[0].row_id = "ZZ"


@pytest.mark.parametrize("expected", _ROWS, ids=[r.row_id for r in _ROWS])
def test_a14_golden_row_values(expected):
    """A14 — 13행 전 필드 골든 비교. 행 삭제·값 변조 즉시 RED(m1·m4)."""
    by_id = {r.row_id: r for r in _attr("MARKET_TABLE")}
    assert expected.row_id in by_id, f"{expected.row_id} 행이 사라졌다 — 표 삭제 금지"
    got = by_id[expected.row_id]
    assert got.market == expected.market, f"{expected.row_id}.market"
    assert got.start == expected.start, f"{expected.row_id}.start {got.start} != {expected.start}"
    assert got.end == expected.end, f"{expected.row_id}.end {got.end} != {expected.end}"
    assert _phase_name(got.phase) == expected.phase, f"{expected.row_id}.phase"
    assert got.name_ko == expected.name_ko, f"{expected.row_id}.name_ko {got.name_ko!r}"
    assert got.match_kind == expected.match_kind, f"{expected.row_id}.match_kind"
    assert got.match_ko == expected.match_ko, f"{expected.row_id}.match_ko {got.match_ko!r}"
    assert tuple(got.order_divisions) == expected.divisions, (
        f"{expected.row_id}.order_divisions {tuple(got.order_divisions)} != {expected.divisions}"
    )
    assert got.priority == expected.priority, f"{expected.row_id}.priority"
    assert got.overlap_ok is expected.overlap_ok, f"{expected.row_id}.overlap_ok"
    assert got.effective_from == expected.effective_from, f"{expected.row_id}.effective_from"
    assert got.effective_to == expected.effective_to, f"{expected.row_id}.effective_to"
    assert got.confidence == expected.confidence, f"{expected.row_id}.confidence"
    if expected.confidence != "confirmed":
        assert got.note and got.note.strip(), (
            f"{expected.row_id}: 미확인 행인데 note 가 비어 있다 — 화면이 사유를 못 띄운다"
        )


# ===========================================================================
# B. 중첩·우선순위 (B1~B8)
# ===========================================================================
def _overlaps(a: Row, b: Row) -> bool:
    return a.market == b.market and a.start < b.end and b.start < a.end


def test_b1_date_blind_overlap_pairs_are_declared():
    """B1 — 날짜 무시 겹침 쌍 == {(K1,K2), (K6,K7)} ∧ 각 쌍에 overlap_ok 선언 존재."""
    rows = list(_attr("MARKET_TABLE"))
    got = set()
    for i, a in enumerate(rows):
        for b in rows[i + 1:]:
            if a.market == b.market and a.start < b.end and b.start < a.end:
                got.add(tuple(sorted((a.row_id, b.row_id))))
    assert got == {("K1", "K2"), ("K6", "K7")}, (
        f"날짜 무시 겹침 쌍 계약 위반 — {sorted(got)}"
    )
    by_id = {r.row_id: r for r in rows}
    for pair in got:
        assert any(by_id[rid].overlap_ok for rid in pair), (
            f"{pair}: overlap_ok 선언이 없다 — 의도된 중첩인지 데이터 결함인지 구분 불가"
        )


@pytest.mark.parametrize("on_date", _ALL_DATES, ids=lambda d: d.isoformat())
@pytest.mark.parametrize("market", ["KRX", "NXT"])
def test_b2_no_chain_row_overlap_per_date(on_date, market):
    """B2 (M1) — 각 시장·각 유효일에 `priority==10` 체인 행끼리 겹침 0."""
    rows = [
        r for r in _table(on_date)
        if r.market == market and r.priority == 10
    ]
    for i, a in enumerate(rows):
        for b in rows[i + 1:]:
            assert not (a.start < b.end and b.start < a.end), (
                f"{on_date} {market}: 체인 행 겹침 {a.row_id}({a.start}~{a.end}) "
                f"× {b.row_id}({b.start}~{b.end}) — 커서가 모호해진다"
            )


def test_b3_k6_and_k7_never_coexist_on_any_date():
    """B3 (정정-3) — K6·K7 이 동시에 유효한 날짜가 **하루도 없다**."""
    by_id = {r.row_id: r for r in _attr("MARKET_TABLE")}
    k6, k7 = by_id["K6"], by_id["K7"]
    assert k7.effective_to is not None and k6.effective_from is not None
    assert k7.effective_to < k6.effective_from, (
        f"K7 폐지일({k7.effective_to}) >= K6 시행일({k6.effective_from}) — 공존일이 생긴다"
    )
    # 전수 — 폐지 2주 전 ~ 시행 2주 후
    d = k7.effective_to - timedelta(days=14)
    last = k6.effective_from + timedelta(days=14)
    while d <= last:
        ids = {r.row_id for r in _table(d)}
        assert not {"K6", "K7"} <= ids, f"{d}: K6·K7 동시 유효"
        d += timedelta(days=1)


def test_b4_0835_cursor_is_k1_with_k2_concurrent():
    """B4 — 08:35 KRX 커서는 K1, 동시 행은 K2(m2: K1 강등 시 뒤집힌다)."""
    st = _state(_at(_D_0911, time(8, 35)), "KRX")
    assert st.row_id == "K1", (
        f"08:35 커서는 K1(시가 단일가)이어야 한다 — 실제 {st.row_id!r}. "
        "K2 가 커서가 되면 화면이 '장전 시간외' 라면서 시장가 가능을 띄운다(모순)"
    )
    assert tuple(st.concurrent_row_ids) == ("K2",), (
        f"동시 행 계약 위반 — {tuple(st.concurrent_row_ids)}"
    )


def test_b5_0835_divisions_are_union_of_live_rows():
    """B5 — 08:35 의 답은 **합집합** ("00","01","05") ∧ 행별 내역 보존."""
    st = _state(_at(_D_0911, time(8, 35)), "KRX")
    assert tuple(st.order_divisions) == ("00", "01", "05"), (
        f"동시 중첩 합집합 위반 — {tuple(st.order_divisions)}. "
        "사용자 질문('지금 무엇을 쓸 수 있나')의 답은 커서 행 단독이 아니다"
    )
    by_row = {rid: tuple(codes) for rid, codes in st.order_divisions_by_row}
    assert by_row == {"K1": ("00", "01"), "K2": ("05",)}, (
        f"행별 내역 계약 위반 — {by_row}"
    )


def test_b6_0825_has_no_concurrent_row():
    """B6 — 08:25 는 K1 단독."""
    st = _state(_at(_D_0911, time(8, 25)), "KRX")
    assert st.row_id == "K1"
    assert tuple(st.concurrent_row_ids) == ()
    assert tuple(st.order_divisions) == ("00", "01")


def test_b7_0840_k2_window_closed_half_open():
    """B7 — 08:40:00 에 K2 는 끝났다(반개구간). `05` 가 사라진다(m3)."""
    st = _state(_at(_D_0911, time(8, 40)), "KRX")
    assert st.row_id == "K1"
    assert tuple(st.concurrent_row_ids) == (), (
        f"08:40:00 에 K2 가 아직 살아 있다 — 구간이 [start, end] 로 바뀌었다: "
        f"{tuple(st.concurrent_row_ids)}"
    )
    assert "05" not in st.order_divisions


def test_b8_priority_tie_is_deterministic_and_ambiguous(monkeypatch):
    """B8 — priority 동률은 데이터 결함. 커서는 결정론적이되 `ambiguous` 로 시끄럽게."""
    mod = _ms()
    rows = list(mod.MARKET_TABLE)
    k3 = next(r for r in rows if r.row_id == "K3")
    twin = dataclasses.replace(k3, row_id="K3X")
    monkeypatch.setattr(mod, "MARKET_TABLE", tuple(rows + [twin]), raising=True)

    st = _state(_at(_D_0911, time(13, 5)), "KRX")
    assert st.row_id == "K3", (
        f"동률 시 커서는 (priority,start,row_id) 최소여야 한다 — 실제 {st.row_id!r}"
    )
    assert st.confidence == "ambiguous", (
        f"동률을 조용히 삼켰다 — confidence={st.confidence!r}. 데이터 결함은 화면에 보여야 한다"
    )


#: 하루 운영 창 — 이 창 안의 **공백 전수**를 고정한다(M1: 공백은 실패가 아니라 데이터다).
_DAY_WINDOW = (time(8, 0), time(20, 0))

#: (시장, 유효일) → 그 날 그 시장의 **빈 구간 전부**. 값이 아니라 *사실* 이다.
_EXPECTED_GAPS = {
    # KRX 저녁 구멍이 날짜에 따라 움직인다 — K7(~09-12) → 없음(09-13) → K6(09-14~)
    ("KRX", _D_0911): ((time(8, 0), time(8, 20)), (time(18, 0), time(20, 0))),
    ("KRX", _D_0912): ((time(8, 0), time(8, 20)), (time(18, 0), time(20, 0))),
    ("KRX", _D_0913): ((time(8, 0), time(8, 20)), (time(16, 0), time(20, 0))),
    ("KRX", _D_0914): ((time(8, 0), time(8, 20)),),
    ("KRX", _D_0915): ((time(8, 0), time(8, 20)),),
    # NXT 는 날짜와 무관하게 **09:00:00~09:00:30 의 30초 꼬리 하나**뿐이다(N3 시작 미확인)
    ("NXT", _D_0911): ((time(9, 0), time(9, 0, 30)),),
    ("NXT", _D_0912): ((time(9, 0), time(9, 0, 30)),),
    ("NXT", _D_0913): ((time(9, 0), time(9, 0, 30)),),
    ("NXT", _D_0914): ((time(9, 0), time(9, 0, 30)),),
    ("NXT", _D_0915): ((time(9, 0), time(9, 0, 30)),),
}


@pytest.mark.parametrize("on_date", _ALL_DATES, ids=lambda d: d.isoformat())
@pytest.mark.parametrize("market", ["KRX", "NXT"])
def test_b10_gap_inventory_is_pinned(market, on_date):
    """B10 (M1) — 08:00~20:00 안의 **빈 구간 전수**를 고정한다.

    공백은 실패가 아니라 데이터다. 다만 *어떤* 공백이 있는지는 화면이 "장 종료" 로
    말하게 되는 자리라 반드시 의도된 것이어야 한다. 세 종류가 있다 —
    ① KRX 08:00~08:20(K1 이전) ② KRX 저녁 구멍(09-13 은 16:00~20:00, 그 밖은 18:00~20:00,
    09-14 부터는 K6 이 메운다) ③ **NXT 09:00:00~09:00:30**(N3 시작 미확인의 30초 꼬리).
    임의로 메우면 미확인 값을 확정 값으로 바꾸는 것이고, 새 공백이 생기면 여기서 붉어진다.
    """
    anchor = date(2026, 1, 1)
    rows = [r for r in _table(on_date) if r.market == market and r.priority == 10]
    win_s = datetime.combine(anchor, _DAY_WINDOW[0])
    win_e = datetime.combine(anchor, _DAY_WINDOW[1])

    spans = sorted(
        (max(win_s, datetime.combine(anchor, r.start)),
         min(win_e, datetime.combine(anchor, r.end)))
        for r in rows
    )
    merged = []
    for s, e in spans:
        if s >= e:
            continue
        if merged and s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))

    gaps, cursor = [], win_s
    for s, e in merged:
        if s > cursor:
            gaps.append((cursor.time(), s.time()))
        cursor = max(cursor, e)
    if cursor < win_e:
        gaps.append((cursor.time(), win_e.time()))

    expected = _EXPECTED_GAPS[(market, on_date)]
    assert tuple(gaps) == expected, (
        f"{on_date} {market}: 빈 구간 {gaps} != 기대 {list(expected)}. "
        "공백이 새로 생겼거나(행 삭제·경계 이동) 임의로 메워졌다"
    )


def test_b9_priority_beats_start_order(monkeypatch):
    """B9 — 커서는 **`priority` 가 먼저**다. 시작 시각 순서가 아니다.

    현재 표에서는 유일한 오버레이(K2)가 체인 행(K1)보다 늦게 시작해 두 정렬이 우연히
    같은 답을 낸다 — 그래서 `priority` 를 빼도 오늘은 아무 테스트도 붉어지지 않는다.
    그 우연이 깨지는 날(체인 행보다 **먼저 시작하는** 오버레이가 생기는 날) 커서가 조용히
    뒤집히므로, 합성 행으로 그 날을 미리 살아본다. 명세 §1.6-2·-3(파생 금지)의 행위면이다.
    """
    mod = _ms()
    rows = list(mod.MARKET_TABLE)
    k3 = next(r for r in rows if r.row_id == "K3")
    overlay = dataclasses.replace(
        k3, row_id="KX", start=time(8, 55), end=time(9, 30),
        priority=20, overlap_ok=True, name_ko="합성 오버레이",
    )
    monkeypatch.setattr(mod, "MARKET_TABLE", tuple(rows + [overlay]), raising=True)

    st = _state(_at(_D_0911, time(9, 10)), "KRX")
    assert st.row_id == "K3", (
        f"커서 {st.row_id!r} — 오버레이(priority=20)가 더 일찍 시작했다고 커서를 가져갔다. "
        "정렬 키는 (priority, start, row_id) 이고 priority 가 먼저다"
    )
    assert tuple(st.concurrent_row_ids) == ("KX",)
    assert st.confidence == "confirmed", "priority 가 다르면 동률이 아니다"


# ===========================================================================
# C. 경계 격자 (C-grid, C-a ~ C-k)
# ===========================================================================
_GRID_POINTS = ("before_start", "start", "last_second", "end")


@pytest.mark.parametrize("point", _GRID_POINTS)
@pytest.mark.parametrize("row", _ROWS, ids=[r.row_id for r in _ROWS])
def test_c_grid_half_open_membership(row, point):
    """C-grid (M3) — 13행 × 4모서리 = 52 케이스. 구간은 `[start, end)`.

    `start-1s` / `end` 에서는 그 행이 **살아 있지 않고**, `start` / `end-1s` 에서는 살아 있다.
    freezegun 으로 고정하고 `now=None`(KST 기본 경로)으로 판정한다.
    """
    base = row.grid_date
    if point == "before_start":
        moment, expect_live = _at(base, row.start) - timedelta(seconds=1), False
    elif point == "start":
        moment, expect_live = _at(base, row.start), True
    elif point == "last_second":
        moment, expect_live = _at(base, row.end) - timedelta(seconds=1), True
    else:
        moment, expect_live = _at(base, row.end), False

    with freeze_time(moment):
        st = _state(None, row.market)
    live = _live_ids(st)
    if expect_live:
        assert row.row_id in live, (
            f"{row.row_id} @ {moment.time()} ({point}): 살아 있어야 하는데 {sorted(live)}"
        )
    else:
        assert row.row_id not in live, (
            f"{row.row_id} @ {moment.time()} ({point}): 끝났는데 아직 살아 있다 — "
            "반개구간 [start, end) 위반"
        )


def test_c_a_0900_is_regular_not_pre_auction():
    """C-a — 09:00:00 은 K1 이 아니라 K3 다(m3·m4)."""
    st = _state(_at(_D_0911, time(9, 0)), "KRX")
    assert st.row_id == "K3", f"09:00:00 커서 {st.row_id!r} — 시가 단일가는 09:00 에 끝난다"
    assert tuple(st.concurrent_row_ids) == ()
    assert st.market_order_ok is True


def test_c_b_1520_close_auction_and_nxt_break():
    """C-b — 15:20:00 → KRX K4(종가 단일가) / NXT N4(휴장)."""
    assert _state(_at(_D_0911, time(15, 20)), "KRX").row_id == "K4"
    nxt = _state(_at(_D_0911, time(15, 20)), "NXT")
    assert nxt.row_id == "N4"
    assert _phase_name(nxt.phase) == "BREAK"
    assert nxt.is_open is False


def test_c_c_1530_after_close_fixed_and_nxt_after_single():
    """C-c — 15:30:00 → KRX K5 / NXT N5."""
    assert _state(_at(_D_0911, time(15, 30)), "KRX").row_id == "K5"
    assert _state(_at(_D_0911, time(15, 30)), "NXT").row_id == "N5"


@pytest.mark.parametrize(
    "on_date,expected",
    [(_D_0914, "K6"), (_D_0911, "K7"), (_D_0913, None)],
    ids=["0914_after_market", "0911_after_single", "0913_gap"],
)
def test_c_d_1600_depends_on_date(on_date, expected):
    """C-d — 16:00:00 의 답은 날짜가 정한다. 09-13 은 **행이 없다**(정정-2)."""
    st = _state(_at(on_date, time(16, 0)), "KRX")
    assert st.row_id == expected, (
        f"{on_date} 16:00 커서 {st.row_id!r} != {expected!r} — 유효기간 해석 결함"
    )
    if expected is None:
        assert _phase_name(st.phase) == "CLOSED", (
            "09-13 16:00 은 표에 행이 없다. 데이터를 넓혀 메우면 정본에 없는 값을 지어내는 것이다"
        )


@pytest.mark.parametrize("market", ["KRX", "NXT"])
def test_c_e_2000_closed_with_no_next_boundary(market):
    """C-e — 20:00:00 이후는 양 시장 CLOSED ∧ 다음 경계 없음(익일로 굴리지 않는다)."""
    st = _state(_at(_D_0914, time(20, 0)), market)
    assert st.row_id is None, f"{market} 20:00 커서 {st.row_id!r}"
    assert _phase_name(st.phase) == "CLOSED"
    assert st.seconds_to_next is None, (
        f"{market}: 20:00 이후 seconds_to_next={st.seconds_to_next} — "
        "내일이 거래일인지 모르는 순수 함수가 다음 날을 말하면 금요일 밤에 거짓이 된다"
    )
    assert st.next_row_id is None
    assert st.next_phase is None


@pytest.mark.parametrize(
    "t,expected",
    [(time(9, 0, 0), None), (time(9, 0, 29), None), (time(9, 0, 30), "N3")],
    ids=["0900_00", "0900_29", "0900_30"],
)
def test_c_f_nxt_unconfirmed_30_second_tail(t, expected):
    """C-f — N3 시작이 미확인이라 09:00:00~09:00:29 에 **어느 행도 없다**.

    ⚠️ 명세 §7.1 C-f 는 이 30초를 N2 로 적었으나 정본 표의 N2 는 08:50~09:00 이고
    구간은 반개구간이다. 표를 넓혀 메우지 않는다(정정-2 와 같은 원칙).
    어느 해석에서도 참인 안전 성질(주문 불가)을 함께 잠근다.
    """
    st = _state(_at(_D_0911, t), "NXT")
    assert st.row_id == expected, (
        f"09:00:{t.second:02d} NXT 커서 {st.row_id!r} != {expected!r}. "
        "30초 꼬리를 임의로 09:00:00 으로 당기면 미확인 값을 확정 값으로 바꾸는 것이다"
    )
    if expected is None:
        assert st.is_open is False and st.can_order is False, (
            "미확인 30초 구간이 '주문 가능' 으로 보이면 안 된다"
        )
        assert st.next_row_id == "N3"
    else:
        assert st.market_order_ok is False


def test_c_g_nxt_premarket_to_break():
    """C-g — 08:49:59 N1 / 08:50:00 N2."""
    assert _state(_at(_D_0911, time(8, 49, 59)), "NXT").row_id == "N1"
    assert _state(_at(_D_0911, time(8, 50)), "NXT").row_id == "N2"


def test_c_h_before_first_row_counts_down_to_it():
    """C-h — 07:59:59 NXT → CLOSED ∧ 다음 행 N1 ∧ 1초."""
    st = _state(_at(_D_0911, time(7, 59, 59)), "NXT")
    assert st.row_id is None and _phase_name(st.phase) == "CLOSED"
    assert st.next_row_id == "N1", f"다음 행 {st.next_row_id!r}"
    assert st.seconds_to_next == 1, f"seconds_to_next={st.seconds_to_next}"
    assert st.next_boundary == time(8, 0)


def test_c_i_nxt_after_single_to_after_market():
    """C-i — 15:39:59 N5 / 15:40:00 N6."""
    assert _state(_at(_D_0911, time(15, 39, 59)), "NXT").row_id == "N5"
    assert _state(_at(_D_0911, time(15, 40)), "NXT").row_id == "N6"


@pytest.mark.parametrize(
    "market,on_date", [("NXT", _D_0911), ("KRX", _D_0914)], ids=["NXT", "KRX"]
)
def test_c_j_seconds_to_next_is_ceiling(market, on_date):
    """C-j — 19:59:59.5 의 남은 시간은 **1** 이다(내림이면 0 = '지금이 경계' 거짓)."""
    st = _state(_at(on_date, time(19, 59, 59)).replace(microsecond=500_000), market)
    assert st.seconds_to_next == 1, (
        f"{market} 19:59:59.5 → seconds_to_next={st.seconds_to_next} (올림 계약 위반)"
    )


@pytest.mark.parametrize("market,first_row", [("KRX", "K1"), ("NXT", "N1")])
def test_c_k_before_any_row_points_at_first_row(market, first_row):
    """C-k — 03:00 은 CLOSED 이고 다음 행은 그날 첫 행이다."""
    st = _state(_at(_D_0911, time(3, 0)), market)
    assert st.row_id is None and _phase_name(st.phase) == "CLOSED"
    assert st.next_row_id == first_row, f"{market} 03:00 다음 행 {st.next_row_id!r}"
    assert st.seconds_to_next and st.seconds_to_next > 0


# ===========================================================================
# D. 날짜 차원 (D1~D9)
# ===========================================================================
def _krx_ids(on_date) -> set:
    return {r.row_id for r in _table(on_date) if r.market == "KRX"}


def test_d1_0912_has_k7_not_k6():
    """D1 — 09-12 는 K7 의 마지막 유효일."""
    ids = _krx_ids(_D_0912)
    assert "K7" in ids, "09-12 는 K7 의 마지막 유효일이다(effective_to inclusive) — m5"
    assert "K6" not in ids, "K6 은 09-14 부터다"


def test_d2_0913_has_neither_k6_nor_k7():
    """D2 (정정-2) — 09-13 은 둘 다 없다. KRX 5행."""
    ids = _krx_ids(_D_0913)
    assert "K6" not in ids and "K7" not in ids, f"09-13 KRX 행 {sorted(ids)}"
    assert ids == {"K1", "K2", "K3", "K4", "K5"}, f"09-13 KRX 행 집합 {sorted(ids)}"


def test_d3_0914_has_k6_not_k7():
    """D3 — 09-14 전환일."""
    ids = _krx_ids(_D_0914)
    assert "K6" in ids and "K7" not in ids, f"09-14 KRX 행 {sorted(ids)}"


def test_d4_0915_identical_to_0914():
    """D4 — 09-15 는 09-14 와 행 집합이 같다(전환은 1회)."""
    a = {r.row_id for r in _table(_D_0914)}
    b = {r.row_id for r in _table(_D_0915)}
    assert a == b, f"09-14 {sorted(a)} != 09-15 {sorted(b)}"


def test_d5_0913_1630_is_closed_with_no_row():
    """D5 — 09-13 16:30 KRX = CLOSED · row_id None. 공백을 데이터로 메우지 않은 귀결."""
    st = _state(_at(_D_0913, time(16, 30)), "KRX")
    assert _phase_name(st.phase) == "CLOSED"
    assert st.row_id is None
    assert st.can_order is False


@pytest.mark.parametrize(
    "on_date,expected_len", [(_D_0912, 13), (_D_0914, 16)], ids=["0912", "0914"]
)
def test_d6_n1_divisions_resolved_by_date(on_date, expected_len):
    """D6 (M2 resolved) — N1 의 27~29 는 09-14 부터만 유효하다(m6)."""
    row = next(r for r in _table(on_date) if r.row_id == "N1")
    codes = tuple(row.order_divisions)
    assert len(codes) == expected_len, f"{on_date} N1 코드 {len(codes)}개 — {codes}"
    gtp = {"27", "28", "29"}
    if expected_len == 13:
        assert not (set(codes) & gtp), f"{on_date} 에 GTP 가 노출됐다 — {codes}"
    else:
        assert gtp <= set(codes), f"{on_date} 에 GTP 가 빠졌다 — {codes}"
    # 날짜 해석 후에도 M2 유지
    assert set(codes) <= _declared_codes_for("NXT")


def test_d7_k6_divisions_and_absence():
    """D7 — 09-14 K6 = 41~47 ∧ 09-13 에는 K6 행 자체가 없다(m7)."""
    row = next(r for r in _table(_D_0914) if r.row_id == "K6")
    assert tuple(row.order_divisions) == _KRX_AFTER, f"K6 코드 {tuple(row.order_divisions)}"
    assert "01" not in row.order_divisions, "애프터마켓에 시장가는 없다"
    assert all(r.row_id != "K6" for r in _table(_D_0913))


def test_d8_pending_and_expired_are_visible_not_deleted():
    """D8 — 빠진 코드는 삭제가 아니라 `pending`/`expired` 로 **보인다**."""
    n1_0912 = next(r for r in _table(_D_0912) if r.row_id == "N1")
    assert tuple(n1_0912.order_divisions_pending) == ("27", "28", "29"), (
        f"09-12 N1 pending {tuple(n1_0912.order_divisions_pending)} — "
        "화면이 '곧 생긴다' 를 못 보여준다"
    )
    assert tuple(n1_0912.order_divisions_expired) == ()
    n1_0914 = next(r for r in _table(_D_0914) if r.row_id == "N1")
    assert tuple(n1_0914.order_divisions_pending) == ()
    # 셋의 합집합 == 선언 상위집합
    union = (
        set(n1_0912.order_divisions)
        | set(n1_0912.order_divisions_pending)
        | set(n1_0912.order_divisions_expired)
    )
    assert union == set(_NXT_PRE), f"유효+pending+expired != 선언 — {sorted(union)}"


def test_d9_table_without_argument_uses_kst_today():
    """D9 — 인자 없는 `get_market_table()` 은 KST 오늘 기준이다(TZ=UTC 에서도)."""
    with _tz("UTC"):
        with freeze_time(datetime(2026, 9, 13, 20, 0, tzinfo=_UTC)):  # KST 09-14 05:00
            ids = {r.row_id for r in _table()}
    assert "K6" in ids and "K7" not in ids, (
        f"KST 오늘(09-14) 기준이 아니다 — {sorted(ids)}. UTC 날짜(09-13)를 썼을 가능성"
    )


# ===========================================================================
# E. KST 강제 (E1~E5)
# ===========================================================================
class _tz:
    """컨테이너 TZ 를 일시 변경(`datetime.now()` naive 경로를 드러내기 위함)."""

    def __init__(self, name: str):
        self.name = name
        self._old = os.environ.get("TZ")

    def __enter__(self):
        os.environ["TZ"] = self.name
        if hasattr(_time_mod, "tzset"):
            _time_mod.tzset()
        return self

    def __exit__(self, *exc):
        if self._old is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = self._old
        if hasattr(_time_mod, "tzset"):
            _time_mod.tzset()
        return False


def test_e1_now_none_uses_kst_even_when_container_tz_is_utc():
    """E1 (M5) — `now=None` 은 KST. TZ=UTC 컨테이너에서 00:30Z 는 09:30 KST = 정규장(m9)."""
    with _tz("UTC"):
        with freeze_time(datetime(2026, 9, 11, 0, 30, tzinfo=_UTC)):
            st = _state(None, "KRX")
    assert st.row_id == "K3", (
        f"00:30Z(=09:30 KST) 커서 {st.row_id!r} — `datetime.now()` naive 로컬을 쓴 것 같다"
    )
    assert st.as_of.tzinfo is not None, "as_of 가 naive 다 — KST 강제 위반"
    assert st.as_of.utcoffset() == timedelta(hours=9), f"as_of offset {st.as_of.utcoffset()}"
    assert st.on_date == _D_0911


def test_e2_naive_now_is_treated_as_kst():
    """E2 (M5) — naive 는 **KST 로 간주**한다(UTC 로 간주하면 m10)."""
    st = _state(datetime(2026, 9, 11, 9, 30), "KRX")
    assert st.row_id == "K3", (
        f"naive 09:30 커서 {st.row_id!r} — naive 를 UTC 로 간주하면 18:30 KST 가 된다"
    )
    assert st.as_of.utcoffset() == timedelta(hours=9)
    assert st.on_date == _D_0911


def test_e3_utc_aware_now_is_converted():
    """E3 (M5) — 다른 tz aware 는 변환한다."""
    st = _state(datetime(2026, 9, 11, 0, 30, tzinfo=_UTC), "KRX")
    assert st.row_id == "K3"
    assert st.as_of.utcoffset() == timedelta(hours=9)


def test_e4_other_timezone_matches_utc_equivalent():
    """E4 (M5) — 임의 tz(뉴욕)도 같은 순간이면 같은 답."""
    try:
        from zoneinfo import ZoneInfo

        ny = ZoneInfo("America/New_York")
    except Exception:  # pragma: no cover — tzdata 부재 환경
        ny = timezone(timedelta(hours=-4))
    ny_moment = datetime(2026, 9, 11, 0, 30, tzinfo=_UTC).astimezone(ny)
    st = _state(ny_moment, "KRX")
    assert st.row_id == "K3"
    assert st.as_of == datetime(2026, 9, 11, 9, 30, tzinfo=_KST)


def test_e5_utc_evening_rolls_on_date_to_next_kst_day():
    """E5 (M5) — 23:00Z 는 KST 익일 08:00 이다. `on_date` 도 익일이어야 한다."""
    st = _state(datetime(2026, 9, 11, 23, 0, tzinfo=_UTC), "NXT")
    assert st.on_date == _D_0912, f"on_date {st.on_date} — KST 기준 날짜가 아니다"
    assert st.row_id == "N1", f"커서 {st.row_id!r} — KST 08:00 은 NXT 프리마켓이다"


# ===========================================================================
# F. 파생 필드 (F1~F6)
# ===========================================================================
def _sweep():
    for on_date in _ALL_DATES:
        for market in ("KRX", "NXT"):
            for t in _SWEEP_TIMES:
                yield on_date, market, t, _state(_at(on_date, t), market)


def test_f1_market_order_ok_matches_code_01_membership():
    """F1 (M6) — `market_order_ok == ("01" in order_divisions)` 전수(m8)."""
    for on_date, market, t, st in _sweep():
        assert st.market_order_ok is ("01" in tuple(st.order_divisions)), (
            f"{on_date} {market} {t}: market_order_ok={st.market_order_ok} vs "
            f"divisions={tuple(st.order_divisions)} — M6 위반"
        )


def test_f2_nxt_never_allows_market_order():
    """F2 (M6) — NXT 는 전 구간·전 날짜 시장가 불가(발견 1 의 행위 봉인)."""
    for on_date, market, t, st in _sweep():
        if market != "NXT":
            continue
        assert st.market_order_ok is False, (
            f"{on_date} NXT {t}: 시장가 가능으로 판정됐다 — NXT 코드 목록에 01 이 없다"
        )


def test_f3_is_open_is_phase_based():
    """F3 (M11) — `is_open` 은 phase 기반이다(divisions 기반이 아니다)."""
    for on_date, market, t, st in _sweep():
        expected = _phase_name(st.phase) not in ("BREAK", "CLOSED")
        assert st.is_open is expected, (
            f"{on_date} {market} {t}: is_open={st.is_open} phase={_phase_name(st.phase)}"
        )


def test_f4_can_order_is_divisions_based_and_n5_splits_them():
    """F4 (M11) — `can_order` 는 divisions 기반. N5 = 열렸지만 주문유형 미확인."""
    for on_date, market, t, st in _sweep():
        assert st.can_order is bool(tuple(st.order_divisions)), (
            f"{on_date} {market} {t}: can_order={st.can_order} divisions={tuple(st.order_divisions)}"
        )
    n5 = _state(_at(_D_0911, time(15, 35)), "NXT")
    assert n5.row_id == "N5"
    assert n5.is_open is True and n5.can_order is False, (
        f"N5: is_open={n5.is_open} can_order={n5.can_order} — "
        "단일가 구간인 것은 확정이고 쓸 주문유형이 미확인이다. 둘을 한 값으로 합치면 휴장으로 보인다"
    )
    assert n5.confidence == "unconfirmed"


def test_f5_decided_by_is_always_time():
    """F5 (M12) — 이 사이클은 시각으로만 판정한다. `code_seen` 은 항상 None."""
    for on_date, market, t, st in _sweep():
        assert st.decided_by == "time", (
            f"{on_date} {market} {t}: decided_by={st.decided_by!r} — "
            "MARKET_CLS_CODE 판정은 09-14 이후 실측이 쌓인 뒤의 별도 사이클이다"
        )
        assert st.code_seen is None, f"{on_date} {market} {t}: code_seen={st.code_seen!r}"


@pytest.mark.parametrize("row", _ROWS, ids=[r.row_id for r in _ROWS])
def test_f6_next_boundary_agrees_with_state_at_that_boundary(row):
    """F6 — `next_*` 는 그 경계에서 다시 물어본 답과 같다(예고와 실제의 정합).

    경계에 행이 없으면 `next_row_id is None` 이고 `next_phase` 는 **CLOSED** 다 —
    화면이 "다음: 장 종료" 를 말할 수 있어야 한다. `next_phase=None` 은 *다음 경계 자체가
    없을 때*(20:00 이후)만이다.
    """
    st = _state(_at(row.grid_date, row.start), row.market)
    if st.next_boundary is None:
        assert st.seconds_to_next is None and st.next_row_id is None
        assert st.next_phase is None
        return
    assert st.next_phase is not None, (
        f"{row.row_id}: 다음 경계 {st.next_boundary} 가 있는데 next_phase 가 None 이다 — "
        "화면이 '다음은 장 종료' 를 말할 수 없다"
    )
    at_boundary = _state(_at(row.grid_date, st.next_boundary), row.market)
    assert at_boundary.row_id == st.next_row_id, (
        f"{row.row_id}: 예고 next_row_id={st.next_row_id!r} vs "
        f"{st.next_boundary} 실제 {at_boundary.row_id!r}"
    )
    assert _phase_name(at_boundary.phase) == _phase_name(st.next_phase), (
        f"{row.row_id}: 예고 next_phase={st.next_phase} vs 실제 {at_boundary.phase}"
    )


def test_f7_market_argument_is_validated():
    """F7 — 미지 시장은 조용히 빈 표를 주지 않고 `ValueError` 다."""
    with pytest.raises(ValueError):
        _state(_at(_D_0911, time(13, 5)), "KOSPI")


# ===========================================================================
# G. 표 행의 파생 3필드 — **값으로** 잰다 (적대 검증 지적 1)
# ===========================================================================
#
# F1·F4 는 `get_market_state` 가 돌려주는 **커서**만 쟀다. `get_market_table` 이 돌려주는
# **표 행**의 `market_order_ok` · `can_order` · `tone` 은 어떤 테스트도 값으로 보지 않아
# 뮤테이션 3종이 살아남았다 —
#
#   * `market_order_ok = "01" in live` → `bool(live)` 로 바꿔도 전 스위트 초록
#   * `can_order` 판정 반전도 초록
#   * `tone` 산출 변경(다른 phase 의 톤을 주거나 상수로 고정)도 초록
#
# 표 행은 화면이 **그대로 그리는 값**이다. `market_order_ok` 가 `bool(live)` 가 되면
# 장전 시간외 종가(05 만 있는 행)가 "시장가 가능" 으로 표시되고, 사용자가 이 화면을 보고
# 낼 수 없는 주문을 기대한다. 그래서 전 행 × 전 유효일 격자로 세 필드를 잰다.
#
# 기대값은 **이 파일의 표 사본**(`_ROWS` · `_DIVISIONS` · `_PHASE_TONE`)에서 만든다.
# 구현 모듈의 `PHASE_TONES` 를 읽어 비교하면 "자기 자신과 같다" 는 공허한 검사가 된다.

#: phase → 화면 톤. 브리프 §1 의 사본이다(구현에서 읽지 않는다).
_PHASE_TONE: dict = {
    "PRE_AUCTION": "auction",
    "PRE_MARKET": "active",
    "REGULAR": "active",
    "CLOSE_AUCTION": "auction",
    "PRE_CLOSE_FIXED": "fixed",
    "AFTER_CLOSE_FIXED": "fixed",
    "AFTER_SINGLE": "auction",
    "AFTER_MARKET": "active",
    "BREAK": "break",
    "CLOSED": "closed",
}

_DIV_BY_CODE = {code: entry for entry in _DIVISIONS for code in (entry[0],)}


def _copy_row_effective(row: Row, on_date: date) -> bool:
    """사본 기준 — 그 날짜에 이 행이 존재하는가(`effective_to` 는 포함)."""
    if row.effective_from is not None and on_date < row.effective_from:
        return False
    if row.effective_to is not None and on_date > row.effective_to:
        return False
    return True


def _copy_live_codes(row: Row, on_date: date) -> tuple:
    """사본 기준 — 그 날짜에 그 행에서 실제로 쓸 수 있는 코드."""
    live = []
    for code in row.divisions:
        entry = _DIV_BY_CODE.get(code)
        if entry is None:
            live.append(code)
            continue
        _c, _ex, _unk, eff_from, eff_to, _conf = entry
        if eff_from is not None and on_date < eff_from:
            continue
        if eff_to is not None and on_date > eff_to:
            continue
        live.append(code)
    return tuple(live)


def _table_grid():
    """(날짜, 표 행) 전수 — 유효일 5개 × 그 날짜에 유효한 행 전부."""
    for on_date in _ALL_DATES:
        for row in _table(on_date):
            yield on_date, row


def test_g1_table_row_market_order_ok_matches_code_01():
    """G1 (M6 표 행) — `market_order_ok == ("01" in order_divisions)` 전수.

    `bool(order_divisions)` 로 바꾸면 05·06·07·41~47 만 있는 행이 전부 "시장가 가능" 이 된다.
    """
    seen_true = 0
    seen_false_with_codes = 0
    for on_date, row in _table_grid():
        codes = tuple(row.order_divisions)
        expected = "01" in codes
        assert row.market_order_ok is expected, (
            f"{on_date} {row.row_id}: market_order_ok={row.market_order_ok} vs "
            f"order_divisions={codes} — M6 위반"
        )
        if expected:
            seen_true += 1
        elif codes:
            seen_false_with_codes += 1
    # 두 코호트가 모두 실재해야 이 단언이 공허하지 않다.
    assert seen_true > 0, "시장가 가능한 표 행이 하나도 없다 — 격자가 잘못됐다"
    assert seen_false_with_codes > 0, (
        "주문유형은 있는데 시장가가 없는 행이 하나도 없다 — "
        "`bool(order_divisions)` 뮤테이션을 이 격자가 잡지 못한다"
    )


def test_g2_table_row_can_order_matches_divisions():
    """G2 (M11 표 행) — `can_order == bool(order_divisions)` 전수.

    판정이 반전되면 휴장 행이 "주문 가능", 정규장 행이 "주문 불가" 로 표시된다.
    """
    seen_true = 0
    seen_false = 0
    for on_date, row in _table_grid():
        codes = tuple(row.order_divisions)
        assert row.can_order is bool(codes), (
            f"{on_date} {row.row_id}: can_order={row.can_order} order_divisions={codes}"
        )
        if codes:
            seen_true += 1
        else:
            seen_false += 1
    assert seen_true > 0 and seen_false > 0, (
        f"한쪽 코호트가 비었다 — can_order True {seen_true} / False {seen_false}. "
        "반전 뮤테이션이 이 격자에서 죽지 않는다"
    )


def test_g3_table_row_tone_matches_phase():
    """G3 — 표 행의 `tone` 은 그 행 `phase` 의 톤이다(사본 `_PHASE_TONE` 기준)."""
    tones = _attr("TONES")
    seen: set = set()
    for on_date, row in _table_grid():
        phase = _phase_name(row.phase)
        expected = _PHASE_TONE[phase]
        assert row.tone == expected, (
            f"{on_date} {row.row_id}: tone={row.tone!r} phase={phase} 기대 {expected!r}"
        )
        assert row.tone in tones, f"{row.row_id}: tone={row.tone!r} 이 닫힌 어휘 밖이다"
        seen.add(row.tone)
    # 상수 고정(모든 행 같은 톤) 뮤테이션은 여기서 죽는다.
    assert len(seen) >= 3, (
        f"표 행의 톤이 {sorted(seen)} 뿐이다 — 화면이 단일가/연속/휴장을 색으로 구분하지 못한다"
    )


def test_g4_nxt_table_rows_never_allow_market_order():
    """G4 (발견 1, 표 행) — NXT 행은 전 날짜에서 `market_order_ok is False`."""
    counted = 0
    for on_date, row in _table_grid():
        if row.market != "NXT":
            continue
        counted += 1
        assert row.market_order_ok is False, (
            f"{on_date} {row.row_id}: NXT 행이 시장가 가능으로 표시됐다 — "
            "NXT 코드 목록에 01 이 없다(발견 1)"
        )
    assert counted >= len(_ALL_DATES) * 6, f"NXT 행 격자가 비었다 — {counted}건"


@pytest.mark.parametrize("on_date", _ALL_DATES, ids=[d.isoformat() for d in _ALL_DATES])
def test_g5_table_row_derived_fields_match_the_copy(on_date):
    """G5 — 세 파생 필드를 **이 파일의 표 사본**으로 독립 재계산해 대조한다.

    G1·G2 는 행 안의 내적 정합만 본다(두 값이 함께 틀리면 통과한다). 이 테스트는 기대값을
    구현 밖에서 만들어 그 구멍을 닫는다 — 행의 유효기간·코드의 유효기간까지 사본으로 다시 푼다.
    """
    rows = {r.row_id: r for r in _table(on_date)}
    expected_ids = {
        r.row_id for r in _ROWS if _copy_row_effective(r, on_date)
    }
    assert set(rows) == expected_ids, (
        f"{on_date} 표 행 집합 {sorted(rows)} vs 사본 기대 {sorted(expected_ids)}"
    )
    for row_id, row in rows.items():
        copy = _ROW_BY_ID[row_id]
        live = _copy_live_codes(copy, on_date)
        assert tuple(row.order_divisions) == live, (
            f"{on_date} {row_id}: order_divisions={tuple(row.order_divisions)} 사본 {live}"
        )
        assert row.market_order_ok is ("01" in live), (
            f"{on_date} {row_id}: market_order_ok={row.market_order_ok} 사본 코드 {live}"
        )
        assert row.can_order is bool(live), (
            f"{on_date} {row_id}: can_order={row.can_order} 사본 코드 {live}"
        )
        assert row.tone == _PHASE_TONE[copy.phase], (
            f"{on_date} {row_id}: tone={row.tone!r} 사본 phase {copy.phase}"
        )


def test_g6_cursor_tone_matches_phase():
    """G6 — 커서의 `tone` 도 값으로 잰다(F 섹션이 비워 둔 자리).

    행이 없는 순간(장 종료)의 톤까지 포함한다 — 그 자리가 `unknown` 이나 `active` 가 되면
    화면이 닫힌 장을 열린 것처럼 칠한다.
    """
    tones = _attr("TONES")
    seen: set = set()
    for on_date, market, t, st in _sweep():
        phase = _phase_name(st.phase)
        assert st.tone == _PHASE_TONE[phase], (
            f"{on_date} {market} {t}: tone={st.tone!r} phase={phase} "
            f"기대 {_PHASE_TONE[phase]!r}"
        )
        assert st.tone in tones
        seen.add(st.tone)
    assert {"closed", "active"} <= seen, (
        f"격자가 장 종료·정규장을 모두 밟지 않았다 — 관측된 톤 {sorted(seen)}"
    )
