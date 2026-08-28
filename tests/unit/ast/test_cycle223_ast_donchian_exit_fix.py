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
_PREEXISTING_CONTENT_SHA: dict[str, str] = {}


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
# 🔁 2026-08-28 — cycle228-A 커밋(`4e7b302`) 후 228-B(setup 리졸버, 같은 두 파일)
#    승인 수정으로 재핀. TODO(cycle228-B 커밋 후): 아래 두 항목을 **삭제**하고 dict 를 비운다.
_CYCLE228_STRATEGY_CONTENT_SHA: dict[str, str] = {
    "src/engine/strategies/bull_flag_breakout.py":
        "cfa6789358497609a56defc66cea56884d33c5e238d579ffb874e4995775ac3b",
    "src/engine/strategies/vcp_breakout.py":
        "fc664feaae2c8cda34fd8265966b5b1f59ea2ae82c101c4ae802aa686d49039c",
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
