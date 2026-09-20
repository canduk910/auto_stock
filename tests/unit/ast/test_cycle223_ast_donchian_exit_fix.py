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
  2파일은 **파일명이 아니라 diff sha 로** 면제 (`_PREEXISTING_CONTENT_SHA`)
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
    """①하드손절/BE → ②시간청산 → ③채널이탈 → ④샹들리에. 이번엔 계산만 고친다.

    ⚠️ 사이클 237 의미 전환 — ② 의 마커가 로그 문장 `"도치안 시간 기반 청산"` 에서
    헬퍼 호출 `_emit_time_exit` 로 바뀌었다. 그 문장이 1회/ticker/일 cap 헬퍼로
    이동했기 때문이며(실측 폭주 68건/일), **분기는 같은 자리에 그대로 있다** —
    이 가드가 지키는 것은 로그 문자열의 위치가 아니라 **청산 분기의 순서**이므로
    마커만 갱신하면 강도가 보존된다(로그 서식 자체는 헬퍼 안에서 byte 동일).
    """
    fn = _func(ast.parse(_read(_DONCHIAN)), "check_exit_signal")
    body = ast.unparse(fn)
    markers = [
        "donchian_turtle_stop",       # ① 하드손절(2ATR, BE 승격 내포)
        "_emit_time_exit",            # ② 시간청산 (사이클 237 — cap 헬퍼 위임)
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
    """git 호출 — **fail-closed** (cycle222-a3 F-G).

    구현은 `.stdout` 만 읽고 `returncode` 를 검사하지 않았다. git 이 실패하면
    stdout=`""` → `changed == []` → **조용히 통과**한다. 가드가 가장 필요한
    상황(레포 손상·경로 오타·git 미설치·detached 상태)에서 정확히 초록이 되는
    구조라, 통과가 아니라 **사각**이다.
    """
    res = subprocess.run(
        ["git", *args], cwd=_REPO_ROOT, capture_output=True, text=True,
    )
    if getattr(res, "returncode", 0) != 0:
        raise AssertionError(
            f"git {' '.join(args)} 실패 (rc={res.returncode}) — 8영역 가드는 "
            "fail-closed 다. stdout 이 비면 '변경 없음' 으로 조용히 통과하므로 "
            f"여기서 멈춘다. stderr: {(res.stderr or '').strip()}"
        )
    return res.stdout


def _changed_paths(paths: list[str]) -> list[str]:
    """staged + unstaged + untracked 를 모두 포함한 변경 경로."""
    tracked = _git("diff", "HEAD", "--name-only", "--", *paths).split()
    untracked = _git("ls-files", "--others", "--exclude-standard", "--", *paths).split()
    return sorted(set(tracked) | set(untracked))


def _read_bytes(path: str) -> bytes:
    """면제 대상 파일의 **현재 내용 바이트**.

    `_content_sha` 에서 분리한 이유 = 테스트가 이 지점만 갈아끼워 "면제 파일의
    내용이 달라지면 FAIL 하는가" 를 워킹트리 오염 없이 검증할 수 있게 하려는 것.
    """
    return (_REPO_ROOT / path).read_bytes()


def _content_sha(path: str) -> str:
    """`path` **파일 내용**의 sha256 — 면제를 "지금 이 내용" 한 벌에 못박는다.

    ## 왜 diff 텍스트 해시를 버렸나 (cycle222-a3 G-2)

    1차 시정(F-D)은 `git diff` 출력에서 `index <abbrev>..<abbrev>` 줄만 걷어냈다.
    그건 **abbrev 축만** 막은 것이고, 같은 실패 클래스(코드 변경 0인데 FAIL →
    "핀 재산출" 유도 → 실제 8영역 변경까지 함께 봉인)가 그대로 남아 있었다.

    실측 — 같은 트리·같은 내용인데 diff 텍스트가 갈리는 축:

        core.abbrev=12            → 동일 (F-D 가 흡수)
        diff.algorithm=histogram  → 동일
        diff.noprefix=true        → **불일치**
        diff.mnemonicPrefix=true  → **불일치**
        diff.srcPrefix / dstPrefix→ **불일치**
        diff.context=5            → **불일치**

    `diff.noprefix=true` 는 흔한 개인 설정이다. git config 축을 하나씩 정규화하는
    싸움은 끝이 없으므로 **입력 자체를 바꾼다** — 파일 바이트를 직접 해시하면
    git 의 출력 포맷 설정 **전 축에 면역**이고, 예외의 의미
    ("이 파일이 지금 이 내용일 때만 면제") 도 더 정확히 표현된다.

    ## 자기소멸 성질은 그대로다

    면제가 조회되는 조건은 여전히 `_changed_paths`(= `git diff HEAD --name-only`
    + `ls-files --others`) 에 그 경로가 잡히는가이다. 면제 대상 작업이 커밋되면
    경로가 거기 나타나지 않아 핀은 조회조차 되지 않고, 그 뒤 누가 같은 파일을
    새로 건드리면 다시 잡혀서 sha 불일치로 FAIL 한다.
    """
    return hashlib.sha256(_read_bytes(path)).hexdigest()


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
#
# 2026-08-21 재산출 (cycle222-a3) — 같은 미커밋 작업에 적대적 검증 후속 시정이 얹혔다
# (F-A 창 상한 15:40→15:30 포함 / F-B 앵커 소유자 제외 / F-C 채택·강등 관측 로그 /
# F-E 잔여 사각 문서화). 8영역 변경 **대상**은 여전히 그 두 파일뿐이고, cycle223
# 작업이 8영역에 얹히지 않았다는 계약도 그대로다. 값만 새 스냅샷이다.
#
# 2026-08-21 재산출 2 (cycle222-a "H-3") — `handler.py` 만 갱신. 변경 내용은
# `[day_high_scope_skip]` 로그 본문의 단정("이 행의 존재 자체가 F-E 코호트")을
# **후보 신호**로 정직화한 것과, 잔여 노이즈 구간("09:00 직후 몇 초" → MAIN 고가가
# 프리장 고가를 넘을 때까지, 갭다운이면 종일)·교차 판별자 보유 한정·정밀 측정 유보를
# docstring 에 명시한 것뿐이다. **발화 조건·강등·채택 행위 diff 0** — 문구와 주석만
# 움직였다(회귀 `tests/unit/realtime/test_cycle222a3g_handler_scope_gate.py`
# `test_h3_emission_condition_and_downgrade_are_unchanged`). `risk.py` 핀은 무변경.
#
# ⚠️ cycle222-a3 G-2 — 핀 입력이 **diff 텍스트 → 파일 내용 바이트** 로 바뀌었다.
#    1차 시정(F-D)이 막은 것은 `index <abbrev>` 축뿐이었고, `diff.noprefix` /
#    `diff.mnemonicPrefix` / `diff.srcPrefix` / `diff.context` 는 여전히 코드 변경
#    0인데 핀을 깨뜨렸다(실측). 파일 바이트 해시는 git config 전 축에 면역이다.
#    ⇒ 아래 값은 `shasum -a 256 <파일>` 과 동일하다. 상세는 `_content_sha` docstring.
# ✅ 2026-08-22 — cycle222-a 가 커밋(`d2def04`)되면서 위 면제는 **자기소멸**했다.
#    두 파일은 더 이상 `git diff HEAD` 에 나타나지 않아 조회조차 되지 않는다.
#    스냅샷 값을 남겨두면 "이 8영역 변경은 승인됐다" 는 죽은 기록이 되므로 비운다.
#    기전(내용 해시 면제)은 그대로 둔다 — 다음 사이클이 같은 상황을 만나면 여기에
#    다시 핀을 걸면 되고, **빈 dict 는 곧 8영역 변경이 하나도 면제되지 않는다**는 뜻이다.
#
# 🔁 2026-08-25 (cycle227) — 예고한 "다음 사이클" 이 왔다. P0-1(BFB·VCP 가 유령 키
#    `ticker_prices["acml_vol"]` 을 읽어 전 기간 매수 0건) 시정 Stage 0 이
#    **사용자 명시 승인**으로 8영역 2파일을 건드린다(`_workspace/red/
#    cycle227_acml_vol_stage0_spec.md` 머리말: "8영역 수정 승인 = handler.py +
#    risk.py 두 파일 한정"). 변경은 순수 추가다 —
#      · `handler.py`  = `_parse_acml_vol`(fields[13], 실패 시 **-1** sentinel) +
#                        `_handle_tick` 이 `acml_vol=` 키워드로 전달.
#                        `len(fields) < 10` 가드 byte 불변(AST-3 가 별도 봉인).
#      · `risk.py`     = `on_tick(*, acml_vol: int = -1)` 수용 + `acml_vol >= 0`
#                        일 때만 `tick_volume.record_acml_vol` 기록.
#                        **`ticker_prices` 4키 불변**(donchian `ext_pct` 커플링 —
#                        AST-1 이 전 소스에서 대입 0건을 영구 강제).
#    핀은 여전히 파일명이 아니라 **이 내용 한 벌**에 걸린다: cycle227 이 커밋되면
#    두 경로는 `git diff HEAD` 에 나타나지 않아 조회조차 되지 않고(자기소멸),
#    커밋 전에 누가 같은 파일을 더 건드리면 sha 불일치로 FAIL 한다.
# TODO(cycle227 커밋 후): 아래 두 항목을 **삭제**하고 dict 를 다시 비운다.
# ✅ 2026-08-27 — cycle227 항목(risk.py·handler.py)은 커밋 `a7245af` 로 **자기소멸**
#    했다(죽은 값 삭제, TODO 이행). 빈 dict = 8영역 변경이 하나도 면제되지 않는다.
#    cycle228 은 8영역 무접촉이라 신규 핀이 없다.
# ✅ 2026-09-02 — cycle235 항목(handler.py·order_engine.py·realtime/CLAUDE.md)은
#    커밋 f2b831f 로 자기소멸, 삭제 (더 이상 `git diff HEAD` 에 나타나지 않는다).
#
# 🔁 2026-09-02 (cycle238) — 프리장 청산 보류 게이트 08:00 정각 ~30초 구멍 시정의
#    사용자 명시 8영역 승인("P1-6 은 A 로 진행", 범위 = `risk.py` 단독).
#    `_defers_pre_market_exit` OR 판정(시각 폴백 `_pre_market_only_by_clock`
#    + `session_tracker.active`) + `_maybe_emit_pre_market_gate_divergence`.
#    명세 = `_workspace/red/cycle238_pre_market_clock_gate_spec.md`.
# TODO(cycle238 커밋 후): 아래 항목을 **삭제**하고 dict 를 다시 비운다.
# ✅ 2026-09-11 (cycle276) — AI 매수평가 주문 발화 시점 이동. 사용자 명시 승인
#    범위 = `src/engine/order_engine.py` **단독**(import 1줄 + `execute_buy` 두 매수
#    경로의 관측 훅 2곳). A-ATOMIC 구간 byte 동일, 매도 경로 훅 0건.
# TODO(cycle276 커밋 후): 아래 항목을 **삭제**하고 dict 를 다시 비운다.
# ✅ 2026-09-11 (cycle283) — 저녁 창 재설계. 사용자 명시 승인 범위 = `src/engine/scanner.py`
#    **단독**(커트오프 상수 `_DAILY_LOAD_TODAY_BAR_CUTOFF` 15:40 → 20:00 + 근거 주석·
#    docstring 정직화). 판정식 2줄은 **텍스트 동일**이고 나머지 7영역은 diff 0 이다.
#    자매 가드 **네 곳 전부**에 같은 값으로 핀한다.
# TODO(cycle283 커밋 후): 아래 항목을 **삭제**한다.
# ✅ 2026-09-12 (cycle286, C4-a) — `nxt_tradable=False` 사후 보강 판정축 교체
#    (거래소 ∧ 좁힌 프리장 창). 사용자 명시 8영역 승인. 자매 가드 네 곳 전부 같은
#    값(`test_g3_9b` 계약). TODO(cycle286 커밋 후): 아래 항목을 **삭제**한다.
# ✅ 2026-09-12 (cycle287) — 시각이 거래소·호가유형을 정한다. 사용자 명시 8영역
#    승인, 범위 = `order_engine.py` + `api/order.py`(docstring 만). 자매 가드
#    네 곳 전부 같은 값. TODO(cycle287 커밋 후): 아래 항목을 **삭제**한다.
_PREEXISTING_CONTENT_SHA: dict[str, str] = {
    # ✅ 2026-09-18 (cycle302) 재핀 — 일봉 backfill 의 **대상**을 지수에서 적재 대상
    #    전부로 확대. 사용자 명시 8영역 승인("전부 담는게 좋을듯한데? VCP평가대상이
    #    어떻게 바뀔지 모르잖아"), 범위 = `src/engine/scanner.py` **단독**이고 이
    #    사이클의 프로덕션 변경은 이 한 파일뿐이다. 바뀐 것 = backfill 분기에서 지수
    #    소속 판정 제거 + 그 판정에만 쓰이던 `vcp_universe_tickers` 집합 소멸.
    #    목표 깊이 상수(`_DAILY_LOAD_VCP_BACKFILL_DAYS`=225)는 그대로다.
    #    나머지 7영역과 `scheduler.py` 는 diff 0.
    #    자매 가드 **네 곳 전부** 같은 값(`test_g3_9b` 계약).
    #    TODO(cycle302 커밋 후): 이 항목을 **삭제**한다.
    "src/engine/scanner.py":
        "95cbb103a38821bb3b68d267a3662094b192fa55ad6071fa8dc4a63726e1c942",
    "src/engine/order_engine.py":
        "e1beeb1fffab6ca5193d6954e9164e75f1d0d16eaaaedbcbb7d3fef1328dfa2e",
    "src/api/order.py":
        "08c5cafd7b8678ec0d0fa85f856fdea3cce38ad92488c6d74c03cd13faa415bb",
    # ✅ 2026-09-14 (cycle293) — 시세 채널 리졸버 2단계(속성축 배관). 사용자 승인
    #    8영역 4파일(`scanner`·`websocket`·`websocket_pool`·`order_engine`) +
    #    §3-E B-1 매수 축 보존 게이트 때문에 `risk.py` 1건(별도 승인 대상, 근거는
    #    `test_cycle293_ast_channel_resolver.py::test_a1b` docstring).
    #    자매 가드 **네 곳 전부** 같은 값이어야 한다(`_PIN_GUARD_FILES` 정본).
    #    등록은 승인된 사이클의 Green 이, 비우기는 병합 후속 커밋이 한다.
    "src/engine/risk.py":
        "e8614235cc0bea638f8c349b2f6910c94f5f9a5b849f5d65bef0583f959d81c9",
    "src/realtime/websocket.py":
        "d4c443bde2ed7aeafba3e9471db0ca4efc15a654610555435145a9b305150c5b",
    "src/realtime/websocket_pool.py":
        "8b02442bcf5f558d6f7095b47d2016f004e3746e07ddc91dae8768b1dd46a10d",
    # 📄 2026-09-14 (cycle293) — **문서 전용 변경**(`src/realtime/**` 이 8영역 디렉터리라
    #    `.md` 도 이 가드에 잡힌다). 「시세 채널」 절이 속성축 리졸버 2단계 착지·프로브
    #    격리 기준 전환·`get_subscribed_tickers()` 합집합 서술을 담도록 갱신됐다.
    #    프로덕션 코드 영향 0. 등록은 Green 이, 비우기는 병합 후속 커밋이 한다.
    # 📄 2026-09-15 (cycle295, A축) — **문서 전용 변경**. 갭 홀드 CRITICAL-1 절이
    #    철회 서술로 재작성됐고(§6-4 — 삭제 아님), 다이얼 표·런북 curl·전환 창
    #    라벨이 「전환 1회」로 되돌아갔다. 프로덕션 코드 영향 0(이 사이클의 코드
    #    영향은 8영역 밖 4파일 — `_APPROVED_CONTENT_SHA` 대상이 아니다).
    # 📄 2026-09-17 — **문서 전용 변경**(덧칠 정리). 경위·실측 수치·폐기 값은
    #    `docs/history/src-realtime-CLAUDE.history.md` 로 verbatim 이관하고 정본엔
    #    현재 계약만 남겼다. 프로덕션 코드 영향 0.
    "src/realtime/CLAUDE.md":
        "871b5e21531e346c016ae9514b2c1c27d511097e17d9464d8701289215f52eac",
    # ✅ 2026-09-17 (cycle296) — `TokenManager.issue()` 매니저 단위 in-flight
    #    합류. 사용자 명시 8영역 승인(`src/auth/**`), 범위 = `src/auth/token.py`
    #    `issue()` + `__init__` 신규 필드뿐(`get_token`/`revoke`/`_is_valid` 무접촉).
    #    자매 가드 네 곳 전부 같은 값(`test_g3_9b`/`test_g223f_9`/`test_g223_10` 계약).
    #    TODO(cycle296 커밋 후): 아래 항목을 **삭제**한다.
    "src/auth/token.py":
        "4125c271b4147e59922f4f000e523429fb4bbef37058dc754fd92b9475ec58f1",
    # 📄 2026-09-17 — **문서 전용 변경**(`src/auth/**` 이 8영역 디렉터리라 `.md` 도
    #    이 가드에 잡힌다 — `src/realtime/CLAUDE.md` 와 같은 계열). 소제목의 사이클
    #    번호를 규칙 이름으로 바꾸고, 걷어낸 경위를 `docs/history/src-auth-CLAUDE.history.md`
    #    로 옮겼다(정본 규약 = 루트 `CLAUDE.md` 「문서 규약」 절). 프로덕션 코드 영향 0.
    #    자매 가드 네 곳 전부 같은 값(`test_g3_9b` 계약).
    #    TODO(커밋 후): 아래 항목을 **삭제**한다.
    "src/auth/CLAUDE.md":
        "1d155e95d386b3ecb19f138e966464490ac4912b055f1f8f9da2a154d14ea363",
    # ✅ 2026-09-20 (cycle329) — 체결통보 **주문수량**(`fields[16] ODER_QTY`) 배선.
    #    사용자 결정("체결통보 주문수량 쓰자") + `domain-consult` 선행. 고치는 것 =
    #    `await place_order` 가 걸려 있는 동안 착지한 통보는 `order_no` 매핑이 아직
    #    비어 `ordered_qty` 가 **증분 체결량으로 폴백**되고, 그러면
    #    `total_filled >= ordered_qty` 가 항상 참이 되어 **부분 체결이 전량으로 오판**된다.
    #    매도는 미체결 잔량이 손절 감시 밖으로 사라지고, 매수는 `_completed_buy_orders`
    #    가 무장해 잔여 통보가 조용히 버려진 채 영원히 적은 수량으로 믿는다.
    #    `handler.py` 변경은 **파싱 1블록 + 콜백 인자 1개**뿐이다 — 체결수량 소스
    #    `fields[9]` 는 무접촉이고 `test_cycle235_ast_execution_qty.py` 가 그대로 봉인한다.
    #    자매 가드 **세 곳 전부** 같은 값(`test_g3_9b` 계약).
    #    TODO(cycle329 커밋 후): 이 항목을 **삭제**한다.
    "src/realtime/handler.py":
        "37b1755210c83cdb2a462e6a37f919b326f8b48bee73d924adcc277d770a8d17",
}


def test_g223_10_eight_areas_diff_zero():
    changed = _changed_paths(_EIGHT_AREAS)
    unexpected = sorted(set(changed) - set(_PREEXISTING_CONTENT_SHA))
    assert unexpected == [], f"8영역 신규 변경 감지 — 범위 밖: {unexpected}"
    for path in sorted(set(changed) & set(_PREEXISTING_CONTENT_SHA)):
        assert _content_sha(path) == _PREEXISTING_CONTENT_SHA[path], (
            f"{path} 의 내용이 면제 스냅샷과 다르다.\n"
            "⚠️ **핀을 먼저 재산출하지 마라** — 그 순간 8영역 실제 변경이 그대로 "
            "새 스냅샷으로 봉인된다.\n"
            f"  1) `git diff HEAD -- {path}` 를 눈으로 읽고 이번 사이클이 얹은 변경이 "
            "있는지 확인하라.\n"
            "  2) 얹혀 있으면 그 변경을 되돌려라(8영역 diff 0 이 계약이다).\n"
            "  3) 면제 대상 작업(cycle222-a) 자체가 갱신된 것이 확실할 때만 핀을 "
            "재산출한다.\n"
            "면제는 파일명이 아니라 **이 파일 내용 한 벌**에만 걸린다. "
            "핀은 파일 바이트 해시라 git config(diff.noprefix / context / abbrev …) "
            "에 면역이므로 '코드 무변경인데 깨짐' 은 원인이 될 수 없다(G-2)."
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
# 🔁 2026-08-25 (cycle227) — 이 가드는 원래 면제 기전이 **없었다**(`out == ""` 단정).
#    cycle227 이 BFB·VCP 에 관측 훅을 넣으면서(사용자 승인 범위) 내용 sha 핀
#    (자기소멸)을 이식했다. 그 항목은 커밋 `a7245af` 로 자기소멸했다.
# 🔁 2026-08-27 (cycle228) — 게이트 전환 + 충족 래치(사용자 승인, 명세
#    `_workspace/red/cycle228_gate_latch_spec.md`)로 같은 두 파일을 다시 승인
#    수정하며 재핀. 파일명 집합 면제는 **영구**라 쓰지 않는다 — 핀에 없는 전략
#    파일이 바뀌면 즉시 FAIL, 핀에 있는 파일도 1 byte 달라지면 FAIL.
# 🔁 2026-08-29 — cycle229 커밋(6d4bc22)으로 VB·momentum 항목 자기소멸.
#    cycle231(P2-5 — kojiro `_held_stage3` 날짜 키 무효화, 자문
#    cycle231_kojiro_stage3_stale.md, 사용자 승인)이 kojiro 를 수정하며 재핀.
# 🔁 2026-08-29 (2차) — cycle231 커밋(84f5867)으로 kojiro 구항목 자기소멸 확인 후 삭제.
#    cycle233(G3′ 계좌 리스크 패키지 — 자문 cycle232_risk_control_review.md,
#    사용자 결정 "A시작")이 6전략 전부를 승인 수정하며 재핀:
#    check_buy_signal 최상단 계좌 SOFT 게이트 1줄(전 전략) + 실효 손절선 read-only
#    미러 get_effective_stop_price(kojiro/VCP/BFB — donchian 은 별도 가드 소관).
# 🔁 2026-09-03 (cycle242) — cycle233 항목이 아직 미커밋인 채로 G0-ⓑ(피라미딩
#    심층 검토 §0.0, `_workspace/red/cycle242_fallback_notional_cap_spec.md`)가
#    kojiro/vcp/bfb 3 파일에 `DEFAULT_PARAMS["max_lot_units"]=2.0` 1줄만 승인
#    추가하며 같은 3 항목을 재핀(momentum/VB/LTV 는 cycle242 무접촉 — 범위 밖
#    선언, 값 무변경). TODO(cycle233+242 커밋 후): 아래 항목을 **전부 삭제**하고
#    dict 를 비운다.
# 🔁 2026-09-04 (cycle245) — cycle233+242 항목이 아직 미커밋인 채로 ρ축 랏 명목 상한
#    (`_workspace/red/cycle245_ratio_notional_cap_spec.md` §2.6 결정 ⑩, 사용자 결정
#    "K=2.0 유지하고 cycle245 도 진행해줘")이 **6 파일 전부**에
#    `DEFAULT_PARAMS["max_lot_ratio_mult"]=2.5` 1줄만 승인 추가하며 6 항목을 재핀.
#    재핀 전 `git diff HEAD -- src/engine/strategies/` 로 7 파일 각 +1/−0 (같은 1줄)
#    임을 눈으로 확인했다(가드 절차 1·2). donchian_swing.py 는 이 dict 소관이 아니다.
# 🔁 2026-09-06 (cycle262) — 09:00 직후 진입 보류 `open_entry_hold_secs`
#    (자문 정본 `_workspace/consult/2026-09-06_open_entry_hold.md`, 사용자 결정 09-06
#    카드 ② '조사와 임시 매수 보류 함께' · 범위 = VB + LTV 둘 다)가 두 파일을 승인
#    수정하며 재핀. 8영역·`scheduler.py`·나머지 전략 5파일은 diff 0 이다.
#    재핀 전 `git diff HEAD -- src/engine/strategies/` 로 두 파일의 변경이 이 사이클
#    범위(DEFAULT_PARAMS 키 1 + 모듈 상수 2 + cap 필드 2 + 카나리아/판정 2 지점 +
#    헬퍼 3)뿐임을 눈으로 확인했다(가드 절차 1·2).
#    ⚠️ 2026-09-06 적대 검증 반영으로 두 파일이 재기록됐고(읽기 `except` 를 bare
#    `Exception` 으로 확대 — `1e400` 이 유효 JSON 이라 `int(inf)` → `OverflowError` 가
#    전파되던 HIGH 시정 + `source` 라벨 의미 명시 + 두 emit 순서·흡수기 폭 봉인), 이
#    핀은 **커밋 직전 마지막 단계**에 `shasum -a 256` 으로 재산출한 값이다.
#    ⚠️ LTV 카나리아를 계좌 게이트 **앞**으로 옮기는 적대 검증 권고는 **불수용**했다 —
#    LTV 는 cycle233 `GATE_FIRST_FILES` 멤버라 게이트 If 가 `check_buy_signal` 첫
#    문장이어야 하고(`test_cycle233_ast_account_risk.py`) 로그 emit 은 부작용이라 그
#    앞에 올 수 없다(실측 RED). 비대칭은 문서화 + `test_c7_8` 로 고정했다.
#    TODO(cycle262 커밋 후): 아래 두 항목을 **삭제**하고 dict 를 다시 비운다
#    (남겨 두면 다음에 VB/LTV 를 정당하게 건드리는 사이클이 "사이클228 게이트 전환"
#    면제 문구가 붙은 오해 소지 있는 실패 메시지를 받는다 — 09-05 카드 #3 재발 방지).
#    워크리스트 "커밋 직후 정리 체크리스트" 1번 항목이 정본이다.
# ✅ 2026-09-07 — cycle268 항목(kojiro.py)은 커밋 `a77f9c3` 으로 **자기소멸**했다
#    (`git diff HEAD` 에 더 이상 나타나지 않는다). 스냅샷을 남겨 두면 (a) `test_g3_8`
#    이 첫 커밋된 항목에서 통째로 skip 돼 나머지 핀의 스테일 탐지가 조용히 죽고
#    (b) 다음에 kojiro.py 를 정당하게 건드리는 사이클이 "cycle268 면제" 문구가 붙은
#    오해 소지 있는 실패를 받아 **핀 재산출로 유도된다**(09-05 카드 #3 재발). 그래서 비운다.
#
# 🔁 2026-09-10 (cycle272) — 사용자 결정 D1(REST 기준가) 구현이 VB·LTV
#    `on_open_price_confirmed` 에 출처 게이트(`open_price_rest.reject_untrusted_main_basis`)
#    1줄 + `DEFAULT_PARAMS["open_price_scope_mode"]="enforce"` 1줄만 승인 추가하며
#    두 파일을 재핀. `check_buy_signal`/`check_exit_signal`/`calc_buy_quantity` 는
#    `source` 기본값을 `"ws"`(불신)로 둬 **한 글자도 바뀌지 않는다**
#    (`test_cycle264_scope_and_pins.py::_STRATEGY_PINS` 6개 sha 불변이 그 증거).
#    8영역·`scheduler.py` 는 별도 라인 상한 가드(`test_cycle272_ast_main_rest_basis.py`)로
#    diff 0 을 기계적으로 강제한다. 명세 = `_workspace/red/cycle272_rest_open_basis_spec.md`.
#    TODO(cycle272 커밋 후): 아래 두 항목을 **삭제**하고 dict 를 다시 비운다.
# ✅ 2026-09-10 — cycle273 J2 273c (D3, `_workspace/red/cycle273c_kojiro_rank_restore_spec.md`):
#    `_rank_candidate_components` 성분①②(macd3 기울기%·띠폭 확장률) 원설계 복원 +
#    OQ-5 nan/inf 중립화 + shadow 관측 `[kojiro_band_observe]` 배선. 가중치·자격
#    게이트·청산 무접촉(C9 후보 집합 불변·C10 진입/수량/청산 sha 불변으로 실증).
#    TODO(cycle273 커밋 후): 아래 항목을 **삭제**하고 dict 를 다시 비운다.
# ✅ 2026-09-11 — cycle276 (AI 매수평가 주문 시점 이동,
#    `_workspace/red/cycle276_order_time_llm_eval_spec.md`): cycle274 의 전략 배선을
#    **원상 복구**하고 훅을 `order_engine.execute_buy` 로 옮겼다. VB·LTV 에 남는 것은
#    `DEFAULT_PARAMS` 4키(설정 표면이자 킬스위치 — order_engine 이 `config.params`
#    로 읽는다)뿐이라 **메서드 6핀은 cycle272 값으로 복귀**하고 **파일 sha 만** 다르다.
#    그 방향 차이가 이 사이클의 미묘한 지점이다.
#    TODO(cycle276 커밋 후): 아래 두 항목을 **삭제**하고 dict 를 다시 비운다.
# ✅ 2026-09-12 (cycle286, C2-a) — LTV `main` 보드 신규 매수 15:20 컷. 사용자 승인
#    범위 = `src/engine/strategies/long_tail_volatility.py` 단독. 추가는 모듈 상수
#    `MAIN_BUY_CUTOFF_KST` + 헬퍼 `_main_buy_cutoff_blocked` + emit cap 필드 1개 +
#    `check_buy_signal` 발사점(cycle262 hold 블록 직후) 신규 게이트 블록뿐이다.
#    `check_exit_signal`/`calc_buy_quantity`/`prepare`/`on_open_price_confirmed`
#    는 byte 동일(`tests/unit/ast/test_cycle286_ast_scope.py::_LTV_FROZEN_METHODS`).
#    TODO(cycle286 커밋 후): 아래 LTV 항목을 **삭제**하고 dict 를 다시 비운다.
# ✅ 2026-09-13 (cycle290) — 장중 킬스위치 두 키 등재. 사용자 결정("나머지는 권고대로")
#    + 도메인 자문 조건부 GO. **7 전략 전부**의 `DEFAULT_PARAMS` 말미에
#    `order_exchange_clock_mode`·`after_market_exit_division` 2줄만 추가(값은
#    `order_engine` 모듈 상수와 동일 — 매매 행위 변경 0). 세그먼트(진입/청산/사이징/
#    준비) 28핀은 `test_cycle290_ast_scope.py::test_g290_2` 가 별도로 불변 증명한다.
#    그동안 이 dict 에 없던 momentum·vcp_breakout·bull_flag_breakout 3 항목을 신규
#    등록(이전 사이클들은 이 세 파일을 건드리지 않았다). donchian_swing.py 는 여전히
#    이 dict 소관이 아니다(파일 상단 `_BASE` — 별도 세그먼트 가드로 다룬다).
#    TODO(cycle290 커밋 후): 이 항목들 삭제하고 dict 를 다시 비운다.
_CYCLE228_STRATEGY_CONTENT_SHA: dict[str, str] = {
    "src/engine/strategies/volatility_breakout.py":
        "d13efaa4a9424e2822b5476ce159987d2a5192a4bca30af3f1a0cae9c3ffcabc",
    "src/engine/strategies/long_tail_volatility.py":
        "51b50560a1240df3fc6085da7253438605079d7d453ff3e77a806e814473be25",
    "src/engine/strategies/kojiro.py":
        "9477790e9d20eb6d17f36fc7586ada77ac5e2e4b0136a334888244afdb7e9cbc",
    "src/engine/strategies/momentum.py":
        "50d5c0b9a232d6110f6b85fc524569853f2b8edffe2fd44adc24289800b95ae2",
    "src/engine/strategies/vcp_breakout.py":
        "5b324b34335f922f82b848ae2313e08660bde75c02d12432867ed224e9709228",
    "src/engine/strategies/bull_flag_breakout.py":
        "0feb3b629bab5ad08ad589315ca12e76b57a73950b948570a78dfe84ba792595",
}


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
    changed = _changed_paths(existing)
    unexpected = sorted(set(changed) - set(_CYCLE228_STRATEGY_CONTENT_SHA))
    assert unexpected == [], f"다른 전략 파일 변경 감지 — 범위 밖: {unexpected}"
    for path in sorted(set(changed) & set(_CYCLE228_STRATEGY_CONTENT_SHA)):
        assert _content_sha(path) == _CYCLE228_STRATEGY_CONTENT_SHA[path], (
            f"{path} 의 내용이 면제 스냅샷과 다르다.\n"
            "⚠️ **핀을 먼저 재산출하지 마라** — 그 순간 실제 변경이 그대로 새 "
            "스냅샷으로 봉인된다.\n"
            f"  1) `git diff HEAD -- {path}` 를 눈으로 읽어라.\n"
            "  2) 이번 사이클이 얹은 범위 밖 변경이면 되돌려라.\n"
            "  3) 면제 대상 작업(cycle228 게이트 전환·래치) 자체가 갱신된 것이 확실할 "
            f"때만 재산출한다 (`shasum -a 256 {path}`)."
        )


# ===========================================================================
# G-223-13 — `_apply_high_since_buy_from_candles` 경계 불변 (H-1 계약)
# ===========================================================================
def test_g223_13_high_recover_boundary_unchanged():
    fn = _func(ast.parse(_read(_BASE)), "_apply_high_since_buy_from_candles")
    assert fn is not None, "_apply_high_since_buy_from_candles 미발견"
    assert "pos.buy_date < bd < today" in ast.unparse(fn), (
        "H-1 과대복구 차단 경계(양쪽 strict) 변경 감지 — 이번 사이클 금기"
    )
