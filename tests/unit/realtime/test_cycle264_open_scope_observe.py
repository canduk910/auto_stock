"""cycle264 — `[open_scope_observe]` shadow 관측 (handler 축). **행위 변경 0.**

## 이 사이클이 재는 것

`H0UNCNT0` 통합 채널의 `[7] STCK_OPRC` 는 **09:00 에 리셋되지 않는다**(cycle222-a2
가 `[8] STCK_HGPR` 에서 같은 성질을 실측했다). 그래서 MAIN 구간 틱이 실어 오는
"시가" 가 08:00~09:00 NXT 프리장 기준가일 수 있고, 그 값이 VB/LTV 목표가의
기준가가 된다. 이 사이클은 **고치지 않는다** — `[24] OPRC_HOUR`(시가가 찍힌 시각)를
한 번도 관측한 적이 없기 때문이다(`grep fields\\[24\\]` = 0건). 하루치 코호트를
먼저 재고, 시정은 cycle265 다.

## 계약 (이 파일이 잠그는 것)

- **C4 행위 불변이 최우선이다.** `_parse_tick_prices` 는 byte 동일(소스 세그먼트
  sha 핀)이고, `_handle_tick` 이 `on_tick` 에 넘기는 6-튜플은 12 케이스 골든
  테이블로 변경 전후 동일해야 한다.
- **C1** `[open_scope_observe]` = INFO · 1회/ticker/일 · `KstDailyEmitCap`(cycle258)
  재사용 · 게이트는 `[1] STCK_CNTG_HOUR` 가 MAIN 창(090000~153000) 안일 때.
  라벨 `in_main_window` 는 **`[24]` 가 창 안인가**를 말한다(게이트 축과 다르다 —
  게이트는 분모를 만들고 라벨이 오염 비율을 만든다).
- **C1 정규화 금지** — `[24]` 부재는 `?`, 빈 문자열/비숫자는 **그대로** 기록한다.
  지금 우리는 그 필드가 무엇을 주는지 모른다. 정규화하면 그 미지가 지워진다.
- **C5** 모든 emit 은 예외를 완전 흡수한다. 여기서 예외가 새면 `_on_tick` 이
  re-raise 해 **WS 가 틱마다 재연결**하고(사이클 88 G-REJECT-1) 그게 곧 손절
  사각이다. 이 파일에서 가장 중요한 안전 가드다.
- **C6** 볼륨 = 구독 종목당 1행/일. "~290행/일" 은 **추정**(동시 구독 슬롯
  41×세션 기준)이지 실측이 아니다 — 운영 `[tick_coverage] subscribed=` 실측은
  09-03/09-04 기준 107~148 이고, `_scan_loop` 5분 delta 회전 때문에 하루 동안
  관측된 서로 다른 ticker 수는 슬롯 수보다 클 수도 있다. D+1 판독에서 실제
  행 수를 세고 그 수를 다음 사이클의 근거로 삼는다. 종목당 다중 로그 금지.

## 구현 계약 (Red 가 지정하는 이름)

- `handler._maybe_log_open_scope_observe(...)` — 관측 헬퍼(이름 고정: C5 격리
  테스트가 이 이름을 예외 주입점으로 쓴다).
- `handler._open_scope_observe_cap` — `KstDailyEmitCap` 인스턴스.
- `handler.reset_open_scope_observe()` — 테스트·운영 리셋 훅
  (`reset_day_high_scope_skip` 대칭).
"""

from __future__ import annotations

import ast
import asyncio
import hashlib
import logging
from pathlib import Path

import pytest
from freezegun import freeze_time

from src.realtime import handler

pytestmark = pytest.mark.unit

_LOGGER_NAME = "src.realtime.handler"
_MARKER = "[open_scope_observe] "

_HANDLER_PATH = Path(__file__).resolve().parents[3] / "src" / "realtime" / "handler.py"

# KIS 정본 `ccnl_total`(H0UNCNT0) 46 컬럼 0-index — 이 파일이 쓰는 자리
#   [0] MKSC_SHRN_ISCD   [1] STCK_CNTG_HOUR  [2] STCK_PRPR
#   [7] STCK_OPRC        [8] STCK_HGPR       [9] STCK_LWPR
#   [13] ACML_VOL        [24] OPRC_HOUR      [27] HGPR_HOUR
#   [34] NEW_MKOP_CLS_CODE                   [43] HOUR_CLS_CODE
_IDX_TICKER = 0
_IDX_CNTG_HOUR = 1
_IDX_PRPR = 2
_IDX_OPRC = 7
_IDX_HGPR = 8
_IDX_ACML_VOL = 13
_IDX_OPRC_HOUR = 24
_IDX_HGPR_HOUR = 27
_IDX_MKOP = 34
_IDX_HOUR_CLS = 43


