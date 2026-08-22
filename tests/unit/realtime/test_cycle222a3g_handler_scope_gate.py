"""cycle222-a3 G-1 / G-3 / G-7 — 2차 적대적 검증 후속 (핸들러 축).

## G-1 — `[day_high_scope_skip]` 이 자기 목적을 달성 못 했다 (MEDIUM, 3렌즈 독립 발견)

이 로그의 **유일한 목적**은 F-E 잔여 사각(프리장/애프터 고가가 당일 최고여서
`day_high` 가 종일 0 인 코호트)의 규모 실측이다. 그런데 cap 이 `1회/ticker/일`
이라 **08:00~09:00 프리장의 정상 강등에서 먼저 소진**됐다. 프리장 체결이 있는
종목은 거의 전부 08:xx 에 1행을 남기므로 두 코호트가 구분되지 않았다:

    (a) 09:00 첫 틱만 강등, 이후 200틱 정상 → skip 1행, day_high>0 이 200/201
    (b) 종일 강등(F-E 코호트)             → skip 1행, day_high>0 이   0/201

게다가 로그 문구는 "종일 반복되면 F-E 사각" 이라 안내하는데 **cap 이 반복을
불가능하게 한다** — 안내대로 따라갈 수 있는 관측이 애초에 존재하지 않았다.

시정 = 강등 로그를 **틱 자신이 MAIN 시간대일 때만** 남긴다. 판별자는 같은
payload 의 `[1] STCK_CNTG_HOUR`(KIS 정본 `ccnl_total` 46컬럼 index 1).

## G-3 — F-A 주석이 KRX 랜덤엔드를 잘못 서술했다 (LOW)

"장마감 동시호가 체결이 15:30:00 에 프린트되므로" 는 **사실이 아니다** — KRX 는
시가·종가 단일가매매에 **30초 이내 임의 연장(랜덤엔드)** 을 적용한다.
상한 `153000` 은 **그대로 둔다**(15:30:01~15:30:30 을 열면 NXT 애프터가 같이
들어온다). 대신 잔여 손실 구간을 정직하게 못박는다.

## G-7 — 창은 **시각 필터이지 시장 필터가 아니다** (LOW, 문서화)

`[27]` 이 09:00~15:30 안이면 출처를 가리지 않는다 — NXT 주간 세션이 이 창과
겹치므로 NXT 주간 체결이 만든 고가는 그대로 통과한다. F-E 를 "명시적 문서화" 로
처리한 기준을 같은 축에 적용한다(코드 변경 없음).
"""

from __future__ import annotations

import logging

import pytest

from src.realtime import handler

pytestmark = pytest.mark.unit

_LOGGER_NAME = "src.realtime.handler"

# KIS 정본 `ccnl_total`(H0UNCNT0) 46 컬럼 — 이 파일이 쓰는 자리
#   [0] MKSC_SHRN_ISCD  [1] STCK_CNTG_HOUR  [2] STCK_PRPR ...
#   [7] STCK_OPRC       [8] STCK_HGPR       [9] STCK_LWPR
#   [24] OPRC_HOUR      [27] HGPR_HOUR      [33] BSOP_DATE
_IDX_CNTG_HOUR = 1
_IDX_HGPR_HOUR = 27


def _payload(*, ticker="000250", cntg_hour="093015", hgpr_hour="093015",
             current="80000", open_="75800", high="86500") -> str:
    f = ["0"] * 46
    f[0] = ticker
    f[_IDX_CNTG_HOUR] = cntg_hour
    f[2] = current
    f[3] = "2"
    f[5] = "5.54"
    f[7] = open_
    f[8] = high
    f[9] = "75000"
    f[24] = "090000"
    f[_IDX_HGPR_HOUR] = hgpr_hour
    f[33] = "20260821"
    return "^".join(f)


@pytest.fixture
def spy():
    seen: list[int] = []
    original = handler._on_tick

    async def _relay(ticker, current_price, open_price, change_rate, **kw):
        seen.append(int(kw.get("day_high", 0) or 0))

    handler.register_tick_handler(_relay)
    handler._silent_drop_count.clear()
    handler.reset_day_high_scope_skip()
    yield seen
    handler._on_tick = original
    handler._silent_drop_count.clear()
    handler.reset_day_high_scope_skip()


