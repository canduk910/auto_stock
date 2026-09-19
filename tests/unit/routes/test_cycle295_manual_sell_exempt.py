"""cycle295 §4-7 · §9-Q3 ② — `POST /api/trading/manual-sell` 는 **컷 면제**다.

정본 = `_workspace/red/cycle295_gap_hold_removal_spec.md` §4-7(사실) · §9-Q3(처분).

이 라우트의 `place_order` 는 `execute_sell` 도 `_apply_clock` 도
`_route_exchange_by_clock` 도 거치지 않는다 — `order_engine._market_rest_gate` 에
닿는 경로가 **구조적으로 없다**. 거래소는 전략 params 의 `exchange` 이고 운영 DB
7전략이 전부 `SOR` 이라, 15:45 에 대시보드 '매도' 를 누르면 SOR 시장가가 나가
NXT AFTER_MARKET leg 로 **체결된다**.

처분(§9-Q3) = ② **명시 면제 + 응답 message 경고**. ③(`execute_sell` 위임)은
cycle287 구멍(애프터 호가유형 미변환 + 실패 시 stale `_selling`)까지 한 번에
닫지만 8영역 diff 와 행위 반경이 커서 별건 카드다.

⚠️ 아무것도 안 적으면 다음 사람이 "15:30~16:00 주문 0건" 판독을 하다가 이 한 건에
걸려 게이트가 고장났다고 오진한다 — 이 파일이 그 오진을 막는 계약이다.

🔴 날짜는 전부 **2026-09-14 이상**(K6 `effective_from`).
"""

from __future__ import annotations

import pytest
from freezegun import freeze_time

pytestmark = [
    pytest.mark.unit,
    # 🔴 cycle317 의 휴식 컷 중립화 픽스처를 **옵트아웃**한다.
    # 이 파일이 검증하는 것이 바로 그 컷이라, 중립화되면 전부 공허하게 통과한다.
    pytest.mark.real_market_rest,
]

# freezegun 은 naive 문자열을 UTC 로 동결한다. KST = UTC + 9h.
_F_1545 = "2026-09-15 06:45:00"  # KST 15:45 — 컷 한가운데
_F_1100 = "2026-09-15 02:00:00"  # KST 11:00 — 정규장
_F_1605 = "2026-09-15 07:05:00"  # KST 16:05 — KRX 애프터
_F_0830 = "2026-09-14 23:30:00"  # KST 08:30 — NXT 프리장


def _note() -> str:
    from src.routes.trading import _market_rest_note

    return _market_rest_note()


@freeze_time(_F_1545)
def test_q3_manual_sell_warns_inside_the_rest_window() -> None:
    """🔴 컷 창 안 — 응답에 붙을 경고 문구가 만들어진다."""
    note = _note()
    assert note, (
        "컷 창(15:30~16:00)인데 면제 경고가 비었다 — 운영자가 '자동매매는 쉬는데 "
        "내 버튼은 나간다' 는 사실을 알 길이 없다(§9-Q3 ②)"
    )
    assert "15:30" in note and "16:00" in note, note
    assert "면제" in note, note


@pytest.mark.parametrize("moment", [_F_1100, _F_1605, _F_0830])
def test_q3_no_warning_outside_the_rest_window(moment) -> None:
    """🔵 양성 대조군 — 창 밖에서는 문구가 **비어** 있다.

    항상 경고하는 퇴화 구현이면 경고가 배경 소음이 되어 정작 필요한 30분에
    아무도 읽지 않는다.
    """
    with freeze_time(moment):
        assert _note() == "", f"{moment} 에 컷 경고가 붙었다 — 과잉 경고"


def test_q3_note_is_never_raise() -> None:
    """🔴 판정이 터져도 **수동 매도 자체는 막히지 않는다**.

    이 헬퍼는 응답 문구를 만드는 관측기다. 여기서 예외가 새면 운영자의
    비상 매도가 500 으로 죽는다 — 관측이 매매를 바꾸면 안 된다(브리프 제약 6).
    """
    import src.engine.order_engine as _oe
    from src.routes import trading as _tr

    orig = _oe._market_rest_now
    try:
        _oe._market_rest_now = lambda now: (_ for _ in ()).throw(RuntimeError("boom"))
        assert _tr._market_rest_note() == ""
    finally:
        _oe._market_rest_now = orig


def test_q3_route_does_not_reach_the_cut_gate() -> None:
    """🔴 구조 — 이 라우트는 게이트를 **부르지 않는다**(면제가 사실임을 고정).

    누군가 조용히 게이트를 걸면 운영자의 비상 매도가 30분 막힌다 — 그것은
    사용자 결정(①)이 필요한 행위 변경이라 여기서 붉어져야 한다.

    ⚠️ 부분 문자열 매치로 재면 **주석·docstring 이 통과시킨다**(cycle292 가
    `/sync-docs` 자가 점검에서 같은 거짓 통과를 실측했다). 그래서 AST 로 실제
    **호출 이름**만 센다.

    🔵 양성 대조군 — 같은 AST 스캔에서 `place_order` 와 `_market_rest_note` 는
    실제 호출로 **존재**한다(스캐너가 파일을 못 읽으면 부정 단언이 전부 참이
    되므로).
    """
    import ast
    import inspect

    from src.routes import trading as _tr

    tree = ast.parse(inspect.getsource(_tr))
    called: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            if isinstance(f, ast.Name):
                called.add(f.id)
            elif isinstance(f, ast.Attribute):
                called.add(f.attr)

    assert "_market_rest_gate" not in called, (
        "manual-sell 라우트가 컷 게이트를 부른다 — 면제(②)가 아니라 ①이다. "
        "운영자 비상 매도를 막는 것은 사용자 결정 사항이다(§9-Q3)"
    )
    assert "execute_sell" not in called, (
        "③(`execute_sell` 위임)이 들어왔다 — 행위 반경이 큰 별건 카드다. "
        "들였다면 이 파일의 계약을 통째로 다시 써야 한다"
    )
    # 🔵 양성 대조군
    assert "place_order" in called, "스캐너가 라우트 소스를 읽지 못했다"
    assert "_market_rest_note" in called, (
        "면제 경고 헬퍼가 호출되지 않는다 — 문구를 만들어도 응답에 안 붙으면 "
        "§9-Q3 ② 가 성립하지 않는다"
    )