def _payload(n: int = 46, **over: str) -> str:
    """`^` 구분 payload. `over` 는 ``_<index>=<값>`` 형태(예: ``_24="080005"``)."""
    f = ["0"] * n
    if n > _IDX_TICKER:
        f[_IDX_TICKER] = "000660"
    if n > _IDX_CNTG_HOUR:
        f[_IDX_CNTG_HOUR] = "093015"
    if n > _IDX_PRPR:
        f[_IDX_PRPR] = "80000"
    if n > _IDX_OPRC:
        f[_IDX_OPRC] = "75800"
    if n > _IDX_HGPR:
        f[_IDX_HGPR] = "86500"
    if n > 9:
        f[9] = "75000"
    if n > _IDX_ACML_VOL:
        f[_IDX_ACML_VOL] = "1234567"
    if n > _IDX_OPRC_HOUR:
        f[_IDX_OPRC_HOUR] = "090001"
    if n > _IDX_HGPR_HOUR:
        f[_IDX_HGPR_HOUR] = "093015"
    if n > _IDX_MKOP:
        f[_IDX_MKOP] = "1"
    if n > _IDX_HOUR_CLS:
        f[_IDX_HOUR_CLS] = "0"
    for key, value in over.items():
        f[int(key[1:])] = value
    return "^".join(f)


@pytest.fixture
def tick_spy(monkeypatch):
    """`_on_tick` 스파이 + 모든 일일 cap 초기화."""
    seen: list[tuple] = []

    async def _relay(ticker, current_price, open_price, change_rate, **kw):
        seen.append((
            ticker, current_price, open_price, change_rate,
            kw.get("day_high"), kw.get("acml_vol"),
        ))

    original = handler._on_tick
    handler.register_tick_handler(_relay)
    handler._silent_drop_count.clear()
    handler.reset_day_high_scope_skip()
    _reset_observe_cap()
    yield seen
    handler._on_tick = original
    handler._silent_drop_count.clear()
    handler.reset_day_high_scope_skip()
    _reset_observe_cap()


def _reset_observe_cap() -> None:
    """cycle264 관측 cap 초기화 — 훅이 아직 없으면(Red) 조용히 통과."""
    fn = getattr(handler, "reset_open_scope_observe", None)
    if callable(fn):
        fn()


def _lines(caplog) -> list[str]:
    """로거명 + INFO 이상 + prefix 3중 한정 (CI 루트 로거 DEBUG 내성)."""
    return [
        r.getMessage()
        for r in caplog.records
        if r.name == _LOGGER_NAME
        and r.levelno >= logging.INFO
        and r.getMessage().startswith(_MARKER)
    ]


def _field(line: str, key: str) -> str:
    """``key=value`` 를 공백 경계로 추출 (빈 값도 그대로 돌려준다)."""
    token = f"{key}="
    idx = line.index(f" {token}") + 1 if f" {token}" in line else line.index(token)
    rest = line[idx + len(token):]
    return rest.split(" ")[0]


# ===========================================================================
# C4 — 행위 불변 (이 사이클의 제1 계약)
# ===========================================================================

# `_parse_tick_prices` 소스 세그먼트 sha256 (2026-09-06 HEAD).
# ⚠️ `ast.dump` 가 아니라 `ast.get_source_segment` 의 sha 다 — `ast.dump` 는
#    파이썬 3.12(CI) / 3.13(로컬) 출력이 달라 로컬 초록·CI 붉음을 만든다
#    (cycle256 G-250-5 · cycle259 S4a 실측).
# ⚠️ **cycle264 에서 이 값이 바뀌면 계약 위반이다.** 갱신은 team-leader 승인 사항.
_PARSE_TICK_PRICES_SHA256 = (
    "769ce96b4b64bb7316f5438bbc46821fae457bbb905ed2ef18c47aa292a659b8"
)


def _fn_segment(name: str) -> str:
    src = _HANDLER_PATH.read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return ast.get_source_segment(src, node) or ""
    raise AssertionError(f"handler.py 에 함수 {name} 가 없다")


def test_c4_parse_tick_prices_source_pinned():
    """C4 — `_parse_tick_prices` 는 **byte 동일**이다. 마커는 이 함수 밖에 둔다."""
    actual = hashlib.sha256(_fn_segment("_parse_tick_prices").encode("utf-8")).hexdigest()
    assert actual == _PARSE_TICK_PRICES_SHA256, (
        "`_parse_tick_prices` 소스가 cycle264 승인 형상과 다르다 — 이 사이클의 제1 "
        "계약은 '매매 행위를 한 글자도 바꾸지 않는다' 이고 이 함수가 그 경계다. "
        f"관측 마커는 `_handle_tick` 안(parsed 성공 뒤)에 둬라. 실측 sha={actual}"
    )


