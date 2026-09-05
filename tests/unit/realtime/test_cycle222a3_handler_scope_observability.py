"""cycle222-a3 — 적대적 검증 후속: F-A(창 상한) · F-C(강등 관측성) · F-E(잔여 사각).

## F-A — MAIN 창 상한이 NXT 애프터를 10분 통과시켰다

`_HGPR_HOUR_MAIN_END = 154000`(배타)은 `session._BOARD_SCHEDULE` 의 MAIN
구간(09:00~15:40)에서 온 값인데, **그 15:40 은 보드 전환 갭 마진이지 거래시간이
아니다**. KRX 정규장은 15:30 에 끝난다(`scheduler.TIME_KRX_MAIN_CLOSE`,
`sell_rejection.is_nxt_session_hours` 가 15:30~20:00 을 NXT 로 판정). 즉
15:30:00~15:39:59 에 **새 당일고가가 생기려면 NXT 애프터 체결뿐**인데 구 필터는
그걸 통과시켰다.

## F-C — 강등 경로에 로그가 0건이면 배포 후 실측이 불가능하다

`TICK_DAY_HIGH_ANCHOR` 롤백 스위치는 있는데 발화 여부를 볼 신호가 없었다.
`[day_high_scope_skip]`(1회/ticker/일 INFO)이 그 침묵을 깬다.

⚠️ 후속 (cycle222-a3 G-1) — 이 로그는 **틱 자신이 MAIN 시각일 때만** 남도록
   게이팅됐다. 게이트가 없으면 08:00~09:00 프리장의 **정상** 강등이 1회 cap 을
   먼저 태워 F-E 코호트를 셀 수 없다. 게이트 축 회귀는
   `test_cycle222a3g_handler_scope_gate.py` 가 담당한다 — 이 파일의 payload 는
   `[1] STCK_CNTG_HOUR` 가 MAIN(093015) 이라 기존 계약이 그대로 유효하다.

## F-E — 프리장 고가가 당일 최고면 그 종목은 **종일** 꺼진다

`[27]` 은 당일 최고가 시각 **하나**뿐이라, 프리장 고가 > MAIN 고가면 종일 창 밖에
머문다 → `day_high` 가 하루 종일 0. 갭업 코호트에서 기능이 통째로 무효화되지만
방향은 fail-closed 라 **조용하다**. 코드로는 못 고치므로(대안 판별자가 payload 에
없다) 문서화 + 위 로그로 **측정 가능하게** 만든다.
"""

from __future__ import annotations

import logging

import pytest
from freezegun import freeze_time

from src.realtime import handler

pytestmark = pytest.mark.unit

_LOGGER_NAME = "src.realtime.handler"


def _payload(*, ticker="000250", current="80000", open_="75800",
             high="86500", hgpr_hour="093015") -> str:
    """KIS 정본 `ccnl_total`(H0UNCNT0) 46 컬럼 중 이 파일이 쓰는 자리만 채운다."""
    f = ["0"] * 46
    f[0] = ticker
    f[1] = "093015"
    f[2] = current
    f[3] = "2"
    f[5] = "5.54"
    f[7] = open_
    f[8] = high
    f[9] = "75000"
    f[24] = "090000"
    f[27] = hgpr_hour
    f[33] = "20260821"
    return "^".join(f)


@pytest.fixture
def spy():
    """콜백을 갈아끼우고 모듈 전역 상태를 복원한다."""
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
# F-A — 상한은 KRX 정규장 종료(15:30, 포함)
# ===========================================================================

@pytest.mark.asyncio
@pytest.mark.parametrize(
    "hour, expected",
    [
        ("152959", 95_000),   # 정규장 마지막 1초
        ("153000", 95_000),   # 장마감 동시호가 체결 프린트 — **포함**
        ("153001", 0),        # NXT 애프터 시작
        ("153100", 0),        # ★ 적대적 검증 실증 케이스
        ("153959", 0),        # 구 상한이 통과시키던 마지막 1초
        ("154000", 0),
    ],
    ids=["1529", "1530_incl", "1530_01", "1531_probe", "1539", "1540"],
)
async def test_fa_nxt_after_hours_high_is_downgraded(spy, hour, expected):
    """15:30:01~ 의 당일고가는 NXT 애프터 체결이므로 KRX 앵커에 쓰면 안 된다."""
    await handler._handle_tick(_payload(hgpr_hour=hour, high="95000"))
    assert spy == [expected]


