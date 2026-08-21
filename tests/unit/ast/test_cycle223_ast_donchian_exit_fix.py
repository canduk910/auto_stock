"""사이클 223 Red/가드 (AST) — donchian 청산 결함 시정(S1~S3) 범위 봉인.

> 자문: `_workspace/domain_consult/donchian_exit_retune.md`

이번 사이클의 의도적 수정은 **`src/engine/recommendation_engine.py`(S1) 와
`src/engine/strategies/donchian_swing.py`(S2·S3) 둘뿐**이다. 파라미터 **값은 하나도
바꾸지 않는다** — S2/S3 는 "세는 방법"과 "기준선 산식"만 고친다.

가드 목록:
- G-223-1 (S1): PARAM_RANGES dict / INT_PARAMS set **리터럴**에 2키 부재 (AST)
- G-223-2 (S1): 제거 사유가 208/209/212 관례대로 **주석으로** 남아 있다
- G-223-3 (S2): `_rederive_breakout_high` 창이 `prior[1: period+1]` · 길이 가드 `period+1`
- G-223-4 (S2, HIGH): **매수 경로 불변** — `prepare` 의 `max(highs[1: donchian_period + 1])`
- G-223-5 (S3, HIGH): `check_exit_signal` hot path 계약 — 신규 `await`/DB/HTTP 0
- G-223-6 (S3): `_business_days_held` 는 **동기** 순수함수 (async 금지)
- G-223-7 (S3): `prepare` / `recompute_held_atr` 가 `_trading_days` 캐시를 채운다
- G-223-8 (HIGH): 청산 **분기 순서** 불변 (하드손절 → 시간 → 채널 → 샹들리에)
- G-223-9 (HIGH): donchian DEFAULT_PARAMS 청산 7키 **값 불변**
- G-223-10 (HIGH): 8영역 diff 0 — **staged + unstaged + untracked** 전부 (사이클 223 G3.
  `git diff` 단독은 unstaged 만 봐서 `git add` 순간 눈을 감았다). cycle222-a pre-existing
  2파일은 **파일명이 아니라 diff sha 로** 면제 (`_PREEXISTING_DIFF_SHA`)
- G-223-11: 8영역에 donchian 청산 심볼 유입 0건
- G-223-12: 다른 전략 파일(kojiro/VCP/BFB) diff 0
- G-223-13: `_apply_high_since_buy_from_candles` 경계 불변 (H-1 계약)

Red 유효성: G-223-1/2/3/6/7 = FAIL · 나머지는 PASS(불변식 회귀 가드).
"""
from __future__ import annotations

import ast
import hashlib
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SRC = _REPO_ROOT / "src"
_RECO = _SRC / "engine" / "recommendation_engine.py"
_DONCHIAN = _SRC / "engine" / "strategies" / "donchian_swing.py"
_BASE = _SRC / "engine" / "strategy_base.py"

_EXCLUDED_KEYS = ("breakout_fail_n_days", "atr_trail_mult")


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _func(tree: ast.Module, name: str):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    return None


def _named_literal_str_keys(src: str, name: str) -> list[str]:
    """`name = {...}` (Assign/AnnAssign) 의 dict keys / set elts 문자열 리터럴."""
    tree = ast.parse(src)
    keys: list[str] = []
    for node in ast.walk(tree):
        value = None
        if isinstance(node, ast.Assign):
            if any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
                value = node.value
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name) and node.target.id == name:
                value = node.value
        if isinstance(value, ast.Dict):
            keys += [k.value for k in value.keys
                     if isinstance(k, ast.Constant) and isinstance(k.value, str)]
        elif isinstance(value, ast.Set):
            keys += [e.value for e in value.elts
                     if isinstance(e, ast.Constant) and isinstance(e.value, str)]
    return keys


