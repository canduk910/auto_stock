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
_PREEXISTING_CONTENT_SHA: dict[str, str] = {
    # (비어 있음 — cycle273 그룹 1·2, cycle274 병합 뒤 2026-09-11 정리. 등록은 승인된 사이클의 Green 이, 비우기는 병합 후속 커밋이 한다)
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