def test_fa_constants_pin_krx_regular_session():
    """상수 값이 KRX 정규장(09:00 / 15:30)과 정확히 일치한다."""
    assert handler._HGPR_HOUR_MAIN_START == 90000
    assert handler._HGPR_HOUR_MAIN_END == 153000


def test_fa_source_documents_divergence_from_board_schedule():
    """상한이 `_BOARD_SCHEDULE` MAIN(15:40)과 **의도적으로 다르다**는 근거가 남아야 한다."""
    import inspect

    src = inspect.getsource(handler)
    assert "_BOARD_SCHEDULE" in src, "출처/차이 근거 주석 부재"
    assert "15:30" in src, "KRX 정규장 종료 15:30 근거 부재"
    assert "의도적으로 다르다" in src, (
        "`_BOARD_SCHEDULE` MAIN 15:40 과의 의도적 불일치가 명시돼 있지 않다 — "
        "나중에 누가 '일관성' 을 이유로 되돌린다"
    )


# ===========================================================================
# F-C — `[day_high_scope_skip]` 1회/ticker/일
# ===========================================================================

@pytest.mark.asyncio
async def test_fc_scope_skip_emits_once_per_ticker_per_day(spy, caplog):
    caplog.set_level(logging.INFO, logger=_LOGGER_NAME)
    for _ in range(5):
        await handler._handle_tick(_payload(ticker="000250", hgpr_hour="083012"))
    await handler._handle_tick(_payload(ticker="005180", hgpr_hour="083012"))

    lines = _skip_lines(caplog)
    assert len(lines) == 2, f"1회/ticker/일 cap 위반: {lines}"
    assert any("ticker=000250" in ln for ln in lines)
    assert any("ticker=005180" in ln for ln in lines)


@pytest.mark.asyncio
async def test_fc_scope_skip_carries_hgpr_hour(spy, caplog):
    """강등 사유 판별에 필요한 최소 필드 — ticker / hgpr_hour."""
    caplog.set_level(logging.INFO, logger=_LOGGER_NAME)
    await handler._handle_tick(_payload(ticker="000250", hgpr_hour="163000"))
    (line,) = _skip_lines(caplog)
    assert "ticker=000250" in line
    assert "hgpr_hour=163000" in line


@pytest.mark.asyncio
async def test_fc_scope_skip_not_emitted_inside_window(spy, caplog):
    caplog.set_level(logging.INFO, logger=_LOGGER_NAME)
    await handler._handle_tick(_payload(hgpr_hour="093015"))
    assert spy == [86_500]
    assert _skip_lines(caplog) == []


@pytest.mark.asyncio
async def test_fc_scope_skip_cap_resets_on_kst_day_rollover(spy, caplog):
    """일일 리셋 — 정산 후(익일) 같은 종목이 다시 1회 emit 된다.

    `_silent_drop_count` 는 scheduler 의 5분 flush 에 의존하는 **윈도우 카운터**라
    일일 cap 의 리셋원으로 쓸 수 없다(5분 cap 이 되어 버린다). 그래서 여기는
    KST 일자 인덱스 자기 리셋이다 — 외부 훅 의존 0.
    """
    caplog.set_level(logging.INFO, logger=_LOGGER_NAME)
    with freeze_time("2026-08-21 05:00:00"):       # KST 14:00
        await handler._handle_tick(_payload(hgpr_hour="083012"))
        await handler._handle_tick(_payload(hgpr_hour="083012"))
    assert len(_skip_lines(caplog)) == 1

    with freeze_time("2026-08-22 05:00:00"):       # 익일 KST 14:00
        await handler._handle_tick(_payload(hgpr_hour="083012"))
    assert len(_skip_lines(caplog)) == 2, "일일 리셋이 없다 — 정산 후 cap 잔류"