def _skip_lines(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records
            if "[day_high_scope_skip]" in r.getMessage()]


# ===========================================================================
# G-1 — 로그 게이트는 **틱 자신의 체결 시각**
# ===========================================================================

def test_g1_kis_canonical_index_of_cntg_hour_is_pinned():
    """`[1] STCK_CNTG_HOUR` — KIS 정본 `ccnl_total` 46 컬럼의 index 1.

    이 인덱스가 틀리면 G-1 게이트 전체가 무의미하다(엉뚱한 필드로 게이팅).
    핸들러 docstring 의 payload 매핑이 정본과 일치하는지 함께 못박는다.
    """
    doc = handler._handle_tick.__doc__ or ""
    assert "[1] 체결시간(STCK_CNTG_HOUR" in doc, (
        "payload 매핑 문서가 `[1] STCK_CNTG_HOUR` 를 잃었다 — 게이트 근거 소실"
    )
    assert "[27] 최고가시간(HGPR_HOUR)" in doc


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "cntg_hour, ids",
    [("080001", "pre_open"), ("083012", "pre_mid"), ("085959", "pre_last"),
     ("153001", "post_first"), ("161000", "post_mid"), ("195959", "post_last")],
)
async def test_g1_non_main_tick_does_not_log(spy, caplog, cntg_hour, ids):
    """프리장·애프터 틱의 **정상** 강등은 로그를 남기지 않는다 (cap 미소모)."""
    caplog.set_level(logging.INFO, logger=_LOGGER_NAME)
    await handler._handle_tick(
        _payload(cntg_hour=cntg_hour, hgpr_hour=cntg_hour),
    )
    assert spy == [0], "강등 자체는 그대로다 — 바뀐 것은 로그뿐"
    assert _skip_lines(caplog) == [], (
        "프리장/애프터 틱이 1회/ticker/일 cap 을 태웠다 — F-E 신호가 그만큼 가려진다"
    )


@pytest.mark.asyncio
async def test_g1_main_tick_with_out_of_window_high_logs(spy, caplog):
    """★ MAIN 체결 틱인데 당일고가 시각이 창 밖 = F-E 신호."""
    caplog.set_level(logging.INFO, logger=_LOGGER_NAME)
    await handler._handle_tick(
        _payload(ticker="000250", cntg_hour="093015", hgpr_hour="083012"),
    )
    (line,) = _skip_lines(caplog)
    assert "ticker=000250" in line
    assert "hgpr_hour=083012" in line
    assert "cntg_hour=093015" in line, (
        "체결 시각이 로그에 없다 — 사후에 두 코호트를 판별할 수 없다"
    )


@pytest.mark.asyncio
async def test_g1_premarket_ticks_do_not_burn_the_cap_for_the_main_signal(spy, caplog):
    """★ 결함의 핵심 재현 — 프리장 틱 다발 뒤에도 MAIN 신호가 **살아 있어야** 한다.

    구 구현: 08:xx 틱이 1회 cap 을 태워, 정작 09:xx 의 F-E 신호가 침묵했다.
    """
    caplog.set_level(logging.INFO, logger=_LOGGER_NAME)
    for _ in range(20):
        await handler._handle_tick(
            _payload(cntg_hour="083012", hgpr_hour="083012"),
        )
    assert _skip_lines(caplog) == []

    await handler._handle_tick(_payload(cntg_hour="093015", hgpr_hour="083012"))
    assert len(_skip_lines(caplog)) == 1, (
        "프리장 틱이 cap 을 태워 MAIN 신호가 사라졌다 — G-1 결함 재발"
    )


