"""cycle282 후속 — 골든 픽스처 **동기화 가드** (적대 검증 지적 3·4).

## 이 파일이 닫는 구멍

`frontend/src/test/fixtures/marketState.fixture.ts` 와 `e2e/fixtures/market-state.fixture.ts`
의 머리말은 "기계 생성이다 · 손으로 고치지 않는다 · 백엔드가 byte 비교한다" 고 **선언**했지만,
생성기도 비교 가드도 없었다. 선언만 있고 강제가 없으면 다음 사람이 픽스처를 손으로 고쳐도
아무것도 붉어지지 않고, 그 순간 목은 *실제 응답*이 아니라 *누군가의 기대*가 된다 —
cycle266(종목마스터 일봉 탭)이 세 목을 전부 손으로 맞춰 3개월을 초록으로 보낸 그 계열이다.

## 무엇을 강제하는가

* **I1 / I2** — `tools/test_fixtures/gen_market_state_fixture.py` 의 산출과 두 픽스처 파일이
  **byte 동일**하다. 생성기는 `src/routes/market_state.py::read_market_state` 를 그대로
  호출하므로(시각·휴장일만 고정), 이 단언은 곧 "픽스처 = 라우트의 실제 응답" 이다.
  표(`MARKET_TABLE`)·카탈로그(`ORDER_DIVISIONS`)·라우트 조립 중 하나라도 바뀌고 재생성을
  빠뜨리면 여기서 멈춘다.
* **I3** — 두 픽스처가 **머리말을 뺀 전부**가 byte 동일하다. 4천 줄짜리 파일이 두 벌로
  복제돼 있는데 둘이 같다는 보장이 없으면, 컴포넌트 테스트와 Playwright 가 서로 다른
  세계를 보면서 양쪽 다 초록일 수 있다.
* **I4** — 5개 export 이름이 두 파일에 모두 있다. 이름은 계약이다(프론트 테스트 3파일과
  MSW·Playwright 목이 그 이름으로 붙어 있다).
* **I5** — 픽스처 머리말이 생성기 경로를 **실재하는 파일로** 가리킨다. 머리말의 거짓 선언
  자체를 막는다.

재생성 =
    python tools/test_fixtures/gen_market_state_fixture.py
"""

from __future__ import annotations

import importlib.util
import pathlib

import pytest

pytestmark = pytest.mark.unit

_ROOT = pathlib.Path(__file__).resolve().parents[3]
_GEN = _ROOT / "tools/test_fixtures/gen_market_state_fixture.py"
_FRONT = _ROOT / "frontend/src/test/fixtures/marketState.fixture.ts"
_E2E = _ROOT / "e2e/fixtures/market-state.fixture.ts"

#: 머리말과 본문의 경계. 두 파일의 머리말은 서로 다르고(용도 설명), 그 뒤는 같아야 한다.
_BODY_ANCHOR = "export interface MarketStateWindow {"

#: 이름이 곧 계약인 export 들.
_EXPORTS = (
    "MARKET_STATE_AT_0835",
    "MARKET_STATE_AT_1305",
    "MARKET_STATE_AT_2030",
    "MARKET_STATE_PREVIEW",
    "MARKET_STATE_FORBIDDEN",
)

_REGEN_HINT = (
    "픽스처가 생성기 산출과 어긋났다. 손으로 고치지 말고 재생성하라 —\n"
    "    python tools/test_fixtures/gen_market_state_fixture.py"
)


def _load_generator():
    """생성기를 모듈로 읽는다(`tools/` 는 패키지가 아니므로 경로 로드).

    생성기는 `if __name__ == "__main__"` 뒤에서만 파일을 쓰므로 import 는 부작용이 없다.
    """
    assert _GEN.exists(), f"생성기 없음 — {_GEN}"
    spec = importlib.util.spec_from_file_location("_cycle282_fixture_generator", _GEN)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _first_diff(expected: str, actual: str) -> str:
    """어긋난 첫 줄을 지목한다(4천 줄 diff 를 통째로 쏟지 않는다)."""
    exp_lines = expected.splitlines()
    act_lines = actual.splitlines()
    for idx, (a, b) in enumerate(zip(exp_lines, act_lines), start=1):
        if a != b:
            return f"{idx}행\n  생성기: {a[:160]}\n  파일  : {b[:160]}"
    if len(exp_lines) != len(act_lines):
        return f"줄 수가 다르다 — 생성기 {len(exp_lines)} vs 파일 {len(act_lines)}"
    return "줄 단위로는 같다(줄바꿈·끝 공백 차이)"


