"""cycle278 Red — 무접촉·봉인 AST 가드 (C31~C36 · B67~B75).

정본 명세 = `_workspace/red/cycle278_param_catalog_ui_spec.md` §3.4 · §7.1.

이 사이클의 제1 계약은 **매매 행위를 한 글자도 바꾸지 않는다** 이다. 사람이 값을 고칠
*수단*(카탈로그·검증·화면)만 만들고, 값과 그 값을 읽는 코드는 그대로 둔다.

## ⚠️ 이 파일은 **프론트 파일을 읽는 백엔드 가드**를 포함한다 (cycle256 g251 관례)

`test_frontend_*` 두 계열이 `frontend/src/**` 를 직접 읽는다. 프론트 전용 사이클의
검증 목록(`grep -rl 'frontend/' tests/unit`)에 이 파일이 걸리게 하려고 여기 명시한다.
프론트 파일을 옮기거나 이름을 바꾸면 이 백엔드 테스트가 붉어진다.

## 왜 `ast.dump` 의 sha 를 핀하지 않는가

3.12(CI) / 3.13(로컬) 의 `ast.dump` 출력이 달라 로컬 초록·CI 실패가 난다
(cycle256 G-250-5 · cycle259 S4a). 본체 무변경 핀은 `ast.get_source_segment` 의
sha256 또는 **파일 내용 sha256** 으로 잰다.

## 왜 `git grep`/`git ls-files` 로 스캔하지 않는가

추적 파일만 보므로 Green 이 새로 만든 **미추적** 파일을 로컬에서 못 보고 CI(커밋 후)
에서만 잡는다(cycle259 S4b). 소스 스캔은 `Path(...).rglob` + AST/텍스트로 한다.
`bare git diff HEAD` 도 쓰지 않는다 — 커밋 직후 공허해지고 다음 편집에서 무조건 붉어진다
(cycle240 A11b · cycle252 G-252-5b).

## 재핀(2026-09-11 병합): order_engine.py·VB·LTV 3건은 **cycle276**(AI 매수평가 주문 시점 이동,
# 병합 bfa1e75)이 바꾼 것이지 cycle278 이 아니다. `git diff 34ba9e6 bfa1e75 -- <path>` 로 확인한 뒤
# 병합 결과 내용으로 재핀했다. cycle278 의 무접촉 주장은 그 병합 기준으로 유효하다.
# ⚠️ 사이클 한정 — 커밋 후 정리 의무

`_BASE_SHA`(8영역·`scheduler.py`·`strategy_base.py`·전략 7파일 내용 sha)와
`_SEGMENT_SHA`(`PARAM_RANGES`/`INT_PARAMS`/7 `DEFAULT_PARAMS` 소스 세그먼트 sha)는
**브랜치 base `34ba9e6` 의 blob** 을 고정한 것이라 cycle278 의 무접촉 증거로만 유효하다.
이후 그 파일들을 **정당하게** 바꾸는 사이클이 오면 그 사이클이 이 dict 를 갱신하거나
이 테스트를 삭제한다(고아 가드 방지).

## C35 프론트 키 하드코딩 예외 (정본)

① `frontend/src/pages/Strategies.tsx` — `THRESHOLD_KEYS` 4키(읽기 전용 요약 그리드).
② `frontend/src/pages/Settings.tsx` — `ExchangeBoardRow` 의 `exchange`·`tradable_boards`
   (라디오/체크박스 특화 UI). 그 밖의 키는 **스키마 응답으로만** 렌더한다.

## Red 상태

`StrategyParamsEditor.tsx` 가 아직 없고 `Settings.tsx` 가 `paramLabels` 24키 카탈로그를
import 해 쓰므로 C35·C36 은 RED 다. C31~C34(무접촉·클램프 존재)는 **작성 시점에 초록**이며
Green 이 그 선을 넘는 순간 붉어진다.
"""

from __future__ import annotations

import ast
import hashlib
import re
from pathlib import Path

import pytest

from src.engine import param_catalog as pc

