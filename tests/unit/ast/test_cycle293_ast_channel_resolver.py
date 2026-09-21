"""cycle293 Red (2단계 · 속성축 배관) — AST/정적 가드.

명세 = `_workspace/red/cycle293_tick_channel_resolver_spec.md`
회귀 가드 목록 = 그 문서 §10 (G1~G10)

## 이 사이클이 하는 일 — 한 문장

`tick_tr_id_for(ticker)` 리졸버를 도입하고, 9파일 25+ 사이트에 흩어진
`tr_id == TICK_TR_ID` **등가 비교를 집합 멤버십으로 바꾼다**(부채 상환).
**전환(살아 있는 구독의 채널 변경)은 넣지 않는다**(§3-C 2단계 한정 규약).

## 종착지 (재론 금지 — 2026-09-07 사용자 결정 + 09-14 재확인)

통합 채널 `H0UNCNT0` 폐기. KRX 전용(`H0STCNT0`) + NXT 전용(`H0NXCNT0`) 2채널.
아래 `fail-open = H0UNCNT0` 규약은 **2단계 한정 과도기 장치**이지 영구 기본값이
아니다(§3-D). 3단계에서 폴백 대상이 전용 채널 중 하나로 바뀐다.

## 이 파일이 잠그는 것

| ID | §10 | 잠그는 것 |
|----|-----|-----------|
| A1 | — | 금지 파일 sha 불변(8영역 중 승인 4파일 제외 · 전략 7파일 · `scheduler.py`) |
| A2 | — | `scheduler.py` 라인 수 정확 일치(3,726) + 영구 상한 3,900 |
| A3 | G5 | 🔴 **`tr_id == TICK_TR_ID` 등가 비교 소스 전역 0건** |
| A4 | G5 | 🔴 **단일 정본 집합** `TICK_TR_IDS` — 세 채널을 담은 컬렉션 리터럴이 소스에 1개 |
| A5 | G5 | 소비처가 그 정본을 **import 해서** 쓴다(두 번째 집합 0건) |
| A6 | G1 | `tick_tr_id_for` 실재 · **동기** · 순수(await/DB/HTTP 0) |
| A7 | G1 | 상수 3개 값 불변 + 리졸버 반환 도메인 = 그 3개 |
| A8 | G4 | HIGH(positions·익일청산) 구독 2곳의 `priority="HIGH", bypass_limit=True` 불변 |
| A9 | G6 | grace ACK 조회 키가 리졸버 경유(`(TICK_TR_ID, t)` 하드코딩 0건) |
| A10 | G7 | `ensure_fresh` 인자가 **채널 무관 집합**(자기 강화 플리커 차단) |
| A11 | — | `routes/realtime.py` 미사용 `TICK_TR_ID` import 제거 |
| A12 | G3 | 병행 dict `_ticker_to_tr_id` 가 `_ticker_to_session` 의 모든 수명 지점에 동행 |
| A13 | §9-A | 신규 마커 5종 실재 |
| A14 | §8-B | 킬스위치는 `system_config` 축 — 전략 `DEFAULT_PARAMS`·`param_catalog` 무접촉 |
| A15 | C-2 | 리졸버·플리커 백스톱에 **시각 리터럴 0건**(출처 검사로 판정) |
| A16 | §4-C | `scheduler.py` 풀 우회 2곳은 **관측만** — 그 파일에 리졸버 호출 0건 |
| A17 | G8 | 해제 3곳(`order_engine`·`stale_universe_guard`·`stale_session_recovery`)이 리졸버 경유 |

## 🔴 구현자에게 — 이 파일이 고정한 이름 (명세가 정하지 않은 부분)

명세 §3-A 는 시그니처를 `tick_tr_id_for(ticker: str) -> str` 로 적었지만 §8-A 의
단계 `enforce_low`(= HIGH 제외, LOW 만 전환)는 **우선순위를 알아야** 성립한다.
그래서 Red 가 **키워드 전용 · 기본값 있는** 인자 하나를 더한다 —
`tick_tr_id_for(ticker: str, *, priority: str = "LOW") -> str`.
명세의 1인자 호출은 그대로 성립한다(기본값 LOW).

| 이름 | 자리 |
|---|---|
| `scanner.TICK_TR_IDS` | 세 채널 단일 정본 frozenset (모듈 레벨) |
| `scanner.tick_tr_id_for` | 리졸버(동기·순수). leaf 재export 허용 |
| `src/engine/tick_channel_mode.py` | 킬스위치 모드 상태 + `system_config` 재조회 |
| `no_feed_registry.is_provenance_ok(ticker)` | §6-C 출처(provenance) 검사 |
| `websocket_pool._ticker_to_tr_id` | §5-C 병행 dict |

## ⚠️ 미해결 충돌 — 사람이 정해야 한다

오케스트레이션 지시는 `risk.py` **diff 0** 을 요구하고(절대 규칙 2), 동시에
`nxt_false` 종목이 5전략 매수 평가에 **도달하지 않음**을 행위로 요구한다
(절대 규칙 5 = 명세 §3-E B-1). 그 게이트의 유일한 자리는 `risk.on_tick` 의
매수 분기(`risk.py:653` 부근)다 — 둘은 동시에 만족되지 않는다.
그래서 `risk.py` 핀은 `_BASE_SHA` 가 아니라 **`_PIN_PENDING_APPROVAL`** 에 둔다
(아래 `test_a1b` 의 docstring 이 선택지 둘을 적는다).
"""

from __future__ import annotations

import ast
import hashlib
import pathlib
import re

import pytest

pytestmark = pytest.mark.unit

_ROOT = pathlib.Path(__file__).resolve().parents[3]
_SRC = _ROOT / "src"

_SCANNER_REL = "src/engine/scanner.py"
_WS_REL = "src/realtime/websocket.py"
_POOL_REL = "src/realtime/websocket_pool.py"
_ORDER_ENGINE_REL = "src/engine/order_engine.py"
_SWC_REL = "src/engine/stale_watcher_core.py"
_DIAG_REL = "src/engine/stale_diagnostics.py"
_ROUTES_REL = "src/routes/realtime.py"
_HANDLER_REL = "src/realtime/handler.py"
_MODE_REL = "src/engine/tick_channel_mode.py"

#: 세 시세 채널 TR_ID.
_TICK_TR_ID_LITERALS = frozenset({"H0UNCNT0", "H0STCNT0", "H0NXCNT0"})

#: 단일 정본 집합의 이름.
_CANONICAL_SET_NAME = "TICK_TR_IDS"

#: `system_config` 킬스위치 키 (§8-B).
_KILL_SWITCH_KEY = "tick_channel_resolver_mode"

#: §9-A 신규 마커.
_NEW_MARKERS = (
    "[tick_channel_config]",
    "[tick_channel_resolve]",
    "[tick_channel_flip]",
    "[tick_channel_dual_detected]",
    "[tick_channel_provenance_unknown]",
)


def _src(rel: str) -> str:
    return (_ROOT / rel).read_text(encoding="utf-8")


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _tree(rel: str) -> ast.Module:
    return ast.parse(_src(rel))


def _function(rel: str, name: str):
    for node in ast.walk(_tree(rel)):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    return None


def _production_py_files() -> list[pathlib.Path]:
    return sorted(p for p in _SRC.rglob("*.py") if "__pycache__" not in p.parts)


def _rel(p: pathlib.Path) -> str:
    return str(p.relative_to(_ROOT))