@pytest.mark.asyncio
async def test_g1_cap_is_still_once_per_ticker_per_day(spy, caplog):
    """cap 자체는 그대로 1회/ticker/일 (폭주 차단 목적 불변)."""
    caplog.set_level(logging.INFO, logger=_LOGGER_NAME)
    for _ in range(10):
        await handler._handle_tick(
            _payload(ticker="000250", cntg_hour="093015", hgpr_hour="083012"),
        )
    await handler._handle_tick(
        _payload(ticker="005180", cntg_hour="101500", hgpr_hour="083012"),
    )
    lines = _skip_lines(caplog)
    assert len(lines) == 2, f"1회/ticker/일 cap 위반: {lines}"


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", ["", "abc", "  "])
async def test_g1_unparsable_cntg_hour_does_not_log(spy, caplog, bad):
    """체결 시각을 못 읽으면 코호트 판정 불가 → cap 을 근거 없이 태우지 않는다."""
    caplog.set_level(logging.INFO, logger=_LOGGER_NAME)
    await handler._handle_tick(_payload(cntg_hour=bad, hgpr_hour="083012"))
    assert spy == [0], "체결 시각 파싱 실패가 틱을 죽이면 안 된다"
    assert _skip_lines(caplog) == []


@pytest.mark.asyncio
async def test_g1_log_wording_matches_the_new_contract(spy, caplog):
    """문구가 "종일 반복되면" 이 아니라 **행의 존재**를 말해야 한다.

    cap 이 반복을 불가능하게 하므로 구 문구는 따라갈 수 없는 안내였다.
    """
    caplog.set_level(logging.INFO, logger=_LOGGER_NAME)
    await handler._handle_tick(_payload(cntg_hour="093015", hgpr_hour="083012"))
    (line,) = _skip_lines(caplog)
    assert "종일 반복" not in line, "구 문구(따라갈 수 없는 안내) 잔존"
    assert "MAIN 체결" in line and "F-E" in line


def test_g1_docstrings_state_the_new_measurement_contract():
    """`_parse_day_high` 의 F-E 측정 수단 서술이 새 계약으로 정정돼야 한다."""
    doc = handler._parse_day_high.__doc__ or ""
    assert "측정 계약" in doc, "측정 계약 절 부재"
    assert "행의 존재" in doc, (
        "판정 단위가 '행의 존재' 로 서술돼 있지 않다"
    )
    helper_doc = handler._maybe_log_day_high_scope_skip.__doc__ or ""
    assert "STCK_CNTG_HOUR" in helper_doc, "게이트 판별자 근거 부재"
    assert "잔여 노이즈" in helper_doc, (
        "09:00 직후 전환 구간이 1행을 남길 수 있다는 잔여를 자백하지 않았다 — "
        "과대주장 금지"
    )


# ===========================================================================
# H-3 (cycle222-a) — 로그·문서가 **판별 불가능한 것을 단정**하지 않는다
# ===========================================================================
#
# 두 가지가 어긋나 있었다:
#   1. 이 로그는 `_parse_day_high` 에서 나오므로 **보유 여부와 무관하게 전 구독
#      종목**(슬롯 ≈287)에 찍힌다. 반면 문서화된 교차 판별자 `[day_high_adopted]`
#      는 `risk.on_tick` 의 `if pos and ...` 안이라 **보유 포지션에만** 존재한다.
#      → skip 행의 대다수는 교차 판별이 **구조적으로 불가능**한데 로그 본문은
#        "이 행의 존재 자체가 F-E 코호트라는 뜻" 이라고 단정했다.
#   2. 잔여 노이즈를 "09:00 직후 몇 초" 라고 적었으나 실제로는 **MAIN 고가가
#      프리장 고가를 넘을 때까지**이고, 갭다운 종목이면 수 시간~종일이다.
#
# 발화 조건·강등 행위는 **무변경**이다 — 문구와 문서만 정직화한다.