pytestmark = pytest.mark.unit

_ROOT = Path(__file__).resolve().parents[3]
_SRC = _ROOT / "src"


def _read(rel: str) -> str:
    path = _ROOT / rel
    assert path.exists(), f"{rel} 이 없다 (Red — Green 이 만든다)"
    return path.read_text(encoding="utf-8")


def _content_sha(rel: str) -> str:
    return hashlib.sha256((_ROOT / rel).read_bytes()).hexdigest()


def _assign_segment(rel: str, name: str, cls_name: str | None = None) -> str:
    """모듈/클래스 레벨 대입문의 **소스 세그먼트**(sha 핀의 입력)."""
    src = _read(rel)
    tree = ast.parse(src)
    body = tree.body
    if cls_name is not None:
        found = [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name == cls_name]
        assert len(found) == 1, f"{rel}: 클래스 {cls_name} 를 찾지 못했다"
        body = found[0].body
    hits = [
        st for st in body
        if (isinstance(st, ast.Assign)
            and any(getattr(t, "id", None) == name for t in st.targets))
        or (isinstance(st, ast.AnnAssign) and getattr(st.target, "id", None) == name)
    ]
    assert len(hits) == 1, f"{rel}: {name} 대입문 {len(hits)}건 (기대 1)"
    segment = ast.get_source_segment(src, hits[0])
    assert segment, f"{rel}: {name} 소스 세그먼트 추출 실패"
    return segment


def _segment_sha(rel: str, name: str, cls_name: str | None = None) -> str:
    return hashlib.sha256(_assign_segment(rel, name, cls_name).encode("utf-8")).hexdigest()


def _func_segment(rel: str, func_name: str) -> str:
    src = _read(rel)
    tree = ast.parse(src)
    hits = [
        n for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == func_name
    ]
    assert hits, f"{rel}: 함수 {func_name} 이 없다"
    segment = ast.get_source_segment(src, hits[0])
    assert segment
    return segment


# ===========================================================================
# C32 · C33 — 소스 세그먼트 sha 핀 (base 34ba9e6)
# ===========================================================================
_RECO = "src/engine/recommendation_engine.py"

_SEGMENT_SHA: dict[tuple[str, str, str | None], str] = {
    (_RECO, "PARAM_RANGES", None):
        "11ed6cd7d849d414e9668056d1e53ef64e172ef8356b97b73ad66ac07d87f346",
    (_RECO, "INT_PARAMS", None):
        "c2a0d4d45123c409c5e977b787dab0a44b25f90920d2969e15338d0fef679066",
}

#: 🔁 cycle290(킬스위치 등재, 2026-09-13) 재핀 — `DEFAULT_PARAMS` 말미에
#: `order_exchange_clock_mode`·`after_market_exit_division` 2키를 코드 상수와 같은
#: 값으로 추가한 것이 그 사이클의 **정당한 목적**이라(카탈로그가 값을 편집하는
#: 수단을 만드는 사이클이지만, 이 두 키는 카탈로그 등재와 짝을 이루는 등재 자체다),
#: 아래 docstring "값 변경은 이 사이클의 범위 밖" 은 **cycle278 한정**이고
#: cycle290 에는 적용되지 않는다 — cycle290 은 이 세그먼트를 정당하게 갱신했다.
_DEFAULT_PARAMS_SHA: dict[str, tuple[str, str, str]] = {
    # 전략 id: (파일, 클래스, cycle290 기준 세그먼트 sha256 — 구 base 34ba9e6 값은 git 이력)
    "momentum": (
        "src/engine/strategies/momentum.py", "MomentumStrategy",
        "2bdedaaa5d676c4daac38e6bbaff73fbfdf0d2fc56744bb974e5adcc1ba895ee"),
    "volatility_breakout": (
        "src/engine/strategies/volatility_breakout.py", "VolatilityBreakoutStrategy",
        "f91b1acc5ebf7278e7a4a85419a415b8cb4c6ec70cc19d8fac8e789e4e3751a0"),
    "long_tail_volatility": (
        "src/engine/strategies/long_tail_volatility.py", "LongTailVolatilityStrategy",
        "41e0b7b5a790c11af934bf3dea1895463b5fc569d42b940db6ef36639279d96e"),
    "donchian_swing": (
        "src/engine/strategies/donchian_swing.py", "DonchianSwingStrategy",
        "ea85f925555b2a4b99a718451099d2e32fbfa5e0f350590909b6162d9b716b31"),
    "bull_flag_breakout": (
        "src/engine/strategies/bull_flag_breakout.py", "BullFlagBreakoutStrategy",
        "bd1a80167f0bf0c3cc90ddbd1c95ba58abde05e3cdd6df7add483c7a862a6eaf"),
    "vcp_breakout": (
        "src/engine/strategies/vcp_breakout.py", "VcpBreakoutStrategy",
        "f56226ba2f7f71a98f9a4b8b9e7c8fa8169457ad2d1658ec3bbfac4a8433ba1b"),
    "kojiro": (
        "src/engine/strategies/kojiro.py", "KojiroStrategy",
        "e7ff138a438d58dfcf509728ec552d0a1920537799ac5ec37c83751d573e068b"),
}


