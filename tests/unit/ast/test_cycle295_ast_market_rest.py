"""cycle295 Red (AST) — 15:30~16:00 주문 컷의 **구조** 계약.

정본 = `_workspace/red/cycle295_gap_hold_removal_spec.md` §3-3 · §5-4 · §2-5.
접촉 허용 프로덕션 파일 = `src/engine/order_engine.py` **하나**(8영역, 사용자 승인
2026-09-15). `scheduler.py`·나머지 8영역 4파일·전략 7파일은 diff 0 이다.

## 왜 이 파일이 따로 있나 — 「시각 리터럴 0건」 가드가 지금 이름보다 약하다

cycle294 A5 는 **원시 소스 정규식** 3종(`time(H,M)` 호출 · `"HH:MM"` 문자열 ·
`datetime.combine(..., time(H,M))`)으로 신규 leaf 3파일을 잰다. 그 방식을
`order_engine.py` 에 그대로 이식하면 **오늘 0건으로 통과한다**(실측). 그런데 이
파일에는 `_compute_next_market_open_kst` 의 `now.replace(hour=9, ...)` 가 **2곳**
(:207·:214) 있다. 즉 이름이 거짓이 되고, 구현자가 컷을

    now.hour == 15 and now.minute >= 30        # ← 정규식 3종 전부 통과
    now.replace(hour=16, minute=0)             # ← 동상

으로 짜도 가드는 조용히 초록이다. 게다가 원시 정규식은 이 파일의 **주석**
(`# 15:30~16:00 …`)까지 금지하게 되어 현실적으로 쓸 수 없다.

⇒ G-295-C1 은 **AST 기반**이다. 판정 대상은 코드 노드뿐이고(주석·docstring 제외),
금지 목록이 `replace(hour=)`·`Attribute(hour|minute|second) == Constant(int)` 까지
넓다. 면제는 **정확히 1건**이고 함수명 **문자열**이 아니라 **AST 노드 줄 범위**로
좁힌다 — 문자열 매칭이면 주석에 함수명을 적는 것만으로 면제가 새 나간다
(cycle292 가 `/sync-docs` 부분문자열 매치에서 실제로 겪은 결함).

## 가드 목록

| # | 이름 | 내용 | 양성 대조군 |
|---|---|---|---|
| C1 | 시각 리터럴 0건 | `time(H,M)` · `"HH:MM"` 코드 상수 · `.replace(hour=/minute=/second=)` · `dt.hour == 15` 류 비교 — allowlist 밖 0건 | C2 |
| C2 | allowlist 생존 | `_compute_next_market_open_kst` 가 **존재**하고 **실제로** `replace(hour=` 를 쓴다(2건) | — |
| C3 | 술어 존재·순수 | `_market_rest_now` 가 모듈 레벨 동기 함수 · `await` 0 · I/O 토큰 0 | C3b |
| C3b | 술어가 표를 읽는다 | `_market_rest_now` 가 `get_market_state` 를 **이름으로** 참조 | — |
| C4 | 재주문 결과 바인딩 | `_cancel_and_reorder` 안 `place_order` 호출이 **값으로 쓰인다**(bare `await place_order(...)` 금지) | C4b |
| C4b | 자매 4곳 대조 | 나머지 `place_order` 호출 4곳은 원래부터 값을 받는다 | — |
| C5 | byte 동일 4함수 | `_route_exchange_by_clock`·`_apply_clock`·`_cancel_after_wait`·`cancel_remaining` 소스 세그먼트 sha 고정 | C5b |
| C5b | 핀 대상 생존 | 그 넷이 전부 존재한다(이름이 바뀌면 sha 비교가 아니라 이 단언이 먼저 붉어진다) | — |

⚠️ **C5 는 cycle295 착지 전용 핀이다.** Green 이 이 넷을 정말로 건드리지 않았음을
기계로 증명하는 것이 목적이고, cycle295 커밋 **이후** 다른 사이클이 이 넷을 바꿀
때는 sha 를 갱신하는 것이 정상이다(공허해지는 가드가 아니라 «그 사이클이 이 넷을
건드렸다»는 신호다). 핀은 `ast.dump` 가 아니라 **소스 세그먼트 sha** 다 —
CI(3.12)와 로컬(3.13)의 `ast.dump` 출력이 달라 로컬 초록·CI 실패가 난다
(메모리 「CI 환경 차이 교훈 2건」).
"""

from __future__ import annotations

import ast
import hashlib
import pathlib
import re