def _body_of(path: pathlib.Path) -> str:
    text = path.read_text(encoding="utf-8")
    index = text.find(_BODY_ANCHOR)
    assert index != -1, f"{path.name}: 본문 시작 앵커를 찾지 못했다 — {_BODY_ANCHOR!r}"
    return text[index:]


# ---------------------------------------------------------------------------
# I1 · I2 — 생성기 산출 == 픽스처 파일 (byte)
# ---------------------------------------------------------------------------
def test_i1_frontend_fixture_matches_generator_output():
    """I1 — 컴포넌트/MSW 픽스처가 생성기 산출과 byte 동일하다."""
    generated = _load_generator().render_front()
    current = _FRONT.read_text(encoding="utf-8")
    assert generated == current, (
        f"{_FRONT.relative_to(_ROOT)} — {_REGEN_HINT}\n첫 불일치: {_first_diff(generated, current)}"
    )


def test_i2_e2e_fixture_matches_generator_output():
    """I2 — Playwright 픽스처가 생성기 산출과 byte 동일하다."""
    generated = _load_generator().render_e2e()
    current = _E2E.read_text(encoding="utf-8")
    assert generated == current, (
        f"{_E2E.relative_to(_ROOT)} — {_REGEN_HINT}\n첫 불일치: {_first_diff(generated, current)}"
    )


# ---------------------------------------------------------------------------
# I3 — 두 벌이 같은 세계를 본다
# ---------------------------------------------------------------------------
def test_i3_two_fixture_copies_share_one_body():
    """I3 — 머리말만 다르고 본문(타입 + 5 export)은 byte 동일하다."""
    front_body = _body_of(_FRONT)
    e2e_body = _body_of(_E2E)
    assert front_body == e2e_body, (
        "컴포넌트 픽스처와 Playwright 픽스처의 본문이 갈라졌다 — 두 스위트가 서로 다른 "
        f"응답을 보면서 양쪽 다 초록일 수 있다.\n{_REGEN_HINT}\n"
        f"첫 불일치: {_first_diff(front_body, e2e_body)}"
    )


def test_i4_export_names_are_the_contract():
    """I4 — 5 export 이름이 두 파일에 모두 있다(프론트 테스트가 그 이름으로 붙어 있다)."""
    for path in (_FRONT, _E2E):
        text = path.read_text(encoding="utf-8")
        for name in _EXPORTS:
            assert f"export const {name}" in text, (
                f"{path.name}: export {name} 이 없다 — 이름은 계약이다"
            )
        assert "export const MARKET_STATE_FIXTURE" in text, (
            f"{path.name}: MSW 기본 변종 별칭이 없다"
        )


# ---------------------------------------------------------------------------
# I5 — 머리말의 선언이 거짓이 아니다
# ---------------------------------------------------------------------------
def test_i5_header_points_at_a_real_generator():
    """I5 — 머리말이 가리키는 생성기 경로가 실재한다(선언만 있고 강제 없음 차단)."""
    rel = str(_GEN.relative_to(_ROOT))
    for path in (_FRONT, _E2E):
        head = path.read_text(encoding="utf-8").split(_BODY_ANCHOR, 1)[0]
        assert rel in head, (
            f"{path.name} 머리말이 생성기 경로({rel})를 가리키지 않는다 — "
            "'기계 생성' 선언은 그 생성기가 실재할 때만 참이다"
        )
    assert _GEN.exists(), f"{rel} 없음"
    module = _load_generator()
    for attr in ("render_front", "render_e2e", "main", "VARIANTS"):
        assert hasattr(module, attr), f"생성기에 {attr} 가 없다"
    assert len(module.VARIANTS) == 4, (
        f"변종 4개 계약 위반 — {len(module.VARIANTS)}개. "
        "하나로는 중첩·장 종료·미리보기를 다 잴 수 없다"
    )