# ===========================================================================
# G-223-1 (S1) — PARAM_RANGES / INT_PARAMS 리터럴 부재
# ===========================================================================
def test_g223_1_param_ranges_literal_absent():
    src = _read(_RECO)
    keys = _named_literal_str_keys(src, "PARAM_RANGES")
    assert keys, "PARAM_RANGES dict 리터럴 파싱 실패 (탐지기 결함)"
    assert "stop_loss_rate" in keys, "탐지기 self-test — 잔존 키 미검출"
    for key in _EXCLUDED_KEYS:
        assert key not in keys, (
            f"PARAM_RANGES dict 리터럴에 '{key}' 잔존 금지 (사이클 223 제거)"
        )


def test_g223_1b_int_params_literal_absent():
    src = _read(_RECO)
    keys = _named_literal_str_keys(src, "INT_PARAMS")
    assert keys, "INT_PARAMS set 리터럴 파싱 실패 (탐지기 결함)"
    assert "k_period" in keys, "탐지기 self-test — 잔존 키 미검출"
    assert "breakout_fail_n_days" not in keys, (
        "INT_PARAMS set 리터럴에 'breakout_fail_n_days' 잔존 금지 (사이클 223 제거)"
    )


# ===========================================================================
# G-223-2 (S1) — 제거 사유 주석 (208/209/212 관례)
# ===========================================================================
@pytest.mark.parametrize("key", _EXCLUDED_KEYS)
def test_g223_2_removal_reason_documented_as_comment(key):
    """제거된 키는 소스에서 **사라지지 않고 주석으로** 사유를 남긴다.

    선례: `max_positions` 제외(2026-08-03) 가 dict 안에 주석 블록을 남긴 형식.
    운영자가 "왜 이 키만 없나" 를 소스에서 바로 읽을 수 있어야 재편입 사고를 막는다.
    """
    src = _read(_RECO)
    comment_lines = [ln.strip() for ln in src.splitlines() if ln.strip().startswith("#")]
    assert any(key in ln for ln in comment_lines), (
        f"'{key}' 제거 사유 주석 부재 — 208/209/212 관례대로 사유를 남겨라"
    )
    assert "정체성 상수" in src, "제외 사유 관용구('정체성 상수') 부재"


# ===========================================================================
# G-223-3 (S2) — 재도출 창 / 길이 가드
# ===========================================================================
def test_g223_3_rederive_window_excludes_signal_day():
    fn = _func(ast.parse(_read(_DONCHIAN)), "_rederive_breakout_high")
    assert fn is not None, "_rederive_breakout_high 미발견"
    body = ast.unparse(fn)
    assert "prior[1:donchian_period + 1]" in body, (
        "S2: 재도출 창은 `prior[1: donchian_period + 1]` (신호일 봉 제외 = 매수 경로 동일 산식)"
    )
    assert "prior[:donchian_period]" not in body, (
        "S2: `prior[:donchian_period]` 는 신호일 봉을 포함한다 (off-by-one 잔존)"
    )
    assert "len(prior) < donchian_period + 1" in body, (
        "S2: 길이 가드도 `donchian_period + 1` 로 동반 조정 (조용한 과소 표본 차단)"
    )


# ===========================================================================
# G-223-4 (S2, HIGH) — 매수 경로 불변
# ===========================================================================
def test_g223_4_buy_path_prior_high_formula_unchanged():
    """`prepare` 의 돌파선 산식은 **정답 쪽** — 절대 접촉 금지."""
    fn = _func(ast.parse(_read(_DONCHIAN)), "prepare")
    assert fn is not None, "prepare 미발견"
    assert "prior_high = max(highs[1:donchian_period + 1])" in ast.unparse(fn), (
        "매수 경로 돌파선 산식 변경 감지 — 이번 사이클 금기"
    )