# ===========================================================================
# A1 — 금지 파일 sha (착수 시점 = cycle292 워크트리, 2026-09-14)
# ===========================================================================
#: 접촉 **허용** = 8영역 4파일(`scanner.py`·`websocket.py`·`websocket_pool.py`·
#: `order_engine.py`, 사용자 승인 2026-09-14) + 8영역 밖 보조 파일
#: (`stale_*`·`routes/realtime.py`·`db/stock_master.py`·`db/system_config.py`)
#: + 신규 leaf. 그 밖은 전부 아래 핀이 지킨다.
_BASE_SHA: dict[str, str] = {
    # 8영역 — 미승인 (절대 규칙 2)
    "src/engine/session.py":
        "36257d86af1c26a868dc991a74a9eb139c98a9358d739d24600f5be2f9c5666c",
    "src/engine/strategy_registry.py":
        "d794696e54ffdc36efa6df917879d780e86bc1f373bb3b5d8dcbc0beac8cef8b",
    "src/api/order.py":
        "08c5cafd7b8678ec0d0fa85f856fdea3cce38ad92488c6d74c03cd13faa415bb",
    "src/auth/__init__.py":
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "src/auth/hashkey.py":
        "7c2aacc703839bdc274b463ee48777006504d70e4d59a1e57120ac5b612396d2",
    # 🔁 cycle296(2026-09-17) 재핀 — 사용자 승인 `issue()` 매니저 단위 in-flight 합류(`src/auth/**`). 같은 값을 10곳 동시 갱신했다.
    "src/auth/token.py":
        "4125c271b4147e59922f4f000e523429fb4bbef37058dc754fd92b9475ec58f1",
    # 8영역 realtime — `handler.py` 는 G10(파싱 무변경)의 대상이다.
    # 🔴 `handler.py:400` 의 3채널 **튜플**은 이 사이클이 집합화하지 않는다 —
    #    파싱 경로 byte 동일이 계약이라 A4 가 이 파일을 면제한다.
    "src/realtime/handler.py":
        "37b1755210c83cdb2a462e6a37f919b326f8b48bee73d924adcc277d770a8d17",
    "src/realtime/__init__.py":
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    # 🔴 `scheduler.py` 무접촉 (절대 규칙 3). cycle292 가 3,897→3,726L 로 만든
    #    여유 174줄은 이 사이클의 예산이 아니다. §4-C 풀 우회 2곳은 관측만.
    "src/engine/scheduler.py":
        "4b9c8ac94706ae622d3404fa10bfa805a69a4b36485787c388dff3aa6e76763d",
    "src/engine/market_op_subscribe.py":
        "7d58f9464c1ed35e4fa8706d801beb5a6b5c062d5a2941f0db6482d028d3d4ac",
    # 전략 7파일 + 베이스 (절대 규칙 5)
    "src/engine/strategy_base.py":
        "869dc20ca561adc561a9ebe9fdb5fe5a3e097f7ec176fdf274d577d509de9252",
    "src/engine/strategies/__init__.py":
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "src/engine/strategies/bull_flag_breakout.py":
        "acf564db24b37efe0cc64b690f17e3e83d9ad943aac0b5bb4f572d5a2940d916",
    "src/engine/strategies/donchian_swing.py":
        "cc57e5673f9982aca97f61677084e040171fff307483fedf10459b567a4679e3",
    "src/engine/strategies/kojiro.py":
        "9477790e9d20eb6d17f36fc7586ada77ac5e2e4b0136a334888244afdb7e9cbc",
    "src/engine/strategies/long_tail_volatility.py":
        "51b50560a1240df3fc6085da7253438605079d7d453ff3e77a806e814473be25",
    "src/engine/strategies/momentum.py":
        "50d5c0b9a232d6110f6b85fc524569853f2b8edffe2fd44adc24289800b95ae2",
    "src/engine/strategies/vcp_breakout.py":
        "5b324b34335f922f82b848ae2313e08660bde75c02d12432867ed224e9709228",
    "src/engine/strategies/volatility_breakout.py":
        "d13efaa4a9424e2822b5476ce159987d2a5192a4bca30af3f1a0cae9c3ffcabc",
    # 파라미터 축 — 킬스위치는 `system_config` 다(§8-B). 전략 파라미터로 새지 않는다.
    "src/engine/param_catalog.py":
        "babaf208053331a9a8487b7b1f79b0d8b569225d0e694370510ce7633cf318c1",
    "src/engine/param_validation.py":
        "b4c5c029800191523bcc511919d6de3774e9ab49ca2fc0a0558ee3907868ee17",
    # 시각·거래소 표의 유일 정본 — 리졸버는 **속성축**이라 이 표를 읽지 않는다.
    "src/engine/market_state.py":
        "7cef2efeb55a7184391ac2cc447c90102fdd7ba507fd6e3834d24a8ad9ce006b",
    # 마지막 write-wins 거래량 기록기 — 이중 채널이면 비결정론이 된다(§5-A 2).
    # 이 사이클은 여기를 고치지 않는다(이중 채널을 **금지**해서 닫는다).
    "src/engine/tick_volume.py":
        "457bd43d80e3cb46c64ae33cb6c1c5d0c12df54246c383bb3d81292d013ef267",
}

#: 🔴 사람이 정해야 하는 한 칸. 위 docstring 「미해결 충돌」 참조.
#:
#: **Green(2026-09-14) 에서 선택지 (가) 를 실행했다** — `risk.py` 에 §3-E B-1
#: 종목 축 매수 skip 게이트를 넣었고 그래서 이 핀이 새 값으로 옮겨졌다. 직전 값 =
#: `19f48b4a4f7c3b4aa47b99a1426d22ec26884277a9f711c279753d6d7452dcc7`.
#: ⚠️ **이것은 8영역 추가 승인 1건을 요구한다**(오케스트레이션 절대 규칙 2 와
#: 상충하는 유일한 항목). 승인 근거·판단은 `test_a1b` docstring 에 적었다.
_PIN_PENDING_APPROVAL: dict[str, str] = {
    "src/engine/risk.py":
        "79fddbec8cf9315c5172fc6634c4f4ea77f525d9ff9a3aba48f321affeb4d3e8",
}

_SCHEDULER_LINES = 3795
_SCHEDULER_LINE_CAP = 3900


@pytest.mark.parametrize("rel", sorted(_BASE_SHA))
def test_a1_forbidden_files_are_byte_identical(rel: str) -> None:
    """A1 — 금지 파일이 착수 시점과 byte 동일하다.

    붉어지면 핀을 옮기지 말고 **변경을 되돌려라.** 이 사이클의 접촉 허용은
    8영역 4파일(`scanner`·`websocket`·`websocket_pool`·`order_engine`) +
    8영역 밖 보조(`stale_*`·`routes/realtime`·`db/*`) + 신규 leaf 뿐이다.
    """
    got = _sha(_src(rel))
    assert got == _BASE_SHA[rel], (
        f"{rel} 가 바뀌었다 — cycle293 접촉 허용 밖이다. 현재 sha={got}"
    )


def test_a1b_risk_py_pin_is_the_open_decision() -> None:
    """A1b — `risk.py` diff 0 (오케스트레이션 절대 규칙 2).

    🔴 **이 핀과 `test_g9_*`(매수 축 보존, 행위 가드)는 동시에 만족되지 않는다.**
    §3-E B-1 의 종목 축 매수 skip 게이트의 유일한 자리가 `risk.on_tick` 의
    매수 분기이기 때문이다. 사람이 둘 중 하나를 골라야 한다:

    (가) **`risk.py` 1행 게이트를 승인**한다 → 이 핀을 새 sha 로 옮기고
         `test_g9_*` 를 초록으로 만든다. 8영역 추가 승인 1건.
    (나) **리졸버를 HIGH(보유·익일청산)에만 적용**한다 → `risk.py` 무접촉으로
         매수 축이 구조적으로 보존된다(보유 종목은 `is_ticker_blocked_for_buy`
         가 전 전략 차단). 대신 명세 §8-A 의 S1(HIGH 제외, LOW 먼저)과
         **반대 순서**가 되므로 그 단계표를 고쳐야 한다.

    (나)를 고르면 `test_g9_ticker_axis_gate_*` 5케이스를 **삭제하지 말고
    xfail 로 의미 전환**하고, 수단 무관 불변식
    `test_g9b_opening_a_channel_never_opens_the_buy_axis` 를 배포 게이트로 쓴다 —
    그 테스트는 두 선택지 어느 쪽에서도 초록이고 위험한 조합에서만 붉다.

    ## 🔴 Green(2026-09-14) 이 고른 것 = **(가)**. 사용자 승인 대상 1건.

    이유는 두 가지다. ① `test_ks_enforce_low_excludes_high` 가 `enforce_low` +
    LOW → `H0STCNT0` 를 **리졸버 반환값 수준에서** 핀하므로 (나)는 그 케이스를
    함께 뒤집어야 하고, 그러면 명세 §8-A 의 S1 단계표(HIGH 제외·LOW 먼저)까지
    고쳐야 한다 — Red 가 잠근 계약을 두 곳 되돌리는 쪽이 위험이 더 크다.
    ② (나)로 가면 `test_g9b` 는 조기 return 으로 초록이 되지만, 그 초록은
    "매수 축이 닫혔다" 가 아니라 "그 코호트를 열지 않았다" 는 뜻이라 3단계에서
    LOW 를 여는 순간 게이트 없이 열린다. 게이트를 **지금** 넣어 두면 3단계는
    걷어내는 결정(= 승인 + `domain-consult`)만 남는다.

    `risk.py` 변경 실체는 **호출 2줄 + 헬퍼 1개**이고, 기본 모드 `observe` 에서
    리졸버가 전 종목 `H0UNCNT0` 를 돌려주므로 게이트는 **발화하지 않는다** =
    배포 시점 매매 행위 변경 0. `enforce_low`/`enforce` 로 올리는 그 순간부터
    의미가 생긴다.
    """
    rel = "src/engine/risk.py"
    got = _sha(_src(rel))
    assert got == _PIN_PENDING_APPROVAL[rel], (
        f"{rel} 가 바뀌었다. 이것이 §3-E B-1 종목 축 게이트라면 승인 근거를 "
        f"이 docstring 에 적고 핀을 옮겨라(선택지 가). 현재 sha={got}"
    )