def test_param_ranges_source_segment_sha_unchanged():
    """B67/C32 — `PARAM_RANGES` 소스 세그먼트 불변.

    UI 편집 가능성과 **AI 자동 조정 가능성은 별개다**. 이 사이클은 후자를 넓히지 않는다 —
    카탈로그가 `auto_tunable` 을 붙였다고 이 dict 를 손대면 그 순간 자문이 그 키를 흔든다.
    """
    key = (_RECO, "PARAM_RANGES", None)
    assert _segment_sha(*key) == _SEGMENT_SHA[key], (
        "PARAM_RANGES 가 바뀌었다 — cycle278 은 자동 튜너 무접촉이다"
    )


def test_int_params_source_segment_sha_unchanged():
    """B68/C32 — `INT_PARAMS` 소스 세그먼트 불변."""
    key = (_RECO, "INT_PARAMS", None)
    assert _segment_sha(*key) == _SEGMENT_SHA[key], "INT_PARAMS 가 바뀌었다 — 자동 튜너 무접촉 위반"


@pytest.mark.parametrize("strategy_id", sorted(_DEFAULT_PARAMS_SHA))
def test_seven_strategy_default_params_source_sha_unchanged(strategy_id: str):
    """B69/C33 — 7 전략 `DEFAULT_PARAMS` **값** 불변(소스 세그먼트 sha 7핀).

    ⚠️ **핀을 먼저 재산출하지 마라** — 그 순간 실제 변경이 새 스냅샷으로 봉인된다.
    이 사이클은 파라미터 *값* 을 바꾸지 않으므로 재산출할 일이 없다.
    """
    rel, cls_name, expected = _DEFAULT_PARAMS_SHA[strategy_id]
    assert _segment_sha(rel, "DEFAULT_PARAMS", cls_name) == expected, (
        f"{strategy_id}: DEFAULT_PARAMS 가 cycle290 기준선에서 또 바뀌었다 — 값 변경은"
        " cycle278/290 범위 밖(사람이 화면에서 고치는 것이 cycle278 의 산출물이고,"
        " cycle290 은 킬스위치 2키 등재만 정당하다)"
    )