# ===========================================================================
# G-223-5 (S3, HIGH) — check_exit_signal hot path 계약
# ===========================================================================
def test_g223_5_check_exit_signal_no_await():
    """`risk.on_tick` 이 초당 수십~수백 회 호출하는 hot path — await 0건."""
    fn = _func(ast.parse(_read(_DONCHIAN)), "check_exit_signal")
    assert fn is not None, "check_exit_signal 미발견"
    assert not isinstance(fn, ast.AsyncFunctionDef), "check_exit_signal 은 동기 함수"
    awaited = [ast.unparse(n.value) for n in ast.walk(fn) if isinstance(n, ast.Await)]
    assert awaited == [], f"check_exit_signal 에 await 유입 — hot path 계약 위반: {awaited}"


def test_g223_5b_check_exit_signal_no_io_tokens():
    fn = _func(ast.parse(_read(_DONCHIAN)), "check_exit_signal")
    body = ast.unparse(fn)
    for banned in (
        "fetch_daily_candles", "get_recent_daily_normalized", "add_business_days",
        "pg.fetch", "pg.execute", "write_log", "insert_", "httpx", "kis_request",
        "kis_get_quote", "asyncio",
    ):
        assert banned not in body, (
            f"check_exit_signal 에 I/O 경로 `{banned}` 유입 — hot path 계약 위반"
        )


# ===========================================================================
# G-223-6 (S3) — `_business_days_held` 는 동기 순수함수
# ===========================================================================
def test_g223_6_business_days_helper_is_sync_and_pure():
    tree = ast.parse(_read(_DONCHIAN))
    fn = _func(tree, "_business_days_held")
    assert fn is not None, (
        "S3 계약 — `_business_days_held(buy_date, today) -> (int, bool)` 신설 의무"
    )
    assert not isinstance(fn, ast.AsyncFunctionDef), (
        "`_business_days_held` 는 hot path 에서 호출된다 — async 금지 "
        "(KIS add_business_days 는 async 라 사용 불가)"
    )
    body = ast.unparse(fn)
    assert not [n for n in ast.walk(fn) if isinstance(n, ast.Await)]
    for banned in ("fetch_daily_candles", "add_business_days", "pg.fetch", "pg.execute",
                   "write_log", "httpx", "kis_request"):
        assert banned not in body, f"`_business_days_held` 에 I/O `{banned}` 금지"


# ===========================================================================
# G-223-7 (S3) — 거래일 캐시 배선
# ===========================================================================
@pytest.mark.parametrize("fname", ["prepare", "recompute_held_atr"])
def test_g223_7_trading_days_cache_wired(fname):
    """이미 fetch 한 일봉으로 `_trading_days` 를 채운다 (KIS 신규 호출 0)."""
    fn = _func(ast.parse(_read(_DONCHIAN)), fname)
    assert fn is not None, f"{fname} 미발견"
    assert "_trading_days" in ast.unparse(fn), (
        f"S3 계약 — `{fname}` 이 거래일 캐시 `_trading_days` 를 갱신해야 한다"
    )


def test_g223_7b_trading_days_uses_shared_date_parser():
    """날짜 추출은 `_candle_trade_date` 위임 (KIS/정규화 키 양쪽 수용 — H-1 계약)."""
    src = _read(_DONCHIAN)
    assert "_candle_trade_date" in src, (
        "거래일 파싱은 StrategyBase._candle_trade_date 위임 — 3번째 복사본 금지"
    )


# ===========================================================================
# G-223-8 (HIGH) — 청산 분기 순서 불변
# ===========================================================================
def test_g223_8_exit_branch_order_unchanged():
    """①하드손절/BE → ②시간청산 → ③채널이탈 → ④샹들리에. 이번엔 계산만 고친다."""
    fn = _func(ast.parse(_read(_DONCHIAN)), "check_exit_signal")
    body = ast.unparse(fn)
    markers = [
        "donchian_turtle_stop",       # ① 하드손절(2ATR, BE 승격 내포)
        "도치안 시간 기반 청산",        # ② 시간청산
        "donchian_channel_exit",      # ③ 채널 이탈
        "도치안 스윙 트레일링",         # ④ 샹들리에
    ]
    idx = []
    for m in markers:
        assert m in body, f"청산 분기 마커 소실: {m}"
        idx.append(body.index(m))
    assert idx == sorted(idx), f"청산 분기 순서 변경 감지 — {list(zip(markers, idx))}"