# `_handle_tick` → `on_tick(ticker, current, open, change_rate, day_high=, acml_vol=)`
# 골든 테이블 — 2026-09-06 HEAD 실측. change_rate 는 계약식으로 재계산해 비교한다.
_GOLDEN_CASES: dict[str, tuple[str, tuple | None]] = {
    # name: (payload, expected (ticker, current, open, day_high, acml_vol) | None=드롭)
    "main_full":    (_payload(),                                   ("000660", 80000, 75800, 86500, 1234567)),
    "pre_tick":     (_payload(_1="083000", _24="080005", _27="083000"), ("000660", 80000, 75800, 0, 1234567)),
    "post_tick":    (_payload(_1="160000", _24="080005", _27="160000"), ("000660", 80000, 75800, 0, 1234567)),
    "oprc_empty":   (_payload(_24=""),                             ("000660", 80000, 75800, 86500, 1234567)),
    "oprc_nonnum":  (_payload(_24="N/A"),                          ("000660", 80000, 75800, 86500, 1234567)),
    "short26":      (_payload(26),                                 ("000660", 80000, 75800, 0, 1234567)),
    "short10":      (_payload(10),                                 ("000660", 80000, 75800, 0, -1)),
    "bad_price":    (_payload(_2="abc"),                           None),
    "zero_open":    (_payload(_7="0"),                             ("000660", 80000, 0, 86500, 1234567)),
    "short9":       (_payload(9),                                  None),
    "neg_vol":      (_payload(_13="-5"),                           ("000660", 80000, 75800, 86500, -1)),
    "hgpr_out":     (_payload(_27="083000"),                       ("000660", 80000, 75800, 0, 1234567)),
}


@pytest.mark.asyncio
@pytest.mark.parametrize("case", sorted(_GOLDEN_CASES))
async def test_c4_handle_tick_dispatch_args_unchanged(case, tick_spy):
    """C4 — `_handle_tick` 이 `on_tick` 에 넘기는 인자가 cycle264 전후 동일하다.

    관측 마커는 이 6-튜플에 **어떤 영향도 주면 안 된다** — 시세/시가/등락률/
    day_high/acml_vol 은 매수·매도·목표가·수량 산출의 유일한 입력이다.
    """
    payload, expected = _GOLDEN_CASES[case]
    await handler._handle_tick(payload)

    if expected is None:
        assert tick_spy == [], (
            f"{case}: 기존 silent-drop 계약이 깨졌다 — 관측 마커가 드롭 경로를 "
            f"바꿨는지 확인하라. 실측={tick_spy!r}"
        )
        return

    ticker, current, open_, day_high, acml_vol = expected
    change_rate = (current - open_) / open_ * 100 if open_ > 0 else 0.0
    assert tick_spy == [(ticker, current, open_, change_rate, day_high, acml_vol)], (
        f"{case}: on_tick 인자가 골든과 다르다 (기대="
        f"{(ticker, current, open_, change_rate, day_high, acml_vol)!r}, "
        f"실측={tick_spy!r})"
    )


# ===========================================================================
# C1 — `[open_scope_observe]` 발화 계약
# ===========================================================================

@pytest.mark.asyncio
async def test_c1_main_tick_emits_one_line_with_all_fields(tick_spy, caplog):
    """C1 — MAIN 창 틱 1개 → 정확히 1행 + 8필드 전부."""
    caplog.set_level(logging.INFO, logger=_LOGGER_NAME)
    await handler._handle_tick(_payload())

    lines = _lines(caplog)
    assert len(lines) == 1, f"MAIN 틱 1개 → 1행이어야 한다. 실측={lines!r}"
    line = lines[0]
    assert _field(line, "ticker") == "000660"
    assert _field(line, "oprc_hour") == "090001"
    assert _field(line, "tick_open") == "75800"
    assert _field(line, "cntg_hour") == "093015"
    assert _field(line, "hgpr_hour") == "093015"
    assert _field(line, "mkop") == "1"
    assert _field(line, "hour_cls") == "0"
    assert _field(line, "in_main_window") == "true"