def test_a2_scheduler_untouched_line_count() -> None:
    """A2 — `scheduler.py` 라인 수 정확 일치 + cycle257 영구 상한.

    cycle292 가 방금 3,897→3,726 으로 만들었다(여유 174). 이 사이클은
    그 예산을 쓰지 않는다 — §4-C 풀 우회 2곳은 병행 dict 관측으로만 드러낸다.
    """
    lines = len(_src("src/engine/scheduler.py").splitlines())
    assert lines == _SCHEDULER_LINES, (
        f"scheduler.py = {lines}L (착수 시점 {_SCHEDULER_LINES}L) — 무접촉 계약 위반"
    )
    assert lines < _SCHEDULER_LINE_CAP


# ===========================================================================
# A3 (G5) — 🔴 등가 비교 전수 집합화
# ===========================================================================
def _equality_hits() -> list[tuple[str, int, str]]:
    """`tr_id == TICK_TR_ID` / `!=` / 리터럴 등가 비교를 전부 찾는다."""
    hits: list[tuple[str, int, str]] = []
    for path in _production_py_files():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:  # pragma: no cover
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Compare):
                continue
            if not any(isinstance(op, (ast.Eq, ast.NotEq)) for op in node.ops):
                continue
            for operand in [node.left, *node.comparators]:
                name = None
                if isinstance(operand, ast.Name):
                    name = operand.id
                elif isinstance(operand, ast.Attribute):
                    name = operand.attr
                elif isinstance(operand, ast.Constant) and isinstance(operand.value, str):
                    if operand.value in _TICK_TR_ID_LITERALS:
                        name = operand.value
                if name is not None and (
                    name.endswith("TICK_TR_ID") or name in _TICK_TR_ID_LITERALS
                ):
                    hits.append((_rel(path), node.lineno, ast.unparse(node)[:100]))
                    break
    return hits


def test_a3_no_equality_comparison_against_tick_tr_id() -> None:
    """🔴 A3 (G5) — 이 사이클에서 **가장 중요한 가드**.

    등가 비교를 하나라도 남기면 `H0STCNT0` 로 옮긴 종목이
    `get_subscribed_tickers()` 에서 **조용히 사라진다**(§5-B):

      * K stale watcher 가 그 종목을 영원히 못 본다
      * `delta_unsubscribe_dropped` 가 못 봐서 **영구 슬롯 누수**
      * `already_in_pool` 에 없다고 판단해 **매 5분 재SEND** = cycle252 가
        없앤 churn 의 은폐된 부활
      * `[tick_coverage] subscribed=` **분모가 줄어 숫자만 좋아진다**
        = cycle252 「은폐 금지」 계약 위반

    착수 시점 = 8곳(`websocket.py:503/513/565` · `websocket_pool.py:494/505/542/545`
    · `scanner.py:1173`). 전부 `tr_id in TICK_TR_IDS` 로 바꾼다.
    """
    hits = _equality_hits()
    assert hits == [], (
        "TICK 채널 등가 비교가 남아 있다 — 집합 멤버십(`tr_id in TICK_TR_IDS`)으로 "
        f"바꿔라. 잔여 {len(hits)}곳:\n"
        + "\n".join(f"  {r}:{ln}  {txt}" for r, ln, txt in hits)
    )


def test_a3b_guard_actually_detects_a_leftover() -> None:
    """A3b — A3 가 공허하지 않음을 증명한다(가드의 가드).

    실제 소스 한 조각에 등가 비교를 되살려 넣으면 탐지되는지 인-메모리로 확인.
    """
    snippet = "def f(tr_id):\n    return tr_id == TICK_TR_ID\n"
    tree = ast.parse(snippet)
    found = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.Compare)
        and any(isinstance(op, ast.Eq) for op in n.ops)
        and any(
            isinstance(o, ast.Name) and o.id.endswith("TICK_TR_ID")
            for o in [n.left, *n.comparators]
        )
    ]
    assert found, "A3 의 탐지 규칙이 등가 비교를 못 잡는다 = 공허 가드"


# ===========================================================================
# A4/A5 (G5) — 단일 정본 집합
# ===========================================================================
def _collection_literals_with_all_three() -> list[tuple[str, int, str | None, bool]]:
    """세 TR_ID 를 **전부** 담은 컬렉션 리터럴을 찾는다.

    Returns: (rel, lineno, 할당 이름 or None, 모듈 레벨 여부)
    """
    out: list[tuple[str, int, str | None, bool]] = []
    for path in _production_py_files():
        rel = _rel(path)
        if rel == _HANDLER_REL:
            # G10 — 파싱 경로 byte 동일이 계약. `handler.py:400` 의 3채널 튜플은
            # 이 사이클의 집합화 대상이 아니다(면제 근거를 여기 남긴다).
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:  # pragma: no cover
            continue
        module_level_nodes = set()
        for stmt in tree.body:
            for sub in ast.walk(stmt):
                module_level_nodes.add(id(sub))
        # 🔴 Green(2026-09-14) 하네스 결함 시정 — `frozenset({...})` 는 컬렉션
        # 리터럴 **한 개**인데 종전 탐지기는 안쪽 `Set` 과 감싼 `Call` 을 각각
        # 세어 **2** 로 보고했다(그래서 정본 집합을 정확히 하나만 둬도
        # `len(found) == 1` 이 성립할 수 없었다 — Red 시점의 `stale_diagnostics.
        # _TICK_TR_IDS = frozenset({...})` 도 같은 이유로 2로 세어졌다).
        # 감싸인 안쪽 리터럴의 id 를 먼저 모아 두고 건너뛴다.
        wrapped_literal_ids: set[int] = set()
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in ("frozenset", "set", "tuple")
                and len(node.args) == 1
                and isinstance(node.args[0], (ast.Set, ast.Tuple, ast.List))
            ):
                wrapped_literal_ids.add(id(node.args[0]))
        # 할당 이름 역인덱싱
        assigned: dict[int, str] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and len(node.targets) == 1:
                tgt = node.targets[0]
                if isinstance(tgt, ast.Name):
                    assigned[id(node.value)] = tgt.id
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                if node.value is not None:
                    assigned[id(node.value)] = node.target.id
        for node in ast.walk(tree):
            elts = None
            container = node
            if isinstance(node, (ast.Set, ast.Tuple, ast.List)):
                elts = node.elts
            elif (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in ("frozenset", "set", "tuple")
                and len(node.args) == 1
                and isinstance(node.args[0], (ast.Set, ast.Tuple, ast.List))
            ):
                elts = node.args[0].elts
            if elts is None:
                continue
            if isinstance(node, (ast.Set, ast.Tuple, ast.List)) and id(node) in wrapped_literal_ids:
                # 감싼 Call 쪽에서 이미 센다 (이중 계수 금지)
                continue
            values = {
                e.value for e in elts
                if isinstance(e, ast.Constant) and isinstance(e.value, str)
            }
            if not _TICK_TR_ID_LITERALS.issubset(values):
                continue
            name = assigned.get(id(container))
            if name is None and isinstance(node, (ast.Set, ast.Tuple, ast.List)):
                # frozenset({...}) 처럼 한 겹 감싼 경우 부모 Call 이름을 찾는다
                for outer in ast.walk(tree):
                    if (
                        isinstance(outer, ast.Call)
                        and outer.args
                        and outer.args[0] is node
                    ):
                        name = assigned.get(id(outer))
                        container = outer
                        break
            out.append((rel, node.lineno, name, id(container) in module_level_nodes))
    return out