import pytest

pytestmark = pytest.mark.unit

_ROOT = pathlib.Path(__file__).resolve().parents[3]
_OE_REL = "src/engine/order_engine.py"

#: §5-4 — 면제는 정확히 1건. 값은 함수 **이름**이지만 판정은 그 함수의 AST 줄
#: 범위로만 한다(아래 `_allowlisted_lines`).
_CLOCK_LITERAL_ALLOWLIST: tuple[str, ...] = ("_compute_next_market_open_kst",)

#: §2-5 — 이 넷은 cycle295 가 **byte 동일**로 남긴다고 선언한 함수다.
_BYTE_IDENTICAL_PINS: dict[str, str] = {
    "_route_exchange_by_clock": "d403317f602318acade625b0540f839c706669aae92b86f13909a5d478512450",
    "_apply_clock": "5b9f0a10cf5291b90b2107a575ef8d7a9e110463d51a1d45fae865820f942c39",
    "_cancel_after_wait": "43c9e2bbb43760dea6674840b4f1d693f4db68fbfec3dcf491fc06ea1f747141",
    "cancel_remaining": "c9a2216d15ece58e212402a6edde10c8a9fcf1133cff44814950041bfe879162",
}

_PREDICATE = "_market_rest_now"
_IO_TOKENS = ("pg.fetch", "pg.execute", "httpx", "aiohttp", "requests.", "kis_request")
_CLOCK_STR_RE = re.compile(r"^\s*(?:[01]?\d|2[0-3]):[0-5]\d(?::[0-5]\d)?\s*$")


# ───────────────────────────── 헬퍼 ────────────────────────────────────────
def _src() -> str:
    return (_ROOT / _OE_REL).read_text(encoding="utf-8")


def _tree() -> ast.Module:
    return ast.parse(_src())


def _functions(tree: ast.AST, name: str) -> list:
    return [
        n for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name
    ]


def _doc_node_ids(tree: ast.AST) -> set[int]:
    """docstring 상수 노드 id — **설명문은 판정에서 제외**한다.

    컷 함수의 docstring 은 §5-6 대로 "(가)사실 → (나)cycle294 판단 → (다)사용자
    결정" 3문장을 담고 거기엔 `15:30~16:00` 이 반드시 나온다. 설명을 금지하면
    가드가 **문서를 지우는 방향**으로 구현을 몬다 — 잠글 것은 **코드**다.
    """
    ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", None) or []
            if (
                body and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                ids.add(id(body[0].value))
    return ids


def _allowlisted_lines(tree: ast.AST) -> set[int]:
    """면제 함수들이 **차지하는 줄 번호 집합**(문자열 매칭 아님)."""
    out: set[int] = set()
    for name in _CLOCK_LITERAL_ALLOWLIST:
        for fn in _functions(tree, name):
            end = getattr(fn, "end_lineno", None) or fn.lineno
            out.update(range(fn.lineno, end + 1))
    return out


def _clock_literal_hits(tree: ast.AST) -> list[tuple[int, str, str]]:
    """(줄, 종류, 소스) — allowlist 여부와 무관하게 **전부** 돌려준다."""
    docs = _doc_node_ids(tree)
    hits: list[tuple[int, str, str]] = []

    for node in ast.walk(tree):
        # (1) time(H, M) / datetime.time(H, M)
        if isinstance(node, ast.Call):
            fn = node.func
            fname = (
                fn.id if isinstance(fn, ast.Name)
                else fn.attr if isinstance(fn, ast.Attribute) else ""
            )
            if (
                fname == "time"
                and len(node.args) >= 2
                and all(
                    isinstance(a, ast.Constant) and isinstance(a.value, int)
                    for a in node.args[:2]
                )
            ):
                hits.append((node.lineno, "time(H,M)", ast.unparse(node)))
            # (3) x.replace(hour=/minute=/second=)
            if isinstance(fn, ast.Attribute) and fn.attr == "replace":
                keys = {k.arg for k in node.keywords}
                if keys & {"hour", "minute", "second"}:
                    hits.append((node.lineno, "replace(hour=)", ast.unparse(node)[:80]))
            # datetime.combine(..., time(...))
            if isinstance(fn, ast.Attribute) and fn.attr == "combine":
                hits.append((node.lineno, "datetime.combine", ast.unparse(node)[:80]))

        # (2) "HH:MM" 코드 상수 (docstring 제외)
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in docs
            and _CLOCK_STR_RE.match(node.value)
        ):
            hits.append((node.lineno, '"HH:MM"', repr(node.value)))

        # (4) now.hour == 15 / now.minute >= 30 류
        if isinstance(node, ast.Compare):
            parts = [node.left, *node.comparators]
            has_attr = any(
                isinstance(p, ast.Attribute) and p.attr in {"hour", "minute", "second"}
                for p in parts
            )
            has_const = any(
                isinstance(p, ast.Constant) and isinstance(p.value, int) for p in parts
            )
            if has_attr and has_const:
                hits.append((node.lineno, "hour/minute 비교", ast.unparse(node)))

    return hits


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _segment_sha(tree: ast.AST, src: str, name: str) -> str:
    fns = _functions(tree, name)
    assert len(fns) == 1, f"{_OE_REL} 의 `{name}` 정의가 {len(fns)}개 — 1개여야 한다"
    seg = ast.get_source_segment(src, fns[0])
    assert seg is not None
    return _sha(seg)