@pytest.mark.asyncio
async def test_h3_log_frames_the_cohort_as_a_candidate_not_a_verdict(spy, caplog):
    """★ 로그 본문이 F-E 를 **후보**로 말하고 교차 판별을 요구해야 한다."""
    caplog.set_level(logging.INFO, logger=_LOGGER_NAME)
    await handler._handle_tick(_payload(cntg_hour="093015", hgpr_hour="083012"))
    (line,) = _skip_lines(caplog)
    assert "후보" in line, (
        "F-E 를 '후보' 가 아니라 확정으로 말한다 — skip 행의 대다수는 미보유 "
        "종목이라 교차 판별 자체가 불가능하다"
    )
    assert "존재 자체가" not in line, "구 단정 문구 잔존"
    assert "day_high_adopted" in line, (
        "교차 판별자 이름이 없다 — 운영자가 확정 절차를 알 수 없다"
    )
    assert "보유 포지션에만" in line, (
        "판별자가 보유 종목에만 존재한다는 한계가 로그에 없다 — 미보유 종목의 "
        "skip 행을 F-E 로 오집계하게 된다"
    )


def test_h3_helper_docstring_states_all_three_limits():
    """헬퍼 docstring 이 노이즈 구간·판별자 범위·유보를 사실대로 적는다."""
    doc = handler._maybe_log_day_high_scope_skip.__doc__ or ""
    # 한계 1 — 노이즈 구간 서술 정정
    assert "MAIN 고가가 프리장 고가를 넘을 때까지" in doc, (
        "잔여 노이즈 구간이 사실대로(고가 역전까지) 서술되지 않았다"
    )
    assert "과소 서술" in doc, (
        "구 서술('09:00 직후 몇 초')이 왜 틀렸는지 정정 표기가 없다 — 표기가 "
        "없으면 다음 사람이 같은 과소 서술로 되돌린다"
    )
    assert "수 시간" in doc and "종일" in doc, (
        "갭다운 종목에서 이 구간이 수 시간~종일까지 늘어난다는 사실 부재"
    )
    # 한계 2 — 판별자 범위
    assert "보유 포지션에만" in doc, "교차 판별자의 보유 한정 서술 부재"
    assert "전 구독" in doc, (
        "이 로그가 전 구독 종목에 찍힌다는 비대칭 서술 부재 — 그게 없으면 "
        "'교차 판별하면 된다' 는 안내가 성립하는 것처럼 읽힌다"
    )
    # 한계 3 — 유보
    assert "범위 밖" in doc and "시그니처" in doc, (
        "보유 한정 정밀 측정이 `_on_tick` 시그니처 변경 대상이라 이번 범위 밖"
        "이라는 유보가 없다"
    )


def test_h3_parse_day_high_docstring_carries_the_same_correction():
    """`_parse_day_high` 의 F-E 측정 수단 서술도 같은 기준으로 정정됐다."""
    doc = handler._parse_day_high.__doc__ or ""
    assert "확정이 아니라 후보" in doc or "후보** 다" in doc or "후보**다" in doc, (
        "측정 계약이 여전히 '행의 존재 = 코호트 확정' 으로 읽힌다"
    )
    assert "보유 포지션에만" in doc, "판별자 보유 한정 한계 부재"
    assert "범위 밖" in doc, "보유 한정 정밀 측정 유보 부재"


@pytest.mark.asyncio
async def test_h3_emission_condition_and_downgrade_are_unchanged(spy, caplog):
    """★ 행위 무변경 — 발화 조건(MAIN 틱 게이트)·cap·강등이 그대로다."""
    caplog.set_level(logging.INFO, logger=_LOGGER_NAME)
    # 프리장 틱: 강등되지만 로그 없음
    await handler._handle_tick(_payload(cntg_hour="083012", hgpr_hour="083012"))
    assert _skip_lines(caplog) == []
    # MAIN 틱 + 창 밖 고가: 1행
    for _ in range(5):
        await handler._handle_tick(_payload(cntg_hour="093015", hgpr_hour="083012"))
    assert len(_skip_lines(caplog)) == 1
    # 창 안 고가: 정상 채택, 추가 로그 없음
    await handler._handle_tick(_payload(cntg_hour="093015", hgpr_hour="093015"))
    assert len(_skip_lines(caplog)) == 1
    assert spy == [0, 0, 0, 0, 0, 0, 86_500]