@pytest.mark.asyncio
async def test_fc_kst_day_index_boundary_is_kst_midnight(spy):
    """일자 인덱스 경계는 **KST 자정** — UTC 자정이 아니다."""
    with freeze_time("2026-08-21 14:59:59"):       # KST 08-21 23:59:59
        a = handler._kst_day_index()
    with freeze_time("2026-08-21 15:00:00"):       # KST 08-22 00:00:00
        b = handler._kst_day_index()
    assert b == a + 1


@pytest.mark.asyncio
async def test_fc_scope_skip_never_drops_the_tick(spy, caplog):
    """관측 로그는 부가물 — 틱 처리·silent drop 계약을 바꾸지 않는다."""
    caplog.set_level(logging.INFO, logger=_LOGGER_NAME)
    await handler._handle_tick(_payload(ticker="000250", hgpr_hour="083012"))
    assert spy == [0], "틱이 drop 됐다"
    assert handler._silent_drop_count.get("000250") is None


@pytest.mark.asyncio
async def test_fc_logger_failure_does_not_break_the_tick(spy, monkeypatch):
    """로깅이 터져도 틱은 산다 (fail-open) — 손절 평가가 로그 때문에 멈추면 안 된다."""
    def _boom(*a, **kw):
        raise RuntimeError("logging backend down")

    monkeypatch.setattr(handler.logger, "info", _boom)
    await handler._handle_tick(_payload(hgpr_hour="083012"))
    assert spy == [0]


# ===========================================================================
# F-E — 프리장 고가가 당일 최고인 코호트는 종일 0
# ===========================================================================

@pytest.mark.asyncio
async def test_fe_premarket_high_of_day_keeps_day_high_zero_all_day(spy, caplog):
    """★ 잔여 사각 못박기 — `[27]` 이 종일 프리장 시각에 머무는 종목.

    프리장 고가(92,000)가 그날 MAIN 고가보다 높으면 `HGPR_HOUR` 는 09:00 이후
    어떤 틱에서도 갱신되지 않는다. 그 결과 이 종목의 `day_high` 는 **하루 종일 0**
    이고 앵커는 cycle222-a 이전(러닝 max)으로 되돌아간다. 방향은 fail-closed 지만
    갭업 코호트에서 기능이 통째로 무효화되므로, 여기서 계약으로 못박아 둔다.
    """
    caplog.set_level(logging.INFO, logger=_LOGGER_NAME)
    for hhmmss, cur in (("090100", "88000"), ("103000", "89000"),
                        ("133000", "90500"), ("152900", "91000")):
        await handler._handle_tick(
            _payload(ticker="000250", current=cur, high="92000",
                     hgpr_hour="083012"),   # 종일 프리장 시각에 고정
        )

    assert spy == [0, 0, 0, 0], (
        "프리장 고가가 당일 최고인 종목은 종일 0 이어야 한다 (F-E 잔여 사각). "
        "0 이 아니면 프리장 왜곡가가 앵커로 흐른다"
    )
    assert len(_skip_lines(caplog)) == 1, (
        "이 코호트를 세는 수단이 `[day_high_scope_skip]` 이다 — 1회/ticker/일"
    )


def test_fe_residual_blind_spot_is_documented():
    """코드가 이 사각을 **자백** 하고, 측정 수단(F-C 로그)과 연결돼 있어야 한다."""
    doc = handler._parse_day_high.__doc__ or ""
    assert "잔여 사각" in doc, "F-E 잔여 사각이 docstring 에 없다"
    assert "종일" in doc, "'종일 0' 이 되는 코호트 서술 부재"
    assert "day_high_scope_skip" in doc, (
        "측정 수단(`[day_high_scope_skip]` 로그) 연결이 없다 — "
        "사각을 적어만 두면 규모를 영원히 모른다"
    )