# ═══════════════════════════ C1 · C2 ═══════════════════════════════════════
def test_c1_no_clock_literals_outside_the_single_allowlisted_function() -> None:
    """🔴 G-295-C1 — 컷의 경계는 `market_state` 표에서만 나온다(§3-3 근거 1).

    금지 4종(코드 노드 한정):
      · `time(H, M)` 호출          · `"HH:MM"` 문자열 상수(docstring 제외)
      · `.replace(hour=/minute=/second=)`  · `dt.hour == 15` 류 비교

    면제 = `_compute_next_market_open_kst` **한 함수의 줄 범위**뿐이다.

    이 단언이 붉어졌다면 컷(또는 다른 무엇)이 벽시계를 직접 읽고 있다는 뜻이다.
    표가 또 움직이는 날(09-14 가 두 번째다) 그 코드는 조용히 틀린다 — allowlist 를
    늘려 초록으로 만들기 **전에** 왜 표로 못 쓰는지를 먼저 적어라.
    """
    tree = _tree()
    allowed = _allowlisted_lines(tree)
    offenders = [h for h in _clock_literal_hits(tree) if h[0] not in allowed]
    assert not offenders, (
        f"{_OE_REL} 에 시각 리터럴이 있다(allowlist 밖) — 경계는 "
        f"`market_state.get_market_state` 파생이어야 한다(§3-3):\n"
        + "\n".join(f"  L{ln}: [{kind}] {srcline}" for ln, kind, srcline in offenders)
    )


def test_c2_allowlist_target_exists_and_actually_uses_replace_hour() -> None:
    """🔵 G-295-C2 (양성 대조군) — 면제가 **살아 있는 면제**인지 확인한다.

    cycle292 교훈: 본체가 떠나면 "0건" 부정 단언은 전부 참이 되어 조용히
    공허해진다. 여기서는 반대 방향의 공허가 문제다 —
    `_compute_next_market_open_kst` 가 사라지거나 `replace(hour=` 를 그만 쓰면
    allowlist 는 **죽은 면제**로 남고, 나중에 같은 이름의 새 함수가 생기면
    면제가 조용히 부활한다. 그래서 「존재 + 실제 사용 2건」을 함께 못박는다.
    """
    tree = _tree()
    fns = _functions(tree, "_compute_next_market_open_kst")
    assert len(fns) == 1, (
        "`_compute_next_market_open_kst` 가 없거나 둘 이상이다 — "
        "G-295-C1 의 allowlist 가 죽은 면제가 된다(§5-4 C2)"
    )
    allowed = _allowlisted_lines(tree)
    inside = [
        h for h in _clock_literal_hits(tree)
        if h[0] in allowed and h[1] == "replace(hour=)"
    ]
    assert len(inside) == 2, (
        f"allowlist 함수 안 `replace(hour=)` 가 {len(inside)}건 — 2건이어야 한다. "
        "스캐너가 아무것도 못 보고 있다면 C1 의 '0건' 도 거짓 통과다"
    )


