"""사이클 223-F Red/가드 (AST) — 리뷰 지적 4건의 범위 봉인.

- G-223F-1 (F2): `routes/recommendations.py` apply 경로가 **`PARAM_RANGES` 를 참조**한다
- G-223F-2 (F2): 화이트리스트 교집합이 `valid_keys` 산출에 실제로 들어간다
- G-223F-3 (F2): 스킵 로그 태그가 자동 경로 `[auto_apply_safeguard_skip]` 와 같은 계열
- G-223F-4 (F2): `apply_weight` 경로 불변 (Σ 사전검증 `[weight_sum_violation]` 잔존)
- G-223F-5 (F1): `_business_days_held` 는 여전히 **동기·I/O 0** (hot path 계약)
- G-223F-6 (F1→G 의미 전환): 캐시 분기의 갭 기여는 **오늘 하루**로 한정된다
  (weekday 순회 루프 재유입 금지 — 공휴일 다음 첫 거래일 과다 계상 봉인)
- G-223F-7 (F4): 폴백 가시성이 `DailyEmitCap` 으로 cap 돼 있다 (hot path 폭주 차단)
- G-223F-8 (F3): `atr_trail_mult` 제외 주석이 **3전략 공유 키**임을 명시한다
- G-223F-9 (HIGH): 8영역 diff 0 — staged + unstaged + untracked 전부 (사이클 223 G3).
  cycle222-a pre-existing 2파일은 diff sha 핀으로 면제 (파일명 영구 면제 금지)
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
_ROUTE = _SRC / "routes" / "recommendations.py"
_RECO = _SRC / "engine" / "recommendation_engine.py"
_DONCHIAN = _SRC / "engine" / "strategies" / "donchian_swing.py"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _func(tree: ast.Module, name: str):
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    return None


# ===========================================================================
# G-223F-1/2/3 (F2) — 수동 apply 화이트리스트 재검증
# ===========================================================================
def test_g223f_1_apply_route_references_param_ranges():
    fn = _func(ast.parse(_read(_ROUTE)), "apply_rec")
    assert fn is not None, "apply_rec 미발견"
    body = ast.unparse(fn)
    assert "PARAM_RANGES" in body, (
        "F2: 수동 apply 경로가 PARAM_RANGES 화이트리스트를 재검증해야 한다 "
        "(자동 경로 `auto_apply_recommendations` 에만 있던 가드)"
    )


def test_g223f_2_valid_keys_is_intersected_with_whitelist():
    """`valid_keys` 대입 시점에 화이트리스트가 반영돼야 한다 (사후 필터 누락 차단)."""
    fn = _func(ast.parse(_read(_ROUTE)), "apply_rec")
    for node in ast.walk(fn):
        target_names = []
        if isinstance(node, ast.Assign):
            target_names = [t.id for t in node.targets if isinstance(t, ast.Name)]
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            target_names = [node.target.id]
        if "valid_keys" in target_names and node.value is not None:
            assert "PARAM_RANGES" in ast.unparse(node.value), (
                "F2: `valid_keys` 산출식에 PARAM_RANGES 교집합이 없다 — "
                f"got `{ast.unparse(node)}`"
            )
            return
    pytest.fail("apply_rec 안에서 `valid_keys` 대입을 찾지 못했다 (탐지기 결함)")


def test_g223f_3_skip_log_tag_matches_auto_path_family():
    """자동 경로 `[auto_apply_safeguard_skip] key=… reason='out_of_param_ranges'` 계열."""
    route_src = _read(_ROUTE)
    assert "[manual_apply_safeguard_skip]" in route_src, (
        "F2: 스킵 로그 태그 부재 — 자동 경로와 같은 계열 `[manual_apply_safeguard_skip]`"
    )
    assert "out_of_param_ranges" in route_src, "F2: 스킵 사유 문자열 부재"
    # 자동 경로 원본 태그도 살아 있어야 한다 (양쪽 grep 가능)
    assert "[auto_apply_safeguard_skip]" in _read(_RECO)


def test_g223f_4_apply_weight_path_unchanged():
    """`apply_weight` 경로는 이번 범위 밖 — N1 Σ 사전검증 잔존 확인."""
    src = _read(_ROUTE)
    assert "[weight_sum_violation]" in src, "apply_weight Σ 사전검증(N1) 소실 감지"
    assert "save_weights" in src


# ===========================================================================
# G-223F-5/6 (F1) — hot path 계약 + `+1` 특수 케이스 흡수
# ===========================================================================
def test_g223f_5_business_days_helper_still_sync_and_pure():
    fn = _func(ast.parse(_read(_DONCHIAN)), "_business_days_held")
    assert fn is not None
    assert not isinstance(fn, ast.AsyncFunctionDef)
    assert not [n for n in ast.walk(fn) if isinstance(n, ast.Await)]
    body = ast.unparse(fn)
    for banned in ("fetch_daily_candles", "add_business_days", "pg.fetch", "pg.execute",
                   "write_log", "httpx", "kis_request", "asyncio"):
        assert banned not in body, f"F1: `_business_days_held` 에 I/O `{banned}` 금지"


def _code_only(fn) -> str:
    """docstring 을 제외한 **코드만** unparse (선례: sector_naming 중복 재발 가드).

    결함 서술을 docstring 에 남기는 것은 권장 사항이므로 탐지 대상에서 뺀다.
    """
    stmts = list(fn.body)
    if (
        stmts and isinstance(stmts[0], ast.Expr)
        and isinstance(stmts[0].value, ast.Constant)
        and isinstance(stmts[0].value.value, str)
    ):
        stmts = stmts[1:]
    return "\n".join(ast.unparse(n) for n in stmts)


def test_g223f_6_gap_contribution_capped_at_today():
    """캐시 분기의 갭 기여는 **오늘 하루**로 한정된다 (사이클 223 G 의미 전환).

    F1 은 여기서 `today not in cache` 특수 케이스의 **제거**를 요구했다 — 갭을
    weekday 로 메우는 일반화로 흡수한다는 계약이었다. 그 일반화가 "캐시 밖 갭의
    원인은 항상 스테일" 을 가정하는데, 라이브 세션 중 `cache_max` 는 구조적으로
    직전 거래일이라(호출부 = `prepare`/`recompute_held_atr` 뿐) **공휴일이 끼면
    갭의 원인은 휴장**이다. 그래서 공휴일 다음 첫 거래일마다 과다 계상(조기 청산)이
    됐고, 그건 연 12~15회 되풀이되는 캘린더 이벤트다.

    바뀐 것은 값이 아니라 **가정**이다. 이 가드는 이제 반대 방향을 봉인한다:
    캐시 분기에 weekday 순회 루프가 되살아나면 과다 계상이 재발한다.
    `cache_max` 는 계상이 아니라 `used_fallback` 판정(F1 의 가시성 절반)에 남는다.
    """
    fn = _func(ast.parse(_read(_DONCHIAN)), "_business_days_held")
    body = _code_only(fn)
    cache_branch = None
    for node in fn.body:
        if isinstance(node, ast.If) and "cache_max" in ast.unparse(node):
            cache_branch = node
            break
    assert cache_branch is not None, "캐시 분기 미발견 (탐지기 결함)"
    assert not [n for n in ast.walk(cache_branch) if isinstance(n, (ast.While, ast.For))], (
        "G: 캐시 분기의 weekday 순회 루프 = 공휴일 과다 계상 재발 — 갭은 오늘 하루뿐"
    )
    assert "today not in cache" in body, (
        "G: 갭 기여를 오늘 하루로 한정하는 가드가 있어야 한다 "
        "(휴장/스테일 판별 불가 — 오늘만 활성 세션이라 영업일 보장)"
    )
    assert "max(cache" in body or "cache_max" in body, (
        "F1(유지): 캐시 최신일(max) 을 봐야 열화(`used_fallback`)를 드러낼 수 있다"
    )


# ===========================================================================
# G-223F-7 (F4) — 폴백 가시성 cap
# ===========================================================================
def test_g223f_7_fallback_log_is_daily_capped():
    src = _read(_DONCHIAN)
    assert "DailyEmitCap" in src, (
        "F4: 폴백 가시성은 hot path 폭주 없이 — `DailyEmitCap` 선례 사용"
    )
    fn = _func(ast.parse(src), "check_exit_signal")
    body = ast.unparse(fn)
    assert "should_emit" in body or "_emit_days_held_fallback" in body, (
        "F4: 폴백 emit 이 cap 을 경유해야 한다"
    )
    # hot path 계약은 그대로
    assert not [n for n in ast.walk(fn) if isinstance(n, ast.Await)]


# ===========================================================================
# G-223F-8 (F3) — 공유 키 적용 범위 명시
# ===========================================================================
def test_g223f_8_atr_trail_mult_shared_scope_documented():
    """`atr_trail_mult` 은 donchian 전용이 아니라 **3전략 공유 키**다.

    S1 의 PARAM_RANGES 제거는 VCP·BFB 의 샹들리에 배수까지 AI 튜닝에서 함께 뺀다.
    오늘은 무해(VCP/BFB 체결 0건)하나, 제거 사유 주석이 donchian 실측만 근거로 들면
    두 전략 체결 개시 후 donchian 표본만으로 내린 결정이 그들 청산 규약을 영구 고정한다.
    선례: `kojiro.py` 의 "atr_trail_mult 재사용 금지" 주석이 같은 함정을 피했다.
    """
    src = _read(_RECO)
    comments = "\n".join(ln.strip() for ln in src.splitlines() if ln.strip().startswith("#"))
    for token in ("vcp_breakout", "bull_flag_breakout"):
        assert token in comments, (
            f"F3: `atr_trail_mult` 제거가 '{token}' 까지 걸린다는 사실이 주석에 없다"
        )
    assert "재검토" in comments, "F3: VCP/BFB 체결 개시 시 재검토 조건 명시 의무"


# ===========================================================================
# G-223F-9 (HIGH) — 8영역 diff 0
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
# 🔁 2026-08-25 (cycle227) — P0-1 Stage 0 이 **사용자 명시 승인**으로 8영역 2파일을
#    건드린다(`handler.py` = `_parse_acml_vol` + `acml_vol=` 키워드 전달 /
#    `risk.py` = `on_tick(*, acml_vol=-1)` 수용 + `tick_volume` 기록). 둘 다 순수
#    추가이고 `ticker_prices` 4키는 불변이다(donchian `ext_pct` 커플링 — 신규
#    AST-1 가드가 전 소스에서 `acml_vol` 대입 0건을 영구 강제).
#    자매 가드 `test_cycle223_ast_donchian_exit_fix.py` 와 **같은 값**으로 핀한다 —
#    두 가드가 같은 워킹트리를 보므로 값이 갈리면 그 자체가 결함 신호다.
# TODO(cycle227 커밋 후): 아래 두 항목을 **삭제**하고 dict 를 다시 비운다.
# ✅ 2026-08-27 — cycle227 항목은 커밋 `a7245af` 로 **자기소멸**(죽은 값 삭제).
#    cycle228 은 8영역 무접촉이라 신규 핀이 없다.
# ✅ 2026-09-02 — cycle235 항목(handler.py·order_engine.py·realtime/CLAUDE.md)은
#    커밋 f2b831f 로 자기소멸, 삭제 (더 이상 `git diff HEAD` 에 나타나지 않는다).
#
# 🔁 2026-09-02 (cycle238) — 프리장 청산 보류 게이트 08:00 정각 ~30초 구멍 시정의
#    사용자 명시 8영역 승인("P1-6 은 A 로 진행", 범위 = `risk.py` 단독).
#    자매 가드 `test_cycle223_ast_donchian_exit_fix.py` 와 **같은 값**으로 핀한다.
#    명세 = `_workspace/red/cycle238_pre_market_clock_gate_spec.md`.
# TODO(cycle238 커밋 후): 아래 항목을 **삭제**하고 dict 를 다시 비운다.
# 🔁 2026-09-11 (cycle276) — AI 매수평가 주문 발화 시점 이동. 사용자 명시 승인 범위 =
#    `src/engine/order_engine.py` **단독**(import 1줄 + `execute_buy` 두 매수 경로의
#    관측 훅 2곳). 자매 가드 **네 곳 전부**에 같은 값으로 핀한다 — 한 곳만 등록하면
#    나머지가 붉어지고 그 실패 문구가 "승인된 변경을 되돌려라" 로 오도한다.
# TODO(cycle276 커밋 후): 아래 항목을 **삭제**하고 dict 를 다시 비운다.
# ✅ 2026-09-11 (cycle283) — 저녁 창 재설계. 사용자 명시 승인 범위 = `src/engine/scanner.py`
#    **단독**(커트오프 상수 `_DAILY_LOAD_TODAY_BAR_CUTOFF` 15:40 → 20:00 + 근거 주석·
#    docstring 정직화). 판정식 2줄은 **텍스트 동일**이고 나머지 7영역은 diff 0 이다.
#    자매 가드 **네 곳 전부**에 같은 값으로 핀한다.
# TODO(cycle283 커밋 후): 아래 항목을 **삭제**한다.
# ✅ 2026-09-12 (cycle286, C4-a) — `nxt_tradable=False` 사후 보강 판정축 교체
#    (거래소 ∧ 좁힌 프리장 창 08:00~08:50). 사용자 명시 8영역 승인, 범위 =
#    `src/engine/order_engine.py` 단독. 자매 가드 네 곳 전부 같은 값.
# TODO(cycle286 커밋 후): 아래 항목을 **삭제**한다.
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
    # 등록은 승인된 사이클의 Green 이, 비우기는 병합 후속 커밋이 한다.
    # (cycle273 그룹 1·2 + cycle274 항목은 병합 뒤 2026-09-11 정리했고, 아래 1건은
    #  cycle276 이 사용자 명시 승인 하에 등록했고 cycle286 이 같은 승인 하에 재핀했다.)
    # 자매 가드 **4곳**(정본 = `test_cycle223g3_ast_guard_sees_staged.py::_PIN_GUARD_FILES`)
    # 이 같은 값을 가져야 한다: `test_cycle222a3_ast_followup_fixes.py` ·
    # `test_cycle223_ast_donchian_exit_fix.py` · 이 파일 ·
    # `tests/unit/engine/strategies/test_cycle226_zero_breakout_defense.py`.
    # `test_cycle274_ast_llm_gate.py` 는 dict 이름이 `_BASE_SHA` 라 그 4곳 목록 밖이지만
    # 같은 파일을 핀하므로 함께 갱신한다(자기 가드가 따로 검사한다).
    # 🔁 2026-09-25 (cycle358) 재핀 — 카드 D(관측 전용). PARTIAL/CANCELLED UPDATE
    # `affected==0` 무흔적에 `[trade_status_update_miss]` WARNING 추가(사용자 승인,
    # 워크리스트 ⑨). 매매·상태전이 로직 무변경. 자매 가드 네 곳 전부 같은 값.
    "src/engine/order_engine.py":
        "118ebf38fd9004bf37cebf065199b949d9093d98ab9792b710b06345b5a119e3",
    # ✅ 2026-09-12 (cycle287) — 시각이 거래소·호가유형을 정한다. docstring 만
    # (본문 byte 동일). 자매 가드 네 곳 전부 같은 값.
    "src/api/order.py":
        "08c5cafd7b8678ec0d0fa85f856fdea3cce38ad92488c6d74c03cd13faa415bb",
    # ✅ 2026-09-14 (cycle293) — 시세 채널 리졸버 2단계(속성축 배관). 사용자 승인
    #    8영역 4파일(`scanner`·`websocket`·`websocket_pool`·`order_engine`) +
    #    §3-E B-1 매수 축 보존 게이트 때문에 `risk.py` 1건(별도 승인 대상, 근거는
    #    `test_cycle293_ast_channel_resolver.py::test_a1b` docstring).
    #    자매 가드 **네 곳 전부** 같은 값이어야 한다(`_PIN_GUARD_FILES` 정본).
    #    등록은 승인된 사이클의 Green 이, 비우기는 병합 후속 커밋이 한다.
    "src/engine/risk.py":
        "79fddbec8cf9315c5172fc6634c4f4ea77f525d9ff9a3aba48f321affeb4d3e8",
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
        "7c3d432254a9f71a8341d371cb14bbc8e58112a16cc536301620c7f1ab62f58d",
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


def test_g223f_9_eight_areas_diff_zero():
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