@pytest.mark.asyncio
async def test_c1_gate_pre_market_tick_does_not_consume_cap(tick_spy, caplog):
    """C1 게이트 — `[1]` 이 창 밖이면 **cap 을 태우지 않는다**.

    `[day_high_scope_skip]` G-1 과 동일 설계. 프리장 틱이 1회 cap 을 먹으면
    코호트 분모(= MAIN 중 관측된 종목 수)가 통째로 죽는다.
    """
    caplog.set_level(logging.INFO, logger=_LOGGER_NAME)

    # 08:30 프리장 틱 3개 — 한 행도 남기지 않는다
    for _ in range(3):
        await handler._handle_tick(_payload(_1="083000", _24="080005"))
    assert _lines(caplog) == [], "프리장 틱은 관측 대상이 아니다 (분모 오염)"

    # 같은 종목이 09:30 MAIN 틱을 받으면 그때 1행
    await handler._handle_tick(_payload(_1="093015", _24="080005"))
    lines = _lines(caplog)
    assert len(lines) == 1, (
        f"프리장에서 cap 이 소진돼 MAIN 틱이 침묵했다. 실측={lines!r}"
    )
    assert _field(lines[0], "in_main_window") == "false", (
        "`[24]`=080005 는 MAIN 창 밖 = 오염 코호트"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("cntg_hour", ["075959", "083000", "085959", "153001", "160000", "195959"])
async def test_c1_gate_out_of_window_cntg_hour_silent(cntg_hour, tick_spy, caplog):
    """C1 게이트 — 창 밖(하한 미만·상한 초과) 체결시각은 전부 무발화."""
    caplog.set_level(logging.INFO, logger=_LOGGER_NAME)
    await handler._handle_tick(_payload(_1=cntg_hour))
    assert _lines(caplog) == [], f"cntg_hour={cntg_hour} 는 창 밖 = 무발화"


@pytest.mark.asyncio
@pytest.mark.parametrize("cntg_hour", ["090000", "093015", "153000"])
async def test_c1_gate_in_window_boundaries_emit(cntg_hour, tick_spy, caplog):
    """C1 게이트 — 창 경계(09:00:00 포함 ~ 15:30:00 포함)는 발화한다."""
    caplog.set_level(logging.INFO, logger=_LOGGER_NAME)
    await handler._handle_tick(_payload(_1=cntg_hour))
    assert len(_lines(caplog)) == 1, f"cntg_hour={cntg_hour} 는 창 안 = 1행"


@pytest.mark.asyncio
async def test_c1_gate_unparsable_cntg_hour_does_not_consume_cap(tick_spy, caplog):
    """C1 게이트 — `[1]` 파싱 실패는 미발화 + cap 미소모(`_maybe_log_day_high_scope_skip` 동형)."""
    caplog.set_level(logging.INFO, logger=_LOGGER_NAME)
    await handler._handle_tick(_payload(_1=""))
    await handler._handle_tick(_payload(_1="??????"))
    assert _lines(caplog) == [], "체결시각을 못 읽으면 코호트 판정이 불가능하다 = 무발화"

    await handler._handle_tick(_payload(_1="093015"))
    assert len(_lines(caplog)) == 1, "파싱 실패가 cap 을 태워 MAIN 틱을 삼켰다"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "oprc_hour,expected_label",
    [
        ("090000", "true"),
        ("093015", "true"),
        ("153000", "true"),
        ("080005", "false"),   # NXT 프리장 = 오염 코호트
        ("085959", "false"),
        ("153001", "false"),
        ("", "false"),         # 파싱 불가 → 창 안이라 단정할 수 없다
        ("N/A", "false"),
    ],
)
async def test_c1_in_main_window_labels_oprc_hour(oprc_hour, expected_label, tick_spy, caplog):
    """C1 — `in_main_window` 는 **`[24]` 축**이다(게이트는 `[1]` 축).

    두 축이 같으면 분모만 있고 분자가 없다 — 오염 **비율**을 못 잰다.
    """
    caplog.set_level(logging.INFO, logger=_LOGGER_NAME)
    await handler._handle_tick(_payload(_24=oprc_hour))
    lines = _lines(caplog)
    assert len(lines) == 1
    assert _field(lines[0], "in_main_window") == expected_label, (
        f"oprc_hour={oprc_hour!r} → in_main_window={expected_label} 이어야 한다: {lines[0]!r}"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("raw", ["", "N/A", "  ", "0", "80005", "0800050"])
async def test_c1_oprc_hour_recorded_verbatim_no_normalization(raw, tick_spy, caplog):
    """C1 — `[24]` 는 **정규화 금지**. 파싱 실패·비숫자·빈 문자열도 그대로 남긴다.

    지금 우리는 이 필드가 무엇을 주는지 **모른다**(`grep fields[24]` = 0건).
    정규화(0 치환·zero-pad·trim)는 그 미지를 지워 이 사이클의 목적 자체를 없앤다.
    """
    caplog.set_level(logging.INFO, logger=_LOGGER_NAME)
    await handler._handle_tick(_payload(_24=raw))
    lines = _lines(caplog)
    assert len(lines) == 1
    # 공백 토큰은 `_field` 로 못 뽑으므로 원문 포함 여부로 검증
    assert f"oprc_hour={raw}" in lines[0], (
        f"`[24]` 원문 {raw!r} 이 그대로 기록되지 않았다: {lines[0]!r}"
    )


@pytest.mark.asyncio
async def test_c1_absent_optional_fields_marked_question(tick_spy, caplog):
    """C1 — `[24]`/`[27]`/`[34]`/`[43]` 부재(짧은 payload)는 `?` 로 남기고 발화한다.

    `len(fields) < 10` 만 통과하면 관측은 성립한다 — 부재 자체가 데이터다.
    """
    caplog.set_level(logging.INFO, logger=_LOGGER_NAME)
    await handler._handle_tick(_payload(11))
    lines = _lines(caplog)
    assert len(lines) == 1, f"짧은 payload 도 관측 대상이다. 실측={lines!r}"
    line = lines[0]
    assert _field(line, "oprc_hour") == "?"
    assert _field(line, "hgpr_hour") == "?"
    assert _field(line, "mkop") == "?"
    assert _field(line, "hour_cls") == "?"
    assert _field(line, "in_main_window") == "false"
    assert _field(line, "tick_open") == "75800"


@pytest.mark.asyncio
async def test_c1_tick_open_is_parsed_field7(tick_spy, caplog):
    """C1 — `tick_open` 은 `[7]` 파싱값(= 목표가 기준가가 되는 바로 그 수)이다."""
    caplog.set_level(logging.INFO, logger=_LOGGER_NAME)
    await handler._handle_tick(_payload(_7="111600"))
    lines = _lines(caplog)
    assert len(lines) == 1
    assert _field(lines[0], "tick_open") == "111600"


@pytest.mark.asyncio
async def test_c1_tick_open_is_the_parsed_value_not_a_reparse_of_field7(tick_spy, caplog, monkeypatch):
    """C1 — `tick_open` 은 `_parse_tick_prices` **가 돌려준 값**이다(`[7]` 재파싱 아님).

    ⚠️ 이 가드가 없으면 뮤턴트 `open_price → int(fields[7] or 0)` 이 **전부 통과**한다
    (적대 검증 M08 ESCAPED). 지금 호출 경로에서는 두 수가 같아 무해하지만,
    **cycle265 가 정확히 그 등가를 깨는 사이클**이다 — `[24] OPRC_HOUR` 스코프
    필터를 `_parse_tick_prices` 에 넣는 순간 `open_price`(필터 후) ≠ `int(fields[7])`
    (필터 전)이 되고, 마커는 조용히 '필터 전 값' 을 계속 재게 된다. 월요일 판독을
    위해 만든 계기가 다음 사이클에 소리 없이 **다른 것을 재기 시작**한다는 뜻이다.

    📌 cycle265 인계 — 이 테스트가 붉어졌다면 스코프 필터가 마커까지 흘렀다는
    뜻이다. 그때는 `tick_open` 을 바꾸지 말고 `tick_open_raw`(필터 전)를 **추가**해
    필터 전/후를 같이 남겨라. 한쪽만 남기면 시정의 효과를 사후 검증할 수 없다.
    """
    caplog.set_level(logging.INFO, logger=_LOGGER_NAME)
    # `[7]` 원문(75800)과 **다른** 값을 파서가 돌려주게 한다
    monkeypatch.setattr(handler, "_parse_tick_prices", lambda _f: (80000, 424242))
    await handler._handle_tick(_payload())

    lines = _lines(caplog)
    assert len(lines) == 1
    assert _field(lines[0], "tick_open") == "424242", (
        "마커가 `_parse_tick_prices` 결과가 아니라 `[7]` 을 다시 파싱했다 — 이 관측은 "
        "'목표가가 실제로 쓴 값' 을 재야 한다. 두 수가 갈라지는 순간(cycle265) "
        f"관측의 의미가 통째로 바뀐다: {lines[0]!r}"
    )
    assert tick_spy == [("000660", 80000, 424242, (80000 - 424242) / 424242 * 100, 86500, 1234567)], (
        f"전제 재현 실패 — 파서 스텁이 실제로 쓰이지 않았다: {tick_spy!r}"
    )


@pytest.mark.asyncio
async def test_c1_no_emit_when_price_parse_fails(tick_spy, caplog):
    """C1 배치 — `parsed` 실패(=silent drop) 경로에서는 발화하지 않는다.

    마커는 `_handle_tick` 안 **`parsed` 성공 뒤**가 계약이다. 드롭 경로에서
    발화하면 cap 을 태워 그 종목의 진짜 MAIN 관측이 사라진다.
    """
    caplog.set_level(logging.INFO, logger=_LOGGER_NAME)
    await handler._handle_tick(_payload(_2="abc"))
    assert _lines(caplog) == []
    assert tick_spy == []

    await handler._handle_tick(_payload())
    assert len(_lines(caplog)) == 1, "드롭 경로가 cap 을 태웠다"


@pytest.mark.asyncio
async def test_c1_no_emit_when_payload_too_short(tick_spy, caplog):
    """C1 배치 — `len(fields) < 10` 드롭 경로 무발화 (기존 계약 보존)."""
    caplog.set_level(logging.INFO, logger=_LOGGER_NAME)
    await handler._handle_tick(_payload(9))
    assert _lines(caplog) == []
    assert handler._silent_drop_count.get("000660") == 1


# ===========================================================================
# C6 — 볼륨 상한 (1회/ticker/일)
# ===========================================================================

@pytest.mark.asyncio
async def test_c6_hundred_ticks_same_ticker_emit_once(tick_spy, caplog):
    """C6 — 같은 ticker 100틱 → **1행**. 종목당 다중 로그는 절대 금지."""
    caplog.set_level(logging.INFO, logger=_LOGGER_NAME)
    for _ in range(100):
        await handler._handle_tick(_payload())
    lines = _lines(caplog)
    assert len(lines) == 1, (
        f"1회/ticker/일 cap 이 없다 — 운영 `system_logs` 8,238~8,542행/일에 "
        f"틱마다 1행이 얹힌다. 실측 {len(lines)}행"
    )
    assert len(tick_spy) == 100, "관측 cap 이 틱 디스패치를 막으면 안 된다"


@pytest.mark.asyncio
async def test_c6_distinct_tickers_get_own_line(tick_spy, caplog):
    """C6 — cap 은 ticker 단위다(전역 1회가 아니다)."""
    caplog.set_level(logging.INFO, logger=_LOGGER_NAME)
    for t in ("000660", "005930", "000720"):
        for _ in range(5):
            await handler._handle_tick(_payload(_0=t))
    lines = _lines(caplog)
    assert len(lines) == 3, f"종목 3개 → 3행이어야 한다. 실측={lines!r}"
    assert {_field(l, "ticker") for l in lines} == {"000660", "005930", "000720"}


@pytest.mark.asyncio
async def test_c6_cap_resets_across_kst_day(tick_spy, caplog):
    """C6 — cap 은 KST 일자 경계에서 자기 리셋된다(`KstDailyEmitCap`)."""
    caplog.set_level(logging.INFO, logger=_LOGGER_NAME)
    with freeze_time("2026-09-07 09:30:15+09:00"):
        await handler._handle_tick(_payload())
        await handler._handle_tick(_payload())
    assert len(_lines(caplog)) == 1

    with freeze_time("2026-09-08 09:30:15+09:00"):
        await handler._handle_tick(_payload())
    assert len(_lines(caplog)) == 2, "익일에는 다시 1행이 남아야 한다"


@pytest.mark.asyncio
async def test_c6_reset_hook_clears_cap(tick_spy, caplog):
    """C6 — `reset_open_scope_observe()` 훅 존재 + 동작(테스트·운영 리셋 대칭)."""
    caplog.set_level(logging.INFO, logger=_LOGGER_NAME)
    assert callable(getattr(handler, "reset_open_scope_observe", None)), (
        "`reset_day_high_scope_skip` 대칭 훅 `reset_open_scope_observe` 가 필요하다"
    )
    await handler._handle_tick(_payload())
    handler.reset_open_scope_observe()
    await handler._handle_tick(_payload())
    assert len(_lines(caplog)) == 2


def test_c6_cap_is_kst_daily_emit_cap():
    """C6 — cap 은 cycle258 `KstDailyEmitCap` 재사용이다(새 날짜 로직 금지)."""
    from src.engine.daily_emit_cap import KstDailyEmitCap

    cap = getattr(handler, "_open_scope_observe_cap", None)
    assert isinstance(cap, KstDailyEmitCap), (
        "cycle258 이 날짜 키 자기 리셋을 표준화했다 — 새 리셋 로직을 손으로 "
        f"다시 쓰지 마라. 실측={type(cap)!r}"
    )


# ===========================================================================
# C5 — 관측 실패 격리 (**가장 중요한 안전 가드**)
# ===========================================================================
#
# 이 경로에서 예외가 새면 `_handle_tick` 의 `_on_tick` 예외 핸들러가 아니라
# **함수 본문**에서 터진다 → `dispatch_message` → `websocket._on_message` 로
# 전파 → 재연결. 틱마다 재연결하면 시세가 통째로 끊기고 그동안 손절 평가가
# 멈춘다(사이클 88 G-REJECT-1).

class _BoomLogger:
    """모든 로깅 호출이 터지는 로거."""

    def __getattr__(self, _name):
        def _boom(*_a, **_kw):
            raise RuntimeError("logger boom")
        return _boom


class _BoomCap:
    def should_emit(self, *_a, **_kw):
        raise RuntimeError("cap boom")

    def mark_emitted(self, *_a, **_kw):
        raise RuntimeError("cap boom")

    def emit_once(self, *_a, **_kw):
        raise RuntimeError("cap boom")


@pytest.mark.asyncio
async def test_c5_logger_explosion_does_not_break_tick(tick_spy, monkeypatch):
    """C5 — 로거가 통째로 터져도 `_handle_tick` 은 예외를 밖으로 내보내지 않는다."""
    monkeypatch.setattr(handler, "logger", _BoomLogger())
    await handler._handle_tick(_payload())
    assert len(tick_spy) == 1, (
        "관측 로그 실패가 틱 디스패치를 삼켰다 — 손절 평가가 멈춘다"
    )


@pytest.mark.asyncio
async def test_c5_cap_explosion_does_not_break_tick(tick_spy, monkeypatch):
    """C5 — cap 이 터져도 틱은 정상 전달된다."""
    assert hasattr(handler, "_open_scope_observe_cap"), "cap 인스턴스 이름 계약"
    monkeypatch.setattr(handler, "_open_scope_observe_cap", _BoomCap())
    await handler._handle_tick(_payload())
    assert len(tick_spy) == 1


@pytest.mark.asyncio
async def test_c5_observer_helper_explosion_does_not_break_tick(tick_spy, monkeypatch):
    """C5 — 관측 헬퍼 자체가 터져도 `_handle_tick` 은 조용히 통과한다.

    (헬퍼 이름 `_maybe_log_open_scope_observe` 를 함께 못박는다 —
     `_maybe_log_day_high_scope_skip` 대칭.)
    """
    assert callable(getattr(handler, "_maybe_log_open_scope_observe", None)), (
        "관측 헬퍼 이름 계약: `_maybe_log_open_scope_observe`"
    )

    def _boom(*_a, **_kw):
        raise RuntimeError("observer boom")

    monkeypatch.setattr(handler, "_maybe_log_open_scope_observe", _boom)
    await handler._handle_tick(_payload())
    assert len(tick_spy) == 1


def test_c5_observer_helper_signature():
    """C5/C1 — 헬퍼 시그니처 계약: ``(fields: list[str], open_price: int) -> None``.

    `open_price` 는 `_parse_tick_prices` 가 이미 만든 값을 **그대로 받는다**
    (헬퍼가 `[7]` 을 다시 파싱하면 두 수가 갈라질 수 있고, 그 순간 이 관측은
    "목표가가 실제로 쓴 값" 을 재는 것이 아니게 된다).
    """
    import inspect

    fn = getattr(handler, "_maybe_log_open_scope_observe", None)
    assert callable(fn), "관측 헬퍼 `_maybe_log_open_scope_observe` 미구현"
    params = list(inspect.signature(fn).parameters)
    assert params[:2] == ["fields", "open_price"], (
        f"헬퍼 시그니처는 (fields, open_price) 다. 실측={params!r}"
    )


@pytest.mark.asyncio
async def test_c5_observer_helper_never_raises_directly(monkeypatch):
    """C5 — 헬퍼를 **직접** 불러도 절대 던지지 않는다(2차 예외까지 흡수)."""
    fn = getattr(handler, "_maybe_log_open_scope_observe", None)
    assert callable(fn), "관측 헬퍼 미구현"
    monkeypatch.setattr(handler, "logger", _BoomLogger())
    monkeypatch.setattr(handler, "_open_scope_observe_cap", _BoomCap())
    # 어떤 인자 조합에서도 예외가 새면 안 된다
    fn(None, 0)                        # type: ignore[arg-type]
    fn(["000660"], 0)                  # 짧은 fields
    fn(_payload().split("^"), 75800)


@pytest.mark.asyncio
async def test_c5_on_tick_exception_still_reraises(tick_spy, monkeypatch, caplog):
    """C5 회귀 — `_on_tick` 예외의 **re-raise 는 그대로 살아 있어야 한다**.

    사이클 88 G-REJECT-1: 콜백 실패는 재연결 trigger 다. 관측 마커를 넣다가
    이 경로를 try/except 로 덮으면 진짜 결함이 조용히 묻힌다.
    """
    async def _boom(*_a, **_kw):
        raise RuntimeError("callback boom")

    monkeypatch.setattr(handler, "_on_tick", _boom)
    with pytest.raises(RuntimeError, match="callback boom"):
        await handler._handle_tick(_payload())


# ===========================================================================
# C7 — 접촉 범위 (handler 축): 마커는 파싱 함수 밖
# ===========================================================================

def test_c7_observer_not_called_from_parse_functions():
    """C7 — 관측 헬퍼는 `_parse_tick_prices`/`_parse_day_high`/`_parse_acml_vol`
    안에서 호출되지 않는다(파싱 함수 byte 동일 계약의 AST 축)."""
    src = _HANDLER_PATH.read_text(encoding="utf-8")
    tree = ast.parse(src)
    for name in ("_parse_tick_prices", "_parse_day_high", "_parse_acml_vol"):
        node = next(
            n for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name
        )
        called = {
            c.func.id for c in ast.walk(node)
            if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)
        }
        assert "_maybe_log_open_scope_observe" not in called, (
            f"{name} 안에서 cycle264 관측 헬퍼를 호출했다 — 배치는 `_handle_tick` "
            "안(parsed 성공 뒤)이 계약이다"
        )