def test_a4_single_canonical_tick_tr_id_set() -> None:
    """A4 (G5) — 세 채널을 담은 컬렉션 리터럴은 소스에 **딱 하나**다.

    현재 `stale_diagnostics.py:76 _TICK_TR_IDS` 가 올바른 형태로 존재하지만
    **함수 지역 변수**라 아무도 import 할 수 없다. 승격 = 모듈 레벨 + 이름
    `TICK_TR_IDS`. **두 번째 집합이 생기면 두 판정이 갈리고, 갈린 순간
    "구독은 A 채널, 해제는 B 채널" 이 된다**(§5-B).

    면제 = `handler.py:400`(G10 파싱 byte 동일) · `routes/realtime.py:81`
    `_PROBE_ALLOWED_TR_IDS`(3채널 중 2개뿐 = 다른 목적, 자연 제외).
    """
    found = _collection_literals_with_all_three()
    assert len(found) == 1, (
        "세 TICK 채널을 담은 컬렉션 리터럴이 1개가 아니다 — 단일 정본이어야 한다.\n"
        + "\n".join(f"  {r}:{ln} name={nm!r} module_level={ml}" for r, ln, nm, ml in found)
    )
    rel, lineno, name, module_level = found[0]
    assert module_level, (
        f"{rel}:{lineno} 정본 집합이 함수 지역이다 — 모듈 레벨로 승격해야 "
        "소비처가 import 할 수 있다"
    )
    assert name == _CANONICAL_SET_NAME, (
        f"{rel}:{lineno} 정본 집합 이름 = {name!r} (기대 {_CANONICAL_SET_NAME!r})"
    )
    # 🔴 Green(적대 검증 M21) — `issubset` 은 "셋을 **포함**하는가" 라 집합을
    # **넓히는** 뮤테이션(`H0STOUP0` 추가 = §7-F 금기)을 못 막았다. 런타임 값까지
    # 정확 일치로 조인다. 상수 3개의 값 자체는 `test_a7` 이 리터럴로 핀한다.
    from src.engine import scanner as _scanner

    assert set(_scanner.TICK_TR_IDS) == _TICK_TR_ID_LITERALS, (
        f"정본 집합이 세 채널과 정확히 같지 않다: {sorted(_scanner.TICK_TR_IDS)} — "
        "시간외 전용 채널(H0STOUP0 등)을 후보에 넣지 않는다(§7-F 금기 8)"
    )
    assert set(_scanner.DEDICATED_TICK_TR_IDS) == {"H0STCNT0", "H0NXCNT0"}, (
        "전용 채널 집합이 KRX·NXT 2종이 아니다 — 통합이 섞이면 매수 축 게이트가 "
        "전 종목에서 참이 되어 틱 매수가 통째로 죽는다"
    )


def test_a4b_stale_diagnostics_no_longer_defines_a_local_set() -> None:
    """A4b — `stale_diagnostics` 의 함수 지역 `_TICK_TR_IDS` 는 사라진다."""
    text = _src(_DIAG_REL)
    assert "_TICK_TR_IDS = frozenset(" not in text, (
        f"{_DIAG_REL} 가 여전히 자기 집합을 정의한다 — 정본을 import 하라"
    )


#: 정본을 써야 하는 소비처 (부록 B (d) + §5-B 공통 원천).
_CANONICAL_CONSUMERS = (
    _WS_REL,
    _POOL_REL,
    _SCANNER_REL,
    _DIAG_REL,
)


#: 정확히 `TICK_TR_IDS` 만 잡는다 — `_TICK_TR_IDS`(구 함수 지역 이름)는 **불통과**.
#: 접두 `_` 를 허용하면 `stale_diagnostics` 가 자기 지역 집합을 그대로 둔 채
#: 초록이 되는 공허 가드가 된다(실측: 첫 실행에서 그 한 케이스만 잘못 통과했다).
_CANONICAL_NAME_RE = re.compile(rf"(?<![A-Za-z0-9_]){_CANONICAL_SET_NAME}\b")


@pytest.mark.parametrize("rel", _CANONICAL_CONSUMERS)
def test_a5_consumers_reference_the_canonical_set(rel: str) -> None:
    """A5 (G5) — 집계 소비처가 정본 집합을 **실제로 읽는다**(`_TICK_TR_IDS` 불통과).

    🔴 Green(적대 검증 M22) — 종전 판정은 소스 텍스트에 이름이 **나타나는가**
    였다. 그래서 "정본 사용을 그만두고 2채널을 하드코딩한 뒤 이름만 **주석**에
    남기는" 뮤테이션이 통과했다(`/sync-docs` 부분문자열 결함과 같은 계열).
    이제 AST 에서 `TICK_TR_IDS` 가 **Load 컨텍스트의 Name 또는 Attribute** 로
    적어도 한 번 나타나는지 본다 — 주석·문자열은 AST 에 남지 않는다.
    """
    tree = _tree(rel)
    used = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == _CANONICAL_SET_NAME:
            if isinstance(node.ctx, ast.Load):
                used += 1
        elif isinstance(node, ast.Attribute) and node.attr == _CANONICAL_SET_NAME:
            if isinstance(node.ctx, ast.Load):
                used += 1
    assert used >= 1, (
        f"{rel} 가 `{_CANONICAL_SET_NAME}` 를 실제로 읽지 않는다(주석·문자열은 "
        "AST 에 없다) — 자기 리터럴을 새로 만들었거나 등가 비교가 남아 있다"
    )


# ===========================================================================
# A6/A7 (G1) — 리졸버 실재 · 동기 · 순수 · 반환 도메인
# ===========================================================================
def test_a6_resolver_exists_and_is_sync() -> None:
    """A6 — `tick_tr_id_for` 가 `scanner` 에 있고 **동기**다.

    async 로 만들면 호출부 7곳(등록) + 9곳(해제)이 전부 await 를 타고, 그중
    `websocket_pool.get_session_status()` 같은 동기 집계까지 오염된다.
    """
    fn = _function(_SCANNER_REL, "tick_tr_id_for")
    assert fn is not None, (
        f"{_SCANNER_REL} 에 `tick_tr_id_for` 미존재 (명세 §3-A — `TICK_TR_ID` "
        "상수 3줄 바로 아래)"
    )
    assert isinstance(fn, ast.FunctionDef), (
        "`tick_tr_id_for` 가 async 다 — 동기 순수 함수여야 한다(§3-A)"
    )


def test_a6b_resolver_is_pure_no_await_no_io() -> None:
    """A6b — 리졸버 본문에 `await`/DB/HTTP 가 없다(A-PURE 관례 승계).

    입력은 **이미 적재된 레지스트리 스냅샷뿐**이다. 여기서 DB 를 치면 5분
    주기 구독 루프가 종목당 1회 왕복을 하게 되고, 실패 시 fail-open 방향이
    "구독을 안 하는" 쪽으로 기울 위험이 생긴다.
    """
    fn = _function(_SCANNER_REL, "tick_tr_id_for")
    if fn is None:
        pytest.fail("A6 선행 실패 — `tick_tr_id_for` 미존재")
    bad: list[str] = []
    for node in ast.walk(fn):
        if isinstance(node, (ast.Await, ast.AsyncFor, ast.AsyncWith)):
            bad.append(f"await/async @L{node.lineno}")
        if isinstance(node, ast.Call):
            src = ast.unparse(node.func)
            if any(k in src for k in ("pg.", "fetch", "execute", "httpx", "request")):
                bad.append(f"I/O 의심 호출 `{src}` @L{node.lineno}")
    assert bad == [], f"리졸버가 순수하지 않다: {bad}"


def test_a7_tick_constants_unchanged() -> None:
    """A7 (G1) — 세 상수 값 불변. cycle257 `_PRESERVED_TICK_CONSTS` 자매 핀."""
    tree = _tree(_SCANNER_REL)
    values: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            tgt = node.targets[0]
            if isinstance(tgt, ast.Name) and isinstance(node.value, ast.Constant):
                if tgt.id.startswith("TICK_TR_ID"):
                    values[tgt.id] = node.value.value
    assert values == {
        "TICK_TR_ID": "H0UNCNT0",
        "TICK_TR_ID_KRX": "H0STCNT0",
        "TICK_TR_ID_NXT": "H0NXCNT0",
    }, f"상수 3개가 바뀌었다 — cycle257 자매 핀도 함께 본다. actual={values!r}"


def test_a7b_resolver_returns_only_the_three_constants() -> None:
    """A7b (G1) — 리졸버의 `return` 이 세 상수(또는 그 별칭)만 돌려준다.

    문자열 리터럴을 직접 return 하면 상수 핀이 무력화된다.
    """
    fn = _function(_SCANNER_REL, "tick_tr_id_for")
    if fn is None:
        pytest.fail("A6 선행 실패 — `tick_tr_id_for` 미존재")
    allowed = {"TICK_TR_ID", "TICK_TR_ID_KRX", "TICK_TR_ID_NXT"}
    bad: list[str] = []
    for node in ast.walk(fn):
        if isinstance(node, ast.Return) and node.value is not None:
            for leaf in ast.walk(node.value):
                if isinstance(leaf, ast.Constant) and isinstance(leaf.value, str):
                    if leaf.value in _TICK_TR_ID_LITERALS:
                        bad.append(f"L{node.lineno} 리터럴 {leaf.value!r}")
                if isinstance(leaf, ast.Name) and leaf.id.startswith("TICK_TR_ID"):
                    if leaf.id not in allowed:
                        bad.append(f"L{node.lineno} 미지 이름 {leaf.id}")
    assert bad == [], f"리졸버 반환이 상수 밖이다: {bad}"


