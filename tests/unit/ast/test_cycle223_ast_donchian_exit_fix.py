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
- G-223-10: 8영역 무접촉은 정본 승인 도장 `test_cycle222a3_ast_followup_fixes.py::
  _APPROVED_CONTENT_SHA` 한 곳이 진다(cycle419 — 이 파일의 diff-0 사본은 걷었다)
- G-223-11: 8영역에 donchian 청산 심볼 유입 0건
- G-223-13: `_apply_high_since_buy_from_candles` 경계 불변 (H-1 계약)

Red 유효성: G-223-1/2/3/6/7 = FAIL · 나머지는 PASS(불변식 회귀 가드).
"""
from __future__ import annotations

import ast
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
    """청산 분기 순서 — cycle405 깡토식으로 재정의(명세 `_workspace/red/cycle405_donchian_kkangto_spec.md` §2).

    옛 순서(①하드손절/BE → ②시간청산 → ③채널 → ④샹들리에)는 끝났다. 지금 지키는 것:
    보유일 관측 → ① −1R·본전 손절(`STOP_LOSS`) → ② 3R 무장 뒤 채널(`TRAILING_STOP`).
    시간 청산(`TIME_EXIT`)은 틱 경로에 없다(15:20 `check_force_clear` 만).
    """
    fn = _func(ast.parse(_read(_DONCHIAN)), "check_exit_signal")
    body = ast.unparse(fn)
    markers = ["_emit_days_held_observation", "Signal.STOP_LOSS", "Signal.TRAILING_STOP"]
    idx = []
    for m in markers:
        assert m in body, f"청산 분기 마커 소실: {m}"
        idx.append(body.index(m))
    assert idx == sorted(idx), f"청산 분기 순서 변경 감지 — {list(zip(markers, idx))}"
    assert "TIME_EXIT" not in body, "시간 청산이 틱 경로에 남아 있다(다음 날 08:00 프리장 시장가 위험)"
    for dead in ("donchian_turtle_stop", "donchian_turtle_backstop", "도치안 스윙 트레일링", "_emit_time_exit"):
        assert dead not in body, f"옛 청산 분기 잔존: {dead}"


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
# G-223-11 — 8영역에 donchian 청산 심볼 유입 0건
#
# 8영역 목록은 정본(`test_cycle222a3_ast_followup_fixes.py::_EIGHT_AREAS`)에서 가져온다.
# 8영역 파일 내용 sha(무접촉)는 같은 정본의 `_APPROVED_CONTENT_SHA` 한 곳이 진다(cycle419).
# ===========================================================================
from tests.unit.ast.test_cycle222a3_ast_followup_fixes import _EIGHT_AREAS  # noqa: E402


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
# G-223-13 — `_apply_high_since_buy_from_candles` 경계 불변 (H-1 계약)
# ===========================================================================
def test_g223_13_high_recover_boundary_unchanged():
    fn = _func(ast.parse(_read(_BASE)), "_apply_high_since_buy_from_candles")
    assert fn is not None, "_apply_high_since_buy_from_candles 미발견"
    assert "pos.buy_date < bd < today" in ast.unparse(fn), (
        "H-1 과대복구 차단 경계(양쪽 strict) 변경 감지 — 이번 사이클 금기"
    )