# ═══════════════════════════ C3 · C3b ══════════════════════════════════════
def test_c3_predicate_exists_module_level_sync_and_pure() -> None:
    """🔴 G-295-C3 — `_market_rest_now` 는 모듈 레벨 **동기·순수** 술어다(§3-3).

    · 동기여야 한다 — 동기 취소 경로(`_cancel_and_reorder` 의 쌍 게이트 판정
      직전 등)와 `execute_buy`/`execute_sell` 이 같은 seam 을 쓴다.
    · 순수여야 한다 — 관측·판정이 DB/HTTP 를 타면 손절 hot path 에 왕복이 붙고,
      그 왕복이 실패하는 날 컷이 통째로 예외가 된다.
    """
    src = _src()
    tree = ast.parse(src)
    top = [
        n for n in tree.body
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == _PREDICATE
    ]
    assert len(top) == 1, (
        f"{_OE_REL} 모듈 레벨에 `{_PREDICATE}` 가 없다 — §3-3 의 이름·자리 계약이다. "
        "메서드로 만들면 순수성 단언이 성립하지 않고 라우터 밖 술어라는 사실이 흐려진다"
    )
    fn = top[0]
    assert isinstance(fn, ast.FunctionDef), (
        f"`{_PREDICATE}` 가 async 다 — 동기여야 한다(§3-3)"
    )
    assert not [n for n in ast.walk(fn) if isinstance(n, ast.Await)], (
        f"`{_PREDICATE}` 에 `await` 가 있다 — 순수 술어여야 한다"
    )
    seg = ast.get_source_segment(src, fn) or ""
    for token in _IO_TOKENS:
        assert token not in seg, (
            f"`{_PREDICATE}` 에 `{token}` — 컷 판정에 I/O 를 넣으면 손절 경로가 막힌다"
        )


def test_c3b_predicate_reads_the_market_table_by_name() -> None:
    """🔵 G-295-C3b (양성 대조군) — 표를 안 읽는 컷은 **정의상** 리터럴 컷이다.

    C1 은 "리터럴이 없다"는 부정 단언이라, 컷이 아예 시각을 안 보고 상수 False 를
    돌려주는 퇴화 구현도 통과시킨다. 이 단언이 그 구멍을 닫는다.
    """
    src = _src()
    fn = _functions(ast.parse(src), _PREDICATE)
    assert fn, f"`{_PREDICATE}` 미존재 — C3 가 먼저 붉어야 한다"
    seg = ast.get_source_segment(src, fn[0]) or ""
    names: set[str] = set()
    for node in ast.walk(ast.parse(seg.strip())):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for a in node.names:
                names.add(a.asname or a.name.split(".")[0])
    assert "get_market_state" in names, (
        f"`{_PREDICATE}` 가 `get_market_state` 를 읽지 않는다 — 그럼 경계를 "
        "어디서 가져오나(§3-3 근거 1). 표 파생이 아닌 컷은 09-14 같은 제도 "
        "변경일에 조용히 틀린다"
    )


# ═══════════════════════════ C4 · C4b ══════════════════════════════════════
def _place_order_calls(fn) -> list[ast.Call]:
    out = []
    for node in ast.walk(fn):
        if isinstance(node, ast.Call):
            f = node.func
            nm = f.id if isinstance(f, ast.Name) else (f.attr if isinstance(f, ast.Attribute) else "")
            if nm == "place_order":
                out.append(node)
    return out


def _bare_await_place_order(fn) -> list[int]:
    """값으로 쓰이지 않는 `await place_order(...)` 의 줄 번호."""
    bare: list[int] = []
    for node in ast.walk(fn):
        if (
            isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Await)
            and isinstance(node.value.value, ast.Call)
        ):
            call = node.value.value
            f = call.func
            nm = f.id if isinstance(f, ast.Name) else (f.attr if isinstance(f, ast.Attribute) else "")
            if nm == "place_order":
                bare.append(node.lineno)
    return bare


def test_c4_stop_loss_reorder_binds_the_place_order_result() -> None:
    """🔴 G-295-C4 ((D) 축, §2-0b) — 손절 잔여 재주문이 **결과를 받는다**.

    현행 `:2505` 는 프로덕션 `place_order` 호출 5곳 중 **유일하게** 반환값을
    버린다. 값을 버리면 주문번호를 모르므로 매핑 5종을 등록할 수가 없고,
    그 재주문의 체결통보는 `_order_strategy` miss → `trade_history` miss →
    `"momentum"` 오귀속으로 흐른다(행위 증언은
    `tests/unit/engine/test_cycle295_stop_loss_reorder_mapping.py`).

    이 가드는 **구조**만 잰다 — "값을 받는가". 무엇을 등록하는지는 행위
    테스트가 잰다. 둘 다 있어야 「받아서 버리는」 구현이 막힌다.
    """
    tree = _tree()
    fns = _functions(tree, "_cancel_and_reorder")
    assert len(fns) == 1, "`_cancel_and_reorder` 가 없거나 둘 이상이다"
    calls = _place_order_calls(fns[0])
    assert len(calls) == 1, (
        f"`_cancel_and_reorder` 안 `place_order` 호출이 {len(calls)}건 — 1건이어야 한다"
    )
    bare = _bare_await_place_order(fns[0])
    assert not bare, (
        f"`_cancel_and_reorder` 의 `place_order` 가 값을 버린다(L{bare}) — "
        "`result = await place_order(...)` 로 받아 매핑 5종 + "
        "`_completed_orders.discard` 를 등록하라(§2-0b)"
    )