# ===========================================================================
# A8 (G4/INV-2) — HIGH 경로 무손상
# ===========================================================================
def test_a8_high_subscribe_calls_keep_bypass_limit() -> None:
    """A8 (G4 / INV-2) — HIGH 구독 2곳의 `priority="HIGH", bypass_limit=True` 불변.

    보유·익일청산 종목의 시세는 절대 보장이다. 리졸버가 tr_id 인자만 바꾸고
    나머지 키워드는 **글자 그대로** 남아야 한다.
    """
    fn = _function(_SCANNER_REL, "subscribe_filtered_stocks")
    assert fn is not None, f"{_SCANNER_REL} 에 `subscribe_filtered_stocks` 미존재"
    # 🔴 Green(2026-09-14) 하네스 결함 시정 — 종전 탐지기는 `priority="HIGH"` 를
    # 가진 **모든** 호출을 셌다. cycle293 이 채널을 리졸버로 고르면서
    # `tick_tr_id_for(t, priority="HIGH")` 가 같은 키워드를 쓰게 되자 HIGH 호출이
    # 4로 보고됐다(리졸버 2 + 구독 2). 이 가드의 의도는 "**구독 호출** 2곳의
    # `bypass_limit=True` 불변" 이므로 `*.subscribe(...)` 로 좁힌다 — 좁히는 쪽이
    # 가드를 약화시키지 않는다(무관한 호출의 오탐만 없앤다).
    high_calls = []
    for node in ast.walk(fn):
        if not isinstance(node, ast.Call):
            continue
        if not (isinstance(node.func, ast.Attribute) and node.func.attr == "subscribe"):
            continue
        kw = {k.arg: k.value for k in node.keywords if k.arg}
        prio = kw.get("priority")
        if isinstance(prio, ast.Constant) and prio.value == "HIGH":
            bypass = kw.get("bypass_limit")
            high_calls.append(
                isinstance(bypass, ast.Constant) and bypass.value is True
            )
    assert len(high_calls) == 2, (
        f"HIGH 구독 호출이 2곳이 아니다(positions·next_day_clear) — actual={len(high_calls)}"
    )
    assert all(high_calls), "HIGH 구독에서 `bypass_limit=True` 가 사라졌다 (INV-2 위반)"


# ===========================================================================
# A9 (G6) — grace ACK 키 정합
# ===========================================================================
def test_a9_grace_ack_key_goes_through_resolver() -> None:
    """A9 (G6) — `_is_within_grace` 의 ACK 조회 키가 리졸버를 경유한다.

    `_subscribed_at` 는 `(tr_id, tr_key)` 키다(`websocket.py:186`). `H0STCNT0`
    ACK 은 `("H0STCNT0", t)` 에 심긴다. 조회 키를 `(TICK_TR_ID, t)` 로 두면
    `nxt_false` 종목에만 **180초 구독 grace 가 영구 miss** 되어 구독 직후
    stale 판정 → 즉시 강제 재등록 = **cycle252 가 없앤 SEND 폭주의 조용한 부활**.
    """
    text = _src(_SWC_REL)
    assert "ack_map.get((TICK_TR_ID, t))" not in text, (
        f"{_SWC_REL} 의 grace ACK 조회가 `TICK_TR_ID` 하드코딩이다 — "
        "`ack_map.get((tick_tr_id_for(t), t))` 로 바꿔라(G6)"
    )
    assert "tick_tr_id_for" in text, (
        f"{_SWC_REL} 가 리졸버를 전혀 쓰지 않는다 — grace 키·해제 6곳이 "
        "틀린 채널을 가리킨다"
    )


# ===========================================================================
# A10 (G7) — 자기 강화 플리커 차단
# ===========================================================================
def test_a10_ensure_fresh_argument_is_channel_agnostic() -> None:
    """A10 (G7 ①) — `ensure_fresh` 인자가 채널 무관 집합이다.

    현재 인자는 `kis_ws_pool.get_subscribed_tickers()`(= `H0UNCNT0` 필터)다.
    리졸버가 62종목을 `H0STCNT0` 로 옮기면 → 다음 `ensure_fresh` 인자에서
    그 62개가 빠짐 → `_no_feed` 탈락 → `is_no_feed()` False → 리졸버가 다시
    `H0UNCNT0` 판정 → **600s TTL 마다 채널 왕복**(KIS 공지 "비정상 케이스 2:
    무한 등록/해제" 그 자체).
    """
    tree = _tree(_SWC_REL)
    # `x = kis_ws_pool.get_subscribed_tickers()` 로 바인딩된 이름
    channel_filtered: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            tgt = node.targets[0]
            val = node.value
            if (
                isinstance(tgt, ast.Name)
                and isinstance(val, ast.Call)
                and isinstance(val.func, ast.Attribute)
                and val.func.attr == "get_subscribed_tickers"
            ):
                channel_filtered.add(tgt.id)

    calls = [
        n for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == "ensure_fresh"
    ]
    assert calls, f"{_SWC_REL} 에 `ensure_fresh` 호출이 없다"
    for call in calls:
        assert call.args, "`ensure_fresh` 가 인자 없이 불린다"
        arg = call.args[0]
        rendered = ast.unparse(arg)
        offending = isinstance(arg, ast.Name) and arg.id in channel_filtered
        offending = offending or (
            isinstance(arg, ast.Call)
            and isinstance(arg.func, ast.Attribute)
            and arg.func.attr == "get_subscribed_tickers"
        )
        assert not offending, (
            f"{_SWC_REL}:{call.lineno} `ensure_fresh({rendered})` 인자가 "
            "채널 필터된 집합이다 — desired ∪ 보유 같은 채널 무관 집합으로 "
            "바꿔야 자기 강화 플리커가 닫힌다(§6-E)"
        )


# ===========================================================================
# A11 — 미사용 import 제거
# ===========================================================================
def test_a11_routes_realtime_has_no_unused_tick_tr_id_import() -> None:
    """A11 — `routes/realtime.py` 의 함수 지역 `TICK_TR_ID` import 는 전부 사용된다.

    부록 B 「미사용」 = `:400`. 남겨 두면 다음 사람이 "이 함수는 통합 채널만
    본다" 고 오독한다.
    """
    tree = _tree(_ROUTES_REL)
    bad: list[str] = []
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        imported = False
        import_line = 0
        for node in ast.walk(fn):
            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    if alias.name == "TICK_TR_ID" and alias.asname is None:
                        imported = True
                        import_line = node.lineno
        if not imported:
            continue
        used = any(
            isinstance(n, ast.Name) and n.id == "TICK_TR_ID" and isinstance(n.ctx, ast.Load)
            for n in ast.walk(fn)
        )
        if not used:
            bad.append(f"{fn.name} (import @L{import_line})")
    assert bad == [], (
        f"{_ROUTES_REL} 미사용 `TICK_TR_ID` import: {bad} — 제거하라"
    )


# ===========================================================================
# A12 (G3) — 병행 dict 가 `_ticker_to_session` 의 수명에 동행한다
# ===========================================================================
#: `_ticker_to_session` 를 쓰기/삭제하는 메서드 (§5-C: "같은 시점에 쓰고 pop 한다")
_POOL_LIFECYCLE_METHODS = (
    "__init__",
    "subscribe",
    "unsubscribe",
    "unsubscribe_all",
    "unsubscribe_in_pool",
    "disable_quote_session",
    "stop",
)


def _dict_mutation_count(fn, attr: str) -> int:
    """`self.<attr>` 를 **변이**하는 지점 수 (대입 · pop/clear/setdefault · del)."""
    n = 0

    def _is_target(node) -> bool:
        return isinstance(node, ast.Attribute) and node.attr == attr

    for node in ast.walk(fn):
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Subscript) and _is_target(tgt.value):
                    n += 1
        elif isinstance(node, ast.Delete):
            for tgt in node.targets:
                if isinstance(tgt, ast.Subscript) and _is_target(tgt.value):
                    n += 1
        elif isinstance(node, ast.Call):
            f = node.func
            if (
                isinstance(f, ast.Attribute)
                and f.attr in ("pop", "clear", "setdefault", "update")
                and _is_target(f.value)
            ):
                n += 1
    return n