# ===========================================================================
# C31 — 8영역 · scheduler · strategy_base · 전략 7파일 내용 sha 불변
# ===========================================================================
# 🔁 2026-09-11 (cycle283) 재핀 — `scanner.py`(8영역, 사용자 승인)·`scheduler.py`(라인 상한
#    승인 대상) 2건. cycle278 이 그 파일들을 건드린 것이 아니라 **다른 사이클의 승인된
#    변경**이므로 값만 현재 워킹트리로 재산출했다. 나머지 핀은 불변이다.
# 🔁 2026-09-12 (cycle286) 재핀 — `order_engine.py`(C4-a, 8영역 사용자 승인)·
#    `long_tail_volatility.py`(C2-a, 전략 7파일 목록 대상 — 승인 항목) 2건. 값만
#    현재 워킹트리로 재산출했다.
_BASE_SHA = {
    "src/engine/risk.py":
        "e8614235cc0bea638f8c349b2f6910c94f5f9a5b849f5d65bef0583f959d81c9",
    "src/engine/order_engine.py": "84e84a972774cd2fbf8ceb70e5569f7760d43a228c2be21d2a1b90f48fd4ce75",
    "src/engine/session.py":
        "36257d86af1c26a868dc991a74a9eb139c98a9358d739d24600f5be2f9c5666c",
    "src/engine/scanner.py":
        "079272e7c4907c6ecc5fdf9b73de70021a9dc2435c7a568538183a7ead98804f",
    "src/engine/strategy_registry.py":
        "d794696e54ffdc36efa6df917879d780e86bc1f373bb3b5d8dcbc0beac8cef8b",
    "src/api/order.py":
        "08c5cafd7b8678ec0d0fa85f856fdea3cce38ad92488c6d74c03cd13faa415bb",
    "src/auth/token.py":
        "049341c7286b57a06337b6bc73ff4b0269efffad8f4554d97f275e7b8ec30a54",
    "src/auth/hashkey.py":
        "7c2aacc703839bdc274b463ee48777006504d70e4d59a1e57120ac5b612396d2",
    "src/realtime/handler.py":
        "23768e6d89ed54b626cce2645a07cc5472ce10120c0b1c81f5d6436ff521ed47",
    "src/realtime/websocket.py":
        "d4c443bde2ed7aeafba3e9471db0ca4efc15a654610555435145a9b305150c5b",
    "src/realtime/websocket_pool.py":
        "8b02442bcf5f558d6f7095b47d2016f004e3746e07ddc91dae8768b1dd46a10d",
    # ⚠️ cycle292(2026-09-14) 재핀 — `_subscribe_market_operation_tickers` 176줄을
    # 신규 leaf `src/engine/market_op_subscribe.py` 로 추출(행위 변경 0 · 5줄 위임
    # wrapper · 3,897→3,726L, 사용자 승인). 여섯 자매 핀(cycle274/276/278/282/290/291)
    # 을 **한 값으로 동시에** 옮겼다 — 한 곳만 넣으면 나머지가 "코드를 되돌려라" 로
    # 붉어져 승인된 변경을 되돌리도록 오도한다. 직전 값 =
    # `50658e06062a0d38afecab1baa08871b89212e295cc95f2a3af62a2ae076115d`.
    "src/engine/scheduler.py":
        "9bf05ccae11bd0c12d5275f36be70863decd83f1f34d77352f505bc15e549d8a",
    "src/engine/strategy_base.py":
        "869dc20ca561adc561a9ebe9fdb5fe5a3e097f7ec176fdf274d577d509de9252",
    # 🔁 cycle290(킬스위치 등재, 2026-09-13) 재핀 — `DEFAULT_PARAMS` 말미 2키 추가뿐.
    "src/engine/strategies/momentum.py":
        "4d7fac9abab4d5fca55509a8682633d31c4bb9868f5bb4cc77d4771ecda68894",
    "src/engine/strategies/volatility_breakout.py": "d13efaa4a9424e2822b5476ce159987d2a5192a4bca30af3f1a0cae9c3ffcabc",
    "src/engine/strategies/long_tail_volatility.py": "51b50560a1240df3fc6085da7253438605079d7d453ff3e77a806e814473be25",
    "src/engine/strategies/donchian_swing.py":
        "1db81a3966985fc23baf64996134af07ac81c90e56b90d8405c46f5b1efce880",
    "src/engine/strategies/bull_flag_breakout.py":
        "f63ee57cd169e4472f24fa76b26ca9ca63e69a1a170da8e57c822fd0028f2ebe",
    "src/engine/strategies/vcp_breakout.py":
        "09c7e1aa02493d678844c06f5850200dcb93f1e08d062d11468c220e5450d727",
    "src/engine/strategies/kojiro.py":
        "eb8057d44c86cfe73088aa65d2036b715ce1a979aab08c47b7a7fb3363f58c65",
}