# ===========================================================================
# G-223-9 (HIGH) — DEFAULT_PARAMS 청산 7키 값 불변
# ===========================================================================
def test_g223_9_donchian_exit_param_values_unchanged():
    """파라미터 값 변경 0 — 이번 사이클은 결함 시정만 한다 (자문 §5 S5 동결)."""
    tree = ast.parse(_read(_DONCHIAN))
    literal = None
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "DEFAULT_PARAMS" for t in node.targets
        ) and isinstance(node.value, ast.Dict):
            literal = node.value
            break
    assert literal is not None, "donchian DEFAULT_PARAMS dict 리터럴 파싱 실패"
    got = {}
    for k, v in zip(literal.keys, literal.values):
        if isinstance(k, ast.Constant) and isinstance(k.value, str):
            try:
                got[k.value] = ast.literal_eval(v)
            except Exception:
                pass
    expected = {
        "breakout_fail_n_days": 5,
        "atr_trail_mult": 2.0,
        "breakeven_promote_atr": 1.5,
        "channel_exit_period": 10,
        "stop_loss_rate": -7.0,
        "stop_atr": 2.0,
        "turtle_backstop_pct": -9.0,
    }
    for key, val in expected.items():
        assert got.get(key) == val, (
            f"청산 파라미터 값 변경 감지: {key} 기대 {val}, got {got.get(key)}"
        )


# ===========================================================================
# G-223-10 (HIGH) — 8영역 diff 0
# ===========================================================================
_EIGHT_AREAS = [
    "src/engine/risk.py",
    "src/engine/order_engine.py",
    "src/engine/scanner.py",
    "src/engine/session.py",
    "src/engine/strategy_registry.py",
    "src/api/order.py",
    "src/realtime",
    "src/auth",
]


# ---------------------------------------------------------------------------
# 워킹트리 스냅샷 헬퍼 (사이클 223 G3)
# ---------------------------------------------------------------------------
# `git diff` 단독은 **unstaged 만** 본다 — `git add` 하는 순간 이 안전망이 눈을 감는다
# (실증: 8영역 파일을 stage 하면 가드가 통과). 커밋 직전이 가드가 가장 필요한 시점이므로
# **`git diff HEAD`** (staged + unstaged) 로 비교하고, `git diff` 가 보지 못하는
# **신규(untracked)** 파일은 `git ls-files --others` 로 별도 확인한다.
def _git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=_REPO_ROOT, capture_output=True, text=True,
    ).stdout


def _changed_paths(paths: list[str]) -> list[str]:
    """staged + unstaged + untracked 를 모두 포함한 변경 경로."""
    tracked = _git("diff", "HEAD", "--name-only", "--", *paths).split()
    untracked = _git("ls-files", "--others", "--exclude-standard", "--", *paths).split()
    return sorted(set(tracked) | set(untracked))


def _diff_sha(path: str) -> str:
    """`path` 의 HEAD 대비 diff 내용 해시 — 면제를 **그 diff 한 벌**에 못박는다."""
    return hashlib.sha256(_git("diff", "HEAD", "--", path).encode("utf-8")).hexdigest()