@pytest.mark.parametrize("method", _POOL_LIFECYCLE_METHODS)
def test_a12_parallel_dict_accompanies_ticker_to_session(method: str) -> None:
    """A12 (G3) — `_ticker_to_tr_id` 가 `_ticker_to_session` 의 모든 수명 지점에 동행.

    한 곳이라도 빠지면 유령 항목이 남아 (a) 이중 채널 오탐 (b) 진짜 이중
    채널 미탐 둘 다 가능해진다. `_ticker_to_session` **키는 바꾸지 않는다**(C-1)
    — 단일 키가 곧 「이중 채널 금지」의 구조적 강제 장치다(§5-A).

    🔴 Green(적대 검증 M8) — 종전 판정은 `ast.unparse(fn)` 부분문자열이라
    **메서드 안에 한 곳이라도 남아 있으면 초록**이었다(`subscribe` 의 5개 대입
    중 하나만 지우는 뮤테이션이 그대로 통과했다 = 보유·익일청산 종목의 병행
    dict 공백). 이제 **변이 횟수**를 센다.
    """
    fn = _function(_POOL_REL, method)
    assert fn is not None, f"{_POOL_REL} 에 `{method}` 미존재"
    body = ast.unparse(fn)
    session_n = _dict_mutation_count(fn, "_ticker_to_session")
    if session_n == 0:
        if "_ticker_to_session" not in body:
            pytest.skip(f"`{method}` 가 `_ticker_to_session` 를 안 만진다 — 동행 불요")
        # `__init__` 처럼 **선언만** 하는 자리 — 선언도 동행해야 한다(둘 중 하나만
        # 없으면 `getattr` 폴백이 조용히 유령 상태를 만든다).
        assert "_ticker_to_tr_id" in body, (
            f"{_POOL_REL}::{method} 가 `_ticker_to_session` 만 선언한다 — "
            "병행 dict 선언 누락(§5-C)"
        )
        return
    tr_id_n = _dict_mutation_count(fn, "_ticker_to_tr_id")
    assert tr_id_n >= session_n, (
        f"{_POOL_REL}::{method} — `_ticker_to_session` 변이 {session_n}회 vs "
        f"`_ticker_to_tr_id` {tr_id_n}회. 동행 누락(§5-C): 한쪽만 남으면 유령 "
        "항목이 이중 채널 오탐·미탐을 동시에 만든다"
    )


def test_a12c_routes_orphan_release_pops_both_dicts() -> None:
    """A12c (적대 검증 F6) — routes 의 고아 라우팅 해제도 병행 dict 를 pop 한다.

    `_release_routing_if_orphaned` 는 `websocket_pool.py` 밖이라 A12 의 순회
    대상이 아니었다. 그 자리가 `_ticker_to_session` 만 비우면
    `stale_watcher_core._actual_or_desired_tick_tr_id` 가 **구독 0건인 종목에
    유령 채널을 "실제 채널" 로 보고**한다.
    """
    fn = _function(_ROUTES_REL, "_release_routing_if_orphaned")
    assert fn is not None, f"{_ROUTES_REL} 에 `_release_routing_if_orphaned` 미존재"
    body = ast.unparse(fn)
    assert "_ticker_to_session" in body and "_ticker_to_tr_id" in body, (
        f"{_ROUTES_REL}::_release_routing_if_orphaned 가 병행 dict 를 함께 "
        "정리하지 않는다(F6)"
    )


def test_a12b_ticker_to_session_key_is_not_rekeyed() -> None:
    """A12b (C-1 · 금기 6) — `_ticker_to_session` 을 `(tr_id, tr_key)` 로 재키잉하지 않는다.

    재키잉하면 `subscribe`/`unsubscribe`/`unsubscribe_all`/
    `resend_subscribe_for_ticker`/`unsubscribe_in_pool`/`disable_quote_session`/
    `get_subscriptions_by_session`/`remove_session` 8개 + routes 고아 판정
    3헬퍼 + cycle221 VI 주석 규약이 **동시에** 무너진다(§5-D).
    """
    tree = _tree(_POOL_REL)
    bad: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Subscript):
            if (
                isinstance(node.value, ast.Attribute)
                and node.value.attr == "_ticker_to_session"
                and isinstance(node.slice, ast.Tuple)
            ):
                bad.append(f"L{node.lineno} {ast.unparse(node)}")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in ("pop", "get") and isinstance(node.func.value, ast.Attribute):
                if node.func.value.attr == "_ticker_to_session" and node.args:
                    if isinstance(node.args[0], ast.Tuple):
                        bad.append(f"L{node.lineno} {ast.unparse(node)}")
    assert bad == [], f"`_ticker_to_session` 재키잉 흔적(금기 6): {bad}"


# ===========================================================================
# A13 (§9-A) — 신규 마커
# ===========================================================================
@pytest.mark.parametrize("marker", _NEW_MARKERS)
def test_a13_new_markers_exist(marker: str) -> None:
    """A13 — §9-A 마커 5종이 소스에 실재한다.

    `[tick_channel_dual_detected]` 는 §4-C 의 `scheduler.py` 풀 우회 2곳
    (`:1382` 익일청산 시가 · `:2728` 매수 직후)을 **드러내는 유일한 수단**이다.
    이 사이클은 그 두 줄을 고치지 않고 **보이게만** 한다.
    """
    found = [
        _rel(p) for p in _production_py_files()
        if marker in p.read_text(encoding="utf-8")
    ]
    assert found, f"마커 {marker} 가 소스에 없다 (§9-A)"


# ===========================================================================
# A14 (§8-B) — 킬스위치는 `system_config` 축 + 즉시 반영
# ===========================================================================
def test_a14_kill_switch_key_is_system_config_axis() -> None:
    """A14 (§8-B) — 킬스위치 키가 `system_config` 에 있고 전략 축으로 새지 않는다.

    🔴 **cycle287 의 실패를 반복하지 않는다** — 그 사이클은 킬스위치 2개를
    `param_catalog` 미등재로 만들어 `PUT /api/strategies/{id}/params` 가
    `unknown_key` 422 를 돌려줬다 = **장중에 끌 수 없었다.** 리졸버는 전략별
    설정이 아니라 인프라 축이므로 `system_config` 가 정답이고, 그 대신
    **재시작 없이 먹히는 재조회 경로**를 같은 커밋에 넣어야 한다(A14b).
    """
    sysconf = _src("src/db/system_config.py")
    assert _KILL_SWITCH_KEY in sysconf, (
        f"`{_KILL_SWITCH_KEY}` 가 `src/db/system_config.py` 에 없다 (§8-B)"
    )
    # 전략 파라미터 축 오염 0 (전략 7파일·param_catalog 는 A1 sha 가 이미 봉인)
    for rel in ("src/engine/param_catalog.py", "src/engine/strategy_base.py"):
        assert _KILL_SWITCH_KEY not in _src(rel), (
            f"{rel} 에 킬스위치 키가 샜다 — 인프라 축(system_config)이어야 한다"
        )


