"""cycle295 Red — (A) 축 · **식별자 소멸** 정적 가드 (G-D3).

명세 = `_workspace/red/cycle295_gap_hold_removal_spec.md` §2-1 · §5-1
행위 자매 = `tests/unit/engine/test_cycle295_gap_hold_removed.py`
라우트 자매 = `tests/unit/routes/test_cycle295_gap_route_surface.py`

## 이 파일이 잠그는 것

행위 가드(G-D1·G-D2)는 "지금 그렇게 동작하는가" 를 잰다. 이 파일은 "그 배선이
**소스에서 사라졌는가**" 를 잰다 — 다이얼만 내리고 코드를 남기면 재기동 후 최대
120초 동안 프로세스 기본값 `True` 로 재무장되는 잔여 경로가 남기 때문이다(§1-5).

## 🔵 공허 가드 금지 — 모든 부정 단언에 양성 대조군이 붙는다

cycle292 실측 교훈: 본체가 떠나면 "…가 0건" 부정 단언이 **전부 참**이 되어 조용히
공허해진다. 그래서 같은 스캐너로 **남아야 하는 식별자**(`switch_windows`·
`pre_to_krx`·`clock_channel`·`REASON_KRX_WINDOW`·`tick_channel_switch_enabled`)가
실제로 잡히는지 함께 단언한다. 스캐너가 파일을 못 읽으면 그쪽이 먼저 붉어진다.

## 스코프 — `src/**/*.py` 만

`docs/HARNESS_CHANGELOG.md`·`_workspace/**` 는 **verbatim 역사**라 스캔 대상이
아니다(cycle257 `_LIVE_DOCS` 관례). `src/**/*.md`(각 디렉터리 CLAUDE.md)의 갭 서술은
`/sync-docs` 단계에서 §6-4 대로 **재서술**한다 — 지우지 않는다.

## docstring 은 판정에서 제외한다

명세 §5-6 은 "이력은 지우지 않고 **철회 문장을 덧붙인다**" 를 요구한다. 설명문을
금지하면 이 가드가 구현을 **문서를 지우는 방향**으로 몰아간다. 잠글 것은 **코드**다
(cycle294 `_doc_node_ids` 관례 답습). 주석은 `ast` 가 애초에 보지 않는다.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

pytestmark = pytest.mark.unit

_ROOT = pathlib.Path(__file__).resolve().parents[3]
_SRC = _ROOT / "src"

_CLOCK_REL = "src/engine/tick_channel_clock.py"
_MODE_REL = "src/engine/tick_channel_mode.py"
_SYSCONF_REL = "src/db/system_config.py"
_ROUTES_REL = "src/routes/realtime.py"
#: §2-2 — 전환 leaf 는 창 목록을 label 문자열로 받기만 한다. **diff 0** 이어야 한다.
_SWITCH_REL = "src/engine/tick_channel_switch.py"


# ===========================================================================
# 스캐너
# ===========================================================================
def _src_files() -> list[pathlib.Path]:
    return sorted(p for p in _SRC.rglob("*.py") if "__pycache__" not in p.parts)


def _doc_node_ids(tree: ast.AST) -> set[int]:
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


def _code_tokens(text: str) -> set[str]:
    """그 소스가 **코드로** 쓰는 식별자 + docstring 을 뺀 문자열 상수 전부.

    `git grep` 을 쓰지 않는다 — 추적 파일만 보므로 Green 이 새로 만든 미추적 파일을
    로컬에서 못 본다(cycle259 S4b 교훈). `rglob` + AST 가 정본이다.
    """
    tree = ast.parse(text)
    skip = _doc_node_ids(tree)
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            out.add(node.id)
        elif isinstance(node, ast.Attribute):
            out.add(node.attr)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out.add(node.name)
        elif isinstance(node, ast.arg):
            out.add(node.arg)
        elif isinstance(node, ast.keyword) and node.arg:
            out.add(node.arg)
        elif isinstance(node, ast.Import):
            for a in node.names:
                out.update(a.name.split("."))
                if a.asname:
                    out.add(a.asname)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                out.update(node.module.split("."))
            for a in node.names:
                out.add(a.name)
                if a.asname:
                    out.add(a.asname)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) not in skip:
                out.add(node.value)
    return out


def _str_literals(text: str) -> list[str]:
    """docstring 을 뺀 문자열 상수 목록 (f-string 조각 포함)."""
    tree = ast.parse(text)
    skip = _doc_node_ids(tree)
    return [
        n.value for n in ast.walk(tree)
        if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in skip
    ]


def _tokens_by_file() -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for path in _src_files():
        rel = path.relative_to(_ROOT).as_posix()
        out[rel] = _code_tokens(path.read_text(encoding="utf-8"))
    return out


# ===========================================================================
# 목록
# ===========================================================================
#: 🔴 사라져야 하는 식별자·문자열 상수 (exact token).
_FORBIDDEN = (
    # 시각축 leaf
    "nxt_only_continuous_window",
    "in_nxt_gap",
    "gap_hold_enabled",
    "REASON_NXT_GAP_WINDOW",
    "nxt_gap_window",
    # 전환 창 라벨 2종
    "krx_to_nxt_gap",
    "nxt_gap_to_krx",
    # 모드 모듈 다이얼
    "GAP_HOLD_ENABLED_KEY",
    "DEFAULT_GAP_HOLD_ENABLED",
    "_gap_hold_enabled",
    "apply_gap_hold_enabled",
    # DB 헬퍼 + 키
    "get_tick_channel_gap_hold_enabled",
    "set_tick_channel_gap_hold_enabled",
    "_TICK_CHANNEL_GAP_HOLD_ENABLED_KEY",
    "tick_channel_gap_hold_enabled",
    # 라우트 표면
    "_nxt_gap_window_repr",
    "gap_config_key",
    "gap_persisted",
)

#: 🔵 양성 대조군 — 같은 스캐너가 반드시 찾아야 하는 **살아남는** 식별자.
#:    (식별자, 그것이 있어야 하는 파일)
_MUST_SURVIVE = (
    ("switch_windows", _CLOCK_REL),
    ("clock_channel", _CLOCK_REL),
    ("REASON_KRX_WINDOW", _CLOCK_REL),
    ("REASON_PRE_WINDOW", _CLOCK_REL),
    ("pre_to_krx", _CLOCK_REL),
    ("switch_at", _CLOCK_REL),
    ("emit_clock_config", _CLOCK_REL),
    ("SWITCH_ENABLED_KEY", _MODE_REL),
    ("refresh_switch_params", _MODE_REL),
    ("apply_switch_enabled", _MODE_REL),
    ("tick_channel_switch_enabled", _SYSCONF_REL),
    ("get_tick_channel_switch_enabled", _SYSCONF_REL),
    ("_get_bool_or_none", _SYSCONF_REL),
    ("_switch_windows_repr", _ROUTES_REL),
)

#: `nxt_only_continuous_window` 전용 헬퍼 — 본체가 떠나면 **고아**가 된다.
_ORPHAN_HELPERS = ("_spans", "_subtract", "_GAP_MEMO", "_EPOCH_DAY")


# ===========================================================================
# G-D3a — 🔵 스캐너 자체의 양성 대조군
# ===========================================================================
def test_gd3a_scanner_reads_the_files_it_claims_to_judge():
    """🔵 G-D3a — 스캐너가 실제로 소스를 읽는가.

    아래 "0건" 단언들은 스캔 결과가 비어 있어도 **전부 참**이다. 이 테스트가 그
    퇴화를 사살한다 — 파일 수 하한 + 판정 대상 4파일 실재 + 살아남는 식별자 실측.
    """
    by_file = _tokens_by_file()
    assert len(by_file) >= 100, (
        f"`src/**/*.py` 스캔이 {len(by_file)}개 파일밖에 못 찾았다 — 스캐너 고장"
    )
    for rel in (_CLOCK_REL, _MODE_REL, _SYSCONF_REL, _ROUTES_REL, _SWITCH_REL):
        assert rel in by_file, f"{rel} 이 스캔 결과에 없다"

    missing = [
        f"{tok} in {rel}" for tok, rel in _MUST_SURVIVE if tok not in by_file.get(rel, set())
    ]
    assert not missing, (
        "🔵 양성 대조군 실패 — 살아남아야 할 식별자를 스캐너가 못 찾았다: "
        f"{missing}. 제거가 필요한 범위를 넘었거나 스캐너가 고장났다"
    )


# ===========================================================================
# G-D3b — 🔴 금지 식별자 0건
# ===========================================================================
@pytest.mark.parametrize("token", _FORBIDDEN)
def test_gd3b_forbidden_identifier_is_gone_from_src(token: str):
    """🔴 G-D3b — 갭 홀드 식별자가 `src/**/*.py` 에서 사라졌다.

    exact token 매칭이다(부분 문자열 금지 — cycle292 가 `/sync-docs` 부분 문자열
    매치에서 겪은 거짓 통과의 반대 방향). docstring 은 제외하므로 §6-4 의
    「철회 문장을 덧붙인다」와 충돌하지 않는다.
    """
    hits = [rel for rel, toks in _tokens_by_file().items() if token in toks]
    assert not hits, (
        f"`{token}` 이 아직 코드에 있다: {hits}. cycle295 (A) 축은 갭 홀드 배선을 "
        "**구조적으로 0** 으로 만든다 — 다이얼만 내리면 재기동 후 ~120초 재무장 경로가 남는다"
    )


def test_gd3c_orphan_helpers_of_the_gap_function_are_gone():
    """🔴 G-D3c — 갭 함수 전용 헬퍼도 함께 사라진다.

    `_spans`·`_subtract`·`_GAP_MEMO`·`_EPOCH_DAY` 는 `nxt_only_continuous_window`
    말고 호출자가 **없다**(2026-09-15 실측). 본체만 지우고 남기면 다음 사람이
    "두 시장 연속 구간 빼기" 를 다시 배선한다 — 그것이 사용자가 지목한 복잡도다.

    🔵 양성 대조군 — 같은 파일에서 `_windows`·`_channels`·`_wall_date` 는 **남는다**.
    """
    text = (_ROOT / _CLOCK_REL).read_text(encoding="utf-8")
    toks = _code_tokens(text)

    left = [t for t in _ORPHAN_HELPERS if t in toks]
    assert not left, f"{_CLOCK_REL} 에 갭 전용 고아 헬퍼가 남았다: {left}"

    for survivor in ("_windows", "_channels", "_wall_date", "_WINDOW_MEMO", "_SWITCH_AT_MEMO"):
        assert survivor in toks, (
            f"🔵 양성 대조군 실패 — `{survivor}` 까지 사라졌다. 제거 범위가 갭을 넘었다"
        )


# ===========================================================================
# G-D3d — 🔴 관측 필드 소멸 (§6-6 — 정확히 4필드)
# ===========================================================================
@pytest.mark.parametrize(("rel", "fragment"), [
    (_CLOCK_REL, "nxt_gap="),
    (_CLOCK_REL, "gap_hold="),
    (_ROUTES_REL, "gap_hold="),
    (_ROUTES_REL, "gap_persisted="),
])
def test_gd3d_marker_fields_that_carried_the_gap_are_gone(rel: str, fragment: str):
    """🔴 G-D3d — 사라지는 관측은 **정확히 4필드**다(§6-6).

    `[tick_channel_clock]` 의 `nxt_gap=`·`gap_hold=` 와 `[tick_channel_mode]` 의
    `gap_hold=`·`gap_persisted=`. **마커 이름 12종은 전부 유지**되므로
    `test_cycle294_ast_stage3.py::A23` 은 무접촉 통과다.

    ⚠️ `emit_clock_config` 와 `_nxt_gap_window_repr` 는 **둘 다 never-raise** 라 안
    고치고 배포하면 예외 없이 **카나리아만 조용히 죽는다**(가장 나쁜 실패 모드 —
    "오늘 전환이 몇 시로 잡혔는가" 를 사후에 알 방법이 없어진다).
    """
    hits = [s for s in _str_literals((_ROOT / rel).read_text(encoding="utf-8")) if fragment in s]
    assert not hits, (
        f"{rel} 의 로그 문자열에 `{fragment}` 가 남았다: {hits[:3]}. "
        "D+1 판독자가 그 필드를 보고 '갭 홀드가 아직 돈다' 고 읽는다"
    )


@pytest.mark.parametrize(("rel", "fragment"), [
    (_CLOCK_REL, "[tick_channel_clock]"),
    (_CLOCK_REL, "switch_at="),
    (_CLOCK_REL, "krx_open="),
    (_CLOCK_REL, "source=market_table"),
    (_ROUTES_REL, "[tick_channel_mode]"),
    (_ROUTES_REL, "switch_enabled="),
])
def test_gd3e_the_surviving_canary_fields_stay(rel: str, fragment: str):
    """🔵 G-D3e 양성 대조군 — 카나리아의 **나머지 필드는 남는다**.

    두 필드만 빼는 것이지 마커를 죽이는 것이 아니다. 이 절이 붉어지면 `emit_clock_config`
    를 통째로 지운 것이다 — 그러면 표가 또 바뀌는 날(09-14 가 두 번째다) 값이 조용히
    움직이고 아무도 모른다.
    """
    text = (_ROOT / rel).read_text(encoding="utf-8")
    assert any(fragment in s for s in _str_literals(text)), (
        f"{rel} 에서 `{fragment}` 가 사라졌다 — 제거 범위가 갭을 넘어 카나리아를 죽였다"
    )


# ===========================================================================
# G-D3f — 🔵 `priority` 는 남는다 (§2-3 — `scanner.py` 8영역 diff 0)
# ===========================================================================
def test_gd3f_clock_channel_keeps_its_priority_parameter():
    """🔵 G-D3f — `clock_channel(..., priority=)` 시그니처는 **유지**한다.

    지우면 `scanner._resolve_channel` ← `tick_tr_id_for` ← `tick_channel_switch`
    ← `stale_watcher_core` 체인으로 연쇄 변경되고 `scanner.py` 는 **8영역**이다.
    승인 파일 1개를 아끼는 쪽이 낫다(§2-3).

    ⚠️ 남기면 다음 사람이 "HIGH 는 다른 채널로 간다" 고 오독하므로 docstring 을
    **지우지 말고 재서술**한다 — "`priority` 는 판정에 쓰이지 않는다. 코호트 축만 본다."
    행위 단언은 자매 파일의 G-D2 다.
    """
    tree = ast.parse((_ROOT / _CLOCK_REL).read_text(encoding="utf-8"))
    fn = next(
        (n for n in ast.walk(tree)
         if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "clock_channel"),
        None,
    )
    assert fn is not None, f"{_CLOCK_REL} 에 `clock_channel` 이 없다"
    kwonly = [a.arg for a in fn.args.kwonlyargs]
    assert "priority" in kwonly, (
        "`clock_channel` 에서 `priority` 를 지웠다 — `scanner.py`(8영역) 연쇄 변경이 "
        "따라온다. §2-3 결정 = **남긴다**"
    )
    assert "offset_secs" in kwonly, "🔵 양성 대조군 — `offset_secs` 까지 사라졌다"


# ===========================================================================
# G-D3g — 🔵 전환 leaf 는 소비자로서 그냥 받는다 (diff 0)
# ===========================================================================
def test_gd3g_switch_leaf_never_knew_about_the_gap():
    """🔵 G-D3g — `tick_channel_switch.py` 는 갭 토큰 0건이고 **그대로여야 한다**.

    그 모듈은 창 목록을 label 문자열로 받아 로그·반환 dict 에만 쓴다. 창이 3→1 로
    줄어드는 것을 소비자로서 그냥 받는다(§2-2). 여기에 손이 가면 제거 범위가 샌 것이다.

    🔵 양성 대조군 — 같은 파일이 `run_switch_cycle` 을 여전히 정의한다.
    """
    toks = _code_tokens((_ROOT / _SWITCH_REL).read_text(encoding="utf-8"))
    leaked = [t for t in _FORBIDDEN if t in toks]
    assert not leaked, f"{_SWITCH_REL} 에 갭 토큰이 들어왔다: {leaked}"
    assert "run_switch_cycle" in toks, (
        "🔵 양성 대조군 실패 — 전환 leaf 의 진입점이 사라졌다"
    )


# ===========================================================================
# G-D3h — 🔴 문서 축: 폐기된 다이얼을 「쓰라」고 지시하는 런북이 남지 않는다
# ===========================================================================
#: 운영자가 사고 중에 실제로 여는 문서들. G-D3 계열의 식별자 스캔은 `src/**/*.py`
#: 만 보므로 `.md` 가 통째로 밖이었고, 그래서 cycle294 런북 4곳(`README.md` 2 ·
#: `src/routes/CLAUDE.md` · `src/engine/CLAUDE.md`)이 **제거 뒤에도 살아남았다**
#: (착지 직후 적대 검증 HIGH). 위험한 방향은 `false`(끄기)가 아니라 **`true`
#: (되살리기)** 다 — `PUT {"mode":"enforce","gap_hold_enabled":true}` 는
#: `200`·`success:true`·`message:""` 를 돌려주며 **아무 일도 하지 않는다**
#: (pydantic `extra=ignore`). 운영자는 "복구했다" 고 믿는다.
_DOC_FILES = (
    "README.md",
    "src/routes/CLAUDE.md",
    "src/engine/CLAUDE.md",
    "src/db/CLAUDE.md",
    "src/realtime/CLAUDE.md",
)


@pytest.mark.parametrize("rel", _DOC_FILES)
def test_gd3h_docs_that_name_the_retired_dial_also_say_it_is_retired(rel: str):
    """🔴 G-D3h — 폐기 다이얼을 언급하는 문서는 **폐기 사실도** 적어야 한다.

    식별자를 문서에서 **지우라는 가드가 아니다** — 이 리포의 관례는 이력을
    지우지 않고 철회 표시를 다는 것이다(같은 사고의 재발 방지: 다음 사람이 옛
    사실만 읽고 승인 없이 되살리는 경로 차단). 그래서 단언은 "언급했다면 같은
    파일에 `cycle295` 도 있어야 한다" 는 **동반 조건**이다. 부분 문자열 금지
    가드로 만들면 지금의 폐기 각주들이 스스로를 붉히고, 다음 사람이 각주를
    지우는 쪽으로 움직인다.

    🔵 양성 대조군 — 파일이 실제로 읽히고 비어 있지 않음을 먼저 확인한다
    (cycle292 교훈: 스캐너가 파일을 못 읽으면 동반 조건이 공짜로 참이 된다).
    """
    path = _ROOT / rel
    assert path.is_file(), f"{rel} 가 없다 — 스캐너가 겨눌 대상을 잃었다"
    text = path.read_text(encoding="utf-8")
    assert len(text) > 500, f"🔵 양성 대조군 실패 — {rel} 이 비었다"

    if "gap_hold_enabled" not in text and "nxt_gap" not in text:
        return  # 언급이 없으면 볼 것도 없다

    assert "cycle295" in text, (
        f"{rel} 이 폐기된 갭 홀드 다이얼을 언급하는데 `cycle295`(철회 사이클) "
        "표기가 없다 — 운영자가 사고 중에 그 런북을 그대로 따라 "
        '`PUT {"mode":"enforce","gap_hold_enabled":true}` 를 보내면 '
        "`200`·`success:true` 를 받고 **아무 일도 일어나지 않는다**(`extra=ignore` "
        "가 키를 버린다). 식별자를 지우지 말고 철회 표시를 달아라(§6-4)"
    )