#: 8영역의 **정본 목록** — 리터럴을 두 번 적지 않고 그 파일에서 가져온다.
#: (루트 CLAUDE.md: "정본 목록 = `tests/unit/ast/test_cycle222a3_ast_followup_fixes.py::
#: _EIGHT_AREAS`") 종전 이 파일은 20 경로를 손으로 적어 두었고, 그 목록에서 한 줄이
#: 빠지면 그 파일은 **조용히 검사되지 않았다** — 무접촉 가드가 공허해지는 전형이다.
_EXTRA_PINNED = (
    "src/engine/scheduler.py",
    "src/engine/strategy_base.py",  # ⚠️ `src/engine/` 바로 아래다(`strategies/` 안이 아니다)
) + tuple(
    f"src/engine/strategies/{name}.py"
    for name in (
        "momentum",
        "volatility_breakout",
        "long_tail_volatility",
        "donchian_swing",
        "bull_flag_breakout",
        "vcp_breakout",
        "kojiro",
    )
)


def _canonical_eight_area_files() -> list[str]:
    """정본 `_EIGHT_AREAS` 를 파일 경로로 펼친다(디렉터리 항목은 그 안의 `.py` 전부)."""
    from tests.unit.ast.test_cycle222a3_ast_followup_fixes import _EIGHT_AREAS

    out: list[str] = []
    for entry in _EIGHT_AREAS:
        target = _ROOT / entry
        assert target.exists(), (
            f"정본 8영역 항목 `{entry}` 가 실재하지 않는다 — 경로가 바뀌었다면"
            " 두 가드 파일을 함께 고친다(존재하지 않는 경로에 건 무접촉 단언은 공허하다)"
        )
        if target.is_dir():
            out += [
                q.relative_to(_ROOT).as_posix()
                for q in sorted(target.rglob("*.py"))
                if q.name != "__init__.py"
            ]
        else:
            out.append(entry)
    return out


def test_pinned_paths_exist_on_disk():
    """가드가 **실재하는** 파일을 잰다.

    존재하지 않는 경로를 대상으로 한 무접촉 단언은 조용히 통과한다(`git diff` 는 0줄,
    glob 은 빈 집합). 그래서 sha 를 비교하기 **전에** 실재를 먼저 못박는다.
    `strategy_base.py` 는 `src/engine/` 바로 아래이고 `src/engine/strategies/` 안이 아니다 —
    실제로 틀리기 쉬운 경로라 명시한다.
    """
    missing = [rel for rel in sorted(_BASE_SHA) if not (_ROOT / rel).is_file()]
    assert not missing, f"핀 대상이 실재하지 않는다: {missing}"

    for rel in _EXTRA_PINNED:
        assert (_ROOT / rel).is_file(), f"{rel} 이 없다 — 경로 오타이거나 파일이 이동했다"
    assert (_ROOT / "src/engine/strategy_base.py").is_file()
    assert not (_ROOT / "src/engine/strategies/strategy_base.py").exists(), (
        "strategy_base.py 가 strategies/ 안에도 생겼다 — 어느 쪽이 정본인지 먼저 정한다"
    )


def test_base_sha_covers_canonical_eight_areas_and_extras():
    """`_BASE_SHA` 가 정본 8영역 전부 + scheduler·strategy_base·전략 7파일을 덮는다.

    핀 목록에서 한 줄이 빠지면 그 파일은 이 사이클의 무접촉 증거에서 **누락된 채**
    가드가 초록이다. 정본 목록과 대조해 그 누락을 붉힌다.
    """
    canonical = set(_canonical_eight_area_files())
    pinned = set(_BASE_SHA)

    assert canonical <= pinned, (
        f"정본 8영역인데 핀에 없는 파일: {sorted(canonical - pinned)}"
        " — 8영역에 파일이 늘었으면 sha 를 등록한다"
    )
    assert set(_EXTRA_PINNED) <= pinned, (
        f"핀에 없는 필수 대상: {sorted(set(_EXTRA_PINNED) - pinned)}"
    )
    assert pinned == canonical | set(_EXTRA_PINNED), (
        f"핀에만 있고 어느 목록에도 없는 경로: {sorted(pinned - canonical - set(_EXTRA_PINNED))}"
    )