def test_a14b_mode_module_has_a_restartless_refresh_path() -> None:
    """A14b (§8-B) — 모드 재조회가 **반복 호출 가능**해야 한다(once-latch 금지).

    `_load_strategy_config` 의 `_config_loaded` 처럼 "프로세스당 1회" 로 만들면
    `off` 가 다음 재시작에만 닿는다 = 킬스위치가 아니다. 그리고 D6 가 보유 중
    장중 재시작을 금지하므로 **그 재시작은 오지 않는다.**
    """
    path = _ROOT / _MODE_REL
    assert path.exists(), (
        f"{_MODE_REL} 미존재 — 킬스위치 모드 leaf 를 같은 커밋에 넣어라(§8-B)"
    )
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = {
        n.name for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert "current_mode" in names, f"{_MODE_REL}: 동기 `current_mode()` 필요"
    assert "refresh_mode" in names, f"{_MODE_REL}: `async refresh_mode()` 필요"
    text = path.read_text(encoding="utf-8")
    assert "_config_loaded" not in text, (
        f"{_MODE_REL} 에 프로세스당 1회 래치가 있다 — 킬스위치가 재시작을 요구하면 "
        "D6(보유 중 장중 재시작 금지) 때문에 영원히 못 끈다"
    )


# ===========================================================================
# A15 (C-2 / §6-C) — 시각 리터럴 0건
# ===========================================================================
_TIME_LITERAL_RE = re.compile(r"\btime\s*\(\s*\d+\s*,")


def test_a15_no_clock_literals_in_resolver_or_mode() -> None:
    """A15 (C-2) — 판정은 **출처(provenance) 검사**이지 시간 창이 아니다.

    오염 창의 양끝(07:45~08:08)이 일정 파생값이고 그 일정은 이미 두 번 움직였다
    (일봉 16:00→18:10→20:30, basics 16:10 vs 부팅 07:53). 시각 리터럴을 넣으면
    일정이 또 움직이는 날 조용히 틀린다. 판별자는
    `raw ? 'cptt_trad_tr_psbl_yn'` 존재 여부다(§6-C 1안).
    """
    fn = _function(_SCANNER_REL, "tick_tr_id_for")
    if fn is None:
        pytest.fail("A6 선행 실패 — `tick_tr_id_for` 미존재")
    seg = ast.unparse(fn)
    assert not _TIME_LITERAL_RE.search(seg), (
        "리졸버에 `time(H, M)` 시각 리터럴이 있다 — 출처 검사로 판정하라(C-2)"
    )
    mode_path = _ROOT / _MODE_REL
    if mode_path.exists():
        assert not _TIME_LITERAL_RE.search(mode_path.read_text(encoding="utf-8")), (
            f"{_MODE_REL} 에 시각 리터럴이 있다 — hold-down 창 길이를 정하지 않는다"
            "(§6-D: 전환 빈도를 과거로 소급 측정할 수 없다)"
        )


def test_a15b_provenance_key_is_actually_queried() -> None:
    """A15b (§6-C) — 출처 판별자가 실제로 DB 에서 조회된다.

    W2(`_full_universe_load_krx_primary`)가 KRX raw 로 `nxt_tradable=False` 를
    2,674종목에 **도장**하고 W1(basics_refresh)이 7~22분 뒤 복원한다. 그 창
    안에 `TIME_PRESUBSCRIBE`(07:59)가 들어 있어, 값을 그대로 믿으면 **진짜
    NXT 종목 ≈420개**를 NXT 체결을 실을 수 없는 채널로 보낸다. W2 도장에는
    `cptt_trad_tr_psbl_yn` 키가 **없다**(2,674/2,674 정확 일치).
    """
    text = _src("src/db/stock_master.py")
    assert "cptt_trad_tr_psbl_yn" in text, (
        "`src/db/stock_master.py` 가 출처 키를 조회하지 않는다 — "
        "`raw ? 'cptt_trad_tr_psbl_yn'` 검사가 없으면 07:59 사전 구독이 "
        "≈420종목을 틀린 채널로 보낸다(§6-C)"
    )


# ===========================================================================
# A16 (§4-C · 절대 규칙 3) — scheduler 풀 우회는 관측만
# ===========================================================================
def test_a16_scheduler_does_not_call_the_resolver() -> None:
    """A16 (§4-C, D-5 권고 (가)) — `scheduler.py` 는 이 사이클에서 무접촉이다.

    `:1382`(익일청산 시가) · `:2728`(매수 직후)의 풀 우회 직접 구독은 여전히
    `H0UNCNT0` 로 나간다. 처분은 **고치기가 아니라 드러내기** —
    `_ticker_to_tr_id` 가 `[tick_channel_dual_detected]` WARNING 으로 올린다.
    실제 시정은 별도 승인(cycle292 착지로 라인 여유 174줄 확보됨).
    """
    text = _src("src/engine/scheduler.py")
    assert "tick_tr_id_for" not in text, (
        "`scheduler.py` 가 리졸버를 호출한다 — 절대 규칙 3(무접촉) 위반. "
        "§4-C 풀 우회 2곳 시정은 별도 승인 대상이다"
    )


# ===========================================================================
# A17 (G8) — 해제 6곳이 리졸버를 경유한다
# ===========================================================================
#: 부록 B (b) 「해제/재전송」 중 이 사이클이 바꾸는 자리.
_UNSUBSCRIBE_SITES = (
    (_ORDER_ENGINE_REL, "_unsubscribe_if_no_other_strategy"),
    ("src/engine/stale_universe_guard.py", "evaluate_universe_guard"),
    ("src/engine/stale_session_recovery.py", "delta_unsubscribe_dropped"),
)


@pytest.mark.parametrize(("rel", "func"), _UNSUBSCRIBE_SITES)
def test_a17_unsubscribe_sites_resolve_the_channel(rel: str, func: str) -> None:
    """A17 (G8) — 해제가 그 종목의 **실제** 채널로 나간다.

    틀린 채널로 해제하면 `OPSP0003 UNSUBSCRIBE ERROR not found!` 스팸(cycle215~218
    이 잡은 그 ERROR)이 나고, 구 채널 튜플이 **영구 고아**로 41 슬롯을 잠식한다.
    특히 `stale_session_recovery.delta_unsubscribe_dropped` 가 빠지면 유니버스에서
    이탈한 종목이 **영원히 해제되지 않는다 = 실제 슬롯 누수**다.

    ⚠️ `order_engine.py:1949` — 원안이 적은 `:1104` 는 2026-09-05 줄번호다.
    HEAD 의 그 자리는 cycle276 LLM 평가 배선(`:1080-1110`)이므로 함수 이름으로
    찾는다(줄번호로 찾으면 엉뚱한 곳을 고친다).
    """
    fn = _function(rel, func)
    assert fn is not None, f"{rel} 에 `{func}` 미존재"
    body = ast.unparse(fn)
    assert "subscribed_tick_tr_id" in body, (
        f"{rel}::{func} 가 `subscribed_tick_tr_id` 를 경유하지 않는다 — "
        "`TICK_TR_ID` 고정 해제는 OPSP0003 스팸 + 영구 고아 튜플을 만든다(G8)"
    )
    # 🔴 Green(적대 검증 F4/MEDIUM-3) — **적용형 리졸버는 금지**다.
    # `tick_tr_id_for` 는 순수 함수가 아니라 §6-D 하루 1회 전환 예산
    # (`_channel_applied`/`_channel_flipped_today`)을 변이한다. 사라지는 종목의
    # 해제가 그 예산을 먹으면 같은 날 재구독이 분류와 반대 채널로 나간다.
    assert "tick_tr_id_for(" not in body, (
        f"{rel}::{func} 가 적용형 리졸버 `tick_tr_id_for` 를 부른다 — 해제는 "
        "판정이 아니라 사실을 따라야 하고, 그 호출은 전환 예산을 소모한다"
    )


# ===========================================================================
# A18~A22 — cycle293 Green(적대 검증 시정)이 새로 세운 계약
# ===========================================================================
def _code_only(fn) -> str:
    """docstring 을 제외한 함수 **코드**만 unparse (주석·설명이 판정에 섞이지 않게)."""
    import copy

    clone = copy.deepcopy(fn)
    if (
        clone.body
        and isinstance(clone.body[0], ast.Expr)
        and isinstance(clone.body[0].value, ast.Constant)
        and isinstance(clone.body[0].value.value, str)
    ):
        clone.body = clone.body[1:] or [ast.Pass()]
    return ast.unparse(clone)


def test_a18_buy_gate_reads_the_subscription_fact_not_the_resolver() -> None:
    """🔴 A18 — 매수 축 게이트는 **코호트**를 읽는다 (cycle294 §6-E 본문 교체).

    ## 구 단언(2단계)과 그것이 3단계에서 틀리게 된 이유

    cycle293 은 이 자리에서 「게이트가 **구독 사실**(`_ticker_to_tr_id` →
    `applied_tick_channel` → `DEDICATED_TICK_TR_IDS`)을 읽어라」를 단언했다.
    2단계에서 그 단언은 옳았다 — 그때 전용 채널로 옮겨지는 종목은 통합 채널에서
    프레임이 **0건**이던 `nxt_false` 코호트뿐이었고, 따라서 「전용 채널에 있다」
    ≡ 「오늘 프레임이 새로 들어오는 종목이다」 였다.

    🔴 **3단계가 그 동치를 깬다.** cycle294 는 통합 채널을 없애고 `nxt_true` 를
    포함한 **모든** 종목을 전용 채널로 보낸다. 구 술어는 전 종목에 대해 참이 되어
    momentum·volatility_breakout·long_tail_volatility·bull_flag_breakout·
    vcp_breakout **5전략의 틱 매수가 통째로 죽는다**(그 5전략은 틱이 유일 매수
    경로다). 오케스트레이션 절대 규칙 5 가 이 사이클 최대 위험으로 지목한 것이
    바로 이 오분류다.

    ⇒ 술어의 **원래 의도**인 코호트(`scanner.tick_buy_cohort_blocked`)로 교체한다.
    `nxt_true` 종목은 어제도 통합 채널에서 프레임을 받았고 매수 평가를 이미 받고
    있었다 — 3단계는 그들에게 **채널만** 바꾸므로 매수 평가가 계속돼야 한다.

    ## 구 계약 중 **살아남는 것** (지우면 안 되는 이유)

    * `tick_tr_id_for(` 금지 — 적용형 리졸버는 순수 함수가 아니라 §6-D 하루 1회
      전환 예산(`_channel_applied`/`_channel_flipped_today`)을 변이한다. `on_tick`
      이 틱마다 부르므로 관측이 예산을 먹는다.
    * **모드를 보지 않는다** — 킬스위치 `off` 는 이미 전용 채널에 올라간 구독을
      되돌리지 않으므로(cycle294 §9-B), 게이트가 모드를 읽으면 「사고 중에 누르는
      안전 조치가 5전략의 매수를 그 코호트에 열어 준다」. cycle293 적대 검증
      CRITICAL 의 재현이다. 이제는 구조적으로 불가능하다 — 술어가 모드를 인자로도
      전역으로도 받지 않는다.

    자매 = `test_cycle294_ast_stage3.py::test_a15_cycle293_a18_is_superseded_not_deleted`
    (이 함수의 **삭제**를 막는다) · `::test_a11_*`(술어에 채널 축 이름 0건) ·
    `test_cycle294_stage3.py::test_d3_*`(100종목 전원 전용 채널 → 매수 호출 집합이
    `nxt_true` 와 정확히 일치).
    """
    fn = _function("src/engine/risk.py", "_tick_buy_eval_blocked_by_channel")
    assert fn is not None, "risk.py 에 `_tick_buy_eval_blocked_by_channel` 미존재"
    body = _code_only(fn)
    assert "tick_tr_id_for(" not in body, (
        "매수 축 게이트가 적용형 리졸버를 부른다 — (a) 킬스위치 `off` 에서 게이트가 "
        "풀리는데 구독은 전용 채널에 남아 있고 (b) 틱마다 §6-D 전환 예산을 소모한다"
    )
    assert "tick_buy_cohort_blocked" in body, (
        "게이트가 코호트 술어(`scanner.tick_buy_cohort_blocked`)를 읽지 않는다 — "
        "3단계는 전 종목이 전용 채널이라 채널 축 술어는 5전략 매수를 통째로 죽인다"
    )
    for banned in ("_ticker_to_tr_id", "applied_tick_channel", "DEDICATED_TICK_TR_IDS"):
        assert banned not in body, (
            f"게이트에 채널 축 이름 `{banned}` 이 남아 있다 — 3단계에서 그 축은 전 "
            "종목에 참이라 매수를 전부 닫는다(cycle294 §6-C)"
        )


def test_a19_flip_marker_is_capped() -> None:
    """A19 — `[tick_channel_flip]` 은 cap 을 거친다.

    `same_day_blocked=1` 분기는 일시적 이벤트가 아니라 **지속 상태**라(차단 시
    `_channel_applied` 를 바꾸지 않는다) 무cap 이면 `risk.on_tick` 계열에서
    도달할 때 틱당 1행이 된다 — cycle237(donchian 청산 로그 하루 1만 행) 계열.
    """
    fn = _function(_SCANNER_REL, "_emit_channel_flip")
    assert fn is not None, "`_emit_channel_flip` 미존재"
    body = _code_only(fn)
    assert "_channel_emit_cap" in body and "emit_once" in body, (
        "cycle293 마커 5종 중 이 하나만 cap 없이 `logger.warning` 을 직접 부른다"
    )


def test_a20_dual_detection_is_a_session_wide_scan() -> None:
    """🔴 A20 — 이중 채널 검출은 **전 세션 `_subscriptions` 전수 대조**다.

    §4-C 는 이 관측에 "`scheduler.py:1382`·`:2728` 풀 우회 2곳을 드러내는 유일한
    수단" 을 맡겼는데, `WebsocketPool.subscribe` 의 중복 분기 안에 두면 그 두
    줄이 `_ticker_to_session` 을 건드리지 않으므로 **구조적으로 도달하지
    못한다**(종전 구현이 자기가 지킨다고 적은 것을 지키지 못했다).
    """
    fn = _function(_POOL_REL, "detect_dual_tick_channels")
    assert fn is not None, (
        f"{_POOL_REL} 에 `detect_dual_tick_channels` 미존재 — 이중 채널 검출이 "
        "다시 `subscribe` 중복 분기 안으로 들어갔다(공허 가드 재발)"
    )
    body = _code_only(fn)
    assert "_subscriptions" in body and "_quotes" in body, (
        "전 세션 `_subscriptions` 를 훑지 않는다"
    )
    assert "[tick_channel_dual_detected]" in body

    sub = _function(_POOL_REL, "subscribe")
    sub_body = _code_only(sub)
    assert "[tick_channel_dual_detected]" not in sub_body, (
        "`subscribe` 중복 분기가 다시 dual 마커를 쓴다 — 그 자리는 '요청 거부'"
        "(`[tick_channel_request_denied]`)이고 정상 운영에서도 뜬다. 두 마커를 "
        "합치면 §8-A S1 진행 게이트 'dual 0건' 이 달성 불가가 된다"
    )

    # 5분 `_scan_loop` 에서 실제로 불린다(정의만 있고 호출자가 없으면 공허하다).
    scanner_src = _src(_SCANNER_REL)
    assert "detect_dual_tick_channels()" in scanner_src, (
        "전수 대조 함수를 아무도 부르지 않는다"
    )


def test_a21_probe_exclusion_has_a_lifecycle() -> None:
    """A21 — 프로브 제외 등록에 **회수 경로**가 있다(수명 주석과 코드 일치).

    적대 검증 HIGH — 종전 주석은 수명이 "20:00 `unsubscribe_all` 과 같다" 고
    적었지만 그 함수는 집합을 비우지 않았다. cycle293 이 같은 채널을 실 구독에
    쓰기 시작했으므로, 남은 항목은 **라이브 구독을 은폐**한다.
    """
    ws_src = _src(_WS_REL)
    for name in ("register_probe_exclusion", "unregister_probe_exclusion",
                 "is_probe_excluded", "reset_probe_exclusions"):
        assert f"def {name}(" in ws_src, f"{_WS_REL} 에 `{name}` 미존재"

    for method in ("unsubscribe_all", "stop"):
        fn = _function(_POOL_REL, method)
        assert fn is not None, f"{_POOL_REL} 에 `{method}` 미존재"
        assert "reset_probe_exclusions" in ast.unparse(fn), (
            f"{_POOL_REL}::{method} 가 프로브 제외 등록을 회수하지 않는다 — "
            "다음 사이클의 실 구독이 그 튜플과 같은 식별자라 집계에서 사라진다"
        )

    # 집계 4곳이 원시 집합 멤버십이 아니라 헬퍼를 경유한다(날짜 경과 자기 회수).
    pool_tree = _tree(_POOL_REL)
    raw = [
        n.lineno for n in ast.walk(pool_tree)
        if isinstance(n, ast.Name) and n.id == "PROBE_EXCLUDED_TUPLES"
    ]
    assert raw == [], (
        f"{_POOL_REL} 이 제외 집합을 직접 읽는다(L{raw}) — 수명 dict 와 갈려 "
        "전날 잔존 항목이 라이브 구독을 은폐한다. `is_probe_excluded()` 경유"
    )


def test_a22_registry_is_warmed_before_the_resolver_runs() -> None:
    """🔴 A22 — 구독 전에 `ensure_fresh` 로 그 사이클 대상 전체를 분류한다.

    적대 검증 H1 — `ensure_fresh` 의 유일한 호출자가 `stale_watcher_core`
    (120초 루프, 인자 = `subscribed ∪ 보유·익일청산`)이면 **아직 구독하지 않은
    후보는 원리상 분류될 수 없다**. 07:59 사전 구독의 LOW 후보 전부가 판정 불가
    → 통합 확정 → 다음 사이클부터 `already_in_pool` skip 이 리졸버 호출보다
    앞이라 그날 다시 판정되지 않는다 = 리졸버가 실효 코호트를 통째로 놓친다.
    """
    fn = _function(_SCANNER_REL, "subscribe_filtered_stocks")
    assert fn is not None, "`subscribe_filtered_stocks` 미존재"
    body = _code_only(fn)
    assert "ensure_fresh" in body, (
        "구독 전에 no_feed 레지스트리를 덥히지 않는다 — 07:59 사전 구독 코호트가 "
        "판정 불가로 통째로 빠진다(H1)"
    )
    lines = body.splitlines()
    warm = next(i for i, ln in enumerate(lines) if "ensure_fresh" in ln)
    resolve = next(
        (i for i, ln in enumerate(lines) if "tick_tr_id_for(" in ln), None,
    )
    assert resolve is not None, "리졸버 호출이 사라졌다"
    assert warm < resolve, (
        "`ensure_fresh` 가 리졸버 호출보다 뒤에 있다 — 그 사이클의 판정은 여전히 "
        "차가운 레지스트리를 본다"
    )

