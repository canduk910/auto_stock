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

## 핀의 자리

`_SEGMENT_SHA`(`PARAM_RANGES`/`INT_PARAMS`/7 `DEFAULT_PARAMS` 소스 세그먼트 sha)는 이 파일의
내용 계약이다 — 그 구간을 정당하게 바꾸는 사이클이 값을 옮긴다. 8영역 + `scheduler.py` 파일
내용 sha 는 정본 `test_cycle222a3_ast_followup_fixes.py::_APPROVED_CONTENT_SHA` 한 곳에만
둔다(cycle419 — 이 파일의 C31 파일 핀은 걷었다).

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


def _read(rel: str) -> str:
    path = _ROOT / rel
    assert path.exists(), f"{rel} 이 없다 (Red — Green 이 만든다)"
    return path.read_text(encoding="utf-8")


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

#: 🔁 cycle365(2026-09-25, 사용자 승인 P5b) 재핀 — `max_scan_stocks` 상한 500→4000.
#: kojiro/BFB/VCP 운영 기본값(4000)을 PARAM_RANGES 가 못 담아 AI 자문이 매일 500
#: (유니버스 87% 축소)을 권고하던 결함(`_workspace/reports/2026-09-25_daily_and_advice_review.md`
#: §5 P5)의 근본 시정이다 — 값 변경이 이 사이클의 **정당한 목적**이라 재핀했다.
#: 나머지 키·`INT_PARAMS` 는 무접촉이다.
_SEGMENT_SHA: dict[tuple[str, str, str | None], str] = {
    (_RECO, "PARAM_RANGES", None):
        "7d69e4aa30437c0544c5f1151f001d4af6b8376ce24c284d8137f907cc1e499b",
    (_RECO, "INT_PARAMS", None):
        "c2a0d4d45123c409c5e977b787dab0a44b25f90920d2969e15338d0fef679066",
}