@pytest.mark.parametrize("rel", sorted(_BASE_SHA))
def test_eight_areas_and_scheduler_and_strategy_base_untouched(rel: str):
    """B70/C31 — 8영역 · `scheduler.py` · `strategy_base.py` · 전략 7파일 **byte 동일**.

    값은 브랜치 base `34ba9e6` 의 blob sha256(`git show 34ba9e6:<path> | shasum -a 256`).
    """
    assert _content_sha(rel) == _BASE_SHA[rel], (
        f"{rel} 이 base(34ba9e6) 와 다르다 — cycle278 무접촉 위반"
        " (파라미터 편집 수단을 만드는 사이클이 매매 코드를 건드렸다)"
    )


def test_realtime_and_auth_have_no_new_python_files():
    """B70b/C31 — `src/realtime/**`·`src/auth/**` 에 신규 `.py` 가 생기지 않았다."""
    seen = {
        p.relative_to(_ROOT).as_posix()
        for d in ("realtime", "auth")
        for p in (_SRC / d).rglob("*.py")
        if p.name != "__init__.py"
    }
    assert seen <= set(_BASE_SHA), f"8영역 디렉터리에 신규 파일: {sorted(seen - set(_BASE_SHA))}"


# ===========================================================================
# C34 — 읽는 쪽 하드 클램프 6곳 존재 (M14)
# ===========================================================================
_CLAMP_SITES: tuple[tuple[str, str, str | None, tuple[str, ...]], ...] = (
    (
        "max_lot_units", "src/engine/strategy_base.py", None,
        ("_MAX_LOT_UNITS_MIN = 1.0", "_MAX_LOT_UNITS_MAX = 20.0",
         "k < _MAX_LOT_UNITS_MIN", "k > _MAX_LOT_UNITS_MAX"),
    ),
    (
        "max_lot_ratio_mult", "src/engine/strategy_base.py", None,
        ("_MAX_LOT_RATIO_MULT_MIN = 1.0", "_MAX_LOT_RATIO_MULT_MAX = 20.0",
         "k < _MAX_LOT_RATIO_MULT_MIN", "k > _MAX_LOT_RATIO_MULT_MAX"),
    ),
    (
        "open_entry_hold_secs(VB)", "src/engine/strategies/volatility_breakout.py",
        "_read_open_entry_hold_secs",
        ("if secs < 0:", "min(secs, OPEN_ENTRY_HOLD_MAX_SECS)"),
    ),
    (
        "open_entry_hold_secs(LTV)", "src/engine/strategies/long_tail_volatility.py",
        "_read_open_entry_hold_secs",
        ("if secs < 0:", "min(secs, OPEN_ENTRY_HOLD_MAX_SECS)"),
    ),
    (
        "llm_gate_min_score", "src/engine/llm_buy_gate.py", "_read_min_score",
        ("1 <= val <= 100",),
    ),
    (
        "llm_gate_daily_call_cap / llm_gate_timeout_secs", "src/engine/llm_buy_gate.py",
        None, ("max(0, min(200, val))", "max(1, min(60, val))"),
    ),
)


