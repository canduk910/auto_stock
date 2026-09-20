"""cycle328 — `execute_sell` 접수 후 구간 통합이 **의존하는 전제**를 구조로 봉인한다.

설계 카드 = `_workspace/refactor/2026-09-20_step1_card.md`

## 이 파일이 지키는 것

1단계는 매도 주 경로·폴백 경로에 복제돼 있던 「체결통보 선행 체크 + PENDING INSERT +
cycle327 ⓑ 경계」를 `_persist_sell_pending_after_send` 한 곳으로 모았다.
그 추출이 **행위 보존**인 근거는 두 가지 구조적 사실이고, 둘 다 테스트로는 안 잡힌다.

### 전제 1 — 매핑 5종과 헬퍼 호출 사이에 `await` 가 0건이다

루트 `CLAUDE.md` 금기: 「주문번호 매핑 등록은 `place_order` 응답 직후 **동기 영역**,
`await insert_trade` 진입 **전**」. 헬퍼 호출을 매핑 앞으로 옮기거나 그 사이에 `await` 를
끼우면 이 금기가 깨지는데, **기존 회귀 중 어느 것도 그것을 붉히지 못한다**
(카드의 돌연변이 M7 — 그물 없음).

### 전제 2 — 헬퍼 본문의 **최초 양보점**이 `_insert_pending_or_absorb_race` 다

`await coro` 는 코루틴을 만들어 **첫 진짜 suspension 까지 동기로 구동**한다. 그래서
`await self._persist_sell_pending_after_send(...)` 라는 토큰이 약 28줄 앞으로 와도,
이벤트 루프에 제어를 넘기기 전에 실행되는 문장 집합은 추출 전후 **동일**하다.

🔴 **이 성질은 헬퍼 앞부분에 `await` 가 없다는 사실에만 의존한다.** 장래에 헬퍼 맨 위로
비동기 관측 호출 한 줄이 들어가면 양보점이 앞당겨져 금기가 조용히 깨진다
(카드의 돌연변이 M8 — 그물 없음).

### 전제 3 — 경계가 호출부 문맥이 아니라 헬퍼 자신에게 있다

두 호출부는 예외가 샜을 때의 **피해 모양이 다르다** — 주 경로는 `except Exception` 이
받아 재시도 루프로 되돌아가 **이미 판 것을 다시 팔고**, 폴백 경로는 `except KisApiError`
안이라 non-`KisApiError` 를 못 받아 `execute_sell` 을 통째로 뚫고 **`risk.on_tick` 으로
전파된다**(그 틱의 다른 종목 손절 평가도 함께 사라진다). 호출부가 어디에 있든 안전한
이유는 경계가 헬퍼 자신의 `except Exception` 이기 때문이다.

## 공허 통과 방지

부정 단언(「0건이다」)만 두면 대상이 사라져도 초록이다. 그래서 각 조항에
**양성 대조군**(대상이 실제로 존재하는가)을 함께 둔다.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_SRC = Path(__file__).resolve().parents[3] / "src" / "engine" / "order_engine.py"
_HELPER = "_persist_sell_pending_after_send"   # 경계 래퍼(매도 전용)
_BUY_HELPER = "_persist_buy_pending_after_send"  # 경계 래퍼(매수 전용, cycle335)
_CORE = "_persist_pending_after_send"          # 4경로 공용 코어(cycle334)
_MAPPING_TARGETS = ("_order_qty", "_order_strategy", "_order_ticker")

#: 축별 경계 래퍼 — 두 축이 **같은 구조 계약**을 진다(cycle335 가 매수를 더했다).
#: 🔴 한 축만 검사하면 다른 축의 경계가 조용히 좁혀지거나 사라진다.
_BOUNDARY_WRAPPERS = [
    pytest.param(_HELPER, "매도", id="sell"),
    pytest.param(_BUY_HELPER, "매수", id="buy"),
]


def _tree() -> ast.Module:
    return ast.parse(_SRC.read_text(encoding="utf-8"))


def _func(name: str) -> ast.AsyncFunctionDef:
    for node in ast.walk(_tree()):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == name:
            return node
    raise AssertionError(f"`{name}` 을 찾지 못했다 — 가드의 대상이 사라졌다")


def _calls_named(fn: ast.AST, name: str) -> list[int]:
    """`self.<name>(...)` 호출의 lineno (오름차순).

    🔴 `attr == name` **정확 일치**다 — 접두/부분 일치로 바꾸면
    `_persist_pending_after_send` 가 `_persist_buy_pending_after_send` 를 함께 세어
    「코어를 직접 부르지 않는다」 단언이 공허해진다.
    """
    out = []
    for n in ast.walk(fn):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) \
                and n.func.attr == name:
            out.append(n.lineno)
    return sorted(out)


def _helper_call_linenos(fn: ast.AST) -> list[int]:
    return _calls_named(fn, _HELPER)


def _core_call_linenos(fn: ast.AST) -> list[int]:
    """4경로 공용 코어 `_persist_pending_after_send` 호출 lineno."""
    return _calls_named(fn, _CORE)


def _mapping_assign_linenos(fn: ast.AST) -> list[int]:
    """`self._order_qty[...] = ...` 형태 대입의 lineno."""
    out = []
    for n in ast.walk(fn):
        if not isinstance(n, ast.Assign):
            continue
        for tgt in n.targets:
            if not isinstance(tgt, ast.Subscript):
                continue
            val = tgt.value
            if isinstance(val, ast.Attribute) and val.attr in _MAPPING_TARGETS:
                out.append(n.lineno)
    return sorted(out)


def _await_linenos(fn: ast.AST) -> list[int]:
    return sorted(n.lineno for n in ast.walk(fn) if isinstance(n, ast.Await))


# ---------------------------------------------------------------------------
# 양성 대조군 — 대상이 실제로 있는가 (없으면 아래 부정 단언이 공허하다)
# ---------------------------------------------------------------------------
def test_g328_0a_helper_exists():
    """헬퍼가 존재하고 `async def` 다."""
    fn = _func(_HELPER)
    assert fn.name == _HELPER


def test_g328_0b_helper_is_called_exactly_twice_from_execute_sell():
    """호출부는 매도 주 경로·폴백 **정확히 2곳**이다.

    3곳이 되면 이 가드의 순서 단언이 그 신규 경로를 안 본 채 통과할 수 있다.
    """
    calls = _helper_call_linenos(_func("execute_sell"))
    assert len(calls) == 2, f"호출부 {len(calls)}곳 (기대 2곳): {calls}"


def test_g328_0c_core_is_shared_by_all_four_paths():
    """🔴 **4경로가 같은 코어를 쓰고, 축마다 경계 래퍼가 하나씩 있다.**

    ⚠️ 이 케이스는 두 번 재조준됐다. 1단계(cycle328)에서는 「헬퍼가 `execute_buy`
    에서 **안** 불린다」, 2단계(cycle334)에서는 「`execute_buy` 가 코어를 2곳에서
    직접 부른다」였다. cycle335 가 매수 경계를 세우면서 그 직접 호출이 래퍼로
    바뀌었다. **매번 지우지 않고 대체하는 이유** = 지우면 "매수 축이 승격돼 있는가" 를
    아무도 안 보게 되고, 나중에 누가 매수 2곳을 인라인으로 풀어도 조용히 통과한다.

    계약 = 접수 후 PENDING 영속화는 **코어 하나**가 하고, 그 코어를 축별 래퍼
    **정확히 2곳**(매수 1 + 매도 1)이 부른다. 두 `execute_*` 는 코어를 **직접 부르지
    않는다** — 직접 부르면 그 경로만 경계 없이 돌아 cycle327 결함이 되살아난다.

    🔴 이 구조가 `4곳 → 1코어 + 축별 경계 2` 라는 성과 그 자체다.
    """
    for axis, fn_name, wrapper_name in (
        ("매수", "execute_buy", _BUY_HELPER),
        ("매도", "execute_sell", _HELPER),
    ):
        wrapper_calls = _calls_named(_func(fn_name), wrapper_name)
        assert len(wrapper_calls) == 2, (
            f"`{fn_name}` 의 {axis} 경계 래퍼 호출이 {len(wrapper_calls)}곳 "
            f"(기대 2곳 = 주·폴백): {wrapper_calls}. 축이 승격되지 않았거나 "
            "다시 인라인으로 풀렸다"
        )
        assert len(_core_call_linenos(_func(wrapper_name))) == 1, (
            f"{axis} 경계 래퍼가 코어를 정확히 한 번 부르지 않는다"
        )
        assert _core_call_linenos(_func(fn_name)) == [], (
            f"`{fn_name}` 이 코어를 직접 부른다 — 그 경로는 접수 후 경계가 없다"
        )


def test_g328_0d_core_does_not_close_the_boundary():
    """🔴 코어는 **경계를 닫지 않는다** — 예외를 그대로 전파한다.

    경계는 호출자 층의 책임이고 축마다 래퍼가 하나씩 닫는다
    (`_persist_buy_pending_after_send` · `_persist_sell_pending_after_send`).

    🔴 코어에 `try` 를 들이면 **두 래퍼의 `except` 가 영영 도달 불가**가 된다.
    그러면 경계가 어느 층에 있는지 알 수 없어지고, 래퍼의 `except` 를 좁히거나
    지우는 회귀가 **무증상**이 된다(그 둘이 이 계열 결함의 실제 재발 경로다).
    """
    fn = _func(_CORE)
    tries = [n for n in ast.walk(fn) if isinstance(n, ast.Try)]
    assert not tries, (
        f"코어에 `try` 가 {len(tries)}개 있다 — 경계를 코어로 내리면 축별 래퍼의 "
        "`except` 가 도달 불가가 되어 좁히기·지우기 회귀가 무증상이 된다"
    )


# ---------------------------------------------------------------------------
# 조항 1 — 매핑 5종 → 헬퍼 호출 순서 + 그 사이 `await` 0건  (돌연변이 M7)
# ---------------------------------------------------------------------------
def test_g328_1_mapping_precedes_helper_with_no_await_between():
    """🔴 매핑 등록이 헬퍼 호출보다 **앞**이고 그 사이에 `await` 가 없다.

    금기 = 「주문번호 매핑 등록은 `place_order` 응답 직후 동기 영역,
    `await insert_trade` 진입 전」. 매핑 누락은 체결통보가 기본값 "momentum" 으로
    잘못 INSERT 되는 경로다.
    """
    fn = _func("execute_sell")
    calls = _helper_call_linenos(fn)
    mappings = _mapping_assign_linenos(fn)
    awaits = _await_linenos(fn)

    assert len(calls) == 2, f"호출부 2곳 전제가 깨졌다: {calls}"
    assert len(mappings) >= 2 * len(_MAPPING_TARGETS), (
        f"매핑 대입이 {len(mappings)}건 — 두 경로 × {len(_MAPPING_TARGETS)}키 미만이다: {mappings}"
    )

    for call_lineno in calls:
        before = [m for m in mappings if m < call_lineno]
        assert before, (
            f"헬퍼 호출(line {call_lineno}) **앞**에 매핑 대입이 없다 — "
            "호출이 매핑보다 먼저 오면 매핑 누락 창이 열린다"
        )
        block_start = max(before)
        between = [
            a for a in awaits
            if block_start < a < call_lineno
        ]
        assert not between, (
            f"매핑(line {block_start}) 과 헬퍼 호출(line {call_lineno}) 사이에 "
            f"`await` 가 있다: {between}. 그 자리에 양보점이 생기면 매핑 등록 전에 "
            "체결통보가 들어와 기본 전략으로 잘못 INSERT 된다"
        )


# ---------------------------------------------------------------------------
# 조항 2 — 헬퍼의 최초 양보점이 INSERT 다  (돌연변이 M8)
# ---------------------------------------------------------------------------
def test_g328_2_helper_has_no_await_before_completed_orders_probe():
    """🔴 헬퍼 본문에서 `_completed_orders` 판정보다 **앞**에 `await` 가 0건이다.

    이것이 "최초 양보점은 여전히 `await insert_trade`" 라는 추출의 전제다.
    맨 위에 비동기 관측 한 줄이 들어가면 양보점이 앞당겨져
    「매핑은 동기 영역」 금기가 **조용히** 깨진다.
    """
    # ⚠️ cycle334 — 선행 체크는 **코어 헬퍼**로 옮겨갔고 `_HELPER` 는 경계 래퍼가 됐다.
    # 「최초 양보점이 `await insert_trade` 다」라는 계약은 **코어**에 대해 성립해야 한다.
    fn = _func(_CORE)

    probe_linenos = [
        n.lineno for n in ast.walk(fn)
        if isinstance(n, ast.Compare)
        and any(isinstance(op, ast.In) for op in n.ops)
        and any(
            isinstance(c, ast.Attribute) and c.attr == "_completed_orders"
            for c in ast.walk(n)
        )
    ]
    assert probe_linenos, (
        "헬퍼 안에서 `order_no in self._completed_orders` 판정을 찾지 못했다 — "
        "체결통보 선행 체크가 사라졌다"
    )

    first_probe = min(probe_linenos)
    early = [a for a in _await_linenos(fn) if a < first_probe]
    assert not early, (
        f"`_completed_orders` 판정(line {first_probe}) 앞에 `await` 가 있다: {early}. "
        "최초 양보점이 앞당겨져 매핑 동기 영역 금기가 깨진다"
    )


@pytest.mark.parametrize(("wrapper", "axis"), _BOUNDARY_WRAPPERS)
def test_g328_2b_wrapper_awaits_only_the_core(wrapper: str, axis: str):
    """🔴 경계 래퍼의 `await` 는 **코어 호출 하나뿐**이다.

    두 래퍼의 docstring 이 「본문 앞부분에 `await` 를 추가하지 않는다」를 금기로 적는데
    **강제하는 가드가 없었다**(관문 2026-09-21 G4). cycle334 가 `test_g328_2` 를
    **코어**로 재조준하면서 래퍼 축이 비었고, `test_g328_1`(매도 매핑↔호출)·
    `test_c1_9`(매수 훅↔호출)는 둘 다 `execute_*` **바깥쪽**만 본다.

    ⚠️ 실제 위험도는 낮다 — 매핑 6종은 래퍼 호출 **전**에 이미 등록되므로 그 `await` 가
    「매핑은 동기 영역」 금기를 실제로 깨지는 않고, 그 창에 착지한 체결통보는 코어의
    `_completed_orders` 판정이 정상 흡수한다. **금기를 적어 놓고 아무도 안 보는 상태**를
    닫는 것이 이 케이스의 목적이다 — 다음 사람이 그 줄을 믿을 수 있어야 한다.
    """
    fn = _func(wrapper)
    awaits = [n for n in ast.walk(fn) if isinstance(n, ast.Await)]
    assert len(awaits) == 1, (
        f"{axis} 래퍼의 `await` 가 {len(awaits)}건 (기대 1건 = 코어 호출): "
        f"{[a.lineno for a in awaits]}"
    )
    inner = awaits[0].value
    assert (
        isinstance(inner, ast.Call)
        and isinstance(inner.func, ast.Attribute)
        and inner.func.attr == _CORE
    ), (
        f"{axis} 래퍼의 유일한 `await` 가 코어 호출이 아니다: "
        f"{ast.unparse(inner)[:80]}"
    )


# ---------------------------------------------------------------------------
# 조항 3 — 경계가 헬퍼 자신에게 있다  (돌연변이 M1/M2 의 구조 축)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(("wrapper", "axis"), _BOUNDARY_WRAPPERS)
def test_g328_3_helper_swallows_exception_itself(wrapper: str, axis: str):
    """🔴 래퍼가 자기 본문에서 `except Exception` 으로 경계를 닫는다.

    행위 축은 회귀가 잡는다(매도 = 주 경로 재발사 · 폴백 예외 전파 / 매수 =
    cycle335 의 pending 해제·예산 이중 사용·틱 관통). 이 조항은 **경계가 호출부
    문맥으로 옮겨가는 것**을 막는다 — 옮기는 순간 두 호출부가 서로 다른 안전성을
    갖게 되고, 그 비대칭이 정확히 cycle327 결함의 모양이다.
    """
    fn = _func(wrapper)
    handlers = [
        h for n in ast.walk(fn) if isinstance(n, ast.Try)
        for h in n.handlers
        if isinstance(h.type, ast.Name) and h.type.id == "Exception"
    ]
    assert handlers, (
        f"{axis} 래퍼에 `except Exception` 이 없다 — 접수 후 경계가 사라졌거나 "
        "호출부로 옮겨갔다. 주문이 나간 뒤의 실패가 재발사·틱 중단을 부른다"
    )


@pytest.mark.parametrize(("wrapper", "axis"), _BOUNDARY_WRAPPERS)
def test_g328_3b_helper_boundary_is_not_narrowed_to_specific_types(
    wrapper: str, axis: str,
):
    """🔴 경계의 **폭**을 봉인한다 — 최상위 `try` 의 핸들러는 정확히 1개, 타입은 `Exception`.

    도메인 관문(2026-09-20)의 지적이다. 행위 회귀 2건은 예외 **타입 표본 둘**
    (`UniqueViolationError` · `TimeoutError`)에만 기대므로, 그 둘을 포함하되 다른 것을
    빼는 좁히기(`except (UniqueViolationError, TimeoutError, OSError):`)는 **초록으로
    통과한다**. 구조로 닫지 않으면 그물이 표본의 크기만큼만 크다.

    🔴 **좁혔을 때의 최악은 재발사가 아니다.** 새는 예외가 우연히 `KisApiError` 면,
    폴백 호출부를 감싼 형제 핸들러 `except KisApiError as fb_err` 가 그것을 잡아
    **「폴백도 거부당했다」로 오분류**한다 — `_selling.discard` +
    `register_market_order_disallowed(fallback_succeeded=False)` + NXT 시간대면
    `_pending_next_day_clear` 등록. **거래소에 살아 있는 주문을 장부에 「거부」로 적고
    익일청산 큐에 넣는다.** 조용한 이중 청산 경로다.

    피해 크기도 두 호출부가 다르다 — 주 경로가 새면 그 종목 중복 매도(1종목),
    폴백이 새면 `execute_sell` 을 관통해 `risk.on_tick` 이 죽어 **그 틱의 전 보유 종목
    손절 평가가 사라진다**. 자릿수가 다른 두 리스크를 이 한 줄이 떠받친다.

    🔴 **매수 축도 같은 구멍을 갖는다**(cycle335 실측). 좁히기 돌연변이
    (`except UniqueViolationError:`)를 넣으면 cycle335 행위 회귀 14건 중 8건이
    붉어지지만 **`UniqueViolationError` 케이스는 통과한다** — 좁히기는 «가장 많이
    테스트된 타입»을 그대로 잡기 때문이다. 표본을 아무리 늘려도 같은 종류의 누락에
    노출되므로 **구조가 유일한 방어**다.
    """
    fn = _func(wrapper)
    tries = [n for n in ast.walk(fn) if isinstance(n, ast.Try)]
    assert len(tries) == 1, (
        f"{axis} 래퍼 안 `try` 가 {len(tries)}개 (기대 1개). 경계가 여러 개로 갈라지면 "
        "어느 것이 접수 후 경계인지 이 가드가 판정할 수 없다"
    )

    handlers = tries[0].handlers
    assert len(handlers) == 1, (
        f"{axis} 래퍼의 핸들러가 {len(handlers)}개 (기대 1개): "
        f"{[ast.unparse(h.type) if h.type else 'bare' for h in handlers]}. "
        "핸들러를 늘리면 잡히지 않는 예외 타입이 생기고, 그것이 폴백 호출부에서는 "
        "`execute_*` 관통 = 그 틱 전 종목 손절 정지다"
    )

    caught = handlers[0].type
    assert isinstance(caught, ast.Name) and caught.id == "Exception", (
        f"{axis} 경계가 `except {ast.unparse(caught) if caught else 'bare'}` 로 좁혀졌다. "
        "`Exception` 이어야 한다 — 좁히면 회귀의 타입 표본만 통과하고, "
        "새는 예외가 `KisApiError` 면 폴백 핸들러가 「거부」로 오분류해 "
        "살아 있는 주문을 익일청산 큐에 넣는다(매도) / 접수된 주문에 저자금 "
        "cooldown 을 걸고 운영자가 주문이 안 나갔다고 믿는다(매수)"
    )


def test_g328_4_skip_label_lookup_cannot_raise():
    """🔴 경로 수식어 조회는 `[...]` 인덱싱이 아니라 `.get(...)` 이다.

    이 조회는 **관측 전용**이다. `KeyError` 가 나면 그 자리의 `except Exception` 이
    삼켜 **PENDING INSERT 가 통째로 건너뛰어진다** — 주문은 나갔는데 `trade_history`
    행이 없는 상태다. 관측이 행위를 바꾸면 안 된다.
    """
    # cycle334 — 수식어 표가 `_PENDING_SKIP_PREFIX`(4경로 공용)로 바뀌고
    # 조회 자리는 **코어 헬퍼** 안이다. 계약(조회가 raise 할 수 없다)은 불변.
    fn = _func(_CORE)
    bad = [
        n.lineno for n in ast.walk(fn)
        if isinstance(n, ast.Subscript)
        and isinstance(n.value, ast.Attribute)
        and n.value.attr in ("_SELL_PENDING_SKIP_PATH_LABEL", "_PENDING_SKIP_PREFIX")
    ]
    assert not bad, (
        f"수식어 표 `[...]` 인덱싱이 있다: line {bad}. "
        "`.get(path, \"\")` 로 두어야 어떤 `path` 값에도 raise 하지 않는다"
    )

    has_get = any(
        isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
        and n.func.attr == "get"
        and isinstance(n.func.value, ast.Attribute)
        and n.func.value.attr in ("_SELL_PENDING_SKIP_PATH_LABEL", "_PENDING_SKIP_PREFIX")
        for n in ast.walk(fn)
    )
    assert has_get, "수식어 표를 `.get()` 으로 읽는 자리가 없다 — 대상이 사라졌다"