#: 🔁 cycle290(킬스위치 등재, 2026-09-13) 재핀 — `DEFAULT_PARAMS` 말미에
#: `order_exchange_clock_mode`·`after_market_exit_division` 2키를 코드 상수와 같은
#: 값으로 추가한 것이 그 사이클의 **정당한 목적**이라(카탈로그가 값을 편집하는
#: 수단을 만드는 사이클이지만, 이 두 키는 카탈로그 등재와 짝을 이루는 등재 자체다),
#: 아래 docstring "값 변경은 이 사이클의 범위 밖" 은 **cycle278 한정**이고
#: cycle290 에는 적용되지 않는다 — cycle290 은 이 세그먼트를 정당하게 갱신했다.
#: 🔁 cycle301(2026-09-18, 사용자 승인 D3·D4) 재핀 — `vcp_breakout` 만 대상.
#: `ema_mid` 60→150 · `ema_long` 120→200 · `min_swing_atr_mult` 0.5→1.0 (운영 DB
#: 실측 정합, 미너비니 원설계 복귀). 값 변경이 이 사이클의 **정당한 목적**이라
#: 재핀했다 — 나머지 6전략 핀은 불변이다.
#: 🔁 cycle384 재핀 — buy_paused 공통 파라미터(사용자 결정 09-27 「돈키언 신규매수
#: 중지」). 7 전략 전부 `DEFAULT_PARAMS` 말미(정확히는 `max_lot_ratio_mult` 다음
#: 줄)에 `"buy_paused": False` 1키 추가. 값 자체는 매매 행위를 바꾸지 않는다
#: (기본 false — 게이트가 읽어 멈추지 않는 것과 byte 동일). 나머지 서술은 그대로다.
_DEFAULT_PARAMS_SHA: dict[str, tuple[str, str, str]] = {
    # 전략 id: (파일, 클래스, cycle384 기준 세그먼트 sha256 — 구 cycle290/352/382 값은 git 이력)
    "momentum": (
        "src/engine/strategies/momentum.py", "MomentumStrategy",
        # 🔁 cycle399 재핀 — 공통 섀도 모드(사용자 승인 10-02 R1) — `"shadow_mode": False` 1줄 추가(`buy_paused` 다음 줄). 그 밖 무변경.
        "f9d286877cd7846f55da0b2f4236c95135d0b89600560e909e8ba5adb0a7f0de"),
    "volatility_breakout": (
        "src/engine/strategies/volatility_breakout.py", "VolatilityBreakoutStrategy",
        # 🔁 cycle399 재핀 — 공통 섀도 모드(사용자 승인 10-02 R1) — `"shadow_mode": False` 1줄 추가(`buy_paused` 다음 줄). 그 밖 무변경.
        "899a61a19a28c4b0f09a5ec35c62c682ef83b36f3a62d5f7a8961eb2570bdd99"),
    # 🔁 cycle352 재핀 — 15:20 상한가 유지 확인 킬스위치 `limit_up_close_hold_mode`
    #    1키 추가(사용자 승인). 구 값(cycle290 기준선)은 git 이력에 남는다.
    "long_tail_volatility": (
        "src/engine/strategies/long_tail_volatility.py", "LongTailVolatilityStrategy",
        # 🔁 cycle399 재핀 — 공통 섀도 모드(사용자 승인 10-02 R1) — `"shadow_mode": False` 1줄 추가(`buy_paused` 다음 줄). 그 밖 무변경.
        "662696e377d3e9c8950398738f453df48f7ed6bfe2c8429e6106fae94976462c"),
    # 🔁 cycle382 재핀(사용자 결정 09-27) — `DEFAULT_PARAMS` 말미에 `market_unit_mode`
    # 1키 추가(4전략 전부). 값은 코드 기본값 "shadow" — 매매 행위는 배선(별도
    # 헬퍼 호출)이 아니라 이 키의 값 자체로는 바뀌지 않는다(모드가 off/shadow
    # 인 동안은 현행 byte 동일, R17 로 검증).
    "donchian_swing": (
        "src/engine/strategies/donchian_swing.py", "DonchianSwingStrategy",
        # 🔁 cycle405 재핀 — 깡토식 청산·사이징 개조(사용자 승인) — `position_ratio`·
        # `max_positions`·`sizing_mode`·`risk_pct` 값 변경 + `kk_*`/`max_daily_entries`
        # 신규 7키 추가. 직전 값(cycle399) = `665679d3608a173e5a344ca1e37896df75635f9599be9cf7b280b04f03848802`.
        "f6bba104b9f17a9bead47acb449eeb577dc881283576cf161d1730253863beb1"),
    "bull_flag_breakout": (
        "src/engine/strategies/bull_flag_breakout.py", "BullFlagBreakoutStrategy",
        # 🔁 cycle399 재핀 — 공통 섀도 모드(사용자 승인 10-02 R1) — `"shadow_mode": False` 1줄 추가(`buy_paused` 다음 줄). 그 밖 무변경.
        "ad2b0b5e02e4f9b2f371cad8c551b7ef9bef30cdff385d55eb4cc36eae9eefe4"),
    "vcp_breakout": (
        "src/engine/strategies/vcp_breakout.py", "VcpBreakoutStrategy",
        # 🔁 cycle399 재핀 — 공통 섀도 모드(사용자 승인 10-02 R1) — `"shadow_mode": False` 1줄 추가(`buy_paused` 다음 줄). 그 밖 무변경.
        "40353fd639002b9311536e3ce839603b511c0a0a1afa1882233d43083286f850"),
    "kojiro": (
        "src/engine/strategies/kojiro.py", "KojiroStrategy",
        # 🔁 cycle399 재핀 — 공통 섀도 모드(사용자 승인 10-02 R1) — `"shadow_mode": False` 1줄 추가(`buy_paused` 다음 줄). 그 밖 무변경.
        "1e7345ae17871c9bd4e56e27820740d76adbfc4fa35d025ed57cbad2ae57c0cb"),
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