# 사이클 222-a(앵커 blind 내성) 작업이 워킹트리에 pre-existing 으로 존재한다. 이번
# 사이클이 **새로** 건드리면 안 되는 것이 계약이므로 baseline 으로 명시한다.
#
# ⚠️ 면제는 **파일명이 아니라 그 diff 한 벌(sha256)** 에 건다. 파일명 집합 면제는
# 영구다 — cycle222-a 가 커밋된 뒤에도 두 파일이 영원히 무시되고, F2 가 스스로 쓴
# *"제외 결정이 한쪽 경로에만 걸리면 제외가 아니다"* 가 그대로 적용된다. 내용 핀은
# **자기소멸**한다: cycle222-a 가 커밋되면 그 경로는 `git diff HEAD` 에 더 이상
# 나타나지 않아 면제가 조회조차 되지 않고, 그 뒤 누가 같은 파일을 새로 건드리면
# sha 불일치로 FAIL 한다.
#
# TODO(cycle222-a 커밋 후): 아래 dict 항목을 **삭제**한다. 커밋 시점부터 항목은
# 무효(조회 불가)이므로 삭제는 청소이지 행위 변경이 아니다.
_PREEXISTING_DIFF_SHA = {
    "src/engine/risk.py": "8a1193a9858bef73bff367ac0b3081e11895b2d5081bc1a464932d9fab0220b5",
    "src/realtime/handler.py": "9d51cfcf9ea32d6d18608968ebfc4659c863515f1be02c0b0d1b0e3c08b452b0",
}


def test_g223_10_eight_areas_diff_zero():
    changed = _changed_paths(_EIGHT_AREAS)
    unexpected = sorted(set(changed) - set(_PREEXISTING_DIFF_SHA))
    assert unexpected == [], f"8영역 신규 변경 감지 — 범위 밖: {unexpected}"
    for path in sorted(set(changed) & set(_PREEXISTING_DIFF_SHA)):
        assert _diff_sha(path) == _PREEXISTING_DIFF_SHA[path], (
            f"{path} 의 diff 가 cycle222-a 스냅샷과 다르다 — 이번 사이클 변경이 얹혔거나 "
            "cycle222-a 가 갱신됐다. 면제는 파일명이 아니라 **이 diff 한 벌**에만 걸린다."
        )


def test_g223_11_eight_areas_have_no_donchian_exit_symbols():
    """donchian 청산 심볼이 8영역으로 새지 않는다 (커플링 차단)."""
    tokens = ("_trading_days", "_business_days_held", "_rederive_breakout_high",
              "breakout_fail_n_days", "_breakout_high")
    targets: list[Path] = []
    for rel in _EIGHT_AREAS:
        p = _REPO_ROOT / rel
        targets += sorted(p.rglob("*.py")) if p.is_dir() else [p]
    for path in targets:
        src = _read(path)
        for tok in tokens:
            assert tok not in src, f"{path.relative_to(_REPO_ROOT)} 에 `{tok}` 유입 금지"


# ===========================================================================
# G-223-12 — 다른 전략 파일 diff 0
# ===========================================================================
def test_g223_12_other_strategy_files_diff_zero():
    others = [
        "src/engine/strategies/kojiro.py",
        "src/engine/strategies/vcp_breakout.py",
        "src/engine/strategies/bull_flag_breakout.py",
        "src/engine/strategies/momentum.py",
        "src/engine/strategies/volatility_breakout.py",
        "src/engine/strategies/long_tail_volatility.py",
    ]
    existing = [p for p in others if (_REPO_ROOT / p).exists()]
    # staged 도 본다 (사이클 223 G3 — `git diff` 단독은 unstaged 만)
    out = " ".join(_changed_paths(existing))
    assert out == "", f"다른 전략 파일 변경 감지 — 범위 밖: {out}"


# ===========================================================================
# G-223-13 — `_apply_high_since_buy_from_candles` 경계 불변 (H-1 계약)
# ===========================================================================
def test_g223_13_high_recover_boundary_unchanged():
    fn = _func(ast.parse(_read(_BASE)), "_apply_high_since_buy_from_candles")
    assert fn is not None, "_apply_high_since_buy_from_candles 미발견"
    assert "pos.buy_date < bd < today" in ast.unparse(fn), (
        "H-1 과대복구 차단 경계(양쪽 strict) 변경 감지 — 이번 사이클 금기"
    )
