"""cycle325 — 비중 0 이 보유 종목의 손절을 조용히 멈추던 것.

## 두 겹이 동시에 뚫린다

1. **`registry.update_weights` 는 `config.enabled = weight > 0` 을 자동 토글한다**
   (`strategy_registry.py`). 즉 **비중 0 = 비활성화**다. 그리고 `risk.on_tick` 은
   `registry.enabled()` 만 순회하므로, 비활성 전략의 보유 종목은
   **손절·트레일링·익일청산·15:20 청산이 전부 멈춘다**(루트 `CLAUDE.md` 「절대 깨지 말 것」).

2. 그걸 막아야 할 **매수금액 하한선 검증이 `if total_asset > 0` 안에** 있다.
   `total_asset` 은 **메모리 예산의 합**이고, 예산은 `_boot()` 의 `allocate_funds` 에서만 선다.
   🔴 **부팅 전에는 0 이라 검증이 통째로 건너뛰어진다.**

## 실측 (2026-09-20 09:2x, 운영)

스케줄러가 `running=False`(주말 대기)이라 `Σ total_investment = 0` 이었다.
그 상태에서 `kojiro` 비중을 0 으로 보내면 **받아들여진다** — DB `positions` 에는
6종목 433,010원이 있는데, 월요일 부팅이 그 포지션을 **비활성 전략에 복구**하고
아무도 보지 않는 채 남는다. `donchian_swing`(3종목)·`bull_flag_breakout`(2종목)도 같다.

## 고치는 방향

하한선 검증의 분모가 **메모리 예산**인 것이 문제의 뿌리다. 보유 여부는 예산과 무관하게
알 수 있어야 한다 — **비중을 0 으로 내리는 것 자체**를 보유가 있으면 막는다.
그 판정은 예산이 0이어도 성립해야 하므로 `if total_asset > 0` **밖**에 둔다.

⚠️ 보유 조회는 메모리(`state.positions`)만 보면 부팅 전에 또 0 이다. **DB `positions` 를 본다.**
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[3]
_ROUTE = _ROOT / "src/routes/strategies.py"


def _src() -> str:
    return _ROUTE.read_text(encoding="utf-8")


def _update_weights_body() -> str:
    """`update_weights` 라우트 본문만 잘라낸다."""
    s = _src()
    i = s.find("async def update_weights(")
    assert i > 0, "update_weights 라우트가 없다"
    j = s.find("\n@router.", i)
    return s[i: j if j > 0 else len(s)]


def test_zero_weight_guard_exists() -> None:
    """비중 0 을 보유 여부로 막는 가드가 있는가.

    막는 회귀 = 이 가드를 지우는 것. 지우면 비중 0 한 번으로
    보유 종목의 손절이 조용히 멈춘다.
    """
    body = _update_weights_body()
    assert "_held_tickers_from_db" in body or "zero_weight" in body, (
        "비중 0 전용 가드가 없다 — `update_weights` 는 `enabled` 를 자동 토글하므로 "
        "비중 0 은 곧 비활성화이고, 보유가 있으면 손절이 멈춘다."
    )


def test_zero_weight_guard_is_outside_the_budget_gate() -> None:
    """🔴 가드가 `if total_asset > 0` **밖**에 있는가 — 이 파일의 핵심.

    막는 회귀 = 새 가드를 기존 하한선 검증 안에 넣는 것. 그러면 **부팅 전에는
    똑같이 건너뛰어져** 고친 것이 아무 일도 하지 않는다(실측: 주말 대기 중 예산 합 0).
    """
    # ⚠️ 주석·docstring 을 걷어내고 **코드 줄만** 본다 — 초판은 가드 설명 주석 안의
    # `if total_asset > 0` 문구를 게이트로 잡아 순서를 거꾸로 읽었다(오늘 다섯 번째로 밟은
    # 「금지 패턴을 문맥 없이 찾는」 함정).
    raw = _update_weights_body()
    body = "\n".join(ln.split("#", 1)[0] for ln in raw.splitlines())
    gate = body.find("if total_asset > 0")
    guard = max(body.find("_held_tickers_from_db"), body.find("zero_weight"))
    assert guard >= 0, "가드가 없다"
    assert gate >= 0, "하한선 검증 게이트가 사라졌다 — 이 가드의 전제부터 재검토"
    assert guard < gate, (
        "비중 0 가드가 `if total_asset > 0` 안(또는 뒤)에 있다 — 부팅 전에는 "
        "예산이 0 이라 통째로 건너뛰어진다. 게이트 **앞**으로 옮긴다."
    )


def test_guard_reads_db_not_only_memory() -> None:
    """보유 판정이 **DB 를 포함**하는가.

    막는 회귀 = `state.positions`(메모리)**만**으로 판정하는 것. 부팅 전에는 메모리가
    비어 있어 똑같이 뚫린다 — 그게 이 결함의 원인이다.

    ⚠️ 메모리를 **함께** 보는 것은 막지 않는다 — 현재 설계는 **DB ∪ 메모리**라
    DB 를 못 읽는 맥락에서도 한 겹이 남는다. 금지되는 것은 DB 를 **빼는** 것뿐이다.
    """
    body = _update_weights_body()
    i = body.find("_held_tickers_from_db")
    assert i >= 0, "DB 조회 헬퍼를 안 쓴다 — 부팅 전에는 메모리가 비어 있어 뚫린다"
    window = body[max(0, i - 200): i + 600]
    assert "state.positions" in window, (
        "메모리를 함께 보지 않는다 — DB 를 못 읽는 맥락에서 한 겹도 안 남는다"
    )


def test_helper_queries_positions_table() -> None:
    """헬퍼가 `positions` 테이블을 읽는가 — 공허 통과 방지."""
    s = _src()
    assert "_held_tickers_from_db" in s, "헬퍼가 없다"
    i = s.find("async def _held_tickers_from_db")
    assert i > 0, "헬퍼 정의가 없다"
    body = s[i: i + 900]
    assert "positions" in body, "헬퍼가 positions 테이블을 안 읽는다"


def test_taboo_is_documented_in_route() -> None:
    """라우트에 **왜** 막는지가 적혀 있는가.

    이유 없는 가드는 다음 사람이 「쓸데없이 막는다」며 지운다.
    """
    body = _update_weights_body()
    assert re.search(r"손절|enabled|비활성", body), (
        "비중 0 이 왜 위험한지(= enabled 토글 → 손절 정지)가 라우트에 안 적혀 있다"
    )