@pytest.mark.parametrize(
    ("label", "rel", "func", "needles"),
    _CLAMP_SITES,
    ids=[s[0] for s in _CLAMP_SITES],
)
def test_reading_side_clamps_still_present(label, rel, func, needles):
    """B71/C34 — 읽는 쪽 하드 클램프는 라우트 422 가 생겨도 **남는다**(HAZARD-7).

    DB 직접 UPDATE · 구버전 행 · 부팅 로드는 라우트를 거치지 않는다. 라우트 검증이
    생겼다고 이 클램프를 "중복"으로 지우면 그 경로가 전부 무방비가 된다.
    """
    body = _func_segment(rel, func) if func else _read(rel)
    for needle in needles:
        assert needle in body, f"{label}: `{needle}` 가 사라졌다 ({rel}) — 읽는 쪽 클램프 제거"


def test_open_entry_hold_max_secs_constant_is_600():
    """B71b/C34 — `[0, 600]` 클램프 상한 상수 자체가 두 전략에 존재한다."""
    for rel in ("src/engine/strategies/volatility_breakout.py",
                "src/engine/strategies/long_tail_volatility.py"):
        assert "OPEN_ENTRY_HOLD_MAX_SECS = 600" in _read(rel), rel


# ===========================================================================
# C35 — 프론트 키 하드코딩 0건 (⚠️ 프론트 파일을 읽는 백엔드 가드)
# ===========================================================================
_EDITOR_TSX = "frontend/src/components/StrategyParamsEditor.tsx"
_STRATEGIES_TSX = "frontend/src/pages/Strategies.tsx"
_SETTINGS_TSX = "frontend/src/pages/Settings.tsx"

_THRESHOLD_KEYS = frozenset({
    "stop_loss_rate", "daily_loss_limit", "trailing_stop_rate", "position_ratio",
})

#: 파일별 허용 키(명세 C35 의 예외 ①②). 그 밖은 **스키마 응답으로만** 렌더한다.
_FRONT_ALLOW: dict[str, frozenset[str]] = {
    _EDITOR_TSX: frozenset(),
    _STRATEGIES_TSX: _THRESHOLD_KEYS,
    _SETTINGS_TSX: frozenset({"exchange", "tradable_boards"}),
}


def _hardcoded_keys(rel: str) -> dict[str, int]:
    body = _read(rel)
    found: dict[str, int] = {}
    for key in pc.all_keys():
        hits = len(re.findall(rf"(?<![A-Za-z0-9_]){re.escape(key)}(?![A-Za-z0-9_])", body))
        if hits:
            found[key] = hits
    return found


@pytest.mark.parametrize("rel", sorted(_FRONT_ALLOW))
def test_frontend_editor_files_have_no_param_key_literals(rel: str):
    """B72/C35 — 편집 3파일에 99키 리터럴 0건(예외 ①②만 허용).

    키를 프론트에 하드코딩하면 **재드리프트가 그날부터 다시 시작된다** — 지금의 24키
    화이트리스트가 99키 중 73키를 화면 밖에 남겨 둔 것이 바로 그 결과다.
    화면은 `GET /api/strategies/params-schema` 응답 하나로 렌더하고, 포맷은
    키가 아니라 `unit`/`type` 으로 분기한다.
    """
    offenders = {
        k: n for k, n in _hardcoded_keys(rel).items() if k not in _FRONT_ALLOW[rel]
    }
    assert not offenders, (
        f"{rel}: 허용 밖 파라미터 키 하드코딩 {sorted(offenders)} — 예외는"
        f" {sorted(_FRONT_ALLOW[rel]) or '없음'} 뿐이다"
    )


@pytest.mark.parametrize("rel", sorted(_FRONT_ALLOW))
def test_frontend_editor_files_do_not_import_param_labels_util(rel: str):
    """B73/C36 — 편집 3파일은 `utils/paramLabels` 를 import 하지 않는다.

    그 파일은 24키 하드코딩 카탈로그다 — 편집 화면이 그것을 계속 쓰면 이 사이클이
    아무 것도 바꾸지 못한다. 단 **삭제하지는 않는다**: `pages/Recommendations.tsx`
    (AI 자문 추천 표)가 계속 쓰며, 지우면 그 화면이 영문 키로 퇴행한다.
    """
    body = _read(rel)
    assert "paramLabels" not in body, (
        f"{rel}: `utils/paramLabels`(구 24키 카탈로그) import — 스키마 응답으로 대체해야 한다"
    )


