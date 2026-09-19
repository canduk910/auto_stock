"""cycle317 — 15:30~16:00 완전 휴식 컷이 **테스트 결과를 실행 시각에 묶던 것**.

## 무슨 일이 있었나

cycle295 가 15:30~16:00 을 「완전 휴식」으로 만들었다(그 창의 주문 0건). 판정은
`order_engine._market_rest_now(now)` 가 하고 기본 인자는 **벽시계**다.

그래서 `execute_buy`/`execute_sell` 을 타는 모든 테스트가 **그 시각에 돌면 컷된다**.
2026-09-19 실측 — 로컬 15:53 에 전체 스위트가 **59건 실패**, CI(UTC 06:46 = KST 15:46)도
같은 59건으로 붉었다. 컨테이너가 `TZ=Asia/Seoul` 이라 CI 도 KST 로 돈다.

🔴 **매일 30분간 CI 가 붉어지는 상태였다.** 코드 결함이 아니라 테스트가 시각에 묶인 것이고,
「로컬에서는 초록인데 특정 시각에만 실패」라 원인 짚기가 특히 어렵다.

## 무엇을 했나

`tests/conftest.py` 에 autouse 픽스처 `_neutralize_market_rest`(선례 = 같은 파일의
`_neutralize_api_auth`)를 넣어 **판정 함수 `_market_rest_now` 자체를 갈아끼운다**.

🔴 **왜 시계가 아니라 판정 함수인가** — `order_engine.py` 는 **8영역**이라 손댈 수 없는데
그 파일에는 `_now_kst()` 같은 시계 seam 이 없다(`datetime.now(_KST_TZ)` 직접 호출).
프로덕션에 seam 을 새로 파려면 승인이 필요하다. 다행히 `_market_rest_now` 는 모듈 전역
이름으로 불리므로(`order_engine.py:620`) 그 이름 하나만 바꾸면 된다 — 프로덕션 무접촉이다.

컷 자체를 검증하는 테스트는 `@pytest.mark.real_market_rest` 로 옵트아웃한다 —
그 규약이 없으면 이 픽스처가 cycle295 의 회귀 가드를 통째로 무력화한다.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

pytestmark = pytest.mark.unit

_KST = timezone(timedelta(hours=9))


def test_rest_is_neutralized_by_default() -> None:
    """기본적으로 컷이 중립화돼 있는가 — **어떤 시각을 넣어도** 막지 않는다.

    막는 회귀 = 픽스처를 지우는 것. 그러면 주문 경로 테스트 59건이 하루 30분 동안 붉어진다
    (2026-09-19 실측 — 로컬 15:53 과 CI(UTC 06:46 = KST 15:46) 둘 다 같은 59건).
    """
    from src.engine import order_engine as oe

    inside = datetime(2026, 9, 21, 15, 45, tzinfo=_KST)  # 휴식 창 한복판
    blocked, reason = oe._market_rest_now(inside)
    assert not blocked, (
        f"휴식 컷이 중립화되지 않았다 (reason={reason}). "
        "주문 경로 테스트가 실행 시각에 묶인다."
    )


def test_neutralized_shape_is_contract() -> None:
    """반환 모양이 계약대로인가 — 호출부가 `(bool, str)` 튜플을 푼다."""
    from src.engine import order_engine as oe

    out = oe._market_rest_now(datetime(2026, 9, 21, 15, 45, tzinfo=_KST))
    assert isinstance(out, tuple) and len(out) == 2, out
    assert out[0] is False and isinstance(out[1], str), out


@pytest.mark.real_market_rest
def test_rest_window_still_cuts_when_real() -> None:
    """컷 자체는 살아 있는가 — 옵트아웃하면 휴식 창을 막아야 한다.

    🔴 이 테스트가 픽스처의 안전장치다. 옵트아웃 규약이 없으면 픽스처가 cycle295 의
    회귀 가드를 통째로 무력화한다 — 「15:30~16:00 에 주문이 안 나간다」를 검증하는
    테스트가 영원히 통과해 버린다.
    """
    from src.engine import order_engine as oe

    inside = datetime(2026, 9, 21, 15, 45, tzinfo=_KST)  # 월요일 15:45
    blocked, reason = oe._market_rest_now(inside)
    assert blocked, f"15:45 에 컷이 안 걸린다 — cycle295 가 깨졌다 (reason={reason})"
    assert reason == "market_rest", reason

    outside = datetime(2026, 9, 21, 11, 0, tzinfo=_KST)  # 월요일 11:00
    blocked2, _ = oe._market_rest_now(outside)
    assert not blocked2, "정규장 11:00 에 컷이 걸린다 — 과잉 차단이다"


# ---------------------------------------------------------------------------
# 메타 가드 — 중립화 픽스처가 cycle295 회귀 가드를 먹어 치우지 않는가
# ---------------------------------------------------------------------------
def test_files_touching_the_rest_cut_opt_out() -> None:
    """휴식 컷을 언급하는 테스트 파일은 **전부** 옵트아웃 마커를 들고 있어야 한다.

    🔴 이 가드가 없으면 같은 사고가 조용히 재발한다. cycle317 픽스처를 넣은 직후
    실측으로 cycle295 회귀 가드 **58건이 통째로 무력화**됐다 — 「15:30~16:00 에 주문이
    안 나간다」를 검증하는 테스트가 중립화된 판정 앞에서 전부 공허하게 통과했다.

    목록을 손으로 관리하지 않고 **자동 탐색**한다. 새로 그런 파일을 만들면 여기서
    붉어져 마커를 붙이게 된다 — 손 목록은 새 파일을 놓친다.

    ⚠️ **한계 — 키워드 기반이라 표현이 다르면 놓친다.** 실측 사례:
    `test_cycle287_exchange_routing.py` 는 판정 이름도 마커 이름도 안 쓰고
    「cycle295 컷」이라는 한글 표현만 써서 이 탐색을 빠져나갔다(전체 스위트에서야 드러났다).
    그래서 이 가드는 **바닥선**이지 완전한 그물이 아니다 —
    진짜 검증은 「휴식 창 시각으로 고정한 채 주문 경로 스모크를 돌리는 것」이고
    그건 별건으로 남겼다(워크리스트).
    """
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    me = Path(__file__).name

    def _code_only(src: str) -> str:
        """주석과 docstring 을 걷어낸다 — 「언급」과 「검증」은 다르다.

        `_market_rest_now` 를 설명 문장에서 부르는 파일은 중립화의 **수혜자**다
        (그 컷 때문에 붉어지던 쪽). 옵트아웃시키면 오히려 되돌아간다.
        """
        import io
        import tokenize

        out: list[str] = []
        try:
            for tok in tokenize.generate_tokens(io.StringIO(src).readline):
                if tok.type == tokenize.COMMENT:
                    continue
                if tok.type == tokenize.STRING:
                    # docstring·설명 문자열은 버리되, 마커 단언에 쓰는 짧은 리터럴은 남긴다.
                    if len(tok.string) > 200 or "\n" in tok.string:
                        continue
                out.append(tok.string)
        except Exception:
            return src
        return " ".join(out)

    missing: list[str] = []
    for p in (root / "tests").rglob("test_*.py"):
        if p.name == me:
            continue
        raw = p.read_text(encoding="utf-8", errors="ignore")
        code = _code_only(raw)
        # 실제로 판정을 부르거나 그 마커를 단언하는 파일만 대상이다.
        touches = (
            "_market_rest_now" in code
            or "market_rest_blocked" in code
            or "market_rest_window" in code
        )
        if not touches:
            continue
        if "real_market_rest" not in raw:
            missing.append(str(p.relative_to(root)))

    assert not missing, (
        "휴식 컷을 검증하는 파일이 중립화 픽스처를 옵트아웃하지 않았다 — "
        "중립화된 판정 앞에서 공허하게 통과한다:\n"
        + "\n".join(f"  {x}" for x in sorted(missing))
        + "\n`pytest.mark.real_market_rest` 를 pytestmark 에 더한다."
    )