def test_c4b_sibling_place_order_sites_already_bind_their_result() -> None:
    """🔵 G-295-C4b (양성 대조군) — 자매 4곳은 **원래부터** 값을 받는다.

    C4 는 "bare 가 0건" 부정 단언이라, 누군가 `place_order` 를 통째로 지우거나
    이름을 바꾸면 조용히 참이 된다. 파일 전체의 `place_order` 호출이 5곳이고
    그중 bare 가 하나도 없음을 함께 못박아 스캐너가 실제로 보고 있음을 증명한다.
    """
    tree = _tree()
    prod_calls = _place_order_calls(tree)
    assert len(prod_calls) == 5, (
        f"{_OE_REL} 의 `place_order` 호출이 {len(prod_calls)}건 — 5건이어야 한다"
        "(§2-0b 실측: 매수 주·매수 폴백·매도 주·매도 폴백·손절 잔여 재주문). "
        "호출을 늘/줄였다면 이 수와 C4 의 판정 범위를 함께 재검토하라"
    )
    bare = _bare_await_place_order(tree)
    assert not bare, (
        f"{_OE_REL} 에 값을 버리는 `await place_order(...)` 가 남아 있다(L{bare})"
    )


# ═══════════════════════════ C5 · C5b ══════════════════════════════════════
@pytest.mark.parametrize("name", sorted(_BYTE_IDENTICAL_PINS))
def test_c5_byte_identical_functions_are_untouched(name: str) -> None:
    """🔴 G-295-C5 (§2-5) — 이 넷은 cycle295 가 **건드리지 않는다**.

    · `_route_exchange_by_clock`·`_apply_clock` — 컷을 라우터 **안**에 넣으면
      `_probe_nxt_downgrade_base` 가 `nxt_tradable=False` 코호트(마스터 83.2%)를
      `base="KRX"` 로 만들어 clause 1 에서 즉시 반환되고, **컷이 가장 필요한
      다수 코호트를 통째로 비껴간다**(§3-2 실행값 반증).
    · `_cancel_after_wait`·`cancel_remaining` — **순수 취소**라 노출 축소다.
      함께 막으면 호가창의 손절을 빼고 아무것도 안 넣는 상태가 된다(§3-5).

    ⚠️ 이 핀은 `ast.dump` 가 아니라 **소스 세그먼트 sha** 다(3.12 CI ↔ 3.13 로컬
    표현 차 — 메모리 「CI 환경 차이 교훈 2건」). cycle295 **이후** 다른 사이클이
    이 넷을 정당하게 바꿀 때는 sha 를 갱신한다 — 그때 이 테스트가 붉어지는 것은
    «그 사이클이 이 넷을 건드렸다»는 신호이지 결함이 아니다.
    """
    src = _src()
    tree = ast.parse(src)
    actual = _segment_sha(tree, src, name)
    assert actual == _BYTE_IDENTICAL_PINS[name], (
        f"`{name}` 이 변경됐다(sha {actual[:12]}… ≠ 핀 "
        f"{_BYTE_IDENTICAL_PINS[name][:12]}…). §2-5 는 이 함수를 byte 동일로 "
        "선언했다 — 컷을 라우터/순수 취소 경로에 넣지 않았는지 먼저 확인하라"
    )


def test_c5b_pinned_functions_all_exist() -> None:
    """🔵 G-295-C5b (양성 대조군) — 핀 대상 4개가 전부 실재한다.

    이름이 바뀌면 sha 비교가 아니라 이 단언이 **먼저** 붉어져야 한다
    (`_segment_sha` 의 assert 메시지보다 의도가 분명하다).
    """
    tree = _tree()
    missing = [n for n in _BYTE_IDENTICAL_PINS if len(_functions(tree, n)) != 1]
    assert not missing, (
        f"{_OE_REL} 에 핀 대상 함수가 없거나 중복이다: {missing}"
    )