def test_param_labels_util_is_kept_for_recommendations():
    """B73b/C36 — `utils/paramLabels.ts` 와 그 유일한 소비처는 **남는다**."""
    assert (_ROOT / "frontend/src/utils/paramLabels.ts").exists(), (
        "paramLabels.ts 를 지우면 AI 자문 추천 표가 영문 키로 퇴행한다"
    )
    assert "paramLabels" in _read("frontend/src/pages/Recommendations.tsx")


def test_threshold_keys_exception_is_exactly_four_and_documented():
    """B74/C35 — 요약 그리드 예외는 정확히 4키이고 가드와 화면이 같은 목록을 본다."""
    body = _read(_STRATEGIES_TSX)
    match = re.search(r"const\s+THRESHOLD_KEYS\s*=\s*\[(.*?)\]", body, re.S)
    assert match, f"{_STRATEGIES_TSX}: THRESHOLD_KEYS 배열을 찾지 못했다"
    keys = frozenset(
        a or b for a, b in re.findall(r"'([a-z0-9_]+)'|\"([a-z0-9_]+)\"", match.group(1))
    )
    assert keys == _THRESHOLD_KEYS, f"THRESHOLD_KEYS={sorted(keys)} 기대={sorted(_THRESHOLD_KEYS)}"
    assert keys <= set(pc.all_keys()), "요약 4키가 카탈로그에 없다"
    assert _FRONT_ALLOW[_STRATEGIES_TSX] == keys, "가드 허용 목록과 화면 상수가 어긋났다"

    doc = __doc__ or ""
    assert "THRESHOLD_KEYS" in doc and "ExchangeBoardRow" in doc, (
        "예외 2건은 이 가드 파일 헤더에 문서화돼 있어야 한다"
    )


# ===========================================================================
# C10 (AST 계층) · §2 — 신규 leaf 의 순수성
# ===========================================================================
def test_catalog_module_has_no_src_imports():
    """B75/C10 — `param_catalog.py` 는 `src.*` 를 import 하지 않는다.

    카탈로그가 엔진을 끌어오면 라우트·도구·테스트가 그 무게를 함께 진다.
    (테스트 계층 이중화: 데이터 계약 쪽 B23 와 별개로 여기서도 잠근다.)
    """
    tree = ast.parse(_read("src/engine/param_catalog.py"))
    bad: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            bad += [a.name for a in node.names if a.name.startswith("src.")]
        elif isinstance(node, ast.ImportFrom) and (node.module or "").startswith("src"):
            bad.append(node.module or "")
    assert not bad, f"param_catalog.py 가 src.* 를 import 한다: {bad}"


def test_param_validation_module_is_leaf_importing_only_catalog():
    """B75b/§2 — 검증 leaf `src/engine/param_validation.py` 는 카탈로그만 import 한다.

    순수 함수로 뽑아 두는 이유(명세 §2): 라우트 없이 테스트할 수 있고, AI 자문 적용
    경로(`routes/recommendations.py`)에 후속 사이클이 같은 함수를 붙이는 것이 한 줄이 된다.
    """
    tree = ast.parse(_read("src/engine/param_validation.py"))
    src_imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            src_imports += [a.name for a in node.names if a.name.startswith("src.")]
        elif isinstance(node, ast.ImportFrom) and (node.module or "").startswith("src"):
            src_imports.append(node.module or "")
    assert set(src_imports) <= {"src.engine.param_catalog", "src.engine"}, (
        f"param_validation 이 카탈로그 밖을 import 한다: {sorted(set(src_imports))}"
        " — 순수 함수 계층이 깨지면 라우트 없이 검증을 테스트할 수 없다"
    )
    banned = {"open", "requests", "logging", "asyncio"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            assert name not in banned, f"param_validation 에 I/O 호출 {name}() (line {node.lineno})"