@pytest.mark.asyncio
async def test_g1_gate_never_changes_the_downgrade_itself(spy):
    """게이트는 **로그 축만** 바꾼다 — 강등/채택 행위는 byte 동일."""
    await handler._handle_tick(_payload(cntg_hour="083012", hgpr_hour="083012"))
    await handler._handle_tick(_payload(cntg_hour="093015", hgpr_hour="083012"))
    await handler._handle_tick(_payload(cntg_hour="093015", hgpr_hour="093015"))
    assert spy == [0, 0, 86_500]


# ===========================================================================
# G-3 — 랜덤엔드 잔여 사각
# ===========================================================================

@pytest.mark.asyncio
@pytest.mark.parametrize("hgpr_hour", ["153001", "153007", "153015", "153030"])
async def test_g3_random_end_close_high_is_downgraded(spy, hgpr_hour):
    """★ 잔여 사각 못박기 — 랜덤엔드(15:30:00~15:30:30) 종가 고가는 강등된다.

    KRX 는 시가·종가 단일가매매에 **30초 이내 임의 연장**을 적용하므로 종가 체결
    프린트는 15:30:00~15:30:30 범위에서 발생한다. 상한이 `153000` 포함이라
    15:30:01 이후 프린트는 NXT 애프터와 **구분되지 않아** 함께 버려진다.

    상한을 넓히지 않는 것이 계약이다 — 잘못 채택하면 없던 고점 기준 조기 청산
    (돌이킬 수 없는 실현손실)이고, 잘못 버리면 현상 유지다.
    """
    await handler._handle_tick(_payload(cntg_hour=hgpr_hour, hgpr_hour=hgpr_hour,
                                        high="95000"))
    assert spy == [0]


def test_g3_random_end_residual_is_documented_with_its_recovery_scope():
    """랜덤엔드 손실과 **회수 범위**가 코드에 남아야 한다 (주석의 거짓 단정 정정)."""
    import inspect

    src = inspect.getsource(handler)
    assert "랜덤엔드" in src, "랜덤엔드(임의 연장) 사실 서술 부재"
    assert "15:30:00~15:30:30" in src, "랜덤엔드 범위 부재"
    assert "_apply_high_since_buy_from_candles" in src, (
        "누락 회수 경로(익일 07:55 부팅 일봉 복구) 서술 부재 — "
        "손실 범위가 무한해 보이면 다음 사람이 상한을 넓힌다"
    )
    assert "매수 당일 봉은 배제" in src, (
        "회수 경로의 `buy_date < 영업일 < today` 양쪽 strict 한계가 없다 — "
        "매수 당일 종가 고가는 그 경로로도 복구되지 않는다"
    )


@pytest.mark.asyncio
async def test_g3_upper_bound_stays_inclusive_at_1530(spy):
    """상한은 **여전히** 15:30:00 포함 — 넓히지도 좁히지도 않았다."""
    assert handler._HGPR_HOUR_MAIN_END == 153000
    await handler._handle_tick(_payload(cntg_hour="153000", hgpr_hour="153000",
                                        high="95000"))
    assert spy == [95_000]


# ===========================================================================
# G-7 — 시각 필터 ≠ 시장 필터
# ===========================================================================

@pytest.mark.asyncio
async def test_g7_nxt_daytime_high_inside_the_window_passes_through(spy):
    """NXT 주간 세션 체결이 만든 고가는 창 안이면 그대로 통과한다 (계약 명시).

    실효 영향은 작다 — 차익거래로 가격대가 붙어 있고 그 역시 그 시각에 **실제로
    체결 가능했던** 가격이다. 통합 채널 payload 에 시장 구분 판별자도 없다.
    고치는 것이 아니라 **아는 것**이 계약이다.
    """
    await handler._handle_tick(_payload(cntg_hour="141500", hgpr_hour="141500",
                                        high="91000"))
    assert spy == [91_000]


def test_g7_market_vs_time_axis_is_documented():
    """F-E 를 문서화로 처리한 기준을 같은 축에 적용했는지 (비일관 차단)."""
    doc = handler._parse_day_high.__doc__ or ""
    assert "시각 필터이지 시장 필터가 아니다" in doc, (
        "이 창이 출처를 가리지 않는다는 축이 문서화되지 않았다"
    )
    assert "NXT 주간" in doc, "NXT 주간 세션 겹침 서술 부재"