def test_c7_cap_peek_precedes_field_reads():
    """C7 hot path — cap 확인이 필드 읽기·인자 구성 **앞**이다(자매 함수와 동형).

    `_maybe_log_day_high_scope_skip` 은 창 게이트 직후 cap 을 먼저 보고 그 다음
    로그 인자를 만든다. 종목당 1행/일 계약이라 **그날 첫 틱 이후의 모든 MAIN 틱**
    (구독 100~150종목 × 종일)이 이 자리를 지나므로, 순서가 뒤집히면 반드시 버려질
    `_tick_field_raw` 4회 + `int()` + 8원소 인자 구성을 매 틱 지불한다. 이 경로는
    `_handle_tick` → `risk.on_tick`(손절 평가) 직전이라 지연을 얹기 가장 나쁜 자리다.

    ⚠️ 순수 낭비라 출력 뮤테이션으로는 잡히지 않는다(행위 등가) — 구조로 잠근다.
    """
    src = _HANDLER_PATH.read_text(encoding="utf-8")
    tree = ast.parse(src)
    node = next(
        n for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        and n.name == "_maybe_log_open_scope_observe"
    )
    peek = [
        c.lineno for c in ast.walk(node)
        if isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute)
        and c.func.attr == "should_emit"
    ]
    reads = [
        c.lineno for c in ast.walk(node)
        if isinstance(c, ast.Call) and isinstance(c.func, ast.Name)
        and c.func.id == "_tick_field_raw"
    ]
    assert peek, "cap `should_emit` 선확인이 없다 — 버려질 인자 구성을 매 틱 지불한다"
    assert reads, "필드 읽기(`_tick_field_raw`)를 찾지 못했다(수집기 고장)"
    assert min(peek) < min(reads), (
        f"cap 확인(line {min(peek)})이 필드 읽기(line {min(reads)}) 뒤에 있다 — "
        "창 게이트 → cap → 인자 순서가 계약이다"
    )


def test_c7_observer_helper_is_hot_path_pure():
    """C7 — 관측 헬퍼는 hot path 다: `await`/`write_log`/DB 금지 (AST A-1 동형)."""
    src = _HANDLER_PATH.read_text(encoding="utf-8")
    tree = ast.parse(src)
    node = next(
        (n for n in ast.walk(tree)
         if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
         and n.name == "_maybe_log_open_scope_observe"),
        None,
    )
    assert node is not None, "관측 헬퍼 `_maybe_log_open_scope_observe` 미구현"
    assert not isinstance(node, ast.AsyncFunctionDef), "동기 함수여야 한다(hot path)"
    assert not any(isinstance(n, ast.Await) for n in ast.walk(node)), (
        "hot path 에 `await` 금지 — 틱 디스패치 지연은 손절 지연이다"
    )
    names = {
        n.func.id for n in ast.walk(node)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
    } | {
        n.func.attr for n in ast.walk(node)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
    }
    assert "write_log" not in names, "hot path 에서 DB 로깅 금지 (logger 만)"
